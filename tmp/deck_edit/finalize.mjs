import fs from 'node:fs/promises';
import {finalizePresentation} from 'file:///C:/Users/tnsmi/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11618/skills/presentations/container_tools/artifact_tool_utils.mjs';
const root='C:/Users/tnsmi/Downloads/Dataset-Editor', skill='C:/Users/tnsmi/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11618/skills/presentations';
await fs.mkdir(root+'/output/quotation_comparison',{recursive:true});
const result=await finalizePresentation({workspaceDir:root,candidatePath:root+'/tmp/deck_edit/candidate.pptx',finalPath:root+'/output/quotation_comparison/[산자부] 비전 PC 견적 비교 261023_완성.pptx',pythonExecutable:'C:/Users/tnsmi/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',explicitTotalSlideCount:8,requiredNativeTableOwnerSlides:[3,4,5,6,7,8],layoutArgs:['--expected-slide-size-emu','12192000,6858000',...[3,4,5,6,7,8].flatMap(n=>['--require-native-table-slide',String(n)])],verifyArtifactToolImport:true,receiptPath:root+'/tmp/deck_edit/validation.json'});
console.log(JSON.stringify(result));

