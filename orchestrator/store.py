"""Durable workflow store with a tamper-evident (hash-chained) audit log."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

GENESIS_HASH = "0" * 64


class _Base(DeclarativeBase):
    pass


class WorkflowRow(_Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    data: Mapped[str] = mapped_column(Text)


class AuditRow(_Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("workflow_id", "seq"),
        Index("ix_audit_workflow", "workflow_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    workflow_id: Mapped[str] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[str] = mapped_column(String(40))
    node_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    event: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


def _digest(prev_hash: str, seq: int, ts: str, node_id: str | None, event: str, detail: str) -> str:
    payload = f"{prev_hash}|{seq}|{ts}|{node_id or ''}|{event}|{detail}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorkflowStore:
    def __init__(self, url: str):
        parsed = make_url(url)
        connect_args: dict = {}
        if parsed.get_backend_name() == "sqlite":
            if parsed.database and parsed.database != ":memory:":
                Path(parsed.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
            connect_args = {"check_same_thread": False, "timeout": 30}
        self._engine = create_engine(url, connect_args=connect_args)
        _Base.metadata.create_all(self._engine)

    def save(self, state: dict) -> None:
        with Session(self._engine) as session:
            session.merge(
                WorkflowRow(
                    id=state["id"],
                    status=state["status"],
                    version=state["version"],
                    created_at=state["created_at"],
                    updated_at=state["updated_at"],
                    data=json.dumps(state, default=str),
                )
            )
            session.commit()

    def load(self, workflow_id: str) -> dict | None:
        with Session(self._engine) as session:
            row = session.get(WorkflowRow, workflow_id)
            return json.loads(row.data) if row else None

    def all_states(self) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.scalars(select(WorkflowRow).order_by(WorkflowRow.created_at)).all()
            return [json.loads(row.data) for row in rows]

    def append_audit(self, workflow_id: str, node_id: str | None, event: str, detail: dict) -> dict:
        ts = datetime.now(UTC).isoformat()
        detail_json = json.dumps(detail, sort_keys=True, default=str)
        with Session(self._engine) as session:
            last = session.scalars(
                select(AuditRow)
                .where(AuditRow.workflow_id == workflow_id)
                .order_by(AuditRow.seq.desc())
                .limit(1)
            ).first()
            seq = last.seq + 1 if last else 1
            prev_hash = last.hash if last else GENESIS_HASH
            row = AuditRow(
                workflow_id=workflow_id,
                seq=seq,
                ts=ts,
                node_id=node_id,
                event=event,
                detail=detail_json,
                prev_hash=prev_hash,
                hash=_digest(prev_hash, seq, ts, node_id, event, detail_json),
            )
            session.add(row)
            session.commit()
            return self._as_dict(row)

    def audit(self, workflow_id: str) -> list[dict]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(AuditRow).where(AuditRow.workflow_id == workflow_id).order_by(AuditRow.seq)
            ).all()
            return [self._as_dict(row) for row in rows]

    def verify_chain(self, workflow_id: str) -> dict:
        events = self.audit(workflow_id)
        previous = GENESIS_HASH
        for event in events:
            detail_json = json.dumps(event["detail"], sort_keys=True, default=str)
            expected = _digest(
                previous, event["seq"], event["ts"], event["node_id"], event["event"], detail_json
            )
            if event["prev_hash"] != previous or event["hash"] != expected:
                return {"valid": False, "events": len(events), "broken_at_seq": event["seq"]}
            previous = event["hash"]
        return {"valid": True, "events": len(events), "broken_at_seq": None}

    @staticmethod
    def _as_dict(row: AuditRow) -> dict:
        return {
            "seq": row.seq,
            "ts": row.ts,
            "node_id": row.node_id,
            "event": row.event,
            "detail": json.loads(row.detail),
            "prev_hash": row.prev_hash,
            "hash": row.hash,
        }

    def raw_session(self) -> Session:
        """Exposed for tests that need to tamper with stored rows."""
        return Session(self._engine)
