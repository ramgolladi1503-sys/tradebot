"""M9 read model for operator navigation."""
from dataclasses import dataclass
@dataclass(frozen=True)
class StatusView: mission:dict; tasks:tuple[dict,...]; blockers:tuple[dict,...]; heartbeat:dict|None
class ObservabilityService:
    def __init__(self,store):self.store=store
    def status(self,mission_id):return StatusView(self.store.mission(mission_id),tuple(self.store.tasks(mission_id)),tuple(self.store.blockers(mission_id)),self.store.latest_heartbeat())
