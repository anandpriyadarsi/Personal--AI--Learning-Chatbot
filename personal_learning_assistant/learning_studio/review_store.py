"""Append-only, version-bound coverage companions in the dedicated feature store."""
import json
from datetime import datetime, timezone
from .coverage import digest, validate_coverage
from .validation import require

COVERAGE_DDL = '''
CREATE TABLE coverage_reports(
 seq INTEGER PRIMARY KEY, module_id TEXT NOT NULL, revision INTEGER NOT NULL,
 digest TEXT NOT NULL, record_json TEXT NOT NULL, timestamp TEXT NOT NULL,
 UNIQUE(module_id,revision,digest),
 FOREIGN KEY(module_id,revision) REFERENCES modules(module_id,revision));
CREATE TRIGGER immutable_coverage_reports_update BEFORE UPDATE ON coverage_reports BEGIN SELECT RAISE(ABORT,'immutable history'); END;
CREATE TRIGGER immutable_coverage_reports_delete BEFORE DELETE ON coverage_reports BEGIN SELECT RAISE(ABORT,'immutable history'); END;
'''

class ReviewStoreMixin:
    def stage_coverage(self, module_id, revision, record):
        # Validation happens from immutable staged bytes, never caller-authored keys.
        with self.store.connection() as con:
            row,p=self._row(con,module_id,revision,staged=True)
            assets={a['name']:a['bytes'] for a in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?',(module_id,revision))}
            validated=validate_coverage(record,p,row['source_blob'],assets)
        encoded=json.dumps(validated,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        identity=digest(validated)
        with self.store.connection(write=True) as con:
            row,p=self._row(con,module_id,revision,staged=True)
            # Recheck after acquiring the writer lock.
            validate_coverage(validated,p,row['source_blob'],assets)
            con.execute('INSERT OR IGNORE INTO coverage_reports(module_id,revision,digest,record_json,timestamp) VALUES(?,?,?,?,?)',
                (module_id,revision,identity,encoded,datetime.now(timezone.utc).isoformat()))
        return {'module_id':module_id,'revision':revision,'digest':identity,'state':'coverage_staged'}

    def coverage_report(self,module_id,revision):
        with self.store.connection() as con:
            row,p=self._row(con,module_id,revision,staged=True)
            # V1 reads do not migrate or initialize anything.
            if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='coverage_reports'").fetchone():return None
            report=con.execute('SELECT * FROM coverage_reports WHERE module_id=? AND revision=? ORDER BY seq DESC LIMIT 1',(module_id,revision)).fetchone()
            if report is None:return None
            record=json.loads(report['record_json'])
            require(digest(record)==report['digest'],'Coverage integrity failure.',409)
            assets={a['name']:a['bytes'] for a in con.execute('SELECT name,bytes FROM assets WHERE module_id=? AND revision=?',(module_id,revision))}
            return validate_coverage(record,p,row['source_blob'],assets)
