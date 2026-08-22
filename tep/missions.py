"""M6-M8 declarative reference mission builders. They define work; they do not grant authority."""
from .kernel import MissionDefinition,TaskDefinition

def _t(i,cap,owner,deps=()):return TaskDefinition(i,cap,owner,tuple(deps),{}, {}, {'validated':True})

def repository_consolidation_mission()->MissionDefinition:
    tasks=(_t('inventory','READ_REPOSITORY','Git Service'),_t('pr_snapshot','READ_GITHUB','GitHub Service'),_t('preserve','READ_EVIDENCE','Evidence Service',('inventory',)),_t('repair','PUSH_BRANCH','Worker Manager',('inventory','pr_snapshot','preserve')),_t('ci','READ_CI','CI Service',('repair',)),_t('merge','MERGE_PR','Merge Service',('ci',)),_t('cleanup_candidates','READ_REPOSITORY','Cleanup Service',('merge','preserve')))
    return MissionDefinition('repository-consolidation','1',tasks,{'all_terminal':True})

def read_only_live_observation_mission()->MissionDefinition:
    tasks=(_t('dated_plan','READ_EVIDENCE','Live Observation Service'),_t('derive_subscriptions','READ_REPOSITORY','Live Observation Service',('dated_plan',)),_t('storage_preflight','READ_REPOSITORY','Live Observation Service',('dated_plan',)),_t('observe','START_READ_ONLY_OBSERVER','Live Observation Service',('derive_subscriptions','storage_preflight')),_t('drain','READ_EVIDENCE','Live Observation Service',('observe',)),_t('seal','SEAL_EVIDENCE','Evidence Service',('drain',)))
    return MissionDefinition('read-only-live-observation','1',tasks,{'sealed_with_limitations':True})

def structural_edge_research_mission()->MissionDefinition:
    tasks=(_t('freeze_hypothesis','READ_EVIDENCE','Research Validator'),_t('leakage_audit','READ_EVIDENCE','Research Validator',('freeze_hypothesis',)),_t('dev','READ_EVIDENCE','Research Validator',('leakage_audit',)),_t('negative_controls','READ_EVIDENCE','Research Validator',('dev',)),_t('holdout','ACCESS_PROTECTED_HOLDOUT','Research Validator',('negative_controls',)),_t('cost_robustness','READ_EVIDENCE','Research Validator',('holdout',)),_t('certification','CERTIFY_STRUCTURAL_EDGE','Research Validator',('cost_robustness',)))
    return MissionDefinition('structural-edge-research','1',tasks,{'certification_is_separate':True})
