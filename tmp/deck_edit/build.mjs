import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/tnsmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
import {groups} from './data.mjs';
const p=await PresentationFile.importPptx(await FileBlob.load('D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx'));
const base=p.slides.items[2];
const slides=[base];for(let i=1;i<groups.length;i++)slides.push(base.duplicate());
const BG='#EFF5FC', BLUE='#114A9F', TEXT='#254570';
function text(s,name,value,x,y,w,h,size=16,align='left',color=TEXT){const o=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});o.text=value;o.text.style={fontFamily:'Pretendard Medium',fontSize:size,color,alignment:align,verticalAlignment:'middle',insets:0,wrap:'word'};return o;}
// Extend the existing section subtitle to reflect all supplied quotation groups.
const section=p.slides.items[1].shapes.items.find(s=>s.name==='TextBox 1079933329');
section.text=[{runs:[{run:'CPU 별 견적 비교',style:{fontSize:'52pt',typeface:'Pretendard Black',color:'#FFFFFF'}}]}, {runs:[{run:' ',style:{fontSize:'18pt'}}]}, {runs:[{run:'7960X / 7965WX / 9955WX / 9965WX',style:{fontSize:'20pt',typeface:'Pretendard Medium',color:'#DDEAFE'}}]}, {runs:[{run:'Intel 시스템 / 7975WX 참고',style:{fontSize:'20pt',typeface:'Pretendard Medium',color:'#DDEAFE'}}]}];
section.position={left:68.44,top:281.64,width:1040,height:220};
const keys=['cpu','gpu','board','ram','ssd','power','case','price','delivery','diff'];
const labels=['CPU','GPU','메인보드','메모리','저장장치','전원','케이스','견적 금액\n(VAT 별도)','납기','주요 차이점'];
const heights=[44,36,40,30,40,40,40,122,40,30,40];
for(let g=0;g<groups.length;g++){
 const s=slides[g],d=groups[g];
 const layout=JSON.parse(await (await s.export({format:'layout'})).text());
 for(const tb of layout.elements.filter(e=>e.kind==='table'))p.delete(tb.id);
 s.shapes.items.find(o=>o.name==='TextBox 518989947').text=d.title;
 s.shapes.items.find(o=>o.name==='TextBox 518989947').position={left:22.22,top:99.95,width:1170,height:42.01};
 s.shapes.items.find(o=>o.name==='TextBox 1953928640').text=String(g+3);
 const count=d.items.length, labelW=154,colW=(1229.34-labelW)/count;
 const values=[['',...d.items.map(x=>x.vendor)],...keys.map((k,r)=>[labels[r],...d.items.map(x=>k==='case'?'':x[k])])];
 const table=s.tables.add({rows:11,columns:count+1,left:22.22,top:148,width:1229.34,height:heights.reduce((a,b)=>a+b),columnWidths:[labelW,...d.items.map(()=>colW)],values});
 table.styleOptions={headerRow:false,bandedRows:false,firstColumn:false};
 table.borders.assign({fill:'#B6CCE9',width:0.7,style:'solid'});
 table.cells.block({row:0,column:0,rowCount:11,columnCount:count+1}).assign({margins:{left:10,right:8,top:0,bottom:0}});
 for(let r=0;r<11;r++){
  table.rows[r].height=heights[r];
  for(let j=0;j<count+1;j++){
   const cell=table.getCell(r,j);cell.fill=r===0?BLUE:r%2===0?BG:'#FFFFFF';
   cell.text.style={fontFamily:r===0?'Pretendard SemiBold':'Pretendard Medium',fontSize:r===0?17:j===0?16:r===8?18:15,color:r===0?'#FFFFFF':TEXT,bold:r===0||j===0||r===8,alignment:r===0?'center':'left',verticalAlignment:'middle'};
  }
 }
 const cy=148+heights.slice(0,7).reduce((a,b)=>a+b,0);
 for(let j=0;j<count;j++){
  const v=d.items[j],x=22.22+labelW+j*colW;
  if(v.img){
   const bytes=await fs.readFile('tmp/deck_edit/'+v.img);
   s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:v.img.endsWith('.png')?'image/png':'image/jpeg',alt:v.case,fit:'contain',position:{left:x+(colW-142)/2,top:cy+5,width:142,height:82}});
  } else text(s,'case-photo-status-'+j,'제품 이미지 확인 필요',x+8,cy+18,colW-16,52,16,'center','#6B7280');
  text(s,'case-model-'+j,v.case,x+8,cy+90,colW-16,30,14,'center');
 }
 if(d.note)text(s,'vat-calculation',d.note,22.22,653,1210,22,13,'left','#6B7280');
 s.speakerNotes.text='견적 원문: '+d.items.map(x=>x.source).join('; ')+'\n표기 원칙: 유통사명, 포장형태, CPU 코드명은 생략. ECC/REG는 ECC RDIMM으로 통일. 부품 수량과 용량은 견적 원문 유지. 납기·모델 미기재는 임의 보완하지 않음.\n케이스 이미지: https://www.fractal-design.com/products/cases/define-series/define-7-xl/define-7-xl-black-solid/ ; https://3rshop.co.kr/front/productdetail.php?productcode=023005000000000024 ; [산자부] Advantech IPS-730 Specsheet.pdf. 영재컴퓨터는 패널형 미기재로 Solid 사진을 참고로 표시. T3000 공식 연출 사진의 내부 부품은 견적 구성과 다를 수 있음. 넥스버/BARO AI/여의시스템은 정확한 케이스 사진 확인 불가.\n'+(d.note??'');
 await fs.writeFile(`tmp/deck_edit/after${g+3}.png`,new Uint8Array(await (await s.export({format:'png',scale:1})).arrayBuffer()));
}
const ids=[];for(const s of [p.slides.items[0],p.slides.items[1],...slides])ids.push(JSON.parse(await (await s.export({format:'layout'})).text()).slide.id);
p.slides.reorder(ids);
await fs.writeFile('tmp/deck_edit/after2.png',new Uint8Array(await (await p.slides.items[1].export({format:'png',scale:1})).arrayBuffer()));
await (await PresentationFile.exportPptx(p)).save('tmp/deck_edit/candidate.pptx');
console.log('Saved',p.slides.items.length,'slides');
