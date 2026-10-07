"""Run all scheduling experiments promised by the second application draft."""
from pathlib import Path
import os
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
import json,pickle,time,itertools,argparse
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor
from scheduler import make_tasks,earliest,solve,scenarios,gain_filter,load_curve,check,seed_for

ROOT=Path(__file__).resolve().parents[1]
CFG=json.loads((ROOT/'config/protocol.json').read_text())
OUT=ROOT/'results'; DAYS=pd.date_range(CFG['start'],CFG['end'])
CUTS=np.r_[0,np.cumsum(CFG['split_days'])]
CTX=None; PARAMS=None

def initialize():
    global CTX,PARAMS
    with (OUT/'forecast_context.pkl').open('rb') as f:CTX=pickle.load(f)
    PARAMS=json.loads((OUT/'schedule_parameters.json').read_text()) if (OUT/'schedule_parameters.json').exists() else {}

def optimize(tasks,bg,base,w,pen):
    return solve(tasks,bg,base,risk=w,penalty=pen,chargers=CFG['chargers'],capacity=CFG['station_limit_kw'],
                 time_limit=CFG['solver_time_limit_seconds'],gap=CFG['solver_mip_rel_gap'])

def tune():
    rows=[]; selected={}
    for b,ctx in CTX.items():
        res=ctx['rolling_residual']; mid=len(res)//2
        for w,pen in itertools.product(CFG['risk_weight_grid'],CFG['shift_penalty_grid_kw_per_mean_hour']):
            observations=[]
            for d in range(CUTS[1],CUTS[2],7):
                if not np.isfinite(ctx['actual'][d]).all():continue
                tasks=make_tasks(d,CFG['baseline_seed'],10,4); base=earliest(tasks)
                assert base is not None
                pred=ctx['pred']['ai'][d]
                bg=scenarios(pred,res[:mid],(b,d,'tune_opt'),CFG['scenario_count'])
                screen=scenarios(pred,res[mid:],(b,d,'tune_screen'),CFG['scenario_count'])
                sol=optimize(tasks,bg,base,w,pen)
                cand=sol['starts'] if sol['starts'] is not None else base
                for threshold in CFG['screen_threshold_grid_kw']:
                    starts,info=gain_filter(tasks,base,cand,screen,threshold)
                    truth=ctx['actual'][d]
                    gain=(truth+load_curve(tasks,base)[0]).max()-(truth+load_curve(tasks,starts)[0]).max()
                    shift=np.abs(starts-base).mean()
                    score=gain-2*max(-gain,0)-.1*shift
                    observations.append(dict(threshold=threshold,score=float(score),gain=float(gain),shift=float(shift),accepted=info['screen_accepted']))
            for threshold in CFG['screen_threshold_grid_kw']:
                vals=[r for r in observations if r['threshold']==threshold]
                rows.append(dict(building=b,risk_weight=w,shift_penalty=pen,threshold_kw=threshold,
                    score=np.mean([r['score'] for r in vals]),gain_kw=np.mean([r['gain'] for r in vals]),
                    recommendation_rate=np.mean([r['accepted'] for r in vals]),n_days=len(vals)))
        best=sorted([r for r in rows if r['building']==b],key=lambda r:(-r['score'],r['risk_weight'],r['shift_penalty'],r['threshold_kw']))[0]
        selected[b]=best
        print('Scheduling parameters',best,flush=True)
    pd.DataFrame(rows).to_csv(OUT/'schedule_tuning.csv',index=False)
    (OUT/'schedule_parameters.json').write_text(json.dumps(selected,indent=2))

def first_workweeks():
    selected=[]
    for period in DAYS[CUTS[3]:].to_period('M').unique():
        candidates=[i for i in range(CUTS[3],len(DAYS)-4) if DAYS[i].to_period('M')==period and DAYS[i].weekday()==0
                    and DAYS[i+4].to_period('M')==period]
        if candidates:selected.extend(range(candidates[0],candidates[0]+5))
    return selected

def enumerate_cases():
    cases=[]
    for b in CTX:
        for d in range(CUTS[3],len(DAYS)):
            cases.append((b,d,10,4,CFG['baseline_seed'],'baseline','none'))
            for perturb in CFG['perturbations'][1:]:
                cases.append((b,d,10,4,CFG['baseline_seed'],'perturbation',perturb))
        for d,n,flex,seed in itertools.product(first_workweeks(),CFG['task_counts'],CFG['flex_hours'],CFG['sensitivity_seeds']):
            cases.append((b,d,n,flex,seed,'sensitivity','none'))
    return cases

def case_key(case):return '|'.join(map(str,case))

def run_case(case):
    b,d,n,flex,seed,experiment,perturb=case
    ctx=CTX[b]; p=PARAMS[b]; truth=ctx['actual'][d]
    common=dict(key=case_key(case),building=b,day=int(d),date=str(DAYS[d].date()),n_tasks=n,flex_hours=flex,seed=seed,
                experiment=experiment,perturbation=perturb)
    if not np.isfinite(truth).all():return dict(**common,excluded='missing_actual',rows=[],tasks=[])
    tasks=make_tasks(d,seed,n,flex); base=earliest(tasks)
    if base is None:
        feasibility=optimize(tasks,np.zeros(24),None,0,0)
        return dict(**common,excluded='earliest_failed' if feasibility['starts'] is not None else 'infeasible',
                    feasibility_status=feasibility['status'],tasks=tasks,rows=[])
    assert not check(tasks,base)['violations']
    pred=ctx['pred']['ai'][d].copy()
    if perturb=='bias_minus_10pct':pred*=.9
    if perturb=='bias_plus_10pct':pred*=1.1
    if perturb=='peak_early_1h':pred=np.roll(pred,-1)
    if perturb=='peak_late_1h':pred=np.roll(pred,1)
    key=(b,d,seed)
    bg=scenarios(pred,ctx['residual_opt'],(key,'opt'),CFG['scenario_count'])
    screen=scenarios(pred,ctx['residual_screen'],(key,'screen'),CFG['scenario_count'])
    baseload=load_curve(tasks,base)[0]; basepeak=float(np.max(truth+baseload))
    rows=[]; solutions={}
    def record(name,starts,solution=None,info=None):
        load=load_curve(tasks,starts)[0]; ck=check(tasks,starts)
        peak=float(np.max(truth+load)); gain=basepeak-peak
        row=dict(method=name,peak_kw=peak,baseline_peak_kw=basepeak,gain_kw=gain,reduction_pct=100*gain/basepeak,
            negative=bool(gain < -1e-7),recommended=bool(np.any(starts!=base)),mean_shift_hours=float(np.abs(starts-base).mean()),
            completed=ck['completed'],violations=len(ck['violations']),energy_error_kwh=ck['energy_error'],
            starts=list(map(int,starts)),solver_status=solution['status'] if solution else 0,
            solver_gap=solution.get('gap') if solution else 0.0,seconds=solution['seconds'] if solution else 0.0,
            fallback=bool(solution and solution['starts'] is None),**(info or {}))
        rows.append(row);solutions[name]=starts
    record('rule',base)
    # The weekly control is intentionally unchanged under AI-only perturbations.
    specs=[('weekly',ctx['pred']['weekly'][d],0),('point',pred,0),('risk',bg,p['risk_weight'])]
    if experiment=='baseline':
        iid=scenarios(pred,ctx['residual_opt'],(key,'iid_opt'),CFG['scenario_count'],True)
        specs += [('mean',bg,0),('iid',iid,p['risk_weight']),('oracle',truth,0)]
    for name,background,w in specs:
        # Oracle minimizes true peak only; it is an unattainable reference, not a deployed method.
        sol=optimize(tasks,background,base,w,0 if name=='oracle' else p['shift_penalty'])
        cand=sol['starts'] if sol['starts'] is not None else base
        record(name,cand,sol)
        if name in ['risk','mean','iid']:
            screening=screen
            if name=='iid':
                screening=scenarios(pred,ctx['residual_screen'],(key,'iid_screen'),CFG['scenario_count'],True)
            screened,info=gain_filter(tasks,base,cand,screening,p['threshold_kw'])
            record({'risk':'full','mean':'mean_screen','iid':'iid_screen'}[name],screened,sol,info)
    return dict(**common,excluded=None,tasks=tasks,rows=rows)

def run_all(workers):
    cases=enumerate_cases(); path=OUT/'schedule_cases.jsonl'; done=set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:done.add(json.loads(line)['key'])
            except json.JSONDecodeError:raise RuntimeError('Incomplete JSONL; preserve and repair before resuming')
    remaining=[c for c in cases if case_key(c) not in done]
    (OUT/'experiment_manifest.json').write_text(json.dumps({'planned_cases':len(cases),'test_days':147,
        'sensitivity_dates':[str(DAYS[d].date()) for d in first_workweeks()],
        'cases_per_experiment':{e:sum(c[-2]==e for c in cases) for e in ['baseline','perturbation','sensitivity']}},indent=2))
    started=time.time()
    print('Scheduling cases',len(cases),'remaining',len(remaining),flush=True)
    with path.open('a',buffering=1) as f, ProcessPoolExecutor(max_workers=workers,initializer=initialize) as pool:
        for i,result in enumerate(pool.map(run_case,remaining,chunksize=5),1):
            f.write(json.dumps(result,separators=(',',':'))+'\n')
            if i%100==0:print('Finished',i,'/',len(remaining),'elapsed',round(time.time()-started,1),flush=True)
    print('Scheduling completed',time.time()-started,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['tune','run','all'],default='all');parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(); initialize()
    if args.stage in ['tune','all']:tune();initialize()
    if args.stage in ['run','all']:run_all(args.workers)
