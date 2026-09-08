"""Bongkar isi DOCX ke JSON berurutan: paragraf (dengan run + gaya), tabel, gambar.

Tujuannya menyusun ulang makalah ke kerangka bagian yang baru tanpa kehilangan
apa pun - teks, penekanan, isi tabel, dan gambar yang tertanam.
"""
import argparse, json, os, shutil, zipfile
from docx import Document
from docx.oxml.ns import qn

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('docx', help='berkas .docx sumber')
ap.add_argument('-o', '--outdir', default='.', help='direktori keluaran (default: direktori kerja)')
A = ap.parse_args()

S = os.path.abspath(A.outdir)
os.makedirs(S, exist_ok=True)
# media dibongkar ke direktori sementara di dalam outdir
UNZ = os.path.join(S, '_unz')
with zipfile.ZipFile(A.docx) as z:
    z.extractall(UNZ)

doc = Document(A.docx)
body = doc.element.body

# peta rId -> nama berkas media
rels = {rid: os.path.basename(getattr(r._target, 'partname', r._target))
        for rid, r in doc.part.rels.items() if 'image' in r.reltype}

os.makedirs(f'{S}/fig', exist_ok=True)
items, fign = [], 0

for child in body.iterchildren():
    tag = child.tag.split('}')[1]
    if tag == 'p':
        # gambar?
        blips = child.findall('.//' + qn('a:blip'))
        if blips:
            rid = blips[0].get(qn('r:embed'))
            src = rels.get(rid)
            if src:
                fign += 1
                dst = f'figure_{fign}.png'
                shutil.copy(os.path.join(UNZ, 'word', 'media', src), f'{S}/fig/{dst}')
                ext = child.findall('.//' + qn('wp:extent'))
                w = h = None
                if ext:
                    w = round(int(ext[0].get('cx')) / 9525)
                    h = round(int(ext[0].get('cy')) / 9525)
                items.append({'k': 'img', 'file': dst, 'w': w, 'h': h})
                continue
        runs, txt = [], ''
        for r in child.findall(qn('w:r')):
            t = ''.join(n.text or '' for n in r.findall(qn('w:t')))
            if not t:
                continue
            rpr = r.find(qn('w:rPr'))
            b = rpr is not None and rpr.find(qn('w:b')) is not None
            i = rpr is not None and rpr.find(qn('w:i')) is not None
            sz = rpr.find(qn('w:sz')) if rpr is not None else None
            sz = int(sz.get(qn('w:val'))) if sz is not None else None
            runs.append({'t': t, 'b': b, 'i': i, 'sz': sz})
            txt += t
        style = ''
        ppr = child.find(qn('w:pPr'))
        if ppr is not None:
            st = ppr.find(qn('w:pStyle'))
            if st is not None:
                style = st.get(qn('w:val'))
        if not runs and not txt.strip():
            continue
        items.append({'k': 'p', 'style': style, 'text': txt, 'runs': runs})
    elif tag == 'tbl':
        from docx.table import Table
        t = Table(child, doc)
        grid, widths = [], []
        for ri, row in enumerate(t.rows):
            cells, seen = [], set()
            for c in row.cells:
                if id(c._tc) in seen:
                    continue
                seen.add(id(c._tc))
                bold = any(r.bold for p in c.paragraphs for r in p.runs if r.bold)
                cells.append({'t': c.text, 'b': bool(bold)})
            grid.append(cells)
        for gc in child.findall(qn('w:tblGrid')):
            widths = [int(g.get(qn('w:w'))) for g in gc.findall(qn('w:gridCol'))]
        items.append({'k': 'tbl', 'rows': grid, 'widths': widths})

shutil.rmtree(UNZ, ignore_errors=True)
json.dump(items, open(f'{S}/doc_items.json', 'w'), indent=1)
print('items', len(items),
      'paras', sum(1 for x in items if x['k'] == 'p'),
      'tables', sum(1 for x in items if x['k'] == 'tbl'),
      'images', fign)
for x in items:
    if x['k'] == 'p' and x['style'].startswith('Heading'):
        print(' ', x['style'], '|', x['text'][:70])
