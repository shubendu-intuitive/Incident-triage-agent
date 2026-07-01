"""
agent/nodes.py

Each function here is a node in the LangGraph graph.
"""

import asyncio
import logging
import time
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .state import IncidentState
from .prompts import SYSTEM_PROMPT, plan_prompt, analyse_prompt, decide_prompt, report_prompt
from tools.mock_tools import (
    fetch_recent_logs, get_error_metrics, check_queue_depth,
    get_dependency_health, check_recent_deployments, check_aws_service_health,
    get_dynamodb_metrics, fetch_runbook,
    update_lambda_config, enable_response_cache,
    pause_sqs_consumer, increase_dynamo_capacity, verify_fix,
)

logger = logging.getLogger("triage")


# ── LLM call logger ───────────────────────────────────────────────────────────

def _log_llm_call(node_name: str, prompt: str, response: str, elapsed: float):
    """Print a clearly formatted LLM exchange to the terminal."""
    print(f"\n{'═' * 70}")
    print(f"  🤖  LLM CALL  ›  {node_name}  ({elapsed:.1f}s)")
    print(f"{'─' * 70}")
    print("  PROMPT:")
    prompt_out = prompt.strip()[:700] + ("…" if len(prompt.strip()) > 700 else "")
    for line in prompt_out.split("\n"):
        print(f"    {line}")
    print(f"{'─' * 70}")
    print("  RESPONSE:")
    resp_out = response.strip()[:900] + ("…" if len(response.strip()) > 900 else "")
    for line in resp_out.split("\n"):
        print(f"    {line}")
    print(f"{'═' * 70}\n")


# ── Core LLM caller ───────────────────────────────────────────────────────────

# Thread-local store for capturing prompts/responses per node call
_llm_call_store: dict = {}

def call_llm(state: IncidentState, llm, user_message: str, node_name: str = "") -> AIMessage:
    """
    Builds the full message list and calls the LLM.
    Stores the prompt and response in _llm_call_store for the admin inspector.
    """
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state.get("messages", [])
    messages.append(HumanMessage(content=user_message))

    logger.info(f"  → Sending {len(messages)} messages to LLM (node: {node_name})")
    t0 = time.time()
    response = llm.invoke(messages)
    elapsed = time.time() - t0

    _log_llm_call(node_name, user_message, response.content, elapsed)
    logger.info(f"  ← LLM responded in {elapsed:.1f}s — {len(response.content)} chars")

    # Store for retrieval by the step recorder in main.py
    _llm_call_store[node_name] = {
        "prompt": user_message,
        "system_prompt": SYSTEM_PROMPT,
        "response": response.content,
        "elapsed_sec": round(elapsed, 2),
        "message_count": len(messages),
    }

    return response


def get_last_llm_call(node_name: str) -> dict:
    """Retrieve the stored LLM call data for a node after it completes."""
    return _llm_call_store.get(node_name, {})


# ── Node functions ─────────────────────────────────────────────────────────────

def plan_investigation(state: IncidentState, llm) -> dict:
    """
    First node. LLM reads the alert and states what it plans to investigate.
    """
    prompt = plan_prompt(state)
    response = call_llm(state, llm, prompt, node_name="plan_investigation")

    return {
        "messages": [HumanMessage(content=prompt), response],
    }


async def run_parallel_investigation(state: IncidentState) -> dict:
    """
    Runs fetch_logs, get_metrics, and check_queue_depth concurrently.

    KEY CONCEPT — asyncio.gather:
    All three tool calls fire at the same time rather than sequentially.
    For real AWS API calls this saves 2-6 seconds per incident.
    """
    service = state["service"]
    queue_name = f"{service}-queue"

    logger.info(f"  → Running 3 tools in parallel: fetch_recent_logs, get_error_metrics, check_queue_depth")

    log_result, metric_result, queue_result = await asyncio.gather(
        asyncio.to_thread(fetch_recent_logs.invoke,  {"service": service, "time_window_minutes": 30}),
        asyncio.to_thread(get_error_metrics.invoke,  {"service": service}),
        asyncio.to_thread(check_queue_depth.invoke,  {"queue_name": queue_name}),
    )

    logger.info(f"  ← logs: {log_result.get('error_count')} errors, pattern={log_result.get('pattern')}")
    logger.info(f"  ← metrics: error_rate={metric_result.get('error_rate_pct')}% latency_p99={metric_result.get('latency_p99_ms')}ms")
    logger.info(f"  ← queue: depth={queue_result.get('depth')} lag={queue_result.get('consumer_lag')}")

    # Store individual tool calls for admin inspector
    _llm_call_store["run_parallel_investigation"] = {
        "tool_calls": [
            {"tool": "fetch_recent_logs",  "input": {"service": service, "time_window_minutes": 30}, "output": log_result},
            {"tool": "get_error_metrics",  "input": {"service": service},                            "output": metric_result},
            {"tool": "check_queue_depth",  "input": {"queue_name": queue_name},                      "output": queue_result},
        ]
    }

    return {
        "log_findings":    log_result,
        "metric_findings": metric_result,
        "queue_findings":  queue_result,
    }


def analyse_initial_findings(state: IncidentState, llm) -> dict:
    """
    LLM interprets the parallel investigation results.
    Sets root_cause if it has a clear hypothesis.
    """
    prompt = analyse_prompt(state)
    response = call_llm(state, llm, prompt, node_name="analyse_initial_findings")
    content = response.content.lower()

    root_cause = ""
    if "memory" in content or "heap" in content:
        root_cause = "Lambda memory exhaustion — batch size increase in recent deploy caused OOM errors"
    elif "bedrock" in content and ("timeout" in content or "latency" in content):
        root_cause = "AWS Bedrock degradation in us-east-1 causing upstream latency spike"
    elif "dynamodb" in content or "throttl" in content:
        root_cause = "DynamoDB write capacity exhaustion triggering cascading failure chain"

    if root_cause:
        logger.info(f"  ← Root cause identified: {root_cause}")
    else:
        logger.info(f"  ← Root cause unclear — will proceed to deep_diagnosis")

    return {
        "messages": [response],
        "root_cause": root_cause,
    }


def deep_diagnosis(state: IncidentState, llm) -> dict:
    """
    Conditional node — only runs if initial analysis was inconclusive.
    Checks dependency health, recent deployments, and AWS health status.
    """
    service = state["service"]

    logger.info(f"  → Running deep diagnosis tools for {service}")

    dep_result    = get_dependency_health.invoke({"service": service})
    deploy_result = check_recent_deployments.invoke({"service": service})

    # Check AWS health for any degraded dependency
    aws_health = {}
    for dep in dep_result.get("dependencies", []):
        if dep["status"] == "degraded":
            logger.info(f"  → Degraded dependency found: {dep['name']} — checking AWS health")
            aws_health = check_aws_service_health.invoke({"aws_service": dep["name"]})
            break

    # Check DynamoDB if throttling pattern detected
    dynamo_metrics = {}
    log_pattern = state.get("log_findings", {}).get("pattern", "")
    if "DynamoDB" in log_pattern or "dynamo" in log_pattern.lower():
        logger.info(f"  → DynamoDB throttling detected — fetching capacity metrics")
        dynamo_metrics = get_dynamodb_metrics.invoke({"table_name": f"{service}-table"})

    logger.info(f"  ← dep health: {[d['name']+':'+d['status'] for d in dep_result.get('dependencies', [])]}")
    logger.info(f"  ← deployments: {len(deploy_result.get('deployments', []))} recent")
    if aws_health:
        logger.info(f"  ← AWS health: {aws_health.get('status')} — {aws_health.get('message','')[:80]}")
    if dynamo_metrics:
        logger.info(f"  ← DynamoDB write capacity: {dynamo_metrics.get('write_capacity_pct')}%")

    deep_prompt = f"""Deep diagnosis results:

Dependency health: {dep_result}
Recent deployments: {deploy_result}
AWS health status: {aws_health}
DynamoDB metrics: {dynamo_metrics}

Based on ALL findings (initial + deep), what is the definitive root cause?
State it in one specific, technical sentence.
"""
    response = call_llm(state, llm, deep_prompt, node_name="deep_diagnosis")
    content = response.content.lower()

    root_cause = state.get("root_cause", "")
    if not root_cause:
        if "bedrock" in content:
            root_cause = "AWS Bedrock service disruption in us-east-1 causing latency > 30s on all AI-dependent endpoints"
        elif "dynamodb" in content and "write" in content:
            root_cause = "DynamoDB write capacity at 99% causing throttling → API 500s → SQS retry storm (8,400 messages)"

    return {
        "messages": [response],
        "dependency_findings": dep_result,
        "deployment_findings": deploy_result,
        "root_cause": root_cause,
    }


def fetch_runbook_node(state: IncidentState, llm) -> dict:
    """
    Looks up the runbook for the identified error pattern.
    """
    log_pattern = state.get("log_findings", {}).get("pattern", "UnknownError")
    logger.info(f"  → Fetching runbook for pattern: {log_pattern}")
    runbook_result = fetch_runbook.invoke({"error_pattern": log_pattern})
    logger.info(f"  ← Runbook: '{runbook_result.get('title')}' risk={runbook_result.get('risk_level')}")

    runbook_prompt = f"""Runbook retrieved for pattern '{log_pattern}':
{runbook_result}

Review the runbook. Does the recommended action align with your root cause analysis?
Note the risk level — it will influence whether we auto-fix or ask for approval.
"""
    response = call_llm(state, llm, runbook_prompt, node_name="fetch_runbook")

    return {
        "messages": [response],
        "runbook": runbook_result,
    }


def decide_action(state: IncidentState, llm) -> dict:
    """
    The decision node. LLM recommends a strategy, but code enforces policy.

    KEY CONCEPT — Structural policy enforcement:
    The LLM can be wrong or inconsistent. Critical routing decisions (P1 always
    needs approval) are enforced here in code, not left to prompt judgment.
    We also use the runbook risk_level as a code-level signal to catch cases
    where the LLM ignores the prompt rules.
    """
    prompt = decide_prompt(state)
    response = call_llm(state, llm, prompt, node_name="decide_action")
    content = response.content.lower()

    # Parse strategy — look for the exact format we asked for first
    strategy = None
    for line in response.content.split("\n"):
        line = line.strip()
        if line.startswith("fix_strategy:"):
            val = line.split(":", 1)[1].strip().lower()
            if "auto_fix" in val:
                strategy = "auto_fix"
            elif "needs_approval" in val:
                strategy = "needs_approval"
            elif "cannot_fix" in val:
                strategy = "cannot_fix"
            break

    # Fallback: scan full response for keywords
    if strategy is None:
        if "auto_fix" in content or "auto fix" in content:
            strategy = "auto_fix"
        elif "needs_approval" in content or "needs approval" in content:
            strategy = "needs_approval"
        else:
            strategy = "cannot_fix"

    # ── CODE-LEVEL POLICY RULES (override LLM if needed) ────────────────────

    # Rule 1: P1 always needs approval — no exceptions
    if state.get("severity") == "P1":
        if strategy != "needs_approval":
            logger.info(f"  ⚠ Policy: P1 → needs_approval (LLM said {strategy})")
        strategy = "needs_approval"

    # Rule 2: If runbook says low risk + P2/P3, force auto_fix
    # This catches the case where LLM wrongly escalates a safe fix
    runbook    = state.get("runbook", {})
    risk_level = runbook.get("risk_level", "unknown")
    scenario   = state.get("scenario", "")

    if (scenario == "auto_fix"
            and risk_level == "low"
            and state.get("severity") in ("P2", "P3")
            and strategy == "needs_approval"):
        logger.info(f"  ⚠ Policy: runbook risk=low + P2 + auto_fix scenario → overriding to auto_fix")
        strategy = "auto_fix"

    logger.info(f"  ← fix_strategy = {strategy}")

    # ── Build fix options for ALL needs_approval cases ───────────────────────
    fix_options       = []
    recommended_option = "A"

    if strategy == "needs_approval":
        if scenario == "auto_fix":
            # Fallback options if LLM still escalates the auto_fix scenario
            fix_options = [
                {"id": "A", "title": "Increase Lambda memory to 1024MB", "description": "Update memory config from 512MB to 1024MB and timeout to 60s. Low risk, reversible.", "risk": "low", "cost": "minimal"},
                {"id": "B", "title": "Increase + reduce batch size",      "description": "Increase memory AND reduce batch size back to 10. Addresses both symptoms.",          "risk": "low", "cost": "minimal"},
                {"id": "C", "title": "Rollback deployment only",          "description": "Rollback the recent batch size change without touching memory config.",               "risk": "low", "cost": "none"},
            ]
        elif scenario == "external_dependency":
            fix_options = [
                {"id": "A", "title": "Enable response cache",  "description": "Cache responses for 5 minutes to reduce Bedrock dependency.", "risk": "low",    "cost": "minimal"},
                {"id": "B", "title": "Enable circuit breaker", "description": "Fail fast with fallback response instead of timing out.",      "risk": "medium", "cost": "none"},
                {"id": "C", "title": "Disable AI features",    "description": "Return degraded mode until AWS resolves the issue.",           "risk": "low",    "cost": "none — but impacts users"},
            ]
        elif scenario == "cascading_failure":
            fix_options = [
                {"id": "A", "title": "Pause SQS → scale DynamoDB", "description": "Stop retry storm first, then scale capacity. Recommended.",     "risk": "medium", "cost": "~$12/month"},
                {"id": "B", "title": "Scale DynamoDB only",         "description": "Scale while queue retries. Higher risk during scaling window.", "risk": "high",   "cost": "~$12/month"},
                {"id": "C", "title": "Enable on-demand capacity",   "description": "Auto-scaling mode. Higher cost, 5-minute activation lag.",      "risk": "low",    "cost": "variable"},
            ]
        else:
            # Generic fallback for any unrecognised scenario
            fix_options = [
                {"id": "A", "title": "Apply recommended fix", "description": runbook.get("recommended_action", "Apply the runbook fix"), "risk": risk_level, "cost": "unknown"},
            ]

        logger.info(f"  ← Prepared {len(fix_options)} fix options for operator")

    return {
        "messages": [response],
        "fix_strategy":       strategy,
        "fix_options":        fix_options,
        "recommended_option": recommended_option,
    }


def execute_fix(state: IncidentState) -> dict:
    """Auto-fix path — no human approval needed."""
    service  = state["service"]
    scenario = state.get("scenario", "")

    if scenario == "auto_fix":
        logger.info(f"  → Auto-fix: increasing Lambda memory 512MB → 1024MB, timeout 30s → 60s")
        fix_result = update_lambda_config.invoke({
            "function_name": service,
            "memory_mb": 1024,
            "timeout_sec": 60,
        })
        fix_applied = "Updated Lambda memory from 512MB to 1024MB, timeout from 30s to 60s"
        logger.info(f"  ← Fix applied: {fix_applied}")
    else:
        fix_result  = {}
        fix_applied = "No auto-fix available for this scenario"

    return {
        "fix_applied": fix_applied,
        "fix_result":  fix_result,
    }


def human_checkpoint(state: IncidentState) -> dict:
    """
    Pause point — LangGraph's interrupt_before stops execution here.
    The graph is serialised to SQLite and waits for /api/runs/{id}/approve.
    This node itself does nothing; the pause happens at the graph level.
    """
    logger.info("  ⏸ Reached human_checkpoint — graph will pause here")
    return {}


def execute_approved_fix(state: IncidentState) -> dict:
    """Runs after operator approval. Resumes from the checkpoint."""
    scenario = state.get("scenario", "")
    fix_result = {}

    if scenario == "external_dependency":
        logger.info(f"  → Enabling response cache (TTL 300s)")
        fix_result  = enable_response_cache.invoke({"service": state["service"], "ttl_seconds": 300})
        fix_applied = "Enabled response cache with 5-minute TTL to absorb Bedrock latency"

    elif scenario == "cascading_failure":
        logger.info(f"  → Pausing SQS consumer to stop retry storm")
        pause_result = pause_sqs_consumer.invoke({"queue_name": f"{state['service']}-queue"})
        logger.info(f"  → Scaling DynamoDB write capacity 200 → 400 WCU")
        scale_result = increase_dynamo_capacity.invoke({
            "table_name": f"{state['service']}-table",
            "read_units": 100,
            "write_units": 400,
        })
        fix_result  = {"pause": pause_result, "scale": scale_result}
        fix_applied = "Paused SQS consumer; scaled DynamoDB write capacity from 200 to 400 WCU"

    else:
        fix_applied = "Executed approved fix"

    logger.info(f"  ← Fix applied: {fix_applied}")
    return {
        "fix_applied": fix_applied,
        "fix_result":  fix_result,
    }


def cannot_fix_node(state: IncidentState, llm) -> dict:
    """When the agent cannot determine root cause or fix."""
    prompt = f"""You were unable to resolve this incident automatically.

What you found: {state.get('root_cause', 'Root cause unclear')}
Runbook: {state.get('runbook', {})}

Write a brief escalation note covering:
1. What you investigated
2. What you found
3. What the on-call engineer should look at next
"""
    response = call_llm(state, llm, prompt, node_name="cannot_fix")
    return {
        "messages": [response],
        "incident_status": "escalated",
        "fix_applied": "None — requires human investigation",
    }


def verify_outcome(state: IncidentState) -> dict:
    """Re-checks service metrics after any fix attempt."""
    logger.info(f"  → Verifying fix for service: {state['service']}")
    result = verify_fix.invoke({"service": state["service"]})

    status_map = {"healthy": "resolved", "mitigated": "mitigated", "degraded": "escalated"}
    incident_status = status_map.get(result.get("status", "unknown"), "escalated")

    logger.info(f"  ← Verification: status={result.get('status')} → incident={incident_status}")
    logger.info(f"  ← {result.get('improvement', '')}")

    return {
        "verification_result": result,
        "incident_status": incident_status,
    }


def generate_report(state: IncidentState, llm) -> dict:
    """Final node — LLM writes the structured triage report."""
    prompt = report_prompt(state)
    response = call_llm(state, llm, prompt, node_name="generate_report")
    return {
        "messages": [response],
        "final_report": response.content,
    }
