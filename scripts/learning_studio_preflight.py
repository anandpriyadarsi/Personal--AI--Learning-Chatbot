"""Validate canonical ZIP/JSON without writing a store; optionally normalize a pilot."""
import argparse
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from personal_learning_assistant.learning_studio.archive import decode_bundle,decode_json,MAX_ARCHIVE
from personal_learning_assistant.learning_studio.authoring import preflight
from personal_learning_assistant.learning_studio.validation import MAX_SOURCE,PackageError


def bounded(path,limit):
    with Path(path).open('rb') as stream:
        raw=stream.read(limit+1)
    if len(raw)>limit:raise PackageError(f'{path}: exceeds {limit} bytes.')
    return raw


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package');parser.add_argument('--source',required=True)
    parser.add_argument('--source-id',required=True,help='Exact existing registry ID, or explicitly synthetic disposable ID.')
    parser.add_argument('--catalogue',help='Read-only JSON export of available/courses/topics; absence supports unmapped only.')
    parser.add_argument('--coverage',help='Optional exact-version coverage companion JSON; digest must match, never rebound.')
    parser.add_argument('--pilot',action='store_true');parser.add_argument('--revision',type=int,default=2)
    parser.add_argument('--export',help='New canonical ZIP path, only after successful preflight. Never overwrites.')
    args=parser.parse_args()
    try:
        raw=bounded(args.package,MAX_ARCHIVE);source=bounded(args.source,MAX_SOURCE)
        catalogue=decode_json(bounded(args.catalogue,2_000_000)) if args.catalogue else {'available':False,'courses':[]}
        if args.pilot:
            from personal_learning_assistant.learning_studio.pilot_quality import normalize_pilot
            package,embedded,assets=normalize_pilot(raw,source_id=args.source_id,module_revision=args.revision)
            if embedded!=source:raise PackageError('Supplied original differs from pilot embedded original.')
            coverage=None
        else:package,assets,coverage=decode_bundle(raw,args.package)
        if args.coverage:
            if coverage is not None:raise PackageError('Specify coverage either in the bundle or --coverage, not both.')
            coverage=decode_json(bounded(args.coverage,2_000_000))
        report=preflight(package,source,assets,catalogue,source_id=args.source_id,coverage=coverage)
        if report['valid'] and args.export:
            with zipfile.ZipFile(args.export,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('module.json',json.dumps(package,ensure_ascii=False))
                if coverage is not None:archive.writestr('coverage.json',json.dumps(coverage,ensure_ascii=False))
                for name,data in assets.items():archive.writestr(name,data)
        print(json.dumps(report,indent=2));return 0 if report['valid'] else 1
    except (PackageError,OSError,ValueError) as exc:
        print(json.dumps({'valid':False,'errors':[{'field':'input','message':str(exc)}]},indent=2));return 1
if __name__=='__main__':raise SystemExit(main())
