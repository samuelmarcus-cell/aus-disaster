"""
merge_audit.py
==============
Scientific audit of dataset merge operations in the Australian Disaster Data Explorer.

Scope
-----
Two merges carry material scientific risk:

1. AIDR + AGD outer merge (load_knowledge_hub)
   Key: lowercase-stripped event title
   Risk: title changes between datasets, silent duplicates, coverage gaps

2. DRFA Activations + Payments left merge (load_drfa_merged)
   Key: (agrn, Location_Name)
   Risk: one-to-many fanout, events in activations with no payment record, AGRN mismatches

This module audits both merges and produces:
  - Per-row match classification (MATCHED / LEFT_ONLY / RIGHT_ONLY / DUPLICATE_KEY)
  - One-to-many warning table
  - Fuzzy near-duplicate detection for unmatched records
  - Downloadable CSV diagnostics

Usage (standalone)
------------------
    python -m src.validation.merge_audit

Produces:
    audit_merge_aidr_agd.csv
    audit_merge_drfa.csv
    audit_merge_summary.csv

Usage (programmatic)
--------------------
    from src.validation.merge_audit import audit_aidr_agd_merge, audit_drfa_merge

Assumptions
-----------
- Title-key matching is case-insensitive and strip-normalised (matching app logic).
- AGRN is treated as the authoritative event identifier for DRFA data.
- "Near-duplicate" = edit distance ≤ 3 characters on cleaned titles (optional,
  requires difflib; degrades gracefully if unavailable).

Known limitations
-----------------
- Fuzzy matching is O(n²) and can be slow for large datasets; it is capped at
  500 unmatched pairs.
- Edit-distance thresholding is heuristic.  Matched pairs still require manual
  review to confirm they represent the same real-world event.
- The AGD dataset covers only up to 2014; unmatched AIDR records from 2015+
  are structurally expected and should not be counted as merge failures.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_key(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower()


def _fuzzy_near_duplicates(
    left_keys: list[str],
    right_keys: list[str],
    max_ratio: float = 0.9,
    max_pairs: int = 500,
) -> pd.DataFrame:
    """
    Find near-duplicate title pairs across unmatched left vs right keys.
    Uses difflib.SequenceMatcher.  Returns DataFrame with columns:
        left_key, right_key, similarity
    """
    try:
        from difflib import SequenceMatcher
    except ImportError:
        return pd.DataFrame(columns=["left_key", "right_key", "similarity"])

    pairs = []
    for l_key in left_keys[:max_pairs]:
        for r_key in right_keys[:max_pairs]:
            ratio = SequenceMatcher(None, l_key, r_key).ratio()
            if ratio >= max_ratio:
                pairs.append({"left_key": l_key, "right_key": r_key, "similarity": round(ratio, 3)})
    return pd.DataFrame(pairs).sort_values("similarity", ascending=False)


# ─────────────────────────────────────────────────────────────────────────────
# AIDR + AGD merge audit
# ─────────────────────────────────────────────────────────────────────────────

def audit_aidr_agd_merge(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Audit the AIDR+AGD outer merge used in load_knowledge_hub().

    Returns
    -------
    audit_df : row-level audit with columns:
        key, source_flag, aidr_event, agd_title, n_aidr_key_dups, n_agd_key_dups
    summary  : aggregate statistics DataFrame

    Notes
    -----
    AGD keys are de-duplicated before the merge (same as app logic).  Duplicate
    detection here counts raw duplicates BEFORE deduplication so the caller knows
    what was silently dropped.
    """
    aidr_path = data_dir / "AIDR_disaster_mapper_data.xlsx"
    agd_path  = data_dir / "au-govt-agd-disaster-events-impact-location-na.csv"

    aidr = pd.read_excel(aidr_path, sheet_name="Disaster Mapper Data")
    aidr.columns = aidr.columns.str.strip()
    aidr["_key"] = _normalise_key(aidr["Event"])

    agd = pd.read_csv(agd_path, low_memory=False)
    agd["_key"] = _normalise_key(agd["title"])

    # Raw duplicate counts (before deduplication)
    aidr_dup_counts = aidr.groupby("_key").size().rename("n_aidr_key_dups")
    agd_dup_counts  = agd.groupby("_key").size().rename("n_agd_key_dups")

    # Deduplication (matching app logic: keep first)
    agd_dedup = agd.drop_duplicates(subset=["_key"])

    # Outer merge
    merged = aidr.merge(agd_dedup[["_key", "title"]], on="_key", how="outer", indicator=True)
    merged["source_flag"] = merged["_merge"].map({
        "both":       "MATCHED",
        "left_only":  "AIDR_ONLY",
        "right_only": "AGD_ONLY",
    })

    audit = merged[["_key", "source_flag"]].copy()
    audit["aidr_event"] = merged.get("Event", pd.Series(dtype=str))
    audit["agd_title"]  = merged.get("title", pd.Series(dtype=str))
    audit = audit.merge(aidr_dup_counts, on="_key", how="left")
    audit = audit.merge(agd_dup_counts,  on="_key", how="left")

    # Fuzzy near-duplicates: unmatched AIDR vs unmatched AGD
    aidr_only_keys = audit.loc[audit["source_flag"] == "AIDR_ONLY", "_key"].dropna().tolist()
    agd_only_keys  = audit.loc[audit["source_flag"] == "AGD_ONLY",  "_key"].dropna().tolist()

    # Filter AIDR-only to pre-2015 records (AGD coverage ends 2014)
    try:
        aidr["_year"] = pd.to_datetime(
            aidr.get("Start Date", pd.Series(dtype=str)), dayfirst=True, errors="coerce"
        ).dt.year
        aidr_only_pre2015 = aidr[
            (aidr["_key"].isin(aidr_only_keys)) & (aidr["_year"] <= 2014)
        ]["_key"].tolist()
    except Exception:
        aidr_only_pre2015 = aidr_only_keys

    fuzzy = _fuzzy_near_duplicates(aidr_only_pre2015, agd_only_keys)

    # Summary
    n_total   = len(audit)
    n_matched = (audit["source_flag"] == "MATCHED").sum()
    n_aidr    = (audit["source_flag"] == "AIDR_ONLY").sum()
    n_agd     = (audit["source_flag"] == "AGD_ONLY").sum()
    n_aidr_dups = int((audit["n_aidr_key_dups"].fillna(1) > 1).sum())
    n_agd_dups  = int((audit["n_agd_key_dups"].fillna(1) > 1).sum())

    summary = pd.DataFrame([
        {"metric": "Total rows in outer merge",         "value": n_total},
        {"metric": "Matched (Both)",                    "value": n_matched},
        {"metric": "AIDR only (no AGD match)",          "value": n_aidr},
        {"metric": "AGD only (no AIDR match)",          "value": n_agd},
        {"metric": "AIDR duplicate keys (pre-dedup)",   "value": n_aidr_dups},
        {"metric": "AGD duplicate keys (pre-dedup)",    "value": n_agd_dups},
        {"metric": "Near-duplicate candidate pairs",    "value": len(fuzzy)},
        {"metric": "Match rate (%)",                    "value": round(100 * n_matched / n_total, 1)},
    ])

    return audit, summary, fuzzy


# ─────────────────────────────────────────────────────────────────────────────
# DRFA activations + payments merge audit
# ─────────────────────────────────────────────────────────────────────────────

def audit_drfa_merge(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Audit the DRFA activations → payments left merge used in load_drfa_merged().

    The merge key is (agrn, Location_Name).  The payments table is pre-aggregated
    by (agrn, Location_Name) before the join to prevent row-count fanout.

    Returns
    -------
    audit_df : per-agrn event-level summary with:
        agrn, event_name, n_activations, has_payment_data,
        n_pay_raw_rows, n_pay_payment_types
    summary  : aggregate statistics DataFrame
    """
    act_path = data_dir / "drfa_activation_history_by_location_2026_march_19.csv"
    pay_path = data_dir / "disaster_history_payments_2026_march_19.csv"

    act = pd.read_csv(act_path, low_memory=False)
    act.columns = act.columns.str.strip()

    pay = pd.read_csv(pay_path, low_memory=False)
    pay.columns = pay.columns.str.strip()

    # Rename payment columns to match app logic
    pay_r = pay.rename(columns={
        "Disaster AGRN":   "agrn",
        "Location Name":   "Location_Name",
    })
    pay_r["agrn"] = pay_r["agrn"].astype(str).str.strip()
    act["agrn"]   = act["agrn"].astype(str).str.strip()

    # Payment rows per AGRN (before aggregation)
    pay_per_agrn = pay_r.groupby("agrn").agg(
        n_pay_raw_rows=("agrn", "count"),
        n_pay_payment_types=("Payment Type Name", "nunique"),
        pay_location_names=("Location_Name", lambda x: "; ".join(sorted(x.dropna().unique())[:5])),
    ).reset_index()

    # One-to-many analysis: check for AGRN present in both with multiple LGA rows
    act_per_agrn = act.groupby("agrn").agg(
        event_name=("event_name", "first"),
        n_activations=("Location_Name", "nunique"),
        n_states=("STATE", "nunique"),
        states=("STATE", lambda x: "; ".join(sorted(x.dropna().unique()))),
    ).reset_index()

    merged = act_per_agrn.merge(pay_per_agrn, on="agrn", how="left")
    merged["has_payment_data"] = merged["n_pay_raw_rows"].notna()

    # Identify AGRNs in payments but not activations
    pay_only_agrns = set(pay_r["agrn"].unique()) - set(act["agrn"].unique())

    n_act   = len(act_per_agrn)
    n_pay   = len(pay_per_agrn)
    n_match = merged["has_payment_data"].sum()
    n_act_only = n_act - n_match
    n_pay_only = len(pay_only_agrns)
    n_fanout_risk = int((merged["n_pay_raw_rows"].fillna(0) > merged["n_activations"]).sum())

    summary = pd.DataFrame([
        {"metric": "Unique AGRNs in activations",          "value": n_act},
        {"metric": "Unique AGRNs in payments",             "value": n_pay},
        {"metric": "Matched AGRNs (activations + payment)","value": n_match},
        {"metric": "Activations with no payment record",   "value": n_act_only},
        {"metric": "Payments with no activation record",   "value": n_pay_only},
        {"metric": "Matched rate (%)",                     "value": round(100 * n_match / n_act, 1) if n_act > 0 else 0},
        {"metric": "Potential row-count fanout events",    "value": n_fanout_risk},
    ])

    return merged, summary


# ─────────────────────────────────────────────────────────────────────────────
# Standalone runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_audit(data_dir: Path) -> None:
    print(f"\n{'='*60}")
    print("Merge Integrity Audit")
    print(f"{'='*60}")

    # AIDR + AGD
    print("\n[1/2] AIDR + AGD merge (Knowledge Hub)…")
    try:
        audit_aidr, summary_aidr, fuzzy = audit_aidr_agd_merge(data_dir)
        print(summary_aidr.to_string(index=False))
        if not fuzzy.empty:
            print(f"\nNear-duplicate candidates (similarity ≥ 0.90):")
            print(fuzzy.head(10).to_string(index=False))
        audit_aidr.to_csv(data_dir / "audit_merge_aidr_agd.csv", index=False)
        fuzzy.to_csv(data_dir / "audit_merge_near_duplicates.csv", index=False)
        print(f"\n  → audit_merge_aidr_agd.csv")
        print(f"  → audit_merge_near_duplicates.csv")
    except Exception as e:
        print(f"  [ERROR] {e}")

    # DRFA activations + payments
    print(f"\n[2/2] DRFA activations + payments merge…")
    try:
        audit_drfa, summary_drfa = audit_drfa_merge(data_dir)
        print(summary_drfa.to_string(index=False))
        audit_drfa.to_csv(data_dir / "audit_merge_drfa.csv", index=False)
        print(f"\n  → audit_merge_drfa.csv")
    except Exception as e:
        print(f"  [ERROR] {e}")

    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    _DATA_DIR = Path(__file__).parent.parent.parent
    _run_audit(_DATA_DIR)
