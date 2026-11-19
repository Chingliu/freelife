from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class Decision:
    id: str
    code: str
    action: str  # buy / sell / hold
    reasons: list[str]
    evidence: list[str]
    risks: list[str]
    confidence: float
    provider_id: str
    as_of: str
    experimental: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    executed: bool | None = None
    execution_note: str = ""


class DecisionJournal:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def add(self, decision: Decision) -> Decision:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO decisions(id, payload) VALUES(?, ?)",
                (decision.id, json.dumps(asdict(decision), ensure_ascii=False)),
            )
        return decision

    def list(self, limit: int = 50) -> list[Decision]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM decisions ORDER BY rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out: list[Decision] = []
        for (payload,) in rows:
            data: dict[str, Any] = json.loads(payload)
            out.append(Decision(**data))
        return out

    @staticmethod
    def make(
        code: str,
        action: str,
        reasons: list[str],
        evidence: list[str],
        risks: list[str],
        confidence: float,
        provider_id: str,
        as_of: str,
        experimental: bool = False,
    ) -> Decision:
        return Decision(
            id=str(uuid4()),
            code=code,
            action=action,
            reasons=reasons,
            evidence=evidence,
            risks=risks,
            confidence=confidence,
            provider_id=provider_id,
            as_of=as_of,
            experimental=experimental,
        )
