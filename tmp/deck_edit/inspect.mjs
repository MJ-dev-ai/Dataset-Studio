import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/tnsmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const p=await PresentationFile.importPptx(await FileBlob.load('D:/project/산자부/견적/[산자부] 비전 PC 견적 비교 261023.pptx'));
await fs.writeFile('tmp/deck_edit/inspect.txt',(await p.inspect({kind:'slide,textbox,shape,image,table',maxChars:40000})).ndjson);
for(let i=0;i<p.slides.items.length;i++){
const s=p.slides.items[i];
await fs.writeFile(`tmp/deck_edit/before${i+1}.png`,new Uint8Array(await (await s.export({format:'png',scale:1})).arrayBuffer()));
await fs.writeFile(`tmp/deck_edit/layout${i+1}.json`,await (await s.export({format:'layout'})).text());
}
console.log('Imported/rendered',p.slides.items.length);
