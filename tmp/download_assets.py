import urllib.request,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
p=Path('tmp/products')
urls={
'amd.jpg':'https://www.amd.com/content/dam/amd/en/images/products/processors/3513563-threadripper-9000-series.jpg',
'i9.jpg':'https://cdn.panacompu.com/cdn-img/pv/bx8071514900k-box-view.jpg?fixedwidthheight=true&height=400&width=400',
'4500.jpg':'https://www.nvidia.com/content/dam/en-zz/Solutions/data-center/rtx-pro-4500-blackwell/nvidia-workstation-rtx4500-og-1200x630.jpg',
'5000.jpg':'https://www.nvidia.com/content/dam/en-zz/Solutions/design-visualization/rtx-5000/rtx-5000-og.jpg',
'5090.jpg':'https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/graphic-cards/50-series/rtx-5090/geforce-rtx-5090-learn-more-og-1200x630.jpg'}
def get(kv):
 k,u=kv
 try:
  data=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read();(p/k).write_bytes(data);return k,len(data)
 except Exception as e:return k,str(e)
print(list(ThreadPoolExecutor(5).map(get,urls.items())))
(p/'image_sources.json').write_text(json.dumps(urls,ensure_ascii=False,indent=2),encoding='utf-8')
