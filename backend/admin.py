"""
admin.py — Admin API routes

Exposes:
- GET /admin/system   — LLM provider info, Ollama model stats, CPU/RAM
- GET /admin/runs/{run_id}/telemetry — per-step timing and LLM call breakdown
- GET /admin/graph    — graph node/edge structure for visualisation
"""

import json
import os
import time
import httpx
import logging
from datetime import datetime
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db, Run, Step

logger = logging.getLogger("triage")
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/system")
async def get_system_info():
    """
    Returns LLM provider, model, and system resource info.
    Pings Ollama API if in offline mode to get model details.
    """
    provider  = os.getenv("LLM_PROVIDER", "ollama")
    model     = os.getenv("OLLAMA_MODEL", "qwen3:14b")
    ollama_url = "http://localhost:11434"

    info = {
        "llm_provider": provider,
        "llm_model":    model if provider == "ollama" else "gpt-4o",
        "ollama_url":   ollama_url if provider == "ollama" else None,
        "mode":         "offline (Ollama)" if provider == "ollama" else "online (OpenAI)",
        "ollama_online": False,
        "ollama_models": [],
        "ollama_model_detail": None,
        "system": {},
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Ping Ollama for model info
    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Check if Ollama is running
                r = await client.get(f"{ollama_url}/api/tags")
                if r.status_code == 200:
                    info["ollama_online"] = True
                    data = r.json()
                    info["ollama_models"] = [
                        {
                            "name": m["name"],
                            "size_gb": round(m.get("size", 0) / 1e9, 1),
                            "modified": m.get("modified_at", ""),
                        }
                        for m in data.get("models", [])
                    ]
                    # Find the active model's details
                    for m in data.get("models", []):
                        if model in m["name"]:
                            info["ollama_model_detail"] = {
                                "name": m["name"],
                                "size_gb": round(m.get("size", 0) / 1e9, 1),
                                "parameter_size": m.get("details", {}).get("parameter_size", "unknown"),
                                "quantization": m.get("details", {}).get("quantization_level", "unknown"),
                                "format": m.get("details", {}).get("format", "unknown"),
                            }
        except Exception as e:
            logger.warning(f"Could not reach Ollama: {e}")

    # Get system resource usage (macOS / Linux compatible)
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        info["system"] = {
            "cpu_percent": round(cpu, 1),
            "ram_total_gb": round(mem.total / 1e9, 1),
            "ram_used_gb": round(mem.used / 1e9, 1),
            "ram_percent": round(mem.percent, 1),
            "ram_available_gb": round(mem.available / 1e9, 1),
        }
    except ImportError:
        info["system"] = {"note": "Install psutil for CPU/RAM stats: pip install psutil"}
    except Exception as e:
        info["system"] = {"error": str(e)}

    return info


@router.get("/runs/{run_id}/telemetry")
def get_run_telemetry(run_id: str, db: Session = Depends(get_db)):
    """
    Returns detailed timing breakdown for a run.
    Shows per-step duration and cumulative timeline.
    """
    run   = db.query(Run).filter(Run.run_id == run_id).first()
    steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.started_at).all()

    if not run:
        return {"error": "Run not found"}

    step_data = []
    total_llm_time = 0
    total_tool_time = 0

    LLM_NODES  = {"plan_investigation", "analyse_initial_findings", "deep_diagnosis",
                  "fetch_runbook", "decide_action", "cannot_fix", "generate_report"}
    TOOL_NODES = {"run_parallel_investigation", "execute_fix",
                  "execute_approved_fix", "verify_outcome"}

    for s in steps:
        duration = 0
        if s.started_at and s.completed_at:
            duration = (s.completed_at - s.started_at).total_seconds()

        category = "llm" if s.node_name in LLM_NODES else \
                   "tool" if s.node_name in TOOL_NODES else \
                   "routing"

        if category == "llm":
            total_llm_time += duration
        elif category == "tool":
            total_tool_time += duration

        step_data.append({
            "node_name": s.node_name,
            "status": s.status,
            "category": category,
            "duration_sec": round(duration, 2),
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "reasoning_preview": (s.agent_reasoning or "")[:150],
        })

    total_duration = 0
    if run.created_at and run.completed_at:
        total_duration = (run.completed_at - run.created_at).total_seconds()

    return {
        "run_id": run_id,
        "service": run.service,
        "scenario": run.scenario,
        "status": run.status,
        "total_duration_sec": round(total_duration, 1),
        "total_llm_time_sec": round(total_llm_time, 1),
        "total_tool_time_sec": round(total_tool_time, 1),
        "llm_call_count": sum(1 for s in step_data if s["category"] == "llm"),
        "tool_call_count": sum(1 for s in step_data if s["category"] == "tool"),
        "steps": step_data,
    }


@router.get("/graph")
def get_graph_structure():
    """
    Returns the graph node/edge structure for frontend visualisation.
    Static definition of the LangGraph state machine.
    """
    return {
        "nodes": [
            {"id": "plan_investigation",         "label": "Plan",            "category": "llm",     "description": "LLM reads alert, plans investigation"},
            {"id": "run_parallel_investigation",  "label": "Parallel checks", "category": "tool",    "description": "3 tools fire simultaneously"},
            {"id": "analyse_initial_findings",    "label": "Analyse",         "category": "llm",     "description": "LLM interprets findings, sets root_cause"},
            {"id": "deep_diagnosis",              "label": "Deep diagnosis",  "category": "llm",     "description": "LLM + tools: deps, deployments, AWS health"},
            {"id": "fetch_runbook",               "label": "Runbook",         "category": "llm",     "description": "LLM reviews runbook for error pattern"},
            {"id": "decide_action",               "label": "Decide",          "category": "llm",     "description": "LLM decides: auto_fix / needs_approval / cannot_fix"},
            {"id": "execute_fix",                 "label": "Auto fix",        "category": "tool",    "description": "Fix tool runs without human approval"},
            {"id": "human_checkpoint",            "label": "HITL ⏸",          "category": "hitl",    "description": "Graph pauses, waits for operator"},
            {"id": "execute_approved_fix",        "label": "Approved fix",    "category": "tool",    "description": "Fix runs after operator approval"},
            {"id": "cannot_fix",                  "label": "Escalate",        "category": "llm",     "description": "LLM writes escalation note"},
            {"id": "verify_outcome",              "label": "Verify",          "category": "tool",    "description": "Re-checks metrics after fix"},
            {"id": "generate_report",             "label": "Report",          "category": "llm",     "description": "LLM writes final triage report"},
        ],
        "edges": [
            {"from": "plan_investigation",        "to": "run_parallel_investigation",  "type": "always"},
            {"from": "run_parallel_investigation","to": "analyse_initial_findings",    "type": "always"},
            {"from": "analyse_initial_findings",  "to": "fetch_runbook",               "type": "conditional", "condition": "root_cause found"},
            {"from": "analyse_initial_findings",  "to": "deep_diagnosis",              "type": "conditional", "condition": "root_cause unclear"},
            {"from": "deep_diagnosis",            "to": "fetch_runbook",               "type": "always"},
            {"from": "fetch_runbook",             "to": "decide_action",               "type": "always"},
            {"from": "decide_action",             "to": "execute_fix",                 "type": "conditional", "condition": "auto_fix"},
            {"from": "decide_action",             "to": "human_checkpoint",            "type": "conditional", "condition": "needs_approval"},
            {"from": "decide_action",             "to": "cannot_fix",                  "type": "conditional", "condition": "cannot_fix"},
            {"from": "human_checkpoint",          "to": "execute_approved_fix",        "type": "always"},
            {"from": "execute_fix",               "to": "verify_outcome",              "type": "always"},
            {"from": "execute_approved_fix",      "to": "verify_outcome",              "type": "always"},
            {"from": "cannot_fix",                "to": "verify_outcome",              "type": "always"},
            {"from": "verify_outcome",            "to": "generate_report",             "type": "always"},
        ],
        "categories": {
            "llm":     {"color": "#8b5cf6", "label": "LLM reasoning"},
            "tool":    {"color": "#14b8a6", "label": "Tool execution"},
            "hitl":    {"color": "#f59e0b", "label": "Human checkpoint"},
            "routing": {"color": "#64748b", "label": "Routing"},
        }
    }


# ── All 14 tools with metadata ────────────────────────────────────────────────

ALL_TOOLS_META = [
    # Investigation tools
    {"name": "fetch_recent_logs",       "category": "investigation", "description": "Fetch recent error logs from CloudWatch Logs",          "params": [{"name": "service", "type": "str", "required": True}, {"name": "time_window_minutes", "type": "int", "required": False}]},
    {"name": "get_error_metrics",       "category": "investigation", "description": "Get error rate and latency metrics from CloudWatch",     "params": [{"name": "service", "type": "str", "required": True}]},
    {"name": "check_queue_depth",       "category": "investigation", "description": "Check SQS queue depth and consumer lag",                "params": [{"name": "queue_name", "type": "str", "required": True}]},
    # Deep diagnosis tools
    {"name": "get_dependency_health",   "category": "diagnosis",     "description": "Check health of downstream service dependencies",       "params": [{"name": "service", "type": "str", "required": True}]},
    {"name": "check_recent_deployments","category": "diagnosis",     "description": "Check recent deployments in the last 24 hours",        "params": [{"name": "service", "type": "str", "required": True}]},
    {"name": "check_aws_service_health","category": "diagnosis",     "description": "Check AWS service health dashboard",                   "params": [{"name": "aws_service", "type": "str", "required": True}]},
    {"name": "get_dynamodb_metrics",    "category": "diagnosis",     "description": "Get DynamoDB capacity utilisation and throttling",      "params": [{"name": "table_name", "type": "str", "required": True}]},
    {"name": "fetch_runbook",           "category": "diagnosis",     "description": "Fetch relevant runbook for an error pattern",           "params": [{"name": "error_pattern", "type": "str", "required": True}]},
    # Fix tools
    {"name": "update_lambda_config",    "category": "fix",           "description": "Update Lambda memory and timeout configuration",        "params": [{"name": "function_name", "type": "str", "required": True}, {"name": "memory_mb", "type": "int", "required": True}, {"name": "timeout_sec", "type": "int", "required": True}]},
    {"name": "trigger_lambda_redeploy", "category": "fix",           "description": "Trigger a fresh Lambda function deployment",            "params": [{"name": "function_name", "type": "str", "required": True}]},
    {"name": "enable_response_cache",   "category": "fix",           "description": "Enable response caching to reduce dependency load",     "params": [{"name": "service", "type": "str", "required": True}, {"name": "ttl_seconds", "type": "int", "required": False}]},
    {"name": "pause_sqs_consumer",      "category": "fix",           "description": "Pause SQS consumer to stop a retry storm",             "params": [{"name": "queue_name", "type": "str", "required": True}]},
    {"name": "increase_dynamo_capacity","category": "fix",           "description": "Increase DynamoDB provisioned read/write capacity",     "params": [{"name": "table_name", "type": "str", "required": True}, {"name": "read_units", "type": "int", "required": True}, {"name": "write_units", "type": "int", "required": True}]},
    {"name": "verify_fix",              "category": "verify",        "description": "Re-check service metrics after a fix attempt",          "params": [{"name": "service", "type": "str", "required": True}]},
]

TOOL_NODES = {
    "run_parallel_investigation": ["fetch_recent_logs", "get_error_metrics", "check_queue_depth"],
    "deep_diagnosis":             ["get_dependency_health", "check_recent_deployments", "check_aws_service_health", "get_dynamodb_metrics"],
    "fetch_runbook":              ["fetch_runbook"],
    "execute_fix":                ["update_lambda_config", "trigger_lambda_redeploy"],
    "execute_approved_fix":       ["enable_response_cache", "pause_sqs_consumer", "increase_dynamo_capacity"],
    "verify_outcome":             ["verify_fix"],
}


@router.get("/tools")
def get_tools_overview(run_id: str = None, db: Session = Depends(get_db)):
    """
    Returns all 14 tools with metadata.
    If run_id provided, marks which tools were called and includes their inputs/outputs.
    """
    fired_tools = {}  # tool_name → list of call details

    if run_id:
        steps = db.query(Step).filter(Step.run_id == run_id, Step.status == "complete").all()
        for step in steps:
            # Check tool_calls JSON (parallel tools)
            if step.tool_calls:
                try:
                    calls = json.loads(step.tool_calls)
                    for call in calls:
                        name = call.get("tool", "")
                        if name not in fired_tools:
                            fired_tools[name] = []
                        fired_tools[name].append({
                            "node": step.node_name,
                            "input": call.get("input", {}),
                            "output": call.get("output", {}),
                            "duration_sec": None,
                        })
                except Exception:
                    pass

            # Check tool_output JSON (single tool nodes)
            if step.tool_output and not step.tool_calls:
                try:
                    output = json.loads(step.tool_output)
                    # Map node to likely tools
                    for tool_name in TOOL_NODES.get(step.node_name, []):
                        if tool_name not in fired_tools:
                            fired_tools[tool_name] = []
                        duration = 0
                        if step.started_at and step.completed_at:
                            duration = (step.completed_at - step.started_at).total_seconds()
                        fired_tools[tool_name].append({
                            "node": step.node_name,
                            "input": {},
                            "output": output,
                            "duration_sec": round(duration, 3),
                        })
                except Exception:
                    pass

    tools_with_status = []
    for tool in ALL_TOOLS_META:
        t = dict(tool)
        t["fired"]  = tool["name"] in fired_tools
        t["calls"]  = fired_tools.get(tool["name"], [])
        tools_with_status.append(t)

    return {
        "tools": tools_with_status,
        "total": len(ALL_TOOLS_META),
        "fired_count": len(fired_tools),
        "categories": {
            "investigation": {"color": "#14b8a6", "label": "Investigation"},
            "diagnosis":     {"color": "#8b5cf6", "label": "Deep diagnosis"},
            "fix":           {"color": "#f59e0b", "label": "Fix action"},
            "verify":        {"color": "#22c55e", "label": "Verification"},
        }
    }


@router.get("/runs/{run_id}/llm-calls")
def get_llm_calls(run_id: str, db: Session = Depends(get_db)):
    """
    Returns all LLM calls for a run — full prompts and responses.
    """
    LLM_NODES = {"plan_investigation", "analyse_initial_findings", "deep_diagnosis",
                 "fetch_runbook", "decide_action", "cannot_fix", "generate_report"}

    steps = db.query(Step).filter(
        Step.run_id == run_id,
        Step.status == "complete"
    ).order_by(Step.started_at).all()

    calls = []
    for s in steps:
        if s.node_name not in LLM_NODES:
            continue
        duration = 0
        if s.started_at and s.completed_at:
            duration = (s.completed_at - s.started_at).total_seconds()

        calls.append({
            "node_name":    s.node_name,
            "duration_sec": round(duration, 1),
            "llm_prompt":   s.llm_prompt   or "",
            "llm_response": s.llm_response or s.agent_reasoning or "",
            "started_at":   s.started_at.isoformat() if s.started_at else None,
        })

    return {
        "run_id": run_id,
        "call_count": len(calls),
        "calls": calls,
        "system_prompt": "",  # will be filled by frontend request to /admin/system-prompt
    }


@router.get("/system-prompt")
def get_system_prompt():
    """Returns the current system prompt."""
    from agent.prompts import SYSTEM_PROMPT
    return {"system_prompt": SYSTEM_PROMPT}


@router.get("/runs/{run_id}/timeline")
def get_run_timeline(run_id: str, db: Session = Depends(get_db)):
    """
    Returns every step with full detail: prompt, response, tool calls, timing.
    """
    from database import Checkpoint

    run   = db.query(Run).filter(Run.run_id == run_id).first()
    steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.started_at).all()
    chkpt = db.query(Checkpoint).filter(Checkpoint.run_id == run_id).first()

    if not run:
        return {"error": "Run not found"}

    LLM_NODES  = {"plan_investigation", "analyse_initial_findings", "deep_diagnosis",
                  "fetch_runbook", "decide_action", "cannot_fix", "generate_report"}
    TOOL_NODES_SET = {"run_parallel_investigation", "execute_fix",
                      "execute_approved_fix", "verify_outcome"}
    HITL_NODES = {"human_checkpoint"}

    timeline = []
    for s in steps:
        duration = 0
        if s.started_at and s.completed_at:
            duration = (s.completed_at - s.started_at).total_seconds()

        category = "llm"     if s.node_name in LLM_NODES     else                    "tool"    if s.node_name in TOOL_NODES_SET else                    "hitl"    if s.node_name in HITL_NODES     else "routing"

        entry = {
            "step_id":      s.step_id,
            "node_name":    s.node_name,
            "status":       s.status,
            "category":     category,
            "duration_sec": round(duration, 2),
            "started_at":   s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            # LLM data
            "llm_prompt":   s.llm_prompt   or "",
            "llm_response": s.llm_response or s.agent_reasoning or "",
            # Tool data
            "tool_output":  json.loads(s.tool_output) if s.tool_output else {},
            "tool_calls":   json.loads(s.tool_calls)  if s.tool_calls  else [],
        }
        timeline.append(entry)

    total_duration = 0
    if run.created_at and run.completed_at:
        total_duration = (run.completed_at - run.created_at).total_seconds()

    return {
        "run_id":           run_id,
        "service":          run.service,
        "scenario":         run.scenario,
        "severity":         run.severity,
        "status":           run.status,
        "total_duration":   round(total_duration, 1),
        "timeline":         timeline,
        "checkpoint":       {
            "question":       chkpt.question,
            "options":        json.loads(chkpt.options) if chkpt else [],
            "recommendation": chkpt.recommendation if chkpt else "",
            "decision":       chkpt.decision if chkpt else None,
        } if chkpt else None,
    }


# ── Tool registry — all 14 tools with metadata ───────────────────────────────

TOOL_REGISTRY = [
    # Investigation tools
    {"name": "fetch_recent_logs",         "category": "investigation", "description": "Fetch recent error logs from CloudWatch Logs",                  "params": ["service", "time_window_minutes"]},
    {"name": "get_error_metrics",         "category": "investigation", "description": "Get error rate and latency metrics from CloudWatch Metrics",    "params": ["service"]},
    {"name": "check_queue_depth",         "category": "investigation", "description": "Check SQS queue depth and consumer lag",                        "params": ["queue_name"]},
    # Deep diagnosis tools
    {"name": "get_dependency_health",     "category": "diagnosis",     "description": "Check health of downstream service dependencies",               "params": ["service"]},
    {"name": "check_recent_deployments",  "category": "diagnosis",     "description": "Check recent deployments for a service in the last 24 hours",   "params": ["service"]},
    {"name": "check_aws_service_health",  "category": "diagnosis",     "description": "Check AWS service health dashboard for disruptions",             "params": ["aws_service"]},
    {"name": "get_dynamodb_metrics",      "category": "diagnosis",     "description": "Get DynamoDB capacity utilisation and throttling metrics",       "params": ["table_name"]},
    {"name": "fetch_runbook",             "category": "diagnosis",     "description": "Fetch the relevant runbook for a given error pattern",           "params": ["error_pattern"]},
    # Fix action tools
    {"name": "update_lambda_config",      "category": "fix",           "description": "Update Lambda function memory and timeout configuration",        "params": ["function_name", "memory_mb", "timeout_sec"]},
    {"name": "trigger_lambda_redeploy",   "category": "fix",           "description": "Trigger a fresh deployment of a Lambda function",               "params": ["function_name"]},
    {"name": "enable_response_cache",     "category": "fix",           "description": "Enable response caching to reduce dependency load",              "params": ["service", "ttl_seconds"]},
    {"name": "pause_sqs_consumer",        "category": "fix",           "description": "Pause SQS queue consumer to stop a retry storm",                "params": ["queue_name"]},
    {"name": "increase_dynamo_capacity",  "category": "fix",           "description": "Increase DynamoDB provisioned read/write capacity",              "params": ["table_name", "read_units", "write_units"]},
    # Verification tools
    {"name": "verify_fix",               "category": "verify",        "description": "Re-check service metrics after a fix has been applied",          "params": ["service"]},
]

CATEGORY_META = {
    "investigation": {"color": "#14b8a6", "label": "Investigation",  "icon": "🔍"},
    "diagnosis":     {"color": "#8b5cf6", "label": "Deep diagnosis", "icon": "🔬"},
    "fix":           {"color": "#f59e0b", "label": "Fix action",     "icon": "🔧"},
    "verify":        {"color": "#22c55e", "label": "Verification",   "icon": "✅"},
}


@router.get("/tools")
def get_tools(run_id: str = None, db: Session = Depends(get_db)):
    """
    Returns all 14 tools with metadata.
    If run_id provided, marks which tools fired and includes their call data.
    """
    fired_tools = {}

    if run_id:
        steps = db.query(Step).filter(Step.run_id == run_id).all()
        for step in steps:
            # Parse tool_output to find which tools ran
            if step.tool_output:
                try:
                    output = json.loads(step.tool_output)
                    # Map output keys back to tool names
                    key_to_tool = {
                        "log_findings":        "fetch_recent_logs",
                        "metric_findings":     "get_error_metrics",
                        "queue_findings":      "check_queue_depth",
                        "dependency_findings": "get_dependency_health",
                        "runbook":             "fetch_runbook",
                        "fix_result":          "update_lambda_config",
                        "verification_result": "verify_fix",
                    }
                    for key, tool_name in key_to_tool.items():
                        if key in output:
                            fired_tools[tool_name] = {
                                "node": step.node_name,
                                "output": output[key],
                                "duration_sec": round(
                                    (step.completed_at - step.started_at).total_seconds(), 2
                                ) if step.completed_at and step.started_at else 0,
                            }
                except Exception:
                    pass

            # Parse tool_calls JSON if present
            if step.tool_calls:
                try:
                    calls = json.loads(step.tool_calls)
                    for call in calls:
                        fired_tools[call["name"]] = {
                            "node": step.node_name,
                            "input": call.get("input", {}),
                            "output": call.get("output", {}),
                            "duration_sec": 0,
                        }
                except Exception:
                    pass

    result = []
    for tool in TOOL_REGISTRY:
        entry = {**tool}
        # Normalise params to always be a list of strings
        entry["params"] = [
            p if isinstance(p, str) else p.get("name", str(p))
            for p in (entry.get("params") or [])
        ]
        entry["category_meta"] = CATEGORY_META.get(tool["category"], {})
        if tool["name"] in fired_tools:
            entry["fired"]      = True
            entry["call_data"]  = fired_tools[tool["name"]]
        else:
            entry["fired"]      = False
            entry["call_data"]  = None
        result.append(entry)

    return {
        "tools": result,
        "total": len(result),
        "fired_count": len(fired_tools),
        "categories": CATEGORY_META,
    }


@router.get("/runs/{run_id}/llm_calls")
def get_llm_calls(run_id: str, db: Session = Depends(get_db)):
    """
    Returns all LLM calls for a run with full prompt + response.
    """
    LLM_NODES = {
        "plan_investigation", "analyse_initial_findings", "deep_diagnosis",
        "fetch_runbook", "decide_action", "cannot_fix", "generate_report"
    }

    steps = db.query(Step).filter(
        Step.run_id == run_id,
    ).order_by(Step.started_at).all()

    calls = []
    for s in steps:
        if s.node_name not in LLM_NODES:
            continue
        duration = 0
        if s.started_at and s.completed_at:
            duration = round((s.completed_at - s.started_at).total_seconds(), 1)

        calls.append({
            "node_name":    s.node_name,
            "status":       s.status,
            "duration_sec": duration,
            "llm_prompt":   s.llm_prompt or "",
            "llm_response": s.llm_response or s.agent_reasoning or "",
            "started_at":   s.started_at.isoformat() if s.started_at else None,
        })

    return {"run_id": run_id, "llm_calls": calls, "total": len(calls)}


@router.get("/runs/{run_id}/timeline")
def get_run_timeline(run_id: str, db: Session = Depends(get_db)):
    """
    Returns a rich per-step timeline with all available detail.
    """
    from database import Run
    run   = db.query(Run).filter(Run.run_id == run_id).first()
    steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.started_at).all()

    if not run:
        return {"error": "Run not found"}

    LLM_NODES  = {"plan_investigation", "analyse_initial_findings", "deep_diagnosis",
                  "fetch_runbook", "decide_action", "cannot_fix", "generate_report"}
    TOOL_NODES = {"run_parallel_investigation", "execute_fix",
                  "execute_approved_fix", "verify_outcome"}

    timeline = []
    for s in steps:
        duration = 0
        if s.started_at and s.completed_at:
            duration = round((s.completed_at - s.started_at).total_seconds(), 2)

        category = "llm" if s.node_name in LLM_NODES else \
                   "tool" if s.node_name in TOOL_NODES else "routing"

        entry = {
            "step_id":      s.step_id,
            "node_name":    s.node_name,
            "category":     category,
            "status":       s.status,
            "duration_sec": duration,
            "started_at":   s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            # LLM data
            "llm_prompt":   s.llm_prompt or "",
            "llm_response": s.llm_response or s.agent_reasoning or "",
            # Tool data
            "tool_output":  json.loads(s.tool_output) if s.tool_output else None,
            "tool_calls":   json.loads(s.tool_calls) if s.tool_calls else None,
            # Summary fields
            "reasoning_preview": (s.agent_reasoning or "")[:200],
        }
        timeline.append(entry)

    total_duration = 0
    if run.created_at and run.completed_at:
        total_duration = round((run.completed_at - run.created_at).total_seconds(), 1)

    return {
        "run_id":           run_id,
        "service":          run.service,
        "scenario":         run.scenario,
        "status":           run.status,
        "total_duration":   total_duration,
        "timeline":         timeline,
        "final_report":     json.loads(run.final_report) if run.final_report else None,
    }