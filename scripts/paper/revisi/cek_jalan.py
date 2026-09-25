"""Apa yang sedang berjalan, dan apakah ia masih hidup atau sudah diam.

    python scripts/paper/revisi/cek_jalan.py

DIAM BUKAN BERARTI MACET, DAN SEBALIKNYA. Satu sel bisa memakan tiga menit
tanpa mencetak apa pun, jadi layar yang diam tidak membuktikan proses mati.
Yang membuktikan justru dua hal lain: apakah prosesnya masih ada, dan berapa
lama sejak berkas log terakhir bertambah. Keduanya dilaporkan di sini,
berdampingan, supaya tidak perlu menebak.

Aman dijalankan kapan saja - hanya membaca. Jalankan dari jendela tmux lain,
atau dari sesi SSH kedua.

Berbeda dari ringkas.py: ringkas.py menjawab "sudah sampai mana hasilnya",
skrip ini menjawab "apakah masih ada yang mengerjakannya".
"""
import glob
import os
import sys
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
H = os.path.join(_DIR, os.environ.get('JBV_HASIL', _BAWAAN))

# Sesudah sekian menit tanpa baris baru, layak dicurigai - bukan dipastikan.
DIAM_CURIGA = 20 * 60


def durasi(detik):
    detik = int(detik)
    if detik < 60:
        return f'{detik} detik'
    if detik < 3600:
        return f'{detik // 60} menit'
    return f'{detik // 3600} jam {(detik % 3600) // 60} menit'


def proses():
    """Proses tahap yang sedang berjalan, dibaca dari /proc.

    Membaca /proc, bukan mencocokkan teks dengan pgrep: pgrep ikut menangkap
    shell yang KEBETULAN menyebut rerun_ di baris perintahnya - termasuk
    baris perintah yang memanggil skrip ini.
    """
    out = []
    aku = os.getpid()
    for d in glob.glob('/proc/[0-9]*'):
        try:
            pid = int(os.path.basename(d))
        except ValueError:
            continue
        if pid == aku:
            continue
        try:
            with open(os.path.join(d, 'cmdline'), 'rb') as f:
                arg = [a for a in f.read().split(b'\0') if a]
            mulai = os.path.getmtime(d)
        except OSError:
            continue
        if not arg or b'python' not in os.path.basename(arg[0]):
            continue
        skrip = None
        for a in arg[1:]:
            b = os.path.basename(a)
            if b.endswith(b'.py') and (b.startswith(b'rerun_')
                                       or b.startswith(b'jalankan_')
                                       or b.startswith(b'shap_')
                                       or b.startswith(b'uji_')):
                skrip = b.decode()
                break
        if skrip:
            out.append((pid, skrip, time.time() - mulai))
    return sorted(out, key=lambda x: x[1])


def main():
    sek = time.time()
    print('=' * 66)
    print('APA YANG SEDANG BERJALAN')
    print('=' * 66)
    print(f'  folder hasil : {H}')
    print(f'  waktu        : {time.strftime("%Y-%m-%d %H:%M:%S")}\n')

    # ---- 1. proses ----
    ps = proses()
    if ps:
        print(f'PROSES ({len(ps)})')
        for pid, skrip, umur in ps:
            print(f'  pid {pid:<7} {skrip:<22} jalan {durasi(umur)}')
    else:
        print('PROSES\n  tidak ada tahap yang berjalan')
    print()

    if not os.path.isdir(H):
        print(f'Folder hasil belum ada: {H}')
        return 1

    # ---- 2. log per shard: kapan terakhir bertambah ----
    log = sorted(glob.glob(os.path.join(H, 'log.*.txt')),
                 key=os.path.getmtime, reverse=True)
    if log:
        print(f'LOG ({len(log)} berkas, terbaru di atas)')
        for p in log[:8]:
            diam = sek - os.path.getmtime(p)
            baris = ''
            try:
                with open(p, 'rb') as f:              # baca ekor saja
                    f.seek(max(0, os.path.getsize(p) - 4000))
                    isi = [b for b in f.read().decode('utf-8', 'replace')
                           .splitlines() if b.strip()]
                baris = isi[-1].strip()[:64] if isi else '(kosong)'
            except OSError:
                baris = '(tidak terbaca)'
            tanda = '  <-- DIAM LAMA' if diam > DIAM_CURIGA else ''
            print(f'  {os.path.basename(p)[:44]:<44} {durasi(diam):>12} lalu{tanda}')
            print(f'      {baris}')
    else:
        print('LOG\n  tidak ada berkas log - dijalankan tanpa jalankan_paralel.py?')
    print()

    # ---- 3. berkas hasil: berapa baris, kapan terakhir tumbuh ----
    csv = sorted(glob.glob(os.path.join(H, '*.csv')))
    if csv:
        print('BERKAS HASIL')
        for p in csv:
            try:
                with open(p, 'rb') as f:
                    n = max(0, sum(1 for _ in f) - 1)
            except OSError:
                n = -1
            diam = sek - os.path.getmtime(p)
            print(f'  {os.path.basename(p)[:46]:<46} {n:>8,} baris  '
                  f'{durasi(diam):>12} lalu')
    else:
        print('BERKAS HASIL\n  belum ada')
    print()

    # ---- 4. verdikt ----
    shard = glob.glob(os.path.join(H, '*.shard-*.csv'))
    print('=' * 66)
    if ps:
        diam_min = min((sek - os.path.getmtime(p) for p in log), default=0)
        if log and diam_min > DIAM_CURIGA:
            print(f'BERJALAN, TAPI SUNYI - {len(ps)} proses hidup, log terbaru '
                  f'{durasi(diam_min)} lalu.')
            print('  Satu sel memang bisa lama. Periksa lagi beberapa menit '
                  'lagi sebelum menyimpulkan.')
        else:
            print(f'BERJALAN - {len(ps)} proses, log masih bertambah.')
    elif shard:
        print(f'BERHENTI, DAN {len(shard)} BERKAS SHARD BELUM DISATUKAN.')
        print(f'  {sys.executable} scripts/paper/revisi/gabung_shard.py --ya')
    elif csv:
        print('BERHENTI. Tidak ada shard yang menggantung.')
        print(f'  Periksa kelengkapannya: {sys.executable} scripts/paper/revisi/ringkas.py')
    else:
        print('BELUM ADA APA-APA di folder ini.')
    print('=' * 66)
    return 0


if __name__ == '__main__':
    sys.exit(main())
