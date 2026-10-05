/* Penyusun naskah DOCX - revisi.
 *
 * Perubahan dari versi pertama:
 *   - satuan data: juta USD (bukan miliar rupiah)
 *   - kalimat diperpendek, alur disederhanakan
 *   - tabel baru per-leaf: feature engineering vs FE + fitur eksternal
 *   - ditegaskan bahwa kondisi eksternal memakai FE + eksternal, bukan eksternal saja
 *   - beeswarm SHAP dan bagan pangsa kepentingan fitur
 *
 * Seluruh angka datang dari tables.json. Berkas ini hanya menyusun.
 */
const fs = require('fs');
const D = require('docx');
const {
  Document, Packer, Paragraph, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, Footer, PageNumber,
} = D;

const path = require('path');

/* Nama TAMPILAN leaf (A.2.a -> A.1, B.a -> B.1, C.e -> C.5), dari
   ../nama_leaf.json - sumber yang sama dengan figs.py dan shap_baru.py.
   Kode internal tetap dipakai di tables.json dan logika (ACTOROF, urutan).
   Penggantian dilakukan di konstruktor TextRun, jadi SETIAP teks di naskah -
   paragraf, sel tabel, judul, keterangan, catatan - lewat satu pintu dan
   tidak ada tempat yang terlewat. Batas kata mencegah "A.2.a" di dalam kode
   lain atau nama fitur ikut terganti. */
const NAMA_LEAF = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'nama_leaf.json'), 'utf8')).peta;
const KODE_LAMA = new RegExp('(?<![\\w.])(' + Object.keys(NAMA_LEAF).map(k => k.replace(/\./g, '\\.')).join('|') + ')(?!\\w|\\.\\w)', 'g');
const tampil = t => t.replace(KODE_LAMA, k => NAMA_LEAF[k]);
let nTampil = 0;
class TextRun extends D.TextRun {
  constructor(o) {
    if (o && typeof o === 'object' && typeof o.text === 'string') {
      const baru = tampil(o.text);
      if (baru !== o.text) nTampil++;
      o = { ...o, text: baru };
    } else if (typeof o === 'string') o = tampil(o);
    super(o);
  }
}

/* Jalan berkas sejajar dengan jalan.py, termasuk env-nya, supaya rantai
   Python dan Node menunjuk folder yang sama. */
const REPO = path.resolve(__dirname, '..', '..', '..');
const KERJA = process.env.JBV_NASKAH_KERJA
  ? path.resolve(process.env.JBV_NASKAH_KERJA)
  : path.join(REPO, 'scripts', 'paper', 'naskah', 'keluaran');
const TABLES = path.join(KERJA, 'tables.json');
const FIG = path.join(KERJA, 'gambar') + path.sep;
if (!fs.existsSync(TABLES)) {
  console.error(`BERHENTI: ${TABLES} belum ada. Jalankan buat_tables.py dulu.`);
  process.exit(1);
}
const T = JSON.parse(fs.readFileSync(TABLES, 'utf8'));
// Badan naskah sejak review ketiga: jalan ulang v2 (buat_tables_v2.py).
const TABLES2 = path.join(KERJA, 'tables_v2.json');
if (!fs.existsSync(TABLES2)) { console.error(`BERHENTI: ${TABLES2} belum ada. Jalankan buat_tables_v2.py.`); process.exit(1); }
const T2 = JSON.parse(fs.readFileSync(TABLES2, 'utf8'));

const PAGE_W = 12240, MARGIN = 1440;
const INK = '1B2530', MUTED = '5E6B76', ACC = '9E2B2B', RULE = 'C8D0D6', HDR = 'EEF2F5';

const n = (v, d = 3) => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  const t = Number(v).toFixed(d);
  return /^-0\.?0*$/.test(t) ? t.slice(1) : t;       // tidak ada "-0.0" (review ketiga)
};
const pv = p => (p === null || p === undefined) ? '—' : (p < 0.0001 ? '< 0.0001' : Number(p).toFixed(4));
const pct = (v, d = 2) => `${v > 0 ? '+' : ''}${n(v, d)}%`;

/* -------------------------------------------------------------- primitives */
/* Gaya dasar bisa diganti supaya NOTE ikut memakai pemroses ini. Sebelumnya
   NOTE mengirim satu untai utuh ke TextRun, jadi **tebal** di TENGAH catatan
   tercetak apa adanya beserta bintangnya - terlihat di 3.5 sebagai "does
   **not** replace". Bold di awal untai memang jalan karena butir bernomor
   memakai runs(); yang di tengah tidak pernah diproses. */
function runs(text, gaya = {}) {
  const dasar = { size: 21, color: INK, ...gaya };
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ ...dasar, text: text.slice(last, m.index) }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ ...dasar, text: t.slice(2, -2), bold: true }));
    else out.push(new TextRun({ ...dasar, text: t.slice(1, -1), italics: true }));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(new TextRun({ ...dasar, text: text.slice(last) }));
  return out;
}
const P = t => new Paragraph({ spacing: { after: 150, line: 300 }, alignment: AlignmentType.JUSTIFIED, children: runs(t) });

/* Angka kecil dieja huruf, mengikuti gaya prosa naskah ("every day from one to
   fifteen"). Dipakai untuk angka yang DITURUNKAN dari konfigurasi, supaya
   memperbaiki angkanya tidak sekaligus merusak gayanya. Di atas dua puluh
   naskah memang memakai digit, jadi di situ dikembalikan apa adanya. */
const KATA = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
  'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
  'seventeen', 'eighteen', 'nineteen', 'twenty'];
const kata = v => (Number.isInteger(v) && v >= 0 && v < KATA.length ? KATA[v] : String(v));

/* Arah sebuah komponen DITURUNKAN dari tanda deltanya, tidak diketik.
   Konvensi: delta = (tanpa komponen - dengan komponen) / dengan komponen, jadi
   POSITIF berarti membuangnya memperburuk, yaitu komponennya MEMBANTU.

   Kenapa perlu fungsi. Kalimat "tuning is the wrong sign" ditulis saat blok
   validasi masih 10 origin dan penyetelan memang -1,18 persen. Sesudah blok
   dilebarkan ke 60 ia menjadi +0,10 persen - membantu, meski tipis - tapi
   kalimatnya tertinggal, dan mencetak "wrong sign" tepat di sebelah angka yang
   membantahnya. Pemeriksa tidak bisa menangkapnya: angkanya benar, kata-kata di
   sekitarnyalah yang salah. */
const komponenMembantu = d => d > 0;
// jamak: subjeknya jamak ("Tuned hyperparameters help", bukan "helps").
const arahKomponen = (d, jamak = false) =>
  d > 0 ? (jamak ? 'help' : 'helps')
        : (jamak ? 'carry the wrong sign' : 'carries the wrong sign');
const matikanJadi = d => (d > 0 ? 'worse' : 'better');
const Kata = v => { const s = kata(v); return s[0].toUpperCase() + s.slice(1); };
const Kata1 = t => t[0].toUpperCase() + t.slice(1);

/* Sebaran relatif ketiga ensemble pohon di Tabel 6, dalam persen. Dipakai di
   abstrak. Diturunkan supaya klaim "within X per cent" tidak perlu diketik
   ulang setiap kali angkanya bergerak. */
const POHON = ['RandomForest', 'LightGBM', 'XGBoost'];
// Pembantu prosa. Di atas `const doc` karena build() dipanggil saat doc dibuat.
const pTeks = p => (p < 0.0001 ? 'p < 0.0001' : `p = ${Number(p).toFixed(4)}`);
const niceK = m => (m === 'RandomForest' ? 'random forest' : m === 'Naive' ? 'the random walk'
  : m === 'SeasonalDecomp' ? 'seasonal decomposition' : m === 'NaiveDrift' ? 'the random walk with drift'
  : m === 'NaiveMean' ? 'the rolling mean' : NICE[m] || m);
const NAMA_KOMP = { 'Redundancy-aware selection': 'redundancy-aware selection',
  'Daily re-fitting': 'daily re-fitting', 'Tuned hyperparameters': 'tuning' };
const fmtN = v => v.toLocaleString('en-US');
const daftarN = xs => xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1];
const NM_POHON = { LightGBM: 'LightGBM', RandomForest: 'random forest', XGBoost: 'XGBoost' };
const URUT_POHON = ['LightGBM', 'RandomForest', 'XGBoost'];     // urutan reverse_by_model
function sebaranPohon() {
  const v = T.e2_summary.filter(r => POHON.includes(r.model)).map(r => r.mase);
  if (v.length !== POHON.length) {
    throw new Error(`sebaranPohon: ketemu ${v.length} dari ${POHON.length} ensemble pohon di e2_summary`);
  }
  const lo = Math.min(...v), hi = Math.max(...v);
  return 100 * (hi - lo) / lo;
}

/* Persamaan terpusat. Dipakai untuk rumus MASE di 3.4. Serif dan sedikit
   lebih besar supaya terbaca sebagai matematika, bukan kalimat. */
const EQ = (t, nomor) => new Paragraph({
  spacing: { before: 170, after: 170, line: 300 },
  tabStops: [{ type: D.TabStopType.CENTER, position: 4680 }, { type: D.TabStopType.RIGHT, position: 9360 }],
  children: [new TextRun({ text: '\t' + t, font: 'Cambria', size: 23, italics: true }),
    ...(nomor ? [new TextRun({ text: `\t(${nomor})`, size: 21 })] : [])],
});
/* Kotak berbayang satu sel untuk "lesson learned" (review kedua: ringkas
   pitfall menjadi boks, bukan subbab panjang). */
/* Persamaan sebagai objek matematika Word (OMML), bukan teks biasa. */
const MR = t => new D.MathRun(t);
const MSUB = (a, b) => new D.MathSubScript({ children: [MR(a)], subScript: [MR(b)] });
const EQM = (isi, nomor) => new Paragraph({
  spacing: { before: 170, after: 170, line: 300 },
  tabStops: [{ type: D.TabStopType.CENTER, position: 4680 }, { type: D.TabStopType.RIGHT, position: 9360 }],
  children: [new TextRun({ text: '\t' }), new D.Math({ children: isi }),
    ...(nomor ? [new TextRun({ text: `\t(${nomor})`, size: 21 })] : [])],
});
/* Putusan satu perbandingan: setara (TOST +-2%), berbeda (CI 95% tidak memuat
   nol) atau belum terputuskan. tanda=+1 berarti perubahan positif = lebih buruk. */
const putusan = (r, buruk = 'worse', baik = 'better') =>
  r.setara ? 'equivalent' : (r.beda ? (r.delta > 0 ? buruk : baik) : 'inconclusive');
const BOX = (judul, paras) => new Table({
  columnWidths: [9360], width: { size: 9360, type: WidthType.DXA },
  rows: [new TableRow({ children: [new TableCell({
    width: { size: 9360, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: 'F3F6F9', color: 'auto' },
    margins: { top: 120, bottom: 120, left: 160, right: 160 },
    borders: { top: { style: BorderStyle.SINGLE, size: 6, color: RULE }, bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE },
      left: { style: BorderStyle.SINGLE, size: 6, color: RULE }, right: { style: BorderStyle.SINGLE, size: 6, color: RULE } },
    children: [new Paragraph({ spacing: { after: 90 }, children: [new TextRun({ text: judul, bold: true, size: 20, color: INK })] }),
      ...paras.map(t => new Paragraph({ spacing: { after: 80, line: 280 }, alignment: AlignmentType.JUSTIFIED, children: runs(t, { size: 19 }) }))],
  })] })],
});
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 330, after: 150 }, children: [new TextRun({ text: t, bold: true, size: 26, color: INK })] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 240, after: 110 }, children: [new TextRun({ text: t, bold: true, size: 22, color: INK })] });
const H3 = t => new Paragraph({ spacing: { before: 200, after: 90 }, children: [new TextRun({ text: t, bold: true, size: 21, color: INK })] });
const LEAD = (l, t) => new Paragraph({
  spacing: { after: 140, line: 300 }, alignment: AlignmentType.JUSTIFIED,
  children: [new TextRun({ text: l + '. ', bold: true, size: 21, color: INK }), ...runs(t)],
});
const NOTE = t => new Paragraph({ spacing: { before: 40, after: 190 }, children: runs(t, { size: 17, italics: true, color: MUTED }) });
const TCAP = (num, t) => new Paragraph({
  spacing: { before: 215, after: 80 },
  children: [new TextRun({ text: `Table ${num}. `, bold: true, size: 18, color: INK }), new TextRun({ text: t, size: 18, color: INK })],
});
const FCAP = (num, t) => new Paragraph({
  spacing: { before: 70, after: 215 },
  children: [new TextRun({ text: `Figure ${num}. `, bold: true, size: 18, color: INK }), new TextRun({ text: t, size: 18, color: INK })],
});
const IMG = (f, w, h) => new Paragraph({
  spacing: { before: 195, after: 0 }, alignment: AlignmentType.CENTER,
  children: [new ImageRun({ type: 'png', data: fs.readFileSync(FIG + f), transformation: { width: w, height: h } })],
});
const BUL = items => items.map(t => new Paragraph({
  numbering: { reference: 'bul', level: 0 },
  spacing: { after: 95, line: 290 }, alignment: AlignmentType.JUSTIFIED, children: runs(t),
}));

function cell(text, o = {}) {
  return new TableCell({
    width: { size: o.w, type: WidthType.DXA },
    shading: o.head ? { type: ShadingType.CLEAR, fill: HDR, color: 'auto' } : undefined,
    margins: { top: 55, bottom: 55, left: 85, right: 85 },
    borders: {
      top: { style: BorderStyle.SINGLE, size: o.top ?? 2, color: RULE },
      bottom: { style: BorderStyle.SINGLE, size: o.bottom ?? 2, color: RULE },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
    },
    children: [new Paragraph({
      alignment: o.right ? AlignmentType.RIGHT : AlignmentType.LEFT,
      spacing: { after: 0 },
      children: [new TextRun({ text: String(text), size: 16.5, bold: !!o.head || !!o.bold, color: o.acc ? ACC : INK })],
    })],
  });
}
function TBL(widths, header, rows, opts = {}) {
  const trs = [new TableRow({
    tableHeader: true,
    children: header.map((h, i) => cell(h, { w: widths[i], head: true, right: i >= (opts.rightFrom ?? 1), top: 6, bottom: 4 })),
  })];
  rows.forEach((r, ri) => trs.push(new TableRow({
    children: r.map((c, i) => cell(c, {
      w: widths[i], right: i >= (opts.rightFrom ?? 1),
      acc: opts.accRows && opts.accRows.includes(ri),
      bold: opts.boldRows && opts.boldRows.includes(ri),
      bottom: ri === rows.length - 1 ? 6 : 2,
    })),
  })));
  return new Table({ columnWidths: widths, width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, rows: trs });
}

/* ------------------------------------------------------------------- data */
const e1rank = [...T.e1_summary].sort((a, b) => a.mase - b.mase);
const e2rank = [...T.e2_summary].sort((a, b) => a.mase - b.mase);
const abl = T.ablation;
const bestK = T.ablation_best;
const ablBest = abl.find(a => a.k === bestK);
const abl25 = abl.find(a => a.k === 25);
const ext12 = T.external.find(e => e.k === 12);
const ext25 = T.external.find(e => e.k === 25);
const pl25 = T.per_leaf_ext.filter(r => r.k === 25);
const pl12 = T.per_leaf_ext.filter(r => r.k === 12);
const plSum = T.per_leaf_ext_summary;
const fam = T.shap_family;
const famKeys = Object.keys(fam);
const extShare = T.shap_ext_share;

const NICE = {
  Naive: 'Random walk', NaiveMean: 'Rolling mean', NaiveDrift: 'Random walk with drift',
  Croston: 'Croston', SeasonalDecomp: 'Seasonal decomposition', ARIMA: 'ARIMA',
  Prophet: 'Prophet', RandomForest: 'Random forest', LightGBM: 'LightGBM', XGBoost: 'XGBoost',
  SeasonalNaive: 'Seasonal naive', ETS: 'ETS', Theta: 'Theta', Ridge: 'Ridge regression',
};
const nice = m => NICE[m] || m;

const bestCount = (() => {
  const c = {};
  Object.values(T.best_per_leaf).forEach(m => { c[m] = (c[m] || 0) + 1; });
  return Object.entries(c).sort((a, b) => b[1] - a[1]);
})();

const PURPOSE_EN = {
  'Ekspor': 'Export', 'Impor': 'Import', 'Investasi': 'Investment',
  'Repatriasi': 'Repatriation', 'Transaksi tanpa underlying': 'No underlying',
  'Remittance': 'Remittance', 'Trading': 'Trading', 'Lainnya': 'Other',
};
const LABEL = Object.fromEntries(T.desc.map(d => {
  const raw = String(d.label).replace(/^[a-f]\.\s*/, '');
  return [d.leaf, PURPOSE_EN[raw] || raw];
}));
const ACTOROF = id => id.startsWith('A') ? 'Corporate'
  : id.startsWith('B') ? 'Individual' : 'Non-resident';

/* Pembantu v2: di atas `const doc` karena build() dipanggil saat doc dibuat. */
const L2 = ['RandomForest', 'LightGBM', 'XGBoost'];
const rk2 = () => T2.peringkat;
const juara2 = () => T2.juara;
const BJ = () => Object.fromEntries(T2.banding_juara.map(r => [r.label, r]));
const D2 = m => T2.desk.find(d => d.model === m);
const mcs2 = () => T2.mcs.tersisa;
const NR2 = () => T2.nroll;
const NU2 = () => T2.n_leaf * T2.nroll;
const tgl2 = d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
const rentangMcs = () => Math.max(...T2.banding_juara.filter(r => T2.mcs.tersisa.includes(r.label)).map(r => r.delta));
const nmL = m => (m === 'Ridge' ? 'ridge regression' : niceK(m));
const tglEN2 = d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

/* ------------------------------------------------------------------ build */
const doc = new Document({
  creator: 'FX flow forecasting study',
  title: 'Does Machine Learning Beat Simple Benchmarks? One-Day-Ahead Forecasts of Foreign-Exchange Flows in Indonesia',
  numbering: {
    config: [{
      reference: 'bul',
      levels: [{ level: 0, format: D.LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 360, hanging: 200 } } } }],
    }],
  },
  styles: { default: { document: { run: { font: 'Calibri', size: 21, color: INK } } } },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 15840 }, margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 17, color: MUTED })] })] }) },
    children: build(),
  }],
});

function build() {
  const c = [];

  /* ------------------------------------------------ angka turunan bersama */
  const J = T.jendela;
  const g8 = T.tabel8b_gabungan;
  const R = Object.fromEntries(T.reverse_ablation.map(a => [a.component, a]));
  const rSel = R['Redundancy-aware selection'], rRef = R['Daily re-fitting'], rTun = R['Tuned hyperparameters'];
  const RB = T.robust;
  const rbKomp = Object.fromEntries(RB.komponen.map(r => [r.label, r]));
  const rbMet = Object.fromEntries(RB.metode.map(r => [r.label, r]));
  const juara = e2rank[0];
  const mcs = T.mcs.tersisa;
  const mcsStat = mcs.filter(m => !POHON.includes(m));
  const acuanK = T.ablation_acuan;
  const kList = abl.map(a => a.k);
  const nMLmenang = T.winners.filter(w => w.fam === 'ML').length;
  const kurtMaks = Math.max(...T.desc.map(d => d.kurt));
  const nPasangMetode = T.e2_summary[0].n, nPasangPipa = T.reverse_ablation[0].n;
  const fmt = v => v.toLocaleString('en-US');
  const daftar = xs => xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1];
  const jendelaTeks = daftar(J.rolling.map(String));
  const setara = RB.komponen.filter(r => r.setara).map(r => NAMA_KOMP[r.label]);
  const tidakSetara = RB.komponen.filter(r => !r.setara).map(r => NAMA_KOMP[r.label]);
  const pasarQ = T.pasar_kualifikasi;
  const skala = T.skala_koreksi;
  const juaraSkala = skala.peringkat.find(r => r.model === juara.model);

  /* ---------------------------------------------------------------- title */
  c.push(new Paragraph({
    spacing: { after: 250 },
    children: [new TextRun({ text: 'Does Machine Learning Beat Simple Benchmarks? One-Day-Ahead Forecasts of Foreign-Exchange Flows in Indonesia', bold: true, size: 32, color: INK })],
  }));

  /* -------------------------------------------------------------- abstract */
  // Formula masukan no. 18 (penting, cara, temuan, implikasi), dibatasi
  // sekitar 250 kata atas saran review kedua. Setiap angka dari tables.json.
  c.push(H1('Abstract'));
  c.push(...abstrakV2());
  c.push(new Paragraph({
    spacing: { before: 110, after: 60 },
    children: [new TextRun({ text: 'Keywords: ', bold: true, size: 20, color: INK }),
      new TextRun({ text: 'machine learning; one-day-ahead forecasting; foreign-exchange flows; feature selection; ablation study; model confidence set; SHAP', size: 20, color: INK })],
  }));
  c.push(new Paragraph({
    spacing: { after: 200 },
    children: [new TextRun({ text: 'JEL classification: ', bold: true, size: 20, color: INK }),
      new TextRun({ text: 'C22, C45, C53, F31, E58', size: 20, color: INK })],
  }));

  /* ---------------------------------------------------------- 1. Intro */
  c.push(H1('1. Introduction'));
  c.push(P('A central bank that watches the foreign-exchange market needs a forward view of supply and demand. ' +
    'The net total is useful but not enough. Two days can share the same net total and be nothing alike. On ' +
    'one, exporters sell and importers buy in equal measure. On the other, non-residents pull money out while ' +
    'corporates sit still. Those two days call for different responses.'));
  c.push(P('This paper forecasts flows at the level where that distinction is visible. The data are ' +
    'administrative. Banks report each transaction, and every transaction carries a counterparty group and a ' +
    'declared purpose, which gives a two-way grid of who transacted and why (Figure 1). The setting is ' +
    'Indonesia, where the exchange-rate regime is a managed float and the onshore market is shallow by ' +
    'regional standards, so a single large settlement can move the daily total in one cell.'));
  c.push(IMG('fig1_taxonomy.png', 560, 258));
  c.push(FCAP(1, `The ${T.n_leaf} forecast units. Rows are counterparty groups, columns declared purposes, ` +
    'and each filled cell is one series, labelled with its mean since its first report, in millions of US dollars. ' +
    'Blue cells are net demand for foreign exchange on average and orange cells net supply. ' +
    'Dashed cells do not occur.'));
  c.push(P('The monitoring cycle is daily, so the forecast that matters is one business day ahead. ' +
    'Flows are quantities rather than prices, and unlike exchange rates, which are famously hard to beat with ' +
    'a random walk (Meese and Rogoff, 1983), they carry autocorrelation, calendar effects and settlement ' +
    'patterns that a learner can exploit. A machine-learning pipeline for this task is more than a learner, ' +
    'however. Around it sit a pool of engineered features, a rule that selects some of them, a search over ' +
    'hyperparameters, a schedule for re-fitting and, often, external market data. Each component is usually ' +
    'adopted by habit, and a pipeline reported only as a whole cannot tell the reader which parts do the work.'));
  c.push(P('We therefore put the pipeline at the centre and ask four questions of it.'));
  c.push(...BUL([
    '**RQ1.** Does a tuned machine-learning pipeline forecast the counterparty and purpose series more accurately than established statistical methods one day ahead?',
    '**RQ2.** Which parts of the pipeline earn their place? We test redundancy-aware feature selection, hyperparameter tuning, daily re-fitting, the number of features kept and, added after the main results, the training loss.',
    '**RQ3.** Do daily market data, such as the exchange rate, bond yields and equity prices, improve the forecasts?',
    '**RQ4.** Which features does the fitted model rely on, and does that differ across counterparty groups?',
  ]));
  c.push(P('The contribution is empirical and methodological. We evaluate a pipeline at the level where the ' +
    'supervisory question is asked, take it apart one component at a time, and report every comparison ' +
    'with paired tests, correction for multiple testing, confidence intervals that respect dependence across ' +
    'days, and equivalence tests that distinguish "no effect" from "not enough data".'));

  /* --------------------------------------------------- 2. Literature */
  c.push(H1('2. Related Literature'));
  c.push(H2('2.1. Machine Learning against Classical Methods'));
  c.push(P('Whether machine learning forecasts better than classical statistical methods has no general ' +
    'answer, and the literature is most useful for what it says about when each wins. The evidence from large ' +
    'comparisons of univariate series favours classical methods. Makridakis, Spiliotis and Assimakopoulos ' +
    '(2018a) compared ten machine-learning methods with eight statistical ones on 1,045 monthly series of the ' +
    'M3 competition and found the machine-learning methods less accurate at every horizon, while also far ' +
    'more costly to compute. They attribute the gap mainly to overfitting, since a flexible model fitted to ' +
    'one short series is hard to keep from fitting noise, and recommend preprocessing such as ' +
    'deseasonalisation before a machine-learning model is used. Eight of their ten methods come from Ahmed et ' +
    'al. (2010), who had compared them on the same data a decade earlier and found that their accuracy ' +
    'depended on how the series were preprocessed. In the M4 competition pure machine-learning entries did poorly, while combinations of ' +
    'statistical methods did well, and the winning method was a hybrid that kept exponential smoothing for ' +
    'level and seasonality and let a neural network learn across series (Smyl, 2020; Makridakis, Spiliotis and ' +
    'Assimakopoulos, 2018b, 2020).'));
  c.push(P('The picture reverses where data are plentiful. Cerqueira, Torgo and Soares (2022) show with ' +
    'learning curves that the advantage of statistical methods in such comparisons holds mainly for very short ' +
    'series and that machine-learning methods gain as the sample grows. In the M5 competition, on daily, ' +
    'grouped and often intermittent retail sales, gradient-boosted trees trained across many series at once ' +
    'led the field (Makridakis, Spiliotis and Assimakopoulos, 2022), and the winners of Kaggle forecasting ' +
    'competitions share the same ingredients, namely many related series, exogenous information and tree ' +
    'ensembles or neural networks trained globally (Bojer and Meldgaard, 2021). Global models can exploit ' +
    'patterns shared across series that a local model never sees (Montero-Manso and Hyndman, 2021), and ' +
    'recurrent networks are competitive with ETS and ARIMA in many situations but no silver bullet, and need ' +
    'careful preprocessing, such as deseasonalisation when seasonal patterns differ across series (Hewamalage, ' +
    'Bergmeir and Bandara, 2021). On daily demand for individual products, Spiliotis et al. (2022) find some ' +
    'machine-learning methods more accurate and less biased than statistical ones, and learning across ' +
    'products helps some of them further.'));
  c.push(P('In economics the gains, where they appear, are traced to specific features of the methods. For US ' +
    'inflation, Medeiros et al. (2021) find random forests more accurate than shrinkage, factor and ' +
    'autoregressive benchmarks, and attribute the gain to nonlinearity and to selecting among many ' +
    'predictors. Goulet Coulombe et al. (2022) separate the ingredients of machine learning in macroeconomic ' +
    'forecasting and conclude that nonlinearity is what matters, while the standard factor model remains the ' +
    'best form of regularisation. At the Reserve Bank of New Zealand, machine-learning nowcasts of GDP growth ' +
    'beat an autoregressive benchmark and a dynamic factor model in real time, and combining them helped ' +
    'further (Richardson, van Florenstein Mulder and Vehbi, 2021). For exchange rates, where the random walk ' +
    'is notoriously hard to beat (Meese and Rogoff, 1983), Amat, Michalski and Stoltz (2018) beat it one month ' +
    'ahead with fundamentals, but the machine learning that achieved this was sequential ridge regression and ' +
    'online averaging, chosen precisely because they limit overfitting.'));
  c.push(P('Read together, these studies suggest four conditions under which machine learning outperforms ' +
    'classical methods. It needs enough data to estimate flexible models, either long series or many related ' +
    'series learned together. It needs a signal that is nonlinear or depends on interactions that a linear or ' +
    'smoothing model cannot represent. It needs informative predictors beyond the series’ own past. And it ' +
    'needs regularisation and validation strong enough to keep the extra flexibility from fitting noise. ' +
    'Where these conditions fail, as with short, noisy series dominated by their own recent level, classical ' +
    'methods are as accurate and much cheaper, and combinations of methods are hard to beat. Our setting ' +
    'meets the first condition through long daily histories but tests the others, since the series are ' +
    'forecast one at a time, one day ahead, where persistence carries most of the signal, and market data are ' +
    'the candidate external predictors. This paper stays with local models, one per series, and Section 6 ' +
    'returns to global models and to reconciliation with the published total (Wickramasuriya, Athanasopoulos ' +
    'and Hyndman, 2019) as the natural next step.'));
  c.push(H2('2.2. Feature Selection and Forecast Evaluation'));
  c.push(P('Feature selection is well studied in theory (Guyon and Elisseeff, 2003; Kohavi and John, 1997), ' +
    'and redundancy-aware criteria such as mRMR (Peng, Long and Ding, 2005) are designed for pools of ' +
    'overlapping candidates like the lags and moving averages of a time series. The bias-variance trade-off ' +
    'says that past some point added predictors reduce out-of-sample accuracy (Hastie, Tibshirani and ' +
    'Friedman, 2009), but not where that point lies. For comparing forecasts, the literature offers paired ' +
    'tests of equal accuracy (Diebold and Mariano, 1995; Harvey, Leybourne and Newbold, 1997), procedures for ' +
    'identifying a set of best models (Hansen, Lunde and Nason, 2011), and rolling-origin and cross-validation ' +
    'designs for time series (Tashman, 2000; Bergmeir and Benítez, 2012). Applied studies rarely use them together.'));
  c.push(H2('2.3. Order Flow and Market Data'));
  c.push(P('On the economics, order flow carries information about exchange-rate moves (Evans and Lyons, ' +
    '2002; Lyons, 2001), and customer flows differ in that information by counterparty, with financial ' +
    'customers’ trades more informative than those of corporates (Menkhoff et al., 2016). Whether prices, in ' +
    'turn, help forecast next-day flows on top of the flows’ own history ' +
    'is the question this paper tests.'));
  c.push(TCAP(1, 'Hypotheses, the design choice each one isolates, and the test used.'));
  c.push(TBL([620, 3300, 2500, 2940],
    ['', 'Hypothesis', 'What is varied', 'Test'],
    [
      ['H1', 'A machine-learning learner is the most accurate method.', 'Method, and the training loss', 'Paired tests against the leading method, block-bootstrap intervals and a model confidence set'],
      ['H2', 'Each component of the pipeline improves accuracy.', 'Selection rule, tuning, re-fitting, one at a time', 'Paired tests and equivalence tests, full pipeline against each removal'],
      ['H3', `A count of ${acuanK} features is the right size.`, `Feature count, 12, 40 and all ${T.pool_internal} candidates`, `Paired and equivalence tests against k = ${acuanK}`],
      ['H4', 'Adding market data improves accuracy.', 'Market data as changes, as levels, or none', 'Paired and equivalence tests against none'],
      ['H5', 'The model draws most of its signal from the series’ own history.', 'Nothing, measured on the fitted model', 'SHAP importance by feature family'],
    ], { rightFrom: 99 }));

  /* --------------------------------------------------- 3. Methodology */
  c.push(H1('3. Data and Methodology'));

  c.push(H2('3.1. Data'));
  c.push(P(`The panel has ${T.n_leaf} daily series of net foreign-exchange transaction flows in millions of ` +
    `US dollars, reported rounded to whole millions, over ${fmt(T.n_hari)} business days from 2 January 2006 ` +
    'to 26 August 2026. **A positive value is net demand for foreign exchange, and a negative value is net ' +
    'supply.** Exporters, for example, sell the foreign currency they earn, so the export cells are negative ' +
    'on average, while importers buy it and the import cells are positive. Figure 2 shows every series.'));
  c.push(IMG('fig_seri_v2.png', 560, 499));
  c.push(FCAP(2, 'The fifteen series in millions of US dollars, each panel on its own scale. The green strip ' +
    `is the ${T2.nval}-day validation block and the orange strip the ${T2.nroll}-day test block. A dotted line ` +
    'marks the first report of a series that entered the reporting framework late.'));
  const late = T.skala_koreksi.seri;
  const tglEN = d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  const kelompokMulai = [...new Set(late.map(r => r.mulai))].sort().reverse()
    .map(d => { const ls = late.filter(r => r.mulai === d).map(r => r.leaf); return `${daftar(ls)} ${ls.length > 1 ? 'are' : 'is'} zero until ${tglEN(d)}`; });
  c.push(P(`Not every series is reported from the start. ${kelompokMulai.join(', and ')}, ` +
    'which reflects when the category entered the reporting framework rather than an absence ' +
    'of flows. Measured from each series’ first report, the share of zero days is small except in ' +
    `${daftar(T.desc.filter(d => d.zero > 15).map(d => `${d.leaf} (${n(d.zero, 1)} per cent)`))}. ` +
    'Because values are rounded to whole millions, part of the remaining zeros in the smallest cells are ' +
    'rounding rather than inactivity. ' +
    'B.a, sales of foreign currency by individuals for export, is thin by nature, because individuals ' +
    'seldom report such sales with the underlying export documents that place them in this category. The ' +
    `series also changes abruptly in January 2022. Its share of zero days is ${n(T.patahan_2022['B.a'].nol_14_21, 1)} ` +
    `per cent over 2014 to 2021 and ${n(T.patahan_2022['B.a'].nol_22, 1)} per cent from 2022 onwards. In the same month ` +
    `the mean absolute daily flow of A.2.a, corporate exports, falls from ${fmt(Math.round(T.patahan_2022['A.2.a'].abs_21))} million US dollars ` +
    `in 2021 to ${fmt(Math.round(T.patahan_2022['A.2.a'].abs_22))} million in 2022, while that of A.2.b, corporate transactions without underlying, rises from ` +
    `${fmt(Math.round(T.patahan_2022['A.2.b'].abs_21))} to ${fmt(Math.round(T.patahan_2022['A.2.b'].abs_22))} million. ` +
    `Their sum changes much less, from a mean daily net supply of ${fmt(Math.round(-T.patahan_2022.jumlah_a.des21))} ` +
    `million US dollars in December 2021 to ${fmt(Math.round(-T.patahan_2022.jumlah_a.jan22))} million in January 2022. ` +
    'A.2.a is also at its most volatile just before the test block. The standard deviation of its daily flow ' +
    `is ${fmt(Math.round(T.patahan_2022.a1_sd.min_19_24))} to ${fmt(Math.round(T.patahan_2022.a1_sd.max_19_24))} million ` +
    `in each year from 2019 to 2024, ${fmt(Math.round(T.patahan_2022.a1_sd.th2025))} million in 2025 and ` +
    `${fmt(Math.round(T.patahan_2022.a1_sd.th2026))} million in 2026. ` +
    'We report these features as they appear in the data and do not model them. Table 2 summarises the series.'));
  c.push(TCAP(2, `Descriptive statistics for the ${T.n_leaf} series, each from its first report. Values in millions of US dollars.`));
  c.push(descTable());
  c.push(P(`The market data cover the same ${fmt(T.n_hari)} dates. ${Kata(T.pasar ? T.pasar.n_var : 8)} ` +
    'variables are used, namely spot USD/IDR bid and ask, the one-month non-deliverable forward (NDF) bid and ' +
    'ask, which is an offshore contract, the ten-year government bond yield, the dollar index, net ' +
    'non-resident equity flows and the equity index. They enter the pipeline as levels. ' +
    (T.pasar
      ? `Missing values are rare, at most ${n(T.pasar.hilang_maks, 1)} per cent for any variable. Gaps are ` +
        'carried forward. At the very start of the sample, before a variable’s first observation, values are ' +
        `carried backwards by at most ${kata(T.pasar.bfill_maks)} date, which affects only the first days of ` +
        '2006 and no forecast origin.'
      : '')));

  c.push(...desain32());

  c.push(H2('3.3. The Machine-Learning Pipeline'));
  c.push(P('The pipeline has five parts. A pool of features is engineered from each series’ own history. A ' +
    'redundancy-aware rule selects a fixed number of them. Three tree ensembles are fitted on the selection. ' +
    'Their hyperparameters are tuned per series on a validation block. And every model is re-fitted at every ' +
    'forecast origin.'));
  c.push(H3('Feature pool'));
  c.push(P(`The pool holds ${T.pool_internal} candidates, listed in full in Appendix D. ` +
    `${Kata(T.n_lags)} lags of the target enter the pool, every day from one to fifteen and then twenty, ` +
    `twenty-five and thirty. Rolling means, standard deviations, minima and maxima use windows of ` +
    `${jendelaTeks} business days, and the pool also holds exponentially weighted means, differences and ` +
    'percentage changes, volatility and extreme-value measures, technical indicators, Fourier terms, calendar ' +
    'effects and four interaction terms. Every window is a multiple of five business days, a whole number of ' +
    `trading weeks, and the same rule sets the volatility windows, the RSI, the Fourier periods and the ` +
    `MACD, which therefore uses ${J.macd[0]}, ${J.macd[1]} and ${J.macd[2]} days rather than the conventional ` +
    '12, 26 and 9. Percentage changes from a zero base are undefined and are set to zero.'));
  const nLagPasar = T.lag_pasar.length;
  const lagMaks = T.lag_pasar[nLagPasar - 1];
  const perVariabel = nLagPasar + 1;
  const nVariabel = T.pool_pasar / perVariabel;
  if (!Number.isInteger(nVariabel) || T.pool_internal + T.pool_pasar !== T.pool_total) {
    throw new Error('kolam fitur tidak konsisten');
  }
  c.push(...pasar33());

  c.push(H3('Redundancy-aware feature selection'));
  c.push(P('We use the minimum-redundancy maximum-relevance criterion, mRMR, of Peng, Long and Ding (2005) in ' +
    'its correlation form. The relevance of a candidate is its absolute Spearman correlation with the ' +
    'target. Its redundancy is its mean absolute Spearman correlation with the features already chosen. ' +
    'Selection is greedy. The most relevant candidate is taken first, and each later step adds the candidate ' +
    'with the highest score'));
  c.push(EQM([MR('score(f) = |ρ(f, y)| − β '),
    new D.MathFraction({ numerator: [MR('1')], denominator: [MR('|S|')] }),
    new D.MathSum({ children: [MR('|ρ(f, s)|')], subScript: [MR('s∈S')] })], 1));
  c.push(P('where y is the target, S the set already chosen and β = 1. Setting β = 0 recovers the univariate ' +
    'rule that ranks candidates by relevance alone. The search runs over a shortlist of the max(3k, 40) most ' +
    'relevant candidates, and all correlations are computed on the training sample of each origin. Spearman ' +
    `rather than Pearson correlation is used because the flows are heavy-tailed, with excess kurtosis up to ` +
    `${n(kurtMaks, 0)}.`));
  c.push(P('Two properties of this form matter for reading the results. Because redundancy is an average over ' +
    'all features already chosen, a near-duplicate of one selected feature is penalised only weakly once ' +
    'many dissimilar features have been chosen, so the rule does not reliably exclude near-duplicates. And ' +
    'because relevance is a rank correlation, it only captures monotone relationships, which puts calendar ' +
    'effects such as the day of the week at a disadvantage. Appendix B shows both effects in the selected ' +
    'sets.'));

  c.push(...sisaV2(acuanK));
  c.push(...diskusiV2());

  /* ---------------------------------------------------- declarations */
  c.push(H1('Declarations'));
  c.push(P('**Data availability.** The flow data are confidential supervisory records and cannot be shared. ' +
    'The market data are from commercial providers.'));
  c.push(P('**Code availability.** The code that produces every table and figure from the model outputs, ' +
    'including the checks that tie each number in the text to its source, is available from the authors on ' +
    'request.'));
  c.push(P('**Disclaimer.** The views expressed are those of the authors and not necessarily those of their ' +
    'institution.'));

  c.push(H1('References'));
  refs().forEach(r => c.push(new Paragraph({
    spacing: { after: 90, line: 280 }, indent: { left: 360, hanging: 360 }, children: runs(r),
  })));

  /* ------------------------------------------------------- appendices */
  c.push(...appendix30());
  c.push(...appendixBeeswarmV2());
  c.push(...appendixZeroFill());
  c.push(...appendixFitur());
  c.push(...appendixRezim());
  c.push(...appendixRepro());
  c.push(...appendixInferensiV2());
  c.push(...appendixWaktu());

  return c;
}

/* ------------------------------------------------------------- fragments */

function gridTable() {
  const CFG = {
    RandomForest: ['100 trees, depth 10', '300 trees, depth 10', '300 trees, no depth limit', '100 trees, depth 4'],
    LightGBM: ['100 trees, rate 0.05, depth 5', '400 trees, rate 0.02, depth 5', '100 trees, rate 0.10, depth 3', '400 trees, rate 0.05, depth 8'],
    XGBoost: ['100 trees, depth 5, rate 0.05', '400 trees, depth 5, rate 0.02', '100 trees, depth 3, rate 0.10', '400 trees, depth 8, rate 0.05'],
  };
  const rows = ['RandomForest', 'LightGBM', 'XGBoost'].map(m => [
    nice(m), ...CFG[m].map((t, i) => `${t} (${T.cfg_terpilih[m][i]})`),
  ]);
  return TBL([1500, 1965, 1965, 1965, 1965],
    ['Learner', 'Configuration 1', 'Configuration 2', 'Configuration 3', 'Configuration 4'],
    rows, { rightFrom: 99 });
}

function suppliedTable() {
  const NK = Object.fromEntries(T.robust.nolkan_kondisi.map(r => [r.label, r]));
  const NG = Object.fromEntries(T.robust.nolkan.map(r => [r.label, r]));
  const rows = T.tabel8b.map(r => [
    r.beta === 0 ? 'univariate' : 'mRMR', String(r.k),
    n(r.mati, 3), n(r.nol, 3), pct(r.delta_nol, 1),
    n(r.benar, 3), pct(r.delta_benar, 1),
    `${n(r.rusak_hilang_pct, 0)}%`, pv(NK[`${r.beta === 1 ? 'mRMR' : 'univariate'}, k = ${r.k}`].p_holm),
  ]);
  const g = T.tabel8b_gabungan;
  rows.push(['pooled', '—', n(g.mati, 3), n(g.nol, 3), pct(g.delta_nol, 1),
    n(g.benar, 3), pct(g.delta_benar, 1), `${n(g.rusak_hilang_pct, 0)}%`,
    pv(NG['zero-filled'].p)]);
  return TBL([1080, 560, 900, 900, 860, 900, 860, 900, 940],
    ['Selector', 'k', 'Market off', 'Zero-filled', 'Penalty',
     'Supplied', 'Penalty', 'Recovered', 'Holm p, zero-filled vs off'],
    rows, { rightFrom: 1 });
}

function ensembleProse1() {
  return [P('No single method dominates, so a natural response is to combine them. Simple averages of ' +
    'forecasts are notoriously hard to beat, because weights that have to be estimated add error of their ' +
    'own (Smith and Wallis, 2009; Claeskens et al., 2016). We therefore test equal-weight combinations, ' +
    'which need no estimation, against the leading single method. Five are tested, and all five are ' +
    'reported and corrected together. The members of three of them were chosen after seeing Table 5, which ' +
    'can only flatter the combinations, so the test is if anything generous to them.')];
}

function ensembleProse2() {
  const E = T.ensemble, J = T.champion_juara;
  const RK = Object.fromEntries(T.robust.kombinasi.map(r => [r.label, r]));
  const nyataBaik = E.filter(e => e.delta < 0 && e.p_holm < 0.05);
  const nyataBuruk = E.filter(e => e.delta > 0 && e.p_holm < 0.05);
  const setara = E.filter(e => RK[e.nama].setara);
  const ragu = E.filter(e => putusan(RK[e.nama]) === 'inconclusive');
  const bawahSatu = E.filter(e => e.mase < 1);
  const c = [];
  c.push(P(`No combination is shown to beat ${nice(J)}. None is significantly better after correction` +
    (nyataBuruk.length
      ? `, and the ${daftarN(nyataBuruk.map(e => e.nama.toLowerCase()))} is significantly worse ` +
        `(Holm ${daftarN(nyataBuruk.map(e => n(e.p_holm, 3)))}), because it gives the weak benchmarks the ` +
        'same weight as the strong ones. '
      : '. ') +
    (setara.length
      ? `By the equivalence test the ${daftarN(setara.map(e => e.nama.toLowerCase()))} ` +
        `${setara.length > 1 ? 'are' : 'is'} equivalent to the leader within ±2 per cent. `
      : '') +
    `The other ${kata(ragu.length)} are inconclusive` +
    (bawahSatu.length === 1 && ragu.includes(bawahSatu[0])
      ? `, including the ${bawahSatu[0].nama.toLowerCase()}, the only forecast in the study whose mean MASE ` +
        `falls below one, at ${n(bawahSatu[0].mase, 3)}, but whose interval runs from ` +
        `${n(RK[bawahSatu[0].nama].lo95, 1)} to ${n(RK[bawahSatu[0].nama].hi95, 1)} per cent. `
      : '. ') +
    `No combination is better on more than ${Math.max(...E.map(e => e.leaf_lebih_baik))} of the ` +
    `${T.n_leaf} series. Combining is a cheap guard against choosing the wrong method for a series, but ` +
    'this test block cannot say whether it also improves accuracy.'));
  if (nyataBaik.length) throw new Error('ensembleProse2: ada kombinasi yang nyata lebih baik; tulis ulang');
  return c;
}

function descTable() {
  const rows = T.desc.map(d => [
    d.leaf, LABEL[d.leaf], n(d.mean, 1), n(d.sd, 1), n(d.med, 1),
    n(d.zero, 1), n(d.skew, 2), n(d.kurt, 1), n(d.acf1, 2),
  ]);
  return TBL([720, 1900, 940, 940, 860, 900, 880, 1060, 1060],
    ['Series', 'Purpose', 'Mean', 'SD', 'Median', 'Zero %', 'Skew', 'Excess kurtosis', 'AC(1)'],
    rows, { rightFrom: 2 });
}

function nCI(v) { return v !== 0 && Math.abs(v) < 0.05 ? n(v, 2) : n(v, 1); }
function ciTeks(r) { return `${pct(r.delta, 1)} [${nCI(r.lo95)}, ${nCI(r.hi95)}]`; }

function rankTable(rank, denganUji = true) {
  const M = Object.fromEntries(T.robust.metode.map(r => [r.label, r]));
  const rows = rank.map((d, i) => {
    const r = [String(i + 1), nice(d.model), n(d.mase, 3), n(d.med, 3)];
    if (denganUji) {
      const m = M[d.model];
      r.push(m ? ciTeks(m) : 'leader', m ? pv(m.p) : '—', n(T.mcs.p[d.model], 3));
    }
    return r;
  });
  return denganUji
    ? TBL([560, 2000, 1080, 1080, 2500, 1100, 1040],
      ['Rank', 'Method', 'Mean MASE', 'Median MASE', 'Change vs leader [95% CI]', 'Wilcoxon p', 'MCS p'], rows,
      { rightFrom: 2, accRows: [0] })
    : TBL([700, 3000, 1900, 1900], ['Rank', 'Method', 'Mean MASE', 'Median MASE'], rows,
      { rightFrom: 2, accRows: [0] });
}

function h1Prose() {
  const r = e2rank, top = r[0], K = T.champion_koreksi;
  const M = Object.fromEntries(T.robust.metode.map(x => [x.label, x]));
  const mcs = T.mcs.tersisa.filter(m => m !== top.model);
  const bedaCI = mcs.filter(m => M[m].beda);
  const dm = Object.fromEntries(T.dm_per_seri.map(d => [d.model, d]));
  const statMcs = mcs.filter(m => !POHON.includes(m));
  const c = [];
  c.push(P(`${nice(top.model)} has the lowest mean MASE, ${n(top.mase, 3)}, and the three learners take the ` +
    `first three places. The best benchmarks, ${daftarN(statMcs.map(niceK))}, follow within ` +
    `${n(Math.max(...statMcs.map(m => M[m].delta)), 1)} per cent. The random-walk forecast scores ` +
    `${n(r.find(d => d.model === 'Naive').mase, 3)}, so every learner beats it on the test block, although ` +
    'no method averages below the in-sample scale of one.'));
  c.push(P(`The leading group is not a single method. A 90 per cent model confidence set retains ` +
    `${kata(T.mcs.tersisa.length)} methods, ${daftarN(T.mcs.tersisa.map(niceK))}, and excludes the others ` +
    `with p-values of ${n(Math.max(...Object.entries(T.mcs.p).filter(([m]) => !T.mcs.tersisa.includes(m)).map(([, v]) => v)), 3)} ` +
    'or less. ' +
    (bedaCI.length
      ? `Within the set, the block-bootstrap intervals for ${daftarN(bedaCI.map(niceK))} lie above zero ` +
        `(${daftarN(bedaCI.map(m => ciTeks(M[m])))}), so taken one at a time they are somewhat less accurate ` +
        `than ${nice(top.model)}. Corrected for the ${K.n_uji} comparisons with Holm, the Wilcoxon p-values ` +
        `are ${daftarN(bedaCI.map(m => n(T.champion_tests.find(t => t.model === m).p_holm, 3)))}, and under ` +
        `Benjamini-Hochberg ${daftarN(bedaCI.map(m => n(T.champion_tests.find(t => t.model === m).p_bh, 3)))}, ` +
        'so whether the gap counts as significant depends on the correction chosen. '
      : '') +
    `Series by series the gap is small. Diebold-Mariano tests find ${nice(top.model)} significantly better ` +
    `than ARIMA on ${dm.ARIMA.juara_lebih_baik} of ${T.n_leaf} series and worse on ${dm.ARIMA.juara_lebih_buruk}, ` +
    `and better than Croston on ${dm.Croston.juara_lebih_baik}. ` +
    'H1 is therefore only weakly supported. The learners lead, but the lead over the best statistical ' +
    'methods is a few per cent and does not hold series by series.'));
  return c;
}

function winnersProse() {
  const w = T.winners, N = T.n_leaf;
  const nML = w.filter(r => r.fam === 'ML').length;
  const cro = T.croston_leaves;
  const c = [];
  c.push(P('Figure 5 shows how much the picture changes from series to series. ' +
    `A learner is the best method on ${kata(nML)} of the ${N} series and a benchmark on the other ` +
    `${kata(N - nML)}, and the best method beats the random walk on ${T.n_beat_rw} of the ${N}. ` +
    'These per-series winners are chosen on the test block itself, so they describe the test block rather ' +
    'than a selection a desk could have made in advance. ' +
    `Croston’s wins, on ${daftarN(cro.map(r => r.leaf))}, come from series with few zeros, where the method ` +
    'reduces to exponential smoothing, so they say nothing about intermittency. ' +
    'Sparsity, measured from each series’ first report, is not related to how hard a series is to forecast ' +
    `either, with a rank correlation of ${n(T.winner_rho_sejak, 2)} (p = ${n(T.winner_p_sejak, 2)}) between ` +
    'the zero share and the best achievable error.'));
  c.push(P(`One series stands apart. ${Object.entries(T.nol_sejak).sort((a, b) => b[1].nol_uji - a[1].nol_uji)[0][0]} ` +
    `is zero on ${n(Object.values(T.nol_sejak).sort((a, b) => b.nol_uji - a.nol_uji)[0].nol_uji, 0)} per cent ` +
    'of the test days, so a forecast of no change is almost always right and every other method loses to ' +
    'the random walk there. Section 3.1 describes why the series is so sparse. The series also shows how ' +
    'a method can be mismatched to the metric. Under absolute error the best forecast for a series that is ' +
    'almost always zero is zero, while Croston’s method forecasts a smoothed average of the non-zero flows, ' +
    `and its MASE on this series is ${n(T.per_leaf_model[T.desk_tanpa.leaf].Croston / T.per_leaf_model[T.desk_tanpa.leaf].Naive, 1)} ` +
    'times that of the random walk.'));
  return c;
}

function ensembleTable() {
  const RK = Object.fromEntries(T.robust.kombinasi.map(r => [r.label, r]));
  const rows = T.ensemble.map(e => [
    e.nama, n(e.mase, 3), n(e.med, 3), ciTeks(RK[e.nama]), pv(e.p_holm), `${e.leaf_lebih_baik} of ${T.n_leaf}`,
    putusan(RK[e.nama]),
  ]);
  return TBL([2900, 900, 900, 1800, 900, 980, 980],
    ['Combination', 'Mean MASE', 'Median MASE', 'Change [95% CI]', 'Holm p', 'Series better', 'Verdict'],
    rows, { rightFrom: 1 });
}

function reverseAblationTable() {
  const RB = Object.fromEntries(T.robust.komponen.map(r => [r.label, r]));
  const rows = T.reverse_ablation.map(a => {
    const rb = RB[a.component];
    return [a.component, n(a.opt, 4), n(a.off, 4), ciTeks(rb), `${rb.a_lebih_baik} / ${rb.a_lebih_baik + rb.b_lebih_baik}`,
      pv(rb.p_holm), putusan(rb, 'different', 'different')];
  });
  return TBL([2300, 1150, 1250, 1900, 1150, 900, 1310],
    ['Component removed', 'MASE with it', 'MASE without it', 'Change [95% CI]', 'Wins for full', 'Holm p', 'Verdict'],
    rows, { rightFrom: 1 });
}

function reverseAblationProse() {
  const RA = T.reverse_ablation, lw = T.reverse_leaf_worse;
  const RB = Object.fromEntries(T.robust.komponen.map(r => [r.label, r]));
  const setara = RA.filter(a => RB[a.component].setara), lain = RA.filter(a => !RB[a.component].setara);
  const tb = T.robust.tuning_bersyarat, nPas = T.n_leaf * 3;
  const PM = T.robust.komponen_per_model;
  const luar = [];
  Object.entries(PM).forEach(([k, v]) => Object.entries(v).forEach(([m, r]) => {
    if (Math.abs(r.delta) > 2) luar.push({ k, m, r });
  }));
  const c = [];
  c.push(P('No component is shown to improve accuracy, and the three nulls differ in kind. ' +
    (setara.length
      ? `For ${daftarN(setara.map(a => NAMA_KOMP[a.component]))} the 90 per cent interval lies within ` +
        '±2 per cent, so pooled effects larger than 2 per cent can be ruled out, while smaller ones cannot be ' +
        'resolved. '
      : '') +
    (lain.length
      ? `For ${daftarN(lain.map(a => NAMA_KOMP[a.component]))} the interval ` +
        `(${daftarN(lain.map(a => `${n(RB[a.component].lo95, 1)} to ${n(RB[a.component].hi95, 1)} per cent`))}) ` +
        'is too wide to decide even at that margin, and it leans towards the pipeline being better without it. '
      : '') +
    `After Holm correction no component differs significantly from the full pipeline, the smallest p-value ` +
    `being ${n(Math.min(...T.robust.komponen.map(r => r.p_holm)), 3)}. H2 is not supported. Across series, ` +
    daftarN(RA.map(a => `${NAMA_KOMP[a.component]} helps ${T.n_leaf - lw[a.component]} of ${T.n_leaf}`)) + '.'));
  c.push(P(`Tuning moved away from configuration 1 in ${tb.n_pasangan} of the ${nPas} series and learner ` +
    `pairs, and in the other ${nPas - tb.n_pasangan} the two arms are identical, which dilutes the pooled ` +
    `effect. Restricted to the ${tb.n_pasangan} pairs that changed, removing tuning changes error by ` +
    `${ciTeks(tb)}, which is equivalent only within ±${Number(Object.entries(tb.setara_margin).find(([, v]) => v)?.[0] ?? 3)} ` +
    'per cent. ' +
    (luar.length
      ? 'The pooled verdicts also need not hold for each learner. ' +
        [...new Set(luar.map(x => x.k))].map(k => `Removing ${NAMA_KOMP[k]} changes the error of ` +
          daftarN(luar.filter(x => x.k === k).map(x => `${NM_POHON[x.m]} by ${pct(x.r.delta, 1)} ` +
            `(90 per cent interval ${nCI(x.r.lo90)} to ${nCI(x.r.hi90)})`)) + '. ').join('')
      : '') +
    'With these settings LightGBM and XGBoost are deterministic, giving identical forecasts whatever the ' +
    'random seed, so their learner-level differences are not seed noise. The random forest was run with ' +
    'a single seed, and part of its differences may be model variance. Appendix G gives every learner separately.'));
  if (!T.robust.komponen.every(r => r.p_holm >= 0.05)) throw new Error('reverseAblationProse: ada komponen nyata setelah Holm');
  return c;
}

function selectorProse() {
  const S0 = T.selector_tests, su = T.slot_uptake_new;
  const S = S0.map(r => ({ ...r, p: T.robust.selektor.find(q => q.label === `k = ${r.k}`).p }));
  const rSel = T.reverse_ablation.find(a => a.component === 'Redundancy-aware selection');
  const c = [];
  c.push(P('Compared directly, at one fit per block and with market data off, the redundancy-aware rule is ' +
    'slightly better than the univariate one at both feature counts, and neither difference is significant ' +
    `(${daftarN(S.map(r => `k = ${r.k}, ${pct(r.delta)}, p = ${n(r.p, 3)}`))}). Inside the tuned and daily ` +
    `re-fitted pipeline, removing it lowered error by ${n(Math.abs(rSel.delta), 2)} per cent. The two ` +
    'experiments disagree in sign, so the effect of the rule on these learners is not identified. ' +
    `The rule also admits more market features than the univariate one, ${n(su.k25_mrmr, 2)} against ` +
    `${n(su.k25_univ, 2)} at 25 features, which follows from the averaged redundancy term. Once many ` +
    'engineered features are chosen, the average dilutes the overlap between a new market lag and its ' +
    'already-chosen neighbours, and Appendix B shows several lags of the same market variable selected ' +
    'together.'));
  if (!S.every(r => r.delta < 0) || !S.every(r => r.p >= 0.05)) {
    throw new Error('selectorProse: arah atau kenyataan uji selektor berubah; tulis ulang kalimatnya');
  }
  return c;
}

function ablationTable() {
  const RK = Object.fromEntries(T.robust.k.map(r => [r.label, r]));
  const rows = abl.map(a => {
    const acuan = a.k === T.ablation_acuan, rk = RK[`k = ${a.k}`];
    return [String(a.k), n(a.mase, 3), n(a.median, 3), acuan ? 'reference' : ciTeks(rk),
      acuan ? '—' : pv(rk.p_holm), acuan ? '—' : n(a.p_leaf, 3)];
  });
  return TBL([900, 1300, 1300, 2400, 1300, 1300],
    ['k', 'Mean MASE', 'Median MASE', 'Change [95% CI]', 'Holm p', 'Series p'],
    rows, { rightFrom: 1, accRows: [abl.findIndex(a => a.k === T.ablation_acuan)] });
}

function ablationProse() {
  const A = T.ablation_acuan;
  const RK = Object.fromEntries(T.robust.k.map(r => [r.label, r]));
  const bawah = abl.filter(r => r.k < A), atas = abl.filter(r => r.k > A);
  const atasBeda = atas.filter(r => RK[`k = ${r.k}`].beda);
  const bawahBeda = bawah.filter(r => RK[`k = ${r.k}`].beda);
  const c = [];
  c.push(P(`Tighter feature sets are worse than ${A} in the mean, by ${n(Math.min(...bawah.map(r => r.delta)), 1)} ` +
    `to ${n(Math.max(...bawah.map(r => r.delta)), 1)} per cent, and larger ones better, by ` +
    `${n(Math.min(...atas.map(r => -r.delta)), 1)} to ${n(Math.max(...atas.map(r => -r.delta)), 1)} per cent. ` +
    `The block-bootstrap interval excludes zero only for ${daftarN([...bawahBeda, ...atasBeda].map(r => `k = ${r.k}`))}, ` +
    `but after Holm correction no count differs significantly from the reference (smallest p = ` +
    `${n(Math.min(...T.robust.k.map(r => r.p_holm)), 3)}), and with the series as the unit none does either, the smallest ` +
    `p-value being ${n(Math.min(...atas.map(r => r.p_leaf)), 3)}. The gain above ${A} is also not shared by ` +
    `every learner. For XGBoost the change at ${daftarN(atas.map(r => String(r.k)))} features is ` +
    `${daftarN(atas.map(r => pct(r.per_model.XGBoost)))}.`));
  c.push(P(`The reading we adopt is that more than ${A} features is at least as good as ${A} one day ahead ` +
    'and may be slightly better, but that the data do not identify a best count. The larger counts were ' +
    `also found on the test block they are reported on, so we keep k = ${A} throughout. H3 is not ` +
    'contradicted, but a count of 25 is not shown to be the right size either.'));
  return c;
}

function marketTable() {
  const RP = Object.fromEntries(T.robust.pasar.map(r => [r.label, r]));
  const rows = T.tabel8b.map(r => {
    const lab = `${r.beta === 1 ? 'mRMR' : 'univariate'}, k = ${r.k}`;
    const q = RP[lab];
    return [r.beta === 0 ? 'univariate' : 'mRMR', String(r.k), n(r.mati, 3), n(r.benar, 3),
      ciTeks(q), `${q.b_lebih_baik} / ${q.a_lebih_baik + q.b_lebih_baik}`, pv(q.p_holm)];
  });
  const g = T.tabel8b_gabungan, q = RP.pooled;
  rows.push(['pooled', '—', n(g.mati, 3), n(g.benar, 3), ciTeks(q),
    `${q.b_lebih_baik} / ${q.a_lebih_baik + q.b_lebih_baik}`, '—']);
  return TBL([1300, 600, 1300, 1300, 2100, 1500, 1260],
    ['Rule', 'k', 'Without market data', 'With market data', 'Change [95% CI]', 'Wins for market data', 'Holm p'],
    rows, { rightFrom: 1 });
}

function marketProse() {
  const RP = T.robust.pasar, Q = T.pasar_kualifikasi;
  const beda = RP.filter(r => r.label !== 'pooled' && r.beda);
  const c = [];
  c.push(P(`Market data do not help on average. Pooled across conditions they raise mean error by ` +
    `${n(RP[0].delta, 1)} per cent, with a 95 per cent interval of ${n(RP[0].lo95, 1)} to ${n(RP[0].hi95, 1)}. ` +
    'The cost is concentrated. Among the four ' +
    `conditions only ${daftarN(beda.map(r => r.label))} ${beda.length > 1 ? 'differ' : 'differs'} clearly ` +
    `from zero (Holm ${daftarN(beda.map(r => pv(r.p_holm)))}), and series by series most of it comes from two cells.`));
  return c;
}

function perLeafTable() {
  const S = T.per_leaf_supplied;
  const rows = T.desc.map(d => {
    const a = S.find(x => x.leaf === d.leaf && x.k === 12), b = S.find(x => x.leaf === d.leaf && x.k === 25);
    return [d.leaf, LABEL[d.leaf], n(a.off, 3), n(a.on, 3), pct(a.delta, 1),
      n(b.off, 3), n(b.on, 3), pct(b.delta, 1), String(b.n_ext)];
  });
  return TBL([700, 1560, 960, 960, 900, 960, 960, 900, 860],
    ['Series', 'Purpose', 'FE, k = 12', 'FE + market, k = 12', 'Change, k = 12',
     'FE, k = 25', 'FE + market, k = 25', 'Change, k = 25', 'Market slots'],
    rows, { rightFrom: 2 });
}

function perLeafProse() {
  const S = T.per_leaf_supplied, Q = T.pasar_kualifikasi;
  const s25 = S.filter(r => r.k === 25);
  const worst = [...s25].sort((a, b) => b.delta - a.delta).slice(0, 2);
  const c = [];
  c.push(P(`At 25 features ${kata(T.n_leaf_membaik)} series are more accurate with market data, ` +
    `${kata(T.n_leaf_memburuk)} are less accurate and ${kata(T.n_leaf_tanpa_slot)} admit no market feature. ` +
    `The average change across series is ${pct(Q['25'].semua, 1)} at 25 features and ` +
    `${pct(Q['12'].semua, 1)} at 12, but without the two worst cells, ` +
    `${daftarN(worst.map(r => `${r.leaf} (${LABEL[r.leaf]}, ${pct(r.delta, 1)})`))}, it falls to ` +
    `${pct(Q['25'].tanpa, 1)} and ${pct(Q['12'].tanpa, 1)}. Both are residual "Other" categories. ` +
    `The cost does not grow with the number of market slots (rank correlation ${n(T.supplied_slot_rho.rho, 3)}, ` +
    `p = ${n(T.supplied_slot_rho.p, 3)}). H4 is not supported on average, and for most series market ` +
    'data make little difference either way.'));
  c.push(NOTE('The market features enter as levels. Levels of the exchange rate or the equity index trend ' +
    'over the sample, and a tree cannot extrapolate beyond the range it was trained on, so a level can act ' +
    'as a proxy for time. Daily changes would be the cleaner specification, and Section 6 lists it.'));
  return c;
}

function famProse() {
  const G = T.shap_per_kelompok, sv = T.shap_dua, sc = T.shap_vs_change;
  const F = sv.famili, RF = F.RandomForest, LG = F.LightGBM;
  const urut = Object.keys(RF);
  const FAMP = { 'Exponentially weighted mean': 'exponentially weighted means', 'Rolling statistics': 'rolling statistics',
    Lag: 'lags', Market: 'market variables', Interaction: 'interaction terms' };
  const fp = k => FAMP[k] || k.toLowerCase();
  const c = [];
  c.push(P(`Pooled across all ${T.n_leaf} series, the random forest draws ${n(RF[urut[0]], 1)} per cent of its ` +
    `importance from ${fp(urut[0])} and ${n(RF[urut[1]], 1)} per cent from ${fp(urut[1])}, ` +
    `and LightGBM ${n(LG[urut[0]], 1)} and ${n(LG[urut[1]], 1)} per cent. Market data carry ` +
    `${n(RF.Market, 1)} per cent for the random forest and ${n(LG.Market, 1)} per cent for LightGBM. ` +
    `Lags take ${n(T.mean_lag_slots, 1)} of the 25 slots on average and market variables ` +
    `${n(T.mean_ext_slots, 1)}, so the models draw their signal mostly from the series’ own recent level, ` +
    'which is partly a consequence of selection. ' +
    'SHAP values were first computed for the random forest, whose averaging over many deep trees gives ' +
    'stable attributions, and Figure 10 adds LightGBM, the leading method, fitted on the same features with ' +
    `its tuned configuration. Both were recomputed in a second environment, which reproduces the published ` +
    `random-forest attributions exactly on ${sv.rf_cocok_vps} of the ${T.n_leaf} series, the rest differing through ` +
    'library versions as Appendix F explains. The two learners agree on which series lean on market data (rank correlation ' +
    `${n(sv.rho_pasar, 2)} across series), while LightGBM gives market variables more weight. These are ` +
    'in-sample attributions, and they describe what the fitted models use, not what improves their forecasts.'));
  const GL = sv.kelompok.LightGBM;
  c.push(P(`The answer to RQ4 is that the market share differs by counterparty group. For the random forest it ` +
    `averages ${n(G.A, 1)} per cent for corporates, ${n(G.C, 1)} per cent for non-residents and ${n(G.B, 1)} per ` +
    `cent for individuals, and for LightGBM ${n(GL.A, 1)}, ${n(GL.C, 1)} and ${n(GL.B, 1)} per cent. ` +
    'Individuals’ flows are explained almost entirely from their own history. The market share of a series ' +
    `does not predict whether market data help its forecast, however (rank correlation ${n(sc.rho, 2)}, ` +
    `p = ${n(sc.p, 2)}).`));
  if (!(sv.rho_pasar > 0.5)) throw new Error('famProse: RF dan LightGBM tidak lagi sepakat; tulis ulang');
  if (!(LG.Market > RF.Market)) throw new Error('famProse: LightGBM tidak lagi memberi bobot pasar lebih besar');
  return c;
}

function deskTable() {
  const tanpa = Object.fromEntries(T.desk_tanpa.rows.map(d => [d.model, d]));
  const rows = T.desk.map(d => [nice(d.model), n(d.rel_mae_geo, 3), n(tanpa[d.model].rel_mae_geo, 3),
    n(d.mae, 1), n(d.bias, 1),
    d.arah == null ? '—' : `${n(d.arah, 1)}${d.pt_p != null && d.pt_p < 0.01 ? '*' : ''}`, n(d.mae_total, 1)]);
  return TBL([1900, 1250, 1350, 1150, 1150, 1300, 1260],
    ['Method', 'Relative MAE', `Relative MAE without ${T.desk_tanpa.leaf}`, 'MAE (USD m)', 'Bias (USD m)',
      'Direction correct (%)', 'MAE of total (USD m)'],
    rows, { rightFrom: 1, accRows: [0] });
}

function deskProse() {
  const D = T.desk, rw = D.find(d => d.model === 'Naive'), J = T.champion_juara;
  const top = D[0], tot = [...D].sort((a, b) => a.mae_total - b.mae_total)[0];
  const TN = T.desk_tanpa, tn = TN.rows, l = TN.leaf;
  const jTn = tn.find(d => d.model === J), kedua = tn[1];
  const lamaKedua = D.find(d => d.model === kedua.model);
  const arahML = D.filter(d => POHON.includes(d.model)).map(d => d.arah);
  const arahTop = [...D].filter(d => d.arah != null).sort((a, b) => b.arah - a.arah);
  const mean = D.find(d => d.model === 'NaiveMean');
  const tidakPT = D.filter(d => d.arah != null && !(d.pt_p < 0.01)).map(d => niceK(d.model));
  const biasKecil = [...D].filter(d => d.model !== 'NaiveDrift').sort((a, b) => Math.abs(a.bias) - Math.abs(b.bias)).slice(0, 2);
  const td = T.topdown, jt = D.find(d => d.model === J), ar = D.find(d => d.model === 'ARIMA');
  const c = [];
  c.push(P(`${nice(top.model)} has the lowest relative MAE, ${n(100 * (1 - top.rel_mae_geo), 0)} per cent below ` +
    `the random walk, and a mean absolute error of ${n(top.mae, 1)} million US dollars against ${n(rw.mae, 1)} ` +
    `for the random walk. Much of that margin comes from ${l}, where every method other than the random walk ` +
    `does badly. Without it ${nice(J)} scores ${n(jTn.rel_mae_geo, 3)} and ${niceK(kedua.model)} ` +
    `${n(kedua.rel_mae_geo, 3)}, so the leader and the best benchmark are level, and ${niceK(kedua.model)} moves ` +
    `from place ${lamaKedua.peringkat} to place ${kedua.peringkat}.`));
  c.push(P(`The direction of change is called correctly more often than chance by every method except ` +
    `${daftarN(tidakPT)}, by the Pesaran-Timmermann test (Pesaran and Timmermann, 1992), pooled over series and ` +
    'ignoring dependence. The margin over a simple baseline is modest, however. The rolling mean is right on ' +
    `${n(mean.arah, 1)} per cent of days, the learners on ${n(Math.min(...arahML), 0)} to ` +
    `${n(Math.max(...arahML), 0)} per cent, and the best score, ${n(arahTop[0].arah, 1)} per cent, belongs to ` +
    `${niceK(arahTop[0].model)}. All methods over-forecast slightly, ${daftarN(biasKecil.map(d => niceK(d.model)))} ` +
    `least. The total of all fifteen series, which is what a desk reports upwards, is forecast best by ` +
    `${niceK(tot.model)}, with a mean absolute error of ${n(tot.mae_total, 1)} million. Forecasting the total ` +
    `directly with ARIMA gives ${n(td.arima, 1)} million, better than summing the ${nice(J)} forecasts ` +
    `(${n(jt.mae_total, 1)}) but not the ${niceK(tot.model)} ones, and the random walk gives ${n(td.rw, 1)}. ` +
    'The best method for the cells is therefore not the best for their sum.'));
  if (top.model !== J) throw new Error('deskProse: juara MASE tidak lagi juara MAE relatif');
  if (!D.every(d => d.bias < 0)) throw new Error('deskProse: tidak semua bias negatif; tulis ulang "over-forecast"');
  if (!(td.arima < jt.mae_total && td.arima > tot.mae_total)) throw new Error('deskProse: urutan top-down berubah');
  if (!(Math.abs(jTn.rel_mae_geo - kedua.rel_mae_geo) < 0.01)) throw new Error('deskProse: tanpa seri jarang, selisih tidak lagi kecil');
  return c;
}

function skalaProse() {
  const S = T.skala_koreksi, j = T.champion_juara;
  const lama = S.peringkat.find(r => r.model === j);
  const bawahSatu = S.peringkat.filter(r => r.baru < 1).map(r => r.model);
  return [P(`Correcting the MASE scale for the ${kata(S.seri.length)} series reported only after the start ` +
    'of the sample, by computing each denominator from the series’ first report, lowers every method’s ' +
    `MASE, that of ${nice(j)} from ${n(lama.lama, 3)} to ${n(lama.baru, 3)}, and leaves the conclusions ` +
    `unchanged. ${nice(S.juara_baru)} still leads, the ranking of the first six methods is the same, ` +
    `${daftarN(bawahSatu.map(niceK))} now average below one, the component effects move by less than half ` +
    `a percentage point, and the market-data cost becomes ${n(S.pasar, 1)} per cent. The statement that no ` +
    'method beats the in-sample scale is therefore an artefact of the structural zeros, while the ' +
    'comparisons between methods are not. Computing the scale from 2022 onwards for every series, which ' +
    'removes the January 2022 break from the denominator, lowers the random walk from ' +
    `${n(T.skala_2022.rw_lama, 3)} to ${n(T.skala_2022.rw, 3)} and leaves the first four places unchanged.`)].concat((() => {
    const a4 = T.skala_2022.peringkat.slice(0, 4).map(r => r.model).join();
    const b4 = [...S.peringkat].sort((a, b) => a.lama - b.lama).slice(0, 4).map(r => r.model).join();
    if (a4 !== b4) throw new Error('skalaProse: empat teratas berubah dengan skala 2022');
    const lamaUrut = [...S.peringkat].sort((a, b) => a.lama - b.lama).slice(0, 6).map(r => r.model).join();
    const baruUrut = [...S.peringkat].sort((a, b) => a.baru - b.baru).slice(0, 6).map(r => r.model).join();
    if (lamaUrut !== baruUrut) throw new Error('skalaProse: urutan enam teratas berubah');
    const geser = T.reverse_ablation.map(a => Math.abs(S.komponen[a.component] - a.delta));
    if (Math.max(...geser) >= 0.5) throw new Error('skalaProse: efek komponen bergeser >= 0,5 poin');
    return [];
  })());
}

function synthProse() {
  const mcs = T.mcs.tersisa, g = T.tabel8b_gabungan, J = T.champion_juara, D = T.desk;
  const tot = [...D].sort((a, b) => a.mae_total - b.mae_total)[0];
  const arah = [...D].filter(d => d.arah != null).sort((a, b) => b.arah - a.arah);
  const arahAtas = arah.filter(d => d.arah > D.find(x => x.model === J).arah).map(d => niceK(d.model));
  const e1 = [...T.e1_summary].sort((a, b) => a.mase - b.mase)[0];
  const tn = T.desk_tanpa.rows;
  return [
    P(`The learners are a reasonable default and not a proven improvement. ${nice(J)} leads on mean MASE and ` +
      `relative MAE, but not on every measure. ${Kata1(niceK(tot.model))} has the lowest error on the daily ` +
      `total, ${daftarN(arahAtas)} call the direction of change more often, ` +
      (e1.model !== J ? `${niceK(e1.model)} leads on the single test date of Appendix A, ` : '') +
      `and without ${T.desk_tanpa.leaf} ${niceK(tn[1].model)} is level with it. The best statistical methods ` +
      `stay in the ${kata(mcs.length)}-method confidence set, no combination does better, and the best method ` +
      'changes from series to series.'),
    P('The machinery around the learner contributes little that this design can measure. For daily ' +
      're-fitting and tuning, pooled effects larger than 2 per cent can be ruled out, but smaller ones ' +
      'cannot be resolved, and per learner, or on the series where tuning changed the configuration, ' +
      'effects of up to about 3 per cent remain possible. For the selection rule not even the 2 per cent ' +
      'margin can be established. The feature count leans towards more features rather than fewer. Market ' +
      `data cost ${n(g.delta_benar, 1)} per cent on average, most of it in two residual cells.`),
    P('These are statements about a six-week window. They describe a problem with a low ceiling, in which ' +
      'the recent level of each series carries most of the predictable signal. The window resolves ' +
      'differences of a few per cent but not smaller ones, and a longer evaluation could change the verdict ' +
      'on any single component.'),
  ];
}

function kotakPitfall() {
  const g = T.tabel8b_gabungan, A = T.slot_damage;
  return [BOX('Box 1. Features withheld at prediction', [
    'In the earlier 30-origin design of Appendix A, with market data as levels, the forecasters built their ' +
    'features afresh at prediction time, and in the first ' +
    'version the routine that does so could not accept the market series. The model was trained on market ' +
    'features and then received zeros in their place when it forecast, with no error or warning. Practitioners ' +
    'call this training-serving skew. It is one form of the hidden dependencies between data and code that ' +
    'Sculley et al. (2015) describe as technical debt in machine-learning systems.',
    `The effect was large. Market data appeared to raise pooled error by ${n(g.delta_nol, 1)} per cent, ` +
    `against ${n(g.delta_benar, 1)} per cent once the features were supplied, so ` +
    `${n(g.rusak_hilang_pct, 0)} per cent of the apparent cost was the handling. The tell-tale sign was that ` +
    `the damage grew with the number of market features selected (rank correlation ${n(A.nol.rho, 3)}) and ` +
    `vanished once they were supplied (${n(A.benar.rho, 3)}). Appendix C gives the details.`,
    'Zero-filling is never the right default. One day ahead the lagged values are known and should be ' +
    'supplied. Several days ahead, a direct formulation that uses only lags at least as long as the horizon, ' +
    'or forecasts of the market series themselves, avoids the problem.',
  ])];
}

function batasan() {
  return [
    'The test block has 30 consecutive days, about 0.6 per cent of the sample, in a single regime. Pooled differences of a few per cent can be detected or excluded, but smaller ones cannot, and per-learner effects are less precise still.',
    'The ±2 per cent equivalence margin was chosen after the results were seen. Appendix G shows which verdicts change at ±1 and ±3 per cent.',
    'The validation block lies immediately before the test block and also covers one regime. Tuning chosen on it need not suit the test period.',
    'The p-values treat series-date units as independent. The block bootstrap and the per-series tests address this in part, but with 30 dates the intervals are wide.',
    'Four series have years of structural zeros before their first report, which the models were trained on. Section 4.7 corrects the evaluation scale for this but not the training data.',
    'Training uses an expanding window from 2006, across changes in reporting and foreign-exchange regulation, such as the January 2022 shift in the export series described in Section 3.1. A sliding window may suit some series better, and this was not tested.',
    'The learners minimise squared error while the evaluation uses absolute error. The random forest was run with one random seed, so part of its differences between arms may be model variance, while LightGBM and XGBoost are deterministic with these settings.',
    'Market data enter as levels, bid and ask quotes enter as near-duplicate pairs, and the selection rule neither excludes near-duplicates reliably nor favours calendar effects, as Section 3.3 explains.',
    'Only one horizon, one jurisdiction and one reporting framework are studied. Appendix E sets out how the exchange-rate regime might shape the market-data results.',
  ];
}

function conclProse() {
  const g = T.tabel8b_gabungan, mcs = T.mcs.tersisa;
  return [P(`We forecast ${T.n_leaf} disaggregated foreign-exchange flow series one business day ahead with a ` +
    'machine-learning pipeline and seven statistical benchmarks, and took the pipeline apart one component ' +
    `at a time. ${nice(T.champion_juara)} leads, but a 90 per cent confidence set retains ` +
    `${kata(mcs.length)} methods, including ${daftarN(mcs.filter(m => !POHON.includes(m)).map(niceK))}. ` +
    'For daily re-fitting and tuning, pooled effects larger than 2 per cent can be ruled out, the effect of ' +
    'the selection rule is unresolved, and more features tend to help rather than fewer. Market data cost ' +
    `${n(g.delta_benar, 1)} per cent on average, concentrated in two cells, and a silent handling default ` +
    'had nearly turned that into a much larger apparent penalty. The value of the study for practice is less ' +
    'in any single ranking than in the discipline it illustrates, namely testing each component by removal, ' +
    'reporting equivalence as well as significance, and checking what a forecaster actually receives.')];
}

function appendixTable() {
  const byLeaf = {};
  T.e1.forEach(r => { if (!byLeaf[r.leaf] || r.mase < byLeaf[r.leaf].mase) byLeaf[r.leaf] = r; });
  const rows = T.desc.map(d => [d.leaf, LABEL[d.leaf], nice(byLeaf[d.leaf].model), n(byLeaf[d.leaf].mase, 3)]);
  return TBL([900, 2600, 3000, 2860], ['Series', 'Purpose', 'Best method', 'MASE'], rows, { rightFrom: 3 });
}

function appendixZeroFill() {
  const c = [];
  c.push(H1('Appendix C. The Zero-Fill Experiment'));
  c.push(P('This experiment belongs to the earlier 30-origin design of Appendix A, with market data as levels. ' +
    'Table C1 and Figures C1 and C2 compare three arms, namely market data off, market data supplied ' +
    'at training but zero-filled at prediction, and market data supplied at both, as summarised in Box 1.'));
  c.push(TCAP('C1', 'Market data off, zero-filled at prediction and supplied at prediction, pooled across the ' +
    'three learners. "Recovered" is the share of the zero-filled penalty that disappears once the features ' +
    'are supplied. The last column tests the zero-filled arm against market data off on series-date units, ' +
    'Holm-corrected across the four conditions (unadjusted for the pooled row).'));
  c.push(suppliedTable());
  c.push(IMG('fig6b_pasar_benar.png', 560, 212));
  c.push(FCAP('C1', 'Mean MASE for the three arms (left) and each market arm as a penalty against the ' +
    'no-market baseline (right).'));
  c.push(IMG('fig11_slot_damage.png', 560, 220));
  c.push(FCAP('C2', 'Penalty against the number of market slots, series by series at 25 features, with the ' +
    'features zero-filled (left) and supplied (right).'));
  const A = T.slot_damage;
  c.push(P(`With the features zero-filled, the penalty rose with the number of market slots (rank correlation ` +
    `${n(A.nol.rho, 3)}, p < 0.001). Once they were supplied the relationship vanished (${n(A.benar.rho, 3)}, ` +
    `p = ${n(A.benar.p, 3)}), and the ${kata(T.n_leaf_tanpa_slot)} series without market slots were ` +
    'unchanged in all three arms. A story in which market data are simply uninformative would survive the ' +
    'correction, since crowding out happens at selection, so the zero-fill is the mechanism.'));
  return c;
}

function appendixFitur() {
  const c = [];
  c.push(H1('Appendix D. The Feature Pool'));
  c.push(TCAP('D1', `The ${T.pool_internal} engineered candidates, by family.`));
  c.push(TBL([2600, 800, 5960], ['Family', 'Count', 'Features'],
    T.daftar_fitur.map(g => [g.kelompok, String(g.fitur.length), g.fitur.join(', ')]), { rightFrom: 99 }));
  return c;
}

function appendixRezim() {
  const SF = T2.shap ? T2.shap.famili : null;
  const extRF = SF ? (SF['ubah|RandomForest'].Market || 0) : 0, extLG = SF ? (SF['ubah|LightGBM'].Market || 0) : 0;
  const c = [];
  c.push(H1('Appendix E. Exchange-Rate Regimes and Market Data'));
  c.push(P('Every market-data result here is conditional on the regime. Many emerging-market central banks ' +
    'that describe their currencies as floating limit their movement in practice (Calvo and Reinhart, 2002), ' +
    'and intervention in emerging markets is regular and often effective (Menkhoff, 2013; Fratzscher et al., ' +
    '2019). When the central bank leans against pressure, part of the private flow is absorbed by its own ' +
    'transactions and the rate moves less than the flow alone would imply, which weakens the link from prices ' +
    'to next-day private flows that market features rely on. Three conjectures follow.'));
  c.push(...BUL([
    `**Regime depth.** In a deep free-floating market, lagged prices should carry more information about next-day flows, and the market share of importance, ${n(extRF, 1)} per cent for the random forest and ${n(extLG, 1)} per cent for LightGBM here, should be larger.`,
    '**Counterparty sensitivity.** Market variables should matter most for counterparties that trade on prices. In this panel the largest market share with daily changes is for individuals, notably B.2, transactions without underlying documents, rather than for non-resident portfolio investors, while non-resident investment (C.1) admits no market feature in its final model, possibly because its flows are dominated by government bond transactions with their own drivers. Retail flows that respond to recent exchange-rate moves would fit a managed float in which the rate itself moves little from day to day, and Menkhoff et al. (2016) find that individual investors trade as contrarians to past currency returns, while the flows of corporations and individuals carry little information about future rates.',
    '**Policy episodes.** Around interventions and macroprudential measures the importance of market variables should shift, which could be tested with SHAP values and test origins placed inside and outside such episodes.',
  ]));
  return c;
}

function appendixRepro() {
  const v = T.versi, r = T.repro, v2 = T2.versi || {}, vl = T2.versi_lokal || {};
  return [H1('Appendix F. Reproducibility'), P(
    `The main results were computed under Python ${v2.python}, NumPy ${v2.numpy}, pandas ${v2.pandas}, SciPy ` +
    `${v2.scipy}, scikit-learn ${v2.sklearn}, LightGBM ${v2.lightgbm}, XGBoost ${v2.xgboost}, statsmodels ` +
    `${v2.statsmodels} and Prophet ${v2.prophet}, one thread per process. Ridge regression, after the guards ` +
    `described in Section 3.4 were added, and the SHAP values of Section 4.6 were recomputed under Python ` +
    `${vl.python}, NumPy ${vl.numpy}, pandas ${vl.pandas}, scikit-learn ${vl.sklearn}, LightGBM ${vl.lightgbm}, XGBoost ${vl.xgboost} and SHAP ${vl.shap}, ` +
    'as were the ridge variants and loss functions of Sections 4.1 and 4.3. The code that ' +
    'produced the main results reproduces the forecasts of the earlier pipeline exactly when run on that ' +
    'pipeline’s design in the same environment.'), P(
    `The earlier 30-origin results were produced under Python ${v.python}, NumPy ${v.numpy}, pandas ${v.pandas}, SciPy ${v.scipy}, ` +
    `scikit-learn ${v.sklearn}, LightGBM ${v.lightgbm}, XGBoost ${v.xgboost}, statsmodels ${v.statsmodels}, ` +
    `Prophet ${v.prophet} and SHAP ${v.shap}, with computation pinned to one thread. ARIMA order selection is ` +
    'sensitive to floating-point summation order. In an earlier run, changing the thread count moved ' +
    `${r.arima_utas_berbeda.sel_bergeser} of ${r.arima_utas_berbeda.n_sel} ARIMA forecasts and shifted its ` +
    `pooled mean from ${n(r.arima_utas_berbeda.mean_empat_utas, 4)} to ${n(r.arima_utas_berbeda.mean_satu_utas, 4)}, while with one ` +
    'thread two complete re-runs were bit-identical. Re-computing SHAP under a different library stack ' +
    `reproduced ${r.shap_lintas_lingkungan.n_leaf_cocok} of ${r.shap_lintas_lingkungan.n_leaf} series exactly, ` +
    'so replication should pin the library versions as well as the threads.')];
}

function appendixInferensi() {
  const RB = T.robust;
  const ya = b => (b ? 'yes' : 'no');
  const ci = (a, b) => `[${nCI(a)}, ${nCI(b)}]`;
  const baris = (grup, r, label) => [grup, label ?? r.label, ciTeks(r),
    `${n(r.hl, 3)} [${n(r.hl_lo, 3)}, ${n(r.hl_hi, 3)}]`,
    ci(...r.blok_sens['2'].slice(0, 2)), ci(...r.blok_sens['10'].slice(0, 2)),
    ['1.0', '2.0', '3.0'].map(m => ya(r.setara_margin[m])).join(' / ')];
  const rows = [
    ...RB.komponen.map(r => baris('Component removed', r)),
    baris('Component removed', RB.tuning_bersyarat, 'Tuned hyperparameters, changed pairs only'),
    ...RB.k.map(r => baris('Feature count vs 25', r)),
    ...RB.kombinasi.map(r => baris('Combination vs leader', r)),
    ...RB.pasar.map(r => baris('Market data on vs off', r)),
    ...RB.selektor.map(r => baris('mRMR vs univariate', r)),
  ];
  const lebar = rows.map(r => {
    const w = s => { const m = s.match(/\[(-?[\d.]+), (-?[\d.]+)\]/); return m ? +m[2] - +m[1] : NaN; };
    return [w(r[2].replace(/^[^[]*/, '')), w(r[4]), w(r[5])];
  });
  const rasio = lebar.map(([a, b, c]) => Math.max(b / a, c / a)).filter(Number.isFinite);
  const c = [];
  c.push(H1('Appendix G. Robustness of the Inference'));
  const semua = [...RB.komponen, RB.tuning_bersyarat, ...RB.k, ...RB.kombinasi, ...RB.pasar, ...RB.selektor];
  const nol = (lo, hi) => lo > 0 || hi < 0;
  const pindah = semua.filter(r => ['2', '10'].some(b => nol(r.blok_sens[b][0], r.blok_sens[b][1]) !== r.beda)).length;
  const ragu2 = semua.filter(r => !r.setara_margin['2.0'] && !r.beda);
  const jadi3 = ragu2.filter(r => r.setara_margin['3.0']).length;
  const setara1 = semua.filter(r => r.setara_margin['1.0']).length;
  c.push(P('Table G1 repeats every pooled comparison with the Hodges-Lehmann shift, the effect size that ' +
    'matches the Wilcoxon test, in MASE units, with block-bootstrap intervals for blocks of two and ten ' +
    'days instead of five, and with the equivalence verdict at margins of ±1, ±2 and ±3 per cent. The ' +
    `intervals are of similar width for every block length, the widest being ${n(Math.max(...rasio), 1)} times ` +
    `the five-day interval, although for ${kata(pindah)} of the ${semua.length} comparisons, all with intervals ` +
    'close to zero, the block length decides whether the interval excludes zero. The margin matters more. ' +
    (setara1 === 0 ? 'At ±1 per cent no comparison is equivalent' : `At ±1 per cent ${kata(setara1)} comparisons are equivalent`) +
    `, and at ±3 per cent ${kata(jadi3)} of the ${ragu2.length} comparisons that are inconclusive at ±2 per ` +
    'cent become equivalent. Table G2 gives the component effects for each learner.'));
  c.push(TCAP('G1', 'Robustness of the pooled comparisons. Change and intervals in per cent of mean MASE, ' +
    'Hodges-Lehmann shift in MASE units. The last column gives the equivalence verdict at ±1, ±2 and ±3 per cent.'));
  c.push(TBL([1500, 2100, 1650, 1700, 950, 950, 1110],
    ['Family', 'Comparison', 'Change [95% CI]', 'Hodges-Lehmann [95% CI]', 'CI, 2-day blocks', 'CI, 10-day blocks', 'Equivalent at ±1 / ±2 / ±3'],
    rows, { rightFrom: 2 }));
  const PM = RB.komponen_per_model;
  const rows2 = [];
  Object.entries(PM).forEach(([k, v]) => URUT_POHON.forEach(m => {
    const r = v[m];
    rows2.push([k, nice(m), ciTeks(r), ci(r.lo90, r.hi90), pv(r.p), putusan(r, 'different', 'different')]);
  }));
  c.push(TCAP('G2', 'Component effects by learner, 450 series-date units each. A positive change means the ' +
    'full pipeline is better. Unadjusted Wilcoxon p-values.'));
  c.push(TBL([2500, 1300, 1900, 1500, 1000, 1160],
    ['Component removed', 'Learner', 'Change [95% CI]', '90% CI', 'Wilcoxon p', 'Verdict'], rows2, { rightFrom: 2 }));
  return c;
}

function appendixBeeswarm() {
  /* Satu beeswarm per seri. Dilewati seluruhnya kalau gambarnya tidak lengkap:
     lampiran yang memuat sebagian seri tanpa mengatakan seri mana yang hilang
     lebih menyesatkan daripada tidak ada lampiran. */
  const dir = FIG + 'beeswarm' + path.sep;
  const leafs = Object.keys(T.shap_per_leaf).sort();
  const ada = leafs.filter(l => fs.existsSync(dir + l + '.png'));
  if (ada.length !== leafs.length) {
    console.warn(`  Lampiran B dilewati: ${ada.length} dari ${leafs.length} `
      + `beeswarm ada di ${dir}`);
    return [];
  }
  const share = Object.fromEntries(T.shap_ext_share.map(r => [r.leaf, r.share]));
  const c = [];
  c.push(H1('Appendix B. Feature contributions, series by series'));
  c.push(P('Figure 9 shows how the 25 selected features divide between market variables, own lags and ' +
    'everything else, and how much of the fitted importance the market variables carry. ' +
    'It cannot show direction, and the beeswarms below can. Each dot is one of the last 300 training days, ' +
    'placed by that feature’s contribution to the predicted next-day flow in millions of US dollars, and ' +
    'coloured by whether the feature value was low (blue) or high (red) that day. ' +
    'Feature names in orange are market variables, and names in black are engineered from the series’ own ' +
    'history. A wide spread means the feature moves the forecast from day to day, while a narrow band ' +
    'around zero means it is carried in the model and does almost nothing.'));
  c.push(NOTE('These are the fourteen highest-importance features of the 25 selected, ordered by mean ' +
    'absolute SHAP value. A series can therefore show fewer market rows here than its market slot count ' +
    'in Figure 9, which means the remaining market features rank below the fourteenth.'));
  ada.forEach((l, i) => {
    const v = T.shap_per_leaf[l];
    c.push(IMG('beeswarm' + path.sep + l + '.png', 520, 282));
    c.push(FCAP(`B${i + 1}`, `${l} (${LABEL[l]}, ${ACTOROF(l)}). ` +
      `The selector kept ${v.n_ext} market feature${v.n_ext === 1 ? '' : 's'} and ${v.n_lag} own ` +
      `lag${v.n_lag === 1 ? '' : 's'} of 25, and market variables carry ${n(share[l] ?? 0, 1)} per cent of ` +
      'total absolute SHAP value.'));
  });
  return c;
}

/* ====================================================================== v2
   Badan naskah sejak review ketiga: jalan ulang v2 (250 origin). Semua angka
   dari tables_v2.json; desain 30 origin lama tinggal di Lampiran A. */
function lossTeks() {
  const L = T2.l1, LL = T2.l1_lain, c = [];
  if (!L) return c;
  const rid = rk2().find(r => r.model === 'Ridge');
  const per = Object.entries(L.per_seri).sort((a, b) => a[1] - b[1]);
  const kw = Object.entries(L.kuartal), nKw = kw.filter(([, v]) => v.l1 < v.ridge).length;
  c.push(H3('Training on the loss the forecasts are judged by'));
  c.push(P('The learners above minimise squared error, which targets the conditional mean, while MASE scores ' +
    'absolute error, which the conditional median minimises. For flows that are skewed and punctuated by ' +
    'large settlements the two can differ a good deal. We therefore re-trained LightGBM on absolute loss and ' +
    'on Huber loss, and XGBoost on absolute loss, with the same features and configurations. To see whether ' +
    'any gain belongs to the trees or to the loss, we also replaced ridge regression by its absolute-loss ' +
    'counterpart, a linear median regression on the same 25 features with the same guards. These variants ' +
    'were added after the main results had been seen. Table 5c reports them against ridge regression, the ' +
    'leader of Table 5.'));
  const baris = [['Ridge regression (Table 5)', n(rid.mase, 3), 'reference', '—']];
  const tambah = (lab, r, m) => baris.push([lab, n(m, 3), ciTeks(r), pv(r.p)]);
  if (LL) tambah('XGBoost, absolute loss', LL.xgb_vs_ridge, LL.xgb.mase);
  tambah('LightGBM, absolute loss', L.vs_ridge, L.mase);
  if (LL) tambah('Linear median regression', LL.median_lin, LL.median_lin.mase);
  c.push(TCAP('5c', 'Methods trained on absolute loss, against ridge regression. A negative change means the ' +
    'method is more accurate than ridge regression. The interval is a 95 per cent block-bootstrap interval and ' +
    'p is the paired Wilcoxon p-value.' +
    (LL ? ` The linear median regression needed a very small L1 penalty to converge at ${LL.n_cadangan} of the ${fmtN(T2.n_leaf * T2.nroll)} origins.` : '')));
  c.push(TBL([4200, 1300, 2300, 1560], ['Method', 'Mean MASE', 'Change [95% CI]', 'p'], baris, { rightFrom: 1, accRows: [0] }));
  const LV = T2.loss_varian;
  c.push(P('Every method improves when it is trained on absolute loss. Against its squared-error version, ' +
    `LightGBM changes by ${ciTeks(LV[0])} on absolute loss and by ${ciTeks(LV[1])} on Huber loss` +
    (LL ? `, XGBoost by ${ciTeks(LL.xgb)}, and the linear model by ${ciTeks(LL.median_lin)} against ridge regression. ` : '. ') +
    (LL
      ? `XGBoost on absolute loss has the lowest mean MASE in the study, ${n(LL.xgb.mase, 3)}, ` +
        `${n(-LL.xgb_vs_ridge.delta, 1)} per cent below ridge regression and ${n(-LL.xgb_vs_median.delta, 1)} per ` +
        `cent below the median of all methods (${ciTeks(LL.xgb_vs_median)}), and LightGBM on absolute loss follows ` +
        `at ${n(L.mase, 3)}. When the four absolute-loss methods are added to the model confidence set, it ` +
        `retains ${daftarN(LL.mcs.tersisa.map(m => m.replace(/ \((absolute|Huber) loss\)/, ' on $1 loss').replace('Linear median', 'the linear median')))} and ` +
        `excludes every squared-error method with p-values of ${n(Math.max(...Object.entries(LL.mcs.p).filter(([m]) => !LL.mcs.tersisa.includes(m)).map(([, v]) => v)), 3)} or less. `
      : `Its mean MASE of ${n(L.mase, 3)} is ${n(-L.vs_ridge.delta, 1)} per cent below ridge regression. `)));
  if (LL) c.push(P('Most of the gain therefore comes from the loss rather than from the trees. Against the linear ' +
    `median regression, XGBoost on absolute loss changes mean MASE by ${ciTeks(LL.xgb_vs_median_lin)} and LightGBM ` +
    `on absolute loss by ${ciTeks(LL.l1_vs_median_lin)}, but the paired rank tests give p = ` +
    `${n(LL.xgb_vs_median_lin.p, 2)} and ${n(LL.l1_vs_median_lin.p, 2)}, so the trees’ edge lies in the mean, ` +
    'not on a typical day. Trained on the ' +
    'right loss, the trees keep a small advantage over a linear model on the same features, about one to two ' +
    'per cent, that they do not have under squared loss.'));
  c.push(P(`Across series the gain is uneven. LightGBM on absolute loss is ahead of ridge regression in ` +
    `${kata(nKw)} of the ${kata(kw.length)} quarters and on ${L.seri_lebih_baik_dari_ridge} of the ` +
    `${T2.n_leaf} series, but against squared-error LightGBM its largest gains are on ${per[0][0]} ` +
    `(${pct(per[0][1], 0)}) and ${per[1][0]} (${pct(per[1][1], 0)}), and series-by-series Diebold-Mariano tests ` +
    `find it better than ridge regression on ${L.dm_vs_ridge.l1_lebih_baik ? `${L.dm_vs_ridge.l1_lebih_baik} series` : 'no series'} ` +
    `and worse on ${L.dm_vs_ridge.ridge_lebih_baik}. The pooled lead is real, but it rests on a few series where ` +
    'squared loss is badly suited, and on most series the methods cannot be told apart.'));
  return c;
}

function ridgeVarianTeks() {
  const RV = T2.ridge_varian;
  const RP = T2.ridge_tanpa_penjaga;
  let t = '';
  if (RV) {
    const lag = RV.find(r => r.label.startsWith('Own lags')), kal = RV.find(r => r.label.startsWith('Calendar')),
      all = RV.find(r => r.label.startsWith('All'));
    t += `To locate the source of the linear model’s accuracy, Table 5b varies its features. On the series’ own ` +
      `eighteen lags alone, which makes it essentially a linear autoregression, ridge regression is ` +
      `${lag.delta > 0 ? 'worse' : 'better'} by ${n(Math.abs(lag.delta), 1)} per cent (${ciTeks(lag)}), so ` +
      (lag.beda && lag.delta > 0
        ? 'the engineered features beyond plain lags do carry accuracy, and that part of the pipeline earns its place. '
        : 'the engineered features add little beyond plain lags. ') +
      `Entering the calendar as dummies instead of integers changes it by ${pct(kal.delta, 1)}, and using all ` +
      `${T.pool_internal} candidates by ${pct(all.delta, 1)}. `;
  }
  if (RP) {
    t += `Without the two guards described in Section 3.4, which were added after its first run, ridge ` +
      `regression produced one forecast of the wrong order of magnitude (${RP.leaf_terburuk}) and a mean MASE of ` +
      `${n(RP.mase, 0)}. Excluding that one forecast its mean MASE is ${n(RP.mase_tanpa_satu, 3)}, ` +
      `${pct(RP.banding_lgbm_tanpa_satu, 1)} against LightGBM, and the guards changed ${RP.n_berubah} of its ` +
      `${fmtN(RP.n)} forecasts. `;
  }
  return t;
}

function desain32() {
  const c = [];
  const rw = rk2().find(r => r.model === 'Naive');
  c.push(H2('3.2. Evaluation Design'));
  c.push(P(`Every method is evaluated over ${NR2()} consecutive one-day origins, from ${tgl2(T2.tgl_uji_awal)} to ` +
    `${tgl2(T2.tgl_uji_akhir)}, about a year of business days (Figure 3). At each origin every model is ` +
    're-fitted on the actual history up to the day before and forecasts one day ahead. A validation block of ' +
    `${T2.nval} origins, from ${tgl2(T2.tgl_val_awal)}, precedes the test block and is used only for tuning and ` +
    'for choosing methods per series. Each origin uses the previous day’s actual value. This matches ' +
    'practice, because the reports for a given day are complete before the forecast for the next day is made.'));
  c.push(IMG('fig2_design_v2.png', 560, 114));
  c.push(FCAP(3, `The evaluation design. Training starts at each series’ first report, the validation block has ` +
    `${T2.nval} origins and the test block ${NR2()}, each re-fitted on the history up to the day before.`));
  c.push(P('Training for each series starts at its first report, so the years of structural zeros before A.2.b, ' +
    'B.b and C.b entered the reporting framework, and the year before C.d did, are not part of any training ' +
    'sample. The same sample fixes the MASE scale. On this scale the random walk scores a mean MASE of ' +
    `${n(rw.mase, 3)}, and computed from 2022 onwards the scale gives ${n(rw.mase_2022, 3)}, so the test year ` +
    'is more volatile than the training history on either reading. Appendix A reports an earlier design with ' +
    'a 30-day test block, which the present design replaces.'));
  return c;
}

function pasar33() {
  return [P(`Where market data are tested they enter in two forms. In the main form, six variables enter as ` +
    'daily changes, namely the log returns of the spot and one-month NDF mid quotes (the mean of bid and ' +
    'ask), the change in the ten-year bond yield, the log returns of the dollar index and the equity index, ' +
    'and net non-resident equity flows, which are already flows. In the second form the eight original ' +
    `variables enter as levels, with bid and ask separately. Each variable enters as ${kata(T.lag_pasar.length)} ` +
    `lags, one to ${kata(T.lag_pasar[T.lag_pasar.length - 1])} days, and a ${kata(T.rata_pasar)}-day rolling ` +
    'mean. No contemporaneous market value enters the model, and the market candidates compete with the ' +
    'engineered ones for the same fixed number of slots.')];
}

function gridTable2() {
  const CFG = {
    RandomForest: ['100 trees, depth 10', '300 trees, depth 10', '300 trees, no depth limit', '100 trees, depth 4'],
    LightGBM: ['100 trees, rate 0.05, depth 5', '400 trees, rate 0.02, depth 5', '100 trees, rate 0.10, depth 3', '400 trees, rate 0.05, depth 8'],
    XGBoost: ['100 trees, depth 5, rate 0.05', '400 trees, depth 5, rate 0.02', '100 trees, depth 3, rate 0.10', '400 trees, depth 8, rate 0.05'],
  };
  const rows = L2.map(m => [nice(m), ...CFG[m].map((t, i) => `${t} (${T2.cfg_terpilih[m][i]})`)]);
  return TBL([1500, 1965, 1965, 1965, 1965],
    ['Learner', 'Configuration 1', 'Configuration 2', 'Configuration 3', 'Configuration 4'], rows, { rightFrom: 99 });
}

function sisaV2(acuanK) {
  const c = [];
  const J = juara2(), M = BJ(), rk = rk2();
  const sR = T2.seed_rf;

  /* ----------------------------------------------- 3.3 learners */
  c.push(H3('Learners, tuning and re-fitting'));
  c.push(P('Three tree ensembles are fitted on the selected features. Random forest averages bagged ' +
    'regression trees (Breiman, 2001). LightGBM (Ke et al., 2017) and XGBoost (Chen and Guestrin, 2016) fit ' +
    `gradient-boosted trees. Every learner keeps k = ${acuanK} features, and Section 4.4 tests that choice. The ` +
    'learners are trained on squared error, while accuracy is measured by absolute scaled error.'));
  c.push(P('The training loss is the measure of error that a learner minimises when it is fitted, and it ' +
    'decides what the learner forecasts. Squared error, the sum of squared forecast errors, is minimised by ' +
    'the conditional mean, so a few large values pull the forecast toward them. Absolute error, the sum of ' +
    'absolute forecast errors, is minimised by the conditional median and is little affected by such values. ' +
    'Huber loss is squared for small errors and absolute for large ones, a compromise between the two ' +
    '(Huber, 1964). For a series that is zero on most days but has occasional large settlements, the mean is ' +
    'a small positive number every day while the median is zero. Because MASE scores absolute error, a ' +
    'learner trained on squared error pursues a target that differs from the one it is judged by. Section 4.1 ' +
    're-trains the learners on absolute and Huber loss, a test added after the main results.'));
  c.push(P(`Hyperparameters are tuned for each series and learner separately over the four configurations in ` +
    `Table 3, on the ${T2.nval}-origin validation block, with daily re-fitting, and the configuration with the ` +
    'lowest mean scaled error is carried forward unchanged. Random forest is run with three random seeds and ' +
    'its forecasts are averaged. With these settings LightGBM and XGBoost are deterministic, giving identical ' +
    `forecasts whatever the seed. Across the three seeds random-forest accuracy differs by ` +
    `${n(sR.rentang_persen, 2)} per cent, so seed variation is negligible at the level of this study.`));
  c.push(TCAP(3, 'Hyperparameter grid. Configuration 1 is the default of the institution’s production system, ' +
    `not the library default. The number in brackets is how many of the ${T2.n_leaf} series selected that configuration.`));
  c.push(gridTable2());

  /* ----------------------------------------------- 3.4 benchmarks */
  c.push(H2('3.4. Comparison Methods'));
  c.push(P('Eleven methods serve as comparisons (Table 4), each fitted on the same training data and scored on ' +
    'the same origins as the tree ensembles. Ten are univariate statistical benchmarks that use only the ' +
    'series’ own past. The eleventh, ridge regression on the same selected features as the trees, is itself ' +
    'a machine-learning model, a regularised linear learner that shares the pipeline’s features and selection ' +
    'but not its nonlinearity, so comparing it with the trees isolates what the trees add. Two pairs of ' +
    'benchmarks turn out to give nearly identical forecasts, ETS and Theta, and the random walk with and ' +
    'without drift, so the fourteen methods are effectively twelve.'));
  c.push(TCAP(4, 'The eleven comparison methods.'));
  c.push(TBL([2200, 1500, 5660], ['Method', 'Family', 'What it does'], [
    ['Random walk', 'Naive', 'Forecast equals yesterday.'],
    ['Random walk with drift', 'Naive', 'Yesterday plus the average change over the training history.'],
    ['Rolling mean', 'Naive', 'Mean of the last 90 days.'],
    ['Seasonal naive', 'Naive', 'The value five business days earlier, the same weekday a week before.'],
    ['Croston', 'Intermittent', 'Croston’s method (Croston, 1972) in the bias-corrected form of Syntetos and Boylan (2005), with α = 0.1, applied to the signed flow. On a series without zeros it equals 0.95 times simple exponential smoothing.'],
    ['Seasonal decomposition', 'Structural', 'An in-house baseline that multiplies a month-of-year share, a day-of-month share and an annual level.'],
    ['ARIMA', 'Statistical', 'statsmodels SARIMAX without seasonal or calendar terms. The order of differencing is set by successive KPSS tests, as in the algorithm of Hyndman and Khandakar (2008), and p and q up to 3 by AIC on the last 750 observations. The chosen model is then estimated on the full training sample.'],
    ['ETS', 'Statistical', 'Exponential smoothing with an additive damped trend (Hyndman et al., 2008), parameters by maximum likelihood (statsmodels).'],
    ['Theta', 'Statistical', 'The Theta method (Assimakopoulos and Nikolopoulos, 2000) with a five-day period and no seasonal adjustment (statsmodels).'],
    ['Prophet', 'Statistical', 'Trend and seasonal terms (Taylor and Letham, 2018), with its default settings.'],
    ['Ridge regression', 'Linear learner', `Ridge regression on the ${acuanK} features selected for the trees, standardised, with the penalty chosen from 13 values between 10⁻³ and 10³ by efficient leave-one-out cross-validation. Near-constant features are dropped and the forecast row is clipped to the training range, since a linear model, unlike a tree, extrapolates. Section 4.1 tests other feature sets.`],
  ], { rightFrom: 99 }));

  /* ----------------------------------------------- 3.5 inference */
  c.push(H2('3.5. Evaluation and Statistical Inference'));
  c.push(P('Figure 4 sets out the whole procedure, from the raw series to the reported tests.'));
  c.push(IMG('fig3_evaluasi_v2.png', 560, 348));
  c.push(FCAP(4, `The evaluation procedure. The validation block is used only for tuning and for choosing ` +
    'methods per series.'));
  c.push(H3('Accuracy'));
  c.push(P('Accuracy is the mean absolute scaled error, MASE (Hyndman and Koehler, 2006). With Yₜ the actual ' +
    'value and Fₜ the forecast, the scaled error divides eₜ = Yₜ − Fₜ by the mean absolute first difference of ' +
    'the training sample of n observations,'));
  c.push(EQM([MSUB('q', 't'), MR(' = '),
    new D.MathFraction({ numerator: [MSUB('e', 't')], denominator: [
      new D.MathFraction({ numerator: [MR('1')], denominator: [MR('n − 1')] }),
      new D.MathSum({ children: [MR('|'), MSUB('Y', 'i'), MR(' − '), MSUB('Y', 'i−1'), MR('|')],
        subScript: [MR('i=2')], superScript: [MR('n')] })] })], 2));
  c.push(P('and MASE is the mean of |qₜ| over the test points. It is scale-free and defined when actual ' +
    'values are zero. A value of one means a forecast as accurate as the in-sample random walk. Section 4.7 ' +
    'adds measures in US dollars.'));
  c.push(H3('Paired tests and their units'));
  c.push(P('Every comparison is paired, and both arms forecast the same series on the same days. Three ' +
    'learners that forecast the same day are not independent replications, so for inference each comparison ' +
    `is first averaged to one value per series and date, giving ${T2.n_leaf} × ${NR2()} = ${fmtN(NU2())} units. ` +
    'Consecutive days of one series and different series on one day are still dependent, and four tools ' +
    'address that.'));
  c.push(...BUL([
    '**Wilcoxon signed-rank tests** (Wilcoxon, 1945), two-sided, with the Hodges-Lehmann shift (Hodges and Lehmann, 1963) as the matching effect size, reported in Appendix G. The test concerns the pseudo-median of the paired differences, not the mean.',
    `**Block-bootstrap confidence intervals** for the percentage change in mean MASE, with 2,000 replications. Test dates are resampled in circular blocks of five business days (Künsch, 1989; Politis and Romano, 1992), with all series of a date kept together, so dependence across days and across series is preserved. ${NR2()} dates give ${NR2() / 5} blocks, and Appendix G repeats the intervals with blocks of two and ten days.`,
    `**Equivalence tests.** A difference is declared practically equivalent to zero when its 90 per cent interval lies within ±2 per cent, the two one-sided tests procedure of Lakens (2017). For the leading method 2 per cent of the mean absolute error is about ${n(0.02 * D2(J).mae, 1)} million US dollars per series and day, close to the one-million rounding unit of each reported series. The margin was first used on an earlier design, after its results were seen, so Appendix G also reports ±1 and ±3 per cent. A non-significant difference that fails the test is reported as inconclusive, not as absent.`,
    `**Diebold-Mariano tests per series**, with the small-sample correction of Harvey, Leybourne and Newbold (1997), and a **90 per cent model confidence set** (Hansen, Lunde and Nason, 2011) on the daily mean MASE of all ${T2.n_metode} methods, using the T-max statistic and the same block bootstrap.`,
  ]));
  c.push(P('Tests that answer one question are corrected together with the Holm-Bonferroni procedure (Holm, ' +
    '1979), which controls the probability of any false rejection whatever the dependence among the tests. ' +
    'Each table is one family, and a comparison reported alongside a family but outside it is marked as ' +
    'such. The Benjamini-Hochberg adjustment (Benjamini and Hochberg, 1995) is reported ' +
    'for the method comparison as a less strict reading.'));
  c.push(H3('Ablation designs'));
  c.push(P('The reverse ablation removes one component at a time from the full pipeline, re-fitted daily. ' +
    'Redundancy-aware selection is replaced by the univariate rule, tuned hyperparameters by configuration 1, ' +
    'and daily re-fitting by one fit per 30 origins. The feature-count and market-data arms are re-fitted ' +
    `every five origins and compared with k = ${acuanK} on the same schedule, so both arms of each comparison ` +
    'are fitted equally often. They vary the number of features (12, 40 and all 116 candidates, the last ' +
    'meaning no selection), add market data as changes or as levels, or train only on data from 2022 ' +
    'onwards. SHAP values on the final models (Lundberg and Lee, 2017) show which features they use.'));

  /* ----------------------------------------------- 4. Results */
  c.push(H1('4. Results'));
  c.push(H2('4.1. Which Methods Lead'));
  c.push(TCAP(5, `The ${T2.n_metode} methods over ${NR2()} one-day origins, ${fmtN(NU2())} forecasts each. The change ` +
    'and Wilcoxon columns compare each method with the leading one on series-date units, with a 95 per cent ' +
    'block-bootstrap interval and Holm correction. The last column is the p-value of the 90 per cent model ' +
    'confidence set, and methods with a value of at least 0.10 are in the set.'));
  c.push(TBL([520, 2050, 1000, 1000, 2350, 1250, 1050],
    ['Rank', 'Method', 'Mean MASE', 'Median MASE', 'Change vs leader [95% CI]', 'Holm p', 'MCS p'],
    rk.map((d, i) => [String(i + 1), nice(d.model), n(d.mase, 3), n(d.med, 3),
      M[d.model] ? ciTeks(M[d.model]) : 'leader', M[d.model] ? pv(M[d.model].p_holm) : '—', n(T2.mcs.p[d.model], 3)]),
    { rightFrom: 2, accRows: [0] }));
  if (T2.ridge_varian) {
    c.push(TCAP('5b', 'Ridge regression with other feature sets, against the ridge regression of Table 5. A ' +
      'positive change means the variant is worse. Holm correction across the three variants.'));
    c.push(TBL([4200, 1300, 2300, 1560], ['Ridge regression on', 'Mean MASE', 'Change [95% CI]', 'Holm p'],
      [['The 25 selected features (Table 5)', n(rk.find(r => r.model === 'Ridge').mase, 3), 'reference', '—'],
        ...T2.ridge_varian.map(r => [r.label, n(r.mase, 3), ciTeks(r), pv(r.p_holm)])], { rightFrom: 1, accRows: [0] }));
  }
  const learnerRk = rk.filter(r => L2.includes(r.model));
  const statMcs = mcs2().filter(m => !L2.includes(m) && m !== J);
  const dm = Object.fromEntries(T2.dm_per_seri.map(d => [d.model, d]));
  const terbaikStat = rk.find(r => !L2.includes(r.model) && r.model !== J);
  c.push(P(`${Kata1(nmL(J))} on the selected features has the lowest mean MASE, ${n(rk[0].mase, 3)}. The three ` +
    `learners follow within ${n(Math.max(...learnerRk.map(r => M[r.model].delta)), 1)} per cent, and so does ` +
    `${nmL(terbaikStat.model)} at ${pct(M[terbaikStat.model].delta, 1)}. A 90 per cent model confidence set ` +
    `retains ${kata(mcs2().length)} methods, ${daftarN(mcs2().map(m => nmL(m)))}, and excludes the others with ` +
    (Math.max(...Object.entries(T2.mcs.p).filter(([m]) => !mcs2().includes(m)).map(([, v]) => v)) < 0.001
      ? 'p-values below 0.001. '
      : `p-values of ${n(Math.max(...Object.entries(T2.mcs.p).filter(([m]) => !mcs2().includes(m)).map(([, v]) => v)), 3)} or less. `) +
    'Within the set the differences are one or two per cent. After Holm correction only ' +
    `${daftarN(T2.banding_juara.filter(r => mcs2().includes(r.label) && r.p_holm < 0.05).map(r => nmL(r.label)))} ` +
    `differ significantly from the leader, and no method in the set is equivalent to it within ±2 per cent. ` +
    `Series by series, Diebold-Mariano tests find ${nmL(J)} better than LightGBM on ${dm.LightGBM.juara_lebih_baik} ` +
    `of ${T2.n_leaf} series and worse on ${dm.LightGBM.juara_lebih_buruk}, and better than ARIMA on ` +
    `${dm.ARIMA.juara_lebih_baik} and worse on ${dm.ARIMA.juara_lebih_buruk}.`));
  c.push(P('As designed, with squared-error training, H1 is not supported. Over a year of daily forecasts the ' +
    'tree ensembles are no more accurate than ridge regression on the same features, nor than ARIMA, ETS and ' +
    'Theta. The answer changes with the training loss, which the next subsection takes up. ' + ridgeVarianTeks() +
    'ETS and Theta give almost identical forecasts, as do the random walk with and without drift, which is ' +
    'also why the confidence set assigns ETS and Theta different p-values: the procedure eliminates one of ' +
    `two near-duplicates first. The ranking is not an artefact of the scale. Computed over the full history or from 2022 onwards, the first ` +
    `place goes to ${nmL(T2.urutan_mase_penuh[0])} in both cases, and the same ${kata(mcs2().length - 1)} methods ` +
    'follow in a slightly different order.'));
  c.push(IMG('fig_heatmap_v2.png', 560, 363));
  c.push(FCAP(5, 'Accuracy by series and method, as MASE relative to the random walk on the same series. The ' +
    'boxed cell in each row is the best method for that series on the test block.'));
  const w = T2.winners;
  const nML = w.filter(r => L2.includes(r.best)).length, nR = w.filter(r => r.best === 'Ridge').length;
  const jarang = T2.desk_tanpa.leaf;
  c.push(P(`Figure 5 shows that the best method changes from series to series. A learner is best on ${kata(nML)} ` +
    `of the ${T2.n_leaf} series, ridge regression on ${kata(nR)} and a statistical method on the other ` +
    `${kata(T2.n_leaf - nML - nR)}, and the best method beats the random walk on ${T2.n_beat_rw === T2.n_leaf ? 'every series' : `${T2.n_beat_rw} of them`}. ` +
    `${jarang} is zero on ${n(T2.nol_uji[jarang], 0)} per cent of the test days, and Section 3.1 describes why ` +
    'it is so sparse. Under absolute error the best forecast for such a series is often zero, while Croston’s ' +
    'method forecasts a smoothed average of the non-zero flows, which illustrates how a method can be ' +
    'mismatched to the metric.'));
  c.push(IMG('fig_kuartal_v2.png', 560, 212));
  c.push(FCAP(6, 'Mean MASE by quarter of the test block for the six leading methods and the random walk.'));
  const qj = T2.kuartal_juara;
  c.push(P(`The lead also changes over time (Figure 6). The best method by quarter is ` +
    `${daftarN(Object.entries(qj).map(([q, m]) => `${nmL(m)} in ${q}`))}. All methods find the second quarter ` +
    'of 2026 hardest and the last weeks of the sample easiest, and they move together, which is why their ' +
    'differences are small relative to the variation over time.'));

  c.push(...lossTeks());

  /* ----------------------------------------------- 4.2 combining */
  c.push(H2('4.2. Combining and Selecting Methods'));
  c.push(P('No single method dominates, so a natural response is to combine methods or to choose one per ' +
    'series. Equal weights need no estimation and are notoriously hard to beat (Smith and Wallis, 2009; ' +
    'Claeskens et al., 2016). We test three equal-weight combinations fixed in advance and one chosen on the ' +
    'validation block, the mean of the five methods with the lowest validation error for each series. We ' +
    'also test choosing the single method with the lowest validation error per series.'));
  const K2 = T2.kombinasi, ps = T2.pilih_per_seri;
  c.push(TCAP(6, `Combinations and per-series selection against ${nmL(J)}. A negative change means the ` +
    'alternative is better. The interval is a 95 per cent block-bootstrap interval, the Holm column corrects ' +
    'for the four combinations, and the verdict applies the ±2 per cent equivalence test.'));
  c.push(TBL([3100, 1000, 1000, 1900, 950, 1000, 1410],
    ['Forecast', 'Mean MASE', 'Median MASE', 'Change [95% CI]', 'Holm p', 'Series better', 'Verdict'],
    [...K2.map(e => [e.label, n(e.mase, 3), n(e.med, 3), ciTeks(e), pv(e.p_holm), `${e.seri_lebih_baik} of ${T2.n_leaf}`, putusan(e)]),
      ['Best single method on validation, per series', n(ps.mase, 3), '—', ciTeks(ps.banding), '—', '—', putusan(ps.banding)]],
    { rightFrom: 1 }));
  const med = K2.find(e => e.label.startsWith('Median'));
  c.push(P(`Among the forecasts of the design as planned, the median of all ${T2.n_metode} methods is the only one that beats the leader clearly, by ` +
    `${n(-med.delta, 1)} per cent (${ciTeks(med)}, Holm ${pv(med.p_holm)}), and it is better on ` +
    `${med.seri_lebih_baik} of the ${T2.n_leaf} series. The median ignores the weak methods without having to ` +
    'identify them, which the mean cannot do. The other combinations are equivalent to the leader or ' +
    `inconclusive, and choosing one method per series on the validation block gains nothing ` +
    `(${ciTeks(ps.banding)}), because the best method on ${T2.nval} validation days is a poor guide to the ` +
    'best method over the following year.'));
  if (!(med.delta < 0 && med.p_holm < 0.05)) throw new Error('kombinasi v2: median tidak lagi nyata lebih baik');
  const MV = Object.fromEntries(T2.median_varian.map(r => [r.label.startsWith('Median of the ten') ? 'univ' : 'beda', r]));
  const uvs = T2.median_univ_vs_semua;
  c.push(P(`The median’s advantage does not come from counting near-duplicates twice. The median of the ` +
    `${MV.beda.label.match(/\d+/)[0]} distinct methods, without Theta and the random walk with drift, changes ` +
    `error against the leader by ${ciTeks(MV.beda)}. Nor does it need the feature-based models. The ` +
    `median of the ten univariate methods alone changes error by ${ciTeks(MV.univ)} against the leader and by ` +
    `${ciTeks(uvs)} against the median of all methods. ` +
    (uvs.beda && uvs.delta > 0
      ? 'A median of simple univariate methods is therefore not a substitute for the pipeline, and the best ' +
        'combination is one that includes it.'
      : 'A median of simple univariate methods is therefore about as good as one that includes the pipeline, ' +
        'and the strength of the median lies in combining many methods rather than in any one of them.')));

  /* ----------------------------------------------- 4.3 components */
  c.push(H2('4.3. What Each Pipeline Component Contributes'));
  const KP = Object.fromEntries(T2.komponen.map(r => [r.label, r]));
  c.push(TCAP(7, 'Reverse ablation, pooled across the three learners. A positive change means the full ' +
    'pipeline is better. Wins count the series-date units on which the full pipeline is more accurate. The ' +
    'Holm p-value corrects for the three components, and "equivalent" means the 90 per cent interval lies ' +
    'within ±2 per cent.'));
  c.push(TBL([2600, 1250, 1250, 1900, 1250, 1110],
    ['Component removed', 'Change [95% CI]', '90% interval', 'Wins for full pipeline', 'Holm p', 'Verdict'],
    T2.komponen.map(r => [r.label, ciTeks(r), `[${nCI(r.lo90)}, ${nCI(r.hi90)}]`,
      `${r.a_lebih_baik} / ${r.a_lebih_baik + r.b_lebih_baik}`, pv(r.p_holm), putusan(r, 'different', 'different')]),
    { rightFrom: 1 }));
  const rf = KP['Daily re-fitting'], sel = KP['Redundancy-aware selection'], tun = KP['Tuned hyperparameters'];
  const PM = T2.komponen_per_model;
  c.push(P(`Daily re-fitting is the one component that clearly matters. Fitting once every 30 days instead ` +
    `raises error by ${n(rf.delta, 1)} per cent (${ciTeks(rf)}, Holm ${pv(rf.p_holm)}), and the cost appears ` +
    `for every learner, ${daftarN(L2.map(m => `${pct(PM['Daily re-fitting'][m].delta, 1)} for ${NM_POHON[m]}`))}. ` +
    `Tuning is equivalent to the production configuration within ±2 per cent ` +
    `(${ciTeks(tun)}), and even on the ${T2.tuning_pasangan_berubah} series and learner pairs where tuning ` +
    `changed the configuration the effect is ${ciTeks(T2.tuning_bersyarat)}. Redundancy-aware selection is ` +
    `equivalent to the univariate rule within ±2 per cent (${ciTeks(sel)}), and if anything the univariate rule ` +
    'is slightly better.'));
  if (T2.loss_varian) {
    const LV = T2.loss_varian;
    c.push(P('The training loss, tested in Section 4.1, is a component of a different order. Re-training ' +
      `LightGBM on absolute loss changes its error by ${ciTeks(LV[0])}, and on Huber loss by ${ciTeks(LV[1])} ` +
      `(Holm ${daftarN(LV.map(r => pv(r.p_holm)))})` +
      (T2.l1_lain ? `, and XGBoost on absolute loss by ${ciTeks(T2.l1_lain.xgb)}` : '') +
      ', more than any other component in Table 7. All other ' +
      'arms of this study use squared error, so their effects are measured for that loss.'));
  }
  c.push(IMG('fig_komponen_v2.png', 560, 204));
  c.push(FCAP(7, 'Change in mean MASE when each component is removed, by learner with 95 per cent intervals. ' +
    'The dashed lines are the pooled effects and the grey band is the ±2 per cent equivalence margin.'));
  c.push(P('H2 is supported for re-fitting and for the training loss only. Re-fitting is cheap, and the evidence for it is ' +
    'consistent across learners, seeds and quarters. The random-forest effect of dropping daily re-fitting ' +
    `is ${daftarN(Object.values(sR.efek_komponen['Daily re-fitting']).map(v => pct(v, 1)))} for the three seeds ` +
    `taken one at a time, and by quarter it ranges from ${pct(Math.min(...Object.values(T2.refit_per_kuartal)), 1)} ` +
    `to ${pct(Math.max(...Object.values(T2.refit_per_kuartal)), 1)}.`));

  /* ----------------------------------------------- 4.4 features */
  c.push(H2('4.4. How Many Features to Keep'));
  c.push(TCAP(8, `Feature count against k = ${acuanK}, all re-fitted every five origins. "All candidates" uses ` +
    'the 116 engineered features without selection.'));
  c.push(TBL([2900, 1300, 2100, 1300, 1760],
    ['Features', 'Mean MASE', 'Change vs k = 25 [95% CI]', 'Holm p', 'Verdict'],
    [['k = 25 (reference)', n(T2.k_mase.k25, 3), 'reference', '—', '—'],
      ...T2.k.map((r, i) => [r.label, n(T2.k_mase[['k12', 'k40', 'k_semua'][i]], 3), ciTeks(r), pv(r.p_holm), putusan(r)])],
    { rightFrom: 1, accRows: [0] }));
  c.push(P(`The number of features makes no measurable difference. Twelve, forty and all ${T.pool_internal} ` +
    `candidates are each equivalent to ${acuanK} within ±2 per cent, and none differs significantly from it. H3 ` +
    'is supported in the weak sense that 25 is as good as any count tested, and so is using no selection at ' +
    'all. The trees decide for themselves which features to use, so a selection step adds little for them.'));
  if (!T2.k.every(r => r.setara)) throw new Error('k v2: tidak semua setara lagi');

  /* ----------------------------------------------- 4.5 market */
  c.push(H2('4.5. Do Market Data Help?'));
  const PS = Object.fromEntries(T2.pasar.map(r => [r.label, r]));
  const ub = PS['Market data as daily changes'], lvl = PS['Market data as levels'];
  c.push(TCAP(9, `Market data against none, pooled across the three learners at k = ${acuanK}, re-fitted every ` +
    'five origins. A positive change means market data make the forecast worse. Holm correction across the two ' +
    'market arms. The last row trains only on data from 2022 onwards and is tested separately, outside that family.'));
  c.push(TBL([3100, 2100, 1300, 1250, 1610],
    ['Arm', 'Change [95% CI]', '90% interval', 'Holm p', 'Verdict'],
    [...T2.pasar.map(r => [r.label, ciTeks(r), `[${nCI(r.lo90)}, ${nCI(r.hi90)}]`, pv(r.p_holm), putusan(r)]),
      [T2.jendela.label, ciTeks(T2.jendela), `[${nCI(T2.jendela.lo90)}, ${nCI(T2.jendela.hi90)}]`, pv(T2.jendela.p), putusan(T2.jendela)]],
    { rightFrom: 1 }));
  c.push(P(`Market data do not help. As daily changes they are equivalent to no market data within ` +
    `±2 per cent (${ciTeks(ub)}). As levels they raise error by ` +
    `${n(lvl.delta, 1)} per cent (${ciTeks(lvl)}, Holm ${pv(lvl.p_holm)}), and for every learner ` +
    `(${daftarN(L2.map(m => `${pct(T2.pasar_per_model['Market data as levels'][m].delta, 1)} for ${NM_POHON[m]}`))}). ` +
    'The levels of the exchange rate and the equity index trend over the sample and correlate strongly with ' +
    'the trending flow series, so a tree can use them as a proxy for time that does not extrapolate into the ' +
    'test year. As changes they carry little information about next-day flows, and the selection rule often ' +
    `admits none of them. H4 is not supported in either form.`));
  const PL = T2.pasar_level_per_seri;
  const plBesar = Object.entries(PL).filter(([, v]) => v >= 5).sort((a, b) => b[1] - a[1]);
  c.push(P(`The cost of levels is concentrated. Its Hodges-Lehmann shift is only ${n(T2.hl_pasar_level, 3)} in MASE ` +
    `units, and series by series it exceeds five per cent for ${daftarN(plBesar.map(([l, v]) => `${l} (${pct(v, 1)})`))}.`));
  if (!(ub.setara && lvl.beda && lvl.delta > 0)) throw new Error('pasar v2: pola berubah');
  if (T2.shap) {
    c.push(IMG('fig_pasar_v2.png', 560, 227));
    c.push(FCAP(8, 'Market data as daily changes, series by series. Left, the number of market features the ' +
      'selector kept in the final model, fitted at the last origin. Right, the change in mean MASE from adding ' +
      `them, averaged over the ${NR2()} origins, at each of which the selection is repeated.`));
    const ef = T2.pasar_ubah_per_seri, ne = T2.shap.n_ext;
    const tanpa = Object.keys(ne).filter(l => ne[l] === 0);
    const besar = Object.entries(ef).filter(([, v]) => Math.abs(v) >= 2).sort((a, b) => a[1] - b[1]);
    const dmB = T2.dm_pasar_ubah;
    const nyata = Object.entries(dmB).filter(([, v]) => v.p < 0.05).sort((a, b) => a[1].delta - b[1].delta);
    c.push(P(`Series by series (Figure 8), the selector admits no market feature for ${kata(tanpa.length)} of the ` +
      `${T2.n_leaf} series in the final model, and the change in error exceeds 2 per cent in either direction ` +
      `only for ${daftarN(besar.map(([l, v]) => `${l} (${pct(v, 1)})`))}. A series can change even with no market ` +
      'feature in its final model, because the selection is repeated at every re-fit and admits market ' +
      'features at some origins. ' +
      (nyata.length
        ? `Diebold-Mariano tests per series find a significant difference for ${daftarN(nyata.map(([l, v]) => `${l} (${pct(v.delta, 1)}, p = ${n(v.p, 3)})`))}. `
        : 'No series shows a significant difference in a Diebold-Mariano test. ') +
      (dmB['B.b'] && dmB['B.b'].delta < -2
        ? `The clearest gain is for B.2, transactions by individuals without underlying documents, whose flows ` +
          `appear to react to market moves, and the final random forest gives market variables ` +
          `${n(T2.shap.pasar['B.b'].RandomForest, 1)} per cent of its importance there. It is the one place in the ` +
          'panel where market data look economically informative one day ahead.'
        : '')));
  }
  const JP = T2.jendela_per_seri;
  c.push(P(`Training only on data from 2022 onwards raises error by ${n(T2.jendela.delta, 1)} per cent ` +
    `(${ciTeks(T2.jendela)}), so the longer history helps despite the January 2022 shift described in ` +
    `Section 3.1. For the series touched by that shift the change is ${pct(JP['A.2.a'], 1)} for A.2.a, ` +
    `${pct(JP['A.2.b'], 1)} for A.2.b and ${pct(JP['B.a'], 1)} for B.a. Since the sum of A.2.a and A.2.b ` +
    'changes little across the shift, forecasting the two as one series is a natural alternative, which we ' +
    'leave for future work.'));

  /* ----------------------------------------------- 4.6 SHAP */
  if (T2.shap) {
    c.push(H2('4.6. What the Model Relies On'));
    const SF = T2.shap.famili, a = SF['ubah|RandomForest'], b = SF['ubah|LightGBM'];
    const ur = Object.keys(a);
    const FP = { 'Exponentially weighted mean': 'exponentially weighted means', 'Rolling statistics': 'rolling statistics',
      Lag: 'lags', Market: 'market variables', Interaction: 'interaction terms' };
    const fp = k => FP[k] || k.toLowerCase();
    c.push(IMG('fig_shap_v2.png', 560, 220));
    c.push(FCAP(9, 'Feature importance by family, from SHAP values on the final random forest and LightGBM ' +
      `models with market data as changes, averaged across the ${T2.n_leaf} series. The families are those of ` +
      'Appendix D, with market variables as a separate family.'));
    const G = T2.shap.kelompok;
    c.push(P(`The final models draw most of their signal from the series’ own recent level. For the random ` +
      `forest ${fp(ur[0])} carry ${n(a[ur[0]], 1)} per cent of the importance and ${fp(ur[1])} ${n(a[ur[1]], 1)} ` +
      `per cent, and for LightGBM ${n(b[ur[0]] || 0, 1)} and ${n(b[ur[1]] || 0, 1)} per cent. Market variables ` +
      `carry ${n(a.Market || 0, 1)} per cent for the random forest and ${n(b.Market || 0, 1)} per cent for ` +
      `LightGBM, and the two learners agree on which series use them (rank correlation ${n(T2.shap.rho, 2)}). H5 ` +
      'is supported. These are in-sample attributions, and they describe what the fitted models use, not what ' +
      'improves their forecasts.'));
    c.push(P(`The answer to RQ4 is that market reliance differs by counterparty group. For the random forest ` +
      `the market share averages ${n(G.RandomForest.A, 1)} per cent for corporates, ${n(G.RandomForest.C, 1)} ` +
      `per cent for non-residents and ${n(G.RandomForest.B, 1)} per cent for individuals, and for LightGBM ` +
      `${n(G.LightGBM.A, 1)}, ${n(G.LightGBM.C, 1)} and ${n(G.LightGBM.B, 1)} per cent. The market share of a ` +
      `series does not predict whether market data help it (rank correlation ${n(T2.shap.vs_efek.rho, 2)}, ` +
      `p = ${n(T2.shap.vs_efek.p, 2)}).`));
    if (T2.shap.level) {
      const GL = T2.shap.level.kelompok.RandomForest;
      c.push(P('The ordering reverses when market data enter as levels. With levels the random forest gives market ' +
        `variables ${n(GL.A, 1)} per cent of the importance for corporates, ${n(GL.C, 1)} per cent for ` +
        `non-residents and ${n(GL.B, 1)} per cent for individuals, against ${n(G.RandomForest.A, 1)}, ` +
        `${n(G.RandomForest.C, 1)} and ${n(G.RandomForest.B, 1)} per cent with changes. The corporate series trend ` +
        'most, and their large share under levels together with its collapse under changes is direct evidence ' +
        'that levels act as a proxy for time rather than as information about markets.'));
    }
  }

  /* ----------------------------------------------- 4.7 operational */
  c.push(H2('4.7. Operational Accuracy'));
  const DS = T2.desk, rw = D2('Naive'), TN = Object.fromEntries(T2.desk_tanpa.rows.map(d => [d.model, d]));
  c.push(P('Scaled errors suit statistical comparison but are not what a desk reads. Table 10 reports, for ' +
    'every method, the geometric mean across series of its mean absolute error relative to the random walk ' +
    '(Davydenko and Fildes, 2013), with and without the sparsest series, the mean absolute error and bias in ' +
    'millions of US dollars, the share of days on which the forecast gets the direction of change right, and ' +
    'the error on the daily total of all fifteen series.'));
  c.push(TCAP(10, `Operational metrics over the ${NR2()} test origins. Relative MAE below one beats the random ` +
    'walk. Bias is actual minus forecast. Direction accuracy excludes days on which the actual or the ' +
    'forecast is unchanged, and an asterisk marks a Pesaran-Timmermann test significant at 1 per cent.'));
  c.push(TBL([1900, 1150, 1350, 1150, 1100, 1350, 1360],
    ['Method', 'Relative MAE', `Relative MAE without ${T2.desk_tanpa.leaf}`, 'MAE (USD m)', 'Bias (USD m)',
      'Direction correct (%)', 'MAE of total (USD m)'],
    DS.map(d => [nice(d.model), n(d.rel_mae_geo, 3), n(TN[d.model].rel_mae_geo, 3), n(d.mae, 1), n(d.bias, 1),
      d.arah == null ? '—' : `${n(d.arah, 1)}${d.pt_p != null && d.pt_p < 0.01 ? '*' : ''}`, n(d.mae_total, 1)]),
    { rightFrom: 1, accRows: [0] }));
  const top = DS[0], tot = [...DS].sort((x, y) => x.mae_total - y.mae_total)[0];
  const arahL = DS.filter(d => L2.includes(d.model)).map(d => d.arah);
  const mean_ = D2('NaiveMean');
  c.push(P(`The ranking in US dollars matches the scaled ranking. ${Kata1(nmL(top.model))} has the lowest ` +
    `relative MAE, ${n(100 * (1 - top.rel_mae_geo), 0)} per cent below the random walk, and the learners and the ` +
    `statistical methods in the confidence set lie within ${n(100 * (Math.max(...DS.filter(d => mcs2().includes(d.model)).map(d => d.rel_mae_geo)) - top.rel_mae_geo), 1)} ` +
    `points of it. Excluding ${T2.desk_tanpa.leaf} changes little over this longer block. Mean absolute errors ` +
    `are about ${n(top.mae, 0)} million US dollars against ${n(rw.mae, 1)} for the random walk, and biases are ` +
    'small. Every method except the random walk with drift calls the direction of change better than chance ' +
    `(Pesaran and Timmermann, 1992), the learners on ${n(Math.min(...arahL), 0)} to ${n(Math.max(...arahL), 0)} ` +
    `per cent of days, but so does the rolling mean, on ${n(mean_.arah, 0)} per cent. The daily total is ` +
    `forecast best by ${daftarN(DS.filter(d => Math.abs(d.mae_total - tot.mae_total) < 0.05).map(d => nmL(d.model)))}, ` +
    `with a mean absolute error of ${n(tot.mae_total, 1)} million, the rolling mean gives ${n(D2('NaiveMean').mae_total, 1)}, ` +
    `better than ${daftarN(DS.filter(d => L2.includes(d.model) && d.mae_total > D2('NaiveMean').mae_total).map(d => nmL(d.model)))}, and ` +
    'the random walk gives ' + n(rw.mae_total, 1) + ' million' +
    (T2.topdown ? (T2.topdown.arima < tot.mae_total
      ? `. ARIMA fitted to the total directly does as well or slightly better, at ${n(T2.topdown.arima, 1)} million, ` +
        'so for the total a single top-down model is as good as summing fifteen cell forecasts'
      : `, against ${n(T2.topdown.arima, 1)} million for ARIMA fitted to the total directly`) : '') + '.'));
  return c;
}

function diskusiV2() {
  const c = [];
  const J = juara2(), mcs = mcs2(), KP = Object.fromEntries(T2.komponen.map(r => [r.label, r]));
  const PS = Object.fromEntries(T2.pasar.map(r => [r.label, r]));
  const med = T2.kombinasi.find(e => e.label.startsWith('Median'));
  const MV = Object.fromEntries(T2.median_varian.map(r => [r.label.startsWith('Median of the ten') ? 'univ' : 'beda', r]));
  const uvs = T2.median_univ_vs_semua;
  const lag = T2.ridge_varian ? T2.ridge_varian.find(r => r.label.startsWith('Own lags')) : null;
  const fiturMembantu = lag && lag.beda && lag.delta > 0;
  const oldRef = T.robust.komponen.find(r => r.label === 'Daily re-fitting');
  const oldAr = T.robust.metode.find(r => r.label === 'ARIMA');
  const qAkhir = Object.keys(T2.refit_per_kuartal).sort().slice(-1)[0];
  c.push(H1('5. Discussion'));
  c.push(H2('5.1. Synthesis'));
  const L1 = T2.l1, LL = T2.l1_lain;
  const linL1 = LL && LL.median_lin.beda && LL.median_lin.delta < 0;
  c.push(P('Trained on squared error, as designed, tree ensembles do not beat a linear model on the same ' +
    `features, nor ARIMA, ETS or Theta, and the median of all methods beats them all. Over ${NR2()} days these ` +
    `methods lie within ${n(rentangMcs(), 1)} per cent of the best, and a model confidence set cannot separate ` +
    `${kata(mcs.length)} of them. ` +
    (LL ? 'Trained on absolute loss, the loss that matches the metric, every method improves, the tree ' +
      `ensembles become the most accurate methods, XGBoost ${n(-LL.xgb_vs_ridge.delta, 1)} per cent ahead of ridge ` +
      'regression, and the model confidence set keeps only the absolute-loss methods. A linear median ' +
      'regression gains too, and the trees lead it by one to two per cent in the mean but not on a typical ' +
      'day. The answer to the question in the title therefore depends less on the model class than on whether ' +
      'the model is trained on the loss it is judged by. ' : '') +
    (fiturMembantu
      ? `Under squared loss what the pipeline contributes is its engineered features, which are worth ${n(lag.delta, 1)} per cent ` +
        'to a linear model over its own lags alone, not the nonlinearity of its learners.'
      : 'Neither the engineered features nor the nonlinearity of the trees add much beyond the series’ own lags.')));
  c.push(P('The four conditions of Section 2.1 explain the squared-error result. Data are plentiful, with long ' +
    'daily histories, but the series are learned one at a time, so the cross-learning that drove the M5 ' +
    'results is absent. Under squared loss the nonlinearity that trees add over a linear model on the same ' +
    'features buys nothing, consistent with a signal dominated by persistence. The external predictors are ' +
    'informative for one series at most, and combinations are hard to beat, as in the M4 competition.'));
  if (L1) c.push(P('The loss result has a simple explanation. The flows are skewed, often zero and punctuated by ' +
    'large settlements. Squared loss pulls a forecast toward the conditional mean, and so toward the rare ' +
    'large values, while absolute loss targets the conditional median, which is what MASE rewards. The gain ' +
    `is largest on ${Object.entries(L1.per_seri).sort((a, b) => a[1] - b[1]).slice(0, 2).map(([l]) => `${l}, zero on ${n(T2.nol_uji[l], 0)} per cent of the test days`).join(', and ')}. ` +
    (LL
      ? (linL1
        ? 'Because the linear median regression gains as well, most of the effect is the loss itself. What the ' +
          'trees add on top is small, plausibly because a tree fitted to absolute error returns the median of ' +
          'each leaf, which can jump between zero and a typical settlement in a way that one slope per feature ' +
          'cannot. '
        : 'The linear median regression does not gain, so the combination of trees and absolute loss is what ' +
          'leads. ')
      : '') +
    'The lesson echoes the M5 competition, where the leading LightGBM models were trained on a loss chosen ' +
    'for the shape of the data, the Tweedie loss for intermittent sales, rather than on squared error ' +
    '(Makridakis et al., 2022). In macroeconomic forecasting, by contrast, Goulet Coulombe et al. (2022) find ' +
    'squared loss preferable to the ε-insensitive loss of support vector regression, so the value of a robust ' +
    'loss depends on the shape of the target, and flows with many zeros and rare large settlements are the ' +
    'case where it pays.'));
  c.push(P('Besides the training loss, one choice within the pipeline matters and most do not. Re-fitting every day rather than every 30 ' +
    `days is worth about ${n(KP['Daily re-fitting'].delta, 0)} per cent. Tuning, redundancy-aware selection, the ` +
    'number of features and market data as changes are each equivalent to their alternatives within ±2 per ' +
    `cent. Two choices hurt, market data as levels (${pct(PS['Market data as levels'].delta, 1)}) and discarding ` +
    `the history before 2022 (${pct(T2.jendela.delta, 1)}).`));
  c.push(P('These results reverse three conclusions of the earlier 30-origin design in Appendix A, and the ' +
    'reason is not only resolution. Its 95 per cent interval for removing daily re-fitting, ' +
    `[${nCI(oldRef.lo95)}, ${nCI(oldRef.hi95)}], excludes the one-year estimate of ${pct(KP['Daily re-fitting'].delta, 1)}, ` +
    `and its interval for ARIMA against LightGBM, [${nCI(oldAr.lo95)}, ${nCI(oldAr.hi95)}], excludes the one-year ` +
    'estimate of about zero. Either the short-window intervals were too narrow, with six bootstrap blocks, or ' +
    'the effects change over time, and Appendix H shows that they do. Over consecutive 30-day windows of the ' +
    `test year the gap between ARIMA and LightGBM ranges from ${pct(Math.min(...T2.jendela30.map(w => w.arima_vs_lgbm)), 1)} ` +
    `to ${pct(Math.max(...T2.jendela30.map(w => w.arima_vs_lgbm)), 1)}, and the effect of re-fitting from ` +
    `${pct(Math.min(...T2.jendela30.map(w => w.refit)), 1)} to ${pct(Math.max(...T2.jendela30.map(w => w.refit)), 1)}. ` +
    'The lesson is sharper than "evaluate longer". A verdict of equivalence from a short window can be ' +
    'statistically convincing and still wrong, because the window does not sample the variation over time ' +
    'that decides the answer.'));
  c.push(H2('5.2. A Lesson Learned in Implementation'));
  c.push(...kotakPitfall());
  c.push(H2('5.3. Limitations'));
  const RP = T2.ridge_tanpa_penjaga;
  c.push(...BUL([
    `The test block covers one year, ${tgl2(T2.tgl_uji_awal)} to ${tgl2(T2.tgl_uji_akhir)}, and the leading method changes from quarter to quarter (Appendix H). The claims rest on this one year. They have not been replicated on a second, non-overlapping year, so whether the ranking, the effect of daily re-fitting and the equivalence of the other components hold in other periods remains open.`,
    'The ±2 per cent equivalence margin was first used after the results of an earlier design were seen. Appendix G shows the verdicts at ±1 and ±3 per cent.',
    'The validation block lies immediately before the test block and is short, which is one reason why choosing methods per series on it does not help.',
    'The absolute-loss and Huber-loss variants were added after the main results had been seen, and the loss was not chosen on the validation block. The case for absolute loss rests on the metric, not on these results, but the variants cover LightGBM, XGBoost and the linear model only, the random forest was not re-trained, and every ablation arm uses squared error, so the effect of each component under absolute loss is untested.',
    `Ridge regression, the leading method under squared loss, includes two guards against extrapolation that were added after its first run produced one extreme forecast.${RP ? ` They changed ${RP.n_berubah} of its ${fmtN(RP.n)} forecasts, and without them and that one forecast its mean MASE is ${n(RP.mase_tanpa_satu, 3)}.` : ''} They follow from the method, which, unlike a tree, extrapolates, but the order of events is reported here.`,
    'The series are forecast one at a time, without models trained across series or reconciliation with the published total.',
    'The purpose labels are not stable over time. In January 2022 flows moved between corporate exports and corporate transactions without underlying documents (Section 3.1), and further reclassifications would change what each series measures.',
    'Only one horizon, one jurisdiction and one reporting framework are studied. Appendix E sets out how the exchange-rate regime might shape the market-data results.',
  ]));
  c.push(H2('5.4. Implications for Practice'));
  c.push(...BUL([
    '**Train on the loss the forecasts are judged by.** For skewed, often-zero flows scored by absolute error, absolute-loss training was the largest single improvement in this study, and it costs nothing.',
    `**Run statistical benchmarks and a linear model on the same features alongside any tree ensemble.** Here ${daftarN(mcs.filter(m => !L2.includes(m)).map(nmL))} remain in the set of methods that cannot be told apart from the best.`,
    '**Re-fit daily.** It is cheap and, besides the loss, the one pipeline choice with a clear, consistent effect.',
    (uvs.beda && uvs.delta > 0
      ? '**Combine with a median, and include the feature-based models in it.** The median of all methods was the most accurate forecast of the design as planned and needs no choice of weights, while a median of the univariate methods alone was less accurate.'
      : '**Combine with a median.** The median of all methods was the most accurate forecast of the design as planned and needs no choice of weights, and a median of the univariate methods alone did about as well.'),
    '**Enter market data as changes, not levels, or not at all.** Levels act as a proxy for time and do harm.',
    '**Evaluate over a long block.** A six-week evaluation of the same pipeline reached three conclusions that a year of data reversed.',
  ]));
  c.push(H1('6. Conclusion and Future Work'));
  c.push(P(`We forecast ${T2.n_leaf} disaggregated foreign-exchange flow series one business day ahead over a ` +
    `year of daily origins, with three tree ensembles and eleven comparison methods, and took the pipeline ` +
    'apart one component at a time. Trained on squared error, the tree ensembles do not beat ridge regression ' +
    `on the same features, nor ARIMA, ETS and Theta, and a 90 per cent model confidence set retains ` +
    `${kata(mcs.length)} methods within ${n(rentangMcs(), 1)} per cent of one another, while the median of all ` +
    'methods beats every one of them. Trained on absolute loss, the loss that matches the metric, every ' +
    `method improves, and XGBoost becomes the most accurate, ${n(-T2.l1_lain.xgb_vs_ridge.delta, 1)} per cent ahead ` +
    'of ridge regression. A linear median regression gains almost as much, so most of the effect is the ' +
    'loss, and the lead of the trees rests on a few series and was found after the main results. Daily re-fitting also ' +
    'helps, while tuning, feature selection, the feature count and market data as changes are equivalent to ' +
    'their alternatives, and market data as levels harm. Whether machine learning beats simple benchmarks ' +
    'here depends less on the model than on training it for the metric. For a central bank the practical ' +
    'message is to train learners on the loss they are judged by, keep a diverse set of well-maintained ' +
    'methods, re-fit them daily, combine them by the median, and test each component of a pipeline by ' +
    'removal over a long evaluation before trusting it.'));
  c.push(P('The first task for future work is to replicate the design on a second, non-overlapping year, ' +
    'for example August 2024 to August 2025 with its own validation block in front and the ridge guards fixed ' +
    'before the run, and to check whether the median, daily re-fitting and the equivalence of the components ' +
    'survive, and whether absolute-loss training keeps its lead when it is chosen in advance and applied to ' +
    'every learner and every arm. Beyond that, future work should train models across all fifteen series ' +
    'at once and reconcile them with the published total, model reclassified purposes jointly, and extend the ' +
    'evaluation to longer horizons, where market data and the feature count may matter more.'));
  return c;
}

function abstrakV2() {
  const mcs = mcs2(), KP = Object.fromEntries(T2.komponen.map(r => [r.label, r]));
  const PS = Object.fromEntries(T2.pasar.map(r => [r.label, r]));
  const med = T2.kombinasi.find(e => e.label.startsWith('Median'));
  return [
    LEAD('Background',
      'A central bank that monitors the foreign-exchange market needs to know who will buy and who will sell ' +
      'tomorrow, not only the net total. Machine-learning pipelines suit this task, but they bundle design ' +
      'choices that are rarely tested one at a time.'),
    LEAD('Methods',
      `We forecast ${T2.n_leaf} daily flow series, each one counterparty group and one transaction purpose, one ` +
      'business day ahead, using Indonesian supervisory data. Three tree ensembles with feature selection, ' +
      `tuning and daily re-fitting are compared with ten statistical benchmarks and a ridge regression on the ` +
      `same features over ${NR2()} rolling origins, about a year. Pipeline components are removed one at a time, ` +
      'the learners are also re-trained on absolute loss, ' +
      'and differences are assessed with paired tests, block-bootstrap intervals, equivalence tests and a model ' +
      'confidence set.'),
    LEAD('Results',
      'Trained on squared error, the tree ensembles do not beat ridge regression on the same features, nor ' +
      `ARIMA, ETS and Theta. A 90 per cent model confidence set retains ${kata(mcs.length)} methods within ` +
      `${n(rentangMcs(), 1)} per cent of the best, and the median of all methods beats each of them by at least ` +
      `${n(-med.delta, 1)} per cent. Re-trained on absolute loss, which matches the metric, every method improves. ` +
      `XGBoost becomes the most accurate method, ${n(-T2.l1_lain.xgb_vs_ridge.delta, 1)} per cent ahead of ridge ` +
      'regression, but a linear median regression gains nearly as much, and the trees lead it in the mean ' +
      'only. ' +
      `Dropping daily re-fitting raises error by ${n(KP['Daily re-fitting'].delta, 1)} per cent. Tuning, feature ` +
      'selection, the number of features and market data as daily changes are each equivalent to their ' +
      `alternatives within ±2 per cent, while market data as levels raise error by ` +
      `${n(PS['Market data as levels'].delta, 1)} per cent.`),
    LEAD('Conclusions',
      'One day ahead, the training loss matters more than the model class. Tree ensembles beat strong ' +
      'statistical methods only when trained on the loss they are judged by, and then a linear model trained ' +
      'on that loss comes close. The loss, a median combination, daily re-fitting and a long ' +
      'evaluation matter more than elaborate pipeline components. The loss variants were added after the main ' +
      'results, and the evidence covers one year, so replication is left for future work.'),
  ];
}

function appendix30() {
  const c = [];
  c.push(H1('Appendix A. The Earlier 30-Origin Design'));
  c.push(P('An earlier version of this study evaluated the same pipeline over the last 30 business days only, ' +
    `${tglEN2(T.tgl_uji_awal)} to ${tglEN2(T.tgl_akhir)}, trained from 2006 including the structural zeros, ` +
    'with seven benchmarks, market data as levels and one random seed. Table A1 gives its ranking and Table ' +
    'A2 its reverse ablation. Its p-values use the same series-date units as the main text.'));
  c.push(TCAP('A1', `The 30-origin design. Mean and median MASE over ${T.n_leaf} series and 30 origins, and the ` +
    'change against its leader with a 95 per cent block-bootstrap interval.'));
  c.push(rankTable(e2rank));
  c.push(TCAP('A2', 'The 30-origin design, reverse ablation pooled across the three learners. A positive ' +
    'change means the full pipeline is better.'));
  c.push(reverseAblationTable());
  c.push(P(`The short design ranked LightGBM first, ${n(T.robust.metode.find(r => r.label === 'ARIMA').delta, 1)} per cent ahead of ARIMA, found daily re-fitting ` +
    'equivalent to its removal within ±2 per cent, and found no combination that beat the leader. The ' +
    'one-year design reverses all three, which is the reason it replaced the short one.'));
  return c;
}

function appendixInferensiV2() {
  const ya = b => (b ? 'yes' : 'no');
  const ci = (a, b) => `[${nCI(a)}, ${nCI(b)}]`;
  const baris = (grup, r) => [grup, r.label, ciTeks(r), `${n(r.hl, 3)} [${n(r.hl_lo, 3)}, ${n(r.hl_hi, 3)}]`,
    ci(...r.blok_sens['2'].slice(0, 2)), ci(...r.blok_sens['10'].slice(0, 2)),
    ['1.0', '2.0', '3.0'].map(m => ya(r.setara_margin[m])).join(' / ')];
  const semua = [...T2.banding_juara.filter(r => mcs2().includes(r.label)).map(r => ['Method vs leader', r]),
    ...T2.kombinasi.map(r => ['Combination vs leader', r]), ['Selection vs leader', T2.pilih_per_seri.banding],
    ...T2.komponen.map(r => ['Component removed', r]), ['Component removed', T2.tuning_bersyarat],
    ...T2.k.map(r => ['Feature count vs 25', r]), ...T2.pasar.map(r => ['Market data vs none', r]),
    ['Window vs full history', T2.jendela]];
  const c = [];
  c.push(H1('Appendix G. Robustness of the Inference'));
  const pindah = semua.filter(([, r]) => ['2', '10'].some(b => ((r.blok_sens[b][0] > 0) || (r.blok_sens[b][1] < 0)) !== r.beda)).length;
  c.push(P('Table G1 repeats the main comparisons with the Hodges-Lehmann shift in MASE units, with ' +
    'block-bootstrap intervals for blocks of two and ten days instead of five, and with the equivalence ' +
    `verdict at margins of ±1, ±2 and ±3 per cent. For ${kata(pindah)} of the ${semua.length} comparisons the ` +
    'block length decides whether the interval excludes zero. Table G2 gives the component effects for each ' +
    'learner.'));
  c.push(TCAP('G1', 'Robustness of the pooled comparisons. Change and intervals in per cent of mean MASE, ' +
    'Hodges-Lehmann shift in MASE units.'));
  c.push(TBL([1500, 2200, 1600, 1700, 950, 950, 1110],
    ['Family', 'Comparison', 'Change [95% CI]', 'Hodges-Lehmann [95% CI]', 'CI, 2-day blocks', 'CI, 10-day blocks', 'Equivalent at ±1 / ±2 / ±3'],
    semua.map(([g, r]) => baris(g, r)), { rightFrom: 2 }));
  const rows2 = [];
  Object.entries(T2.komponen_per_model).forEach(([k, v]) => L2.forEach(m => {
    const r = v[m];
    rows2.push([k, nice(m), ciTeks(r), ci(r.lo90, r.hi90), pv(r.p), putusan(r, 'different', 'different')]);
  }));
  c.push(TCAP('G2', `Component effects by learner, ${fmtN(NU2())} series-date units each. A positive change ` +
    'means the full pipeline is better. Unadjusted Wilcoxon p-values.'));
  c.push(TBL([2500, 1300, 1900, 1500, 1000, 1160],
    ['Component removed', 'Learner', 'Change [95% CI]', '90% CI', 'Wilcoxon p', 'Verdict'], rows2, { rightFrom: 2 }));
  return c;
}

function appendixWaktu() {
  const c = [];
  c.push(H1('Appendix H. Results over Time'));
  c.push(P(`Table H1 splits the ${NR2()}-day test block into consecutive 30-day windows, the length of the ` +
    'earlier design’s test block. Table H2 repeats the main comparisons by calendar quarter. Both show how ' +
    'much a verdict can depend on the period evaluated.'));
  c.push(TCAP('H1', 'Consecutive 30-day windows of the test block. The ARIMA column is the change in mean MASE of ' +
    'ARIMA against LightGBM, the re-fitting column the effect of removing daily re-fitting, pooled over the ' +
    'learners, and the median column the change of the median of all methods against the best single method ' +
    'in that window.'));
  c.push(TBL([2600, 1700, 1700, 1700, 1660], ['Window', 'Best single method', 'ARIMA vs LightGBM', 'Without daily re-fitting', 'Median vs best'],
    T2.jendela30.map(w => [`${tgl2(w.awal)} to ${tgl2(w.akhir)}`, nice(w.juara), pct(w.arima_vs_lgbm, 1), pct(w.refit, 1), pct(w.median_vs_terbaik, 1)]),
    { rightFrom: 2 }));
  const t30 = T2.tiga_puluh_terakhir;
  c.push(P(`The last 30 origins, from ${tgl2(t30.awal)}, cover the same dates as the earlier design. On them the ` +
    `present design also ranks ${daftarN(t30.urutan.slice(0, 3).map(nmL))} first, second and third, with ARIMA ` +
    `${pct(t30.arima_vs_lgbm, 1)} against LightGBM, so the earlier ranking reflects those weeks rather than ` +
    'the design changes made since.'));
  const KB = T2.kuartal_banding, qs = Object.keys(T2.per_kuartal).sort();
  c.push(TCAP('H2', 'Changes in mean MASE by quarter of the test block, in per cent. Methods are compared with the ' +
    'leader of Table 5, components with the full pipeline, and feature and market arms with k = 25.'));
  c.push(TBL([2900, ...qs.map(() => Math.floor(6460 / qs.length))], ['Comparison', ...qs.map(q => `${q} (${T2.kuartal_n[q]} days)`)],
    Object.entries(KB).map(([k, v]) => [k, ...qs.map(q => pct(v[q], 1))]), { rightFrom: 1 }));
  return c;
}

function appendixBeeswarmV2() {
  const dir = FIG + 'beeswarm_v2' + path.sep;
  const leafs = Object.keys(T2.per_leaf_model).sort();
  if (!T2.shap || !leafs.every(l => fs.existsSync(dir + l + '.png'))) {
    console.warn('  Lampiran B dilewati: beeswarm v2 belum lengkap');
    return [];
  }
  const c = [];
  c.push(H1('Appendix B. Feature contributions, series by series'));
  c.push(P('The beeswarms below come from the final random forest of each series, with market data as daily ' +
    'changes. Each dot is one of the last 300 training days, placed by that feature’s contribution to the ' +
    'predicted next-day flow in millions of US dollars, and coloured by whether the feature value was low ' +
    '(blue) or high (red) that day. Feature names in orange are market variables, and names in black are ' +
    'engineered from the series’ own history.'));
  c.push(NOTE('These are the fourteen highest-importance features of the 25 selected, ordered by mean absolute SHAP value.'));
  leafs.forEach((l, i) => {
    const ne = T2.shap.n_ext[l], sh = T2.shap.pasar[l].RandomForest;
    c.push(IMG('beeswarm_v2' + path.sep + l + '.png', 520, 282));
    c.push(FCAP(`B${i + 1}`, `${l} (${LABEL[l]}, ${ACTOROF(l)}). The selector kept ${ne} market ` +
      `feature${ne === 1 ? '' : 's'} of 25, carrying ${n(sh, 1)} per cent of total absolute SHAP value.`));
  });
  return c;
}

function refs() {
  return [
    'Ahmed, N. K., Atiya, A. F., El Gayar, N. and El-Shishiny, H. (2010). An empirical comparison of machine learning models for time series forecasting. *Econometric Reviews*, 29(5–6), 594–621.',
    'Amat, C., Michalski, T. and Stoltz, G. (2018). Fundamentals and exchange rate forecastability with simple machine learning methods. *Journal of International Money and Finance*, 88, 1–24.',
    'Assimakopoulos, V. and Nikolopoulos, K. (2000). The theta model: a decomposition approach to forecasting. *International Journal of Forecasting*, 16(4), 521–530.',
    'Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society, Series B*, 57(1), 289–300.',
    'Bergmeir, C. and Benítez, J. M. (2012). On the use of cross-validation for time series predictor evaluation. *Information Sciences*, 191, 192–213.',
    'Bojer, C. S. and Meldgaard, J. P. (2021). Kaggle forecasting competitions: an overlooked learning opportunity. *International Journal of Forecasting*, 37(2), 587–603.',
    'Breiman, L. (2001). Random forests. *Machine Learning*, 45(1), 5–32.',
    'Calvo, G. A. and Reinhart, C. M. (2002). Fear of floating. *Quarterly Journal of Economics*, 117(2), 379–408.',
    'Cerqueira, V., Torgo, L. and Soares, C. (2022). A case study comparing machine learning with statistical methods for time series forecasting: size matters. *Journal of Intelligent Information Systems*, 59(2), 415–433.',
    'Chen, T. and Guestrin, C. (2016). XGBoost: a scalable tree boosting system. In *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.',
    'Claeskens, G., Magnus, J. R., Vasnev, A. L. and Wang, W. (2016). The forecast combination puzzle: a simple theoretical explanation. *International Journal of Forecasting*, 32(3), 754–762.',
    'Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289–303.',
    'Davydenko, A. and Fildes, R. (2013). Measuring forecasting accuracy: the case of judgmental adjustments to SKU-level demand forecasts. *International Journal of Forecasting*, 29(3), 510–522.',
    'Diebold, F. X. and Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business and Economic Statistics*, 13(3), 253–263.',
    'Evans, M. D. D. and Lyons, R. K. (2002). Order flow and exchange rate dynamics. *Journal of Political Economy*, 110(1), 170–180.',
    'Fratzscher, M., Gloede, O., Menkhoff, L., Sarno, L. and Stöhr, T. (2019). When is foreign exchange intervention effective? Evidence from 33 countries. *American Economic Journal: Macroeconomics*, 11(1), 132–156.',
    'Goulet Coulombe, P., Leroux, M., Stevanovic, D. and Surprenant, S. (2022). How is machine learning useful for macroeconomic forecasting? *Journal of Applied Econometrics*, 37(5), 920–964.',
    'Guyon, I. and Elisseeff, A. (2003). An introduction to variable and feature selection. *Journal of Machine Learning Research*, 3, 1157–1182.',
    'Hansen, P. R., Lunde, A. and Nason, J. M. (2011). The model confidence set. *Econometrica*, 79(2), 453–497.',
    'Harvey, D., Leybourne, S. and Newbold, P. (1997). Testing the equality of prediction mean squared errors. *International Journal of Forecasting*, 13(2), 281–291.',
    'Hastie, T., Tibshirani, R. and Friedman, J. (2009). *The Elements of Statistical Learning*, 2nd edition. New York: Springer.',
    'Hewamalage, H., Bergmeir, C. and Bandara, K. (2021). Recurrent neural networks for time series forecasting: current status and future directions. *International Journal of Forecasting*, 37(1), 388–427.',
    'Hodges, J. L. and Lehmann, E. L. (1963). Estimates of location based on rank tests. *Annals of Mathematical Statistics*, 34(2), 598–611.',
    'Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.',
    'Huber, P. J. (1964). Robust estimation of a location parameter. *Annals of Mathematical Statistics*, 35(1), 73–101.',
    'Hyndman, R. J. and Khandakar, Y. (2008). Automatic time series forecasting: the forecast package for R. *Journal of Statistical Software*, 27(3), 1–22.',
    'Hyndman, R. J. and Koehler, A. B. (2006). Another look at measures of forecast accuracy. *International Journal of Forecasting*, 22(4), 679–688.',
    'Hyndman, R. J., Koehler, A. B., Ord, J. K. and Snyder, R. D. (2008). *Forecasting with Exponential Smoothing: The State Space Approach*. Berlin: Springer.',
    'Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q. and Liu, T.-Y. (2017). LightGBM: a highly efficient gradient boosting decision tree. In *Advances in Neural Information Processing Systems*, 30, 3146–3154.',
    'Kohavi, R. and John, G. H. (1997). Wrappers for feature subset selection. *Artificial Intelligence*, 97(1–2), 273–324.',
    'Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of Statistics*, 17(3), 1217–1241.',
    'Lakens, D. (2017). Equivalence tests: a practical primer for t tests, correlations, and meta-analyses. *Social Psychological and Personality Science*, 8(4), 355–362.',
    'Lundberg, S. M. and Lee, S.-I. (2017). A unified approach to interpreting model predictions. In *Advances in Neural Information Processing Systems*, 30, 4765–4774.',
    'Lyons, R. K. (2001). *The Microstructure Approach to Exchange Rates*. Cambridge, MA: MIT Press.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2018a). Statistical and machine learning forecasting methods: concerns and ways forward. *PLOS ONE*, 13(3), e0194889.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2018b). The M4 competition: results, findings, conclusion and way forward. *International Journal of Forecasting*, 34(4), 802–808.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2020). The M4 competition: 100,000 time series and 61 forecasting methods. *International Journal of Forecasting*, 36(1), 54–74.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2022). M5 accuracy competition: results, findings, and conclusions. *International Journal of Forecasting*, 38(4), 1346–1364.',
    'Medeiros, M. C., Vasconcelos, G. F. R., Veiga, Á. and Zilberman, E. (2021). Forecasting inflation in a data-rich environment: the benefits of machine learning methods. *Journal of Business and Economic Statistics*, 39(1), 98–119.',
    'Meese, R. A. and Rogoff, K. (1983). Empirical exchange rate models of the seventies: do they fit out of sample? *Journal of International Economics*, 14(1–2), 3–24.',
    'Menkhoff, L. (2013). Foreign exchange intervention in emerging markets: a survey of empirical studies. *The World Economy*, 36(9), 1187–1208.',
    'Menkhoff, L., Sarno, L., Schmeling, M. and Schrimpf, A. (2016). Information flows in foreign exchange markets: dissecting customer currency trades. *Journal of Finance*, 71(2), 601–634.',
    'Montero-Manso, P. and Hyndman, R. J. (2021). Principles and algorithms for forecasting groups of time series: locality and globality. *International Journal of Forecasting*, 37(4), 1632–1653.',
    'Peng, H., Long, F. and Ding, C. (2005). Feature selection based on mutual information: criteria of max-dependency, max-relevance, and min-redundancy. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 27(8), 1226–1238.',
    'Pesaran, M. H. and Timmermann, A. (1992). A simple nonparametric test of predictive performance. *Journal of Business and Economic Statistics*, 10(4), 461–465.',
    'Politis, D. N. and Romano, J. P. (1992). A circular block-resampling procedure for stationary data. In R. LePage and L. Billard (eds), *Exploring the Limits of Bootstrap*, 263–270. New York: Wiley.',
    'Richardson, A., van Florenstein Mulder, T. and Vehbi, T. (2021). Nowcasting GDP using machine-learning algorithms: a real-time assessment. *International Journal of Forecasting*, 37(2), 941–948.',
    'Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D., Chaudhary, V., Young, M., Crespo, J.-F. and Dennison, D. (2015). Hidden technical debt in machine learning systems. In *Advances in Neural Information Processing Systems*, 28, 2503–2511.',
    'Smith, J. and Wallis, K. F. (2009). A simple explanation of the forecast combination puzzle. *Oxford Bulletin of Economics and Statistics*, 71(3), 331–355.',
    'Smyl, S. (2020). A hybrid method of exponential smoothing and recurrent neural networks for time series forecasting. *International Journal of Forecasting*, 36(1), 75–85.',
    'Spiliotis, E., Makridakis, S., Semenoglou, A.-A. and Assimakopoulos, V. (2022). Comparison of statistical and machine learning methods for daily SKU demand forecasting. *Operational Research*, 22(3), 3037–3061.',
    'Syntetos, A. A. and Boylan, J. E. (2005). The accuracy of intermittent demand estimates. *International Journal of Forecasting*, 21(2), 303–314.',
    'Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: an analysis and review. *International Journal of Forecasting*, 16(4), 437–450.',
    'Taylor, S. J. and Letham, B. (2018). Forecasting at scale. *The American Statistician*, 72(1), 37–45.',
    'Wickramasuriya, S. L., Athanasopoulos, G. and Hyndman, R. J. (2019). Optimal forecast reconciliation for hierarchical and grouped time series through trace minimization. *Journal of the American Statistical Association*, 114(526), 804–819.',
    'Wilcoxon, F. (1945). Individual comparisons by ranking methods. *Biometrics Bulletin*, 1(6), 80–83.',
];
}

const OUTF = process.argv[2] || path.join(KERJA, 'FX_15seri.docx');
console.log(`nama leaf tampilan: ${nTampil} potongan teks memakai nama baru (nama_leaf.json)`);
Packer.toBuffer(doc).then(b => { fs.writeFileSync(OUTF, b); console.log('ditulis:', OUTF, (b.length / 1024).toFixed(0) + ' KB'); });
