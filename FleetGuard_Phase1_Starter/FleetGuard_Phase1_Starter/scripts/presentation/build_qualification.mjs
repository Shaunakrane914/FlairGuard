// Run from repository root with the bundled presentation runtime; see release README.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const runtime=process.env.RUNTIME_NODE_MODULES;
const skill=process.env.PRESENTATIONS_SKILL_DIR;
if(!runtime||!skill)throw new Error('Set RUNTIME_NODE_MODULES and PRESENTATIONS_SKILL_DIR to the supplied runtime');
const {FileBlob,PresentationFile}=await import(pathToFileURL(path.join(runtime,'@oai/artifact-tool/dist/artifact_tool.mjs')).href);
const repo=process.cwd();
const source=path.join(repo,'1790163819038-Teliport S4_Case Study and Submission Template/Teliport S4_Submission Template.pptx');
const build=path.join(repo,'FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/integration_release/presentation-v1');
const output=path.join(repo,'deliverables/qualification-2026-11-01');
await fs.mkdir(output,{recursive:true});
const finalPath=path.join(output,'FlairGuard_Qualification.pptx');
if(process.argv.includes('--pdf')){
  const p=await PresentationFile.importPptx(await FileBlob.load(finalPath));
  const pdf=await p.export({format:'pdf'});
  await fs.writeFile(path.join(output,'FlairGuard_Qualification.pdf'),new Uint8Array(await pdf.arrayBuffer()),{flag:'wx'});
  const png=await p.export({slide:p.slides.items[0],format:'png',scale:1.5});
  await fs.writeFile(path.join(output,'FlairGuard_Qualification.png'),new Uint8Array(await png.arrayBuffer()),{flag:'wx'});
  process.exit(0);
}
const p=await PresentationFile.importPptx(await FileBlob.load(source));
p.slides.items[0].delete(); // User requested a single qualification slide, with no cover.
const s=p.slides.items[0];
function text(name,value,x,y,w,h,size=18,color='#24374a',bold=false){
  const sh=s.shapes.add({name,geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  sh.text=value;sh.text.insets=0;sh.text.style={fontFamily:'Calibri',fontSize:size,color,bold};return sh;
}
function arrow(x,y){s.shapes.add({name:'Architecture flow',geometry:'rightArrow',position:{left:x,top:y,width:18,height:12},fill:'#058fb8',line:{fill:'none',width:0}});}
text('Case identity','CASE STUDY 1  /  CONNECTED FLEET PREDICTIVE MAINTENANCE',40,91,1180,25,15,'#087ea4',true);
text('Project title','FlairGuard AI',40,120,1200,51,43,'#17354d',true);
text('Problem and objective','Maintenance decisions when telemetry is missing, unreliable or constrained by service capacity',40,175,1200,29,23,'#365269');
text('Blank team fields','Team: __________________    Members: __________________    College: __________________    Team ID: __________',40,212,1200,24,15,'#556b7b');
text('Architecture label','CAUSAL OBSERVATIONS TO AUDITABLE MAINTENANCE ACTIONS',40,253,1200,22,15,'#087ea4',true);
const nodes=[
  ['Telemetry + features','21 sensors, 3 settings\nPast-only rolling windows'],
  ['RUL + anomaly models','LightGBM / HGB / Ridge\nRegime-aware preprocessing'],
  ['Telemetry trust','Missingness, staleness\nPersistence and abstention'],
  ['Rule-based triage','RUL and quality thresholds\nHuman review for exceptions'],
  ['Orders + execution','Priority, deduplication\nSQLite audit and recovery'],
];
for(let i=0;i<nodes.length;i++){
  const x=40+i*244;
  s.shapes.add({name:'Editable architecture node '+i,geometry:'rect',position:{left:x,top:286,width:224,height:91},fill:'#f0f7fb',line:{fill:'#c6dce9',width:1}});
  text('Component '+i,nodes[i][0],x+12,299,203,24,20,'#17354d',true);
  text('Component details '+i,nodes[i][1],x+12,330,203,40,16,'#365269');
  if(i<4)arrow(x+227,325);
}
text('MATLAB role','MATLAB research worker: similarity-based RUL, matched Python comparisons and versioned evidence',40,390,1200,25,19,'#976126');
const columns=[
  ['TRUST','Fit-only normalization and engine-disjoint evaluation. Causal histories prevent future-data leakage. Missing telemetry remains explicit.'],
  ['VALUE','FD002 trigger outage: regime imputation produced 0/80 modeled failures versus 14/80 with bounded countdown. Scenario-specific result.'],
  ['EXECUTION','FastAPI + React operator workflow. Persisted work orders and model pins. Genuine retraining, rollback and backend restart verified.'],
];
for(let i=0;i<3;i++){
  const x=40+i*414;
  text('Evidence heading '+i,columns[i][0],x,442,376,27,21,'#087ea4',true);
  text('Evidence body '+i,columns[i][1],x,478,376,106,20,'#24374a');
}
text('Evaluation coverage','332 full-life policy runs independently scored across 169 source engines. MATLAB comparison runs through the application.',40,603,1200,27,19,'#17354d',true);
text('Limits','Retrospective NASA C-MAPSS study with hypothetical maintenance costs. Advanced-policy superiority and fresh model promotion remain unestablished.',40,644,1200,42,16,'#526b7f');
s.speakerNotes.text='Sources: docs/phase-d/RESULTS.md; artifacts/phase_d/reliability-v1-run002/summary.json, FD002/causal_trigger/reference, regime_impute versus bounded_last, point policy, 80 engines. Failure counts are modeled, not field safety outcomes. Primary cohort has 169 distinct source engines; repeated policy episodes are not independent engines. MATLAB evidence: artifacts/integration_release/matlab-api-v2/report.json and its sealed job outputs, plus final genuine Chromium job workflow. MATLAB/Python serving roles remain distinct. Scientific promotion remains blocked without fresh acceptance labels. All team fields intentionally blank at user request. Architecture uses causal windows 5 and 20, fit-derived regime scaling, quality gates, deterministic thresholds and durable work orders; no LLM is involved. FD001/FD002 serve; FD003/FD004 are retrospective research/browsing. Required qualification format is one slide, as specified by the user.';
const candidate=path.join(build,'candidate-v2.pptx');
await (await PresentationFile.exportPptx(p)).save(candidate);
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
await finalizePresentation({workspaceDir:repo,candidatePath:candidate,finalPath,
  pythonExecutable:process.env.RUNTIME_PYTHON,explicitTotalSlideCount:1,
  integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
  // The blank content slide has no explicit typeface runs. Calibri is selected
  // from its theme, so declare a design font rather than an explicit-run reference.
  fontPolicy:{basis:'design',families:['Calibri']},
  verifyArtifactToolImport:true,receiptPath:path.join(build,'validation-v2.json')});
await fs.writeFile(path.join(build,'layout.json'),await (await s.export({format:'layout'})).text());
console.log(finalPath);
