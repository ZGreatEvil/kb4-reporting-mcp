from datetime import date

import pytest

from agent.period import parse_period

TODAY = date(2026, 11, 6)


@pytest.mark.parametrize("question,start,end", [
    # from a point on
    ("tes phishing dari 2026 aja", "2026-01-01", None),
    ("phishing 2026 onwards brp phish prone nya", "2026-01-01", None),
    ("yg gagal phishing lebih dr sekali sejak juli 2026 siapa aja", "2026-07-01", None),
    ("show phishing tests since January 2026", "2026-01-01", None),
    ("yg dari 2026 aja", "2026-01-01", None),
    ("mulai bulan maret", "2026-03-01", None),
    ("since december", "2025-12-01", None),           # a month that has not come yet this year means last year
    ("data 2026 ke atas", "2026-01-01", None),
    ("dari 2026-03-15", "2026-03-15", None),
    # named periods
    ("training campaign tahun ini gimana", "2026-01-01", None),
    ("export hasil phishing tahun lalu ke csv", "2025-01-01", "2025-12-31"),
    ("bandingin sama tahun lalu", "2025-01-01", "2025-12-31"),
    ("training yg lewat tenggat bulan ini brp", "2026-11-01", None),
    ("phishing bulan lalu brp yg ketipu", "2026-10-01", "2026-10-31"),
    ("last month results", "2026-10-01", "2026-10-31"),
    ("minggu ini", "2026-11-02", None),
    # rolling windows
    ("risk score 3 bulan terakhir gmn", "2026-08-06", None),
    ("last 30 days phishing results", "2026-10-07", None),
    ("2 minggu terakhir", "2026-10-23", None),
    ("past 1 year", "2025-11-06", None),
    # quarters
    ("phishing Q3 2026 hasilnya gmn", "2026-07-01", "2026-09-30"),
    ("kuartal 1", "2026-01-01", "2026-03-31"),
    ("and last quarter?", "2026-07-01", "2026-09-30"),
    ("kuartal ini", "2026-10-01", None),
    # ranges
    ("grafik phish prone tes2 dari maret sampe juni 2026", "2026-03-01", "2026-06-30"),
    ("between march and june 2026", "2026-03-01", "2026-06-30"),
    ("antara januari 2025 dan maret 2025", "2025-01-01", "2025-03-31"),
    ("dari 2025 sampai 2026", "2025-01-01", None),     # runs into today: no end filter
    # up to a point
    ("tes phishing sebelum 2026", None, "2025-12-31"),
    ("before july 2026", None, "2026-06-30"),
    ("sampai juni 2026", None, "2026-06-30"),
    # a single month or year
    ("hasil phishing maret 2026", "2026-03-01", "2026-03-31"),
    ("training tahun 2025", "2025-01-01", "2025-12-31"),
    ("phishing in 2026", "2026-01-01", None),
    # a lone year after other words
    ("rekomendasikan modul dari modstore 2026", "2026-01-01", None),
    ("modules 2025 completion", "2025-01-01", "2025-12-31"),
])
def test_periods(question, start, end):
    p = parse_period(question, TODAY)
    assert p is not None, question
    assert (p.start.isoformat() if p.start else None, p.end.isoformat() if p.end else None) == (start, end)


@pytest.mark.parametrize("question", [
    "brp risk score kita skrg",
    "risk kita naik ga dibanding 90 hari lalu",      # a comparison point, not a filter
    "siapa 10 pengguna paling berisiko",
    "tampilkan pengguna 21-40",                       # a page of users, not dates
    "risk score 39.4 itu bagus?",
    "kenapa skor 2 orang itu 47.09",
    "NIST SP 800-50 bilang apa",
    "batas 2010 request per hari",                    # a count, not a year
    "berapa 2025 users yang aktif",
    'modul "Newsletter 2025" sudah dibuka siapa',     # a quoted title
    "risk score 2026 vs 2025",                        # two years: not one period
    "kampanye 2015",                                  # too old to be meant as a filter
])
def test_no_period(question):
    assert parse_period(question, TODAY) is None


def test_period_args_and_label():
    p = parse_period("dari maret sampe juni 2026", TODAY)
    assert p.args() == {"start_date": "2026-03-01", "end_date": "2026-06-30"}
    assert parse_period("dari 2026", TODAY).label() == "2026-01-01 – today"


def test_default_period_is_the_past_twelve_months():
    from agent.period import default_period

    assert default_period(TODAY).args() == {"start_date": "2025-11-06"}
    assert default_period(date(2024, 2, 29)).start == date(2023, 2, 28)  # from a leap day
