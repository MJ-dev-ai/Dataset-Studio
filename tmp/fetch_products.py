import urllib.request,re,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
p=Path('tmp/products');p.mkdir(exist_ok=True)
urls={
'amd':'https://www.amd.com/en/products/processors/workstations/ryzen-threadripper.html',
'intel':'https://www.intel.com/content/www/us/en/products/sku/236773/intel-core-i9-processor-14900k-36m-cache-up-to-6-00-ghz/specifications.html',
'xeon':'https://www.intel.com/content/www/us/en/products/sku/233482/intel-xeon-w53425-processor-30m-cache-3-20-ghz/specifications.html',
'4500':'https://www.nvidia.com/en-eu/products/workstations/professional-desktop-gpus/rtx-pro-4500/',
'5090':'https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/',
'5000':'https://www.nvidia.com/en-us/products/workstations/rtx-5000/'}
def fetch(kv):
 k,u=kv
 try:
  h=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=35).read().decode()
  (p/(k+'.html')).write_text(h,encoding='utf-8')
  imgs=list(dict.fromkeys(re.findall(r'(?:src|content|data-src)=[\"\x27]([^\"\x27]+\.(?:png|jpg|jpeg|webp)(?:\?[^\"\x27]*)?)',h)))
  return k,imgs
 except Exception as e:return k,str(e)
for r in ThreadPoolExecutor(6).map(fetch,urls.items()):print(json.dumps(r,ensure_ascii=False))
