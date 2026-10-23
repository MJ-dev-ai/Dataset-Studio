from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import ImageReader
import pdfplumber,json

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'output'/'cpu_gpu_comparison'; OUT.mkdir(parents=True,exist_ok=True)
ASSET=ROOT/'tmp'/'products'
pdfmetrics.registerFont(TTFont('KR','C:/Windows/Fonts/malgun.ttf'))
pdfmetrics.registerFont(TTFont('KRB','C:/Windows/Fonts/malgunbd.ttf'))
W,H=1200,900
INK='#172F3C'; MUTED='#637581'; LINE='#DCE5E8'; BG='#F7F9F9'; TEAL='#127E79'; BLUE='#4276B6'; ORANGE='#BD613F'

def rect(c,x,y,w,h,color,r=0):
 c.setFillColor(HexColor(color));c.setStrokeColor(HexColor(color))
 if r:c.roundRect(x,H-y-h,w,h,r,stroke=0,fill=1)
 else:c.rect(x,H-y-h,w,h,stroke=0,fill=1)
def txt(c,x,y,s,size=14,bold=False,color=INK,align='left'):
 c.setFillColor(HexColor(color));c.setFont('KRB' if bold else 'KR',size)
 fn={'left':c.drawString,'right':c.drawRightString,'center':c.drawCentredString}[align]
 fn(x,H-y-size*.8,str(s))
def line(c,x,y,x2,color=LINE):
 c.setStrokeColor(HexColor(color));c.setLineWidth(.7);c.line(x,H-y,x2,H-y)
def pic(c,name,x,y,w,h):
 c.drawImage(str(ASSET/name),x,H-y-h,width=w,height=h,preserveAspectRatio=True,anchor='c',mask='auto')
def lines(c,x,y,ss,size=13,leading=21,color=MUTED,bold=False):
 for i,s in enumerate(ss):txt(c,x,y+i*leading,s,size,bold,color)
def footer(c,kind,page):
 line(c,44,855,1156);txt(c,44,869,'산자부 비전 PC  |  견적 13건 기준  |  자료 확인 2026.10.23',10,color=MUTED)
 txt(c,1156,869,f'{kind}   {page} / 2',10,color=MUTED,align='right')
def head(c,label,title,sub):
 rect(c,0,0,W,H,'#FFFFFF');txt(c,44,27,label,11,True,TEAL)
 txt(c,44,53,title,31,True);txt(c,44,99,sub,12,color=MUTED)
def link(c,x,y,label,url,size=10):
 txt(c,x,y,label,size,color=BLUE)
 c.linkURL(url,(x,H-y-size-3,x+pdfmetrics.stringWidth(label,'KR',size),H-y+2),relative=0,thickness=0)
def pill(c,x,y,label,color=TEAL,w=38):
 rect(c,x,y,w,27,color,5);txt(c,x+w/2,y+6,label,13,True,'#FFFFFF','center')
def bar(c,x,y,w,val,maxval,color,label):
 rect(c,x,y,w,16,'#EAF0F1',4);rect(c,x,y,max(1,w*val/maxval),16,color,4)
 txt(c,x+w+12,y-1,label,14,True,color)

CPU=[
 dict(model='PRO 7975WX',family='AMD Threadripper',core='32코어 / 64스레드',multi=95566,single=3989,n=196,tier='A',vendor='여의시스템 10/14',id=5729,mem='8채널',pcie='128 (Gen 5)',power='350W',board='sTR5 / PRO',ram='32GB × 4 = 128GB'),
 dict(model='PRO 9965WX',family='AMD Threadripper',core='24코어 / 48스레드',multi=92266,single=4541,n=93,tier='A',vendor='샵다나와 10/08·20, 아싸컴 10/23',id=6804,mem='8채널',pcie='128 (Gen 5)',power='350W',board='sTR5 / WRX90',ram='128GB / 10/20 견적은 64GB'),
 dict(model='7960X',family='AMD Threadripper',core='24코어 / 48스레드',multi=83411,single=4125,n=371,tier='B',vendor='미리내·영재컴퓨터 10/20',id=5792,mem='4채널',pcie='48 (Gen 5)¹',power='350W',board='sTR5 / TRX50',ram='32GB × 4 = 128GB'),
 dict(model='PRO 7965WX',family='AMD Threadripper',core='24코어 / 48스레드',multi=82214,single=4009,n=183,tier='B',vendor='미리내 10/14·16, 영재컴퓨터 10/15',id=5731,mem='8채널',pcie='128 (Gen 5)',power='350W',board='sTR5 / WRX90',ram='16GB × 8 = 128GB'),
 dict(model='PRO 9955WX',family='AMD Threadripper',core='16코어 / 32스레드',multi=66577,single=4526,n=124,tier='C',vendor='샵다나와 10/12',id=6803,mem='8채널',pcie='128 (Gen 5)',power='350W',board='sTR5 / WRX90',ram='32GB × 4 = 128GB'),
 dict(model='Core i9-14900K',family='Intel Core',core='24코어 (8P+16E) / 32스레드',multi=58173,single=4690,n=13918,tier='C',vendor='Advantech 10/07',id=5717,mem='2채널',pcie='20 (Gen 5+4)',power='125 / 253W²',board='LGA1700 / Q670E',ram='32GB × 4 = 128GB'),
 dict(model='Xeon W5-3425',family='Intel Xeon W',core='12코어 / 24스레드',multi=36365,single=3350,n=59,tier='D',vendor='넥스버 10/13',id=5598,mem='8채널',pcie='112 (Gen 5)',power='270 / 324W²',board='LGA4677 / W790',ram='32GB × 4 = 128GB'),
]
COL={'A':'#126C65','B':'#38998D','C':'#5482A2','D':'#7B8790'}

def cpu():
 c=canvas.Canvas(str(OUT/'CPU_성능등급_비교.pdf'),pagesize=(W,H));c.setTitle('비전 PC CPU 성능·플랫폼 등급 비교')
 head(c,'CPU / PERFORMANCE MAP','CPU 성능, 두 축으로 비교','견적 CPU 8종 전체  ·  PassMark 실측 제출 평균  ·  7종 수치 비교 + 1종 등급 보류')
 for name,x,lab in [('pro.jpg',836,'Threadripper PRO 대표'),('i9.jpg',948,'Core i9-14900K'),('xeon.jpg',1060,'Xeon W5-3425')]:
  pic(c,name,x,20,95,78);txt(c,x+47,105,lab,8,False,MUTED,'center')
  image_url={'pro.jpg':'https://www.amazon.com/dp/B0CK2ZQJZ6','i9.jpg':'https://www.panacompu.com/peru/en/product-information/intel-core-i9-14900k-processor-raptor-lake-24-cores-32-threads-60ghz-lga-1700-253w','xeon.jpg':'https://www.jumbo-computer.com/en/products/intel-xeon-w5-3425-tray-processor-12c-24t-30m-cache-3-20-ghz-fclga4677'}[name]
  c.linkURL(image_url,(x,H-110,x+95,H-20),relative=0,thickness=0)
 rect(c,44,137,1112,80,'#EFF5F4',8)
 for x,title,body in [(65,'멀티코어 상위','7975WX · 9965WX'),(438,'단일 스레드 상위','i9-14900K · 9965WX · 9955WX'),(834,'확장성은 별도 판단','Xeon W는 12코어여도 112레인')]:
  txt(c,x,153,title,11,True,TEAL);txt(c,x,177,body,17,True)
 txt(c,44,243,'멀티 등급 / 모델',12,True)
 txt(c,387,243,'멀티코어 처리량',15,True,TEAL);txt(c,803,243,'단일 스레드 처리량',15,True,BLUE)
 txt(c,387,266,'최고점 = 100  |  막대: 상대지수 / 우측: 원점수',10,color=MUTED)
 txt(c,803,266,'최고점 = 100  |  우측: 원점수',10,color=MUTED)
 for i,d in enumerate(CPU):
  y=293+i*57
  if i%2==0:rect(c,44,y-5,1112,55,BG,3)
  pill(c,55,y+7,d['tier'],COL[d['tier']]);txt(c,109,y,('TR '+d['model']) if d['family'].startswith('AMD') else d['model'],18,True)
  txt(c,109,y+28,d['core'],11,color=MUTED)
  bar(c,387,y+13,300,d['multi'],95566,COL[d['tier']],f"{d['multi']:,}")
  txt(c,387+300*d['multi']/95566-7,y+15,f"{d['multi']/95566*100:.0f}",10,True,'#FFFFFF','right')
  bar(c,803,y+13,237,d['single'],4690,BLUE,f"{d['single']:,}")
  txt(c,803+237*d['single']/4690-7,y+15,f"{d['single']/4690*100:.0f}",10,True,'#FFFFFF','right')
 rect(c,44,704,1112,57,'#F4F1EA',6)
 pill(c,55,718,'?', '#978565');txt(c,109,714,'Xeon Silver × 2',18,True)
 txt(c,109,740,'BARO AI · 총 24코어 / 48스레드',10,color=MUTED)
 txt(c,435,722,'상세 모델 미기재 → 점수와 등급 보류',16,True,'#796449')
 lines(c,44,783,[
 'TR = AMD Ryzen Threadripper. 멀티 등급: A 90 이상 / B 80~90 미만 / C 55~80 미만 / D 55 미만. 동일 성능을 뜻하지 않습니다.',
 '벤치마크는 서로 다른 시스템의 제출 평균입니다. 실제 견적 PC의 전력·냉각·메모리 설정 및 비전 검사 처리속도를 보증하지 않습니다.',
 '사진은 식별용 제품 이미지입니다. Threadripper PRO는 계열 대표 사진이며, 견적 시스템 실물 사진이 아닙니다. 상세 사양·출처는 2쪽.'
 ],10,19)
 footer(c,'CPU',1);c.showPage()
 head(c,'CPU / PLATFORM & SOURCES','연산 성능과 확장성은 따로 읽기','CPU 성능 등급은 1쪽 기준  ·  메모리 채널·PCIe는 플랫폼 지원 상한이며 실제 슬롯 배선·장착 구성과 다를 수 있음')
 xs=[44,239,391,493,656,805]
 widths=[195,152,102,163,149,351]
 headers=['CPU','플랫폼 / 소켓','메모리 채널','PCIe 레인','전력 기준','견적 연결 / 장착 RAM']
 rect(c,44,144,1112,34,INK)
 for x,h in zip(xs,headers):txt(c,x+10,154,h,11,True,'#FFFFFF')
 for i,d in enumerate(CPU):
  y=178+i*48
  if i%2==0:rect(c,44,y,1112,48,BG)
  vals=[d['model'],'sTR5 / 보드 미기재' if d['model']=='PRO 7975WX' else d['board'],d['mem'],d['pcie'],d['power']]
  for x,v in zip(xs,vals):txt(c,x+10,y+15,v,11,bold=x==44)
  txt(c,815,y+8,d['vendor'],11);txt(c,815,y+27,d['ram'],10,color=MUTED)
 y=514;rect(c,44,y,1112,42,'#F4F1EA');txt(c,54,y+13,'Xeon Silver × 2',12,True)
 txt(c,249,y+13,'상세 모델·보드 미기재 / 플랫폼 사양 확인 필요',12,color=MUTED)
 txt(c,815,y+7,'BARO AI 10/16',11);txt(c,815,y+25,'64GB × 2 = 128GB',10,color=MUTED)
 lines(c,44,572,[
 '¹ 7960X/TRX50는 Gen 5 사용 가능 레인 48개 기준. Gen 4와 칩셋 레인을 포함한 전체 레인 수와 구분했습니다.',
 '² Intel은 기본 / 최대 터보 전력, AMD는 기본 TDP 표기. 전력 숫자만으로 동일 부하 소비전력을 비교할 수 없습니다.',
 '8채널 지원 CPU라도 DIMM 4개만 장착하면 8채널 전체를 채운 구성이 아닙니다. 여의시스템 보드의 정확한 모델명은 미기재입니다.'
 ],10,18)
 txt(c,44,640,'데이터 출처',14,True)
 txt(c,44,665,'PassMark PerformanceTest V10 · 2026.10.23 조회 / 페이지 표시 10.21~23 · 각 링크에 원점수·표본 수 공개',10,color=MUTED)
 for i,d in enumerate(CPU):
  x=44+(i%2)*560;y=690+(i//2)*23
  link(c,x,y,f"{d['model']}  |  {d['multi']:,} / {d['single']:,}  |  n={d['n']:,}",f"https://www.cpubenchmark.net/cpu.php?id={d['id']}",10)
 link(c,44,791,'AMD 공식: Threadripper 7000 / TRX50 / WRX90', 'https://www.amd.com/en/newsroom/press-releases/2023-10-19-amd-introduces-new-amd-ryzen-threadripper-7000-ser.html',9)
 link(c,604,791,'AMD 공식: Threadripper PRO 9000', 'https://www.amd.com/en/products/processors/workstations/ryzen-threadripper.html',9)
 link(c,44,810,'Intel 공식: i9-14900K / 사양', 'https://www.intel.com/content/www/us/en/products/sku/236773/specifications.html',9)
 link(c,604,810,'Intel 공식: Xeon W5-3425 / 사양', 'https://www.intel.com/content/www/us/en/products/sku/233482/specifications.html',9)
 txt(c,44,831,'사진: Threadripper PRO / Amazon 상품 이미지 · Core i9 / Pana Compu · Xeon W5 / Jumbo Computer. 이미지 출처 링크는 사진에 연결.',8,color=MUTED)
 # Links to image sources are attached to the page-2 caption as separate areas.
 for x,label,url in [(44,'Threadripper','https://www.amazon.com/dp/B0CK2ZQJZ6'),(430,'i9','https://www.panacompu.com/peru/en/product-information/intel-core-i9-14900k-processor-raptor-lake-24-cores-32-threads-60ghz-lga-1700-253w'),(780,'Xeon','https://www.jumbo-computer.com/en/products/intel-xeon-w5-3425-tray-processor-12c-24t-30m-cache-3-20-ghz-fclga4677')]:
  c.linkURL(url,(x,H-844,x+320,H-829),relative=0,thickness=0)
 footer(c,'CPU',2);c.save()

GPUS=[
 dict(name='GeForce RTX 5090',sub='Blackwell · GeForce 최상위',image='5090.jpg',fp=104.9,bw=1792,mem='32GB GDDR7',ecc='메모리 ECC 지원 없음',power='575W',tier='A',color=TEAL,core='21,760',pcie='PCIe 5.0 x16'),
 dict(name='RTX 5000 Ada',sub='Ada Lovelace · 전문가용',image='5000.jpg',fp=65.3,bw=576,mem='32GB GDDR6 ECC',ecc='메모리 ECC 지원',power='250W',tier='B',color=BLUE,core='12,800',pcie='PCIe 4.0 x16'),
 dict(name='RTX PRO 4500',sub='Blackwell · 전문가용 / Workstation Edition',image='4500.jpg',fp=51.0,bw=896,mem='32GB GDDR7 ECC',ecc='메모리 ECC 지원',power='200W',tier='C',color='#9B7742',core='10,496',pcie='PCIe 5.0 x16'),
]
def gpu():
 c=canvas.Canvas(str(OUT/'GPU_성능등급_비교.pdf'),pagesize=(W,H));c.setTitle('비전 PC GPU 성능·사양 등급 비교')
 head(c,'GPU / PERFORMANCE MAP','GPU 급 비교, 같은 32GB라도 다릅니다','견적 GPU 3종 전체  ·  제조사 기준 사양으로 비교  ·  FP32 이론 성능과 메모리 대역폭을 분리')
 for i,d in enumerate(GPUS):
  x=44+i*378
  pic(c,d['image'],x,137,356,187)
  txt(c,x,341,d['name'],25,True);txt(c,x,376,d['sub'],11,color=MUTED)
  pill(c,x,410,d['tier'],d['color']);txt(c,x+49,416,'FP32 기준 순위',11,True,d['color'])
  txt(c,x,456,'FP32 이론 연산 성능',12,True)
  txt(c,x+356,448,f"{d['fp']:.1f}",30,True,d['color'],'right')
  txt(c,x+356,480,'TFLOPS',10,color=MUTED,align='right')
  rect(c,x,501,356,14,'#EAF0F1',4);rect(c,x,501,356*d['fp']/104.9,14,d['color'],4)
  txt(c,x,524,f"5090 대비 {d['fp']/104.9*100:.0f}%",11,color=MUTED)
  txt(c,x,565,'메모리 대역폭',12,True);txt(c,x+356,557,f"{d['bw']:,}",30,True,d['color'],'right')
  txt(c,x+356,589,'GB/s',10,color=MUTED,align='right')
  rect(c,x,610,356,14,'#EAF0F1',4);rect(c,x,610,356*d['bw']/1792,14,d['color'],4)
  txt(c,x,633,f"5090 대비 {d['bw']/1792*100:.0f}%",11,color=MUTED)
  line(c,x,663,x+356)
  txt(c,x,681,d['mem'],15,True);txt(c,x+356,681,d['power'],15,True,INK,'right')
  txt(c,x,707,d['ecc'],10,color=MUTED);txt(c,x+356,707,'레퍼런스 전력',10,color=MUTED,align='right')
 rect(c,44,746,1112,49,'#EFF5F4',6)
 txt(c,62,762,'5090: 연산·대역폭 상위  |  전문가용 2종 간: 5000 Ada는 FP32, PRO 4500은 대역폭 우위',16,True,TEAL)
 lines(c,44,810,[
 'A/B/C는 이 3종의 FP32 사양 순위입니다. 이론 최대치이며 AI 추론 FPS·지연시간·실측 벤치마크 순위를 뜻하지 않습니다.',
 '5090은 NVIDIA 기준 사양에서 계산한 약값(104.9). 사진은 NVIDIA 대표 제품이며 견적의 제조사별 외형과 다릅니다. 출처·매핑은 2쪽.'
 ],10,18)
 footer(c,'GPU',1);c.showPage()
 head(c,'GPU / QUOTE MAPPING & SOURCES','견적별 제품 연결과 비교 기준','RTX 5090 제조사·공랭·수랭 차이는 별도 성능 등급으로 나누지 않음  ·  GPU 미포함 견적도 누락 없이 표시')
 rect(c,44,143,1112,33,INK)
 for x,t in [(54,'GPU'),(320,'견적에 포함된 제품 / 업체'),(930,'분류')]:txt(c,x,153,t,12,True,'#FFFFFF')
 rows=[
 ('RTX 5090','ZOTAC SOLID OC 32GB / 미리내 10/14·16·20','동일 GPU 계열'),
 ('RTX 5090','GIGABYTE AORUS XTREME 워터 블럭 / 영재컴퓨터 10/15·20','수랭 구성'),
 ('RTX 5090','PALIT GAMEROCK / 샵다나와 10/08·12, 아싸컴 10/23','동일 GPU 계열'),
 ('RTX 5090','브랜드·세부 모델 미기재 / 넥스버 10/13, BARO AI 10/16','동일 GPU 계열'),
 ('RTX PRO 4500 Blackwell','샵다나와 10/20 / 32GB','Workstation 사양 기준¹'),
 ('RTX 5000 Ada','여의시스템 10/14 / 32GB','전문가용 GPU'),
 ('GPU 미포함','Advantech 10/07 / RTX 5090 제외 명시','GPU 등급 부여 안 함'),
 ]
 for i,row in enumerate(rows):
  y=176+i*39
  if i%2==0:rect(c,44,y,1112,39,BG)
  for x,t in zip([54,320,930],row):txt(c,x,y+12,t,11,bold=x==54)
 txt(c,44,469,'핵심 사양',14,True)
 specs=[['항목']+[d['name'] for d in GPUS],['CUDA 코어']+[d['core'] for d in GPUS],['인터페이스']+[d['pcie'] for d in GPUS],['메모리']+[d['mem'] for d in GPUS]]
 for i,row in enumerate(specs):
  y=496+i*29
  if i==0:rect(c,44,y,1112,29,'#EAF0F1')
  for j,t in enumerate(row):txt(c,[54,285,604,924][j],y+8,t,11,bold=i==0 or j==0)
 lines(c,44,630,[
 '¹ 견적에는 RTX PRO 4500 Blackwell로 기재. 비교 수치는 Workstation Edition 기준이며 실제 납품 SKU 확인 필요.',
 '5090 FP32 = 21,760 CUDA 코어 × 2 연산/클럭 × 2.41GHz ÷ 1,000 ≈ 104.9 TFLOPS. 반올림 클럭에 기반한 계산값.',
 'GPU 세대·정밀도·희소성 조건이 다른 AI TOPS는 단일 순위로 합산하지 않았습니다. 최종 비전 성능은 동일 모델·입력·배치로 측정해야 합니다.'
 ],10,18)
 txt(c,44,697,'공식 사양·이미지 출처  /  링크 클릭',14,True)
 sources=[
 ('NVIDIA GeForce RTX 5090 · 사양 / 사진','https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/'),
 ('NVIDIA RTX PRO 4500 Workstation · 2026.04 데이터시트 (51 TFLOPS)','https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-4500-blackwell/workstation-datasheet-blackwell-rtx-pro-4500-we-nvidia-us-5108623-web.pdf'),
 ('NVIDIA RTX 5000 Ada · FP32 / 사진','https://www.nvidia.com/en-us/products/workstations/rtx-5000/'),
 ('PNY 공식 제품군 표 · RTX 5000 Ada 대역폭 / 전력','https://www.pny.com/professional/software-solutions/blackwell-architecture?iscommercial=true'),
 ('PALIT 공식 RTX 5090 · 메모리 대역폭','https://www.palit.com/palit/vgapro.php?id=5335&lang=en&pn=NE75090S19R5-GB2020G&tab=sp'),
 ]
 for i,(lab,url) in enumerate(sources):link(c,44,724+i*22,lab,url,10)
 txt(c,44,837,'범위: 제공 ZIP의 견적 13건. 제품 사진 © NVIDIA. 가격은 GPU 부품 단가와 시스템 총액이 혼재하므로 본 성능표에서 제외.',9,color=MUTED)
 footer(c,'GPU',2);c.save()

cpu();gpu()
for path in OUT.glob('*.pdf'):
 with pdfplumber.open(path) as doc:
  for i,page in enumerate(doc.pages):
   page.to_image(resolution=180).original.save(OUT/(path.stem+('_한눈에보기.png' if i==0 else '_상세.png')))
  print(path.name,len(doc.pages),'pages')
print(str(OUT))
