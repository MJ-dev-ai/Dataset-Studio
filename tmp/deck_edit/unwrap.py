from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from copy import deepcopy
A='http://schemas.openxmlformats.org/drawingml/2006/main'
ns={'a':A}
source='D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx'
with ZipFile(source) as src, ZipFile('tmp/deck_edit/candidate_unwrap.pptx','w',ZIP_DEFLATED) as dst:
 for n in src.namelist():
  data=src.read(n)
  if n.startswith('ppt/slides/slide') and n.endswith('.xml'):
   root=E.fromstring(data)
   for cell in root.findall('.//a:tbl/a:tr/a:tc',ns):
    tx=cell.find('a:txBody',ns)
    if tx is None:continue
    ps=tx.findall('a:p',ns)
    # Retain deliberate separation for unavailable case photos.
    combined=''.join(tx.xpath('.//a:t/text()',namespaces=ns))
    if '제품 이미지 확인 필요' in combined or combined=='견적 금액(VAT 별도)':continue
    texts=[''.join(p.xpath('.//a:t/text()',namespaces=ns)).strip() for p in ps]
    text=' '.join(t for t in texts if t)
    if len(ps)>1 or tx.find('.//a:br',ns) is not None:
     p=E.Element(f'{{{A}}}p')
     if ps and ps[0].find('a:pPr',ns) is not None:p.append(deepcopy(ps[0].find('a:pPr',ns)))
     r=E.SubElement(p,f'{{{A}}}r')
     pr=tx.find('.//a:rPr',ns)
     if pr is not None:r.append(deepcopy(pr))
     E.SubElement(r,f'{{{A}}}t').text=text
     for old in ps:tx.remove(old)
     tx.append(p)
    body=tx.find('a:bodyPr',ns)
    if body is not None:body.set('wrap','square')
   data=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
  dst.writestr(n,data)
print('Removed manual line breaks from table cells')
