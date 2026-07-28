# Agent Framework

> 本文不寻找一个“最好的 Agent 框架”，而是说明如何用 Runtime/Harness 职责拆解框架、建立硬性门槛、做可比较实验并控制版本锁定。读完后，读者应能判断原生模型 SDK、Agent SDK、图运行时和数据框架分别何时值得引入。

## 面试速记

### 背诵提纲

**1. 定义**

Agent Framework 是把模型适配、Tool、Agent Loop、State、Workflow、Middleware、Tracing 或部署集成封装为可复用 API 的软件库；它实现 Runtime/Harness 的部分或全部职责，但不是 Agent 能力本身。

**2. 主要价值**

框架通过统一接口、成熟集成、状态与编排原语、调试工具和社区生态降低重复开发成本；代价是额外抽象、版本迁移、行为隐藏、依赖体积和供应商锁定。

**3. 常见类型**

- **组件与 Agent Framework**：统一 Model、Tool、Middleware 和常见 Loop。
- **Graph / Workflow Runtime**：强调 State、Node、Edge、Checkpoint 和 Durable Execution。
- **Provider-native Agent SDK**：贴近特定模型和 Harness 的原生 Tool、Session、Guardrail 或 Sandbox 能力。
- **Data / RAG Framework**：强调摄取、索引、检索、Query Engine 与数据型 Agent。

**4. 选择顺序**

先定义任务、风险和运行要求，再以稳定能力做硬性门槛，随后用同一垂直切片完成契约测试、Behavior Eval 和故障测试，最后比较质量、P95、成本、可观测性和迁移代价。

**5. 抽象边界**

业务实体、权限、Artifact 和核心状态应由应用拥有，Framework DTO 留在 Adapter 内；但过度追求统一接口也会抹掉 Provider-native 能力，应保留显式扩展点。

**6. State 与恢复**

不能只检查“支持 Memory/Checkpoint”，还要确认保存边界、并发语义、序列化格式、Schema Migration、未决副作用和旧版本恢复；状态所有权直接决定迁移成本。

**7. 可观测与测试**

框架必须能把 Run、Model、Tool、State 和 Error 映射为应用的稳定事件，并通过 Contract Test 验证取消、超时、HITL、重放和异常，而不是只看 Demo 是否跑通。

**8. 版本管理**

评测和生产都应使用精确版本，跟踪 Changelog 与 Migration Guide，并对 Prompt、Tool Schema、Checkpoint 和 Event Adapter 做回归；`latest` 不是可复现的版本策略。

**9. 学习策略**

先手写最小 Agent Loop，再选择一种与项目最匹配的框架深入 State、Tool、Trace 和失败语义；无需同时学习所有框架，也不要把框架 API 当成底层原理。

### 高频对比

| 类型 | 最强抽象中心 | 适合优先验证的问题 | 常见代价 |
| --- | --- | --- | --- |
| 原生 Model SDK | Request/Response 与 Tool Calling | 调用最少、控制最直接的 Agent | Loop、State、Trace 需自行实现 |
| Agent SDK / Harness | Agent、Runner、Session、Tool、Policy | Provider-native 能力和快速闭环 | Provider/执行语义耦合更强 |
| Graph / Workflow Runtime | State、Node、Edge、Checkpoint | 长任务、HITL、恢复和复杂路径 | 状态建模与迁移成本 |
| Data / RAG Framework | Document、Index、Retriever、Query Engine | 数据摄取、检索与知识型 Agent | 数据抽象和存储集成较重 |

### 高频问题

#### 问题1：什么情况下原生模型 SDK 比 Agent Framework 更合适？

当流程短、工具少、状态和控制要求明确，而且团队愿意维护一个小型 Runtime 时，原生 SDK 的行为更透明、依赖更少。框架只有在集成、持久化、编排或运维能力能抵消其复杂度时才有净收益。

#### 问题2：怎样判断框架抽象已经妨碍调试？

如果无法从 Trace 还原真实模型请求、Tool 参数、State Diff 和停止原因，错误只能靠重跑猜测，或简单行为需要跨多层 Hook 才能修改，抽象就超过了团队可控制范围。应建立源码逃生口、稳定 Adapter 和最小复现。

#### 问题3：框架支持多个模型提供商，是否意味着可以无成本切换？

不意味着。Tool Schema、Structured Output、Reasoning 参数、Streaming Event、缓存、Hosted Tool 和错误语义可能不同；统一接口覆盖的是公共子集，迁移仍需 Provider Contract Test 和任务 Eval。

#### 问题4：框架升级后代码能启动，为什么旧 Run 仍可能无法恢复？

Checkpoint 可能包含旧类名、节点 ID、State Schema、序列化对象或未决 Tool Call。升级测试必须用旧版本生成真实 Checkpoint，再由新版本 Resume，并重新校验权限、幂等和外部现实状态。

#### 问题5：多个框架候选应该怎样公平比较？

固定模型、Prompt、Tool、数据、测试集、并发和预算，用相同应用层事件与指标运行同一垂直切片。先淘汰缺少硬能力者，再保留质量、延迟、成本和可观测性上的 Pareto 候选，而不是编一个主观总分。

---

## 框架是执行机制的实现，不是新的基础原理

前 16 章已经建立 Model、Tool、State、Context、Workflow、Eval、Trace、Runtime 和 Harness。Agent Framework 的作用是把其中一些机制包装为可复用对象和生命周期，使团队不必为每个项目重新实现 Provider Adapter、Tool Schema、Streaming、Checkpoint 或 Trace Export。它缩短工程路径，却没有改变 Agent 的基本循环。

因此理解框架的第一步不是记类名，而是把 API 映射回职责：`Agent` 保存哪些配置，`Runner` 谁控制循环，`State` 何时提交，`Tool` 在哪里校验，`Memory` 是 Session 还是长期存储，`Middleware` 能否改变执行，`Checkpoint` 能恢复到什么边界。一个名称相同的对象，在不同框架里可能承担完全不同的语义。

```text
业务需求
   ↓
Runtime / Harness 职责清单
   ↓
框架 API 映射：谁拥有 State、Loop、Tool、Policy、Event、Compute？
   ↓
硬性能力门槛
   ↓
同一垂直切片 + Contract Test + Eval + Fault Injection
   ↓
选型、ADR、版本锁定与退出方案
```

“不用框架”也不等于没有框架职责。团队仍需维护自己的 Loop、错误处理、事件和升级适配，只是这些代码由应用拥有。真正的比较是自建成本与外部抽象成本，而不是代码行数多少。

## 先按抽象中心分类，再看具体产品

框架经常跨越多个类别，下面的分类只回答其最强抽象中心，不能替代当前版本文档。

LangChain 当前把自身定位为较高层 Agent Framework：提供多 Provider Model Interface、Tool、Structured Output、Agent Loop 和 Middleware；其 `create_agent` 构建在 LangGraph 之上。它适合快速组合模型与工具，并在标准 Loop 周围增加 Summarization、HITL、Retry 或自定义 Middleware。需要验证的是 Provider 特性经统一接口后还保留多少，以及 Middleware 的顺序和失败语义。

LangGraph 是更低层的 Orchestration Runtime，以 State、Node、Edge 和 Checkpoint 为核心。官方当前强调 Durable Execution、Streaming、Human-in-the-loop 和 Persistence，并说明可以独立于 LangChain 使用。它适合执行拓扑与恢复边界本身就是业务问题的系统；代价是团队必须显式建模 State、Reducer、Node Idempotency 和 Migration。

LlamaIndex 的抽象中心是 Context Augmentation。官方文档覆盖 Data Connector、Index、Retriever、Query/Chat Engine、Agent 和 Event-driven Workflow，尤其适合需要完整摄取与检索链的数据型应用。它也能实现普通 Agent Loop 和 Multi-Agent，但选它的充分理由通常应来自数据处理与检索能力，而不是“也有 Agent 类”。

OpenAI Agents SDK 当前提供较少的核心原语，同时集成 Agent Loop、Tools、Handoffs、Guardrails、Sessions、Tracing 和 Sandbox Agent。它贴近 OpenAI Responses 与模型原生能力，也允许应用用 Python 代码控制编排。选择时应核对目标模型、Tool 类型、State 策略和 Sandbox 支持，而不是把 SDK 名称理解为所有 Provider 行为完全一致。

Claude Agent SDK 把 Claude Code 的 Agent Loop、文件与命令工具、Context 管理、Permissions、Hooks、Sessions、Subagents、MCP 和 Skills 作为 Python/TypeScript 库提供。当前文档明确区分在自有进程运行的 Agent SDK 与托管 Agent 服务；二者的 Sandbox、Session State、Custom Tool 和运维所有权不同，不能只按“都是 Claude Agent”合并评估。

| 当前产品 | 文档中的主要抽象中心 | 选型时优先验证 |
| --- | --- | --- |
| LangChain | Model/Tool/Agent/Middleware 组合 | Provider 差异、Middleware、Structured Output |
| LangGraph | Stateful Graph 与 Durable Runtime | Checkpoint、Resume、Node 幂等、State Migration |
| LlamaIndex | Data、Index、Retrieval、Query 与 Workflow | 摄取更新、权限过滤、引用和检索 Eval |
| OpenAI Agents SDK | Provider-native Agent Runtime/Harness | Responses 能力、Guardrail、Handoff、Session、Sandbox |
| Claude Agent SDK | Claude Code Harness as Library | 内置 Tool、Permission、Hook、Session、宿主隔离 |

这个表是阅读入口，不是排名，也不是永久能力矩阵。框架演进很快；某个功能在今天可能是 Stable、Preview、外部集成或只存在于托管产品中，必须把版本、运行形态和来源一起记录。

## 用硬性门槛淘汰，而不是先做主观打分

选型应先从业务约束推导不可妥协的能力。例如一个需要跨天审批的支付 Agent，Hard Requirement 可能包括持久 Checkpoint、精确 Tool Approval、应用拥有 Identity、旧状态恢复和完整 Audit Event；一个只读知识助手则可能优先数据摄取、权限过滤、引用和检索 Eval。

每项能力至少记录四种状态：Stable、Experimental、External Integration 和 Missing。把 Preview 当成“支持”会把发布风险藏起来；把需要额外托管服务的能力当成本地库内置，也会误判数据与运维边界。硬性门槛未通过的候选直接淘汰，不应靠社区热度或其他加分抵消。

随后再比较软性取舍：开发速度、API 清晰度、文档、调试可见性、依赖大小、人才供给和生态集成。软性指标可以作为讨论证据，但不宜压成一个失去解释力的总分。成功率更高但更贵，与便宜但稍慢，可能都是合理的 Pareto Candidate，最终选择取决于产品 SLO 和价值。

```text
Hard Gate：稳定能力、数据边界、身份、许可证、运行环境
   ↓ 通过
Contract Gate：Tool、Event、Cancel、Resume、Error 是否满足应用契约
   ↓ 通过
Behavior Gate：固定测试集上的任务质量与安全
   ↓ 通过
Operational Gate：P95、成本、恢复、部署、升级和可观测
```

## 同一垂直切片比功能清单更可信

框架官网的 Feature List 只能生成候选，不能证明适用于你的系统。应挑一条包含真实困难的垂直切片，例如：读取有权限的数据，调用一个有副作用的 Tool，在审批点暂停，跨进程恢复，产生带引用 Artifact，并在 Trace 中重建完整路径。所有候选使用相同模型版本、Prompt、Tool Schema、数据、并发、预算和 Eval Case。

测试分为三层。Contract Test 检查框架 Adapter 是否保留 Tool Call ID、Stop Reason、Usage、Cancellation、Error Category、State Version 和 Event Order；Behavior Eval 检查真实任务成功、事实与安全；Fault Test 主动注入 Timeout、重复 Event、进程重启、旧 Checkpoint 和部分 Tool Failure。只跑 Happy-path Demo 无法揭示 Framework 的运行语义。

比较时记录成功率分布而非几个“看起来不错”的输出，并至少包含 P50/P95、Token、Tool Call、外部费用和 Trace Completeness。框架默认 Prompt、自动 Retry、History Merge 或并行策略都会改变成本与行为，应显式记录，否则候选并不在同一实验条件下。

## 多 Provider Interface 只覆盖公共子集

统一 Model Adapter 很有价值：应用可以共享基础 Message、Tool 和 Usage 处理，也更容易运行 A/B Test。但 Provider 的 Tool Result 关联、Structured Output、Reasoning Control、Prompt Cache、Hosted Tool、Multimodal Block、Streaming Event 和错误码并不完全相同。

如果业务只依赖公共子集，统一接口能降低切换成本；如果系统依赖某个 Provider-native Computer Use、Sandbox 或缓存语义，把它强行塞进最低公共接口会丢失能力或产生错误抽象。更稳妥的 Adapter 同时提供稳定 Core Contract 和显式 Capability/Extension：调用方先检测能力，再使用有版本的 Provider Extension。

“模型名换一下就完成迁移”只能证明代码能够发出请求。真正迁移需要用相同任务集重跑 Tool Selection、参数、Stop Reason、Structured Output、上下文预算、Safety 和 Cost，并检查用户可见结果与外部副作用。

## 业务状态与 Framework State 之间需要防腐层

框架对象直接进入数据库和 Domain Model，原型阶段最省事，升级时最昂贵。Checkpoint 可能序列化 Class Path、Node Name、Provider Item 或内部 Message 类型；框架改名或 State Schema 变化后，即使应用代码能启动，旧 Run 也可能无法加载。

应用应拥有业务真相，例如订单状态、审批决定、Artifact Metadata 和权限；Framework Checkpoint 作为带版本的执行快照，通过 Opaque Reference 关联。Adapter 负责把 Framework Event 归一为应用的 Canonical Event，把最终结果转成 Domain DTO。不要在每个业务模块散落框架类型。

```text
Domain Service ── Stable Port ── Framework Adapter ── Framework Runtime
      │                                      │
      ├── Canonical Run / Artifact / Policy  └── Opaque Checkpoint
      └── Canonical Event Store  ← Event Normalizer ← Vendor Events
```

防腐层不是承诺零迁移。它隔离常见变化，让团队清楚哪些能力属于公共契约，哪些是 Framework Extension。过度包装到所有 Tool、Message 和 Event 都只剩字符串，同样会损失类型和诊断信息。

## 可观测性必须能穿透抽象

至少应能从应用 Run ID 追到 Framework Run/Thread、Model Request、Tool Call、State Diff、Retry、Handoff、Checkpoint 和 Final Result。敏感内容可以脱敏或不采集，但关联关系和状态原因不能消失。框架提供漂亮 UI 并不等于数据可以导出、长期保留或与现有 OpenTelemetry/SIEM 关联。

Middleware 和 Hook 的可组合性也要测试。两个组件都修改 Model Input 时谁先执行；Retry 是否重复 Audit Side Effect；HITL 是否覆盖 Subagent Tool；异常是被格式化给模型还是抛给应用。这些问题需要读文档、查源码并用 Contract Test 固化，不能从类型签名推断。

当错误只能在框架内部重现时，应保留 Escape Hatch：输出原始 Provider Request/Response 的安全副本，支持最小化复现，必要时绕过高层 Agent API 调用下层 Model Adapter。团队如果没有人能读懂关键 Runtime 路径，就不真正拥有这个系统。

## 升级测试包含正在运行的历史状态

精确 Pin 版本是可复现的起点，不是停止升级。团队应订阅 Release Note 和 Security Advisory，记录 Framework、Provider SDK、Model、Prompt、Tool Schema、State Schema 和 Event Adapter 的兼容矩阵。实验性能力单独开关，不能在库升级后静默变成新默认。

升级流水线至少包含：新旧版本 Behavior Regression；旧版本写入的 Checkpoint 由新版本 Resume；新版本能否回滚并读取仍在运行的旧状态；Streaming/Event Schema 是否改变；Tool Approval 和 Guardrail 是否仍覆盖同一范围。长任务可以让旧 Worker 继续完成，新任务再逐步切流，避免在执行中替换语义。

退出方案也应在采用时设计：应用数据能否导出，Checkpoint 是否可迁移，Trace 是否使用开放格式，Tool 和 Prompt 是否独立存储，托管服务终止后如何恢复。Lock-in 不一定不可接受，但必须与节省的工程成本一起显式决策。

## 学习框架的目标是读懂取舍

初学者先用原生 API 手写一次 Tool Loop，才能识别框架替自己做了什么。之后选择一种与项目最贴近的路径深入：普通工具型 Agent 可以学习 Agent SDK 或 LangChain；需要状态图和 HITL 可深入 LangGraph；数据摄取与复杂 RAG 可深入 LlamaIndex；需要现成编码工作环境则评估 Provider-native Harness。

学习时不要只复刻 Quickstart。应跟踪一次真实 Run 的 Model Input、Tool Call、State、Checkpoint、Event 和 Error，修改默认停止条件，注入 Tool Failure，再解释恢复结果。能回答“默认值是什么、状态在哪里、失败后会怎样、如何替换”才算理解框架。

生产项目通常只需要一套主要 Runtime/Framework，再通过清晰 Adapter 接少量专用组件。把多个拥有重叠 State、Message 和 Trace 抽象的框架层层嵌套，会让所有权和故障边界更模糊。

## 最小实现演示可复现选型

本章示例 [`framework_selection.py`](../../examples/17-agent-framework/framework_selection.py) 不安装任何候选框架，而是实现选型时应由应用拥有的门禁。`FrameworkProfile` 要求精确 `version_pin`，每项 Capability 标为 Stable、Experimental 或 Missing；Policy 可以要求 Application-owned State 和 Portable Checkpoint。

通过硬门槛后，`BenchmarkResult` 才进入同一 Suite 的比较。代码不生成单一总分，而是移除在成功率、P95、成本和 Trace Completeness 上被严格支配的候选：

```python
no_worse = (
    left.success_rate >= right.success_rate
    and left.p95_latency_ms <= right.p95_latency_ms
    and left.mean_cost <= right.mean_cost
    and left.trace_completeness >= right.trace_completeness
)
```

示例还提供 Versioned `EventAdapter`，把已知 Framework Event 映射为 Canonical Event；Schema Version 或 Kind 未映射时直接失败，避免升级后悄悄丢 Trace。13 项测试覆盖 Stable/Experimental/Missing Gate、Release Channel、State Ownership、Checkpoint Portability、精确版本、Benchmark Threshold、Pareto Trade-off 和 Event Schema Drift。

它没有替代真实 Spike：Profile 中“Stable”的结论必须来自当前官方文档和 Contract Test，Benchmark 也必须使用业务数据。示例的价值是让选择理由可审计、可重跑，而不是给所有团队一套固定权重。

## 参考资料

- [Frameworks, runtimes, and harnesses](https://docs.langchain.com/oss/python/concepts/products)，LangChain 官方概念文档；用于核对 Agent Framework、Runtime 与 Harness 的分层，以及 LangChain、LangGraph 和 Deep Agents 当前关系；最后核验日期：2026-07-23。
- [Agents](https://docs.langchain.com/oss/python/langchain/agents)，LangChain 官方文档；用于核对 Model、Tool、Structured Output、State 和 Middleware 组成的当前 Agent API，以及 `create_agent` 构建在 LangGraph 上；最后核验日期：2026-07-23。
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)，LangGraph 官方文档；用于核对低层 Stateful Orchestration Runtime、Durable Execution、Streaming、HITL、Persistence 及可独立使用的边界；最后核验日期：2026-07-23。
- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)，LangGraph 官方文档；用于核对 Thread、Checkpoint、Super-step、Pending Write 和恢复语义，说明“支持持久化”仍需检查具体边界；最后核验日期：2026-07-23。
- [Welcome to LlamaIndex](https://developers.llamaindex.ai/python/framework/)，LlamaIndex 官方文档；用于核对 Context Augmentation、Data Connector、Index、Query Engine、Agent 与 Event-driven Workflow 的抽象中心；最后核验日期：2026-07-23。
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)，OpenAI Agents SDK 官方文档；用于核对 Agent Loop、Tools、Handoffs、Guardrails、Tracing、Sessions 和 Sandbox Agent 的当前能力边界；最后核验日期：2026-07-23。
- [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)，Anthropic Claude Code 官方文档；用于核对 Claude Agent SDK 的内置 Tool、Hooks、Subagents、MCP、Permissions、Sessions，以及自托管 SDK 与 Managed Agents 的所有权区别；最后核验日期：2026-07-23。
