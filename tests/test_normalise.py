import pytest

from agent.normalise import normalise


@pytest.mark.parametrize("raw,clean", [
    ("brp risk score kita skrg", "berapa risk score kita sekarang"),
    ("yg ga ngerjain training siapa", "yang tidak mengerjakan training siapa"),
    ("org yg klik phishing terakhir siapa", "orang yang klik phishing terakhir siapa"),
    ("phising terakhir gmn hasilnya", "phishing terakhir bagaimana hasilnya"),
    ("trainingnya udh pd selesai blm", "trainingnya sudah pada selesai belum"),
    ("yg sering ketipu phishing siapa ya", "yang sering tertipu phishing siapa ya"),
    ("siapa aja yg paling beresiko", "siapa saja yang paling berisiko"),
    ("kalo grup gmn?", "kalau grup bagaimana?"),
    ("Brp yg klik dr bln lalu", "berapa yang klik dari bulan lalu"),
    ("how bad r u rn", "how bad are you right now"),
    ("bandingin sm thn lalu", "bandingkan sama tahun lalu"),
])
def test_chat_spellings_are_spelled_out(raw, clean):
    assert normalise(raw) == clean


@pytest.mark.parametrize("text", [
    "Berapa risk score sekarang?",                    # already plain
    "Risiko dr. Rina tinggi?",                       # a title, not "dari"
    "orang kaya dan buat grafik",                    # words with another meaning stay
    "group, ura, gak2, yga",                          # only whole words
    "NIST SP 800-50r1 dan TN 2276",                   # ids untouched
    "risk score 39,4 dan 2.233 enrolment",           # numbers untouched
    "https://example.com/u/r",                        # inside links
])
def test_other_text_is_left_alone(text):
    assert normalise(text) == text


@pytest.mark.parametrize("raw,clean", [
    ("trainnig yg terlmbat siapa aja", "training yang terlambat siapa saja"),
    ("siapa pengguan paling berisko", "siapa pengguna paling berisiko"),
    ("tampilkan grafk level risko", "tampilkan grafik level risiko"),
    ("exprot user ke csv", "export user ke csv"),
    ("grup mna yg plaing berisiko", "grup mana yang paling berisiko"),
    ("rsik score 3 bln trakhir", "risk score 3 bulan terakhir"),
    ("whats our risk scroe", "what is our risk score"),
    ("make a chrat of risk over time", "make a chart of risk over time"),
    ("phisingnya gmn", "phishingnya bagaimana"),
    ("trainignya udh?", "trainingnya sudah?"),
])
def test_typos_of_the_bots_words_are_corrected(raw, clean):
    assert normalise(raw) == clean


@pytest.mark.parametrize("raw,clean", [
    ("siapa yg nunggak training", "siapa yang terlambat training"),
    ("yg kecolongan phishing kemarin siapa", "yang tertipu phishing kemarin siapa"),
    ("training yg udh jatuh tempo tp blm kelar", "training yang sudah tenggat tapi belum selesai"),
    ("pegawai mana yg paling rawan", "karyawan mana yang paling berisiko"),
    ("gimana caranya nurunin klik", "bagaimana caranya menurunkan klik"),
    ("who r the riskiest ppl", "who are the riskiest people"),
])
def test_uncommon_words_and_slang_become_plain_words(raw, clean):
    assert normalise(raw) == clean


@pytest.mark.parametrize("text", [
    "Cari pengguna bernama Trina",                    # name search: nothing corrected
    "Risk score Rina Putri berapa?",                 # capitalised names
    "apa kata NIST soal phishing",                    # acronyms
    "tes phishing testing 2 hasilnya",
    "user1@example.com risikonya",
    "chat model text store used",                     # real words one letter from a bot word
    "scores measured completely organizational",      # endings
    "kesalahan repeated computed",
])
def test_real_words_and_names_are_not_corrected(text):
    assert normalise(text) == text