import urllib.request,re
from pathlib import Path
urls={'fractal':'https://www.fractal-design.com/products/cases/define-series/define-7-xl/define-7-xl-black-solid/','3rsys':'https://3rshop.co.kr/front/productdetail.php?productcode=023005000000000024'}
for key,url in urls.items():
 try:
  data=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=25).read()
  Path(f'tmp/deck_edit/{key}.html').write_bytes(data)
  s=data.decode('utf-8',errors='replace')
  print(key, re.findall(r'<img[^>]+src=[\"\x27]([^\"\x27]+)',s)[:60])
 except Exception as e: print(key,e)
