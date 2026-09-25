# Komputasi ulang naskah

Seluruh tabel dan gambar naskah dihasilkan dari satu perintah:

```bash
cd /opt/jbv && tmux new -s naskah
venv/bin/python scripts/paper/revisi/jalankan_semua.py           # panel 18 leaf
venv/bin/python scripts/paper/revisi/jalankan_semua.py gabung    # panel 15 leaf
```

Lepas dengan `Ctrl-b d`, sambung lagi dengan `tmux attach -t naskah`.
Perkiraan 12-15 jam untuk 18 leaf, sekitar seperlima lebih singkat untuk 15.

**Jalankan di VPS, bukan di sesi Claude.** Lingkungan sesi Claude me-restart
kontainernya tiap belasan menit dan membunuh proses lepas, jadi pekerjaan
sepanjang ini tidak pernah bisa selesai di sana.

Cek kemajuan kapan saja dari jendela lain:

```bash
JBV_PANEL=data/processed/sdv-wide-gabung.csv venv/bin/python scripts/paper/revisi/ringkas.py
```

Keluarannya menutup dengan verdikt **SELESAI** atau **BELUM SELESAI**.

---

## Lebih cepat: paralel per leaf

Leaf saling bebas — tidak ada tahap yang memakai hasil leaf lain — jadi 15 leaf
boleh dikerjakan beberapa proses sekaligus. Dan yang mahal justru bagian yang
berjalan **satu utas**: pembangunan bingkai fitur dan seleksi mRMR, 79% waktu
per sel. Pelatihan model yang memakai banyak utas hanya 0,5–1,3 detik. Empat
proses satu-utas karena itu mengalahkan satu proses empat-utas.

```bash
cd /opt/jbv && tmux new -s naskah
P=data/processed/sdv-wide-gabung.csv
for T in rerun_optimal.py rerun_headline.py rerun_ablasi.py rerun_sisa.py; do
  venv/bin/python scripts/paper/revisi/jalankan_paralel.py $T 4 gabung || break
  JBV_PANEL=$P venv/bin/python scripts/paper/revisi/gabung_shard.py --ya || break
done
JBV_PANEL=$P venv/bin/python scripts/paper/revisi/shap_baru.py
JBV_PANEL=$P venv/bin/python scripts/paper/revisi/uji_statistik.py
```

Tiga hal yang membuatnya aman, dan kenapa:

**Berkas keluaran terpisah per shard.** Tiap proses menulis ke
`opt_rolling.shard-2-of-4.csv` dan seterusnya, lalu `gabung_shard.py`
menyatukannya. Ini bukan kehati-hatian berlebih: dua proses yang meng-`append`
ke satu CSV persis yang melahirkan baris ganda 125,9% dan 163,3% di folder
hasil panel 18 seri. `gabung_shard.py` menolak menulis kalau satu kunci sel
muncul dengan isi berbeda — tanda dua shard mengerjakan leaf yang sama.

**Satu utas per proses.** `jalankan_paralel.py` menyetel `OMP_NUM_THREADS=1`
dan `LOKY_MAX_CPU_COUNT=1`. Tanpa itu keempat proses sama-sama meminta seluruh
core dan saling berebut — bisa lebih lambat daripada berurutan.

**Urutan antar tahap tetap wajib.** `rerun_headline`, `rerun_ablasi` dan
`rerun_sisa` membaca setelan terpilih dari `rerun_optimal`. Satukan dulu
sebelum lanjut; loop di atas sudah melakukannya.

`ringkas.py` memperingatkan kalau masih ada berkas shard yang belum disatukan —
ia membaca nama kanonik saja, jadi tanpa peringatan itu layarnya tampak seperti
pekerjaan yang belum jalan.

Untuk menjalankan satu leaf saja: `JBV_LEAF=A.2.d` (menang atas `JBV_SHARD`).

---

## Alurnya, langkah demi langkah

### 1. Siapkan data

Panel 15 atau 18 seri × 5.032 hari kerja, dalam juta USD, plus 8 variabel
pasar pada tanggal yang sama persis: kurs spot bid/ask, forward 1 bulan
bid/ask, yield SUN 10 tahun, indeks dolar, arus saham nonresiden, IHSG.

Panel 15 leaf dibangun `gabung_leaf.py`, yang menjumlahkan tiga leaf PTMN ke
pasangannya di Korporasi Lainnya (A.1.a→A.2.d, A.1.b→A.2.e, A.1.c→A.2.f) lalu
membuang simpul A.1 yang kehilangan seluruh anaknya.

### 2. Potong garis waktu jadi tiga

Untuk **tiap** seri:

```
hari 1 ──────────────── 4.992 │ 4.993─5.002 │ 5.003─5.032
       bahan latihan            10 hari        30 hari
                                VALIDASI        UJI
```

Validasi hanya untuk memilih setelan, uji hanya untuk melaporkan angka.
Keduanya tidak pernah bertukar peran.

### 3. Bangun fitur

Dari riwayat seri itu sendiri: 18 lag (1-15, 20, 25, 30), rata-rata bergerak,
volatilitas, indikator teknikal, efek kalender → **104 kandidat**. Dengan data
pasar, tiap variabel masuk sebagai lag 1 sampai 14 hari plus rata-rata 7 hari
— 8 seri × 15 = 120 tambahan, total **224**.

Semuanya menoleh ke belakang; tidak ada nilai hari berjalan yang masuk. Lag
pasar mulai dari 1, bukan 0: lag 0 berarti memakai angka yang belum ada saat
ramalan dibuat.

> **Kolam 224 hanya berlaku di sebagian tahap.** `fit()` model berbasis fitur
> menyaring seri pasar lewat `cross_series_for_recursive`, dan saklar
> `ENABLE_CROSS_SERIES_FOR_RECURSIVE` bernilai `False` — peramal rekursif
> tidak punya nilai seri lain untuk tanggal masa depan, jadi fitur `ext_*`
> akan dinolkan saat `predict()`. Akibatnya tahap 1, 2, 3 dan 4a berjalan
> pada **104 kandidat**. Yang benar-benar memakai 224 hanya lengan "pasar
> hidup" di tahap 4b — yang memang menambal saringan itu jadi identitas —
> serta `shap_baru.py` dan `cek_slot_pasar.py`, yang memanggil pembangun
> fitur langsung.

### 4. Pilih 25 fitur dengan mRMR

Skor kandidat = korelasi Spearman dengan target **dikurangi** rata-rata
korelasinya dengan fitur yang sudah terpilih, diambil satu per satu sampai k.

mRMR hanya berjalan atas **3k kandidat teratas** menurut korelasi mentah
(`select_top_features_optimized`). Akibatnya variabel pasar bisa menendang
fitur internal keluar dari daftar pendek tanpa pernah terpilih sendiri — jadi
"nol slot pasar" tidak berarti "tanpa pengaruh pasar".

### 5. Cari setelan tiap model — *tahap 1*

Empat kandidat setelan per model, masing-masing diuji di 10 hari validasi,
yang menang disimpan ke `opt_tuned.csv`.

`15 × 3 model × 4 setelan × 10 hari = 1.800 pelatihan`

### 6. Blok uji 30 hari — *tahap 1*

Inti evaluasinya. Untuk tiap seri, metode, dan hari di blok uji: latih ulang
dari nol dengan **semua** data sebelum hari itu, ramal hari itu, bandingkan
aktual, bagi penyebut MASE.

`15 × 10 metode × 30 hari = 4.500 ramalan` → **Tabel 6, Gambar 3-4**

### 7. Desain satu hari — *tahap 2*

Latih seluruh riwayat, ramal hari terakhir. Cara desk sebenarnya bekerja,
tapi satu hari tidak memberi sebaran sampel — deskripsi, bukan bukti.

`15 × 10 = 150 ramalan` → **Tabel 5, Lampiran A1**

---

## Tiga ablasi

Semuanya berprinsip sama: **tahan segalanya, ubah satu hal, bandingkan
berpasangan** pada hari, seri dan model yang identik.

### 8. Ablasi terbalik — *tahap 3*

Mulai dari konfigurasi penuh, copot **satu** komponen, ukur berapa yang
hilang. Dua komponen lain tetap menyala, jadi yang terukur adalah sumbangan
marginalnya di atas yang lain.

| Lengan | Yang dicopot |
|---|---|
| `tanpa_mrmr` | seleksi mRMR → kembali ke korelasi biasa |
| `tanpa_setelan` | setelan terpilih → pakai bawaan library |
| `tanpa_refit` | refit harian → latih sekali di awal blok |

`15 × 3 model × 3 lengan × 30 hari = 4.050` → **Tabel 9, Gambar 9**, refit harian.

Hasil panel 18 leaf: mRMR +2,28% (p=0,637, tidak nyata), refit harian +1,64%
(**p=0,001, nyata**), penyetelan **−0,94%** — mematikannya justru memperbaiki
11 dari 18 seri.

### 9. Ablasi jumlah fitur — *tahap 4a*

Satu tombol disapu enam nilai, sisanya beku: `k = 6, 8, 12, 16, 20, 25`.

`15 × 3 × 6 × 30 = 8.100` → **Tabel 7, Gambar 5**

Hasil panel 18 leaf: k=8 terbaik tapi hanya −0,88% dan tidak signifikan —
jawabannya null. Yang tidak null ada di kolom maksimum: pada k=6 galat
terburuk meledak ke 25,3, dua kali lipat semua nilai k lain. Rata-rata dan
median diam soal itu.

### 10. Ablasi data pasar — *tahap 4b*

Copot seluruh blok 120 fitur pasar sekaligus, di dua nilai k × dua aturan
seleksi × hidup/mati.

`15 × 3 × 2 k × 2 aturan × 2 kondisi × 30 = 10.800` → **Tabel 8, Gambar 6**;
perbandingan antar aturan seleksinya jadi **Gambar 10**.

Hasil panel 18 leaf terbelah: menurut rata-rata data pasar merugikan di
keempat sel, tapi menurut hitungan hari ia menang di tiga dari empat — sampai
82% hari. Ia memperbaiki hari biasa dan gagal parah di segelintir hari.

### 10b. Data pasar yang ikut dipakai saat meramal — *tahap 4c*

Tahap 4b di atas mengukur lengan yang **dilumpuhkan**. `predict()` dulu tidak
punya jalan untuk menerima seri pasar, jadi fitur `ext_*` yang dipakai saat
`fit()` selalu hilang saat meramal dan ditambal **nol**
(`warn_missing_at_predict`). Untuk ramalan rekursif multi-langkah itu tak
terhindarkan — nilai seri lain di masa depan tidak ada. Tapi desain naskah ini
**satu langkah**, dan di situ `ext_lag_1` adalah nilai pasar hari sebelumnya:
sudah diketahui, begitu juga lag 2–14.

Gejalanya terukur di hasil kolam 224: kerusakan per leaf berkorelasi dengan
jumlah slot yang direbut fitur pasar — **Spearman 0,690, p = 0,004** — dan dua
leaf yang tidak memberi slot pasar sama sekali nyaris tidak rusak (0,0% dan
4,3%). Pada satu sel uji, galat absolut turun dari 370,8 kembali ke 195,1,
hampir menyamai acuan tanpa pasar (191,5).

`15 × 3 × 2 k × 2 aturan × 30 = 5.400` → **Tabel 8b**

Lengan *tanpa* pasar tidak diulang — identik dengan `ext=False` di tahap 4b,
jadi baris itu yang jadi acuan. `uji_statistik.py` melaporkan dua pembanding:
lawan tanpa-pasar (apakah pasar menolong?) dan lawan pasar-dinolkan (berapa
banyak kerusakan Tabel 8 yang sekadar penolan nol?).

`predict()` **menolak** `external_series` tanpa `external_series_dates`:
bingkainya hanya 271 baris terakhir, sementara penyejajaran tanpa tanggal
memotong dari depan — nilai pasar 2006 akan tertempel ke baris 2026 tanpa satu
pun pesan galat.

> **Refit.** Ablasi terbalik memakai refit harian; dua ablasi lain fit sekali
> per blok. Sah, karena keduanya melaporkan selisih antar lengan dan jalan
> pintas yang sama dikenakan ke setiap lengan — menggeser kedua sisi sama
> besar. Dengan refit harian ketiganya butuh ~35 jam, dengan fit sekali ~2 jam.

---

### 11. SHAP — *tahap 5*

Seleksi hanya memutuskan fitur mana yang **masuk**; SHAP mengukur berapa besar
tiap fitur benar-benar **menggerakkan** ramalan setelah model terlatih.
→ **Gambar 7-8**

### 12. Uji statistik — *tahap 6*

Wilcoxon berpasangan atas 1.350 titik per perbandingan. Dilaporkan berempat
sekaligus: rata-rata, median, maksimum, hitungan menang.

Keempatnya sering tidak sepakat — refit harian menang lebih *sedikit* daripada
mRMR tapi justru signifikan — karena rata-rata digerakkan segelintir selisih
besar sementara uji peringkat digerakkan banyak selisih kecil yang konsisten.
Menyajikan satu saja akan menyesatkan.

**Total 27.600 ramalan** plus 1.800 pelatihan penyetelan.

---

## Keluaran

Semua di `hasil/`, atau `hasil_<nama-panel>/` untuk panel alternatif.

| Berkas | Isi |
|---|---|
| `opt_tuned.csv` | Setelan terpilih per (leaf, model) dari blok validasi |
| `opt_rolling.csv` | Blok uji 30 origin, 10 metode, refit harian |
| `headline.csv` | Desain tanggal-tunggal, 10 metode |
| `opt_ablasi.csv` | Tiga lengan ablasi terbalik |
| `sisa_kablasi.csv` | Ablasi jumlah fitur, enam nilai k |
| `sisa_eksternal.csv` | Data pasar hidup/mati × dua k × dua aturan |
| `shap_ringkas.json` | Pangsa kepentingan fitur per keluarga dan per seri |
| `uji_statistik.json` | p-value, hitungan menang, median gabungan |

Kirim isi folder itu untuk penyusunan tabel, gambar dan naskahnya.

## Perkakas lain

| Skrip | Kegunaan |
|---|---|
| `ringkas.py` | Status keenam tahap + verdikt SELESAI/BELUM |
| `cek_slot_pasar.py` | Berapa slot yang dimenangkan fitur pasar; hanya penyeleksi, murah |
| `buang_baris_rusak.py` | Buang baris dari lengan yang rusak supaya checkpoint mengisinya kembali |
| `gabung_leaf.py` | Bangun panel 15 leaf dari panel penuh |
| `ganti_hasil.py` | Arsipkan folder hasil lalu kosongkan, sebelum komputasi dari nol |
| `cache_fitur.py` | Bangun bingkai fitur sekali per leaf lalu iris; dipakai otomatis |
| `cek_jalan.py` | Apa yang sedang berjalan, dan apakah masih hidup atau sudah diam |
| `jalankan_paralel.py` | Jalankan satu tahap pada beberapa proses, dibagi per leaf |
| `gabung_shard.py` | Satukan berkas per shard jadi berkas kanonik |

---

## Catatan desain

**Checkpoint per sel.** Setiap tahap menulis sel begitu selesai dan melewati
sel yang sudah tercatat saat dijalankan ulang. Mati di tengah berarti
kehilangan satu sel, bukan seluruh pekerjaan.

**Panel dipilih lewat `JBV_PANEL`, folder hasil ikut bergeser sendiri.**
Checkpoint berkunci `(leaf, model, origin)` tanpa menyebut panel, jadi
mengganti panel tanpa memindahkan folder akan membuat sel dari dataset lama
dianggap selesai — hasilnya campuran dua dataset tanpa satu pun pesan galat.
Karena itu menyetel `JBV_PANEL` otomatis memindahkan folder, kecuali
`JBV_HASIL` disetel eksplisit.

**Blok validasi 10 origin, blok uji 30 origin.** Blok validasi lebih pendek
dengan sengaja: ini tahap pemilihan, bukan hasil yang dilaporkan. Setelan
tetap dipilih pada blok yang *mendahului* blok uji, jadi tidak ada kebocoran.
Keterbatasannya nyata dan dilaporkan naskah: sepuluh galat satu langkah tidak
cukup memisahkan empat kandidat, dan pada konfigurasi ini penyetelan justru
lebih buruk daripada memakai bawaan library.

**`TOP_K = 25` dipertahankan** supaya hanya satu hal yang berubah terhadap
draf lama. Jangan disamakan dengan `TOP_K_FEATURES = 12` di
`utils/feature_config.py`, yang dipilih dari ablasi horizon 60 hari.

**`leaves()` menegaskan jumlah leaf**, per panel lewat `NLEAF_HARUS`. Ini
menangkap salah-definisi "level terdalam", yang hanya memberi 9 baris karena
cabang B dan C berhenti di level 2.

## Jebakan yang pernah terjadi

**Nilai bawaan `mrmr_beta`.** Lengan `beta=0` harus menyebut `mrmr_beta=0.0`
secara eksplisit. Nilai bawaan `select_top_features_optimized` adalah 1.0
sejak commit 7006b01, jadi menyerahkan fungsinya begitu saja membuat lengan
"tanpa mRMR" diam-diam tetap memakai mRMR — gejalanya selisih persis 0,0000
dengan p=NaN. Sudah diperbaiki; `buang_baris_rusak.py` ada untuk merapikan
hasil yang terlanjur tertulis.

**Layar diam bukan berarti macet.** Blok uji melatih ulang model di setiap
origin; satu model bisa memakan tiga menit atau lebih sebelum mencetak apa
pun. Denyut per origin sudah dipasang supaya diamnya tidak disalahartikan.

**Jalankan di tmux, keluar dengan `Ctrl-b d`.** Tanpa tmux, proses ikut mati
begitu koneksi SSH putus.

**Dua proses meng-`append` ke satu CSV.** Inilah asal baris ganda 125,9% dan
163,3% di folder hasil panel 18 seri: `append` tidak atomik untuk tulisan
sebesar satu sel, dan barisnya saling menyisip. Kalau menjalankan sesuatu
secara paralel, pastikan berkas keluarannya terpisah — itu yang dilakukan
`JBV_SHARD`. `periksa_duplikat.py` ada untuk memeriksa hasil yang terlanjur.
