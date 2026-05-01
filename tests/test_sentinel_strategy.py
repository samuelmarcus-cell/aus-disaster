"""
Tests for sentinel value handling (DRFA/ICA '<20' privacy sentinel).

Scientific risk: substituting <20 with different values can materially change
aggregate claim counts, especially for small disasters.  These tests verify:
  - Each strategy produces the correct substituted value
  - EXCLUDE strategy produces NaN (excluded from sum/mean)
  - Non-sentinel values are untouched by all strategies
  - Sensitivity table covers all strategies
  - Count of sentinel cells is accurate
  - Comma-separated large numbers are correctly stripped before sentinel detection
"""

import math

import pandas as pd
import pytest

from src.methods.sentinel_strategy import (
    SentinelStrategy,
    apply_sentinel,
    count_sentinels,
    sentinel_sensitivity_table,
    SENTINEL_LOWER,
    SENTINEL_MIDPOINT,
    SENTINEL_UPPER,
    SENTINEL_STRING,
)


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def mixed_series() -> pd.Series:
    """Series with a mix of normal values, sentinels, and NaNs."""
    return pd.Series(["100", "<20", "500", "<20", "nan", "1,234"])


@pytest.fixture
def all_sentinel_series() -> pd.Series:
    return pd.Series(["<20", "<20", "<20"])


@pytest.fixture
def no_sentinel_series() -> pd.Series:
    return pd.Series(["100", "200", "1,500"])


# ── Strategy correctness ───────────────────────────────────────────────────

class TestStrategyValues:

    def test_midpoint_replaces_sentinel_with_10(self, mixed_series):
        result = apply_sentinel(mixed_series, SentinelStrategy.MIDPOINT)
        # Second and fourth values were <20 → should be 10.0
        assert result.iloc[1] == pytest.approx(SENTINEL_MIDPOINT)
        assert result.iloc[3] == pytest.approx(SENTINEL_MIDPOINT)

    def test_lower_replaces_sentinel_with_1(self, mixed_series):
        result = apply_sentinel(mixed_series, SentinelStrategy.LOWER)
        assert result.iloc[1] == pytest.approx(SENTINEL_LOWER)
        assert result.iloc[3] == pytest.approx(SENTINEL_LOWER)

    def test_upper_replaces_sentinel_with_19(self, mixed_series):
        result = apply_sentinel(mixed_series, SentinelStrategy.UPPER)
        assert result.iloc[1] == pytest.approx(SENTINEL_UPPER)
        assert result.iloc[3] == pytest.approx(SENTINEL_UPPER)

    def test_exclude_replaces_sentinel_with_nan(self, mixed_series):
        result = apply_sentinel(mixed_series, SentinelStrategy.EXCLUDE)
        assert math.isnan(result.iloc[1])
        assert math.isnan(result.iloc[3])


class TestNonSentinelValuesPreserved:

    def test_normal_values_unchanged_midpoint(self, mixed_series):
        result = apply_sentinel(mixed_series, SentinelStrategy.MIDPOINT)
        assert result.iloc[0] == pytest.approx(100.0)
        assert result.iloc[2] == pytest.approx(500.0)

    def test_comma_separated_large_numbers(self):
        s = pd.Series(["1,234", "5,678", "<20"])
        result = apply_sentinel(s, SentinelStrategy.MIDPOINT)
        assert result.iloc[0] == pytest.approx(1234.0)
        assert result.iloc[1] == pytest.approx(5678.0)
        assert result.iloc[2] == pytest.approx(10.0)

    def test_nan_string_becomes_nan(self, mixed_series):
        result = apply_sentinel(mixed_series, SentinelStrategy.MIDPOINT)
        assert math.isnan(result.iloc[4])

    def test_zero_value_preserved(self):
        s = pd.Series(["0", "<20"])
        result = apply_sentinel(s, SentinelStrategy.MIDPOINT)
        assert result.iloc[0] == pytest.approx(0.0)


# ── Count sentinels ────────────────────────────────────────────────────────

class TestCountSentinels:

    def test_count_correct(self, mixed_series):
        assert count_sentinels(mixed_series) == 2

    def test_count_zero_when_no_sentinels(self, no_sentinel_series):
        assert count_sentinels(no_sentinel_series) == 0

    def test_count_all_sentinels(self, all_sentinel_series):
        assert count_sentinels(all_sentinel_series) == 3


# ── Sensitivity table ──────────────────────────────────────────────────────

class TestSensitivityTable:

    def test_table_has_four_rows(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        assert len(tbl) == 4

    def test_table_has_required_columns(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        for col in ("strategy", "n_sentinel", "sum", "mean", "min", "max", "n_valid"):
            assert col in tbl.columns, f"Missing column: {col}"

    def test_midpoint_sum_higher_than_lower(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        midpoint_sum = tbl.loc[tbl["strategy"].str.contains("Midpoint"), "sum"].iloc[0]
        lower_sum    = tbl.loc[tbl["strategy"].str.contains("Lower"),    "sum"].iloc[0]
        assert midpoint_sum > lower_sum

    def test_upper_sum_higher_than_midpoint(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        upper_sum    = tbl.loc[tbl["strategy"].str.contains("Upper"),    "sum"].iloc[0]
        midpoint_sum = tbl.loc[tbl["strategy"].str.contains("Midpoint"), "sum"].iloc[0]
        assert upper_sum > midpoint_sum

    def test_exclude_has_fewer_valid_entries(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        midpoint_n = tbl.loc[tbl["strategy"].str.contains("Midpoint"), "n_valid"].iloc[0]
        exclude_n  = tbl.loc[tbl["strategy"].str.contains("Exclude"),  "n_valid"].iloc[0]
        assert exclude_n < midpoint_n

    def test_n_sentinel_consistent_across_rows(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        assert tbl["n_sentinel"].nunique() == 1

    def test_no_sentinel_series_all_strategies_equal(self, no_sentinel_series):
        tbl = sentinel_sensitivity_table(no_sentinel_series)
        # When no sentinels, all strategies should produce identical sums
        sums = tbl["sum"].unique()
        assert len(sums) == 1

    def test_n_sentinel_zero_when_no_sentinels(self, no_sentinel_series):
        tbl = sentinel_sensitivity_table(no_sentinel_series)
        assert (tbl["n_sentinel"] == 0).all()


# ── Aggregate sensitivity ──────────────────────────────────────────────────

class TestAggregateSensitivity:

    def test_sum_range_midpoint_within_lower_upper(self, mixed_series):
        """Midpoint sum must lie between lower-bound and upper-bound sums."""
        tbl = sentinel_sensitivity_table(mixed_series)
        sums = dict(zip(tbl["strategy"].str.split(" ").str[0], tbl["sum"]))
        assert sums["Lower"] <= sums["Midpoint"] <= sums["Upper"]

    def test_all_strategy_enum_values_present(self, mixed_series):
        tbl = sentinel_sensitivity_table(mixed_series)
        assert len(tbl) == len(SentinelStrategy)
