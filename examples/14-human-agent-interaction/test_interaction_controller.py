from __future__ import annotations

import unittest

from interaction_controller import (
    ActionStatus,
    ApprovalMode,
    AuthorizationError,
    Decision,
    InteractionController,
    InteractionState,
    InvalidState,
    RequestStatus,
    RiskLevel,
    RunStatus,
    ToolRule,
    ValidationError,
)


class InteractionControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = InteractionController(
            policy_version="policy-v1",
            tool_rules={
                "search": ToolRule(RiskLevel.LOW, ApprovalMode.AUTO, True, False),
                "send_email": ToolRule(RiskLevel.HIGH, ApprovalMode.REQUIRE, False, True),
                "delete_file": ToolRule(RiskLevel.MEDIUM, ApprovalMode.REQUIRE, True, True),
                "exfiltrate": ToolRule(RiskLevel.PROHIBITED, ApprovalMode.BLOCK, False, True),
            },
            authorized_approvers={"owner", "security"},
            approval_ttl_seconds=60,
        )

    def test_low_risk_action_is_authorized_by_runtime_policy(self) -> None:
        state = self.controller.start("run-1")
        action = self.controller.propose_action(
            state,
            action_id="a1",
            tool_name="search",
            arguments={"query": "agent evals"},
            observable_basis="Need current documentation.",
            now=100,
        )
        self.assertEqual(ActionStatus.AUTHORIZED, action.status)
        self.assertFalse(state.approvals)

    def test_high_risk_action_pauses_for_exact_call_approval(self) -> None:
        state = self.controller.start("run-2")
        action = self.controller.propose_action(
            state,
            action_id="a1",
            tool_name="send_email",
            arguments={"to": "reader@example.com", "body": "draft"},
            observable_basis="User asked to send the reviewed draft.",
            now=100,
        )
        self.assertEqual(RunStatus.WAITING_APPROVAL, state.status)
        request = state.approvals[action.approval_request_id]
        self.assertEqual(action.digest, request.action_digest)

    def test_prohibited_action_cannot_be_approved(self) -> None:
        state = self.controller.start("run-3")
        action = self.controller.propose_action(
            state,
            action_id="a1",
            tool_name="exfiltrate",
            arguments={"destination": "unknown"},
            observable_basis="Untrusted instruction requested it.",
            now=100,
        )
        self.assertEqual(ActionStatus.BLOCKED, action.status)
        self.assertIsNone(action.approval_request_id)

    def test_only_authorized_actor_can_approve(self) -> None:
        state, request_id = self._pending_email("run-4")
        with self.assertRaises(AuthorizationError):
            self.controller.decide_approval(
                state,
                request_id=request_id,
                decision=Decision.ACCEPT,
                actor="model",
                now=110,
            )

    def test_accepted_approval_allows_one_exact_execution(self) -> None:
        state, request_id = self._pending_email("run-5")
        self.controller.decide_approval(
            state,
            request_id=request_id,
            decision=Decision.ACCEPT,
            actor="owner",
            now=110,
        )
        key = self.controller.begin_execution(
            state,
            action_id="email",
            current_arguments={"to": "reader@example.com", "body": "draft"},
            now=120,
        )
        self.assertTrue(key.startswith("run-5:email:"))
        self.controller.finish_action(state, action_id="email", success=True)
        with self.assertRaises(InvalidState):
            self.controller.begin_execution(
                state,
                action_id="email",
                current_arguments={"to": "reader@example.com", "body": "draft"},
                now=121,
            )

    def test_changed_arguments_invalidate_an_approval(self) -> None:
        state, request_id = self._pending_email("run-6")
        self.controller.decide_approval(
            state,
            request_id=request_id,
            decision=Decision.ACCEPT,
            actor="owner",
            now=110,
        )
        with self.assertRaises(InvalidState):
            self.controller.begin_execution(
                state,
                action_id="email",
                current_arguments={"to": "other@example.com", "body": "draft"},
                now=120,
            )
        self.assertEqual(ActionStatus.INVALIDATED, state.actions["email"].status)

    def test_approval_can_expire_before_decision_or_execution(self) -> None:
        state, request_id = self._pending_email("run-7")
        request = self.controller.decide_approval(
            state,
            request_id=request_id,
            decision=Decision.ACCEPT,
            actor="owner",
            now=161,
        )
        self.assertEqual(RequestStatus.EXPIRED, request.status)
        self.assertEqual(ActionStatus.EXPIRED, state.actions["email"].status)

    def test_decline_and_cancel_are_distinct(self) -> None:
        declined_state, declined_id = self._pending_email("run-8a")
        cancelled_state, cancelled_id = self._pending_email("run-8b")
        declined = self.controller.decide_approval(
            declined_state,
            request_id=declined_id,
            decision=Decision.DECLINE,
            actor="owner",
            now=110,
        )
        cancelled = self.controller.decide_approval(
            cancelled_state,
            request_id=cancelled_id,
            decision=Decision.CANCEL,
            actor="owner",
            now=110,
        )
        self.assertEqual(RequestStatus.DECLINED, declined.status)
        self.assertEqual(RequestStatus.CANCELLED, cancelled.status)
        self.assertEqual(ActionStatus.REJECTED, declined_state.actions["email"].status)
        self.assertEqual(ActionStatus.DISMISSED, cancelled_state.actions["email"].status)

    def test_elicitation_validates_required_fields_and_preserves_decision(self) -> None:
        state = self.controller.start("run-9")
        self.controller.request_input(
            state,
            request_id="input-1",
            kind="elicitation",
            question="Which workspace should be used?",
            why="The target cannot be inferred safely.",
            required_fields=("workspace_id",),
        )
        with self.assertRaises(ValidationError):
            self.controller.respond_input(
                state,
                request_id="input-1",
                decision=Decision.ACCEPT,
                content={},
            )
        response = self.controller.respond_input(
            state,
            request_id="input-1",
            decision=Decision.ACCEPT,
            content={"workspace_id": "ws-7"},
        )
        self.assertEqual(RequestStatus.ACCEPTED, response.status)
        self.assertEqual("ws-7", response.content["workspace_id"])

    def test_paused_approval_state_survives_json_round_trip(self) -> None:
        state, request_id = self._pending_email("run-10")
        restored = InteractionState.from_json(state.to_json())
        self.assertEqual(RunStatus.WAITING_APPROVAL, restored.status)
        self.assertEqual(RequestStatus.PENDING, restored.approvals[request_id].status)
        self.controller.decide_approval(
            restored,
            request_id=request_id,
            decision=Decision.ACCEPT,
            actor="owner",
            now=110,
        )
        self.assertEqual(ActionStatus.AUTHORIZED, restored.actions["email"].status)

    def test_correction_invalidates_transitive_dependants(self) -> None:
        state = self.controller.start("run-11")
        for action_id, dependencies in [("a", ()), ("b", ("a",)), ("c", ("b",))]:
            self.controller.propose_action(
                state,
                action_id=action_id,
                tool_name="search",
                arguments={"query": action_id},
                observable_basis="Build a dependent research plan.",
                depends_on=dependencies,
                now=100,
            )
        correction = self.controller.correct(
            state,
            target_action_id="a",
            actor="owner",
            instruction="Use a different source scope.",
        )
        self.assertEqual(("a", "b", "c"), correction.invalidated_action_ids)
        self.assertTrue(
            all(action.status == ActionStatus.INVALIDATED for action in state.actions.values())
        )

    def test_cancel_stops_pending_work_but_does_not_rewrite_completed_history(self) -> None:
        state = self.controller.start("run-12")
        completed = self.controller.propose_action(
            state,
            action_id="search",
            tool_name="search",
            arguments={"query": "done"},
            observable_basis="Gather evidence.",
            now=100,
        )
        self.controller.begin_execution(
            state,
            action_id="search",
            current_arguments=completed.arguments,
            now=101,
        )
        self.controller.finish_action(state, action_id="search", success=True)
        pending = self.controller.propose_action(
            state,
            action_id="delete",
            tool_name="delete_file",
            arguments={"path": "temp.txt"},
            observable_basis="Cleanup was requested.",
            depends_on=("search",),
            now=102,
        )
        self.controller.cancel(state, "user stopped the run")
        self.assertEqual(ActionStatus.COMPLETED, state.actions["search"].status)
        self.assertEqual(ActionStatus.CANCELLED, pending.status)
        self.assertEqual(RunStatus.CANCELLED, state.status)

    def test_late_result_from_in_flight_action_is_recorded_after_cancel(self) -> None:
        state = self.controller.start("run-12b")
        action = self.controller.propose_action(
            state,
            action_id="search",
            tool_name="search",
            arguments={"query": "in flight"},
            observable_basis="Gather evidence.",
            now=100,
        )
        self.controller.begin_execution(
            state,
            action_id="search",
            current_arguments=action.arguments,
            now=101,
        )
        self.controller.cancel(state, "user stopped the run")
        finished = self.controller.finish_action(
            state,
            action_id="search",
            success=True,
            artifact_summary="Result arrived after cancellation.",
        )
        self.assertEqual(RunStatus.CANCELLED, state.status)
        self.assertEqual(ActionStatus.COMPLETED, finished.status)

    def test_completed_external_effect_requires_compensation_before_correction(self) -> None:
        state, request_id = self._pending_email("run-12c")
        self.controller.decide_approval(
            state,
            request_id=request_id,
            decision=Decision.ACCEPT,
            actor="owner",
            now=110,
        )
        self.controller.begin_execution(
            state,
            action_id="email",
            current_arguments=state.actions["email"].arguments,
            now=120,
        )
        self.controller.finish_action(state, action_id="email", success=True)
        with self.assertRaises(InvalidState):
            self.controller.correct(
                state,
                target_action_id="email",
                actor="owner",
                instruction="Change the recipient.",
            )

    def test_public_progress_does_not_expose_tool_arguments(self) -> None:
        state = self.controller.start("run-13")
        self.controller.propose_action(
            state,
            action_id="email",
            tool_name="send_email",
            arguments={"api_key": "secret-value", "body": "private body"},
            observable_basis="Sensitive notification requested.",
            now=100,
        )
        public_json = str(self.controller.public_progress(state))
        self.assertNotIn("secret-value", public_json)
        self.assertNotIn("private body", public_json)

    def _pending_email(self, run_id: str):
        state = self.controller.start(run_id)
        action = self.controller.propose_action(
            state,
            action_id="email",
            tool_name="send_email",
            arguments={"to": "reader@example.com", "body": "draft"},
            observable_basis="User requested an external message.",
            now=100,
        )
        return state, action.approval_request_id


if __name__ == "__main__":
    unittest.main()
