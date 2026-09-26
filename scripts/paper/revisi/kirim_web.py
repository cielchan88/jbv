"""Layani SATU berkas lewat HTTP sebentar, untuk diunduh dari peramban.

    python scripts/paper/revisi/kirim_web.py ~/hasil15_inti.tgz
    python scripts/paper/revisi/kirim_web.py ~/hasil15_inti.tgz --menit 30

KENAPA BUKAN `python3 -m http.server` SAJA. Perintah itu menyajikan SELURUH
isi folder tempat ia dijalankan, lengkap dengan daftar berkasnya, dan terus
terbuka sampai seseorang ingat mematikannya. Berkas hasil di sini memuat kolom
actual dan pred arus valas per leaf. Jadi:

  - hanya SATU berkas yang disajikan, di bawah path acak 32 heksadesimal;
    permintaan ke path lain dijawab 404, dan tidak ada daftar folder
  - server MATI SENDIRI begitu berkasnya selesai terkirim satu kali
  - ada juga batas waktu (bawaan 15 menit), supaya lupa mematikan tidak
    berarti terbuka sepanjang hari
  - port dipilih acak, bukan 8000 yang lazim dipindai

YANG TETAP HARUS ANDA TAHU. HTTP ini TIDAK terenkripsi. Berkasnya lewat dalam
bentuk terang, jadi siapa pun di jalur jaringan bisa membacanya. Path acak
membuat tautannya tidak bisa diterka, bukan membuatnya rahasia. Untuk data
seperti ini SFTP lebih pantas; ini untuk keadaan ketika SFTP tidak tersedia.
"""
import argparse
import http.server
import os
import secrets
import socket
import sys
import threading
import time


def ip_utama():
    """IP antarmuka yang dipakai keluar - biasanya IP publik VPS.

    Tidak ada data yang dikirim: UDP connect() hanya memilih rute.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '<IP-VPS>'
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('berkas')
    ap.add_argument('--menit', type=int, default=15,
                    help='batas waktu sebelum server mati sendiri (bawaan 15)')
    ap.add_argument('--port', type=int, default=0,
                    help='port tertentu; bawaan acak')
    a = ap.parse_args()

    jalan = os.path.abspath(os.path.expanduser(a.berkas))
    if not os.path.isfile(jalan):
        print(f'BERHENTI: {jalan} bukan berkas.')
        return 1
    besar = os.path.getsize(jalan)
    nama = os.path.basename(jalan)
    token = secrets.token_hex(16)
    path_sah = f'/{token}/{nama}'
    selesai = threading.Event()

    class Penyaji(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def do_GET(self):
            if self.path != path_sah:
                # Tidak menyebut apa pun tentang berkas yang ada. Pemindai
                # yang menembak path acak tidak perlu diberi petunjuk.
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(besar))
            self.send_header('Content-Disposition',
                             f'attachment; filename="{nama}"')
            self.end_headers()
            terkirim = 0
            with open(jalan, 'rb') as f:
                while True:
                    blok = f.read(64 * 1024)
                    if not blok:
                        break
                    self.wfile.write(blok)
                    terkirim += len(blok)
            print(f'  terkirim {terkirim/1e6:.2f} MB ke {self.client_address[0]}',
                  flush=True)
            # Hanya matikan kalau BENAR-BENAR utuh. Unduhan yang terputus di
            # tengah harus bisa diulang, bukan menutup pintu.
            if terkirim == besar:
                selesai.set()

        def do_HEAD(self):
            self.send_error(404)

        def log_message(self, *args):
            pass                       # diam; yang penting sudah dicetak sendiri

    srv = http.server.ThreadingHTTPServer(('0.0.0.0', a.port), Penyaji)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()

    print('=' * 68)
    print(f'  berkas : {nama}  ({besar/1e6:.2f} MB)')
    print(f'  batas  : {a.menit} menit, atau mati sendiri sesudah terkirim')
    print('=' * 68)
    print('\n  Buka di peramban HP:\n')
    print(f'    http://{ip_utama()}:{port}/{token}/{nama}\n')
    print('  Path acak; permintaan ke path lain dijawab 404.')
    print('  HTTP tidak terenkripsi - berkasnya lewat dalam bentuk terang.')
    print('  Kalau tidak terbuka, kemungkinan besar firewall menutup port ini.')
    print(f'\n  Ctrl-C untuk mematikan lebih awal.\n', flush=True)

    batas = time.time() + a.menit * 60
    try:
        while not selesai.is_set() and time.time() < batas:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print('\n  dihentikan.')
    srv.shutdown()
    if selesai.is_set():
        print('  SELESAI - berkas terkirim utuh, server ditutup.')
    elif time.time() >= batas:
        print(f'  batas {a.menit} menit tercapai, server ditutup tanpa '
              f'unduhan utuh.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
