"""Read-only preview reconciliation for legacy data/notes.json versus registered vault notes."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from typing import Iterable,Tuple
from personal_learning_assistant.domain.notes_studio_models import LegacyNoteDecision

def _norm(value): return ' '.join(str(value or '').strip().casefold().split())
def _body_hash(value): return hashlib.sha256(str(value or '').replace('\r\n','\n').encode('utf-8')).hexdigest()

def preview_legacy_notes(path, registered_notes: Iterable, body_lookup=None)->Tuple[LegacyNoteDecision,...]:
    p=Path(path)
    if not p.exists(): return ()
    raw=p.read_bytes()
    if not raw.strip(): return ()
    try:data=json.loads(raw.decode('utf-8'))
    except Exception: return (LegacyNoteDecision(-1,'','needs_review',(), 'legacy notes JSON is invalid'),)
    if not isinstance(data,list): return (LegacyNoteDecision(-1,'','needs_review',(), 'legacy notes JSON is not a list'),)
    notes=tuple(registered_notes); out=[]
    for index,item in enumerate(data):
        if not isinstance(item,dict):
            out.append(LegacyNoteDecision(index,'','needs_review',(), 'legacy record is not an object')); continue
        title=str(item.get('title') or ''); content=str(item.get('content') or '')
        title_matches=[n for n in notes if _norm(n.title)==_norm(title)]
        exact=[]
        if body_lookup is not None:
            wanted=_body_hash(content)
            for n in title_matches:
                body=body_lookup(n)
                if body is not None and _body_hash(body)==wanted: exact.append(n.id)
        if len(exact)==1: decision='match_existing'; candidates=tuple(exact); reason='normalized title and body hash match'
        elif title_matches: decision='needs_review'; candidates=tuple(n.id for n in title_matches); reason='title candidate exists but exact body match is not proven'
        else: decision='create_markdown'; candidates=(); reason='no registered title candidate'
        out.append(LegacyNoteDecision(index,title,decision,candidates,reason))
    return tuple(out)
