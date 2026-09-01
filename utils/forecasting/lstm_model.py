"""
LSTM forecaster untuk deret SDV.

Berbeda dari model pohon di repo ini, jaringan saraf BENAR-BENAR peka terhadap
skala: gradien pada fitur bernilai ratusan akan menenggelamkan fitur bernilai
pecahan, dan tanh/sigmoid jenuh di luar rentang kecil. Karena itu modul ini
melakukan standardisasi sendiri - memakai statistik dari data LATIH saja, tidak
pernah dari periode uji.

Ini satu-satunya tempat di repo yang normalisasi memang diperlukan. Pengujian
sebelumnya menunjukkan standardisasi tidak berpengaruh pada RandomForest,
XGBoost, dan LightGBM (median selisih MAE tepat 0,000; Wilcoxon p = 0,79),
karena pohon memecah berdasarkan urutan nilai, bukan besarannya.

Arsitektur sengaja kecil. Tiap leaf hanya punya ~4.000 observasi dengan ekor
tebal (excess kurtosis sampai 240) dan pergeseran rezim yang terdeteksi -
kondisi di mana jaringan besar akan menghafal, bukan belajar. Satu lapis LSTM
dengan hidden kecil plus early stopping adalah pilihan yang sepadan dengan
ukuran datanya.

Prediksi bersifat RECURSIVE, sama seperti forecaster lain di sini: buffer
digeser, prediksi dimasukkan kembali sebagai input langkah berikutnya.

HASIL PENGUKURAN (18 leaf x 3 jendela, horizon 60 hari, protokol recursive):

    model        MAE     RMSE      R2    MASE    bias
    AutoARIMA  36,98    49,27  -0,124   1,244  +2,261
    LightGBM   38,73    50,90  -4,129   1,395  -1,876
    LSTM       40,56    53,37  -0,361   1,340  +1,335
    NaiveMean  40,53    52,30  -0,807   1,365  -0,888

Tidak ada selisih yang signifikan secara statistik (Wilcoxon, n=54: vs
LightGBM p=0,40; vs AutoARIMA p=0,23; vs NaiveMean p=0,74).

Cara membacanya:
- Pada MAE rata-rata, LSTM setara NaiveMean dan di bawah AutoARIMA. Ia TIDAK
  menggantikan AutoARIMA sebagai model utama.
- Tapi per leaf, LSTM terpilih sebagai terbaik di 6 dari 18 - sama banyak
  dengan AutoARIMA (LightGBM 4, NaiveMean 2). Jadi ia punya tempat.
- Yang paling menonjol: LSTM TIDAK mengalami drift recursive. R2 -0,36
  dibanding -4,13 milik LightGBM, dan bias +1,34 dibanding -1,88. Ini
  membenarkan diagnosis sebelumnya bahwa drift itu spesifik pada
  keterbatasan ekstrapolasi model pohon - LSTM bisa mengekstrapolasi,
  sehingga umpan balik recursive tidak memutar turun.
- MASE LSTM (1,340) lebih baik dari LightGBM (1,395) meski MAE rata-ratanya
  lebih besar, artinya LSTM relatif lebih unggul pada deret yang sulit.

CATATAN: sama sekali belum ada penyetelan hyperparameter. lookback, hidden,
learning rate, dan epoch memakai nilai tetap untuk semua leaf. Angka di atas
adalah dasar, bukan batas atas.

UJI TERHADAP KLAIM LITERATUR
----------------------------
Siami-Namini dkk. (2018, IEEE ICMLA) melaporkan LSTM menurunkan RMSE 84-87%
dibanding ARIMA pada 12 deret keuangan bulanan. Klaim itu diuji pada data ini
(18 leaf x 3 jendela, jendela dan data identik antar horizon):

    horizon    AutoARIMA      LSTM     selisih    LSTM menang        p
      1 hari      28,111    33,781      +20,2%          23/54    0,157
     60 hari      36,980    40,558       +9,7%          23/54    0,227

Klaim itu TIDAK terulang di sini, pada horizon mana pun. Dugaan awal bahwa
keunggulan LSTM di paper adalah artefak horizon satu-langkah juga TIDAK
terbukti - LSTM justru tertinggal lebih jauh di h=1 (+20,2%) daripada di
h=60 (+9,7%).

Penjelasan yang tersisa untuk selisih dengan paper, berdasarkan isi paper
itu sendiri:
  - ARIMA pembandingnya dilemahkan: order tetap (5,1,0) tanpa pencarian,
    diakui sendiri "may not be the optimal model". Di sini pembandingnya
    AutoARIMA dengan grid search.
  - Pola reduksi RMSE mereka mengikuti skala deret, bukan kesulitan
    peramalan: deret bernilai besar dapat 85-90%, deret indeks ~100 hanya
    1-17%. Itu tanda RMSE dihitung pada skala berbeda, dan paper menyatakan
    transformasi memang disembunyikan dari pseudocode.
  - Deret mereka adalah level indeks bertren; deret ini aliran neto bertanda
    dengan rata-rata mendekati nol dan ACF lag-1 hanya 0,444.

Satu hal yang justru terlihat dari tabel di atas: error LSTM tumbuh lebih
lambat terhadap horizon (+20,1% dari h=1 ke h=60) dibanding AutoARIMA
(+31,6%). Konsisten dengan ketiadaan drift recursive di atas. Belum diuji
apakah pada horizon lebih panjang keduanya berpotongan.

Perlu dicatat: kedua selisih di tabel TIDAK signifikan secara statistik
(p=0,157 dan p=0,227), dan LSTM menang di 23 dari 54 unit pada keduanya.
Arahnya konsisten, tapi bukan bukti kuat.
"""

import numpy as np
import pandas as pd

from .base import BaseForecaster
from .. import generate_business_dates


class LSTMForecaster(BaseForecaster):
    """
    LSTM satu lapis atas jendela nilai historis.

    Parameters
    ----------
    lookback : panjang jendela masukan (hari kerja)
    hidden   : ukuran hidden state
    epochs   : batas atas epoch; early stopping biasanya berhenti lebih awal
    patience : berapa epoch tanpa perbaikan validasi sebelum berhenti
    """

    def __init__(self, holidays=None, lookback=60, hidden=48, layers=1,
                 epochs=120, patience=12, batch_size=64, lr=1e-3,
                 val_fraction=0.15, seed=42):
        super().__init__(holidays)
        self.lookback = int(lookback)
        self.hidden = int(hidden)
        self.layers = int(layers)
        self.epochs = int(epochs)
        self.patience = int(patience)
        self.batch_size = int(batch_size)
        self.lr = float(lr)
        self.val_fraction = float(val_fraction)
        self.seed = int(seed)
        self.model = None

    # ------------------------------------------------------------------
    @staticmethod
    def _windows(values, lookback):
        """Bangun pasangan (jendela, target berikutnya)."""
        n = len(values) - lookback
        if n <= 0:
            return np.empty((0, lookback, 1), dtype=np.float32), np.empty((0,), dtype=np.float32)
        X = np.lib.stride_tricks.sliding_window_view(values[:-1], lookback)[:n]
        y = values[lookback:lookback + n]
        return X[..., None].astype(np.float32), y.astype(np.float32)

    # ------------------------------------------------------------------
    def fit(self, dates, values, external_series=None):
        import torch
        import torch.nn as nn

        torch.manual_seed(self.seed)
        np.random.seed(self.seed)
        # Batasi thread: halaman Evaluasi menjalankan banyak leaf berurutan dan
        # torch yang memakai semua core justru memperlambat karena rebutan.
        try:
            torch.set_num_threads(max(1, min(2, torch.get_num_threads())))
        except Exception:
            pass

        v = np.asarray(values, dtype=float)
        v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)

        if len(v) < self.lookback * 3:
            raise ValueError(f"Butuh minimal {self.lookback*3} observasi, ada {len(v)}")

        # Standardisasi dari data latih saja
        self.mu_ = float(np.mean(v))
        self.sd_ = float(np.std(v))
        if self.sd_ < 1e-9:
            raise ValueError("Deret konstan - tidak ada variasi untuk dipelajari")
        z = (v - self.mu_) / self.sd_

        X, y = self._windows(z, self.lookback)
        if len(X) < 50:
            raise ValueError("Jendela latih terlalu sedikit")

        # Split validasi TERAKHIR secara kronologis - bukan acak. Split acak
        # pada deret waktu membocorkan masa depan ke dalam validasi dan membuat
        # early stopping berhenti di titik yang salah.
        n_val = max(20, int(len(X) * self.val_fraction))
        n_val = min(n_val, len(X) // 3)
        Xtr, ytr = X[:-n_val], y[:-n_val]
        Xva, yva = X[-n_val:], y[-n_val:]

        dev = torch.device('cpu')
        Xtr_t = torch.from_numpy(Xtr).to(dev)
        ytr_t = torch.from_numpy(ytr).to(dev)
        Xva_t = torch.from_numpy(Xva).to(dev)
        yva_t = torch.from_numpy(yva).to(dev)

        class Net(nn.Module):
            def __init__(self, hidden, layers):
                super().__init__()
                self.lstm = nn.LSTM(1, hidden, num_layers=layers, batch_first=True)
                self.head = nn.Linear(hidden, 1)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.head(out[:, -1, :]).squeeze(-1)

        net = Net(self.hidden, self.layers).to(dev)
        opt = torch.optim.Adam(net.parameters(), lr=self.lr)
        # Huber, bukan MSE. Dengan excess kurtosis sampai 240, MSE akan
        # didominasi segelintir hari ekstrem dan model mengabaikan sisanya.
        lossf = nn.HuberLoss(delta=1.0)

        best = float('inf')
        best_state = None
        bad = 0
        n = len(Xtr_t)

        for _ in range(self.epochs):
            net.train()
            perm = torch.randperm(n)
            for i in range(0, n, self.batch_size):
                idx = perm[i:i + self.batch_size]
                opt.zero_grad()
                loss = lossf(net(Xtr_t[idx]), ytr_t[idx])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                opt.step()

            net.eval()
            with torch.no_grad():
                vl = float(lossf(net(Xva_t), yva_t))

            if vl < best - 1e-6:
                best = vl
                best_state = {k: t.clone() for k, t in net.state_dict().items()}
                bad = 0
            else:
                bad += 1
                if bad >= self.patience:
                    break

        if best_state is not None:
            net.load_state_dict(best_state)
        net.eval()

        self.model = net
        self.torch = torch
        self.last_date = pd.to_datetime(dates[-1])
        self.tail_ = z[-self.lookback:].copy()
        return self

    # ------------------------------------------------------------------
    def predict(self, dates, values, n_days):
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        torch = self.torch
        v = np.nan_to_num(np.asarray(values, dtype=float), nan=0.0, posinf=0.0, neginf=0.0)
        z = (v - self.mu_) / self.sd_
        buf = list(z[-self.lookback:])

        future_business_dates = generate_business_dates(self.last_date, n_days, self.holidays)

        out = []
        with torch.no_grad():
            for _ in range(len(future_business_dates)):
                x = torch.from_numpy(
                    np.asarray(buf[-self.lookback:], dtype=np.float32)[None, :, None])
                p = float(self.model(x).item())
                if not np.isfinite(p):
                    p = buf[-1]
                buf.append(p)
                out.append(p * self.sd_ + self.mu_)

        return out, future_business_dates
