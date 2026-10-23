import fs from 'node:fs/promises';
import {FileBlob,PresentationFile} from 'file:///C:/Users/tnsmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
const p=await PresentationFile.importPptx(await FileBlob.load('tmp/deck_edit/candidate_font.pptx'));
for(let i=0;i<p.slides.items.length;i++)await fs.writeFile(`tmp/deck_edit/font${i+1}.png`,new Uint8Array(await (await p.slides.items[i].export({format:'png',scale:1})).arrayBuffer()));
console.log('Rendered all',p.slides.items.length,'final slides');

