import urllib.request,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
p=Path('tmp/products')
urls={
'7975WX.jpg':'https://img.danuri.io/catalog-image/105/143/030/dc5b3d8c6fea4b97846f1cfade4d491d.jpg',
'9965WX.jpg':'https://img.danuri.io/catalog-image/922/690/094/632b865feff143f288cad85a4e768357.jpg',
'7960X.jpg':'https://img.danuri.io/catalog-image/030/593/072/6c932e93f7af47f7b35a88636aaf9579.jpg',
'9955WX.jpg':'https://img.danuri.io/catalog-image/237/691/094/009933c033a94ccbab0cdb5a846e4af6.jpg',
'5090palit.jpg':'https://img.danuri.io/catalog-image/490/376/075/997455cee3f6412497311070e713ab9b.jpg'}
def get(kv):
 k,u=kv
 try:
  data=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read();(p/k).write_bytes(data);return k,len(data)
 except Exception as e:return k,str(e)
print(list(ThreadPoolExecutor(5).map(get,urls.items())))
(p/'model_image_sources.json').write_text(json.dumps(urls,indent=2),encoding='utf-8')
