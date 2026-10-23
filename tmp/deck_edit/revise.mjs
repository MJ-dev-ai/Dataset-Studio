import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/tnsmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
import {groups} from './data.mjs';
const p=await PresentationFile.importPptx(await FileBlob.load('D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx'));
for(let i=2;i<p.slides.items.length;i++){
 const s=p.slides.items[i];
 const layout=JSON.parse(await (await s.export({format:'layout'})).text());
 for(const e of layout.elements.filter(e=>e.name?.startsWith('case-model-')||e.name?.startsWith('case-photo-status-')))p.delete(e.id);
 const tb=s.tables.items[0];
 for(let j=0;j<groups[i-2].items.length;j++){
  const v=groups[i-2].items[j],c=tb.getCell(7,j+1);
  c.value=v.img?v.case:'제품 이미지 확인 필요\n\n'+v.case;
  c.text.style={fontFamily:'Malgun Gothic',fontSize:14,color:'#254570',alignment:'center',verticalAlignment:v.img?'bottom':'middle'};
  tb.cells.block({row:7,column:j+1,rowCount:1,columnCount:1}).assign({margins:{left:8,right:8,top:0,bottom:4}});
 }
}
await (await PresentationFile.exportPptx(p)).save('tmp/deck_edit/revised_raw.pptx');
