"""
Tests for dataset merge integrity.

Scientific risk: title-key joins silently drop or duplicate records.  These
tests verify structural properties of the merge logic that, if violated, would
introduce systematic bias into multi-source analyses.

Tests cover:
  - Key deduplication before merge (prevents row-count inflation)
  - Source flag completeness (every merged row has a flag)
  - No duplicate (agrn, Location_Name) rows after DRFA aggregation
  - Payment aggregation sum consistency
  - AGRN type consistency between activations and payments
"""

import pytest
import pandas as pd


# ── AIDR+AGD merge structural tests ───────────────────────────────────────

class TestAidrAgdMergeStructure:

    def test_deduplication_prevents_row_count_inflation(self):
        """
        If AGD has 2 rows with the same title-key, the merge must not
        produce more rows than AIDR has unique events.
        """
        aidr = pd.DataFrame({
            "_key":  ["flood 2011", "fire 2009"],
            "Event": ["Flood 2011", "Fire 2009"],
        })
        agd = pd.DataFrame({
            "_key":  ["flood 2011", "flood 2011"],  # duplicate in AGD
            "lat":   [-27.0, -27.5],
            "lon":   [153.0, 153.1],
        })
        # Deduplication step (as in app)
        agd_dedup = agd.drop_duplicates(subset=["_key"])
        merged = aidr.merge(agd_dedup[["_key", "lat", "lon"]], on="_key", how="left")
        # Row count must not exceed AIDR row count
        assert len(merged) <= len(aidr)

    def test_source_flag_covers_all_merge_outcomes(self):
        """Every row in the merged output must have a valid source flag."""
        aidr = pd.DataFrame({"_key": ["a", "b"], "Event": ["A", "B"]})
        agd  = pd.DataFrame({"_key": ["b", "c"], "lat":   [-27.0, -30.0], "lon": [153.0, 150.0]})
        merged = aidr.merge(agd, on="_key", how="outer", indicator=True)
        merged["_source_flag"] = merged["_merge"].map({
            "both":       "MATCHED",
            "left_only":  "AIDR_ONLY",
            "right_only": "AGD_ONLY",
        })
        assert merged["_source_flag"].notna().all()
        assert set(merged["_source_flag"]) == {"MATCHED", "AIDR_ONLY", "AGD_ONLY"}

    def test_outer_merge_preserves_all_aidr_events(self):
        """Outer merge: AIDR-only events must not be lost."""
        aidr = pd.DataFrame({"_key": ["a", "b", "c"], "Event": ["A", "B", "C"]})
        agd  = pd.DataFrame({"_key": ["b"], "lat": [-27.0], "lon": [153.0]})
        merged = aidr.merge(agd, on="_key", how="outer", indicator=True)
        aidr_keys_in_merged = set(merged.loc[merged["_merge"].isin(["both", "left_only"]), "_key"])
        assert set(aidr["_key"]) == aidr_keys_in_merged

    def test_right_only_agd_rows_are_not_duplicated(self):
        """AGD-only rows must appear exactly once in the outer merge."""
        aidr = pd.DataFrame({"_key": ["a"], "Event": ["A"]})
        agd  = pd.DataFrame({"_key": ["b", "b"], "lat": [-27.0, -27.1], "lon": [153.0, 153.1]})
        agd_dedup = agd.drop_duplicates(subset=["_key"])
        merged = aidr.merge(agd_dedup, on="_key", how="outer", indicator=True)
        agd_only = merged[merged["_merge"] == "right_only"]
        assert agd_only["_key"].nunique() == agd_only.shape[0]


# ── DRFA activations + payments aggregation tests ─────────────────────────

class TestDrfaPaymentAggregation:

    @pytest.fixture
    def act_df(self):
        return pd.DataFrame({
            "agrn":                ["D001", "D001", "D002"],
            "Location_Name":       ["Brisbane", "Ipswich", "Armidale"],
            "Payment Type Name":   [None, None, None],
            "_num_paid":           [0.0, 0.0, 0.0],
        })

    @pytest.fixture
    def pay_df(self):
        return pd.DataFrame({
            "agrn":               ["D001", "D001"],
            "Location_Name":      ["Brisbane", "Brisbane"],
            "Payment Type Name":  ["AGDRP", "DRA"],
            "_num_paid":          [10000.0, 5000.0],
            "_num_granted":       [11000.0, 5500.0],
            "_num_eligible":      [100.0, 50.0],
            "_num_total_received":["110", "55"],
        })

    def test_payment_aggregation_eliminates_type_fanout(self, act_df, pay_df):
        """
        Pre-aggregating payments by (agrn, Location_Name) before the merge
        must reduce the row count to one row per (agrn, Location_Name) pair.
        """
        pay_agg = (
            pay_df.groupby(["agrn", "Location_Name"], as_index=False)
            .agg(n_types=("Payment Type Name", "count"))
        )
        merged = act_df.merge(pay_agg, on=["agrn", "Location_Name"], how="left")
        # Must have same number of rows as activations (no fanout)
        assert len(merged) == len(act_df)

    def test_payment_sum_aggregation_is_correct(self, pay_df):
        """
        Summing payment rows for the same (agrn, Location_Name) must
        aggregate correctly.
        """
        pay_agg = (
            pay_df.groupby(["agrn", "Location_Name"], as_index=False)
            .agg(_num_paid_sum=("_num_paid", "sum"))
        )
        brisbane_row = pay_agg[pay_agg["Location_Name"] == "Brisbane"]
        assert brisbane_row["_num_paid_sum"].iloc[0] == pytest.approx(15000.0)

    def test_unmatched_activations_get_nan_not_zero(self, act_df, pay_df):
        """
        Activations with no matching payment record must have NaN payment
        columns, not 0, so that absence-of-data is distinguishable from
        zero-payment events.
        """
        pay_agg = (
            pay_df.groupby(["agrn", "Location_Name"], as_index=False)
            .agg(pay_sum=("_num_paid", "sum"))
        )
        # Drop any pre-existing payment column from act_df before merge
        act_clean = act_df.drop(columns=["_num_paid"], errors="ignore")
        merged = act_clean.merge(pay_agg, on=["agrn", "Location_Name"], how="left")
        # D002/Armidale has no payment data → pay_sum must be NaN
        armidale = merged[merged["Location_Name"] == "Armidale"]
        assert armidale["pay_sum"].isna().all()

    def test_has_payment_data_flag_is_boolean(self, act_df, pay_df):
        """The Has_Payment_Data flag must be a boolean-ish column with no other values."""
        pay_agg = (
            pay_df.groupby(["agrn", "Location_Name"], as_index=False)
            .agg(Payment_Types=("Payment Type Name", lambda x: "; ".join(x.dropna().unique())))
        )
        merged = act_df.merge(pay_agg, on=["agrn", "Location_Name"], how="left")
        merged["Has_Payment_Data"] = merged["Payment_Types"].notna().map({True: "Yes", False: "No"})
        assert set(merged["Has_Payment_Data"]) <= {"Yes", "No"}


# ── AGRN key consistency ───────────────────────────────────────────────────

class TestAgrnKeyConsistency:

    def test_agrn_is_string_after_normalisation(self):
        """
        AGRN from both sources must be string-typed after stripping to prevent
        silent numeric/string type mismatch in the join.
        """
        act = pd.DataFrame({"agrn": [1001, 1002, 1003]})
        pay = pd.DataFrame({"agrn": ["1001", "1002"]})
        act["agrn"] = act["agrn"].astype(str).str.strip()
        pay["agrn"] = pay["agrn"].astype(str).str.strip()
        merged = act.merge(pay, on="agrn", how="left", indicator=True)
        matched = (merged["_merge"] == "both").sum()
        assert matched == 2

    def test_agrn_numeric_string_mismatch_without_normalisation(self):
        """
        Without normalisation, int AGRN in activations will not match
        string AGRN in payments (this is the pre-fix failure mode).
        Current pandas raises ValueError on int64 vs object merge — either
        a ValueError or a zero-match result confirms the risk.
        """
        act = pd.DataFrame({"agrn": [1001, 1002]})
        pay = pd.DataFrame({"agrn": ["1001"]})
        try:
            merged = act.merge(pay, on="agrn", how="left", indicator=True)
            matched = (merged["_merge"] == "both").sum()
            assert matched == 0, "Type mismatch must produce zero matches"
        except ValueError:
            pass  # pandas ≥ 2.0 raises ValueError — also acceptable, confirms the risk
