from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pdfplumber
P=Path('output/cpu_gpu_comparison'); A=Path('tmp/products')
D=json.loads((P/'온라인가격_조회근거.json').read_text(encoding='utf-8'))
pdfmetrics.registerFont(TTFont('R','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('B','C:/Windows/Fonts/malgunbd.ttf'))
W,H=1500,1060
INK='#183342'; MUT='#647581'; TEAL='#117A76'; BLUE='#557DA4'; LINE='#DFE7EA'; LIGHT='#F3F6F7'
def t(c,x,y,s,z=20,b=False,col=INK,align='left'):
 c.setFont('B' if b else 'R',z);c.setFillColor(HexColor(col));{'left':c.drawString,'right':c.drawRightString,'center':c.drawCentredString}[align](x,H-y-z*.8,str(s))
def box(c,x,y,w,h,col):
 c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,stroke=0,fill=1)
def line(c,x,y,w):box(c,x,y,w,1,LINE)
def image(c,name,x,y,w,h):c.drawImage(str(A/name),x,H-y-h,width=w,height=h,preserveAspectRatio=True,anchor='c',mask='auto')
def url(c,u,x,y,w,h):c.linkURL(u,(x,H-y-h,x+w,H-y),relative=0,thickness=0)
def head(c,title,sub):
 t(c,55,40,title,42,True);t(c,1445,51,'2026.10.23',17,col=MUT,align='right');t(c,55,100,sub,19,col=MUT)
def bar(c,x,y,w,v,color,h=16):box(c,x,y,w,h,'#E9EFF1');box(c,x,y,w*v/100,h,color)
def money(p):return f'{p/10000:,.1f}만원'

c=canvas.Canvas(str(P/'CPU_성능가격_검토.pdf'),pagesize=(W,H));c.setTitle('CPU 성능 비교')
head(c,'CPU 성능 비교','멀티코어 성능순 정렬  |  PassMark V10 벤치마크 점수')
box(c,55,157,1390,58,INK)
for x,s in [(72,'순위 / CPU'),(590,'멀티코어'),(980,'싱글코어'),(1425,'온라인 단품가')]:t(c,x,176,s,20,True,col='#FFFFFF',align='right' if x==1425 else 'left')
model_images=['7975WX.jpg','9965WX.jpg','7960X.jpg','pro.jpg','9955WX.jpg','i9.jpg','xeon.jpg']
for i,r in enumerate(D['CPU'][:7]):
 m,multi,single,price,kind,src,bid,u=r;y=215+i*101
 t(c,77,y+40,f'{i+1:02}',22,True,col=TEAL if i<2 else MUT)
 image(c,model_images[i],121,y+4,110,93)
 t(c,252,y+38,m,25,True)
 for x,w,v,mx,color in [(590,275,multi,95566,TEAL),(980,225,single,4690,BLUE)]:
  t(c,x,y+25,f'{v:,}점',23,True,col=color);bar(c,x,y+63,w,v/mx*100,color,12)
 t(c,1425,y+41,money(price),21,col=MUT,align='right')
 line(c,55,y+101,1390)
 url(c,f'https://www.cpubenchmark.net/cpu.php?id={bid}',252,y,620,101);url(c,u,1250,y,195,101);url(c,u,121,y,110,101)
line(c,55,923,1390)
box(c,55,949,1390,64,LIGHT);t(c,78,968,'Xeon Silver × 2',23,True);t(c,382,971,'정확한 모델명 미기재 · 성능 비교 보류',21,col=MUT)
t(c,1425,971,'단품가: VAT 포함',17,col=MUT,align='right')
c.save()

c=canvas.Canvas(str(P/'GPU_성능가격_검토.pdf'),pagesize=(W,H));c.setTitle('GPU 성능 비교')
head(c,'GPU 성능 비교','동일 32GB 용량  |  FP32 이론 연산 성능과 메모리 대역폭 비교')
colors=[TEAL,BLUE,'#7C8B94']
for i,r in enumerate(D['GPU']):
 model,short,fp,bw,price,kind,src,u=r;x=55+i*470;color=colors[i];w=450
 if i==0:fp=104.8
 image(c,['5090palit.jpg','5000.jpg','4500.jpg'][i],x,153,w,236)
 t(c,x+20,411,['GeForce RTX 5090','RTX 5000 Ada','RTX PRO 4500'][i],30,True)
 t(c,x+20,453,['PALIT GAMEROCK D7 32GB','Ada Generation','Blackwell Workstation Edition'][i],17,col=MUT)
 line(c,x,494,w)
 t(c,x+20,520,'FP32 이론 연산 성능',19,True,col=color)
 t(c,x+20,558,f'{fp:.1f}',52,True,col=color);t(c,x+198,586,'TFLOPS',18,col=MUT)
 bar(c,x+20,632,410,fp/104.8*100,color,20)
 t(c,x+20,690,'메모리 대역폭',19,True)
 t(c,x+20,728,f'{bw:,}',36,True);t(c,x+169,743,'GB/s',18,col=MUT)
 bar(c,x+20,787,410,bw/1792*100,color,15)
 line(c,x,838,w)
 t(c,x+20,862,'온라인 단품가',18,col=MUT);t(c,x+428,858,money(price),25,True,align='right')
 t(c,x+20,904,['가격: PALIT GAMEROCK 기준','엔비디아코리아 정품','엔비디아코리아 정품'][i],17,col=MUT)
 url(c,u,x,849,w,80)
 url(c,['https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/','https://www.nvidia.com/en-us/products/workstations/rtx-5000/','https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-4500-blackwell/workstation-datasheet-blackwell-rtx-pro-4500-we-nvidia-us-5108623-web.pdf'][i],x,411,w,410)
box(c,55,965,1390,54,LIGHT);t(c,77,981,'FP32는 이론 성능이며 실제 AI 처리속도와는 다릅니다.',20,col=MUT);t(c,1425,984,'단품가: VAT 포함',17,col=MUT,align='right')
c.save()
for typ in ['CPU','GPU']:
 f=P/f'{typ}_성능가격_검토.pdf'
 with pdfplumber.open(f) as pdf:
  assert len(pdf.pages)==1
  pdf.pages[0].to_image(resolution=120).original.save(f.with_suffix('.png'))
 print(f.resolve())
