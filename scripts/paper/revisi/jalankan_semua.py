"""Jalankan seluruh komputasi ulang naskah dengan satu perintah.

    python scripts/paper/revisi/jalankan_semua.py

Menjalankan rerun_optimal.py lalu rerun_ablasi.py berurutan. Urutannya
wajib: ablasi membaca setelan terpilih yang dihasilkan tahap pertama.

KENAPA PEMBUNGKUS, BUKAN DIGABUNG JADI SATU BERKAS. Kedua skrip tetap bisa
dijalankan sendiri-sendiri. Itu bukan kerapian belaka - kalau nanti hanya
ablasi yang perlu diulang (misalnya lengannya ditambah), mengulang tahap
penyetelan yang makan berjam-jam akan sia-sia.

Aman dijalankan ulang. Keduanya melanjutkan dari checkpoint per sel, jadi
perintah yang sama akan meneruskan pekerjaan, bukan mengulangnya. Kalau
tahap pertama mati di tengah, jalankan lagi perintah ini: ia menyelesaikan
sisa tahap pertama lebih dulu, baru lanjut ke ablasi.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def garis(judul):
    print('\n' + '=' * 64, flush=True)
    print(judul, flush=True)
    print('=' * 64, flush=True)


def main():
    t0 = time.time()
    garis('KOMPUTASI ULANG NASKAH - DUA TAHAP')
    print('  1. rerun_optimal.py   penyetelan + blok uji, 10 metode', flush=True)
    print('  2. rerun_ablasi.py    ablasi terbalik, 3 lengan', flush=True)
    print('  Jalankan di tmux. Perkiraan total 7-9 jam.', flush=True)

    import rerun_optimal
    rerun_optimal.main()
    t1 = time.time()
    print(f'\n>>> TAHAP 1 SELESAI dalam {(t1-t0)/3600:.1f} jam', flush=True)

    # Impor ditunda sampai di sini dengan sengaja: rerun_ablasi membaca
    # opt_tuned.csv saat modulnya dipakai, dan berkas itu baru lengkap
    # setelah tahap pertama tuntas.
    import rerun_ablasi
    rerun_ablasi.main()

    total = (time.time() - t0) / 3600
    garis(f'SELURUHNYA SELESAI dalam {total:.1f} jam')
    print('  Periksa hasilnya:', flush=True)
    print('    python scripts/paper/revisi/ringkas.py', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nDihentikan. Checkpoint tersimpan - jalankan lagi perintah '
              'yang sama untuk melanjutkan.', flush=True)
        sys.exit(130)
