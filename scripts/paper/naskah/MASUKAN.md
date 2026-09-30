# Masukan revisi naskah utama — DIENDAPKAN

Status: **badan naskah, Kesimpulan dan Abstrak sudah ditulis ulang dari hasil
`hasil_w5`** (no. 2-14, 16-18). Yang tersisa: **judul** (no. 1, 15), yang
dibahas sesudah badan naskah disetujui.

Review eksternal (30-09-2026), semua dikerjakan tanpa run ulang:
- Artefak data pasar: 4.5 kini hanya hasil terkoreksi (Tabel 10-11); zero-fill
  pindah ke 5.2 "An Implementation Pitfall" (Tabel 12, Gambar 11-12).
- Ensemble: lima kombinasi berbobot sama, Holm bersama (Tabel 7). Tidak ada
  yang nyata lebih baik dari LightGBM; median 10 metode satu-satunya < 1.
- Blok validasi: 3.3 diperjelas (rolling-origin, expanding window);
  keterbatasan satu rezim di 5.6.
- 5.4 baru: kerangka rezim nilai tukar, tiga proposisi (bukan temuan).
  Sitasi baru: Calvo & Reinhart 2002, Menkhoff 2013, Fratzscher et al. 2019,
  Smith & Wallis 2009, Claeskens et al. 2016.
- Riset lanjutan (6.3): CatBoost, validasi tersebar, SHAP-RFE, bobot
  kombinasi dari blok validasi.

Keputusan sesudah hasil VPS: k tetap **25** (ditetapkan sebelum studi).
Ablasi k dilaporkan sebagai temuan: k 30/35/40 lebih baik per titik dan
lolos Holm atas 8 lengan, tetapi tidak nyata per seri (n = 15), tidak
dimiliki XGBoost, dan kurvanya tidak mulus. Menyetel k di blok validasi
dicatat sebagai riset lanjutan.

Naskah yang dimaksud: `FX_15seri.docx`, dibangun dari `build.js` pada commit
`acc0b05`.

---

## Keputusan yang sudah diambil

| No | Masukan | Keputusan |
|---|---|---|
| 1 | Judul lebih menarik dan lebih ML, begitu pula subjudul | **Belum final.** Minta alternatif lain; lihat daftar opsi di bawah |
| 2 | Kurangi em dash, titik dua, titik koma | Kerjakan saat menulis ulang. Hitungan awal: 22 em dash, 20 "-" sebagai dash, 101 titik dua, 62 titik koma |
| 3 | Tanda supply/demand terbalik | **Benar terbalik.** Data: Ekspor rata-rata −79, Impor +270. Negatif = supply, positif = demand |
| 4 | Paragraf sel PMA tidak jelas | **Diubah (30-09-2026): penjelasan penggabungan dihapus seluruhnya.** Label sel korporasi cukup "Corporate". Sel A.1 di data berlabel PTMN, bukan PMA; istilah "foreign direct investment" di draf sebelumnya keliru. Penyebutan grid 18 sel di 5.2 juga dihapus; 5.2 hanya menyebut ablasi h=60 dijalankan sebelum jendela kelipatan 5 dan dengan hyperparameter tetap |
| 5 | Ganti nama leaf | Pakai peta di bawah. "C,5" dibaca C.5 |
| 6 | Paragraf deep learning | Ringkas jadi dua kalimat, pertahankan bahwa naskah tidak mengklaim DL lebih buruk |
| 7 | Tonjolkan metodologi ML | Pipeline ML jadi inti Metodologi; tujuh metode lain dipadatkan jadi satu subbab benchmark |
| 8 | Jendela rolling kelipatan 5 | **Komputasi ulang** dengan **5, 10, 15, 20, 25, 30, 60, 120** |
| 9 | Elaborasi mRMR | Tambah rumus, algoritma greedy, saringan 3k, alasan Spearman, parameter β, contoh lag berturut-turut |
| 10 | Elaborasi Wilcoxon | Tambah yang diuji, alasan bukan uji-t, satuan pasangan (n = 450 / 1.350), perlakuan selisih nol, dua sisi, Holm/BH, keterbatasan ketergantungan antar-origin |
| 11 | Kenapa hanya enam nilai k | **Tambah lengan 30, 35, 40.** Daftar lama `[6, 8, 12, 16, 20, 25]` di `rerun_sisa.py` tidak punya alasan tercatat dan tidak menguji di atas 25 |
| 12 | Hapus 3.5 Ethical Considerations dan paragraf deep learning | Hapus keduanya. Menggantikan keputusan no. 6 |
| 13 | Elaborasi Holm-Bonferroni | Tambah prosedur langkah-turun, alasan memilih Holm (FWER, tanpa asumsi ketergantungan), keluarga uji yang dikoreksi, dan pembanding BH (FDR) |
| 14 | ML sebagai sudut pandang utama di Bab 4, 5, 6 dan seluruh naskah | Hasil dibuka dari pipeline ML (seleksi fitur, penyetelan, ablasi, SHAP); metode statistik dibaca sebagai garis dasar. Berlaku juga untuk abstrak dan pendahuluan |
| 15 | Judul | Ditunda sampai badan naskah OK |
| 16 | Rata-rata bergerak data pasar kelipatan 5 | **7 → 5.** Lag pasar ikut **1–14 → 1–15** |
| 17 | Jendela lain kelipatan 5, cek seluruh kode | **Dikerjakan.** Peta lengkap di bawah. Semua ikut dikomputasi ulang |
| 18 | Abstrak | Ditulis **terakhir**, sesudah Hasil dan Kesimpulan versi baru jadi, dan disusun dari keduanya dengan urutan: (1) mengapa studi ini penting, (2) bagaimana dilakukan, (3) temuan kunci, (4) implikasi ke depan. Semua angka di abstrak diturunkan dari `tables.json`, bukan ditulis tangan, dan diperiksa `cek_draft.py` |

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

## Peta jendela (no. 8, 16, 17)

Satuan: baris = hari kerja. Sumber tunggal: `utils/feature_config.py`
(blok JENDELA di atas `FEATURE_CONFIG`). Yang dulu tertulis langsung di
`feature_engineering_optimized.py` sekarang dibaca dari konfigurasi.

| Kelompok | Lama | Baru |
|---|---|---|
| Statistik rolling (mean/std/min/max) | 7, 14, 30, 60, 90 | 5, 10, 15, 20, 25, 30, 60, 120 |
| EWM | 7, 30 | 5, 30 |
| Selisih dan persentase perubahan | 1, 7, 30 | 1, 5, 30 |
| Volatilitas | 7, 14, 30 | 5, 15, 30 |
| Rasio volatilitas | 7/30 | 5/30 |
| Rezim volatilitas (median) | vol 14, median 60 | vol 15, median 60 |
| Volatilitas asimetris | 14, 30 | 15, 30 |
| Posisi harga | 30, 60 | tetap |
| RSI | 14 | 15 |
| Bollinger | 20 | tetap |
| MACD (cepat/lambat/sinyal) | 12/26/9 | 10/25/10 |
| Z-score | 14, 30 | 15, 30 |
| Deteksi lonjakan | 14 | 15 |
| Batas perubahan | 14 | 15 |
| Fourier (mingguan/bulanan/kuartalan) | 7/30/90 | 5/20/60 |
| Siklus hari dalam minggu (sin/cos) | 7 | 5 |
| Interaksi | lag_7 × hari, rolling_mean_7 × bulan | lag_5 × hari, rolling_mean_5 × bulan |
| Lag pasar | 1–14 | 1–15 |
| Rata-rata bergerak pasar | 7 | 5 |
| Riwayat prediksi rekursif | 270 | 360 (= 120 × 3) |

Lag target (1–15, 20, 25, 30) tidak diubah: itu lag, bukan jendela, dan
isinya sudah memuat seluruh kelipatan 5 sampai 30.

Kolam: internal **104 → 116**, pasar 8 variabel × (15 lag + 1 rata-rata) =
**128**, total **244** (dulu 224). Terverifikasi dari keluaran pembangun fitur.

### Cacat lama yang ikut ditemukan dan diperbaiki

Keempatnya memengaruhi hasil lama juga, jadi disebut di naskah bila relevan.

1. **Fase Fourier tidak konsisten antara latih dan prediksi.** `time_idx`
   dulu `arange(len(df))`, jadi bergantung pada panjang potongan data;
   prediksi rekursif memakai 270 baris terakhir sehingga fasenya bergeser.
   Sekarang dihitung dari tanggal (hari kerja sejak 2000-01-03).
2. **`days_since_jump` terpotong saat prediksi.** Nilainya bisa melebihi
   riwayat yang tersedia saat prediksi. Sekarang dibatasi `jump_cap` = 120.
3. **Nama fitur rezim volatilitas tertulis langsung** (`volatility_7`,
   `volatility_14`). Mengganti jendela akan menghilangkan fitur itu diam-diam.
   Sekarang diturunkan dari konfigurasi.
4. **Interaksi `rolling_mean_7 × month`** akan hilang diam-diam dengan
   jendela baru. Diganti `rolling_mean_5`.

Sesudah perbaikan: nol selisih fitur antara latih dan prediksi pada 116 fitur
× 15 leaf, dan pemotongan awalan (cache) tetap bit-identik.

### Temuan pemeriksaan ulang sebelum VPS (ikut diperbaiki)

5. **Daftar prioritas volatilitas masih memakai jendela 7/14.** 16 dari 28
   nama di `VOLATILITY_PRIORITY_FEATURES` tidak lagi dibangkitkan. Sekarang
   diturunkan dari konfigurasi, 28 dari 28 ada. Daftar ini hanya aktif bila
   `volatility_quota > 0` (bawaan 0, tanpa pemanggil), jadi hasil naskah tidak
   terpengaruh.
6. **Label SHAP rata-rata pasar tertulis "7d mean"** di `shap_baru.py`, dan
   nama variabelnya ikut membawa "rolling mean 7" (label dobel). Sekarang
   jendelanya dibaca dari nama fitur: "bid usdidr, 5d mean".
7. **24 fitur jatuh ke keluarga SHAP "Other"**: 16 rolling min/max, posisi
   harga, lonjakan, batas perubahan, minggu-dalam-tahun. Sekarang
   dikelompokkan sesuai feature_config.py (min/max, posisi harga, batas
   perubahan: Volatility / range; lonjakan: Extreme value; minggu: Calendar).
   Seluruh 244 fitur punya keluarga, "Other" kosong. Pangsa per keluarga di
   Gambar 7 dan prosa 4.x akan bergeser karena ini, bukan hanya karena jendela.

### Nama leaf tampilan (no. 5) - sudah terpasang di seluruh keluaran

- **Naskah (build.js):** konstruktor `TextRun` membungkus semua teks, jadi
  paragraf, sel tabel, judul, keterangan gambar dan catatan lewat satu pintu.
- **Gambar (figs.py):** Gambar 1, 3, 8 memakai nama baru; `simpan()` berhenti
  kalau ada kode lama di teks gambar mana pun.
- **SHAP (shap_baru.py):** judul 15 beeswarm dan grafik "By series".
  Berhenti di awal kalau ada leaf tanpa nama; `vps.py periksa` mengecek
  peta terhadap leaf panel sebelum apa pun dijalankan.
- **Pemeriksa (cek_draft.py):** Tabel 8 dicocokkan lewat peta balik, dan
  gagal kalau ada kode lama atau salah satu dari 15 nama baru tidak muncul.
- Beeswarm di draf SEKARANG masih berjudul kode lama karena disalin dari
  `hasil_nval60`. Hasil VPS membawa judul baru.

### Catatan terbuka

- **MACD 10/25/10 menyimpang dari standar 12/26/9.** Konsekuensi aturan
  kelipatan 5. Sebut di naskah.
- **`is_weekend` dan `rolling_mean_30_x_is_weekend` konstan** (data hanya hari
  kerja). Sudah ada sejak dulu; penyeleksi membuangnya. Tidak diubah, cukup
  dicatat.
- **`utils/feature_engineering.py` (versi lama) masih memakai jendela lama**,
  tapi tidak ada di jalur model (external_loader hanya mengimpor fungsi
  penggabung seri silang). Dibiarkan.

---

## Prasyarat SEBELUM komputasi ulang (no. 8 dan 11) — SUDAH DITANGANI

Ditemukan saat mencatat. Status penanganan di akhir tiap butir.

1. **Sidik jari konfigurasi TIDAK memuat jendela rolling.** `_sidik_konfigurasi()`
   di `h1_common.py` hanya mencatat `lag_target`, `lag_pasar`, `rata_pasar`,
   `panel` dan `nval`. Menjalankan jendela baru ke `hasil_nval60` tidak akan
   dihentikan. Lebih buruk lagi, `sudah()` melewati sel yang sudah tercatat,
   sehingga hasil jendela lama dan baru **tercampur tanpa pesan**. Perbaikan:
   masukkan semua jendela ke sidik jari, dan pakai folder hasil baru
   (misalnya `hasil_w5`). **Selesai.** Folder lama dibaca dalam mode baca-saja
   (`JBV_BACA_SAJA=1`) supaya draf sekarang tetap bisa disusun.
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
   dengan nama leaf baru. **Selesai:** judul beeswarm memakai `nama_leaf.json`.
6. **Ablasi h=60 (`ablasi_h60.json`) memakai kolam lama.** Perbandingan
   lintas-horizon di 5.2 akan membandingkan dua kolam yang berbeda. Nyatakan
   di naskah, atau sebutkan sebagai keterbatasan.

Pertanyaan terbuka sebelumnya (rata-rata pasar, jendela lain) sudah
dijawab oleh no. 16 dan 17.

---

## Menjalankan di VPS

```bash
cd /opt/jbv && git pull
venv/bin/python scripts/paper/revisi/vps.py periksa
venv/bin/python scripts/paper/revisi/vps.py mulai
venv/bin/python scripts/paper/revisi/vps.py pantau
```

Arsip `jbv_hasil_w5_<tanggal>.tgz` dibuat otomatis di akhir. Sesudah
diunggah, naskah disusun dengan `JBV_NASKAH_HASIL=.../hasil_w5` dan
`JBV_NASKAH_SLOT=.../hasil_slot_w5`.

### Yang harus dikerjakan di teks sesudah hasil masuk

Urutan penulisan: badan naskah (Metodologi, Bab 4-6) -> Kesimpulan -> Abstrak
(no. 18) -> Judul (no. 1, 15).

- Prosa yang masih menulis jendela lama ("seven, fourteen, thirty, sixty and
  ninety days", "seven-day rolling mean") diturunkan dari `T['jendela']` dan
  `T['rata_pasar']`, bukan ditulis ulang tangan.
- Nama leaf lewat `nama_leaf.json` di buat_tables.py, figs.py, build.js.
- Ablasi h=60 (`ablasi_h60.json`) masih kolam lama: sebut sebagai keterbatasan.
