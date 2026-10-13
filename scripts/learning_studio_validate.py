"""Cross-platform disposable gates; Chromium is required even for healthcheck."""
import argparse
from datetime import datetime,timezone
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
BASE='775941c730e8160501c849bc4971e8eb178331d1'
DEPENDENCIES={'flask':'Flask','mistune':'mistune','pypdf':'pypdf','PIL':'Pillow','yaml':'PyYAML','dotenv':'python-dotenv','pytest':'pytest','playwright':'playwright','numpy':'numpy'}
FOCUSED=['tests/test_phase7_5_web_foundation.py','tests/test_phase7_5_courses_topics.py','tests/test_main_startup_isolation.py','tests/test_phase7_5_15_10_notes_obsidian_separation.py','tests/test_phase7_5_15_14_focus_companion_analysis.py',*[f'tests/test_assessment_studio_phase_{s}.py' for s in 'abcd']]


def health():
    errors=[]
    if sys.version_info<(3,10):errors.append('Python >=3.10 required; validated CI uses 3.12.')
    for name,label in DEPENDENCIES.items():
        try:importlib.import_module(name)
        except ImportError:errors.append(f'Missing {label}: run python -m pip install -r requirements-learning-studio.txt')
    if not errors:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,executable_path=os.environ.get('ANVAYA_BROWSER_EXECUTABLE') or None);browser.close()
        except Exception as exc:errors.append(f'Chromium unavailable: python -m playwright install --with-deps chromium. {exc}')
    return {'valid':not errors,'python':sys.version,'interpreter':sys.executable,'errors':errors}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope',choices=['health','feature','focused','all'],default='feature')
    parser.add_argument('--output',required=True);parser.add_argument('--base',default=BASE)
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    output=Path(args.output).absolute()/('run-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False)
    report={'scope':args.scope,'output':str(output),'health':health(),'gates':[]}
    def save():
        (output/'validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2))
    if not report['health']['valid']:save();return 1
    env=dict(os.environ,ANVAYA_BROWSER_TESTS='1',ANVAYA_BROWSER_ARTIFACTS=str(output/'browser'))
    with tempfile.TemporaryDirectory(prefix='anvaya-studio-validation-') as temporary:
        env['TMPDIR']=env['TEMP']=env['TMP']=temporary
        def run(name,command):
            with (output/(name+'.log')).open('w',encoding='utf-8') as log:
                result=subprocess.run(command,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['gates'].append({'name':name,'exit_code':result.returncode,'log':str(output/(name+'.log'))})
            return result.returncode==0
        ok=True
        if args.scope in {'feature','all'}:
            xml=output/'feature.xml'
            ok=run('feature',[sys.executable,'-m','pytest','-q','tests/learning_studio','--basetemp',temporary+'/feature','--junitxml',str(xml)])
            if ok:ok=run('feature-counts',[sys.executable,'scripts/learning_studio_junit_gate.py',str(xml)])
        if ok and args.scope in {'focused','all'}:
            xml=output/'focused.xml'
            ok=run('focused',[sys.executable,'-m','pytest','-q',*FOCUSED,'--basetemp',temporary+'/focused','--junitxml',str(xml)])
            if ok:ok=run('focused-counts',[sys.executable,'scripts/learning_studio_junit_gate.py',str(xml)])
        if ok and args.scope=='all':
            ok=run('full-suite',[sys.executable,'scripts/learning_studio_regression_gate.py','--base',args.base,'--output',str(output/'full-suite')])
        if ok and args.scope!='health':
            ok=run('compile',[sys.executable,'-m','compileall','-q','personal_learning_assistant/learning_studio','personal_learning_assistant/ui/web/learning_studio.py'])
            if ok:ok=run('whitespace',['git','diff','--check',args.base,'HEAD'])
    report['valid']=ok;save();return 0 if ok else 1
if __name__=='__main__':raise SystemExit(main())
