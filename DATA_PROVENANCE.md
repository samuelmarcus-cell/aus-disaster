# Data Provenance

**Project:** Australian Disaster Data Explorer  
**Author:** Samuel Marcus, Monash University  
**Updated:** 2026-05-01

---

## Overview

This document records the origin, access conditions, retrieval dates, schema notes, and known transformation assumptions for every dataset used in this application.  It is intended to support reproducibility, peer review, and methodological transparency.

---

## 1. AIDR Disaster Mapper (AIDR)

| Field | Value |
|---|---|
| **Provider** | Australian Institute for Disaster Resilience (AIDR) |
| **Source URL** | https://knowledge.aidr.org.au/resources/disaster-mapper/ |
| **File** | `AIDR_disaster_mapper_data.xlsx`, sheet "Disaster Mapper Data" |
| **Coverage** | 1727–2023 |
| **Last retrieved** | March 2023 (dataset last updated by AIDR) |
| **Access** | Publicly available via AIDR Knowledge Hub |

### Schema notes
- `Start Date` / `End Date`: Australian date format (dd/mm/yyyy); parsed with `dayfirst=True`.
- `Category`: mixed case in source (e.g. "flood", "Flood") — normalised to title case on load.
- `Insured Cost`: free-text field with mixed formats (e.g. "$1.2 billion", "$450 million") — the app extracts the first numeric token only; text notes are discarded.
- `Fatalities`, `Injured`: contain mixed types (integers, strings like "Not Available", "A ") — normalised to string then to numeric on load; non-numeric values become NaN.
- `Zone`: comma-separated state list (e.g. "Queensland, New South Wales") — parsed into a Python list per event.

### Transformation assumptions
- Column names are stripped of whitespace before use.
- `Category` strings are title-cased unconditionally.
- `Insured Cost` parsing extracts the first number found (e.g. in "approx $1.2 billion", extracts 1.2).

---

## 2. AGD Geocoded Disaster Events (AGD)

| Field | Value |
|---|---|
| **Provider** | Attorney-General's Department (AGD) |
| **Source URL** | https://data.gov.au/data/dataset/australian-disasters-geocoded |
| **File** | `au-govt-agd-disaster-events-impact-location-na.csv` |
| **Coverage** | Up to 2014 |
| **Last retrieved** | Unknown (dataset is a static export; no update since ~2014) |
| **Access** | Open data (data.gov.au, Creative Commons) |

### Schema notes
- `startdate` / `enddate`: US date format (MM/DD/YYYY) — parsed with explicit `format="%m/%d/%Y"`.
- Damage columns (homes_damaged, buildings_destroyed, etc.) are ≤7% populated; not used in any analysis.
- `lat` / `lon`: only columns carried into the merged dataset.

### Merge with AIDR
- Key: lowercase-stripped `title` (AGD) matched to `Event` (AIDR).
- AIDR fields take precedence on conflicts.
- AGD contributes only `lat` / `lon` to matched records.
- AGD-only records (no AIDR match) appear with `_source_flag = "AGD only"`.
- Duplicate AGD keys (same title string, multiple rows): first occurrence kept.
- Coverage gap: AGD ends 2014; AIDR-only records from 2015+ are structurally expected, not merge failures.

---

## 3. DRFA Activation History (DRFA Activations)

| Field | Value |
|---|---|
| **Provider** | National Emergency Management Agency (NEMA) |
| **Source URL** | https://data.gov.au/data/dataset/drfa-activation-history-by-lga |
| **File** | `drfa_activation_history_by_location_2026_march_19.csv` |
| **Coverage** | 2006–March 2026 |
| **Last retrieved** | 19 March 2026 |
| **Access** | Open data (data.gov.au, Creative Commons Attribution) |

### Schema notes
- `disaster_start_date`: ISO 8601 format (YYYY-MM-DD).
- `agrn`: Australian Government Reference Number — unique identifier per declared disaster event.
- `hazard_type`: can be a compound string (e.g. "Flood, Storm") — the app uses the first token as primary hazard for classification.
- `cat_A` through `cat_D`: binary DRFA category eligibility flags per LGA.
- `AGDRP` / `DRA`: binary flags indicating individual/household payment eligibility.
- `STATE`: two-letter abbreviation (NSW, VIC, QLD, SA, WA, TAS, ACT, NT).

### Sentinel values
None in this dataset (categorical/binary columns only).

---

## 4. DRFA Disaster Payment History (DRFA Payments)

| Field | Value |
|---|---|
| **Provider** | Services Australia / National Emergency Management Agency (NEMA) |
| **Source URL** | https://www.nema.gov.au/our-work/disaster-recovery/disaster-recovery-payments |
| **File** | `disaster_history_payments_2026_march_19.csv` |
| **Coverage** | 2009–March 2026 |
| **Last retrieved** | 19 March 2026 |
| **Access** | Open data (nema.gov.au) |

### Schema notes
- `Disaster AGRN`: matches `agrn` in the activations dataset — the join key.
- `State Name`: contains "Unknown" for some records — state inferred from `Disaster Name` by regex (see Inference section below).
- `Eligible Claims (No.)` / `Total Recieved Claims (No.)`: note deliberate typo "Recieved" — matches source CSV column name exactly.
- `Dollars Paid ($)` / `Dollars Granted ($)`: string-formatted dollar amounts (e.g. "$1,234,567").

### Sentinel values
The strings `<20` in claim count columns indicate that the true value is between 1 and 19, suppressed for privacy.  The app substitutes midpoint = 10.  Sensitivity of aggregate results to this choice can be assessed with `src/methods/sentinel_strategy.py`.

### State name inference
Rows where `State Name == "Unknown"` have their state inferred from `Disaster Name` via regex rules (`_STATE_RULES` in `app.py`).  The inference assigns a single primary state on a first-match basis.  A confidence class (`_state_infer_conf`) is attached to each inferred row:
- **EXACT**: exactly one state pattern matched (highest confidence)
- **MULTI**: two or more patterns matched; first match used (ambiguous — may be a genuine cross-border event)
- **UNKNOWN**: no pattern matched (inference failed; state remains "Unknown" after inference)

A full audit report can be generated with `python -m src.validation.state_inference_audit`.

### Merge with DRFA Activations
- Key: `(agrn, Location_Name)` after aggregating payments to one row per LGA–event pair.
- Payment table pre-aggregated to prevent row-count fanout (multiple payment types per LGA–event).
- Left merge: activations without matching payment data retain NaN in payment columns.
- 44 unique AGRNs have matching payment data (as of March 2026); the remainder are activation-only.

---

## 5. EM-DAT International Disaster Database — Australia subset

| Field | Value |
|---|---|
| **Provider** | Centre for Research on the Epidemiology of Disasters (CRED), UCLouvain |
| **Source URL** | https://public.emdat.be/ |
| **File** | `EMDAT_Disaster_Aus.csv` |
| **Coverage** | 1939–present (Australia subset) |
| **Last retrieved** | Unknown (access requires registration at public.emdat.be) |
| **Access** | Free registration required; Creative Commons for non-commercial use |

### Schema notes
- Damage figures in '000 USD; "Adjusted" columns normalised to 2022 USD using CPI.
- `Associated Types`: non-empty value indicates CRED classified the event as having a secondary hazard — used as the compound disaster flag (`_is_compound`). This is CRED's own contemporaneous classification, not derived.
- `DisNo.` is the unique event identifier.
- Column names contain special characters (apostrophes, parentheses) — stripped of whitespace on load.

---

## 6. ICA Historical Normalised Catastrophe Loss Data (ICA)

| Field | Value |
|---|---|
| **Provider** | Insurance Council of Australia (ICA) |
| **Source URL** | https://insurancecouncil.com.au/industry-members/data-hub/ |
| **File** | `ICA-Historical-Normalised-Catastrophe-Master-Updated-2026_02.csv` |
| **Coverage** | 1967–February 2026 |
| **Last retrieved** | February 2026 |
| **Access** | ICA member portal (restricted) |

### Schema notes
- `Event Start` / `Event Finish`: `%d-%b-%y` format (e.g. "14-Apr-99").
- **2-digit year ambiguity**: Python strptime maps 2-digit years 00–68 → 2000–2068, 69–99 → 1969–1999. Historical ICA events (pre-2000) are corrected: if `parsed_year > declared_Year + 1`, subtract 100 years.
- `ORIGINAL LOSS VALUE` / `NORMALISED LOSS VALUE (2022)`: string-formatted dollar amounts.
- Normalised loss adjusts for inflation, property values, and building code changes to a 2022 AUD baseline.
- `CAT Name`: `"Undeclared"` is shared by 497 events (significant events that never received a formal CAT or SE number). Row index is used as unique key, not CAT Name.
- Claim count columns use `<20` sentinel (see Sentinel values above).

### Sentinel values
Same `<20` privacy sentinel as DRFA payments. See `src/methods/sentinel_strategy.py`.

---

## 7. AFAC National Capability Statement (AFAC)

| Field | Value |
|---|---|
| **Provider** | Australasian Fire and Emergency Service Authorities Council (AFAC) |
| **Source URL** | https://afac.com.au/resources/national-capability-statement/ |
| **File** | `2023-national-capability-statement-data.xlsx` |
| **Coverage** | Static 2023 snapshot |
| **Last retrieved** | 2023 |
| **Access** | Publicly available |

### Schema notes
- Multi-sheet Excel workbook; each sheet = one operational domain (e.g. "Firefighting (bushfire)", "Search and Rescue").
- Deployable capability rows are flagged in a section header row ("Deployable Capability").
- Aviation sheet has a different column layout from non-aviation sheets.
- Values of "-", "–", "", None are treated as 0.

---

## 8. Climate Indices (fetched live)

### ONI (Oceanic Niño Index)

| Field | Value |
|---|---|
| **Provider** | NOAA Climate Prediction Center (CPC) |
| **Source URL** | https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php |
| **Cache file** | `oni_cache.csv` |
| **Coverage** | 1950–present |
| **Update frequency** | Monthly (~10th of month for previous season) |

- 3-month running mean SST anomaly for Niño 3.4 region (5°N–5°S, 170°W–120°W).
- Phase threshold: El Niño ≥ +0.5°C; La Niña ≤ −0.5°C.
- Cache refreshed when local copy is > 2 months behind current date.

### SAM (Southern Annular Mode)

| Field | Value |
|---|---|
| **Primary source** | BAS Marshall SAM (1957–1978 historical) |
| **BAS URL** | https://legacy.bas.ac.uk/met/gjma/newsam.1957.2007.txt |
| **Secondary source** | NOAA CPC AAO (1979–present) |
| **CPC URL** | https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_ao_index/aao/monthly.aao.index.b79.current.ascii.table |
| **Cache file** | `sam_cache.csv` |
| **Splice point** | BAS used pre-1979; NOAA CPC used 1979 onwards |

- Phase threshold: Positive SAM ≥ +1.0; Negative SAM ≤ −1.0.
- The two series use different methodologies (station-based vs reanalysis); correlation is high (r > 0.95) but variance differs.

### IOD / DMI (Indian Ocean Dipole)

| Field | Value |
|---|---|
| **Primary source** | NOAA PSL HadISST1.1 monthly DMI (1870–~12 months ago) |
| **PSL URL** | https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.csv |
| **Gap-fill source** | BoM GAMSSA weekly (July 2008–present) |
| **BoM URL** | https://www.bom.gov.au/clim_data/IDCK000072/iod_1.txt |
| **Cache file** | `iod_cache.csv` |

- Phase threshold: ±0.4°C (BoM operational standard).
- **FY-level classification**: sustained-event criterion — a financial year is classified as Positive/Negative IOD if ≥3 of the 7 active-season months (May–November) exceed ±0.4°C. Simple seasonal averaging is NOT used (dilutes short events to near-zero; produces near-universal Neutral classification).

### MJO (Madden-Julian Oscillation)

| Field | Value |
|---|---|
| **Provider** | Australian Bureau of Meteorology (BoM) |
| **Source URL** | http://www.bom.gov.au/clim_data/IDCKGEM000/rmm.74toRealtime.txt |
| **Cache file** | `mjo_cache.csv` |
| **Coverage** | 1 June 1974–present (daily, 2-day lag) |
| **Reference** | Wheeler & Hendon (2004), Mon. Wea. Rev., 132, 1917–1932 |

- RMM1, RMM2: PC1 and PC2 of combined OLR+U850+U200.
- Phase: 1–8 geographic sectors; 0 = weak event (amplitude < 1.0).
- Missing-value sentinels (|value| > 900) are dropped on load.

---

## ICA ↔ DRFA Verdicts Reference File

| Field | Value |
|---|---|
| **File** | `ica_drfa_verdicts.csv` |
| **Status** | Reference data only — NOT merged into the app |

Manually curated event links between ICA catastrophes and DRFA activations.  The probabilistic matching methodology was assessed as scientifically indefensible for publication and removed.  This file is retained as a reference for future methodological development.
