"""Chat-style Indonesian and English spelled out before the model reads the question ("brp yg klik" -> "berapa
yang klik"). Whole words only, and only spellings with one meaning: "kaya" (rich) or "buat" (make) stay as they are.
Then typos of the words this bot works with are corrected ("trainnig" -> "training"), see `fix_typos`.
"""
from __future__ import annotations

import re

WORDS = {
    # indonesian chat spellings
    "yg": "yang", "brp": "berapa", "brpa": "berapa", "brapa": "berapa",
    "gmn": "bagaimana", "gmna": "bagaimana", "gimana": "bagaimana", "gmana": "bagaimana", "bgmn": "bagaimana",
    "bgmna": "bagaimana", "bagaimna": "bagaimana",
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
    "kpn": "kapan", "mn": "mana", "mna": "mana", "lbh": "lebih", "bnyk": "banyak", "byk": "banyak",
    "smua": "semua", "smw": "semua", "jg": "juga", "hrs": "harus", "dpt": "dapat", "sblm": "sebelum",
    "kmrn": "kemarin", "tgl": "tanggal", "skali": "sekali", "trakhir": "terakhir", "trkhr": "terakhir",
    "gw": "saya", "gue": "saya", "gua": "saya", "tau": "tahu", "gede": "besar",
    "liat": "lihat", "liatin": "tampilkan", "tunjukin": "tampilkan", "tampilin": "tampilkan", "kasih liat": "tampilkan",
    "ngerjain": "mengerjakan", "ngerjakan": "mengerjakan", "ketipu": "tertipu", "kena tipu": "tertipu",
    "nyelesain": "menyelesaikan", "nyelesaiin": "menyelesaikan", "selesain": "menyelesaikan",
    "bandingin": "bandingkan", "bandingkan": "bandingkan", "jelasin": "jelaskan", "kasi": "beri", "kasih": "beri",
    "pengen": "ingin", "pgn": "ingin", "mo": "mau",
    "ngelaporin": "melaporkan", "laporin": "laporkan", "ngelapor": "melapor", "ngukur": "mengukur",
    "ngecek": "mengecek", "ngeklik": "klik", "ngklik": "klik",
    "nurunin": "menurunkan", "turunin": "menurunkan", "ngurangin": "mengurangi", "naikin": "meningkatkan",
    "ningkatin": "meningkatkan", "ngelatih": "melatih",
    # less common words for the things this bot answers, in the plain words its checks look for
    "nunggak": "terlambat", "molor": "terlambat", "telat": "terlambat", "jatuh tempo": "tenggat",
    "kelar": "selesai", "rampung": "selesai",
    "kecolongan": "tertipu", "kejebak": "tertipu", "terjebak": "tertipu", "kena jebak": "tertipu",
    "termakan": "tertipu", "kemakan": "tertipu",
    "rawan": "berisiko", "rentan": "berisiko", "kerawanan": "risiko",
    "pegawai": "karyawan", "staf": "karyawan",
    # common misspellings of the words this bot works with
    "phising": "phishing", "fising": "phishing", "pishing": "phishing", "phissing": "phishing",
    "phisng": "phishing", "phsing": "phishing", "phishng": "phishing", "pising": "phishing",
    "beresiko": "berisiko", "beresikonya": "berisikonya", "resiko": "risiko", "resikonya": "risikonya",
    "trainig": "training", "traning": "training", "trening": "training",
    # english text speak
    "u": "you", "ur": "your", "r": "are", "rn": "right now", "pls": "please", "plz": "please", "thx": "thanks",
    "abt": "about", "bc": "because", "cuz": "because", "w/": "with", "w/o": "without", "smth": "something",
    "ppl": "people", "whats": "what is", "hasnt": "has not", "havent": "have not", "dont": "do not",
    "doesnt": "does not", "didnt": "did not", "wanna": "want to", "gonna": "going to", "dunno": "do not know",
}
# "dr." is a title (dr. Rina), "g." an initial: only expand when no dot follows
PATTERN = re.compile(
    r"(?<![\w/])(" + "|".join(re.escape(w) for w in sorted(WORDS, key=len, reverse=True)) + r")(?![\w/.])",
    re.IGNORECASE,
)

# the words typos are corrected to: what the bot's checks and tools are about, in both languages
VOCAB = """
risk risiko berisiko risikonya score skor level levels phishing training pelatihan campaign campaigns kampanye
pengguna user users grup group groups kelompok grafik chart charts export ekspor laporan report reported reports
lapor melapor melaporkan laporkan dilaporkan terlambat tenggat overdue selesai menyelesaikan completion
penyelesaian persentase percent persen percentage klik click clicked clicks gagal failed tertipu terakhir latest
sekarang berapa siapa bagaimana kenapa mengapa tampilkan tunjukkan tren trend riwayat history bulan tahun minggu
month year week organisasi organisation organization karyawan employee employees awareness kesadaran keamanan
security simulasi simulation efektivitas efektif effective effectiveness mengukur measure meningkatkan improve
menurunkan mengurangi lower reduce average benchmark paling lebih sekali semua daftar riskiest highest lowest
tertinggi terendah modul module modules enrolment enrollment departemen department rentan vulnerable hasil result
results tes test tests email palsu people rate rates finished completed kapabilitas kemampuan
fitur bantuan pertama terbanyak terbaru lanjut berikutnya
"""
# real words that look like a typo of a VOCAB word, and everything spelled out above: never corrected
COMMON = """
yang dari untuk dengan kalau karena tentang antara sejak sampai hingga sebelum sesudah setelah sudah belum tidak
bukan akan bisa dapat harus perlu ingin tahu kita kami saya kamu anda mereka orang setiap kurang sangat juga lagi
masih pernah sering jarang jadi tapi atau jika sama seperti pada dalam oleh depan kedua baru lama tinggi rendah naik
turun besar kecil banyak sedikit nama bernama cari lihat beri buat bikin minta tolong kaya data hasilnya soal cara
caranya program lain sebelumnya tadi barusan kemarin hari divisi bagian mana saja kapan memang terus
what which when where does have could should would will show give list find search named called your their there
they them these those most more less last first next previous since until before after today people person team
many much some please thanks high good best worst fell open opened file over time risky repeat offenders about
with from this that than then were been made make makes date dates name names http https nist know going want
tell testing posts post rata lever chat chats chars text texts model models store used uses using complete
computed repeated clickers kesalahan paging resort code mode note notes host most rest dear finish employer
"""
ENDINGS = ("s", "es", "ed", "d", "ing", "er", "ers", "ly", "al")
WORD_SET = set(VOCAB.split())
KNOWN = WORD_SET | set(COMMON.split()) | {w for v in WORDS.values() for w in v.split()} | {k for k in WORDS if " " not in k}
# where a question names a person, a word next to "bernama" may be a name, so nothing is corrected
NAME_ASK = re.compile(r"\b(nama|bernama|named|called|cari|find|search)\b", re.I)
CHUNK = re.compile(r"\S+")
WORD_CORE = re.compile(r"^(\W*)([A-Za-z]+)(\W*)$")


def _distance(a: str, b: str, limit: int) -> int:
    """letters changed, missing, added or swapped (restricted damerau-levenshtein); stops early past limit"""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = a[i - 1] != b[j - 1]
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], prev2[j - 2] + 1)
        if min(row) > limit:
            return limit + 1
        prev2, prev = prev, row
    return prev[-1]


def _closest(word: str) -> str | None:
    # one slip, two from 10 letters; same first letter, since typos rarely hit it. in short words a replaced
    # letter is usually another real word (text/test, model/modul), so there only a missing, extra or swapped one
    limit = 1 if len(word) < 10 else 2
    best: tuple[int, int, str] | None = None
    for candidate in WORD_SET:
        if candidate[0] != word[0]:
            continue
        if len(word) < 7 and len(candidate) == len(word) and sorted(candidate) != sorted(word):
            continue
        d = _distance(word, candidate, limit)
        if d <= limit and (best is None or (d, -len(candidate)) < best[:2]):
            best = (d, -len(candidate), candidate)
    return best[2] if best else None


def fix_typos(question: str) -> tuple[str, list[tuple[str, str]]]:
    """'trainnig yg terlmbat' -> 'training yg terlambat'. Only words of 4+ letters that are not known, only to a
    VOCAB word, and never names (capitalised mid-sentence, or any word in a name search), acronyms, links,
    emails or anything with digits."""
    if NAME_ASK.search(question):
        return question, []
    fixes: list[tuple[str, str]] = []
    sentence_start = True

    def fix(m: re.Match[str]) -> str:
        nonlocal sentence_start
        chunk = m.group(0)
        starts = sentence_start
        sentence_start = chunk[-1] in ".?!"
        core = WORD_CORE.match(chunk)
        if not core or any(c in chunk for c in "@/\\:"):
            return chunk
        lead, word, trail = core.groups()
        lower = word.lower()
        # capitals inside a word: an acronym (NIST) or a product name
        if len(word) < 4 or lower in KNOWN or (word[0].isupper() and not starts) or any(c.isupper() for c in word[1:]):
            return chunk
        # "scores", "measured": a known word with an ending, not a typo
        stems = [lower[: -len(end)] for end in ENDINGS if lower.endswith(end)]
        if any(s in KNOWN or s + "e" in KNOWN for s in stems) or (lower.endswith("ies") and lower[:-3] + "y" in KNOWN):
            return chunk
        fixed = _closest(lower)
        if fixed is None and lower.endswith("nya") and len(lower) >= 7:
            # "phisingnya", "trainnignya": the word before -nya
            base = lower[:-3]
            base = WORDS[base] if base in WORDS and " " not in WORDS[base] else None if base in KNOWN else _closest(base)
            fixed = base + "nya" if base else None
        if fixed is None:
            return chunk
        fixes.append((word, fixed))
        return lead + fixed + trail

    return CHUNK.sub(fix, question), fixes


def normalise_with_fixes(question: str) -> tuple[str, list[tuple[str, str]]]:
    spelled = PATTERN.sub(lambda m: WORDS[m.group(1).lower()], question)
    return fix_typos(spelled)


def normalise(question: str) -> str:
    return normalise_with_fixes(question)[0]
