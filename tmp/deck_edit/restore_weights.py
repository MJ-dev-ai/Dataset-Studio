from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
import re
A='http://schemas.openxmlformats.org/drawingml/2006/main'
ns={'a':A,'p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
def font(node,name):
 for el in node.iter():
  if 'typeface' in el.attrib:el.set('typeface',name)
  if el.tag in [f'{{{A}}}rPr',f'{{{A}}}defRPr',f'{{{A}}}endParaRPr']:
   el.set('b','0')
   for tag in ['latin','ea','cs']:
    q=el.find(f'{{{A}}}{tag}')
    if q is None:q=E.SubElement(el,f'{{{A}}}{tag}')
    q.set('typeface',name)
with ZipFile('D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx') as src,ZipFile('tmp/deck_edit/candidate_weights.pptx','w',ZIP_DEFLATED) as dst:
 for n in src.namelist():
  data=src.read(n)
  if re.fullmatch(r'ppt/slides/slide\d+\.xml',n):
   root=E.fromstring(data);i=int(re.search(r'slide(\d+)',n)[1])
   for s in root.findall('.//p:sp',ns):
    value=''.join(s.xpath('.//a:t/text()',namespaces=ns))
    name='Pretendard Medium'
    if i==1 and value.startswith('산자부'):name='Pretendard ExtraBold'
    elif i==1 and value.startswith('01'):name='Pretendard SemiBold'
    elif value=='01':name='Pretendard ExtraBold'
    elif value.startswith('CPU 별 견적 비교'):name='Pretendard Black'
    font(s,name)
    if value.startswith('CPU 별 견적 비교'):
     for p in s.findall('.//a:p',ns):
      txt=''.join(p.xpath('.//a:t/text()',namespaces=ns))
      if not txt.startswith('CPU 별 견적 비교'):font(p,'Pretendard Medium')
   for table in root.findall('.//a:tbl',ns):
    for r,tr in enumerate(table.findall('a:tr',ns)):
     for c,cell in enumerate(tr.findall('a:tc',ns)):
      label=''.join(tr.xpath('a:tc[1]//a:t/text()',namespaces=ns))
      font(cell,'Pretendard Black' if r==0 else 'Pretendard Bold' if c==0 or '견적 금액' in label else 'Pretendard')
   data=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
  dst.writestr(n,data)
print('Restored Pretendard weight hierarchy')
