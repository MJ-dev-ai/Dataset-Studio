exec(open('tmp/build_price_reports.py',encoding='utf-8').read().split('# Model, multi')[0])
import json
def finish(c):
 rule(c,570);text(c,38,580,'온라인 단품 판매가 · VAT 포함 · 배송비 제외  |  조회일: 2026.10.23  |  가격은 변동될 수 있음',8,col=GRAY)
 text(c,804,580,'1 / 1',8,col=GRAY,right=True);c.save()
def dan(n):return f'https://prod.danawa.com/info/?pcode={n}'
def comp(n):return f'https://www.compuzone.co.kr/product/product_detail.htm?ProductNo={n}'
# Prices exclude delivery; no card, cash-only, membership or point deductions.
cpu=[
 ('TR PRO 7975WX',95566,3989,6085060,'멀티팩 정품','다나와 / 컴오아시스',5729,dan(30143105)),
 ('TR PRO 9965WX',92266,4541,4509840,'멀티팩 정품','다나와 / 11번가',6804,dan(94690922)),
 ('TR 7960X',83411,4125,1960880,'멀티팩 정품','다나와 / 11번가',5792,dan(72593030)),
 ('TR PRO 7965WX',82214,4009,4210650,'멀티팩 정품','다나와 / G마켓',5731,dan(30143039)),
 ('TR PRO 9955WX',66577,4526,2588270,'멀티팩 정품','다나와 / 11번가',6803,dan(94691237)),
 ('Core i9-14900K',58173,4690,765000,'정품 박스','다나와 / 에프에이치디',5717,dan(28798964)),
 ('Xeon W5-3425',36365,3350,2398000,'Tray·주문 수입','컴퓨존',5598,comp(1137513)),
 ('Xeon Silver × 2',None,None,None,'모델명 미기재','정확한 모델 확인 필요',None,None)]
c=canvas.Canvas(str(P/'CPU_성능가격_검토.pdf'),pagesize=(W,H));c.setTitle('CPU 온라인 단품 가격 및 성능 비교')
header(c,'CPU 성능·가격 비교','견적에 포함된 CPU 8개 구성  |  온라인 단품 판매가로 환산한 성능 및 가성비 비교')
text(c,38,126,'1. 성능 및 온라인 단품 가격',12,True);text(c,804,129,'가격 단위: 원 / 1개',9,col=GRAY,right=True)
box(c,38,151,766,27,'#F0F2F4')
for x,t in [(47,'CPU'),(267,'멀티 점수'),(342,'싱글 점수'),(455,'단품 판매가'),(480,'유통 형태'),(618,'가격 출처 ↗')]:text(c,x,159,t,9,True,right=x in [267,342,455])
for i,(m,multi,single,price,kind,src,bid,url) in enumerate(cpu):
 y=178+i*24;rule(c,y+24);text(c,47,y+8,m,10,True)
 if bid:c.linkURL(f'https://www.cpubenchmark.net/cpu.php?id={bid}',(47,H-y-22,195,H-y),relative=0,thickness=0)
 for x,v in [(267,f'{multi:,}' if multi else '—'),(342,f'{single:,}' if single else '—'),(455,f'{price:,}' if price else '산정 불가')]:text(c,x,y+8,v,10,right=True)
 text(c,480,y+8,kind,9,col=GRAY)
 if url:link(c,618,y+8,src,url,9)
 else:text(c,618,y+8,src,9,col=GRAY)
text(c,38,386,'2. 멀티 성능 / 가격 지수',12,True);text(c,445,386,'검토 요점',12,True)
available=sorted([r for r in cpu if r[3]],key=lambda r:r[1]/r[3],reverse=True);base=available[0][1]/available[0][3]
for i,r in enumerate(available):mini(c,47,410+i*14,r[0],r[1]/r[3]/base*100,width=180)
for i,t in enumerate(['단품 가성비: i9-14900K > 7960X > 9955WX.', 'Threadripper 5종 중 가성비는 7960X가 가장 높음.', '멀티 성능은 7975WX·9965WX가 상위.', '9965WX는 7975WX 성능의 약 97%, 가격은 약 74%.', '인텔은 별도 플랫폼이므로 확장성 조건을 함께 검토.']):text(c,445,411+i*19,t,9)
note(c,514,[
 '지수 = CPU Mark ÷ 단품 가격, 비교군 최고(i9-14900K)=100. 메인보드·RAM·전력·확장성 비용은 미반영.',
 '가격은 신품 대표 판매가. 카드·현금 전용 할인, 쿠폰·멤버십·적립금 제외. 7975WX·i9는 배송비 3,000원을 차감.',
 'W5-3425는 주문 수입형 Tray(입고 2일~5주 안내). Xeon Silver는 모델 불명으로 가격·성능 및 가성비 산정 제외.',
 '성능: PassMark V10 평균(모델명 클릭). 가격: 출처 클릭. TR = AMD Ryzen Threadripper. 실사용 검사속도와 다를 수 있음.'
]);finish(c)

gpu=[
 ('GeForce RTX 5090','RTX 5090',104.9,1792,11187000,'PALIT GAMEROCK / 이엠텍','에누리 / 하이마트','https://price.enuri.com/catalog/131695974'),
 ('RTX 5000 Ada','RTX 5000 Ada',65.3,576,7205000,'엔비디아코리아 정품','컴퓨존',comp(1115947)),
 ('RTX PRO 4500 Blackwell','RTX PRO 4500',51.,896,8200000,'엔비디아코리아 정품','컴퓨존',comp(1294644))]
c=canvas.Canvas(str(P/'GPU_성능가격_검토.pdf'),pagesize=(W,H));c.setTitle('GPU 온라인 단품 가격 및 성능 비교')
header(c,'GPU 성능·가격 비교','견적에 포함된 GPU 3종  |  동일 32GB 용량 · 온라인 단품 판매가 · FP32 이론 성능 기준')
text(c,38,126,'1. 성능 및 온라인 단품 가격',12,True);text(c,804,129,'가격 단위: 원 / 1개',9,col=GRAY,right=True)
box(c,38,151,766,31,'#F0F2F4')
for x,t in [(47,'GPU / 비교 가격에 적용한 제품'),(344,'FP32'),(451,'대역폭'),(580,'단품 판매가'),(616,'가격 출처 ↗')]:text(c,x,161,t,9,True,right=x in [344,451,580])
for i,(m,short,fp,bw,price,kind,src,url) in enumerate(gpu):
 y=182+i*42;text(c,47,y+8,m,11,True);text(c,47,y+24,kind,8,col=GRAY)
 for x,v in [(344,f'{fp:.1f} TFLOPS'),(451,f'{bw:,} GB/s'),(580,f'{price:,}')]:text(c,x,y+16,v,10,right=True)
 link(c,616,y+16,src,url,9);rule(c,y+42)
text(c,38,328,'2. FP32 이론 성능 지수',12,True);text(c,445,328,'3. FP32 성능 / 가격 지수',12,True)
base=max(r[2]/r[4] for r in gpu)
for i,r in enumerate(gpu):
 mini(c,47,356+i*25,r[1],r[2]/104.9*100,width=180)
 mini(c,445,356+i*25,r[1],r[2]/r[4]/base*100,width=170)
text(c,38,443,'검토 요점',12,True)
text(c,38,466,'5090은 이론 성능·대역폭 모두 상위. 단품 가격 대비 FP32 성능도 비교군에서 가장 높음.',10)
text(c,38,485,'5000 Ada는 5090 대비 가격 약 64%, FP32 약 62%로 가성비가 근접. 4500은 대역폭에서 Ada보다 우위.',10)
note(c,514,[
 '성능·가성비 지수는 각각 비교군 최고=100. 가격은 신품 국내 정품 대표 판매가이며 카드·쿠폰·멤버십·적립금 할인 제외.',
 '5090은 견적에 포함된 PALIT GAMEROCK을 가격 기준으로 선정. ZOTAC·AORUS 등 제조사별 가격·냉각 비용은 다름.',
 'FP32는 이론 최대치이며 AI 실측 처리속도가 아님. 5090은 21,760×2×2.41GHz, 4500은 최신 NVIDIA 자료(51 TFLOPS) 적용.'
])
link(c,38,556,'사양: NVIDIA RTX 5090','https://www.nvidia.com/en-gb/geforce/graphics-cards/50-series/rtx-5090/')
link(c,214,556,'NVIDIA RTX 5000 Ada','https://www.nvidia.com/en-us/products/workstations/rtx-5000/')
link(c,385,556,'NVIDIA RTX PRO 4500 데이터시트','https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-4500-blackwell/workstation-datasheet-blackwell-rtx-pro-4500-we-nvidia-us-5108623-web.pdf')
finish(c)
for typ in ['CPU','GPU']:
 f=P/(typ+'_성능가격_검토.pdf')
 with pdfplumber.open(f) as pdf:
  assert len(pdf.pages)==1
  pdf.pages[0].to_image(resolution=200).original.save(f.with_suffix('.png'))
 print(f)
(P/'온라인가격_조회근거.json').write_text(json.dumps({'date':'2026-10-23','basis':'VAT 포함 단품, 배송비 제외, 일반 판매가; 검색 요약 대신 상품 페이지 재조회','CPU':cpu,'GPU':gpu},ensure_ascii=False,indent=2),encoding='utf-8')
