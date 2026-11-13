"""Bounded synthetic offline verification. Never installs, migrates personal owners,
activates live providers, or dispatches CI. --full-offline runs all local gates.
"""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

GATES=('unit','browser','restore','integrity')
DEPENDENCIES=('pytest','Flask','pypdf','PyMuPDF','Pillow','mistune','PyYAML','python-dotenv','requests','playwright')


def unit_files(root):
    """Discover added multimodal coverage; browser and restore have separate gates."""
    return [p.relative_to(root).as_posix() for p in sorted((root/'tests').glob('test_multimodal_*.py'))
            if not p.name.startswith(('test_multimodal_browser','test_multimodal_restore'))]


def _status(suite):
    if not suite.get('requested',True):return 'NOT_AUTHORIZED'
    if suite.get('blocked_reason'):return 'BLOCKED_ENVIRONMENT'
    return 'PASS' if (suite.get('executed',True) and not suite.get('timed_out',False)
                      and suite.get('returncode')==0 and suite.get('passed',0)>0
                      and all(suite.get(k,0)==0 for k in ('failed','errors','skipped'))) else 'FAIL'


def report(system,suites):
    """system is descriptive only; platform evidence can never be passed in."""
    by_name={s['name']:s for s in suites}
    gates={name:dict(requested=name in by_name,executed=bool(by_name.get(name,{}).get('executed',name in by_name)),
                     status=_status(by_name[name]) if name in by_name else 'NOT_AUTHORIZED') for name in GATES}
    passed=bool(suites) and all(_status(s)=='PASS' for s in suites)
    offline=all(gates[n]['status']=='PASS' for n in GATES)
    windows=platform.system()=='Windows' and offline
    gates['windows_runtime']=dict(requested=True,executed=windows,status='PASS' if windows else 'BLOCKED_ENVIRONMENT',
                                  reason='' if windows else 'Requires all offline gates on an actual Windows host')
    gates['live_model']=dict(requested=False,executed=False,status='NOT_AUTHORIZED')
    return dict(report_version=2,platform=platform.system(),reported_platform=system,passed=passed,offline_passed=offline,
                windows_runtime_verified=windows,windows_verified=windows,
                live_model_quality='unverified',video_asr='deferred',
                release_readiness='conditional' if offline else 'not_ready',gates=gates,suites=suites)


def junit_counts(path):
    root=ET.parse(path).getroot()
    # Read leaf suites only: nested aggregate attributes must not double-count.
    suites=[element for element in root.iter('testsuite') if not list(element.iter('testsuite'))[1:]]
    if not suites:suites=[root]
    totals=dict(passed=0,failed=0,errors=0,skipped=0,collected=0)
    for suite in suites:
        cases=list(suite.iter('testcase'))
        counts={label:sum(c.find(tag) is not None for c in cases)
                for label,tag in (('failed','failure'),('errors','error'),('skipped','skipped'))}
        for label,attribute in (('failed','failures'),('errors','errors'),('skipped','skipped')):
            counts[label]=max(counts[label],int(suite.get(attribute,'0')))
        counts['collected']=max(len(cases),int(suite.get('tests','0')))
        counts['passed']=max(0,len(cases)-counts['failed']-counts['errors']-counts['skipped'])
        for label,value in counts.items():totals[label]+=value
    return totals



def _credential(name):
    return bool(re.search(r'(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTHORIZATION)',name,re.I))


def redact(value):
    text=str(value)
    for name,secret in os.environ.items():
        if _credential(name) and len(secret)>=4:text=text.replace(secret,'[REDACTED]')
    text=re.sub(r'(?i)(Bearer\s+)\S+',r'\1[REDACTED]',text)
    text=re.sub(r'(?i)((?:api[_-]?key|token|secret|password)\s*[=:]\s*)[^\s,;]+',r'\1[REDACTED]',text)
    # Keep artifacts shareable without leaking the home-directory username.
    home=str(Path.home())
    if len(home)>1:text=text.replace(home,'<HOME>')
    return text


def offline_environment(root,screenshots):
    env={k:v for k,v in os.environ.items() if not _credential(k)}
    for name in list(env):
        if re.search(r'(?:BUDGET|MONTHLY_MICROS|MAX_COST)',name,re.I):env[name]='0'
    env.update(ANVAYA_MM_MONTHLY_MICROS='0',ANVAYA_OFFLINE_GUARD='1',
               ANVAYA_WEB_ARTIFACTS=str(screenshots),PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               PLAYWRIGHT_DISABLE_FORCED_CHROMIUM_PROXIED_LOOPBACK='1')
    guard=root/'scripts'/'offline_guard'
    env['PYTHONPATH']=os.pathsep.join([str(guard),str(root),env.get('PYTHONPATH','')])
    return env


def blocked_suite(name,reason,deadline):
    return dict(name=name,requested=True,executed=False,status='BLOCKED_ENVIRONMENT',blocked_reason=reason,
                returncode=None,passed=0,failed=0,errors=0,skipped=0,collected=0,timed_out=False,deadline_seconds=deadline)


def browser_prerequisite(env):
    # Probe in a bounded, credential-cleared child; driver startup must not hang
    # the orchestrator or leave Node alive before the browser suite starts.
    command=[sys.executable,'-c',
             "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p: print(p.chromium.executable_path)"]
    process=None
    try:
        process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 text=True,start_new_session=os.name!='nt',
                                 creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        output,_=process.communicate(timeout=30)
        if process.returncode:return 'Playwright unavailable; prepare the approved environment explicitly'
        executable=Path(env.get('ANVAYA_CHROMIUM_PATH') or output.strip())
        if not executable.is_file():return 'Chromium executable absent; install browser explicitly before validation'
    except (OSError,subprocess.TimeoutExpired):return 'Playwright prerequisite probe unavailable or exceeded 30 seconds'
    finally:
        if process is not None:_terminate(process)
    return None


def _terminate(process):
    if os.name=='nt':
        try:subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=10)
        except (OSError,subprocess.TimeoutExpired):process.kill()
    else:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill()


def run_suite(name,command,root,env,artifacts,deadline):
    artifacts.mkdir(parents=True,exist_ok=True)
    junit=artifacts/(name+'.xml');log=artifacts/(name+'.log')
    # A rerun must never accept old JUnit evidence after a startup failure.
    junit.unlink(missing_ok=True)
    started=time.monotonic()
    # Spool output directly to disk so a malformed test cannot exhaust memory.
    raw=artifacts/(name+'.raw.log')
    timed_out=False;returncode=None
    try:
        with raw.open('w',encoding='utf-8') as stream:
            process=subprocess.Popen(command,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                     start_new_session=os.name!='nt',
                                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
            try:returncode=process.wait(timeout=deadline)
            except subprocess.TimeoutExpired:
                timed_out=True;_terminate(process);returncode=process.returncode
            finally:
                # Also kill lingering browser/worker children after a normal pytest exit.
                _terminate(process)
        log.write_text(redact(raw.read_text(encoding='utf-8',errors='replace')),encoding='utf-8')
    except OSError as exc:
        log.write_text(redact(type(exc).__name__+': '+str(exc)),encoding='utf-8')
    finally:raw.unlink(missing_ok=True)
    counts=dict(passed=0,failed=0,errors=0,skipped=0,collected=0)
    junit_error=None
    if junit.exists():
        try:
            counts=junit_counts(junit)
            tree=ET.parse(junit)
            for element in tree.iter():
                if element.text:element.text=redact(element.text)
                if element.tail:element.tail=redact(element.tail)
                element.attrib.update({key:redact(value) for key,value in element.attrib.items()})
            tree.write(junit,encoding='utf-8',xml_declaration=True)
        except (ET.ParseError,OSError):junit_error='Invalid JUnit evidence'
    else:junit_error='No JUnit evidence'
    value=dict(name=name,requested=True,executed=True,command=[redact(c) for c in command],
               returncode=returncode,**counts,timed_out=timed_out,deadline_seconds=deadline,
               duration_seconds=round(time.monotonic()-started,3),junit_path=str(junit) if junit.exists() else None,
               log_path=str(log),junit_error=junit_error)
    value['status']=_status(value)
    return value


def host_evidence(root):
    def git(*args):
        try:return subprocess.check_output(['git',*args],cwd=root,text=True,stderr=subprocess.DEVNULL,timeout=10).strip()
        except (OSError,subprocess.SubprocessError):return None
    dependencies={}
    for name in DEPENDENCIES:
        try:dependencies[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:dependencies[name]=None
    dirty=git('status','--porcelain')
    return dict(python=platform.python_version(),python_implementation=platform.python_implementation(),
                os_release=platform.release(),machine=platform.machine(),source_sha=git('rev-parse','HEAD'),
                working_tree_dirty=None if dirty is None else bool(dirty),dependencies=dependencies)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path,help='JSON report destination')
    parser.add_argument('--browser',action='store_true',help='Run installed real Chromium without installing it')
    parser.add_argument('--restore',action='store_true',help='Run synthetic activation/restore and integrity gates')
    parser.add_argument('--full-offline',action='store_true',help='Run focused unit, real browser, synthetic restore and integrity gates')
    parser.add_argument('--suite-timeout',type=float,default=600,help='Deadline in seconds per suite (default 600)')
    args=parser.parse_args(argv)
    if args.suite_timeout<=0:parser.error('--suite-timeout must be positive')
    root=Path(__file__).resolve().parents[1]
    output=args.output.resolve();artifacts=output.parent/(output.stem+'-artifacts');artifacts.mkdir(parents=True,exist_ok=True)
    screenshots=artifacts/'screenshots';screenshots.mkdir(exist_ok=True)
    for previous in screenshots.glob('*.png'):previous.unlink()
    env=offline_environment(root,screenshots)
    suites=[]
    groups=[('unit',unit_files(root),[])]
    if args.full_offline or args.browser:groups.append(('browser',['tests/test_multimodal_browser.py'],[]))
    if args.full_offline or args.restore:
        groups.extend([('restore',['tests/test_multimodal_restore.py'],['-k','not integrity']),
                       ('integrity',['tests/test_multimodal_restore.py'],['-k','integrity'])])
    with tempfile.TemporaryDirectory(prefix='anvaya-validation-') as temporary:
        for name,files,options in groups:
            if not files:
                suites.append(blocked_suite(name,'No focused tests discovered',args.suite_timeout));continue
            if name=='browser':
                reason=browser_prerequisite(env)
                if reason:suites.append(blocked_suite(name,reason,args.suite_timeout));continue
            child_env=dict(env,ANVAYA_BROWSER_TESTS='1' if name=='browser' else '0')
            command=[sys.executable,'-m','pytest','-p','scripts.multimodal_offline_plugin','-q',*files,*options,
                     '--basetemp',str(Path(temporary)/name),'--junitxml',str(artifacts/(name+'.xml'))]
            suites.append(run_suite(name,command,root,child_env,artifacts,args.suite_timeout))
    value=report(platform.system(),suites)
    value.update(host_evidence(root))
    value.update(created_at=datetime.now(timezone.utc).isoformat(),
                 offline_network='deny outbound; loopback only; Python children inherit socket guard; Chromium dead proxy with loopback bypass',
                 synthetic_only=True,screenshots=[str(p) for p in sorted(screenshots.glob('*.png'))],
                 personal_activation=False,live_calls=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(value,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in value.items() if k not in ('suites','dependencies','screenshots')}))
    return 0 if value['passed'] else 1


if __name__=='__main__':sys.exit(main())
