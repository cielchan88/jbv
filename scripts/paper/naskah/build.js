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
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, Footer, PageNumber,
} = D;

const path = require('path');

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
function runs(text) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), size: 21, color: INK }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, size: 21, color: INK }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, size: 21, color: INK }));
    last = re.lastIndex;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), size: 21, color: INK }));
  return out;
}
const P = t => new Paragraph({ spacing: { after: 150, line: 300 }, alignment: AlignmentType.JUSTIFIED, children: runs(t) });

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
const NOTE = t => new Paragraph({ spacing: { before: 40, after: 190 }, children: [new TextRun({ text: t, size: 17, italics: true, color: MUTED })] });
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
  c.push(H1('Abstract'));
  c.push(LEAD('Background',
    'A central bank that watches the foreign-exchange market daily needs more than the net total: exporters, ' +
    'importers, individuals and non-residents behave differently, and one aggregate number hides all of it. ' +
    'The desk works on a daily cycle, so the forecast it needs is for the next business day.'));
  c.push(LEAD('Objectives',
    `We forecast ${T.n_leaf} flow series one business day ahead, each series being one counterparty group and ` +
    'one transaction purpose, and ask which method works best for each series, how many engineered features a ' +
    'machine-learning model should keep, whether market data such as the exchange rate and the equity index ' +
    'help, and whether the answer changes across counterparty groups.'));
  c.push(LEAD('Methodology',
    `The panel covers ${T.n_leaf} cells over 5,032 business days, from 2 January 2006 to 26 August 2026, ` +
    'in millions of US dollars. ' +
    'The headline test trains on every day except the last and forecasts the last day; because one test day ' +
    'gives no sampling distribution, every statistical test uses a second design with 30 rolling one-day origins. ' +
    'Ten methods are compared, drawn from classical statistical forecasting and machine learning, with ' +
    'deep-learning models outside the scope, and the number of retained features is chosen by ablation rather ' +
    'than taken from convention.'));
  c.push(LEAD('Findings',
    `The striking result is how little survives paired testing. ` +
    `No method wins everywhere: eight of the ten are best on at least one series and none on more than ` +
    `${bestCount[0][1]} of ${T.n_leaf}. ` +
    `The aggregate ranking dissolves as well: the three tree ensembles finish within 4.5 per cent of each ` +
    `other and signed-rank tests separate none of them ` +
    `(p = ${n(T.champion_tests[0].p, 3)} and ${n(T.champion_tests[1].p, 3)}); the first gap the data ` +
    `support is the one to ARIMA. ` +
    `Nor does any part of the configuration earn its place. Removing redundancy-aware selection, daily ` +
    `re-fitting or hyperparameter tuning moves the pooled mean by ` +
    `${pct(T.reverse_ablation[0].delta)}, ${pct(T.reverse_ablation[1].delta)} and ` +
    `${pct(T.reverse_ablation[2].delta)} respectively, and not one of the three reaches significance; ` +
    `tuning is the wrong sign, and switching it off improves ` +
    `${T.reverse_leaf_worse['Tuned hyperparameters']} of the ${T.n_leaf} series. ` +
    `The feature count is a null too: no count between 6 and 20 beats the usual 25. ` +
    `Market data are the one factor that moves anything decisively, and the result there is mostly a ` +
    `methodological artefact that we found and corrected. ` +
    `Supplying the market series when the model is trained but not when it forecasts - the default behaviour ` +
    `of a recursive forecaster, which has no future values of another series - raises pooled error by ` +
    `${n(T.tabel8b_gabungan.delta_nol, 1)} per cent. ` +
    `At a one-day horizon that omission is unnecessary, because the market lags the model uses are already ` +
    `observed when the forecast is made. Supplying them cuts the penalty to ` +
    `${n(T.tabel8b_gabungan.delta_benar, 1)} per cent, so ${n(T.tabel8b_gabungan.rusak_hilang_pct, 0)} per ` +
    `cent of the apparent damage was an artefact of the handling. ` +
    `What identifies the mechanism is that the penalty scaled with how many slots the selector gave the ` +
    `market variables (Spearman ${n(T.slot_damage.nol.rho, 2)}, p = ${n(T.slot_damage.nol.p, 3)}) and that ` +
    `this relationship disappears once they are supplied (${n(T.slot_damage.benar.rho, 2)}, ` +
    `p = ${n(T.slot_damage.benar.p, 3)}). ` +
    `A residual cost of ${n(T.tabel8b_gabungan.delta_benar, 1)} per cent remains and is significant, but it ` +
    `is not uniform: ${T.n_leaf_membaik} of the ${T.n_leaf} series are more accurate with market data than ` +
    `without.`));
  c.push(LEAD('Significance and conclusion',
    'The one-day problem is not a smaller version of the long-horizon problem: settings copied from a longer ' +
    'horizon can be useless or harmful, and machinery built for recursive multi-step forecasting can quietly ' +
    'discard information that a one-day forecast already has. ' +
    'On a panel of this size the honest summary of the engineering choices is that they are not separable ' +
    'from noise, which is itself a finding worth reporting rather than a failure to find one. ' +
    'We recommend forecasting each counterparty and purpose cell on its own, tuning at the horizon that will ' +
    'actually be run, and keeping a random walk in production as a pass-or-fail threshold for every series.'));
  c.push(new Paragraph({
    spacing: { before: 110, after: 60 },
    children: [new TextRun({ text: 'Keywords: ', bold: true, size: 20, color: INK }),
      new TextRun({ text: 'one-day-ahead forecasting; foreign-exchange flows; disaggregated forecasting; feature selection; ablation study; SHAP; gradient boosting; MASE', size: 20, color: INK })],
  }));
  c.push(new Paragraph({
    spacing: { after: 200 },
    children: [new TextRun({ text: 'JEL classification: ', bold: true, size: 20, color: INK }),
      new TextRun({ text: 'C22, C53, F31, E58', size: 20, color: INK })],
  }));

  /* ---------------------------------------------------------- 1. Intro */
  c.push(H1('1. Introduction'));

  c.push(H2('1.1. Background and Context'));
  c.push(P('A central bank that watches the foreign-exchange market needs a forward view of supply and demand. ' +
    'The net total is useful but not enough. ' +
    'Two days can share the same net total and be nothing alike: on one, exporters sell and importers buy in equal measure; ' +
    'on the other, non-residents pull money out while corporates sit still. ' +
    'Those two days call for different responses.'));
  c.push(P('The setting is Indonesia, and two structural features matter for reading the results. ' +
    'The exchange-rate regime is a managed float, so flows and the rate are linked through a policy reaction as ' +
    'well as through the market; and the onshore market is shallow by regional standards, so a single large ' +
    'corporate settlement can move the daily total in one cell. ' +
    'Both raise the weight of counterparty composition, which is what this paper forecasts, and both bound how ' +
    'far the results travel — a point we return to in Section 5.4.'));
  c.push(P('The data are administrative. Banks report each transaction, and every transaction carries a counterparty group and a declared purpose. ' +
    'That gives a two-way grid of who transacted and why, and the grid cell is the unit of analysis here.'));
  c.push(IMG('fig1_taxonomy.png', 560, 258));
  c.push(FCAP(1, `The ${T.n_leaf} forecast units. Rows are counterparty groups, columns declared purposes, ` +
    'and each filled cell one series, labelled with its sample mean in millions of US dollars. ' +
    'Blue is net supply of foreign exchange, red net demand. Dashed cells do not occur.'));
  c.push(P('The cells do not behave alike. Some are dense and move smoothly; others are zero on most days and then jump. ' +
    'That is the first reason to avoid one pooled model for the whole grid.'));

  c.push(H2('1.2. Problem Statement'));
  c.push(P('The monitoring cycle is daily: the desk closes one day and plans the next. ' +
    'The forecast that fits this cycle is one business day ahead. ' +
    'Longer horizons matter for planning, but they answer a different question.'));
  c.push(P('Forecasting flows is also not the same as forecasting the exchange rate. ' +
    'Rates are prices, and are famously hard to beat with a random walk (Meese and Rogoff, 1983). ' +
    'Flows are quantities, and they carry strong autocorrelation, calendar effects and settlement patterns that prices do not.'));
  c.push(P('Three practical choices are usually made by habit rather than evidence. ' +
    'How many engineered features should the model keep? Should market data be added? ' +
    'Should each cell be modelled on its own, or pooled? ' +
    'This paper treats all three as questions to be tested.'));

  c.push(H2('1.3. Research Objectives and Questions'));
  c.push(P('The study answers four questions.'));
  c.push(...BUL([
    '**RQ1.** Which method forecasts each counterparty and purpose series best one day ahead? Does any single method dominate?',
    '**RQ2.** How many engineered features should a tree-based model keep? Is the usual count of 25 defensible on this data?',
    '**RQ3.** Do daily market data help? We test the rupiah exchange rate, the one-month forward, the ten-year bond yield, the dollar index, non-resident equity flows and the equity index.',
    '**RQ4.** Which features does the model actually rely on, and does that differ across counterparty groups?',
  ]));

  c.push(H2('1.4. Significance of the Study'));
  c.push(P('The paper adds three things: it forecasts at the level the supervisory question is asked, the ' +
    'counterparty and purpose cell rather than the total; it chooses the feature count by ablation and shows ' +
    'the whole curve, not just the winning value; and it tests market data at a horizon where those data are ' +
    'genuinely known in advance, which avoids a common source of flattering results.'));

  /* --------------------------------------------------- 2. Literature */
  c.push(H1('2. Literature Review'));

  c.push(H2('2.1. Theoretical Background'));
  c.push(P('Two ideas shape the design. The first is the bias–variance trade-off. ' +
    'Adding predictors lowers bias and raises variance, and past some point the second effect wins: ' +
    'out-of-sample accuracy falls even while in-sample fit keeps improving (Hastie, Tibshirani and Friedman, 2009). ' +
    'Theory does not say where that point sits for a given dataset. Only measurement does.'));
  c.push(P('The second comes from market microstructure. ' +
    'Order flow carries information about exchange-rate moves (Evans and Lyons, 2002; Lyons, 2001). ' +
    'If flows and prices are linked, price variables might help forecast flows. ' +
    'Whether they do so one day ahead, on top of the flow series own history, is an open question, and we test it directly.'));

  c.push(H2('2.2. Critical Review of Existing Literature'));
  c.push(P('Forecasting competitions give a consistent message: simple methods are hard to beat and combinations usually help ' +
    '(Makridakis, Spiliotis and Assimakopoulos, 2018, 2020). ' +
    'Gradient-boosted trees do well on tabular problems (Chen and Guestrin, 2016; Ke et al., 2017), ' +
    'but their edge over a good statistical benchmark on short-horizon series is smaller than often assumed.'));
  c.push(P('Feature selection is well studied in theory (Guyon and Elisseeff, 2003; Kohavi and John, 1997), ' +
    'but applied time-series work rarely says how the retained-feature count was chosen, and when it is tuned ' +
    'only the winning value is reported, so the reader cannot see how sensitive the result is. ' +
    'Evaluation practice is uneven too: Bergmeir and Benítez (2012) and Tashman (2000) set out how ' +
    'rolling-origin evaluation should work, yet single-split evaluations remain common and are often reported ' +
    'without noting that one split gives no sampling distribution.'));

  c.push(H2('2.3. Identification of Research Gaps'));
  c.push(P('Three gaps follow.'));
  c.push(...BUL([
    'Disaggregated administrative flow series are rarely forecast cell by cell. Most work models a total, because that is how the data are published, not because that is where decisions are made.',
    'Retained-feature counts are almost never reported as a tuned quantity with a sensitivity curve. Published settings are therefore hard to move to a new dataset.',
    'External predictors are often tested at horizons where their own future values would not be known. That inflates their apparent value.',
  ]));

  c.push(H2('2.4. Conceptual Framework and Hypothesis Development'));
  c.push(P('We treat a forecasting system as a set of design choices, each of which can be varied while the rest is held fixed. ' +
    'Each hypothesis is written the way a practitioner would expect it to hold, because the prior belief is the thing being tested.'));
  c.push(TCAP(1, 'Hypotheses, the design choice each one isolates, and the test used.'));
  c.push(TBL([620, 3300, 2500, 2940],
    ['', 'Hypothesis', 'What is varied', 'Test'],
    [
      ['H1', 'No single method is best for all series one day ahead.', 'Method, per series', `Count of best methods across ${T.n_leaf} series`],
      ['H2', 'A feature count below 25 features improves one-day accuracy.', 'Feature count, 6 to 25', 'Paired Wilcoxon against k = 25'],
      ['H3', 'Adding market data improves one-day accuracy.', 'Market data on or off', 'Paired Wilcoxon, on against off'],
      ['H4', 'The model draws most of its signal from the series own history, not from market data.', 'Nothing; measured on the fitted model', 'SHAP importance by feature family'],
    ], { rightFrom: 99 }));
  c.push(NOTE('H2 and H3 are written in the direction a practitioner would expect. Both are tested two-sided. Both are rejected, and H3 with the sign reversed.'));

  /* --------------------------------------------------- 3. Methodology */
  c.push(H1('3. Methodology'));

  c.push(H2('3.1. Research Design and Approach'));
  c.push(P('The study is a controlled comparison. ' +
    'The panel, the anchor date and the error measure stay the same throughout, and only one design element changes at a time. ' +
    'Two evaluation designs are used, and the difference between them matters for how the results should be read.'));
  c.push(IMG('fig2_design.png', 560, 148));
  c.push(FCAP(2, 'The two evaluation designs. Panel A is the operational design: train on everything except ' +
    'the last day, then forecast that day, which gives one error per series and no sampling distribution. ' +
    'Panel B supports the statistical tests, re-fitting parameters at every origin of a 30-day block and ' +
    'forecasting one day ahead using the actual history up to the day before.'));
  c.push(P('At a one-day horizon, using yesterday actual value is not leakage; it is how the desk works, since ' +
    'the forecaster always knows yesterday. ' +
    'That is why the rolling design is valid, and also why the usual distinction between recursive and direct ' +
    'multi-step strategies (Marcellino, Stock and Watson, 2006) does not arise here.'));
  c.push(NOTE('Parameters are re-fitted at every origin, which is how the system is meant to run. ' +
    'Section 4.3 measures what fitting once per block instead would cost, and finds it is the one ' +
    'component of the configuration whose contribution a paired test supports.'));

  c.push(H2('3.2. Data Sources'));
  c.push(P(`The panel has ${T.n_leaf} daily series of net foreign-exchange transaction flows. ` +
    '**All values are in millions of US dollars.** ' +
    'They cover 5,032 business days from 2 January 2006 to 26 August 2026. ' +
    'Each series is one counterparty group and one declared purpose, as in Figure 1. ' +
    'A positive value is net supply of foreign exchange; a negative value is net demand.'));
  c.push(P('One aggregation is applied to the reporting framework before any modelling. ' +
    'The framework separates foreign-investment corporates from other corporates for three of the six ' +
    'corporate purposes: import, repatriation and other. ' +
    'Those three foreign-investment cells are thin - one of them is zero on 95.9 per cent of days, and its ' +
    'entire 30-day evaluation block is zero - so a forecast for it would be scored on a cell where ' +
    'predicting zero is already perfect. ' +
    'The supervisory question for those purposes is asked of corporates as a whole, so we sum each ' +
    'foreign-investment cell into its counterpart and forecast the combined series. ' +
    'Flows are additive, so the aggregation moves demand between cells without creating or destroying any: ' +
    'the panel total is unchanged to machine precision.'));
  c.push(NOTE('The alternative is to forecast all eighteen cells and exclude the degenerate one from every ' +
    'reading, which is what a longer version of this study did. ' +
    'Merging is preferable because it removes the exception rather than carrying it through every table, ' +
    'and because the merged cell is the unit a supervisor actually acts on.'));
  c.push(P('The market data cover the same 5,032 dates, with no date missing on either side. ' +
    'Eight variables are used: spot USD/IDR bid and ask, one-month forward bid and ask, the ten-year government ' +
    'bond yield, the dollar index, net non-resident equity flows, and the equity index. ' +
    'Missing values are rare, between 0.1 and 0.7 per cent, and are carried forward; no value is carried ' +
    'backwards by more than one date, so the training sample holds no future information.'));
  c.push(TCAP(2, `Descriptive statistics for the ${T.n_leaf} series. Values in millions of US dollars.`));
  c.push(descTable());
  c.push(NOTE('Sparsity still varies a great deal after the aggregation: the zero share runs from 0.4 per ' +
    'cent of days to 38.4. No cell is close to empty, which is what the aggregation was for. ' +
    'Excess kurtosis is the wider spread, from 0.8 to 241.'));

  c.push(H2('3.3. Data Collection Instruments and Procedures'));
  c.push(P('Ten methods are compared. Deep-learning models are outside the scope of this study and were not tested. ' +
    'The decision is a scoping one resting on published evidence rather than on results of ours: the M4 ' +
    'competition found that pure machine-learning and neural methods did not outperform established statistical ' +
    'benchmarks across a large and varied collection of series (Makridakis et al., 2018, 2020), and our panel is ' +
    'short by deep-learning standards and mostly zero in several cells, which is the combination that literature ' +
    'identifies as least favourable. ' +
    'Whether that expectation holds here is an empirical question we leave open; nothing in this paper tests it.'));
  c.push(TCAP(3, 'The ten methods, grouped by family.'));
  c.push(TBL([1850, 1450, 6060],
    ['Method', 'Family', 'What it does'],
    [
      ['Random walk', 'Benchmark', 'Forecast equals yesterday. The MASE denominator is defined against this method, so its own MASE is one by construction.'],
      ['Rolling mean', 'Benchmark', 'Mean of the last 90 days. Suits a series that reverts to its mean.'],
      ['Random walk with drift', 'Benchmark', 'Yesterday plus the average trend over the whole history.'],
      ['Croston', 'Intermittent', 'Smooths non-zero sizes and gaps between them separately (Croston, 1972). Built for series with many zeros.'],
      ['Seasonal decomposition', 'Structural', 'Multiplies a month-of-year share, a day-of-month share and an annual level. A scaling factor is calibrated on recent data.'],
      ['ARIMA', 'Statistical', 'Order picked automatically by information criterion. Stationarity checked with KPSS.'],
      ['Prophet', 'Statistical', 'Splits the series into trend and several seasonal terms (Taylor and Letham, 2018).'],
      ['Random forest', 'Machine learning', 'Bagged regression trees (Breiman, 2001) on the engineered features.'],
      ['LightGBM', 'Machine learning', 'Gradient-boosted trees with histogram splitting (Ke et al., 2017).'],
      ['XGBoost', 'Machine learning', 'Gradient-boosted trees with a regularised objective (Chen and Guestrin, 2016).'],
    ], { rightFrom: 99 }));
  c.push(NOTE('The method called seasonal decomposition is an in-house baseline, known internally as the APUVA algorithm. ' +
    'It is renamed here for the standard method it matches: a multiplicative seasonal-index forecast built from nested calendar shares.'));

  c.push(H3('Model settings'));
  c.push(P('Table 4 lists the library defaults for the three machine-learning methods; results in this paper ' +
    'do not use them. ' +
    'For each series and method we search a grid of four configurations, scored on a validation block of ten ' +
    'origins that ends where the test block begins, and carry the winner forward, so selection and evaluation ' +
    'use disjoint data. ' +
    'The defaults are listed because Section 4.3 reports what tuning contributes over them.'));
  c.push(TCAP(4, 'Settings for the machine-learning methods. Applied identically to every series.'));
  c.push(TBL([2000, 1900, 1900, 1900, 1660],
    ['Method', 'Trees', 'Max depth', 'Learning rate', 'Target transform'],
    [
      ['Random forest', '100', '10', 'n/a', 'none'],
      ['LightGBM', '100', '5', '0.05', 'none'],
      ['XGBoost', '100', '5', '0.05', 'none'],
    ], { rightFrom: 1 }));
  c.push(NOTE('ARIMA order is chosen automatically by information criterion, with stationarity checked by KPSS. ' +
    'Prophet uses its own default seasonality settings. ' +
    'Croston and the seasonal decomposition have smoothing constants estimated from the training sample.'));

  c.push(H3('The feature pool'));
  c.push(P('The three machine-learning methods share one pool of engineered features, all built from the ' +
    'series own history: lags, rolling statistics, exponentially weighted means, differences and percentage ' +
    'changes, volatility and extreme-value measures, technical indicators, Fourier terms and calendar effects, ' +
    `for ${T.pool_internal} candidates in total. ` +
    `The lags are worth naming. ${T.n_lags} lags of the target enter the pool — every day from one to fifteen, ` +
    'then twenty, twenty-five and thirty — and rolling statistics use windows of seven, fourteen, thirty, sixty ' +
    'and ninety days. ' +
    'At a one-day horizon the near lags are where signal is most likely to sit, so concluding that recent ' +
    'history carries the predictable signal while never offering lags two through six to the selector would be ' +
    'a conclusion never tested.'));
  c.push(NOTE('A wide lag pool and a univariate selection rule are a poor pair. ' +
    'Consecutive lags are highly correlated, so a rule that ranks candidates one at a time will admit a block of ' +
    'near-duplicates and crowd out features carrying different information. ' +
    'The redundancy-aware criterion below penalises exactly that overlap, which is what makes a pool of this ' +
    'width usable; neither choice is safe without the other.'));
  c.push(P(`Adding the eight market variables extends the pool to ${T.pool_total} candidates. ` +
    'Each market variable enters as three lags, of one, seven and fourteen days, and a seven-day rolling mean. ' +
    'Market variables are therefore lagged on the same principle as the target: no contemporaneous value of any ' +
    'market variable enters the model, because on the morning a forecast is made that day own market data do not yet exist.'));
  c.push(NOTE('One point is easy to get wrong. The "with market data" condition does **not** replace the ' +
    `engineered features: it adds 32 market candidates to the same ${T.pool_internal} engineered ones, and all ` +
    `${T.pool_total} then compete for the same fixed number of slots. ` +
    'That competition, not the market data alone, is what Section 4.2 measures.'));
  c.push(P('Selection scores each candidate by its absolute Spearman correlation with the target, minus its ' +
    'average absolute correlation with the candidates already chosen, and adds features one at a time, highest ' +
    'score first, until k are held. ' +
    'The rule is the standard minimum-redundancy maximum-relevance criterion (Peng, Long and Ding, 2005), and ' +
    'both correlations are computed on the training sample only. ' +
    'Section 4.3 reports what it is worth against a univariate alternative that ignores overlap between ' +
    'candidates; the value of k comes from the ablation described next.'));

  c.push(H2('3.4. Data Analysis Methods'));
  c.push(H3('Accuracy measure'));
  c.push(P('Accuracy is the mean absolute scaled error, or MASE, proposed by Hyndman and Koehler (2006) as a ' +
    'generally applicable replacement for percentage-based measures. ' +
    'Their argument applies directly here: percentage errors are undefined when the actual value is zero and ' +
    'asymmetric between over- and under-prediction, while relative errors can have infinite variance, and ' +
    'scaling by an in-sample benchmark avoids both problems.'));
  c.push(P('Let Yₜ be the actual value at time t and Fₜ the forecast, so the error is eₜ = Yₜ − Fₜ. ' +
    'The scaled error divides it by the mean absolute first difference of the training sample of n observations:'));
  c.push(EQ('qₜ  =  eₜ  ⁄  [ (1 ⁄ (n − 1)) ∑ᵢ₌₂ⁿ |Yᵢ − Yᵢ₋₁| ]'));
  c.push(P('MASE is the mean of the absolute scaled errors over the test points:'));
  c.push(EQ('MASE  =  (1 ⁄ m) ∑ₜ₌₁ᵐ |qₜ|'));
  c.push(P('The denominator is the in-sample mean absolute error of the naïve one-step forecast, that is of the ' +
    'random walk. Three properties follow, and all three matter for this panel.'));
  c.push(...BUL([
    `It is scale-free. The ${T.n_leaf} series differ in size by two orders of magnitude, so raw errors cannot be pooled across them; scaled errors can.`,
    'It is defined when actual values are zero. Several cells here are zero on a third of days or more, which rules out the mean absolute percentage error entirely.',
    'It reads naturally. A MASE of one matches the in-sample random walk, below one beats it and above one loses to it, so the threshold is fixed by construction.',
  ]));
  c.push(NOTE('The denominator is computed on the training sample only, never on the test block, since scaling ' +
    'by a quantity that includes the test period would let the evaluation window into the measure itself. ' +
    'Because it is fixed before testing begins, the random walk own MASE on the test block is close to but not ' +
    'exactly one, and is reported as measured. ' +
    'R-squared and directional accuracy are dropped for the single test date, being undefined on one observation.'));
  c.push(P('Paired comparisons use the Wilcoxon signed-rank test, with pairs formed on series, model and origin. ' +
    'Pairing is essential, because series differ from each other far more than treatments differ within a series.'));
  c.push(NOTE('One caution applies to every rank test here, and it recurs throughout Section 4. ' +
    'The Wilcoxon statistic sees the direction of each difference, not its size, so a setting that wins slightly ' +
    'on most units and fails badly on a few will pass the test and still be unusable. ' +
    'A mean is moved by a few large differences; a signed-rank test by many consistent ones. ' +
    'We therefore report the mean, the median and the maximum next to every p-value, and the two disagree often ' +
    'enough below that neither can be read alone.'));
  c.push(P('The ablation varies the number of retained features over six settings - 6, 8, 12, 16, 20 and 25 - ' +
    `holding everything else fixed, so each count uses the same ${T.n_leaf} series, three methods and 30 ` +
    `origins, giving ${(T.n_leaf * 3 * 30).toLocaleString('en-US')} paired observations. ` +
    'To see which features the model actually uses, we compute SHAP values on the fitted trees (Lundberg and ' +
    'Lee, 2017), which split a prediction into per-feature contributions and so show not only which features ' +
    'matter but in which direction.'));

  c.push(H2('3.5. Ethical Considerations'));
  c.push(P('The underlying transaction reports are confidential supervisory data. ' +
    'Every series used here is an aggregate over many banks and many transactions, and no individual bank, ' +
    'counterparty or transaction can be identified at this level. No record-level data were accessed. ' +
    'The forecasts support internal liquidity monitoring and are not used to make decisions about any single reporting institution.'));

  /* ------------------------------------------------------- 4. Results */
  c.push(H1('4. Results'));

  c.push(H2('4.1. Data Presentation and Description'));
  c.push(P('Table 2 shows a panel that remains heterogeneous in every way that matters: means run from ' +
    `${n(Math.min(...T.desc.map(d => d.mean)), 0)} to +${n(Math.max(...T.desc.map(d => d.mean)), 0)} million ` +
    'US dollars, excess kurtosis passes 200 in two series and sits below 1 in another, and the zero share runs ' +
    'from 0.4 to 38.4 per cent.'));
  c.push(P('Two features are shared by almost every series. ' +
    'Day-to-day autocorrelation of the level is positive everywhere, from 0.13 to 0.88, and — more useful — the ' +
    `autocorrelation of absolute changes is positive in all ${T.n_leaf} series, with a median near 0.49. ` +
    'That is volatility clustering, and it is why volatility measures sit in the candidate pool.'));

  c.push(NOTE('Every result in this paper uses one feature pool and one selection rule: ' +
    `${T.n_lags} lags among ${T.pool_internal} engineered candidates, chosen by the redundancy-aware criterion, ` +
    'with hyperparameters tuned on a preceding validation block. ' +
    'Two things vary, and both are stated where they apply. ' +
    'Market data enter only where they are the subject of the test: Tables 8 and 9 and Figures 6 to 10. ' +
    'Everywhere else — the method comparison in Tables 5 and 6, the feature-count ablation in Table 7, and the ' +
    'reverse ablation in Table 10 — the models see the engineered candidates alone, which is the configuration ' +
    'Section 4.2 recommends. ' +
    'And Tables 5, 6 and 10 and Figures 3, 4 and 11 re-fit parameters at every origin, while the comparative ' +
    'experiments in Tables 7, 8 and 9 and Figures 5, 6, 7 and 12 fit once per block, because they report ' +
    'the difference between arms rather than the level of accuracy and the same shortcut applies to every arm, ' +
    'so it shifts both sides equally and favours neither. ' +
    'Daily re-fitting would take about thirty-five hours against two.'));

  c.push(H2('4.2. Main Analysis and Hypothesis Testing'));

  c.push(H3('H1. Which method wins'));
  c.push(P('Table 5 gives the headline design, where every model trains on 5,031 days and forecasts 26 August 2026. ' +
    'Table 6 gives the same models over 30 rolling one-day origins.'));
  c.push(TCAP(5, `Headline design. Ten methods trained on 5,031 business days and tested on 26 August 2026. Averaged over the ${T.n_leaf} series.`));
  c.push(rankTable(e1rank));
  c.push(TCAP(6, 'Rolling design at optimal capacity. The same methods over 30 one-day origins, '
    + `${T.n_leaf * 30} forecasts each. Every feature-based model uses redundancy-aware selection, `
    + 'hyperparameters chosen on a preceding validation block, and parameters re-fitted at every origin.'));
  c.push(rankTable(e2rank));
  c.push(...tieGroupProse());
  c.push(P(`The two designs broadly agree on this panel. Their Spearman correlation is ` +
    `${n(T.rank_corr.rho, 3)} (p = ${n(T.rank_corr.p, 4)}): the same three tree ensembles lead under both, ` +
    `and the same two naive baselines trail. ` +
    `The agreement should not be over-read. It is a correlation between two orderings of ten methods, ` +
    `computed on ${T.n_leaf} series, and it says the single date was not unrepresentative - not that one ` +
    `test day is sufficient evidence. ` +
    `Within the leading group the two designs still disagree about the order, which is the part no design ` +
    `resolves. ` +
    `Figure 3 gives the stronger reason not to trust any aggregate ranking: the best method changes from ` +
    `series to series.`));
  c.push(IMG('fig3_leaf.png', 560, 250));
  c.push(FCAP(3, 'Accuracy by series over 30 one-day origins. Each row is one series and each grey dot one ' +
    'method; the red dot marks the best method for that series and the blue tick the random walk. ' +
    'The dashed line at MASE = 1 is the random-walk threshold, so dots to its left beat the benchmark.'));
  c.push(P(`Counting winners across the ${T.n_leaf} series gives: ` +
    bestCount.map(([m, k]) => `${nice(m)} (${k})`).join(', ') + `. ` +
    `No method wins more than ${bestCount[0][1]} of ${T.n_leaf}, so H1 holds, and a desk that runs one method for the ` +
    `whole grid accepts worse accuracy on most cells to keep the system simple. ` +
    `The pattern of winners is worth a closer look, because a natural guess is that sparsity picks the family: ` +
    `methods built for intermittent demand should win the series that are mostly zero. ` +
    `Figure 4 tests that guess.`));
  c.push(IMG('fig4_winners.png', 560, 227));
  c.push(FCAP(4, `How many of the ${T.n_leaf} series each method wins. `
    + `Eight methods win at least one; none wins more than ${bestCount[0][1]}. `
    + 'The distribution is flatter than any aggregate ranking suggests: a method that is mediocre on '
    + 'average can still be the right choice for a particular cell.'));
  c.push(...winnersProse());

  c.push(H3('H2. How many features to keep'));
  c.push(P('The ablation holds the model, the data, the origins and the metric fixed, and changes only the number ' +
    'of retained features. Figure 5 shows the curve; Table 7 gives the tests.'));
  c.push(IMG('fig5_kablation.png', 560, 197));
  c.push(FCAP(5, 'Feature-count ablation. Left: mean and median MASE against the number of features kept, '
    + `pooled over three methods, ${T.n_leaf} series and 30 origins. Right: the worst scaled error at each `
    + 'count. Both panels are flat: no count improves on the largest tested, and the worst case varies '
    + 'only between 11.7 and 12.5 with its peak at a loose count rather than a tight one.'));
  c.push(TCAP(7, 'Feature-count ablation. Paired Wilcoxon tests against the usual count of 25 features. Parameters are fitted once per block in this comparison; see the note in Section 4.1.'));
  c.push(ablationTable());
  c.push(...ablationProse());

  c.push(H3('H3. Do market data help'));
  c.push(P('The eight market variables are known for every date in the sample, including the test dates. ' +
    'One day ahead that is not an assumption: yesterday exchange rate and bond yield are on the screen when ' +
    'today forecast is made, so the test is a fair one.'));
  c.push(IMG('fig6_external.png', 560, 197));
  c.push(FCAP(6, 'Market data supplied at training but not at prediction, under both selection rules and both '
    + 'feature counts. '
    + 'Left: mean MASE with market data off and on, where off is lower in all four cells. '
    + 'Right: the share of non-tied paired forecasts on which off is the better of the two. '
    + 'Ties are excluded from the denominator and their share is printed above each bar: where a series '
    + 'admits no market feature the two arms are identical, and counting those days would make the losing '
    + 'arm appear to win. '
    + 'Both panels agree - market data are worse on both summaries. '
    + 'Section 4.2 shows that most of this loss is an artefact of how the features were handled at '
    + 'prediction time, not a property of the data.'));
  c.push(...externalProse());
  c.push(TCAP(8, 'Series by series: engineered features only against engineered features plus market data, '
    + 'under redundancy-aware selection on the full lag pool. Mean MASE over 30 one-day origins, pooled across '
    + 'the three machine-learning methods. "Market slots" counts the market features the selector retains.'));
  c.push(perLeafTable());
  c.push(...perLeafProse());

  c.push(H3('H3b. The market-data loss is mostly an artefact'));
  c.push(...suppliedProse());
  c.push(TCAP(9, 'Market data supplied at prediction time against the same data zero-filled, both measured '
    + 'against the no-market baseline. Mean MASE over 30 one-day origins, pooled across the three '
    + 'machine-learning methods. "Recovered" is the share of the zero-filled penalty that disappears once the '
    + 'features are supplied.'));
  c.push(suppliedTable());
  c.push(IMG('fig6b_pasar_benar.png', 560, 212));
  c.push(FCAP(7, 'Three arms of the same comparison. '
    + 'Left: mean MASE with market data off, with them supplied at training but zero-filled at prediction, '
    + 'and with them supplied at both. '
    + 'Right: each arm as a percentage penalty against the no-market baseline, with the share of the '
    + 'zero-filled penalty that the correction removes printed above.'));
  c.push(IMG('fig11_slot_damage.png', 560, 220));
  c.push(FCAP(8, 'Why the penalty scaled with exposure. '
    + 'Each point is one series at 25 features under redundancy-aware selection. '
    + 'Left: with market features zero-filled at prediction, the penalty rises with the number of slots the '
    + 'selector gives them. '
    + 'Right: once the features are supplied, the relationship disappears. '
    + 'This is what identifies the zero-fill as the mechanism rather than the market data themselves.'));
  c.push(...slotDamageProse());

  c.push(H3('H4. Which features the model actually uses'));
  c.push(P('Selection decides which features enter the model, not how much each contributes once it is fitted. ' +
    'Figure 9 shows what the selector kept for each series, and how much of the fitted model importance the ' +
    'market variables carry.'));
  c.push(IMG('fig8_slotcomposition.png', 560, 242));
  c.push(FCAP(9, 'What the selector kept, series by series, at a 25-feature set with market data switched on. ' +
    'Left: how the 25 slots divide between market variables, the series own lags, and everything else. ' +
    'Right: the share of total absolute SHAP value carried by the market variables in the fitted model.'));
  c.push(IMG('fig7_shapfamily.png', 560, 212));
  c.push(FCAP(10, 'Feature importance by family, from SHAP values on the fitted trees, averaged across all ' +
    `${T.n_leaf} series at a 25-feature set with market data switched on.`));
  c.push(...famProse());

  c.push(H2('4.3. What Each Part of the Configuration Contributes'));
  c.push(P('Section 4.2 reports every feature-based model at optimal capacity: redundancy-aware selection, ' +
    'hyperparameters chosen on a preceding validation block, and parameters re-fitted at every origin. ' +
    'Which of those three earns its place? We remove them one at a time, each arm switching off exactly one ' +
    'component and leaving the other two in place, so the number reported is what that component contributes on ' +
    `top of the rest rather than on its own. Each arm covers ${(T.n_leaf * 3 * 30).toLocaleString('en-US')} paired points.`));
  c.push(TCAP(10, 'Reverse ablation. Each row removes one component from the optimal configuration. '
    + 'A positive change means the optimal configuration is better by that much. '
    + 'Wins count the paired forecasts on which the optimal configuration is the more accurate of the two.'));
  c.push(reverseAblationTable());
  c.push(IMG('fig9_ablation.png', 560, 265));
  c.push(FCAP(11, 'What each component contributes, by method and pooled. ' +
    'Bars above zero mean the optimal configuration is better. ' +
    'The dashed line is the pooled effect with its paired test.'));
  c.push(...reverseAblationProse());

  c.push(H3('Is the market-data loss the data, or the selector?'));
  c.push(P('A univariate rule that ranks features one at a time by absolute Spearman correlation with the target ' +
    'is blind to overlap between candidates, so a block of eight market variables — each correlated with the level ' +
    'and with each other — could crowd out lags simply by arriving together. ' +
    'On that reading the market-data loss would be a fault of the selector rather than of the data, and it should ' +
    'disappear under the redundancy-aware rule. We repeat the on-off comparison under both rules.'));
  c.push(IMG('fig10_selector.png', 560, 204));
  c.push(FCAP(12, 'What replacing the univariate rule with the redundancy-aware one is worth, at a 25-feature set. ' +
    'Left: how many market features get in. Right: what switching them on costs.'));
  c.push(...selectorProse());

  /* ---------------------------------------------------- 5. Discussion */
  c.push(H1('5. Discussion'));

  c.push(H2('5.1. Synthesis and Interpretation of Findings'));
  c.push(...synthProse());

  c.push(H2('5.2. Alignment and Contrast with Prior Research'));
  c.push(P('Simple benchmarks holding up is familiar from the forecasting competitions ' +
    '(Makridakis, Spiliotis and Assimakopoulos, 2018, 2020). ' +
    'The random walk is not the best method overall here, but it is still best on ' +
    `${Object.values(T.best_per_leaf).filter(m => m === 'Naive').length} of ${T.n_leaf} series, and it needs no estimation at all.`));
  c.push(P('The feature-count result sits alongside bias-variance theory without confirming it. ' +
    'Theory says accuracy must fall once added features stop carrying information; at one day ahead we cannot ' +
    'detect that turning point in either direction, while at sixty days ahead, on the same reporting panel, it ' +
    'is clear and large. The lever exists, and its strength depends on the horizon. ' +
    'The market-data result, meanwhile, contrasts with the microstructure literature (Evans and Lyons, 2002), ' +
    'which studies how flows move prices. ' +
    'We test the reverse direction, one day ahead, on top of the flow series own history, and in this panel ' +
    'that direction is weak.'));

  c.push(H2('5.3. Theoretical and Practical Implications'));
  c.push(P('Five recommendations follow for an institution running a system like this.'));
  c.push(...BUL([
    '**Model each counterparty and purpose cell on its own.** Eight methods win at least one cell and none wins more than five, so one pooled choice is worse for most of the grid.',
    '**Tune at the horizon you will run.** The feature count matters at sixty days and not at one. A setting copied from another horizon is an untested assumption, not a saving.',
    `**Check what your forecaster actually receives at prediction time, before concluding a predictor is useless.** Training on a feature and then withholding it at forecast time is silent, and here it accounted for ${n(T.tabel8b_gabungan.rusak_hilang_pct, 0)} per cent of an apparent ${n(T.tabel8b_gabungan.delta_nol, 1)} per cent penalty on market data. The diagnostic is cheap: if the damage scales with how much of the feature pool the predictor occupies, suspect the plumbing before the data.`,
    `**Then test market data on their merits, and expect a modest cost.** Handled correctly they still raise pooled error by ${n(T.tabel8b_gabungan.delta_benar, 1)} per cent here, but not uniformly: ${T.n_leaf_membaik} of ${T.n_leaf} series improve. Decide per series rather than for the panel.`,
    '**Prefer a redundancy-aware filter to a univariate one, but do not expect much.** It points the right way at both feature counts and at neither is the gain separable from noise. Its real value here is that it makes a wide lag pool usable at all.',
    '**Keep the random walk in production as a threshold.** Flag any series where the deployed model cannot beat MASE = 1, because a free benchmark is doing better there.',
  ]));

  c.push(H2('5.4. Research Limitations and Constraints'));
  c.push(...BUL([
    'The headline design has one test date. It is reported because it is the operational setting, but it supports description only, and every inferential claim here rests on the 30-origin design.',
    `Hyperparameters are selected on a validation block of only ten origins, which cannot separate four candidates reliably; on this configuration that selection is worse than using library defaults, by ${n(Math.abs(T.reverse_ablation[2].delta), 2)} per cent. Ten one-step errors are too few to choose among four candidates, so what the block selects is mostly noise, and the negative sign should be read as a statement about the block rather than about tuning. The validation length is a parameter of the released code and widening it costs time linearly — at sixty origins the tuning stage alone is roughly six times as long — so the question is answerable, and we report the reversal at ten rather than widening the block until the sign turns.`,
    'The panel has 15 series and each paired test rests on 1,350 points. That is enough to separate the leading learner from the classical methods and not enough to separate effects of one or two per cent, which is the size of every configuration effect reported in Section 4.3. Absence of significance there is a statement about the resolution of this study, not a demonstration that the components do nothing.',
    `The three leading methods are statistically indistinguishable, so the order within that group in Table 6 carries no weight. The ${T.champion_koreksi ? T.champion_koreksi.n_uji : 9} pairwise tests against the leading method are corrected for multiplicity by Holm-Bonferroni; the correction widens the tie group in principle but changes nothing here, because the two non-significant comparisons were already far from the threshold and the seven significant ones all survive.`,
    'Only one horizon is studied, and the panel comes from one jurisdiction and one reporting framework. Three features of that setting bound the results and each cuts in a specific direction. Under a managed float the central bank is itself a counterparty and its reaction is part of the data-generating process, so the flow-to-rate relationship this paper measures is partly a policy artefact rather than a pure market one. A shallow onshore market means a single large corporate settlement can move a daily cell, which raises the weight of counterparty composition — the thing being forecast — and inflates the tails that make the maximum-error columns move. And the administrative reporting framework fixes both the counterparty categories and the declared purposes, so the grid itself is an institutional choice, not a natural one. In a deep free-floating market with a different reporting taxonomy we would expect the disaggregation to buy less, the tails to be thinner, and the market-data question to be worth re-asking rather than settled by these numbers.',
    'Three reported cells are aggregates of two reporting categories each, as Section 3.2 sets out. That removes a degenerate cell but also removes the possibility of saying anything about foreign-investment corporates separately, which a supervisor may want.',
    `Reproducibility has two separate requirements, and we state both because they were diagnosed separately. The first is the thread count. ARIMA order selection is sensitive to floating-point summation order, and running the identical code and data with a different number of compute threads moved ${T.repro.arima_utas_berbeda.sel_bergeser} of the ${T.repro.arima_utas_berbeda.n_sel} ARIMA cells, shifting its pooled mean from ${n(T.repro.arima_utas_berbeda.mean_empat_utas, 4)} to ${n(T.repro.arima_utas_berbeda.mean_satu_utas, 4)}. No other method moved. This is not a random-seed problem — ARIMA draws no random numbers here — and it is fully removable: with threads pinned to one, two complete re-runs over ${T.repro.arima_utas.leaf.length} series and ${T.repro.arima_utas.n_origin} origins each were bit-identical, maximum absolute difference ${n(T.repro.arima_utas.beda_maks_absolut, 1)}. All results reported here were produced with threads pinned, and the code now pins them by default.`,
    `The second requirement is the library stack, and pinning threads does not substitute for it. The results were produced under Python ${T.versi.python}, NumPy ${T.versi.numpy}, pandas ${T.versi.pandas}, scikit-learn ${T.versi.sklearn}, LightGBM ${T.versi.lightgbm}, XGBoost ${T.versi.xgboost} and statsmodels ${T.versi.statsmodels}, recorded alongside them. Re-running the SHAP computation under a different stack reproduced ${T.repro.shap_lintas_lingkungan.n_leaf_cocok} of the ${T.repro.shap_lintas_lingkungan.n_leaf} series exactly and two only approximately: on ${T.repro.shap_lintas_lingkungan.leaf_berbeda[1]} the market share of importance came out ${n(T.repro.shap_lintas_lingkungan.ext_share_utas_terkunci, 1)} per cent against ${n(T.repro.shap_lintas_lingkungan.ext_share_mesin_komputasi, 1)} reported here. We checked whether that too was a thread effect; it is not — pinning and unpinning threads gave the same ${n(T.repro.shap_lintas_lingkungan.ext_share_utas_bebas, 1)} per cent — so the residual difference is the library versions themselves. Replication should pin the versions listed above.`,
    'The market-data correction in Section 4.2 supplies the market series at prediction time, which is valid at a one-day horizon because the required lags are already observed. It does not extend to multi-step recursive forecasting, where the future values of another series genuinely do not exist; a study at longer horizons would need either a direct multi-horizon formulation or forecasts of the market series themselves.',
  ]));

  /* -------------------------------------------- 6. Conclusion */
  c.push(H1('6. Conclusion and Future Work'));

  c.push(H2('6.1. Summary of Key Contributions'));
  c.push(...conclProse());

  c.push(H2('6.2. Policy and Practical Recommendations'));
  c.push(P('Beyond the five points above, a supervisory desk should be clear about what a single-date test can ' +
    'support. A ranking from one day describes that day; deployment decisions need repeated origins, and the ' +
    'feature count should be chosen by ablation on the institution own history rather than inherited.'));

  c.push(H2('6.3. Recommendations for Future Research'));
  c.push(...BUL([
    'Test market data at longer horizons, where their own future values must also be forecast, and measure how much of any gain survives that.',
    'Model the sparse cells with methods built for intermittent demand, scored with measures suited to them, and test whether sibling series help one day ahead, where yesterday value of every other cell is known.',
    'Widen the validation block used for hyperparameter selection and check whether the configurations chosen stop reversing sign on the test block. Ten origins was affordable, not sufficient.',
    'Score selection rules on tail behaviour rather than average error, to establish why redundancy-aware selection moves the mean without moving the paired test, and re-run the comparison with a formal tie-group procedure across all ten methods rather than pairwise tests against the leader.',
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
  c.push(P('Table A1 reports the headline design one series at a time: the actual value on 26 August 2026, ' +
    'the forecast from the best method for that series, and the scaled error.'));
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

function rankTable(rank) {
  const rows = rank.map((d, i) => [
    String(i + 1), nice(d.model), n(d.mase, 3), n(d.med, 3),
    d.model === 'Naive' ? 'benchmark' : (d.mase < 1 ? 'beats random walk' : ''),
  ]);
  return TBL([700, 3000, 1900, 1900, 1860],
    ['Rank', 'Method', 'Mean MASE', 'Median MASE', 'Note'], rows,
    { rightFrom: 2, accRows: [0] });
}

function tieGroupProse() {
  const r = e2rank, ct = T.champion_tests;
  const top = r[0];
  const ns = ct.filter(t => !t.sig);
  const sig = ct.filter(t => t.sig).sort((a, b) => a.p - b.p)[0];
  const first = ct.filter(t => t.sig).reduce((a, b) =>
    (e2rank.findIndex(x => x.model === a.model) < e2rank.findIndex(x => x.model === b.model) ? a : b));
  const out = [];
  out.push(P(`At optimal capacity the ranking question dissolves. ` +
    `${nice(top.model)} records the lowest mean MASE at ${n(top.mase, 3)}, the only method in the study ` +
    `to finish below the random-walk threshold on average, yet paired signed-rank tests separate it from ` +
    `neither of the next two: ` +
    ns.map(t => `${t.wins} of ${t.n} paired points against ${nice(t.model)} (p = ${n(t.p, 3)})`).join(', and ') + `. ` +
    (T.champion_koreksi
      ? `All ${T.champion_koreksi.n_uji} comparisons against the leading method are made on the same data, ` +
        `so they are corrected for multiplicity. Under Holm-Bonferroni the two above rise to ` +
        ns.map(t => `${n(t.p_holm, 3)}`).join(' and ') + `, further from significance rather than nearer, ` +
        `while the remaining ${T.champion_koreksi.signifikan_holm.length} all survive - the weakest, against ` +
        `${nice(T.champion_koreksi.signifikan_holm.find(m => m === 'Croston') || T.champion_koreksi.signifikan_holm[0])}, ` +
        `at ${n(T.champion_koreksi.holm_terbesar_yang_masih_signifikan, 4)}. ` +
        `The correction therefore costs the paper nothing: the tie group is a tie under a stricter rule, and ` +
        `every gap the uncorrected tests supported is still supported. `
      : '') +
    `Those are coin flips, so the three tree ensembles form one indistinguishable group. ` +
    `The first gap the data support is the one to ${nice(first.model)} ` +
    `(${first.wins} of ${first.n}, p = ${pv(first.p)}), and every method below it is separated as well. ` +
    `We therefore report a tie group rather than a winner.`));

  out.push(P(`The two summaries of central tendency disagree inside that group, and both are reported. ` +
    `${nice(top.model)} has the lowest mean at ${n(top.mase, 3)}; ${nice(r[1].model)} has the lowest ` +
    `median at ${n(r[1].med, 3)}. ` +
    `A mean rewards a method that avoids large misses, a median one that is accurate on the ordinary day. ` +
    `Choosing whichever favours a preferred conclusion would be an easy error to make silently, so the ` +
    `tables carry the mean, the median and the maximum side by side throughout.`));
  return out;
}

function winnersProse() {
  const w = T.winners;
  const cro = T.croston_leaves;
  const sp = T.sparsest;
  const sparse = w.filter(r => r.zero > 30);
  const spML = sparse.filter(r => r.fam === 'ML').length;
  const c = [];
  c.push(P(`The guess does not survive. Croston, the one method built for intermittent series, wins ` +
    cro.map(r => `${r.leaf} (${n(r.zero, 1)} per cent zero)`).join(', ') + `, ` +
    `none of which is sparse: its three wins sit between 0.5 and 7.1 per cent zero, while the six ` +
    `sparsest cells in the panel, from 18.6 to 38.4 per cent zero, all go to other methods - the ` +
    `sparsest of all, ${sp.leaf}, to ${nice(sp.best).toLowerCase()}. ` +
    `Across the panel ${sparse.length} series are zero on more than 30 per cent of days and machine ` +
    `learning wins ${spML} of them. ` +
    `Sparsity also fails to predict how hard a series is: the correlation between zero share and the best ` +
    `achievable error is ${n(T.winner_rho, 2)} (p = ${n(T.winner_p, 2)}).`));
  c.push(P(`So the winner is not chosen by any single summary statistic we measured. ` +
    `Zero share, autocorrelation and volatility clustering all fail to sort the panel into families. ` +
    `This is a negative result, and it strengthens the practical recommendation: if a rule of thumb could ` +
    `pick the method from the data profile, per-cell testing would be unnecessary. It cannot, so it is ` +
    `necessary. ` +
    `The best method for a cell does earn its keep: it beats the random walk on ${T.n_beat_rw} of the ` +
    `${T.n_leaf} series.`));
  return c;
}

function ablationTable() {
  const rows = abl.map(a => [
    String(a.k), n(a.mase, 3), n(a.median, 3), n(a.max, 1),
    a.k === 25 ? 'baseline' : pct(a.delta), a.k === 25 ? '—' : `${a.wins} / ${a.n}`, pv(a.p),
  ]);
  return TBL([1100, 1420, 1420, 1160, 1700, 1420, 1140],
    ['Features (k)', 'Mean MASE', 'Median MASE', 'Max MASE', 'Change in mean', 'Wins vs k = 25', 'Wilcoxon p'],
    rows, { rightFrom: 1, accRows: [abl.findIndex(a => a.k === bestK)] });
}

function ablationProse() {
  const a = abl, b = a.find(r => r.k === 25), best = a.find(r => r.k === bestK);
  const sig = a.filter(r => r.p !== null && r.p !== undefined && r.p < 0.05);
  const k6 = a.find(r => r.k === 6);
  const c = [];
  c.push(P(`The answer is a null, and this time it points the other way. ` +
    `The best count is the largest tested: ${bestK} features, at ${n(b.mase, 4)}. ` +
    `Every tighter setting is worse in the mean, by between ${n(Math.min(...a.filter(r => r.k !== 25).map(r => r.delta)), 2)} ` +
    `and ${n(Math.max(...a.map(r => r.delta)), 2)} per cent, and only ` +
    sig.map(r => `k = ${r.k} (p = ${n(r.p, 4)})`).join(' and ') +
    ` is separated from the baseline by a paired test. ` +
    `Cutting the feature count buys nothing here, and the case for cutting it rests on a saving in ` +
    `computation rather than on accuracy.`));
  c.push(P(`The right panel of Figure 5 is as flat as the left. ` +
    `The worst scaled error at ${k6.k} features is ${n(k6.max, 1)}, against ${n(b.max, 1)} at ${b.k}, and ` +
    `across all six counts it moves only between ` +
    `${n(Math.min(...a.map(r => r.max)), 1)} and ${n(Math.max(...a.map(r => r.max)), 1)} - with the peak ` +
    `at ${a.reduce((x, y) => x.max > y.max ? x : y).k} features, a loose count rather than a tight one. ` +
    `A tail penalty for tight feature counts is easy to produce on a panel that contains a near-empty ` +
    `cell, because a single series with almost no signal dominates the maximum. ` +
    `On a panel without one, the penalty does not appear, which is a useful warning about how sensitive ` +
    `worst-case statistics are to the composition of the panel they are computed on.`));
  return c;
}

function externalProse() {
  const E = T.external_full;
  const worst = E.reduce((m, r) => r.delta > m.delta ? r : m, E[0]);
  const best = E.reduce((m, r) => r.delta < m.delta ? r : m, E[0]);
  const c = [];
  c.push(P(`Both summaries of the same ${E[0].n.toLocaleString('en-US')} paired forecasts agree. ` +
    `Switching market data on raises mean error in all four cells, by between ` +
    `${n(best.delta, 1)} and ${n(worst.delta, 1)} per cent, and it also loses on the count of days: ` +
    `outside tied days the no-market arm is the better forecast on between ` +
    `${n(Math.min(...E.map(r => r.pct_off)), 1)} and ${n(Math.max(...E.map(r => r.pct_off)), 1)} per cent ` +
    `of them. ` +
    `Tied days are numerous and must be excluded: where the selector gives a series no market slot the two ` +
    `arms are the same model, and at the tightest cell ${n(100 * E[0].ties / E[0].n, 0)} per cent of pairs ` +
    `are identical. Counting those as evidence would make the losing arm appear to win.`));
  c.push(P(`Taken alone this looks like a clean verdict against market data, and in the first version of ` +
    `this analysis that is how we read it. It is wrong, and the next subsection shows why: the models were ` +
    `trained on market features and then asked to predict without them. ` +
    `The subsection that follows separates the two explanations and finds that most of the penalty above ` +
    `belongs to the handling rather than to the data.`));
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
  c.push(P(`Table 8 breaks the same test down by series, under the configuration used throughout: ` +
    `${T.n_lags} lags, redundancy-aware selection, market data switched on and off. ` +
    `Columns three to five keep 12 features, columns six to eight keep 25. ` +
    `"FE only" holds just the engineered candidates; "FE + market" adds the eight market variables, each at ` +
    `lags 1 to 14 plus a seven-day mean, to the same engineered pool, so all ${T.pool_total} candidates ` +
    `compete for the same slots.`));
  c.push(P(`How much of the panel is exposed depends sharply on the feature count. ` +
    `At 12 features only ${act12.length} of ${N} series admit any market feature at all and the rest are ` +
    `unchanged, as they must be; of those affected, ${w12} get worse and ${b12} better. ` +
    `At 25 features the exposure is nearly universal: ${act25.length} of ${N} admit at least one, ` +
    `${w25} series get worse and ${b25} better. ` +
    `The worst is ${worst.leaf} (${LABEL[worst.leaf]}) at ${n(worst.delta, 1)} per cent and the best ` +
    `${best.leaf} (${LABEL[best.leaf]}) at ${n(best.delta, 1)}.`));
  c.push(P(`The damage tracks exposure closely. Across the ${sp.n} affected series at 25 features the rank ` +
    `correlation between market slots and the penalty is ${n(sp.rho, 2)} ` +
    `(p = ${n(sp.p, 3)}): the more slots a series gives the market variables, the more it loses. ` +
    `That is a strong clue, and not the one it first appears to be. ` +
    `A genuinely uninformative predictor would dilute a model roughly in proportion to how much of it was ` +
    `admitted, but so would a predictor that was informative at training and then withheld at prediction. ` +
    `The next subsection distinguishes the two.`));
  c.push(NOTE('Zero market slots does not guarantee zero market effect. ' +
    'The redundancy-aware criterion is run over the 3k candidates ranked highest on raw relevance, so a ' +
    'market variable that outranks an engineered feature on correlation alone can displace it from that ' +
    'shortlist without ever being selected itself. ' +
    'The "Market slots" column is therefore a lower bound on exposure.'));
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
  const worstRec = cells.reduce((a, b) => (a.rusak_hilang_pct < b.rusak_hilang_pct ? a : b));
  const c = [];
  c.push(P(`The comparison above has a flaw, and it is ours rather than the data's. ` +
    `The recursive forecasters build their features afresh at prediction time, and the routine that does so ` +
    `had no way to accept the market series. Every market feature the model had been trained on was therefore ` +
    `absent when the forecast was made, and silently filled with zero. ` +
    `For a recursive multi-step forecast that is unavoidable: the future values of another series do not ` +
    `exist. But this paper forecasts one day ahead, and one day ahead the market variables at lags one to ` +
    `fourteen are all known — yesterday's exchange rate is on the screen when today's forecast is made. ` +
    `The arm labelled "market on" in Table 8 was thus trained on information it was then denied.`));
  c.push(P(`We repeated the comparison with the market series supplied at prediction as well as at training. ` +
    `Nothing else changed: the same selector, the same feature counts, the same origins, the same fitted ` +
    `hyperparameters. Pooled over all ${g.n.toLocaleString('en-US')} paired forecasts the penalty against the ` +
    `no-market baseline falls from ${n(g.delta_nol, 1)} per cent to ${n(g.delta_benar, 1)} per cent. ` +
    `${n(g.rusak_hilang_pct, 0)} per cent of the reported loss was an artefact of the zero-fill ` +
    `(p = ${pv(g.p_vs_nol)} against the zero-filled arm).`));
  c.push(P(`What survives is smaller and still real. Market data remain worse than no market data by ` +
    `${n(g.delta_benar, 1)} per cent (p = ${pv(g.p_vs_mati)}), significantly so in ${sig} of the four cells, ` +
    `and outside tied days they are the better forecast on only ${n(g.pct_benar, 1)} per cent of them. ` +
    `The recovery is uneven: three cells shed ${n(Math.min(...cells.filter(r => r !== worstRec).map(r => r.rusak_hilang_pct)), 0)} ` +
    `per cent or more of the penalty, while the ${worstRec.beta === 0 ? 'univariate' : 'mRMR'} rule at ` +
    `${worstRec.k} features sheds only ${n(worstRec.rusak_hilang_pct, 0)} per cent. ` +
    `We have no evidence-backed explanation for that cell and record it as it stands.`));
  c.push(P(`The per-series picture is likewise mixed rather than uniformly negative. ` +
    `Once the features are supplied, ${T.n_leaf_membaik} of the ${T.n_leaf} series are more accurate with ` +
    `market data than without, ${T.n_leaf_memburuk} are worse, and ${T.n_leaf_tanpa_slot} admit no market ` +
    `feature at all and are therefore unchanged by construction. ` +
    `The honest summary is that market data neither help nor hurt uniformly here; on average they cost a ` +
    `little, and which series they help is not something this study can predict in advance.`));
  return c;
}

function slotDamageProse() {
  const A = T.slot_damage;
  const c = [];
  c.push(P(`Figure 8 identifies the mechanism. With the market features zero-filled, the penalty a series ` +
    `suffers rises with the number of slots the selector gave them: the rank correlation across the ` +
    `${A.n} series is ${n(A.nol.rho, 3)} (p = ${n(A.nol.p, 3)}). ` +
    `That is exactly what a withheld-at-prediction feature predicts — the more of the model that is blanked ` +
    `at forecast time, the worse the forecast. ` +
    `Once the same features are supplied, the relationship vanishes: ${n(A.benar.rho, 3)} ` +
    `(p = ${n(A.benar.p, 3)}), no longer distinguishable from no relationship at all.`));
  c.push(P(`The two series that give market variables no slot at all anchor the reading. ` +
    `They are unchanged across all three arms, as they must be, and they sit at the origin of both panels. ` +
    `A dilution story — market data are simply uninformative and crowd out better features — would survive ` +
    `the correction, because the crowding out happens at selection time and is untouched by what is supplied ` +
    `at prediction. It does not survive. The zero-fill, not the market data, produced three quarters of the ` +
    `loss originally reported.`));
  return c;
}

function famProse() {
  const ks = famKeys;
  const extShareAvg = fam['External'] ?? 0;
  const sorted = [...extShare].sort((a, b) => b.share - a.share);
  const nZero = extShare.filter(r => r.share < 1).length;
  const c = [];
  c.push(P(`Pooling across all ${T.n_leaf} series gives the same message. ` +
    `${ks[0]} features carry ${n(fam[ks[0]], 1)} per cent of all feature importance and ${ks[1]} features ` +
    `${n(fam[ks[1]], 1)} per cent, while market data carry ${n(extShareAvg, 1)} per cent on average. ` +
    `The right panel of Figure 9 shows how uneven that is: the market share reaches ${n(sorted[0].share, 1)} ` +
    `per cent on ${sorted[0].leaf} (${LABEL[sorted[0].leaf]}) and is under one per cent on ${nZero} of ` +
    `${T.n_leaf} series. ` +
    `H4 is supported - the model draws its signal from the series own history - and the three series where ` +
    `market data take the largest share are all series that market data make worse.`));
  c.push(P(`The lag pool is used rather than merely offered. ` +
    `Lags take ${n(T.mean_lag_slots, 1)} of the 25 slots on average and carry ${n(fam['Lag'], 1)} per cent ` +
    `of importance, while market variables take ${n(T.mean_ext_slots, 1)}. ` +
    `The redundancy-aware rule is what keeps that ratio: on the same pool it admits ` +
    `${n(T.slot_uptake_new.k25_mrmr, 2)} market features on average against ` +
    `${n(T.slot_uptake_new.k25_univ, 2)} under the univariate rule. ` +
    `It halves the market variables' foothold, and the ones it keeps still carry little.`));
  return c;
}

function reverseAblationTable() {
  const rows = T.reverse_ablation.map(a => [
    a.component, n(a.opt, 4), n(a.off, 4), pct(a.delta),
    `${a.wins} / ${a.n}`, pv(a.p),
    a.sig ? 'significant' : 'not significant',
  ]);
  return TBL([2560, 1340, 1440, 1180, 1340, 1120, 1380],
    ['Component removed', 'Mean MASE with it', 'Mean MASE without it',
     'Change', 'Wins for optimal', 'Wilcoxon p', 'Verdict'],
    rows, { rightFrom: 1, accRows: [T.reverse_ablation.findIndex(a => a.sig)] });
}

function reverseAblationProse() {
  const R = Object.fromEntries(T.reverse_ablation.map(a => [a.component, a]));
  const bm = T.reverse_by_model, lw = T.reverse_leaf_worse;
  const sel = R['Redundancy-aware selection'], ref = R['Daily re-fitting'],
        tun = R['Tuned hyperparameters'];
  const out = [];

  out.push(P(`Not one of the three earns its place on this panel. ` +
    `Daily re-fitting is worth ${pct(ref.delta)} and comes closest to significance without reaching it ` +
    `(p = ${n(ref.p, 4)}). ` +
    `Redundancy-aware selection is worth ${pct(sel.delta)}, which is indistinguishable from nothing ` +
    `(p = ${n(sel.p, 3)}). ` +
    `Tuned hyperparameters carry the wrong sign: switching them off makes the pooled result ` +
    `${Math.abs(tun.delta).toFixed(2)} per cent better.`));

  out.push(P(`The per-model breakdown shows why the pooled figures are so small. ` +
    `The three components do not agree across learners. ` +
    `Daily re-fitting is worth ${bm['Daily re-fitting'][0].toFixed(2)} per cent to LightGBM and ` +
    `${bm['Daily re-fitting'][2].toFixed(2)} to XGBoost; redundancy-aware selection helps random forest ` +
    `(${bm['Redundancy-aware selection'][1].toFixed(2)} per cent) and hurts XGBoost ` +
    `(${bm['Redundancy-aware selection'][2].toFixed(2)}); tuning helps only random forest. ` +
    `Every component is positive for at least one learner and negative for at least one other, so the ` +
    `pooled mean is a cancellation rather than a consensus.`));

  out.push(P(`Counting series makes the same point. ` +
    `Daily re-fitting helps ${T.n_leaf - lw['Daily re-fitting']} of the ${T.n_leaf} series, ` +
    `redundancy-aware selection ${T.n_leaf - lw['Redundancy-aware selection']}, and tuning ` +
    `${T.n_leaf - lw['Tuned hyperparameters']}. ` +
    `Only one of the three is on the right side of a tie, and by a single series. ` +
    `Each is a bet that pays on some cells and costs on others - the same heterogeneity the model ` +
    `comparison shows, one level down.`));

  out.push(P(`The honest reading is that a pipeline assembled from defensible choices is, on a panel this ` +
    `size, indistinguishable from a simpler one. ` +
    `That is not an argument for abandoning the choices: daily re-fitting costs seconds and points the ` +
    `right way for two of three learners, and redundancy-aware selection is what keeps a wide lag pool ` +
    `usable. ` +
    `It is an argument against reporting any of them as a demonstrated improvement, which is what an ` +
    `applied literature reporting only the assembled system would invite a reader to assume.`));
  return out;
}

function selectorProse() {
  const S = T.selector_tests;
  const c = [];
  c.push(P(`The redundancy-aware rule is better than the univariate one at both feature counts, and at ` +
    `neither does the difference reach significance. ` +
    S.map(r => `At k = ${r.k} it lowers mean error by ${Math.abs(r.delta).toFixed(2)} per cent and wins ` +
      `${r.wins} of ${r.n} paired points (p = ${n(r.p, 3)})`).join('. ') + `. ` +
    `Mean and count agree on the direction; the test declines to call it.`));
  c.push(P(`Replacing the selector does not rescue market data either. ` +
    `Under the univariate rule at 25 features they cost ` +
    `${n(T.external_full.find(e => e.beta === 0 && e.k === 25).delta, 1)} per cent in the mean; under the ` +
    `redundancy-aware rule they cost ` +
    `${n(T.external_full.find(e => e.beta === 1 && e.k === 25).delta, 1)} per cent. ` +
    `The selector was the weaker of the two rules and the market variables carry little short-horizon ` +
    `signal; these are separate facts, and correcting the first does not address the second.`));
  return c;
}

function synthProse() {
  const c = [];
  c.push(P('The findings connect, and together they point away from the model-choice question that usually ' +
    'dominates applied work - and, more awkwardly, away from most of the engineering questions too.'));
  c.push(P(`The first is that many methods win, not one. ` +
    `Eight of the ten are best on at least one series and none on more than ${bestCount[0][1]} of ` +
    `${T.n_leaf}, and no summary statistic we measured predicts which. ` +
    `At the aggregate level the three tree ensembles are separated by less than five per cent and by no ` +
    `test. An applied literature that reports a best learner on a single panel is reporting something ` +
    `this fragile, usually without the tests that would reveal it.`));
  c.push(P('The second is that the configuration around the learner matters even less than the learner. ' +
    'Redundancy-aware selection, daily re-fitting and hyperparameter tuning together define the ' +
    'configuration this paper reports, and removing any one of them moves the pooled mean by at most one ' +
    'per cent, in a direction that differs by learner, with no paired test reaching significance. ' +
    'The feature count behaves the same way: no setting between 6 and 20 features beats the usual 25. ' +
    'These are null results, and they are reported as such rather than dressed as a tuned pipeline.'));
  c.push(P('The third is that market data are the exception, and that how you summarise them decides what ' +
    'you conclude. ' +
    'They raise mean error in every condition tested and lower it on most individual days in three ' +
    'conditions out of four, and both statements come from the same paired forecasts. ' +
    'The loss is concentrated in a minority of days rather than spread across them, which is exactly what ' +
    'a summary based on averages will exaggerate and one based on counts will hide.'));
  c.push(P('One mechanism ties these together: competition for a fixed number of slots. ' +
    'Selection ranks candidates by correlation with the level, which rewards anything that tracks the ' +
    'level whether or not it says anything about tomorrow change. ' +
    'A long moving average tracks the level. So does an exchange rate. So does an equity index. ' +
    'The competition begins before the final slots are allocated, since the redundancy-aware criterion is ' +
    'run over a shortlist ranked on raw relevance, so a market variable can displace an engineered feature ' +
    'without ever being selected itself. ' +
    'One day ahead the useful features are few and specific, and everything else is competition for the ' +
    'space they need.'));
  c.push(P('Taken together these results describe a problem with a low ceiling. ' +
    'The predictable part of a one-day flow is small, the recent lags capture most of it, and effort spent ' +
    'on the machinery around them returns little. ' +
    'That is a more useful thing for a supervisory desk to know than a ranking it cannot reproduce.'));
  return c;
}

function conclProse() {
  const c = [];
  c.push(P(`We forecast ${T.n_leaf} disaggregated foreign-exchange flow series one business day ahead, the ` +
    'unit being the counterparty and purpose cell, which is where the supervisory question is asked. ' +
    'Ten methods were compared, deep-learning models were left out, and all values are in millions of US ' +
    'dollars.'));
  c.push(P(`Four contributions follow. No method dominates: eight are best on at least one series, none on ` +
    `more than ${bestCount[0][1]}, and at the aggregate level the three leading learners are ` +
    `statistically indistinguishable, so reporting a best learner from a panel this size is reporting a ` +
    `design choice. ` +
    `Nor does the configuration around the learner earn its place - selection rule, daily re-fitting and ` +
    `hyperparameter tuning each move the pooled mean by at most one per cent, disagree across learners, ` +
    `and survive no paired test - and the feature count is a null in the same way. ` +
    `Market data are the one choice with a decisive effect, and the fourth contribution is that most of ` +
    `that effect turned out to be ours rather than the data's: training on market features and then ` +
    `withholding them at prediction - the default of a recursive forecaster - accounted for ` +
    `${n(T.tabel8b_gabungan.rusak_hilang_pct, 0)} per cent of an apparent ` +
    `${n(T.tabel8b_gabungan.delta_nol, 1)} per cent penalty, which falls to ` +
    `${n(T.tabel8b_gabungan.delta_benar, 1)} per cent once the features are supplied at a horizon where ` +
    `they are already observed. ` +
    `And SHAP confirms where the signal is: lags and moving averages carry ` +
    `${n((fam['Lag'] || 0) + (fam['Moving average'] || 0), 0)} per cent of feature importance between ` +
    `them, market data ${n(fam['External'] ?? 0, 1)} per cent.`));
  c.push(P('The broader point is methodological. ' +
    'A pipeline assembled from individually defensible choices can be, on a panel of this size, ' +
    'indistinguishable from a simpler one - and the only way to learn that is to remove the choices one at ' +
    'a time and test the difference on paired forecasts. ' +
    'Reporting the assembled system alone would have implied an improvement the data do not support.'));
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
    'It cannot show direction. The beeswarms below can: each dot is one of the last 300 training days, ' +
    'placed by that feature contribution to the predicted next-day flow in millions of US dollars, and ' +
    'coloured by whether the feature value was low (blue) or high (red) that day. ' +
    'Feature names in orange are market variables; names in black are engineered from the series own ' +
    'history. A wide spread means the feature moves the forecast from day to day; a narrow band around ' +
    'zero means it is carried in the model and does almost nothing.'));
  c.push(NOTE('These are the fourteen highest-importance features of the 25 selected, ordered by mean ' +
    'absolute SHAP value. A series can therefore show fewer market rows here than its market slot count ' +
    'in Figure 9, which means the remaining market features rank below the fourteenth.'));
  ada.forEach((l, i) => {
    const v = T.shap_per_leaf[l];
    c.push(IMG('beeswarm' + path.sep + l + '.png', 520, 282));
    c.push(FCAP(`B${i + 1}`, `${l} (${LABEL[l]}, ${ACTOROF(l)}). ` +
      `The selector kept ${v.n_ext} market features and ${v.n_lag} own lags of 25; ` +
      `market variables carry ${n(share[l] ?? 0, 1)} per cent of total absolute SHAP value.`));
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
    'Bergmeir, C. and Benítez, J. M. (2012). On the use of cross-validation for time series predictor evaluation. *Information Sciences*, 191, 192–213.',
    'Breiman, L. (2001). Random forests. *Machine Learning*, 45(1), 5–32.',
    'Chen, T. and Guestrin, C. (2016). XGBoost: a scalable tree boosting system. In *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery and Data Mining*, 785–794.',
    'Croston, J. D. (1972). Forecasting and stock control for intermittent demands. *Operational Research Quarterly*, 23(3), 289–303.',
    'Evans, M. D. D. and Lyons, R. K. (2002). Order flow and exchange rate dynamics. *Journal of Political Economy*, 110(1), 170–180.',
    'Guyon, I. and Elisseeff, A. (2003). An introduction to variable and feature selection. *Journal of Machine Learning Research*, 3, 1157–1182.',
    'Hastie, T., Tibshirani, R. and Friedman, J. (2009). *The Elements of Statistical Learning*, 2nd edition. New York: Springer.',
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
Packer.toBuffer(doc).then(b => { fs.writeFileSync(OUTF, b); console.log('ditulis:', OUTF, (b.length / 1024).toFixed(0) + ' KB'); });
