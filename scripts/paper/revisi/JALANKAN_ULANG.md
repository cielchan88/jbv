# Komputasi ulang dengan kolam lag baru

Kolam lag diperlebar dari 4 jadi 18 (commit `f199d2d`): setiap hari dari 1
sampai 15, lalu 20, 25, 30. Kolam internal naik dari 90 ke **105** kandidat,
**137** dengan fitur eksternal.

Seluruh angka naskah harus dihitung ulang, termasuk penyetelan - setelan yang
tersimpan dipilih dengan kolam lama dan tidak lagi berlaku.

## Jalankan

```bash
cd /opt/jbv && git pull

# WAJIB: buang checkpoint lama. Tanpa ini skripnya melewati sel yang sudah
# ada dan Anda mendapat campuran dua kolam fitur - lebih buruk daripada
# tidak mengubah sama sekali.
rm -f scripts/paper/revisi/hasil/opt_tuned.csv \
      scripts/paper/revisi/hasil/opt_rolling.csv \
      scripts/paper/revisi/hasil/opt_ablasi.csv

tmux new -s naskah
/opt/jbv/venv/bin/python -u scripts/paper/revisi/rerun_optimal.py
/opt/jbv/venv/bin/python -u scripts/paper/revisi/rerun_ablasi.py
```

Lepas dengan `Ctrl-b d`, sambung lagi dengan `tmux attach -t naskah`.

Perkiraan waktu naik dari sebelumnya: kolam 105 kandidat lebih mahal
disaring daripada 90, terutama untuk mRMR yang menghitung korelasi antar
kandidat terpilih. Perkiraan **7-9 jam** untuk keduanya.

## Pantau

```bash
/opt/jbv/venv/bin/python scripts/paper/revisi/ringkas.py
```

## Kirim hasilnya

```bash
cd /opt/jbv/scripts/paper/revisi/hasil
for f in opt_rolling opt_ablasi; do cut -d, -f3- $f.csv > ${f}_kirim.csv; done
head -1 opt_rolling_kirim.csv    # harus: err,ae,mase,smape,leaf,model,origin
```

Lalu jalankan peringkas dan salin-tempel keluarannya, atau unggah
`opt_rolling_kirim.csv`, `opt_ablasi_kirim.csv`, dan `opt_tuned.csv`.

## Yang akan berubah di naskah

Seluruh Tabel 5, 6, 7, 8, 9 dan Gambar 3-10. Jangan pakai angka lama
bersama kolam baru.
