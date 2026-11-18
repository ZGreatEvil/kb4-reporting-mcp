"""User-facing server messages in every supported language, so nothing comes out half-translated."""
from __future__ import annotations

from typing import Any, Literal

Language = Literal["id", "en"]
DEFAULT_LANGUAGE: Language = "id"

# name used in the system prompt
LANGUAGE_NAMES: dict[str, str] = {"id": "Indonesian", "en": "English"}

MESSAGES: dict[str, dict[str, str]] = {
    "llm_timeout": {
        "id": "Model tidak menjawab dalam {seconds:.0f} detik. Coba pertanyaan yang lebih sempit, atau naikkan LLM_TIMEOUT_SECONDS.",
        "en": "The model did not answer within {seconds:.0f} seconds. Try a narrower question, or raise LLM_TIMEOUT_SECONDS.",
    },
    "llm_unreachable": {
        "id": "Tidak bisa terhubung ke server LLM di {url}. Pastikan Ollama sedang berjalan.",
        "en": "Cannot reach the LLM server at {url}. Make sure Ollama is running.",
    },
    "llm_model_missing": {
        "id": "Model '{model}' belum ada di server LLM. Admin: buat dengan perintah ollama create kb4-analyst -f ollama\\Modelfile (README langkah 3), atau ollama pull {model} untuk model lain.",
        "en": "Model '{model}' is not on the LLM server. Admins: create it with the command ollama create kb4-analyst -f ollama\\Modelfile (README step 3), or ollama pull {model} for another model.",
    },
    "llm_context": {
        "id": "Percakapan melebihi context length model. Mulai percakapan baru atau persempit pertanyaan. Admin: naikkan num_ctx di ollama\\Modelfile jika memori GPU cukup.",
        "en": "The conversation exceeds the model's context length. Start a new conversation or narrow the question. Admins: raise num_ctx in ollama\\Modelfile if GPU memory allows.",
    },
    "llm_bad_request": {
        "id": "Server LLM menolak permintaan (HTTP 400).",
        "en": "The LLM server rejected the request (HTTP 400).",
    },
    "llm_http": {
        "id": "Server LLM mengembalikan error HTTP {status}.",
        "en": "The LLM server returned HTTP error {status}.",
    },
    "llm_no_choice": {
        "id": "Server LLM tidak mengembalikan jawaban.",
        "en": "The LLM server returned no answer.",
    },
    "empty_question": {
        "id": "Masukkan pertanyaan terlebih dahulu.",
        "en": "Please enter a question first.",
    },
    "loop_limit": {
        "id": "Batas maksimum {loops} putaran tool call tercapai tanpa jawaban akhir. Coba persempit pertanyaan.",
        "en": "Reached the limit of {loops} tool-call rounds without a final answer. Try a narrower question.",
    },
    "cut_off": {
        "id": "_(Jawaban terpotong karena batas LLM_MAX_TOKENS.)_",
        "en": "_(Answer cut off by the LLM_MAX_TOKENS limit.)_",
    },
    "no_answer": {
        "id": "Model tidak memberikan jawaban.",
        "en": "The model did not give an answer.",
    },
    "nudge": {
        "id": "Tuliskan jawaban akhir untuk pengguna sekarang, berdasarkan hasil tool di atas.",
        "en": "Write the final answer for the user now, based on the tool results above.",
    },
    # used inside the system prompt so the model writes these in the user's language
    "no_prediction": {
        "id": "Saya tidak bisa memprediksi nilai di masa depan.",
        "en": "I can't predict future values.",
    },
    "facts_heading": {
        "id": "Fakta utama",
        "en": "Key facts",
    },
    "why_heading": {
        "id": "Kenapa",
        "en": "Why",
    },
    "rewrite_language": {
        "id": "Tulis ulang jawaban Anda sebelumnya sepenuhnya dalam Bahasa Indonesia, tanpa karakter Mandarin atau bahasa lain. Isi dan angkanya tetap sama.",
        "en": "Rewrite your previous answer entirely in English, without Chinese characters or any other language. Keep the content and numbers the same.",
    },
    "must_use_tool": {
        "id": "Jawaban Anda berisi angka, tetapi tidak ada tool yang dipanggil untuk pertanyaan ini. Jika pertanyaan ini butuh data KnowBe4, panggil tool yang tepat lalu jawab hanya dari hasilnya. Jika tidak butuh data (misalnya penolakan atau penjelasan umum), jawab ulang pertanyaan yang sama tanpa angka dari pesan sebelumnya.",
        "en": "Your answer contains numbers, but no tool was called for this question. If the question needs KnowBe4 data, call the right tool and answer only from its result. If it does not (for example a refusal or a general explanation), answer the same question again without numbers from earlier messages.",
    },
    "call_report": {
        "id": "Data siapa yang melaporkan belum diambil. Panggil phishing_test_detail sekarang, lalu jawab dari hasilnya.",
        "en": "Who reported it has not been fetched. Call phishing_test_detail now, then answer from its result.",
    },
    "period_current_only": {
        "id": "Catatan: data ini adalah kondisi saat ini. KnowBe4 tidak menyimpannya per periode, jadi periode {period} tidak bisa diterapkan.",
        "en": "Note: this is today's data. KnowBe4 does not keep it per period, so the period {period} could not be applied.",
    },
    "ungrounded_numbers": {
        "id": "Angka berikut tidak ada di hasil tool: {numbers}. Tulis ulang jawaban Anda hanya dengan angka persis dari hasil tool. Jangan menghitung, memperkirakan atau menambah angka sendiri.",
        "en": "These numbers are not in the tool results: {numbers}. Rewrite your answer using only numbers exactly as the tools gave them. Do not calculate, estimate or add numbers yourself.",
    },
    "kb4_unreachable": {
        "id": "**KnowBe4 tidak dapat dihubungi saat ini, jadi saya tidak bisa mengambil datanya.** Coba lagi sebentar lagi. Jika terus terjadi, admin dapat memeriksa koneksi internet server.",
        "en": "**KnowBe4 cannot be reached right now, so I could not fetch the data.** Try again in a moment. If it keeps happening, admins can check the server's internet connection.",
    },
    "kb4_daily_limit": {
        "id": "**Batas harian permintaan ke KnowBe4 sudah tercapai, jadi saya tidak bisa mengambil data baru.** Coba lagi nanti; batas ini dihitung per 24 jam.",
        "en": "**The daily limit of requests to KnowBe4 has been reached, so I cannot fetch new data.** Try again later; the limit counts the last 24 hours.",
    },
    "kb4_key_rejected": {
        "id": "**KnowBe4 menolak API key yang dipakai, jadi saya tidak bisa mengambil data.** Admin: periksa Reporting API key di .env (jalankan test_knowbe4.py).",
        "en": "**KnowBe4 rejected the API key in use, so I cannot fetch data.** Admins: check the Reporting API key in .env (run test_knowbe4.py).",
    },
    "no_data_answer": {
        "id": "Maaf, saya belum berhasil mengambil data untuk pertanyaan ini. Coba ulangi dengan pertanyaan yang lebih spesifik.",
        "en": "Sorry, I couldn't fetch the data for this question. Please try again with a more specific question.",
    },
    "call_page": {
        "id": "Panggil list_users_page dengan offset={offset} sekarang, lalu tampilkan user tersebut dalam tabel. Jangan pakai data dari pesan sebelumnya.",
        "en": "Call list_users_page with offset={offset} now, then show those users in a table. Do not reuse data from earlier messages.",
    },
    "fresh_data": {
        "id": "Data diambil langsung dari KnowBe4 barusan.",
        "en": "Data fetched from KnowBe4 just now.",
    },
    "fresh_recent": {
        "id": "Data sudah diambil ulang dari KnowBe4 {seconds} detik yang lalu, jadi masih terbaru.",
        "en": "Data was refetched from KnowBe4 {seconds} seconds ago, so it is still current.",
    },
    "library_line": {
        "id": "Pustaka akun berisi {total} konten ({retired} sudah retired); {never} belum pernah ditugaskan ke siapa pun.",
        "en": "The account's library has {total} content items ({retired} retired); {never} have never been assigned to anyone.",
    },
    "library_line_period": {
        "id": "Dari {period}: {total} konten baru ({published} diterbitkan KnowBe4, {added} ditambahkan ke akun); {never} belum pernah ditugaskan ke siapa pun.",
        "en": "From {period}: {total} content items are new ({published} published by KnowBe4, {added} added to the account); {never} have never been assigned to anyone.",
    },
    "read_only": {
        "id": "**Saya hanya membaca data KnowBe4, jadi saya tidak bisa mengubah, menambah atau menghapus apa pun.** Lakukan perubahan itu di console KnowBe4. Saya bisa membantu melihat datanya, misalnya siapa saja yang terkait.",
        "en": "**I only read KnowBe4 data, so I can't change, add or delete anything.** Make that change in the KnowBe4 console. I can help you look at the data, for example who it would affect.",
    },
    "unknown_console": {
        "id": "**Tidak ada console bernama \"{name}\".** Console yang tersedia: {consoles}.",
        "en": "**There is no console called \"{name}\".** Available consoles: {consoles}.",
    },
    "nothing_to_continue": {
        "id": "Belum ada jawaban sebelumnya untuk dilanjutkan. Tanyakan sesuatu tentang data KnowBe4 Anda, misalnya \"berapa risk score sekarang?\"",
        "en": "There is no earlier answer to continue yet. Ask something about your KnowBe4 data, for example \"what is our risk score now?\"",
    },
    "file_status_line": {"id": "Status di file: {counts}.", "en": "Status in the file: {counts}."},
    "file_line_csv": {"id": "File CSV sudah dibuat: {rows} baris.", "en": "The CSV file is ready: {rows} rows."},
    "file_line_xlsx": {"id": "File Excel sudah dibuat: {rows} baris.", "en": "The Excel file is ready: {rows} rows."},
    "console_no_key": {
        "id": "**Console \"{name}\" belum punya API key, jadi datanya tidak bisa dibaca.** Admin bisa menambahkan key-nya di file .env. Console yang bisa dipakai: {consoles}.",
        "en": "**The \"{name}\" console has no API key yet, so its data can't be read.** An admin can add its key in the .env file. Consoles you can use: {consoles}.",
    },
    "call_find_user": {
        "id": "Pertanyaan ini tentang orang bernama {name}. Panggil find_user dengan query \"{name}\" sekarang, lalu jawab hanya dari hasilnya (tidak ditemukan, atau tanyakan yang mana).",
        "en": "This question is about a person called {name}. Call find_user with query \"{name}\" now, then answer only from its result (not found, or ask which one).",
    },
    "chart_data": {"id": "Data grafik", "en": "Chart data"},
    "chart_more": {"id": "…dan {n} lagi (file CSV atau Excel berisi semuanya).", "en": "…and {n} more (a CSV or Excel export has them all)."},
    "chart_cols_users_by_level": {"id": "| Level | Pengguna |", "en": "| Level | Users |"},
    "chart_cols_top_users": {"id": "| No | Nama | Risk score | Level |", "en": "| No | Name | Risk score | Level |"},
    "chart_cols_phishing_tests": {"id": "| Tes | Tanggal | Phish-prone % |", "en": "| Test | Date | Phish-prone % |"},
    "chart_cols_groups": {"id": "| Grup | Risk score | Level | Pengguna aktif |", "en": "| Group | Risk score | Level | Active users |"},
    "chart_cols_training_completion": {"id": "| Campaign | Mulai | Penyelesaian |", "en": "| Campaign | Start | Completion |"},
    "chart_cols_modules": {"id": "| Modul | Terdaftar | Lulus | Sedang berjalan | Belum mulai | Past Due | % selesai |",
                           "en": "| Module | Enrolled | Passed | In progress | Not started | Past Due | % complete |"},
    "chart_cols_reported_emails": {"id": "| Bulan | Email dilaporkan |", "en": "| Month | Emails reported |"},
    "chart_cols_trend": {"id": "| Titik | Tanggal | Risk score |", "en": "| Point | Date | Risk score |"},
    "chart_point_first": {"id": "Awal", "en": "First"},
    "chart_point_lowest": {"id": "Terendah", "en": "Lowest"},
    "chart_point_highest": {"id": "Tertinggi", "en": "Highest"},
    "chart_point_last": {"id": "Terakhir", "en": "Latest"},
    "chart_categories": {"id": "Per kategori: {items}. Masih terbuka: {open}.", "en": "By category: {items}. Still open: {open}."},
    "table_phishing_by_group": {
        "id": "| Grup | Terkirim | Gagal | Klik | Isi data | Buka lampiran | Melapor | % gagal | % melapor |",
        "en": "| Group | Delivered | Failed | Clicked | Entered data | Opened attachment | Reported | % failed | % reported |",
    },
    "table_find_group": {"id": "| No | Grup | Anggota | Risk score | Level | Tipe |", "en": "| No | Group | Members | Risk score | Level | Type |"},
    "table_find_campaign": {"id": "| No | Kampanye | Status | Terakhir jalan | Tes | Phish-prone % terakhir |",
                            "en": "| No | Campaign | Status | Last run | Tests | Last phish-prone % |"},
    "table_find_campaign_training": {"id": "| No | Kampanye | Status | Mulai | Selesai | % selesai |",
                                     "en": "| No | Campaign | Status | Start | End | % complete |"},
    "table_list_dimension_values": {"id": "| No | Nilai | Pengguna |", "en": "| No | Value | Users |"},
    "table_phishing_by_attribute": {"id": "| Nilai | Orang | Email terkirim | Phish-prone % | Email gagal % | Dilaporkan % |",
                                    "en": "| Value | People | Emails delivered | Phish-prone % | Emails failed % | Reported % |"},
    "table_training_by_attribute": {"id": "| Nilai | Orang | Selesai | Sedang berjalan | Belum mulai | Past Due | % selesai |",
                                    "en": "| Value | People | Completed | In progress | Not started | Past Due | % complete |"},
    "table_manager_report": {"id": "| Manager | Tim | Orang dengan Past Due | Modul Past Due | Orang gagal phishing | Email gagal |",
                             "en": "| Manager | Team | People with Past Due | Past Due modules | People who failed phishing | Failed emails |"},
    "table_manager_report_team": {"id": "| No | Nama | Email | Jabatan | Modul Past Due | Email phishing gagal |",
                                  "en": "| No | Name | Email | Job title | Past Due modules | Failed phishing emails |"},
    "table_group_report": {"id": "| No | Anggota paling berisiko | Jabatan | Risk score | Level |",
                           "en": "| No | Riskiest members | Job title | Risk score | Level |"},
    "table_organisation_summary": {"id": "| Grup | Orang | Risk score | Level | Phish-prone % | Dilaporkan % | % training selesai | Past Due |",
                                   "en": "| Group | People | Risk score | Level | Phish-prone % | Reported % | % training complete | Past Due |"},
    "field_department": {"id": "Departemen", "en": "Department"},
    "field_division": {"id": "Divisi", "en": "Division"},
    "field_location": {"id": "Lokasi", "en": "Location"},
    "field_manager_name": {"id": "Manager", "en": "Manager"},
    "field_job_title": {"id": "Jabatan", "en": "Job title"},
    "field_organization": {"id": "Organisasi", "en": "Organisation"},
    "field_custom_field_1": {"id": "Custom field 1", "en": "Custom field 1"},
    "field_custom_field_2": {"id": "Custom field 2", "en": "Custom field 2"},
    "field_custom_field_3": {"id": "Custom field 3", "en": "Custom field 3"},
    "field_custom_field_4": {"id": "Custom field 4", "en": "Custom field 4"},
    "attribute_empty_groups": {"id": "{field} belum diisi untuk pengguna di KnowBe4, jadi ini hasil per grup KnowBe4.",
                               "en": "{field} is not filled in for users in KnowBe4, so these are the results per KnowBe4 group."},
    "table_phishing_trend": {"id": "| Periode | Tes | Email terkirim | Phish-prone % | Dilaporkan % |",
                             "en": "| Period | Tests | Emails delivered | Phish-prone % | Reported % |"},
    "table_phishing_by_template": {"id": "| No | Template | Jenis | Kesulitan | Terkirim | Phish-prone % | Dilaporkan % |",
                                   "en": "| No | Template | Type | Difficulty | Sent | Phish-prone % | Reported % |"},
    "table_reporting_behaviour": {"id": "| No | Belum pernah melapor | Email diterima | Email gagal |",
                                  "en": "| No | Never reported | Emails received | Emails failed |"},
    "table_phishing_click_details": {"id": "| Jenis | Nilai | Kegagalan | % |", "en": "| Kind | Value | Failures | % |"},
    "table_executive_report": {"id": "| Grup paling berisiko | Orang | Risk score | Level | Phish-prone % | Dilaporkan % | % training selesai | Past Due |",
                               "en": "| Riskiest groups | People | Risk score | Level | Phish-prone % | Reported % | % training complete | Past Due |"},
    "table_policy_acknowledgement": {"id": "| Kebijakan | Terdaftar | Sudah disetujui | Belum disetujui | % disetujui |",
                                     "en": "| Policy | Enrolled | Acknowledged | Not acknowledged | % acknowledged |"},
    "small_sample_note": {"id": "* kurang dari 5 orang: persentasenya mudah berubah.",
                          "en": "* fewer than 5 people: the percentages swing easily."},
    "table_campaign_people": {"id": "| No | Nama | Email | Grup | Status | Modul |", "en": "| No | Name | Email | Groups | Status | Modules |"},
    "table_group_members": {"id": "| No | Nama | Email | Risk score | Level | Phish-prone % | Training Past Due |",
                            "en": "| No | Name | Email | Risk score | Level | Phish-prone % | Past Due training |"},
    "table_person_training": {"id": "| Campaign | Modul | Status | Didaftarkan | Selesai | Menit |",
                              "en": "| Campaign | Module | Status | Enrolled | Completed | Minutes |"},
    "table_coverage_gaps": {"id": "| No | Nama | Email | Bergabung |", "en": "| No | Name | Email | Joined |"},
    "coverage_neither_heading": {"id": "Belum pernah dites phishing maupun ikut training:", "en": "Never phished and never trained:"},
    "table_compare": {"id": "| | {a} | {b} |", "en": "| | {a} | {b} |"},
    "compare_rows_phishing": {"id": "Tes|Email terkirim|Phish-prone %|Melapor|% melapor", "en": "Tests|Emails delivered|Phish-prone %|Reported|% reported"},
    "compare_rows_training": {"id": "Enrolmen|Selesai|Past Due|% selesai|% Past Due", "en": "Enrolments|Completed|Past Due|% completed|% Past Due"},
    "breakdown_more": {"id": "…dan {n} lagi.", "en": "…and {n} more."},
    "phishing_group_line": {
        "id": "Tes phishing {what}: {delivered} email terkirim ke orang di {groups} grup; {failed} {unit} gagal ({fpct}) dan {reported} {unit} melapor ({rpct}).",
        "en": "Phishing test {what}: {delivered} emails delivered to people in {groups} groups; {failed} {unit} failed ({fpct}) and {reported} {unit} reported it ({rpct}).",
    },
    "compare_line": {
        "id": "{label}: {a} pada {pa} dibanding {b} pada {pb} ({change}).",
        "en": "{label}: {a} in {pa} against {b} in {pb} ({change}).",
    },
    "compare_label_phishing": {"id": "Phish-prone %", "en": "Phish-prone %"},
    "compare_label_training": {"id": "Penyelesaian training", "en": "Training completion"},
    "compare_better": {"id": "{points} poin, lebih baik", "en": "{points} points, better"},
    "compare_worse": {"id": "{points} poin, lebih buruk", "en": "{points} points, worse"},
    "compare_same": {"id": "tidak berubah", "en": "no change"},
    "compare_missing": {"id": "salah satu periode tidak punya data", "en": "one period has no data"},
    "phishing_unit_people": {"id": "orang", "en": "people"},
    "phishing_unit_emails": {"id": "email", "en": "emails"},
    "phishing_group_standouts": {
        "id": "% gagal tertinggi: {top} ({top_pct}%); % melapor tertinggi: {rep} ({rep_pct}%). Email terbanyak: {big} ({big_n}).",
        "en": "Highest % failed: {top} ({top_pct}%); highest % reported: {rep} ({rep_pct}%). Most emails: {big} ({big_n}).",
    },
    "trend_standouts": {
        "id": "Phish-prone % tertinggi: {top} ({top_pct}%); terendah: {low} ({low_pct}%).",
        "en": "Highest phish-prone %: {top} ({top_pct}%); lowest: {low} ({low_pct}%).",
    },
    "trend_line": {
        "id": "Phish-prone {how} dari {a} ({pa}) menjadi {b} ({pb}).",
        "en": "Phish-prone {how} from {a} ({pa}) to {b} ({pb}).",
    },
    "trend_up": {"id": "naik", "en": "rose"},
    "trend_down": {"id": "turun", "en": "fell"},
    "trend_flat": {"id": "tetap", "en": "stayed the same"},
    "group_training_line": {
        "id": "{name} (mulai {date}, {status}): {total} {unit} di {groups} grup; {completed} selesai ({percent}%), {in_progress} sedang berjalan, {not_started} belum mulai, {past_due} Past Due ({percent_past_due}%).",
        "en": "{name} (started {date}, {status}): {total} {unit} in {groups} groups; {completed} completed ({percent}%), {in_progress} in progress, {not_started} not started, {past_due} Past Due ({percent_past_due}%).",
    },
    "group_training_header": {
        "id": "| Grup | {unit} | Selesai | Sedang berjalan | Belum mulai | Past Due | % selesai |",
        "en": "| Group | {unit} | Completed | In progress | Not started | Past Due | % complete |",
    },
    "group_training_unit_user": {"id": "orang", "en": "people"},
    "group_training_unit_enrolment": {"id": "enrolmen", "en": "enrolments"},
    "group_training_total": {"id": "Total", "en": "Total"},
    "group_training_standouts": {
        "id": "Penyelesaian tertinggi: {top} ({top_pct}%); terendah: {low} ({low_pct}%). Past Due terbanyak: {most} ({most_n} orang). Grup terbesar: {big} ({big_n} orang).",
        "en": "Highest completion: {top} ({top_pct}%); lowest: {low} ({low_pct}%). Most Past Due: {most} ({most_n} people). Largest group: {big} ({big_n} people).",
    },
    "group_training_overlap": {
        "id": "Total {per_campaign} dihitung per campaign, seperti di KnowBe4: {count} orang terdaftar di lebih dari satu campaign, jadi ada {different} orang berbeda.",
        "en": "The total of {per_campaign} counts each campaign, as KnowBe4 does: {count} person(s) are in more than one of these campaigns, so there are {different} different people.",
    },
    "group_training_rule": {
        "id": "Tiap orang dihitung sekali per grup menurut modul yang paling belum selesai (satu modul Past Due = Past Due).",
        "en": "Each person counts once per group, by their least finished module (one Past Due module means Past Due).",
    },
    "group_training_archived": {
        "id": "{count} orang yang sudah diarsipkan di KnowBe4 tidak dihitung; minta \"termasuk yang diarsipkan\" untuk ikut menghitungnya.",
        "en": "{count} people archived in KnowBe4 are not counted; ask to \"include archived\" to count them too.",
    },
    "group_training_not_targeted": {
        "id": "Grup ini tidak menjadi target campaign tersebut: {names}.",
        "en": "These groups were not targeted by these campaigns: {names}.",
    },
    "group_training_unknown": {
        "id": "Grup ini tidak ditemukan di KnowBe4: {names}.",
        "en": "These groups were not found in KnowBe4: {names}.",
    },
    "campaign_choices": {
        "id": "Ada beberapa training campaign yang cocok. Yang mana?",
        "en": "Several training campaigns match. Which one?",
    },
    "campaign_choices_hint": {
        "id": "Balas dengan nomornya atau sebut nama campaign-nya.",
        "en": "Reply with its number or name the campaign.",
    },
    "modstore_media_scope": {
        "id": "Daftar ModStore ini berisi video dan konten coaching. Modul pelatihan (course) ModStore tidak tersedia lewat API KnowBe4; lihat di Training → ModStore di console.",
        "en": "This ModStore list covers videos and coaching content. ModStore training courses are not available through KnowBe4's API; browse them in Training → ModStore in the console.",
    },
    "modstore_scope": {
        "id": "API KnowBe4 hanya menampilkan konten yang sudah ditambahkan ke akun ini, bukan seluruh katalog ModStore. Untuk melihat semua konten yang bisa ditambahkan, buka Training → ModStore di console.",
        "en": "KnowBe4's API only shows the content already added to this account, not the whole ModStore catalogue. To browse everything you can add, open Training → ModStore in the console.",
    },
    "call_topic": {
        "id": "Pertanyaan ini dijawab oleh {tool}. Panggil {tool} sekarang, lalu jawab hanya dari hasilnya.",
        "en": "This question is answered by {tool}. Call {tool} now, then answer only from its result.",
    },
    "call_period": {
        "id": "Pertanyaan ini menyebut periode lain. Panggil {tool} sekarang untuk periode itu, lalu jawab hanya dari hasilnya.",
        "en": "This question names another period. Call {tool} now for that period, then answer only from its result.",
    },
    "call_again": {
        "id": "Alasannya harus dari data. Panggil {tool} sekarang, lalu jelaskan hanya dari hasilnya; jangan menebak penyebab yang tidak ada di data.",
        "en": "The reason must come from the data. Call {tool} now, then explain only from its result; do not guess causes the data does not show.",
    },
    "call_user_summary": {
        "id": "Panggil user_risk_summary dengan user_id={id} sekarang, lalu jawab dari hasilnya.",
        "en": "Call user_risk_summary with user_id={id} now, then answer from its result.",
    },
    "users_page_heading": {
        "id": "Pengguna {first}–{last} dari {total}, {order}.",
        "en": "Users {first}–{last} of {total}, {order}.",
    },
    "order_risk": {
        "id": "diurutkan dari risiko tertinggi",
        "en": "highest risk first",
    },
    "order_name": {
        "id": "diurutkan berdasarkan nama",
        "en": "sorted by name",
    },
    "users_table_header": {
        "id": "| No | Nama | Risk score | Level | Phish-prone % |",
        "en": "| No | Name | Risk score | Level | Phish-prone % |",
    },
    "users_page_more": {
        "id": "Ketik **lanjut** untuk 20 pengguna berikutnya.",
        "en": "Type **next** for the next 20 users.",
    },
    "sources_heading": {
        "id": "Sumber",
        "en": "Sources",
    },
    "pdf_pages": {
        "id": "hlm. PDF {pages}",
        "en": "PDF page {pages}",
    },
    "download_csv": {
        "id": "⬇ Unduh CSV: {file} ({rows} baris)",
        "en": "⬇ Download CSV: {file} ({rows} rows)",
    },
    "download_xlsx": {
        "id": "⬇ Unduh Excel: {file} ({rows} baris)",
        "en": "⬇ Download Excel: {file} ({rows} rows)",
    },
    "call_chart": {
        "id": "Grafik belum dibuat. Panggil make_chart sekarang dengan chart yang sesuai, lalu jelaskan hasilnya.",
        "en": "No chart has been made yet. Call make_chart now with the fitting chart, then explain the result.",
    },
    "chart_person": {
        "id": " Untuk orang yang dibahas sebelumnya gunakan chart=risk_trend dan user_id={id}.",
        "en": " For the person discussed before, use chart=risk_trend and user_id={id}.",
    },
    "call_nist": {
        "id": "Jawaban ini harus bersumber dari dokumen NIST. Panggil search_nist sekarang dengan kata kunci bahasa Inggris, lalu jawab hanya dari kutipan yang ditemukan.",
        "en": "This answer must come from the NIST documents. Call search_nist now with English keywords, then answer only from the passages it returns.",
    },
    "call_export": {
        "id": "File belum dibuat. Panggil export_csv sekarang dengan dataset yang sesuai.",
        "en": "No file has been made yet. Call export_csv now with the fitting dataset.",
    },
    "which_one": {
        "id": "Yang mana yang Anda maksud?",
        "en": "Which one do you mean?",
    },
    "which_person": {
        "id": "**Ada {count} orang dengan nama itu. Yang mana yang Anda maksud?** Ketik nomornya.",
        "en": "**{count} people have that name. Which one do you mean?** Type their number.",
    },
    "answer_in_language": {
        "id": "Jawab dalam Bahasa Indonesia.",
        "en": "Answer in English.",
    },
    # the first line of a risk score answer, built from the data
    "risk_line": {
        "id": "Risk score {subject} sekarang {score} ({level}); {then}.",
        "en": "{subject} risk score is {score} ({level}) now; {then}.",
    },
    "risk_subject_org": {
        "id": "organisasi",
        "en": "The organisation's",
    },
    "risk_subject_person": {
        "id": "{name}",
        "en": "{name}'s",
    },
    "risk_then": {
        "id": "{days} hari lalu {score} (perubahan {change})",
        "en": "{days} days ago it was {score} (change {change})",
    },
    "risk_then_missing": {
        "id": "tidak ada data dari {days} hari lalu",
        "en": "no data from {days} days ago",
    },
    "risk_period": {
        "id": "periode {period}: dari {score} pada {date} (perubahan {change})",
        "en": "over {period}: from {score} on {date} (change {change})",
    },
    "period_data_start": {
        "id": "awal data",
        "en": "the start of the data",
    },
    "period_today": {
        "id": "sekarang",
        "en": "today",
    },
    "risk_period_missing": {
        "id": "tidak ada data pada periode {period}",
        "en": "no data from {period}",
    },
    # capability lines for product apis, shown only when that product's key is configured
    "capability_ksat": {
        "id": "- **Benchmark dan simulasi lain:** phish-prone % dibanding benchmark resmi KnowBe4 per industri dan ukuran perusahaan, tes USB, tes QR fisik, semua jenis kampanye (termasuk callback dan vishing), log perubahan admin, pustaka template KnowBe4 (email phishing, landing page, email notifikasi, skrip callback), peran admin, pengaturan Second Chance, dan jadwal kampanye.",
        "en": "- **Benchmarks and other simulations:** phish-prone % against KnowBe4's official benchmark per industry and company size, USB drive tests, physical QR tests, every campaign type (including callback and vishing), the admin change log, KnowBe4's template library (phishing emails, landing pages, notification emails, callback scripts), admin roles, Second Chance settings and how campaigns are scheduled.",
    },
    "capability_phisher": {
        "id": "- **Email yang dilaporkan (PhishER):** berapa email mencurigakan yang dilaporkan karyawan, mana yang ancaman, spam atau bersih, mana yang belum ditangani, dan aturan PhishER.",
        "en": "- **Reported emails (PhishER):** how many suspicious emails employees reported, which were threats, spam or clean, which are still open, and the PhishER rules.",
    },
    "capability_piq": {
        "id": "- **Password (PasswordIQ):** password lemah, dipakai bersama, bocor atau tidak pernah kedaluwarsa dari pemindaian Active Directory.",
        "en": "- **Passwords (PasswordIQ):** weak, shared, breached or never-expiring passwords from the Active Directory scan.",
    },
    "capability_coach": {
        "id": "- **Real-Time Coaching dan ModStore:** apakah sudah disiapkan, kampanye dan aturan deteksi, berapa coaching yang dikirim, siapa yang paling sering memicunya, dan katalog video serta konten coaching ModStore (mana yang sudah ada di akun).",
        "en": "- **Real-Time Coaching and ModStore:** whether it is set up, campaigns and detection rules, how much coaching went out, who triggered it most, and ModStore's catalogue of videos and coaching content (which ones the account already has).",
    },
    "capability_events": {
        "id": "- **Event dari tool keamanan lain** (User Event API), dan produk KnowBe4 mana yang sedang dipakai.",
        "en": "- **Events from other security tools** (User Event API), and which KnowBe4 products are in use.",
    },
    # only what the bot really does; keep in step with the tools when they change
    "capabilities": {
        "id": (
            "**Saya membaca data KnowBe4 organisasi Anda dan memberi panduan security awareness.**\n\n"
            "Yang bisa saya lakukan:\n"
            "- **Ringkasan dan laporan:** laporan bulanan untuk manajemen, ringkasan keamanan organisasi dengan semua grup berdampingan, laporan lengkap satu grup, hasil phishing dan training per departemen, lokasi atau jabatan, dan laporan per manager (siapa di timnya yang terlambat training atau gagal phishing).\n"
            "- **Risk score:** risk score organisasi sekarang, levelnya, perubahannya dalam 30 dan 90 hari, dan alasannya; pengguna dan grup paling berisiko, tren risiko sebuah grup, dan riwayat risk score seseorang.\n"
            "- **Phishing:** hasil tiap tes, siapa yang klik dan siapa yang melaporkan, hasil per grup, tren phish-prone per bulan, template dan tingkat kesulitan yang paling banyak menipu, kebiasaan melapor (persentase, kecepatan, siapa yang tidak pernah melapor), siapa yang gagal lebih dari sekali, seberapa cepat orang tertipu dan dari perangkat atau browser apa, serta callback phishing (lewat telepon).\n"
            "- **Training:** penyelesaian training campaign, satu campaign per grup (selesai, sedang berjalan, belum mulai, Past Due), siapa saja yang lewat tenggat, siapa yang belum menyetujui sebuah kebijakan, progres per modul, konten training yang dimiliki, riwayat training seseorang, dan siapa yang belum pernah ditraining.\n"
            "- **Orang dan grup:** mencari orang berdasarkan nama, email atau nomor karyawan, mencari grup atau kampanye berdasarkan nama atau bulan, anggota sebuah grup, daftar departemen, jabatan, manager atau lokasi yang ada, siapa yang belum pernah login ke KnowBe4, karyawan baru, serta tingkat langganan, tanggal berakhir dan jumlah kursi lisensi.\n"
            "- **Istilah:** arti risk score dan levelnya, phish-prone %, report rate, jenis kegagalan, dan status training.\n"
            "{products}"
            "- **Periode dan perbandingan:** sebutkan periode seperti \"dari 2026\" atau \"3 bulan terakhir\" (tanpa periode, saya memakai 12 bulan terakhir), atau bandingkan dua periode, misalnya kuartal ini dengan kuartal lalu.\n"
            "- **Grafik dan file:** grafik muncul sendiri bila membantu, dengan angkanya juga sebagai teks. File CSV atau Excel saya buat bila Anda memintanya, termasuk daftar per orang untuk sebuah campaign.\n"
            "- **Data terbaru:** data KnowBe4 disimpan 10 menit. Tulis \"ambil data terbaru\" atau \"refresh\" untuk mengambilnya langsung dari KnowBe4.\n"
            "- **Panduan NIST:** cara menjalankan, mengukur dan meningkatkan program awareness dan simulasi phishing, dengan sumber dari dokumen NIST.\n\n"
            "Yang tidak bisa saya lakukan: mengubah atau menghapus data (saya hanya membaca), memprediksi nilai di masa depan, "
            "dan menjawab pertanyaan di luar KnowBe4 dan security awareness.\n\n"
            "Contoh pertanyaan:\n"
            "- Ringkasan keamanan perusahaan kami\n"
            "- Berapa risk score sekarang, dan kenapa?\n"
            "- Tren phish-prone 12 bulan terakhir\n"
            "- Per manager, siapa yang timnya telat training?\n"
            "- Template phishing mana yang paling banyak menipu?\n"
            "- Bagaimana cara mengukur efektivitas training security awareness?"
        ),
        "en": (
            "**I read your organisation's KnowBe4 data and give security awareness guidance.**\n\n"
            "What I can do:\n"
            "- **Summaries and reports:** a monthly report for management, an organisation security summary with every group side by side, a full report on one group, phishing and training results per department, location or job title, and a report per manager (who in their team is late with training or failed phishing).\n"
            "- **Risk score:** the organisation's current risk score, its level, how it changed over 30 and 90 days, and why; the riskiest users and groups, a group's risk trend, and a person's risk score history.\n"
            "- **Phishing:** each test's results, who clicked and who reported, results per group, the phish-prone trend per month, the templates and difficulty levels that fooled most people, reporting habits (rate, speed, who never reports), who failed more than once, how fast people fell for it and on which device or browser, and callback (phone) phishing.\n"
            "- **Training:** training campaign completion, one campaign per group (completed, in progress, not started, Past Due), who is overdue, who has not acknowledged a policy, progress per module, the training content you have, a person's training history, and who has never been trained.\n"
            "- **People and groups:** finding a person by name, email or employee number, finding a group or campaign by name or month, a group's members, which departments, job titles, managers or locations exist, who has never signed in to KnowBe4, new joiners, and the subscription level, end date and licensed seats.\n"
            "- **Terms:** what risk score and its levels, phish-prone %, report rate, failure types and training statuses mean.\n"
            "{products}"
            "- **Periods and comparisons:** name a period such as \"since 2026\" or \"the last 3 months\" (without one, I use the past 12 months), or compare two periods, such as this quarter with last quarter.\n"
            "- **Charts and files:** charts appear on their own when they help, with their numbers as text too. I make a CSV or Excel file when you ask for one, including a per-person list for a campaign.\n"
            "- **Fresh data:** KnowBe4 data is kept for 10 minutes. Say \"fetch fresh data\" or \"refresh\" to get it straight from KnowBe4.\n"
            "- **NIST guidance:** how to run, measure and improve awareness programmes and phishing simulations, with sources from NIST documents.\n\n"
            "What I can't do: change or delete data (I only read it), predict future values, "
            "or answer questions outside KnowBe4 and security awareness.\n\n"
            "Example questions:\n"
            "- Give me a security summary of our organisation\n"
            "- What is the risk score now, and why?\n"
            "- Phish-prone trend over the last 12 months\n"
            "- Per manager, whose team is behind on training?\n"
            "- Which phishing templates fooled the most people?\n"
            "- How can we measure how effective security awareness training is?"
        ),
    },
    "mcp_transport": {
        "id": "Layanan data KnowBe4 (server MCP) tidak dapat dihubungi. Coba lagi sebentar lagi. Admin: pastikan run_mcp.py berjalan.",
        "en": "The KnowBe4 data service (MCP server) cannot be reached. Try again in a moment. Admins: check that run_mcp.py is running.",
    },
    "pipeline_error": {
        "id": "Terjadi kesalahan saat memproses pertanyaan ini. Coba lagi; jika terus terjadi, admin dapat melihat log server.",
        "en": "Something went wrong while handling this question. Try again; if it keeps happening, admins can check the server log.",
    },
}


def msg(key: str, language: str = DEFAULT_LANGUAGE, **params: Any) -> str:
    texts = MESSAGES[key]
    return texts.get(language, texts[DEFAULT_LANGUAGE]).format(**params)
