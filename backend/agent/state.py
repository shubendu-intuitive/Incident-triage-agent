"""
agent/state.py

This is the agent's "working memory" — a typed dictionary that gets passed
between every node in the LangGraph graph.
"""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class IncidentState(TypedDict):
    # ── Input (set once when the run starts) ─────────────────────────────────
    run_id: str
    service: str
    alert_type: str          # error_rate | latency | queue_backup | dependency_failure
    severity: str            # P1 | P2 | P3
    description: str
    scenario: str            # auto_fix | external_dependency | cascading_failure

    # ── LLM conversation history ──────────────────────────────────────────────
    # add_messages is a reducer: new messages are appended, not replaced.
    # This gives the LLM the full context of what it has done so far.
    messages: Annotated[list, add_messages]

    # ── Investigation findings (populated by parallel investigation node) ─────
    log_findings: dict        # from fetch_recent_logs
    metric_findings: dict     # from get_error_metrics
    queue_findings: dict      # from check_queue_depth

    # ── Deep diagnosis findings (only populated if initial findings unclear) ──
    dependency_findings: dict
    deployment_findings: dict
    runbook: dict

    # ── Decision (populated by decide_action node) ────────────────────────────
    root_cause: str
    fix_strategy: str         # "auto_fix" | "needs_approval" | "cannot_fix"
    fix_options: list         # list of option dicts shown to operator
    recommended_option: str   # e.g. "A"

    # ── Execution (populated by execute_fix / execute_approved_fix) ──────────
    fix_applied: str
    fix_result: dict
    verification_result: dict

    # ── Output (populated by generate_report node) ───────────────────────────
    final_report: str
    incident_status: str      # "resolved" | "mitigated" | "escalated"
