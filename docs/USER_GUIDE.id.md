# Panduan pengguna: chat KnowBe4

*English: [USER_GUIDE.md](USER_GUIDE.md)*

Chat KnowBe4 menjawab pertanyaan tentang data KnowBe4 organisasi Anda dengan bahasa sehari-hari: risk score, tes phishing, training, orang dan grup. Chat ini juga bisa membuat grafik, file CSV atau Excel, dan memberi panduan security awareness dari dokumen NIST.

Chat ini **hanya membaca** data KnowBe4 dan tidak pernah mengubah apa pun. Jawaban ditulis oleh model AI yang berjalan di server organisasi Anda sendiri. Pertanyaan Anda dan data KnowBe4 tidak dikirim ke layanan AI luar.

## Isi

1. [Membuka chat](#1-membuka-chat)
2. [Mengajukan pertanyaan](#2-mengajukan-pertanyaan)
3. [Apa yang bisa ditanyakan](#3-apa-yang-bisa-ditanyakan)
4. [Periode dan perbandingan](#4-periode-dan-perbandingan)
5. [Pertanyaan lanjutan](#5-pertanyaan-lanjutan)
6. [Grafik dan file](#6-grafik-dan-file)
7. [Membaca jawaban](#7-membaca-jawaban)
8. [Pesan yang mungkin muncul](#8-pesan-yang-mungkin-muncul)
9. [Kebiasaan yang baik](#9-kebiasaan-yang-baik)

## 1. Membuka chat

1. Buka alamat yang diberikan administrator Anda, misalnya `https://kb4-chat.example.internal`. Jika muncul kotak login, masuk dengan akun yang diberikan kepada Anda.
2. Pertama kali, pilih **Bahasa Indonesia** atau **English**. Halaman akan mengingat pilihan Anda. Ganti kapan saja lewat **ID / EN** di kanan atas.
3. Label status di bagian atas menunjukkan apakah layanan berjalan:

| Status | Arti |
|---|---|
| **Online** | Semua berjalan normal. |
| **Terbatas** | Sebagian layanan bermasalah; jawaban bisa gagal. Beri tahu administrator. |
| **Offline** | Halaman tidak dapat menghubungi server. Coba lagi nanti atau beri tahu administrator. |

## 2. Mengajukan pertanyaan

- Ketik pertanyaan lalu tekan **Enter** atau **Kirim**. **Shift + Enter** membuat baris baru.
- Selama bekerja, halaman menunjukkan apa yang sedang dilakukan, misalnya "Mengambil data…" atau "Menyusun jawaban…". Sebagian besar jawaban butuh 10–60 detik.
- Anda bisa mengetik pertanyaan berikutnya selagi satu pertanyaan dijawab. Sampai 10 pertanyaan bisa antre, dan setiap jawaban muncul di bawah pertanyaannya sendiri.
- **Baru** menghapus percakapan dan memulai dari awal. Tombol ini juga menghentikan jawaban yang masih ditulis.
- Tulis dengan wajar. Pertanyaan pendek, santai atau sedikit salah ketik tidak masalah: "risk score skrg?", "siapa yg klik phishing terakhir", "training bulan ini gimana".

Jika organisasi Anda punya lebih dari satu konsol KnowBe4, sebutkan nama konsolnya di pertanyaan, misalnya "risk score *Anak Perusahaan*". Jika tidak, konsol utama yang dipakai.

## 3. Apa yang bisa ditanyakan

Ketik **"apa saja yang bisa kamu lakukan"** kapan saja untuk daftar lengkapnya. Ringkasnya:

| Bidang | Contoh pertanyaan |
|---|---|
| **Ringkasan dan laporan** | "Ringkasan keamanan perusahaan kami" · "Laporan bulanan untuk direksi bulan Oktober" · "Laporan lengkap grup Finance" · "Per manager, siapa yang timnya telat training?" |
| **Risk score** | "Berapa risk score sekarang, dan kenapa?" · "Siapa 10 pengguna paling berisiko?" · "Grup mana yang paling berisiko?" · "Tren risiko grup IT membaik atau memburuk?" |
| **Phishing** | "Bagaimana hasil tes phishing terakhir?" · "Siapa yang klik, dan siapa yang melaporkan?" · "Tren phish-prone 12 bulan terakhir" · "Template phishing mana yang paling banyak menipu?" · "Siapa yang gagal lebih dari sekali?" · "Orang gagal lewat HP atau laptop?" |
| **Training** | "Penyelesaian training campaign terbaru" · "Campaign bulan Oktober per grup" · "Siapa yang lewat tenggat (Past Due)?" · "Modul mana yang paling sedikit diselesaikan?" · "Siapa yang belum pernah ditraining?" |
| **Orang dan grup** | "Cari Budi Contoh" · "Siapa saja anggota grup Finance?" · "Departemen apa saja yang ada?" · "Siapa yang belum pernah login ke KnowBe4?" · "Karyawan baru kuartal ini" |
| **Istilah** | "Phish-prone % itu apa?" · "Past Due artinya apa?" |
| **Lisensi** | "Langganan kita berakhir kapan, dan berapa kursi yang terpakai?" |
| **Panduan NIST** | "Bagaimana cara mengukur efektivitas training security awareness?" · "Seberapa sering sebaiknya simulasi phishing dijalankan?" |

Jika organisasi Anda memakai produk KnowBe4 lain (PhishER, PasswordIQ, Real-Time Coaching), "apa saja yang bisa kamu lakukan" juga menampilkan pertanyaan untuk produk tersebut.

**Yang tidak bisa dilakukan:**
- mengubah atau menghapus apa pun di KnowBe4;
- memprediksi nilai di masa depan;
- menjawab pertanyaan di luar KnowBe4 dan security awareness.

## 4. Periode dan perbandingan

- **Sebutkan periode di pertanyaan:** "bulan Oktober 2026", "3 bulan terakhir", "Q3 2026", "dari Maret", "tahun ini".
- **Tanpa periode, yang dipakai adalah 12 bulan terakhir.** Jawaban menyebutkan periode yang dipakai.
- **Bandingkan dua periode:** "phishing kuartal ini dibanding kuartal lalu", "training 2026 dibanding 2025".
- Beberapa jawaban selalu tentang **hari ini**, misalnya risk score saat ini dan anggota grup. Jika Anda menyebut periode untuk jawaban seperti itu, jawabannya menyebutkan bahwa yang ditampilkan adalah kondisi saat ini.

## 5. Pertanyaan lanjutan

Chat mengingat beberapa pesan terakhir, jadi Anda bisa melanjutkan dengan wajar:

- **Baris berikutnya:** "lanjut" atau "berikutnya" setelah sebuah daftar.
- **Memilih dari daftar:** "2" atau "yang kedua" jika chat menampilkan beberapa orang atau kampanye.
- **Merujuk jawaban sebelumnya:** "kenapa?", "kalau kuartal lalu?" atau "risk score dia?" setelah jawaban tentang satu orang.
- **Nama yang sama:** jika sebuah nama cocok dengan beberapa orang, chat menanyakan dulu orang yang mana.

Jika jawaban melenceng, tekan **Baru** dan tanyakan lagi dengan lebih rinci.

## 6. Grafik dan file

- **Grafik** muncul sendiri bila membantu. Angka grafik selalu ditampilkan juga sebagai tabel di bawahnya. Anda juga bisa memintanya: "grafik risk score setahun ini".
- **File** hanya dibuat jika Anda memintanya: "export yang Past Due ke Excel" atau "CSV campaign Oktober per orang". Tautannya muncul di jawaban.
- **File dan grafik dihapus setelah satu jam.** Segera unduh yang Anda perlukan.
- File bisa berisi nama dan alamat email. Simpan dan bagikan seperti data pribadi lainnya, hanya kepada orang yang berhak melihatnya.

## 7. Membaca jawaban

Sebagian besar jawaban punya bentuk yang sama:

1. **Baris pertama tebal**: jawabannya.
2. **Fakta utama**: angka di baliknya, sering dengan tabel.
3. **Kenapa**: hal dalam data yang menjelaskannya.

Jika jawaban panduan memakai NIST, dokumen sumbernya dicantumkan di bagian akhir.

Data KnowBe4 disimpan 10 menit untuk menghemat permintaan. Untuk mengambilnya langsung dari KnowBe4, tulis **"ambil data terbaru"** atau **"refresh"**.

Jawaban ditulis oleh model AI. Pemeriksaan dalam perangkat lunak membuang angka yang tidak ada di data, tetapi model sesekali masih bisa menulis dengan kurang tepat. **Untuk keputusan atau laporan ke manajemen, cek angka utamanya di konsol KnowBe4.**

## 8. Pesan yang mungkin muncul

| Pesan (ringkas) | Yang perlu dilakukan |
|---|---|
| Batas harian permintaan ke KnowBe4 sudah tercapai | KnowBe4 membatasi jumlah permintaan dalam 24 jam. Coba lagi nanti. Pertanyaan yang diajukan dalam 10 menit terakhir mungkin masih bisa dijawab dari data yang tersimpan. |
| KnowBe4 tidak dapat dihubungi / API key ditolak | Coba lagi beberapa menit lagi. Jika terus terjadi, beri tahu administrator. |
| Tidak ada respons selama … detik | Ajukan pertanyaan yang lebih sempit, misalnya satu grup atau satu bulan. |
| Pertanyaan atau percakapan terlalu panjang | Tekan **Baru**, atau persingkat pertanyaan (maksimal 4.000 karakter). |
| Orang yang mana? | Beberapa orang cocok dengan nama itu. Balas dengan nomornya atau nama lengkapnya. |
| Saya hanya membaca data KnowBe4 | Anda meminta perubahan; lakukan di konsol KnowBe4. |

## 9. Kebiasaan yang baik

- **Spesifiklah jika penting:** sebutkan grup, kampanye, bulan atau orangnya. "Training campaign Oktober untuk grup Finance" menghasilkan jawaban yang lebih baik daripada "training?".
- **Satu pertanyaan sekali kirim** menghasilkan jawaban yang lebih jelas daripada tiga pertanyaan dalam satu pesan.
- **Jangan menempelkan password, API key atau rahasia lain** ke chat.
- **Jawaban berisi data pribadi** rekan kerja. Gunakan hanya untuk pekerjaan security awareness Anda.
