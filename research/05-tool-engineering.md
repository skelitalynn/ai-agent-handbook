# 第 05 章研究记录：Tool Engineering

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Tool Calling 的契约包含哪些对象，模型和应用分别承担什么责任？
2. 工具名称、描述、输入与输出 Schema 如何影响选择和执行正确性？
3. 为什么 Schema 通过仍不代表调用有权限、业务合法或可以安全重试？
4. 如何区分读取、写入、不可逆副作用，并设计审批、幂等和超时语义？
5. 工具错误如何结构化返回，什么错误适合让模型修正，什么错误应直接停止？
6. 工具很多时如何进行权限过滤、发现和延迟加载？

## 范围边界

- 第 04 章已经解释 Agent Loop 与 Observation 写回，本章不重复循环推导。
- 本章建立单个 Tool 从定义、暴露、选择、校验、授权、执行到返回结果的完整契约。
- 第 09 章展开 Trace 与可观测性，第 14 章展开 Human-in-the-loop 交互。
- 第 18 章展开 MCP 协议；本章只借 MCP Tool 规范核对通用 Schema、错误和安全要求。
- 第 23 章展开跨服务重试预算、Circuit Breaker、补偿和故障恢复。
- 第 24 章展开 Prompt Injection、最小权限、沙箱与完整威胁模型。

## 一手资料与采用结论

### 1. Function calling

- 来源：OpenAI API 官方文档
- 链接：https://developers.openai.com/api/docs/guides/function-calling
- 核对内容：模型返回的是 Tool Call 请求，应用执行并用 `call_id` 回传结果；工具定义包含名称、描述和 JSON Schema；Strict Mode 的 Schema 限制；`tool_choice`、多工具调用和并行开关；工具定义占用上下文 Token。
- 采用结论：模型不是函数执行器；Schema 只约束结构，Runtime 仍需授权与业务校验；处理响应时应预期零个、一个或多个调用并准确关联结果。
- 版本说明：`strict` 默认行为、支持的 Schema 子集和模型能力会变化，正文仅把厂商无关机制写成通用结论。
- 最后核验日期：2026-07-22

### 2. Tool search

- 来源：OpenAI API 官方文档
- 链接：https://developers.openai.com/api/docs/guides/tools-tool-search
- 核对内容：延迟加载工具可避免预先把所有定义放入上下文，并降低 Token 成本；当前只支持 `gpt-5.4` 及以后模型。
- 采用结论：把 Tool Discovery 写成通用架构模式，把 OpenAI `tool_search` 明确标成有模型限制的具体实现，不推广为所有模型 API 的通用能力。
- 最后核验日期：2026-07-22

### 3. Define tools

- 来源：Anthropic Claude Platform 官方文档
- 链接：https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
- 核对内容：客户端工具定义包含名称、详细描述和 `input_schema`；描述应说明用途、适用与不适用条件、参数含义和限制；复杂输入可增加经过 Schema 校验的示例；`tool_choice` 控制调用要求。
- 采用结论：工具描述是模型侧接口文档，名称和边界比把内部函数原样暴露更重要；示例是按失败数据决定的可选成本，不是默认堆叠。
- 最后核验日期：2026-07-22

### 4. Handle tool calls

- 来源：Anthropic Claude Platform 官方文档
- 链接：https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
- 核对内容：`tool_use` 的 ID、名称和输入与后续 `tool_result` 关联；`is_error` 明确工具执行错误；消息顺序有严格协议要求；外部工具结果应视为不可信内容。
- 采用结论：Tool Result 必须有调用关联和显式错误状态，厂商消息格式不能混用；外部返回值不是可信指令。
- 最后核验日期：2026-07-22

### 5. MCP Tools Specification 2025-11-25

- 来源：Model Context Protocol 官方规范
- 链接：https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- 核对内容：Tool 的名称、描述、`inputSchema`、可选 `outputSchema`、结构化结果和两类错误；服务器必须校验输入、实施访问控制、限流和净化输出，客户端应对敏感操作确认、验证结果、设置超时并记录审计日志。
- 采用结论：输入和输出都要校验；协议错误与可修正的执行错误应分开；工具注解来自不可信服务器时不能直接作为授权事实。
- 版本说明：采用 2025-11-25 稳定规范；正文不把 MCP 字段强制套到所有厂商 API。
- 最后核验日期：2026-07-22

### 6. RFC 9110: HTTP Semantics

- 来源：IETF / RFC Editor
- 链接：https://www.rfc-editor.org/rfc/rfc9110.html#name-idempotent-methods
- 核对内容：安全方法的语义基本只读；幂等表示多次相同请求的预期服务端效果与一次相同；非幂等请求不应在无法确认首次请求未生效时自动重试。
- 采用结论：区分“只读”“有副作用”和“幂等”；超时并不证明写操作未发生，只有下游真正支持幂等键、状态查询或事务语义时才可安全自动重试。
- 最后核验日期：2026-07-22

### 7. Building effective agents

- 来源：Anthropic Engineering
- 链接：https://www.anthropic.com/engineering/building-effective-agents
- 核对内容：工具接口应像人机界面一样投入设计；定义需包含清晰名称、参数、示例、边界，并根据模型真实失败迭代。
- 采用结论：Tool Engineering 是 Agent-Computer Interface 设计，不是给现有后端函数自动生成 JSON Schema 即结束。
- 最后核验日期：2026-07-22

## 术语和工程决策

### Function、Tool 与 Tool Call

- Function 是应用代码中的实现单元。
- Tool 是暴露给模型的能力契约，可能由本地函数、远程 API、MCP Server 或托管服务实现。
- Tool Call 是模型提出的调用请求，不是执行成功证明。

正文以 Tool 为核心术语，并在厂商 API 语境中保留 Function Calling 的官方名称。

### Strict Schema 是否足够安全？

不够。Strict 只提高参数对声明 Schema 的符合度，不能证明资源属于当前用户、金额满足业务上限、工具描述可信或调用应被执行。授权、审批、业务不变量和输出验证继续由确定性系统承担。

### 工具注解能否直接决定审批？

不能。副作用与只读注解有助于策略和 UI，但如果定义来自外部或不可信 Tool Server，客户端必须把它当作声明而不是事实。高风险能力应在受信注册表和执行层独立分类。

### 超时后是否可以重试？

读取通常可以在有限预算内重试；写入超时可能已经产生副作用，结果只是调用方未知。除非同一幂等键能被下游原子识别，或系统可以查询和协调最终状态，否则不得盲目重试。

## 示例设计

`examples/05-tool-engineering/tool_executor.py` 用标准库实现一个最小异步 Tool Executor：

- 注册时保存模型可见定义和受信执行策略；
- 只向模型暴露调用者 Scope 允许的工具；
- 使用工具专属 Validator 做参数与业务前置校验；
- 写操作要求幂等键，敏感工具要求显式审批；
- 使用 `asyncio.wait_for` 实施超时；
- 区分读取超时和写入结果未知；
- 返回结构化错误，不把内部异常文本泄露给模型；
- 内存幂等缓存只用于解释机制，不冒充生产持久化方案。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过 10 项单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
