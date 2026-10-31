"""Export scientific figures from a scored run, without changing run evidence."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plot(run,out):
    out.mkdir(parents=True,exist_ok=False)
    report=json.loads((run/'independent_score.json').read_text());p=json.loads((run/'protocol.json').read_text())
    if report['status']!='PASS_EVIDENCE_INTEGRITY':raise ValueError('Evidence must pass scoring before plotting')
    primary=[s['name'] for s in p['scenarios'] if not s.get('diagnostic_only')]
    table=report['Trust']['tables'];fig,axes=plt.subplots(1,2,figsize=(12,5.3),layout='constrained')
    ax=axes[0];control=[]
    for selector,label,color in [('learned_gate','Learned error','#bb6326'),('quality_gate','Quality heuristic','#346a97')]:
        xs=[];ys=[];annotations={}
        for budget in p['budgets']:
            rows=[r for r in table if r['mode']=='fixed_threshold' and r['selector']==selector and r['budget']==budget and r['scenario'] in primary]
            n=sum(r['accepted']['n'] for r in rows);observed=sum(r['n_observed'] for r in rows)
            if not n:continue
            xs.append(n/observed);ys.append(sum(r['accepted']['mae']*r['accepted']['n'] for r in rows if r['accepted']['n'])/n)
            if selector=='learned_gate':control.append((xs[-1],sum(r['expected_matched_random_mae']*r['accepted']['n'] for r in rows)/n))
            annotations.setdefault((round(xs[-1],8),round(ys[-1],8)),[]).append(f'{budget:.0%}')
        for xy,labels in annotations.items():ax.annotate(', '.join(labels),xy,xytext=(4,5),textcoords='offset points',fontsize=8,color=color)
        ax.plot(xs,ys,'o-',label=label,color=color)
    if control:ax.plot(*zip(*control),'s--',color='#777777',label='Expected matched random (learned counts)')
    ax.set(xlabel='Automation coverage, including mandatory deferrals',ylabel='Accepted MAE (cycles)',title='Trust: frozen development thresholds')
    ax.grid(alpha=.2);ax.legend(fontsize=8,loc='best');ax.set_xlim(0,1.03)
    with (run/'policy_costs.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
    index={(r['scenario'],r['policy'],int(r['engine_id'])):r for r in rows}
    kinds=['none','fixed','point','quality_gate','quality_decision','learned_gate']
    labels=['Run to\nfailure','Fixed\nage','Tuned\npoint','Broad\nquality','Decision\nquality','Learned\ndecision']
    rng=np.random.default_rng(p['seed']);sample=rng.integers(0,80,size=(p['bootstrap_replicates'],80));means=[];errors=[];failures=[]
    for kind in kinds:
        per_engine=np.array([np.mean([float(index[s,kind,e]['total_cost']) for s in primary]) for e in p['partitions']['evaluation']])
        mean=float(per_engine.mean());ci=np.quantile(per_engine[sample].mean(axis=1),[.025,.975])
        means.append(mean);errors.append([mean-ci[0],ci[1]-mean]);failures.append(sum(int(index[s,kind,e]['failures']) for s in primary for e in p['partitions']['evaluation']))
    ax=axes[1];bars=ax.bar(range(6),means,yerr=np.array(errors).T,capsize=3,color=['#777777','#a3a3a3','#346a97','#9a5361','#758a99','#bb6326'])
    for bar,mean,failed,error in zip(bars,means,failures,errors):ax.annotate(f'{mean:.2f}\n{failed} failures',(bar.get_x()+bar.get_width()/2,bar.get_height()+error[1]),xytext=(0,7),textcoords='offset points',ha='center',fontsize=8)
    ax.set_xticks(range(6),labels,fontsize=8);ax.set(ylabel='Mean hypothetical cost per engine-life',title='Value: all primary episodes retained')
    ax.set_ylim(0,max(means)*1.25);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('FD002 | 80 engine clusters | nine primary measurement scenarios',fontsize=12)
    finding=report['Trust']['primary'];ci=finding['engine_bootstrap_95']
    verdict='primary criteria met' if finding['status'].startswith('PASS_') else 'superiority not established'
    fig.supxlabel(f"Trust primary {p['primary_budget']:.0%}: MAE delta {finding['accepted_minus_expected_random_mae']:.2f} cycles (95% CI {ci[0]:.2f} to {ci[1]:.2f}); {verdict}. Labels are development referral targets.\n"
                  'Costs: planned=1, failure=10, unused cycle=0.05, inspection=0.2. Bars: engine bootstrap 95% intervals. Failure counts are scenario episodes.',fontsize=8)
    for suffix in ('png','svg'):fig.savefig(out/f'fd002_trust_value.{suffix}',dpi=180)
    plt.close(fig)
    shutil.copy2(__file__,out/'plotter.py')
    metadata=dict(source_score_sha256=sha(run/'independent_score.json'),source_costs_sha256=sha(run/'policy_costs.csv'),
                  protocol_sha256=sha(run/'protocol.json'),plotter_sha256=sha(__file__),matplotlib_version=matplotlib.__version__,
                  numpy_version=np.__version__,scope='Descriptive exports; no model or policy selection performed',
                  outputs={p.name:sha(p) for p in sorted(out.iterdir())})
    with (out/'figure_manifest.json').open('x') as stream:json.dump(metadata,stream,indent=2)
    print('Saved figures:',out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-dir',type=Path,required=True);parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args();plot(args.run_dir,args.output_dir)
