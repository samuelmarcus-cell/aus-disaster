"""
state_inference_audit.py
========================
Scientific audit of the regex-based state/territory inference used to fill
"Unknown" state labels in DRFA payment records.

Problem statement
-----------------
app.py::_infer_state_from_name() iterates over _STATE_RULES and returns on the
FIRST matching pattern.  This produces three scientifically silent failure modes:

  1. First-match bias: if a name matches both Queensland and NSW patterns (e.g.
     cross-border floods), only the first rule fires.  The second match is lost.

  2. No confidence signal: the caller cannot tell whether an assignment was
     unambiguous (exact single match) or guessed (first of many matches).

  3. No coverage audit: there is no record of how many events were inferred vs
     labelled in the source data.

This module re-implements the inference to expose all three failure modes, and
provides an audit report suitable for inclusion in supplementary material.

Confidence classes
------------------
EXACT        – exactly one state pattern matched  (highest confidence)
MULTI        – two or more state patterns matched (ambiguous; first-match used)
UNKNOWN      – no pattern matched                 (inference failed)

Usage (standalone)
------------------
    python -m src.validation.state_inference_audit

Produces:
    - console report
    - audit_state_inference.csv (one row per inferred event)
    - audit_state_inference_summary.csv (aggregate statistics)

Usage (programmatic)
--------------------
    from src.validation.state_inference_audit import (
        infer_state_with_confidence,
        audit_state_inference,
    )

    conf_class, matched_states, primary_state = infer_state_with_confidence("2011 Queensland Floods")
    # → ("EXACT", ["Queensland"], "Queensland")

Assumptions
-----------
- _STATE_RULES are applied in order; first match is used as primary assignment
  (matching original app behaviour), but all matches are recorded.
- The audit is descriptive: it does not alter the underlying data.

Known limitations
-----------------
- Regex rules were built incrementally from known event names; novel place names
  will not match and will receive UNKNOWN classification.
- "Queensland Floods" will match Queensland only; "Queensland and NSW Floods" may
  match both Queensland and New South Wales — the MULTI classification flags this
  for manual review.
- Cross-border events classified as MULTI are not necessarily misclassified;
  they are genuinely multi-jurisdiction events.
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path
from typing import Literal

import pandas as pd

# ── replicate the STATE_RULES from app.py ────────────────────────────────────
# These are copied verbatim so the audit is independent of the Streamlit app.
_STATE_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(
        r"Queensland|South.?East Queensland|Southern Queensland|Northern.*Queensland"
        r"|North.*Queensland|Western Queensland|\bQLD\b|\bQld\b|\bSEQ\b"
        r"|Far North Qld|West QLD"
        r"|Tropical Cyclone (Jasper|Kirrily|Alfred|Koji|Debbie|Marcia|Ita|Yasi)"
        r"|North and Far North(?! Tropical Low)|Queensland Monsoon"
        r"|Queensland Bushfire|Queensland Flood|Queensland Storms|Queensland Rainfall"
        r"|Rockhampton|Mackay|Cairns|Townsville|Bundaberg|Toowoomba|Ipswich|Fernvale"
        r"|Emerald|Lockyer Valley|Somerset|Moreton|Sunshine Coast|Gold Coast"
        r"|Christmas Storms|Christmas and New Year Storms",
        re.IGNORECASE), "Queensland"),
    (re.compile(
        r"\bNSW\b|New South Wales|NSW North Coast|NSW East Coast|Far West Region"
        r"|Hunter Valley|Northern Rivers|Newcastle|Sydney|Blue Mountains"
        r"|Warrumbungle|Wagga|Lismore|Blacktown|East Coast Low|Northern NSW"
        r"|Shoalhaven|Coffs Harbour|Grafton|Armidale|Tamworth|Goulburn"
        r"|Mid North Coast|Clarence Valley|Kempsey|Port Macquarie|Singleton"
        r"|Cessnock|Muswellbrook|Oberon|Maitland|Snowy|Penrith|Richmond Valley"
        r"|Greater Taree|Bourke|Glen Innes|Tenterfield|Cooma|Hilltops|Carrathool",
        re.IGNORECASE), "New South Wales"),
    (re.compile(
        r"Victorian|Western Victoria|Victoria(?!\s*Bushfire.*QLD)|\bVIC\b"
        r"|Melbourne|Gippsland|Black Saturday|Great Ocean Rd|Great Ocean Road|Wye River"
        r"|Bunyip|Latrobe Valley|Bendigo|Ballarat|Mornington Peninsula"
        r"|Yarra Ranges|Pyrenees|Thomson Catchment|Rosedale|Timbarra"
        r"|Corangamite|Grampians|Colac|Surf Coast|Gannawarra|Loddon"
        r"|East Gippsland|West Gippsland|South Gippsland|Central Victoria",
        re.IGNORECASE), "Victoria"),
    (re.compile(
        r"South Australian|South Australia(?! Flood.*QLD)|\bSA\b"
        r"|\bAdelaide\b|Sampson.?s? Flat|Pinery|Kangaroo Island|Coober Pedy"
        r"|Mount Lofty|Eyre Peninsula|Fleurieu|Cherryville|Kingston|Tulka|Coomunga"
        r"|Bundaleer|Clare Valley|Yorke Peninsula|Barossa",
        re.IGNORECASE), "South Australia"),
    (re.compile(
        r"Tasmanian|Tasmania|\bTAS\b|Hobart|Tasman Peninsula|Dunalley|Launceston"
        r"|Devonport|Molesworth|Circular Head|St Helens|Bicheno|Boomer Bay"
        r"|North West Tasmania|Southern Tasmania|East Coast Tasmania",
        re.IGNORECASE), "Tasmania"),
    (re.compile(
        r"Australian Capital Territory|\bACT\b|Canberra",
        re.IGNORECASE), "Australian Capital Territory"),
    (re.compile(
        r"Western Australia|\bWA\b|Wooroloo|Perth|Margaret River|Leschenault"
        r"|Pilbara|Kimberley|Broome|Busselton|Gascoyne|Wheatbelt|Esperance"
        r"|Carnarvon|Geraldton|Kalgoorlie|Collie|Augusta|Mandurah|Rockingham"
        r"|Tropical Cyclone (George|Hilda|Lua|Rusty|Olwyn|Christine|Heidi|Kelvin|Blake)"
        r"|Cyclone (George|Jacob)|South West Land Division|Great Southern Region"
        r"|Shire of Wandering|Shire of Kellerberrin",
        re.IGNORECASE), "Western Australia"),
    (re.compile(
        r"Northern Territory|\bNT\b|Northern Region"
        r"|Ex.?TC Ellie|Ex.?Tropical Cyclone Ellie|North and Far North Tropical Low"
        r"|Darwin|Daly River|Kakadu|Top End|Alice Springs|Nhulunbuy"
        r"|Tropical Cyclone (Marcus|Carlos|Lam|Trevor|Nathan|Heatlie)"
        r"|Cyclone (Marcus|Grant|Carlos)|Central Australian|Arnhem",
        re.IGNORECASE), "Northern Territory"),
]

ConfidenceClass = Literal["EXACT", "MULTI", "UNKNOWN"]


def infer_state_with_confidence(
    name: str,
) -> tuple[ConfidenceClass, list[str], str]:
    """
    Apply ALL state inference rules to name and return a confidence-classified result.

    Returns
    -------
    confidence : "EXACT" | "MULTI" | "UNKNOWN"
    all_matches : list of all states whose pattern matched (may be empty or multiple)
    primary_state : the state assigned (first match, or "MULTI" or "UNKNOWN")

    Notes
    -----
    Primary state uses first-match (matching original app behaviour) so that
    downstream data frames are unchanged.  The confidence class and all_matches
    are diagnostic outputs only.
    """
    n = str(name)
    matches: list[str] = []
    for pattern, state in _STATE_RULES:
        if pattern.search(n):
            matches.append(state)

    if len(matches) == 0:
        return "UNKNOWN", [], "Unknown"
    elif len(matches) == 1:
        return "EXACT", matches, matches[0]
    else:
        return "MULTI", matches, matches[0]  # first-match preserved as primary


def audit_state_inference(
    df: pd.DataFrame,
    name_col: str,
    state_col: str | None = None,
) -> pd.DataFrame:
    """
    Run inference audit over a DataFrame of disaster names.

    Args:
        df:        DataFrame containing disaster names (and optionally labelled states).
        name_col:  Column with the disaster name string.
        state_col: Optional column with labelled state (used for precision/recall if present).

    Returns:
        Audit DataFrame with columns:
            name, inferred_primary, confidence, all_matches, n_matches
            [labelled_state, match_correct]  — only if state_col provided
    """
    records = []
    for _, row in df.iterrows():
        name = str(row[name_col])
        conf, all_m, primary = infer_state_with_confidence(name)
        rec = {
            "name":             name,
            "inferred_primary": primary,
            "confidence":       conf,
            "all_matches":      "; ".join(all_m) if all_m else "",
            "n_matches":        len(all_m),
        }
        if state_col and state_col in df.columns:
            labelled = str(row[state_col])
            rec["labelled_state"] = labelled
            rec["match_correct"] = (
                primary == labelled
                if conf != "UNKNOWN" and labelled not in ("Unknown", "nan", "")
                else None
            )
        records.append(rec)
    return pd.DataFrame(records)


def summarise_audit(audit_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate audit DataFrame into a summary statistics table.

    Returns a one-row-per-confidence-class summary with counts and percentages.
    """
    total = len(audit_df)
    rows = []
    for conf in ("EXACT", "MULTI", "UNKNOWN"):
        subset = audit_df[audit_df["confidence"] == conf]
        n = len(subset)
        rows.append({
            "confidence_class": conf,
            "count":            n,
            "pct":              round(100 * n / total, 1) if total > 0 else 0.0,
            "example_names":    "; ".join(subset["name"].head(3).tolist()),
        })

    summary = pd.DataFrame(rows)

    if "match_correct" in audit_df.columns:
        labelled = audit_df["match_correct"].notna()
        if labelled.any():
            correct = audit_df.loc[labelled, "match_correct"].sum()
            total_labelled = labelled.sum()
            precision = round(100 * correct / total_labelled, 1)
            summary["labelled_precision_pct"] = [
                precision if conf == "EXACT" else None
                for conf in ("EXACT", "MULTI", "UNKNOWN")
            ]

    return summary


def _run_audit(data_dir: Path) -> None:
    """Standalone audit runner — called from __main__."""
    pay_path = data_dir / "disaster_history_payments_2026_march_19.csv"
    if not pay_path.exists():
        print(f"[ERROR] Payments CSV not found: {pay_path}")
        sys.exit(1)

    pay = pd.read_csv(pay_path, low_memory=False)

    # Identify rows that will be inferred (State Name == "Unknown")
    unknown_mask = pay["State Name"].astype(str).str.strip() == "Unknown"
    infer_df = pay[unknown_mask][["Disaster Name", "State Name"]].drop_duplicates("Disaster Name")
    all_df   = pay[["Disaster Name", "State Name"]].drop_duplicates("Disaster Name")

    print(f"\n{'='*60}")
    print("State Inference Audit — DRFA Payments")
    print(f"{'='*60}")
    print(f"Total unique disaster names:     {len(all_df)}")
    print(f"Names requiring inference:       {len(infer_df)}")

    audit = audit_state_inference(infer_df, name_col="Disaster Name", state_col="State Name")
    summary = summarise_audit(audit)

    print("\n--- Confidence class breakdown ---")
    print(summary[["confidence_class", "count", "pct"]].to_string(index=False))

    multi = audit[audit["confidence"] == "MULTI"]
    if not multi.empty:
        print(f"\n--- MULTI-match events ({len(multi)}) — manual review recommended ---")
        for _, row in multi.iterrows():
            print(f"  '{row['name']}' → {row['all_matches']}")

    unknown = audit[audit["confidence"] == "UNKNOWN"]
    if not unknown.empty:
        print(f"\n--- UNKNOWN events ({len(unknown)}) — inference failed ---")
        for _, row in unknown.head(20).iterrows():
            print(f"  '{row['name']}'")
        if len(unknown) > 20:
            print(f"  ... and {len(unknown) - 20} more")

    out_audit   = data_dir / "audit_state_inference.csv"
    out_summary = data_dir / "audit_state_inference_summary.csv"
    audit.to_csv(out_audit, index=False)
    summary.to_csv(out_summary, index=False)
    print(f"\nAudit CSV written:   {out_audit}")
    print(f"Summary CSV written: {out_summary}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    _DATA_DIR = Path(__file__).parent.parent.parent
    _run_audit(_DATA_DIR)
