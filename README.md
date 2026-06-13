# Australian Disaster Data Explorer

A multi-page Streamlit application for exploring Australian disaster and climate datasets. Built as part of PhD research into compound hazards and emergency management capacity at Monash University.

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

Climate index data (ONI, IOD, SAM, MJO) is fetched live from NOAA, BAS, and BoM on first run and cached locally.

## Data sources

| File | Source | Coverage |
|------|--------|----------|
| `AIDR_disaster_mapper_data.xlsx` | AIDR Knowledge Hub | 1727–2023 |
| `au-govt-agd-disaster-events-impact-location-na.csv` | Attorney-General's Dept | 1900–2023 |
| `drfa_activation_history_by_location_2026_march_19.csv` | NEMA | 2006–Mar 2026 |
| `disaster_history_payments_2026_march_19.csv` | NEMA | 2009–present |
| `EMDAT_Disaster_Aus.csv` | EM-DAT (CRED) | 1939–present |
| `ICA-Historical-Normalised-Catastrophe-Master-Updated-2026_02.csv` | Insurance Council of Australia | 1967–Feb 2026 |
| `2023-national-capability-statement-data.xlsx` | AFAC | 2023 snapshot |

## Pages

**Source Datasets**
- Home
- AIDR Event Catalogue — merged AIDR + AGD disaster records
- ICA Catastrophes — normalised insured loss (1967–present)
- DRFA Activations — LGA-level Commonwealth activation history
- DRFA Payments — AGDRP/DRA claims and expenditure
- EM-DAT — international disaster database, Australia subset

**Climate Data**
- ENSO / ONI, SAM Index, IOD / DMI, MJO / RMM, Climate Science

**Integrated Data**
- DRFA Activations + Payments — merged Commonwealth response view

**Analysis**
- Compound Disasters (ICA) — Gissing et al. (2022) methodology applied to ICA insured loss data, with adjustable clustering window

**EM Capacity**
- National Capability (AFAC) — 2023 static capability snapshot
- State Capability Profiles — per-state breakdown

## Reference

Gissing, A., Crompton, R., McAneney, J., & Vidana-Rodriguez, R. (2022). Compound natural disasters in Australia: a historical analysis. *International Journal of Disaster Risk Reduction*, 72, 102812.

## Author

Samuel Marcus — PhD Candidate, Monash University
