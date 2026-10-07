"""Independent coverage audit against the second-draft experiment matrix."""
from pathlib import Path
from collections import Counter
import json,hashlib,datetime,itertools
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results'

def main():
    split=json.loads((OUT/'data_split.json').read_text());buildings=split['buildings'];assert len(buildings)==3
    cases=[json.loads(s) for s in (OUT/'schedule_cases.jsonl').read_text().splitlines()]
    main={'rule','weekly','point','risk','full'}
    extended=main|{'mean','mean_screen','iid','iid_screen','oracle'}
    dates=pd.date_range('2017-08-07','2017-12-31').strftime('%Y-%m-%d').tolist()
    weeks=[]
    for month in [8,9,10,11,12]:
        first=datetime.date(2017,month,1)
        monday=first+datetime.timedelta(days=(-first.weekday())%7)
        while monday<datetime.date(2017,8,7):monday+=datetime.timedelta(days=7)
        weeks += [(monday+datetime.timedelta(days=i)).isoformat() for i in range(5)]
    expected_baseline=set(itertools.product(buildings,dates))
    expected_perturb=set(itertools.product(buildings,dates,['bias_minus_10pct','bias_plus_10pct','peak_early_1h','peak_late_1h']))
    expected_scale=set(itertools.product(buildings,weeks,[5,10,20],[2,4,8],range(101,111)))
    actual_baseline={(c['building'],c['date']) for c in cases if c['experiment']=='baseline'}
    actual_perturb={(c['building'],c['date'],c['perturbation']) for c in cases if c['experiment']=='perturbation'}
    actual_scale={(c['building'],c['date'],c['n_tasks'],c['flex_hours'],c['seed']) for c in cases if c['experiment']=='sensitivity'}
    assert actual_baseline==expected_baseline
    assert actual_perturb==expected_perturb
    assert actual_scale==expected_scale
    assert len(cases)==len(expected_baseline)+len(expected_perturb)+len(expected_scale)==8955
    scored=0
    for c in cases:
        if c['excluded']:
            assert c['excluded']=='missing_actual' and not c['rows']
        else:
            expected=extended if c['experiment']=='baseline' else main
            assert {r['method'] for r in c['rows']}==expected
            assert len(c['rows'])==len(expected)
            for row in c['rows']:
                assert row['completed']==c['n_tasks'] and row['violations']==0 and abs(row['energy_error_kwh'])<1e-8
            scored+=len(c['rows'])
    fm=pd.read_csv(OUT/'forecast_metrics.csv');ft=pd.read_csv(OUT/'forecast_tuning.csv')
    for b in buildings:
        for m in ['weekly','linear','ai','no_response','no_interaction','no_weather','daily']:
            assert len(fm[(fm.building==b)&(fm.model==m)&(fm.split=='test')])==2
        for m in ['ai','no_response','no_interaction','no_weather']:
            assert len(ft[(ft.building==b)&(ft.model==m)])==6
    ci=pd.read_csv(OUT/'paired_confidence_intervals.csv');assert len(ci)==18
    checks=json.loads((OUT/'verification.json').read_text());assert len(checks)==12 and all(r['passed'] for r in checks)
    protocol_hash=hashlib.sha256((ROOT/'config/protocol.json').read_bytes()).hexdigest()
    assert protocol_hash==json.loads((OUT/'forecast_run.json').read_text())['protocol_sha256']
    result=dict(primary_scope='second application draft experiments',baseline_cases=len(actual_baseline),perturbation_cases=len(actual_perturb),
        scale_flexibility_cases=len(actual_scale),scored_schedules=scored,coverage_complete=True,
        all_required_method_groups_present=True,all_6_candidate_searches_present=True,paired_ci_comparisons=18,
        algorithm_verification_checks=12,protocol_unchanged=True,excluded_reasons=dict(Counter(c['excluded'] for c in cases if c['excluded'])))
    (OUT/'completion_audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
