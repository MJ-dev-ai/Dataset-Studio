import urllib.request,re,html,json
from pathlib import Path
urls={'fractal.jpg':'https://assets.fractal-design.com/images/uxzbxy2o/production/83748af2554874114150a0e6422345afce028c34-2560x2560.jpg?w=640&q=90','t3000.jpg':'https://3rshop.co.kr/data/shopimages/product/0230050000000000241.jpg'}
s=Path('tmp/deck_edit/3rsys.html').read_text(encoding='utf-8',errors='replace')
print('\n'.join(sorted(set(re.findall(r'[^\s\"\x27<>]*\.(?:jpg|png)',s)))[:60]))
for name,u in urls.items():
 data=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=20).read();Path('tmp/deck_edit/'+name).write_bytes(data)
Path('tmp/deck_edit/image_sources.json').write_text(json.dumps(urls),encoding='utf-8')
