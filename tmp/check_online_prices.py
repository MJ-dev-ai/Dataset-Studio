import urllib.request,re,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from html import unescape
p=Path('tmp/online_prices');p.mkdir(exist_ok=True)
urls={str(n):f'https://www.compuzone.co.kr/product/product_detail.htm?ProductNo={n}' for n in [1137513,1115947,1294644]}
def fetch(kv):
 k,u=kv
 try:
  raw=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read()
  h=raw.decode('euc-kr',errors='replace');t=unescape(re.sub('<[^>]+>',' ',h));t=re.sub(r'\s+',' ',t)
  (p/(k+'.txt')).write_text(t,encoding='utf-8')
  return k,[(s,t[max(0,m.start()-100):m.start()+350]) for s in ['판매가','부가세','상품번호'] for m in list(re.finditer(s,t))[:2]]
 except Exception as e:return k,str(e)
for r in ThreadPoolExecutor(3).map(fetch,urls.items()):print(json.dumps(r,ensure_ascii=False))
