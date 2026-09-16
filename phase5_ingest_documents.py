"""Operator CLI for Phase 5.6 local unified ingestion."""
from __future__ import annotations
import argparse,json,sqlite3,sys
from pathlib import Path
from urllib.parse import quote
from personal_learning_assistant.ingestion.source_resolver import SourceRootResolver
from personal_learning_assistant.repositories.sqlite.ingestion_repository import IngestionRepositoryError,SQLiteIngestionRepository
from personal_learning_assistant.services.unified_ingestion_service import UnifiedIngestionService
CONFIRMATION_PHRASE="INGEST_PHASE5_DOCUMENTS"
def _parser():
    p=argparse.ArgumentParser(description="Preview or execute Phase 5.6 local document ingestion.");p.add_argument("--database",default="data/learning_assistant.db");p.add_argument("--root",action="append",default=[],metavar="KEY=PATH");p.add_argument("--document-id",action="append",default=[]);p.add_argument("--apply",action="store_true");p.add_argument("--confirm",default="");p.add_argument("--max-chars",type=int,default=1600);return p
def _roots(values):
    result={}
    for value in values:
        if "=" not in value: raise ValueError("--root must use KEY=PATH")
        key,path=value.split("=",1);key=key.strip().casefold();path=path.strip()
        if not key or not path: raise ValueError("--root requires non-empty KEY and PATH")
        if key in result: raise ValueError("duplicate logical root key")
        result[key]=Path(path)
    return result
def _uri(path,mode): return "file:{}?mode={}".format(quote(str(path.resolve(strict=False)).replace("\\","/"),safe="/:"),mode)
def _open(path,writable):
    if not path.is_file() or path.is_symlink(): raise RuntimeError("SQLite database is missing or not a regular file")
    c=sqlite3.connect(_uri(path,"rw" if writable else "ro"),uri=True,isolation_level=None,timeout=5.0);c.row_factory=sqlite3.Row;c.execute("PRAGMA foreign_keys=ON");c.execute("PRAGMA busy_timeout=5000");return c
def main(argv=None):
    args=_parser().parse_args(argv)
    if args.apply and args.confirm!=CONFIRMATION_PHRASE:
        print("PHASE 5.6 UNIFIED INGESTION: BLOCKED",file=sys.stderr);print("--apply requires --confirm {}".format(CONFIRMATION_PHRASE),file=sys.stderr);return 2
    if not args.apply and args.confirm: print("--confirm is only valid with --apply",file=sys.stderr);return 2
    try:
        resolver=SourceRootResolver(_roots(args.root));c=_open(Path(args.database),args.apply)
        try:
            repo=SQLiteIngestionRepository(c);svc=UnifiedIngestionService(repo,resolver,max_chunk_chars=args.max_chars);ids=tuple(args.document_id) or None
            if args.apply:
                results=svc.ingest_all(ids);counts={};chunks=0
                for item in results: counts[item.status]=counts.get(item.status,0)+1;chunks+=item.chunk_count
                output={"mode":"apply","document_count":len(results),"status_counts":counts,"chunks_written":chunks,"semantic_rag_executed":False,"source_files_modified":False}
            else:
                before=c.total_changes;preview=svc.preview(ids);after=c.total_changes
                if before!=after: raise RuntimeError("preview unexpectedly changed SQLite")
                output={"mode":"preview","total":preview.total,"ready":preview.ready,"current":preview.current,"unsupported":preview.unsupported,"missing_source":preview.missing_source,"hash_mismatch":preview.hash_mismatch,"remote_only":preview.remote_only,"preview_writes_performed":False,"semantic_rag_executed":False,"source_files_modified":False}
        finally: c.close()
    except (OSError,ValueError,RuntimeError,sqlite3.Error,IngestionRepositoryError) as error:
        print("PHASE 5.6 UNIFIED INGESTION: BLOCKED",file=sys.stderr);print("{}: {}".format(type(error).__name__,error),file=sys.stderr);return 1
    print("PHASE 5.6 UNIFIED INGESTION: PASS");print(json.dumps(output,indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
