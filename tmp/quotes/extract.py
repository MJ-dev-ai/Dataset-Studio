import pathlib, pdfplumber, zipfile, lxml.etree as E, openpyxl
p = pathlib.Path(__file__).parent
out=[]
for f in p.glob('*.pdf'):
    with pdfplumber.open(f) as doc:
        out.append('\nFILE: '+f.name+'\n'+'\n'.join('PAGE '+str(i+1)+'\n'+(page.extract_text() or '') for i,page in enumerate(doc.pages)))
for f in p.glob('*.xlsx'):
    out.append('\nFILE: '+f.name+'\n'+'\n'.join(str(row) for s in openpyxl.load_workbook(f,data_only=True).worksheets for row in s.values if any(v is not None for v in row)))
for f in p.glob('*.pptx'):
    with zipfile.ZipFile(f) as z:
        out.append('\nFILE: '+f.name+'\n'+'\n'.join(n+': '+' | '.join(E.fromstring(z.read(n)).xpath('//*[local-name()="t"]/text()')) for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')))
(p/'text.txt').write_text('\n'.join(out),encoding='utf-8')
