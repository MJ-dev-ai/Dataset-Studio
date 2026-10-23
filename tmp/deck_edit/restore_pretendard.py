from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
A='http://schemas.openxmlformats.org/drawingml/2006/main'
with ZipFile('D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx') as src, ZipFile('tmp/deck_edit/candidate_pretendard.pptx','w',ZIP_DEFLATED) as dst:
 for n in src.namelist():
  data=src.read(n)
  if n.startswith('ppt/') and n.endswith('.xml'):
   root=E.fromstring(data)
   for el in root.iter():
    if 'typeface' in el.attrib: el.set('typeface','Pretendard')
    if el.tag in [f'{{{A}}}rPr',f'{{{A}}}defRPr',f'{{{A}}}endParaRPr']:
     for tag in ['latin','ea','cs']:
      q=el.find(f'{{{A}}}{tag}')
      if q is None:q=E.SubElement(el,f'{{{A}}}{tag}')
      q.set('typeface','Pretendard')
   data=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
  dst.writestr(n,data)
print('All typefaces unified: Pretendard')

