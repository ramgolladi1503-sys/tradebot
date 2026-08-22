"""M6 reference consolidation mission used for integrated orchestration tests."""
from .kernel import MissionDefinition,TaskDefinition
def consolidation_reference():
 def t(i,cap,owner,deps=()):return TaskDefinition(i,cap,owner,tuple(deps),{'max_attempts':3},{'passive':True},{'validated':True})
 return MissionDefinition('repository-consolidation-reference','1',(
  t('inventory','READ_REPOSITORY','Git Service'),
  t('graph','READ_GITHUB','GitHub Service',('inventory',)),
  t('ci','READ_CI','CI Service',('graph',)),
  t('prepare','PUSH_BRANCH','Git Service',('ci',)),
  t('merge','MERGE_PR','Merge Service',('prepare',)),
  t('cleanup','DELETE_LOCAL_PATH','Cleanup Service',('merge',)),
 ),{'all_tasks_succeeded':True})
