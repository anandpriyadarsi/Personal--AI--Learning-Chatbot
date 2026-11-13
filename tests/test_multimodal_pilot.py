"""Small deterministic retrieval pilot; this does NOT grade live model quality."""
from io import BytesIO
import hashlib
import json
from pathlib import Path
import sqlite3
from contextlib import closing
from PIL import Image,ImageDraw
import pytest
from test_multimodal_jobs import owners,records
from personal_learning_assistant.services.multimodal_evidence_service import MultimodalEvidenceService
from personal_learning_assistant.services.unified_search_runtime import UnifiedSearchRuntime


def test_thirty_gold_retrieval_cases_and_text_only_projection(owners,tmp_path):
    import fitz
    lib,db=owners;service=MultimodalEvidenceService(lib);gold=[];hashes={}
    pdf=fitz.open()
    for page_index in range(3):
        page=pdf.new_page();lines=[]
        for n in range(page_index*4,min(10,(page_index+1)*4)):
            token=f'rrefgold{n:02d}';fact=f'{token}: A pivot is the first nonzero entry in a row.'
            lines.append(fact);gold.append(dict(id=f'doc-{n}',token=token,modality='embedded_text',page=page_index+1,expected=fact))
        page.insert_text((40,60),'\n'.join(lines),fontsize=10)
    raw=pdf.tobytes();pdf.close();doc=lib.upload(BytesIO(raw),'RREF-and-LU-3-pages.pdf')
    hashes['RREF-and-LU-3-pages.pdf']=hashlib.sha256(raw).hexdigest()
    for case in gold:case['document_id']=doc['id']
    for number in range(5):
        image=Image.new('RGB',(640,160),'white');draw=ImageDraw.Draw(image);lines=[]
        for n in range(2):
            token=f'matrixgold{number*2+n:02d}';fact=f'{token}: Matrix [[1,-1],[0,2]] has two rows and two columns.'
            lines.append(fact)
        draw.multiline_text((10,20),'\n'.join(lines),fill='black');stream=BytesIO();image.save(stream,format='PNG');raw=stream.getvalue()
        title=f'matrix-{number}.png';hashes[title]=hashlib.sha256(raw).hexdigest();item=lib.upload(BytesIO(raw),title)
        preview=service.preview(item['id'],{'kind':'image'},method='review',text='\n'.join(lines))
        service.enqueue(item['id'],preview['token'])
        for line in lines:gold.append(dict(id=line.split(':')[0],token=line.split(':')[0],modality='user_transcription',document_id=item['id'],expected=line))
    transcript=[]
    for n in range(10):
        token=f'lecturegold{n:02d}';fact=f'{token}: Swap rows before elimination when the pivot is zero.'
        transcript.append(f'00:00:{n*2:02d}.125 --> 00:00:{n*2+1:02d}.750\n{fact}')
        gold.append(dict(id=token,token=token,modality='user_transcript',start_ms=n*2000+125,end_ms=n*2000+1750,expected=fact))
    raw=('WEBVTT\n\n'+'\n\n'.join(transcript)).encode();hashes['lecture.vtt']=hashlib.sha256(raw).hexdigest()
    lecture=lib.upload(BytesIO(raw),'lecture.vtt')
    for case in gold:
        if case['modality']=='user_transcript':case['document_id']=lecture['id']
    lib.run_pending()
    runtime=UnifiedSearchRuntime(database_path=db,index_root=db.parent/'tutor_retrieval')
    results=[]
    try:
        for case in gold:
            hits=runtime.search(case['token'],top_k=5)
            relevant=[h for h in hits if h.locator.get('native_document_id')==case['document_id'] and case['token'] in h.text]
            assert relevant,case['id']
            if case.get('page'):assert relevant[0].page_number==case['page']
            if case.get('start_ms') is not None:
                assert relevant[0].locator['timestamp_start_ms']==case['start_ms']
                assert relevant[0].locator['timestamp_end_ms']==case['end_ms']
            results.append(dict(id=case['id'],recall=bool(relevant),precision=len(relevant)/len(hits)))
        # The same corpus's baseline projection excludes newly introduced image
        # and transcript evidence. This is not a rerun of old executable code.
        assert sum(case['modality']=='embedded_text' for case in gold)==10
        assert len(results)==30 and sum(r['recall'] for r in results)==30
        assert sum(r['precision'] for r in results)/len(results)>=.7
        for n in range(15):assert not runtime.search(f'absentgold{n:02d}',top_k=5)
    finally:runtime.close()
    report=dict(positive_cases=30,negative_retrieval_cases=15,recall_at_5=1.,mean_precision_at_5=sum(r['precision'] for r in results)/30,
                baseline_text_only_projection_recall='10/30',live_answer_quality='NOT EVALUATED',hashes=hashes,gold=gold)
    destination=Path(__import__('os').getenv('ANVAYA_PILOT_REPORT',str(tmp_path/'pilot.json')))
    destination.write_text(json.dumps(report,indent=2))
