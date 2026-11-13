"""Durable scope receipts and integer micro-dollar reservations. No network."""
from contextlib import contextmanager
from datetime import datetime,timezone
import sqlite3
import time
import uuid
from personal_learning_assistant.domain.multimodal_models import canonical,integer


class PermissionGuard:
    def __init__(self,database,*,monthly_limit_micros=0):
        self.database=database;self.limit=integer(monthly_limit_micros,0,1_000_000_000)

    @contextmanager
    def connection(self):
        con=sqlite3.connect(str(self.database),isolation_level=None,timeout=5)
        con.row_factory=sqlite3.Row
        try:
            con.execute('BEGIN IMMEDIATE');yield con;con.commit()
        except Exception:con.rollback();raise
        finally:con.close()

    def grant(self,scope,provider,purpose,*,max_cost_micros=0,ttl=900):
        integer(max_cost_micros,0,1_000_000);integer(ttl,1,3600)
        if purpose not in ('extract','answer') or not provider:raise ValueError('Invalid disclosure purpose/provider')
        receipt=uuid.uuid4().hex
        with self.connection() as con:
            con.execute('INSERT INTO mm_permissions VALUES(?,?,?,?,?,?,0)',(receipt,canonical(scope),provider,purpose,max_cost_micros,time.time()+ttl))
        return receipt

    def revoke(self,receipt):
        with self.connection() as con:con.execute('UPDATE mm_permissions SET revoked=1 WHERE id=?',(receipt,))

    def reserve(self,receipt,scope,provider,purpose,operation,cost):
        integer(cost,1,1_000_000)
        month=datetime.now(timezone.utc).strftime('%Y-%m')
        with self.connection() as con:
            row=con.execute('SELECT * FROM mm_permissions WHERE id=?',(receipt,)).fetchone()
            if not row or row['revoked'] or row['expires']<time.time() or (row['scope_json'],row['provider'],row['purpose'])!=(canonical(scope),provider,purpose):raise ValueError('Consent required or source/provider/scope changed')
            if cost>row['max_cost']:raise ValueError('Operation budget exceeded')
            spent=con.execute('SELECT coalesce(sum(coalesce(actual,reserved)),0) FROM mm_provider_requests WHERE month=?',(month,)).fetchone()[0]
            if spent+cost>self.limit:raise ValueError('Monthly budget exceeded; local-only is the default')
            # No concurrent paid calls; unknown outcomes continue reserving cost.
            if con.execute("SELECT 1 FROM mm_provider_requests WHERE status='sending'").fetchone():raise ValueError('Provider call already in progress')
            if con.execute('SELECT 1 FROM mm_provider_requests WHERE id=?',(operation,)).fetchone():raise ValueError('Operation already dispatched; unknown outcomes are not retried')
            con.execute('INSERT INTO mm_provider_requests VALUES(?,?,?,?,NULL,?)',(operation,receipt,month,cost,'sending'))

    def finish(self,operation,status,actual=None):
        if status not in ('complete','outcome_unknown','failed'):raise ValueError('Invalid outcome')
        with self.connection() as con:
            row=con.execute('SELECT reserved,status FROM mm_provider_requests WHERE id=?',(operation,)).fetchone()
            if not row or row['status']!='sending':raise ValueError('Operation is not sending')
            if actual is not None:integer(actual,0,row['reserved'])
            con.execute('UPDATE mm_provider_requests SET status=?,actual=? WHERE id=?',(status,actual,operation))
