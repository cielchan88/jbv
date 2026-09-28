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

## Lubang di `cek_draft.py`, dan apa yang menutupnya

Pemeriksa itu **hanya melihat angka yang ada di `tables.json`**. Dua kelas
kesalahan lewat begitu saja:

- **angka yang dieja huruf** — "three lags", "none wins more than five";
- **digit yang diketik langsung ke untai** di `build.js`, yang secara kebetulan
  masih masuk akal.

Keduanya sekaligus terjadi pada kalimat kolam fitur pasar: naskah menulis
"three lags, of one, seven and fourteen days" dan "32 market candidates"
padahal konfigurasinya sudah lama lag 1–14 ditambah satu rata-rata bergerak,
120 fitur. Aritmetikanya membantah dirinya sendiri (104 + 32 = 136, bukan 224
yang disebut satu kalimat sebelumnya) dan prosa Tabel 8 di 4.2 sudah benar.
Audit satu kali menemukan lima lagi yang sejenis: jumlah seri berkurtosis di
atas 200, "none wins more than five" (sebenarnya tiga), sampel uji metode yang
diberi 1.350 padahal 450, sebaran ensemble pohon, dan butir riset lanjutan yang
sudah dikerjakan.

**Jadi aturannya: setiap angka yang mengaku fakta diturunkan dari
`tables.json`, tidak diketik.** Di mana penurunannya punya invarian, `build.js`
memeriksanya dan **gagal membangun** kalau invariannya pecah:

| penjaga | yang diperiksa |
| --- | --- |
| kolam fitur | `pool_internal + pool_pasar == pool_total`, dan `pool_pasar` habis dibagi fitur per variabel |
| `kAblasi` | ada tepat satu k acuan, dan **tidak ada** k lain yang mengalahkannya — kalau ada, klaim abstrak memang salah |
| `sebaranPohon` | ketiga ensemble pohon ada di `e2_summary` |

### Angka yang bukan hasil naskah ini

Dua berkas menyimpan angka yang **tidak bisa** diturunkan dari folder hasil,
supaya tetap terlacak dan tidak diketik ke prosa:

| berkas | isinya | kalau tidak ada |
| --- | --- | --- |
| `repro.json` | percobaan yang membandingkan beberapa **run** (utas ARIMA, SHAP lintas lingkungan) | butir batasan hilang |
| `ablasi_h60.json` | ablasi jumlah fitur pada **horizon 60 hari**, pembanding untuk klaim di 5.2 | kalimat tanpa angka |

`ablasi_h60.json` berasal dari `scripts/paper/ablation_topk.py`, tercatat di
komentar `TOP_K_FEATURES` pada `utils/feature_config.py`. CSV mentahnya tidak
ada di repo. Dua hal penting: naskah pendamping di repo ini **tidak** melaporkan
ablasi itu, jadi tidak ada yang bisa disitasi — angkanya harus dicetak di dalam
naskah; dan ablasi itu memakai **18 sel pra-penggabungan**, termasuk sel
degenerat yang naskah ini justru buang, jadi kerangka pelaporannya sama tapi
definisi selnya tidak. Naskah menyatakan kedua hal itu terbuka.

`buat_tables.py` memeriksa berkasnya: arm terbaik harus cocok dengan ringkasan,
dan `n_leaf x n_jendela x n_model` harus sama dengan `n_unit`. Keduanya
**berhenti** kalau tidak cocok, karena ringkasan yang basi akan mencetak angka
yang tidak ada di tabelnya sendiri.

Untuk mengaudit ulang setelah menambah prosa, cari untai di `build.js` yang
memuat angka di luar `${...}`: yang bertetangga dengan kata seperti *lags*,
*features*, *candidates*, *methods*, *series*, *origins* atau *per cent* adalah
kandidat klaim, dan harus diturunkan.

---

## Lampiran B: beeswarm per seri

`figs.py` **menyalin** beeswarm dari `<hasil>/fig/beeswarm/<leaf>.png`, tidak
menghitungnya ulang. `shap_baru.py` sudah menuliskannya di sana memakai nilai
SHAP yang sama yang menghasilkan `shap_ringkas.json`.

**Jangan menghitungnya ulang di mesin lain.** Fitur terpilihnya memang sama,
tapi pembagian kepentingan SHAP bisa bergeser antar versi pustaka — terukur
pada C.b, 14,6% jadi 8,6% — sehingga beeswarm-nya bertentangan dengan Gambar 9
yang memakai angka folder hasil. Kalau naskah disusun di mesin yang bukan
tempat komputasi berjalan, salin foldernya:

```bash
# di mesin tempat komputasi berjalan
cd <hasil> && tar czf ~/beeswarm.tgz fig/beeswarm/
```

Kalau gambarnya tidak lengkap, `build.js` **melewatkan seluruh Lampiran B**
dan mengatakannya. Lampiran yang memuat sebagian seri tanpa menyebut seri mana
yang hilang lebih menyesatkan daripada tidak ada lampiran. `cek_draft.py`
memeriksa B1..B15 berurutan sebagai penjagaan kedua.
