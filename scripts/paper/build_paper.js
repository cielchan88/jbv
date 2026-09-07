/*
 * Susun ulang makalah ke kerangka bagian standar (Abstract berlabel, IMRaD
 * lengkap dengan Literature Review, Ethical Considerations, dan Conclusion +
 * Future Work).
 *
 * Isi diambil dari doc_items.json - hasil bongkar DOCX sebelumnya - sehingga
 * seluruh teks, penekanan, tabel, dan gambar terbawa apa adanya. Yang berubah
 * hanyalah urutan bagian, penomoran tabel/gambar, dan bagian-bagian baru yang
 * dituntut kerangka.
 *
 * Penomoran tabel dipetakan lewat TMAP, dan setiap rujukan silang dalam teks
 * lama ditulis ulang otomatis - jangan mengganti nomor secara manual.
 */
const fs = require('fs');
const d = require('docx');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  ImageRun, PageBreak
} = d;

const path = require('path');
// Pemakaian: node build_paper.js [dir-kerja] [keluaran.docx]
// dir-kerja adalah direktori yang berisi doc_items.json dan fig/, yaitu keluaran
// extract.py. Default: direktori kerja saat ini.
const S = path.resolve(process.argv[2] || '.');
const OUT = process.argv[3] || path.join(S, 'paper.docx');
const IT = JSON.parse(fs.readFileSync(path.join(S, 'doc_items.json'), 'utf8'));
const SERIF = 'Times New Roman';
const CW = 9026;

// ---------- penomoran ----------
// lama -> baru, mengikuti urutan kemunculan pada kerangka baru
const TMAP = { 1: 5, 2: 6, 3: 7, 4: 8, 5: 3, 6: 4, 7: 9, 8: 10, 9: 11, 10: 13, 11: 1, 12: 12, 13: 14 };
const T = {                       // nomor tabel BARU, dipakai teks yang ditulis ulang
  parallels: 1, hypo: 2, protocols: 3, windows: 4, desc: 5, trainfit: 6,
  diag: 7, featfam: 8, protomase: 9, horizon: 10, allten: 11, robust: 12,
  channels: 13, threats: 14, followup: 15
};
const PHRASE = [
  ['Figure 2(a)', 'Figure 3(a)'],
  ['Section 7 reports the full set of checks', 'Section 4.3 reports the full set of checks'],
  ['Section 7 answers the second', 'Section 4.3 answers the second'],
  ['Because Section 4.4 established', 'Because the evidence on H1 established'],
  ['documented in Section 2', 'documented in Section 3.2'],
  ['reported in Section 5.4', 'reported in Section 4.2'],
  ['Section 5.5 returns to the full set of methods', 'the closing part of Section 4.2 returns to the full set of methods'],
  ['Section 4.5 shows that the ensembles', 'The evidence on H4 in Section 4.2 shows that the ensembles'],
  ['rebuilt around the finding of Section 4.5', 'rebuilt around the finding on H4 in Section 4.2'],
  ['the impurity and gain measures used in Section 4.5', 'the impurity and gain measures used in Section 4.2'],
  ['identified in Section 6.2', 'identified in Section 5.1'],
  ['Section 7 sets out the limitations in full, together with the robustness checks behind the Stage I claim',
   'Section 5.4 sets out the limitations in full, and Section 4.3 the robustness checks behind the Stage I claim'],
  ['common horizon grid of Section 5.2', 'common horizon grid of Section 3.3'],
  // pointer ke objek yang sebelumnya tak dirujuk di badan teks
  ['Beyond h = 30 they separate sharply: 2.167 against 1.681, a penalty of 29 per cent.',
   'Beyond h = 30 they separate sharply: 2.167 against 1.681, a penalty of 29 per cent. Table 10 sets out the two horizon segments in full.'],
  ['Three results follow, and the first is a corrective.',
   'Three results follow, summarised in Figure 2; the first is a corrective.'],
  ['which is the configuration in which the system is operated.',
   'which is the configuration in which the system is operated, and Figure 4 presents the same ranking graphically.'],
  ['so that a positive value indicates that recursion is the less accurate of the two valid protocols.',
   'so that a positive value indicates that recursion is the less accurate of the two valid protocols. Figure A1 plots the same comparison.'],
  // Sisi KIRI PHRASE tidak boleh memuat nomor tabel lama karena regex sudah berjalan lebih dulu;
  // "described in Table 6 below" ditangani regex (6 -> 4) dan tetap "below".
  ['We estimate nine methods, grouped into two families',
   'We estimate ten methods, grouped into two families'],
  ['three tree ensembles — bagged regression trees and two gradient-boosting implementations — estimated on ninety engineered features from which twenty-five are retained by absolute Spearman correlation with the target',
   'three tree ensembles — bagged regression trees and two gradient-boosting implementations — estimated on ninety engineered features from which twenty-five are retained by absolute Spearman correlation with the target, together with a stacked ensemble combining them']
];
function fix(t) {
  // Urutan penting: petakan nomor tabel lama -> baru dulu, baru ganti frasa.
  // Dengan begitu sisi kanan PHRASE boleh menyebut nomor tabel versi BARU.
  t = t.replace(/\bTable (\d+)\b/g, (m, n) => 'Table ' + (TMAP[+n] || n));
  for (const [a, b] of PHRASE) t = t.split(a).join(b);
  return t;
}

// ---------- pembentuk ----------
function P(t, o = {}) {
  return new Paragraph({ alignment: o.align || AlignmentType.JUSTIFIED,
    spacing: { after: o.after === undefined ? 140 : o.after, line: 300 },
    children: [new TextRun({ text: t, font: SERIF, size: o.size || 22, bold: o.bold, italics: o.italics })] });
}
function Rich(runs, o = {}) {
  return new Paragraph({ alignment: o.align || AlignmentType.JUSTIFIED,
    spacing: { after: o.after === undefined ? 140 : o.after, line: 300 },
    children: runs.map(r => new TextRun({ text: r.t, font: SERIF, size: r.size || 22, bold: r.b, italics: r.i })) });
}
function H(t, lvl) {
  return new Paragraph({ heading: lvl, spacing: { before: 260, after: 130 },
    children: [new TextRun({ text: t, font: SERIF, bold: true,
      size: lvl === HeadingLevel.HEADING_1 ? 26 : 23, color: '1a1a1a' })] });
}
function cap(label, t, o = {}) {
  return new Paragraph({ alignment: AlignmentType.LEFT,
    spacing: { before: o.before === undefined ? 60 : o.before, after: o.after === undefined ? 180 : o.after, line: 240 },
    children: [new TextRun({ text: label + ' ', font: SERIF, size: 19, bold: true }),
               new TextRun({ text: fix(t), font: SERIF, size: 19 })] });
}
function cell(t, w, o = {}) {
  return new TableCell({ width: { size: w, type: WidthType.DXA },
    shading: o.head ? { type: ShadingType.CLEAR, fill: 'ECEFF3', color: 'auto' } : undefined,
    margins: { top: 40, bottom: 40, left: 70, right: 70 },
    children: [new Paragraph({ alignment: o.num ? AlignmentType.RIGHT : AlignmentType.LEFT,
      spacing: { after: 0, line: 230 },
      children: [new TextRun({ text: String(t), font: SERIF, size: 17, bold: o.head || o.bold })] })] });
}
function table(widths, rows) {
  return new Table({ columnWidths: widths, width: { size: CW, type: WidthType.DXA },
    borders: { top: { style: BorderStyle.SINGLE, size: 6, color: '444444' },
      bottom: { style: BorderStyle.SINGLE, size: 6, color: '444444' },
      left: { style: BorderStyle.NONE }, right: { style: BorderStyle.NONE },
      insideVertical: { style: BorderStyle.NONE },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: 'CCCCCC' } }, rows });
}
function ref(t) {
  return new Paragraph({ spacing: { after: 100, line: 240 }, indent: { left: 420, hanging: 420 },
    children: [new TextRun({ text: t, font: SERIF, size: 20 })] });
}

// ---------- ambil dari dokumen lama ----------
const NUMRE = /^-?[\d.,+%×]+$|^[+-]?\d/;
function p(i) {                                   // paragraf, penekanan dipertahankan
  const x = IT[i];
  if (x.k !== 'p') throw new Error(`item ${i} bukan paragraf`);
  const runs = (x.runs.length ? x.runs : [{ t: x.text }]);
  return new Paragraph({ alignment: AlignmentType.JUSTIFIED,
    spacing: { after: 140, line: 300 },
    children: runs.map(r => new TextRun({ text: fix(r.t), font: SERIF,
      size: r.sz || 22, bold: r.b, italics: r.i })) });
}
function note(i) {                                // paragraf "Note. ..." di bawah tabel
  const x = IT[i];
  const t = fix(x.text);
  const m = t.match(/^(Note\.)\s*([\s\S]*)$/);
  return cap(m ? m[1] : 'Note.', m ? m[2] : t);
}
function capOf(i, label) {                        // caption tabel/gambar dari item lama
  const t = fix(IT[i].text);
  const m = t.match(/^((?:Table|Figure) [A-Z]?\d+\.)\s*([\s\S]*)$/);
  return cap(label, m ? m[2] : t, { before: label.startsWith('Table') ? 160 : 60,
                                    after: label.startsWith('Table') ? 60 : 180 });
}
function tb(i) {                                  // tabel utuh
  const x = IT[i];
  if (x.k !== 'tbl') throw new Error(`item ${i} bukan tabel`);
  const w = x.widths.length ? x.widths : new Array(x.rows[0].length).fill(Math.floor(CW / x.rows[0].length));
  const rows = x.rows.map((r, ri) => new TableRow({
    tableHeader: ri === 0,
    children: r.map((c, ci) => cell(fix(c.t), w[ci] || w[w.length - 1],
      { head: ri === 0, bold: ri > 0 && c.b, num: ri > 0 && NUMRE.test(c.t.trim()) && c.t.trim().length < 12 }))
  }));
  return table(w, rows);
}
function im(i) {                                  // gambar
  const x = IT[i];
  return new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 },
    children: [new ImageRun({ data: fs.readFileSync(path.join(S, 'fig', x.file)), type: 'png',
      transformation: { width: x.w, height: x.h } })] });
}
const lead = t => new Paragraph({ spacing: { before: 200, after: 90, line: 300 },
  children: [new TextRun({ text: t, font: SERIF, size: 22, bold: true })] });

const b = [];

// ============ JUDUL ============
b.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 120 },
  children: [new TextRun({ text: IT[0].text, font: SERIF, size: 30, bold: true })] }));
b.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 300 },
  children: [new TextRun({ text: 'This version: ' + new Date().toISOString().slice(0, 10),
    font: SERIF, size: 20, italics: true })] }));

// ============ ABSTRACT ============
b.push(H('Abstract', HeadingLevel.HEADING_1));
const AB = [
  ['Background. ', 'Institutions that operate short-horizon forecasting systems make two decisions that are usually treated as separate: which model to estimate, and how a model fitted to one-step-ahead relationships should be used to forecast many steps ahead. Applied practice devotes most of its attention to the first. It also routinely selects among candidate models on training-stage output, and routinely evaluates lag-based learners by feeding them realised test-period values at each step — a procedure that is not a forecasting strategy at all.'],
  ['Objectives. ', 'This paper asks four questions. Does training fit predict forecast accuracy in this class of data, and if so with what sign? How much of the apparent accuracy penalty of recursive forecasting is genuine error accumulation and how much is information leakage from teacher-forced evaluation? Where along the forecast horizon does the penalty arise? And what do the machine-learning models actually use out of an engineered feature set?'],
  ['Methodology. ', 'We evaluate ten methods — six traditional and four machine-learning — on 18 daily foreign-exchange transaction-flow series observed over 5032 business days (2 January 2006 to 26 August 2026), using rolling-origin validation with three windows anchored on the final observation. The design has two stages that are reported separately. Stage I estimates every model and records in-sample fit, residual diagnostics and feature importance. Stage II tests each model out of sample under three multi-step protocols — recursive, direct and teacher-forced — on a common twelve-point horizon grid, so that the protocols differ in nothing but the way the multi-step forecast is formed. Accuracy is measured by MASE; inference uses Diebold–Mariano tests with the Harvey–Leybourne–Newbold correction, paired Wilcoxon tests, and exact permutation tests.'],
  ['Findings. ', 'Training fit is not merely uninformative for model selection but systematically misleading. The model that fits the training sample best (RandomForest, in-sample MASE 0.611) is the worst out of sample (2.195), while the worst-fitting model (Prophet, 1.037) is the best (1.441). Once the random walk is set aside — its in-sample MASE equals unity by construction — the reversal of the two rankings is exact (Spearman ρ = -1.000, exact permutation p = 0.00139), and within-series rank correlations between training fit and test accuracy are negative in 40 of 54 series-window units (Wilcoxon p = 0.0010). On the protocol question, mean MASE is 1.403 under teacher-forcing, 1.505 under the direct strategy and 1.657 under recursion: of the 18.1 per cent apparent penalty of recursion, 10.1 percentage points are genuine error accumulation and 7.3 points are information leakage. The penalty is negligible to h = 23 and reaches 29 per cent beyond h = 30. The ensembles concentrate 55 to 73 per cent of their importance on five of twenty-five retained features, and importance is mildly negatively correlated with the criterion used to select those features.'],
  ['Significance and conclusion. ', 'Within this regime the protocol decision moves measured accuracy by an amount comparable to the model decision, and the training stage provides no guidance on either. Three operational rules follow: do not select models on training-stage metrics; evaluate under the protocol in which the system will be operated, treating teacher-forced results as diagnostic bounds; and estimate horizon-specific models where the operational horizon exceeds roughly one trading month. The paper also reports, and withdraws, a summary statistic used in an earlier version of this work whose null distribution we had not examined — a failure of the same kind the paper documents in model selection — and specifies four follow-up studies, each with a stated falsification criterion, so that the interpretation offered here can be tested rather than accepted.']
];
AB.forEach(a => b.push(Rich([{ t: a[0], b: true }, { t: a[1] }])));
b.push(p(4));
b.push(p(5));

// ============ 1. INTRODUCTION ============
b.push(H('1. Introduction', HeadingLevel.HEADING_1));
b.push(H('1.1 Background and Context', HeadingLevel.HEADING_2));
b.push(p(7));
b.push(P('The setting is an operational forecasting system of a kind maintained by many central banks and supervisory authorities: daily net foreign-exchange transaction flows, disaggregated by counterparty group and transaction purpose, forecast at horizons from one day to one trading quarter to support liquidity planning and market monitoring. Series of this kind are administrative rather than market data. They are recorded net, are frequently zero, and are dominated by dependence in the second moment rather than the first. These properties are not incidental to the results reported below; they define the regime to which the results apply.'));
b.push(H('1.2 Problem Statement', HeadingLevel.HEADING_2));
b.push(p(8));
b.push(P('Two practices follow from treating the two decisions separately, and both are consequential. The first is selecting among candidate models on training-stage output, which presumes that fit and forecast accuracy are positively related. The second is reporting teacher-forced accuracy as though it were out-of-sample accuracy, which presumes that the difference between protocols is a matter of implementation detail rather than of attainable performance. Neither presumption has been tested on the same data, windows and horizons with the protocols held otherwise identical. That is the gap this paper addresses.'));
b.push(H('1.3 Research Objectives and Questions', HeadingLevel.HEADING_2));
b.push(P('The study pursues four objectives, each stated as a question that the design is built to answer:'));
[['RQ1. ', 'What is the relationship between in-sample fit and out-of-sample accuracy across methods in this class of data — positive, absent, or inverted — and how robust is that relationship to the statistic used to measure it?'],
 ['RQ2. ', 'How does the choice of multi-step protocol affect measured accuracy when the model, data, windows and horizon grid are held identical, and how much of the apparent penalty of recursion is genuine error accumulation rather than information leakage from teacher-forced evaluation?'],
 ['RQ3. ', 'Where along the forecast horizon does the recursive penalty arise, and does it admit an operational threshold?'],
 ['RQ4. ', 'Which of the engineered features do the machine-learning models actually use, and does the feature-selection criterion agree with the estimator that consumes its output?']
].forEach(q => b.push(Rich([{ t: q[0], b: true }, { t: q[1] }], { after: 90 })));
b.push(H('1.4 Significance of the Study', HeadingLevel.HEADING_2));
b.push(p(9));
b.push(P('The practical significance is that all three findings bear on decisions an operating institution must make before any model is deployed, and two of them can be acted upon without additional data or computation. The methodological significance is that reporting the training and testing stages separately, rather than reporting only the second, makes the inversion visible as a measured relationship rather than as an inference. The remainder of the paper is organised as follows. Section 2 reviews the theoretical and empirical literature and develops the hypotheses. Section 3 sets out the design, data, procedures and analysis methods. Section 4 reports the descriptive evidence, the hypothesis tests and the robustness checks. Section 5 interprets the findings, contrasts them with prior research, draws out the implications and states the limitations. Section 6 concludes and identifies future work.'));

// ============ 2. LITERATURE REVIEW ============
b.push(new Paragraph({ children: [new PageBreak()] }));
b.push(H('2. Literature Review', HeadingLevel.HEADING_1));
b.push(H('2.1 Theoretical Background', HeadingLevel.HEADING_2));
b.push(P('Two theoretical strands underpin the design. The first concerns multi-step forecasting strategy. Marcellino, Stock and Watson (2006) formalise the trade-off between the iterated and direct strategies: iteration reuses one set of parameters at every step and is therefore efficient when the one-step model is correctly specified, but compounds specification error when it is not; the direct strategy estimates a separate model per horizon, discarding that efficiency in exchange for robustness. Chevillon (2007) surveys the conditions under which each dominates, and Ben Taieb and Atiya (2016) express the choice as a bias–variance decomposition in which the direct strategy trades lower bias for higher estimation variance because each horizon-specific model is fitted on a shorter effective sample. Ben Taieb, Bontempi, Atiya and Sorjamaa (2012) provide the corresponding empirical comparison for machine-learning predictors.'));
b.push(p(94));
b.push(P('The second strand concerns evaluation itself. Hyndman and Koehler (2006) propose the mean absolute scaled error as a scale-free accuracy measure that remains defined for series containing zeros, which matters here because a substantial minority of our series are intermittent. Tashman (2000) sets out the requirements of a credible out-of-sample test, and Bergmeir and Benítez (2012) examine when cross-validation is admissible for dependent data, concluding in favour of rolling-origin designs of the kind used below. Diebold and Mariano (1995), with the small-sample correction of Harvey, Leybourne and Newbold (1997), supply the test of equal predictive accuracy. Together these fix what an evaluation must hold constant for a comparison between protocols to be interpretable.'));

b.push(H('2.2 Critical Review of Existing Literature', HeadingLevel.HEADING_2));
b.push(p(101));
b.push(capOf(102, `Table ${T.parallels}.`));
b.push(tb(103));
b.push(p(105));
b.push(P('Read together, these studies establish the phenomenon but leave its interpretation contested and its magnitude unquantified in any single design. Three features recur. Each is drawn from a low signal-to-noise environment. Each infers the divergence by comparing a fitted model with a forecast exercise, rather than by reporting the two stages as separate measured quantities. And none of them isolates the contribution of evaluation protocol, because in each case a single protocol is used throughout.'));

b.push(H('2.3 Identification of Research Gaps', HeadingLevel.HEADING_2));
b.push(P('Three gaps follow from that reading. First, the relationship between training fit and forecast accuracy is almost always inferred rather than measured: studies report out-of-sample failure of models known to fit well, but rarely report both quantities for every method on a common scale, which is what would be required to establish the sign and strength of the relationship. Second, the applied machine-learning practice of teacher-forcing has, to our knowledge, never been quantified against a valid direct strategy on identical data, so the share of reported accuracy that is unattainable in deployment is unknown. Third, the econometric literature on iterated versus direct forecasting reports aggregate comparisons but rarely locates the penalty along the horizon, which is what an institution needs in order to decide whether the additional cost of horizon-specific estimation is warranted at its own operating horizon.'));
b.push(P('A fourth, narrower gap concerns feature pipelines. Where tree ensembles are applied to economic series, the feature-selection criterion and the estimator are typically chosen independently, and the question of whether they agree is not usually asked. Strobl, Boulesteix, Zeileis and Hothorn (2007) and Gregorutti, Michel and Saint-Pierre (2017) establish that importance measures behave unreliably when predictors are correlated, which makes the question both harder and more necessary.'));

b.push(H('2.4 Conceptual Framework and Hypothesis Development', HeadingLevel.HEADING_2));
b.push(P('The conceptual framework is the decomposition set out in Section 2.1 applied twice: once to the difference between fitting and forecasting, and once to the difference between multi-step protocols. In a low signal-to-noise regime the irreducible component of error dominates the reducible one, so differences between methods in flexibility translate into differences in estimation variance without a compensating reduction in bias. This yields a testable prediction about the sign of the fit–accuracy relationship. Applied to protocols, the same framework predicts that iteration compounds specification error, so the penalty of recursion should be increasing in the horizon and should vanish at the first step, where by construction no prediction has yet been fed back. Four hypotheses follow, stated in Table 2 with the test used for each.'));
const wh = [700, 3050, 2600, 2676];
const th = [new TableRow({ tableHeader: true, children: [
  cell('', wh[0], { head: 1 }), cell('Hypothesis', wh[1], { head: 1 }),
  cell('Prediction', wh[2], { head: 1 }), cell('Test', wh[3], { head: 1 })] })];
[['H1', 'In-sample fit and out-of-sample accuracy are negatively related across methods.',
  'Methods that fit the training sample most closely forecast least accurately; the two rankings invert rather than merely decouple.',
  'Rank correlation between the two MASE series, at method level and within series-window units; exact permutation and Wilcoxon signed-rank tests.'],
 ['H2', 'The recursive strategy is less accurate than the direct strategy on a like-for-like comparison.',
  'A positive and statistically significant recursive penalty remains after teacher-forced leakage is removed.',
  'Paired Wilcoxon tests over series-window-model units on a common horizon grid.'],
 ['H3', 'A material part of the apparent recursive penalty is information leakage rather than accuracy.',
  'Teacher-forced accuracy exceeds direct accuracy, and the excess is unattainable at the forecast origin.',
  'Three-way protocol decomposition with model, data, windows and horizons held identical.'],
 ['H4', 'The feature-selection criterion and the estimator optimise different objectives.',
  'Importance is concentrated on few features and is uncorrelated or negatively correlated with the selection criterion.',
  'Selection frequency, normalised importance by feature family, and rank correlation between importance and absolute Spearman correlation with the target.']
].forEach(r => th.push(new TableRow({ children: [
  cell(r[0], wh[0], { bold: true }), cell(r[1], wh[1]), cell(r[2], wh[2]), cell(r[3], wh[3])] })));
b.push(cap(`Table ${T.hypo}.`, 'Hypotheses, predictions and the tests applied to each.', { before: 160, after: 60 }));
b.push(table(wh, th));
b.push(cap('Note.', 'H1 is tested in Section 4.2 and subjected to robustness analysis in Section 4.3. H2 and H3 are tested jointly, since the decomposition requires all three protocols. H4 is descriptive rather than confirmatory and is reported for the interpretation it supplies to H1.'));

// ============ 3. METHODOLOGY ============
b.push(new Paragraph({ children: [new PageBreak()] }));
b.push(H('3. Methodology', HeadingLevel.HEADING_1));
b.push(H('3.1 Research Design and Approach', HeadingLevel.HEADING_2));
b.push(P('The study uses a two-stage comparative evaluation design on a panel of time series, with rolling-origin validation. The two stages are reported separately and neither informs the other: Stage I estimates every model on the training sample and records fit, residual diagnostics and feature usage; Stage II tests the same fitted specifications out of sample under three multi-step protocols. Separating them is the methodological device on which the paper rests, because it makes the relationship between fit and accuracy a measured quantity rather than an inference. No model, feature set or hyper-parameter was chosen using out-of-sample results, and the hypotheses of Table 2 were fixed before the protocol comparison was run.'));
b.push(p(21));

b.push(H('3.2 Data Sources', HeadingLevel.HEADING_2));
b.push(p(12));
b.push(p(13));
b.push(P('The full descriptive profile of the eighteen terminal series is reported in Section 4.1. The data are administrative records drawn from an institutional reporting system; no sampling is involved, and the panel is the population of series at this level of the hierarchy.'));

b.push(H('3.3 Instruments and Procedures', HeadingLevel.HEADING_2));
b.push(Rich([{ t: 'Models. ', b: true }, { t: fix(IT[18].text) }]));
b.push(Rich([{ t: 'Protocols. ', b: true }, { t: fix(IT[54].text) }]));
b.push(capOf(55, `Table ${T.protocols}.`));
b.push(tb(56));
b.push(p(57));
b.push(p(58));
b.push(Rich([{ t: 'Windows and horizons. ', b: true },
  { t: `Table ${T.windows} reports the rolling-origin training and test windows used throughout.` }]));
b.push(capOf(60, `Table ${T.windows}.`));
b.push(tb(61));
b.push(p(62));

b.push(H('3.4 Data Analysis Methods', HeadingLevel.HEADING_2));
b.push(P('Accuracy is measured by the mean absolute scaled error, scaled by the mean absolute first difference of the corresponding training sample (Hyndman and Koehler, 2006), so that unity corresponds to the accuracy of a one-step random walk within the estimation sample. MASE is preferred to percentage measures because a substantial minority of the series contain zeros and take both signs, which makes MAPE and its variants undefined or unstable. Mean absolute error, root mean squared error, symmetric MAPE, the coefficient of determination, directional accuracy and bias are reported alongside it. Unless stated otherwise, every reported figure is the mean across the 18 series of the median across the 3 windows; the median is taken first so that a single anomalous window cannot dominate a series, and the mean is taken second so that every series carries equal weight.'));
b.push(P('Inference proceeds on three levels. Differences in predictive accuracy between methods are tested by the Diebold and Mariano (1995) statistic with the small-sample correction of Harvey, Leybourne and Newbold (1997). Differences between protocols are tested by paired Wilcoxon signed-rank tests over series-window-model units, which avoids distributional assumptions on a panel with heavy tails. The relationship between training fit and forecast accuracy is tested by exact permutation over all orderings of the method-level statistics, and, at series level, by within-unit rank correlations summarised by a Wilcoxon signed-rank test and by pooled rank correlation after removal of unit fixed effects. Exact permutation is used in preference to the asymptotic Spearman test because the method-level sample is small and, in one case reported in Section 4.3, because the statistic of interest is mechanically constrained under the null.'));
b.push(P('Specification is assessed by three residual diagnostics applied to every estimation: Ljung–Box at lag 10 with degrees of freedom adjusted for estimated parameters, the Engle (1982) ARCH Lagrange-multiplier test at lag 10, and Jarque–Bera. Feature usage is measured by each algorithm’s built-in importance — impurity reduction for the bagged trees and total gain for the two boosting implementations — normalised to sum to unity within each estimation. Because impurity- and gain-based importance are biased towards correlated and high-cardinality predictors (Strobl et al., 2007; Gregorutti et al., 2017), importance is reported alongside the absolute Spearman correlation used by the selector, so that the two criteria can be compared directly rather than assumed to agree.'));

b.push(H('3.5 Ethical Considerations', HeadingLevel.HEADING_2));
b.push(P('The study uses aggregated administrative statistics on transaction flows. The unit of observation is a daily total for a counterparty group and transaction purpose; no record identifies a person, a firm or a transaction, and no personal data were accessed at any stage. The work involves no human participants and required no ethics approval. Because the underlying series are supervisory data, they are not distributed with this paper; the descriptive statistics, aggregate results and all code paths necessary to reproduce the analysis from an equivalent panel are reported in full. Two disclosures follow from the same principle. Hyper-parameters and window definitions are stated exactly as used rather than as tuned for presentation, and a summary statistic reported in an earlier version of this work is withdrawn in Section 4.3 rather than quietly replaced.'));

// ============ 4. RESULTS ============
b.push(new Paragraph({ children: [new PageBreak()] }));
b.push(H('4. Results', HeadingLevel.HEADING_1));
b.push(H('4.1 Data Presentation and Description', HeadingLevel.HEADING_2));
b.push(P('Table 5 profiles the eighteen terminal series over the full sample. The dispersion of scale across the panel is wide, and the distributional pathologies noted in Section 3.2 are visible in the skewness, excess kurtosis and zero-share columns.'));
b.push(capOf(14, `Table ${T.desc}.`));
b.push(tb(15));
b.push(note(16));

b.push(H('4.2 Main Analysis and Hypothesis Testing', HeadingLevel.HEADING_2));
b.push(lead('H1. Training fit and out-of-sample accuracy'));
b.push(p(23));
b.push(capOf(24, `Table ${T.trainfit}.`));
b.push(tb(25));
b.push(note(26));
b.push(p(28));
b.push(capOf(29, `Table ${T.diag}.`));
b.push(tb(30));
b.push(note(31));
b.push(p(33));
b.push(p(34));
b.push(p(35));
b.push(Rich([
  { t: `The comparison can be made sharper. On the Ljung–Box criterion the three ensembles pass in ` },
  { t: 'none', b: true },
  { t: ` of the 54 estimations — precisely the record of the random walk, which estimates nothing at all. The only method that removes any residual autocorrelation is AutoARIMA, at seven of 54, and it is the most parsimonious estimated model in the comparison. A procedure that fits the training sample roughly forty per cent more closely than the random walk while leaving the dependence structure of its residuals exactly as the random walk leaves it has not identified the conditional mean; it has interpolated the estimation sample. That is what overfitting denotes in this setting, and the diagnostics permit it to be stated as a measurement rather than offered as an interpretation.` }
]));
b.push(p(36));
b.push(im(37));
b.push(capOf(38, 'Figure 1.'));

b.push(lead('H4. What the ensembles actually use'));
b.push(p(40));
b.push(p(41));
b.push(capOf(42, `Table ${T.featfam}.`));
b.push(tb(43));
b.push(note(44));
b.push(im(45));
b.push(capOf(46, 'Figure 2.'));
b.push(p(47));
b.push(p(48));
b.push(p(49));
b.push(p(50));
b.push(p(51));

b.push(lead('H2 and H3. The multi-step protocol'));
b.push(p(64));
b.push(capOf(65, `Table ${T.protomase}.`));
b.push(tb(66));
b.push(note(67));
b.push(im(68));
b.push(capOf(69, 'Figure 3.'));
b.push(p(71));
b.push(p(72));
b.push(capOf(73, `Table ${T.horizon}.`));
b.push(tb(74));
b.push(p(75));
b.push(p(76));

b.push(lead('The full model set under the production protocol'));
b.push(p(78));
b.push(capOf(79, `Table ${T.allten}.`));
b.push(tb(80));
b.push(note(81));
b.push(im(82));
b.push(capOf(83, 'Figure 4.'));
b.push(p(84));

b.push(H('4.3 Robustness Checks', HeadingLevel.HEADING_2));
b.push(p(107));
b.push(p(109));
b.push(p(110));
b.push(p(111));
b.push(p(112));
b.push(capOf(113, `Table ${T.robust}.`));
b.push(tb(114));
b.push(note(115));
b.push(im(116));
b.push(capOf(117, 'Figure 5.'));
b.push(p(118));

// ============ 5. DISCUSSION ============
b.push(new Paragraph({ children: [new PageBreak()] }));
b.push(H('5. Discussion', HeadingLevel.HEADING_1));
b.push(H('5.1 Synthesis and Interpretation of Findings', HeadingLevel.HEADING_2));
b.push(p(87));
b.push(p(88));
b.push(p(89));
b.push(p(90));
b.push(p(93));
b.push(p(98));
b.push(capOf(95, `Table ${T.channels}.`));
b.push(tb(96));
b.push(note(97));
b.push(p(99));

b.push(H('5.2 Alignment and Contrast with Prior Research', HeadingLevel.HEADING_2));
b.push(P('The findings align with the empirical record reviewed in Section 2.2 on every point where a comparison is available, and extend it on two. The alignment is close: our inversion reproduces the pattern Bossaerts and Hillion (1999) document for model-selection criteria, our benchmark result reproduces Meese and Rogoff (1983) and Welch and Goyal (2008) in a different asset class, and the family ordering reproduces the first conclusion of the M3 competition (Makridakis and Hibon, 2000). The extension is that we report both stages as measured quantities on a common scale rather than inferring the divergence, and that we separate the protocol effect from the model effect, which the prior studies do not attempt because each holds protocol fixed.'));
b.push(p(104));
b.push(P('One contrast with the machine-learning literature deserves recording. Makridakis, Spiliotis and Assimakopoulos (2018) attribute the post-sample failure of ML methods to overfitting in a general sense; our Section 4.2 permits a more specific attribution. The ensembles do not overfit by exploiting the volatility structure, which is the most prominent form of dependence in these series. They overfit through redundancy in a feature set whose selection criterion is anti-correlated with the estimator’s own use of it. That is a defect of pipeline construction rather than of the algorithm class, and it is correctable.'));

b.push(H('5.3 Theoretical and Practical Implications', HeadingLevel.HEADING_2));
b.push(P('The theoretical implication is that evaluation protocol should be treated as a first-order design parameter rather than an implementation detail. Our decomposition shows the protocol decision moving measured accuracy by 18.1 per cent, of which 7.3 points are not accuracy at all. That is the same order of magnitude as the spread between the best and worst methods in the comparison, which means that a study reporting a model ranking without specifying its protocol has not reported a result that can be compared with any other study. The corollary for the bias–variance literature is that the direct strategy’s advantage in this regime is conditional on misspecification: it is realised where the recursive bias is large and reversed where it is small, exactly as Ben Taieb and Atiya (2016) predict, and the per-algorithm pattern of Section 4.2 is a direct test of that prediction rather than an anomaly.'));
b.push(P('The practical implications concern evaluation governance rather than modelling technique. If training-stage output is negatively related to forecast accuracy, then any review process that inspects training metrics before out-of-sample results is not merely uninformative but actively harmful, and the ordering of the review matters as much as its content. If teacher-forced accuracy overstates attainable accuracy by roughly seven per cent in this panel, then a system accepted on that basis will underperform its acceptance criteria in production by about that margin, and the shortfall will be attributed to regime change rather than to the evaluation. Both failures are avoidable at no computational cost by fixing the order and the protocol of the evaluation in advance.'));
b.push(p(91));

b.push(H('5.4 Research Limitations and Constraints', HeadingLevel.HEADING_2));
b.push(p(120));
b.push(capOf(121, `Table ${T.threats}.`));
b.push(tb(122));

// ============ 6. CONCLUSION AND FUTURE WORK ============
b.push(new Paragraph({ children: [new PageBreak()] }));
b.push(H('6. Conclusion and Future Work', HeadingLevel.HEADING_1));
b.push(H('6.1 Summary of Key Contributions', HeadingLevel.HEADING_2));
b.push(p(127));
b.push(p(128));
b.push(P('A third contribution is diagnostic rather than comparative. Because Stage I records what the ensembles select and what they then use, the overfitting can be localised. It does not arise where one would first look — in the volatility features, which occupy roughly a tenth of the feature budget and earn about half that share of importance — but in redundancy among level-tracking predictors, and in a selection criterion whose ranking is mildly anti-correlated with the estimator’s own use of the features it retains. The engineered feature set, as configured in production, is therefore largely inert: five of twenty-five predictors carry most of the fitted signal while the estimation pays the variance cost of all twenty-five. That is a defect of pipeline construction, it is measurable, and unlike the regime characteristics it is under the modeller’s control.'));
b.push(H('6.2 Policy and Practical Recommendations', HeadingLevel.HEADING_2));
b.push(p(129));
b.push(Rich([
  { t: 'Two of the three cost nothing to adopt, because they are review procedure rather than modelling work. Fix the evaluation protocol before estimation begins, and record it alongside every reported accuracy figure, so that a number produced under teacher-forcing can never be compared with one produced under recursion. Withhold training-stage output from the model-selection decision altogether rather than merely discounting it: given a relationship of the sign documented here, a reviewer who sees training metrics first is worse placed than one who never sees them. The third recommendation has a computational price that should be stated plainly rather than buried. Horizon-specific estimation multiplies the number of fits by the number of horizons evaluated — a twelvefold increase on the grid used here, sixtyfold on the full horizon. Where the operational horizon is short that price buys nothing, since the two valid protocols are indistinguishable to ' },
  { t: 'h', i: true },
  { t: ' = 23. Where it is long the trade is clearly favourable: the 29 per cent reduction in scaled error beyond ' },
  { t: 'h', i: true },
  { t: ' = 30 is more than half the distance separating the best from the worst of the nine non-stacked methods in Table 11 (1.441 against 2.195). An institution operating at a one-quarter horizon is choosing between a protocol change and a model search, and on this evidence the protocol change is both the larger and the cheaper of the two.' }
]));
b.push(H('6.3 Recommendations for Future Research', HeadingLevel.HEADING_2));
b.push(p(124));
b.push(P('Because a research agenda stated in prose is difficult to hold anyone to, we specify the four studies in Table 15, each with the design that would execute it and the result that would falsify the interpretation offered in this paper. The list is ordered by expected value, and the first two are the ones we would run before treating any of our recommendations as settled.'));
const wf = [1900, 3550, 3576];
const tf = [new TableRow({ tableHeader: true, children: [
  cell('Study', wf[0], { head: 1 }), cell('Design', wf[1], { head: 1 }),
  cell('What would falsify the present interpretation', wf[2], { head: 1 })] })];
[['Reduced feature set',
  'Re-estimate the three ensembles on five to eight predictors drawn from the difference and exponentially weighted families, holding windows, protocol and horizon grid fixed so that the feature set is the only thing that changes.',
  'If out-of-sample accuracy does not improve and the in-sample to out-of-sample inversion persists at its present magnitude, then the inversion is a property of the data rather than of an over-specified pipeline, and the account of channel two in Table 13 is wrong.'],
 ['Extended test sequence',
  'Repeat the three-protocol comparison over a rolling sequence of at least twenty non-overlapping sixty-day test blocks spanning several years, retaining the anchoring rule and the common horizon grid.',
  'If the ordering of the protocols reverses in a material share of blocks, the recursive penalty is regime-specific rather than structural, and the threshold near h = 23 cannot be used as an operating rule.'],
 ['Estimator-aligned selection',
  'Replace the marginal Spearman selector with one that optimises the estimator’s own objective — forward selection on rolling-origin validation error, or permutation importance under a conditional inference framework — and re-measure the correlation between selection score and realised importance.',
  'If that correlation remains negative under an aligned criterion, the mismatch documented under H4 is not attributable to the choice of selector, and the interpretation in Section 5.2 must be revised.'],
 ['Tuned hyper-parameters',
  'Tune each ensemble by rolling-origin validation inside the training sample only, never touching test data, and then repeat both stages unchanged.',
  'If tuning lifts out-of-sample accuracy above the statistical benchmarks, the family ranking of Table 11 is an artefact of configuration rather than a property of the regime. If instead it lowers in-sample fit while leaving the out-of-sample ranking intact, the inversion is strengthened rather than weakened.']
].forEach(r => tf.push(new TableRow({ children: [
  cell(r[0], wf[0], { bold: true }), cell(r[1], wf[1]), cell(r[2], wf[2])] })));
b.push(cap(`Table ${T.followup}.`, 'Specified follow-up studies and their falsification criteria.', { before: 160, after: 60 }));
b.push(table(wf, tf));
b.push(cap('Note.', 'Each design holds fixed everything the present study holds fixed, so that a single factor varies. The falsification criteria are stated in terms of this paper’s own claims rather than in terms of statistical significance, because with three windows the relevant question is the size and direction of an effect rather than its p-value.'));
b.push(p(125));

// ============ ACKNOWLEDGEMENTS ============
b.push(H('Acknowledgements', HeadingLevel.HEADING_1));
b.push(P('We thank the operational team responsible for the forecasting system for access to the reporting series and for discussion of the deployment constraints that shaped the protocol comparison. Any errors of analysis or interpretation are ours alone.'));

// ============ REFERENCES ============
b.push(H('References', HeadingLevel.HEADING_1));
IT.forEach((x, i) => { if (i > 144 && x.k === 'p' && !x.style) b.push(ref(x.text)); });

// ============ APPENDIX ============
b.push(new Paragraph({ children: [new PageBreak()] }));
b.push(H('Appendix A. Series-level accuracy under the three protocols', HeadingLevel.HEADING_1));
b.push(p(131));
b.push(p(132));
b.push(im(133));
b.push(capOf(134, 'Figure A1.'));
[[135, 136, 137], [138, 139, 140], [141, 142, 143]].forEach((g, k) => {
  b.push(capOf(g[0], `Table A${k + 1}.`));
  b.push(tb(g[1]));
  b.push(note(g[2]));
});

const doc = new Document({
  creator: 'Forecast evaluation study',
  title: 'Training Fit, Multi-Step Protocol and Forecast Accuracy',
  styles: { default: { document: { run: { font: SERIF, size: 22 } } } },
  sections: [{ properties: { page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    children: b }]
});
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log('written', OUT, buf.length, 'bytes');
});
