"""Causal day-ahead load forecasts. Run from any directory with the experiment venv."""
from pathlib import Path
import json, pickle, time, hashlib, platform, sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from lightgbm import LGBMRegressor

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT/'config/protocol.json').read_text())
OUT = ROOT/'results'
DAYS = pd.date_range(CFG['start'], CFG['end'], freq='D')
HOURS = pd.date_range(CFG['start'], periods=len(DAYS)*24, freq='h')
CUTS = np.r_[0, np.cumsum(CFG['split_days'])]

def features(load, temp):
    """Features for day d never access any observation at or after d 00:00."""
    y = np.asarray(load, float)
    lf = pd.Series(y).ffill().fillna(0).to_numpy()
    tf = pd.Series(temp).ffill().fillna(0).to_numpy()
    rows = []
    for d in range(7,len(DAYS)):
        i=d*24; a=lf[i-24:i]; w=lf[i-168:i]
        t=tf[i-24:i]; tw=tf[i-168:i]
        day=DAYS[d]
        for h in range(24):
            work=int(day.weekday()<5 and 8<=h<18)
            rows.append(dict(day=d,hour=h,lead=h+1,weekday=day.weekday(),weekend=int(day.weekday()>=5),
                hour_sin=np.sin(h*np.pi/12),hour_cos=np.cos(h*np.pi/12),
                doy_sin=np.sin(day.dayofyear*2*np.pi/365.25),doy_cos=np.cos(day.dayofyear*2*np.pi/365.25),
                workhour=work,last=lf[i-1],lag24=lf[i+h-24],lag168=lf[i+h-168],
                mean24=a.mean(),std24=a.std(),min24=a.min(),max24=a.max(),
                mean168=w.mean(),std168=w.std(),min168=w.min(),max168=w.max(),
                missing24=np.isnan(y[i-24:i]).mean(),missing168=np.isnan(y[i-168:i]).mean(),
                temp_last=tf[i-1],temp_mean24=t.mean(),temp_mean168=tw.mean(),temp_delta24=tf[i-1]-tf[i-25],
                response_cool24=np.maximum(t-18,0).mean(),response_heat24=np.maximum(18-t,0).mean(),
                response_cool168=np.maximum(tw-18,0).mean(),response_heat168=np.maximum(18-tw,0).mean(),
                interaction_temp_work=t.mean()*work,interaction_cool_work=np.maximum(t-18,0).mean()*work,
                interaction_temp_sin=t.mean()*np.sin(h*np.pi/12)))
    return pd.DataFrame(rows)

def select_data():
    raw=ROOT/'data/raw'
    meta=pd.read_csv(raw/'metadata.csv')
    candidates=meta[(meta.primaryspaceusage=='Office')&(meta.electricity=='Yes')].sort_values('building_id')
    hdr=pd.read_csv(raw/'electricity.csv',nrows=0).columns.tolist()
    ids=[b for b in candidates.building_id if b in hdr]
    meter=pd.read_csv(raw/'electricity.csv',usecols=[hdr[0]]+ids,index_col=0,parse_dates=True).reindex(HOURS)
    weather=pd.read_csv(raw/'weather.csv',parse_dates=['timestamp'])
    assert not meter.index.duplicated().any()
    rows=[]; chosen=[]; sites=set(); temps={}
    for _,r in candidates.iterrows():
        b=r.building_id
        if b not in meter: continue
        y=meter[b].mask(meter[b]<0)
        t=weather[weather.site_id==r.site_id].set_index('timestamp').airTemperature
        assert not t.index.duplicated().any()
        t=t.reindex(HOURS)
        yt=y.iloc[:CUTS[1]*24]; tt=t.iloc[:CUTS[1]*24]
        valid=yt.notna().mean(); pos=(yt>0).mean(); wvalid=tt.notna().mean()
        eligible=valid>=.995 and pos>=.95 and wvalid>=.95
        pick=eligible and r.site_id not in sites and len(chosen)<3
        rows.append(dict(building=b,site=r.site_id,training_valid=valid,training_positive=pos,
                         weather_training_valid=wvalid,eligible=eligible,selected=pick))
        if pick:
            chosen.append(b); sites.add(r.site_id); temps[b]=t.to_numpy()
    assert len(chosen)==3, 'Not enough eligible buildings; do not relax rules silently'
    pd.DataFrame(rows).to_csv(OUT/'selection_audit.csv',index=False)
    meta[meta.building_id.isin(chosen)].to_csv(OUT/'selected_metadata.csv',index=False)
    meter[chosen].to_csv(ROOT/'data/processed/selected_electricity.csv')
    pd.DataFrame(temps,index=HOURS).to_csv(ROOT/'data/processed/selected_temperature.csv')
    json.dump({'buildings':chosen,'splits':{s:{'start':str(DAYS[CUTS[j]].date()),'end':str(DAYS[CUTS[j+1]-1].date()),'days':int(CUTS[j+1]-CUTS[j])}
              for j,s in enumerate(['train','tune','calibration','test'])}},(OUT/'data_split.json').open('w'),indent=2)
    return meter, temps, chosen

def fit_model(params):
    return LGBMRegressor(**params,learning_rate=.05,min_child_samples=40,verbosity=-1,n_jobs=2,
                         random_state=CFG['seed'],deterministic=True,force_col_wise=True)

def main():
    start=time.time(); meter,temps,chosen=select_data()
    contexts={}; metric_rows=[]; tuning=[]; quality=[]; alarms=[]
    for b in chosen:
        print('Forecast',b,flush=True)
        y=meter[b].mask(meter[b]<0).to_numpy().reshape(-1,24)
        feat=features(y.ravel(),temps[b]); target=y[7:].ravel(); di=feat.day.to_numpy()
        allcols=[c for c in feat if c!='day']
        colsets={'ai':allcols,
                 'no_response':[c for c in allcols if not c.startswith('response_') and c!='interaction_cool_work'],
                 'no_interaction':[c for c in allcols if not c.startswith('interaction_')],
                 'no_weather':[c for c in allcols if not c.startswith(('temp_','response_','interaction_'))]}
        train=(di<CUTS[1])&np.isfinite(target)
        tune=(di>=CUTS[1])&(di<CUTS[2])&np.isfinite(target)
        preds={}; best={}
        for name,cols in colsets.items():
            x=feat[cols]
            scores=[]
            for leaves in CFG['forecast_grid']['num_leaves']:
                for trees in CFG['forecast_grid']['n_estimators']:
                    params={'num_leaves':leaves,'n_estimators':trees}
                    model=fit_model(params); model.fit(x.loc[train],target[train])
                    pr=np.maximum(model.predict(x.loc[tune]),0)
                    mae=float(np.abs(pr-target[tune]).mean())
                    tuning.append(dict(building=b,model=name,**params,tune_mae=mae))
                    scores.append((mae,leaves,trees,model))
            score,leaves,trees,model=min(scores,key=lambda v:(v[0],v[1],v[2]))
            best[name]={'num_leaves':leaves,'n_estimators':trees,'tune_mae':score}
            pp=np.full_like(y,np.nan); pp[7:]=np.maximum(model.predict(x),0).reshape(-1,24)
            preds[name]=pp
            (OUT/'models').mkdir(exist_ok=True)
            model.booster_.save_model(str(OUT/'models'/f'{b}_{name}.txt'))
            if name=='ai':
                pd.DataFrame({'feature':cols,'gain':model.booster_.feature_importance(importance_type='gain')}).to_csv(OUT/f'{b}_feature_gain.csv',index=False)
        linear=make_pipeline(StandardScaler(),LinearRegression())
        linear.fit(feat[allcols].loc[train],target[train])
        preds['linear']=np.full_like(y,np.nan)
        preds['linear'][7:]=np.maximum(linear.predict(feat[allcols]),0).reshape(-1,24)
        with (OUT/'models'/f'{b}_linear.pkl').open('wb') as f: pickle.dump(linear,f)
        for name,col in [('weekly','lag168'),('daily','lag24')]:
            preds[name]=np.full_like(y,np.nan); preds[name][7:]=feat[col].to_numpy().reshape(-1,24)
        # Expanding-window out-of-fold residuals entirely inside training period.
        roll=[]; rolldates=[]
        for lo,hi in CFG['rolling_training_folds']:
            tr=(di<lo)&np.isfinite(target); val=(di>=lo)&(di<hi)
            model=fit_model({'num_leaves':15,'n_estimators':150})
            model.fit(feat[allcols].loc[tr],target[tr])
            pp=np.maximum(model.predict(feat[allcols].loc[val]),0).reshape(-1,24)
            rr=y[lo:hi]-pp; ok=np.isfinite(rr).all(axis=1)
            roll.extend(rr[ok]); rolldates.extend(np.arange(lo,hi)[ok])
        residual=y-preds['ai']; cal=np.arange(CUTS[2],CUTS[3]); opt=cal[:36]; screen=cal[36:]
        opt=opt[np.isfinite(residual[opt]).all(axis=1)]; screen=screen[np.isfinite(residual[screen]).all(axis=1)]
        assert len(opt)>=20 and len(screen)>=20
        threshold=float(np.nanquantile(y[:CUTS[1]],.95))
        contexts[b]={'actual':y,'pred':preds,'residual_opt':residual[opt],'residual_screen':residual[screen],
                     'opt_dates':opt,'screen_dates':screen,'rolling_residual':np.array(roll),
                     'rolling_dates':np.array(rolldates),'threshold':threshold,'best':best}
        for name,pp in preds.items():
            for split,j in [('tune',1),('test',3)]:
                yy=y[CUTS[j]:CUTS[j+1]]; pred=pp[CUTS[j]:CUTS[j+1]]
                for subset,mask in [('all',np.isfinite(yy)),('high',np.isfinite(yy)&(yy>threshold))]:
                    err=pred[mask]-yy[mask]
                    metric_rows.append(dict(building=b,model=name,split=split,subset=subset,n=int(mask.sum()),
                        mae=float(np.abs(err).mean()),rmse=float(np.sqrt((err**2).mean())),threshold_kw=threshold))
        for j,split in enumerate(['train','tune','calibration','test']):
            yy=y[CUTS[j]:CUTS[j+1]]
            quality.append(dict(building=b,split=split,total_hours=yy.size,valid_hours=int(np.isfinite(yy).sum()),
                         complete_days=int(np.isfinite(yy).all(axis=1).sum()),zero_hours=int((yy==0).sum()),
                         mean_kw=float(np.nanmean(yy)),max_kw=float(np.nanmax(yy))))
        for d in range(CUTS[3],CUTS[4]):
            if not np.isfinite(y[d]).all():continue
            from scheduler import scenarios
            sc=scenarios(preds['ai'][d],residual[opt],((b,d,CFG['baseline_seed']),'opt'),CFG['scenario_count'])
            prob=(sc>threshold).mean(axis=0)
            for h in range(24):
                alarms.append(dict(building=b,date=str(DAYS[d].date()),hour=h,probability=float(prob[h]),
                                   actual_high=bool(y[d,h]>threshold),predicted_high=bool(prob[h]>=.5)))
        pd.DataFrame([{'date':str(DAYS[d].date()),'hour':h,'actual_kw':y[d,h],**{k:v[d,h] for k,v in preds.items()}}
                     for d in range(CUTS[1],CUTS[4]) for h in range(24)]).to_csv(OUT/f'{b}_forecasts.csv',index=False)
        print('Selected models',best,flush=True)
    for name,rows in [('forecast_metrics',metric_rows),('forecast_tuning',tuning),('data_quality',quality),('alarm_predictions',alarms)]:
        pd.DataFrame(rows).to_csv(OUT/f'{name}.csv',index=False)
    with (OUT/'forecast_context.pkl').open('wb') as f: pickle.dump(contexts,f)
    (OUT/'forecast_run.json').write_text(json.dumps({'elapsed_seconds':time.time()-start,'python':sys.version,'platform':platform.platform(),
        'protocol_sha256':hashlib.sha256((ROOT/'config/protocol.json').read_bytes()).hexdigest()},indent=2))
    print('Forecast completed',time.time()-start,flush=True)

if __name__=='__main__': main()
