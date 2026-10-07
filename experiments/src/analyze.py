"""Audit every result, summarize paired experiments, bootstrap daily effects, draw figures."""
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.mplconfig'))
import json,pickle,math,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scheduler import check,load_curve,seed_for

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results';FIG=ROOT.parent/'reports/figures'
CFG=json.loads((ROOT/'config/protocol.json').read_text())
MAIN=['rule','weekly','point','risk','full']
NAMES={'rule':'Earliest rule','weekly':'Weekly + MILP','point':'AI point + MILP','risk':'AI risk + MILP','full':'Risk + screening',
       'mean':'Mean only','mean_screen':'Mean + screening','iid':'Independent hours','iid_screen':'Independent + screening','oracle':'Oracle reference'}
COLORS={'rule':'#777777','weekly':'#bd9847','point':'#437ea0','risk':'#9183aa','full':'#227c63','oracle':'#333333'}

def summary(g):
    gains=g.gain_kw.to_numpy();neg=gains[gains<0];k=max(1,math.ceil(.1*len(g)))
    return dict(n=len(g),mean_reduction_pct=g.reduction_pct.mean(),mean_gain_kw=g.gain_kw.mean(),
        median_reduction_pct=g.reduction_pct.median(),negative_pct=100*g.negative.mean(),
        recommendation_pct=100*g.recommended.mean(),mean_shift_hours=g.mean_shift_hours.mean(),
        completion_pct=100*g.completed.sum()/g.n_tasks.sum(),violations=int(g.violations.sum()),
        max_energy_error_kwh=float(g.energy_error_kwh.abs().max()),mean_seconds=g.seconds.mean(),p95_seconds=g.seconds.quantile(.95),
        worst10_mean_gain_kw=float(np.sort(gains)[:k].mean()),min_gain_kw=float(gains.min()),
        mean_negative_gain_kw=float(neg.mean()) if len(neg) else 0,timeout_count=int((g.solver_status==1).sum()),fallback_count=int(g.fallback.sum()))

def summarize(df,cols,name):
    rows=[]
    for key,g in df.groupby(cols,sort=True):
        if not isinstance(key,tuple):key=(key,)
        rows.append(dict(zip(cols,key),**summary(g)))
    result=pd.DataFrame(rows);result.to_csv(OUT/f'{name}.csv',index=False);return result

def block_ci(days,values,key):
    # Actual consecutive calendar-day blocks, avoiding accidental adjacency across missing dates.
    days=np.asarray(days);values=np.asarray(values)
    valid_starts=[i for i in range(len(days)-6) if np.all(np.diff(days[i:i+7])==1)]
    if not valid_starts:raise ValueError('No 7-day consecutive blocks')
    blocks=np.array([values[i:i+7] for i in valid_starts])
    rng=np.random.default_rng(seed_for('bootstrap',key));n=len(values);nb=math.ceil(n/7)
    samples=blocks[rng.integers(len(blocks),size=(CFG['bootstrap_replicates'],nb))].reshape(CFG['bootstrap_replicates'],-1)[:,:n]
    lo,hi=np.quantile(samples.mean(axis=1),[.025,.975]);return float(lo),float(hi)

def main():
    FIG.mkdir(parents=True,exist_ok=True)
    with (OUT/'forecast_context.pkl').open('rb') as f:ctx=pickle.load(f)
    records=[];cases=[];keys=set();errors=[]
    for line in (OUT/'schedule_cases.jsonl').open():
        c=json.loads(line);assert c['key'] not in keys;keys.add(c['key']);cases.append(c)
        for row in c['rows']:
            ck=check(c['tasks'],row['starts']);assert not ck['violations'] and abs(ck['energy_error'])<1e-7
            actual_peak=float(np.max(ctx[c['building']]['actual'][c['day']]+load_curve(c['tasks'],row['starts'])[0]))
            assert abs(actual_peak-row['peak_kw'])<1e-7
            records.append({k:v for k,v in c.items() if k not in ['rows','tasks','excluded']}|{k:v for k,v in row.items() if k!='starts'})
    manifest=json.loads((OUT/'experiment_manifest.json').read_text());assert len(keys)==manifest['planned_cases']
    df=pd.DataFrame(records);df.to_csv(OUT/'all_scheduling_metrics.csv',index=False)
    exclusions=[{k:v for k,v in c.items() if k not in ['tasks','rows']} for c in cases if c['excluded']]
    (OUT/'excluded_cases.json').write_text(json.dumps(exclusions,indent=2))
    base=df[df.experiment=='baseline'];sens=df[df.experiment=='sensitivity'];pert=df[df.experiment=='perturbation']
    bs=summarize(base,['building','method'],'baseline_summary')
    ss=summarize(sens,['building','n_tasks','flex_hours','method'],'sensitivity_summary')
    ps=summarize(pd.concat([base[base.method.isin(MAIN)],pert]),['building','perturbation','method'],'perturbation_summary')
    ci=[]
    for b,g in base.groupby('building'):
        pivot=g.pivot(index='day',columns='method',values='reduction_pct').sort_index()
        for first,second in [('full','rule'),('point','weekly'),('risk','point'),('full','risk'),('risk','mean'),('risk','iid')]:
            value=(pivot[first]-pivot[second]).to_numpy();lo,hi=block_ci(pivot.index,value,(b,first,second))
            ci.append(dict(building=b,comparison=f'{first}-{second}',mean_pp=float(value.mean()),ci_low_pp=lo,ci_high_pp=hi,n_days=len(value)))
    pd.DataFrame(ci).to_csv(OUT/'paired_confidence_intervals.csv',index=False)
    forecast=pd.read_csv(OUT/'forecast_metrics.csv');fm=forecast[(forecast.split=='test')&(forecast.subset=='all')]
    alarms=pd.read_csv(OUT/'alarm_predictions.csv');ar=[]
    for b,g in alarms.groupby('building'):
        true=g.actual_high.to_numpy(bool);pred=g.predicted_high.to_numpy(bool);tp=int((true&pred).sum());fp=int((~true&pred).sum());fn=int((true&~pred).sum())
        ar.append(dict(building=b,threshold_kw=ctx[b]['threshold'],hours=len(g),actual_high_hours=int(true.sum()),
            tp=tp,fp=fp,fn=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
            brier=float(((g.probability.to_numpy()-true)**2).mean())))
    pd.DataFrame(ar).to_csv(OUT/'alarm_summary.csv',index=False)
    # Scenario coverage and temporal correlation are diagnostics, not fitted test calibrations.
    diag=[]
    from scheduler import scenarios
    for b,c in ctx.items():
        coverage=[];width=[]
        for d in sorted(base[base.building==b].day.unique()):
            sc=scenarios(c['pred']['ai'][d],c['residual_opt'],((b,int(d),CFG['baseline_seed']),'opt'),50)
            lo,hi=np.quantile(sc,[.1,.9],axis=0);truth=c['actual'][d]
            coverage.extend((truth>=lo)&(truth<=hi));width.extend(hi-lo)
        rr=c['residual_opt'];corr=float(np.corrcoef(rr[:,:-1].ravel(),rr[:,1:].ravel())[0,1])
        diag.append(dict(building=b,opt_days=len(c['opt_dates']),screen_days=len(c['screen_dates']),rolling_residual_days=len(c['rolling_dates']),
                    lag1_residual_correlation=corr,test_10_90_coverage_pct=100*np.mean(coverage),mean_interval_width_kw=np.mean(width)))
    pd.DataFrame(diag).to_csv(OUT/'scenario_diagnostics.csv',index=False)
    # Export all baseline detail files for independent review and product demonstrations.
    baseline_cases=[c for c in cases if c['experiment']=='baseline' and not c['excluded']]
    candidates=[]
    for c in baseline_cases:
        rr={r['method']:r for r in c['rows']};candidates.append((rr['full']['gain_kw'],c))
    best=max(candidates,key=lambda x:x[0])[1];worst=min(candidates,key=lambda x:x[0])[1]
    risk_worst=min(baseline_cases,key=lambda c:next(r['gain_kw'] for r in c['rows'] if r['method']=='risk'))
    examples={'largest_full_gain':best,'worst_full_gain':worst,'worst_risk_gain':risk_worst}
    (OUT/'example_cases.json').write_text(json.dumps(examples,indent=2))
    audit=dict(completed_cases=len(cases),scored_cases=sum(not c['excluded'] for c in cases),
        excluded_cases=len(exclusions),scored_schedules=len(df),unique_solver_results=int(df.method.isin(['weekly','point','risk','mean','iid','oracle']).sum()),
        constraint_violations=int(df.violations.sum()),max_energy_error_kwh=float(df.energy_error_kwh.abs().max()),
        solver_status_counts={str(k):int(v) for k,v in df[df.method.isin(['weekly','point','risk','mean','iid','oracle'])].solver_status.value_counts().items()},
        all_peak_recomputations_passed=True,all_case_keys_unique=True,planned_cases=manifest['planned_cases'])
    (OUT/'result_audit.json').write_text(json.dumps(audit,indent=2))
    draw(fm,base,bs,ss,ps,ctx,examples)
    print(json.dumps(audit,indent=2),flush=True)

def save(fig,name):
    fig.savefig(FIG/f'{name}.png',dpi=190,bbox_inches='tight');fig.savefig(FIG/f'{name}.pdf',bbox_inches='tight');plt.close(fig)

def draw(fm,base,bs,ss,ps,ctx,examples):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    buildings=list(ctx);short={b:b.replace('_office_',' / ') for b in buildings}
    fig,axs=plt.subplots(1,3,figsize=(10,3.0),layout='constrained')
    models=['weekly','linear','ai','no_response','no_interaction','no_weather']
    labels=['Weekly','Linear','Full AI','No response','No interaction','No weather']
    for ax,b in zip(axs,buildings):
        vals=fm[fm.building==b].set_index('model').loc[models].mae
        ax.barh(labels,vals,color=['#888888','#a3acb7','#227c63','#749dad','#749dad','#749dad']);ax.invert_yaxis();ax.set_xlabel('Test MAE (kW)');ax.set_title(short[b])
    save(fig,'01_forecast_mae')
    fig,axs=plt.subplots(1,3,figsize=(10,3.1),layout='constrained')
    for ax,b in zip(axs,buildings):
        d=bs[(bs.building==b)&bs.method.isin(MAIN)].set_index('method').loc[MAIN]
        ax.bar(np.arange(5),d.mean_reduction_pct,color=[COLORS[m] for m in MAIN]);ax.set_xticks(range(5),['Rule','Weekly','Point','Risk','Full'],rotation=25)
        ax.set_title(short[b]);ax.set_ylabel('Mean daily peak reduction (%)');ax.axhline(0,color='#333333',lw=.7)
    save(fig,'02_scheduling_mean')
    fig,axs=plt.subplots(1,3,figsize=(10,3.1),layout='constrained')
    for ax,b in zip(axs,buildings):
        for m in ['point','risk','full']:
            v=np.sort(base[(base.building==b)&(base.method==m)].gain_kw)
            ax.plot(v,np.arange(1,len(v)+1)/len(v),label=NAMES[m],color=COLORS[m])
        ax.axvline(0,color='#333333',ls='--',lw=.8);ax.set_title(short[b]);ax.set_xlabel('Actual peak reduction (kW)');ax.set_ylabel('Empirical cumulative probability')
    axs[-1].legend(fontsize=7,loc='lower right');save(fig,'03_gain_distribution')
    fig,axs=plt.subplots(1,3,figsize=(10,3.0),layout='constrained')
    values=[]
    for b in buildings:
        s=ss[(ss.building==b)&(ss.method=='full')].pivot(index='n_tasks',columns='flex_hours',values='mean_reduction_pct').reindex(index=[5,10,20],columns=[2,4,8]);values.append(s)
    lo=min(0,min(s.to_numpy().min() for s in values));hi=max(s.to_numpy().max() for s in values)
    for ax,b,s in zip(axs,buildings,values):
        im=ax.imshow(s,aspect='auto',cmap='YlGnBu',vmin=lo,vmax=hi);ax.set_xticks(range(3),[2,4,8]);ax.set_yticks(range(3),[5,10,20]);ax.set_xlabel('Extra waiting window (hours)');ax.set_ylabel('Tasks per day');ax.set_title(short[b])
        for i in range(3):
            for j in range(3):ax.text(j,i,f'{s.iloc[i,j]:.2f}%',ha='center',va='center',color='white' if s.iloc[i,j]>(lo+hi)*.65 else 'black')
    fig.colorbar(im,ax=axs,label='Mean peak reduction (%)',shrink=.85);save(fig,'04_scale_flexibility')
    fig,axs=plt.subplots(1,3,figsize=(10,3.0),layout='constrained')
    modes=CFG['perturbations'];labels=['None','-10%','+10%','Early 1h','Late 1h']
    for ax,b in zip(axs,buildings):
        for m in ['point','risk','full']:
            s=ps[(ps.building==b)&(ps.method==m)].set_index('perturbation').loc[modes]
            ax.plot(range(5),s.mean_reduction_pct,'o-',label=NAMES[m],color=COLORS[m],markersize=4)
        ax.set_xticks(range(5),labels,rotation=25);ax.set_title(short[b]);ax.set_ylabel('Mean peak reduction (%)');ax.axhline(0,color='#aaa',lw=.8)
    axs[-1].legend(fontsize=7);save(fig,'05_perturbation')
    for suffix,key in [('06_success_case','largest_full_gain'),('07_failure_case','worst_risk_gain')]:
        c=examples[key];truth=ctx[c['building']]['actual'][c['day']];rows={r['method']:r for r in c['rows']}
        fig,axs=plt.subplots(2,1,figsize=(9,5.1),gridspec_kw={'height_ratios':[1.3,1]},layout='constrained')
        for m in ['rule','point','risk','full']:
            axs[0].plot(range(24),truth+load_curve(c['tasks'],rows[m]['starts'])[0],label=NAMES[m],color=COLORS[m],lw=1.7)
        axs[0].plot(range(24),ctx[c['building']]['pred']['ai'][c['day']],':',color='#999999',label='Forecast background')
        axs[0].set_title(short[c['building']]+' | '+c['date']);axs[0].set_ylabel('Hourly average power (kW)');axs[0].legend(ncol=3,fontsize=7)
        for i,t in enumerate(c['tasks']):
            for m,offset in [('rule',-.18),('full',.18)]:
                axs[1].barh(i+offset,t['duration'],left=rows[m]['starts'][i],height=.32,color=COLORS[m])
        axs[1].set_yticks(range(len(c['tasks'])),[str(i+1) for i in range(len(c['tasks']))]);axs[1].set_ylabel('Task');axs[1].set_xlabel('Local hour');axs[1].set_xlim(0,24)
        save(fig,suffix)
    fig,axs=plt.subplots(3,1,figsize=(9,5.5),layout='constrained')
    for ax,b in zip(axs,buildings):
        days=np.arange(584,591);actual=ctx[b]['actual'][days].ravel();pred=ctx[b]['pred']['ai'][days].ravel()
        ax.plot(actual,color='#333333',label='Observed',lw=1);ax.plot(pred,color='#227c63',label='AI forecast',lw=1)
        ax.set_title(short[b]);ax.set_ylabel('Power (kW)');ax.set_xlabel('Hours from test start')
    axs[0].legend(ncol=2,fontsize=8);save(fig,'08_forecast_week')

if __name__=='__main__':main()
