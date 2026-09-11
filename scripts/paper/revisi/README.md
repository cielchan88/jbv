# Komputasi ulang naskah pada konfigurasi optimal

Menjawab tiga kritik pengulas yang menuntut angka baru, bukan penyuntingan:

1. **Peringkat memakai parameter bawaan.** RandomForest tersetel membaik
   9,5% dan semestinya naik ke peringkat satu. Hasil utama harus mewakili
   kapasitas optimal tiap model.
2. **Selektor univariat.** mRMR memangkas galat rata-rata ~7% dibanding
   Spearman, jadi arsitektur inferior tidak bisa dipertahankan di hasil utama.
3. **Refit statis.** Refit harian lebih baik 4,5% dan biayanya hitungan
   detik, sehingga alasan memakai jalan pintas menjadi lemah.

Ketiganya menuntut konfigurasi yang sama, jadi dijalankan sebagai satu jalur:
**mRMR + setelan terpilih dari blok validasi + refit setiap hari.**

## Jalankan di VPS, bukan di sesi Claude

Pekerjaan ini 6-7 jam. Lingkungan sesi Claude me-restart kontainernya tiap
belasan menit dan membunuh proses lepas, sehingga tidak pernah bisa selesai
di sana. VPS stabil dan sudah punya data serta venv-nya.

```bash
cd /opt/jbv && git pull
tmux new -s naskah

# tahap 1+2: setelan per leaf/model, lalu blok uji dengan refit harian
/opt/jbv/venv/bin/python -u scripts/paper/revisi/rerun_optimal.py

# tahap 3: ablasi terbalik untuk Bagian 4.3
/opt/jbv/venv/bin/python -u scripts/paper/revisi/rerun_ablasi.py
```

Lepas dengan `Ctrl-b d`, sambung lagi dengan `tmux attach -t naskah`.

## Checkpoint

Keduanya menulis **setiap sel** ke `hasil/*.csv` begitu selesai, dan
melewati sel yang sudah tercatat saat dijalankan ulang. Mati di tengah
berarti kehilangan satu sel, bukan seluruh pekerjaan. Menjalankan ulang
perintah yang sama akan melanjutkan, bukan mengulang.

## Keluaran

| Berkas | Isi |
|---|---|
| `hasil/opt_tuned.csv` | Setelan terpilih per (leaf, model) dari blok validasi |
| `hasil/opt_rolling.csv` | Blok uji 30 origin, 10 metode, refit harian |
| `hasil/opt_ablasi.csv` | Tiga lengan ablasi terbalik untuk Bagian 4.3 |

Kirim balik ketiga berkas itu untuk penyusunan tabel, gambar, dan naskahnya.

## Catatan desain

**Blok validasi 10 origin, blok uji 30 origin.** Blok validasi lebih pendek
dengan sengaja: ini tahap pemilihan, bukan hasil yang dilaporkan, dan
menyetel dengan refit harian pada 30 origin makan 10 menit per model per
leaf — 9 jam hanya untuk menyetel. Yang dipersoalkan pengulas tidak berubah:
setelan tetap dipilih pada blok yang **mendahului** blok uji, jadi tidak ada
kebocoran.

**`TOP_K = 25` dipertahankan.** Supaya hanya satu hal yang berubah terhadap
draf lama. Jangan disamakan dulu dengan `TOP_K_FEATURES = 12` di
`utils/feature_config.py`, yang dipilih dari ablasi horizon 60 hari.

**Ablasi terbalik.** Dari konfigurasi optimal, tiap lengan mematikan satu
komponen: `tanpa_setelan`, `tanpa_mrmr`, `tanpa_refit`. Arah pertanyaannya
membalik dari draf lama — bukan lagi "apakah komponen ini penting" melainkan
"berapa yang hilang kalau dimatikan" — sehingga bukti yang sudah dibayar
mahal tetap terpakai dan pembaca mendapat jawaban atas "kenapa konfigurasi
ini".
