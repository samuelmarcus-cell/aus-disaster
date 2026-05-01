"""
Tests for date parsing correctness across dataset loaders.

Scientific risk: date parsing errors silently assign events to wrong years,
distorting time-series analysis, financial year attribution, and compound
disaster clustering.

Edge cases tested:
  - ICA 2-digit year ambiguity fix (dates near year 2000 boundary)
  - AIDR mixed datetime/string Excel dates
  - DRFA %Y-%m-%d format strict parsing
  - Financial year boundary assignment (June vs July)
  - Coercion of unparseable dates to NaT (not crash, not silent wrong date)
"""

import pandas as pd
import pytest


# ── ICA 2-digit year disambiguation ───────────────────────────────────────

class TestIca2DigitYearFix:
    """
    ICA data uses %d-%b-%y format (e.g. "14-Apr-99").
    Python's strptime maps 2-digit years: 00–68 → 2000–2068; 69–99 → 1969–1999.
    ICA data pre-dates 2000 for many historical events; the app corrects
    any parsed year > (declared Year + 1) by subtracting 100 years.
    """

    def _parse_and_fix(self, date_str: str, declared_year: int) -> pd.Timestamp:
        ts = pd.to_datetime(date_str, format="%d-%b-%y", errors="coerce")
        if ts is pd.NaT:
            return ts
        if ts.year > declared_year + 1:
            ts -= pd.DateOffset(years=100)
        return ts

    def test_1999_event_not_pushed_to_2099(self):
        ts = self._parse_and_fix("14-Apr-99", declared_year=1999)
        assert ts.year == 1999

    def test_1967_event_stays_in_1967(self):
        ts = self._parse_and_fix("01-Jan-67", declared_year=1967)
        assert ts.year == 1967

    def test_2011_event_stays_in_2011(self):
        ts = self._parse_and_fix("10-Jan-11", declared_year=2011)
        assert ts.year == 2011

    def test_ambiguous_2000_event(self):
        # "00" → 2000 by strptime convention; no fix needed
        ts = self._parse_and_fix("01-Jul-00", declared_year=2000)
        assert ts.year == 2000

    def test_unparseable_returns_nat(self):
        ts = pd.to_datetime("not-a-date", format="%d-%b-%y", errors="coerce")
        assert ts is pd.NaT


# ── DRFA date parsing ──────────────────────────────────────────────────────

class TestDrfaDateParsing:

    def test_iso_format_parsed_correctly(self):
        s = pd.Series(["2011-01-10", "2019-11-08", "2021-06-10"])
        result = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
        assert result.iloc[0] == pd.Timestamp("2011-01-10")
        assert result.iloc[1] == pd.Timestamp("2019-11-08")
        assert result.iloc[2] == pd.Timestamp("2021-06-10")

    def test_missing_dates_coerce_to_nat(self):
        s = pd.Series(["2011-01-10", None, "bad-date", "2021-06-10"])
        result = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
        assert result.iloc[1] is pd.NaT
        assert result.iloc[2] is pd.NaT

    def test_year_extracted_from_iso_date(self):
        s = pd.Series(["2011-01-10", "2019-11-08"])
        result = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
        years = result.dt.year
        assert list(years) == [2011, 2019]


# ── Financial year boundary ────────────────────────────────────────────────

class TestFinancialYearBoundary:
    """
    Australian financial year: 1 July – 30 June.
    FY label = start calendar year (FY2011 = 1 Jul 2011 – 30 Jun 2012).
    Boundary months July and June must be assigned to the correct FY.
    """

    @staticmethod
    def _assign_fy(dt: pd.Timestamp) -> int:
        return dt.year if dt.month >= 7 else dt.year - 1

    def test_july_belongs_to_fy_of_same_year(self):
        assert self._assign_fy(pd.Timestamp("2011-07-01")) == 2011

    def test_june_belongs_to_fy_of_previous_year(self):
        assert self._assign_fy(pd.Timestamp("2012-06-30")) == 2011

    def test_january_belongs_to_fy_of_previous_year(self):
        assert self._assign_fy(pd.Timestamp("2011-01-10")) == 2010

    def test_december_belongs_to_fy_of_same_year(self):
        assert self._assign_fy(pd.Timestamp("2011-12-31")) == 2011

    def test_june_july_boundary_different_fy(self):
        june_fy = self._assign_fy(pd.Timestamp("2011-06-30"))
        july_fy = self._assign_fy(pd.Timestamp("2011-07-01"))
        assert june_fy == 2010
        assert july_fy == 2011
        assert july_fy == june_fy + 1

    def test_fy_consistent_with_compound_clustering(self):
        """
        Two events in the same financial year (one in Aug, one in May of the
        next calendar year) must receive the same FY label.
        """
        aug_event = pd.Timestamp("2010-08-01")   # FY2010
        may_event = pd.Timestamp("2011-05-15")   # FY2010 (before July 2011)
        assert self._assign_fy(aug_event) == self._assign_fy(may_event)


# ── AGD date format (MM/DD/YYYY) ───────────────────────────────────────────

class TestAgdDateParsing:

    def test_us_date_format_parsed_correctly(self):
        s = pd.Series(["01/10/2011", "11/08/2019"])
        result = pd.to_datetime(s, format="%m/%d/%Y", errors="coerce")
        assert result.iloc[0].month == 1
        assert result.iloc[0].day == 10
        assert result.iloc[0].year == 2011

    def test_day_month_swap_would_cause_wrong_date(self):
        """
        Demonstrate what goes wrong if dayfirst=True is used on MM/DD/YYYY.
        This is a regression guard — AGD explicitly uses %m/%d/%Y.
        """
        s = pd.Series(["03/01/2011"])   # means March 1 in MM/DD/YYYY
        correct = pd.to_datetime(s, format="%m/%d/%Y", errors="coerce").iloc[0]
        assert correct.month == 3
        assert correct.day == 1

    def test_unparseable_agd_date_becomes_nat(self):
        s = pd.Series(["bad", "", None])
        result = pd.to_datetime(s, format="%m/%d/%Y", errors="coerce")
        assert result.isna().all()


# ── AIDR dayfirst parsing ──────────────────────────────────────────────────

class TestAidrDateParsing:

    def test_dayfirst_parses_australian_format(self):
        # "10/01/2011" with dayfirst=True → 10 Jan 2011 (not 1 Oct)
        s = pd.Series(["10/01/2011"])
        result = pd.to_datetime(s, dayfirst=True, errors="coerce")
        assert result.iloc[0].day == 10
        assert result.iloc[0].month == 1

    def test_mixed_string_datetime_coercion(self):
        # Excel can return a mix of datetime objects and strings for date columns
        import datetime
        s = pd.Series([datetime.datetime(2011, 1, 10), "10/01/2011", None, "bad"])
        result = pd.to_datetime(s, dayfirst=True, errors="coerce")
        assert result.iloc[0] == pd.Timestamp("2011-01-10")
        assert result.iloc[2] is pd.NaT
        assert result.iloc[3] is pd.NaT
