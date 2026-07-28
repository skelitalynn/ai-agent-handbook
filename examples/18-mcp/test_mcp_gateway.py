import unittest

from mcp_gateway import (
    LATEST_STABLE_PROTOCOL,
    Approval,
    ApprovalError,
    AuthorizationContext,
    AuthorizationError,
    MCPConnection,
    MCPGateway,
    ObjectContract,
    ProtocolError,
    ServerManifest,
    SessionPhase,
    ToolExecutionError,
    ToolSpec,
)


def read_tool(name="read_issue"):
    return ToolSpec(
        name,
        "Read one issue",
        ObjectContract({"id": str}, frozenset({"id"})),
        frozenset({"issues:read"}),
    )


def write_tool():
    return ToolSpec(
        "close_issue",
        "Close one issue",
        ObjectContract({"id": str}, frozenset({"id"})),
        frozenset({"issues:write"}),
        mutating=True,
    )


def connection(server_id="tracker", uri="https://mcp.example.com/tracker", tools=None):
    manifest = ServerManifest(
        server_id,
        uri,
        frozenset({LATEST_STABLE_PROTOCOL}),
        frozenset({"tools", "resources"}),
        tuple(tools or (read_tool(), write_tool())),
    )
    return MCPConnection(manifest)


def initialized_connection(**kwargs):
    item = connection(**kwargs)
    item.initialize(LATEST_STABLE_PROTOCOL, frozenset({"sampling", "elicitation"}))
    return item


def auth(scope="issues:read", audience="https://mcp.example.com/tracker", subject="user-1"):
    return AuthorizationContext(subject, audience, frozenset({scope}))


class MCPGatewayTests(unittest.TestCase):
    def test_initialize_must_happen_before_operations(self):
        item = connection()
        with self.assertRaisesRegex(ProtocolError, "not operating"):
            item.list_tools()
        item.initialize(LATEST_STABLE_PROTOCOL, frozenset())
        self.assertEqual(item.phase, SessionPhase.OPERATING)

    def test_protocol_version_is_negotiated_explicitly(self):
        with self.assertRaisesRegex(ProtocolError, "unsupported protocol version"):
            connection().initialize("2024-11-05", frozenset())

    def test_capabilities_are_directional(self):
        item = initialized_connection()
        item.require_server_capability("resources")
        item.require_client_capability("sampling")
        with self.assertRaisesRegex(ProtocolError, "client did not declare"):
            item.require_client_capability("roots")

    def test_tool_names_are_unique_within_a_server(self):
        item = initialized_connection()
        with self.assertRaisesRegex(ProtocolError, "unique"):
            item.refresh_tools((read_tool(), read_tool()), revision=2)

    def test_gateway_namespaces_same_tool_name_from_different_servers(self):
        gateway = MCPGateway()
        gateway.add_connection(initialized_connection())
        gateway.add_connection(
            initialized_connection(
                server_id="archive",
                uri="https://mcp.example.com/archive",
                tools=(read_tool(),),
            )
        )
        self.assertIn("tracker::read_issue", gateway.discover_tools())
        self.assertIn("archive::read_issue", gateway.discover_tools())

    def test_tool_arguments_are_validated_at_the_boundary(self):
        gateway = MCPGateway({"tracker": initialized_connection()})
        with self.assertRaisesRegex(ToolExecutionError, "must be str"):
            gateway.prepare_call("tracker::read_issue", {"id": 42}, auth())

    def test_authorization_binds_audience_and_scope(self):
        gateway = MCPGateway({"tracker": initialized_connection()})
        with self.assertRaisesRegex(AuthorizationError, "audience"):
            gateway.prepare_call(
                "tracker::read_issue",
                {"id": "7"},
                auth(audience="https://other.example.com"),
            )
        with self.assertRaisesRegex(AuthorizationError, "missing scopes"):
            gateway.prepare_call(
                "tracker::read_issue", {"id": "7"}, auth(scope="profile:read")
            )

    def test_read_only_call_does_not_require_approval(self):
        gateway = MCPGateway({"tracker": initialized_connection()})
        prepared = gateway.prepare_call("tracker::read_issue", {"id": "7"}, auth())
        result = gateway.execute_call(prepared, auth(), lambda _, args: args["id"])
        self.assertEqual(result.content, "7")
        self.assertFalse(result.is_error)

    def test_mutating_call_requires_exact_call_approval(self):
        gateway = MCPGateway({"tracker": initialized_connection()})
        write_auth = auth(scope="issues:write")
        prepared = gateway.prepare_call("tracker::close_issue", {"id": "7"}, write_auth)
        with self.assertRaises(ApprovalError):
            gateway.execute_call(prepared, write_auth, lambda *_: "closed")
        wrong = Approval("not-the-call", "reviewer", True)
        with self.assertRaises(ApprovalError):
            gateway.execute_call(prepared, write_auth, lambda *_: "closed", wrong)
        exact = Approval(prepared.digest, "reviewer", True)
        self.assertEqual(
            gateway.execute_call(prepared, write_auth, lambda *_: "closed", exact).content,
            "closed",
        )

    def test_subject_cannot_change_between_prepare_and_execute(self):
        gateway = MCPGateway({"tracker": initialized_connection()})
        prepared = gateway.prepare_call("tracker::read_issue", {"id": "7"}, auth())
        with self.assertRaisesRegex(AuthorizationError, "subject changed"):
            gateway.execute_call(
                prepared,
                auth(subject="user-2"),
                lambda *_: "should not run",
            )

    def test_tool_list_change_invalidates_prepared_call(self):
        item = initialized_connection()
        gateway = MCPGateway({"tracker": item})
        prepared = gateway.prepare_call("tracker::read_issue", {"id": "7"}, auth())
        item.refresh_tools((read_tool(), write_tool()), revision=2)
        with self.assertRaisesRegex(ProtocolError, "tool list changed"):
            gateway.execute_call(prepared, auth(), lambda *_: "stale")

    def test_tool_execution_failure_is_a_result_and_is_audited(self):
        gateway = MCPGateway({"tracker": initialized_connection()})
        prepared = gateway.prepare_call("tracker::read_issue", {"id": "7"}, auth())

        def fail(*_):
            raise ToolExecutionError("upstream timed out")

        result = gateway.execute_call(prepared, auth(), fail)
        self.assertTrue(result.is_error)
        self.assertEqual(gateway.audit_log[-1].outcome, "tool_error")
        self.assertEqual(gateway.audit_log[-1].request_id, result.request_id)

    def test_closed_connection_rejects_further_operations(self):
        item = initialized_connection()
        item.close()
        with self.assertRaisesRegex(ProtocolError, "not operating"):
            item.list_tools()


if __name__ == "__main__":
    unittest.main()
