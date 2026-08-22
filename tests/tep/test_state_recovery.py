from tep.state import StateStore,StateConflict
from tep.kernel import *
from tep.supervisor import Supervisor
import sqlite3,pytest

def ev(i):return EventRecord(i,i,'transition','t')
def test_atomic_transition_and_event(tmp_path):
 s=StateStore(tmp_path/'s.db');s.create_mission('m','h');s.create_task('i','m','t','fp');s.transition_task('i',TaskState.RUNNABLE,ev('e'));snap=s.snapshot();assert snap['tasks'][0]['state']=='RUNNABLE' and len(snap['events'])==1
def test_duplicate_idempotency_collision_fails(tmp_path):
 s=StateStore(tmp_path/'s.db');s.append_event(ev('e1'))
 with pytest.raises(StateConflict):s.append_event(EventRecord('e2','e1','x','x'))
def test_expired_lease_recovery_and_heartbeat(tmp_path):
 s=StateStore(tmp_path/'s.db');s.create_mission('m','h');s.create_task('i','m','a','fp');s.acquire_lease('i','old','fp',1,now=1);d=MissionDefinition('m','1',(TaskDefinition('a','READ_REPOSITORY','Git Service'),),{});r=Supervisor(s,d,'sup',99).tick();assert r.expired_leases==1 and s.latest_heartbeat()['pid']==99
def test_integrity_and_backup(tmp_path):
 s=StateStore(tmp_path/'s.db');assert s.integrity_check()=='ok';s.backup(tmp_path/'b.db');c=sqlite3.connect(tmp_path/'b.db');assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
