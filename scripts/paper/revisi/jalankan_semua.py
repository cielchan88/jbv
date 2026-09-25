"""Jalankan SELURUH komputasi ulang naskah dengan satu perintah.

    python scripts/paper/revisi/jalankan_semua.py              # panel 18 leaf
    python scripts/paper/revisi/jalankan_semua.py gabung       # panel 15 leaf

Argumen panel boleh berupa jalan berkas, atau pintasan 'gabung' yang berarti
data/processed/sdv-wide-gabung.csv - dan kalau berkas itu belum ada, skrip
membangunnya lebih dulu lewat gabung_leaf.py. Tidak perlu 'export' apa pun.

    0. gabung_leaf     bangun panel gabungan, kalau diminta dan belum ada
    1. rerun_optimal   penyetelan + blok uji, 10 metode, refit harian
    2. rerun_headline  desain tanggal-tunggal, Tabel 5 + Lampiran A1
    3. rerun_ablasi    ablasi terbalik, 3 lengan
    4. rerun_sisa      ablasi jumlah fitur + data pasar + dua penyeleksi
    5. shap_baru       SHAP pada konfigurasi terpilih
    6. uji_statistik   p-value, hitungan menang, median gabungan

URUTANNYA WAJIB. Tahap 2 membaca setelan terpilih dari tahap 1, tahap 3 juga,
dan tahap 5 membaca seluruh berkas mentah yang dihasilkan 1-3.

KENAPA SUBPROSES, BUKAN IMPOR. h1_common membaca JBV_PANEL sekali saat
diimpor, lalu nilainya melekat di modul itu untuk seumur proses. Menjalankan
tiap tahap sebagai proses sendiri membuat panel yang dipakai selalu yang
diminta di baris perintah, bukan yang kebetulan terbaca lebih dulu.

AMAN DIJALANKAN ULANG. Setiap tahap melanjutkan dari checkpoint per sel, jadi
perintah yang sama meneruskan pekerjaan - bukan mengulangnya. Kalau mati di
tengah, jalankan lagi persis perintah yang sama.

KALAU MAU LEBIH CEPAT. Skrip ini berurutan, satu proses. Leaf saling bebas,
jadi tahap 1-4 bisa dibagi ke beberapa proses lewat jalankan_paralel.py, lalu
disatukan gabung_shard.py - lihat bagian "Lebih cepat" di README.md.
"""
import os
import subprocess
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))

# Pindah ke akar repo sebelum apa pun. Jalan panel di PINTASAN relatif
# terhadap akar repo, dan tiap skrip tahap juga ber-chdir ke sana lewat
# h1_common - tapi pemeriksaan os.path.exists di bawah dijalankan di sini,
# di cwd pemanggil. Tanpa chdir ini, menjalankan perintahnya dari direktori
# lain (misalnya home) membuat panel yang sudah ada dianggap tidak ada, lalu
# skrip berhenti dengan 'BERHENTI' padahal berkasnya lengkap.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(DIR)))
os.chdir(REPO)

PINTASAN = {'gabung': 'data/processed/sdv-wide-gabung.csv'}

TAHAP = [
    ('rerun_optimal.py', 'penyetelan + blok uji, 10 metode'),
    ('rerun_headline.py', 'desain tanggal-tunggal, Tabel 5 + Lampiran A1'),
    ('rerun_ablasi.py', 'ablasi terbalik, 3 lengan'),
    ('rerun_sisa.py', 'jumlah fitur + data pasar + dua penyeleksi'),
    ('shap_baru.py', 'SHAP pada konfigurasi terpilih'),
    ('uji_statistik.py', 'p-value, hitungan menang, median gabungan'),
]


def garis(judul):
    print('\n' + '=' * 66, flush=True)
    print(judul, flush=True)
    print('=' * 66, flush=True)


def jalankan(skrip, env):
    r = subprocess.run([sys.executable, os.path.join(DIR, skrip)], env=env)
    if r.returncode != 0:
        print(f'\nBERHENTI: {skrip} keluar dengan kode {r.returncode}. '
              f'Checkpoint tersimpan - jalankan lagi perintah yang sama.', flush=True)
        sys.exit(r.returncode)


def main():
    env = dict(os.environ)
    panel = None
    if len(sys.argv) > 1:
        panel = PINTASAN.get(sys.argv[1], sys.argv[1])
        env['JBV_PANEL'] = panel

    t0 = time.time()
    garis('KOMPUTASI ULANG NASKAH')
    print(f'  panel  {panel or "data/processed/sdv-wide.csv (bawaan)"}', flush=True)
    for i, (s, ket) in enumerate(TAHAP, 1):
        print(f'  {i}. {s:18s} {ket}', flush=True)
    print('\n  Perkiraan 12-15 jam pada panel 18 leaf, sekitar seperlima lebih\n  singkat pada panel 15 leaf. Jalankan di tmux.', flush=True)

    # Tahap 0: panel gabungan dibangun lebih dulu kalau diminta tapi belum ada.
    if panel and not os.path.exists(panel):
        garis(f'TAHAP 0  bangun {panel}')
        jalankan('gabung_leaf.py', env)
        if not os.path.exists(panel):
            print(f'BERHENTI: {panel} tetap tidak ada sesudah gabung_leaf.py.')
            sys.exit(1)

    for i, (skrip, ket) in enumerate(TAHAP, 1):
        garis(f'TAHAP {i}/{len(TAHAP)}  {skrip}  -  {ket}')
        t = time.time()
        jalankan(skrip, env)
        print(f'\n>>> tahap {i} selesai dalam {(time.time()-t)/3600:.2f} jam '
              f'| total {(time.time()-t0)/3600:.2f} jam', flush=True)

    garis(f'SELESAI dalam {(time.time()-t0)/3600:.1f} jam')
    print(f'  Ringkasan:  {sys.executable} scripts/paper/revisi/ringkas.py', flush=True)
    print('  Kirim isi folder hasil untuk penyusunan naskahnya.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nDihentikan. Checkpoint tersimpan - jalankan lagi perintah '
              'yang sama untuk melanjutkan.', flush=True)
        sys.exit(130)
