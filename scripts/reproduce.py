"""Run checks or the full protocol in a new directory, preserving submitted results."""
from pathlib import Path
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['checks', 'full'], default='checks')
    parser.add_argument('--name', default=None, help='New run directory name; existing names are never overwritten.')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    name = args.name or args.mode + '-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name):
        parser.error('Name must be 1-64 letters, digits, hyphens or underscores, starting with a letter or digit.')
    if args.workers < 1:
        parser.error('--workers must be positive')
    work = ROOT / 'runs' / name
    if work.exists():
        parser.error('Run already exists; choose a new name. No files were changed.')
    exp = work / 'experiments'
    for folder in ['src', 'config', 'data/raw']:
        shutil.copytree(ROOT / 'experiments' / folder, exp / folder,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.csv', '*.part'))
    (exp / 'results').mkdir()
    (exp / 'data/processed').mkdir()
    (work / 'reports').mkdir()
    scripts = ['verify.py'] if args.mode == 'checks' else [
        'download_data.py', 'verify.py', 'forecast.py', 'run_scheduling.py',
        'analyze.py', 'diagnostics.py', 'audit_completion.py']
    environment = os.environ.copy()
    environment['MPLCONFIGDIR'] = str(work / '.mplconfig')
    with (work / 'run.log').open('w', encoding='utf-8') as log:
        for script in scripts:
            command = [sys.executable, '-u', str(exp / 'src' / script)]
            if script == 'run_scheduling.py':
                command += ['--stage', 'all', '--workers', str(args.workers)]
            print('Running', script, flush=True)
            log.write('Running ' + script + '\n'); log.flush()
            with subprocess.Popen(command, cwd=work, env=environment, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace') as proc:
                for line in proc.stdout:
                    print(line, end='', flush=True); log.write(line); log.flush()
                status = proc.wait()
            if status:
                raise SystemExit(f'{script} failed with status {status}; inspect {work / "run.log"}')
    print('Completed:', work.relative_to(ROOT))


if __name__ == '__main__':
    main()
