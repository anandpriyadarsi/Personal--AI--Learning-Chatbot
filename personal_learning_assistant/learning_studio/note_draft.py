"""Explicit bounded PDF draft extraction. Never stages, imports or publishes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from .validation import PackageError, require

MAX_BYTES=8_000_000


def convert(source, *, media_type):
    require(media_type=='application/pdf','PPT/PPTX conversion is unsupported; export a reviewed PDF first.',415)
    require(isinstance(source,bytes) and 0<len(source)<=MAX_BYTES and source.startswith(b'%PDF-'),
        'Supply a PDF of at most 8 MB.')
    # Separate worker and bounded lifetime; this is not an OS security sandbox.
    # Credentials/provider configuration are never passed to the worker.
    env={k:v for k,v in os.environ.items() if k in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE'}}
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    worker=Path(__file__).with_name('note_draft_worker.py')
    try:
        result=subprocess.run([sys.executable,str(worker)],input=source,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,timeout=12,env=env,check=False)
        require(result.returncode==0 and len(result.stdout)<=700_000,'PDF extraction unavailable or exceeds its bound.',422)
        draft=json.loads(result.stdout)
        require(draft['source_sha256']==hashlib.sha256(source).hexdigest(),'Draft source hash mismatch.',409)
        return draft
    except subprocess.TimeoutExpired as error:
        raise PackageError('PDF extraction timed out; original content remains unchanged.',422) from error
    except (OSError,ValueError,KeyError) as error:
        raise PackageError('PDF extraction unavailable; original content remains unchanged.',422) from error
