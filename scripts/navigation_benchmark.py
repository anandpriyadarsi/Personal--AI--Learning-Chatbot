"""Disposable real HTTP/browser benchmark. Synthetic data only; no device claim."""
import argparse
import io
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time

parser=argparse.ArgumentParser()
parser.add_argument('--repo',default=str(Path(__file__).resolve().parents[1]))
parser.add_argument('--output',required=True)
parser.add_argument('--samples',type=int,default=25)
args=parser.parse_args()
sys.path.insert(0,args.repo)
sys.path.insert(0,str(Path(args.repo)/'tests'))
from pypdf import PdfWriter
from werkzeug.serving import make_server, WSGIRequestHandler
from playwright.sync_api import sync_playwright
from tests.learning_studio.helpers import package,catalogue
from personal_learning_assistant.learning_studio.service import LearningStudioService
from personal_learning_assistant.repositories.sqlite.migration_runner import apply_migrations
from personal_learning_assistant.services.knowledge_reader_service import KnowledgeReaderService
from personal_learning_assistant.ui.web import create_app
import config
import sqlite3


def stats(values):
    return {'median_ms':round(statistics.median(values),2),
            'p95_ms':round(sorted(values)[min(len(values)-1,int(len(values)*.95))],2),'samples':len(values)}


class Quiet(WSGIRequestHandler):
    def log_request(self,*args,**kwargs): pass


with tempfile.TemporaryDirectory(prefix='anvaya-benchmark-') as directory:
    root=Path(directory)
    from tests.test_phase7_5_academic_agent_web import build_test_web_service
    (root/'tutor').mkdir()
    tutor,db,_,_,_=build_test_web_service(root/'tutor')
    # Every page reads the same disposable canonical owner, as on the device.
    with sqlite3.connect(db) as con:
        con.execute('PRAGMA journal_mode=DELETE')
        for i in range(200):
            con.execute('INSERT INTO knowledge_documents(id,kind,path_key,mime_type,content_hash,extraction_status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                (f'd{i}','pdf',f'course/Synthetic lecture {i}.pdf','application/pdf','a'*64,'complete','2026-10-24T00:00:00Z','2026-10-24T00:00:00Z'))
    config.DATABASE_PATH=db
    config.DATA_PATH=root
    config.NOTES_FILE=str(root/'notes.json');config.RESOURCES_FILE=str(root/'resources.json')
    writer=PdfWriter()
    for _ in range(2):writer.add_blank_page(width=612,height=792)
    writer.add_attachment('synthetic-padding.txt',b'x'*12_000_000)
    buffer=io.BytesIO();writer.write(buffer);raw=buffer.getvalue()
    studio=LearningStudioService(root/'learning_studio.sqlite3',source_loader=lambda _:raw,catalogue_loader=catalogue)
    studio.stage(package(raw));studio.publish('synthetic',1)
    app=create_app({'ACADEMIC_AGENT_WEB_SERVICE_FACTORY':lambda:tutor,'TESTING':True,'ACADEMIC_DATABASE_PATH':db,'LEARNING_LIBRARY_DATABASE_PATH':db,
        'KNOWLEDGE_READER_SERVICE_FACTORY':lambda:KnowledgeReaderService(database_path=db),
        'LEARNING_STUDIO_SERVICE_FACTORY':lambda:studio})
    server=make_server('127.0.0.1',0,app,threaded=True,request_handler=Quiet)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    paths={'Home':'/','Learning Studio':'/learning','Library':'/library','Knowledge / Resources':'/library?view=search',
        'Assessment':'/assessments','Tutor':'/agent','Analysis':'/analysis','Existing note':'/learning/modules/synthetic/1?view=learn'}
    result={'environment':{'kind':'Chromium Linux container; browser CPU/network emulation, not Android',
        'viewport':'390x844','cpu_slowdown':4,'latency_ms':80,'download_bytes_sec':1_600_000,'upload_bytes_sec':750_000,
        'source_pdf_bytes':len(raw),'library_documents':200,'readiness':'load event; excludes artificial networkidle waits'},'routes':{}}
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            result['environment']['browser']=browser.version
            context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            page=context.new_page();cdp=context.new_cdp_session(page)
            cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
            cdp.send('Network.enable')
            cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':80,
                'downloadThroughput':1_600_000,'uploadThroughput':750_000})
            failures=[];errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            for name,path in paths.items():
                cdp.send('Network.clearBrowserCache')
                start=time.perf_counter();response=page.goto(base+path,wait_until='load')
                cold=(time.perf_counter()-start)*1000
                values=[];transfer=[];heap=[]
                for _ in range(args.samples):
                    page.goto('about:blank')
                    start=time.perf_counter();response=page.goto(base+path,wait_until='load')
                    values.append((time.perf_counter()-start)*1000)
                    transfer.append(page.evaluate('performance.getEntriesByType("resource").reduce((n,e)=>n+e.transferSize,0)'))
                    heap.append(page.evaluate('performance.memory?.usedJSHeapSize || 0'))
                    if response.status != 200:failures.append({'route':path,'status':response.status})
                result['routes'][name]={**stats(values),'cold_ms':round(cold,2),'status':response.status,
                    'median_resource_transfer_bytes':statistics.median(transfer),'median_js_heap_bytes':statistics.median(heap)}
            result['navigation_failures']=failures;result['browser_errors']=errors
            context.close();browser.close()
    finally:
        server.shutdown();thread.join(timeout=5);server.server_close()
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
