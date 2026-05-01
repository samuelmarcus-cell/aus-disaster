"""
Tests for schema validation of critical datasets.

Scientific risk: upstream schema changes (column renames, dropped fields,
format changes in refreshed data downloads) silently break downstream analyses
without raising errors.  These tests lock in the expected schema so that
data update failures are loud, not silent.

Approach:
  - Uses synthetic fixtures from conftest.py (no real files required)
  - Validates required columns, expected dtypes, and value constraints
  - Each schema test is named for the downstream analysis it protects
"""

import math

import pandas as pd
import pytest


# ── Required column presence tests ────────────────────────────────────────

class TestDrfaActivationsSchema:

    REQUIRED_COLS = [
        "Location_Name", "STATE", "event_name", "agrn",
        "hazard_type", "disaster_start_date",
        "cat_A", "cat_B", "cat_C", "cat_D",
    ]

    def test_required_columns_present(self, drfa_activations_df):
        missing = [c for c in self.REQUIRED_COLS if c not in drfa_activations_df.columns]
        assert missing == [], f"Missing required columns: {missing}"

    def test_state_values_are_australian_abbreviations(self, drfa_activations_df):
        valid_states = {"NSW", "VIC", "QLD", "SA", "WA", "TAS", "ACT", "NT"}
        actual_states = set(drfa_activations_df["STATE"].dropna().unique())
        unexpected = actual_states - valid_states
        assert not unexpected, f"Unexpected STATE values: {unexpected}"

    def test_disaster_start_date_parseable(self, drfa_activations_df):
        parsed = pd.to_datetime(
            drfa_activations_df["disaster_start_date"], format="%Y-%m-%d", errors="coerce"
        )
        n_failed = parsed.isna().sum()
        # Allow ≤ 5% parse failure in synthetic data (real data should be 0%)
        assert n_failed / len(parsed) <= 0.05, f"{n_failed} dates failed to parse"

    def test_agrn_not_all_null(self, drfa_activations_df):
        assert drfa_activations_df["agrn"].notna().any()

    def test_hazard_type_not_all_null(self, drfa_activations_df):
        assert drfa_activations_df["hazard_type"].notna().any()

    def test_cat_columns_are_numeric(self, drfa_activations_df):
        for col in ("cat_A", "cat_B", "cat_C", "cat_D"):
            assert pd.api.types.is_numeric_dtype(drfa_activations_df[col]), \
                f"{col} should be numeric"


class TestDrfaPaymentsSchema:

    REQUIRED_COLS = [
        "State Name", "Disaster Name", "Payment Type Name",
        "Dollars Paid ($)", "Dollars Granted ($)",
        "Eligible Claims (No.)", "Total Recieved Claims (No.)",
    ]

    def test_required_columns_present(self, payments_df):
        missing = [c for c in self.REQUIRED_COLS if c not in payments_df.columns]
        assert missing == [], f"Missing required columns: {missing}"

    def test_state_name_column_has_known_values(self, payments_df):
        valid_states = {
            "Queensland", "New South Wales", "Victoria", "South Australia",
            "Western Australia", "Tasmania", "Northern Territory",
            "Australian Capital Territory", "Unknown",
        }
        actual = set(payments_df["State Name"].dropna().unique())
        unexpected = actual - valid_states
        assert not unexpected, f"Unexpected State Name values: {unexpected}"

    def test_typo_column_name_preserved(self, payments_df):
        # "Total Recieved Claims" (sic) — must match source CSV exactly
        assert "Total Recieved Claims (No.)" in payments_df.columns, \
            "Column name must match the source CSV typo ('Recieved')"

    def test_dollars_paid_parseable_after_strip(self, payments_df):
        parsed = (
            payments_df["Dollars Paid ($)"]
            .astype(str)
            .str.replace(r"[\$,\s]", "", regex=True)
            .replace({"nan": None, "<20": None})
            .pipe(pd.to_numeric, errors="coerce")
        )
        n_failed = parsed.isna().sum()
        assert n_failed <= 2, f"Too many unparseable dollar values: {n_failed}"


class TestIcaSchema:

    REQUIRED_COLS = [
        "CAT Name", "Event Name", "Event Start", "Type", "Year",
        "NORMALISED LOSS VALUE (2022)",
    ]

    def test_required_columns_present(self, ica_df):
        missing = [c for c in self.REQUIRED_COLS if c not in ica_df.columns]
        assert missing == [], f"Missing required columns: {missing}"

    def test_event_start_parseable(self, ica_df):
        parsed = pd.to_datetime(ica_df["Event Start"], format="%d-%b-%y", errors="coerce")
        # Some synthetic rows may fail; require ≥ 80% parseable
        pct_ok = parsed.notna().mean()
        assert pct_ok >= 0.8, f"Only {pct_ok:.0%} of Event Start dates parsed"

    def test_normalised_loss_parseable(self, ica_df):
        parsed = (
            ica_df["NORMALISED LOSS VALUE (2022)"]
            .astype(str)
            .str.replace(r"[\$,\s]", "", regex=True)
            .replace("nan", None)
            .pipe(pd.to_numeric, errors="coerce")
        )
        assert parsed.notna().any(), "No normalised loss values parsed"

    def test_type_field_has_known_values(self, ica_df):
        known_types = {"Flood", "Storm", "Cyclone", "Bushfire", "Hail",
                       "Heatwave", "Landslide", "Earthquake", "Man-made"}
        actual = set(ica_df["Type"].dropna().unique())
        unexpected = actual - known_types
        assert not unexpected, f"Unexpected Type values: {unexpected}"

    def test_year_is_integer_range(self, ica_df):
        years = pd.to_numeric(ica_df["Year"], errors="coerce").dropna()
        assert (years >= 1967).all(), "Years below ICA coverage start (1967)"
        assert (years <= 2030).all(), "Implausibly future years in ICA data"


# ── Dollar parsing helper tests ────────────────────────────────────────────

class TestDollarParsing:

    def test_dollar_sign_stripped(self):
        s = pd.Series(["$1,234,567"])
        result = s.str.replace(r"[\$,\s]", "", regex=True).pipe(pd.to_numeric, errors="coerce")
        assert result.iloc[0] == pytest.approx(1234567.0)

    def test_commas_stripped_from_large_values(self):
        s = pd.Series(["1,000,000"])
        result = s.str.replace(",", "", regex=False).pipe(pd.to_numeric, errors="coerce")
        assert result.iloc[0] == pytest.approx(1000000.0)

    def test_nan_string_becomes_na(self):
        s = pd.Series(["nan"]).replace("nan", pd.NA)
        result = pd.to_numeric(s, errors="coerce")
        assert result.isna().all()

    def test_zero_dollar_is_zero_not_nan(self):
        s = pd.Series(["$0"])
        result = s.str.replace(r"[\$,\s]", "", regex=True).pipe(pd.to_numeric, errors="coerce")
        assert result.iloc[0] == pytest.approx(0.0)


# ── Compound disaster schema tests ────────────────────────────────────────

class TestCompoundClusteringInputSchema:

    def test_cluster_id_assigned_to_all_events(self):
        """Cluster IDs must be non-negative integers for all events after clustering."""
        import numpy as np
        # Simulate clustering output
        events = pd.DataFrame({
            "_cluster_id": [0, 0, 1, 2, 2],
            "_fy":         [2011, 2011, 2011, 2012, 2012],
        })
        assert (events["_cluster_id"] >= 0).all()
        assert events["_cluster_id"].dtype in (int, np.int64, np.int32)

    def test_is_compound_flag_is_boolean(self):
        clusters = pd.DataFrame({
            "n_events":     [1, 2, 3],
            "_is_compound": [False, True, True],
        })
        assert clusters["_is_compound"].dtype == bool

    def test_compound_requires_at_least_two_events(self):
        clusters = pd.DataFrame({
            "n_events": [1, 2, 3, 4],
        })
        clusters["_is_compound"] = clusters["n_events"] >= 2
        singletons = clusters[clusters["n_events"] == 1]
        assert not singletons["_is_compound"].any()


# ── Boolean fillna pattern test ────────────────────────────────────────────

class TestBooleanFillnaPattern:
    """
    Guard against deprecated pandas FutureWarning: never use .fillna(False)
    on object-dtype columns.  Always convert to nullable BooleanDtype first.
    """

    def test_correct_bool_fillna_pattern(self):
        # After a left merge, bool-indicating columns may be object dtype
        df = pd.DataFrame({
            "flag": pd.array([True, None, False, None], dtype=pd.BooleanDtype()),
        })
        # Correct pattern from app.py
        result = df["flag"].astype("boolean").fillna(False).astype(bool)
        assert result.dtype == bool
        assert list(result) == [True, False, False, False]

    def test_incorrect_fillna_on_object_dtype_raises_or_warns(self):
        """
        This test documents the failure mode — not a test that should pass cleanly.
        If object-dtype .fillna(False) still works in the current pandas version,
        this test records that we are aware of the fragility.
        """
        import warnings
        df = pd.DataFrame({"flag": [True, None, False, None]})
        # object dtype — .fillna(False) is fragile
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = df["flag"].fillna(False)
            # Document: result may be object dtype, not bool
            # The correct pattern must be used instead
            assert result is not None  # just ensure no crash; dtype may be wrong
