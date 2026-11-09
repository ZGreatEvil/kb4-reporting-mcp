"""The date range a question asks for ("dari 2026", "3 bulan terakhir", "Q3 2026", "since January"), worked out
in code: the small model left it out or guessed, and a question about 2026 came back with data from 2024.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    "januari": 1, "january": 1, "jan": 1,
    "februari": 2, "february": 2, "feb": 2, "pebruari": 2,
    "maret": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "june": 6, "jun": 6,
    "juli": 7, "july": 7, "jul": 7,
    "agustus": 8, "august": 8, "agu": 8, "agt": 8, "aug": 8,
    "september": 9, "sept": 9, "sep": 9,
    "oktober": 10, "october": 10, "okt": 10, "oct": 10,
    "november": 11, "nov": 11, "nopember": 11,
    "desember": 12, "december": 12, "des": 12, "dec": 12,
}
MONTH = r"(?:" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")"
YEAR = r"(?:20\d{2})"
# a point in time: "juli 2026", "juli", "2026", "2026-07-15", "15/07/2026"
POINT = rf"(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|{MONTH}\s+{YEAR}|{MONTH}|{YEAR})"
FROM = r"(?:dari|sejak|mulai|semenjak|from|since|starting|after|setelah|sesudah)"
TO = r"(?:sampai|sampe|smp|hingga|s\.?d\.?|until|till|to|through|-|–|dan|and)"
BEFORE = r"(?:sebelum|before|prior to)"
UNTIL = r"(?:sampai|sampe|hingga|until|up to)"
ONWARDS = r"(?:onwards?|and later|ke ?atas|dan seterusnya|seterusnya|ke depan|and after)"
UNITS = {
    "hari": "day", "day": "day", "days": "day",
    "minggu": "week", "pekan": "week", "week": "week", "weeks": "week",
    "bulan": "month", "bln": "month", "month": "month", "months": "month",
    "tahun": "year", "thn": "year", "year": "year", "years": "year",
}
UNIT = r"(?:" + "|".join(UNITS) + r")"


@dataclass(frozen=True)
class Period:
    start: date | None
    end: date | None

    def args(self) -> dict[str, str]:
        out = {}
        if self.start:
            out["start_date"] = self.start.isoformat()
        if self.end:
            out["end_date"] = self.end.isoformat()
        return out

    def label(self) -> str:
        return f"{self.start.isoformat() if self.start else '…'} – {self.end.isoformat() if self.end else 'today'}"


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(day: date, months: int) -> date:
    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _span(text: str, today: date, year_hint: int | None = None) -> tuple[date, date] | None:
    """the first and last day a written point covers"""
    text = text.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
        d = date(int(m[1]), int(m[2]), int(m[3]))
        return d, d
    if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text):
        d = date(int(m[3]), int(m[2]), int(m[1]))
        return d, d
    if m := re.fullmatch(rf"({MONTH})\s+({YEAR})", text):
        month, year = MONTHS[m[1]], int(m[2])
        return date(year, month, 1), _month_end(year, month)
    if text in MONTHS:
        month = MONTHS[text]
        # a month without a year: the latest one that has started
        year = year_hint or (today.year if month <= today.month else today.year - 1)
        return date(year, month, 1), _month_end(year, month)
    if re.fullmatch(YEAR, text):
        year = int(text)
        return date(year, 1, 1), date(year, 12, 31)
    return None


def _open_end(end: date, today: date) -> date | None:
    # a range that runs into the future is "until today": no end filter
    return None if end >= today else end


def parse_period(question: str, today: date | None = None) -> Period | None:
    today = today or date.today()
    q = " " + re.sub(r"\s+", " ", question.lower()) + " "

    # between two points: "dari maret sampe juni 2026", "between march and june 2026", "2025-2026"
    if m := re.search(rf"(?:{FROM}|antara|between)?\s*\b({POINT})\s*{TO}\s*({POINT})\b", q):
        right = _span(m[2], today)
        hint = int(re.search(YEAR, m[2])[0]) if re.search(YEAR, m[2]) else None
        left = _span(m[1], today, hint)
        if left and right and left[0] <= right[1] and (re.search(rf"{FROM}|antara|between", m[0]) or re.search(YEAR, m[0])):
            return Period(left[0], _open_end(right[1], today))

    # quarters: "q3 2026", "kuartal 3", "last quarter", "kuartal lalu", "this quarter"
    if m := re.search(rf"\b(?:q|kuartal|quarter|triwulan)\s*([1-4])\b(?:\s*({YEAR}))?", q):
        quarter, year = int(m[1]), int(m[2]) if m[2] else today.year
        start = date(year, 3 * quarter - 2, 1)
        return Period(start, _open_end(_month_end(year, 3 * quarter), today))
    current_q = (today.month - 1) // 3 + 1
    if re.search(r"\b(?:last quarter|kuartal (?:lalu|kemarin|sebelumnya)|triwulan lalu)\b", q):
        year, quarter = (today.year, current_q - 1) if current_q > 1 else (today.year - 1, 4)
        return Period(date(year, 3 * quarter - 2, 1), _month_end(year, 3 * quarter))
    if re.search(r"\b(?:this quarter|kuartal ini|triwulan ini)\b", q):
        return Period(date(today.year, 3 * current_q - 2, 1), None)

    # the last n days / weeks / months / years ("3 bulan terakhir", "last 30 days", "30 hari ke belakang")
    if m := re.search(rf"\b(?:last|past)\s+(\d{{1,3}})\s+({UNIT})\b|\b(\d{{1,3}})\s+({UNIT})\s+(?:terakhir|belakangan|ke ?belakang|terakhir ini)\b", q):
        n, unit = (int(m[1]), UNITS[m[2]]) if m[1] else (int(m[3]), UNITS[m[4]])
        if unit == "day":
            start = today - timedelta(days=n)
        elif unit == "week":
            start = today - timedelta(weeks=n)
        elif unit == "month":
            start = _add_months(today, -n)
        else:
            start = date(today.year - n, today.month, min(today.day, 28))
        return Period(start, None)

    # this / last year, month, week
    named = {
        r"tahun ini|this year": (date(today.year, 1, 1), None),
        r"tahun (?:lalu|kemarin|sebelumnya)|last year|previous year": (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)),
        r"bulan ini|this month": (today.replace(day=1), None),
        r"minggu ini|pekan ini|this week": (today - timedelta(days=today.weekday()), None),
    }
    for pattern, (start, end) in named.items():
        if re.search(rf"\b(?:{pattern})\b", q):
            return Period(start, end)
    if re.search(r"\b(?:bulan (?:lalu|kemarin|sebelumnya)|last month|previous month)\b", q):
        first = _add_months(today.replace(day=1), -1)
        return Period(first, _month_end(first.year, first.month))
    if re.search(r"\b(?:minggu (?:lalu|kemarin)|pekan lalu|last week)\b", q):
        monday = today - timedelta(days=today.weekday() + 7)
        return Period(monday, monday + timedelta(days=6))

    # from a point on: "dari 2026", "sejak juli 2026", "since january", "2026 onwards"
    if m := re.search(rf"\b{FROM}\s+(?:tahun\s+|bulan\s+|awal\s+)?({POINT})\b", q):
        if span := _span(m[1], today):
            return Period(span[0], None)
    if m := re.search(rf"\b({POINT})\s+{ONWARDS}", q):
        if span := _span(m[1], today):
            return Period(span[0], None)

    # up to a point: "sebelum 2026", "before july 2026", "sampai juni 2026"
    if m := re.search(rf"\b{BEFORE}\s+(?:tahun\s+|bulan\s+)?({POINT})\b", q):
        if span := _span(m[1], today):
            return Period(None, span[0] - timedelta(days=1))
    if m := re.search(rf"\b{UNTIL}\s+(?:tahun\s+|bulan\s+|akhir\s+)?({POINT})\b", q):
        if span := _span(m[1], today):
            return Period(None, _open_end(span[1], today))

    # one month or year on its own: "di bulan maret 2026", "tahun 2025", "in 2025", "maret 2026"
    if m := re.search(rf"\b(?:{MONTH})\s+{YEAR}\b", q):
        span = _span(m[0], today)
        return Period(span[0], _open_end(span[1], today))
    if m := re.search(rf"\b(?:tahun|in|di|pada|during|selama)\s+({YEAR})\b", q):
        span = _span(m[1], today)
        return Period(span[0], _open_end(span[1], today))
    return None


def default_period(today: date | None = None) -> Period:
    """what a question without a period covers: the past 12 months"""
    today = today or date.today()
    return Period(_add_months(today, -12), None)
