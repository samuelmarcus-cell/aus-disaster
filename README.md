# Australian Disaster Data Explorer

A multi-page Streamlit application for exploring Australian disaster and climate datasets. Built as part of PhD research into compound hazards and emergency management capacity at Monash University.

## Research context

This tool integrates five disaster datasets with four real-time climate indices to support analysis of:
- Compound disaster events (multiple hazards within a single season)
- DRFA (Disaster Recovery Funding Arrangements) activation patterns
- Emergency management capacity and concurrency demand
- Climate–disaster linkages (ENSO, SAM, IOD, MJO)

Methodology follows Gissing et al. (2022) for compound disaster classification and Cuthbertson et al. (2021) for EM-DAT compound hazard identification.

## Installation

```bash
pip install -r requirements.txt
```

Then run:

```bash
streamlit run app.py
```

## Data files

The following source files must be placed in the same directory as `app.py`. They are not included in this repository (large files stored separately on OneDrive).

| File | Source | Coverage |
|------|--------|----------|
| `AIDR_disaster_mapper_data.xlsx` | AIDR Knowledge Hub | 1727–2023 |
| `au-govt-agd-disaster-events-impact-location-na.csv` | Attorney-General's Dept | 1900–2023 |
| `drfa_activation_history_by_location_2026_march_19.csv` | NEMA | 2006–Mar 2026 |
| `disaster_history_payments_2026_march_19.csv` | NEMA | 2009–present |
| `EMDAT_Disaster_Aus.csv` | EM-DAT (CRED) | 1939–present |
| `ICA-Historical-Normalised-Catastrophe-Master-Updated-2026_02.csv` | Insurance Council of Australia | 1967–Feb 2026 |
| `2023-national-capability-statement-data.xlsx` | AFAC | 2023 snapshot |

Climate index data (ONI, IOD, SAM, MJO) is fetched live from NOAA, BAS, and BoM on first run and cached locally. Cache files are not tracked in this repository.

## App pages

**Source Datasets**
- Home — dataset overview and event map
- AIDR Event Catalogue — merged AIDR + AGD disaster records
- ICA Catastrophes — normalised insured loss (1967–present)
- DRFA Activations — LGA-level Commonwealth activation history
- DRFA Payments — AGDRP/DRA claims and expenditure
- EM-DAT — international disaster database, Australia subset

**Climate Data**
- ENSO / ONI — Oceanic Niño Index with ICA compound overlay
- SAM Index — Southern Annular Mode
- IOD / DMI — Indian Ocean Dipole
- MJO / RMM — Madden–Julian Oscillation
- Climate Science — methodology and data source notes

**Integrated Analysis**
- DRFA Activations + Payments — merged Commonwealth response view
- Event Map — geospatial disaster explorer

**Research**
- Compound Disasters (ICA) — Gissing et al. (2022) methodology applied to insured loss data
- Compound Disasters (DRFA) — same methodology adapted for government activation data
- EM Concurrency Analysis — concurrent activation demand across states
- State Co-occurrence — multi-state disaster patterns

**EM Capacity**
- National Capability (AFAC) — 2023 static capability snapshot
- State Capability Profiles — per-state breakdown

## Key references

- Gissing, A., Crompton, R., McAneney, J., & Vidana-Rodriguez, R. (2022). Compound natural disasters in Australia: a historical analysis. *International Journal of Disaster Risk Reduction*, 72, 102812.
- Cuthbertson, J., et al. (2021). Compound disasters and emergency management implications. *Prehospital and Disaster Medicine*.

## Author

Samuel Marcus — PhD Candidate, Monash University  
Research focus: Compound Hazards & Emergency Management Capacity
