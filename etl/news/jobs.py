"""Peluncur pekerjaan latar untuk pipeline berita.

KENAPA TIDAK DIJALANKAN LANGSUNG DI STREAMLIT

Penarikan dan penilaian berlangsung puluhan menit sampai berjam-jam. Tiga hal
akan rusak kalau dijalankan di dalam permintaan halaman:

1. Nginx dan browser memutus sambungan jauh sebelum selesai. Prosesnya
   mungkin lanjut di server, tapi penggunanya tidak pernah tahu hasilnya.
2. Streamlit menjalankan ULANG seluruh skrip halaman setiap kali ada
   interaksi. Satu klik tak sengaja bisa memulai penarikan kedua di atas
   yang pertama.
3. Satu pekerjaan panjang menahan satu worker Streamlit, sehingga halaman
   lain ikut melambat bagi semua pengguna.

Karena itu pekerjaan dilepas sebagai proses TERPISAH dengan sesi sendiri
(start_new_session=True), sehingga ia tetap hidup meskipun Streamlit
di-restart. Halaman hanya membaca berkas log dan berkas PID.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

JOB_DIR = Path('data/news/jobs')

# Perintah yang BOLEH diluncurkan dari halaman. Daftar putih, bukan daftar
# hitam: halaman tidak boleh bisa menjalankan perintah sembarang, dan
# menyusun daftar larangan selalu ada yang terlewat.
ALLOWED = {
    'cek', 'tarik-gdelt', 'tarik-situs', 'tarik-te', 'nilai',
    'agregasi', 'cakupan',
}


def _paths(name: str) -> tuple[Path, Path]:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    return JOB_DIR / f'{name}.pid', JOB_DIR / f'{name}.log'


def is_running(name: str) -> tuple[bool, int | None]:
    pid_file, _ = _paths(name)
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().split()[0])
    except Exception:
        return False, None
    try:
        # Sinyal 0 tidak mengirim apa-apa, hanya menguji keberadaan proses.
        os.kill(pid, 0)
        return True, pid
    except (ProcessLookupError, PermissionError):
        return False, pid


def launch(name: str, args: list[str]) -> dict:
    """Lepas satu tahap pipeline sebagai proses terpisah.

    Menolak kalau pekerjaan dengan nama sama masih berjalan - itu penjagaan
    terhadap klik ganda, yang di antarmuka web adalah kejadian biasa, bukan
    kecelakaan langka.
    """
    if name not in ALLOWED:
        raise ValueError(f'perintah tidak diizinkan: {name}')
    jalan, pid = is_running(name)
    if jalan:
        return {'status': 'sudah_jalan', 'pid': pid}

    pid_file, log_file = _paths(name)
    cmd = [sys.executable, '-m', 'etl.news.run', name, *[str(a) for a in args]]
    with open(log_file, 'a') as log:
        log.write(f'\n===== {datetime.now(timezone.utc).isoformat()} '
                  f'{" ".join(cmd)} =====\n')
        log.flush()
        p = subprocess.Popen(
            cmd, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(Path.cwd()),
            # Sesi baru: proses lepas dari Streamlit, jadi restart dashboard
            # tidak membunuh penarikan yang sudah berjalan dua jam.
            start_new_session=True,
        )
    pid_file.write_text(f'{p.pid}\n{" ".join(cmd)}\n')
    return {'status': 'diluncurkan', 'pid': p.pid, 'cmd': ' '.join(cmd)}


def stop(name: str) -> dict:
    jalan, pid = is_running(name)
    if not jalan or pid is None:
        return {'status': 'tidak_jalan'}
    try:
        # Bunuh seluruh grup proses, bukan hanya induknya. Tanpa ini anak
        # prosesnya jadi yatim dan tetap menarik data di latar.
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception as e:
        return {'status': 'gagal', 'pesan': f'{type(e).__name__}: {e}'}
    return {'status': 'dihentikan', 'pid': pid}


def tail(name: str, n: int = 60) -> str:
    _, log_file = _paths(name)
    if not log_file.exists():
        return '(belum ada log)'
    try:
        baris = log_file.read_text(errors='replace').splitlines()
    except Exception as e:
        return f'(log tidak terbaca: {e})'
    return '\n'.join(baris[-n:]) if baris else '(log kosong)'


def all_status() -> list[dict]:
    out = []
    for name in sorted(ALLOWED):
        jalan, pid = is_running(name)
        _, log_file = _paths(name)
        out.append({
            'pekerjaan': name,
            'status': 'BERJALAN' if jalan else 'berhenti',
            'pid': pid,
            'log_terakhir': (
                datetime.fromtimestamp(log_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                if log_file.exists() else '-'),
        })
    return out
