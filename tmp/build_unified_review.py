from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pdfplumber
from PIL import Image, ImageChops
P=Path('output/cpu_gpu_comparison');A=Path('tmp/products')
D=json.loads((P/'온라인가격_조회근거.json').read_text(encoding='utf-8'))
CPU=D['CPU'][:7];GPU=D['GPU'];GPU[0][2]=104.8
imgs=dict(zip([r[0] for r in CPU],['7975WX.jpg','9965WX.jpg','7960X.jpg','pro.jpg','9955WX.jpg','i9.jpg','xeon.jpg']))
pdfmetrics.registerFont(TTFont('R','tmp/fonts/NotoSansKR-400.ttf'));pdfmetrics.registerFont(TTFont('B','tmp/fonts/NotoSansKR-600.ttf'))
W,H=842,595;INK='#233246';GRAY='#748092';ACC='#36536F';LINE='#E6EAF0';LIGHT='#F5F7FA'
OUTPUT=P/'워크스테이션_CPU_GPU_비교보고서_v7.pdf'
c=canvas.Canvas(str(OUTPUT),pagesize=(W,H))
c.setTitle('워크스테이션 CPU · GPU 성능 및 가격 비교');c.setAuthor('산자부 비전 PC 비교')
def t(x,y,s,z=10,b=False,col=INK,right=False):
 z={27:22,14:11.5,13:11,12:10.5,11:10}.get(z,z)
 c.setFont('B' if b else 'R',z);c.setFillColor(HexColor(col));(c.drawRightString if right else c.drawString)(x,H-y-z*.8,str(s))
def rect(x,y,w,h,col):
 c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,stroke=0,fill=1)
def line(y,x=38,w=766):rect(x,y,w,.5,LINE)
def pic(name,x,y,w,h):c.drawImage(str(A/name),x,H-y-h,w,h,preserveAspectRatio=True,anchor='c',mask='auto')
def tight_pic(name,x,y,w,h):
 # Fit the visible alpha bounds in the PDF cell without modifying the asset.
 with Image.open(A/name) as im:
  iw,ih=im.size;l,top,r,bottom=im.getchannel('A').getbbox()
 scale=min(w/(r-l),h/(bottom-top))
 dx=x+(w-(r-l)*scale)/2-l*scale
 dy=H-y-h+(h-(bottom-top)*scale)/2-(ih-bottom)*scale
 c.drawImage(str(A/name),dx,dy,iw*scale,ih*scale,mask='auto')
def cpu_pic(name,x,y,w,h):
 # Measure whitespace only; scale and clip the original image in PDF layout.
 with Image.open(A/name) as im:
  rgb=im.convert('RGB');iw,ih=rgb.size
  diff=ImageChops.difference(rgb,Image.new('RGB',rgb.size,'white')).convert('L')
  bounds=diff.point(lambda v:255 if v>32 else 0).getbbox()
  l,top,r,bottom=bounds or (0,0,iw,ih)
 scale=min(w/(r-l),h/(bottom-top))
 dx=x+(w-(r-l)*scale)/2-l*scale
 dy=H-y-h+(h-(bottom-top)*scale)/2-(ih-bottom)*scale
 c.saveState();clip=c.beginPath();clip.rect(x,H-y-h,w,h);c.clipPath(clip,stroke=0,fill=0)
 c.drawImage(str(A/name),dx,dy,iw*scale,ih*scale);c.restoreState()
def link(u,x,y,w,h):pass
def bar(x,y,w,v,maxv,label,h=23):
 rect(x,y,w,h,'#EFF2F6');rect(x,y,w*v/maxv,h,ACC)
 t(x+7,y+(h-9)/2,label,9,True,col='#FFFFFF')
def header(n,title,sub):
 rect(38,0,766,3,INK)
 t(38,20,'산자부 비전 PC / 부품 비교',9,col=GRAY);t(804,20,f'{n:02} / 04',9,col=GRAY,right=True)
 t(38,42,title.replace('검토','비교'),27,True);t(38,75,sub,9.5,col=GRAY);line(93)
def summary(a,b):
 rect(38,100,2,30,ACC);t(51,102,a,12,True);t(51,120,b,9.5,col=GRAY)
def footer(note,refs):
 line(547)
 t(46,556,'출처',9.5,True);t(90,556,note,9.5,col=GRAY)
 x=90+pdfmetrics.stringWidth(note,'R',9.5)+18
 for label,u in refs:
  width=pdfmetrics.stringWidth(label,'R',9)
  t(x,556,label,9,col=ACC)
  rect(x,566,width,.4,ACC)
  c.linkURL(u,(x,H-570,x+width,H-551),relative=0,thickness=0)
  x+=width+17
 assert x<815, 'Source row overflow'
 t(804,582,'조회일: 2026.10.23',8.5,col=GRAY,right=True);c.showPage()
def columns(items):
 rect(38,137,766,28,LIGHT)
 for x,s,right in items:t(x,145,s,9.5,True,col=GRAY,right=right)
 line(165)

header(1,'CPU 성능 검토','멀티코어 성능순 비교 · PassMark V10 벤치마크 · 막대와 수치는 동일 항목 내 비교')
summary('멀티코어 상위: 7975WX · 9965WX','싱글코어는 i9-14900K가 가장 높으며, 9965WX와 9955WX가 그다음 순위입니다.')
columns([(46,'CPU / 모델별 이미지',False),(330,'멀티코어 성능',False),(574,'싱글코어 성능',False)])
for i,r in enumerate(CPU):
 m,multi,single,price,kind,src,bid,u=r;y=166+i*49
 cpu_pic(imgs[m],43,y+3,87,43);t(145,y+19,m,11,True)
 for x,w,v,maxv in [(330,220,multi,95566),(574,222,single,4690)]:
  bar(x,y+9,w,v,maxv,f'{v:,}점',32)
 line(y+49)
t(45,528,'Xeon Silver × 2',10,True);t(190,528,'정확한 모델명이 없어 성능 비교 보류',10,col=GRAY)
footer('PassMark',[(r[0].replace('TR PRO ','').replace('TR ','').replace('Core i9-','').replace('Xeon ',''),f'https://www.cpubenchmark.net/cpu.php?id={r[6]}') for r in CPU])

header(2,'CPU 가격 검토','온라인 단품가 · VAT 포함 / 배송비 제외')
columns([(46,'CPU / 모델별 이미지',False),(330,'온라인 단품 가격 (원)',False)])
ordered=CPU;best=max(r[3] for r in CPU)
for i,r in enumerate(ordered):
 m,multi,single,price,kind,src,bid,u=r;y=166+i*49
 cpu_pic(imgs[m],43,y+3,87,43);t(145,y+19,m,11,True)
 bar(330,y+8,466,price,best,f'{price:,}원',34);line(y+49)
footer('다나와·컴퓨존',[(r[0].replace('TR PRO ','').replace('TR ','').replace('Core i9-','').replace('Xeon ',''),r[7]) for r in CPU])

header(3,'GPU 성능 검토','32GB 제품 3종 · FP32 이론 연산 성능과 메모리 대역폭 · 실제 AI 처리속도와는 구분')
summary('RTX 5090이 FP32 연산 성능과 메모리 대역폭 모두 상위','RTX 5000 Ada는 RTX PRO 4500보다 FP32가 높고, RTX PRO 4500은 메모리 대역폭이 높습니다.')
columns([(46,'GPU / 모델별 이미지',False),(208,'FP32 연산 성능',False),(526,'메모리 대역폭',False)])
urls=['https://www.palit.com/palit/vgapro.php?id=5335&lang=en&pn=NE75090S19R5-GB2020G&tab=sp','https://www.nvidia.com/en-us/products/workstations/rtx-5000/','https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-4500-blackwell/workstation-datasheet-blackwell-rtx-pro-4500-we-nvidia-us-5108623-web.pdf']
for i,r in enumerate(GPU):
 m,short,fp,bw,price,kind,src,u=r;y=166+i*114
 tight_pic(['5090_cutout.png','5000_cutout.png','4500_cutout.png'][i],42,y+7,153,100)
 t(208,y+15,['GeForce RTX 5090','RTX 5000 Ada','RTX PRO 4500 Blackwell'][i],12,True)
 t(208,y+33,['PALIT GAMEROCK','Ada Generation','Workstation Edition'][i],9.5,col=GRAY)
 bar(208,y+53,278,fp,104.8,f'{fp:.1f} TFLOPS',48)
 bar(526,y+53,270,bw,1792,f'{bw:,} GB/s',48)
 line(y+114)
t(45,528,'메모리 용량',10,True);t(140,528,'세 제품 모두 32GB',10,col=GRAY)
footer('제조사 사양',[('PALIT RTX 5090',urls[0]),('NVIDIA RTX 5000 Ada',urls[1]),('NVIDIA RTX PRO 4500',urls[2])])

header(4,'GPU 가격 검토','온라인 단품가 · VAT 포함 / 배송비 제외')
columns([(46,'GPU / 모델별 이미지',False),(208,'온라인 단품 가격 (원)',False)])
best=max(r[4] for r in GPU)
gpu_images={r[0]:name for r,name in zip(GPU,['5090_cutout.png','5000_cutout.png','4500_cutout.png'])}
for i,r in enumerate(GPU):
 m,short,fp,bw,price,kind,src,u=r;y=166+i*114
 tight_pic(gpu_images[m],42,y+7,153,100);t(208,y+15,m,12,True)
 bar(208,y+49,588,price,best,f'{price:,}원',54)
 line(y+114)
footer('온라인 판매가',[('5090 / 에누리',GPU[0][7]),('5000 Ada / 컴퓨존',GPU[1][7]),('PRO 4500 / 컴퓨존',GPU[2][7])])
c.save()
f=OUTPUT
with pdfplumber.open(f) as pdf:
 assert len(pdf.pages)==4
 for i,page in enumerate(pdf.pages):page.to_image(resolution=140).original.save(P/f'통합보고서_{i+1}.png')
print(f.resolve())
