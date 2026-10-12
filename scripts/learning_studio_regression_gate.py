"""Run the whole suite on the verified base and feature; report every failure.

This is a regression-delta gate, not a claim that a red whole suite passed.
The raw suites and baseline-only blockers are always kept as CI artifacts.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def results(path):
    tree = ET.parse(path)
    rows = []
    for case in tree.iter('testcase'):
        kind = 'passed'
        for candidate in ('failure', 'error', 'skipped'):
            if case.find(candidate) is not None: kind = candidate
        rows.append((case.get('classname', '') + '::' + case.get('name', ''), kind))
    return rows


def run(root, folder, name):
    xml = folder / (name + '.xml')
    log = folder / (name + '.log')
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--junitxml', str(xml)],
                                 cwd=root, stdout=output, stderr=subprocess.STDOUT, env=dict(os.environ))
    rows = results(xml)
    summary = {key: sum(kind == key for _, kind in rows) for key in ('passed', 'failure', 'error', 'skipped')}
    return process.returncode, rows, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='9ed585ca8e1fbcfb6f5a7e0426d030560109115e')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = Path(args.output).absolute(); folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='anvaya-studio-baseline-') as temp:
        base = Path(temp) / 'baseline'
        subprocess.run(['git', 'worktree', 'add', '--detach', str(base), args.base], cwd=root, check=True, stdout=subprocess.DEVNULL)
        try:
            base_code, base_rows, baseline = run(base, folder, 'baseline-full-suite')
            feature_code, feature_rows, feature = run(root, folder, 'feature-full-suite')
        finally:
            subprocess.run(['git', 'worktree', 'remove', '--force', str(base)], cwd=root, check=True)
    base_failed = {name for name, kind in base_rows if kind in ('failure', 'error')}
    feature_failed = {name for name, kind in feature_rows if kind in ('failure', 'error')}
    added = sorted(feature_failed-base_failed)
    report = {'base_sha': args.base, 'feature_sha': subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
              'baseline': baseline, 'feature': feature, 'baseline_exit_code': base_code, 'feature_exit_code': feature_code,
              'new_failures': added, 'baseline_failures': sorted(base_failed),
              'whole_suite_green': feature_code == 0, 'regression_delta_green': not added and base_code in (0,1) and feature_code in (0,1)}
    (folder/'regression-delta.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['regression_delta_green'] else 1


if __name__ == '__main__': raise SystemExit(main())
