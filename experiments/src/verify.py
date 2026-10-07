"""Independent checks: exact enumeration on tiny MILPs, infeasible inputs, and causal features."""
from pathlib import Path
import itertools,json,time
import numpy as np
from scheduler import solve,check,earliest,load_curve,gain_filter,scenarios

ROOT=Path(__file__).resolve().parents[1]

def main():
    rows=[]; rng=np.random.default_rng(9)
    for seed in range(6):
        tasks=[dict(id=0,release=5,duration=2,deadline=10,power=7.),dict(id=1,release=6,duration=2,deadline=11,power=7.)]
        bg=rng.uniform(10,30,(50,24));base=earliest(tasks,1,7)
        w=.5;pen=.5
        best=float('inf')
        for starts in itertools.product(range(5,9),range(6,10)):
            if check(tasks,starts,1,7)['violations']:continue
            peaks=(bg+load_curve(tasks,starts)[0]).max(axis=1)
            score=(1-w)*peaks.mean()+w*np.sort(peaks)[-5:].mean()+pen*np.abs(np.array(starts)-base).mean()
            best=min(best,score)
        sol=solve(tasks,bg,base,w,pen,1,7,time_limit=10,gap=1e-9)
        assert sol['starts'] is not None and abs(sol['objective']-best)<1e-6,(sol,best)
        rows.append({'check':'milp_vs_exhaustive','seed':seed,'absolute_error':abs(sol['objective']-best),'passed':True})
    cases=[('short_window',[dict(id=0,release=8,duration=4,deadline=10,power=7.)],10,70),
           ('port_conflict',[dict(id=i,release=8,duration=3,deadline=11,power=7.) for i in range(3)],2,14),
           ('power_conflict',[dict(id=i,release=8,duration=2,deadline=10,power=7.) for i in range(2)],10,7)]
    for name,tasks,ports,capacity in cases:
        sol=solve(tasks,np.zeros(24),chargers=ports,capacity=capacity)
        assert sol['starts'] is None and sol['status']==2
        rows.append({'check':name,'passed':True,'solver_status':sol['status'],'explanation':sol['message']})
    # Clipping and threshold-boundary regression tests.
    ss=scenarios(np.zeros(24),np.full((10,24),-1.),'negative')
    assert ss.min()==0
    tasks=[dict(id=0,release=0,duration=1,deadline=3,power=7.)]
    base=np.array([0]);candidate=np.array([1])
    chosen,info=gain_filter(tasks,base,candidate,np.zeros((50,24)),0)
    assert np.array_equal(chosen,base) and not info['screen_accepted']
    rows += [{'check':'scenario_nonnegative','passed':True},{'check':'zero_gain_not_recommended','passed':True}]
    from forecast import features
    load=rng.uniform(10,20,731*24);temp=rng.uniform(0,30,731*24)
    before=features(load,temp);d=610
    load[d*24:]=1e6;temp[d*24:]=1e6
    after=features(load,temp)
    assert np.array_equal(before[before.day<=d].to_numpy(),after[after.day<=d].to_numpy())
    rows.append({'check':'features_unaffected_by_future_observations','passed':True,'last_unchanged_origin_day':d})
    (ROOT/'results/verification.json').write_text(json.dumps(rows,indent=2))
    print('All',len(rows),'verification checks passed',flush=True)

if __name__=='__main__':main()
