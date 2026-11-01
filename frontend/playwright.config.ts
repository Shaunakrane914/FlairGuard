import {defineConfig} from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';
const output=process.env.PHASE_D_BROWSER_OUTPUT || path.resolve('../FleetGuard_Phase1_Starter/FleetGuard_Phase1_Starter/artifacts/phase_d/browser-v1-run001');
if(!process.env.PHASE_D_BROWSER_RESERVED){
  if(fs.existsSync(output))throw new Error("Refusing to overwrite browser evidence: "+output);
  fs.mkdirSync(output,{recursive:true});process.env.PHASE_D_BROWSER_RESERVED="1";
}
export default defineConfig({testDir:'./e2e',workers:1,fullyParallel:false,timeout:180000,
  expect:{timeout:20000},outputDir:path.join(output,'test-results'),
  reporter:[['list'],['json',{outputFile:path.join(output,'playwright-report.json')}]],
  use:{actionTimeout:20000,browserName:'chromium',headless:true,viewport:{width:1440,height:1000},trace:'on',screenshot:'only-on-failure'}});
