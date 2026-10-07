"""Post-hoc zero-reading diagnostics. Does not alter any primary experiment or fit."""
from pathlib import Path
import pickle,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results'
def main():
    with (OUT/'forecast_context.pkl').open('rb') as f:ctx=pickle.load(f)
    days=pd.date_range('2016-01-01','2017-12-31');start=584;rows=[];monthly=[];conditions=[]
    for b,c in ctx.items():
        y=c['actual'];test=y[start:];zero=(test==0);complete=np.isfinite(test).all(axis=1)
        for group,mask in [('all_observed',np.isfinite(test)),('strictly_positive_hours',test>0),
                           ('complete_days_without_zero',np.repeat((complete & ~zero.any(axis=1))[:,None],24,axis=1))]:
            for m in ['weekly','daily','linear','ai']:
                e=(c['pred'][m][start:]-test)[mask]
                rows.append(dict(building=b,group=group,model=m,n_hours=int(len(e)),mae=float(np.abs(e).mean()),rmse=float(np.sqrt(np.mean(e**2)))))
        for period in days[start:].to_period('M').unique():
            ix=np.where(days.to_period('M')==period)[0];ix=ix[ix>=start];yy=y[ix]
            monthly.append(dict(building=b,month=str(period),mean_kw=float(np.nanmean(yy)),zero_hours=int((yy==0).sum()),
                total_hours=int(yy.size),zero_all_day_count=int(np.all(yy==0,axis=1).sum())))
        for d in range(start,len(days)):
            conditions.append(dict(building=b,day=d,zero_any_hour=bool(np.any(y[d]==0)),all_zero_day=bool(np.all(y[d]==0))))
    pd.DataFrame(rows).to_csv(OUT/'posthoc_forecast_zero_diagnostics.csv',index=False)
    pd.DataFrame(monthly).to_csv(OUT/'posthoc_monthly_load_diagnostics.csv',index=False)
    sched_path=OUT/'all_scheduling_metrics.csv'
    if sched_path.exists():
        s=pd.read_csv(sched_path);s=s[s.experiment=='baseline'].merge(pd.DataFrame(conditions),on=['building','day'])
        output=[]
        for (b,m),g in s.groupby(['building','method']):
            for group,h in [('all_complete_days',g),('complete_days_without_zero',g[~g.zero_any_hour]),('all_zero_days',g[g.all_zero_day])]:
                if not len(h):continue
                output.append(dict(building=b,method=m,group=group,n_days=len(h),mean_reduction_pct=float(h.reduction_pct.mean()),
                     mean_gain_kw=float(h.gain_kw.mean()),negative_pct=float(100*h.negative.mean())))
        pd.DataFrame(output).to_csv(OUT/'posthoc_scheduling_zero_diagnostics.csv',index=False)
    print('Post-hoc diagnostics saved; primary results unchanged')
if __name__=='__main__':main()
