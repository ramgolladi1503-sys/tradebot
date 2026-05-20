from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.repo_forensics.config_loader import ConfigError, ForensicsConfig, load_config


REQUIRED_CE_AGENTS = ("ariadne", "daedalus", "vulcan", "minerva", "cerberus")

REQUIRED_AGENT_FIELDS: dict[str, tuple[str, ...]] = {
    "ariadne": ("mission", "input_sources", "cluster_signals", "confidence_levels", "output_required"),
    "daedalus": ("mission", "decisions", "required_contract_fields", "block_on", "output_required"),
    "vulcan": ("mission", "allowed_only_after", "hardening_targets", "forbidden_actions", "output_required"),
    "minerva": ("mission", "classes", "weak_test_patterns", "required_negative_tests", "output_required"),
    "cerberus": ("mission", "protected_modes", "forbidden_import_markers", "required_non_action_fields", "block_on", "output_required"),
}

LIST_FIELDS_BY_AGENT: dict[str, tuple[str, ...]] = {
    agent: tuple(field for field in fields if field != "mission") for agent, fields in REQUIRED_AGENT_FIELDS.items()
}


@dataclass(frozen=True)
class AgentParameterProfile:
    name: str
    mission: str
    raw: dict[str, Any]

    def require_list(self, key: str) -> tuple[str, ...]:
        value = self.raw.get(key)
        if not isinstance(value, list) or not value:
            raise ConfigError(f"agent_parameter_list_required agent={self.name} key={key}")
        return tuple(str(item) for item in value)


@dataclass(frozen=True)
class CodeExcellenceAgentParameters:
    ariadne: AgentParameterProfile
    daedalus: AgentParameterProfile
    vulcan: AgentParameterProfile
    minerva: AgentParameterProfile
    cerberus: AgentParameterProfile

    def get(self, agent_name: str) -> AgentParameterProfile:
        normalized = agent_name.strip().lower()
        if normalized not in REQUIRED_CE_AGENTS:
            raise ConfigError(f"unknown_code_excellence_agent agent={agent_name}")
        return getattr(self, normalized)

    @property
    def agents(self) -> tuple[AgentParameterProfile, ...]:
        return tuple(self.get(name) for name in REQUIRED_CE_AGENTS)


def load_code_excellence_agent_parameters(config_path: str | Path) -> CodeExcellenceAgentParameters:
    return extract_code_excellence_agent_parameters(load_config(config_path))


def extract_code_excellence_agent_parameters(config: ForensicsConfig) -> CodeExcellenceAgentParameters:
    raw_agent_parameters = config.data.get("agent_parameters")
    if not isinstance(raw_agent_parameters, dict):
        raise ConfigError("agent_parameters_must_be_mapping")

    profiles = {
        agent_name: _build_profile(agent_name, raw_agent_parameters.get(agent_name)) for agent_name in REQUIRED_CE_AGENTS
    }
    return CodeExcellenceAgentParameters(
        ariadne=profiles["ariadne"],
        daedalus=profiles["daedalus"],
        vulcan=profiles["vulcan"],
        minerva=profiles["minerva"],
        cerberus=profiles["cerberus"],
    )


def _build_profile(agent_name: str, raw_profile: object) -> AgentParameterProfile:
    if not isinstance(raw_profile, dict):
        raise ConfigError(f"agent_parameters_missing agent={agent_name}")

    missing = [field for field in REQUIRED_AGENT_FIELDS[agent_name] if field not in raw_profile]
    if missing:
        raise ConfigError(f"agent_parameters_missing_fields agent={agent_name} fields={','.join(missing)}")

    mission = raw_profile.get("mission")
    if not isinstance(mission, str) or not mission.strip():
        raise ConfigError(f"agent_parameter_mission_required agent={agent_name}")

    for field in LIST_FIELDS_BY_AGENT[agent_name]:
        value = raw_profile.get(field)
        if not isinstance(value, list) or not value:
            raise ConfigError(f"agent_parameter_list_required agent={agent_name} key={field}")

    return AgentParameterProfile(name=agent_name, mission=mission.strip(), raw=dict(raw_profile))
