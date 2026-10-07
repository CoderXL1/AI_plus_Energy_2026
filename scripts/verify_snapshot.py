"""Read-only verification of the published snapshot, using Python's standard library."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'experiments/results'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def near(actual, expected, label):
    require(math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-7), label)


def main():
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    for relative, record in manifest['files'].items():
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT), 'Manifest path outside repository')
        require(path.is_file(), 'Missing file: ' + relative)
        content = path.read_bytes()
        require(len(content) == record['bytes'], 'Size mismatch: ' + relative)
        require(hashlib.sha256(content).hexdigest() == record['sha256'], 'Hash mismatch: ' + relative)
    config_path = ROOT / 'experiments/config/protocol.json'
    cfg = json.loads(config_path.read_text())
    original = json.loads((RESULTS / 'forecast_run.json').read_text())
    require(hashlib.sha256(config_path.read_bytes()).hexdigest() == original['protocol_sha256'], 'Protocol changed')
    observed = {}
    for path in RESULTS.glob('*_forecasts.csv'):
        building = path.name.removesuffix('_forecasts.csv')
        with path.open(newline='') as stream:
            for row in csv.DictReader(stream):
                key = (building, row['date'])
                observed.setdefault(key, [math.nan] * 24)[int(row['hour'])] = float(row['actual_kw'] or 'nan')
    counts = Counter(); seen = set(); scored = excluded = 0
    main_methods = {'rule', 'weekly', 'point', 'risk', 'full'}
    extended = main_methods | {'mean', 'mean_screen', 'iid', 'iid_screen', 'oracle'}
    with (RESULTS / 'schedule_cases.jsonl').open() as stream:
        for line in stream:
            case = json.loads(line)
            require(case['key'] not in seen, 'Duplicate case')
            seen.add(case['key']); counts[case['experiment']] += 1
            actual = observed[(case['building'], case['date'])]
            if case['excluded']:
                require(case['excluded'] == 'missing_actual' and not case['rows'], 'Unexpected exclusion')
                require(not all(math.isfinite(x) for x in actual), 'Excluded a complete observation day')
                excluded += 1
                continue
            require(all(math.isfinite(x) for x in actual), 'Missing scored observation')
            rows = case['rows']; tasks = case['tasks']
            expected = extended if case['experiment'] == 'baseline' else main_methods
            require(len(rows) == len(expected) and {r['method'] for r in rows} == expected, 'Missing method')
            require(len(tasks) == case['n_tasks'], 'Wrong task count')
            rule = next(row for row in rows if row['method'] == 'rule')
            peaks = {}
            for row in rows:
                starts = row['starts']; power = [0.0] * 24; ports = [0] * 24
                require(len(starts) == len(tasks), 'Missing start time')
                for task, start in zip(tasks, starts):
                    require(isinstance(start, int), 'Noninteger start')
                    require(task['release'] <= start and start + task['duration'] <= min(24, task['deadline']), 'Window violation')
                    for hour in range(start, start + task['duration']):
                        power[hour] += task['power']; ports[hour] += 1
                require(max(ports) <= cfg['chargers'] and max(power) <= cfg['station_limit_kw'], 'Capacity violation')
                near(sum(power), sum(t['power'] * t['duration'] for t in tasks), 'Energy mismatch')
                peak = max(a + p for a, p in zip(actual, power)); peaks[row['method']] = peak
                near(peak, row['peak_kw'], 'Peak mismatch')
                near(sum(abs(a - b) for a, b in zip(starts, rule['starts'])) / len(tasks), row['mean_shift_hours'], 'Shift mismatch')
                require(row['completed'] == len(tasks) and row['violations'] == 0, 'Completion mismatch')
                near(row['energy_error_kwh'], 0, 'Recorded energy mismatch')
                scored += 1
            for row in rows:
                gain = peaks['rule'] - peaks[row['method']]
                near(row['baseline_peak_kw'], peaks['rule'], 'Baseline mismatch')
                near(row['gain_kw'], gain, 'Gain mismatch')
                near(row['reduction_pct'], 100 * gain / peaks['rule'], 'Percentage mismatch')
    require(dict(counts) == {'baseline': 441, 'perturbation': 1764, 'sensitivity': 6750}, 'Matrix counts differ')
    require(len(seen) == 8955 and excluded == 120 and scored == 46350, 'Unexpected result counts')
    print(json.dumps({'status': 'PASS', 'file_hashes_checked': len(manifest['files']),
                      'cases': len(seen), 'excluded': excluded, 'schedules_recomputed': scored,
                      'constraint_violations': 0, 'all_peak_gain_energy_checks_passed': True}, indent=2))


if __name__ == '__main__':
    main()
