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

# 2. evaluasi satu langkah -> h1_results.csv + h1_facts2.json
#    (butuh data/processed/sdv-wide.csv dan worktree kode yang menghasilkan naskah)
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
3. **`AutoARIMA` lawan `ARIMA`** untuk `ARIMAForecaster` yang sama.
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

- **`p = 0.00139` memaksa tepat ENAM item yang diperingkat**, karena uji
  permutasi eksak untuk rho = -1 memberi 1/n! dan 1/6! = 0,001389. Abstraknya
  menyebut "ten methods" lalu "once the random walk is set aside", yang terbaca
  sembilan; 1/9! = 3e-6. Jumlah metode dalam pemeringkatan itu tidak pernah
  disebut. Naskah harus menyebutnya, dan angkanya harus datang dari yang
  menjalankan ujinya - bukan ditebak dari p-nya.
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
