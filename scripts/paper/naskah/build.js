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

const PAGE_W = 12240, MARGIN = 1440;
const INK = '1B2530', MUTED = '5E6B76', ACC = '9E2B2B', RULE = 'C8D0D6', HDR = 'EEF2F5';

const n = (v, d = 3) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(d);
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

/* Sebaran relatif ketiga ensemble pohon di Tabel 6, dalam persen. Dipakai di
   abstrak. Diturunkan supaya klaim "within X per cent" tidak perlu diketik
   ulang setiap kali angkanya bergerak. */
const POHON = ['RandomForest', 'LightGBM', 'XGBoost'];
// Pembantu prosa. Di atas `const doc` karena build() dipanggil saat doc dibuat.
const pTeks = p => (p < 0.0001 ? 'p < 0.0001' : `p = ${Number(p).toFixed(4)}`);
const niceK = m => (m === 'RandomForest' ? 'random forest' : m === 'Naive' ? 'the random walk'
  : m === 'SeasonalDecomp' ? 'seasonal decomposition' : NICE[m] || m);
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
const EQ = t => new Paragraph({
  spacing: { before: 170, after: 170, line: 300 },
  alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: t, font: 'Cambria', size: 23, italics: true })],
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
const ACTOROF = id => id.startsWith('A.1') ? 'FDI corporate'
  : id.startsWith('A.2') ? 'Other corporate'
  : id.startsWith('B') ? 'Individual' : 'Non-resident';

/* ------------------------------------------------------------------ build */
const doc = new Document({
  creator: 'FX flow forecasting study',
  title: 'One-Day-Ahead Forecasting of Foreign-Exchange Flows by Counterparty and Purpose',
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
  const ct = T.champion_tests;
  const juara = e2rank[0];
  const rwUji = T.e2_summary.find(r => r.model === 'Naive');
  const nsHolm = T.champion_koreksi.tak_signifikan_holm;          // tidak terpisah dari juara
  const statTak = nsHolm.filter(m => !POHON.includes(m));          // metode statistik yang setara
  const grupDepan = [juara.model, ...nsHolm];
  const lebarGrup = (() => {
    const v = T.e2_summary.filter(r => grupDepan.includes(r.model)).map(r => r.mase);
    return 100 * (Math.max(...v) - Math.min(...v)) / Math.min(...v);
  })();
  const acuanK = T.ablation_acuan;
  const kAtas = abl.filter(a => a.k > acuanK), kBawah = abl.filter(a => a.k < acuanK);
  const kList = abl.map(a => a.k);
  const nMLmenang = T.winners.filter(w => w.fam === 'ML').length;
  const nDefault = Object.values(T.cfg_terpilih).reduce((s, v) => s + v[0], 0);
  const nSelTune = Object.values(T.cfg_terpilih).reduce((s, v) => s + v.reduce((a, b) => a + b, 0), 0);
  const kurtMaks = Math.max(...T.desc.map(d => d.kurt));
  const nPasangMetode = T.e2_summary[0].n, nPasangPipa = T.reverse_ablation[0].n;
  const fmt = v => v.toLocaleString('en-US');
  const daftar = xs => xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1];
  const jendelaTeks = daftar(J.rolling.map(String));

  /* ---------------------------------------------------------------- title */
  c.push(new Paragraph({
    spacing: { after: 90 },
    children: [new TextRun({ text: 'One-Day-Ahead Forecasting of Foreign-Exchange Flows by Counterparty and Purpose', bold: true, size: 32, color: INK })],
  }));
  c.push(new Paragraph({
    spacing: { after: 250 },
    children: [new TextRun({ text: 'Fifteen daily series, ten methods, and a market-data result that turned out to be an artefact', size: 22, italics: true, color: MUTED })],
  }));

  /* -------------------------------------------------------------- abstract */
  // Formula masukan no. 18: mengapa penting, bagaimana dilakukan, temuan
  // kunci, implikasi ke depan. Disusun dari Hasil dan Kesimpulan di bawah;
  // setiap angka diturunkan dari tables.json.
  c.push(H1('Abstract'));
  c.push(LEAD('Why it matters',
    'A central bank that monitors the foreign-exchange market needs to know who will buy and who will sell ' +
    'tomorrow, not only the net total. Machine-learning pipelines are the natural tool for forecasting many ' +
    'such series at once, but each pipeline bundles design choices, such as feature selection, tuning, ' +
    're-fitting and external data, that are usually adopted by habit and rarely tested one at a time.'));
  c.push(LEAD('How it was done',
    `We forecast ${T.n_leaf} daily flow series, each one counterparty group and one transaction purpose, one ` +
    `business day ahead over ${fmt(T.n_hari)} business days of Indonesian supervisory data. ` +
    `The core is a machine-learning pipeline of three tree ensembles with ${T.pool_internal} engineered ` +
    `features, redundancy-aware selection, hyperparameters tuned on a ${T.nval}-day validation block and ` +
    `daily re-fitting. Seven statistical methods serve as benchmarks. ` +
    `Every comparison is paired over 30 rolling one-day origins, tested with the Wilcoxon signed-rank test ` +
    `and corrected for multiple testing with the Holm-Bonferroni procedure, and every pipeline component is ` +
    `removed in turn to measure what it contributes.`));
  c.push(LEAD('What we found',
    `The learners lead the panel, with ${nice(juara.model)} lowest at a mean MASE of ${n(juara.mase, 3)}, ` +
    `but the lead does not survive correction. ` +
    `${daftar(statTak.map(nice))} ${statTak.length > 1 ? 'are' : 'is'} statistically indistinguishable from ` +
    `the leading learner, and machine learning is the best method on only ${kata(nMLmenang)} of the ` +
    `${T.n_leaf} series. ` +
    `None of the pipeline components earns its place. ` +
    ([rSel, rRef, rTun].every(a => a.delta < 0)
      ? `Removing redundancy-aware selection, daily re-fitting or tuning in fact lowers pooled error, by ` +
        `${n(-rSel.delta, 2)}, ${n(-rRef.delta, 2)} and ${n(-rTun.delta, 2)} per cent, `
      : `Removing redundancy-aware selection, daily re-fitting or tuning changes pooled error by ` +
        `${pct(rSel.delta)}, ${pct(rRef.delta)} and ${pct(rTun.delta)}, `) +
    `and none of the three changes is significant after correction. ` +
    `Keeping more than the conventional ${acuanK} features helps a little, but not consistently across series. ` +
    `Market data at first appeared to raise error by ${n(g8.delta_nol, 1)} per cent. ` +
    `Most of that penalty, ${n(g8.rusak_hilang_pct, 0)} per cent of it, was an artefact of the pipeline, which ` +
    `trained on market features and then silently zero-filled them at prediction. ` +
    `Once supplied correctly they cost ${n(g8.delta_benar, 1)} per cent on average and help ` +
    `${kata(T.n_leaf_membaik)} series.`));
  c.push(LEAD('What it implies',
    'Machine learning is a reasonable default for this task but not a demonstrated improvement over good ' +
    'statistical methods, and the components that make a pipeline look sophisticated should be tested by ' +
    'removal before they are trusted. ' +
    'Practitioners should forecast each counterparty and purpose cell separately, check what their forecaster ' +
    'actually receives at prediction time, and tune settings such as the feature count at the horizon they ' +
    'will run. Future work should tune the feature count on validation data and test market data at longer ' +
    'horizons, where their own future values must also be forecast.'));
  c.push(new Paragraph({
    spacing: { before: 110, after: 60 },
    children: [new TextRun({ text: 'Keywords: ', bold: true, size: 20, color: INK }),
      new TextRun({ text: 'machine learning; one-day-ahead forecasting; foreign-exchange flows; feature selection; mRMR; ablation study; SHAP; gradient boosting', size: 20, color: INK })],
  }));
  c.push(new Paragraph({
    spacing: { after: 200 },
    children: [new TextRun({ text: 'JEL classification: ', bold: true, size: 20, color: INK }),
      new TextRun({ text: 'C22, C45, C53, F31, E58', size: 20, color: INK })],
  }));

  /* ---------------------------------------------------------- 1. Intro */
  c.push(H1('1. Introduction'));

  c.push(H2('1.1. Background and Context'));
  c.push(P('A central bank that watches the foreign-exchange market needs a forward view of supply and demand. ' +
    'The net total is useful but not enough. ' +
    'Two days can share the same net total and be nothing alike. On one, exporters sell and importers buy in ' +
    'equal measure. On the other, non-residents pull money out while corporates sit still. ' +
    'Those two days call for different responses.'));
  c.push(P('The setting is Indonesia, and two structural features matter for reading the results. ' +
    'The exchange-rate regime is a managed float, so flows and the rate are linked through a policy reaction as ' +
    'well as through the market. And the onshore market is shallow by regional standards, so a single large ' +
    'corporate settlement can move the daily total in one cell. ' +
    'Both raise the weight of counterparty composition, which is what this paper forecasts, and both bound how ' +
    'far the results travel, a point we return to in Section 5.4.'));
  c.push(P('The data are administrative. Banks report each transaction, and every transaction carries a ' +
    'counterparty group and a declared purpose. ' +
    'That gives a two-way grid of who transacted and why, and the grid cell is the unit of analysis here.'));
  c.push(IMG('fig1_taxonomy.png', 560, 258));
  c.push(FCAP(1, `The ${T.n_leaf} forecast units. Rows are counterparty groups, columns declared purposes, ` +
    'and each filled cell is one series, labelled with its sample mean in millions of US dollars. ' +
    'Blue cells are net demand for foreign exchange on average and orange cells net supply. ' +
    'Dashed cells do not occur.'));
  c.push(P('The cells do not behave alike. Some are dense and move smoothly, while others are zero on many ' +
    'days and then jump. A forecasting system for this grid therefore has to cope with very different series ' +
    'at once, which is the kind of problem machine-learning pipelines are built for.'));

  c.push(H2('1.2. Problem Statement'));
  c.push(P('The monitoring cycle is daily. The desk closes one day and plans the next, so the forecast that ' +
    'fits this cycle is one business day ahead. ' +
    'Forecasting flows is also not the same as forecasting the exchange rate. ' +
    'Rates are prices, and are famously hard to beat with a random walk (Meese and Rogoff, 1983). ' +
    'Flows are quantities, and they carry autocorrelation, calendar effects and settlement patterns that a ' +
    'learner can exploit.'));
  c.push(P('A machine-learning pipeline for this task is more than a learner. Around the learner sit a pool ' +
    'of engineered features, a rule that selects some of them, a search over hyperparameters, a schedule for ' +
    're-fitting and, often, external data such as exchange rates and equity prices. ' +
    'Each of these is usually justified by habit or by analogy with another problem. ' +
    'Whether each one actually improves a one-day forecast of disaggregated flows is rarely tested, and a ' +
    'pipeline reported only as an assembled whole cannot tell the reader which parts are doing the work.'));

  c.push(H2('1.3. Research Objectives and Questions'));
  c.push(P('The study puts the machine-learning pipeline at the centre and asks four questions of it.'));
  c.push(...BUL([
    '**RQ1.** Does a tuned machine-learning pipeline forecast the counterparty and purpose series more accurately than established statistical methods one day ahead, and does any single method dominate across series?',
    '**RQ2.** Which parts of the pipeline earn their place? We test redundancy-aware feature selection, hyperparameter tuning, daily re-fitting and the number of features kept.',
    '**RQ3.** Do daily market data improve the machine-learning forecasts once they are handled correctly? We test the rupiah exchange rate, the one-month forward, the ten-year bond yield, the dollar index, non-resident equity flows and the equity index.',
    '**RQ4.** Which features does the fitted model actually rely on, and does that differ across counterparty groups?',
  ]));

  c.push(H2('1.4. Significance of the Study'));
  c.push(P('The paper adds three things. ' +
    'It evaluates a machine-learning pipeline at the level where the supervisory question is asked, the ' +
    'counterparty and purpose cell rather than the total. ' +
    'It dismantles the pipeline one component at a time and tests each removal on paired forecasts with ' +
    'correction for multiple testing, so the reader can see which components carry the result. ' +
    'And it finds and corrects a handling error in how external features reach the model at prediction ' +
    'time, an error that would otherwise have been reported as a property of the data.'));

  /* --------------------------------------------------- 2. Literature */
  c.push(H1('2. Literature Review'));

  c.push(H2('2.1. Theoretical Background'));
  c.push(P('Two ideas shape the design. The first is the bias-variance trade-off. ' +
    'Adding predictors lowers bias and raises variance, and past some point the second effect wins, so ' +
    'out-of-sample accuracy falls even while in-sample fit keeps improving (Hastie, Tibshirani and Friedman, 2009). ' +
    'Theory does not say where that point sits for a given dataset. Only measurement does, which is why the ' +
    'feature count is treated here as something to test rather than to assume.'));
  c.push(P('The second comes from market microstructure. ' +
    'Order flow carries information about exchange-rate moves (Evans and Lyons, 2002; Lyons, 2001). ' +
    'If flows and prices are linked, price variables might help forecast flows. ' +
    'Whether they do so one day ahead, on top of the flow series own history, is an open question, and we test it directly.'));

  c.push(H2('2.2. Critical Review of Existing Literature'));
  c.push(P('Forecasting competitions give a consistent message. Simple methods are hard to beat, and pure ' +
    'machine-learning methods did not outperform established statistical benchmarks across the M4 collection ' +
    '(Makridakis, Spiliotis and Assimakopoulos, 2018, 2020). ' +
    'Gradient-boosted trees do well on tabular problems (Chen and Guestrin, 2016; Ke et al., 2017), ' +
    'but their edge over a good statistical benchmark on short-horizon series is smaller than often assumed.'));
  c.push(P('Feature selection is well studied in theory (Guyon and Elisseeff, 2003; Kohavi and John, 1997), ' +
    'and redundancy-aware criteria such as mRMR (Peng, Long and Ding, 2005) are designed for pools of ' +
    'overlapping candidates like the lags and moving averages of a time series. ' +
    'Applied work rarely reports how the retained-feature count was chosen, and when it is tuned only the ' +
    'winning value is shown. ' +
    'Evaluation practice is uneven too. Bergmeir and Benítez (2012) and Tashman (2000) set out how ' +
    'rolling-origin evaluation should work, yet single-split evaluations remain common, and multiple ' +
    'comparisons on the same forecasts are seldom corrected.'));

  c.push(H2('2.3. Identification of Research Gaps'));
  c.push(P('Three gaps follow.'));
  c.push(...BUL([
    'Disaggregated administrative flow series are rarely forecast cell by cell. Most work models a total, because that is how the data are published, not because that is where decisions are made.',
    'Machine-learning pipelines are usually reported as a whole. The contribution of each component, and the sensitivity of the result to the feature count, is almost never shown.',
    'External predictors are often tested without checking what the model receives at prediction time, and at horizons where their own future values would not be known. Both can distort their apparent value.',
  ]));

  c.push(H2('2.4. Conceptual Framework and Hypothesis Development'));
  c.push(P('We treat the forecasting system as a pipeline of design choices, each of which can be varied while ' +
    'the rest is held fixed. ' +
    'Each hypothesis is written the way a practitioner would expect it to hold, because the prior belief is ' +
    'the thing being tested.'));
  c.push(TCAP(1, 'Hypotheses, the design choice each one isolates, and the test used.'));
  c.push(TBL([620, 3300, 2500, 2940],
    ['', 'Hypothesis', 'What is varied', 'Test'],
    [
      ['H1', 'A machine-learning learner is the most accurate method, and no single method is best for every series.', 'Method, pooled and per series', 'Paired Wilcoxon against the leading method, Holm-corrected, and a count of per-series winners'],
      ['H2', 'Each component of the pipeline improves accuracy.', 'Selection rule, tuning, re-fitting, one at a time', 'Paired Wilcoxon, full pipeline against each removal, Holm-corrected'],
      ['H3', `The conventional count of ${acuanK} features is the right size.`, `Feature count, ${kList[0]} to ${kList[kList.length - 1]}`, `Paired Wilcoxon against k = ${acuanK}, Holm-corrected, and a per-series check`],
      ['H4', 'Adding market data improves accuracy.', 'Market data on or off', 'Paired Wilcoxon, on against off'],
      ['H5', 'The model draws most of its signal from the series own history.', 'Nothing, measured on the fitted model', 'SHAP importance by feature family'],
    ], { rightFrom: 99 }));
  c.push(NOTE('All tests are two-sided, so a hypothesis can be rejected in either direction.'));

  /* --------------------------------------------------- 3. Methodology */
  c.push(H1('3. Methodology'));

  c.push(H2('3.1. Research Design and Approach'));
  c.push(P('The study is a controlled comparison built around one machine-learning pipeline. ' +
    'The panel, the anchor date and the error measure stay the same throughout, and only one design element ' +
    'changes at a time. The statistical methods are benchmarks against which the pipeline is judged. ' +
    'Two evaluation designs are used, and the difference between them matters for how the results should be read.'));
  c.push(IMG('fig2_design.png', 560, 148));
  c.push(FCAP(2, 'The two evaluation designs. Panel A is the operational design, which trains on everything ' +
    'except the last day and forecasts that day, giving one error per series and no sampling distribution. ' +
    'Panel B supports the statistical tests. It re-fits parameters at every origin of a 30-day block and ' +
    'forecasts one day ahead from the actual history up to the day before.'));
  c.push(P('At a one-day horizon, using yesterday actual value is not leakage. It is how the desk works, ' +
    'since the forecaster always knows yesterday. ' +
    'That is why the rolling design is valid, and also why the usual distinction between recursive and direct ' +
    'multi-step strategies (Marcellino, Stock and Watson, 2006) does not arise here.'));

  c.push(H2('3.2. Data Sources'));
  c.push(P(`The panel has ${T.n_leaf} daily series of net foreign-exchange transaction flows. ` +
    '**All values are in millions of US dollars.** ' +
    `They cover ${fmt(T.n_hari)} business days from 2 January 2006 to 26 August 2026. ` +
    'Each series is one counterparty group and one declared purpose, as in Figure 1. ' +
    '**A positive value is net demand for foreign exchange, and a negative value is net supply.** ' +
    'Exporters, for example, sell the foreign currency they earn, so the export cells are negative on average, ' +
    'while importers buy it and the import cells are positive.'));
  // Masukan no. 4: yang harus tersurat adalah PENGGABUNGANNYA. Sel PMA lama
  // disebut dengan deskripsinya, bukan kodenya, karena sesudah penggantian
  // nama "A.1" berarti sel lain (lihat nama_leaf.json).
  c.push(P('The reporting framework records corporates with foreign direct investment separately from other ' +
    'corporates, and for three purposes, import, repatriation and other, that split leaves cells too thin to ' +
    'forecast. The thinnest is zero on 95.9 per cent of days, and its whole 30-day test block is zero, so any ' +
    'method that predicts zero would score perfectly on it. ' +
    'We therefore merge each of the three foreign-investment cells into the other-corporate cell with the same ' +
    'purpose, which reduces the grid from eighteen cells to fifteen. ' +
    'The merged series are A.2.d (Import), A.2.e (Repatriation) and A.2.f (Other). ' +
    'Flows are additive, so the merge moves no value between purposes and leaves the panel total unchanged to ' +
    'machine precision. It also matches how the supervisory question is asked, since it concerns corporates ' +
    'as a whole for these purposes.'));
  c.push(P(`The market data cover the same ${fmt(T.n_hari)} dates, with no date missing on either side. ` +
    `${Kata(T.pasar ? T.pasar.n_var : 8)} variables are used. They are spot USD/IDR bid and ask, one-month ` +
    'forward bid and ask, the ten-year government bond yield, the dollar index, net non-resident equity ' +
    'flows, and the equity index. ' +
    (T.pasar
      ? `Missing values are rare. No variable exceeds ${n(T.pasar.hilang_maks, 1)} per cent missing and ` +
        `${kata(T.pasar.n_tanpa_hilang)} of the ${kata(T.pasar.n_var)} have none. ` +
        `Gaps are carried forward, and no value is carried backwards by more than ` +
        `${kata(T.pasar.bfill_maks)} date, so the training sample holds no future information.`
      : 'Missing values are rare and are carried forward, and no value is carried backwards by more than ' +
        'one date, so the training sample holds no future information.')));
  c.push(TCAP(2, `Descriptive statistics for the ${T.n_leaf} series. Values in millions of US dollars.`));
  c.push(descTable());
  c.push(NOTE(`Sparsity still varies a great deal after the merge. The zero share runs from ` +
    `${n(Math.min(...T.desc.map(d => d.zero)), 1)} per cent of days to ` +
    `${n(Math.max(...T.desc.map(d => d.zero)), 1)}, and excess kurtosis from ` +
    `${n(Math.min(...T.desc.map(d => d.kurt)), 1)} to ${n(kurtMaks, 0)}.`));

  c.push(H2('3.3. The Machine-Learning Pipeline'));
  c.push(P('The pipeline has five parts, and Section 4 tests each of them. A pool of features is engineered ' +
    'from each series own history. A redundancy-aware rule selects a fixed number of them. Three tree ' +
    'ensembles are fitted on the selection. Their hyperparameters are tuned per series on a validation block. ' +
    'And every model is re-fitted at every forecast origin.'));

  c.push(H3('Feature pool'));
  c.push(P(`The pool holds ${T.pool_internal} candidates, all built from the series own history. ` +
    `${Kata(T.n_lags)} lags of the target enter the pool, every day from one to fifteen and then twenty, ` +
    'twenty-five and thirty. ' +
    'At a one-day horizon the near lags are where signal is most likely to sit, so the selector is offered ' +
    'all of them rather than a sparse subset. ' +
    `Rolling means, standard deviations, minima and maxima use windows of ${jendelaTeks} business days, and ` +
    'the pool also holds exponentially weighted means, differences and percentage changes, volatility and ' +
    'extreme-value measures, technical indicators, Fourier terms and calendar effects.'));
  c.push(P('Every window in the pool is a multiple of five business days, that is, a whole number of trading ' +
    'weeks. A window that cuts a week in two mixes the start of one week with the end of another, and flows ' +
    'follow a weekly settlement rhythm, so whole-week windows keep that rhythm out of the rolling statistics. ' +
    `The same rule sets the volatility windows (${daftar(J.volatilitas.map(String))} days), the RSI ` +
    `(${J.rsi.join(', ')}), the z-scores (${daftar(J.z_score.map(String))}), the Fourier periods ` +
    `(${daftar(J.fourier.map(String))}) and the weekly cycle of ${J.minggu_hari} business days. ` +
    `One consequence is visible. The MACD indicator uses ${J.macd[0]}, ${J.macd[1]} and ${J.macd[2]} days ` +
    'rather than the conventional 12, 26 and 9.'));
  // Angka fitur pasar DITURUNKAN dari konfigurasi, dengan penjaga yang
  // menggagalkan build bila kolamnya tidak konsisten.
  const nLagPasar = T.lag_pasar.length;
  const lagMaks = T.lag_pasar[nLagPasar - 1];
  const perVariabel = nLagPasar + 1;
  const nVariabel = T.pool_pasar / perVariabel;
  if (!Number.isInteger(nVariabel) || T.pool_internal + T.pool_pasar !== T.pool_total) {
    throw new Error(`kolam fitur tidak konsisten: ${T.pool_internal} internal + ` +
      `${T.pool_pasar} pasar != ${T.pool_total} total, atau ${T.pool_pasar} pasar ` +
      `tidak habis dibagi ${perVariabel} fitur per variabel`);
  }
  c.push(P(`Where market data are tested, the ${kata(nVariabel)} market variables extend the pool to ` +
    `${T.pool_total} candidates. Each enters as ${kata(nLagPasar)} consecutive lags, every day from one to ` +
    `${kata(lagMaks)}, and a ${kata(T.rata_pasar)}-day rolling mean, which gives ${kata(perVariabel)} features ` +
    `per variable and ${T.pool_pasar} in all. ` +
    'No contemporaneous value of any market variable enters the model, because on the morning a forecast is ' +
    'made that day market data do not yet exist. ' +
    'The market candidates are added to the engineered ones, not substituted for them, so all ' +
    `${T.pool_total} compete for the same fixed number of slots.`));

  c.push(H3('Redundancy-aware feature selection'));
  c.push(P('Selection is where the pipeline does most of its work, because the pool offers far more ' +
    'candidates than a learner is allowed to keep. ' +
    'We use the minimum-redundancy maximum-relevance criterion, mRMR, of Peng, Long and Ding (2005) in its ' +
    'correlation form. The relevance of a candidate is its absolute Spearman correlation with the target. ' +
    'Its redundancy is its mean absolute Spearman correlation with the features already chosen. ' +
    'Selection is greedy. The most relevant candidate is taken first, and each later step adds the candidate ' +
    'with the highest score'));
  c.push(EQ('score(f)  =  |ρ(f, y)|  −  β · (1 ⁄ |S|) ∑ₛ∈S |ρ(f, s)|'));
  c.push(P('where y is the target, S the set already chosen and β the weight on redundancy. ' +
    'Selection stops when k features are held. ' +
    'We set β = 1, which weighs relevance and redundancy equally. Setting β = 0 recovers the univariate rule ' +
    'that ranks candidates by relevance alone, and that rule is the comparison in Section 4.3.'));
  c.push(P('Three details matter in practice. ' +
    'The greedy search runs over a shortlist of the most relevant candidates, max(3k, 40) of them, rather ' +
    'than the whole pool. That keeps the correlation matrix small, and it means a candidate with little ' +
    'relevance can never enter on the strength of low redundancy alone. ' +
    'The correlations are Spearman rather than Pearson because the flows are heavy-tailed, with excess ' +
    `kurtosis up to ${n(kurtMaks, 0)}, and a rank correlation is not dominated by a handful of extreme days. ` +
    'And all correlations are computed on the training sample of each origin only.'));
  c.push(P('The case that motivates the criterion is a run of near-duplicates. Lags one and two of a ' +
    'persistent series, or its 20-day and 25-day means, carry almost the same information. ' +
    'A univariate rule admits both because both are relevant, and a block of such twins can fill most of ' +
    'the slots. mRMR admits the first and then asks the second to justify itself against it, which leaves ' +
    'room for features that carry different information.'));

  c.push(H3('Learners, tuning and re-fitting'));
  c.push(P('Three tree ensembles are fitted on the selected features. Random forest averages bagged ' +
    'regression trees (Breiman, 2001). LightGBM (Ke et al., 2017) and XGBoost (Chen and Guestrin, 2016) ' +
    'fit gradient-boosted trees, the first with histogram-based splitting and the second with a regularised ' +
    `objective. Every learner keeps k = ${acuanK} features, the count fixed before the study began, and ` +
    'Section 4.4 tests that choice.'));
  c.push(P(`Hyperparameters are tuned for each series and learner separately. We search the four ` +
    `configurations in Table 3 on a validation block of ${T.nval} one-day origins that ends where the test ` +
    'block begins. Within the validation block the models are re-fitted at every origin, exactly as in the ' +
    'test, and the configuration with the lowest mean scaled error is carried forward unchanged. ' +
    'Tuning and evaluation therefore use disjoint days. ' +
    'In the test block every model is re-fitted at every origin, which is how the system is meant to run.'));
  c.push(TCAP(3, 'Hyperparameter grid for the three learners. Configuration 1 is the library default. ' +
    `The number in brackets is how many of the ${T.n_leaf} series selected that configuration.`));
  c.push(gridTable());

  c.push(H2('3.4. Benchmark Methods'));
  c.push(P('Seven statistical methods serve as benchmarks. They range from forecasts that need no ' +
    'estimation at all to full time-series models, and they are listed in Table 4. ' +
    'Each is fitted on the same training data and scored on the same origins as the learners.'));
  c.push(TCAP(4, 'The seven benchmark methods.'));
  c.push(TBL([2200, 1500, 5660],
    ['Method', 'Family', 'What it does'],
    [
      ['Random walk', 'Naive', 'Forecast equals yesterday. The MASE scale is defined against this method on the training sample.'],
      ['Rolling mean', 'Naive', 'Mean of the last 90 days. Suits a series that reverts to its mean.'],
      ['Random walk with drift', 'Naive', 'Yesterday plus the average trend over the whole history.'],
      ['Croston', 'Intermittent', 'Smooths non-zero sizes and the gaps between them separately (Croston, 1972). Built for series with many zeros.'],
      ['Seasonal decomposition', 'Structural', 'Multiplies a month-of-year share, a day-of-month share and an annual level, with a scaling factor calibrated on recent data.'],
      ['ARIMA', 'Statistical', 'Order picked automatically by information criterion, with stationarity checked by KPSS.'],
      ['Prophet', 'Statistical', 'Splits the series into a trend and several seasonal terms (Taylor and Letham, 2018), with its default seasonality settings.'],
    ], { rightFrom: 99 }));
  c.push(NOTE('The seasonal decomposition is an in-house baseline, known internally as the APUVA algorithm. ' +
    'It is named here for the standard method it matches, a multiplicative seasonal-index forecast built ' +
    'from nested calendar shares.'));

  c.push(H2('3.5. Evaluation and Statistical Inference'));
  c.push(P('Figure 3 sets out the whole evaluation procedure, from the raw series to the reported test. ' +
    'Each series is split in time order into a training sample, a validation block for tuning and a test ' +
    'block. The learners are tuned on the validation block, every method is then re-fitted and scored at ' +
    'each test origin, the forecasts are paired across the arms of each experiment, and the paired ' +
    'differences are tested and corrected for multiple testing. The rest of this section describes each ' +
    'step.'));
  c.push(IMG('fig3_evaluasi.png', 560, 477));
  c.push(FCAP(3, `The evaluation procedure. Steps 2 and 3 run separately for each of the ${T.n_leaf} series. ` +
    `Tuning uses the ${T.nval}-origin validation block only, so the configuration is fixed before the ` +
    'test block is seen. Step 5 lists the four experiments, and every one of them passes through the same ' +
    'paired tests and correction in step 6.'));
  c.push(H3('Accuracy measure'));
  c.push(P('Accuracy is the mean absolute scaled error, or MASE, proposed by Hyndman and Koehler (2006) as a ' +
    'generally applicable replacement for percentage-based measures. ' +
    'Percentage errors are undefined when the actual value is zero and asymmetric between over- and ' +
    'under-prediction, and scaling by an in-sample benchmark avoids both problems.'));
  c.push(P('Let Yₜ be the actual value at time t and Fₜ the forecast, so the error is eₜ = Yₜ − Fₜ. ' +
    'The scaled error divides it by the mean absolute first difference of the training sample of n observations'));
  c.push(EQ('qₜ  =  eₜ  ⁄  [ (1 ⁄ (n − 1)) ∑ᵢ₌₂ⁿ |Yᵢ − Yᵢ₋₁| ]'));
  c.push(P('and MASE is the mean of the absolute scaled errors over the m test points'));
  c.push(EQ('MASE  =  (1 ⁄ m) ∑ₜ₌₁ᵐ |qₜ|'));
  c.push(P('The denominator is the in-sample mean absolute error of the random walk. Three properties ' +
    'follow, and all three matter for this panel.'));
  c.push(...BUL([
    `It is scale-free. The ${T.n_leaf} series differ in size by two orders of magnitude, so raw errors cannot be pooled across them, while scaled errors can.`,
    'It is defined when actual values are zero. Several cells here are zero on a third of days or more, which rules out the mean absolute percentage error.',
    'It reads naturally. A MASE of one matches the in-sample random walk, below one beats it and above one loses to it.',
  ]));
  c.push(NOTE('The denominator is computed on the training sample only, never on the test block. ' +
    'Because it is fixed before testing begins, the random walk own MASE on the test block is not exactly ' +
    'one, and it is reported as measured.'));

  c.push(H3('Paired tests'));
  c.push(P('Every comparison in this paper is paired. The unit is one forecast, identified by series, ' +
    'learner and origin, and both arms of a comparison forecast exactly the same units. ' +
    'For each unit we take the difference in absolute scaled error between the two arms, and the Wilcoxon ' +
    'signed-rank test (Wilcoxon, 1945) asks whether those differences are centred on zero. ' +
    'It ranks the absolute differences, gives each rank the sign of its difference, and compares the sum of ' +
    'positive ranks with what symmetry around zero would produce.'));
  c.push(P('We use it rather than a paired t-test because the differences are heavy-tailed. Scaled errors ' +
    'on this panel exceed 12 on single days, and a t-test on such data is driven by the few largest ' +
    'differences. The signed-rank test weighs each unit by its rank, so one extreme day counts once. ' +
    'Units with identical errors in both arms say nothing about direction and are dropped from the ' +
    'statistic. This matters in the market-data tests, where a series that admits no market feature gives ' +
    'identical forecasts in both arms. All tests are two-sided. ' +
    `A comparison between two methods pairs ${T.n_leaf} series and 30 origins for ${fmt(nPasangMetode)} ` +
    `units, and a comparison inside the pipeline pools the three learners for ${fmt(nPasangPipa)}.`));
  c.push(P('Two cautions govern how the p-values should be read. ' +
    'The statistic uses the direction and rank of each difference, not its size, so a setting that wins ' +
    'slightly on most units and fails badly on a few can pass the test. We therefore report the mean, the ' +
    'median and the maximum next to every p-value. ' +
    'More important, the units are not independent. Thirty consecutive origins of the same series share a ' +
    `history, so the effective sample is smaller than ${fmt(nPasangPipa)} and the nominal p-values are too ` +
    'small. Where a result matters for a recommendation we repeat the test with the series as the unit, ' +
    `averaging each series over learners and origins and testing the ${T.n_leaf} paired means. That test ` +
    'has little power, but it cannot be flattered by dependence across origins.'));

  c.push(H3('Correction for multiple testing'));
  c.push(P('A study that runs many tests on the same forecasts will find some small p-values by chance. ' +
    'We control this with the Holm-Bonferroni procedure (Holm, 1979), applied within each family of tests ' +
    'that answers one question. ' +
    'Holm orders the m p-values of a family from smallest to largest and compares the i-th smallest with ' +
    'α ⁄ (m − i + 1). The smallest must clear α ⁄ m, as in a Bonferroni correction, the next α ⁄ (m − 1), ' +
    'and so on, and testing stops at the first p-value that fails. ' +
    'Equivalently, the adjusted p-value of the i-th smallest is'));
  c.push(EQ('p̃₍ᵢ₎  =  min { 1,  maxⱼ≤ᵢ (m − j + 1) · p₍ⱼ₎ }'));
  c.push(P('and a test is significant when its adjusted value is below α = 0.05. ' +
    'The procedure controls the family-wise error rate, the probability of even one false rejection, ' +
    'whatever the dependence among the tests. That suits this study, where every test in a family reuses ' +
    'the same forecasts. It is also never less powerful than the plain Bonferroni correction. ' +
    `Three families are corrected. They are the ${T.champion_koreksi.n_uji} comparisons of every method ` +
    `against the leading one, the ${T.reverse_ablation.length} components removed in the reverse ablation, ` +
    `and the ${abl.length - 1} feature counts compared with ${acuanK}. ` +
    'For the method comparison we also report the Benjamini-Hochberg adjustment (Benjamini and Hochberg, ' +
    '1995), which controls the expected share of false discoveries and gives a less strict reading.'));

  c.push(H3('Ablation designs'));
  c.push(P('Two ablations take the pipeline apart. ' +
    'The reverse ablation removes one component at a time from the full pipeline and leaves the other two ' +
    'in place. Redundancy-aware selection is replaced by the univariate rule, daily re-fitting by one fit ' +
    'per block, and tuned hyperparameters by the library defaults. Each result is therefore what that ' +
    'component adds on top of the rest. ' +
    `The feature-count ablation varies k over ${kata(kList.length)} settings, ${daftar(kList.map(String))}, ` +
    `with ${acuanK} as the reference.`));
  c.push(NOTE('The feature-count and market-data experiments fit each model once per test block rather than ' +
    'at every origin. They report the difference between arms rather than the level of accuracy, and the ' +
    'same shortcut applies to every arm, so it shifts both sides of each comparison equally. ' +
    'The method comparison and the reverse ablation re-fit at every origin.'));
  c.push(P('To see which features the fitted models actually use, we compute SHAP values on the fitted ' +
    'trees (Lundberg and Lee, 2017). They split each prediction into per-feature contributions, so they show ' +
    'not only which features matter but in which direction.'));

  /* ------------------------------------------------------- 4. Results */
  c.push(H1('4. Results'));

  c.push(H2('4.1. Data Presentation and Description'));
  c.push(P('Table 2 shows a panel that is heterogeneous in every way that matters. Means run from ' +
    `${n(Math.min(...T.desc.map(d => d.mean)), 0)} to +${n(Math.max(...T.desc.map(d => d.mean)), 0)} million ` +
    `US dollars, excess kurtosis passes 200 in ${kata(T.desc.filter(d => d.kurt > 200).length)} ` +
    `series and sits below 1 in ${T.desc.filter(d => d.kurt < 1).length === 1 ? 'another' : kata(T.desc.filter(d => d.kurt < 1).length)}, and the zero share runs ` +
    `from ${n(Math.min(...T.desc.map(d => d.zero)), 1)} to ` +
    `${n(Math.max(...T.desc.map(d => d.zero)), 1)} per cent.`));
  c.push(P('Two features are shared by almost every series. ' +
    'Day-to-day autocorrelation of the level is positive everywhere, from 0.13 to 0.88. More useful for a ' +
    `learner, the autocorrelation of absolute changes is positive in all ${T.n_leaf} series, with a median near 0.49. ` +
    'That is volatility clustering, and it is why volatility measures sit in the feature pool.'));

  /* ---------------------------------------------------------------- H1 */
  c.push(H2('4.2. Does the Machine-Learning Pipeline Beat the Benchmarks?'));
  c.push(P(`Table 5 gives the headline design, where every model trains on ${fmt(T.n_hari - 1)} days and ` +
    'forecasts 26 August 2026. Table 6 gives the same methods over 30 rolling one-day origins, and every ' +
    'test in this section uses Table 6.'));
  c.push(TCAP(5, `Headline design. Ten methods trained on ${fmt(T.n_hari - 1)} business days and tested on 26 August 2026. Averaged over the ${T.n_leaf} series.`));
  c.push(rankTable(e1rank));
  c.push(TCAP(6, 'Rolling design with the full pipeline. The same methods over 30 one-day origins, '
    + `${T.n_leaf * 30} forecasts each. The learners use redundancy-aware selection, tuned `
    + 'hyperparameters and re-fitting at every origin.'));
  c.push(rankTable(e2rank));
  c.push(...h1Prose());
  c.push(IMG('fig3_leaf.png', 560, 250));
  c.push(FCAP(4, 'Accuracy by series over 30 one-day origins. Each row is one series and each grey dot one ' +
    'method. The orange dot marks the best method for that series and the blue tick the random walk. ' +
    'The dashed line at MASE = 1 is the in-sample random-walk scale.'));
  c.push(...winnersProse());
  c.push(IMG('fig4_winners.png', 560, 227));
  c.push(FCAP(5, `How many of the ${T.n_leaf} series each method wins. `
    + `${Kata(T.n_metode_menang)} methods win at least one series and none wins more than ${kata(bestCount[0][1])}.`));

  /* ---------------------------------------------------------------- H2 */
  c.push(H2('4.3. What Each Part of the Pipeline Contributes'));
  c.push(P('The learners in Table 6 run inside the full pipeline. Which of its components earns its place? ' +
    'We remove them one at a time, each arm switching off exactly one component and leaving the other two ' +
    `in place. Each arm covers ${fmt(nPasangPipa)} paired forecasts.`));
  c.push(TCAP(7, 'Reverse ablation. Each row removes one component from the full pipeline. '
    + 'A positive change means the full pipeline is better by that much. Wins count the paired forecasts on '
    + 'which the full pipeline is the more accurate. The verdict uses the Holm-adjusted p-value across the '
    + 'three components.'));
  c.push(reverseAblationTable());
  c.push(IMG('fig9_ablation.png', 560, 265));
  c.push(FCAP(6, 'What each component contributes, by learner and pooled. ' +
    'Bars above zero mean the full pipeline is better. The dashed line is the pooled effect, and its ' +
    'paired test and Holm-adjusted p-value are printed below each group.'));
  c.push(...reverseAblationProse());

  /* ---------------------------------------------------------------- H3 */
  c.push(H2('4.4. How Many Features to Keep'));
  c.push(P('The feature-count ablation holds the learners, the data, the origins and the metric fixed and ' +
    `changes only the number of features kept. Figure 7 shows the curve and Table 8 gives the tests against ` +
    `k = ${acuanK}.`));
  c.push(IMG('fig5_kablation.png', 560, 197));
  c.push(FCAP(7, 'Feature-count ablation. The left panel shows mean and median MASE against the number of ' +
    `features kept, pooled over three learners, ${T.n_leaf} series and 30 origins. The right panel shows the ` +
    'worst scaled error at each count.'));
  c.push(TCAP(8, `Feature-count ablation against k = ${acuanK}. The Holm column corrects for the ` +
    `${abl.length - 1} counts tested. The series column repeats the test with the ${T.n_leaf} series as the unit.`));
  c.push(ablationTable());
  c.push(...ablationProse());

  /* ---------------------------------------------------------------- H4 */
  c.push(H2('4.5. Do Market Data Help?'));
  c.push(P(`The ${kata(nVariabel)} market variables are known for every date in the sample, including the ` +
    'test dates. One day ahead that is not an assumption, since yesterday exchange rate and bond yield are on ' +
    'the screen when today forecast is made. The test is therefore a fair one, provided the model actually ' +
    'receives those values when it forecasts.'));
  c.push(IMG('fig6_external.png', 560, 197));
  c.push(FCAP(8, 'Market data as first tested, under both selection rules and both feature counts. '
    + 'The left panel shows mean MASE with market data off and on. The right panel shows the share of '
    + 'non-tied paired forecasts on which the market-off arm is the better one, with the share of tied pairs '
    + 'printed above each bar. The rest of this section shows that most of this loss is an artefact of the pipeline.'));
  c.push(...externalProse());
  c.push(TCAP(9, 'Series by series, engineered features only against engineered features plus market data, '
    + `under redundancy-aware selection. Mean MASE over 30 one-day origins, pooled across the three learners. `
    + '"Market slots" counts the market features the selector retains at 25 features.'));
  c.push(perLeafTable());
  c.push(...perLeafProse());

  c.push(H3('The market-data loss is mostly an artefact'));
  c.push(...suppliedProse());
  c.push(TCAP(10, 'Market data supplied at prediction time against the same data zero-filled, both measured '
    + 'against the no-market baseline. Mean MASE over 30 one-day origins, pooled across the three learners. '
    + '"Recovered" is the share of the zero-filled penalty that disappears once the features are supplied.'));
  c.push(suppliedTable());
  c.push(IMG('fig6b_pasar_benar.png', 560, 212));
  c.push(FCAP(9, 'Three arms of the same comparison. '
    + 'The left panel shows mean MASE with market data off, supplied at training but zero-filled at '
    + 'prediction, and supplied at both. The right panel shows each arm as a penalty against the no-market '
    + 'baseline, with the share of the zero-filled penalty that the correction removes.'));
  c.push(IMG('fig11_slot_damage.png', 560, 220));
  c.push(FCAP(10, 'Why the penalty scaled with exposure. Each point is one series at 25 features under '
    + 'redundancy-aware selection. With market features zero-filled at prediction (left), the penalty rises '
    + 'with the number of slots the selector gives them. Once the features are supplied (right), the '
    + 'relationship disappears.'));
  c.push(...slotDamageProse());

  c.push(H3('Does the selection rule change the verdict?'));
  c.push(P('A univariate rule ranks features one at a time and is blind to overlap, so a block of ' +
    'market variables, each correlated with the level and with each other, could crowd out lags simply by ' +
    'arriving together. If that were the whole story the market-data loss would be a fault of the selector ' +
    'and would shrink under the redundancy-aware rule. We repeat the comparison under both rules.'));
  c.push(IMG('fig10_selector.png', 560, 204));
  c.push(FCAP(11, 'The two selection rules compared. The left panel shows how many market features each ' +
    'rule admits. The right panel shows the change in mean MASE from using the redundancy-aware rule instead ' +
    'of the univariate one, with market data off.'));
  c.push(...selectorProse());

  /* ---------------------------------------------------------------- H5 */
  c.push(H2('4.6. What the Model Relies On'));
  c.push(P('Selection decides which features enter the model, not how much each contributes once it is ' +
    'fitted. Figure 12 shows what the selector kept for each series and how much of the fitted importance the ' +
    'market variables carry, and Figure 13 pools the importance by feature family.'));
  c.push(IMG('fig8_slotcomposition.png', 560, 242));
  c.push(FCAP(12, 'What the selector kept, series by series, at 25 features with market data switched on. ' +
    'The left panel divides the 25 slots between market variables, the series own lags and everything else. ' +
    'The right panel shows the share of total absolute SHAP value carried by the market variables.'));
  c.push(IMG('fig7_shapfamily.png', 560, 212));
  c.push(FCAP(13, 'Feature importance by family, from SHAP values on the fitted trees, averaged across all ' +
    `${T.n_leaf} series at 25 features with market data switched on.`));
  c.push(...famProse());

  /* ---------------------------------------------------- 5. Discussion */
  c.push(H1('5. Discussion'));

  c.push(H2('5.1. Synthesis and Interpretation of Findings'));
  c.push(...synthProse());

  c.push(H2('5.2. Alignment and Contrast with Prior Research'));
  c.push(P('The central result, a machine-learning pipeline that leads on average but cannot be separated ' +
    'from the best statistical methods, is what the forecasting competitions would predict ' +
    '(Makridakis, Spiliotis and Assimakopoulos, 2018, 2020). ' +
    `The random walk is not the best method overall here, but it is still best on ` +
    `${kata(Object.values(T.best_per_leaf).filter(m => m === 'Naive').length)} of the ${T.n_leaf} series, ` +
    'and it needs no estimation at all.'));
  // Perbandingan lintas horizon memakai ablasi h=60 LAMA (kolam fitur lama,
  // sel sebelum penggabungan). Itu disebut terbuka, bukan disembunyikan.
  c.push(P('The feature-count result fits bias-variance theory once the horizon is taken into account. ' +
    `One day ahead, keeping more than ${acuanK} features tends to help and no tighter count does. ` +
    (T.ablasi_h60
      ? `Sixty days ahead the direction is the opposite. In our own earlier ablation on the same reporting ` +
        `framework, over ${T.ablasi_h60.n_leaf} cells, ${kata(T.ablasi_h60.n_jendela)} rolling windows and the same ` +
        `${kata(T.ablasi_h60.n_model)} tree models (${T.ablasi_h60.n_unit} paired units), keeping ` +
        `${T.ablasi_h60.terbaik_k} features rather than ${T.ablasi_h60.acuan_k} lowered mean MASE by ` +
        `${n(Math.abs(T.ablasi_h60.terbaik_delta_pct), 1)} per cent. ` +
        `That ablation predates both the merge described in Section 3.2 and the whole-week feature windows. ` +
        `Its cells are the ${T.ablasi_h60.n_leaf} unmerged ones and include the degenerate series this paper ` +
        'merges away, and it fixes the hyperparameters rather than tuning them, so it is a comparison of ' +
        'horizons rather than a like-for-like extension of Table 8. '
      : 'Sixty days ahead, in our own earlier ablation, the direction is the opposite. ') +
    'The plausible reading is that a one-day forecast can use many weakly informative recent features, while ' +
    'at a long horizon the same features mostly add variance. The configuration that is right at one ' +
    'horizon is an untested assumption at another, which is the lesson the direct-versus-iterated ' +
    'literature draws from a different angle (Marcellino, Stock and Watson, 2006).'));
  c.push(P('The redundancy-aware selector does not deliver what its design promises for these learners. ' +
    'mRMR was built for pools of overlapping candidates, and our pool is exactly that. But tree ensembles ' +
    'already cope with redundant inputs, because each split picks one of a group of correlated features ' +
    'and ignores the rest, so removing duplicates gives them little they did not have. ' +
    'The market-data result, meanwhile, contrasts with the microstructure literature (Evans and Lyons, 2002), ' +
    'which studies how flows move prices. We test the reverse direction, one day ahead and on top of the ' +
    'flow series own history, and in this panel that direction is weak.'));

  c.push(H2('5.3. Theoretical and Practical Implications'));
  c.push(P('Six recommendations follow for an institution running a machine-learning system like this one.'));
  c.push(...BUL([
    `**Model each counterparty and purpose cell on its own.** ${Kata(T.n_metode_menang)} methods win at least one cell and none wins more than ${kata(T.menang_terbanyak)}, so one pooled choice is worse for most of the grid.`,
    `**Treat machine learning as a reasonable default, not a proven improvement.** The learners lead on average, but ${daftar(T.champion_koreksi.tak_signifikan_holm.filter(m => !POHON.includes(m)).map(nice))} cannot be separated from the leader after correction. Keep the best statistical methods running alongside.`,
    '**Test each pipeline component by removing it.** None of the three components tested here is separable from noise, and one points the wrong way on average. A component that is not tested by removal is an assumption, however standard it is.',
    `**Tune at the horizon you will run, and include the feature count in the tuning.** More than ${acuanK} features tends to help one day ahead, while fewer helps sixty days ahead. A count copied from another horizon or another feature pool is untested.`,
    `**Check what your forecaster actually receives at prediction time, before concluding a predictor is useless.** Training on a feature and then withholding it at forecast time is silent, and here it accounted for ${n(T.tabel8b_gabungan.rusak_hilang_pct, 0)} per cent of an apparent ${n(T.tabel8b_gabungan.delta_nol, 1)} per cent penalty on market data. If the damage scales with how much of the feature pool the predictor occupies, suspect the plumbing before the data.`,
    `**Decide on market data per series, and keep the random walk as a threshold.** Handled correctly, market data still cost ${n(T.tabel8b_gabungan.delta_benar, 1)} per cent on average but help ${kata(T.n_leaf_membaik)} series. And any series where the deployed model cannot beat the random walk should be flagged, because a free benchmark is doing better there.`,
  ]));

  c.push(H2('5.4. Research Limitations and Constraints'));
  c.push(...BUL([
    'The headline design has one test date. It is reported because it is the operational setting, but it supports description only, and every inferential claim here rests on the 30-origin design.',
    `The paired tests treat ${fmt(T.reverse_ablation[0].n)} forecasts as independent units, but consecutive origins of the same series are not independent, so the nominal p-values are too small. The Holm correction handles the number of tests, not this dependence. Where it matters most, for the feature count, the per-series test is not significant, and we read that result accordingly.`,
    `The feature count was fixed at ${acuanK} before the study and the ablation was run on the test block, so the counts that beat ${acuanK} were found on the same data they are reported on. We keep ${acuanK} for every other result for that reason. Choosing k on the validation block would remove the problem, and we leave it to future work.`,
    `The panel has ${T.n_leaf} series. That is enough to separate the learners from the weakest benchmarks and not enough to separate effects of one or two per cent, which is the size of every pipeline effect reported here. Absence of significance is a statement about the resolution of this study, not a demonstration that the components do nothing.`,
    `Hyperparameters are tuned on ${T.nval} validation origins. In an earlier run a validation block of 10 origins chose a different configuration in more than half of the cells, which is why the longer block is used. Sixty origins is long enough to avoid that instability, but not to resolve a tuning effect as small as the one measured here.`,
    'Only one horizon is studied, and the panel comes from one jurisdiction and one reporting framework. Under a managed float the central bank is itself a counterparty, so the flow-to-rate relationship measured here is partly a policy artefact. A shallow onshore market lets a single large settlement move a daily cell, which inflates the tails. And the reporting framework fixes both the counterparty categories and the declared purposes, so the grid is an institutional choice. In a deep free-floating market with a different taxonomy we would expect disaggregation to buy less and the market-data question to be worth asking again.',
    'Three reported cells are merges of two reporting categories each, as Section 3.2 sets out. That removes a degenerate cell but also removes the possibility of saying anything about foreign-investment corporates separately, which a supervisor may want.',
    `Reproducibility has two requirements. The first is the thread count. ARIMA order selection is sensitive to floating-point summation order, and in an earlier run the identical code and data with a different number of threads moved ${T.repro.arima_utas_berbeda.sel_bergeser} of the ${T.repro.arima_utas_berbeda.n_sel} ARIMA cells, shifting its pooled mean from ${n(T.repro.arima_utas_berbeda.mean_empat_utas, 4)} to ${n(T.repro.arima_utas_berbeda.mean_satu_utas, 4)}. No other method moved. With threads pinned to one, two complete re-runs over ${T.repro.arima_utas.leaf.length} series and ${T.repro.arima_utas.n_origin} origins each were bit-identical, maximum absolute difference ${n(T.repro.arima_utas.beda_maks_absolut, 1)}. All results reported here were produced with threads pinned.`,
    `The second requirement is the library stack. The results were produced under Python ${T.versi.python}, NumPy ${T.versi.numpy}, pandas ${T.versi.pandas}, scikit-learn ${T.versi.sklearn}, LightGBM ${T.versi.lightgbm}, XGBoost ${T.versi.xgboost} and statsmodels ${T.versi.statsmodels}. In an earlier run, re-computing SHAP under a different stack reproduced ${T.repro.shap_lintas_lingkungan.n_leaf_cocok} of ${T.repro.shap_lintas_lingkungan.n_leaf} series exactly, while on one series the market share of importance came out ${n(T.repro.shap_lintas_lingkungan.ext_share_utas_terkunci, 1)} per cent against ${n(T.repro.shap_lintas_lingkungan.ext_share_mesin_komputasi, 1)}. Pinning threads did not remove that difference, so replication should pin the library versions as well.`,
    'The market-data correction supplies the market series at prediction time, which is valid one day ahead because the required lags are already observed. It does not extend to multi-step recursive forecasting, where the future values of another series do not exist.',
  ]));

  /* -------------------------------------------- 6. Conclusion */
  c.push(H1('6. Conclusion and Future Work'));

  c.push(H2('6.1. Summary of Key Contributions'));
  c.push(...conclProse());

  c.push(H2('6.2. Policy and Practical Recommendations'));
  c.push(P('Beyond the six points above, a supervisory desk should be clear about what a single-date test ' +
    'can support. A ranking from one day describes that day. Deployment decisions need repeated origins, ' +
    'paired tests and a correction for the number of comparisons made, and the settings of a pipeline should ' +
    'be chosen on the institution own history rather than inherited.'));

  c.push(H2('6.3. Recommendations for Future Research'));
  c.push(...BUL([
    'Tune the feature count on the validation block together with the other hyperparameters, so that the best count is chosen on data the test never sees. This study shows that the count matters one day ahead but cannot say which count is best.',
    'Replace the per-forecast tests with methods that respect dependence across origins, such as a block bootstrap over consecutive origins, so that the p-values of small pipeline effects can be trusted.',
    'Test market data at longer horizons, where their own future values must also be forecast, and measure how much of any gain survives that.',
    'Model the sparse cells with methods built for intermittent demand, scored with measures suited to them, and test whether sibling series help one day ahead, where yesterday value of every other cell is known.',
  ]));

  /* ------------------------------------------------------ back matter */
  c.push(H1('Acknowledgements'));
  c.push(P('We thank colleagues in the foreign-exchange monitoring function for access to the reporting panel ' +
    'and for discussion of the operational requirements behind the evaluation design. ' +
    'Any errors are ours. ' +
    'The views expressed are those of the authors and not necessarily those of their institution.'));

  c.push(H1('References'));
  refs().forEach(r => c.push(new Paragraph({
    spacing: { after: 90, line: 280 }, indent: { left: 360, hanging: 360 }, children: runs(r),
  })));

  c.push(H1('Appendix A. Series-level results at the final date'));
  c.push(P('Table A1 reports the headline design one series at a time. It gives the actual value on 26 ' +
    'August 2026, the forecast from the best method for that series, and the scaled error.'));
  c.push(TCAP('A1', 'Series-level results for the headline design. Values in millions of US dollars. Best method chosen per series by MASE.'));
  c.push(appendixTable());

  /* ------------------------------------------- Lampiran B: beeswarm per seri */
  c.push(...appendixBeeswarm());

  return c;
}

/* ------------------------------------------------------------- fragments */

function descTable() {
  const rows = T.desc.map(d => [
    d.leaf, LABEL[d.leaf], n(d.mean, 1), n(d.sd, 1), n(d.med, 1),
    n(d.zero, 1), n(d.skew, 2), n(d.kurt, 1), n(d.acf1, 2),
  ]);
  return TBL([720, 1900, 940, 940, 860, 900, 880, 1060, 1060],
    ['Series', 'Purpose', 'Mean', 'SD', 'Median', 'Zero %', 'Skew', 'Kurtosis', 'AC(1)'],
    rows, { rightFrom: 2 });
}

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

function rankTable(rank) {
  const rw = rank.find(d => d.model === 'Naive');
  const rows = rank.map((d, i) => [
    String(i + 1), nice(d.model), n(d.mase, 3), n(d.med, 3),
    d.model === 'Naive' ? 'benchmark' : (d.mase < rw.mase ? 'better than random walk' : ''),
  ]);
  return TBL([700, 3000, 1900, 1900, 1860],
    ['Rank', 'Method', 'Mean MASE', 'Median MASE', 'Note'], rows,
    { rightFrom: 2, accRows: [0] });
}

function h1Prose() {
  const r = e2rank, top = r[0], ct = T.champion_tests, K = T.champion_koreksi;
  const rw = r.find(d => d.model === 'Naive');
  const nPohonDepan = r.findIndex(d => !POHON.includes(d.model));
  const statTerbaik = r.find(d => !POHON.includes(d.model));
  const ns = ct.filter(t => t.p_holm >= 0.05);
  const nsMentah = ns.filter(t => t.p < 0.05);           // nyata mentah, hilang sesudah Holm
  const sigH = ct.filter(t => t.p_holm < 0.05).sort((a, b) => a.p_holm - b.p_holm);
  const pertamaTerpisah = ct.filter(t => t.p_holm < 0.05)
    .sort((a, b) => r.findIndex(x => x.model === a.model) - r.findIndex(x => x.model === b.model))[0];
  const medTerendah = [...r].sort((a, b) => a.med - b.med)[0];
  const e1top = e1rank[0];
  const semuaDiAtasSatu = r.every(d => d.mase >= 1);
  const pohonMengalahkanRW = r.filter(d => POHON.includes(d.model)).every(d => d.mase < rw.mase);
  const out = [];
  out.push(P(`On average the pipeline leads. ` +
    (nPohonDepan === 3
      ? `The three learners take the first three places, with ${nice(top.model)} lowest at ` +
        `${n(top.mase, 3)}, followed by ${niceK(r[1].model)} at ${n(r[1].mase, 3)} and ${niceK(r[2].model)} ` +
        `at ${n(r[2].mase, 3)}. `
      : `${nice(top.model)} has the lowest mean MASE at ${n(top.mase, 3)}. `) +
    `The best benchmark is ${nice(statTerbaik.model)} at ${n(statTerbaik.mase, 3)}. ` +
    (semuaDiAtasSatu
      ? `No method averages below one, so none beats the in-sample random-walk scale, ` +
        (pohonMengalahkanRW
          ? `but every learner beats the random-walk forecast itself, which scores ${n(rw.mase, 3)} on the test block.`
          : `and the random-walk forecast itself scores ${n(rw.mase, 3)} on the test block.`)
      : `The random-walk forecast itself scores ${n(rw.mase, 3)} on the test block.`)));
  out.push(P(`Paired tests shrink the lead. ` +
    `All ${K.n_uji} comparisons against ${nice(top.model)} reuse the same forecasts, so they are corrected ` +
    `with the Holm procedure. ` +
    `${nice(top.model)} wins between ${Math.min(...ns.map(t => t.wins))} and ${Math.max(...ns.map(t => t.wins))} ` +
    `of the ${ns[0].n} pairs against each of ` +
    `${daftarN(ns.map(t => `${niceK(t.model)} (p = ${n(t.p, 3)}, Holm ${n(t.p_holm, 3)})`))}, ` +
    `and none of these ${kata(ns.length)} can be separated from it. ` +
    (nsMentah.length
      ? `${daftarN(nsMentah.map(t => nice(t.model)))} ${nsMentah.length > 1 ? 'are' : 'is'} separated at ` +
        `the nominal level but not after correction, and the Benjamini-Hochberg adjustment, which is less ` +
        `strict, gives ${daftarN(nsMentah.map(t => n(t.p_bh, 3)))}. `
      : '') +
    `The first method the corrected tests do separate is ${nice(pertamaTerpisah.model)} ` +
    `(Holm ${n(pertamaTerpisah.p_holm, 3)}), and every method below it is separated as well. ` +
    `The honest summary is therefore a leading group of ${kata(ns.length + 1)} methods, spanning ` +
    `${n(100 * (Math.max(...[top, ...ns.map(t => r.find(x => x.model === t.model))].map(d => d.mase)) - top.mase) / top.mase, 1)} ` +
    `per cent in mean error, rather than a winner.`));
  out.push(P(`The mean and the median agree on the leader here. ${nice(medTerendah.model)} also has the ` +
    `lowest median, ${n(medTerendah.med, 3)}. ` +
    `The headline design broadly agrees with the rolling one. The Spearman correlation between the two ` +
    `rankings is ${n(T.rank_corr.rho, 3)} (p = ${n(T.rank_corr.p, 4)}), and on the single test date ` +
    `${nice(e1top.model)} is the most accurate method. ` +
    `That agreement says the final date was not unusual, not that one test day is enough evidence. ` +
    `Figure 4 gives a stronger reason not to lean on any aggregate ranking, because the best method changes ` +
    `from series to series.`));
  // Pemeriksa: kalimat "mean dan median sepakat" hanya sah bila memang sepakat.
  if (medTerendah.model !== top.model) {
    throw new Error(`h1Prose: juara mean ${top.model} bukan juara median ${medTerendah.model}; tulis ulang kalimatnya`);
  }
  return out;
}

function winnersProse() {
  const w = T.winners;
  const cro = T.croston_leaves;
  const sp = T.sparsest;
  const sparse = w.filter(r => r.zero > 30);
  const spML = sparse.filter(r => r.fam === 'ML').length;
  const nML = w.filter(r => r.fam === 'ML').length;
  const c = [];
  c.push(P(`Counting winners across the ${T.n_leaf} series gives ` +
    daftarN(bestCount.map(([m, k]) => `${nice(m)} (${k})`)) + '. ' +
    `Machine learning is the best method on ${kata(nML)} series and the benchmarks on the other ` +
    `${kata(T.n_leaf - nML)}, and no method wins more than ${kata(bestCount[0][1])}. ` +
    `The best method for a series does beat the random walk on ${T.n_beat_rw} of the ${T.n_leaf}.`));
  c.push(P(`A natural guess is that sparsity picks the winner, with methods built for intermittent demand ` +
    `taking the series that are mostly zero. The guess does not survive. ` +
    `Croston, the one method built for intermittent series, wins ` +
    daftarN(cro.map(r => `${r.leaf} (${n(r.zero, 1)} per cent zero)`)) + ', ' +
    `none of which is sparse. ` +
    `Of the ${kata(sparse.length)} series that are zero on more than 30 per cent of days, machine learning ` +
    `wins ${kata(spML)}, and the sparsest of all, ${sp.leaf}, goes to ${nice(sp.best).toLowerCase()}. ` +
    `Sparsity does not predict how hard a series is either. The correlation between zero share and the best ` +
    `achievable error is ${n(T.winner_rho, 2)} (p = ${n(T.winner_p, 2)}). ` +
    `If a rule of thumb could pick the method from the data profile, per-series testing would be ` +
    `unnecessary. It cannot, so it is necessary. ` +
    `H1 is therefore only half supported. No single method is best for every series, but no learner can ` +
    `be separated from the best statistical methods either.`));
  return c;
}

function reverseAblationTable() {
  const rows = T.reverse_ablation.map(a => [
    a.component, n(a.opt, 4), n(a.off, 4), pct(a.delta),
    `${a.wins} / ${a.n}`, pv(a.p), pv(a.p_holm),
    a.sig ? 'significant' : 'not significant',
  ]);
  return TBL([2300, 1150, 1250, 1000, 1200, 1000, 1000, 1460],
    ['Component removed', 'MASE with it', 'MASE without it',
     'Change', 'Wins for full', 'Wilcoxon p', 'Holm p', 'Verdict'],
    rows, { rightFrom: 1 });
}

function reverseAblationProse() {
  const RA = T.reverse_ablation;
  const bm = T.reverse_by_model, lw = T.reverse_leaf_worse;
  const out = [];
  const nSig = RA.filter(a => a.sig).length;
  const nBantu = RA.filter(a => a.delta > 0).length;
  const rinci = a => `${n(Math.abs(a.delta), 2)} per cent for ${NAMA_KOMP[a.component]} ` +
    `(p = ${n(a.p, 3)}, Holm ${n(a.p_holm, 3)})`;
  out.push(P((nSig === 0
      ? 'None of the three components earns its place. '
      : `${Kata(nSig)} of the three components is separable from noise after correction. `) +
    (nBantu === 0
      ? `Removing any one of them lowers pooled error, by ${daftarN(RA.map(rinci))}. ` +
        'On average the pipeline is slightly better without each of them, and none of the three changes ' +
        'is separable from noise once the tests are corrected together.'
      : RA.map(a => `Removing ${NAMA_KOMP[a.component]} ${a.delta < 0 ? 'lowers' : 'raises'} pooled error by ` +
          `${n(Math.abs(a.delta), 2)} per cent (p = ${n(a.p, 3)}, Holm ${n(a.p_holm, 3)}).`).join(' '))));

  const perModel = comp => {
    const v = bm[comp];
    const bantu = URUT_POHON.filter((_, i) => v[i] > 0).map(m => NM_POHON[m]);
    const rugi = URUT_POHON.filter((_, i) => v[i] <= 0).map(m => NM_POHON[m]);
    return { bantu, rugi, v };
  };
  const bagian = RA.map(a => {
    const p = perModel(a.component);
    if (!p.bantu.length) return `${NAMA_KOMP[a.component]} helps none of the three`;
    if (!p.rugi.length) return `${NAMA_KOMP[a.component]} helps all three`;
    return `${NAMA_KOMP[a.component]} helps ${daftarN(p.bantu)} and hurts ${daftarN(p.rugi)}`;
  });
  out.push(P(`The breakdown by learner shows why the pooled figures are small. ` +
    `${bagian[0][0].toUpperCase() + bagian[0].slice(1)}, ${bagian[1]}, and ${bagian[2]}. ` +
    `Each component helps at least one learner and hurts at least one other, so the pooled mean is a ` +
    `cancellation rather than a consensus. The XGBoost column is the most negative throughout, ` +
    `at ${daftarN(RA.map(a => `${bm[a.component][2].toFixed(2)}`))} per cent for the three components.`));
  if (!RA.every(a => bm[a.component][2] === Math.min(...bm[a.component]))) {
    throw new Error('reverseAblationProse: XGBoost bukan yang paling negatif di setiap komponen; tulis ulang kalimatnya');
  }

  out.push(P(`Counting series makes the same point. Of the ${T.n_leaf} series, ` +
    daftarN(RA.map(a => `${NAMA_KOMP[a.component]} helps ${T.n_leaf - lw[a.component]}`)) + '. ' +
    `Each component is a bet that pays on some series and costs on others, the same heterogeneity the ` +
    `method comparison shows, one level down.`));

  const nDef = Object.values(T.cfg_terpilih).reduce((s, v) => s + v[0], 0);
  const nTot = Object.values(T.cfg_terpilih).reduce((s, v) => s + v.reduce((a, b) => a + b, 0), 0);
  out.push(P(`The tuning result is not a sign that tuning did nothing. Table 3 shows that it moved away from ` +
    `the library default in ${nTot - nDef} of ${nTot} series and learner pairs. The configurations it chose ` +
    `were different, and they were not measurably better on the test block. ` +
    `The honest reading is that a pipeline assembled from defensible components is, on a panel this size, ` +
    `indistinguishable from a simpler one. That is not an argument for discarding the components, since ` +
    `daily re-fitting costs seconds and helps ${kata(bm['Daily re-fitting'].filter(v => v > 0).length)} of the three learners. It is an argument against ` +
    `reporting any of them as a demonstrated improvement. H2 is rejected.`));
  return out;
}

function ablationTable() {
  const rows = abl.map(a => [
    String(a.k), n(a.mase, 3), n(a.median, 3), n(a.max, 1),
    a.k === T.ablation_acuan ? 'reference' : pct(a.delta),
    a.k === T.ablation_acuan ? '—' : `${a.wins} / ${a.n}`,
    a.k === T.ablation_acuan ? '—' : pv(a.p),
    a.k === T.ablation_acuan ? '—' : pv(a.p_holm),
    a.k === T.ablation_acuan ? '—' : n(a.p_leaf, 3),
  ]);
  return TBL([900, 1050, 1050, 900, 1100, 1250, 1000, 1000, 1110],
    ['k', 'Mean MASE', 'Median MASE', 'Max MASE', 'Change in mean', `Wins for k = ${T.ablation_acuan}`,
     'Wilcoxon p', 'Holm p', 'Series p'],
    rows, { rightFrom: 1, accRows: [abl.findIndex(a => a.k === T.ablation_acuan)] });
}

function ablationProse() {
  const A = T.ablation_acuan;
  const b = abl.find(r => r.k === A);
  const bawah = abl.filter(r => r.k < A), atas = abl.filter(r => r.k > A);
  const bawahBuruk = bawah.every(r => r.delta > 0);
  const bawahHolm = bawah.filter(r => r.p_holm < 0.05);
  const atasBaik = atas.every(r => r.delta < 0);
  const atasHolm = atas.filter(r => r.p_holm < 0.05);
  const pLeafMin = Math.min(...atas.map(r => r.p_leaf));
  const k30 = atas[0];
  const xgb = atas.map(r => r.per_model.XGBoost);
  const c = [];
  c.push(P(`Below the reference the answer is clear. ` +
    (bawahBuruk ? `Every tighter count is worse than ${A} in the mean, ` : 'Tighter counts are mostly worse than the reference, ') +
    `by between ${n(Math.min(...bawah.map(r => r.delta)), 2)} and ${n(Math.max(...bawah.map(r => r.delta)), 2)} per cent, ` +
    (bawahHolm.length
      ? `and ${daftarN(bawahHolm.map(r => `k = ${r.k}`))} survive${bawahHolm.length === 1 ? 's' : ''} the Holm correction. `
      : 'though none of the differences survives the Holm correction. ') +
    `Cutting the feature count buys nothing one day ahead.`));
  c.push(P(`Above the reference the curve keeps falling. ` +
    (atasBaik ? `All ${kata(atas.length)} larger counts are better than ${A}, ` : 'Larger counts are mostly better, ') +
    daftarN(atas.map(r => `k = ${r.k} by ${n(Math.abs(r.delta), 2)} per cent (Holm ${n(r.p_holm, 3)})`)) + '. ' +
    (atasHolm.length === atas.length
      ? `All of them survive the correction for the ${kata(abl.length - 1)} counts tested, which makes this the only pipeline effect in the study that does. `
      : `${Kata(atasHolm.length)} of them survive the correction. `)));
  c.push(P(`Three checks temper that result, and we give them equal weight. ` +
    `First, with the series as the unit the effect is not significant. The per-series tests give ` +
    `${daftarN(atas.map(r => `p = ${n(r.p_leaf, 3)}`))} for ${daftarN(atas.map(r => String(r.k)))}, ` +
    `although the larger counts are better on ${daftarN(atas.map(r => String(r.leaf_lebih_baik)))} of the ` +
    `${T.n_leaf} series. ` +
    `Second, the gain is not shared by every learner. For XGBoost the change is ` +
    `${daftarN(xgb.map(v => pct(v)))} at ${daftarN(atas.map(r => String(r.k)))} features, against ` +
    `${pct(k30.per_model.RandomForest)} for random forest and ${pct(k30.per_model.LightGBM)} for LightGBM at ${k30.k}. ` +
    `Third, the curve is not smooth. The gain at ${k30.k} is stable across the two halves of the test block ` +
    `(${pct(k30.paruh[0])} and ${pct(k30.paruh[1])}), while ` +
    daftarN(atas.slice(1).map(r => `at ${r.k} it moves from ${pct(r.paruh[0])} in the first half to ` +
      `${pct(r.paruh[1])} in the second`)) + '.'));
  c.push(P(`The reading we adopt is that more than ${A} features is at least as good as ${A} and probably ` +
    `slightly better one day ahead, but that the data do not identify a best count. ` +
    `The counts above ${A} were also found on the test block they are reported on. ` +
    `We therefore keep k = ${A}, the count fixed before the study, for every other result in this paper, ` +
    `and treat the feature count as a hyperparameter to be tuned on validation data in future work. ` +
    `The worst case does not discriminate between counts at all. The largest scaled error moves only between ` +
    `${n(Math.min(...abl.map(r => r.max)), 1)} and ${n(Math.max(...abl.map(r => r.max)), 1)} across the ` +
    `${kata(abl.length)} settings. ` +
    `H3 is therefore rejected, in the direction of more features rather than fewer, but not decisively.`));
  if (pLeafMin < 0.05) {
    throw new Error('ablationProse: uji per seri kini NYATA; kalimat "not significant" harus ditulis ulang');
  }
  return c;
}

function externalProse() {
  const E = T.external_full;
  const worst = E.reduce((m, r) => r.delta > m.delta ? r : m, E[0]);
  const best = E.reduce((m, r) => r.delta < m.delta ? r : m, E[0]);
  const c = [];
  c.push(P(`As first tested, market data look harmful. ` +
    `Switching them on raises mean error in all four conditions, by between ` +
    `${n(best.delta, 1)} and ${n(worst.delta, 1)} per cent, and it also loses on the count of days. ` +
    `Outside tied days the market-off arm is the better forecast on between ` +
    `${n(Math.min(...E.map(r => r.pct_off)), 1)} and ${n(Math.max(...E.map(r => r.pct_off)), 1)} per cent ` +
    `of them. ` +
    `Tied days are numerous and must be excluded. Where the selector gives a series no market slot the two ` +
    `arms are the same model, and in the tightest condition ${n(100 * E[0].ties / E[0].n, 0)} per cent of ` +
    `pairs are identical. Counting those as evidence would make the losing arm appear to win.`));
  c.push(P(`Taken alone this looks like a clean verdict against market data, and in the first version of ` +
    `this analysis that is how we read it. It is wrong. The models were trained on market features and then ` +
    `asked to forecast without them, and the subsection after Table 9 shows that most of the penalty ` +
    `belongs to that handling rather than to the data.`));
  return c;
}

function perLeafTable() {
  const rows = pl25.map(r => {
    const r12 = pl12.find(x => x.leaf === r.leaf);
    return [
      r.leaf, LABEL[r.leaf],
      n(r12.fe, 3), n(r12.fe_ext, 3), pct(r12.delta, 1),
      n(r.fe, 3), n(r.fe_ext, 3), pct(r.delta, 1), String(r.n_ext),
    ];
  });
  return TBL([700, 1560, 960, 960, 900, 960, 960, 900, 860],
    ['Series', 'Purpose', 'FE only', 'FE + market', 'Change', 'FE only', 'FE + market', 'Change', 'Market slots'],
    rows, { rightFrom: 2 });
}

function perLeafProse() {
  const c = [];
  const act25 = pl25.filter(r => r.n_ext > 0);
  const act12 = pl12.filter(r => r.n_ext > 0);
  const w25 = pl25.filter(r => r.delta > 0.5).length;
  const b25 = pl25.filter(r => r.delta < -0.5).length;
  const w12 = act12.filter(r => r.delta > 0.5).length;
  const b12 = act12.filter(r => r.delta < -0.5).length;
  const worst = pl25.reduce((a, b) => (a.delta > b.delta ? a : b));
  const best = pl25.reduce((a, b) => (a.delta < b.delta ? a : b));
  const sp = T.per_leaf_spearman_informative;
  const N = T.n_leaf;
  const lagMaks = T.lag_pasar[T.lag_pasar.length - 1];
  c.push(P(`Table 9 breaks the same test down by series. Columns three to five keep 12 features and ` +
    `columns six to eight keep 25. "FE only" holds just the engineered candidates, and "FE + market" adds ` +
    `the market variables, each at lags 1 to ${lagMaks} plus a ${kata(T.rata_pasar)}-day mean, so all ` +
    `${T.pool_total} candidates compete for the same slots.`));
  c.push(P(`How much of the panel is exposed depends on the feature count. ` +
    `At 12 features only ${act12.length} of ${N} series admit any market feature and the rest are ` +
    `unchanged, as they must be. Of those affected, ${w12} get worse and ${b12} better. ` +
    `At 25 features ${act25.length} of ${N} admit at least one, ` +
    `${w25} series get worse and ${b25} better. ` +
    `The worst is ${worst.leaf} (${LABEL[worst.leaf]}) at ${pct(worst.delta, 1)} and the best ` +
    `${best.leaf} (${LABEL[best.leaf]}) at ${pct(best.delta, 1)}.`));
  c.push(P(`The damage tracks exposure closely. Across the ${sp.n} affected series at 25 features the rank ` +
    `correlation between market slots and the penalty is ${n(sp.rho, 2)} ` +
    `(p = ${n(sp.p, 3)}), so the more slots a series gives the market variables, the more it loses. ` +
    `That is a strong clue, and not the one it first appears to be. ` +
    `A genuinely uninformative predictor would dilute a model roughly in proportion to how much of it was ` +
    `admitted, but so would a predictor that was informative at training and then withheld at prediction.`));
  c.push(NOTE('Zero market slots does not guarantee zero market effect. ' +
    'The redundancy-aware search runs over a shortlist ranked on raw relevance, so a market variable that ' +
    'outranks an engineered feature on correlation alone can displace it from that shortlist without being ' +
    'selected itself. The "Market slots" column is therefore a lower bound on exposure.'));
  return c;
}

function suppliedTable() {
  const rows = T.tabel8b.map(r => [
    r.beta === 0 ? 'univariate' : 'mRMR', String(r.k),
    n(r.mati, 3), n(r.nol, 3), pct(r.delta_nol, 1),
    n(r.benar, 3), pct(r.delta_benar, 1),
    `${n(r.rusak_hilang_pct, 0)}%`, pv(r.p_vs_mati),
  ]);
  const g = T.tabel8b_gabungan;
  rows.push(['pooled', '—', n(g.mati, 3), n(g.nol, 3), pct(g.delta_nol, 1),
    n(g.benar, 3), pct(g.delta_benar, 1), `${n(g.rusak_hilang_pct, 0)}%`,
    pv(g.p_vs_mati)]);
  return TBL([1080, 560, 900, 900, 860, 900, 860, 900, 940],
    ['Selector', 'k', 'Market off', 'Zero-filled', 'Penalty',
     'Supplied', 'Penalty', 'Recovered', 'p vs off'],
    rows, { rightFrom: 1 });
}

function suppliedProse() {
  const g = T.tabel8b_gabungan;
  const cells = T.tabel8b;
  const sig = cells.filter(r => r.p_vs_mati < 0.05).length;
  const lagMaks = T.lag_pasar[T.lag_pasar.length - 1];
  const lebih100 = cells.filter(r => r.rusak_hilang_pct > 100);
  const kurang = cells.reduce((a, b) => (a.rusak_hilang_pct < b.rusak_hilang_pct ? a : b));
  const c = [];
  c.push(P(`The comparison above has a flaw, and it is in our pipeline rather than in the data. ` +
    `The recursive forecasters build their features afresh at prediction time, and the routine that does so ` +
    `had no way to accept the market series. Every market feature the model had been trained on was ` +
    `therefore absent when the forecast was made, and silently filled with zero. ` +
    `For a recursive multi-step forecast that is unavoidable, because the future values of another series do ` +
    `not exist. But this paper forecasts one day ahead, and one day ahead the market variables at lags one ` +
    `to ${kata(lagMaks)} are all known. The market-on arm of Table 9 was thus trained on information it was ` +
    `then denied.`));
  c.push(P(`We repeated the comparison with the market series supplied at prediction as well as at training. ` +
    `Nothing else changed, neither the selector, the feature counts, the origins nor the fitted ` +
    `hyperparameters. Pooled over all ${fmtN(g.n)} paired forecasts the penalty against the ` +
    `no-market baseline falls from ${n(g.delta_nol, 1)} per cent to ${n(g.delta_benar, 1)} per cent, so ` +
    `${n(g.rusak_hilang_pct, 0)} per cent of the reported loss was an artefact of the zero-fill ` +
    `(${pTeks(g.p_vs_nol)} against the zero-filled arm).`));
  c.push(P(`What survives is smaller and still real. Market data remain worse than no market data by ` +
    `${n(g.delta_benar, 1)} per cent (${pTeks(g.p_vs_mati)}), significantly so in ${kata(sig)} of the four ` +
    `conditions, and outside tied days they are the better forecast on only ${n(g.pct_benar, 1)} per cent ` +
    `of them. ` +
    `The recovery is uneven across conditions. ` +
    (lebih100.length
      ? `For ${daftarN(lebih100.map(r => `the ${r.beta === 0 ? 'univariate' : 'mRMR'} rule at ${r.k} features`))} ` +
        `the correction removes more than the whole penalty, so supplied market data are slightly better ` +
        `than none there, while `
      : 'While ') +
    `the ${kurang.beta === 0 ? 'univariate' : 'mRMR'} rule at ${kurang.k} features sheds only ` +
    `${n(kurang.rusak_hilang_pct, 0)} per cent.`));
  c.push(P(`The per-series picture is mixed rather than uniformly negative. ` +
    `Once the features are supplied, ${kata(T.n_leaf_membaik)} of the ${T.n_leaf} series are more accurate ` +
    `with market data than without, ${kata(T.n_leaf_memburuk)} are worse, and ${kata(T.n_leaf_tanpa_slot)} ` +
    `admit no market feature at all and are therefore unchanged. ` +
    `On average market data cost a little, and which series they help is not something the pipeline can ` +
    `predict in advance. H4 is rejected on average, though not for every series.`));
  return c;
}

function slotDamageProse() {
  const A = T.slot_damage;
  const g = T.tabel8b_gabungan;
  const c = [];
  c.push(P(`Figure 10 identifies the mechanism. With the market features zero-filled, the penalty a series ` +
    `suffers rises with the number of slots the selector gave them. The rank correlation across the ` +
    `${A.n} series is ${n(A.nol.rho, 3)} (p = ${n(A.nol.p, 4)}). ` +
    `That is what a feature withheld at prediction would produce, since the more of the model is blanked ` +
    `at forecast time, the worse the forecast. ` +
    `Once the same features are supplied, the relationship vanishes, at ${n(A.benar.rho, 3)} ` +
    `(p = ${n(A.benar.p, 3)}).`));
  c.push(P(`The ${kata(T.n_leaf_tanpa_slot)} series that give market variables no slot at all anchor the reading. ` +
    `They are unchanged across all three arms and sit at the origin of both panels. ` +
    `A dilution story, in which market data are simply uninformative and crowd out better features, would ` +
    `survive the correction, because crowding out happens at selection time and is untouched by what is ` +
    `supplied at prediction. It does not survive. The zero-fill, not the market data, produced ` +
    `${n(g.rusak_hilang_pct, 0)} per cent of the loss first reported.`));
  return c;
}

function selectorProse() {
  const S = T.selector_tests;
  const su = T.slot_uptake_new;
  const e0 = T.external_full.find(e => e.beta === 0 && e.k === 25);
  const e1 = T.external_full.find(e => e.beta === 1 && e.k === 25);
  const rSel = T.reverse_ablation.find(a => a.component === 'Redundancy-aware selection');
  const lebihBanyak = su.k25_mrmr > su.k25_univ;
  const c = [];
  c.push(P(`The crowding story does not hold either. At 25 features the redundancy-aware rule admits ` +
    `${n(su.k25_mrmr, 2)} market features on average against ${n(su.k25_univ, 2)} under the univariate ` +
    `rule, ${lebihBanyak ? 'more rather than fewer' : 'fewer'}, and market data cost ${n(e1.delta, 1)} per ` +
    `cent under it against ${n(e0.delta, 1)} per cent under the univariate rule. ` +
    `The selector changes how the penalty is distributed, not whether there is one.`));
  c.push(P(`With market data off, the redundancy-aware rule is slightly better than the univariate one at ` +
    `both feature counts, and at neither does the difference reach significance. ` +
    S.map(r => `At k = ${r.k} it ${r.delta < 0 ? 'lowers' : 'raises'} mean error by ` +
      `${Math.abs(r.delta).toFixed(2)} per cent and wins ${r.wins} of ${r.n} paired points (p = ${n(r.p, 3)})`).join('. ') + '. ' +
    `This comparison fits once per block, whereas the reverse ablation in Section 4.3 re-fits daily with ` +
    `tuned hyperparameters, and there removing the rule ${rSel.delta < 0 ? 'lowered' : 'raised'} error by ` +
    `${n(Math.abs(rSel.delta), 2)} per cent. The two experiments disagree in sign and neither is significant ` +
    `after correction. The effect of the selection rule on these learners is not identified by this study.`));
  if (!S.every(r => r.delta < 0) || !S.every(r => r.p >= 0.05)) {
    throw new Error('selectorProse: arah atau kenyataan uji selektor berubah; tulis ulang kalimatnya');
  }
  return c;
}

function famProse() {
  const ks = famKeys;
  const extShareAvg = fam['External'] ?? 0;
  const sorted = [...extShare].sort((a, b) => b.share - a.share);
  const nZero = extShare.filter(r => r.share < 1).length;
  const pb = Object.fromEntries(T.per_leaf_benar.map(r => [r.leaf, r]));
  const top2 = sorted.slice(0, 2);
  const top2Bantu = top2.filter(r => pb[r.leaf] && pb[r.leaf].rusak_benar < 0);
  const c = [];
  c.push(P(`Pooled across all ${T.n_leaf} series, ${ks[0].toLowerCase()} features carry ` +
    `${n(fam[ks[0]], 1)} per cent of all feature importance and ${ks[1].toLowerCase()} features ` +
    `${n(fam[ks[1]], 1)} per cent, while market data carry ${n(extShareAvg, 1)} per cent on average. ` +
    `H5 is supported. The model draws its signal from the series own history, and above all from its ` +
    `recent level, which is what moving averages over whole weeks summarise.`));
  c.push(P(`The market share is very uneven across series. It reaches ${n(sorted[0].share, 1)} per cent on ` +
    `${sorted[0].leaf} (${LABEL[sorted[0].leaf]}) and ${n(sorted[1].share, 1)} per cent on ${sorted[1].leaf} ` +
    `(${LABEL[sorted[1].leaf]}), and is under one per cent on ${nZero} of ${T.n_leaf} series. ` +
    (top2Bantu.length === 2
      ? `Those two series are also among the ${kata(T.n_leaf_membaik)} that market data improve once ` +
        `supplied correctly, so where the fitted model leans on market variables most, it has reason to. `
      : '') +
    `Lags take ${n(T.mean_lag_slots, 1)} of the 25 slots on average and carry ${n(fam['Lag'], 1)} per cent ` +
    `of importance, while market variables take ${n(T.mean_ext_slots, 1)} slots.`));
  return c;
}

function synthProse() {
  const r = e2rank, top = r[0];
  const K = T.champion_koreksi;
  const statSetara = K.tak_signifikan_holm.filter(m => !POHON.includes(m));
  const RA = T.reverse_ablation;
  const g = T.tabel8b_gabungan;
  const A = T.ablation_acuan;
  const nML = T.winners.filter(w => w.fam === 'ML').length;
  const c = [];
  c.push(P('Read through the lens of the machine-learning pipeline, the findings form one picture.'));
  c.push(P(`The learners are a good default and not a proven improvement. They take the top places on ` +
    `average, with ${nice(top.model)} first, but ${daftarN(statSetara.map(nice))} cannot be separated from ` +
    `the leader after correction, and a learner is the best method on only ${kata(nML)} of ` +
    `${T.n_leaf} series. An applied study that reports a best learner on a single panel is reporting ` +
    `something this fragile, usually without the tests that would reveal it.`));
  c.push(P(`The machinery around the learner contributes even less. ` +
    `Redundancy-aware selection, daily re-fitting and tuning each move the pooled mean by less than two ` +
    `per cent when removed, in directions that differ by learner, and none is significant after correction. ` +
    `The one pipeline setting with a measurable effect is the feature count, and it points towards keeping ` +
    `more features than the conventional ${A}, not fewer. ` +
    `One day ahead the model benefits from a broad view of the recent level, and the ` +
    `apparatus for narrowing that view does not pay for itself.`));
  c.push(P(`Market data show how a pipeline can mislead its user. The first result, a penalty of ` +
    `${n(g.delta_nol, 1)} per cent, was mostly a property of the pipeline, which trained on features it ` +
    `later withheld. Corrected, the penalty is ${n(g.delta_benar, 1)} per cent and the effect varies by ` +
    `series. The diagnostic that exposed it, damage that scales with exposure and vanishes once the ` +
    `features are supplied, is general and cheap.`));
  c.push(P('Taken together these results describe a problem with a low ceiling. ' +
    'The predictable part of a one-day flow is small, the recent level and lags capture most of it, and ' +
    'sophistication in the pipeline around them returns little. ' +
    'That is a more useful thing for a supervisory desk to know than a ranking it cannot reproduce.'));
  if (RA.some(a => Math.abs(a.delta) >= 2)) {
    throw new Error('synthProse: ada komponen yang bergeser >= 2 persen; tulis ulang "less than two per cent"');
  }
  return c;
}

function conclProse() {
  const r = e2rank, top = r[0];
  const K = T.champion_koreksi;
  const statSetara = K.tak_signifikan_holm.filter(m => !POHON.includes(m));
  const g = T.tabel8b_gabungan;
  const A = T.ablation_acuan;
  const c = [];
  c.push(P(`We built a machine-learning pipeline to forecast ${T.n_leaf} disaggregated foreign-exchange ` +
    'flow series one business day ahead, with the counterparty and purpose cell as the unit, and took it ' +
    'apart one component at a time against seven statistical benchmarks.'));
  c.push(P(`Four contributions follow. ` +
    `First, the learners lead on average, with ${nice(top.model)} at a mean MASE of ${n(top.mase, 3)}, but ` +
    `${daftarN(statSetara.map(nice))} cannot be separated from the leader after correction for multiple ` +
    `testing, and no method is best on more than ${kata(T.menang_terbanyak)} of the ${T.n_leaf} series. ` +
    `Second, none of the pipeline components tested, redundancy-aware selection, tuning or daily ` +
    `re-fitting, earns its place, while keeping more than ${A} features tends to help, a tendency the ` +
    `per-series tests cannot confirm. ` +
    `Third, most of the apparent damage from market data, ${n(g.rusak_hilang_pct, 0)} per cent of a ` +
    `${n(g.delta_nol, 1)} per cent penalty, came from the pipeline zero-filling features at prediction ` +
    `that it had used in training. Supplied correctly, market data cost ${n(g.delta_benar, 1)} per cent on ` +
    `average and help ${kata(T.n_leaf_membaik)} series. ` +
    `Fourth, SHAP shows that the fitted models rely on the series own recent level, with moving averages and ` +
    `lags carrying ${n((fam['Moving average'] || 0) + (fam['Lag'] || 0), 0)} per cent of importance and ` +
    `market data ${n(fam['External'] ?? 0, 1)} per cent.`));
  c.push(P('The broader point is methodological. ' +
    'A machine-learning pipeline assembled from individually defensible choices can be, on a panel of this ' +
    'size, indistinguishable from a simpler one, and it can hide a handling error that looks like a finding. ' +
    'The only way to learn either is to remove the choices one at a time and test each difference on ' +
    'paired forecasts, with correction for the number of tests.'));
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
  c.push(P('Figure 12 shows how the 25 selected features divide between market variables, own lags and ' +
    'everything else, and how much of the fitted importance the market variables carry. ' +
    'It cannot show direction, and the beeswarms below can. Each dot is one of the last 300 training days, ' +
    'placed by that feature contribution to the predicted next-day flow in millions of US dollars, and ' +
    'coloured by whether the feature value was low (blue) or high (red) that day. ' +
    'Feature names in orange are market variables, and names in black are engineered from the series own ' +
    'history. A wide spread means the feature moves the forecast from day to day, while a narrow band ' +
    'around zero means it is carried in the model and does almost nothing.'));
  c.push(NOTE('These are the fourteen highest-importance features of the 25 selected, ordered by mean ' +
    'absolute SHAP value. A series can therefore show fewer market rows here than its market slot count ' +
    'in Figure 12, which means the remaining market features rank below the fourteenth.'));
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

function appendixTable() {
  const byLeaf = {};
  T.e1.forEach(r => { if (!byLeaf[r.leaf] || r.mase < byLeaf[r.leaf].mase) byLeaf[r.leaf] = r; });
  const rows = T.desc.map(d => {
    const b = byLeaf[d.leaf];
    return [d.leaf, LABEL[d.leaf], nice(b.model), n(b.actual, 1), n(b.pred, 1), n(b.mase, 3)];
  });
  return TBL([760, 1900, 2200, 1500, 1500, 1500],
    ['Series', 'Purpose', 'Best method', 'Actual', 'Forecast', 'MASE'], rows, { rightFrom: 3 });
}

function refs() {
  return [
    'Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society, Series B*, 57(1), 289–300.',
    'Bergmeir, C. and Benítez, J. M. (2012). On the use of cross-validation for time series predictor evaluation. *Information Sciences*, 191, 192–213.',
    'Breiman, L. (2001). Random forests. *Machine Learning*, 45(1), 5–32.',
    'Chen, T. and Guestrin, C. (2016). XGBoost: a scalable tree boosting system. In *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.',
    'Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289–303.',
    'Evans, M. D. D. and Lyons, R. K. (2002). Order flow and exchange rate dynamics. *Journal of Political Economy*, 110(1), 170–180.',
    'Guyon, I. and Elisseeff, A. (2003). An introduction to variable and feature selection. *Journal of Machine Learning Research*, 3, 1157–1182.',
    'Hastie, T., Tibshirani, R. and Friedman, J. (2009). *The Elements of Statistical Learning*, 2nd edition. New York: Springer.',
    'Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.',
    'Hyndman, R. J. and Koehler, A. B. (2006). Another look at measures of forecast accuracy. *International Journal of Forecasting*, 22(4), 679–688.',
    'Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q. and Liu, T.-Y. (2017). LightGBM: a highly efficient gradient boosting decision tree. In *Advances in Neural Information Processing Systems*, 30, 3146–3154.',
    'Kohavi, R. and John, G. H. (1997). Wrappers for feature subset selection. *Artificial Intelligence*, 97(1–2), 273–324.',
    'Lundberg, S. M. and Lee, S.-I. (2017). A unified approach to interpreting model predictions. In *Advances in Neural Information Processing Systems*, 30, 4765–4774.',
    'Lyons, R. K. (2001). *The Microstructure Approach to Exchange Rates*. Cambridge, MA: MIT Press.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2018). The M4 competition: results, findings, conclusion and way forward. *International Journal of Forecasting*, 34(4), 802–808.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2020). The M4 competition: 100,000 time series and 61 forecasting methods. *International Journal of Forecasting*, 36(1), 54–74.',
    'Marcellino, M., Stock, J. H. and Watson, M. W. (2006). A comparison of direct and iterated multistep AR methods for forecasting macroeconomic time series. *Journal of Econometrics*, 135(1–2), 499–526.',
    'Meese, R. A. and Rogoff, K. (1983). Empirical exchange rate models of the seventies: do they fit out of sample? *Journal of International Economics*, 14(1–2), 3–24.',
    'Peng, H., Long, F. and Ding, C. (2005). Feature selection based on mutual information: criteria of max-dependency, max-relevance, and min-redundancy. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 27(8), 1226–1238.',
    'Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: an analysis and review. *International Journal of Forecasting*, 16(4), 437–450.',
    'Taylor, S. J. and Letham, B. (2018). Forecasting at scale. *The American Statistician*, 72(1), 37–45.',
    'Wilcoxon, F. (1945). Individual comparisons by ranking methods. *Biometrics Bulletin*, 1(6), 80–83.',
  ];
}

const OUTF = process.argv[2] || path.join(KERJA, 'FX_15seri.docx');
console.log(`nama leaf tampilan: ${nTampil} potongan teks memakai nama baru (nama_leaf.json)`);
Packer.toBuffer(doc).then(b => { fs.writeFileSync(OUTF, b); console.log('ditulis:', OUTF, (b.length / 1024).toFixed(0) + ' KB'); });
