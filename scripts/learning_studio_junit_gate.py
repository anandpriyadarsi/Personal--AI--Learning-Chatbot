"""CI gate: only explicitly external pilot cases may skip; built-in browser cases must run."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def inspect_report(path):
    root=ET.parse(path)
    cases=list(root.iter('testcase'))
    skipped=[c.get('name','') for c in cases if c.find('skipped') is not None]
    failed=[c.get('name','') for c in cases if c.find('failure') is not None or c.find('error') is not None]
    forbidden=[name for name in skipped if not name.startswith('test_external_')]
    return {'cases':len(cases),'passed':len(cases)-len(skipped)-len(failed),'failed_or_errors':failed,
            'skipped_external':skipped,'forbidden_skips':forbidden}


if __name__=='__main__':
    report=inspect_report(sys.argv[1]);print(json.dumps(report,indent=2))
    Path(sys.argv[1]).with_suffix('.summary.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(1 if report['failed_or_errors'] or report['forbidden_skips'] or not report['cases'] else 0)
