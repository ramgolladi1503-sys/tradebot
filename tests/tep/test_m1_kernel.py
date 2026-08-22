import pytest
from tep.kernel import *

def task(i,deps=()): return TaskDefinition(i,"READ_REPOSITORY","Git Service",tuple(deps),{}, {}, {"validated":True})
def mission(tasks): return MissionDefinition("m","1",tuple(tasks),{"all_tasks_succeeded":True})

def test_truth_values_are_distinct():
    assert len({TruthValue.UNKNOWN,TruthValue.MISSING,TruthValue.ZERO,TruthValue.PASS})==4

def test_illegal_transition_rejected():
    with pytest.raises(ValueError): require_transition(TaskState.PENDING,TaskState.SUCCEEDED)
    require_transition(TaskState.PENDING,TaskState.RUNNABLE)

def test_terminal_failure_cannot_reset():
    with pytest.raises(ValueError): require_transition(TaskState.FAILED_TERMINAL,TaskState.RUNNABLE)

def test_graph_validation_and_deterministic_runnable_order():
    m=mission([task("b",("a",)),task("a"),task("c")]); validate_mission(m)
    assert compute_runnable(m,{}) == ("a","c")
    assert compute_runnable(m,{"a":TaskState.SUCCEEDED}) == ("b","c")

def test_unknown_dependency_rejected():
    with pytest.raises(ValueError): validate_mission(mission([task("a",("x",))]))

def test_cycle_rejected():
    with pytest.raises(ValueError): validate_mission(mission([task("a",("b",)),task("b",("a",))]))

def test_fingerprint_is_order_stable_for_mapping_keys():
    a=MissionDefinition("m","1",(TaskDefinition("a","READ_REPOSITORY","Git Service",(),{"x":1,"y":2},{},{}),),{})
    b=MissionDefinition("m","1",(TaskDefinition("a","READ_REPOSITORY","Git Service",(),{"y":2,"x":1},{},{}),),{})
    assert a.fingerprint==b.fingerprint

def test_schema_version_rejected():
    with pytest.raises(ValueError): validate_mission(MissionDefinition("m","1",(),{},"future"))

def test_contract_records_preserve_required_fields():
    assert AuthorityDecision("d","PUSH_BRANCH",False,"sha").allowed is False
    assert EvidenceRecord("e","claim","producer","validator","source","ref","hash").validator=="validator"

def test_m1_has_no_external_mutation_surface():
    import tep.kernel as k
    forbidden={"requests","subprocess","socket","sqlite3","kiteconnect"}
    assert forbidden.isdisjoint(set(k.__dict__))
