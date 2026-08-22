"""M2 durable SQLite state/event store. No external mutation authority."""
from __future__ import annotations
import json, sqlite3, threading, time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Iterator
from .kernel import EventRecord, MissionState, TaskState, require_transition

SCHEMA_VERSION=1
class StateConflict(RuntimeError): pass
class LeaseConflict(RuntimeError): pass

class StateStore:
    def __init__(self,path:str|Path):
        self.path=str(path); self._lock=threading.RLock(); self._init()
    def _connect(self):
        c=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); c.execute("PRAGMA busy_timeout=5000"); c.execute("PRAGMA journal_mode=WAL")
        return c
    @contextmanager
    def tx(self)->Iterator[sqlite3.Connection]:
        with self._lock:
            c=self._connect()
            try:
                c.execute("BEGIN IMMEDIATE"); yield c; c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK"); raise
            finally:c.close()
    def _init(self):
        with self.tx() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY,definition_hash TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,mission_id TEXT NOT NULL,task_id TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 0,updated REAL NOT NULL,UNIQUE(mission_id,task_id));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,idempotency_key TEXT UNIQUE NOT NULL,event_type TEXT NOT NULL,subject TEXT NOT NULL,causal_refs TEXT NOT NULL,payload TEXT NOT NULL,schema_version TEXT NOT NULL,created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS leases(task_instance_id TEXT PRIMARY KEY,owner TEXT NOT NULL,fingerprint TEXT NOT NULL,expires REAL NOT NULL,version INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS waits(task_instance_id TEXT PRIMARY KEY,wake_at REAL,reason TEXT NOT NULL,event_key TEXT);
            """); c.execute("INSERT OR IGNORE INTO meta VALUES('schema_version',?)",(str(SCHEMA_VERSION),))
    def create_mission(self,id,definition_hash,state=MissionState.CREATED):
        with self.tx() as c:c.execute("INSERT INTO missions VALUES(?,?,?,?,?)",(id,definition_hash,state.value,0,time.time()))
    def create_task(self,id,mission_id,task_id,fingerprint,state=TaskState.PENDING):
        with self.tx() as c:c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)",(id,mission_id,task_id,fingerprint,state.value,0,0,time.time()))
    def transition_task(self,id,target:TaskState,event:EventRecord,expected_version:int|None=None):
        with self.tx() as c:
            row=c.execute("SELECT * FROM tasks WHERE id=?",(id,)).fetchone()
            if not row: raise KeyError(id)
            if expected_version is not None and row['version']!=expected_version: raise StateConflict('stale task version')
            current=TaskState(row['state']); require_transition(current,target)
            c.execute("UPDATE tasks SET state=?,version=version+1,updated=? WHERE id=?",(target.value,time.time(),id))
            self._append_event(c,event)
    def _append_event(self,c,e:EventRecord):
        try:c.execute("INSERT INTO events(event_id,idempotency_key,event_type,subject,causal_refs,payload,schema_version,created) VALUES(?,?,?,?,?,?,?,?)",(e.event_id,e.idempotency_key,e.event_type,e.subject,json.dumps(e.causal_refs),json.dumps(dict(e.payload),sort_keys=True),e.schema_version,time.time()))
        except sqlite3.IntegrityError:
            row=c.execute("SELECT event_id FROM events WHERE idempotency_key=?",(e.idempotency_key,)).fetchone()
            if not row or row['event_id']!=e.event_id: raise StateConflict('idempotency collision')
    def append_event(self,e:EventRecord):
        with self.tx() as c:self._append_event(c,e)
    def acquire_lease(self,task_id,owner,fingerprint,duration:float,now:float|None=None):
        now=time.time() if now is None else now; exp=now+duration
        with self.tx() as c:
            row=c.execute("SELECT * FROM leases WHERE task_instance_id=?",(task_id,)).fetchone()
            if row and row['expires']>now and (row['owner']!=owner or row['fingerprint']!=fingerprint): raise LeaseConflict(task_id)
            c.execute("INSERT INTO leases VALUES(?,?,?,?,0) ON CONFLICT(task_instance_id) DO UPDATE SET owner=excluded.owner,fingerprint=excluded.fingerprint,expires=excluded.expires,version=leases.version+1",(task_id,owner,fingerprint,exp))
        return exp
    def release_lease(self,task_id,owner):
        with self.tx() as c:
            row=c.execute("SELECT owner FROM leases WHERE task_instance_id=?",(task_id,)).fetchone()
            if row and row['owner']!=owner: raise LeaseConflict(task_id)
            c.execute("DELETE FROM leases WHERE task_instance_id=?",(task_id,))
    def set_wait(self,task_id,reason,wake_at=None,event_key=None):
        with self.tx() as c:c.execute("INSERT INTO waits VALUES(?,?,?,?) ON CONFLICT(task_instance_id) DO UPDATE SET wake_at=excluded.wake_at,reason=excluded.reason,event_key=excluded.event_key",(task_id,wake_at,reason,event_key))
    def due_waits(self,now=None):
        now=time.time() if now is None else now
        with self._connect() as c:return [dict(r) for r in c.execute("SELECT * FROM waits WHERE wake_at IS NOT NULL AND wake_at<=? ORDER BY wake_at",(now,))]
    def snapshot(self):
        with self._connect() as c:return {'missions':[dict(r) for r in c.execute('SELECT * FROM missions ORDER BY id')],'tasks':[dict(r) for r in c.execute('SELECT * FROM tasks ORDER BY id')],'events':[dict(r) for r in c.execute('SELECT * FROM events ORDER BY seq')]}
