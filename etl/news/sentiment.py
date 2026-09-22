"""Tahap penilaian sentimen - terpisah dari pengumpulan.

Pemisahan ini disengaja. Korpus dikumpulkan sekali (mahal, lambat, butuh
jaringan); penilaian bisa diulang berkali-kali (murah, lokal, tanpa jaringan)
setiap kali metodenya berubah. Versi lama menyatukan keduanya, sehingga satu
perbaikan logika label berarti menarik ulang seluruh berita.

Penilaian bisa DILANJUTKAN: yang sudah dinilai oleh scorer yang sama dilewati.
Proses yang mati di tengah tinggal dijalankan lagi.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .store import connect, unscored, write_scores

# Nama scorer ikut disimpan di tiap baris. Naikkan angkanya kalau cara
# menghitung polaritas berubah - baris lama otomatis dinilai ulang karena
# nama scorer-nya tidak lagi cocok.
FINBERT_SCORER = 'finbert-v3'
BATCH = 64


def _polarity_from_dist(dist) -> tuple:
    """P(positif) - P(negatif), dari distribusi penuh tiga kelas.

    Alasannya sama dengan di helper/tradingeconomics_scraper.py: argmax
    membuang derajat. Judul 49% positif / 48% negatif dan judul 95% positif
    sama-sama keluar 'positive', padahal yang pertama praktis tidak berarah.
    """
    if dist and isinstance(dist[0], list):
        dist = dist[0]
    p = {str(d['label']).strip().lower(): float(d['score']) for d in dist}
    pos = p.get('positive', p.get('label_0', 0.0))
    neg = p.get('negative', p.get('label_2', 0.0))
    neu = p.get('neutral', p.get('label_1', 0.0))
    return pos - neg, pos, neg, neu


def load_pipeline(model: str = 'ProsusAI/finbert'):
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              pipeline)
    tok = AutoTokenizer.from_pretrained(model)
    mdl = AutoModelForSequenceClassification.from_pretrained(model)
    return pipeline('sentiment-analysis', model=mdl, tokenizer=tok,
                    top_k=None, truncation=True, max_length=128)


def score_corpus(db_path: Path | str, limit: Optional[int] = None,
                 scorer: str = FINBERT_SCORER, batch: int = BATCH) -> dict:
    """Nilai artikel yang belum punya skor dari `scorer` ini.

    CATATAN BIAYA: FinBERT di CPU kira-kira puluhan judul per detik. Korpus
    ratusan ribu artikel berarti hitungan jam, bukan menit. Jalankan di layar
    terpisah (tmux/screen) di VPS, bukan lewat tombol di dashboard.
    """
    pipe = load_pipeline()
    total = {'dinilai': 0, 'gagal': 0}
    with connect(db_path) as con:
        todo = unscored(con, scorer, limit)
        if todo.empty:
            return {'dinilai': 0, 'gagal': 0, 'catatan': 'semua sudah dinilai'}
        # Baris tanpa judul tidak bisa dinilai FinBERT - itu baris nada
        # agregat yang sudah punya polarity-nya sendiri. Dilewati, bukan
        # dianggap gagal.
        todo = todo[todo['title'].notna() & (todo['title'].str.len() > 0)]
        for i in range(0, len(todo), batch):
            chunk = todo.iloc[i:i + batch]
            try:
                out = pipe(list(chunk['title'].astype(str)))
            except Exception as e:
                total['gagal'] += len(chunk)
                print(f'  batch {i}: GAGAL {type(e).__name__}: {e}')
                continue
            rows = []
            for uid, dist in zip(chunk['uid'], out):
                pol, pp, pn, pu = _polarity_from_dist(dist)
                rows.append((uid, pol, pp, pn, pu))
            total['dinilai'] += write_scores(con, scorer, rows)
            if i % (batch * 20) == 0:
                con.commit()
                print(f'  {total["dinilai"]:,}/{len(todo):,} dinilai', flush=True)
    return total
