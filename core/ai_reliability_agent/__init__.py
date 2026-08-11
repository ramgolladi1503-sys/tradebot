"""Bounded AI reliability and post-market decision analytics for TradeBot."""

from .agent import AssertionVerifier, ReliabilityAgent, ScriptedReasoner, ToolRegistry
from .analytics import analyze_candidates, build_candidate_autopsy, derive_session_verdict
from .certification import run_component_certification
from .contracts import *  # noqa: F401,F403
from .evidence import EvidenceLedger
from .openai_reasoner import OpenAIReasoner
from .pr763_session import (
    FAILED_VERDICT as PR763_FAILED_VERDICT,
    PASS_VERDICT as PR763_PASS_VERDICT,
    PENDING_VERDICT as PR763_PENDING_VERDICT,
    certify_pr763_session,
)
from .runtime import build_session_manifest, build_tools, finalize_session
from .supervisor import LiveAgentSupervisor, detect_triggers

__all__ = [
    "AssertionVerifier",
    "EvidenceLedger",
    "OpenAIReasoner",
    "PR763_FAILED_VERDICT",
    "PR763_PASS_VERDICT",
    "PR763_PENDING_VERDICT",
    "ReliabilityAgent",
    "ScriptedReasoner",
    "ToolRegistry",
    "analyze_candidates",
    "build_candidate_autopsy",
    "build_session_manifest",
    "build_tools",
    "certify_pr763_session",
    "derive_session_verdict",
    "finalize_session",
    "run_component_certification",
    "LiveAgentSupervisor",
    "detect_triggers",
]
