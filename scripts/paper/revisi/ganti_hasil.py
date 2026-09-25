"""Arsipkan folder hasil lalu kosongkan, supaya komputasi berikutnya mengisinya dari nol.

KENAPA BUKAN SEKADAR MENGHAPUS. Isi folder hasil adalah belasan jam komputasi.
Sekali terhapus ia hanya bisa dikembalikan dengan menjalankan ulang selama itu
juga. Jadi skrip ini selalu membuat arsip .tgz lebih dulu dan menyebutkan
jalannya; kalau pengarsipan gagal, tidak ada yang dihapus.

KENAPA PERLU DIKOSONGKAN SAMA SEKALI. Setiap tahap melewati sel yang kuncinya
sudah tercatat, dan kunci itu tidak menyebut kolam fitur. Menimpa dengan cara
menjalankan ulang di atas berkas lama tidak akan menghasilkan apa-apa: seluruh
sel dianggap selesai dan skrip berhenti dalam hitungan detik. Folder harus
benar-benar kosong supaya hasil baru benar-benar baru.

Folder yang dituju ditentukan JBV_PANEL / JBV_HASIL dengan aturan yang sama
seperti skrip lain, jadi ia selalu folder yang akan dipakai komputasi
berikutnya - bukan folder lain yang kebetulan mirip namanya.

    python scripts/paper/revisi/ganti_hasil.py           # lihat saja
    python scripts/paper/revisi/ganti_hasil.py --ya      # arsipkan lalu kosongkan
"""
import os
import shutil
import sys
import tarfile
import time

_DIR = os.path.dirname(os.path.abspath(__file__))
_P = os.environ.get('JBV_PANEL')
_BAWAAN = 'hasil' if not _P else 'hasil_' + os.path.splitext(os.path.basename(_P))[0]
NAMA = os.environ.get('JBV_HASIL', _BAWAAN)
H = os.path.join(_DIR, NAMA)


def isi(folder):
    berkas = []
    for akar, _, nama in os.walk(folder):
        for x in nama:
            j = os.path.join(akar, x)
            berkas.append((os.path.relpath(j, folder), os.path.getsize(j)))
    return sorted(berkas)


def main():
    lanjut = '--ya' in sys.argv
    if not os.path.isdir(H):
        print(f'Folder hasil belum ada, tidak ada yang perlu diganti:\n  {H}')
        return 0

    berkas = isi(H)
    total = sum(s for _, s in berkas)
    print(f'folder : {H}')
    print(f'isi    : {len(berkas)} berkas, {total/1e6:.1f} MB\n')
    for nm, s in berkas:
        if s > 1000:
            print(f'  {s/1e6:8.2f} MB  {nm}')
    print(f'\n  (berkas kecil tidak ditampilkan)')

    if not lanjut:
        print('\nBELUM ADA YANG DIUBAH. Tambahkan --ya untuk mengarsipkan lalu mengosongkan.')
        print('Arsip .tgz dibuat lebih dulu; kalau pengarsipan gagal, tidak ada yang dihapus.')
        return 0

    # Pastikan tidak ada yang sedang menulis ke folder ini.
    print('\nPASTIKAN tidak ada komputasi yang sedang berjalan:')
    print('  pgrep -af "[j]alankan_semua"; pgrep -af "[r]erun_"')

    cap = time.strftime('%Y%m%d-%H%M')
    arsip = f'{H}.arsip-{cap}.tgz'
    print(f'\nmengarsipkan ke {arsip} ...', flush=True)
    with tarfile.open(arsip, 'w:gz') as t:
        t.add(H, arcname=os.path.basename(H))
    besar = os.path.getsize(arsip)
    if besar < 1000:
        print(f'BERHENTI: arsip hanya {besar} byte, mencurigakan. Tidak ada yang dihapus.')
        return 1
    print(f'  arsip {besar/1e6:.1f} MB')

    # Periksa arsipnya benar-benar bisa dibaca sebelum menghapus apa pun.
    with tarfile.open(arsip) as t:
        n_arsip = sum(1 for m in t.getmembers() if m.isfile())
    if n_arsip != len(berkas):
        print(f'BERHENTI: arsip berisi {n_arsip} berkas, folder berisi {len(berkas)}. '
              f'Tidak ada yang dihapus.')
        return 1
    print(f'  terverifikasi: {n_arsip} berkas terbaca kembali dari arsip')

    shutil.rmtree(H)
    os.makedirs(H, exist_ok=True)
    print(f'\nfolder dikosongkan: {H}')
    print('\nJalankan komputasi ulang sekarang - seluruh tahap akan mengisinya dari nol:')
    print('  python scripts/paper/revisi/jalankan_semua.py gabung')
    print(f'\nKalau perlu mengembalikan yang lama:')
    print(f'  tar xzf {arsip} -C {os.path.dirname(H)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
