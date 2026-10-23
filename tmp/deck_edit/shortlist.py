from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from copy import deepcopy
from pathlib import Path
import hashlib
A='http://schemas.openxmlformats.org/drawingml/2006/main'
P='http://schemas.openxmlformats.org/presentationml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PK='http://schemas.openxmlformats.org/package/2006/relationships'
ns={'a':A,'p':P,'r':R}
source=Path('D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx')
Path('tmp/deck_edit/shortlist_hash.txt').write_text(hashlib.sha256(source.read_bytes()).hexdigest())
with ZipFile(source) as z: parts={n:z.read(n) for n in z.namelist()}
def read(n):return E.fromstring(parts[n])
def save(n,r):parts[n]=E.tostring(r,encoding='UTF-8',xml_declaration=True,standalone=True)
def settext(node,value,size=None,font=None):
 body=node.find('a:txBody',ns)
 if body is None:body=node.find('p:txBody',ns)
 p=deepcopy(body.find('a:p',ns));run=p.find('a:r',ns)
 if run is None:run=E.SubElement(p,'{'+A+'}r');E.SubElement(run,'{'+A+'}rPr');E.SubElement(run,'{'+A+'}t')
 for ch in list(p):
  if ch.tag not in ['{'+A+'}pPr','{'+A+'}r']:p.remove(ch)
 for extra in p.findall('a:r',ns)[1:]:p.remove(extra)
 run.find('a:t',ns).text=value
 pr=run.find('a:rPr',ns)
 if pr is None:pr=E.Element('{'+A+'}rPr');run.insert(0,pr)
 if size:pr.set('sz',str(int(size*100)))
 if font:
  for tag in ['latin','ea','cs']:
   el=pr.find('{'+A+'}'+tag)
   if el is None:el=E.SubElement(pr,'{'+A+'}'+tag)
   el.set('typeface',font)
  pr.set('b','0')
 for old in body.findall('a:p',ns):body.remove(old)
 body.append(p)
def shape(r,name):return next(s for s in r.findall('.//p:sp',ns) if s.find('p:nvSpPr/p:cNvPr',ns).get('name')==name)
r=read('ppt/slides/slide6.xml')
settext(shape(r,'TextBox 1484883484'),'선정 3안 핵심 비교')
settext(shape(r,'TextBox 518989947'),'영재 7960X · 다나와 최신본 · 추가 추천 아싸컴 / 금액은 VAT 별도',19)
settext(shape(r,'TextBox 1953928640'),'3')
settext(shape(r,'TextBox 1745001461'),'SELECTED SYSTEMS & PRICING')
sp=shape(r,'vat-calculation');sp.getparent().remove(sp)
for pic in r.findall('.//p:pic',ns)[1:]:pic.getparent().remove(pic)
table=r.find('.//a:tbl',ns)
rows=table.findall('a:tr',ns)
values=[['비교 항목','영재컴퓨터 10/20','샵다나와 10/20','아싸컴 10/23'],['CPU','Threadripper 7960X','Threadripper PRO 9965WX','Threadripper PRO 9965WX'],['GPU','GeForce RTX 5090 32GB','RTX PRO 4500 Blackwell 32GB','GeForce RTX 5090 32GB'],['메모리','128GB (32GB × 4)','64GB (32GB × 2)','128GB (16GB × 8)'],['지원 조건','프레임그래버 3장 검수','방문 A/S 불가','1년간 출장 A/S 3회'],['가격 (VAT 별도)','₩25,836,570','₩22,157,273','₩26,600,000'],['선정 이유','128GB 구성 / 장착 검수','3안 중 최저가','영재 대비 약 3% 추가\n9965WX·128GB 구성']]
heights=[54,66,66,54,60,70,78]
for old in rows:table.remove(old)
for i,vals in enumerate(values):
 row=deepcopy(rows[0 if i==0 else 8 if i==5 else 1 if i%2 else 2]);row.set('h',str(heights[i]*9525))
 for j,(cell,value) in enumerate(zip(row.findall('a:tc',ns),vals)):
  settext(cell,value.replace('\n',' / '),22 if i==5 and j else 16 if j==0 else 18 if i in [1,2,6] else 20,'Pretendard Black' if i in [0,5] or j==0 else 'Pretendard Medium')
  if i==0:
   pr=cell.find('.//a:rPr',ns)
   for oldfill in pr.findall('a:solidFill',ns):pr.remove(oldfill)
   fill=E.Element('{'+A+'}solidFill');pr.insert(0,fill);E.SubElement(fill,'{'+A+'}srgbClr',val='FFFFFF')
  cell.find('a:txBody/a:bodyPr',ns).set('anchor','ctr')
  for pp in cell.findall('.//a:pPr',ns):pp.set('algn','ctr' if j else 'l')
 table.append(row)
frame=table.getparent().getparent().getparent();frame.find('p:xfrm/a:off',ns).set('y',str(170*9525));frame.find('p:xfrm/a:ext',ns).set('cy',str(sum(heights)*9525))
save('ppt/slides/slide10.xml',r)
rels=read('ppt/slides/_rels/slide6.xml.rels')
for rel in list(rels):
 if rel.get('Type').endswith('/notesSlide'):rels.remove(rel)
save('ppt/slides/_rels/slide10.xml.rels',rels)
ct=read('[Content_Types].xml');E.SubElement(ct,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',PartName='/ppt/slides/slide10.xml',ContentType='application/vnd.openxmlformats-officedocument.presentationml.slide+xml');save('[Content_Types].xml',ct)
presrels=read('ppt/_rels/presentation.xml.rels');newrid='rIdShortlist';E.SubElement(presrels,'{'+PK+'}Relationship',Id=newrid,Type=R+'/slide',Target='slides/slide10.xml');save('ppt/_rels/presentation.xml.rels',presrels)
pres=read('ppt/presentation.xml');lst=pres.find('p:sldIdLst',ns);old=list(lst);mapping={rel.get('Id'):rel.get('Target') for rel in presrels};by_num={int(mapping[s.get('{'+R+'}id')].split('slide')[-1].split('.')[0]):s for s in old}
new=E.Element('{'+P+'}sldId',id=str(max(int(s.get('id')) for s in old)+1));new.set('{'+R+'}id',newrid);by_num[10]=new
order=[1,2,10,9,3,4,5,6,7,8]
for s in old:lst.remove(s)
for n in order:lst.append(by_num[n])
save('ppt/presentation.xml',pres)
for n,num,title,sub in [(2,'01','선정 3안 비교','영재 7960X / 다나와 최신본 / 아싸컴 9965WX'),(9,'02','CPU 별 상세 견적','7960X / 7965WX / 9955WX / 9965WX / Intel / 7975WX')]:
 r=read(f'ppt/slides/slide{n}.xml');settext(shape(r,'TextBox 1242089716'),num)
 s=shape(r,'TextBox 1079933329');paras=s.findall('p:txBody/a:p',ns)
 for idx,value in [(0,title),(2,sub),(3,'')]:
  texts=paras[idx].findall('.//a:t',ns);texts[0].text=value
  for t in texts[1:]:t.text=''
 save(f'ppt/slides/slide{n}.xml',r)
r=read('ppt/slides/slide1.xml');s=shape(r,'TextBox 1874383746')
for para,value in zip(s.findall('p:txBody/a:p',ns),['01 선정 3안 비교','02 CPU 별 상세 견적','']):
 texts=para.findall('.//a:t',ns)
 if texts:
  texts[0].text=value
  for t in texts[1:]:t.text=''
save('ppt/slides/slide1.xml',r)
for position,n in enumerate(order,1):
 if n in [1,2,9,10]:continue
 r=read(f'ppt/slides/slide{n}.xml');s=shape(r,'TextBox 1953928640');settext(s,str(position))
 if position>=10:
  x=s.find('p:spPr/a:xfrm',ns);off=x.find('a:off',ns);ext=x.find('a:ext',ns);off.set('x',str(int(off.get('x'))-190500));ext.set('cx',str(int(ext.get('cx'))+190500))
 save(f'ppt/slides/slide{n}.xml',r)
with ZipFile('tmp/deck_edit/candidate_shortlist.pptx','w',ZIP_DEFLATED) as z:
 for n,data in parts.items():z.writestr(n,data)
print('Built 10 slides, shortlist at page 3, detail divider at page 4')

