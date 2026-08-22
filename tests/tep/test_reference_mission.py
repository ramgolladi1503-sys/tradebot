from tep.reference_mission import consolidation_reference
from tep.kernel import *
def test_reference_mission_orders_dangerous_steps():
 m=consolidation_reference();validate_mission(m);s={};assert compute_runnable(m,s)==('inventory',);s['inventory']=TaskState.SUCCEEDED;assert compute_runnable(m,s)==('graph',);s['graph']=TaskState.SUCCEEDED;s['ci']=TaskState.SUCCEEDED;s['prepare']=TaskState.SUCCEEDED;assert compute_runnable(m,s)==('merge',)
