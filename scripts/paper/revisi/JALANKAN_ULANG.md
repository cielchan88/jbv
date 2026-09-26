# Komputasi ulang — panel 15 seri, kolam lag pasar 1–14, paralel per leaf

Yang berubah sejak hasil terakhir:

- **Panel 15 seri** (`sdv-wide-gabung.csv`): A.1.a→A.2.d, A.1.b→A.2.e, A.1.c→A.2.f.
- **Lag pasar diperlebar** dari `[1, 7, 14]` jadi `1..14` (commit `66bc95a`).
  Kolam dengan data pasar naik dari 136 ke **224** kandidat; kolam internal
  tetap **104**.
- **Cache bingkai fitur** (`fcd58cf`) — 1,82× pada tahap refit harian, hasil
  bit-identik.
- **Paralel per leaf** (`a922774`) — tahap 1–4 bisa dibagi ke beberapa proses.

Seluruh angka naskah dihitung ulang, termasuk penyetelan: setelan tersimpan
dipilih pada panel dan kolam yang lama.

> **Kolam 224 hanya berlaku di sebagian tahap.** `fit()` model berbasis fitur
> menyaring seri pasar lewat `cross_series_for_recursive`, dan saklar
> `ENABLE_CROSS_SERIES_FOR_RECURSIVE` bernilai `False`. Tahap 1, 2, 3 dan 4a
> berjalan pada 104 kandidat. Yang memakai 224 hanya lengan "pasar hidup" di
> tahap 4b, `shap_baru.py` dan `cek_slot_pasar.py`.

---

## 0. Ambil kode terbaru

```bash
cd /opt/jbv && git pull
nproc                      # berapa core — menentukan angka N di langkah 2
```

## 1. Arsipkan lalu kosongkan folder hasil lama

**Wajib.** Checkpoint per sel berkunci `(leaf, model, origin)` dan tidak
menyebut kolam fitur. Menjalankan ulang di atas berkas lama membuat seluruh
sel dianggap selesai: skrip berhenti dalam hitungan detik dan hasilnya tetap
hasil lama, tanpa satu pun pesan.

`ganti_hasil.py` membuat arsip `.tgz` lebih dulu dan memverifikasinya bisa
dibaca kembali; kalau pengarsipan gagal, tidak ada yang dihapus.

```bash
cd /opt/jbv

# a. folder panel 15 seri
JBV_PANEL=data/processed/sdv-wide-gabung.csv \
  venv/bin/python scripts/paper/revisi/ganti_hasil.py          # lihat dulu
JBV_PANEL=data/processed/sdv-wide-gabung.csv \
  venv/bin/python scripts/paper/revisi/ganti_hasil.py --ya     # arsipkan + kosongkan

# b. folder panel 18 seri — sidik jari konfigurasinya sudah disimpan di
#    scripts/paper/revisi/sidik_panel18.json (commit 7b2224c), jadi hasilnya
#    boleh dilepas. 'env -u' melepas kedua variabel untuk perintah ini saja.
env -u JBV_PANEL -u JBV_HASIL venv/bin/python scripts/paper/revisi/ganti_hasil.py
env -u JBV_PANEL -u JBV_HASIL venv/bin/python scripts/paper/revisi/ganti_hasil.py --ya
```

Catat jalan berkas `.tgz` yang disebutkannya. Kalau perlu mengembalikan:
`tar xzf <arsip>.tgz -C scripts/paper/revisi/`

## 2. Jalankan tahap 1–4, paralel per leaf

```bash
cd /opt/jbv && tmux new -s naskah

N=4                                           # samakan dengan nproc
P=data/processed/sdv-wide-gabung.csv

for T in rerun_optimal.py rerun_headline.py rerun_ablasi.py rerun_sisa.py; do
  venv/bin/python scripts/paper/revisi/jalankan_paralel.py $T $N gabung || break
  JBV_PANEL=$P venv/bin/python scripts/paper/revisi/gabung_shard.py --ya || break
done
```

Lepas dengan `Ctrl-b d`, sambung lagi dengan `tmux attach -t naskah`.

**Urutannya wajib** — `rerun_headline`, `rerun_ablasi` dan `rerun_sisa`
membaca setelan terpilih dari `rerun_optimal`, jadi tiap tahap disatukan dulu
sebelum tahap berikutnya. Loop di atas sudah melakukannya, dan `|| break`
menghentikannya kalau ada yang gagal.

**Kalau terputus, jalankan lagi perintah yang sama.** Checkpoint per sel
tersimpan; yang sudah selesai dilewati.

## 2b. Tahap 4c — data pasar yang ikut dipakai saat meramal

Hanya perlu kalau hasil tahap 1–4 **sudah ada**. `rerun_sisa.py` akan melewati
bagian 1 dan 2 yang sudah tercatat, dan hanya mengerjakan bagian 3 yang baru.

```bash
cd /opt/jbv && git pull
P=data/processed/sdv-wide-gabung.csv
venv/bin/python scripts/paper/revisi/jalankan_paralel.py rerun_sisa.py 4 gabung
JBV_PANEL=$P venv/bin/python scripts/paper/revisi/gabung_shard.py --ya
```

Keluarannya `sisa_pasar_benar.csv`, 5.400 baris. Lengan *tanpa* pasar tidak
diulang — identik dengan `ext=False` di bagian 2.

**Kenapa ada bagian ini.** Bagian 2 mengukur lengan yang dilumpuhkan:
`predict()` dulu tidak punya jalan menerima seri pasar, jadi fitur `ext_*` yang
dipakai saat `fit()` ditambal **nol** saat meramal. Untuk ramalan satu hari itu
tidak perlu — `ext_lag_1` adalah nilai pasar hari sebelumnya, sudah diketahui.
Terukur: kerusakan per leaf berkorelasi dengan jumlah slot pasar
(Spearman 0,690, p = 0,004), dan pada satu sel uji galat turun dari 370,8
kembali ke 195,1 setelah diperbaiki — hampir menyamai acuan tanpa pasar (191,5).

Jalur lama **tidak berubah**: parameter barunya opsional dan bawaan `None`,
jadi Tabel 5, 6, 7 dan 9 tetap apa adanya. Sudah diuji A/B di kode yang sama —
selisih maksimum 2×10⁻¹⁶.

## 2c. Blok validasi lebar — menjawab kritik pengulas

Pengulas menilai blok validasi 10 origin tidak memadai, dan hasilnya sendiri
yang membuktikan: setelan terpilih justru **1,18% lebih buruk** daripada bawaan
library. Sepuluh galat satu langkah tidak cukup memisahkan empat kandidat.

`JBV_NVAL` melebarkannya. Blok uji tetap 30 origin terakhir — blok validasi
hanya memanjang **mundur**, jadi tidak ada kebocoran.

```bash
cd /opt/jbv && git pull
P=data/processed/sdv-wide-gabung.csv
export JBV_NVAL=60
export JBV_HASIL=hasil_nval60          # WAJIB folder baru

for T in rerun_optimal.py rerun_headline.py rerun_ablasi.py rerun_sisa.py; do
  venv/bin/python scripts/paper/revisi/jalankan_paralel.py $T 4 gabung || break
  JBV_PANEL=$P venv/bin/python scripts/paper/revisi/gabung_shard.py --ya || break
done
env -u JBV_SHARD -u JBV_LEAF JBV_PANEL=$P venv/bin/python scripts/paper/revisi/shap_baru.py
env -u JBV_SHARD -u JBV_LEAF JBV_PANEL=$P venv/bin/python scripts/paper/revisi/uji_statistik.py
```

**Folder hasil harus baru.** `NVAL` sekarang ikut di sidik jari konfigurasi,
jadi menjalankannya ke folder lama akan berhenti dengan exit 2 — bukan
mencampur dua penyetelan diam-diam. Sudah diuji: `JBV_NVAL=60` ditolak di
folder yang ada, dan folder lama tetap diterima pada nilai bawaan 10.

**Biayanya linear pada NVAL.** Penyetelan = 3 model × 4 kandidat × NVAL fit per
leaf, sekitar 8,75 detik per fit:

| NVAL | penyetelan per leaf | `rerun_optimal` dengan 4 shard | seluruh 4 tahap |
|---|---|---|---|
| 10 (sekarang) | ~18 menit | ~2,5 jam | ~5–7 jam |
| 40 | ~70 menit | ~6 jam | ~9–11 jam |
| 60 | ~105 menit | ~8,5 jam | ~12–14 jam |

Saya sarankan **NVAL=60**: dua kali blok uji, cukup untuk menjadikan
pembalikan tanda sebagai temuan dan bukan derau. Kalau waktunya tidak ada,
NVAL=40 sudah empat kali lipat dari sekarang.

Setelan lama **tidak dibuang** — folder `hasil_sdv-wide-gabung` tetap utuh,
jadi naskah bisa melaporkan keduanya berdampingan: itu justru jawaban yang
lebih kuat kepada pengulas daripada sekadar mengganti angkanya.

## 3. Tahap 5–6, seluruh panel

Kedua tahap ini **tidak boleh dibagi** — keduanya menulis satu berkas
ringkasan utuh, bukan menambah baris per sel. `shap_baru.py` akan menolak
jalan kalau `JBV_SHARD` masih terpasang.

```bash
P=data/processed/sdv-wide-gabung.csv
env -u JBV_SHARD -u JBV_LEAF JBV_PANEL=$P venv/bin/python scripts/paper/revisi/shap_baru.py
env -u JBV_SHARD -u JBV_LEAF JBV_PANEL=$P venv/bin/python scripts/paper/revisi/uji_statistik.py
```

## 4. Periksa

```bash
P=data/processed/sdv-wide-gabung.csv
JBV_PANEL=$P venv/bin/python scripts/paper/revisi/ringkas.py
```

Menutup dengan verdikt **SELESAI** atau **BELUM SELESAI**, dan memperingatkan
kalau masih ada berkas shard yang belum disatukan.

Pemeriksa tambahan kalau ada yang mencurigakan:

```bash
JBV_PANEL=$P venv/bin/python scripts/paper/revisi/periksa_duplikat.py
```

## 5. Kirim hasilnya

```bash
cd /opt/jbv/scripts/paper/revisi
tar czf hasil15.tgz hasil_sdv-wide-gabung/
ls -la hasil15.tgz
```

Unggah `hasil15.tgz`. Isinya cukup untuk menyusun seluruh tabel dan gambar.

---

## Memantau saat berjalan

Dari jendela lain:

```bash
cd /opt/jbv/scripts/paper/revisi/hasil_sdv-wide-gabung
tail -f log.rerun_optimal.*           # denyut tiap shard
ls -la *.csv                          # berkas shard yang sedang tumbuh
```

Tiap shard menulis log sendiri karena empat proses yang mencetak ke satu
terminal saling menimpa barisnya.

## Kalau perlu satu leaf saja

```bash
JBV_LEAF=A.2.d JBV_PANEL=$P venv/bin/python scripts/paper/revisi/rerun_optimal.py
JBV_PANEL=$P venv/bin/python scripts/paper/revisi/gabung_shard.py --ya
```

`JBV_LEAF` menang atas `JBV_SHARD`, dan keluarannya tetap ditulis ke berkas
terpisah — jadi aman dijalankan bersamaan dengan yang lain.

## Perkiraan waktu

Serial, panel 15 seri, sebelum cache: sekitar 10–12 jam. Cache memberi 1,82×
pada tahap refit harian (terukur), dan paralel memberi tambahan sebanding
jumlah core pada bagian yang berjalan satu utas — 79% waktu per sel.

Dengan 4 core perkiraannya **2–4 jam**. Ini perkiraan dari profil waktu, bukan
pengukuran penuh: percepatan cache diukur langsung, percepatan paralel belum.

## Yang akan berubah di naskah

Seluruh Tabel 5–9 dan Gambar 3–10, plus angka SHAP. Jangan campur dengan
angka panel 18 seri atau kolam lag pasar yang lama.
