"""M2 durable SQLite state/event store with recovery and observable blockers."""
from __future__ import annotations
import json,sqlite3,threading,time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from .kernel import EventRecord,MissionState,TaskState,require_transition
SCHEMA_VERSION=2
class StateConflict(RuntimeError):pass
class LeaseConflict(RuntimeError):pass
class StateStore:
 def __init__(self,path):self.path=str(path);self._lock=threading.RLock();self._init()
 def _connect(self):
  c=sqlite3.connect(self.path,timeout=5,isolation_level=None);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=5000');c.execute('PRAGMA journal_mode=WAL');return c
 @contextmanager
 def tx(self):
  with self._lock:
   c=self._connect()
   try:c.execute('BEGIN IMMEDIATE');yield c;c.execute('COMMIT')
   except Exception:c.execute('ROLLBACK');raise
   finally:c.close()
 def _init(self):
  with self.tx() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY,definition_hash TEXT NOT NULL,state TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,updated REAL NOT NULL);CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,mission_id TEXT NOT NULL,task_id TEXT NOT NULL,fingerprint TEXT NOT NULL,state TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,version INTEGER NOT NULL DEFAULT 0,updated REAL NOT NULL,UNIQUE(mission_id,task_id));CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,idempotency_key TEXT UNIQUE NOT NULL,event_type TEXT NOT NULL,subject TEXT NOT NULL,causal_refs TEXT NOT NULL,payload TEXT NOT NULL,schema_version TEXT NOT NULL,created REAL NOT NULL);CREATE TABLE IF NOT EXISTS leases(task_instance_id TEXT PRIMARY KEY,owner TEXT NOT NULL,fingerprint TEXT NOT NULL,expires REAL NOT NULL,version INTEGER NOT NULL DEFAULT 0);CREATE TABLE IF NOT EXISTS waits(task_instance_id TEXT PRIMARY KEY,wake_at REAL,reason TEXT NOT NULL,event_key TEXT);CREATE TABLE IF NOT EXISTS heartbeats(owner TEXT PRIMARY KEY,pid INTEGER NOT NULL,at_ns INTEGER NOT NULL);CREATE TABLE IF NOT EXISTS blockers(id TEXT PRIMARY KEY,mission_id TEXT NOT NULL,task_id TEXT,kind TEXT NOT NULL,detail TEXT NOT NULL,created REAL NOT NULL,resolved REAL);''')
   old=c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
   if old and int(old['value'])>SCHEMA_VERSION:raise StateConflict('database schema newer than runtime')
   c.execute("INSERT INTO meta(key,value) VALUES('schema_version',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(SCHEMA_VERSION),))
 def create_mission(self,id,definition_hash,state=MissionState.CREATED):
  with self.tx() as c:c.execute('INSERT INTO missions VALUES(?,?,?,?,?)',(id,definition_hash,state.value,0,time.time()))
 def create_task(self,id,mission_id,task_id,fingerprint,state=TaskState.PENDING):
  with self.tx() as c:c.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?)',(id,mission_id,task_id,fingerprint,state.value,0,0,time.time()))
 def transition_task(self,id,target,event,expected_version=None):
  with self.tx() as c:
   r=c.execute('SELECT * FROM tasks WHERE id=?',(id,)).fetchone()
   if not r:raise KeyError(id)
   if expected_version is not None and r['version']!=expected_version:raise StateConflict('stale task version')
   require_transition(TaskState(r['state']),target);c.execute('UPDATE tasks SET state=?,version=version+1,updated=? WHERE id=?',(target.value,time.time(),id));self._append_event(c,event)
 def _append_event(self,c,e):
  try:c.execute('INSERT INTO events(event_id,idempotency_key,event_type,subject,causal_refs,payload,schema_version,created) VALUES(?,?,?,?,?,?,?,?)',(e.event_id,e.idempotency_key,e.event_type,e.subject,json.dumps(e.causal_refs),json.dumps(dict(e.payload),sort_keys=True),e.schema_version,time.time()))
  except sqlite3.IntegrityError:
   r=c.execute('SELECT event_id FROM events WHERE idempotency_key=?',(e.idempotency_key,)).fetchone()
   if not r or r['event_id']!=e.event_id:raise StateConflict('idempotency collision')
 def append_event(self,e):
  with self.tx() as c:self._append_event(c,e)
 def acquire_lease(self,task_id,owner,fingerprint,duration,now=None):
  now=time.time() if now is None else now;exp=now+duration
  with self.tx() as c:
   r=c.execute('SELECT * FROM leases WHERE task_instance_id=?',(task_id,)).fetchone()
   if r and r['expires']>now and (r['owner']!=owner or r['fingerprint']!=fingerprint):raise LeaseConflict(task_id)
   c.execute('INSERT INTO leases VALUES(?,?,?,?,0) ON CONFLICT(task_instance_id) DO UPDATE SET owner=excluded.owner,fingerprint=excluded.fingerprint,expires=excluded.expires,version=leases.version+1',(task_id,owner,fingerprint,exp))
  return exp
 def expire_leases(self,now=None):
  now=time.time() if now is None else now
  with self.tx() as c:
   ids=[r['task_instance_id'] for r in c.execute('SELECT task_instance_id FROM leases WHERE expires<=?',(now,))];c.execute('DELETE FROM leases WHERE expires<=?',(now,));return len(ids)
 def release_lease(self,task_id,owner):
  with self.tx() as c:
   r=c.execute('SELECT owner FROM leases WHERE task_instance_id=?',(task_id,)).fetchone()
   if r and r['owner']!=owner:raise LeaseConflict(task_id)
   c.execute('DELETE FROM leases WHERE task_instance_id=?',(task_id,))
 def set_wait(self,task_id,reason,wake_at=None,event_key=None):
  with self.tx() as c:c.execute('INSERT INTO waits VALUES(?,?,?,?) ON CONFLICT(task_instance_id) DO UPDATE SET wake_at=excluded.wake_at,reason=excluded.reason,event_key=excluded.event_key',(task_id,wake_at,reason,event_key))
 def due_waits(self,now=None):
  now=time.time() if now is None else now
  with self._connect() as c:return [dict(r) for r in c.execute('SELECT * FROM waits WHERE wake_at IS NOT NULL AND wake_at<=? ORDER BY wake_at',(now,))]
 def heartbeat(self,owner,pid,at_ns):
  with self.tx() as c:c.execute('INSERT INTO heartbeats VALUES(?,?,?) ON CONFLICT(owner) DO UPDATE SET pid=excluded.pid,at_ns=excluded.at_ns',(owner,pid,at_ns))
 def latest_heartbeat(self):
  with self._connect() as c:
   r=c.execute('SELECT * FROM heartbeats ORDER BY at_ns DESC LIMIT 1').fetchone();return dict(r) if r else None
 def task_states(self):
  with self._connect() as c:return {r['task_id']:TaskState(r['state']) for r in c.execute('SELECT task_id,state FROM tasks')}
 def add_blocker(self,id,mission_id,task_id,kind,detail):
  with self.tx() as c:c.execute('INSERT OR REPLACE INTO blockers VALUES(?,?,?,?,?,?,NULL)',(id,mission_id,task_id,kind,detail,time.time()))
 def mission(self,id):
  with self._connect() as c:
   r=c.execute('SELECT * FROM missions WHERE id=?',(id,)).fetchone();return dict(r) if r else {}
 def tasks(self,mission_id):
  with self._connect() as c:return [dict(r) for r in c.execute('SELECT * FROM tasks WHERE mission_id=? ORDER BY task_id',(mission_id,))]
 def blockers(self,mission_id):
  with self._connect() as c:return [dict(r) for r in c.execute('SELECT * FROM blockers WHERE mission_id=? AND resolved IS NULL ORDER BY created',(mission_id,))]
 def integrity_check(self):
  with self._connect() as c:return c.execute('PRAGMA integrity_check').fetchone()[0]
 def backup(self,destination):
  dst=sqlite3.connect(str(destination));src=self._connect()
  try:src.backup(dst)
  finally:src.close();dst.close()
 def snapshot(self):
  with self._connect() as c:return {'missions':[dict(r) for r in c.execute('SELECT * FROM missions ORDER BY id')],'tasks':[dict(r) for r in c.execute('SELECT * FROM tasks ORDER BY id')],'events':[dict(r) for r in c.execute('SELECT * FROM events ORDER BY seq')],'blockers':[dict(r) for r in c.execute('SELECT * FROM blockers ORDER BY created')]}
