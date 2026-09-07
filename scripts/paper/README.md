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
