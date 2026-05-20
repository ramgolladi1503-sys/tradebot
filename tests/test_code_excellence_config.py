from __future__ import annotations

import pytest

from tools.code_excellence.config import (
    REQUIRED_CE_AGENTS,
    extract_code_excellence_agent_parameters,
    load_code_excellence_agent_parameters,
)
from tools.repo_forensics.config_loader import ConfigError, load_config


def _base_config_text() -> str:
    return """
gsd_forensics_config_version: 1
project:
  name: tradebot
baseline_rules:
  no_target_runtime_execution: true
entrypoints:
  required:
    - main.py
critical_modules:
  runtime:
    - main.py
agent_parameters:
  ariadne:
    mission: root_cause_investigator
    input_sources:
      - repo_forensics_report
    cluster_signals:
      - same_file
    confidence_levels:
      - CONFIRMED
    output_required:
      - finding_cluster
  daedalus:
    mission: remediation_architect
    decisions:
      - FIX_NOW
    required_contract_fields:
      - root_cause
    block_on:
      - no_root_cause
    output_required:
      - scoped_pr_contract
  vulcan:
    mission: production_hardening_from_scoped_contract
    allowed_only_after:
      - daedalus_contract
    hardening_targets:
      - safe_defaults
    forbidden_actions:
      - broad_repo_rewrite
    output_required:
      - maturity_before
  minerva:
    mission: test_reality_classifier
    classes:
      - SAFETY_REGRESSION
    weak_test_patterns:
      - shape_only
    required_negative_tests:
      - unsafe_path_blocks
    output_required:
      - test_classification_summary
  cerberus:
    mission: sim_paper_live_safety_boundary_guard
    protected_modes:
      - PAPER
    forbidden_import_markers:
      - place_order
    required_non_action_fields:
      - is_order_action=false
    block_on:
      - read_only_sets_order_action_true
    output_required:
      - safety_boundary_status
"""


def test_load_code_excellence_agent_parameters_from_config(tmp_path):
    config_path = tmp_path / ".gsd-forensics.yaml"
    config_path.write_text(_base_config_text(), encoding="utf-8")

    params = load_code_excellence_agent_parameters(config_path)

    assert tuple(agent.name for agent in params.agents) == REQUIRED_CE_AGENTS
    assert params.ariadne.mission == "root_cause_investigator"
    assert params.daedalus.require_list("decisions") == ("FIX_NOW",)
    assert params.vulcan.require_list("hardening_targets") == ("safe_defaults",)
    assert params.minerva.require_list("classes") == ("SAFETY_REGRESSION",)
    assert params.cerberus.require_list("protected_modes") == ("PAPER",)


def test_extract_code_excellence_agent_parameters_rejects_missing_agent(tmp_path):
    text = _base_config_text().replace("  cerberus:\n    mission: sim_paper_live_safety_boundary_guard\n    protected_modes:\n      - PAPER\n    forbidden_import_markers:\n      - place_order\n    required_non_action_fields:\n      - is_order_action=false\n    block_on:\n      - read_only_sets_order_action_true\n    output_required:\n      - safety_boundary_status\n", "")
    config_path = tmp_path / ".gsd-forensics.yaml"
    config_path.write_text(text, encoding="utf-8")
    config = load_config(config_path)

    with pytest.raises(ConfigError, match="agent_parameters_missing agent=cerberus"):
        extract_code_excellence_agent_parameters(config)


def test_extract_code_excellence_agent_parameters_rejects_missing_required_field(tmp_path):
    text = _base_config_text().replace("    decisions:\n      - FIX_NOW\n", "")
    config_path = tmp_path / ".gsd-forensics.yaml"
    config_path.write_text(text, encoding="utf-8")
    config = load_config(config_path)

    with pytest.raises(ConfigError, match="agent_parameters_missing_fields agent=daedalus fields=decisions"):
        extract_code_excellence_agent_parameters(config)


def test_extract_code_excellence_agent_parameters_rejects_empty_list(tmp_path):
    text = _base_config_text().replace("    output_required:\n      - finding_cluster\n", "    output_required:\n")
    config_path = tmp_path / ".gsd-forensics.yaml"
    config_path.write_text(text, encoding="utf-8")
    config = load_config(config_path)

    with pytest.raises(ConfigError, match="agent_parameter_list_required agent=ariadne key=output_required"):
        extract_code_excellence_agent_parameters(config)


def test_get_unknown_agent_rejected(tmp_path):
    config_path = tmp_path / ".gsd-forensics.yaml"
    config_path.write_text(_base_config_text(), encoding="utf-8")
    params = load_code_excellence_agent_parameters(config_path)

    with pytest.raises(ConfigError, match="unknown_code_excellence_agent"):
        params.get("unknown")
