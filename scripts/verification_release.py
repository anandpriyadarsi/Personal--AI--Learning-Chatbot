"""Check mandatory frozen-candidate gates through authenticated GitHub API reads.

No local user-editable result JSON can confer authority. Physical-phone and
private-fixture gates need separately provisioned trusted workflows. This tool
does not merge, sign, publish or authorize release and cannot invent those gates.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from verification_integration import github, REPOSITORY

GATES = {
    'architecture': ('.github/workflows/architecture-validation.yml',
                     ['Synthetic development (ubuntu-latest)','Synthetic development (windows-latest)', 'Cross-platform development acceptance']),
    'android': ('.github/workflows/verification-release.yml',
                ['Android source and JVM', 'Installed Android (31)', 'Installed Android (35)']),
    'private': ('.github/workflows/architecture-private-fixtures.yml', ['private-validation (Linux)', 'private-validation (Windows)']),
    # Deliberately not supplied by desktop/source checks. Provision and review
    # an actual protected physical-device workflow before changing this policy.
    'phone': ('.github/workflows/verification-phone.yml', ['Physical phone acceptance']),
}


def inspect_run(run_id, sha, workflow_path, required_jobs, repository, api):
    result = {'run_id':run_id,'source_sha':sha,'workflow':workflow_path,'state':'BLOCKED','blockers':[]}
    try:
        run = api('actions/runs/'+str(int(run_id)))
        if (run.get('head_sha') != sha or run.get('status') != 'completed'
                or run.get('conclusion') != 'success' or run.get('path','').split('@')[0] != workflow_path
                or run.get('head_repository',{}).get('full_name') != repository):
            result['blockers'].append('Stale, failed, untrusted or wrong-workflow run')
            return result
        jobs, page = [], 1
        while True:
            batch = api(f'actions/runs/{int(run_id)}/jobs?per_page=100&page={page}')
            jobs.extend(batch['jobs'])
            if len(jobs) >= batch['total_count']:
                break
            if not batch['jobs']:
                raise ValueError('Incomplete job inventory')
            page += 1
        for name in required_jobs:
            found = [j for j in jobs if j['name'] == name or j['name'].endswith(' / '+name)]
            if len(found) != 1 or found[0].get('status') != 'completed' or found[0].get('conclusion') != 'success' or found[0].get('head_sha',sha) != sha:
                result['blockers'].append('Missing, ambiguous, failed or skipped mandatory job: '+name)
        if not result['blockers']:
            result['state'] = 'PASS'
    except Exception as exc:
        result['blockers'].append(type(exc).__name__+': required GitHub evidence unavailable')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha',required=True)
    parser.add_argument('--repository',default=REPOSITORY)
    parser.add_argument('--output',default='release-certification.json')
    for name in GATES:
        parser.add_argument('--'+name+'-run',type=int)
    args=parser.parse_args(argv)
    report={'schema':'anvaya.release-gates.v2','source_sha':args.source_sha,'state':'BLOCKED',
            'release_authorized':False,'gates':{},'limitations':['Owner release approval remains required',
            'Workflow success must be accompanied by review of private/device artifacts and required cross-feature scenarios']}
    if re.fullmatch('[0-9a-f]{40}',args.source_sha) and os.environ.get('GH_TOKEN'):
        for name,(path,jobs) in GATES.items():
            run_id=getattr(args,name+'_run')
            report['gates'][name]=(inspect_run(run_id,args.source_sha,path,jobs,args.repository,
                lambda p:github(p,args.repository)) if run_id else {'state':'NOT_VERIFIED','blockers':['No required '+name+' run supplied']})
        # API job evidence establishes automated gate completion only. Owner
        # approval is intentionally outside this program's authority.
        if all(r['state']=='PASS' for r in report['gates'].values()):
            report['state']='AUTOMATED_GATES_PASS_OWNER_REVIEW_REQUIRED'
    else:
        report['blockers']=['Exact SHA and authenticated GitHub evidence required']
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['state']=='AUTOMATED_GATES_PASS_OWNER_REVIEW_REQUIRED' else 2


if __name__=='__main__':
    raise SystemExit(main())
