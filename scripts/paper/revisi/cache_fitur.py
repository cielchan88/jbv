"""Bangun bingkai fitur sekali per deret, lalu iris - bukan bangun ulang tiap origin.

MASALAHNYA. Protokol refit harian melatih ulang model di setiap origin, dan
setiap fit membangun seluruh bingkai fitur dari nol. Pada kolam 224 kandidat
itu 1,63 detik, sementara pelatihan modelnya sendiri 0,5-1,3 detik. Diukur di
satu sel: 79% waktu habis di pembangunan fitur dan seleksi, bukan di model.

KENAPA MENGIRIS SAH. Semua fitur di sini menoleh ke belakang - lag, rata-rata
bergerak, volatilitas, kalender - jadi nilai di baris i hanya bergantung pada
baris <= i. Menambah hari di ujung tidak mengubah baris sebelumnya. Diuji
langsung: bingkai untuk 5.002 hari, diiris di tiga titik, dibandingkan kolom
per kolom dengan bingkai yang dibangun ulang dari deret terpotong - 225 kolom,
nol perbedaan. Hasil dengan cache ini bit-identik, bukan sekadar mirip.

TERUKUR. A.2.d, 10 origin refit harian, 3 model: 94,4 s jadi 50,4 s termasuk
1,5 s pemanasan - 1,82x. Cache kena 32 dari 63 panggilan, dan 32 itu memang
batas atasnya: 30 fit ditambah 2 pemanasan. Sisa 31 adalah jalur predict(),
yang membangun dari 271 baris TERAKHIR - bukan awalan, jadi memang tidak
bisa diiris. Ketiga model bit-identik dengan hasil tanpa cache.

YANG TIDAK DI-CACHE: SELEKSI FITUR. Himpunan fitur terpilih memang berubah
saat data bertambah, dan mengunci pilihannya akan mengubah hasil. Seleksi
tetap dijalankan setiap origin.

SATU SIMPANAN UNTUK TIGA MODEL. randomforest_model, lightgbm_model dan
xgboost_model mengimpor OBJEK fungsi yang sama, jadi kuncinya pun sama dan
bingkai yang dibangun untuk model pertama langsung dipakai dua model lainnya.

PENJAGA KEBENARAN. Cache tidak bersandar pada panjang deret saja. Ia menyimpan
nilai y yang dipakai membangun, dan hanya mengiris kalau permintaan baru
benar-benar merupakan awalan dari nilai itu. Deret yang berbeda - misalnya
riwayat yang sudah disisipi ramalan - akan membangun ulang, bukan diam-diam
memakai bingkai milik deret lain.

Pakai:
    from cache_fitur import pasang_cache
    stat = pasang_cache(rfm, lgm, xgm)      # modul model yang dipercepat
    for leaf in ...:
        stat.bersihkan()                    # lepaskan bingkai leaf sebelumnya
        stat.siapkan(d, y, external_series=esd)   # WAJIB, lihat siapkan()
"""
import numpy as np


def _sidik_ext(external_series):
    """Sidik jari seri pasar untuk kunci cache: nama-namanya, bukan jumlahnya."""
    if not external_series:
        return ()
    try:
        return (id(external_series), tuple(sorted(map(str, external_series))))
    except TypeError:                      # bukan pemetaan
        return (id(external_series), len(external_series))


def _sidik_libur(holidays_list):
    """Sidik jari daftar libur: ISINYA, bukan ada-tidaknya objek.

    BaseForecaster mengubah holidays=None jadi [], lalu fit() meneruskan []
    itu ke pembangun fitur. Kunci yang hanya menanyakan `is not None` akan
    menganggap [] berbeda dari None padahal bingkainya identik - dan kunci
    pemanasan tidak akan pernah cocok dengan kunci fit(). Terukur: cache
    berhenti di 35% kena dan 1,42x, karena hanya model kedua dan ketiga yang
    menumpang bingkai bangunan model pertama.
    """
    if not holidays_list:
        return ()
    return tuple(sorted(map(str, holidays_list)))


def pasang_cache(*moduls, laporkan=True):
    """Ganti create_features_advanced di tiap modul dengan versi ber-cache.

    Mengembalikan fungsi statistik() yang melaporkan berapa kali cache kena
    dan berapa kali bingkai dibangun ulang.
    """
    simpan = {}
    hit = [0, 0]                       # [kena cache, bangun ulang]

    def bungkus(asli):
        def dipanggil(df, lag_steps=90, holidays_list=None, external_series=None,
                      **kw):
            y = np.asarray(df.iloc[:, 1].values, dtype=float)
            n = len(y)
            # Kunci menyebut NAMA seri pasar, bukan sekadar jumlahnya. Dua
            # kumpulan seri berbeda yang kebetulan sama banyak akan memberi
            # bingkai yang berbeda pula, dan penjaga awalan di bawah hanya
            # memeriksa y - ia tidak akan menangkap tertukarnya seri pasar.
            kunci = (id(asli), _sidik_ext(external_series), lag_steps,
                     _sidik_libur(holidays_list))
            simpanan = simpan.get(kunci)
            if simpanan is not None:
                y_lama, f_lama = simpanan
                # Hanya iris kalau permintaan ini benar-benar awalan dari
                # deret yang dipakai membangun bingkai tersimpan.
                if n <= len(y_lama) and np.array_equal(y_lama[:n], y):
                    hit[0] += 1
                    return f_lama.iloc[:n].copy()
            f = asli(df, lag_steps=lag_steps, holidays_list=holidays_list,
                     external_series=external_series, **kw)
            hit[1] += 1
            if len(f) == n:            # hanya bisa diiris kalau pemetaannya 1:1
                if simpanan is None or n > len(simpanan[0]):
                    simpan[kunci] = (y, f)
            return f
        return dipanggil

    for m in moduls:
        m.create_features_advanced = bungkus(m.create_features_advanced)

    def siapkan(dates, values=None, external_series=None, lag_steps=90,
                holidays_list=None):
        """Bangun bingkai untuk rentang TERPANJANG lebih dulu.

        Tanpa ini cache hampir tidak berguna pada protokol refit harian: tiap
        origin menambah satu hari, sehingga permintaan berikutnya selalu lebih
        panjang dari yang tersimpan dan bingkai dibangun ulang. Diukur begitu:
        cache hanya kena 33% dan percepatannya 1,39x. Dengan pemanasan ini,
        dan setelah kuncinya diperbaiki (lihat _sidik_libur), 51% dan 1,82x.

        Dipanggil sekali per leaf dengan deret penuh, seluruh origin sesudahnya
        tinggal mengiris. Ini TIDAK membocorkan masa depan: nilai fitur di
        baris i hanya bergantung pada baris <= i, jadi irisan 0..t identik
        dengan bingkai yang dibangun hanya dari 0..t - diuji kolom per kolom,
        225 kolom, nol perbedaan. Model tetap hanya melihat baris 0..t.

        Boleh dipanggil dengan (dates, values) seperti fit(), atau dengan
        satu DataFrame ds/y.

        PENTING: values harus sudah dibersihkan persis seperti fit()
        membersihkannya - fit() menjalankan np.nan_to_num lebih dulu, jadi
        di sini pun begitu. Kalau tidak, deret yang tersimpan tidak akan
        cocok dengan yang diminta dan cache tidak pernah kena.
        """
        import pandas as pd
        if values is None:
            df = dates
        else:
            v = np.nan_to_num(np.asarray(values, dtype=float),
                              nan=0.0, posinf=0.0, neginf=0.0)
            df = pd.DataFrame({'ds': pd.to_datetime(dates), 'y': v})
        for m in moduls:
            # Seri pasar HARUS dilewatkan saringan modul ini dulu, persis
            # seperti fit() melakukannya. ENABLE_CROSS_SERIES_FOR_RECURSIVE
            # bernilai False secara bawaan, jadi fit() membuang seri pasar
            # dan membangun bingkai TANPA fitur ext_*. Memanaskan cache
            # dengan seri pasar utuh menghasilkan kunci yang tidak akan
            # pernah diminta fit(), dan pemanasannya mubazir - terukur:
            # cache hanya kena 35% dan percepatannya berhenti di 1,46x.
            # rerun_sisa menambal fungsi ini jadi identitas untuk lengan
            # 'data pasar hidup', dan memanggilnya di sini ikut benar sendiri.
            es = external_series
            if es:
                import warnings as _w
                with _w.catch_warnings():
                    _w.simplefilter('ignore')
                    es = m.cross_series_for_recursive(es, 'cache_fitur')
            m.create_features_advanced(df, lag_steps=lag_steps,
                                       holidays_list=holidays_list,
                                       external_series=es)

    def statistik():
        # n_kunci ikut dilaporkan karena itulah gejala satu-satunya kalau
        # pemanasan memakai kunci yang berbeda dari yang diminta fit():
        # hasilnya tetap benar, hanya lambat. Untuk satu leaf angkanya
        # semestinya 1 (atau 2 kalau lengan 'pasar hidup' ikut dijalankan)
        # ditambah 1 untuk jalur predict yang memakai 271 baris terakhir.
        total = hit[0] + hit[1]
        return {'kena_cache': hit[0], 'bangun_ulang': hit[1],
                'n_kunci': len(simpan),
                'persen_kena': 100 * hit[0] / total if total else 0.0}

    def bersihkan():
        simpan.clear()

    if laporkan:
        print(f'[cache_fitur] aktif untuk {len(moduls)} modul model', flush=True)
    statistik.bersihkan = bersihkan
    statistik.siapkan = siapkan
    return statistik


def pasang_cache_seleksi(*moduls, laporkan=True):
    """Cache seleksi fitur per origin. Pasangan pasang_cache, untuk tahap setelan.

    KENAPA ADA YANG BISA DIHEMAT. Himpunan fitur terpilih bergantung pada data,
    jumlah fitur, dan aturan seleksinya - TIDAK pada hyperparameter model. Di
    tahap penyetelan, satu origin diselesaikan 4 kandidat setelan x 3 model =
    12 kali, dan keduabelasnya menyeleksi ulang himpunan yang sama persis.
    Diukur: seleksi 1,1 detik, jadi pada NVAL=60 terbuang 12 menit per leaf.

    KENAPA INI TIDAK SAMA DENGAN MENGUNCI SELEKSI. cache_fitur sengaja TIDAK
    menyimpan hasil seleksi, karena himpunan terpilih memang harus berubah saat
    data bertambah. Yang di-cache di sini hanya pemakaian ULANG dalam origin
    yang SAMA. Begitu datanya berubah satu baris pun, kuncinya meleset dan
    seleksi dijalankan lagi.

    PENJAGA KEBENARAN. Kuncinya memuat panjang bingkai, daftar kolomnya, dan
    parameter seleksi; nilai kolom target ikut disimpan dan dibandingkan, jadi
    bingkai dengan bentuk sama tapi isi berbeda tidak akan memakai hasil yang
    salah.
    """
    simpan = {}
    hit = [0, 0]

    def bungkus(asli):
        def dipanggil(df, top_k=None, **kw):
            try:
                y = np.asarray(df['value'].values, dtype=float)
            except Exception:
                return asli(df, top_k=top_k, **kw) if top_k is not None else asli(df, **kw)
            kunci = (id(asli), len(df), tuple(df.columns), top_k,
                     tuple(sorted(kw.items())))
            simpanan = simpan.get(kunci)
            if simpanan is not None:
                y_lama, hasil = simpanan
                if len(y_lama) == len(y) and np.array_equal(y_lama, y):
                    hit[0] += 1
                    return hasil
            out = asli(df, top_k=top_k, **kw) if top_k is not None else asli(df, **kw)
            hit[1] += 1
            simpan[kunci] = (y, out)
            return out
        return dipanggil

    for m in moduls:
        m.select_top_features = bungkus(m.select_top_features)

    def statistik():
        total = hit[0] + hit[1]
        return {'kena_cache': hit[0], 'bangun_ulang': hit[1],
                'persen_kena': 100 * hit[0] / total if total else 0.0}

    def bersihkan():
        simpan.clear()

    if laporkan:
        print(f'[cache_fitur] cache seleksi aktif untuk {len(moduls)} modul',
              flush=True)
    statistik.bersihkan = bersihkan
    return statistik
