"""Replay solver error cases for diagnosis, without replacing primary outcomes."""
from pathlib import Path
import json,pickle
import numpy as np
from scheduler import earliest,solve
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results'
def main():
    ctx=pickle.load((OUT/'forecast_context.pkl').open('rb'));params=json.loads((OUT/'schedule_parameters.json').read_text());rows=[]
    for line in (OUT/'schedule_cases.jsonl').open():
        c=json.loads(line)
        for row in c['rows']:
            if row['solver_status']!=4 or row['method']!='point':continue
            p=ctx[c['building']]['pred']['ai'][c['day']].copy()
            if c['perturbation']=='bias_minus_10pct':p*=.9
            if c['perturbation']=='bias_plus_10pct':p*=1.1
            if c['perturbation']=='peak_early_1h':p=np.roll(p,-1)
            if c['perturbation']=='peak_late_1h':p=np.roll(p,1)
            base=earliest(c['tasks']);r=solve(c['tasks'],p,base,0,params[c['building']]['shift_penalty'])
            rows.append(dict(key=c['key'],original_status=4,original_fallback=row['fallback'],replay_status=r['status'],
                            message=r['message'],replay_feasible=r['starts'] is not None,seconds=r['seconds']))
    (OUT/'solver_error_diagnostics.json').write_text(json.dumps(rows,indent=2))
    print('Solver error replays',len(rows));print(json.dumps(rows[:2],indent=2))
if __name__=='__main__':main()
