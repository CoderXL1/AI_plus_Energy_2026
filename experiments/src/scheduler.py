"""Finite-scenario MILP, independent feasibility checks, and synthetic task model."""
from dataclasses import dataclass
import hashlib, json, time, warnings
import numpy as np
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix, vstack, csc_matrix

def seed_for(*parts):
    return int.from_bytes(hashlib.sha256('|'.join(map(str,parts)).encode()).digest()[:4],'little')

def make_tasks(day,seed,n,flex):
    rng=np.random.default_rng(seed_for('tasks',day,seed))
    # Draw a fixed 20-task sequence so all task counts share a prefix.
    release=rng.integers(6,13,20); duration=rng.integers(1,5,20)
    return [{'id':i,'release':int(release[i]),'duration':int(duration[i]),
             'deadline':int(release[i]+duration[i]+flex),'power':7.0} for i in range(n)]

def load_curve(tasks,starts):
    load=np.zeros(24); count=np.zeros(24)
    for t,s in zip(tasks,starts):
        if s<0:continue
        load[s:s+t['duration']]+=t['power']; count[s:s+t['duration']]+=1
    return load,count

def check(tasks,starts,chargers=10,capacity=70):
    violations=[]; done=0
    if len(tasks)!=len(starts):return {'violations':['task_count'],'completed':0,'energy_error':float('nan')}
    for t,s in zip(tasks,starts):
        if s!=int(s) or s<t['release'] or s+t['duration']>min(24,t['deadline']):
            violations.append('window_'+str(t['id']))
        else:done+=1
    load,count=load_curve(tasks,starts)
    if count.max()>chargers+1e-7:violations.append('chargers')
    if load.max()>capacity+1e-7:violations.append('station_power')
    energy=sum(t['power']*t['duration'] for t in tasks)
    return {'violations':violations,'completed':done,'energy_error':float(load.sum()-energy)}

def earliest(tasks,chargers=10,capacity=70):
    starts=np.full(len(tasks),-1,int); load=np.zeros(24); count=np.zeros(24)
    for i in sorted(range(len(tasks)),key=lambda j:(tasks[j]['release'],tasks[j]['deadline'],j)):
        t=tasks[i]
        for s in range(t['release'],min(24,t['deadline'])-t['duration']+1):
            sl=slice(s,s+t['duration'])
            if np.all(load[sl]+t['power']<=capacity) and np.all(count[sl]+1<=chargers):
                starts[i]=s; load[sl]+=t['power']; count[sl]+=1; break
        if starts[i]<0:return None
    return starts

def scenarios(pred,residuals,key,count=50,independent=False):
    rng=np.random.default_rng(seed_for('scenario',key))
    if independent:
        idx=rng.integers(len(residuals),size=(count,24))
        err=residuals[idx,np.arange(24)]
    else:err=residuals[rng.integers(len(residuals),size=count)]
    return np.maximum(np.asarray(pred)[None,:]+err,0)

def solve(tasks,background,baseline=None,risk=.5,penalty=.5,chargers=10,capacity=70,time_limit=2,gap=.001):
    started=time.perf_counter()
    background=np.atleast_2d(np.asarray(background,float))
    assert background.shape[1]==24 and np.isfinite(background).all()
    # Compress exactly repeated sampled curves without changing scenario probabilities.
    bg,multiplicity=np.unique(background,axis=0,return_counts=True)
    prob=multiplicity/multiplicity.sum(); ns=len(bg); n=len(tasks)
    choices=[(j,s) for j,t in enumerate(tasks) for s in range(t['release'],min(24,t['deadline'])-t['duration']+1)]
    if any(not any(j==i for j,s in choices) for i in range(n)):
        return dict(starts=None,status=2,message='empty task window',seconds=time.perf_counter()-started,gap=None)
    k=len(choices); use_tail=risk>0 and ns>1
    nv=k+ns+(1+ns if use_tail else 0)
    c=np.zeros(nv); c[k:k+ns]=(1-risk)*prob if use_tail else prob
    if baseline is not None:
        c[:k]=[penalty*abs(s-int(baseline[j]))/n for j,s in choices]
    if use_tail:c[k+ns]=risk; c[k+ns+1:]=risk*prob/.1
    # Binary assignment; all remaining variables are continuous.
    integ=np.zeros(nv,int); integ[:k]=1
    low=np.zeros(nv); high=np.full(nv,np.inf); high[:k]=1
    assign=lil_matrix((n,nv)); power=lil_matrix((24,nv)); ports=lil_matrix((24,nv))
    for q,(j,s) in enumerate(choices):
        assign[j,q]=1
        for h in range(s,s+tasks[j]['duration']):
            power[h,q]=tasks[j]['power']; ports[h,q]=1
    blocks=[assign,power,ports]; lbs=[np.ones(n),np.full(24,-np.inf),np.full(24,-np.inf)]
    ubs=[np.ones(n),np.full(24,capacity),np.full(24,chargers)]
    peaks=lil_matrix((ns*24,nv))
    for z in range(ns):
        peaks[z*24:(z+1)*24,:k]=power[:,:k]
        peaks[z*24:(z+1)*24,k+z]=-1
    blocks.append(peaks);lbs.append(np.full(ns*24,-np.inf));ubs.append(-bg.ravel())
    if use_tail:
        tail=lil_matrix((ns,nv))
        for z in range(ns):tail[z,k+z]=1;tail[z,k+ns]=-1;tail[z,k+ns+1+z]=-1
        blocks.append(tail);lbs.append(np.full(ns,-np.inf));ubs.append(np.zeros(ns))
    A=csc_matrix(vstack(blocks,format='csc'))
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore',message='Unrecognized options detected')
        result=milp(c,integrality=integ,bounds=Bounds(low,high),
                    constraints=LinearConstraint(A,np.concatenate(lbs),np.concatenate(ubs)),
                    options={'time_limit':time_limit,'mip_rel_gap':gap,'threads':1,'random_seed':17})
    starts=None
    if result.x is not None:
        cand=np.full(n,-1,int)
        for q,(j,s) in enumerate(choices):
            if result.x[q]>.5:cand[j]=s
        if not check(tasks,cand,chargers,capacity)['violations']:starts=cand
    return dict(starts=starts,status=int(result.status),message=str(result.message),
                seconds=time.perf_counter()-started,gap=float(result.mip_gap) if getattr(result,'mip_gap',None) is not None else None,
                objective=float(result.fun) if getattr(result,'fun',None) is not None else None)

def gain_filter(tasks,baseline,candidate,bg,threshold):
    original=load_curve(tasks,baseline)[0]; shifted=load_curve(tasks,candidate)[0]
    gains=np.max(bg+original,axis=1)-np.max(bg+shifted,axis=1)
    low=float(np.quantile(gains,.1,method='linear'))
    accepted=low>threshold+1e-9
    return (candidate if accepted else baseline).copy(),dict(screen_q10_kw=low,screen_mean_kw=float(gains.mean()),
           screen_q90_kw=float(np.quantile(gains,.9)),screen_accepted=bool(accepted))
