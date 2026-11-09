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
    "answer_in_language": {
        "id": "Jawab dalam Bahasa Indonesia.",
        "en": "Answer in English.",
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
