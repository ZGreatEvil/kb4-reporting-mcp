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
