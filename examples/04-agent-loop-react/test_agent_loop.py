import unittest

from agent_loop import (
    AgentRuntime,
    FinalAnswer,
    NeedUserInput,
    ScriptedModel,
    ToolCall,
    ToolObservation,
)


class AgentRuntimeTests(unittest.TestCase):
    def test_tool_observation_is_written_back_before_final_answer(self) -> None:
        model = ScriptedModel(
            [
                ToolCall("c1", "lookup", {"id": 7}),
                FinalAnswer("found"),
            ]
        )
        result = AgentRuntime(model, {"lookup": lambda args: args["id"]}).run(
            "find 7"
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.final_answer, "found")
        self.assertEqual(len(model.seen_histories), 2)
        observation = model.seen_histories[1][-1]
        self.assertIsInstance(observation, ToolObservation)
        self.assertTrue(observation.ok)
        self.assertEqual(observation.output, 7)

    def test_user_input_request_interrupts_the_run(self) -> None:
        model = ScriptedModel([NeedUserInput("Which order?")])

        result = AgentRuntime(model, {}).run("check my order")

        self.assertEqual(result.status, "interrupted")
        self.assertEqual(result.pending_question, "Which order?")
        self.assertIsNone(result.final_answer)

    def test_repeated_identical_call_is_stopped(self) -> None:
        repeated = [ToolCall(f"c{i}", "lookup", {"id": 7}) for i in range(3)]
        model = ScriptedModel(repeated)
        executions = 0

        def lookup(_args):
            nonlocal executions
            executions += 1
            return "missing"

        result = AgentRuntime(
            model, {"lookup": lookup}, max_steps=5, max_identical_calls=2
        ).run("find 7")

        self.assertEqual(result.status, "failed")
        self.assertIn("repeated tool call", result.error)
        self.assertEqual(executions, 2)

    def test_maximum_steps_bounds_different_calls(self) -> None:
        model = ScriptedModel(
            [ToolCall(f"c{i}", "lookup", {"id": i}) for i in range(3)]
        )

        result = AgentRuntime(model, {"lookup": lambda args: args}, max_steps=2).run(
            "keep looking"
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error, "maximum steps exceeded: 2")

    def test_tool_exception_becomes_an_observation_and_model_can_recover(self) -> None:
        model = ScriptedModel(
            [ToolCall("c1", "fragile", {}), FinalAnswer("fallback used")]
        )

        def fragile(_args):
            raise TimeoutError("service timed out")

        result = AgentRuntime(model, {"fragile": fragile}).run("try it")

        self.assertEqual(result.status, "completed")
        observation = model.seen_histories[1][-1]
        self.assertIsInstance(observation, ToolObservation)
        self.assertFalse(observation.ok)
        self.assertIn("TimeoutError", observation.error)

    def test_unknown_tool_is_an_explicit_observation(self) -> None:
        model = ScriptedModel(
            [ToolCall("c1", "missing", {}), FinalAnswer("cannot use that tool")]
        )

        result = AgentRuntime(model, {}).run("try missing")

        self.assertEqual(result.status, "completed")
        observation = model.seen_histories[1][-1]
        self.assertIsInstance(observation, ToolObservation)
        self.assertEqual(observation.error, "unknown tool")


if __name__ == "__main__":
    unittest.main()
