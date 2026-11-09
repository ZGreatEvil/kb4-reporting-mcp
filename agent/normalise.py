"""Chat-style Indonesian and English spelled out before the model reads the question ("brp yg klik" -> "berapa
yang klik"). Whole words only, and only spellings with one meaning: "kaya" (rich) or "buat" (make) stay as they are.
"""
from __future__ import annotations

import re

WORDS = {
    # indonesian chat spellings
    "yg": "yang", "brp": "berapa", "brpa": "berapa", "brapa": "berapa",
    "gmn": "bagaimana", "gmna": "bagaimana", "gimana": "bagaimana", "gmana": "bagaimana", "bgmn": "bagaimana",
    "skrg": "sekarang", "skrng": "sekarang", "skg": "sekarang",
    "org": "orang", "orng": "orang",
    "ga": "tidak", "gak": "tidak", "gk": "tidak", "nggak": "tidak", "ngga": "tidak", "engga": "tidak", "enggak": "tidak",
    "kagak": "tidak", "tdk": "tidak", "g": "tidak",
    "udh": "sudah", "udah": "sudah", "sdh": "sudah", "dah": "sudah",
    "blm": "belum", "belom": "belum", "blom": "belum",
    "klo": "kalau", "kalo": "kalau", "kl": "kalau",
    "kek": "seperti", "kyk": "seperti", "kayak": "seperti", "spt": "seperti",
    "dr": "dari", "sm": "sama", "ama": "sama",
    "knp": "kenapa", "napa": "kenapa", "ngapa": "kenapa", "knapa": "kenapa",
    "utk": "untuk", "dgn": "dengan", "dg": "dengan", "krn": "karena", "karna": "karena",
    "tp": "tapi", "jd": "jadi", "jdi": "jadi", "lg": "lagi", "lgi": "lagi", "bs": "bisa", "bsa": "bisa",
    "trs": "terus", "trus": "terus", "aja": "saja", "aj": "saja", "doang": "saja",
    "bgt": "sangat", "banget": "sangat", "pd": "pada", "msh": "masih", "masi": "masih",
    "emg": "memang", "emang": "memang", "dlm": "dalam", "dll": "dan lain-lain",
    "ni": "ini", "nih": "ini", "tu": "itu", "tuh": "itu",
    "thn": "tahun", "bln": "bulan", "mgg": "minggu", "hr": "hari",
    "liat": "lihat", "liatin": "tampilkan", "tunjukin": "tampilkan", "tampilin": "tampilkan", "kasih liat": "tampilkan",
    "ngerjain": "mengerjakan", "ngerjakan": "mengerjakan", "ketipu": "tertipu", "kena tipu": "tertipu",
    "nyelesain": "menyelesaikan", "nyelesaiin": "menyelesaikan", "selesain": "menyelesaikan",
    "bandingin": "bandingkan", "bandingkan": "bandingkan", "jelasin": "jelaskan", "kasi": "beri", "kasih": "beri",
    "pengen": "ingin", "pgn": "ingin", "mo": "mau",
    # common misspellings of the words this bot works with
    "phising": "phishing", "fising": "phishing", "pishing": "phishing", "phissing": "phishing",
    "beresiko": "berisiko", "beresikonya": "berisikonya", "resiko": "risiko", "resikonya": "risikonya",
    "trainig": "training", "traning": "training", "trening": "training",
    # english text speak
    "u": "you", "ur": "your", "r": "are", "rn": "right now", "pls": "please", "plz": "please", "thx": "thanks",
    "abt": "about", "bc": "because", "cuz": "because", "w/": "with", "w/o": "without", "smth": "something",
}
# "dr." is a title (dr. Rina), "g." an initial: only expand when no dot follows
PATTERN = re.compile(
    r"(?<![\w/])(" + "|".join(re.escape(w) for w in sorted(WORDS, key=len, reverse=True)) + r")(?![\w/.])",
    re.IGNORECASE,
)


def normalise(question: str) -> str:
    return PATTERN.sub(lambda m: WORDS[m.group(1).lower()], question)
