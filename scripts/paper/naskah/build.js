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
  c.push(LEAD('Background',
    'A central bank that monitors the foreign-exchange market needs to know who will buy and who will sell ' +
    'tomorrow, not only the net total. Machine-learning pipelines suit this task, but they bundle design ' +
    'choices that are rarely tested one at a time.'));
  c.push(LEAD('Methods',
    `We forecast ${T.n_leaf} daily flow series, each one counterparty group and one transaction purpose, one ` +
    'business day ahead, using Indonesian supervisory data from 2006 to 2026. Three tree ensembles with ' +
    'redundancy-aware feature selection, tuning and daily re-fitting are compared with seven statistical ' +
    'benchmarks over 30 rolling origins. Pipeline components are removed one at a time, and differences are ' +
    'assessed with paired tests, block-bootstrap intervals, equivalence tests and a model confidence set.'));
  c.push(LEAD('Results',
    `${nice(juara.model)} has the lowest mean scaled error, but a 90 per cent model confidence set retains ` +
    `${kata(mcs.length)} methods, including ${daftar(mcsStat.map(nice))}. ` +
    'No pipeline component is shown to improve accuracy. ' +
    (setara.length
      ? `For ${daftar(setara)}, pooled effects larger than 2 per cent can be ruled out, and for ` +
        `${daftar(tidakSetara)} not even that. `
      : '') +
    'No equal-weight combination is shown to improve on the leader. ' +
    `Market data, supplied at prediction time, raise error by ${n(g8.delta_benar, 1)} per cent on average, ` +
    `mostly through two series.`));
  c.push(LEAD('Conclusions',
    'For one-day flow forecasting, a well-tested learner run alongside strong statistical benchmarks is a ' +
    'reasonable default, and pipeline components should be tested by removal before they are trusted. ' +
    'A six-week test block resolves differences of a few per cent, not smaller ones.'));
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
  // Epigraf atas permintaan penulis: pertanyaan pembuka Turing (1950), versi pendek.
  c.push(new Paragraph({
    spacing: { after: 40 }, alignment: AlignmentType.RIGHT, indent: { left: 3600 },
    children: [new TextRun({ text: '“Can machines think?”', italics: true, size: 20, color: MUTED })],
  }));
  c.push(new Paragraph({
    spacing: { after: 220 }, alignment: AlignmentType.RIGHT,
    children: [new TextRun({ text: 'Alan M. Turing (1950)', size: 18, color: MUTED })],
  }));
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
    'and each filled cell is one series, labelled with its sample mean in millions of US dollars. ' +
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
    '**RQ2.** Which parts of the pipeline earn their place? We test redundancy-aware feature selection, hyperparameter tuning, daily re-fitting and the number of features kept.',
    '**RQ3.** Do daily market data, such as the exchange rate, bond yields and equity prices, improve the forecasts?',
    '**RQ4.** Which features does the fitted model rely on, and does that differ across counterparty groups?',
  ]));
  c.push(P('The contribution is empirical and methodological. We evaluate a pipeline at the level where the ' +
    'supervisory question is asked, take it apart one component at a time, and report every comparison ' +
    'with paired tests, correction for multiple testing, confidence intervals that respect dependence across ' +
    'days, and equivalence tests that distinguish "no effect" from "not enough data".'));

  /* --------------------------------------------------- 2. Literature */
  c.push(H1('2. Related Literature'));
  c.push(P('Forecasting competitions give a consistent but evolving message. In M4, pure machine-learning ' +
    'methods did not outperform established statistical benchmarks, while combinations did well ' +
    '(Makridakis, Spiliotis and Assimakopoulos, 2018, 2020). In M5, whose series were daily, grouped and ' +
    'often intermittent, gradient-boosted trees trained across many series at once led the field ' +
    '(Makridakis, Spiliotis and Assimakopoulos, 2022). Such global models can outperform series-by-series ' +
    'models even when the series differ (Montero-Manso and Hyndman, 2021), and grouped series can be forecast ' +
    'coherently with their totals by reconciliation (Wickramasuriya, Athanasopoulos and Hyndman, 2019). ' +
    'This paper stays with local models, one per series, and Section 6 returns to global and reconciled ' +
    'alternatives as the natural next step.'));
  c.push(P('Feature selection is well studied in theory (Guyon and Elisseeff, 2003; Kohavi and John, 1997), ' +
    'and redundancy-aware criteria such as mRMR (Peng, Long and Ding, 2005) are designed for pools of ' +
    'overlapping candidates like the lags and moving averages of a time series. The bias-variance trade-off ' +
    'says that past some point added predictors reduce out-of-sample accuracy (Hastie, Tibshirani and ' +
    'Friedman, 2009), but not where that point lies. For comparing forecasts, the literature offers paired ' +
    'tests of equal accuracy (Diebold and Mariano, 1995; Harvey, Leybourne and Newbold, 1997), procedures for ' +
    'identifying a set of best models (Hansen, Lunde and Nason, 2011), and rolling-origin designs (Tashman, ' +
    '2000; Bergmeir and Benítez, 2012). Applied studies rarely use them together.'));
  c.push(P('On the economics, order flow carries information about exchange-rate moves (Evans and Lyons, ' +
    '2002; Lyons, 2001), and customer flows differ in that information by counterparty, with financial ' +
    'customers’ trades more informative than those of corporates (Menkhoff et al., 2016). Whether prices, in ' +
    'turn, help forecast next-day flows on top of the flows’ own history ' +
    'is the question this paper tests.'));
  c.push(TCAP(1, 'Hypotheses, the design choice each one isolates, and the test used.'));
  c.push(TBL([620, 3300, 2500, 2940],
    ['', 'Hypothesis', 'What is varied', 'Test'],
    [
      ['H1', 'A machine-learning learner is the most accurate method.', 'Method', 'Paired tests against the leading method, block-bootstrap intervals and a model confidence set'],
      ['H2', 'Each component of the pipeline improves accuracy.', 'Selection rule, tuning, re-fitting, one at a time', 'Paired tests and equivalence tests, full pipeline against each removal'],
      ['H3', `A count of ${acuanK} features is the right size.`, `Feature count, ${kList[0]} to ${kList[kList.length - 1]}`, `Paired tests against k = ${acuanK}, with a per-series check`],
      ['H4', 'Adding market data improves accuracy.', 'Market data on or off', 'Paired tests, on against off'],
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
  c.push(IMG('fig_seri.png', 560, 499));
  c.push(FCAP(2, 'The fifteen series in millions of US dollars, each panel on its own scale. The shaded strip ' +
    'at the right is the 30-day test block.'));
  const late = T.skala_koreksi.seri;
  const tglEN = d => new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });
  const kelompokMulai = [...new Set(late.map(r => r.mulai))].sort().reverse()
    .map(d => { const ls = late.filter(r => r.mulai === d).map(r => r.leaf); return `${daftar(ls)} ${ls.length > 1 ? 'are' : 'is'} zero until ${tglEN(d)}`; });
  c.push(P(`Not every series is reported from the start. ${kelompokMulai.join(', and ')}, ` +
    'which reflects when the category entered the reporting framework rather than an absence ' +
    'of flows. Measured from each series’ first report, the share of zero days is small except in ' +
    `${daftar(Object.entries(T.nol_sejak).filter(([, v]) => v.nol_sejak > 15).map(([l, v]) => `${l} (${n(v.nol_sejak, 1)} per cent)`))}. ` +
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
  c.push(TCAP(2, `Descriptive statistics for the ${T.n_leaf} series over the full sample. Values in millions of US dollars.`));
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

  c.push(H2('3.2. Evaluation Design'));
  c.push(P('Two designs are used (Figure 3). The headline design trains on everything except the last day ' +
    'and forecasts that day, which is the operational setting but gives one error per series. The rolling ' +
    'design supports inference. It re-fits every model at each of 30 consecutive test origins and ' +
    'forecasts one day ahead from the actual history up to the day before. Every inferential result in this ' +
    'paper uses the rolling design, and the headline results are in Appendix A.'));
  c.push(IMG('fig2_design.png', 560, 148));
  c.push(FCAP(3, 'The two evaluation designs. Panel A is the headline design, with one test day. Panel B is ' +
    'the rolling design, with 30 one-day origins, each re-fitted on the history up to the day before.'));
  c.push(P('Each origin uses the previous day’s actual value. This matches practice, because the reports ' +
    'for a given day are complete before the forecast for the next day is made. ' +
    `The 30 test origins run from ${tglEN(T.tgl_uji_awal)} to ${tglEN(T.tgl_akhir)}, about six weeks, and on ` +
    'them the random walk itself scores a mean MASE of ' +
    `${n(T.e2_summary.find(r => r.model === 'Naive').mase, 3)} on the scale of the full training history but ` +
    `${n(T.skala_2022.rw, 3)} on the scale of 2022 onwards. The block is therefore volatile relative to the long ` +
    'history and calm relative to recent years, and Section 4.7 shows that the comparison between methods ' +
    'does not depend on which scale is used.'));

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
  c.push(P(`Where market data are tested, the ${kata(nVariabel)} market variables extend the pool to ` +
    `${T.pool_total} candidates, each as ${kata(nLagPasar)} consecutive lags, one to ${kata(lagMaks)} days, ` +
    `and a ${kata(T.rata_pasar)}-day rolling mean. No contemporaneous market value enters the model. The ` +
    'market candidates are added to the engineered ones, so all compete for the same fixed number of slots.'));

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

  c.push(H3('Learners, tuning and re-fitting'));
  c.push(P('Three tree ensembles are fitted on the selected features. Random forest averages bagged ' +
    'regression trees (Breiman, 2001). LightGBM (Ke et al., 2017) and XGBoost (Chen and Guestrin, 2016) fit ' +
    `gradient-boosted trees. Every learner keeps k = ${acuanK} features, the count fixed at the outset of the ` +
    'study, and Section 4.4 tests that choice. The learners are trained on squared error, while accuracy is ' +
    'measured by absolute scaled error, and Section 5.3 notes what that mismatch may cost.'));
  c.push(P(`Hyperparameters are tuned for each series and learner separately over the four configurations in ` +
    `Table 3, on a validation block of ${T.nval} one-day origins that ends where the test block begins. At ` +
    'each validation origin every candidate is re-fitted on all data up to the day before and forecasts one ' +
    `day ahead, and the configuration with the lowest mean scaled error over the ${T.nval} origins is carried ` +
    'forward unchanged. In the test block every model is re-fitted at every origin.'));
  c.push(TCAP(3, 'Hyperparameter grid. Configuration 1 is the default of the institution’s production system, ' +
    `not the library default. The number in brackets is how many of the ${T.n_leaf} series selected that configuration.`));
  c.push(gridTable());
  c.push(NOTE('The library defaults differ. Random forest grows trees to unlimited depth, LightGBM uses a ' +
    'learning rate of 0.1 with unlimited depth, and XGBoost a learning rate of 0.3 with depth 6. Tuning is ' +
    'therefore tested against the production baseline, and four configurations are a narrow search.'));

  c.push(H2('3.4. Benchmark Methods'));
  c.push(P('Seven statistical methods serve as benchmarks (Table 4). Each is fitted on the same training data ' +
    'and scored on the same origins as the learners.'));
  c.push(TCAP(4, 'The seven benchmark methods.'));
  c.push(TBL([2200, 1500, 5660],
    ['Method', 'Family', 'What it does'],
    [
      ['Random walk', 'Naive', 'Forecast equals yesterday.'],
      ['Rolling mean', 'Naive', 'Mean of the last 90 days.'],
      ['Random walk with drift', 'Naive', 'Yesterday plus the average change over the whole history.'],
      ['Croston', 'Intermittent', 'Croston’s method (Croston, 1972) in the bias-corrected form of Syntetos and Boylan (2005), with a fixed smoothing constant α = 0.1, applied to the signed flow. On a series without zeros it equals 0.95 times simple exponential smoothing.'],
      ['Seasonal decomposition', 'Structural', 'An in-house baseline that multiplies a month-of-year share, a day-of-month share and an annual level.'],
      ['ARIMA', 'Statistical', 'statsmodels SARIMAX without seasonal or calendar terms. The order of differencing is set by successive KPSS tests, as in the Hyndman-Khandakar algorithm, and p and q up to 3 by AIC on the last 750 observations.'],
      ['Prophet', 'Statistical', 'Trend and seasonal terms (Taylor and Letham, 2018), with its default settings.'],
    ], { rightFrom: 99 }));

  c.push(H2('3.5. Evaluation and Statistical Inference'));
  c.push(P('Figure 4 sets out the whole procedure, from the raw series to the reported tests.'));
  c.push(IMG('fig3_evaluasi.png', 560, 477));
  c.push(FCAP(4, `The evaluation procedure. Steps 2 and 3 run separately for each of the ${T.n_leaf} series, ` +
    `and tuning uses the ${T.nval}-origin validation block only.`));
  c.push(H3('Accuracy'));
  c.push(P('Accuracy is the mean absolute scaled error, MASE (Hyndman and Koehler, 2006). With Yₜ the actual ' +
    'value and Fₜ the forecast, the scaled error divides eₜ = Yₜ − Fₜ by the mean absolute first difference of ' +
    'the training sample of n observations,'));
  c.push(EQM([MSUB('q', 't'), MR(' = '),
    new D.MathFraction({ numerator: [MSUB('e', 't')], denominator: [
      new D.MathFraction({ numerator: [MR('1')], denominator: [MR('n − 1')] }),
      new D.MathSum({ children: [MR('|'), MSUB('Y', 'i'), MR(' − '), MSUB('Y', 'i−1'), MR('|')],
        subScript: [MR('i=2')], superScript: [MR('n')] })] })], 2));
  c.push(P('and MASE is the mean of |qₜ| over the test points. It is scale-free, defined when actual values ' +
    'are zero, and equal to one for a forecast as good as the in-sample random walk. For the series reported ' +
    'only from 2013, the training sample includes years of structural zeros, which shrink the denominator and ' +
    'inflate their MASE. Section 4.7 repeats the main results with the denominator computed from each ' +
    'series’ first report.'));
  c.push(H3('Paired tests and their units'));
  c.push(P('Every comparison is paired, and both arms forecast the same series on the same days. Three ' +
    'learners, or four market-data conditions, that forecast the same day are not independent replications, ' +
    `so for inference each comparison is first averaged to one value per series and date, giving ` +
    `${T.n_leaf} × 30 = ${nPasangMetode} units. Consecutive days of one series and different series on one ` +
    'day are still dependent, and four tools address that.'));
  c.push(...BUL([
    '**Wilcoxon signed-rank tests** (Wilcoxon, 1945), two-sided, on the 450 units, with the Hodges-Lehmann shift (Hodges and Lehmann, 1963) as the matching effect size, reported in Appendix G. The test concerns the pseudo-median of the paired differences, not the mean, which is why a small mean change can be significant and a larger one not.',
    '**Block-bootstrap confidence intervals** for the percentage change in mean MASE, with 2,000 replications. Test dates are resampled in circular blocks of five business days (Künsch, 1989; Politis and Romano, 1994), with all series of a date kept together, so dependence across days and across series is preserved. Thirty dates give only six blocks, so percentile intervals may be too narrow, and Appendix G repeats them with blocks of two and ten days.',
    `**Equivalence tests.** A difference is declared practically equivalent to zero when its 90 per cent interval lies within ±2 per cent, the two one-sided tests procedure of Lakens (2017). For the leading method 2 per cent of the mean absolute error is about ${n(0.02 * T.desk.find(d => d.model === T.champion_juara).mae, 1)} million US dollars per series and day, and about ${n(0.02 * T.desk.find(d => d.model === T.champion_juara).mae_total, 1)} million on the daily total, ${0.02 * T.desk.find(d => d.model === T.champion_juara).mae < 1 ? 'less than the one-million rounding unit of each reported series' : 'close to the one-million rounding unit of each reported series'}. The margin was set after the results were seen, so Appendix G also reports ±1 and ±3 per cent. A non-significant difference that fails the test is reported as inconclusive, not as absent.`,
    '**Diebold-Mariano tests per series**, with the small-sample correction of Harvey, Leybourne and Newbold (1997), and a **90 per cent model confidence set** (Hansen, Lunde and Nason, 2011) on the daily mean MASE of all ten methods, which identifies the set of methods that cannot be told apart from the best. The set uses the T-max statistic with the same block bootstrap, and its p-value for each method is given in Table 5.',
  ]));
  c.push(P('Tests that answer one question are corrected together with the Holm-Bonferroni procedure (Holm, ' +
    '1979), which orders the m p-values of a family and compares the i-th smallest with α ⁄ (m − i + 1), ' +
    'controlling the probability of any false rejection whatever the dependence among the tests. Each table ' +
    'is one family, namely the comparisons of every method with the leading one, the three pipeline ' +
    `components, the ${kata(abl.length - 1)} feature counts, the five combinations, the four market-data ` +
    'conditions, the two selection rules and the four zero-fill conditions. All p-values are computed on the ' +
    'series-date units. The Benjamini-Hochberg ' +
    'adjustment (Benjamini and Hochberg, 1995) is reported for the method comparison as a less strict reading.'));
  c.push(H3('Ablation designs'));
  c.push(P('The reverse ablation removes one component at a time from the full pipeline. Redundancy-aware ' +
    'selection is replaced by the univariate rule, daily re-fitting by one fit per block, and tuned ' +
    'hyperparameters by configuration 1. The feature-count ablation varies k over ' +
    `${kata(kList.length)} settings, ${daftar(kList.map(String))}. The feature-count and market-data ` +
    'experiments fit once per test block, which shifts both arms of each comparison in the same way. SHAP ' +
    'values on the fitted trees (Lundberg and Lee, 2017) show which features the models use.'));

  /* ------------------------------------------------------- 4. Results */
  c.push(H1('4. Results'));

  c.push(H2('4.1. Which Methods Lead'));
  c.push(TCAP(5, `The ten methods over 30 one-day origins, ${nPasangMetode} forecasts each. The learners use the full ` +
    'pipeline. The change and Wilcoxon columns compare each method with the leading one on units averaged ' +
    'by series and date, with a 95 per cent block-bootstrap interval. The last column is the p-value of the ' +
    '90 per cent model confidence set, and methods with a value of at least 0.10 are in the set.'));
  c.push(rankTable(e2rank));
  c.push(...h1Prose());
  c.push(IMG('fig_heatmap.png', 560, 348));
  c.push(FCAP(5, 'Accuracy by series and method, as MASE relative to the random walk on the same series. The ' +
    'boxed cell in each row is the best method for that series on the test block. Colours use a log scale ' +
    'capped at 0.35 and 2.8.'));
  c.push(...winnersProse());

  c.push(H2('4.2. Does Combining Methods Help?'));
  c.push(...ensembleProse1());
  c.push(TCAP(6, `Equal-weight combinations against ${nice(T.champion_juara)}. A negative change means the ` +
    'combination is better. The interval is a 95 per cent block-bootstrap interval, the Holm column ' +
    'corrects for the five combinations, and the verdict applies the ±2 per cent equivalence test.'));
  c.push(ensembleTable());
  c.push(...ensembleProse2());

  c.push(H2('4.3. What Each Pipeline Component Contributes'));
  c.push(P('We remove the components one at a time, each arm switching off exactly one and leaving the other ' +
    'two in place.'));
  c.push(TCAP(7, 'Reverse ablation. A positive change means the full pipeline is better. Wins count the ' +
    'series-date units on which the full pipeline is more accurate, outside tied units. The interval is a 95 per ' +
    'cent block-bootstrap interval, the Holm p-value is computed on the same units, and "equivalent" means ' +
    'the 90 per cent interval lies within ±2 per cent.'));
  c.push(reverseAblationTable());
  c.push(IMG('fig9_ablation.png', 560, 265));
  c.push(FCAP(6, 'What each component contributes, by learner and pooled. Bars above zero mean the full ' +
    'pipeline is better. The dashed line is the pooled effect.'));
  c.push(...reverseAblationProse());
  c.push(IMG('fig10_selector.png', 560, 204));
  c.push(FCAP(7, 'The two selection rules compared at one fit per block. The left panel shows how many ' +
    'market features each rule admits when market data are available. The right panel shows the change in ' +
    'mean MASE from using the redundancy-aware rule instead of the univariate one, with market data off.'));
  c.push(...selectorProse());

  c.push(H2('4.4. How Many Features to Keep'));
  c.push(IMG('fig5_kablation.png', 560, 197));
  c.push(FCAP(8, 'Mean and median MASE against the number of features kept, pooled over three learners, ' +
    `${T.n_leaf} series and 30 origins.`));
  c.push(TCAP(8, `Feature-count ablation against k = ${acuanK}. The interval is a 95 per cent block-bootstrap ` +
    `interval, the Holm column corrects the series-date tests for the ${abl.length - 1} counts, and the series column tests the ` +
    `${T.n_leaf} series means.`));
  c.push(ablationTable());
  c.push(...ablationProse());

  c.push(H2('4.5. Do Market Data Help?'));
  c.push(P('One day ahead the market variables at every lag used here are known when the forecast is made, ' +
    'so they are supplied to the model both in training and at prediction. Box 1 in Section 5.2 describes ' +
    'what happens when they are not.'));
  c.push(TCAP(9, 'Market data on against off, under both selection rules and both feature counts, pooled ' +
    'across the three learners. A positive change means market data make the forecast worse. Wins are ' +
    'counted on series-date units outside tied units, the interval is a 95 per cent block-bootstrap interval, ' +
    'and the Holm column corrects for the four conditions.'));
  c.push(marketTable());
  c.push(...marketProse());
  c.push(TCAP(10, 'Series by series, engineered features only (FE) against engineered features plus market ' +
    'data, under redundancy-aware selection. "Market slots" counts the market features kept at 25 features.'));
  c.push(perLeafTable());
  c.push(...perLeafProse());

  c.push(H2('4.6. What the Model Relies On'));
  c.push(IMG('fig8_slotcomposition.png', 560, 242));
  c.push(FCAP(9, 'What the selector kept, series by series, at 25 features with market data on. The left ' +
    'panel divides the slots between market variables, own lags and everything else. The right panel shows ' +
    'the market share of total absolute SHAP value.'));
  c.push(IMG('fig7_shapfamily.png', 560, 212));
  c.push(FCAP(10, `Feature importance by family, from SHAP values on the fitted random forests and LightGBM ` +
    `models, averaged across the ${T.n_leaf} series at 25 features with market data on. The families are those ` +
    'of Appendix D, with market variables as a separate family' +
    (['RandomForest', 'LightGBM'].every(m => !(T.shap_dua.famili[m]['Calendar and Fourier'] > 0))
      ? '. Calendar and Fourier features were not selected for any series, so they do not appear.'
      : '.')));
  c.push(...famProse());

  c.push(H2('4.7. Operational Accuracy and Robustness'));
  c.push(P('Scaled errors suit statistical comparison but are not what a desk reads. Table 11 reports, for ' +
    'every method, the geometric mean across series of its mean absolute error relative to the random walk, ' +
    'the mean absolute error and bias in millions of US dollars, the share of days on which the forecast ' +
    'gets the direction of change right, and the error on the daily total of all fifteen series.'));
  c.push(TCAP(11, 'Operational metrics over the 30 test origins. Relative MAE is the geometric mean across ' +
    `series of each method’s MAE relative to the random walk (Davydenko and Fildes, 2013), shown with and ` +
    `without ${T.desk_tanpa.leaf}, and below one beats the random walk. Bias is actual minus forecast, so a ` +
    'negative bias means over-forecasting. Direction accuracy excludes days on which the actual or the ' +
    'forecast is unchanged, and an asterisk marks a Pesaran-Timmermann test significant at 1 per cent.'));
  c.push(deskTable());
  c.push(...deskProse());
  c.push(...skalaProse());

  /* ---------------------------------------------------- 5. Discussion */
  c.push(H1('5. Discussion'));
  c.push(H2('5.1. Synthesis'));
  c.push(...synthProse());
  c.push(H2('5.2. A Lesson Learned in Implementation'));
  c.push(...kotakPitfall());
  c.push(H2('5.3. Limitations'));
  c.push(...BUL(batasan()));
  c.push(H2('5.4. Implications for Practice'));
  c.push(...BUL([
    `**Run a learner alongside strong statistical benchmarks.** The learners lead on average, but ${daftar(mcsStat.map(nice))} remain in the set of methods that cannot be told apart from the best.`,
    '**Do not assume one method suits every cell, and select per cell on validation data.** Different methods win different cells in Figure 5, but those winners were identified on the test block, so the choice has to be made on data the evaluation does not see.',
    '**Test each pipeline component by removing it, and report equivalence as well as significance.** Here pooled effects above 2 per cent can be excluded for two of the three components, which is a finding, while the third cannot be resolved.',
    '**Check what the forecaster receives at prediction time.** Box 1 shows how a silent default nearly produced a wrong conclusion about market data.',
    '**Treat the feature count as a hyperparameter to be tuned at the horizon that will be run.** More features tended to help one day ahead here, and nothing in this design says the same count suits longer horizons.',
  ]));

  /* -------------------------------------------- 6. Conclusion */
  c.push(H1('6. Conclusion and Future Work'));
  c.push(...conclProse());
  c.push(P('The main priority for future work is resolution, and most of the open points can be settled by ' +
    'one further run of the same code. Its design is fixed in advance. The test block grows to at least 250 ' +
    'one-day origins, with the validation block before it and results reported by sub-period. Market ' +
    `features enter as daily changes of mid quotes rather than bid and ask levels. An arm without feature ` +
    `selection, using all ${T.pool_internal} engineered candidates, joins the feature-count ablation. Every ` +
    'learner runs with three random seeds, and training starts from each series’ first report, with a ' +
    'sliding window after January 2022 as a further arm. Exponential smoothing, Theta, seasonal naive and a ' +
    'ridge regression on the same features join the benchmarks, and the choice of method per series is made ' +
    'on the validation block and scored on the test block. Global models trained across all fifteen series ' +
    'and reconciliation with the published total are a separate study.'));

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
  c.push(H1('Appendix A. The Headline Design'));
  c.push(P(`Table A1 ranks the ten methods on the single test date, 26 August 2026, after training on ` +
    `${fmt(T.n_hari - 1)} business days. Table A2 reports the best method for each series on that date. ` +
    `The two rankings agree broadly, with a Spearman correlation of ${n(T.rank_corr.rho, 3)} ` +
    `(p = ${n(T.rank_corr.p, 4)}), but one day supports description only.`));
  c.push(TCAP('A1', `Headline design. Mean and median MASE over the ${T.n_leaf} series on one test date.`));
  c.push(rankTable(e1rank, false));
  c.push(TCAP('A2', 'Headline design, series by series. Best method chosen per series by MASE on the test date.'));
  c.push(appendixTable());
  c.push(...appendixBeeswarm());
  c.push(...appendixZeroFill());
  c.push(...appendixFitur());
  c.push(...appendixRezim());
  c.push(...appendixRepro());
  c.push(...appendixInferensi());

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
    'Each learner was run with a single random seed, so part of these learner-level differences may be ' +
    'model variance rather than an effect of the component. Appendix G gives every learner separately.'));
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
    'The forecasters in our pipeline build their features afresh at prediction time, and in the first ' +
    'version the routine that does so could not accept the market series. The model was trained on market ' +
    'features and then received zeros in their place when it forecast, with no error or warning. This is a ' +
    'case of training-serving skew, a known hazard of machine-learning systems (Sculley et al., 2015).',
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
    'The learners minimise squared error while the evaluation uses absolute error, and each learner was run with one random seed, so part of the differences between arms may be model variance.',
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
  c.push(P('Table C1 and Figures C1 and C2 compare three arms, namely market data off, market data supplied ' +
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
  const ext = fam['External'] ?? 0;
  const c = [];
  c.push(H1('Appendix E. Exchange-Rate Regimes and Market Data'));
  c.push(P('Every market-data result here is conditional on the regime. Many emerging-market central banks ' +
    'that describe their currencies as floating limit their movement in practice (Calvo and Reinhart, 2002), ' +
    'and intervention in emerging markets is regular and often effective (Menkhoff, 2013; Fratzscher et al., ' +
    '2019). When the central bank leans against pressure, part of the private flow is absorbed by its own ' +
    'transactions and the rate moves less than the flow alone would imply, which weakens the link from prices ' +
    'to next-day private flows that market features rely on. Three conjectures follow.'));
  c.push(...BUL([
    `**Regime depth.** In a deep free-floating market, lagged prices should carry more information about next-day flows, and the market share of importance, ${n(ext, 1)} per cent here, should be larger.`,
    '**Counterparty sensitivity.** Market variables should matter most for counterparties that trade on prices, such as non-resident portfolio investors, and least for trade settlement. Non-resident investment (C.1) is a counter-example in this panel, with no market feature selected, possibly because its flows are dominated by government bond transactions with their own drivers.',
    '**Policy episodes.** Around interventions and macroprudential measures the importance of market variables should shift, which could be tested with SHAP values and test origins placed inside and outside such episodes.',
  ]));
  return c;
}

function appendixRepro() {
  const v = T.versi, r = T.repro;
  return [H1('Appendix F. Reproducibility'), P(
    `The results were produced under Python ${v.python}, NumPy ${v.numpy}, pandas ${v.pandas}, SciPy ${v.scipy}, ` +
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

function refs() {
  return [
    'Benjamini, Y. and Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society, Series B*, 57(1), 289–300.',
    'Bergmeir, C. and Benítez, J. M. (2012). On the use of cross-validation for time series predictor evaluation. *Information Sciences*, 191, 192–213.',
    'Breiman, L. (2001). Random forests. *Machine Learning*, 45(1), 5–32.',
    'Calvo, G. A. and Reinhart, C. M. (2002). Fear of floating. *Quarterly Journal of Economics*, 117(2), 379–408.',
    'Chen, T. and Guestrin, C. (2016). XGBoost: a scalable tree boosting system. In *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.',
    'Claeskens, G., Magnus, J. R., Vasnev, A. L. and Wang, W. (2016). The forecast combination puzzle: a simple theoretical explanation. *International Journal of Forecasting*, 32(3), 754–762.',
    'Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289–303.',
    'Davydenko, A. and Fildes, R. (2013). Measuring forecasting accuracy: the case of judgmental adjustments to SKU-level demand forecasts. *International Journal of Forecasting*, 29(3), 510–522.',
    'Diebold, F. X. and Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business and Economic Statistics*, 13(3), 253–263.',
    'Evans, M. D. D. and Lyons, R. K. (2002). Order flow and exchange rate dynamics. *Journal of Political Economy*, 110(1), 170–180.',
    'Fratzscher, M., Gloede, O., Menkhoff, L., Sarno, L. and Stöhr, T. (2019). When is foreign exchange intervention effective? Evidence from 33 countries. *American Economic Journal: Macroeconomics*, 11(1), 132–156.',
    'Guyon, I. and Elisseeff, A. (2003). An introduction to variable and feature selection. *Journal of Machine Learning Research*, 3, 1157–1182.',
    'Hansen, P. R., Lunde, A. and Nason, J. M. (2011). The model confidence set. *Econometrica*, 79(2), 453–497.',
    'Harvey, D., Leybourne, S. and Newbold, P. (1997). Testing the equality of prediction mean squared errors. *International Journal of Forecasting*, 13(2), 281–291.',
    'Hastie, T., Tibshirani, R. and Friedman, J. (2009). *The Elements of Statistical Learning*, 2nd edition. New York: Springer.',
    'Hodges, J. L. and Lehmann, E. L. (1963). Estimates of location based on rank tests. *Annals of Mathematical Statistics*, 34(2), 598–611.',
    'Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2), 65–70.',
    'Hyndman, R. J. and Koehler, A. B. (2006). Another look at measures of forecast accuracy. *International Journal of Forecasting*, 22(4), 679–688.',
    'Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q. and Liu, T.-Y. (2017). LightGBM: a highly efficient gradient boosting decision tree. In *Advances in Neural Information Processing Systems*, 30, 3146–3154.',
    'Kohavi, R. and John, G. H. (1997). Wrappers for feature subset selection. *Artificial Intelligence*, 97(1–2), 273–324.',
    'Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of Statistics*, 17(3), 1217–1241.',
    'Lakens, D. (2017). Equivalence tests: a practical primer for t tests, correlations, and meta-analyses. *Social Psychological and Personality Science*, 8(4), 355–362.',
    'Lundberg, S. M. and Lee, S.-I. (2017). A unified approach to interpreting model predictions. In *Advances in Neural Information Processing Systems*, 30, 4765–4774.',
    'Lyons, R. K. (2001). *The Microstructure Approach to Exchange Rates*. Cambridge, MA: MIT Press.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2018). The M4 competition: results, findings, conclusion and way forward. *International Journal of Forecasting*, 34(4), 802–808.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2020). The M4 competition: 100,000 time series and 61 forecasting methods. *International Journal of Forecasting*, 36(1), 54–74.',
    'Makridakis, S., Spiliotis, E. and Assimakopoulos, V. (2022). M5 accuracy competition: results, findings, and conclusions. *International Journal of Forecasting*, 38(4), 1346–1364.',
    'Meese, R. A. and Rogoff, K. (1983). Empirical exchange rate models of the seventies: do they fit out of sample? *Journal of International Economics*, 14(1–2), 3–24.',
    'Menkhoff, L. (2013). Foreign exchange intervention in emerging markets: a survey of empirical studies. *The World Economy*, 36(9), 1187–1208.',
    'Menkhoff, L., Sarno, L., Schmeling, M. and Schrimpf, A. (2016). Information flows in foreign exchange markets: dissecting customer currency trades. *Journal of Finance*, 71(2), 601–634.',
    'Montero-Manso, P. and Hyndman, R. J. (2021). Principles and algorithms for forecasting groups of time series: locality and globality. *International Journal of Forecasting*, 37(4), 1632–1653.',
    'Peng, H., Long, F. and Ding, C. (2005). Feature selection based on mutual information: criteria of max-dependency, max-relevance, and min-redundancy. *IEEE Transactions on Pattern Analysis and Machine Intelligence*, 27(8), 1226–1238.',
    'Pesaran, M. H. and Timmermann, A. (1992). A simple nonparametric test of predictive performance. *Journal of Business and Economic Statistics*, 10(4), 461–465.',
    'Politis, D. N. and Romano, J. P. (1994). The stationary bootstrap. *Journal of the American Statistical Association*, 89(428), 1303–1313.',
    'Sculley, D., Holt, G., Golovin, D., Davydov, E., Phillips, T., Ebner, D., Chaudhary, V., Young, M., Crespo, J.-F. and Dennison, D. (2015). Hidden technical debt in machine learning systems. In *Advances in Neural Information Processing Systems*, 28, 2503–2511.',
    'Smith, J. and Wallis, K. F. (2009). A simple explanation of the forecast combination puzzle. *Oxford Bulletin of Economics and Statistics*, 71(3), 331–355.',
    'Syntetos, A. A. and Boylan, J. E. (2005). The accuracy of intermittent demand estimates. *International Journal of Forecasting*, 21(2), 303–314.',
    'Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: an analysis and review. *International Journal of Forecasting*, 16(4), 437–450.',
    'Taylor, S. J. and Letham, B. (2018). Forecasting at scale. *The American Statistician*, 72(1), 37–45.',
    'Turing, A. M. (1950). Computing machinery and intelligence. *Mind*, 59(236), 433–460.',
    'Wickramasuriya, S. L., Athanasopoulos, G. and Hyndman, R. J. (2019). Optimal forecast reconciliation for hierarchical and grouped time series through trace minimization. *Journal of the American Statistical Association*, 114(526), 804–819.',
    'Wilcoxon, F. (1945). Individual comparisons by ranking methods. *Biometrics Bulletin*, 1(6), 80–83.',
];
}

const OUTF = process.argv[2] || path.join(KERJA, 'FX_15seri.docx');
console.log(`nama leaf tampilan: ${nTampil} potongan teks memakai nama baru (nama_leaf.json)`);
Packer.toBuffer(doc).then(b => { fs.writeFileSync(OUTF, b); console.log('ditulis:', OUTF, (b.length / 1024).toFixed(0) + ' KB'); });
