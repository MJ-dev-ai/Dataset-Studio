import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/tnsmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const p=await PresentationFile.importPptx(await FileBlob.load('output/quotation_comparison/[산자부] 비전 PC 견적 비교 261023_완성.pptx'));
for(let i=0;i<p.slides.items.length;i++)await fs.writeFile(`tmp/deck_edit/final${i+1}.png`,new Uint8Array(await (await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
console.log('Rendered all',p.slides.items.length,'final slides');
