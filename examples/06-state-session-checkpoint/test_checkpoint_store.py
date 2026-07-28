import tempfile
import unittest
from pathlib import Path

from checkpoint_store import (
    CheckpointConflict,
    CheckpointStore,
    InvalidTransition,
    RunStatus,
)


class CheckpointStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.database = Path(self._temporary.name) / "checkpoints.db"
        self.store = CheckpointStore(self.database)

    def tearDown(self) -> None:
        self.store.close()
        self._temporary.cleanup()

    def create_run(self):
        return self.store.create(
            tenant_id="tenant-1",
            session_id="session-1",
            run_id="run-1",
            state={"goal": "inspect order", "facts": []},
            state_schema_version=3,
        )

    def test_checkpoint_persists_across_store_instances(self) -> None:
        created = self.create_run()
        interrupted = self.store.save(
            created,
            status=RunStatus.INTERRUPTED,
            step=2,
            state={"goal": "inspect order", "facts": ["order exists"]},
            pending_action={"tool": "cancel_order", "id": "A-1"},
        )
        self.store.close()
        self.store = CheckpointStore(self.database)

        loaded = self.store.load("tenant-1", "run-1")

        self.assertEqual(loaded, interrupted)
        self.assertEqual(loaded.state_schema_version, 3)

    def test_tenant_is_part_of_the_lookup_boundary(self) -> None:
        self.create_run()

        self.assertIsNone(self.store.load("tenant-2", "run-1"))

    def test_stale_writer_is_rejected(self) -> None:
        original = self.create_run()
        stale_copy = self.store.load("tenant-1", "run-1")
        self.store.save(
            original,
            status=RunStatus.RUNNING,
            step=1,
            state={"goal": "inspect order", "facts": ["first writer"]},
        )

        with self.assertRaises(CheckpointConflict):
            self.store.save(
                stale_copy,
                status=RunStatus.RUNNING,
                step=1,
                state={"goal": "inspect order", "facts": ["stale writer"]},
            )

    def test_terminal_run_cannot_be_resumed(self) -> None:
        run = self.create_run()
        completed = self.store.save(
            run,
            status=RunStatus.COMPLETED,
            step=1,
            state={"answer": "done"},
        )

        with self.assertRaises(InvalidTransition):
            self.store.save(
                completed,
                status=RunStatus.RUNNING,
                step=2,
                state=completed.state,
            )

    def test_interrupted_run_can_resume_with_a_decision(self) -> None:
        run = self.create_run()
        interrupted = self.store.save(
            run,
            status=RunStatus.INTERRUPTED,
            step=1,
            state={"approval": None},
            pending_action={"tool": "cancel_order", "id": "A-1"},
        )
        resumed = self.store.save(
            interrupted,
            status=RunStatus.RUNNING,
            step=1,
            state={"approval": "rejected"},
        )

        self.assertEqual(resumed.status, RunStatus.RUNNING)
        self.assertIsNone(resumed.pending_action)
        self.assertEqual(resumed.state["approval"], "rejected")

    def test_step_cannot_move_backwards(self) -> None:
        run = self.create_run()
        run = self.store.save(
            run,
            status=RunStatus.RUNNING,
            step=2,
            state=run.state,
        )

        with self.assertRaises(InvalidTransition):
            self.store.save(
                run,
                status=RunStatus.RUNNING,
                step=1,
                state=run.state,
            )

    def test_duplicate_run_id_in_same_tenant_is_rejected(self) -> None:
        self.create_run()

        with self.assertRaises(CheckpointConflict):
            self.create_run()


if __name__ == "__main__":
    unittest.main()
