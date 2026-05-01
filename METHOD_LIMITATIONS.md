# Methodological Limitations

**Project:** Australian Disaster Data Explorer  
**Author:** Samuel Marcus, Monash University  
**Updated:** 2026-05-01

This document catalogues the known methodological limitations, untested assumptions, and sources of uncertainty in the analyses implemented in this application.  It is intended to accompany any published outputs derived from this platform.

---

## 1. State / Jurisdiction Inference

### What the code does
Rows in the DRFA payments dataset with `State Name == "Unknown"` are assigned a jurisdiction by matching the disaster name string against a set of precompiled regular expressions (`_STATE_RULES` in `app.py`).

### Limitations
1. **First-match bias**: when a disaster name matches multiple state patterns (e.g. cross-border flood events), the state of the first rule in the ordered list is assigned.  The true multi-jurisdiction nature of the event is silently collapsed.
2. **Vocabulary coverage**: the regex vocabulary was built from known event names.  Novel place names, naming conventions introduced after the vocabulary was last updated, or events described at national level will return `UNKNOWN`.
3. **Name ambiguity**: some place names appear in multiple states.  The rules attempt to resolve this through context (e.g. "Kingston" is ambiguous but "Kingston SE" is South Australia), but unresolvable cases exist.
4. **Confidence is not propagated**: the confidence class (`EXACT`, `MULTI`, `UNKNOWN`) attached to inferred rows is metadata only.  It does not filter or weight downstream state-level aggregations.

### Residual risk
State-level payment totals and per-state disaster frequency counts will be biased by misclassified records.  The magnitude of this bias depends on the proportion of `MULTI` and `UNKNOWN` events in the filtered dataset.

### Audit tool
`python -m src.validation.state_inference_audit` — produces a row-level audit CSV and a precision/recall summary.

---

## 2. Sentinel Value Imputation (`<20`)

### What the code does
DRFA payment and ICA claim count columns use the string `<20` to suppress counts between 1 and 19 (privacy protection).  The app substitutes the midpoint value of 10.

### Limitations
1. **Midpoint is an assumption**: the true value could be anywhere from 1 to 19.  For small disasters (total claims close to the suppression threshold), the choice of 1, 10, or 19 changes per-event totals by up to ±900%.
2. **Aggregation uncertainty**: when multiple sentinel cells are summed, uncertainty compounds.  A sum of 100 sentinel cells has a range of ±900 from the midpoint estimate.
3. **No distributional information**: there is no way to recover the true distribution of suppressed counts from the published data.

### Residual risk
Published claim count totals and means that include sentinel-imputed cells should report a range (lower bound, midpoint, upper bound) rather than a point estimate.

### Sensitivity tool
`src/methods/sentinel_strategy.sentinel_sensitivity_table(series)` — returns a comparison table across all four strategies (midpoint, lower, upper, exclude).

---

## 3. AIDR + AGD Title-Key Merge

### What the code does
The Knowledge Hub dataset merges AIDR events with AGD geocoded records using a case-insensitive, strip-normalised disaster name as the join key.

### Limitations
1. **Exact title matching only**: event names that differ by even one character (punctuation, abbreviation, accidental space) will not match.  Fuzzy matching is diagnostically available in `src/validation/merge_audit.py` but is not applied to the merged output.
2. **AGD coverage ends 2014**: all AIDR events after 2014 are structurally unmatched.  These appear as `AIDR only` and receive `NaN` lat/lon coordinates.
3. **AGD deduplication**: if the AGD CSV contains multiple rows with the same title (checked during audit), only the first row is used.  Subsequent rows (potentially different lat/lon) are discarded.
4. **Merge confidence is not flagged in the UI**: the `_source_flag` column distinguishes `Both`, `AIDR only`, `AGD only`, but filters in the UI do not warn when a geographic analysis uses events with missing coordinates.

### Residual risk
Any spatial analysis (event map, state frequency maps) will be biased toward AIDR events with known AGD coordinates.  Pre-2014 events are better represented spatially than post-2014 events.

### Audit tool
`python -m src.validation.merge_audit` — produces `audit_merge_aidr_agd.csv` and `audit_merge_near_duplicates.csv`.

---

## 4. DRFA Activations + Payments Merge

### What the code does
DRFA payment records (one row per payment type per LGA per event) are pre-aggregated to one row per `(agrn, Location_Name)` pair, then left-joined to activations.

### Limitations
1. **Coverage gap**: payment data exists for only ~44 unique AGRNs (2009–2026).  All other activations show `NaN` in payment columns.  The `Has_Payment_Data` flag distinguishes these, but users filtering by dollar amounts will implicitly exclude unpaid events.
2. **Aggregation flattens payment types**: summing AGDRP and DRA dollars produces a total, but the type breakdown is concatenated as a string, not a numeric breakdown.
3. **AGRN type mismatch risk**: if the activations CSV stores AGRN as an integer and the payments CSV stores it as a string, the join silently matches zero records.  The app normalises both to string; any future data update that changes this behaviour will silently break the join.

### Residual risk
Analyses that compare event severity using payment totals represent only the subset of events where individual/household payments were administered.  Infrastructure and public asset payments (DRFA Categories B–D) are not captured.

---

## 5. Compound Disaster Methodology (Gissing et al. 2022)

### What the code does
Events above a normalised loss threshold (ICA dataset) or with ≥2 AGRN activations (DRFA dataset) are clustered within each Australian financial year using chain-link onset-date proximity (91-day window).  Clusters of ≥2 events are classified as "compound disasters".

### Limitations
1. **Threshold sensitivity**: the default ≥$100M normalised loss threshold excludes small events.  Events just below the threshold that are genuinely part of a compound sequence are invisible to the analysis.
2. **Window sensitivity**: the 91-day window is from Gissing et al. (2022) and may not be appropriate for all hazard types.  A short cyclone–flood sequence within 7 days would be clustered; a slow-onset drought–fire sequence over 6 months would not.
3. **Chain-link clustering**: the clustering algorithm links events to the previous event in the sequence.  If event B occurs 90 days after event A and event C occurs 90 days after event B, all three are in the same cluster even if C is 180 days from A.  This transitivity may not match the physical compound disaster definition.
4. **DRFA magnitude scale (DGMS)**: the DRFA-adapted magnitude scale uses LGA activation count as a severity proxy for normalised loss (which is unavailable for DRFA events).  LGA count is not linearly related to economic impact.
5. **Financial year framing**: compound clustering is performed within financial years.  Events spanning the June–July boundary (e.g. a cyclone in late June and a flood in early July) are not clustered together.

### Reference
Gissing, A., Crompton, R., McAneney, J. (2022). Compound natural disasters in Australia: a historical analysis. *Natural Hazards and Earth System Sciences*, 22(3), 1071–1085. https://doi.org/10.5194/nhess-22-1071-2022

---

## 6. Climate–Disaster Linkage Analysis

### What the code does
Financial-year-level climate phase classifications (ENSO, SAM, IOD) are matched to compound disaster seasons.  Contingency tables and Fisher's exact tests are produced.

### Limitations
1. **ENSO and IOD are not independent**: La Niña co-occurs with negative IOD more often than positive IOD (Walker circulation coupling).  Treating them as independent predictors would be scientifically incorrect.  The application explicitly does NOT make independence assumptions (the "Loaded Dice" tab was removed for this reason).
2. **Exploratory associations only**: the contingency tables show conditional frequencies.  They do not establish causation, and p-values are not corrected for multiple comparisons.
3. **FY-level averaging loses within-year dynamics**: assigning a single ENSO phase label to a financial year discards sub-seasonal variability.  A year with 6 months of El Niño and 6 months of Neutral is classified as Neutral if the mean ONI is < 0.5.
4. **IOD sustained-event criterion**: requiring ≥3 of 7 active-season months above ±0.4°C is a methodological choice.  Different thresholds or duration criteria would classify some years differently.
5. **SAM phase threshold**: SAM phase is classified using a ±1.0 threshold on the FY mean.  The meteorological literature does not specify a universal threshold; this value is conventional.
6. **ICA insurance penetration bias**: compound disaster seasons identified from ICA data reflect insured losses only.  Events in regions with lower insurance penetration (rural areas, low-income communities) are systematically underrepresented.
7. **Limited sample size**: the overlap period with reliable data for all three indices (ONI, SAM, IOD) starts approximately 1957.  With ~70 financial years, individual cell counts in contingency tables are small, limiting statistical power.

---

## 7. EM Concurrency Analysis

### What the code does
A sweep-line algorithm counts how many DRFA events are "active" on each calendar day, using a user-configurable active duration assumption.

### Limitations
1. **Duration assumption is not derived**: the active duration window (default: variable by UI slider) is not drawn from event records — it is a user-chosen assumption.  DRFA activations do not record an end date.
2. **Event intensity is not considered**: the concurrency count treats a 2-LGA flood and a 300-LGA cyclone identically (both count as 1 active event).
3. **DRFA coverage starts 2006**: concurrency estimates for earlier periods are unavailable.

---

## 8. State Co-occurrence Analysis

### What the code does
For each calendar day, the binary active-state matrix is computed, then a symmetric co-occurrence matrix is derived by dot product.

### Limitations
Same limitations as the EM Concurrency Analysis (duration assumption, intensity-blind counting).  Additionally, state-level analysis aggregates LGA-level activations upward, which may attribute localised events to the entire state.

---

## 9. AFAC Capability Analysis

### What the code does
Parses the 2023 AFAC National Capability Statement Excel file to extract personnel and equipment counts by domain, function, and jurisdiction.

### Limitations
1. **Static 2023 snapshot**: capability figures are not updated automatically.  Changes to state agency capacity since 2023 are not reflected.
2. **Deployable ≠ available**: the "Deployable Capability" section records teams available for interstate deployment within 48 hours under mutual aid.  Actual availability depends on concurrent domestic demand and political agreements.
3. **Categories are broad**: "Severe Weather Response" covers both cyclone search-and-rescue and urban flood cleanup — very different capability requirements collapsed into one domain.

---

## General Caveats

- **Multiple comparisons**: where multiple statistical tests are presented (e.g. multiple contingency tables), p-values are not adjusted.  Interpret all significance claims with caution.
- **Data sovereignty**: disaster data for events affecting Indigenous communities may be underrepresented or miscategorised in all datasets.
- **Temporal inconsistency**: datasets cover different time periods and have different update frequencies.  Cross-dataset comparisons should account for coverage mismatches.
- **Dollar figures**: ICA losses are in 2022 AUD (normalised).  EM-DAT figures are in '000 USD (2022 adjusted).  DRFA payment figures are in nominal AUD at payment date.  These are not directly comparable without further conversion.
