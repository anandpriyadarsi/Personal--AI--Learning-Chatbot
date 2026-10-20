"""Disposable UC100N-style example. Never imports an installed course or private PDF."""
from contextlib import closing
from io import BytesIO
import hashlib
import sqlite3
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from PIL import Image, ImageDraw
from tests.test_academic_evidence_v23 import NOW
from tests.test_planning_analysis_v2 import _database

PAGE_TEXT=[
    'SYNTHETIC UC100N-style demonstration; not official course material.\nAn observation is one case. A variable is an attribute measured for cases.\nKeep case identifiers separate from measured scores.',
    'Case ID | Score\n1 | 8\n2 | 6\nMean score = (8 + 6) / 2 = 7.\nThe denominator is two observations. Do not average the case IDs with scores.',
    'Revision: identify the cases, select the measured variable, then compute.\nA practice answer and a completed task do not prove independent understanding.'
]

def source_pdf():
    writer=PdfWriter()
    font=writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')}))
    for lines in PAGE_TEXT:
        page=writer.add_blank_page(width=612,height=792)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        content=DecodedStreamObject()
        commands=['BT /F1 11 Tf 40 745 Td 17 TL']
        for line in lines.splitlines():
            escaped=line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
            commands.append('('+escaped+') Tj T*')
        commands.append('ET')
        content.set_data('\n'.join(commands).encode('ascii'))
        page[NameObject('/Contents')]=writer._add_object(content)
    out=BytesIO();writer.write(out);return out.getvalue()

def authored_sample(raw):
    p={'schema':'anvaya.learning-module.v2','module_id':'uc100n-demo','module_revision':1,
       'title':'UC100N-style demonstration: observations, variables and the mean','unit':'Synthetic example',
       'source':{'source_id':'synthetic-uc100n-source','sha256':hashlib.sha256(raw).hexdigest(),
           'filename':'synthetic-uc100n.pdf','media_type':'application/pdf','page_count':3},
       'mapping':{'course_id':'v23-uc100n','topic_id':'v23-data','topic_name':'Observations and variables','reviewed':True,'confidence':.95},
       'pages':[{'page':n,'status':'needs_review','text':text,
           'review_flags':['Synthetic authored fidelity requires an independent source review.']} for n,text in enumerate(PAGE_TEXT,1)],
       'sections':[{'id':'data-meaning','title':'Cases, variables and a worked mean','pages':[1,2],'blocks':[
           {'kind':'source','text':PAGE_TEXT[0],'pages':[1]},
           {'kind':'definition','text':'An **observation** is one case. A **variable** is an attribute measured for cases.','pages':[1]},
           {'kind':'table','headers':['Case ID','Score'],'rows':[['1','8'],['2','6']],'pages':[2]},
           {'kind':'example','text':'## Work the mean\n1. Select scores 8 and 6.\n2. Total: 14.\n3. Divide by 2 observations: **7**.','pages':[2]},
           {'kind':'graph','graph_type':'process','nodes':[{'id':'cases','label':'Two observations'},{'id':'scores','label':'Scores 8 and 6'},{'id':'mean','label':'Mean score 7'}],
            'edges':[{'from':'cases','to':'scores','label':'measure the score variable'},{'from':'scores','to':'mean','label':'sum 14 then divide by 2'}],
            'alt':'Two cases have scores 8 and 6, giving mean score 7.','pages':[1,2]},
           {'kind':'image','asset':'assets/cases.png','alt':'Two synthetic case cards showing scores 8 and 6.','caption':'Case IDs label rows; scores are the measured variable.','pages':[2]},
           {'kind':'activity','widget':'compare_reveal','prompt':'Which column answers a question about the average score?',
            'choices':[{'id':'ids','label':'Case IDs','detail':'IDs identify cases; averaging them does not answer the score question.'},
                       {'id':'scores','label':'Scores','detail':'Scores 8 and 6 give a mean score of 7.'}],
            'feedback':'Explain why selecting the variable comes before computing. This activity is ungraded.','pages':[2]},
           {'kind':'misconception','text':'Do not average case IDs with measured scores. The denominator counts observations, not columns.','pages':[2]},
           {'kind':'recall','text':'Before calculating, what identifies a case and what is measured?','answer':'PRIVATE-RECALL-ANSWER','pages':[1]}]}],
       'revision':[{'kind':'teaching','text':'## Revision checklist\nIdentify cases → select the variable → show the calculation.','pages':[3]}],
       'questions':[{'id':'mean-score','revision':1,'kind':'mcq','prompt':'What is the mean of scores 8 and 6?',
           'options':['14','7'],'correct_index':1,'explanation':'Add the scores, then divide by two observations.',
           'pages':[2],'difficulty':'normal','low_stakes':True}]}
    image=Image.new('RGB',(520,120),'#14232c');draw=ImageDraw.Draw(image)
    draw.text((20,40),'Case 1: score 8       Case 2: score 6',fill='#e3eef1')
    out=BytesIO();image.save(out,format='PNG')
    return p,{'assets/cases.png':out.getvalue()}

@pytest.fixture
def uc_owners(tmp_path,monkeypatch):
    from personal_learning_assistant.learning_studio import service as owner
    from personal_learning_assistant.learning_studio.service import LearningStudioService
    monkeypatch.chdir(tmp_path);monkeypatch.setattr(owner,'now',lambda:NOW.isoformat())
    db=_database(tmp_path)
    with closing(sqlite3.connect(db)) as c,c:
        c.execute("INSERT INTO courses(id,code,name,created_at,updated_at) VALUES('v23-uc100n','UC100N','Synthetic data foundations',?,?)",(NOW.isoformat(),)*2)
        c.execute("INSERT INTO topics(id,course_id,name,normalized_name,position,status,created_at,updated_at) VALUES('v23-data','v23-uc100n','Observations and variables','observations and variables',1,'not_started',?,?)",(NOW.isoformat(),)*2)
    cat={'available':True,'courses':[{'id':'v23-uc100n','code':'UC100N','name':'Synthetic data foundations',
        'topics':[{'id':'v23-data','name':'Observations and variables'}]}]}
    raw=source_pdf();p,assets=authored_sample(raw)
    studio=LearningStudioService(tmp_path/'learning_studio.sqlite3',source_loader=lambda _:raw,catalogue_loader=lambda:cat)
    studio.stage(p,assets);studio.publish('uc100n-demo',1)
    return db,studio,p
