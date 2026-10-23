from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
A='http://schemas.openxmlformats.org/drawingml/2006/main'
with ZipFile('tmp/deck_edit/revised_raw.pptx') as src, ZipFile('tmp/deck_edit/candidate_font.pptx','w',ZIP_DEFLATED) as dst:
 for n in src.namelist():
  data=src.read(n)
  if n.startswith('ppt/') and n.endswith('.xml'):
   root=E.fromstring(data)
   for el in root.iter():
    if 'typeface' in el.attrib: el.set('typeface','Malgun Gothic')
    if el.tag in [f'{{{A}}}rPr',f'{{{A}}}defRPr',f'{{{A}}}endParaRPr']:
     for tag in ['latin','ea','cs']:
      q=el.find(f'{{{A}}}{tag}')
      if q is None:q=E.SubElement(el,f'{{{A}}}{tag}')
      q.set('typeface','Malgun Gothic')
   data=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
  dst.writestr(n,data)
print('All typefaces unified: Malgun Gothic')
