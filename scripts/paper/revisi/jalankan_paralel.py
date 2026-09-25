"""Jalankan satu tahap komputasi pada beberapa proses sekaligus, dibagi per leaf.

    python scripts/paper/revisi/jalankan_paralel.py rerun_optimal.py 4 gabung
    python scripts/paper/revisi/jalankan_paralel.py rerun_sisa.py 4 gabung

Argumen: nama skrip tahap, jumlah proses, lalu panel (boleh 'gabung').

KENAPA INI MEMPERCEPAT. Leaf saling bebas - tidak ada tahap yang memakai hasil
leaf lain. Dan yang mahal justru bagian yang berjalan SATU UTAS: pembangunan
bingkai fitur dan seleksi mRMR, 79% waktu per sel. Pelatihan modelnya sendiri
yang memakai banyak utas hanya 0,5-1,3 detik. Jadi empat proses yang
masing-masing satu utas mengalahkan satu proses yang memakai empat utas.

KARENA ITU TIAP PROSES DIKUNCI SATU UTAS. Tanpa itu keempat proses sama-sama
meminta seluruh core dan saling berebut, dan hasilnya bisa lebih lambat
daripada berurutan. OMP_NUM_THREADS mengatur LightGBM, XGBoost dan BLAS;
LOKY_MAX_CPU_COUNT mengatur joblib, yang dipakai RandomForest.

BERKAS KELUARAN TERPISAH PER SHARD, lalu disatukan gabung_shard.py. Dua proses
yang meng-append ke satu CSV persis yang melahirkan baris ganda 125,9% dan
163,3% di folder hasil panel 18 seri - append tidak atomik untuk tulisan
sebesar satu sel, dan barisnya saling menyisip.

URUTAN ANTAR TAHAP TETAP WAJIB. rerun_headline, rerun_ablasi dan rerun_sisa
membaca setelan terpilih dari rerun_optimal. Skrip ini menjalankan SATU tahap;
satukan dulu dengan gabung_shard.py sebelum lanjut ke tahap berikutnya.

Keluaran tiap proses ditulis ke berkas log terpisah di folder hasil, karena
empat proses yang mencetak ke satu terminal saling menimpa barisnya.
"""
import os
import subprocess
import sys
import time

DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(DIR)))
os.chdir(REPO)

PINTASAN = {'gabung': 'data/processed/sdv-wide-gabung.csv'}

# Satu utas per proses. Lihat alasannya di docstring.
SATU_UTAS = {
    'OMP_NUM_THREADS': '1',
    'MKL_NUM_THREADS': '1',
    'OPENBLAS_NUM_THREADS': '1',
    'NUMEXPR_NUM_THREADS': '1',
    'LOKY_MAX_CPU_COUNT': '1',
}


def folder_hasil(panel):
    bawaan = ('hasil' if not panel else
              'hasil_' + os.path.splitext(os.path.basename(panel))[0])
    return os.path.join(DIR, os.environ.get('JBV_HASIL', bawaan))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    skrip = sys.argv[1]
    n = int(sys.argv[2])
    panel = PINTASAN.get(sys.argv[3], sys.argv[3]) if len(sys.argv) > 3 else None

    jalan_skrip = os.path.join(DIR, skrip)
    if not os.path.exists(jalan_skrip):
        print(f'BERHENTI: {jalan_skrip} tidak ada.')
        return 1
    if n < 1:
        print('BERHENTI: jumlah proses minimal 1.')
        return 1

    inti = os.cpu_count() or 1
    if n > inti:
        print(f'Catatan: {n} proses di mesin {inti} core. Proses akan '
              f'bergantian, bukan makin cepat.')

    H = folder_hasil(panel)
    os.makedirs(H, exist_ok=True)
    cap = time.strftime('%Y%m%d-%H%M')

    print('=' * 66)
    print(f'PARALEL  {skrip}  x{n}')
    print('=' * 66)
    print(f'  panel  {panel or "data/processed/sdv-wide.csv (bawaan)"}')
    print(f'  hasil  {H}')
    print(f'  core   {inti} terdeteksi, tiap proses dikunci 1 utas\n')

    proses = []
    for i in range(1, n + 1):
        env = dict(os.environ)
        env.update(SATU_UTAS)
        env['JBV_SHARD'] = f'{i}/{n}'
        if panel:
            env['JBV_PANEL'] = panel
        log = os.path.join(H, f'log.{os.path.splitext(skrip)[0]}.{i}-of-{n}.{cap}.txt')
        f = open(log, 'w')
        p = subprocess.Popen([sys.executable, '-u', jalan_skrip],
                             env=env, stdout=f, stderr=subprocess.STDOUT)
        proses.append((i, p, f, log))
        print(f'  shard {i}/{n}  pid {p.pid}  -> {os.path.basename(log)}')

    print(f'\n  Pantau:  tail -f {os.path.join(H, "log." + os.path.splitext(skrip)[0])}*')
    print('  Jalankan di tmux; keluar dengan Ctrl-b d.\n')

    t0 = time.time()
    gagal = []
    for i, p, f, log in proses:
        kode = p.wait()
        f.close()
        tanda = 'selesai' if kode == 0 else f'GAGAL kode {kode}'
        print(f'  shard {i}/{n}  {tanda}  ({(time.time()-t0)/60:.1f} menit)', flush=True)
        if kode != 0:
            gagal.append((i, log))

    print(f'\nSELURUH SHARD BERHENTI dalam {(time.time()-t0)/3600:.2f} jam')
    if gagal:
        print(f'\n{len(gagal)} shard gagal. Checkpoint per sel tersimpan, jadi '
              f'menjalankan perintah yang sama akan melanjutkan:')
        for i, log in gagal:
            print(f'  shard {i}: {log}')
        return 1

    print('\nSatukan berkasnya sebelum tahap berikutnya:')
    env_panel = f'JBV_PANEL={panel} ' if panel else ''
    print(f'  {env_panel}python scripts/paper/revisi/gabung_shard.py --ya')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\nDihentikan. Checkpoint tersimpan - jalankan lagi perintah '
              'yang sama untuk melanjutkan.')
        sys.exit(130)
