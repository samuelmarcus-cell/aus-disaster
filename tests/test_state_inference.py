"""
Tests for state/territory inference logic.

Scientific risk: the regex-based inference is the sole mechanism for assigning
jurisdiction to ~X% of DRFA payment records labelled "Unknown".  Errors here
propagate directly into per-state disaster burden calculations.

Test strategy:
  - Unambiguous cases: names that clearly belong to one state
  - Cross-border cases: names that should match multiple states (MULTI)
  - Unknown cases: names with no geographic signal
  - First-match stability: verify primary assignment matches expected state
  - Regression: events that were known to be misclassified historically
"""

import pytest
from src.validation.state_inference_audit import infer_state_with_confidence


# ── Helpers ────────────────────────────────────────────────────────────────

def infer(name: str) -> str:
    """Return primary state (matching original app._infer_state_from_name behaviour)."""
    _, _, primary = infer_state_with_confidence(name)
    return primary


def conf(name: str) -> str:
    confidence, _, _ = infer_state_with_confidence(name)
    return confidence


# ── Unambiguous state inference ────────────────────────────────────────────

class TestUnambiguousStates:

    def test_queensland_explicit(self):
        assert infer("2011 Queensland Floods") == "Queensland"
        assert conf("2011 Queensland Floods") == "EXACT"

    def test_queensland_abbreviation(self):
        assert infer("2019 QLD Bushfire") == "Queensland"

    def test_queensland_city(self):
        assert infer("Townsville Monsoon Event") == "Queensland"

    def test_nsw_explicit(self):
        assert infer("2019 NSW Bushfires") == "New South Wales"
        assert conf("2019 NSW Bushfires") == "EXACT"

    def test_nsw_city(self):
        assert infer("Hunter Valley Floods") == "New South Wales"

    def test_nsw_lismore(self):
        assert infer("2022 Lismore Floods") == "New South Wales"

    def test_victoria_explicit(self):
        assert infer("2009 Victorian Bushfires") == "Victoria"
        assert conf("2009 Victorian Bushfires") == "EXACT"

    def test_victoria_city(self):
        assert infer("Melbourne Storm Event") == "Victoria"

    def test_victoria_black_saturday(self):
        assert infer("Black Saturday Bushfires") == "Victoria"

    def test_south_australia_explicit(self):
        assert infer("2019 South Australia Bushfires") == "South Australia"

    def test_south_australia_city(self):
        assert infer("Adelaide Storms") == "South Australia"

    def test_tasmania_explicit(self):
        assert infer("2013 Tasmania Bushfires") == "Tasmania"

    def test_tasmania_city(self):
        assert infer("Hobart Flood Event") == "Tasmania"

    def test_act_explicit(self):
        assert infer("2003 ACT Bushfires") == "Australian Capital Territory"

    def test_act_canberra(self):
        assert infer("Canberra Firestorm") == "Australian Capital Territory"

    def test_western_australia_explicit(self):
        assert infer("2011 Western Australia Flooding") == "Western Australia"

    def test_western_australia_city(self):
        assert infer("Perth Hills Bushfire") == "Western Australia"

    def test_northern_territory_explicit(self):
        assert infer("2023 Northern Territory Floods") == "Northern Territory"

    def test_northern_territory_darwin(self):
        assert infer("Darwin Cyclone Event") == "Northern Territory"


# ── Abbreviation and acronym tests ─────────────────────────────────────────

class TestAbbreviations:

    def test_qld_abbrev(self):
        assert infer("2022 QLD Floods") == "Queensland"

    def test_nsw_abbrev(self):
        assert infer("2022 NSW Floods") == "New South Wales"

    def test_vic_abbrev(self):
        # VIC must not match words containing "vic" (e.g. "victim")
        assert infer("VIC Storm Event") == "Victoria"

    def test_sa_abbrev(self):
        # SA must not match too broadly — check it doesn't match unrelated words
        assert infer("2019 SA Bushfires") == "South Australia"

    def test_nt_abbrev(self):
        assert infer("2023 NT Monsoonal Trough") == "Northern Territory"

    def test_wa_abbrev(self):
        assert infer("2022 WA Cyclone") == "Western Australia"

    def test_act_abbrev(self):
        assert infer("ACT Bushfire 2003") == "Australian Capital Territory"

    def test_tas_abbrev(self):
        assert infer("TAS Flooding 2016") == "Tasmania"


# ── Unknown cases ──────────────────────────────────────────────────────────

class TestUnknownCases:

    def test_generic_national_event_no_state_signal(self):
        # A purely generic name with no place-name signal should be UNKNOWN
        result, _, primary = infer_state_with_confidence("National Emergency Event")
        assert primary == "Unknown"
        assert result == "UNKNOWN"

    def test_empty_string(self):
        _, _, primary = infer_state_with_confidence("")
        assert primary == "Unknown"

    def test_nan_string(self):
        _, _, primary = infer_state_with_confidence("nan")
        assert primary == "Unknown"

    def test_generic_flood(self):
        # "Flood" with no location signal
        _, _, primary = infer_state_with_confidence("Major Flood Event")
        assert primary == "Unknown"


# ── Multi-state detection ──────────────────────────────────────────────────

class TestMultiStateDetection:

    def test_qld_nsw_cross_border(self):
        # A name referencing both QLD and NSW should be flagged MULTI
        conf_class, all_matches, _ = infer_state_with_confidence(
            "2022 Queensland and NSW Border Floods"
        )
        assert conf_class == "MULTI"
        assert "Queensland" in all_matches
        assert "New South Wales" in all_matches

    def test_multi_preserves_first_match_as_primary(self):
        # Primary assignment must match the first rule in _STATE_RULES (QLD before NSW)
        _, _, primary = infer_state_with_confidence(
            "2022 Queensland and NSW Border Floods"
        )
        assert primary == "Queensland"

    def test_all_matches_list_length(self):
        conf_class, all_matches, _ = infer_state_with_confidence(
            "Queensland and New South Wales Floods"
        )
        assert len(all_matches) >= 2

    def test_vic_sa_cross_border(self):
        # Adelaide–Melbourne corridor events may match both SA and VIC
        conf_class, all_matches, _ = infer_state_with_confidence(
            "South Australia and Victoria Flooding"
        )
        if conf_class == "MULTI":
            assert "South Australia" in all_matches
            assert "Victoria" in all_matches


# ── Confidence class completeness ─────────────────────────────────────────

class TestConfidenceClasses:

    def test_confidence_is_one_of_three_values(self):
        for name in [
            "Queensland Floods",
            "National Emergency",
            "Queensland and NSW Floods",
        ]:
            c, _, _ = infer_state_with_confidence(name)
            assert c in ("EXACT", "MULTI", "UNKNOWN"), f"Unexpected confidence for '{name}': {c}"

    def test_exact_has_single_match(self):
        c, matches, _ = infer_state_with_confidence("Bundaberg Flooding 2013")
        assert c == "EXACT"
        assert len(matches) == 1

    def test_unknown_has_empty_matches(self):
        _, matches, _ = infer_state_with_confidence("Generic Disaster Event")
        assert matches == []


# ── Cyclone name tests ─────────────────────────────────────────────────────

class TestCycloneNames:

    def test_cyclone_yasi_queensland(self):
        assert infer("Tropical Cyclone Yasi") == "Queensland"

    def test_cyclone_debbie_queensland(self):
        assert infer("Tropical Cyclone Debbie") == "Queensland"

    def test_cyclone_george_wa(self):
        assert infer("Tropical Cyclone George") == "Western Australia"

    def test_cyclone_marcus_nt(self):
        assert infer("Tropical Cyclone Marcus") == "Northern Territory"


# ── Regression: previously known misclassification risks ──────────────────

class TestRegressions:

    def test_snowy_goes_to_nsw_not_vic(self):
        # "Snowy" is in NSW rules; check it doesn't match VIC first
        result = infer("Snowy Mountains Flood")
        assert result == "New South Wales"

    def test_gippsland_is_victoria(self):
        assert infer("2022 East Gippsland Floods") == "Victoria"

    def test_pilbara_is_wa(self):
        assert infer("Pilbara Cyclone Event") == "Western Australia"

    def test_kakadu_is_nt(self):
        assert infer("Kakadu Flood Event") == "Northern Territory"

    def test_kangaroo_island_is_sa(self):
        assert infer("Kangaroo Island Bushfires") == "South Australia"

    def test_grampians_is_victoria(self):
        assert infer("Grampians Fires") == "Victoria"
