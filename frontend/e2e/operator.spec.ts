import {test,expect} from '@playwright/test';
import {spawn,ChildProcess} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const project=path.resolve('../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter');
const output=process.env.PHASE_D_BROWSER_OUTPUT || path.join(project,'artifacts/phase_d/browser-v1-run001');
const key=crypto.randomBytes(24).toString('hex');
const base='http://127.0.0.1:8031';
let server:ChildProcess;
let log:fs.WriteStream;
async function start(){
  server=spawn(process.env.PHASE_D_PYTHON || 'python',['-m','uvicorn','flairguard.service.app:app','--host','127.0.0.1','--port','8031'],
    {cwd:project,env:{...process.env,FLAIRGUARD_DB_PATH:path.join(output,'storage/platform.db'),
      FLAIRGUARD_API_KEY:key,FLAIRGUARD_CORS_ORIGINS:JSON.stringify([base])},windowsHide:true});
  server.stdout?.pipe(log,{end:false});server.stderr?.pipe(log,{end:false});
  await expect.poll(async()=>{try{return (await fetch(base+'/api/v1/health')).status;}catch{return 0;}},{timeout:60000}).toBe(200);
}
async function stop(){if(server&&server.exitCode===null){server.kill();await new Promise<void>(resolve=>server.once('close',()=>resolve()));}}
test.beforeAll(async()=>{
  fs.mkdirSync(output,{recursive:true});
  fs.copyFileSync(path.resolve('e2e/operator.spec.ts'),path.join(output,'operator.spec.ts'));
  fs.copyFileSync(path.resolve('playwright.config.ts'),path.join(output,'playwright.config.ts'));
  log=fs.createWriteStream(path.join(output,'backend.log'));
  await start();
});
test.afterAll(async()=>{await stop();log?.end();});

test('operator workflow uses real models, orders, durable sessions and blocked promotion',async({page},testInfo)=>{
  const errors:string[]=[];const consoleErrors:string[]=[];const apiResponses:any[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
  page.on('response',r=>{if(r.url().includes('/api/v1/'))apiResponses.push({url:r.url(),status:r.status()});});
  await page.goto(base);
  await expect(page.getByText('Backend Status:',{exact:false})).toBeVisible();
  await expect(page.getByText('Active Bundles:',{exact:false})).toBeVisible();
  await page.getByLabel('Operator API key').fill(key);
  await expect(page.getByText(/Backend Status:\s*Online/)).toBeVisible();
  await page.screenshot({path:path.join(output,'01-fleet.png'),fullPage:true});
  await page.getByRole('row').filter({has:page.getByText('Engine #15',{exact:true})}).getByRole('button',{name:'Diagnostics',exact:true}).click();
  await expect(page.getByText('Engine Telemetry Diagnostics',{exact:true})).toBeVisible();
  await page.getByLabel('Diagnostics engine').fill('15');
  await page.getByRole('button',{name:'Open in Scenario Lab'}).click();
  await page.getByLabel('Replay policy').selectOption('quality_gate');
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 0');
  await page.getByRole('button',{name:'+20 Cycles',exact:true}).click();
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 20');
  const identity=await page.getByTestId('replay-identity').innerText();
  const sid=identity.match(/Session ([a-f0-9-]+)/)![1];
  await page.getByLabel('Fault onset').fill('21');
  await page.getByLabel('Fault duration').fill('20');
  await page.getByRole('button',{name:'Arm Fault Injection'}).click();
  await page.getByRole('button',{name:'+5 Cycles',exact:true}).click();
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 25');
  await page.getByRole('button',{name:'+5 Cycles',exact:true}).click();
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 30');
  const status=await (await fetch(base+'/api/v1/replay/'+sid)).json();
  expect(status.last_evidence.usable).toBe(false);
  expect(status.active_work_order).toBeTruthy();
  const orderId=status.active_work_order.work_order_id;
  await page.screenshot({path:path.join(output,'02-fault-and-real-order.png'),fullPage:true});
  await page.getByRole('button',{name:/Active Work Order/}).click();
  await expect(page.getByText(orderId.slice(0,16)+'...', {exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Acknowledge',exact:true}).click();
  await page.getByRole('button',{name:/Confirm/}).click();
  await expect(page.getByRole('cell',{name:'ACKNOWLEDGED',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('cell',{name:'ACKNOWLEDGED',exact:true})).toBeVisible();
  await stop();await start();
  await page.reload();
  await expect(page.getByRole('cell',{name:'ACKNOWLEDGED',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Scenario Lab',exact:true}).click();
  // Restored selection plus persisted session is recovered, not silently replaced.
  await page.getByLabel('Replay policy').selectOption('quality_gate');
  await expect(page.getByTestId('replay-identity')).toContainText(sid);
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 30');
  const recovered=await (await fetch(base+'/api/v1/replay/'+sid)).json();
  expect(recovered.last_evidence.is_perturbed).toBe(true);
  await page.getByRole('button',{name:'+1 Cycle',exact:true}).click();
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 31');
  await page.getByLabel('Fault mechanism').selectOption('missing_data');
  await page.getByLabel('Fault onset').fill('32');
  await page.getByLabel('Fault duration').fill('3');
  await page.getByRole('button',{name:'Arm Fault Injection'}).click();
  await page.getByRole('button',{name:'+1 Cycle',exact:true}).click();
  await expect(page.getByTestId('replay-identity')).toContainText('Cycle 32');
  const missingState=await (await fetch(base+'/api/v1/replay/'+sid)).json();
  expect(missingState.last_evidence.prediction).toBeNull();
  expect(missingState.last_evidence.usable).toBe(false);
  await page.screenshot({path:path.join(output,'02b-missing-telemetry.png'),fullPage:true});
  await page.getByRole('button',{name:'Evidence Center',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Persisted model release history'})).toBeVisible();
  await page.getByLabel('Challenger model').selectOption('Ridge');
  await page.getByRole('button',{name:'Train Challenger & Run Gate'}).click();
  await expect(page.getByText('CHAMPION RETAINED',{exact:true})).toBeVisible({timeout:60000});
  await expect(page.getByText(/promotion blocked: historical research labels/i)).toBeVisible();
  await page.screenshot({path:path.join(output,'03-genuine-training-blocked-promotion.png'),fullPage:true});
  await page.getByRole('button',{name:'Reliability research',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Maintenance consequences'})).toBeVisible();
  await expect(page.getByText(/Retrospective\/developmental/)).toBeVisible();
  await page.getByRole('button',{name:'Inspect ledger'}).first().click();
  await expect(page.getByRole('heading',{name:'Executed-action ledger'})).toBeVisible();
  await page.screenshot({path:path.join(output,'04-research-ledger.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:path.join(output,'05-mobile-evidence.png'),fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+2);
  expect(overflow).toBe(false);
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'Fleet Overview',exact:true}).click();
  await page.getByRole('button',{name:/^FD004/}).click();
  const researchOnly=page.getByRole('row').filter({has:page.getByText('Engine #1',{exact:true})});
  await expect(researchOnly.getByRole('cell',{name:'FD004',exact:true})).toBeVisible();
  await expect(researchOnly.getByRole('button',{name:'Replay Lab'})).toBeDisabled();
  expect(errors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(apiResponses.filter(r=>r.status>=500)).toEqual([]);
  fs.writeFileSync(path.join(output,'workflow-evidence.json'),JSON.stringify({status:'PASS',session_id:sid,order_id:orderId,
    browser:'Chromium via Playwright',backend_restarted:true,scientific_promotion:false,
    page_errors:errors,console_errors:consoleErrors,api_responses:apiResponses},null,2));
  await testInfo.attach('workflow-evidence',{path:path.join(output,'workflow-evidence.json'),contentType:'application/json'});
});
