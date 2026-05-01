"""
sentinel_strategy.py
====================
Centralised handling of privacy-sentinel values in DRFA/Services Australia CSVs.

Background
----------
DRFA payment and claim-count columns use the string "<20" as a privacy sentinel
when the true count is between 1 and 19 (suppressed to protect small populations).
The original app substitutes the midpoint (10) unconditionally.  This module
exposes the full strategy space so that downstream analyses can quantify the
sensitivity of their conclusions to this imputation choice.

Strategies
----------
MIDPOINT  – replace <20 with 10  (default; matches original app behaviour)
LOWER     – replace <20 with 1   (conservative lower bound)
UPPER     – replace <20 with 19  (liberal upper bound)
EXCLUDE   – replace <20 with NaN (exclude from aggregation)

Usage
-----
    from src.methods.sentinel_strategy import SentinelStrategy, apply_sentinel

    counts = apply_sentinel(df["Eligible Claims (No.)"], SentinelStrategy.MIDPOINT)

    # Sensitivity table across all strategies:
    from src.methods.sentinel_strategy import sentinel_sensitivity_table
    print(sentinel_sensitivity_table(df["Eligible Claims (No.)"]))

Assumptions
-----------
- The sentinel string is exactly "<20" (case-sensitive, no surrounding spaces after
  comma-stripping).  The source CSV also contains commas in large numbers; these are
  stripped before sentinel detection.
- "<20" means the value is in [1, 19].  The true value is unknown.
- Summing imputed columns gives approximate totals; callers should propagate this
  uncertainty explicitly in any published results.

Known limitations
-----------------
- Upper bound (19) may still undercount if the actual value is close to 20 but the
  suppression threshold has changed across data vintages.
- There is no way to recover the true value from the published data.
- Large aggregations (>100 sentinel cells) will have wider uncertainty bands than
  small aggregations.
"""

from __future__ import annotations

import enum
import pandas as pd


SENTINEL_STRING = "<20"
SENTINEL_LOWER  = 1
SENTINEL_MIDPOINT = 10
SENTINEL_UPPER  = 19
SENTINEL_TRUE_RANGE = (1, 19)


class SentinelStrategy(enum.Enum):
    """Imputation strategy for DRFA '<20' privacy sentinels."""
    MIDPOINT = "midpoint"
    LOWER    = "lower"
    UPPER    = "upper"
    EXCLUDE  = "exclude"

    @property
    def label(self) -> str:
        labels = {
            "midpoint": "Midpoint (<20 → 10)",
            "lower":    "Lower bound (<20 → 1)",
            "upper":    "Upper bound (<20 → 19)",
            "exclude":  "Exclude (<20 → NaN)",
        }
        return labels[self.value]

    @property
    def replacement(self) -> float | None:
        mapping = {
            "midpoint": float(SENTINEL_MIDPOINT),
            "lower":    float(SENTINEL_LOWER),
            "upper":    float(SENTINEL_UPPER),
            "exclude":  None,
        }
        return mapping[self.value]


def apply_sentinel(
    series: pd.Series,
    strategy: SentinelStrategy = SentinelStrategy.MIDPOINT,
) -> pd.Series:
    """
    Parse a raw claim-count series, applying the chosen sentinel strategy.

    Strips commas, replaces the '<20' sentinel per the strategy, coerces to
    numeric.  Non-sentinel non-numeric values become NaN.

    Args:
        series:   Raw string series (as read from CSV).
        strategy: One of SentinelStrategy.{MIDPOINT, LOWER, UPPER, EXCLUDE}.

    Returns:
        Float64 series with sentinel replaced and all values coerced to numeric.
    """
    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .replace("nan", pd.NA)
    )
    repl = strategy.replacement
    if repl is None:
        cleaned = cleaned.replace(SENTINEL_STRING, pd.NA)
    else:
        cleaned = cleaned.replace(SENTINEL_STRING, str(int(repl)))

    return pd.to_numeric(cleaned, errors="coerce")


def count_sentinels(series: pd.Series) -> int:
    """Return the number of '<20' sentinel cells in a raw series."""
    return int((series.astype(str).str.strip() == SENTINEL_STRING).sum())


def sentinel_sensitivity_table(series: pd.Series) -> pd.DataFrame:
    """
    Compute descriptive statistics for each sentinel strategy applied to series.

    Returns a DataFrame with columns:
        strategy, n_sentinel, sum, mean, min, max

    Useful for documenting sensitivity of aggregate results to the imputation
    choice in published tables.
    """
    n_sentinel = count_sentinels(series)
    rows = []
    for strat in SentinelStrategy:
        s = apply_sentinel(series, strat)
        rows.append({
            "strategy":   strat.label,
            "n_sentinel": n_sentinel,
            "sum":        s.sum(),
            "mean":       round(s.mean(), 2) if s.notna().any() else float("nan"),
            "min":        s.min(),
            "max":        s.max(),
            "n_valid":    int(s.notna().sum()),
        })
    return pd.DataFrame(rows)
