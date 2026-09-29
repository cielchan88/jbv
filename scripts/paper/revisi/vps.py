"""Komputasi ulang naskah di VPS - satu skrip: periksa, jalankan, pantau, kemas.

    cd /opt/jbv
    venv/bin/python scripts/paper/revisi/vps.py periksa     # prasyarat saja, tidak menjalankan apa pun
    venv/bin/python scripts/paper/revisi/vps.py mulai       # periksa, lalu jalan di latar belakang
    venv/bin/python scripts/paper/revisi/vps.py status      # sudah sampai mana, masih hidup atau tidak
    venv/bin/python scripts/paper/revisi/vps.py pantau      # status diperbarui tiap menit (Ctrl-C keluar)
    venv/bin/python scripts/paper/revisi/vps.py berhenti    # hentikan; checkpoint tetap tersimpan
    venv/bin/python scripts/paper/revisi/vps.py kemas       # kemas hasil jadi satu .tgz untuk diunduh

KENAPA SATU SKRIP. Sebelumnya komputasi ulang berarti menyalin loop shell dari
JALANKAN_ULANG.md, menjalankannya di tmux, lalu menebak-nebak dari cek_jalan.py
dan ringkas.py apakah ia masih hidup, lalu mengemas foldernya dengan tar. Setiap
langkah itu pernah salah di sesi-sesi sebelumnya: folder hasil yang keliru,
shard yang lupa disatukan, OOM yang membunuh proses tanpa jejak. Di sini semua
langkah itu satu alur, dan statusnya tercatat di berkas, bukan di layar.

APA YANG DIJALANKAN, BERURUTAN (urutan wajib - tahap 2-4 membaca setelan
terpilih dari tahap 1):

    1  rerun_optimal    penyetelan + blok uji 30 origin, 10 metode    paralel
    2  rerun_headline   desain tanggal tunggal                        paralel
    3  rerun_ablasi     ablasi terbalik, 3 lengan                     paralel
    4  rerun_sisa       ablasi k 6..40 + data pasar + pasar benar     paralel
    5  shap_baru        SHAP + 15 beeswarm bernama baru               seluruh panel
    6  uji_statistik    p-value, Holm/BH, hitungan menang             seluruh panel
    7  cek_slot_pasar   slot pasar per leaf untuk naskah              seluruh panel

Tahap paralel dijalankan lewat jalankan_paralel.py lalu disatukan
gabung_shard.py. Setiap tahap yang sudah lengkap DILEWATI, jadi `mulai` yang
dijalankan ulang melanjutkan, bukan mengulang. Sesudah tahap 7 hasilnya
diperiksa ringkas.py lalu dikemas otomatis.

TETAP HIDUP SESUDAH SSH PUTUS. `mulai` melepas pekerjaannya ke sesi proses
sendiri (setsid), jadi menutup Termius atau terputus jaringan tidak
menghentikannya. Tidak perlu tmux.

FOLDER HASIL BARU. Bawaannya hasil_w5 (jendela kelipatan 5) dan hasil_slot_w5.
Sidik jari konfigurasi memuat seluruh jendela, jadi menjalankan ke folder hasil
lama berhenti dengan exit 2 alih-alih mencampur dua kolam fitur.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time

DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(DIR)))
os.chdir(REPO)

PANEL = 'data/processed/sdv-wide-gabung.csv'
N_LEAF = 15
NVAL = 60

# Paket yang diimpor tahap-tahap komputasi. BUKAN requirements.txt penuh -
# streamlit, torch dan transformers tidak dipakai di sini.
PAKET = ['numpy', 'pandas', 'scipy', 'sklearn', 'lightgbm', 'xgboost',
         'statsmodels', 'prophet', 'shap', 'matplotlib', 'openpyxl']
NAMA_PIP = {'sklearn': 'scikit-learn'}

# Puncak memori per proses shard, diukur di VPS ini pada NVAL=60: 978 MB.
# Dibulatkan ke atas, karena kolam fitur sekarang 12% lebih lebar.
MB_PER_SHARD = 1200


# --------------------------------------------------------------- utilitas
def waktu():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def durasi(detik):
    detik = int(max(0, detik))
    if detik < 60:
        return f'{detik} dtk'
    if detik < 3600:
        return f'{detik // 60} mnt'
    return f'{detik // 3600} j {(detik % 3600) // 60} mnt'


def jalur_hasil(nama):
    return os.path.join(DIR, nama)


def arms_k():
    src = open(os.path.join(DIR, 'rerun_sisa.py')).read()
    return [int(x) for x in re.search(r'^ARMS_K = \[([^\]]*)\]', src, re.M).group(1).split(',')]


def tahap_daftar(hasil, slot):
    """Tahap beserta berkas keluaran dan jumlah baris yang harus dicapai.

    Target sama dengan ringkas.py. Jumlah lengan ablasi dibaca dari
    rerun_sisa.py, supaya tidak ada angka yang bisa tertinggal.
    """
    N, K = N_LEAF, len(arms_k())
    return [
        dict(id=1, nama='penyetelan + blok uji', skrip='rerun_optimal.py', paralel=True,
             hasil=hasil, target={'opt_tuned.csv': N * 3, 'opt_rolling.csv': N * 10 * 30}),
        dict(id=2, nama='desain tanggal tunggal', skrip='rerun_headline.py', paralel=True,
             hasil=hasil, target={'headline.csv': N * 10}),
        dict(id=3, nama='ablasi terbalik', skrip='rerun_ablasi.py', paralel=True,
             hasil=hasil, target={'opt_ablasi.csv': N * 3 * 3 * 30}),
        dict(id=4, nama=f'ablasi k ({K} lengan) + data pasar', skrip='rerun_sisa.py', paralel=True,
             hasil=hasil, target={'sisa_kablasi.csv': N * 3 * K * 30,
                                  'sisa_eksternal.csv': N * 3 * 2 * 2 * 2 * 30,
                                  'sisa_pasar_benar.csv': N * 3 * 2 * 2 * 30}),
        dict(id=5, nama='SHAP + beeswarm', skrip='shap_baru.py', paralel=False,
             hasil=hasil, target={'shap_ringkas.json': 1}, ckpt=('shap_baru.json', 'leaf')),
        dict(id=6, nama='uji statistik', skrip='uji_statistik.py', paralel=False,
             hasil=hasil, target={'uji_statistik.json': 1}),
        dict(id=7, nama='slot pasar', skrip='cek_slot_pasar.py', paralel=False,
             hasil=slot, target={'slot_pasar.json': N}, ckpt=('slot_pasar.json', None)),
    ]


def hitung_baris(folder, berkas):
    """Baris data di berkas kanonik DAN berkas shard-nya (yang belum disatukan)."""
    n = 0
    for p in [os.path.join(folder, berkas)] + glob.glob(
            os.path.join(folder, berkas.replace('.csv', '.shard-*.csv'))):
        if os.path.exists(p):
            with open(p, 'rb') as f:
                n += max(0, sum(1 for _ in f) - 1)
    return n


def kemajuan(t):
    """(selesai, target) untuk satu tahap."""
    folder = jalur_hasil(t['hasil'])
    if 'ckpt' in t:
        nama, kunci = t['ckpt']
        p = os.path.join(folder, nama)
        tot = N_LEAF
        try:
            d = json.load(open(p))
            n = len(d[kunci] if kunci else d)
        except Exception:
            n = 0
        # SHAP baru benar-benar selesai kalau ringkasannya sudah ditulis.
        if t['id'] == 5 and not os.path.exists(os.path.join(folder, 'shap_ringkas.json')):
            n = min(n, tot - 1) if n else 0
        return min(n, tot), tot
    sel, tot = 0, 0
    for berkas, target in t['target'].items():
        if berkas.endswith('.csv'):
            sel += min(hitung_baris(folder, berkas), target)
        else:
            sel += target if os.path.exists(os.path.join(folder, berkas)) else 0
        tot += target
    return sel, tot


def lengkap(t):
    folder = jalur_hasil(t['hasil'])
    for berkas, target in t['target'].items():
        p = os.path.join(folder, berkas)
        if berkas.endswith('.csv'):
            if not os.path.exists(p) or hitung_baris(folder, berkas) < target:
                return False
            if glob.glob(os.path.join(folder, berkas.replace('.csv', '.shard-*.csv'))):
                return False            # belum disatukan
        elif berkas == 'slot_pasar.json':
            try:
                if len(json.load(open(p))) < target:
                    return False
            except Exception:
                return False
        elif not os.path.exists(p):
            return False
    return True


def memori():
    info = {}
    try:
        for baris in open('/proc/meminfo'):
            k, v = baris.split(':', 1)
            info[k] = int(v.split()[0]) // 1024        # MB
    except Exception:
        pass
    return info


def env_tahap(hasil, nval):
    e = dict(os.environ)
    for k in ('JBV_SHARD', 'JBV_LEAF', 'JBV_BACA_SAJA', 'JBV_VERSI_PAKSA'):
        e.pop(k, None)
    e.update(JBV_PANEL=PANEL, JBV_HASIL=hasil, JBV_NVAL=str(nval), PYTHONUNBUFFERED='1')
    return e


def folder_vps(hasil):
    d = os.path.join(jalur_hasil(hasil), '_vps')
    os.makedirs(d, exist_ok=True)
    return d


def baca_status(hasil):
    p = os.path.join(jalur_hasil(hasil), '_vps', 'status.json')
    try:
        return json.load(open(p))
    except Exception:
        return {}


def tulis_status(hasil, st):
    p = os.path.join(folder_vps(hasil), 'status.json')
    tmp = p + '.tmp'
    json.dump(st, open(tmp, 'w'), indent=1)
    os.replace(tmp, p)                 # atomik: status tidak pernah terbaca setengah jadi


def pid_hidup(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- periksa
def periksa(a, cetak=True):
    """Semua prasyarat. Mengembalikan (lolos, saran_shard)."""
    ok = True
    say = print if cetak else (lambda *x, **y: None)

    def gagal(m):
        nonlocal ok
        ok = False
        say(f'  GAGAL  {m}')

    def lulus(m):
        say(f'  ok     {m}')

    def awas(m):
        say(f'  AWAS   {m}')

    say(f'\n=== PERIKSA  {waktu()} ===')

    # 1. interpreter dan paket
    say('\n-- python dan paket')
    if sys.prefix == getattr(sys, 'base_prefix', sys.prefix):
        awas(f'bukan venv ({sys.executable}). Jalankan dengan venv/bin/python.')
    else:
        lulus(f'venv: {sys.executable}')
    kurang = []
    for pk in PAKET:
        try:
            m = __import__(pk)
            lulus(f'{pk:12s} {getattr(m, "__version__", "?")}')
        except Exception:
            kurang.append(NAMA_PIP.get(pk, pk))
            gagal(f'{pk} tidak terpasang')
    if kurang:
        say(f'         pasang: {sys.executable} -m pip install {" ".join(kurang)}')

    # 2. berkas masukan
    say('\n-- data masukan')
    for p in (PANEL, 'data/external_features.xlsx'):
        (lulus if os.path.exists(p) else gagal)(p + ('' if os.path.exists(p) else ' TIDAK ADA'))

    # 3. kode yang akan dijalankan
    say('\n-- kode')
    try:
        h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
        kotor = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'],
                               capture_output=True, text=True).stdout.strip()
        (awas if kotor else lulus)(f'commit {h}' + (' - ADA PERUBAHAN BELUM DI-COMMIT' if kotor else ''))
    except Exception:
        awas('git tidak terbaca')
    try:
        sys.path.insert(0, REPO)
        from utils.feature_config import FEATURE_CONFIG as FC, MIN_HISTORY_FOR_RECURSIVE_PREDICT as MH
        w = FC['rolling_statistics']['windows']
        harap = [5, 10, 15, 20, 25, 30, 60, 120]
        (lulus if w == harap else gagal)(f'jendela rolling {w}')
        rp = FC['cross_series_features']['rolling_mean_window']
        (lulus if rp % 5 == 0 else gagal)(f'rata-rata bergerak pasar {rp}')
        lp = FC['cross_series_features']['lags']
        lulus(f'lag pasar {lp[0]}..{lp[-1]} ({len(lp)} lag)')
        lulus(f'riwayat prediksi rekursif {MH} baris (= jendela terpanjang x 3)')
    except Exception as e:
        gagal(f'feature_config tidak terbaca: {e}')
    k = arms_k()
    (lulus if max(k) >= 40 else gagal)(f'lengan ablasi k = {k}')
    # Nama tampilan leaf untuk judul beeswarm (shap_baru.py). Dicek terhadap
    # leaf panel yang sebenarnya, supaya tahap SHAP tidak berhenti berjam-jam
    # kemudian, atau mencetak kode lama.
    try:
        peta = json.load(open(os.path.join(os.path.dirname(DIR), 'nama_leaf.json')))['peta']
        r = subprocess.run([sys.executable, '-c',
                            'import sys, json; sys.path.insert(0, %r)\n'
                            'from h1_common import load_panel, leaves\n'
                            'print(json.dumps(list(leaves(load_panel()[0])["Row_ID"])))' % DIR],
                           env=dict(env_tahap('_periksa_nama', a.nval), JBV_BACA_SAJA='1'),
                           capture_output=True, text=True)
        ids = json.loads(r.stdout.strip().splitlines()[-1])
        kurang_nama = [x for x in ids if x not in peta]
        (gagal if kurang_nama else lulus)(
            f'nama leaf tampilan: {len(ids) - len(kurang_nama)} dari {len(ids)} leaf panel'
            + (f' - TANPA NAMA: {kurang_nama}' if kurang_nama else
               f' ({ids[0]} -> {peta[ids[0]]} ... {ids[-1]} -> {peta[ids[-1]]})'))
    except Exception as e:
        gagal(f'nama_leaf.json / leaf panel tidak terbaca: {e}')
    finally:
        shutil.rmtree(jalur_hasil('_periksa_nama'), ignore_errors=True)

    # 4. folder hasil: baru, atau sidik jarinya cocok
    say('\n-- folder hasil')
    for nama in (a.hasil, a.slot):
        folder = jalur_hasil(nama)
        if not os.path.exists(os.path.join(folder, 'konfigurasi.json')):
            lulus(f'{nama}: baru')
            continue
        r = subprocess.run([sys.executable, '-c',
                            'import sys; sys.path.insert(0, %r); import h1_common' % DIR],
                           env=env_tahap(nama, a.nval), capture_output=True, text=True)
        if r.returncode == 0:
            lulus(f'{nama}: sudah ada, konfigurasinya cocok - akan DILANJUTKAN')
        else:
            gagal(f'{nama}: konfigurasinya BERBEDA dari kode sekarang')
            for b in r.stderr.splitlines():
                if b.strip().startswith(('jendela', 'lag_', 'rata_', 'nval', 'panel')):
                    say(f'           {b.strip()}')
            say(f'         pakai folder lain: --hasil hasil_w5_b  (atau pindahkan folder lama)')

    # 5. mesin
    say('\n-- mesin')
    mem = memori()
    total, avail, swap = mem.get('MemTotal', 0), mem.get('MemAvailable', 0), mem.get('SwapTotal', 0)
    ncpu = os.cpu_count() or 1
    lulus(f'{ncpu} core, RAM {total} MB (tersedia {avail} MB), swap {swap} MB')
    muat = max(1, (avail + mem.get('SwapFree', 0) // 2 - 500) // MB_PER_SHARD)
    saran = int(max(1, min(ncpu, muat)))
    if swap == 0:
        awas('TANPA SWAP. Di VPS ini OOM killer pernah membunuh shard tanpa jejak.')
        say('         sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && '
            'sudo mkswap /swapfile && sudo swapon /swapfile')
    lulus(f'saran jumlah shard: {saran}  (~{MB_PER_SHARD} MB per shard)')
    bebas = shutil.disk_usage(REPO).free // (1024 ** 3)
    (lulus if bebas >= 3 else gagal)(f'ruang disk bebas {bebas} GB')

    say('\n' + ('SIAP.' if ok else 'BELUM SIAP - perbaiki yang GAGAL di atas.'))
    return ok, saran


# ------------------------------------------------------------------ kerja
def kerja(a):
    """Dijalankan di latar belakang oleh `mulai`. Menulis status.json tiap tahap."""
    daftar = tahap_daftar(a.hasil, a.slot)
    st = baca_status(a.hasil)
    st.update(mulai=st.get('mulai') or waktu(), pid=os.getpid(), keadaan='BERJALAN',
              hasil=a.hasil, slot=a.slot, nval=a.nval, shard=a.shard, galat=None)
    st.setdefault('tahap', {})
    tulis_status(a.hasil, st)
    print(f'[{waktu()}] mulai: hasil={a.hasil} slot={a.slot} nval={a.nval} shard={a.shard}', flush=True)

    for t in daftar:
        k = str(t['id'])
        if lengkap(t):
            st['tahap'].setdefault(k, {})['keadaan'] = 'SELESAI'
            tulis_status(a.hasil, st)
            print(f'[{waktu()}] tahap {k} {t["nama"]}: sudah lengkap, dilewati', flush=True)
            continue
        sel0, tot = kemajuan(t)
        st['tahap'][k] = dict(keadaan='BERJALAN', mulai=waktu(), t0=time.time(), awal=sel0)
        st['aktif'] = t['id']
        tulis_status(a.hasil, st)
        print(f'[{waktu()}] tahap {k} {t["nama"]}: mulai ({sel0}/{tot})', flush=True)

        env = env_tahap(t['hasil'], a.nval)
        if t['paralel']:
            langkah = [[sys.executable, '-u', os.path.join(DIR, 'jalankan_paralel.py'),
                        t['skrip'], str(a.shard), PANEL],
                       # --bersihkan: shard yang tertinggal membuat lengkap() menganggap
                       # tahapnya belum disatukan. Penyatuan membaca kanonik + shard dan
                       # sudah() di h1_common membaca keduanya, jadi menghapusnya aman.
                       [sys.executable, '-u', os.path.join(DIR, 'gabung_shard.py'), '--ya', '--bersihkan']]
        else:
            langkah = [[sys.executable, '-u', os.path.join(DIR, t['skrip'])]]
        for cmd in langkah:
            kode = subprocess.call(cmd, env=env)
            if kode != 0:
                st['tahap'][k]['keadaan'] = 'GAGAL'
                st.update(keadaan='GAGAL', galat=f'tahap {k} ({os.path.basename(cmd[2] if len(cmd) > 2 else cmd[1])}) keluar dengan kode {kode}')
                tulis_status(a.hasil, st)
                print(f'[{waktu()}] GAGAL: {st["galat"]}', flush=True)
                return 1
        if not lengkap(t):
            sel, tot = kemajuan(t)
            st['tahap'][k]['keadaan'] = 'GAGAL'
            st.update(keadaan='GAGAL', galat=f'tahap {k} berhenti tanpa galat tapi hasilnya belum lengkap ({sel}/{tot})')
            tulis_status(a.hasil, st)
            print(f'[{waktu()}] GAGAL: {st["galat"]}', flush=True)
            return 1
        st['tahap'][k].update(keadaan='SELESAI', selesai=waktu(), lama=time.time() - st['tahap'][k]['t0'])
        tulis_status(a.hasil, st)
        print(f'[{waktu()}] tahap {k} selesai dalam {durasi(st["tahap"][k]["lama"])}', flush=True)

    # Pemeriksaan akhir: ringkas.py membaca baca-saja, jadi aman.
    print(f'[{waktu()}] ringkas.py:', flush=True)
    subprocess.call([sys.executable, os.path.join(DIR, 'ringkas.py')], env=env_tahap(a.hasil, a.nval))
    st.update(keadaan='SELESAI', selesai=waktu(), aktif=None)
    tulis_status(a.hasil, st)
    arsip = kemas(a, cetak=True)
    st['arsip'] = arsip
    tulis_status(a.hasil, st)
    print(f'[{waktu()}] SELESAI. Arsip: {arsip}', flush=True)
    return 0


# ------------------------------------------------------------------ mulai
def mulai(a):
    st = baca_status(a.hasil)
    if st.get('keadaan') == 'BERJALAN' and pid_hidup(st.get('pid', 0)):
        print(f'Sudah berjalan (pid {st["pid"]}). Pantau: {sys.executable} {__file__} status')
        return 1
    ok, saran = periksa(a)
    if not ok:
        return 2
    if not a.shard:
        a.shard = saran
    log = os.path.join(folder_vps(a.hasil), 'vps.log')
    cmd = [sys.executable, '-u', os.path.abspath(__file__), '_kerja',
           '--hasil', a.hasil, '--slot', a.slot, '--nval', str(a.nval), '--shard', str(a.shard)]
    f = open(log, 'a')
    p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True)
    st = baca_status(a.hasil)
    st.update(pid=p.pid, keadaan='BERJALAN', shard=a.shard)
    tulis_status(a.hasil, st)
    rel = os.path.relpath(__file__, REPO)
    if (a.hasil, a.slot) != ('hasil_w5', 'hasil_slot_w5'):
        rel += f' --hasil {a.hasil} --slot {a.slot}'
    print(f'\nBERJALAN di latar belakang, pid {p.pid}, {a.shard} shard.')
    print('Aman menutup SSH/Termius - prosesnya tidak ikut berhenti.\n')
    py = os.path.relpath(sys.executable, REPO) if sys.executable.startswith(REPO) else sys.executable
    skrip, _, ekor = rel.partition(' ')
    for label, cmd in (('pantau', 'pantau'), ('status', 'status'), ('hentikan', 'berhenti')):
        print(f'  {label:9s}: {py} {skrip} {cmd} {ekor}'.rstrip())
    print(f'  log      : tail -f {os.path.relpath(log, REPO)}')
    return 0


# ----------------------------------------------------------------- status
def status(a):
    st = baca_status(a.hasil)
    daftar = tahap_daftar(a.hasil, a.slot)
    hidup = pid_hidup(st.get('pid', 0)) if st.get('pid') else False
    keadaan = st.get('keadaan', 'BELUM DIMULAI')
    if keadaan == 'BERJALAN' and not hidup:
        keadaan = 'MATI'
    print(f'\n=== STATUS  {waktu()}   folder {a.hasil} ===')
    print(f'keadaan : {keadaan}' + (f'   (pid {st["pid"]})' if st.get('pid') else '')
          + (f'   dimulai {st["mulai"]}' if st.get('mulai') else ''))
    if st.get('galat'):
        print(f'galat   : {st["galat"]}')
    print()
    tot_sel = tot_all = 0
    for t in daftar:
        k = str(t['id'])
        info = st.get('tahap', {}).get(k, {})
        sel, tot = kemajuan(t)
        tot_sel += sel / tot if tot else 0
        tot_all += 1
        ks = info.get('keadaan') or ('SELESAI' if lengkap(t) else 'menunggu')
        if ks == 'BERJALAN' and not hidup:
            ks = 'TERHENTI'
        pct = 100 * sel / tot if tot else 0
        bar = '#' * int(pct / 5) + '.' * (20 - int(pct / 5))
        eta, rinci = '', []
        if ks == 'BERJALAN' and info.get('t0'):
            dt = time.time() - info['t0']
            eta = f'  jalan {durasi(dt)}'
            rinci = eta_fase(a.hasil, t, info)
        elif ks == 'SELESAI' and info.get('lama'):
            eta = f'  {durasi(info["lama"])}'
        print(f'  {k}  {t["nama"]:30s} [{bar}] {pct:5.1f}%  {sel:>6}/{tot:<6} {ks:9s}{eta}')
        for b in rinci:
            print(f'       {b}')
    print(f'\n  keseluruhan: {100 * tot_sel / tot_all:.1f}%  (rata-rata per tahap, bukan per waktu)')

    mem = memori()
    if mem:
        print(f'\nmemori  : terpakai {mem["MemTotal"] - mem.get("MemAvailable", 0)} / {mem["MemTotal"]} MB, '
              f'swap terpakai {mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)} / {mem.get("SwapTotal", 0)} MB')

    # Baris terakhir log tiap shard: "diam" bukan berarti macet, tapi lama
    # diam sambil prosesnya mati itulah tanda OOM.
    aktif = st.get('aktif')
    if aktif:
        t = next(x for x in daftar if x['id'] == aktif)
        log = sorted(glob.glob(os.path.join(jalur_hasil(t['hasil']), f'log.{t["skrip"][:-3]}.*')))
        # Hanya log dari peluncuran terakhir (penanda waktu di ujung nama sama).
        if log:
            cap = log[-1].rsplit('.', 2)[-2]
            log = [p for p in log if p.rsplit('.', 2)[-2] == cap]
        if log:
            print('\nlog shard terakhir:')
            for p in log:
                try:
                    isi = open(p, errors='replace').read().rstrip().splitlines()
                    umur = time.time() - os.path.getmtime(p)
                    print(f'  {os.path.basename(p)[:40]:40s} {durasi(umur):>8} lalu | {(isi[-1] if isi else "")[:70]}')
                except Exception:
                    pass
    vl = os.path.join(jalur_hasil(a.hasil), '_vps', 'vps.log')
    if os.path.exists(vl):
        isi = open(vl, errors='replace').read().rstrip().splitlines()
        print('\nvps.log:')
        for b in [x for x in isi if x.startswith('[')][-4:]:
            print(f'  {b[:110]}')

    rel = os.path.relpath(__file__, REPO)
    if keadaan == 'MATI':
        print('\nPROSESNYA SUDAH TIDAK ADA, padahal belum selesai. Penyebab tersering di VPS ini: OOM.')
        print('  cek     : sudo dmesg -T | grep -iE "killed process|out of memory" | tail')
        print(f'  lanjut  : {sys.executable} {rel} mulai          (checkpoint tersimpan, tidak mengulang)')
        print(f'  lebih hemat memori: {sys.executable} {rel} mulai --shard 2')
    elif keadaan == 'GAGAL':
        print(f'\nLihat galatnya: tail -50 {os.path.relpath(vl, REPO)}')
        print(f'Sesudah diperbaiki: {sys.executable} {rel} mulai   (melanjutkan)')
    elif keadaan == 'SELESAI':
        print(f'\nSELESAI. Arsip: {st.get("arsip", "(jalankan: " + rel + " kemas)")}')
    return 0


# Satu tahap bisa memuat beberapa berkas dengan ongkos per baris yang sangat
# berbeda. Tahap 1: satu baris opt_tuned = 4 setelan x NVAL origin refit harian
# (240 fit pada NVAL=60), satu baris opt_rolling = 1 fit. Perkiraan dari laju
# gabungan membagi baris murah dengan laju baris mahal, dan pernah mencetak
# "sisa ~887 jam". Karena itu laju dihitung PER BERKAS, hanya untuk berkas
# yang sedang dikerjakan, dan berkas berikutnya ditandai "belum diketahui".
LABEL_BERKAS = {'opt_tuned.csv': 'penyetelan', 'opt_rolling.csv': 'blok uji 30 origin',
                'sisa_kablasi.csv': 'ablasi k', 'sisa_eksternal.csv': 'data pasar',
                'sisa_pasar_benar.csv': 'pasar benar'}


def eta_fase(hasil, t, info):
    berkas = [b for b in t['target'] if b.endswith('.csv')]
    if len(berkas) < 1 or 'ckpt' in t:
        return []
    folder = jalur_hasil(t['hasil'])
    p = os.path.join(folder_vps(hasil), 'fase.json')
    try:
        fase = json.load(open(p))
    except Exception:
        fase = {}
    kunci = f"{t['id']}|{info.get('t0')}"
    catat = fase.setdefault(kunci, {})
    out, aktif_ada = [], False
    for i, b in enumerate(berkas):
        n, target = min(hitung_baris(folder, b), t['target'][b]), t['target'][b]
        nama = LABEL_BERKAS.get(b, b)
        if n >= target:
            out.append(f'- {nama:20s} {n}/{target} selesai')
            continue
        if aktif_ada:
            out.append(f'- {nama:20s} {n}/{target} menunggu (laju belum diketahui)')
            continue
        aktif_ada = True
        if b not in catat:
            # Berkas pertama tahap ini dimulai bersama tahapnya; berkas
            # berikutnya dicatat saat pertama terlihat aktif.
            catat[b] = [info['t0'], info.get('awal', 0)] if i == 0 else [time.time(), n]
        t_awal, n_awal = catat[b]
        dt = time.time() - t_awal
        if n > n_awal and dt > 0:
            per = dt / (n - n_awal)
            out.append(f'- {nama:20s} {n}/{target} ~{durasi(per)}/baris, sisa fase ini ~{durasi(per * (target - n))}')
        else:
            out.append(f'- {nama:20s} {n}/{target} menghitung laju...')
    try:
        tmp = p + '.tmp'
        json.dump(fase, open(tmp, 'w'))
        os.replace(tmp, p)
    except Exception:
        pass
    return out


def pantau(a):
    try:
        while True:
            os.system('clear')
            status(a)
            st = baca_status(a.hasil)
            if st.get('keadaan') in ('SELESAI', 'GAGAL') or (st.get('pid') and not pid_hidup(st['pid'])):
                break
            print(f'\n(diperbarui tiap {a.selang} detik - Ctrl-C untuk keluar; prosesnya tetap jalan)')
            time.sleep(a.selang)
    except KeyboardInterrupt:
        print('\nkeluar dari pantauan; komputasi tetap berjalan.')
    return 0


def berhenti(a):
    st = baca_status(a.hasil)
    pid = st.get('pid')
    if not pid or not pid_hidup(pid):
        print('Tidak ada yang berjalan.')
        return 0
    os.killpg(os.getpgid(int(pid)), signal.SIGTERM)       # seluruh shard ikut
    st.update(keadaan='DIHENTIKAN', galat='dihentikan manual')
    tulis_status(a.hasil, st)
    print(f'Dihentikan (grup proses {pid}). Checkpoint tersimpan; `mulai` melanjutkan.')
    return 0


# ------------------------------------------------------------------ kemas
def kemas(a, cetak=True):
    """Satu .tgz berisi semua yang dibutuhkan penyusunan naskah, tanpa sampah.

    Dibuang: shard yang sudah disatukan, log, folder _vps. Disertakan:
    seluruh CSV/JSON hasil, beeswarm, konfigurasi.json dan versi.json (bukti
    kolam fitur dan tumpukan pustaka), plus slot_pasar.json dari folder slot.
    """
    daftar = tahap_daftar(a.hasil, a.slot)
    belum = [t['nama'] for t in daftar if not lengkap(t)]
    if belum and not getattr(a, 'paksa', False):
        print(f'BELUM LENGKAP: {", ".join(belum)}. Tambah --paksa untuk mengemas apa adanya.')
        return None
    tgl = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    arsip = os.path.join(REPO, f'jbv_{a.hasil}_{tgl}.tgz')
    buang = re.compile(r'(\.shard-|^log\.|/_vps/|/log\.|\.tmp$)')
    n = 0
    with tarfile.open(arsip, 'w:gz') as tar:
        for nama in (a.hasil, a.slot):
            akar = jalur_hasil(nama)
            for dp, _, fs in os.walk(akar):
                for f in fs:
                    p = os.path.join(dp, f)
                    rel = os.path.relpath(p, DIR)
                    if buang.search('/' + rel) or buang.search(f):
                        continue
                    tar.add(p, arcname=rel)
                    n += 1
    import hashlib
    h = hashlib.sha256(open(arsip, 'rb').read()).hexdigest()
    ukuran = os.path.getsize(arsip) / 1e6
    if cetak:
        print(f'\nARSIP  {arsip}')
        print(f'       {n} berkas, {ukuran:.1f} MB, sha256 {h[:16]}...')
        print('\nUnduh ke komputer Anda (jalankan di komputer lokal, bukan di VPS):')
        print(f'  scp <user>@<ip-vps>:{arsip} .')
        print('\nLalu unggah .tgz itu ke percakapan. Di sisi penyusun naskah, ekstrak ke')
        print('scripts/paper/revisi/ dan setel JBV_NASKAH_HASIL=.../' + a.hasil + ',')
        print('JBV_NASKAH_SLOT=.../' + a.slot + '.')
        print('\nISINYA DATA PENGAWASAN (actual/pred per sel dalam juta USD). Jangan diunggah')
        print('ke layanan berbagi publik seperti transfer.sh atau file.io, dan jangan di-commit.')
    return arsip


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('perintah', choices=['periksa', 'mulai', 'status', 'pantau', 'berhenti', 'kemas', '_kerja'])
    ap.add_argument('--hasil', default='hasil_w5', help='folder hasil (bawaan hasil_w5)')
    ap.add_argument('--slot', default='hasil_slot_w5', help='folder slot pasar (bawaan hasil_slot_w5)')
    ap.add_argument('--nval', type=int, default=NVAL, help='panjang blok validasi (bawaan 60)')
    ap.add_argument('--shard', type=int, default=0, help='jumlah proses paralel (bawaan: dari RAM dan core)')
    ap.add_argument('--selang', type=int, default=60, help='detik antar-pembaruan untuk `pantau`')
    ap.add_argument('--paksa', action='store_true', help='`kemas` walau belum lengkap')
    a = ap.parse_args()
    if a.perintah == '_kerja':
        # SIGTERM dari `berhenti` dijadikan SystemExit(143) supaya status tercatat.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        try:
            return kerja(a)
        except BaseException as e:
            st = baca_status(a.hasil)
            if st.get('keadaan') == 'BERJALAN':
                dihentikan = isinstance(e, SystemExit) and e.code == 143
                st.update(keadaan='DIHENTIKAN' if dihentikan else 'GAGAL',
                          galat='dihentikan manual' if dihentikan else f'{type(e).__name__}: {e}')
                tulis_status(a.hasil, st)
            print(f'[{waktu()}] BERHENTI: {type(e).__name__}: {e}', flush=True)
            raise
    f = {'periksa': lambda a: 0 if periksa(a)[0] else 2, 'mulai': mulai, 'status': status,
         'pantau': pantau, 'berhenti': berhenti, 'kemas': lambda a: 0 if kemas(a) else 1,
         '_kerja': kerja}[a.perintah]
    return f(a)


if __name__ == '__main__':
    sys.exit(main())
