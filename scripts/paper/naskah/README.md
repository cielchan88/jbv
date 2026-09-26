# Penyusun naskah

Empat langkah, dari berkas hasil mentah ke draft .docx yang setiap angkanya
sudah dicek terhadap sumbernya.

```bash
cd /opt/jbv
python scripts/paper/naskah/buat_tables.py    # 1. angka  -> keluaran/tables.json
python scripts/paper/naskah/figs.py           # 2. gambar -> keluaran/gambar/
node   scripts/paper/naskah/build.js          # 3. naskah -> keluaran/FX_15seri.docx
python scripts/paper/naskah/cek_draft.py      # 4. verifikasi
```

Langkah 3 butuh paket `docx`; ia sudah terdaftar di `scripts/paper/package.json`,
jadi `npm install` di folder itu sekali saja sudah cukup.

---

## Prasyarat

| Yang dibutuhkan | Dari mana |
|---|---|
| Tujuh CSV/JSON hasil komputasi | `jalankan_paralel.py` + `gabung_shard.py`, lalu `shap_baru.py` dan `uji_statistik.py` — lihat `scripts/paper/revisi/JALANKAN_ULANG.md` |
| `slot_pasar.json` | `JBV_HASIL=hasil_slot python scripts/paper/revisi/cek_slot_pasar.py` |

`buat_tables.py` berhenti dengan menyebut berkas yang kurang, bukan gagal di
tengah dengan `KeyError`.

## Jalan berkas

Diatur `jalan.py`, semuanya bisa dialihkan lewat env:

| Env | Bawaan | Isi |
|---|---|---|
| `JBV_NASKAH_HASIL` | `scripts/paper/revisi/hasil_sdv-wide-gabung/` | hasil komputasi mentah |
| `JBV_NASKAH_SLOT` | `scripts/paper/revisi/hasil_slot/` | `slot_pasar.json` |
| `JBV_NASKAH_KERJA` | `scripts/paper/naskah/keluaran/` | tables.json, gambar, .docx |
| `JBV_NASKAH_LAMA` | *(kosong)* | folder hasil run **sebelumnya**, opsional |

`JBV_NASKAH_LAMA` hanya dipakai untuk menghitung butir batasan soal
reprodusibilitas ARIMA. Tanpa itu langkahnya dilewati dan naskah kehilangan
satu butir — bukan galat.

**Folder `keluaran/` tidak masuk git.** `tables.json` memuat kolom `actual`
dan `pred` per leaf — arus valas dalam juta USD — dan repo ini publik.

---

## Kenapa empat berkas, bukan satu

**`buat_tables.py`** menghitung SETIAP angka naskah dari CSV/JSON mentah. Tidak
ada angka yang disalin dengan tangan ke dalam `build.js`. Itulah yang membuat
langkah 4 mungkin: pemeriksa bisa membandingkan naskah terhadap sumber yang
sama, karena keduanya membaca `tables.json`.

**`figs.py`** membangun ulang **semua** gambar yang bergantung data, termasuk
skema desain. Versi sebelumnya menyalin tiga gambar dari run terdahulu; saat
kolam fitur berubah, dua di antaranya jadi usang dan angka di badan naskah
tidak lagi cocok dengan gambarnya.

**`build.js`** hanya menata. Seluruh angkanya datang dari `tables.json`.

**`cek_draft.py`** memeriksa tiga hal, dan yang kedua paling berguna:

1. **Klaim kunci** — angka yang wajib muncul di badan naskah, dicari di teksnya.
2. **Sel tabel** — setiap angka tabel dibandingkan **numerik** dengan sumbernya,
   jadi bebas dari asumsi pembulatan.
3. **Angka yatim** — angka di prosa yang tidak bisa diturunkan dari
   `tables.json`. Sebagian besar akan berupa tahun sitasi dan nomor halaman;
   yang bukan itu layak dicurigai sebagai angka usang dari draf sebelumnya.

Keluar dengan kode 1 kalau 1 atau 2 menemukan masalah.

---

## Dua jebakan yang sudah terjadi di sini

**Pemeriksa yang berbohong soal kegagalan lebih buruk daripada tidak ada
pemeriksa.** Versi pertama `cek_draft.py` menuntut tiga desimal padahal naskah
mencetak satu, lalu melaporkan 21 kegagalan palsu. Versi berikutnya
mencocokkan Tabel 5 dengan sumber Tabel 6 — keduanya berheader identik — dan
melaporkan 16 lagi. Keduanya sudah diperbaiki, tapi pelajarannya tetap: kalau
pemeriksa ini melapor gagal, periksa dulu pemeriksanya sebelum mengubah naskah.

**Gambar yang disalin dari run lain akan usang tanpa suara.** Karena itu
`figs.py` membangun semuanya, dan tidak ada gambar yang disalin masuk.

---

## Yang tidak bisa dibangun ulang di sini

Beeswarm SHAP per leaf. `shap_baru.py` menulisnya sebagai PNG di folder
hasil (`fig/beeswarm/<leaf>.png`), dan `shap_ringkas.json` hanya menyimpan
nama fitur tanpa magnitudonya. Naskah memakai Gambar 9 — komposisi 25 slot
terpilih per seri — yang bisa direproduksi penuh dari `shap_ringkas.json`.
Kalau beeswarm-nya diinginkan, salin PNG-nya ke `keluaran/gambar/` dan
sisipkan sendiri di `build.js`.
