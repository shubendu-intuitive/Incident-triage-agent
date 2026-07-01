"""
database.py

Three tables: runs, steps, checkpoints.

"""

import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./runs.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Run(Base):
    __tablename__ = "runs"

    run_id       = Column(String, primary_key=True)
    status       = Column(String, default="pending")
    # pending | running | waiting_approval | complete | failed | aborted
    service      = Column(String)
    severity     = Column(String)
    alert_type   = Column(String)
    description  = Column(Text, default="")
    scenario     = Column(String)
    created_at   = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    final_report = Column(Text, nullable=True)  # JSON blob


class Step(Base):
    __tablename__ = "steps"

    step_id          = Column(String, primary_key=True)
    run_id           = Column(String)
    node_name        = Column(String)   # LangGraph node name
    tool_name        = Column(String, nullable=True)
    tool_input       = Column(Text, nullable=True)   # JSON
    tool_output      = Column(Text, nullable=True)   # JSON
    agent_reasoning  = Column(Text, nullable=True)   # LLM response text
    llm_prompt       = Column(Text, nullable=True)   # Full prompt sent to LLM
    llm_response     = Column(Text, nullable=True)   # Full LLM response
    tool_calls       = Column(Text, nullable=True)   # JSON list of tool calls with inputs/outputs
    status           = Column(String, default="running")  # running | complete | failed
    started_at       = Column(DateTime, default=datetime.utcnow)
    completed_at     = Column(DateTime, nullable=True)


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    checkpoint_id  = Column(String, primary_key=True)
    run_id         = Column(String)
    question       = Column(Text)
    options        = Column(Text)        # JSON array of option dicts
    recommendation = Column(String)      # "A", "B", or "C"
    decision       = Column(String, nullable=True)  # null until resolved
    created_at     = Column(DateTime, default=datetime.utcnow)
    resolved_at    = Column(DateTime, nullable=True)


def init_db():
    """Create all tables. Called once at app startup."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
