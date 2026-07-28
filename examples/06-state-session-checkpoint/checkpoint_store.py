"""A small SQLite checkpoint store with tenant isolation and OCC."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Mapping


class RunStatus(str, Enum):
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
ALLOWED_TRANSITIONS = {
    RunStatus.RUNNING: {
        RunStatus.RUNNING,
        RunStatus.INTERRUPTED,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.INTERRUPTED: {
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    },
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}


class CheckpointConflict(RuntimeError):
    pass


class InvalidTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class RunCheckpoint:
    tenant_id: str
    session_id: str
    run_id: str
    version: int
    status: RunStatus
    step: int
    state: Mapping[str, object]
    pending_action: Mapping[str, object] | None = None
    state_schema_version: int = 1


class CheckpointStore:
    def __init__(self, database: str | Path) -> None:
        self._connection = sqlite3.connect(str(database), isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS run_checkpoints (
                tenant_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                status TEXT NOT NULL,
                step INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                pending_action_json TEXT,
                state_schema_version INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, run_id)
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_checkpoint_session
            ON run_checkpoints (tenant_id, session_id)
            """
        )

    def close(self) -> None:
        self._connection.close()

    def create(
        self,
        *,
        tenant_id: str,
        session_id: str,
        run_id: str,
        state: Mapping[str, object],
        state_schema_version: int = 1,
    ) -> RunCheckpoint:
        checkpoint = RunCheckpoint(
            tenant_id=tenant_id,
            session_id=session_id,
            run_id=run_id,
            version=0,
            status=RunStatus.RUNNING,
            step=0,
            state=self._json_copy(state),
            state_schema_version=state_schema_version,
        )
        try:
            self._connection.execute(
                """
                INSERT INTO run_checkpoints (
                    tenant_id, run_id, session_id, version, status, step,
                    state_json, pending_action_json, state_schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._parameters(checkpoint),
            )
        except sqlite3.IntegrityError as exc:
            raise CheckpointConflict("run already exists") from exc
        return checkpoint

    def load(self, tenant_id: str, run_id: str) -> RunCheckpoint | None:
        row = self._connection.execute(
            """
            SELECT * FROM run_checkpoints
            WHERE tenant_id = ? AND run_id = ?
            """,
            (tenant_id, run_id),
        ).fetchone()
        return None if row is None else self._from_row(row)

    def save(
        self,
        checkpoint: RunCheckpoint,
        *,
        status: RunStatus,
        step: int,
        state: Mapping[str, object],
        pending_action: Mapping[str, object] | None = None,
    ) -> RunCheckpoint:
        if status not in ALLOWED_TRANSITIONS[checkpoint.status]:
            raise InvalidTransition(f"{checkpoint.status.value} -> {status.value}")
        if step < checkpoint.step:
            raise InvalidTransition("step cannot move backwards")

        updated = replace(
            checkpoint,
            version=checkpoint.version + 1,
            status=status,
            step=step,
            state=self._json_copy(state),
            pending_action=(
                None if pending_action is None else self._json_copy(pending_action)
            ),
        )
        cursor = self._connection.execute(
            """
            UPDATE run_checkpoints
            SET session_id = ?, version = ?, status = ?, step = ?,
                state_json = ?, pending_action_json = ?, state_schema_version = ?
            WHERE tenant_id = ? AND run_id = ? AND version = ?
            """,
            (
                updated.session_id,
                updated.version,
                updated.status.value,
                updated.step,
                json.dumps(updated.state, ensure_ascii=False, sort_keys=True),
                self._dump_optional(updated.pending_action),
                updated.state_schema_version,
                updated.tenant_id,
                updated.run_id,
                checkpoint.version,
            ),
        )
        if cursor.rowcount != 1:
            raise CheckpointConflict("checkpoint was changed or removed")
        return updated

    @staticmethod
    def _parameters(checkpoint: RunCheckpoint) -> tuple[object, ...]:
        return (
            checkpoint.tenant_id,
            checkpoint.run_id,
            checkpoint.session_id,
            checkpoint.version,
            checkpoint.status.value,
            checkpoint.step,
            json.dumps(checkpoint.state, ensure_ascii=False, sort_keys=True),
            CheckpointStore._dump_optional(checkpoint.pending_action),
            checkpoint.state_schema_version,
        )

    @staticmethod
    def _dump_optional(value: Mapping[str, object] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _json_copy(value: Mapping[str, object]) -> dict[str, object]:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        decoded = json.loads(encoded)
        if not isinstance(decoded, dict):
            raise TypeError("checkpoint state must be a JSON object")
        return decoded

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RunCheckpoint:
        pending = (
            None
            if row["pending_action_json"] is None
            else json.loads(row["pending_action_json"])
        )
        return RunCheckpoint(
            tenant_id=row["tenant_id"],
            session_id=row["session_id"],
            run_id=row["run_id"],
            version=row["version"],
            status=RunStatus(row["status"]),
            step=row["step"],
            state=json.loads(row["state_json"]),
            pending_action=pending,
            state_schema_version=row["state_schema_version"],
        )


if __name__ == "__main__":
    store = CheckpointStore(":memory:")
    run = store.create(
        tenant_id="tenant-1",
        session_id="session-7",
        run_id="run-42",
        state={"goal": "cancel order A-17"},
    )
    run = store.save(
        run,
        status=RunStatus.INTERRUPTED,
        step=1,
        state=run.state,
        pending_action={"tool": "cancel_order", "order_id": "A-17"},
    )
    print(run)
    store.close()
