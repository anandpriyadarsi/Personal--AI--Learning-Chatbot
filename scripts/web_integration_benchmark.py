"""Reproducible local web-only synthetic latency and streaming backup measurements."""
from pathlib import Path
from io import BytesIO
import argparse
import hashlib
import json
import platform
import statistics
import tempfile
import time
import tracemalloc
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from personal_learning_assistant.services.native_document_library import NativeDocumentLibrary
from personal_learning_assistant.ui.web import create_app
from personal_learning_assistant.android_backup import export_backup_file,stage_restore,apply_pending_restore


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='anvaya-web-benchmark-') as temporary:
        root=Path(temporary);lib=NativeDocumentLibrary(root/'data/native_library',autostart=False)
        try:
            folders=[lib.create_folder(f'Folder {i}') for i in range(100)]
            for i in range(1000):lib.upload(BytesIO(f'Synthetic fact {i}'.encode()),f'Lecture {i}.txt',folder_id=folders[i%100]['id'],indexing=False)
            app=create_app({'TESTING':True,'NATIVE_LIBRARY_SERVICE':lib,'NATIVE_LIBRARY_CATALOGUE_FACTORY':lambda:{'courses':[]}})
            client=app.test_client();timings={}
            cases={'folder':lambda:client.get('/library/files?folder_id='+folders[0]['id']),
                   'metadata_search':lambda:lib.metadata_search('Lecture 99')}
            for name,action in cases.items():
                for _ in range(5):action()
                samples=[]
                for _ in range(60):
                    start=time.perf_counter();result=action();samples.append((time.perf_counter()-start)*1000)
                    if name=='folder':assert result.status_code==200
                samples.sort();timings[name]={'samples':60,'p50_ms':round(statistics.median(samples),3),'p95_ms':round(samples[56],3)}
            # More than the old aggregate cap; no full-file allocation/read.
            large=root/'data/large-synthetic.bin';block=b'private synthetic lecture block\n'*8192
            with large.open('wb') as stream:
                for _ in range(470):stream.write(block)
            assert large.stat().st_size>100*1024*1024
            tracemalloc.start();archive=export_backup_file(root);_,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            dest=root/'restore'
            with archive.open('rb') as stream:stage_restore(dest,stream)
            assert apply_pending_restore(dest)
            def digest(path):
                with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
            assert digest(large)==digest(dest/'data/large-synthetic.bin')
            result={'platform':platform.platform(),'python':platform.python_version(),'documents':1000,'folders':100,
                    'latency':timings,'backup':{'payload_bytes':large.stat().st_size,'archive_bytes':archive.stat().st_size,
                    'peak_traced_python_bytes':peak,'roundtrip_hash_equal':True},
                    'limits':'Shared Linux executor; warm caches. Traced Python allocations exclude native-process RSS. No phone or Windows measurement.'}
            Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
        finally:lib.close()

if __name__=='__main__':main()
