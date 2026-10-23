from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import pdfplumber
P=Path(__file__).resolve().parent.parent/'output'/'cpu_gpu_comparison'
pdfmetrics.registerFont(TTFont('R','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('B','C:/Windows/Fonts/malgunbd.ttf'))
W,H=842,595
NAVY='#263D52';GRAY='#65717C';LIGHT='#E4E8EC';WHITE='#FFFFFF'
def text(c,x,y,t,s=10,b=False,col=NAVY,right=False):
 c.setFont('B' if b else 'R',s);c.setFillColor(HexColor(col));(c.drawRightString if right else c.drawString)(x,H-y-s*.8,str(t))
def box(c,x,y,w,h,col):
 c.setFillColor(HexColor(col));c.rect(x,H-y-h,w,h,fill=1,stroke=0)
def rule(c,y,x=38,x2=804,col=LIGHT):
 c.setStrokeColor(HexColor(col));c.setLineWidth(.5);c.line(x,H-y,x2,H-y)
def header(c,title,sub):
 text(c,38,26,'산자부 비전 PC  |  견적 검토 참고자료',9,col=GRAY)
 text(c,804,26,'2026.10.23',9,col=GRAY,right=True)
 text(c,38,52,title,24,True);text(c,38,88,sub,10,col=GRAY);rule(c,111,col=NAVY)
def note(c,y,rows):
 for i,t in enumerate(rows):text(c,38,y+i*14,t,8,col=GRAY)
def link(c,x,y,label,url,s=8):
 text(c,x,y,label,s,col=GRAY)
 c.linkURL(url,(x,H-y-s-2,x+pdfmetrics.stringWidth(label,'R',s),H-y+2),relative=0,thickness=0)
def mini(c,x,y,label,value,maxv=100,width=150,color=NAVY):
 text(c,x,y,label,9);box(c,x+120,y+1,width*value/maxv,9,color);text(c,x+120+width+30,y,f'{value:.1f}',9,True,right=True)
def finish(c):
 rule(c,570);text(c,38,580,'가격: 제공 견적 기준 / VAT 포함  |  성능 자료 확인일: 2026.10.23',8,col=GRAY);text(c,804,580,'1 / 1',8,col=GRAY,right=True);c.save()

# Model, multi, single, unit price KRW incl. VAT, system range, price source, PassMark ID
cpu=[
 ('TR PRO 7975WX',95566,3989,None,'4,400.0','여의시스템 10/14',5729),
 ('TR PRO 9965WX',92266,4541,4895000,'2,437.3~3,231.3','샵다나와 10/08·20',6804),
 ('TR 7960X',83411,4125,2156000,'2,732.4~2,842.0','영재컴퓨터 10/20',5792),
 ('TR PRO 7965WX',82214,4009,4493137,'3,145.3~3,523.3','영재컴퓨터 10/15',5731),
 ('TR PRO 9955WX',66577,4526,2789000,'3,020.7','샵다나와 10/12',6803),
 ('Core i9-14900K',58173,4690,None,'1,100.0¹','Advantech 10/07',5717),
 ('Xeon W5-3425',36365,3350,None,'3,278.0','넥스버 10/13',5598),
 ('Xeon Silver × 2',None,None,None,'4,430.0','BARO AI 10/16',None)]
c=canvas.Canvas(str(P/'CPU_성능가격_검토.pdf'),pagesize=(W,H));c.setTitle('CPU 성능 및 가격 검토')
header(c,'CPU 성능 및 가격 검토','견적 CPU 8종 비교  |  성능은 멀티·싱글을 구분하고, 가격은 부품 단가와 시스템 총액을 분리')
text(c,38,126,'1. 성능 및 견적 가격',12,True);text(c,804,129,'금액 단위: 만원',9,col=GRAY,right=True)
box(c,38,151,766,27,'#F0F2F4')
for x,t in [(47,'CPU'),(257,'멀티 점수'),(333,'싱글 점수'),(423,'CPU 단가'),(570,'시스템 총액'),(644,'단가 출처 / 미공개 시 견적')]:text(c,x,159,t,9,True,right=x in [257,333,423,570])
for i,(m,multi,single,price,system,src,bid) in enumerate(cpu):
 y=178+i*25;rule(c,y+25)
 text(c,47,y+8,m,10,True)
 if bid:c.linkURL(f'https://www.cpubenchmark.net/cpu.php?id={bid}',(47,H-y-23,195,H-y),relative=0,thickness=0)
 for x,v in [(257,f'{multi:,}' if multi else '미확인'),(333,f'{single:,}' if single else '미확인'),(423,f'{price/10000:,.1f}' if price else '미공개'),(570,system)]:text(c,x,y+8,v,10,right=True)
 text(c,644,y+8,src,9,col=GRAY)
text(c,38,397,'2. CPU 단가 대비 멀티 성능',12,True);text(c,445,397,'검토 요점',12,True)
available=sorted([r for r in cpu if r[3]],key=lambda r:r[1]/r[3],reverse=True)
base=83411/2156000
for i,r in enumerate(available):mini(c,47,422+i*19,r[0],r[1]/r[3]/base*100,width=180)
for i,t in enumerate(['멀티 성능: 7975WX·9965WX가 비교군 상위.', '싱글 성능: i9-14900K가 비교군 최고.', '단가 공개 4종 중 7960X의 멀티 성능/가격이 가장 높음.', '7965WX의 PRO 기능·확장성 가치는 이 지수에 미반영.']):text(c,445,422+i*19,t,9)
note(c,509,[
 '계산: (CPU Mark ÷ VAT 포함 CPU 단가)를 7960X=100으로 환산. 단가 미공개 모델은 계산 제외. TR = AMD Ryzen Threadripper.',
 '¹ Advantech는 GPU 제외. 시스템 총액 범위는 이전 견적·RAM 64GB 구성 등을 포함하므로 총액 기반 가성비 순위는 계산하지 않음.',
 '단가는 견적 내 부품 금액이며 현재 소매 시세가 아님. 영재컴퓨터 공급가에 VAT 10% 가산. 날짜는 파일명 기준.',
 '성능 출처: PassMark PerformanceTest V10, 2026.10.23 조회값(모델명 클릭). 서로 다른 시스템의 평균이며 실제 검사 속도와 다름.'
]);finish(c)

c=canvas.Canvas(str(P/'GPU_성능가격_검토.pdf'),pagesize=(W,H));c.setTitle('GPU 성능 및 가격 검토')
header(c,'GPU 성능 및 가격 검토','견적 GPU 3종 비교  |  FP32 이론 연산 성능·메모리 대역폭·공개 부품 단가 중심')
text(c,38,126,'1. 성능 및 부품 견적 가격',12,True);text(c,804,129,'금액 단위: 만원',9,col=GRAY,right=True)
box(c,38,151,766,34,'#F0F2F4')
for x,t in [(47,'GPU'),(303,'FP32¹'),(423,'메모리 대역폭'),(552,'GPU 단가'),(588,'가격 출처')]:text(c,x,161,t,9,True,right=x in [303,423,552])
rows=[('GeForce RTX 5090','104.9 TFLOPS','1,792 GB/s','1,120.0~1,210.0','샵다나와 10/08·12 / 영재 10/15·20'),('RTX 5000 Ada','65.3 TFLOPS','576 GB/s','미공개','여의시스템 10/14: 시스템 4,400.0'),('RTX PRO 4500 Blackwell','51.0 TFLOPS','896 GB/s','911.8','샵다나와 10/20')]
for i,r in enumerate(rows):
 y=185+i*39
 for x,v in zip([47,303,423,552,588],r):text(c,x,y+14,v,10 if x!=588 else 8.5,b=x==47,right=x in [303,423,552])
 rule(c,y+39)
text(c,38,322,'2. FP32 이론 성능 비교',12,True);text(c,445,322,'3. 공개 단가 대비 FP32 성능',12,True)
for i,(m,v) in enumerate([('RTX 5090',104.9),('RTX 5000 Ada',65.3),('RTX PRO 4500',51)]):mini(c,47,350+i*25,m,v/104.9*100,width=180)
for i,(m,v) in enumerate([('RTX 5090',100),('RTX PRO 4500',(51/9118000)/(104.9/11200000)*100)]):mini(c,445,350+i*25,m,v,width=170)
text(c,445,400,'RTX 5000 Ada: 단가 미공개로 계산 제외',9,col=GRAY)
text(c,38,435,'검토 요점',12,True)
text(c,38,459,'5090은 FP32·대역폭 모두 상위. 공개 최저 단가 기준의 FP32/가격도 4500보다 높음.',10)
text(c,38,478,'5000 Ada는 4500보다 FP32가 높고, 4500은 대역폭이 높음. 실제 AI 처리속도 순위와는 구분해야 함.',10)
note(c,505,[
 '¹ FP32는 이론 최대치. 5090: 21,760 × 2 × 2.41GHz로 계산. 4500: NVIDIA Workstation Edition 자료(51 TFLOPS) 기준.',
 '가격대비 지수: FP32 ÷ VAT 포함 GPU 단가, 5090=100. 5090은 공개 최저 단가 1,120만원 적용(수랭 1,210만원 별도).',
 '견적 부품 가격을 사용했으며 현재 소매 시세가 아님. 5000 Ada의 4,400만원은 PC 전체 가격으로 GPU 단가 계산에 사용하지 않음.'
])
link(c,38,549,'출처: NVIDIA 5090', 'https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/')
link(c,175,549,'NVIDIA 5000 Ada','https://www.nvidia.com/en-us/products/workstations/rtx-5000/')
link(c,309,549,'NVIDIA 4500 데이터시트','https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-4500-blackwell/workstation-datasheet-blackwell-rtx-pro-4500-we-nvidia-us-5108623-web.pdf')
link(c,480,549,'PNY 사양표','https://www.pny.com/professional/software-solutions/blackwell-architecture?iscommercial=true')
link(c,580,549,'PALIT 5090 대역폭','https://www.palit.com/palit/vgapro.php?id=5335&lang=en&pn=NE75090S19R5-GB2020G&tab=sp')
finish(c)
for typ in ['CPU','GPU']:
 f=P/(typ+'_성능가격_검토.pdf')
 with pdfplumber.open(f) as pdf:pdf.pages[0].to_image(resolution=200).original.save(f.with_suffix('.png'))
 print(f)
