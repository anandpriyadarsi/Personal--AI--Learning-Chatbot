from importlib.util import find_spec
import json
from pathlib import Path
import subprocess
import sys


def test_validation_help_is_read_only_and_portable(tmp_path):
    result=subprocess.run([sys.executable,'-m','scripts.multimodal_validate','--help'],capture_output=True,text=True)
    assert result.returncode==0
    assert '--output' in result.stdout and '--browser' in result.stdout


def test_validation_report_never_claims_other_platforms():
    from scripts.multimodal_validate import report
    value=report('Linux',[{'name':'unit','returncode':0,'passed':4,'failed':0,'skipped':0}])
    assert value['passed'] and not value['windows_verified'] and value['live_model_quality']=='unverified'
    assert not report('Windows',[{'name':'unit','returncode':0,'passed':1,'failed':0,'skipped':2}])['passed']
