from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping


LATEST_STABLE_PROTOCOL = "2025-11-25"
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class ProtocolError(RuntimeError):
    """The peer violated the MCP session or message contract."""


class ToolExecutionError(ValueError):
    """The call reached the tool boundary but its input cannot be executed."""


class AuthorizationError(PermissionError):
    pass


class ApprovalError(PermissionError):
    pass


class SessionPhase(str, Enum):
    NEW = "new"
    OPERATING = "operating"
    CLOSED = "closed"


@dataclass(frozen=True)
class ObjectContract:
    """A deliberately small contract, not a full JSON Schema implementation."""

    properties: Mapping[str, type]
    required: frozenset[str] = frozenset()
    allow_extra: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))

    def validate(self, value: Mapping[str, object]) -> None:
        missing = self.required - value.keys()
        if missing:
            raise ToolExecutionError(f"missing required arguments: {sorted(missing)}")
        extra = value.keys() - self.properties.keys()
        if extra and not self.allow_extra:
            raise ToolExecutionError(f"unknown arguments: {sorted(extra)}")
        for name, item in value.items():
            expected = self.properties.get(name)
            if expected is not None and not isinstance(item, expected):
                raise ToolExecutionError(
                    f"argument {name!r} must be {expected.__name__}"
                )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_contract: ObjectContract
    required_scopes: frozenset[str] = frozenset()
    mutating: bool = False

    def __post_init__(self) -> None:
        if not _TOOL_NAME.fullmatch(self.name):
            raise ProtocolError(f"invalid MCP tool name: {self.name!r}")


@dataclass(frozen=True)
class ServerManifest:
    server_id: str
    canonical_uri: str
    supported_versions: frozenset[str]
    capabilities: frozenset[str]
    tools: tuple[ToolSpec, ...] = ()


@dataclass(frozen=True)
class InitializeResult:
    protocol_version: str
    server_capabilities: frozenset[str]
    client_capabilities: frozenset[str]


class MCPConnection:
    """One client connection to one MCP server."""

    def __init__(self, manifest: ServerManifest) -> None:
        self.manifest = manifest
        self.phase = SessionPhase.NEW
        self.protocol_version: str | None = None
        self.client_capabilities: frozenset[str] = frozenset()
        self.tool_revision = 0
        self._tools: dict[str, ToolSpec] = {}

    def initialize(
        self, protocol_version: str, client_capabilities: frozenset[str]
    ) -> InitializeResult:
        if self.phase is not SessionPhase.NEW:
            raise ProtocolError("initialize must be the first and only initialization")
        if protocol_version not in self.manifest.supported_versions:
            raise ProtocolError(f"unsupported protocol version: {protocol_version}")
        self.protocol_version = protocol_version
        self.client_capabilities = client_capabilities
        self.phase = SessionPhase.OPERATING
        if "tools" in self.manifest.capabilities:
            self.refresh_tools(self.manifest.tools, revision=1)
        return InitializeResult(
            protocol_version,
            self.manifest.capabilities,
            client_capabilities,
        )

    def require_server_capability(self, name: str) -> None:
        if self.phase is not SessionPhase.OPERATING:
            raise ProtocolError("connection is not operating")
        if name not in self.manifest.capabilities:
            raise ProtocolError(f"server did not declare capability: {name}")

    def require_client_capability(self, name: str) -> None:
        if self.phase is not SessionPhase.OPERATING:
            raise ProtocolError("connection is not operating")
        if name not in self.client_capabilities:
            raise ProtocolError(f"client did not declare capability: {name}")

    def refresh_tools(self, tools: tuple[ToolSpec, ...], revision: int) -> None:
        self.require_server_capability("tools")
        if revision <= self.tool_revision:
            raise ProtocolError("tool-list revision must increase")
        indexed = {tool.name: tool for tool in tools}
        if len(indexed) != len(tools):
            raise ProtocolError("tool names must be unique within one server")
        self._tools = indexed
        self.tool_revision = revision

    def list_tools(self) -> tuple[ToolSpec, ...]:
        self.require_server_capability("tools")
        return tuple(self._tools[name] for name in sorted(self._tools))

    def get_tool(self, name: str) -> ToolSpec:
        self.require_server_capability("tools")
        try:
            return self._tools[name]
        except KeyError as error:
            raise ProtocolError(f"unknown tool: {name}") from error

    def close(self) -> None:
        self.phase = SessionPhase.CLOSED


@dataclass(frozen=True)
class AuthorizationContext:
    subject: str
    audience: str
    scopes: frozenset[str]


@dataclass(frozen=True)
class PreparedCall:
    server_id: str
    tool_name: str
    arguments: Mapping[str, object]
    subject: str
    tool_revision: int
    approval_required: bool
    digest: str


@dataclass(frozen=True)
class Approval:
    call_digest: str
    approved_by: str
    approved: bool


@dataclass(frozen=True)
class ToolResult:
    request_id: str
    content: object
    is_error: bool = False


@dataclass(frozen=True)
class AuditEvent:
    request_id: str
    subject: str
    server_id: str
    tool_name: str
    call_digest: str
    outcome: str


@dataclass
class MCPGateway:
    connections: dict[str, MCPConnection] = field(default_factory=dict)
    audit_log: list[AuditEvent] = field(default_factory=list)
    _next_request_id: int = 1

    def add_connection(self, connection: MCPConnection) -> None:
        server_id = connection.manifest.server_id
        if server_id in self.connections:
            raise ProtocolError(f"duplicate server id: {server_id}")
        self.connections[server_id] = connection

    def discover_tools(self) -> tuple[str, ...]:
        refs: list[str] = []
        for server_id, connection in sorted(self.connections.items()):
            refs.extend(f"{server_id}::{tool.name}" for tool in connection.list_tools())
        return tuple(refs)

    def prepare_call(
        self,
        tool_ref: str,
        arguments: Mapping[str, object],
        auth: AuthorizationContext,
    ) -> PreparedCall:
        connection, tool = self._resolve(tool_ref)
        self._authorize(connection, tool, auth)
        tool.input_contract.validate(arguments)
        normalized = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        material = "\n".join(
            (connection.manifest.server_id, tool.name, auth.subject, normalized)
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return PreparedCall(
            connection.manifest.server_id,
            tool.name,
            MappingProxyType(dict(arguments)),
            auth.subject,
            connection.tool_revision,
            tool.mutating,
            digest,
        )

    def execute_call(
        self,
        prepared: PreparedCall,
        auth: AuthorizationContext,
        executor: Callable[[str, Mapping[str, object]], object],
        approval: Approval | None = None,
    ) -> ToolResult:
        connection, tool = self._resolve(
            f"{prepared.server_id}::{prepared.tool_name}"
        )
        self._authorize(connection, tool, auth)
        if auth.subject != prepared.subject:
            raise AuthorizationError("authorization subject changed after preparation")
        if connection.tool_revision != prepared.tool_revision:
            raise ProtocolError("tool list changed after call preparation")
        if prepared.approval_required:
            if (
                approval is None
                or not approval.approved
                or approval.call_digest != prepared.digest
            ):
                raise ApprovalError("an approval bound to this exact call is required")

        request_id = f"mcp-{self._next_request_id}"
        self._next_request_id += 1
        try:
            content = executor(tool.name, prepared.arguments)
            result = ToolResult(request_id, content)
            outcome = "success"
        except ToolExecutionError as error:
            result = ToolResult(request_id, str(error), is_error=True)
            outcome = "tool_error"
        self.audit_log.append(
            AuditEvent(
                request_id,
                auth.subject,
                prepared.server_id,
                prepared.tool_name,
                prepared.digest,
                outcome,
            )
        )
        return result

    def _resolve(self, tool_ref: str) -> tuple[MCPConnection, ToolSpec]:
        try:
            server_id, tool_name = tool_ref.split("::", 1)
            connection = self.connections[server_id]
        except (ValueError, KeyError) as error:
            raise ProtocolError(f"invalid namespaced tool reference: {tool_ref}") from error
        return connection, connection.get_tool(tool_name)

    @staticmethod
    def _authorize(
        connection: MCPConnection, tool: ToolSpec, auth: AuthorizationContext
    ) -> None:
        if not auth.subject:
            raise AuthorizationError("a verified subject is required")
        if auth.audience != connection.manifest.canonical_uri:
            raise AuthorizationError("token audience does not match the MCP server")
        missing = tool.required_scopes - auth.scopes
        if missing:
            raise AuthorizationError(f"missing scopes: {sorted(missing)}")
