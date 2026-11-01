"""Export a standalone evidence figure with explicit populations and negative findings."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def render(run,output):
    output.mkdir(parents=True,exist_ok=False)
    paired=json.loads((run/'paired_engine_results.json').read_text())
    summary=pd.DataFrame(json.loads((run/'summary.json').read_text()))
    availability=pd.read_csv(run/'availability.csv')
    fig,axes=plt.subplots(3,1,figsize=(10,11),layout='constrained')
    for i,row in enumerate(paired):
        lo,hi=row['interval_95'];mean=row['mean_cost_difference']
        axes[0].errorbar(mean,i,xerr=[[mean-lo],[hi-mean]],fmt='o',capsize=5,color='#a13838')
    axes[0].axvline(0,color='black',lw=1)
    axes[0].set_yticks(range(3),['Logistic risk','Boosted risk','Residual-CDF risk'])
    axes[0].set_xlabel('Mean cost difference versus tuned point (lower is better)')
    axes[0].set_title('A. No risk candidate earns the frozen advantage criterion\n49 source engines; conditional reweighting ranges, queues held fixed',fontsize=11)
    methods=['abstain','bounded_last','regime_impute','missing_aware','decision_fallback']
    names=['Abstain','Bounded last','Regime impute','Missingness model','Decision fallback']
    x=np.arange(len(methods));width=.35
    for offset,ds,color in [(-.18,'FD002','#2e647b'),(.18,'FD004','#ad7832')]:
        selected=summary.loc[(summary.subset==ds)&(summary.scenario=='packet_40')&(summary.condition=='reference')&(summary.policy=='point')].set_index('recovery')
        bars=axes[1].bar(x+offset,[selected.loc[m,'cost'] for m in methods],width,label=ds,color=color)
        for bar,m in zip(bars,methods):axes[1].text(bar.get_x()+bar.get_width()/2,bar.get_height()+.05,str(int(selected.loc[m,'failures'])),ha='center',fontsize=9)
        rows=availability.loc[(availability.subset==ds)&(availability.scenario=='packet_40')].set_index('recovery')
        axes[2].bar(x+offset,[100*rows.loc[m,'availability'] for m in methods],width,label=ds,color=color)
    axes[1].set_xticks(x,names);axes[1].set_ylabel('Hypothetical mean cost');axes[1].legend(ncol=2)
    axes[1].set_title('B. Forty-cycle packet outage: costs and failure trade-offs\nLabels above bars are failed engines (FD002 n=80; FD004 n=49)',fontsize=11)
    axes[1].set_ylim(0,6)
    axes[2].set_xticks(x,names);axes[2].set_ylim(0,105);axes[2].set_ylabel('Available forecasts (%)')
    axes[2].set_title('C. More available forecasts do not imply better safety or economics\nAll alive cycles after warm-up; repeated cycles are not independent engines',fontsize=11)
    for ax in axes:
        ax.spines[['top','right']].set_visible(False);ax.grid(axis='x' if ax==axes[0] else 'y',alpha=.15)
    fig.suptitle('FlairGuard Phase D — retrospective reliability evidence',fontsize=15)
    fig.supxlabel('Frozen run reliability-v1-run002 · hypothetical clocks/costs · no fresh confirmation or champion promotion',fontsize=9)
    fig.savefig(output/'phase-d-evidence.png',dpi=180);fig.savefig(output/'phase-d-evidence.svg')
    (output/'source-run.txt').write_text(str(run.resolve()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();render(args.run,args.output)
