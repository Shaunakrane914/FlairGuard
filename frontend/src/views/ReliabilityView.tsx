import React, {useEffect,useState} from "react";
import {api} from "../api/client";

export const ReliabilityView: React.FC = () => {
  const [data,setData]=useState<any>(null);
  const [error,setError]=useState<string|null>(null);
  const [subset,setSubset]=useState("FD004");
  const [scenario,setScenario]=useState("clean");
  const [condition,setCondition]=useState("reference");
  const [recovery,setRecovery]=useState("abstain");
  const [ledger,setLedger]=useState<any>(null);
  useEffect(()=>{api.getReliability().then(setData).catch(e=>setError(e.message));},[]);
  if(error)return <section className="panel"><h1>Reliability research</h1><p role="alert" className="error-banner">{error}</p><p>No benchmark metrics are substituted when evidence is unavailable.</p></section>;
  if(!data)return <section className="panel" role="status">Loading verified reliability evidence…</section>;
  const results=data.results.filter((r:any)=>r.subset===subset&&r.scenario===scenario&&r.condition===condition&&r.recovery===recovery);
  const inspect=async(row:any)=>{
    try {const id=[row.subset,row.scenario,row.recovery,row.condition,row.policy].join("-");
      const res=await fetch(`/api/v1/reliability/ledger?run_id=${encodeURIComponent(id)}`);
      if(!res.ok)throw new Error((await res.json()).detail);setLedger(await res.json());
    } catch(e:any){setError(e.message);}
  };
  return <div>
    <section className="panel">
      <h1>Reliability research</h1>
      <p className="scope-note">{data.scope}. Hypothetical costs and resource constraints; no field safety, repair-effect or champion-promotion claim.</p>
      <div className="research-stats"><span><strong>{data.execution.engine_episodes.toLocaleString()}</strong> executed engine episodes</span><span><strong>{data.execution.policy_runs}</strong> independently checked policy runs</span><span><strong>{data.run_id}</strong> frozen evidence</span></div>
      <details><summary>Model lineage and protocol</summary><p className="font-mono">Manifest SHA-256: {data.manifest_sha256}</p>
        {Object.entries(data.protocol.lineage).map(([ds,l]:[string,any])=><p key={ds}>{ds}: {l.predictor_fit.length} predictor-fit engines; {l.preprocessing_fit.length} preprocessing-fit engines; {l.evaluation.length} evaluation engines. {l.history}</p>)}
        <p>{data.protocol.clock}. {data.protocol.repair}. {data.protocol.boundary}.</p>
      </details>
    </section>
    <section className="panel">
      <h2>Maintenance consequences</h2>
      <div className="research-controls">
        <label>Subset <select aria-label="Research subset" value={subset} onChange={e=>setSubset(e.target.value)}>{Object.keys(data.protocol.lineage).map(s=><option key={s}>{s}</option>)}</select></label>
        <label>Measurement scenario <select aria-label="Research scenario" value={scenario} onChange={e=>setScenario(e.target.value)}>{data.protocol.scenarios.map((s:any)=><option key={s.name}>{s.name}</option>)}</select></label>
        <label>Resources <select aria-label="Research resources" value={condition} onChange={e=>setCondition(e.target.value)}>{data.protocol.conditions.map((s:any)=><option key={s.name}>{s.name}</option>)}</select></label>
        <label>Recovery <select aria-label="Research recovery" value={recovery} onChange={e=>setRecovery(e.target.value)}>{data.protocol.recovery.map((s:string)=><option key={s}>{s}</option>)}</select></label>
      </div>
      <div className="data-table-container"><table className="data-table"><thead><tr><th>Policy</th><th>Engines</th><th>Mean cost</th><th>Failures</th><th>Completed service</th><th>Mean wait</th><th>Reviews</th><th>Evidence</th></tr></thead><tbody>
        {results.map((r:any)=><tr key={r.policy}><td>{r.policy}</td><td>{r.engines}</td><td>{r.cost.toFixed(4)}</td><td>{r.failures}</td><td>{r.completed}</td><td>{r.mean_wait.toFixed(2)}</td><td>{r.review_requests}</td><td><button className="btn btn-secondary btn-sm" onClick={()=>inspect(r)}>Inspect ledger</button></td></tr>)}
        {!results.length&&<tr><td colSpan={8}>This combination was not evaluated. No extrapolated result is shown.</td></tr>}
      </tbody></table></div>
    </section>
    <section className="panel"><h2>Decision-risk evidence</h2><p>These are conditional engine-cost reweighting ranges on historically exposed engines. They hold the executed queues fixed and are not sampling confidence intervals for a new resource-constrained fleet. A separate fleet-resampling study re-executes resource competition.</p>
      {data.paired.map((r:any)=><p key={r.policy}><strong>{r.policy}</strong>: cost difference {r.mean_cost_difference.toFixed(4)}, 95% reweighting range [{r.interval_95.map((v:number)=>v.toFixed(4)).join(", ")}], {r.independent_engines} source engines; additional harmed engines: {r.incrementally_harmed_engines}. {r.earned_development_advantage?"Meets frozen developmental advantage criterion; no promotion.":"No earned advantage under the frozen criterion."}</p>)}
      <p>FD004 diagnostic: {data.fd004.dangerous_engines}/{data.fd004.population_engines} engines have dangerous full-life overestimates. This preserves the earlier negative finding.</p>
    </section>
    {ledger&&<section className="panel"><h2>Executed-action ledger</h2><p>{ledger.context.subset} / {ledger.context.policy} / {ledger.context.scenario}. Proposals and commitments precede service execution. Outcomes are independently reconstructed.</p>
      <a className="btn btn-secondary" download="flairguard-ledger.json" href={URL.createObjectURL(new Blob([JSON.stringify(ledger,null,2)],{type:"application/json"}))}>Export ledger</a>
      <div className="data-table-container"><table className="data-table"><thead><tr><th>Tick</th><th>Engine</th><th>Event</th><th>Order</th><th>Reason</th></tr></thead><tbody>{ledger.events.slice(0,100).map((e:any,i:number)=><tr key={i}><td>{e.tick}</td><td>{e.engine_id}</td><td>{e.kind}</td><td>{e.order_id||"—"}</td><td>{e.reason||"—"}</td></tr>)}</tbody></table></div><p>First 100 events displayed; the export contains the complete ledger.</p>
    </section>}
  </div>;
};
