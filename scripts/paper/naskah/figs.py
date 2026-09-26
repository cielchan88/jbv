"""Gambar naskah, dibangun dari tables.json dan berkas hasil mentah.

    python scripts/paper/naskah/figs.py

Jalan berkas diatur jalan.py. Gambar yang bergantung data SELALU dibangun
ulang di sini - memakai ulang gambar dari run sebelumnya pernah membuat
angka di badan naskah tidak cocok dengan gambarnya.
"""
import json, os, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jalan import HASIL, TABLES, GAMBAR, siapkan

siapkan()
if not os.path.exists(TABLES):
    raise SystemExit(f'BERHENTI: {TABLES} belum ada. Jalankan buat_tables.py dulu.')
T = json.load(open(TABLES)); H = HASIL; F = GAMBAR
BLUE,ACC,GRID,MUTED='#3b6ea5','#c4713d','#d8d8d8','#5e6b76'
NICE={'Naive':'Random walk','NaiveMean':'Rolling mean','NaiveDrift':'RW w/ drift',
 'Croston':'Croston','SeasonalDecomp':'Seasonal decomp','ARIMA':'ARIMA','Prophet':'Prophet',
 'RandomForest':'Random forest','LightGBM':'LightGBM','XGBoost':'XGBoost'}
nice=lambda m: NICE.get(m,m)
PUR={'Ekspor':'Export','Impor':'Import','Investasi':'Investment','Repatriasi':'Repatriation',
 'Transaksi tanpa underlying':'No underlying','Remittance':'Remittance','Trading':'Trading',
 'Lainnya':'Other'}
LAB={d['leaf']:PUR.get(str(d['label']).split('. ',1)[-1],str(d['label']).split('. ',1)[-1])
     for d in T['desc']}
def simpan(fig,nama):
    fig.tight_layout(); fig.savefig(F+nama,dpi=200); plt.close(fig); print('  ',nama)

# ---------------------------------------------------------------- Gambar 1
KOL=['Export','Import','Investment','Repatriation','No underlying','Remittance','Trading','Other']
BARIS=[('A.2','Corporate'),('B','Individual'),('C','Non-resident')]
fig,ax=plt.subplots(figsize=(7.4,2.9))
ax.set_xlim(-.5,len(KOL)-.5); ax.set_ylim(-.5,len(BARIS)-.5); ax.invert_yaxis()
mean={d['leaf']:d['mean'] for d in T['desc']}
for i,(pre,nm) in enumerate(BARIS):
    for j,kol in enumerate(KOL):
        leaf=next((l for l in LAB if l.startswith(pre+'.') and LAB[l]==kol),None)
        if leaf is None:
            ax.add_patch(plt.Rectangle((j-.45,i-.42),.9,.84,fill=False,ec=GRID,ls='--',lw=.8)); continue
        m=mean[leaf]; warna=BLUE if m>0 else ACC
        ax.add_patch(plt.Rectangle((j-.45,i-.42),.9,.84,fc=warna,alpha=.16,ec=warna,lw=1.1))
        ax.text(j,i-.10,leaf,ha='center',va='center',fontsize=7.6,weight='bold',color=warna)
        ax.text(j,i+.18,f'{m:,.0f}',ha='center',va='center',fontsize=6.8,color=MUTED)
ax.set_xticks(range(len(KOL))); ax.set_xticklabels(KOL,fontsize=7.2,rotation=20,ha='right')
ax.set_yticks(range(len(BARIS))); ax.set_yticklabels([n for _,n in BARIS],fontsize=8)
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)
simpan(fig,'fig1_taxonomy.png')

# ---------------------------------------------------------------- Gambar 3
roll=pd.read_csv(H+'opt_rolling.csv')
g=roll.groupby(['leaf','model'])['mase'].mean().reset_index()
leafs=sorted(g.leaf.unique())
fig,ax=plt.subplots(figsize=(7.4,3.3))
for i,l in enumerate(leafs):
    s=g[g.leaf==l]
    ax.scatter(s.mase,[i]*len(s),s=16,c=GRID,ec='none',zorder=2)
    b=s.loc[s.mase.idxmin()]; ax.scatter(b.mase,i,s=30,c=ACC,zorder=4)
    rw=s[s.model=='Naive'].mase.iloc[0]
    ax.plot([rw,rw],[i-.28,i+.28],c=BLUE,lw=1.4,zorder=3)
ax.axvline(1,ls='--',c=MUTED,lw=.9)
ax.set_yticks(range(len(leafs)))
ax.set_yticklabels([f'{l}  {LAB[l]}' for l in leafs],fontsize=7)
ax.set_xlabel('MASE (mean over 30 one-day origins)',fontsize=8)
ax.set_xlim(0,max(3,g.mase.quantile(.97))); ax.grid(axis='x',color=GRID,lw=.6); ax.set_axisbelow(True)
ax.invert_yaxis()
simpan(fig,'fig3_leaf.png')

# ---------------------------------------------------------------- Gambar 4
cnt=pd.Series(T['best_per_leaf']).value_counts()
fig,ax=plt.subplots(figsize=(7.4,2.7))
ax.barh(range(len(cnt))[::-1],cnt.values,color=[ACC if i==0 else BLUE for i in range(len(cnt))],zorder=3)
ax.set_yticks(range(len(cnt))[::-1]); ax.set_yticklabels([nice(m) for m in cnt.index],fontsize=8)
for i,v in enumerate(cnt.values): ax.text(v+.06,len(cnt)-1-i,str(v),va='center',fontsize=8,color=MUTED)
ax.set_xlabel('number of series won (of 15)',fontsize=8)
ax.set_xlim(0,cnt.max()+.6); ax.grid(axis='x',color=GRID,lw=.6); ax.set_axisbelow(True)
simpan(fig,'fig4_winners.png')

# ---------------------------------------------------------------- Gambar 5
ab=pd.DataFrame(T['ablation']).sort_values('k')
fig,axes=plt.subplots(1,2,figsize=(7.4,2.6))
ax=axes[0]
ax.plot(ab.k,ab.mase,'o-',c=BLUE,lw=1.6,ms=5,label='mean')
ax.plot(ab.k,ab['median'],'s--',c=ACC,lw=1.4,ms=4,label='median')
ax.set_xlabel('features kept (k)',fontsize=8); ax.set_ylabel('MASE',fontsize=8)
ax.legend(fontsize=7,frameon=False); ax.grid(color=GRID,lw=.6); ax.set_axisbelow(True)
ax=axes[1]
ax.bar(ab.k.astype(str),ab['max'],color=BLUE,zorder=3)
ax.set_xlabel('features kept (k)',fontsize=8); ax.set_ylabel('worst scaled error',fontsize=8)
ax.grid(axis='y',color=GRID,lw=.6); ax.set_axisbelow(True)
simpan(fig,'fig5_kablation.png')

# ---------------------------------------------------------------- Gambar 6
E=pd.DataFrame(T['external_full'])
lbl=[f"{'univariate' if b==0 else 'mRMR'}\nk={k}" for b,k in zip(E.beta,E.k)]
x=np.arange(len(E)); w=.38
fig,axes=plt.subplots(1,2,figsize=(7.4,2.6))
ax=axes[0]
ax.bar(x-w/2,E.off,w,label='market off',color=BLUE,zorder=3)
ax.bar(x+w/2,E.on,w,label='market on',color=ACC,zorder=3)
ax.set_xticks(x); ax.set_xticklabels(lbl,fontsize=6.8); ax.set_ylabel('mean MASE',fontsize=8)
ax.legend(fontsize=7,frameon=False); ax.grid(axis='y',color=GRID,lw=.6); ax.set_axisbelow(True)
ax=axes[1]
# Persen dihitung di LUAR hari seri. Kalau tidak ada fitur pasar yang terpilih
# untuk satu leaf, kedua lengan identik - memasukkan hari seri ke penyebut
# membuat lengan yang kalah tampak menang.
share=E.pct_off
ax.bar(x,share,color=[BLUE if s>50 else ACC for s in share],zorder=3)
ax.axhline(50,ls='--',c=MUTED,lw=.9)
for i,r in enumerate(E.itertuples()):
    ax.text(i,share.iloc[i]+1.5,f'{100*r.ties/r.n:.0f}% tied',ha='center',
            fontsize=6.2,color=MUTED)
ax.set_xticks(x); ax.set_xticklabels(lbl,fontsize=6.8)
ax.set_ylabel('% of non-tied days where OFF is better',fontsize=7.2); ax.set_ylim(0,100)
ax.grid(axis='y',color=GRID,lw=.6); ax.set_axisbelow(True)
simpan(fig,'fig6_external.png')

# ------------------------------------------------- Gambar 6b (baru): pasar benar
B=pd.DataFrame(T['tabel8b'])
lbl2=[f"{'univariate' if b==0 else 'mRMR'}\nk={k}" for b,k in zip(B.beta,B.k)]
x2=np.arange(len(B)); w2=.26
fig,axes=plt.subplots(1,2,figsize=(7.4,2.8))
ax=axes[0]
ax.bar(x2-w2,B.mati,w2,label='market off',color=BLUE,zorder=3)
ax.bar(x2,B.nol,w2,label='market on, zero-filled',color=ACC,zorder=3)
ax.bar(x2+w2,B.benar,w2,label='market on, supplied',color='#4f7d5a',zorder=3)
ax.set_xticks(x2); ax.set_xticklabels(lbl2,fontsize=6.8)
ax.set_ylabel('mean MASE',fontsize=8)
ax.legend(fontsize=6.4,frameon=False); ax.grid(axis='y',color=GRID,lw=.6)
ax.set_axisbelow(True)
ax=axes[1]
ax.bar(x2-w2/2,B.delta_nol,w2,label='zero-filled',color=ACC,zorder=3)
ax.bar(x2+w2/2,B.delta_benar,w2,label='supplied',color='#4f7d5a',zorder=3)
for i,r in enumerate(B.itertuples()):
    ax.text(i,r.delta_nol+1.0,f'-{r.rusak_hilang_pct:.0f}%',ha='center',
            fontsize=6.6,color=MUTED)
ax.axhline(0,c='#222',lw=.9)
ax.set_ylim(top=B.delta_nol.max()*1.14)   # ruang untuk label di atas batang
ax.set_xticks(x2); ax.set_xticklabels(lbl2,fontsize=6.8)
ax.set_ylabel('% worse than market off',fontsize=8)
ax.legend(fontsize=6.6,frameon=False); ax.grid(axis='y',color=GRID,lw=.6)
ax.set_axisbelow(True)
simpan(fig,'fig6b_pasar_benar.png')

# ------------------------- Gambar 11 (baru): slot pasar lawan kerusakan
P=pd.DataFrame(T['per_leaf_benar']); SD=T['slot_damage']
fig,axes=plt.subplots(1,2,figsize=(7.4,2.9),sharey=True)
for ax,kol,tag,warna,st in ((axes[0],'rusak_nol','zero-filled',ACC,SD['nol']),
                            (axes[1],'rusak_benar','supplied','#4f7d5a',SD['benar'])):
    ax.scatter(P.slot,P[kol],s=34,c=warna,ec='white',lw=.6,zorder=3)
    ax.axhline(0,c='#222',lw=.9)
    ax.set_xlabel('market features retained (of 25)',fontsize=8)
    ax.set_title(f"{tag}\nSpearman {st['rho']:.3f}, p={st['p']:.3f}",fontsize=8)
    ax.grid(color=GRID,lw=.6); ax.set_axisbelow(True)
axes[0].set_ylabel('% worse than market off',fontsize=8)
simpan(fig,'fig11_slot_damage.png')

# ---------------------------------------------------------------- Gambar 9
R=pd.DataFrame(T['reverse_ablation']); bm=T['reverse_by_model']
mods=['LightGBM','RandomForest','XGBoost']
x=np.arange(len(R)); w=.24
fig,ax=plt.subplots(figsize=(7.4,3.0))
for i,m in enumerate(mods):
    v=[bm[c][i] for c in R.component]
    ax.bar(x+(i-1)*w,v,w,label=m,color=[BLUE,ACC,MUTED][i],zorder=3)
for i,r in enumerate(R.itertuples()):
    ax.plot([i-.42,i+.42],[r.delta]*2,c='#222',lw=1.6,ls='--',zorder=5)
    ax.text(i,r.delta+.25,f'pooled {r.delta:+.2f}%  p={r.p:.3f}',ha='center',fontsize=7)
ax.axhline(0,c='#222',lw=.9)
ax.set_xticks(x); ax.set_xticklabels([c.replace(' ','\n',1) for c in R.component],fontsize=7.6)
ax.set_ylabel('% lost when component removed',fontsize=8)
ax.legend(fontsize=7,frameon=False,ncol=3); ax.grid(axis='y',color=GRID,lw=.6); ax.set_axisbelow(True)
simpan(fig,'fig9_ablation.png')

# ---------------------------------------------------------------- Gambar 10
sl=T['slot_uptake_new']; st=pd.DataFrame(T['selector_tests']).sort_values('k')
fig,axes=plt.subplots(1,2,figsize=(7.4,2.5))
ax=axes[0]
x=np.arange(2); w=.36
ax.bar(x-w/2,[sl['k12_mrmr'],sl['k25_mrmr']],w,label='mRMR',color=BLUE,zorder=3)
ax.bar(x+w/2,[sl['k12_univ'],sl['k25_univ']],w,label='univariate',color=ACC,zorder=3)
ax.set_xticks(x); ax.set_xticklabels(['k=12','k=25'],fontsize=8)
ax.set_ylabel('market features retained',fontsize=8)
ax.legend(fontsize=7,frameon=False); ax.grid(axis='y',color=GRID,lw=.6); ax.set_axisbelow(True)
ax=axes[1]
ax.bar([f'k={int(k)}' for k in st.k],st.delta,color=BLUE,zorder=3)
for i,r in enumerate(st.itertuples()):
    ax.text(i,r.delta-.12,f'p={r.p:.3f}',ha='center',fontsize=7,color=MUTED)
ax.axhline(0,c='#222',lw=.9)
ax.set_ylabel('% change from using mRMR',fontsize=8)
ax.grid(axis='y',color=GRID,lw=.6); ax.set_axisbelow(True)
simpan(fig,'fig10_selector.png')
print('selesai ->',F)

# ---------------------------------------------------- Gambar 7 (dibangun ulang)
# WAJIB dibangun ulang, tidak boleh dipakai ulang dari versi lama: kolam lag
# pasar berubah, dan pangsa kepentingannya ikut bergeser - Lag 26,1% -> 19,0%,
# External 7,8% -> 11,5%.
FAM = {k: v for k, v in sorted(T['shap_family'].items(), key=lambda kv: -kv[1])
       if v >= 0.05}
fig, ax = plt.subplots(figsize=(7.4, 2.7))
nm = list(FAM); vv = [FAM[k] for k in nm]
warna = [ACC if k == 'External' else BLUE for k in nm]
ax.barh(range(len(nm))[::-1], vv, color=warna, zorder=3)
for i, v in enumerate(vv):
    ax.text(v + .6, len(nm) - 1 - i, f'{v:.1f}%', va='center', fontsize=7.6, color=MUTED)
ax.set_yticks(range(len(nm))[::-1]); ax.set_yticklabels(nm, fontsize=7.6)
ax.set_xlabel('share of total |SHAP| across the 15 series (%)', fontsize=8)
ax.set_xlim(0, max(vv) * 1.16)
ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
simpan(fig, 'fig7_shapfamily.png')

# --------------------------------------- Gambar 8 (pengganti beeswarm lama)
# Komposisi 25 slot terpilih per seri, plus pangsa kepentingan pasar. Dibangun
# dari shap_ringkas.json, jadi bisa direproduksi tanpa nilai SHAP mentah.
PL = T['shap_per_leaf']; ES = T['shap_ext_share']
lf = sorted(PL, key=lambda l: -PL[l]['n_ext'])
n_ext = [PL[l]['n_ext'] for l in lf]; n_lag = [PL[l]['n_lag'] for l in lf]
n_sisa = [25 - a - b for a, b in zip(n_ext, n_lag)]
fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2), sharey=True)
ax = axes[0]; yy = np.arange(len(lf))
ax.barh(yy, n_ext, color=ACC, zorder=3, label='market')
ax.barh(yy, n_lag, left=n_ext, color=BLUE, zorder=3, label='own lags')
ax.barh(yy, n_sisa, left=np.add(n_ext, n_lag), color=GRID, zorder=3, label='other')
ax.set_yticks(yy); ax.set_yticklabels([f'{l}  {LAB[l]}' for l in lf], fontsize=6.8)
ax.set_xlabel('composition of the 25 selected features', fontsize=8)
ax.legend(fontsize=6.6, frameon=False, ncol=3, loc='lower center',
          bbox_to_anchor=(0.5, 1.005))   # di atas sumbu; di dalam ia menutupi batang terakhir
ax.invert_yaxis(); ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
ax = axes[1]
esd = {r['leaf']: r['share'] for r in ES}   # ES adalah daftar {leaf, share}
share = [esd.get(l, 0.0) for l in lf]
ax.barh(yy, share, color=ACC, zorder=3)
ax.set_xlabel('market share of total |SHAP| (%)', fontsize=8)
ax.grid(axis='x', color=GRID, lw=.6); ax.set_axisbelow(True)
simpan(fig, 'fig8_slotcomposition.png')

# ---------------------------------------------------------------- Gambar 2
# Skema desain evaluasi. Dibangun di sini, bukan disalin dari run lama:
# pipeline yang menyalin gambar dari tempat lain akan patah di mesin bersih,
# dan itulah yang terjadi saat berkas ini pertama kali dicoba di repo.
fig, ax = plt.subplots(figsize=(7.4, 1.95))
NTRAIN = T['n_hari'] - 1
ax.add_patch(plt.Rectangle((0, .62), 8.6, .3, fc='#E8EFF4', ec=BLUE, lw=.8))
ax.text(4.3, .77, f'Training — {NTRAIN:,} business days '
        f'({T["tgl_awal"]} – {T["tgl_akhir"]})',
        ha='center', va='center', fontsize=7.8, color='#1B2530')
ax.add_patch(plt.Rectangle((8.65, .62), .35, .3, fc='#F6E9E7', ec=ACC, lw=1.1))
ax.text(8.82, .77, '1', ha='center', va='center', fontsize=7.6,
        weight='bold', color=ACC)
ax.text(9.12, .77, f'test: {T["tgl_akhir"]}', ha='left', va='center',
        fontsize=7.6, color=ACC)
ax.text(0, 1.0, 'A. Headline design — one origin, one step',
        fontsize=8.2, weight='bold', color='#1B2530')
ax.add_patch(plt.Rectangle((0, .06), 7.4, .3, fc='#E8EFF4', ec=BLUE, lw=.8))
ax.text(3.7, .21, f'Training — {T["n_hari"] - 30:,} business days',
        ha='center', va='center', fontsize=7.8, color='#1B2530')
for i in range(30):
    ax.add_patch(plt.Rectangle((7.45 + i * .052, .06), .045, .3,
                               fc='#F6E9E7', ec=ACC, lw=.35))
ax.text(9.12, .21, '30 rolling one-step origins', ha='left',
        va='center', fontsize=7.6, color=ACC)
ax.text(0, .44, 'B. Inference design — 30 origins, one step each',
        fontsize=8.2, weight='bold', color='#1B2530')
ax.set_xlim(-.1, 12.3); ax.set_ylim(0, 1.15); ax.axis('off')
simpan(fig, 'fig2_design.png')
