"""Run isolated offline Phase 1 checks and record the actual host platform.

No personal database migration, live provider call, or model download is run.
Install requirements-dev.txt and optional browser tooling before requesting it.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

UNIT=['tests/test_multimodal_contracts.py','tests/test_multimodal_jobs.py',
      'tests/test_multimodal_grounding.py','tests/test_multimodal_web.py',
      'tests/test_multimodal_vision.py','tests/test_multimodal_pilot.py',
      'tests/test_multimodal_validation_command.py']


def report(system,suites):
    passed=bool(suites) and all(s['returncode']==0 and s['failed']==0 and s['skipped']==0 and s['passed']>0 for s in suites)
    return dict(platform=system,passed=passed,windows_verified=system=='Windows' and passed,
                live_model_quality='unverified',video_asr='deferred',suites=suites)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path,help='JSON report destination')
    parser.add_argument('--browser',action='store_true',help='Also exercise installed Playwright Chromium; never installs a browser')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    env=dict(os.environ)
    for name in ('LLM_API_KEY','ANVAYA_MM_VISION_KEY','VISION_API_KEY','OPENAI_API_KEY'):env.pop(name,None)
    env['ANVAYA_MM_MONTHLY_MICROS']='0'
    suites=[]
    with tempfile.TemporaryDirectory(prefix='anvaya-validation-') as temporary:
        groups=[('unit',UNIT)]
        if args.browser:groups.append(('browser',['tests/test_multimodal_browser.py']))
        for name,files in groups:
            if name=='browser':env['ANVAYA_BROWSER_TESTS']='1'
            command=[sys.executable,'-m','pytest','-q',*files,'--basetemp',str(Path(temporary)/name)]
            result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
            output=result.stdout+'\n'+result.stderr
            counts={label:sum(int(v) for v in re.findall(r'(\d+) '+label+r'\b',output)) for label in ('passed','failed','skipped')}
            suites.append(dict(name=name,command=command,returncode=result.returncode,**counts,output=output))
    value=report(platform.system(),suites)
    value['working_tree_dirty']=bool(subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip())
    value.update(python=sys.version.split()[0],source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip())
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in value.items() if k!='suites'}))
    return 0 if value['passed'] else 1

if __name__=='__main__':sys.exit(main())
