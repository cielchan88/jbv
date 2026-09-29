# Masukan revisi naskah utama — DIENDAPKAN

Status: **dicatat, belum dikerjakan.** Masih ada masukan lanjutan. Jangan mulai
menulis ulang atau menjalankan komputasi sebelum daftar ini dinyatakan lengkap.

Naskah yang dimaksud: `FX_15seri.docx`, dibangun dari `build.js` pada commit
`acc0b05`.

---

## Keputusan yang sudah diambil

| No | Masukan | Keputusan |
|---|---|---|
| 1 | Judul lebih menarik dan lebih ML, begitu pula subjudul | **Belum final.** Minta alternatif lain; lihat daftar opsi di bawah |
| 2 | Kurangi em dash, titik dua, titik koma | Kerjakan saat menulis ulang. Hitungan awal: 22 em dash, 20 "-" sebagai dash, 101 titik dua, 62 titik koma |
| 3 | Tanda supply/demand terbalik | **Benar terbalik.** Data: Ekspor rata-rata −79, Impor +270. Negatif = supply, positif = demand |
| 4 | Paragraf sel PMA tidak jelas | Tulis ulang supaya **penggabungannya** yang tersurat: tiga sel PMA digabung ke sel korporasi lain dengan tujuan yang sama, 18 → 15 sel |
| 5 | Ganti nama leaf | Pakai peta di bawah. "C,5" dibaca C.5 |
| 6 | Paragraf deep learning | Ringkas jadi dua kalimat, pertahankan bahwa naskah tidak mengklaim DL lebih buruk |
| 7 | Tonjolkan metodologi ML | Pipeline ML jadi inti Metodologi; tujuh metode lain dipadatkan jadi satu subbab benchmark |
| 8 | Jendela rolling kelipatan 5 | **Komputasi ulang** dengan **5, 10, 15, 20, 25, 30, 60, 120** |
| 9 | Elaborasi mRMR | Tambah rumus, algoritma greedy, saringan 3k, alasan Spearman, parameter β, contoh lag berturut-turut |
| 10 | Elaborasi Wilcoxon | Tambah yang diuji, alasan bukan uji-t, satuan pasangan (n = 450 / 1.350), perlakuan selisih nol, dua sisi, Holm/BH, keterbatasan ketergantungan antar-origin |
| 11 | Kenapa hanya enam nilai k | **Tambah lengan 30, 35, 40.** Daftar lama `[6, 8, 12, 16, 20, 25]` di `rerun_sisa.py` tidak punya alasan tercatat dan tidak menguji di atas 25 |

### Peta nama leaf (no. 5)

| Lama | Baru | Lama | Baru | Lama | Baru |
|---|---|---|---|---|---|
| A.2.a | A.1 | B.a | B.1 | C.a | C.1 |
| A.2.b | A.2 | B.b | B.2 | C.b | C.2 |
| A.2.c | A.3 | B.c | B.3 | C.c | C.3 |
| A.2.d | A.4 | B.d | B.4 | C.d | C.4 |
| A.2.e | A.5 | | | C.e | C.5 |
| A.2.f | A.6 | | | | |

Catatan:
- **Bentrok nama.** Kode lama A.1.a/b/c adalah sel PMA yang digabung. Setelah
  diganti, "A.1" berarti sel lain. Sel lama disebut dengan deskripsinya, bukan kodenya.
- **Beeswarm Lampiran B** mencetak kode lama di judul gambarnya ("A.2.a"), jadi
  15 gambar itu harus dibuat ulang. Ini terjadi juga karena komputasi ulang no. 8.
- Naskah pendamping (18 sel) tetap memakai kode lama.
- Kode internal di data dan hasil **tidak** diubah. Penggantian dilakukan saat
  menampilkan, sama seperti `NAMA_METODE` di naskah pendamping.

---

## Opsi judul (no. 1)

Opsi putaran pertama (belum disetujui):
- a. *Does Machine Learning Earn Its Complexity?* / Forecasting fifteen foreign-exchange flow series one day ahead
- b. *Plumbing Before Prediction* / How a feature-handling artefact disguised itself as a market-data failure in machine-learning forecasts of foreign-exchange flows
- c. *Tree Ensembles and the Limits of Feature Engineering* / Evidence from daily foreign-exchange flows by counterparty and purpose

Opsi putaran kedua:
- d. *Forecasting the Flow, Not the Rate* / Machine learning for daily foreign-exchange supply and demand by counterparty and purpose
- e. *Who Buys, Who Sells, and Can a Machine Tell?* / One-day-ahead machine-learning forecasts of disaggregated foreign-exchange flows
- f. *Beyond the Aggregate* / Machine-learning forecasts of foreign-exchange supply and demand across fifteen counterparty and purpose cells
- g. *Fifteen Flows, Ten Models, One Artefact* / What machine learning adds to one-day-ahead foreign-exchange flow forecasting
- h. *The Price of Complexity* / Tree ensembles, feature selection and the limits of machine learning for daily foreign-exchange flows

---

## Prasyarat SEBELUM komputasi ulang (no. 8 dan 11)

Ditemukan saat mencatat, dan wajib ditangani lebih dulu.

1. **Sidik jari konfigurasi TIDAK memuat jendela rolling.** `_sidik_konfigurasi()`
   di `h1_common.py` hanya mencatat `lag_target`, `lag_pasar`, `rata_pasar`,
   `panel` dan `nval`. Menjalankan jendela baru ke `hasil_nval60` tidak akan
   dihentikan. Lebih buruk lagi, `sudah()` melewati sel yang sudah tercatat,
   sehingga hasil jendela lama dan baru **tercampur tanpa pesan**. Perbaikan:
   masukkan semua jendela ke sidik jari, dan pakai folder hasil baru
   (misalnya `hasil_w5`).
2. **Riwayat prediksi ikut membesar, dan itu sudah ditangani otomatis.**
   `MIN_HISTORY_FOR_RECURSIVE_PREDICT = jendela_maks × 3`, jadi 270 → 360 baris.
   Ketiga model pohon membacanya dari konstanta ini, bukan dari angka tetap.
   Tetap diverifikasi sesudah jalan: tidak boleh ada fitur `rolling_*_120` yang
   terisi nol saat prediksi. Itu kelas artefak yang sama dengan temuan data pasar.
3. **`TOP_K_FEATURES` di kode bernilai 12, naskah memakai 25.** Skrip komputasi
   menyetel k secara eksplisit, jadi ini aman, tapi harus dicek ulang.
4. **`slot_pasar.json` akan basi.** Isinya bergantung pada kolam fitur. Hitung
   ulang dengan `cek_slot_pasar.py`, lalu commit versi barunya.
5. **SHAP dan 15 beeswarm dihitung ulang di VPS** (`shap_baru.py`), sekaligus
   dengan nama leaf baru.
6. **Ablasi h=60 (`ablasi_h60.json`) memakai kolam lama.** Perbandingan
   lintas-horizon di 5.2 akan membandingkan dua kolam yang berbeda. Nyatakan
   di naskah, atau sebutkan sebagai keterbatasan.

Ukuran kolam yang diharapkan: statistik rolling naik dari 5 × 4 = 20 menjadi
8 × 4 = 32 fitur, jadi kolam internal ≈ 104 → 116 dan total ≈ 224 → 236.
Verifikasi dari keluaran, jangan dari hitungan ini.

---

## Pertanyaan terbuka (belum diputuskan)

- **Rata-rata bergerak data pasar** sekarang 7 hari kerja. Ikut diganti ke kelipatan 5?
- **Jendela lain yang juga bukan kelipatan 5** ada di `feature_config.py`:
  volatilitas `[7, 14, 30]`, RSI `[14]`, Bollinger `[20]`, extreme/change `[14]`.
  Masukan no. 8 menyebut "rolling statistics"; apakah ini ikut diganti?
- **Lengan ablasi 30/35/40** memperbesar komputasi `rerun_sisa.py` sekitar
  setengah kali lipat. Perkiraan waktunya dihitung sebelum dijalankan.
