# Scientific Hardening Refactor Summary

**Project:** Australian Disaster Data Explorer  
**Author:** Samuel Marcus, Monash University  
**Completed:** 2026-05-01  
**Scope:** PhD prototype → scientifically defensible, publication-supportable analytical platform

---

## Objective

Harden the repository against scientific and methodological risk without redesigning existing analytical capability.  Every change directly addresses a reproducibility, auditability, or scientific defensibility concern.

---

## Changes Made

### Priority 1 — High-Risk Methodological Assumptions

#### A. State Inference Validation

**Scientific risk addressed:** Regex-based state assignment from disaster names used first-match logic with no confidence signal.  Multi-state events were silently collapsed.  No audit trail existed.

**Changes made:**

| File | Change |
|---|---|
| `app.py` | Added `_infer_state_confidence()` — returns `(confidence_class, all_matched_states)` alongside the existing first-match primary assignment |
| `app.py` | `load_drfa_payments()` now attaches `_state_infer_conf` column: `"LABELLED"` / `"EXACT"` / `"MULTI"` / `"UNKNOWN"` for every row |
| `app.py` | `render_drfa_payments()` shows an expandable warning panel when MULTI or UNKNOWN inference rows exist in the loaded dataset |
| `src/validation/state_inference_audit.py` | Standalone audit module: `infer_state_with_confidence()`, `audit_state_inference()`, `summarise_audit()`; run via `python -m src.validation.state_inference_audit` |

**Validation added:** 42 pytest tests in `tests/test_state_inference.py` covering unambiguous states, abbreviations, multi-state detection, confidence classes, cyclone names, and regression cases.

**Remaining limitations:** Regex vocabulary was built from known events; novel place names will return UNKNOWN.  MULTI events are genuinely ambiguous (cross-border events) — first-match is used as primary but is not guaranteed correct.

---

#### B. Merge Integrity Validation

**Scientific risk addressed:** Title-key joins (AIDR+AGD) and AGRN joins (DRFA act+pay) had no duplicate detection, no unmatched record reporting, and no fanout guards.

**Changes made:**

| File | Change |
|---|---|
| `src/validation/merge_audit.py` | Audit module for both merges: duplicate key counts, source flag distribution, AGD pre-2014 unmatched analysis, fuzzy near-duplicate detection (difflib), DRFA fanout analysis, downloadable CSV outputs |

**Validation added:** 9 pytest tests in `tests/test_merge_integrity.py` verifying structural properties: deduplication prevents row inflation, source flags are complete, left merge preserves all activation rows, NaN (not 0) for unmatched records.

**Remaining limitations:** Fuzzy matching is heuristic and capped at 500 pairs.  Near-duplicate pairs still require manual review.

---

#### C. Sentinel Value Sensitivity Analysis

**Scientific risk addressed:** `<20` privacy sentinel was hardcoded to midpoint 10 with no way to assess sensitivity of results to this imputation choice.

**Changes made:**

| File | Change |
|---|---|
| `src/methods/sentinel_strategy.py` | `SentinelStrategy` enum (MIDPOINT/LOWER/UPPER/EXCLUDE), `apply_sentinel()`, `count_sentinels()`, `sentinel_sensitivity_table()` |
| `app.py` | `to_num_counts()` now delegates to `apply_sentinel(SentinelStrategy.MIDPOINT)` — identical default behaviour, with fallback if `src/` is not on path |
| `app.py` | `render_drfa_payments()` shows sentinel count and uncertainty note when `<20` cells are present |
| `app.py` | `render_ica()` shows sentinel count note for ICA claim columns |

**Validation added:** 21 pytest tests in `tests/test_sentinel_strategy.py` covering each strategy value, non-sentinel preservation, comma stripping, count detection, sensitivity table structure, and aggregate ordering invariants.

**Remaining limitations:** Midpoint remains the default — published analyses should report lower/upper bounds for any aggregate that includes sentinel cells.

---

### Priority 2 — Structural Defensibility

**Scientific risk addressed:** 6700-line monolithic `app.py` makes methodological components difficult to inspect independently.

**Changes made:**

```
src/
├── __init__.py
├── methods/
│   ├── __init__.py
│   └── sentinel_strategy.py    ← extracted from to_num_counts()
└── validation/
    ├── __init__.py
    ├── state_inference_audit.py ← extracted + extended from _infer_state_from_name()
    └── merge_audit.py           ← new; implements merge diagnostics
```

**Approach:** Only methodologically critical components were extracted.  UI rendering and data loaders remain in `app.py` to avoid breaking changes.  All extracted functions include docstrings with assumptions and known limitations.

**Remaining limitations:** Full separation of loaders, analytics, and rendering would improve testability further but was deferred to avoid breaking Streamlit session state.

---

### Priority 3 — Reproducibility

**Scientific risk addressed:** Loose dependency ranges (`>=1.51`) are not reproducible across environments.  No provenance documentation existed.

**Changes made:**

| File | Change |
|---|---|
| `requirements.txt` | Pinned to exact installed versions |
| `DATA_PROVENANCE.md` | Full source documentation for all 9 datasets: URLs, retrieval dates, schema notes, transformation assumptions |
| `METHOD_LIMITATIONS.md` | Catalogues all known methodological limitations across all analysis types |
| `.gitignore` | Reviewed and verified — already covers notebooks, caches, pycache, macOS artefacts |

**Pinned versions:**
```
streamlit==1.51.0
pandas==2.3.3
plotly==6.3.0
pyarrow==21.0.0
requests==2.32.5
openpyxl==3.1.5
scipy==1.16.3
numpy==2.3.5
```

---

### Priority 4 — Testing

**Scientific risk addressed:** No tests existed; schema changes in refreshed data files would fail silently.

**Test suite:** `tests/` — 122 tests, all passing.

| File | Tests | What it guards |
|---|---|---|
| `tests/conftest.py` | — | Synthetic fixtures for all datasets (no real files required) |
| `tests/test_state_inference.py` | 42 | State inference correctness, multi-state detection, confidence classes, regression cases |
| `tests/test_sentinel_strategy.py` | 21 | Sentinel strategy values, non-sentinel preservation, sensitivity table ordering |
| `tests/test_merge_integrity.py` | 9 | Row-count invariants, NaN vs 0 for unmatched rows, AGRN type normalisation |
| `tests/test_date_parsing.py` | 19 | ICA year disambiguation, FY boundary, AGD vs AIDR format differences |
| `tests/test_schema_validation.py` | 31 | Required column presence, value constraints, dollar/count parsing, boolean fillna pattern |

Run with: `python -m pytest tests/ -v`

---

### Priority 5 — Transparency

**Scientific risk addressed:** Methodological assumptions were invisible to users.

**Changes made:**

| Location | Warning added |
|---|---|
| `render_drfa_payments()` | Expandable panel showing EXACT/MULTI/UNKNOWN inference counts when uncertain rows exist |
| `render_drfa_payments()` | Caption noting sentinel count and approximate nature of claim totals |
| `render_ica()` | Caption noting ICA sentinel count |
| `to_num_counts()` docstring | Updated to reference `sentinel_sensitivity_table()` |
| `_infer_state_from_name()` docstring | Updated to reference audit module |

---

## What Was NOT Changed

- No UI redesign or cosmetic refactors
- No changes to compound disaster clustering methodology (scientifically sound)
- No changes to ICA or DRFA merge logic (sound, now audited)
- No changes to climate index fetching logic
- No changes to IOD FY classification (sustained-event criterion, already correct)
- No changes to the Gissing et al. (2022) magnitude scale
- No database migration
- No cloud infrastructure changes
- Existing git history preserved

---

## Success Criteria Assessment

> "A scientifically literate reviewer should be able to inspect this repository and conclude: the methodology may still contain assumptions, but those assumptions are explicit, tested, sensitivity-checked, and scientifically defensible."

| Criterion | Status |
|---|---|
| State inference assumptions are explicit | ✅ `_STATE_RULES` documented; audit tool available |
| State inference is tested | ✅ 42 tests covering correctness and edge cases |
| Sentinel assumptions are explicit | ✅ Docstring + UI warning + `sentinel_strategy.py` |
| Sentinel sensitivity is checkable | ✅ `sentinel_sensitivity_table()` covers all four strategies |
| Merge assumptions are explicit | ✅ `DATA_PROVENANCE.md` documents all joins |
| Merge integrity is verifiable | ✅ `merge_audit.py` produces downloadable diagnostic CSVs |
| Date parsing is tested | ✅ 19 tests covering all format edge cases |
| Schema changes will be caught | ✅ Schema validation tests for all 3 primary datasets |
| Dependency versions are pinned | ✅ Exact versions in `requirements.txt` |
| Data provenance is documented | ✅ `DATA_PROVENANCE.md` |
| Method limitations are documented | ✅ `METHOD_LIMITATIONS.md` |
| Uncertainty is visible in UI | ✅ Inference confidence panel, sentinel count captions |
