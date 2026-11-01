import {useEffect,useState} from "react";
import {api} from "../api/client";
import {LineChart,Line,XAxis,YAxis,Tooltip,Legend,ResponsiveContainer,CartesianGrid} from "recharts";
import {Play,RefreshCw,Download} from "lucide-react";

export function MatlabView(){
  const [cap,setCap]=useState<any>(null),[data,setData]=useState<any>(null),[jobs,setJobs]=useState<any[]>([]);
  const [job,setJob]=useState<any>(null),[source,setSource]=useState("Historical Phase D run");
  const [error,setError]=useState<string|null>(null),[busy,setBusy]=useState(false),[log,setLog]=useState("");
  const [engine,setEngine]=useState<number|null>(null),[scenario,setScenario]=useState("clean");
  const selectResult=async(id:string)=>{setData(await api.getMatlabResult(id));setSource(`Application job ${id.slice(0,10)}`);};
  const refresh=async()=>{try{setCap(await api.getMatlabCapabilities());if(sessionStorage.getItem("flairguard_operator_key"))setJobs(await api.getMatlabJobs());}catch(e:any){setError(e.message);}};
  useEffect(()=>{let active=true;api.getMatlabHistorical().then(d=>{if(active)setData(d);}).catch(e=>{if(active)setError(e.message);});refresh();
    const id=sessionStorage.getItem("flairguard_matlab_job");
    if(id&&sessionStorage.getItem("flairguard_operator_key"))api.getMatlabJob(id).then(j=>{if(active)setJob(j);}).catch(e=>{if(active)setError(e.message);});
    return()=>{active=false;};},[]);
  useEffect(()=>{if(!job||!["QUEUED","RUNNING"].includes(job.status))return;
    let active=true;const timer=setInterval(async()=>{try{const next=await api.getMatlabJob(job.id);if(active){setJob(next);if(next.status==="COMPLETED"){await selectResult(next.id);await refresh();}}}catch(e:any){if(active)setError(e.message);}},1500);
    return()=>{active=false;clearInterval(timer);};},[job?.id,job?.status]);
  const action=async(fn:()=>Promise<any>)=>{setBusy(true);setError(null);try{await fn();}catch(e:any){setError(e.message);}finally{setBusy(false);}};
  const run=()=>action(async()=>{const j=await api.runMatlab(crypto.randomUUID());setJob(j);sessionStorage.setItem("flairguard_matlab_job",j.id);await refresh();});
  const engines:number[]=data?Array.from(new Set<number>(data.forecasts.map((r:any)=>r.engine_id))).sort((a,b)=>a-b):[];
  const selected=engine&&engines.includes(engine)?engine:engines[0];
  const forecasts=data?.forecasts.filter((r:any)=>r.engine_id===selected&&r.scenario===scenario)||[];
  const download=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const a=document.createElement('a');a.href=url;a.download='flairguard-matlab-comparison.json';a.click();URL.revokeObjectURL(url);};
  return <div className="workspace-stack">
    <section className="page-intro"><span className="eyebrow">RESEARCH WORKSPACE</span><h1>MATLAB analysis</h1><p>Run a toolbox comparison and inspect its maintenance consequences. Active Python models stay unchanged.</p></section>
    {error&&<div role="alert" className="error-banner">{error}</div>}
    <section className="panel matlab-control"><div><h2>Similarity-based RUL</h2><p className="scope-note">FD003 · 60 fit engines · 20 evaluation engines · clean and missing telemetry. Historically exposed research population.</p><p role="status">{cap?.available?"MATLAB executable configured. Toolbox and license are checked when the job runs.":cap?.reason||"Checking optional MATLAB runtime…"}</p></div>
      <div className="action-row"><button className="btn-primary" onClick={run} disabled={busy||!cap?.available||["QUEUED","RUNNING"].includes(job?.status)}><Play size={15}/> Run MATLAB comparison</button><button className="btn-secondary" aria-label="Refresh MATLAB status" onClick={refresh}><RefreshCw size={15}/></button></div></section>
    {job&&<section className="panel job-progress" aria-live="polite"><h2>Analysis job: <span data-testid="matlab-job-status">{job.status}</span></h2><code>{job.id}</code><p>{job.error||(["QUEUED","RUNNING"].includes(job.status)?"Processing real trajectories. You can leave this view and return to the persisted job.":"Job state persists independently of the browser.")}</p>
      <div className="action-row">{["RUNNING","QUEUED"].includes(job.status)&&<button className="btn-secondary" onClick={()=>action(async()=>setJob(await api.cancelMatlab(job.id)))}>Cancel analysis</button>}{job.status==="COMPLETED"&&<button className="btn-secondary" onClick={()=>action(()=>selectResult(job.id))}>Open completed result</button>}<button className="btn-secondary" onClick={()=>action(async()=>setLog((await api.getMatlabLog(job.id)).log))}>Inspect job log</button></div>{log&&<pre className="job-log">{log}</pre>}</section>}
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">DISPLAYED EVIDENCE</span><h2>{source}</h2></div><button className="btn-secondary" disabled={!data} onClick={download}><Download size={15}/> Export comparison</button></div>
      <div className="action-row"><button className="text-button" onClick={()=>action(async()=>{setData(await api.getMatlabHistorical());setSource("Historical Phase D run");})}>Open historical result</button>{jobs.filter(j=>j.status==="COMPLETED").map(j=><button className="text-button" key={j.id} onClick={()=>action(()=>selectResult(j.id))}>Job {j.id.slice(0,8)}</button>)}</div>
      {!data?<p role="status">Loading verified evidence…</p>:<><p className="scope-note">{data.scope}. Costs use hypothetical service constraints.</p><div className="table-scroll"><table><thead><tr><th>Telemetry</th><th>Model</th><th>Available prefixes</th><th>RMSE, cycles</th><th>MAE, cycles</th><th>Failures</th><th>Cost / engine</th></tr></thead><tbody>{data.metrics.map((r:any)=>{const p=data.policies.find((p:any)=>p.model===r.model&&p.scenario===r.scenario);return <tr key={r.scenario+r.model}><td>{r.scenario}</td><td>{r.model==="matlab"?"MATLAB similarity":"Python baseline"}</td><td>{r.available_rows} / {r.expected_rows}</td><td>{r.rmse_cycles.toFixed(2)}</td><td>{r.mae_cycles.toFixed(2)}</td><td>{p?.failures} / {p?.engines}</td><td>{p?.mean_cost.toFixed(4)}</td></tr>;})}</tbody></table></div>
      <p className="scope-note">Error metrics above use each model's available rows. Missing-case coverage can differ.</p>
      {data.common_valid_metrics.length>0&&<details><summary>Errors on identical available prefixes</summary><div className="table-scroll"><table><thead><tr><th>Telemetry</th><th>Model</th><th>Matched rows</th><th>RMSE</th><th>MAE</th></tr></thead><tbody>{data.common_valid_metrics.map((r:any)=><tr key={r.scenario+r.model}><td>{r.scenario}</td><td>{r.model}</td><td>{r.n_snapshots}</td><td>{r.rmse_cycles.toFixed(2)}</td><td>{r.mae_cycles.toFixed(2)}</td></tr>)}</tbody></table></div></details>}
      <div className="chart-toolbar"><h3>Observed-prefix forecasts</h3><label>Engine <select aria-label="MATLAB comparison engine" value={selected||""} onChange={e=>setEngine(Number(e.target.value))}>{engines.map(e=><option key={e}>{e}</option>)}</select></label><label>Telemetry <select aria-label="MATLAB telemetry scenario" value={scenario} onChange={e=>setScenario(e.target.value)}><option value="clean">Clean</option><option value="missing">Sensor loss</option></select></label></div>
      <ResponsiveContainer width="100%" height={300}><LineChart data={forecasts} margin={{left:0,right:20,top:12,bottom:20}}><CartesianGrid stroke="#293748" strokeDasharray="3 3"/><XAxis dataKey="cycle" stroke="#a3b3c6" label={{value:"Observed operating cycle",position:"bottom",fill:"#a3b3c6"}}/><YAxis stroke="#a3b3c6"/><Tooltip contentStyle={{background:"#152131",border:"1px solid #33465d",color:"#fff"}}/><Legend verticalAlign="top"/><Line name="MATLAB RUL, cycles" dataKey="prediction_matlab" stroke="#f6a65b" connectNulls={false} isAnimationActive={false}/><Line name="Python RUL, cycles" dataKey="prediction_python" stroke="#53c9d5" connectNulls={false} isAnimationActive={false}/></LineChart></ResponsiveContainer>
      <details><summary>Protocol and provenance</summary><p>Manifest SHA-256</p><code className="hash-value">{data.manifest_sha256}</code><p>{data.protocol.health_indicator}</p><p>{data.protocol.queries}</p><p>{data.timing_scope}</p><p>Chart values are previews. Full-precision CSVs and fitted models are archived with the job.</p></details></>}
    </section></div>;
}
