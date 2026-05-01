"""
Shared fixtures for the Australian Disaster Data Explorer test suite.

Fixtures here provide minimal synthetic DataFrames that replicate the structure
of the real datasets without requiring the actual files to be present.  This
makes the tests runnable in CI and by reviewers who do not have access to the
OneDrive-hosted data.

Real-data tests (marked with @pytest.mark.realdata) are skipped unless
DATA_DIR is set to a directory containing the actual CSV/XLSX files.
"""

import os
from pathlib import Path

import pandas as pd
import pytest


# ── Real-data path ─────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def data_dir() -> Path | None:
    """Return the data directory path if the real files are accessible."""
    candidate = Path(__file__).parent.parent
    markers = [
        "drfa_activation_history_by_location_2026_march_19.csv",
        "disaster_history_payments_2026_march_19.csv",
    ]
    if all((candidate / m).exists() for m in markers):
        return candidate
    return None


# ── Synthetic DRFA payments fixture ───────────────────────────────────────

@pytest.fixture
def payments_df() -> pd.DataFrame:
    """
    Minimal synthetic DRFA payments DataFrame.
    Mirrors required columns and includes all sentinel/edge cases.
    """
    return pd.DataFrame({
        "State Name":             ["Queensland", "Unknown", "Unknown", "New South Wales", "Victoria"],
        "Disaster Name":          [
            "2011 Queensland Floods",
            "2019 NSW Bushfires and Floods",
            "Far North Tropical Low 2023",
            "2021 Hunter Valley Floods",
            "2009 Black Saturday Bushfires",
        ],
        "Payment Type Name":      ["AGDRP", "AGDRP", "DRA", "AGDRP", "AGDRP"],
        "Dollars Paid ($)":       ["$1,234,567", "$987,654", "$0", "<20", "$5,000,000"],
        "Dollars Granted ($)":    ["$1,300,000", "$1,000,000", "$0", "<20", "$5,100,000"],
        "Eligible Claims (No.)":  ["1234", "<20", "0", "<20", "5000"],
        "Total Recieved Claims (No.)": ["1300", "<20", "0", "<20", "5100"],
    })


# ── Synthetic ICA fixture ──────────────────────────────────────────────────

@pytest.fixture
def ica_df() -> pd.DataFrame:
    """Minimal synthetic ICA DataFrame with normalised loss and sentinel claims."""
    return pd.DataFrame({
        "CAT Name":    ["CAT001", "CAT002", "Undeclared", "CAT003"],
        "Event Name":  ["Brisbane Floods 2011", "Black Saturday 2009",
                        "Sydney Hail 1999", "Cyclone Yasi 2011"],
        "Event Start": ["11-Jan-11", "07-Feb-09", "14-Apr-99", "02-Feb-11"],
        "Event Finish":["14-Jan-11", "07-Feb-09", "14-Apr-99", "03-Feb-11"],
        "Type":        ["Flood", "Bushfire", "Hail", "Cyclone"],
        "Year":        [2011, 2009, 1999, 2011],
        "ORIGINAL LOSS VALUE":       ["$2,300,000,000", "$4,400,000,000", "$1,700,000,000", "$1,400,000,000"],
        "NORMALISED LOSS VALUE (2022)": ["$3,100,000,000", "$5,200,000,000", "$2,200,000,000", "$1,600,000,000"],
        "TOTAL CLAIMS RECEIVED":     ["35000", "10000", "<20", "15000"],
        "Domestic Building Claims":  ["20000", "8000", "<20", "10000"],
        "Domestic Content Claims":   ["10000", "1500", "0", "4000"],
        "Domestic Motor Claims":     ["3000", "200", "0", "800"],
        "Commercial Property Claims":["2000", "300", "<20", "200"],
        "State":  ["QLD", "VIC", "NSW", "QLD"],
    })


# ── Synthetic DRFA activations fixture ────────────────────────────────────

@pytest.fixture
def drfa_activations_df() -> pd.DataFrame:
    """Minimal synthetic DRFA activations DataFrame."""
    return pd.DataFrame({
        "agrn":               ["D001", "D001", "D002", "D003"],
        "event_name":         ["2011 Queensland Floods"] * 2 + ["2019 NSW Bushfire", "2021 VIC Floods"],
        "Location_Name":      ["Brisbane", "Ipswich", "Armidale", "Melbourne"],
        "STATE":              ["QLD", "QLD", "NSW", "VIC"],
        "hazard_type":        ["Flood", "Flood", "Bushfire", "Flood"],
        "disaster_start_date":["2011-01-10", "2011-01-10", "2019-11-08", "2021-06-10"],
        "highest_drfa_category_group": ["B", "B", "C", "A"],
        "cat_A":  [0, 0, 0, 1],
        "cat_B":  [1, 1, 0, 0],
        "cat_C":  [0, 0, 1, 0],
        "cat_D":  [0, 0, 0, 0],
        "AGDRP":  [0, 0, 1, 0],
        "DRA":    [0, 0, 0, 0],
    })
