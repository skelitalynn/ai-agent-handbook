# AI Agent 知识范围缺口核验

## 1. 核验目的

检查现有 `docs/LEARNING_PATH.md` 和 `SUMMARY.md` 是否遗漏了已经形成独立问题域、具有稳定工程边界和面试价值的 Agent 知识，并避免继续用“与”把不同抽象层级的概念合并成一个章节。

最后核验日期：2026-07-22。

## 2. 目录调整结论

新增为正式一级章节：

- Planning、Reasoning 与决策控制
- Human-Agent Interaction
- Multimodal 与 Realtime Agents
- Agent Reliability Engineering

同时拆开以下原有混合章节：

- State、Session 与 Memory：拆为 `State 与 Session`、`Memory`
- Workflow、Orchestration 与 Multi-Agent：拆为 `Workflow 与 Orchestration`、`Multi-Agent Systems`
- Framework、Runtime、Harness 与 Skills：拆为 `Agent Framework`、`Runtime 与 Harness`、`Skills 与扩展机制`
- MCP、A2A 与 Agent 协议：拆为 `MCP`、`Agent 间通信与 A2A`
- Evals、Tracing 与 Observability：拆为 `Agent Evals`、`Tracing 与 Observability`
- Fine-tuning、项目与术语索引：拆为三个附录

## 3. 主要官方来源

| 来源 | 用于核对的内容 | 核验结论 |
|---|---|---|
| [Anthropic：Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents) | Workflow 与 Agent 的边界；Routing、Parallelization、Orchestrator-Workers、Evaluator-Optimizer | Planning 与 Workflow 应形成独立知识域，Multi-Agent 不应承载所有编排模式 |
| [Anthropic：Trustworthy Agents in Practice](https://www.anthropic.com/research/trustworthy-agents) | Agent 的计划、行动、观察、调整；人类控制、透明度和隐私 | Human-Agent Interaction 不应只散落在安全或工作流章节中 |
| [OpenAI Agents SDK：Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) | Tool Approval、中断、状态序列化和恢复 | 人工审批具有独立的运行状态和恢复语义 |
| [OpenAI Agents SDK：Realtime Agents Guide](https://openai.github.io/openai-agents-python/realtime/guide/) | 实时 Session、事件、历史、用户打断、工具、审批和 Handoff | Realtime Agent 具有区别于普通请求响应 Agent 的完整生命周期 |
| [OpenAI Agents SDK：Realtime Transport](https://openai.github.io/openai-agents-python/realtime/transport/) | WebSocket、SIP 和浏览器 WebRTC 的边界 | 实时传输和部署形态需要单独解释 |
| [Anthropic：Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | 跨上下文窗口和跨 Session 的持续执行 | 长任务、交接 Artifact 和恢复属于可靠性与 Harness 的核心问题 |
| [A2A Protocol Specification 0.3.0](https://a2a-protocol.org/v0.3.0/specification/) | Agent Card、Message、Task、Artifact、Streaming、Push Notification | A2A 面向独立 Agent 系统间通信，不应与 MCP 合并讲解 |
| [MCP Specification](https://modelcontextprotocol.io/specification/) | Host、Client、Server、Resources、Prompts、Tools、Sampling | MCP 面向 Agent 应用与外部能力和上下文的连接，和 A2A 的主体不同 |
| [MCP Elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation) | Server 请求用户补充结构化信息 | 协议层也需要处理接受、拒绝、取消和用户控制 |
| [MCP Tasks](https://modelcontextprotocol.io/extensions/tasks/overview) | 异步长任务扩展 | 当前作为实验扩展记录，不写成稳定核心规范 |
| [OpenAI：The Next Evolution of the Agents SDK](https://openai.com/index/the-next-evolution-of-the-agents-sdk/) | Harness、Sandbox、计算环境和长时间任务 | Runtime、Harness、Sandbox 与可靠性需要明确分工 |

## 4. 版本与来源边界

- 新增章节先讲厂商无关的概念和工程边界，具体 SDK 只作为可核验实现。
- Realtime 资料目前主要采用 OpenAI Agents SDK 的公开实现来核对生命周期，不把其类名和传输选择写成行业统一标准。
- A2A 以核验日可访问的 0.3.0 正式规范为依据，写正文时仍须重新检查最新稳定版本。
- MCP Tasks 在核验日属于扩展能力，正文必须保留实验性标记。
- Human-Agent Interaction 同时涉及产品交互、安全和执行状态，但以“人如何控制和纠正 Agent”为独立边界，避免复制 Security 和 Workflow 正文。

## 5. 待正文阶段核验

- Multimodal 与 Realtime Agents 是否需要补充其他厂商的正式实现，用于交叉核对通用机制。
- A2A、MCP 扩展和实时 SDK 在实际写作日期的最新稳定版本。
- Planning 与 Reasoning 章节中的术语是否具有一致定义；无法确认行业统一用法时，应明确来源和适用语境。
