"""
agent/graph.py — MemorySaver version, all nodes properly bound with partial.
"""

import logging
from functools import partial
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .state import IncidentState
from .nodes import (
    plan_investigation,
    run_parallel_investigation,
    analyse_initial_findings,
    deep_diagnosis,
    fetch_runbook_node,
    decide_action,
    execute_fix,
    human_checkpoint,
    execute_approved_fix,
    cannot_fix_node,
    verify_outcome,
    generate_report,
)
from llm_provider import get_llm

logger = logging.getLogger("triage")


def route_after_analysis(state: IncidentState) -> str:
    if state.get("root_cause"):
        logger.info("route → fetch_runbook (root cause identified)")
        return "fetch_runbook"
    logger.info("route → deep_diagnosis (root cause unclear)")
    return "deep_diagnosis"


def route_after_decide(state: IncidentState) -> str:
    strategy = state.get("fix_strategy", "cannot_fix")
    logger.info(f"route → {strategy}")
    if strategy == "auto_fix":
        return "execute_fix"
    elif strategy == "needs_approval":
        return "human_checkpoint"
    else:
        return "cannot_fix"


def build_graph():
    logger.info("Building LangGraph graph...")
    llm = get_llm()
    logger.info(f"LLM provider: {type(llm).__name__}")

    # Bind llm to every node that calls the LLM
    plan_node    = partial(plan_investigation,       llm=llm)
    analyse_node = partial(analyse_initial_findings, llm=llm)
    deep_node    = partial(deep_diagnosis,           llm=llm)
    runbook_node = partial(fetch_runbook_node,       llm=llm)
    decide_node  = partial(decide_action,            llm=llm)
    cannot_fix   = partial(cannot_fix_node,          llm=llm)
    report_node  = partial(generate_report,          llm=llm)

    workflow = StateGraph(IncidentState)

    workflow.add_node("plan_investigation",         plan_node)
    workflow.add_node("run_parallel_investigation", run_parallel_investigation)
    workflow.add_node("analyse_initial_findings",   analyse_node)
    workflow.add_node("deep_diagnosis",             deep_node)
    workflow.add_node("fetch_runbook",              runbook_node)
    workflow.add_node("decide_action",              decide_node)
    workflow.add_node("execute_fix",                execute_fix)
    workflow.add_node("human_checkpoint",           human_checkpoint)
    workflow.add_node("execute_approved_fix",       execute_approved_fix)
    workflow.add_node("cannot_fix",                 cannot_fix)
    workflow.add_node("verify_outcome",             verify_outcome)
    workflow.add_node("generate_report",            report_node)

    workflow.set_entry_point("plan_investigation")
    workflow.add_edge("plan_investigation",         "run_parallel_investigation")
    workflow.add_edge("run_parallel_investigation", "analyse_initial_findings")

    workflow.add_conditional_edges(
        "analyse_initial_findings",
        route_after_analysis,
        {"deep_diagnosis": "deep_diagnosis", "fetch_runbook": "fetch_runbook"}
    )

    workflow.add_edge("deep_diagnosis",       "fetch_runbook")
    workflow.add_edge("fetch_runbook",        "decide_action")

    workflow.add_conditional_edges(
        "decide_action",
        route_after_decide,
        {"execute_fix": "execute_fix", "human_checkpoint": "human_checkpoint", "cannot_fix": "cannot_fix"}
    )

    workflow.add_edge("execute_fix",          "verify_outcome")
    workflow.add_edge("execute_approved_fix", "verify_outcome")
    workflow.add_edge("cannot_fix",           "verify_outcome")
    workflow.add_edge("human_checkpoint",     "execute_approved_fix")
    workflow.add_edge("verify_outcome",       "generate_report")
    workflow.add_edge("generate_report",      END)

    checkpointer = MemorySaver()
    logger.info("Checkpointer: MemorySaver ✓")

    compiled = workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_checkpoint"],
    )

    logger.info("Graph compiled successfully ✓")
    return compiled


graph = build_graph()