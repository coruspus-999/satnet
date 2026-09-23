from __future__ import annotations
import json
from sqlalchemy import create_engine, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from satnet.domain.models import SimulationSummary

class Base(DeclarativeBase):
    pass

class SimulationRow(Base):
    __tablename__ = "simulations"
    simulation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False)

class SimulationRepository:
    def __init__(self, database_url: str):
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
    def save_summary(self, summary: SimulationSummary) -> None:
        with self.sessions.begin() as session:
            row = session.get(SimulationRow, summary.simulation_id)
            payload = summary.model_dump_json()
            if row is None:
                session.add(SimulationRow(simulation_id=summary.simulation_id, summary_json=payload))
            else:
                row.summary_json = payload
    def get_summary(self, simulation_id: str) -> SimulationSummary | None:
        with self.sessions() as session:
            row = session.get(SimulationRow, simulation_id)
            return SimulationSummary.model_validate(json.loads(row.summary_json)) if row else None
