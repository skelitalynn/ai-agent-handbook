# Runtime 与 Harness

> 本文建立 Agent 的执行底座：Runtime 怎样把模型输出变成受控状态转换，Harness 又怎样把 Runtime、工具、Workspace、Sandbox、指令和反馈回路装配成适合某类任务的工作环境。前文已经逐个解释这些组件；本章把它们组合起来，并为下一章评价 Agent Framework 建立判断基准。

## 面试速记

### 背诵提纲

**1. Runtime**

Agent Runtime 是执行 Agent Loop 的权威控制层，负责模型调用、输出解析、工具调度、状态转换、终止、预算、权限和事件；模型只提出候选输出或动作，Runtime 决定能否执行。

**2. Harness**

Agent Harness 是围绕 Runtime 装配的任务工作环境，通常组合模型适配、工具、指令、Context 策略、Workspace、Sandbox、Artifact、Hooks 和验证反馈；它是工程术语，不同产品的边界并不完全一致。

**3. 完整链路**

创建 Run → 准备 Workspace 与本地依赖 → 构建 Model Context → 调用模型 → 校验输出 → 执行或拒绝 Tool → 写回 State 与 Artifact → 发出事件 → 继续、暂停、失败或结束。

**4. 三类上下文**

- **Run State**：Runtime 持久化的事实、状态和预算。
- **Local Context**：工具与 Hook 使用的依赖、身份和连接，不自动发送给模型。
- **Model Context**：本轮选择后交给模型的有限输入。

**5. Lifecycle 与 Hooks**

Lifecycle 定义 Run、Model、Tool、Handoff 和 Artifact 的状态与事件顺序；Hook 可以观察、扩展或拦截这些事件，但安全策略必须由 Runtime 明确强制，并定义 Hook 失败、重放和超时语义。

**6. Workspace 与 Artifact**

Workspace 是任务期间可读写的受控工作集，Artifact 是带来源、版本和内容摘要的持久产物；Workspace 中的临时文件不会自动成为可信输出。

**7. Sandbox**

Sandbox 是限制代码或工具执行的计算安全边界，需要约束文件系统、网络、进程、凭证和资源；路径白名单或临时目录只是 Workspace Policy，不能单独等同于 Sandbox。

**8. 长任务与恢复**

Runtime 应把 Checkpoint 和 Artifact 外部化，使进程或 Sandbox 丢失后仍可恢复；Harness 还应提供计划、进度、验证命令和清理后的交接状态，单靠 Context Compaction 不足以保证连续工作。

**9. 工程判断**

评价 Harness 要同时测任务成功、模型与工具调用、上下文利用、权限违规、恢复、延迟和成本，并与同一模型的简化 Harness 做消融；Framework 只是实现这些职责的一种代码封装。

### 高频对比

| 对象 | 主要职责 | 是否拥有执行权限 | 常见变化原因 |
| --- | --- | --- | --- |
| Runtime | 执行循环、状态、策略、预算和事件 | 是 | 可靠性、安全或运行语义变化 |
| Harness | 为一类任务装配 Runtime、环境、工具和反馈 | 通过 Runtime | 任务形态、模型能力或工作方式变化 |
| Framework / SDK | 提供可复用 API、抽象和集成 | 取决于具体实现 | 生态、版本和供应商变化 |
| Application | 定义用户目标、业务规则和产品交互 | 通过业务服务与 Runtime | 产品需求和组织政策变化 |

### 高频问题

#### 问题1：为什么 `before_tool` Hook 不能天然视为安全边界？

Hook 可能被漏注册、超时、抛错、重放或只覆盖部分 Tool 类型。安全授权应由不可绕过的 Tool Executor 或 Policy Gate 强制并默认拒绝，Hook 更适合审计、指标和可替换扩展。

#### 问题2：已经限制 Agent 只能访问某个目录，为什么仍不能称为 Sandbox？

目录限制只控制一部分路径，进程仍可能访问网络、环境变量、系统调用、其他进程或耗尽资源。Sandbox 需要在模型生成代码之外建立文件、网络、身份、进程和资源的组合隔离。

#### 问题3：模型没有变化，Agent 效果为什么会因 Harness 改动明显变化？

Harness 决定模型看见什么、有哪些动作、如何收到工具反馈、何时验证和怎样跨窗口继续。错误的工具接口、陈旧指令、缺失环境反馈或不稳定交接，都可能让同一模型沿完全不同的轨迹执行。

#### 问题4：长任务恢复时，为什么不能只保存聊天历史？

聊天历史没有完整表示外部副作用、Workspace 版本、未决审批、预算和代码版本。恢复需要权威 Run State、Checkpoint、Artifact、环境快照或重建清单，并在继续前重新校验兼容性和现实状态。

#### 问题5：怎样判断一项 Harness 能力应该进入核心 Runtime 还是普通 Hook？

凡是影响授权、状态正确性、幂等、预算和终止的不变量，应进入 Runtime 的强制路径；可观察、通知和非关键派生信息可放在 Hook。还要明确 Hook 失败时是忽略、重试、降级还是让 Run 失败。

---

## Runtime 是执行权威，不只是一个循环函数

第 04 章用最小循环说明了 Agent 如何在模型与工具之间往返。真正的 Runtime 要把这个循环变成有身份、有状态、有预算、可观察且能停止的执行过程。它不是某个 Python 进程的同义词，也不一定负责部署；它描述的是“谁有权把候选决策变成系统状态和外部动作”。

模型可以返回最终文本、结构化对象、Tool Call 或 Handoff，但这些都只是提议。Runtime 需要解析并验证输出，查找真实 Tool，应用身份和参数策略，管理并发与超时，记录结果，再判断下一步。若模型请求了未注册工具、参数不合法或预算已耗尽，Runtime 应拒绝或失败，而不是让模型用自然语言说服执行层。

```text
Application / API
        ↓ 目标、用户身份、业务策略
┌──────────────────── Harness ────────────────────┐
│ Instructions  Context Builder  Tools  Workspace │
│ Hooks         Artifact Store   Sandbox Adapter  │
│                       ↓                         │
│              ┌────── Runtime ──────┐            │
│              │ State / Loop / Budget│            │
│              │ Policy / Executor    │            │
│              │ Lifecycle / Events   │            │
│              └───────┬───────┬──────┘            │
└──────────────────────┼───────┼───────────────────┘
                       ↓       ↓
                    Model    Isolated Compute / External Systems
```

Runtime 最重要的性质是所有关键状态转换经过同一权威路径。工具不能在模型输出一出现就自行执行，UI 不能只凭 Token 流把 Run 标记完成，Observer 也不能通过修改日志事件给动作授权。集中不代表所有代码必须在一个进程，而是 Policy、State Transition 和 Execution Result 必须有一致语义。

## Harness 把模型放进能完成任务的环境

“Agent Harness”目前是一个广泛使用但没有单一协议定义的工程术语。狭义 Harness 可能只指 Agent Loop 和 Tool Adapter；广义 Harness 还包含 Workspace、Sandbox、Skills、指令文件、Session、Subagent、Trace 和部署适配。本文采用后一种但保持边界：Runtime 是其中具有执行权威的内核，Harness 是把内核与工作环境装配起来的组合层。

一个 Coding Harness 可能提供代码搜索、文件编辑、Shell、Git、测试命令和隔离工作树；研究 Harness 可能提供搜索、浏览、引用提取和报告 Artifact；客服 Harness 则需要客户身份、知识检索、订单工具、审批和工单状态。三者可以复用同一 Runtime，但有效的 Context、工具和验证回路不同。

Harness 与 Prompt 的差异在于，它不只告诉模型“应该怎么做”，还改变模型能观察和行动的环境。例如把测试结果作为 Tool Observation 写回、在文件编辑后强制运行结构检查、只挂载任务需要的数据、为长任务保留进度 Artifact，都是可执行的反馈结构，而不是一句建议。

Framework 和 SDK 留到第 17 章讨论。它们是实现和分发 Runtime/Harness 能力的代码产品；一个 Framework 可能自带完整 Runner，也可能只提供图编排或模型适配。不能因为安装了某个包，就认为 Runtime 所需职责已经完整实现。

## 一次 Run 是明确的状态机和事件序列

Runtime 通常从 `Created` 进入 `Running`，随后在模型和工具之间产生多个步骤，最后到达 `Completed`、`Failed` 或 `Cancelled`；需要人工输入或外部事件时进入可持久化的 `Paused`。Terminal State 不应被普通重试直接改回 Running，新尝试应有独立 Attempt 或显式恢复语义。

```text
Created
   ↓ validate + prepare
Running ──需要外部决定──→ Paused ──resume + revalidate──→ Running
   │                          │
   ├── final output ───────→ Completed
   ├── error / budget ─────→ Failed
   └── cancel observed ────→ Cancelled
```

每轮至少包含 `model.started`、`model.completed`，工具路径再包含 `tool.requested`、`tool.started`、`tool.completed` 或 `tool.failed`。事件必须携带 Run/Step/Tool Call 等关联标识，并保证单 Run 内可重建顺序。分布式传输常只能提供 At-least-once Delivery，Consumer 应用 Event ID 去重，不能假设 Hook 永远只执行一次。

OpenAI Agents SDK 当前也把 Runner Loop、Run/Agent Hooks、Model/Tool/Handoff 生命周期和 Run Context 分开暴露。具体回调名会随 SDK 发展，但底层判断稳定：状态转换属于执行器，Lifecycle Event 是扩展和观察接口。

## State、Local Context 和 Model Context 不能混为一份字典

Run State 是恢复和审计所需的权威事实，例如当前步骤、消息项、未决 Tool Call、预算、Approval、Artifact Reference 和版本。它通常需要持久化，并有明确 Schema。把数据库连接、Logger 或 API Client 塞进 State 会使序列化和恢复失去边界。

Local Context 是 Runtime 进程内提供给 Tool、Policy 和 Hook 的依赖注入对象，可以包含当前用户 ID、Logger、数据库访问器或短期 Credential Handle。它不应自动进入模型输入。OpenAI Agents SDK 的 Context 文档也明确区分本地 `RunContextWrapper` 与发送给 LLM 的 Conversation Context。

Model Context 是 Context Builder 从 State、历史、检索、Memory 和 Artifact 中选择的本轮视图。模型不需要、也不应该看到所有本地依赖。把三者分开，既能控制 Token，也能避免 Secret 因“方便共享 Context”而进入 Prompt、Trace 或第三方模型。

| 数据 | 权威保存位置 | 默认给模型看 | 典型内容 |
| --- | --- | --- | --- |
| Run State | Checkpoint / State Store | 经过选择后部分可见 | 状态、步骤、预算、未决动作 |
| Local Context | Runtime 依赖容器 | 否 | 用户身份、Client、Logger、Secret Handle |
| Model Context | 本轮模型请求 | 是 | 指令、消息、相关证据、工具 Schema |
| Artifact | Artifact Store | 只传引用或所需内容 | 文件、报告、图片、数据和验证结果 |

## Hook 应按观察、变换和强制策略分类

Hook 是 Lifecycle 上的扩展点，但“能在工具前运行”不表示它天然不可绕过。工程上至少区分三类：Observer 只记录 Trace、指标和通知；Transformer 可以裁剪 Context、格式化 Tool Result 或生成派生 Artifact；Policy Gate 决定请求是否允许执行。第三类必须进入 Runtime 的强制路径、默认拒绝，并覆盖所有等价执行通道。

Hook 设计需要回答以下问题：同一个事件在 Retry 或恢复后是否重放；多个 Hook 的顺序是否稳定；Hook 超时或抛错时是忽略、重试还是 Fail Closed；Hook 能否修改输入；副作用是否幂等；敏感字段是否会进入日志。没有这些语义，Lifecycle API 只是回调列表。

对于日志和指标，通常允许 Observer 失败后记录诊断而不改变业务结果；对于授权和参数校验，检查失败必须阻止工具。不要把二者放入一个“任何 Hook 异常都忽略”或“任何 Hook 异常都终止”的全局策略。

## Workspace、Artifact 和 Sandbox 分别解决可操作性、交付与隔离

Workspace 是 Agent 本次任务可以导航的文件或对象视图。一个 Manifest 可以把只读输入挂载到 `inputs/`，把临时工作放到 `work/`，把候选交付物写到 `outputs/`。稳定路径和清晰目录能降低模型搜索成本，但路径校验只是应用策略。

Artifact 是从 Workspace 或工具结果中提升出来的持久产物。发布时应记录 Run、来源 Step、版本、Media Type、内容摘要、验证状态和访问控制。`outputs/report.md` 存在不代表它已经发布；Runtime 应在 Tool 完成后验证路径与内容，再写入独立 Artifact Store。后续 Agent 最好通过不可变 ID 读取，避免同名文件被静默覆盖。

Sandbox 是运行不可信或模型生成操作的隔离计算环境。有效边界至少考虑：

- 允许读写的文件和挂载方式；
- 网络默认关闭、Allowlist 或受控代理，以及 DNS/重定向后的真实去向；
- 进程、系统调用、子进程和宿主接口；
- CPU、内存、磁盘、进程数和执行时间；
- Credential 是否留在 Sandbox 外，由受控 Broker 代表调用；
- Snapshot、销毁、恶意 Artifact 和审计策略。

容器可以是 Sandbox 的实现部件，但默认容器配置不是安全结论。反过来，内存中的虚拟 Workspace 可以很好地测试 Path Policy，却没有隔离任意代码执行。OpenAI 在 2026 年更新 Agents SDK 时也明确把 Harness 与 Compute 分离：状态外部化便于恢复，Credential 留在执行环境之外可以缩小 Prompt Injection 和 Exfiltration 的影响面。

## 长任务需要环境交接，而不只是更多上下文

Context Compaction 能压缩历史，但会丢失细节，也无法代表文件系统、外部副作用和验证状态。Anthropic 的长任务 Harness 实验使用首轮 Initializer 建立 Feature List 和环境，后续 Session 每次只推进有限工作，并通过 Git、Progress File 和端到端测试把干净状态交给下一轮。这里可泛化的结论不是必须使用这些文件名，而是连续工作依赖外部可检查的 Artifact 和恢复协议。

恢复流程应先重新定位环境：读取 Checkpoint 和计划，检查 Workspace/Artifact 版本，确认已发生的外部效果，运行轻量 Smoke Test，再选择下一项工作。若 Agent、Prompt、Tool Schema 或 Runtime 已升级，应保存版本标记并经过迁移；不能把旧的未决 Tool Call 直接交给新代码执行。

Harness 也应控制知识入口。OpenAI 的 Harness Engineering 案例把短 `AGENTS.md` 作为地图，把详细知识放在可索引、版本化且可机械检查的仓库文档中。对任意领域都适用的原则是 Progressive Disclosure：先给稳定导航，再按任务加载权威细节，而不是把整本手册塞入每轮 Prompt。

## Harness 的质量必须与模型分开测量

一个强模型可能掩盖 Harness 的工具或上下文缺陷，直到模型升级、任务变长或环境异常。评测矩阵至少要交叉 Model Version 与 Harness Version，并保留同一任务集；否则无法判断提升来自模型、更多 Token、工具变化还是执行结构。

除了最终成功率，还应记录 Context 中无关信息比例、Tool Selection 与参数错误、Policy Denial、Workspace Escape 尝试、Artifact Contract、Step/Token/Tool Budget、Pause/Resume、Observer 丢失、Sandbox 重建和取消响应。长任务还需要从 Checkpoint 故障注入，验证新进程或新 Sandbox 能否恢复到一致状态。

消融实验很重要：去掉 Progress Artifact、换回全量 Context、关闭强制测试或把特定 Tool 改成普通函数，观察质量、成本和失败类型。只有能说明某个 Harness 机制解决了什么失败，并有回归测试保护，它才不是不断堆积的脚手架。

## 最小实现把职责边界写成不变量

本章示例 [`runtime_harness.py`](../../examples/16-runtime-harness/runtime_harness.py) 使用 Python 标准库实现一个可暂停的 Runtime。`Harness` 只负责装配 Model、Tools、Policy、Workspace、Artifact Store、Observer 和 Local Context；`Runtime` 持有状态转换和执行权。

模型收到的 `ModelRequest` 只有 Goal、Step、Observation 和 Allowed Tool Name，本地 `api_key` 等依赖只在 `ToolContext` 中可见。Tool Call 先经过 Runtime Policy，再进入真实 Handler；Observer 收到不可变 Event，即使 Observer 抛错也只记录诊断，不能修改授权。

虚拟 Workspace 通过 Mount 和路径规范化验证只读输入、可写工作区与输出区。它故意不声称是操作系统 Sandbox。只有 `outputs/` 下的文件可以提升为带 SHA-256 和来源 Step 的 Artifact：

```python
if normalized.parts[0] != policy.publish_mount:
    raise RuntimeViolation("artifact path is outside publish mount")

artifact = artifacts.publish(run_id, path, content, source_step)
```

13 项测试覆盖 Lifecycle 顺序、未授权工具、最大步骤、取消、路径逃逸、只读 Mount、Local/Model Context 隔离、Artifact 身份与发布范围、暂停序列化恢复、Observer 失败和事件不可变性。示例没有隔离真实进程或网络，也没有实现数据库 Checkpoint、并发 Tool、Credential Broker 和分布式 Event Bus；这些限制正是 Workspace Policy 与生产 Sandbox/Runtime 的边界。

## 参考资料

- [Running agents](https://openai.github.io/openai-agents-python/running_agents/)，OpenAI Agents SDK 官方文档；用于核对 Runner Loop、Streaming、状态延续、最大轮次、异常和 Durable Execution 集成的当前语义；最后核验日期：2026-07-23。
- [Context management](https://openai.github.io/openai-agents-python/context/)，OpenAI Agents SDK 官方文档；用于核对 Local Context 与发送给 LLM 的 Context 不同，以及 Tool、Hook、Usage 和序列化状态的边界；最后核验日期：2026-07-23。
- [Lifecycle](https://openai.github.io/openai-agents-python/ref/lifecycle/)，OpenAI Agents SDK API Reference；用于核对 Run/Agent Scope 下 Model、Tool、Agent 与 Handoff Hook 的事件位置；最后核验日期：2026-07-23。
- [The next evolution of the Agents SDK](https://openai.com/index/the-next-evolution-of-the-agents-sdk/)，OpenAI 官方产品文章，2026-04-15；用于核对 Harness、Workspace Manifest、Native Sandbox，以及 Harness/Compute 分离对 Credential、Durability 和 Scale 的作用；最后核验日期：2026-07-23。
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)，Anthropic Engineering，2025-11-26；用于核对跨 Context Window 的 Initializer、Feature List、增量工作、Progress Artifact、干净交接和端到端验证；最后核验日期：2026-07-23。
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)，OpenAI Engineering，2026-02-11；用于核对仓库知识作为事实源、短导航与 Progressive Disclosure、机械约束、计划 Artifact 和环境反馈回路；最后核验日期：2026-07-23。
