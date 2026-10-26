"""Read-only live stream resolution and Git-object-only merge preview.

Never checkout, reset, merge a worktree, push a ref or modify source branches.
GitHub metadata failures remain blockers. A prepared tree is not verification.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from verification_policy import affected

REPOSITORY = 'anandpriyadarsi/Personal--AI--Learning-Chatbot'


def github(path, repository=REPOSITORY):
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', repository):
        raise ValueError('Invalid repository')
    request = urllib.request.Request(f'https://api.github.com/repos/{repository}/{path}', headers={
        'Accept':'application/vnd.github+json', 'X-GitHub-Api-Version':'2022-11-28',
        **({'Authorization':'Bearer '+os.environ['GH_TOKEN']} if os.environ.get('GH_TOKEN') else {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args], text=True, stderr=subprocess.PIPE).strip()


def ancestor(root, a, b):
    result = subprocess.run(['git','-C',str(root),'merge-base','--is-ancestor',a,b], capture_output=True)
    if result.returncode not in (0,1):
        raise ValueError('Cannot establish commit ancestry; fetch complete histories')
    return result.returncode == 0


def changed(root, base, head):
    # Merge base explicitly validates connected histories; use no-renames so
    # deleted paths and original areas remain visible.
    merge_base = git(root,'merge-base',base,head)
    return git(root,'diff','--no-renames','--name-only',merge_base,head).splitlines()


def preview(root, base, heads):
    result = {'status':'BLOCKED', 'base_sha':base, 'source_shas':heads,
              'included_by':{}, 'overlaps':[], 'blockers':[], 'verified':False}
    try:
        for sha in [base,*heads.values()]:
            if not re.fullmatch('[0-9a-f]{40}',sha):
                raise ValueError('Preview requires exact full commit SHAs')
            git(root,'cat-file','-e',sha+'^{commit}')
        files = {name:set(changed(root,base,sha)) for name,sha in heads.items()}
        for a,b in itertools.combinations(heads,2):
            shared = sorted(files[a] & files[b])
            stacked = ancestor(root,heads[a],heads[b]) or ancestor(root,heads[b],heads[a])
            if shared:
                result['overlaps'].append({'streams':[a,b], 'files':shared,'stacked':stacked})
        # Equal heads use the first name. Strict ancestors are included by a
        # descendant, so their commits are never reapplied independently.
        kept = []
        for name,sha in heads.items():
            if ancestor(root,sha,base):
                result['included_by'][name] = 'base'
                continue
            descendants = [n for n,s in heads.items() if n != name and s != sha and ancestor(root,sha,s)]
            equal = next((n for n in kept if heads[n] == sha), None)
            if descendants or equal:
                result['included_by'][name] = equal or sorted(descendants)[0]
            else:
                kept.append(name)
        candidate = base
        for name in kept:
            proc = subprocess.run(['git','-C',str(root),'merge-tree','--write-tree','--name-only',candidate,heads[name]],
                                  capture_output=True,text=True)
            if proc.returncode:
                # --write-tree lists conflict file names before its explanatory
                # messages. Keep only paths, never conflicting document text.
                result['conflicting_files'] = sorted({p for p in files[name]
                    if p in proc.stdout.splitlines()})
                result.update(status='CONFLICT' if proc.returncode == 1 else 'BLOCKED',
                              blockers=['Cannot combine stream '+name+'; inspect overlapping files with git merge-tree'])
                return result
            tree = proc.stdout.splitlines()[0]
            # commit-tree writes immutable local objects only. Fixed identity
            # avoids depending on the maintainer's local Git configuration.
            env = {**os.environ, 'GIT_AUTHOR_NAME':'ANVAYA preview', 'GIT_AUTHOR_EMAIL':'preview@example.invalid',
                   'GIT_COMMITTER_NAME':'ANVAYA preview','GIT_COMMITTER_EMAIL':'preview@example.invalid'}
            candidate = subprocess.check_output(['git','-C',str(root),'commit-tree',tree,
                         '-p',candidate,'-p',heads[name],'-m','Unverified integration preview: '+name],env=env,text=True).strip()
        result.update(status='PREPARED_NOT_VERIFIED', candidate_commit=candidate,
                      candidate_tree=git(root,'rev-parse',candidate+'^{tree}'))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        result['blockers'].append(str(exc))
    return result


def inspect_candidate(root, base, heads, candidate):
    """Inventory an existing manual composition; ancestry is never test evidence."""
    result={'status':'BLOCKED','base_sha':base,'source_shas':heads,'included_by':{},
            'blockers':[],'verified':False,'integration_method':'existing_candidate'}
    try:
        for sha in [base,candidate,*heads.values()]:
            if not re.fullmatch('[0-9a-f]{40}',sha): raise ValueError('Exact commit SHAs required')
            git(root,'cat-file','-e',sha+'^{commit}')
        if not heads or not ancestor(root,base,candidate):
            raise ValueError('Candidate must retain current main and every source head')
        for name,sha in heads.items():
            if not ancestor(root,sha,candidate): raise ValueError('Candidate is missing source stream '+name)
            result['included_by'][name]='candidate'
        result.update(status='PREPARED_NOT_VERIFIED',candidate_commit=candidate,
                      candidate_tree=git(root,'rev-parse',candidate+'^{tree}'))
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        result['blockers'].append(str(error))
    return result


def resolve(config, api=github):
    manifest = {'schema':'anvaya.integration-manifest.v2', 'resolved_at':datetime.now(timezone.utc).isoformat(),
                'repository':config['repository'], 'streams':[], 'blockers':[], 'certified':False}
    base = api('branches/'+urllib.parse.quote(config.get('base','main'),safe=''))
    manifest['base_sha'] = base['commit']['sha']
    manifest['main_protected'] = base.get('protected',False)
    for stream in config['streams']:
        record = {**stream, 'verification_state':'NOT_VERIFIED', 'integration_readiness':'BLOCKED',
                  'outstanding_blockers':[], 'parent_base_relationships':[], 'files_modified':[],
                  'shared_components_affected':[]}
        try:
            head = api('branches/'+urllib.parse.quote(stream['source_branch'],safe=''))
            record['source_sha'] = head['commit']['sha']
            for number in stream.get('related_pull_requests',[]):
                pr = api('pulls/'+str(number))
                record['parent_base_relationships'].append({'pull_request':number,'base':pr['base']['ref'],
                    'head':pr['head']['ref'],'state':pr['state'],'merged':bool(pr.get('merged_at'))})
            compare = api('compare/'+manifest['base_sha']+'...'+record['source_sha'])
            files = compare.get('files',[])
            record['files_modified'] = sorted({p for f in files for p in (f['filename'],f.get('previous_filename',f['filename']))})
            record['shared_components_affected'] = affected(record['files_modified'])['components']
            if len(files) >= 300:
                record['outstanding_blockers'].append('GitHub comparison may be truncated; fetch Git history before preview')
                manifest['blockers'].append(stream['name']+': possibly truncated modified-file inventory')
            runs = api('actions/runs?head_sha='+record['source_sha']+'&per_page=100')
            record['workflow_evidence'] = [{'id':r['id'],'url':r['html_url'],'workflow_id':r['workflow_id'],
                'conclusion':r.get('conclusion'),'status':r['status'],'head_sha':r['head_sha']}
                for r in runs.get('workflow_runs',[]) if r['head_sha'] == record['source_sha']]
            record['outstanding_blockers'].append('Source-branch runs do not certify a combined tree; run integration and installed Android gates')
        except Exception as exc:
            record['outstanding_blockers'].append(type(exc).__name__+': live source/evidence resolution unavailable')
            manifest['blockers'].append(stream['name']+': live metadata resolution failed')
        manifest['streams'].append(record)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='verification/streams.json')
    parser.add_argument('--output',default='integration-manifest.json')
    parser.add_argument('--preview',action='store_true',help='Require fetched complete history; write objects, never refs')
    parser.add_argument('--candidate',help='Exact existing integrated SHA; inventory only, never certification')
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text())
    try:
        manifest = resolve(config, lambda p:github(p,config['repository']))
        if args.preview:
            heads = {s['name']:s['source_sha'] for s in manifest['streams'] if s.get('source_sha')}
            if len(heads) != len(config['streams']):
                manifest['blockers'].append('Cannot preview without every exact source head')
            else:
                automatic=preview(Path.cwd(),manifest['base_sha'],heads)
                if args.candidate:
                    manifest['automatic_preview']=automatic
                    manifest['preview']=inspect_candidate(Path.cwd(),manifest['base_sha'],heads,args.candidate)
                else:
                    manifest['preview']=automatic
    except Exception as exc:
        manifest = {'schema':'anvaya.integration-manifest.v2','blockers':[type(exc).__name__+': resolution failed'], 'certified':False}
    Path(args.output).write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    return 2 if manifest.get('blockers') or manifest.get('preview',{}).get('status','PREPARED_NOT_VERIFIED') != 'PREPARED_NOT_VERIFIED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
