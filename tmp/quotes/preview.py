from pathlib import Path
import pdfplumber
from PIL import Image, ImageDraw
p=Path(__file__).parent
files=[f for f in p.glob('*.pdf') if '견적서' in f.name]
for start in range(0,len(files),4):
    board=Image.new('RGB',(1400,2020),'#dddddd')
    for j,f in enumerate(files[start:start+4]):
        with pdfplumber.open(f) as pdf:
            im=pdf.pages[0].to_image(resolution=105).original
            im.thumbnail((690,970))
            x=(j%2)*700;y=(j//2)*1010
            board.paste(im,(x,y+30))
            ImageDraw.Draw(board).text((x+8,y+8),str(start+j+1),fill='black')
    board.save(p/f'preview{start//4}.png')
print('\n'.join(f'{i+1}: {f.name}' for i,f in enumerate(files)))
