"""
main.py — FastAPI app with proper logging throughout.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import init_db, get_db, Run, Step, Checkpoint
from schemas import CreateRunRequest, ApproveCheckpointRequest, RejectCheckpointRequest
from tools.mock_tools import set_scenario
from agent.nodes import get_last_llm_call
from admin import router as admin_router

# ── Logging setup  ─────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("triage")

# ── Active WebSocket connections ──────────────────────────────────────────────
active_connections: Dict[str, WebSocket] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database...")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(title="Incident Triage Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)


async def send_ws(run_id: str, msg_type: str, data: dict):
    ws = active_connections.get(run_id)
    if ws:
        try:
            await ws.send_json({"type": msg_type, "data": data})
            logger.debug(f"[{run_id[:8]}] WS → {msg_type}")
        except Exception as e:
            logger.warning(f"[{run_id[:8]}] WS send failed: {e}")


async def run_agent(run_id: str, initial_state: dict):
    from agent.graph import graph

    db = next(get_db())
    short_id = run_id[:8]

    try:
        set_scenario(initial_state["scenario"])
        config = {"configurable": {"thread_id": run_id}}

        logger.info(f"[{short_id}] ═══ AGENT START ═══ service={initial_state['service']} scenario={initial_state['scenario']}")

        async for event in graph.astream_events(initial_state, config=config, version="v2"):
            event_name = event.get("event")
            node_name  = event.get("name", "")

            # Skip internal LangGraph wrapper events
            if node_name in ("__start__", "LangGraph", ""):
                continue

            if event_name == "on_chain_start":
                logger.info(f"[{short_id}] ▶ START  {node_name}")

                step_id = str(uuid.uuid4())
                step = Step(
                    step_id=step_id,
                    run_id=run_id,
                    node_name=node_name,
                    status="running",
                    started_at=datetime.utcnow(),
                )
                db.add(step)
                db.commit()

                await send_ws(run_id, "step_start", {
                    "step_id": step_id,
                    "node_name": node_name,
                    "timestamp": datetime.utcnow().isoformat(),
                })

            elif event_name == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                logger.info(f"[{short_id}] ✓ END    {node_name}")

                step = db.query(Step).filter(
                    Step.run_id == run_id,
                    Step.node_name == node_name,
                    Step.status == "running",
                ).order_by(Step.started_at.desc()).first()

                if step:
                    reasoning = ""
                    if isinstance(output, dict) and "messages" in output:
                        for msg in output["messages"]:
                            if hasattr(msg, "content") and msg.content:
                                reasoning = msg.content
                                break

                    if reasoning:
                        logger.info(f"[{short_id}]   reasoning: {reasoning[:120]}{'...' if len(reasoning) > 120 else ''}")

                    step.status = "complete"
                    step.completed_at = datetime.utcnow()
                    step.agent_reasoning = reasoning

                    # Save LLM prompt + response for admin inspector
                    llm_data = get_last_llm_call(node_name)
                    if llm_data.get("prompt"):
                        step.llm_prompt   = llm_data.get("prompt", "")
                        step.llm_response = llm_data.get("response", "")
                    if llm_data.get("tool_calls"):
                        step.tool_calls = json.dumps(llm_data["tool_calls"])

                    tool_output = {}
                    for key in ["log_findings", "metric_findings", "queue_findings",
                                "dependency_findings", "runbook", "fix_result",
                                "verification_result", "root_cause", "fix_strategy"]:
                        if isinstance(output, dict) and output.get(key):
                            tool_output[key] = output[key]
                    if tool_output:
                        step.tool_output = json.dumps(tool_output)
                        logger.info(f"[{short_id}]   output keys: {list(tool_output.keys())}")

                    db.commit()

                    await send_ws(run_id, "step_complete", {
                        "step_id": step.step_id,
                        "node_name": node_name,
                        "reasoning": reasoning,
                        "output": tool_output,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

            elif event_name == "on_chat_model_start":
                logger.info(f"[{short_id}]   🤖 Calling Ollama/LLM...")

            elif event_name == "on_chat_model_end":
                output = event.get("data", {}).get("output", {})
                content = ""
                if hasattr(output, "content"):
                    content = output.content
                logger.info(f"[{short_id}]   🤖 LLM responded: {str(content)[:100]}{'...' if len(str(content)) > 100 else ''}")

        # ── Check final state ────────────────────────────────────────────────
        final_state = graph.get_state(config)
        values = final_state.values

        if final_state.next and "human_checkpoint" in final_state.next:
            logger.info(f"[{short_id}] ⏸ PAUSED at human_checkpoint — waiting for operator approval")

            checkpoint_id = str(uuid.uuid4())
            fix_options  = values.get("fix_options", [])
            recommended  = values.get("recommended_option", "A")

            chkpt = Checkpoint(
                checkpoint_id=checkpoint_id,
                run_id=run_id,
                question="The agent has identified the root cause and prepared fix options. Please review and approve an action.",
                options=json.dumps(fix_options),
                recommendation=recommended,
            )
            db.add(chkpt)

            run = db.query(Run).filter(Run.run_id == run_id).first()
            if run:
                run.status = "waiting_approval"
                db.commit()

            await send_ws(run_id, "checkpoint", {
                "checkpoint_id": checkpoint_id,
                "question": chkpt.question,
                "options": fix_options,
                "recommendation": recommended,
                "root_cause": values.get("root_cause", ""),
                "fix_strategy": values.get("fix_strategy", ""),
            })

        else:
            final_report    = values.get("final_report", "")
            incident_status = values.get("incident_status", "unknown")
            logger.info(f"[{short_id}] ═══ COMPLETE ═══ status={incident_status}")

            run = db.query(Run).filter(Run.run_id == run_id).first()
            if run:
                run.status = "complete"
                run.completed_at = datetime.utcnow()
                run.final_report = json.dumps({"report": final_report, "status": incident_status})
                db.commit()

            await send_ws(run_id, "complete", {
                "final_report": final_report,
                "incident_status": incident_status,
            })

    except Exception as e:
        logger.error(f"[{short_id}] ✗ AGENT ERROR: {e}", exc_info=True)
        run = db.query(Run).filter(Run.run_id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        await send_ws(run_id, "error", {"message": str(e)})

    finally:
        db.close()


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.post("/api/runs")
async def create_run(
    request: CreateRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run_id = str(uuid.uuid4())
    logger.info(f"Creating run {run_id[:8]} — {request.service} / {request.scenario}")

    run = Run(
        run_id=run_id,
        status="running",
        service=request.service,
        severity=request.severity,
        alert_type=request.alert_type,
        description=request.description,
        scenario=request.scenario,
    )
    db.add(run)
    db.commit()

    initial_state = {
        "run_id": run_id,
        "service": request.service,
        "alert_type": request.alert_type,
        "severity": request.severity,
        "description": request.description,
        "scenario": request.scenario,
        "messages": [],
        "log_findings": {},
        "metric_findings": {},
        "queue_findings": {},
        "dependency_findings": {},
        "deployment_findings": {},
        "runbook": {},
        "root_cause": "",
        "fix_strategy": "",
        "fix_options": [],
        "recommended_option": "",
        "fix_applied": "",
        "fix_result": {},
        "verification_result": {},
        "final_report": "",
        "incident_status": "",
    }

    background_tasks.add_task(run_agent, run_id, initial_state)
    return {"run_id": run_id, "status": "started"}


@app.get("/api/runs")
def list_runs(db: Session = Depends(get_db)):
    runs = db.query(Run).order_by(Run.created_at.desc()).all()
    return {
        "runs": [
            {
                "run_id": r.run_id,
                "status": r.status,
                "service": r.service,
                "severity": r.severity,
                "alert_type": r.alert_type,
                "scenario": r.scenario,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]
    }


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.started_at).all()
    checkpoint = db.query(Checkpoint).filter(
        Checkpoint.run_id == run_id,
        Checkpoint.decision == None
    ).first()

    return {
        "run_id": run.run_id,
        "status": run.status,
        "service": run.service,
        "severity": run.severity,
        "alert_type": run.alert_type,
        "scenario": run.scenario,
        "description": run.description,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "final_report": json.loads(run.final_report) if run.final_report else None,
        "steps": [
            {
                "step_id": s.step_id,
                "node_name": s.node_name,
                "tool_name": s.tool_name,
                "tool_output": json.loads(s.tool_output) if s.tool_output else None,
                "agent_reasoning": s.agent_reasoning,
                "status": s.status,
                "started_at": s.started_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in steps
        ],
        "checkpoint": {
            "checkpoint_id": checkpoint.checkpoint_id,
            "question": checkpoint.question,
            "options": json.loads(checkpoint.options),
            "recommendation": checkpoint.recommendation,
        } if checkpoint else None,
    }


@app.post("/api/runs/{run_id}/approve")
async def approve_checkpoint(
    run_id: str,
    request: ApproveCheckpointRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from agent.graph import graph

    chkpt = db.query(Checkpoint).filter(
        Checkpoint.checkpoint_id == request.checkpoint_id
    ).first()
    if not chkpt:
        raise HTTPException(status_code=404, detail="Checkpoint not found")

    chkpt.decision = request.option_selected
    chkpt.resolved_at = datetime.utcnow()

    run = db.query(Run).filter(Run.run_id == run_id).first()
    if run:
        run.status = "running"
    db.commit()

    logger.info(f"[{run_id[:8]}] Operator approved option {request.option_selected} — resuming graph")

    scenario = run.scenario if run else "auto_fix"

    async def resume():
        config = {"configurable": {"thread_id": run_id}}
        graph.update_state(config, {"fix_applied": request.option_selected})
        set_scenario(scenario)
        await run_agent_resume(run_id, config)

    background_tasks.add_task(resume)
    return {"success": True}


async def run_agent_resume(run_id: str, config: dict):
    from agent.graph import graph

    db = next(get_db())
    short_id = run_id[:8]

    try:
        logger.info(f"[{short_id}] ▶ RESUMING from checkpoint...")

        async for event in graph.astream_events(None, config=config, version="v2"):
            event_name = event.get("event")
            node_name  = event.get("name", "")

            if node_name in ("__start__", "LangGraph", ""):
                continue

            if event_name == "on_chain_start":
                logger.info(f"[{short_id}] ▶ START  {node_name}")
                step_id = str(uuid.uuid4())
                step = Step(
                    step_id=step_id,
                    run_id=run_id,
                    node_name=node_name,
                    status="running",
                    started_at=datetime.utcnow(),
                )
                db.add(step)
                db.commit()
                await send_ws(run_id, "step_start", {
                    "step_id": step_id,
                    "node_name": node_name,
                    "timestamp": datetime.utcnow().isoformat(),
                })

            elif event_name == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                logger.info(f"[{short_id}] ✓ END    {node_name}")

                step = db.query(Step).filter(
                    Step.run_id == run_id,
                    Step.node_name == node_name,
                    Step.status == "running",
                ).order_by(Step.started_at.desc()).first()

                if step:
                    reasoning = ""
                    if isinstance(output, dict) and "messages" in output:
                        for msg in output["messages"]:
                            if hasattr(msg, "content") and msg.content:
                                reasoning = msg.content
                                break
                    step.status = "complete"
                    step.completed_at = datetime.utcnow()
                    step.agent_reasoning = reasoning
                    db.commit()

                    await send_ws(run_id, "step_complete", {
                        "step_id": step.step_id,
                        "node_name": node_name,
                        "reasoning": reasoning,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

            elif event_name == "on_chat_model_start":
                logger.info(f"[{short_id}]   🤖 Calling Ollama/LLM...")

            elif event_name == "on_chat_model_end":
                output = event.get("data", {}).get("output", {})
                content = getattr(output, "content", "")
                logger.info(f"[{short_id}]   🤖 LLM responded: {str(content)[:100]}")

        final_state = graph.get_state(config)
        values = final_state.values
        final_report    = values.get("final_report", "")
        incident_status = values.get("incident_status", "unknown")

        logger.info(f"[{short_id}] ═══ COMPLETE (after approval) ═══ status={incident_status}")

        run = db.query(Run).filter(Run.run_id == run_id).first()
        if run:
            run.status = "complete"
            run.completed_at = datetime.utcnow()
            run.final_report = json.dumps({"report": final_report, "status": incident_status})
            db.commit()

        await send_ws(run_id, "complete", {
            "final_report": final_report,
            "incident_status": incident_status,
        })

    except Exception as e:
        logger.error(f"[{short_id}] ✗ RESUME ERROR: {e}", exc_info=True)
        run = db.query(Run).filter(Run.run_id == run_id).first()
        if run:
            run.status = "failed"
            db.commit()
        await send_ws(run_id, "error", {"message": str(e)})

    finally:
        db.close()


@app.post("/api/runs/{run_id}/reject")
def reject_checkpoint(
    run_id: str,
    request: RejectCheckpointRequest,
    db: Session = Depends(get_db),
):
    chkpt = db.query(Checkpoint).filter(
        Checkpoint.checkpoint_id == request.checkpoint_id
    ).first()
    if chkpt:
        chkpt.decision = "rejected"
        chkpt.resolved_at = datetime.utcnow()

    run = db.query(Run).filter(Run.run_id == run_id).first()
    if run:
        run.status = "aborted"
        run.completed_at = datetime.utcnow()
    db.commit()
    logger.info(f"[{run_id[:8]}] Run aborted by operator")
    return {"success": True}




@app.post("/api/runs/{run_id}/abort")
def abort_run(
    run_id: str,
    db: Session = Depends(get_db),
):
    """Terminate a running investigation at any point."""
    run = db.query(Run).filter(Run.run_id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status in ("complete", "aborted", "failed"):
        return {"success": False, "reason": f"Run is already {run.status}"}

    run.status = "aborted"
    run.completed_at = datetime.utcnow()
    db.commit()

    logger.info(f"[{run_id[:8]}] Run terminated by operator")
    return {"success": True}

@app.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    await websocket.accept()
    active_connections[run_id] = websocket
    logger.info(f"[{run_id[:8]}] WebSocket connected")

    try:
        db = next(get_db())
        run = db.query(Run).filter(Run.run_id == run_id).first()

        if run:
            # Replay all completed steps so UI catches up if WS connected late
            steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.started_at).all()
            for s in steps:
                await websocket.send_json({
                    "type": "step_start",
                    "data": {
                        "step_id": s.step_id,
                        "node_name": s.node_name,
                        "timestamp": s.started_at.isoformat() if s.started_at else "",
                    }
                })
                if s.status == "complete":
                    await websocket.send_json({
                        "type": "step_complete",
                        "data": {
                            "step_id": s.step_id,
                            "node_name": s.node_name,
                            "reasoning": s.agent_reasoning or "",
                            "output": json.loads(s.tool_output) if s.tool_output else {},
                            "timestamp": s.completed_at.isoformat() if s.completed_at else "",
                        }
                    })

            # If run already complete, send the final report
            if run.status == "complete" and run.final_report:
                report_data = json.loads(run.final_report)
                await websocket.send_json({
                    "type": "complete",
                    "data": {
                        "final_report": report_data.get("report", ""),
                        "incident_status": report_data.get("status", "unknown"),
                    }
                })

            # If waiting for approval, send the checkpoint
            if run.status == "waiting_approval":
                chkpt = db.query(Checkpoint).filter(
                    Checkpoint.run_id == run_id,
                    Checkpoint.decision == None
                ).first()
                if chkpt:
                    await websocket.send_json({
                        "type": "checkpoint",
                        "data": {
                            "checkpoint_id": chkpt.checkpoint_id,
                            "question": chkpt.question,
                            "options": json.loads(chkpt.options),
                            "recommendation": chkpt.recommendation,
                        }
                    })

        db.close()

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        logger.info(f"[{run_id[:8]}] WebSocket disconnected")
    finally:
        active_connections.pop(run_id, None)
