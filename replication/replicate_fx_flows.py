"""
Replication code for "Does Machine Learning Beat Simple Benchmarks? One-Day-Ahead
Forecasts of Foreign-Exchange Flows in Indonesia".

The flow data are confidential supervisory records and are NOT distributed. This
single file reimplements the design of the paper so that it can be inspected and
run on any data of the same shape. Run it on synthetic data first:

    python replicate_fx_flows.py --demo --quick        # minutes, synthetic data
    python replicate_fx_flows.py --flows flows.csv [--market market.csv]

Input formats
  flows.csv   column `date` (business days) plus one column per series, net flow
              in millions of USD (positive = net demand for foreign exchange).
  market.csv  column `date` plus bid_usdidr, ask_usdidr, bid_ndf1m, ask_ndf1m,
              yield_sbn_10year, dxy, jci_index, flows_nr_eq (optional).

Design (Sections 3.1-3.5 of the paper)
  * Training starts at a series' first report: leading zeros are dropped when
    there are at least 250 of them (a category that entered the framework late).
  * 250 one-day-ahead test origins, preceded by a 60-origin validation block.
    Every model is re-fitted at every origin on all data before that day.
  * Pool of 116 engineered features (Appendix D), redundancy-aware mRMR selection
    of k = 25 (Spearman relevance minus mean Spearman redundancy, beta = 1).
  * Learners: random forest (3 seeds, averaged), LightGBM, XGBoost, each tuned per
    series over a 4-configuration grid on the validation block. Squared loss as
    designed; absolute and Huber loss as the variants of Section 4.1.
  * Benchmarks: random walk, drift, 90-day mean, seasonal naive (5 days), Croston
    SBA, ARIMA, damped ETS, Theta, Prophet (if installed), ridge regression on the
    same features with extrapolation guards, and a linear median regression.
    The in-house seasonal-decomposition baseline of Table 4 is not included.
  * Ablations: no mRMR (beta = 0), production configuration instead of tuning,
    one fit per 30 origins, k in {12, 40, all}, market data as changes or levels,
    training from 2022 only. Feature-count, market and window arms are re-fitted
    every 5 origins and compared with k = 25 on the same schedule.
  * Accuracy: MASE, scaled by the mean absolute first difference of the training
    sample from the first report. Inference on series-date units: paired Wilcoxon,
    circular block bootstrap (5-day blocks, 2,000 draws), TOST at +-2 per cent,
    Holm correction, Diebold-Mariano with the Harvey-Leybourne-Newbold correction,
    and a 90 per cent model confidence set (T-max statistic).

Library versions used for the paper are listed in Appendix F. Exact numbers also
depend on thread count (ARIMA order selection), so pin one thread per process.
"""
import argparse, os, warnings
import numpy as np, pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import RidgeCV, QuantileRegressor
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.forecasting.theta import ThetaModel
from statsmodels.tsa.stattools import kpss
warnings.filterwarnings('ignore')
os.environ.setdefault('OMP_NUM_THREADS', '1')

NROLL, NVAL, K, WEEK, BLOCK30, MIN_LEAD_ZEROS = 250, 60, 25, 5, 30, 250
GRID = {'RandomForest': [dict(n_estimators=100, max_depth=10), dict(n_estimators=300, max_depth=10),
                         dict(n_estimators=300, max_depth=None), dict(n_estimators=100, max_depth=4)],
        'LightGBM': [dict(n_estimators=100, learning_rate=0.05, max_depth=5), dict(n_estimators=400, learning_rate=0.02, max_depth=5),
                     dict(n_estimators=100, learning_rate=0.10, max_depth=3), dict(n_estimators=400, learning_rate=0.05, max_depth=8)],
        'XGBoost': [dict(n_estimators=100, max_depth=5, learning_rate=0.05), dict(n_estimators=400, max_depth=5, learning_rate=0.02),
                    dict(n_estimators=100, max_depth=3, learning_rate=0.10), dict(n_estimators=400, max_depth=8, learning_rate=0.05)]}
RF_SEEDS = (42, 1, 2)


# ----------------------------------------------------------------------------- features
def features(dates, y, market=None):
    """The 116-candidate pool of Appendix D. Every feature uses data up to t-1 only."""
    d = pd.DatetimeIndex(dates); v = pd.Series(np.asarray(y, float)); s1 = v.shift(1); F = {}
    dow, mon = pd.Series(d.dayofweek, dtype=float), pd.Series(d.month, dtype=float)
    F.update(day_of_week=dow, month=mon, week_of_year=pd.Series(d.isocalendar().week.values, dtype=float),
             day_of_week_sin=np.sin(2 * np.pi * dow / 5), day_of_week_cos=np.cos(2 * np.pi * dow / 5),
             month_sin=np.sin(2 * np.pi * mon / 12), month_cos=np.cos(2 * np.pi * mon / 12), is_weekend=(dow >= 5) * 1.0)
    for L in list(range(1, 16)) + [20, 25, 30]:
        F[f'lag_{L}'] = v.shift(L)
    for w in (5, 10, 15, 20, 25, 30, 60, 120):
        r = s1.rolling(w)
        F[f'rolling_mean_{w}'], F[f'rolling_std_{w}'], F[f'rolling_min_{w}'], F[f'rolling_max_{w}'] = r.mean(), r.std(), r.min(), r.max()
    for sp in (5, 30):
        F[f'ewm_{sp}'], F[f'ewm_std_{sp}'] = s1.ewm(span=sp).mean(), s1.ewm(span=sp).std()
    F['value_diff_1'] = s1 - v.shift(2)
    F['value_pct_change_1'] = v.diff().shift(1) / (v.shift(2).fillna(0).abs() + 1e-8)
    for p in (5, 30):
        F[f'value_diff_{p}'] = s1 - v.shift(p + 1)
        F[f'value_pct_change_{p}'] = (s1 - v.shift(p + 1)) / (v.shift(p + 1).fillna(0).abs() + 1e-8)
    for w in (5, 15, 30):
        F[f'volatility_{w}'] = s1.rolling(w).std() / (s1.rolling(w).mean().fillna(0).abs() + 1e-8)
    F['volatility_ratio_5_30'] = F['volatility_5'] / (F['volatility_30'] + 1e-8)
    F['is_high_volatility_regime'] = (F['volatility_15'].shift(1) > F['volatility_15'].shift(1).rolling(60, min_periods=1).median()) * 1.0
    for w in (30, 60):
        lo, hi = s1.rolling(w, min_periods=1).min(), s1.rolling(w, min_periods=1).max()
        F[f'price_position_{w}'] = (s1 - lo) / (hi - lo + 1e-8)
    ret = s1.diff() / (v.shift(2).fillna(0).abs() + 1e-8)
    for w in (15, 30):
        dn, up = ret.clip(upper=0).rolling(w, min_periods=1).std(), ret.clip(lower=0).rolling(w, min_periods=1).std()
        F[f'downside_volatility_{w}'], F[f'upside_volatility_{w}'], F[f'volatility_skew_{w}'] = dn, up, dn / (up + 1e-8)
    ch = v.diff().shift(1)
    F['max_change_15d'], F['min_change_15d'] = ch.rolling(15, min_periods=1).max(), ch.rolling(15, min_periods=1).min()
    F['change_range_15d'] = F['max_change_15d'] - F['min_change_15d']
    for w in (15, 30):
        z = (s1 - s1.rolling(w, min_periods=1).mean()) / (s1.rolling(w, min_periods=1).std() + 1e-8)
        F[f'z_score_{w}'], F[f'is_extreme_high_{w}'], F[f'is_extreme_low_{w}'] = z, (z > 2) * 1.0, (z < -2) * 1.0
    typ, sd = ch.abs().rolling(15, min_periods=1).mean(), ch.rolling(15, min_periods=1).std()
    F['jump_size'] = s1.diff().abs() / (typ + 1e-8)
    F['is_jump'] = (s1.diff().abs() > typ + 2 * sd) * 1.0
    last = pd.Series(np.where(F['is_jump'] == 1, np.arange(len(v)), np.nan)).shift(1).ffill()
    F['days_since_jump'] = (np.arange(len(v)) - last.fillna(0)).clip(upper=120)
    dl = s1.diff()
    F['rsi_15'] = 100 - 100 / (1 + dl.clip(lower=0).rolling(15, min_periods=1).mean() / ((-dl.clip(upper=0)).rolling(15, min_periods=1).mean() + 1e-8))
    F['macd'] = s1.ewm(span=10, adjust=False).mean() - s1.ewm(span=25, adjust=False).mean()
    F['macd_signal'] = F['macd'].shift(1).ewm(span=10, adjust=False).mean()
    F['macd_histogram'] = F['macd'] - F['macd_signal']
    m20, s20 = s1.rolling(20).mean(), s1.rolling(20).std()
    F.update(bb_upper_20=m20 + 2 * s20, bb_lower_20=m20 - 2 * s20, bb_middle_20=m20, bb_width_20=4 * s20 / (m20 + 1e-8),
             bb_percent_20=(s1 - m20 + 2 * s20) / (4 * s20 + 1e-8))
    ti = pd.Series(np.busday_count(np.datetime64('2000-01-03'), d.values.astype('datetime64[D]')), dtype=float)
    for name, per in (('weekly', 5), ('monthly', 20), ('quarterly', 60)):
        F[f'fourier_{name}_sin'], F[f'fourier_{name}_cos'] = np.sin(2 * np.pi * ti / per), np.cos(2 * np.pi * ti / per)
    me = pd.Series([(pd.Period(x, 'M').end_time.date() - x.date()).days for x in d], dtype=float)
    qe = pd.Series([(pd.Period(x, 'Q').end_time.date() - x.date()).days for x in d], dtype=float)
    F.update(days_until_month_end=me, days_until_quarter_end=qe, is_near_month_end=(me <= 5) * 1.0, is_near_quarter_end=(qe <= 10) * 1.0)
    for a, b in (('lag_1', 'day_of_week'), ('lag_5', 'day_of_week'), ('rolling_mean_5', 'month'), ('rolling_mean_30', 'is_weekend')):
        F[f'{a}_x_{b}'] = F[a] * F[b]
    for name, x in (market or {}).items():        # 15 lags and a 5-day mean per market variable
        x = pd.Series(np.asarray(x, float))
        for L in range(1, 16):
            F[f'ext_{name}_lag_{L}'] = x.shift(L)
        F[f'ext_{name}_rolling_mean_5'] = x.shift(1).rolling(5).mean()
    X = pd.DataFrame({k: pd.Series(np.asarray(c, float)) for k, c in F.items()}).replace([np.inf, -np.inf], np.nan)
    return X.ffill().bfill().fillna(0.0)


def market_frames(mk, dates):
    """Market data aligned to the flow dates: levels as given, and daily changes of mid quotes."""
    m = mk.set_index('date').reindex(pd.DatetimeIndex(dates)).ffill().bfill()
    spot, ndf = (m.bid_usdidr + m.ask_usdidr) / 2, (m.bid_ndf1m + m.ask_ndf1m) / 2
    chg = dict(usdidr_mid_ret=np.log(spot).diff(), ndf1m_mid_ret=np.log(ndf).diff(), yield10y_chg=m.yield_sbn_10year.diff(),
               dxy_ret=np.log(m.dxy).diff(), jci_ret=np.log(m.jci_index).diff(), flows_nr_eq=m.flows_nr_eq)
    return {c: m[c].values for c in m.columns}, {k: s.fillna(0).values for k, s in chg.items()}


def mrmr(X, y, k, beta=1.0):
    """Greedy mRMR in correlation form on the training rows only (Section 3.3)."""
    if k == 'all':
        return list(X.columns)
    rel = X.corrwith(pd.Series(y, index=X.index), method='spearman').abs().fillna(0).sort_values(ascending=False)
    if beta == 0:
        return list(rel.index[:k])
    cand = list(rel.index[:max(3 * k, 40)])
    R = X[cand].corr(method='spearman').abs().fillna(0)
    picked = [cand[0]]
    while len(picked) < min(k, len(cand)):
        rest = [c for c in cand if c not in picked]
        picked.append(max(rest, key=lambda c: rel[c] - beta * R.loc[c, picked].mean()))
    return picked


# ----------------------------------------------------------------------------- models
def learner(name, cfg, seed=42, loss='squared', y_scale=1.0):
    if name == 'RandomForest':
        return RandomForestRegressor(random_state=seed, n_jobs=1, **cfg)
    if name == 'LightGBM':
        obj = {'squared': {}, 'absolute': dict(objective='l1'), 'huber': dict(objective='huber', alpha=1.345 * y_scale)}[loss]
        return LGBMRegressor(random_state=42, verbose=-1, n_jobs=1, **cfg, **obj)
    obj = {'squared': {}, 'absolute': dict(objective='reg:absoluteerror')}[loss]
    return XGBRegressor(random_state=42, verbosity=0, n_jobs=1, **cfg, **obj)


def linear(Xl, yl, xt, median=False):
    """Ridge (or median regression) with the two guards of Section 3.4: drop near-constant
    columns and clip the forecast row to the training range, since a linear model extrapolates."""
    sd = Xl.std(0); keep = sd > 1e-8 * (np.abs(Xl).max(0) + 1)
    Xl, xt, sd = Xl[:, keep], np.clip(xt[:, keep], Xl[:, keep].min(0), Xl[:, keep].max(0)), sd[keep]
    mu = Xl.mean(0); Z, z = (Xl - mu) / sd, (xt - mu) / sd
    if not median:
        return float(RidgeCV(alphas=np.logspace(-3, 3, 13)).fit(Z, yl).predict(z)[0])
    sy = float(np.std(yl)) or 1.0
    for a in (0.0, 1e-6, 1e-4):                      # tiny penalty only if the LP fails
        try:
            return float(QuantileRegressor(quantile=0.5, alpha=a, solver='highs').fit(Z, yl / sy).predict(z)[0]) * sy
        except Exception:
            continue
    return float(np.median(yl))


def arima(y):
    """Differencing by successive KPSS tests, p and q up to 3 by AIC on the last 750 points,
    then the chosen order is estimated on the full training sample."""
    s, dd = np.asarray(y[-750:], float), 0
    while dd < 2 and kpss(np.diff(s, dd) if dd else s, regression='c', nlags='auto')[1] < 0.05:
        dd += 1
    best = min(((p, dd, q) for p in range(4) for q in range(4)),
               key=lambda o: SARIMAX(s, order=o, enforce_stationarity=False, enforce_invertibility=False).fit(disp=False).aic)
    return float(SARIMAX(y, order=best, enforce_stationarity=False, enforce_invertibility=False).fit(disp=False).forecast(1)[0])


def croston_sba(y, alpha=0.1):
    nz = np.nonzero(y)[0]
    if len(nz) < 2:
        return float(np.mean(y))
    z, p, prev = y[nz[0]], nz[0] + 1, nz[0]
    for i in nz[1:]:
        z, p, prev = z + alpha * (y[i] - z), p + alpha * (i - prev - p), i
    return float(z / p * (1 - alpha / 2))


def benchmark(name, d, y):
    if name == 'Naive':         return y[-1]
    if name == 'NaiveDrift':    return y[-1] + (y[-1] - y[0]) / (len(y) - 1)
    if name == 'NaiveMean':     return y[-90:].mean()
    if name == 'SeasonalNaive': return y[-WEEK]
    if name == 'Croston':       return croston_sba(y)
    if name == 'ARIMA':         return arima(y)
    if name == 'ETS':
        return float(ExponentialSmoothing(y, trend='add', damped_trend=True, initialization_method='estimated').fit().forecast(1)[0])
    if name == 'Theta':
        return float(np.asarray(ThetaModel(y, period=WEEK, deseasonalize=False).fit().forecast(1)).ravel()[0])
    if name == 'Prophet':
        from prophet import Prophet
        m = Prophet().fit(pd.DataFrame({'ds': d, 'y': y}))
        return float(m.predict(pd.DataFrame({'ds': [pd.bdate_range(d[-1], periods=2)[-1]]})).yhat[0])


# ----------------------------------------------------------------------------- one series
class Series:
    def __init__(self, name, dates, y, market=None, nroll=NROLL, nval=NVAL):
        y = np.asarray(y, float); nz = np.nonzero(y)[0]
        s0 = int(nz[0]) if len(nz) and nz[0] >= MIN_LEAD_ZEROS else 0       # first report
        self.name, self.d, self.y = name, pd.DatetimeIndex(dates)[s0:], y[s0:]
        self.test0 = len(self.y) - nroll; self.val0 = self.test0 - nval
        self.scale = np.mean(np.abs(np.diff(self.y[:self.test0])))         # MASE denominator
        self.F = {'none': features(self.d, self.y)}
        if market is not None:
            lv, ch = market
            self.F['levels'] = features(self.d, self.y, {k: v[s0:] for k, v in lv.items()})
            self.F['changes'] = features(self.d, self.y, {k: v[s0:] for k, v in ch.items()})
        self._sel = {}

    def select(self, fk, t, k, beta=1.0, start=0):
        key = (fk, t, k, beta, start)
        if key not in self._sel:
            self._sel[key] = mrmr(self.F[fk].iloc[start:t], self.y[start:t], k, beta)
        return self._sel[key]

    def run_learner(self, name, cfg, origins, fk='none', k=K, beta=1.0, every=1, start=0, seed=42, loss='squared'):
        out, m, cols = [], None, None
        for i, t in enumerate(origins):
            if i % every == 0:
                cols = self.select(fk, t, k, beta, start)
                m = learner(name, cfg, seed, loss, self.scale).fit(self.F[fk][cols].values[start:t], self.y[start:t])
            out.append(float(m.predict(self.F[fk][cols].values[t:t + 1])[0]))
        return np.array(out)

    def run_linear(self, origins, median=False):
        res = []
        for t in origins:
            X = self.F['none'][self.select('none', t, K)].values
            res.append(linear(X[:t], self.y[:t], X[t:t + 1], median))
        return np.array(res)

    def run_benchmark(self, name, origins):
        res = []
        for t in origins:
            try:
                res.append(float(benchmark(name, self.d[:t], self.y[:t])))
            except Exception:
                res.append(np.nan)
        return np.array(res)


def forecast_series(S, quick=False, with_prophet=False):
    """All methods and arms for one series. Returns {(method, arm): forecasts on the test block}."""
    val, test = list(range(S.val0, S.test0)), list(range(S.test0, len(S.y)))
    mase = lambda p, idx: np.mean(np.abs(S.y[idx] - p)) / S.scale
    out, tuned = {}, {}
    for name in GRID:                                        # tuning on the validation block
        scores = [mase(S.run_learner(name, c, val), val) for c in GRID[name]]
        tuned[name] = GRID[name][int(np.nanargmin(scores))]
    for name, cfg in tuned.items():
        seeds = RF_SEEDS if name == 'RandomForest' else (42,)
        def run(c=cfg, **kw):
            return np.mean([S.run_learner(name, c, test, seed=s, **kw) for s in seeds], axis=0)
        out[name, 'main'] = run()
        out[name, 'no_mrmr'] = run(beta=0.0)
        out[name, 'no_tuning'] = run(GRID[name][0])
        out[name, 'no_refit'] = run(every=BLOCK30)
        if quick:
            continue
        for k in (12, 25, 40, 'all'):
            out[name, f'k{k}'] = run(k=k, every=WEEK)
        for fk in set(S.F) - {'none'}:
            out[name, f'market_{fk}'] = run(fk=fk, every=WEEK)
        start = int(np.argmax(S.d >= pd.Timestamp('2022-01-01')))
        out[name, 'from_2022'] = run(every=WEEK, start=start)
    for name, loss in (('LightGBM', 'absolute'), ('LightGBM', 'huber'), ('XGBoost', 'absolute')):
        out[name, f'loss_{loss}'] = S.run_learner(name, tuned[name], test, loss=loss)
    out['Ridge', 'main'] = S.run_linear(test)
    out['MedianRegression', 'main'] = S.run_linear(test, median=True)
    bench = ['Naive', 'NaiveDrift', 'NaiveMean', 'SeasonalNaive', 'Croston', 'ARIMA', 'ETS', 'Theta']
    for b in bench + (['Prophet'] if with_prophet else []):
        out[b, 'main'] = S.run_benchmark(b, test)
    return out, S.y[test], S.d[test], S.scale, tuned


# ----------------------------------------------------------------------------- SHAP (Section 4.6, Appendix B)
FAMILIES = [('Market', lambda c: c.startswith('ext_')), ('Interaction', lambda c: '_x_' in c),
            ('Lag', lambda c: c.startswith('lag_')), ('Rolling statistics', lambda c: c.startswith('rolling_')),
            ('Exponentially weighted mean', lambda c: c.startswith('ewm_')),
            ('Difference and percentage change', lambda c: c.startswith('value_')),
            ('Volatility and range', lambda c: any(s in c for s in ('volatil', 'price_position', 'max_change', 'min_change', 'change_range'))),
            ('Extreme value and jump', lambda c: any(s in c for s in ('z_score', 'is_extreme', 'jump'))),
            ('Technical indicator', lambda c: c.startswith(('rsi', 'bb_', 'macd'))),
            ('Calendar and Fourier', lambda c: True)]
family = lambda c: next(n for n, f in FAMILIES if f(c))


def label(c):
    """Readable feature names for the beeswarm."""
    if '_x_' in c:
        a, b = c.split('_x_', 1); return f'{label(a)} x {b.replace("_", " ")}'
    if c.startswith('ext_'):
        v, _, L = c[4:].partition('_lag_')
        if L:
            return f'{v.replace("_", " ")}, lag {L}'
        v, _, w = c[4:].rpartition('_rolling_mean_'); return f'{v.replace("_", " ")}, {w}d mean'
    if c.startswith('lag_'):          return f'Own lag {c[4:]}'
    if c.startswith('rolling_mean_'): return f'Own mean, {c.split("_")[-1]}d'
    if c.startswith('ewm_'):          return f'Own EWM, span {c.split("_")[-1]}'
    return c.replace('_', ' ')


def beeswarm(cols, Xs, sv, title, path, n=14):
    """One dot per training day and feature, placed by its SHAP value and coloured by the rank
    of the feature value (blue low, red high). Market variables are labelled in orange."""
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    order = np.argsort(-np.abs(sv).mean(0))[:n]
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    for row, i in enumerate(order):
        xv = Xs.iloc[:, i].values.astype(float)
        rank = np.argsort(np.argsort(xv)) / max(1, len(xv) - 1)
        jitter = (np.random.RandomState(row).rand(len(xv)) - .5) * .34
        ax.scatter(sv[:, i], len(order) - row + jitter, c=rank, cmap='coolwarm', s=5, alpha=.7, linewidths=0)
    ax.set_yticks([len(order) - r for r in range(len(order))])
    ax.set_yticklabels([label(cols[i]) for i in order], fontsize=7.4)
    for r, i in enumerate(order):
        if cols[i].startswith('ext_'):
            ax.get_yticklabels()[r].set_color('#c4713d')
    ax.axvline(0, color='#888', lw=.7); ax.grid(axis='x', color='#d8d8d8', lw=.6); ax.set_axisbelow(True)
    ax.set_xlabel('SHAP value (effect on the forecast, millions of USD)'); ax.set_title(title, fontsize=9, loc='left')
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    fig.tight_layout(); fig.savefig(path, dpi=200); plt.close(fig)


def shap_series(S, tuned, outdir='beeswarm'):
    """SHAP on the final models: random forest (first seed) and LightGBM with their tuned
    configurations, fitted on the whole sample from the first report with mRMR k = 25, and
    explained on the last 300 training days. Done for each feature pool (no market data,
    market data as changes, as levels). Returns {pool: {learner: {family: share in %}}}."""
    import shap
    res, N = {}, len(S.y)
    for fk in S.F:
        cols = S.select(fk, N, K)
        X = S.F[fk][cols]; Xs = X.iloc[-300:]
        res[fk] = {'n_market': int(sum(c.startswith('ext_') for c in cols))}
        for name in ('RandomForest', 'LightGBM'):
            m = learner(name, tuned[name], RF_SEEDS[0] if name == 'RandomForest' else 42).fit(X.values, S.y)
            sv = np.asarray(shap.TreeExplainer(m).shap_values(Xs, check_additivity=False))
            imp = np.abs(sv).mean(0); tot = imp.sum() + 1e-12; fam = {}
            for i, c in enumerate(cols):
                fam[family(c)] = fam.get(family(c), 0.0) + 100 * imp[i] / tot
            res[fk][name] = fam
            # Appendix B draws the random forest with market data as changes (or without market data).
            if name == 'RandomForest' and fk == ('changes' if 'changes' in S.F else 'none'):
                n_ext = res[fk]['n_market']
                beeswarm(cols, Xs, sv, f'{S.name}: {n_ext} market features of {K}, '
                         f'{fam.get("Market", 0):.1f}% of total |SHAP|', os.path.join(outdir, f'{S.name}.png'))
    return res


def shap_summary(SH, effect=None, group_of=lambda s: s[0]):
    """Figure 9 and the RQ4 contrast: mean family shares, market share by counterparty group,
    agreement of the two learners, and whether the market share predicts the market-data gain."""
    for fk in next(iter(SH.values())):
        print(f'\nSHAP family shares (%), pool "{fk}", mean over series:')
        tab = {nm: pd.DataFrame({s: v[fk][nm] for s, v in SH.items()}).fillna(0).mean(1) for nm in ('RandomForest', 'LightGBM')}
        print(pd.DataFrame(tab).sort_values('RandomForest', ascending=False).round(1).to_string())
        mk = pd.DataFrame({s: {nm: v[fk][nm].get('Market', 0.0) for nm in ('RandomForest', 'LightGBM')} for s, v in SH.items()}).T
        if mk.values.sum() > 0:
            print('Market share by group (%):\n', mk.groupby(mk.index.map(group_of)).mean().round(1).to_string())
            r, p = stats.spearmanr(mk.RandomForest, mk.LightGBM)
            print(f'Rank correlation of market shares, random forest vs LightGBM: {r:.2f} (p = {p:.3f})')
            if effect is not None and fk == 'changes':
                r, p = stats.spearmanr(mk.RandomForest.reindex(effect.index), effect.values)
                print(f'Market share vs gain from market data as changes: {r:.2f} (p = {p:.2f})')


# ----------------------------------------------------------------------------- inference
def block_bootstrap(a, b, dates, B=2000, block=5, seed=0):
    """Percentage change in mean MASE of b against a, with a circular block bootstrap over
    dates that keeps all series of one date together (Section 3.5)."""
    df = pd.DataFrame({'a': a, 'b': b, 'd': dates}).groupby('d')[['a', 'b']].agg(['sum', 'count'])
    sa, sb, n = df[('a', 'sum')].values, df[('b', 'sum')].values, df[('a', 'count')].values
    T, rng = len(sa), np.random.default_rng(seed)
    starts = rng.integers(0, T, size=(B, int(np.ceil(T / block))))
    idx = ((starts[:, :, None] + np.arange(block)) % T).reshape(B, -1)[:, :T]
    boot = 100 * (sb[idx].sum(1) / n[idx].sum(1)) / (sa[idx].sum(1) / n[idx].sum(1)) - 100
    return 100 * (b.mean() / a.mean() - 1), np.percentile(boot, [2.5, 97.5]), np.percentile(boot, [5, 95])


def compare(a, b, dates, margin=2.0):
    delta, ci95, ci90 = block_bootstrap(a, b, dates)
    p = stats.wilcoxon(a, b).pvalue
    verdict = 'equivalent' if -margin < ci90[0] and ci90[1] < margin else ('different' if p < 0.05 else 'inconclusive')
    return dict(delta=delta, lo95=ci95[0], hi95=ci95[1], p=p, verdict=verdict)


def holm(ps):
    order, m, adj, run = np.argsort(ps), len(ps), np.empty(len(ps)), 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, (m - r) * ps[i])); adj[i] = run
    return adj


def dm_hln(e1, e2, h=1):
    """Diebold-Mariano on absolute errors with the Harvey-Leybourne-Newbold correction."""
    dd = np.abs(e1) - np.abs(e2); n = len(dd)
    stat = dd.mean() / np.sqrt(np.var(dd, ddof=0) / n) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    return stat, 2 * stats.t.sf(abs(stat), n - 1)


def mcs(L, alpha=0.10, B=2000, block=5, seed=0):
    """Model confidence set of Hansen, Lunde and Nason (2011), T-max statistic. L: dates x models."""
    rng, models, pvals, pmax = np.random.default_rng(seed), list(L.columns), {}, 0.0
    T = len(L); starts = rng.integers(0, T, size=(B, int(np.ceil(T / block))))
    idx = ((starts[:, :, None] + np.arange(block)) % T).reshape(B, -1)[:, :T]
    while len(models) > 1:
        X = L[models].values; d = X - X.mean(1, keepdims=True); dbar = d.mean(0)
        boot = d[idx].mean(1) - dbar; se = boot.std(0)
        t = dbar / se; tb = (boot / se).max(1)
        pmax = max(pmax, float((tb >= t.max()).mean()))
        worst = models[int(np.argmax(t))]; pvals[worst] = pmax
        if pmax >= alpha:
            break
        models.remove(worst)
    for m in models:
        pvals.setdefault(m, 1.0)
    return models, pvals


# ----------------------------------------------------------------------------- driver
def demo_data(n=1600, n_series=3, seed=0):
    """Synthetic flows with persistence, weekday effects, zeros and rare large settlements."""
    rng, d = np.random.default_rng(seed), pd.bdate_range('2019-01-01', periods=n)
    cols = {}
    for j in range(n_series):
        e, x = rng.standard_t(3, n) * 20, np.zeros(n)
        for t in range(1, n):
            x[t] = 0.6 * x[t - 1] + e[t]
        x += 15 * (d.dayofweek == 4) + rng.binomial(1, 0.02, n) * rng.normal(0, 400, n)
        x[rng.random(n) < 0.2 * j] = 0                       # later series are more often zero
        cols[f'S{j + 1}'] = np.round(x)
    return pd.DataFrame({'date': d, **cols})


def demo_market(dates, seed=1):
    """Synthetic market data in the layout of market.csv: random-walk prices and an equity flow."""
    rng, n = np.random.default_rng(seed), len(dates)
    walk = lambda s0, sd: s0 * np.exp(np.cumsum(rng.normal(0, sd, n)))
    spot, ndf = walk(14000, .004), walk(14050, .005)
    return pd.DataFrame({'date': pd.DatetimeIndex(dates), 'bid_usdidr': spot - 5, 'ask_usdidr': spot + 5,
                         'bid_ndf1m': ndf - 8, 'ask_ndf1m': ndf + 8, 'yield_sbn_10year': 6.5 + np.cumsum(rng.normal(0, .02, n)),
                         'dxy': walk(95, .003), 'jci_index': walk(6000, .008), 'flows_nr_eq': rng.normal(0, 50, n)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--flows'); ap.add_argument('--market')
    ap.add_argument('--demo', action='store_true', help='synthetic data instead of --flows')
    ap.add_argument('--quick', action='store_true', help='30 test and 10 validation origins, main arms only')
    ap.add_argument('--prophet', action='store_true', help='include Prophet (slow)')
    ap.add_argument('--no-shap', action='store_true', help='skip SHAP and the beeswarm plots')
    ap.add_argument('--groups', default='', help='counterparty group per series prefix, e.g. "A=Corporate,B=Individual,C=Non-resident"')
    a = ap.parse_args()
    flows = demo_data() if a.demo else pd.read_csv(a.flows, parse_dates=['date'])
    nroll, nval = (30, 10) if a.quick else (NROLL, NVAL)
    if a.market:
        mk = market_frames(pd.read_csv(a.market, parse_dates=['date']), flows.date)
    else:
        mk = market_frames(demo_market(flows.date), flows.date) if a.demo else None
    rows, SH = [], {}
    for col in [c for c in flows.columns if c != 'date']:
        S = Series(col, flows.date, flows[col].values, mk, nroll, nval)
        out, actual, dates, scale, tuned = forecast_series(S, a.quick, a.prophet)
        if not a.no_shap:
            SH[col] = shap_series(S, tuned)
        for (m, arm), p in out.items():
            rows += [dict(series=col, date=dd, method=m, arm=arm, pred=pp, actual=aa, mase=abs(aa - pp) / scale)
                     for dd, pp, aa in zip(dates, p, actual)]
        print(f'{col}: done', flush=True)
    R = pd.DataFrame(rows); R.to_csv('forecasts.csv', index=False)

    # Units are series x date. Learner arms are pooled by averaging the three learners per unit.
    U = R.pivot_table(index=['series', 'date'], columns=['method', 'arm'], values='mase')
    main = U.xs('main', level='arm', axis=1).dropna(axis=1)
    pred = R[R.arm == 'main'].pivot_table(index=['series', 'date'], columns='method', values='pred')[main.columns]
    act = R[R.arm == 'main'].groupby(['series', 'date']).actual.first()
    scale = pd.Series({c: Series(c, flows.date, flows[c].values, None, nroll, nval).scale for c in main.index.levels[0]})
    main['Median of all methods'] = (pred.median(1) - act).abs() / scale.reindex(act.index.get_level_values(0)).values
    rank = main.mean().sort_values(); lead = rank.index[0]; dts = main.index.get_level_values('date')
    print('\nMean MASE (Table 5):\n', rank.round(3).to_string())
    res = [dict(method=m, **compare(main[lead].values, main[m].values, dts)) for m in rank.index[1:]]
    for r, ph in zip(res, holm([r['p'] for r in res])):
        r['p_holm'] = ph
    print(f'\nAgainst the leader ({lead}):\n', pd.DataFrame(res).round(4).to_string(index=False))
    kept, p = mcs(main.drop(columns='Median of all methods').groupby(level='date').mean())
    print('\n90% model confidence set:', kept)
    for m in [c for c in rank.index if c != lead][:3]:
        nsig = sum(dm_hln(main[lead].xs(s).values, main[m].xs(s).values)[1] < 0.05 for s in main.index.levels[0])
        print(f'DM-HLN {lead} vs {m}: significant on {nsig} series')
    pool = lambda arm: U.xs(arm, level='arm', axis=1)[[c for c in GRID if (c, arm) in U.columns]].mean(1)
    print('\nComponents (Table 7), change in mean MASE when removed:')
    for arm in ('no_mrmr', 'no_tuning', 'no_refit'):
        r = compare(pool('main').values, pool(arm).values, dts); print(f"  {arm:10s} {r['delta']:+.1f}% [{r['lo95']:.1f}, {r['hi95']:.1f}] {r['verdict']}")
    if not a.quick:
        for arm in ('k12', 'k40', 'kall', 'market_changes', 'market_levels', 'from_2022'):
            if (('LightGBM', arm) in U.columns):
                r = compare(pool('k25').values, pool(arm).values, dts); print(f"  {arm:14s} vs k25 {r['delta']:+.1f}% {r['verdict']}")
    if SH:
        gmap = dict(g.split('=') for g in a.groups.split(',') if '=' in g)
        effect = None
        if ('LightGBM', 'market_changes') in U.columns:
            effect = (pool('market_changes').groupby(level='series').mean() / pool('k25').groupby(level='series').mean() - 1) * 100
        shap_summary(SH, effect, lambda s: gmap.get(s[0], s[0]))
        print('Beeswarm plots written to ./beeswarm/')
    print('\nTraining loss (Section 4.1):')
    for m, arm, ref in (('LightGBM', 'loss_absolute', 'LightGBM'), ('LightGBM', 'loss_huber', 'LightGBM'),
                        ('XGBoost', 'loss_absolute', 'XGBoost'), ('MedianRegression', 'main', 'Ridge')):
        r = compare(U[ref, 'main'].values, U[m, arm].values, dts)
        print(f"  {m} {arm} vs {ref}: {r['delta']:+.1f}% [{r['lo95']:.1f}, {r['hi95']:.1f}]")


if __name__ == '__main__':
    main()
