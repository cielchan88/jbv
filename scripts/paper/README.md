# Penyusun naskah evaluasi peramalan

Dua skrip untuk membongkar naskah `.docx` dan menyusunnya ulang ke kerangka
bagian jurnal standar (Abstract berlabel, Literature Review, Methodology dengan
Ethical Considerations, Results dengan pengujian hipotesis dan robustness,
Discussion, Conclusion and Future Work).

Skrip ini **hanya mengatur ulang naskah**. Tidak ada evaluasi model yang
dijalankan dan tidak ada angka yang dihitung ulang — seluruh teks, penekanan,
tabel, dan gambar diambil apa adanya dari `.docx` masukan.

## Alur

```bash
# 1. bongkar naskah lama -> doc_items.json + fig/
python3 scripts/paper/extract.py naskah-lama.docx -o kerja/

# 2. evaluasi satu langkah -> h1_results.csv + h1_facts.json
#    (butuh data/processed/sdv-wide.csv dan worktree kode di scripts/paper/paperwt)
#    PERHATIAN: langkah ini TIDAK menghasilkan h1_facts2.json yang dibaca
#    build_paper.js. Lihat "Langkah yang hilang" di bawah.
python3 scripts/paper/run_one_step.py

# 3. pasang dependensi sekali saja
cd scripts/paper && npm install && cd -

# 4. susun ulang -> naskah baru
node scripts/paper/build_paper.js kerja/ naskah-baru.docx
```

`build_paper.js` membaca `doc_items.json`, `h1_facts2.json`, dan `fig/` dari
dir-kerja. Kalau `h1_facts2.json` belum ada, langkah 2 belum dijalankan.

`extract.py` menulis `doc_items.json` (paragraf beserta gaya tiap run, isi
tabel, dan lebar kolom) dan menyalin gambar tertanam ke `kerja/fig/` dengan
nama berurutan sesuai kemunculannya di dokumen.

## Catatan pemeliharaan

Penomoran tabel berubah karena urutan bagian bergeser. `build_paper.js`
menanganinya lewat dua mekanisme, dan keduanya harus dipakai — **jangan**
mengganti nomor secara manual di dalam teks:

- `TMAP` memetakan nomor tabel lama ke nomor baru. Fungsi `fix()` menerapkannya
  ke setiap potong teks, termasuk isi sel tabel dan keterangan gambar.
- `T` memuat nomor tabel versi baru untuk teks yang memang ditulis ulang.

Urutan di dalam `fix()` penting: regex nomor tabel berjalan lebih dulu, baru
penggantian frasa di `PHRASE`. Karena itu sisi kanan `PHRASE` boleh menyebut
nomor tabel versi baru, sedangkan sisi kirinya tidak boleh memuat nomor tabel
lama.

Rujukan antar-bagian ("Section 4.5", "Figure 2(a)") tidak bisa dipetakan dengan
pola umum karena satu nomor lama bisa jatuh ke beberapa tujuan berbeda
tergantung kalimatnya. Rujukan semacam itu terdaftar satu per satu di `PHRASE`.

Setelah menyusun ulang, periksa dua hal: tidak ada nomor tabel atau gambar yang
ganda, dan setiap rujukan dalam teks menunjuk keterangan yang benar. Keduanya
bisa dicek dengan membaca hasilnya lewat `python-docx`.

### `PHRASE` bekerja per RUN, bukan per paragraf

`p()` menerapkan `fix()` ke **setiap run**, bukan ke teks paragraf. Kalimat yang
angkanya ditebalkan terpecah jadi banyak run — satu kalimat di 5.4 terpecah jadi
**tujuh** — sehingga entri `PHRASE` yang sisi kirinya melintasi batas run
**tidak akan pernah cocok**, dan gagalnya **diam**: build tetap sukses,
perbaikannya tidak masuk naskah, tidak ada yang memberi tahu.

Itu benar-benar terjadi: perbaikan dekomposisi protokol ditulis atas kalimat
utuh dan tidak pernah berlaku. Ketahuan hanya karena `cek_pendamping_docx.py`
membaca DOCX hasilnya dan masih menemukan "percentage points".

Sekarang `build_paper.js` **menghitung** berapa kali tiap entri kena dan
melaporkan yang nol di akhir build:

```
PERINGATAN: 1 dari 23 entri PHRASE tidak pernah cocok, jadi penggantiannya
TIDAK masuk naskah: …
```

Kalau muncul, pecah entrinya jadi beberapa yang masing-masing muat di satu run.

### `fix()` hanya boleh jalan SEKALI, dan hanya atas teks LAMA

Regex nomor tabel memetakan lama → baru tanpa tahu dari mana angkanya datang.
Dua akibatnya, dan keduanya pernah terjadi:

- **Teks yang ditulis baru** dan sudah memuat nomor skema baru ikut dipetakan.
  Keterangan tabel satu langkah menulis ``Table ${T.allten}`` = "Table 11",
  lalu `fix()` mengubahnya jadi `TMAP[11]` = **"Table 1"**. Terlihat di keluaran
  build sebelumnya: *"the method's position in Table 1"*, padahal maksudnya
  Tabel 11.
- **`note()` memetakan dua kali** — ia memanggil `fix()` lalu menyerahkan
  hasilnya ke `cap()` yang memanggilnya lagi. Pemetaan ganda merusak **11 dari
  13** nomor (1→5→3, 9→11→1, …), dan entri `PHRASE` yang sisi kanannya memuat
  sisi kirinya akan menempel dua kali. Belum menggigit karena tidak ada catatan
  beku yang menyebut tabel — keberuntungan, bukan desain.

Keduanya ditutup dengan `cap(label, t, { raw: true })`, yang berarti "teks ini
sudah final, jangan di-`fix()` lagi". Pakai `raw` untuk **setiap** keterangan
yang ditulis baru dan memuat nomor tabel.

Yang **tidak** memanggil `fix()`: `Rich()` dan `P()`. Jadi prosa yang ditulis
baru di sana aman dari penomoran ulang — tapi juga tidak tersentuh `PHRASE`,
sehingga penggantian nama metode di situ harus disunting langsung.

## Berkas yang tidak ikut di-commit

`doc_items.json`, `fig/`, dan berkas `.docx` memuat statistik deskriptif per
seri dari data pengawasan — rata-rata, simpangan baku, kemencengan, kurtosis,
pangsa nol. Sesuai pola `data/processed/*.csv` di `.gitignore`, ketiganya tidak
disimpan di repositori. Yang di-commit hanya skripnya, sehingga naskah bisa
disusun ulang dari `.docx` yang dipegang sendiri.

Perlu dicatat agar tidak salah paham: `build_paper.js` memuat bagian-bagian
yang ditulis ulang (abstrak, tabel hipotesis, metodologi), dan di dalamnya ada
angka hasil evaluasi agregat seperti nilai MASE dan koefisien korelasi. Yang
tidak ikut ter-commit adalah deskriptif per seri di atas, bukan seluruh angka.

Satu lagi yang sebelumnya tidak tercatat di mana pun: **`scripts/paper/paperwt`**,
worktree kode yang menghasilkan naskah ini. Ia dipisah supaya angkanya tidak
bergeser saat kode utama berubah, jadi ia memang tidak boleh masuk repo — tapi
ia juga tidak ada di `.gitignore`, sehingga tidak ada satu pun tanda bahwa ia
dibutuhkan. Sekarang tercatat, dan `run_one_step.py` menyebutnya beserta perintah
`git worktree add`-nya kalau tidak ada.

## Langkah yang hilang

Alur di atas **tidak lengkap**, dan ini lebih dari sekadar berkas yang tidak
di-commit: `build_paper.js` membaca `h1_facts2.json`, sementara `run_one_step.py`
menulis `h1_facts.json` dengan **skema yang berbeda** —

| dibutuhkan `build_paper.js` | ditulis `run_one_step.py` |
| --- | --- |
| `rows` | `table` |
| `rows[].med` | `table[].median` |
| `rows[].family` | `table[].lag_based` |
| `rows[].r1`, `.r60`, `.best` | — |
| `rho`, `rho_p` | — |
| `proto_mase` | — |
| `rec_tf_identical`, `rec_tf_pairs`, `rec_tf_max` | — |
| `dir_diff`, `dir_pairs`, `dir_median_pct`, `dir_max_pct` | — |
| `n_methods`, `n_below_one_mean`, `n_below_one_med` | `n_below_one` |

**Tidak ada apa pun di repo ini yang menulis `h1_facts2.json`.** Angka "2" pada
namanya menyiratkan ada langkah kedua yang mengolah keluaran `run_one_step.py`
menjadi bentuk yang dibaca naskah, dan langkah itu tidak ikut di-commit. Jadi
walaupun `paperwt`, `doc_items.json` dan `fig/` dilengkapi, mengikuti alur di
atas tetap **tidak** menghasilkan masukan yang bisa dibangun.

### Jalan memutar: pulihkan dari keluaran

```bash
python3 scripts/paper/pulihkan_h1_facts.py <docx-hasil-build> -o kerja/
```

Seluruh isi `H1` **sudah tercetak** di DOCX hasil build sebelumnya — tabel satu
langkah memuat `rows`, prosanya memuat setiap skalar — jadi masukannya bisa
dibaca kembali dari keluarannya. Batasnya harus dinyatakan: yang dipulihkan
adalah nilai yang **sudah dibulatkan** saat dicetak. Untuk menyusun ulang naskah
itu cukup, karena `build_paper.js` mencetak dengan pembulatan yang sama; ia
**bukan** pengganti menjalankan ulang `run_one_step.py` dan tidak boleh dipakai
sebagai sumber angka baru.

Setiap medan wajib harus ketemu, kalau tidak skrip berhenti dan menyebut medan
mana — bukan menulis JSON separuh kosong yang membuat build gagal jauh di
kemudian. Diuji dengan memberinya naskah **asli**: *"tabel satu langkah tidak
ketemu di DOCX itu. Yakin ini hasil build_paper.js, bukan naskah aslinya?"*

## Di checkout bersih naskah ini TIDAK bisa dibangun

Keempat masukannya tidak ada di repo: `doc_items.json` (ter-gitignore),
`h1_facts2.json`, `fig/`, dan `paperwt`. Dulu keduanya mati dengan jejak mentah —
`os.chdir` melempar `FileNotFoundError` tanpa menyebut worktree, dan
`readFileSync` melempar `ENOENT` tanpa menyebut langkah mana yang belum
dijalankan. Sekarang keduanya berhenti dengan pesan yang menyebut berkasnya dan
perintah untuk membuatnya.

Konsekuensinya harus dinyatakan terbuka: **angka naskah ini tidak punya jalan
kembali ke datanya di dalam repo ini.** Prosanya beku di `doc_items.json`, dan
`build_paper.js` tidak menghitung apa pun — ia hanya menata ulang. Berbeda dengan
`scripts/paper/naskah/`, yang menurunkan setiap angka dari `tables.json` dan
punya `cek_draft.py` untuk memeriksanya. Angka di sini hanya bisa diaudit secara
internal: aritmetikanya, pemakaian ulang angka yang sama untuk dua hal berbeda,
dan penomoran tabelnya.

## Konsistensi ANTAR kedua naskah

```bash
JBV_NASKAH_HASIL=$PWD/scripts/paper/revisi/hasil_nval60 \
JBV_NASKAH_BANDING=$PWD/scripts/paper/revisi/hasil_sdv-wide-gabung \
python3 scripts/paper/cek_antar_naskah.py
```

Keduanya memakai data yang sama, sebagian metode yang sama, dan sejak naskah
utama mengutip angka horizon 60 hari di 5.2 mereka saling merujuk. Kalau dikirim
berpasangan, pengulas akan membandingkannya. Yang diperiksa: panel dan rentang
tanggal, definisi penyebut MASE, himpunan metode (dengan alias
`AutoARIMA` = `ARIMA`), jumlah fitur yang dipertahankan versus default kode,
arah inversi peringkat h=1 lawan h=60, desain ablasi h=60 lawan desain naskah
pendamping, pangsa nol sel degenerat, dan penanganan hari libur.

**Cocok:** 5032 hari dan rentang tanggal identik; penyebut MASE sama
(rata-rata |selisih pertama| sampel latih), jadi persentase kedua naskah
sebanding; 18 lawan 15 sel memang beda tiga pasang yang digabung, dan naskah
utama menjelaskannya; A.1.b nol pada 95,93 persen hari, cocok dengan yang
dicetak naskah utama; ablasi h=60 memakai 18 sel x 3 jendela, sama dengan desain
naskah pendamping; **inversinya searah** — di h=1 RandomForest peringkat 1 dan
Prophet 6, di h=60 RandomForest terburuk dan Prophet terbaik, yang mendukung
rho = -0,915 yang diklaim naskah pendamping.

**Empat hal yang perlu diputuskan, bukan bug:**

1. **Default kode tidak cocok dengan naskah mana pun yang berlaku di horizonnya.**
   `TOP_K_FEATURES` kini **12**, diambil dari ablasi horizon 60 hari. Naskah utama
   melaporkan k=25 dan menemukan k=12 **+1,36 persen lebih buruk** di h=1 (tidak
   signifikan, p=0,214). Siapa pun yang menjalankan kode ini apa adanya untuk
   ramalan satu hari memakai setelan yang tidak didukung naskah utama. Ini justru
   contoh "tune at the horizon you will run" pada kode sendiri, dan pemeriksa
   menyebutnya setiap kali dijalankan.
2. **Kedua naskah menyebut "ten methods"** padahal himpunannya berbeda: irisan
   tujuh, hanya-utama `Croston`, `NaiveDrift`, `SeasonalDecomp`, hanya-pendamping
   `APUVA`, `Stacking`, `VAR`.
3. ~~`AutoARIMA` lawan `ARIMA`~~ — **sudah disamakan.** Naskah pendamping kini
   menulis `ARIMA`, seperti naskah utama. Nama itu sampai ke DOCX lewat **empat**
   kanal, dan ketiganya yang bisa diubah sudah ditutup:

   | kanal | mekanisme |
   | --- | --- |
   | prosa beku di `doc_items.json` | entri `PHRASE`, **di akhir** daftar |
   | prosa yang diketik di `build_paper.js` | disunting langsung |
   | kolom Method Tabel satu langkah, dari `h1_facts2.json` | `NAMA_METODE` saat menampilkan — kolom ini **tidak** lewat `fix()` |
   | label di dalam berkas gambar `fig/*.png` | **belum** — lihat di bawah |

   Entri `PHRASE` **harus tetap di akhir**: daftar itu dijalankan berurutan, dan
   beberapa entri di atasnya bersisi-kiri teks yang memuat `AutoARIMA`. Kalau
   renamenya dipindah ke atas, entri-entri itu tidak akan pernah cocok lagi.

   Kunci internal `run_one_step.py` sengaja **dibiarkan** `AutoARIMA`: mengubahnya
   membuat `h1_facts2.json` yang sudah ada tidak terbaca. Penggantiannya dilakukan
   saat menampilkan.

   Renamenya diuji dengan **build sungguhan** memakai masukan sintetis (setiap
   paragraf, sel tabel, keterangan dan judul beku sengaja diisi `AutoARIMA`), lalu
   DOCX-nya dibaca kembali: nol kemunculan. Uji itu menemukan satu kebocoran nyata
   — judul dibangun dari `IT[0].text` **mentah**, satu-satunya potong teks beku
   yang tidak lewat `fix()`, sehingga penomoran tabel pun tak akan terkoreksi di
   situ. Sudah ditutup.

   **Dua gambar masih memakai label lama.** Gambar tertanam di DOCX diperiksa
   satu per satu:

   | gambar | memuat `AutoARIMA`? | di mana |
   | --- | --- | --- |
   | Gambar 1 — hasil Tahap I | **ya** | kategori sumbu-x panel (a) **dan** label titik panel (b) |
   | Gambar 2 — kepentingan fitur | tidak | kategorinya keluarga fitur |
   | Gambar 3 — hasil Tahap II | tidak | protokol dan tiga model pohon |
   | Gambar 4 — MASE per metode | **ya** | kategori sumbu-y |
   | Gambar 5 — robustness inversi | tidak | distribusi |
   | Gambar A1 — MASE per seri | tidak | tiga model pohon |

   Teks di dalamnya sudah ter-raster, jadi **Gambar 1 dan Gambar 4 dibuat
   ulang**:

   ```bash
   python3 scripts/paper/figs_pendamping.py        # -> scripts/paper/fig_baru/
   ```

   Angkanya **disalin dari tabel naskah itu sendiri** — tabel Tahap I untuk
   Gambar 1, tabel sepuluh metode untuk Gambar 4 — dan direkam di
   `gambar_pendamping.json`, bukan ditaksir dari piksel gambar lama. Palet
   aslinya diambil dari PNG-nya (`#c1666b` ML, `#3d5a80` tradisional, `#9aa8bd`
   dalam-sampel), jadi keduanya menyatu dengan empat gambar lain yang tidak
   diusik.

   Nama metode diganti di **satu tempat** (`NAMA_METODE` di
   `figs_pendamping.py`), persis seperti di `build_paper.js`; kunci di
   JSON-nya sengaja tetap `AutoARIMA`.

   Klaim yang tercetak di judul Gambar 1(b) — `rho = -1.000` dan `p = 1/6!` —
   **dihitung ulang dari datanya**, tidak diketik, dan skripnya berhenti kalau
   tidak cocok. Diuji: menggeser satu nilai memberi *"rho dari data -0.4286
   tidak cocok dengan -1.0"*; membuang satu metode memberi *"1/5! = 0.008333
   tidak cocok dengan p = 0.00139"*.

   Keluarannya di-gitignore seperti `naskah/keluaran/` — skrip dan datanya yang
   di-commit, gambarnya dibangun ulang kapan saja.

   Pemeriksaan gambar itu sekalian **menutup satu celah** yang sebelumnya hanya
   bisa dilaporkan: judul panel (b) Gambar 1 berbunyi `rho=-1.000, p=0.00139,
   excl. Naive`, dan panel (a) memuat tepat **tujuh** metode — yaitu yang punya
   fit dalam-sampel. Tujuh dikurangi random walk sama dengan **enam**, dan
   1/6! = 0,001389. Jadi jumlah itu bukan tebakan dari p-nya; ia terbaca dari
   gambarnya sendiri, dan abstrak sekarang menyebutnya.
4. **Hari libur dikonfigurasi berbeda:** `run_one_step.py` meneruskan
   `load_holidays()` ke setiap peramal, `rerun_optimal.py` tidak. Sekarang
   **inert** karena `holiday_features` dan `ENABLE_HOLIDAY_FEATURES` sama-sama
   `False`, dan `p1()` mengambil nilai pertama tanpa melihat label tanggal.
   Jangan menyamakan salah satu skrip tanpa menjalankan ulang: menyalakan flag
   itu akan menggeser angka di satu naskah saja.

Ketiga kelas penjaganya diuji menyala: jumlah hari panel dibuat beda memberi
*"pendamping 5000 vs utama 5032"*; ablasi h=60 dibuat memilih k yang sama dengan
h=1 memberi *"klaim ketergantungan horizon di 5.2 tidak lagi berdasar"*; jumlah
sel ablasi dibuat tidak cocok memberi *"ablasi memakai 15 sel, pendamping 18"*.

## Memeriksa DOCX yang sudah dibangun

```bash
python3 scripts/paper/cek_pendamping_docx.py <docx-hasil-build>
```

`cek_naskah_pendamping.py` mengaudit **sumber** `build_paper.js` secara statis.
Yang ini membaca **hasilnya** dan mencocokkan prosa dengan sel tabel — baru
mungkin setelah naskah bisa disusun ulang. Sepadan dengan `cek_draft.py` milik
naskah utama, dengan satu beda yang harus dinyatakan: naskah utama mencocokkan
angka dengan **hasil komputasi**, sedangkan di sini tidak ada hasil komputasi di
repo. Yang diperiksa adalah apakah naskah **konsisten dengan dirinya sendiri**.
Itu menangkap angka usang dan salah rujuk; itu **tidak** menangkap tabel yang
seluruhnya salah.

Yang diperiksa: setiap keterangan punya tabel dan nomornya tidak ganda; setiap
`Table N`/`Figure N` yang dirujuk prosa benar-benar ada; nilai kunci Tahap I
muncul di prosa; peringkat luar-sampel tanpa random walk benar-benar terbalik
sempurna (yang mengesahkan rho = −1); baris Mean protokol dan ketiga
persentasenya; persentase segmen horizon lahir dari barisnya; baris `n = 6` di
tabel robustness disebut prosa; kolom `Rank h=60` cocok dengan urutan tabel
h=60; `Best in` berjumlah sesuai; kosakata kolom Family seragam antar-tabel; dan
nol `AutoARIMA`.

### Tabel keluarga fitur lawan Gambar 2

Keduanya mencetak **rasio yang sama** dan pernah berbeda di tiga baris:

| keluarga | tabel (lama) | gambar | dipakai |
| --- | --- | --- | --- |
| Technical indicators | 0,61× | **0,62×** | 0,62× |
| Interaction | 0,62× | **0,63×** | 0,63× |
| Extreme and jump | 0,40× | **0,39×** | 0,39× |

Angka **gambar** yang dipakai, dan alasannya bisa diperiksa. Rasio sebenarnya
lahir dari pangsa tak-terbulat, jadi membagi kolom pangsa yang tercetak tidak
menghasilkannya persis — tapi selisihnya menunjukkan mana yang lebih dekat. Pada
empat baris yang **keduanya sepakat**, deviasinya 0,06–1,17 persen. Pada tiga
baris yang berbeda, gambar menyimpang **0,06 / 1,24 / 2,82** persen dan tabel
**1,67 / 2,81 / 5,45** persen — kira-kira dua kali lipat, dan deviasi tabel pada
*Extreme and jump* jauh di luar rentang baris yang sepakat.

Ini kesimpulan dari bukti, **bukan kepastian**: pangsa tak-terbulat tidak ada di
repo, jadi tidak ada yang bisa diperiksa terhadapnya.

Angka gambarnya sekarang **direkam** di `gambar_pendamping.json`, dan
`cek_pendamping_docx.py` membandingkan ketiga kolom tabel terhadapnya — jadi
perbedaan semacam ini menggagalkan pemeriksaan, bukan menunggu ditemukan mata.

Penggantiannya **berantai**: sisi kanan satu entri (`0.62×`) sama dengan sisi
kiri entri lain. Kalau urutannya terbalik, sel *Technical* jadi 0,62 lalu
tertangkap aturan berikutnya dan berakhir 0,63 — **tanpa galat**. Karena itu
`build_paper.js` memeriksa jumlah kena tiap entri berantai, dan berhenti kalau
meleset: *"0.62× diharap 1x, kena 2x"*.

**Pemeriksa ini langsung menemukan satu kesalahan yang lolos dari audit sumber.**
Prosa beku di 5.4 memuat dekomposisi protokol yang sama salahnya dengan abstrak
— *"decomposes into 10.1 percentage points … and 7.3 points"* — dan itulah
sumber aslinya; abstrak hanya menyalinnya. Audit sumber tidak melihatnya karena
kalimat itu datang dari `doc_items.json`, bukan dari kode.

## Audit internal

```bash
python3 scripts/paper/cek_naskah_pendamping.py
```

Memeriksa tiga hal tanpa masukan apa pun, dan keluar dengan kode 1 kalau dua
yang pertama bermasalah:

1. **Aritmetika** — rata-rata MASE ketiga protokol dibaca dari prosanya sendiri,
   lalu ketiga persentasenya dihitung ulang; dekomposisi yang berlipat diuji
   terhadap totalnya; pasangan MASE segmen horizon diuji terhadap persentasenya;
   klaim "more than half the distance" dihitung; `p` uji permutasi eksak dipakai
   untuk menyimpulkan jumlah item yang diperingkat; jumlah unit diuji terhadap
   seri x jendela.
2. **Penomoran** — target ganda di `TMAP`, lompatan atau nomor ganda di `T`,
   sisi kiri `PHRASE` yang memuat nomor tabel, dan rujukan `Table N` di luar
   rentang.
3. **Angka yang dipakai ulang** di satu paragraf — dilaporkan untuk manusia,
   tidak menggagalkan.

Ketiga kelasnya diuji menyala: mengembalikan kalimat `percentage points` yang
lama memberi *"komponennya tidak menjumlah (17.4 vs 18.1)"*; menggeser satu MASE
memberi *"2.5 vs 1.681 memberi 48.72%, prosa menulis 29%"*; membuat `TMAP`
bertabrakan memberi *"target ganda: {15: 2}"*.

### Apa yang ditemukannya

Yang ditemukan dan diperbaiki:

- **Dekomposisi protokol tidak berjumlah.** Abstrak menulis "of the 18.1 per cent
  apparent penalty of recursion, 10.1 percentage points are genuine error
  accumulation and 7.3 points are information leakage". Ketiga persentase itu
  diukur terhadap **penyebut yang berbeda** — 18,1% = recursion vs teacher-forcing,
  10,1% = recursion vs direct, 7,3% = direct vs teacher-forcing — sehingga
  10,1 + 7,3 = 17,4, bukan 18,1. Dekomposisinya **berlipat**, bukan menjumlah:
  1,1010 x 1,0727 = 1,1810. Menyebutnya "percentage points" dari 18,1 salah, dan
  kesalahannya muncul dua kali: di abstrak dan di 5.3.
- **Angka 7,3 dipakai untuk dua hal berbeda** di paragraf yang sama — komponen
  kebocoran, dan median selisih antar-ramalan individual di uji satu langkah.
  Sekarang dinyatakan bahwa kemiripannya kebetulan.

Yang ditemukan tapi **tidak** diperbaiki, karena memperbaikinya butuh angka yang
tidak ada di repo:

- ~~`p = 0.00139` memaksa tepat ENAM item yang diperingkat~~ — **sudah
  diselesaikan**, dan sumbernya gambar, bukan tebakan dari p-nya. Abstraknya
  dulu menyebut "ten methods" lalu "once the random walk is set aside", yang
  terbaca sembilan (1/9! = 3e-6), tanpa pernah menyebut jumlah yang diperingkat.
  Gambar 1 panel (a) memuat tepat tujuh metode — yang punya fit dalam-sampel —
  dan judul panel (b) berbunyi `excl. Naive`, jadi enam, dan 1/6! = 0,001389.
  Abstrak sekarang menulis "in-sample fit is defined for seven of the ten
  methods ... exact across the remaining six methods ... p = 1/6! = 0.00139".
- **Ada celah antara h = 23 dan h = 30.** "negligible to h = 23 and reaches 29
  per cent beyond h = 30" tidak mengatakan apa yang terjadi di antaranya.

Yang diperiksa dan **benar**: 29% = (2,167 - 1,681)/1,681 = 28,91; "more than
half the distance" (29 > 26,2, separuh dari 52,3); 54 = 18 seri x 3 jendela,
konsisten di seluruh naskah; penggabungan panel "eighteen-fold"; sepuluh metode =
enam tradisional + empat ML, cocok dengan `FUNCFORM`/`LAGBASED` di
`run_one_step.py`; 5032 hari dan rentang tanggalnya cocok dengan naskah utama dan
dengan `data/processed/sdv-wide.csv`; 25 fitur dipertahankan cocok dengan
`TOP_K_FEATURES`.

Penomoran tabel juga diperiksa secara statis, yang memang diminta di atas dan
bisa dilakukan tanpa masukan mana pun: `TMAP` tidak punya target ganda, `T`
memuat nomor 1-16 tepat sekali tanpa lompatan, tabel 2, 12 dan 16 memang ditulis
baru (bukan dipetakan), tidak ada sisi kiri `PHRASE` yang memuat nomor tabel
sehingga tidak ada yang terpetakan dua kali, dan tidak ada rujukan `Table N`
dengan N di luar 1-16.
