# Workflow 与 Orchestration

> 本文讨论如何把模型调用、工具、副作用和人工审批组织成可恢复的长任务。它承接第 12 章的决策控制：模型可以提议下一步，但 Workflow 定义业务路径，Orchestrator 负责持久化状态、调度执行并处理失败；第 14、15 章将在此基础上加入人机协作和多 Agent 分工。

## 面试速记

### 背诵提纲

**1. 定义**

Workflow 是步骤、依赖和转移规则构成的执行定义；Orchestration 是根据持久状态和事件推进每个 Workflow Run 的运行时控制过程。

**2. 核心对象**

- **State**：记录继续执行所需的业务数据、进度、预算、审批和失败状态。
- **Node、Edge 与 Event**：Node 承载计算或副作用，Edge 表示依赖或转移，Event 记录已经发生的事实。
- **Definition 与 Run**：Definition 是带版本的流程模板，Run 是一次拥有独立状态和身份的执行实例。

**3. 基本组合模式**

- **Sequential**：后一步依赖前一步结果，必须顺序执行。
- **Parallel**：无数据依赖和共享状态冲突的分支可以并发，并在汇合点聚合结果。
- **Routing 与 Conditional**：根据输入类别或当前状态选择后续分支，路由是条件分支的一种常见用途。

**4. 动态组合模式**

- **Orchestrator-Workers**：Orchestrator 动态拆分未知子任务，Worker 执行后再聚合结果。
- **Evaluator-Optimizer**：Generator 与 Evaluator 按明确标准迭代，但必须有通过条件、轮数和成本上限。

**5. 三种执行表示**

DAG 适合无环依赖，状态机适合循环、等待和显式生命周期，事件驱动编排适合跨服务异步协作；生产系统常组合使用三者。

**6. 持久执行**

Checkpoint 或事件历史把进度写入持久存储，使进程退出后能够 Replay 或从安全边界 Resume；已记录结果应复用，LLM、网络和文件 I/O 等非确定性操作应作为外部 Activity 隔离。

**7. 失败控制**

Timeout 限制等待，Cancellation 请求停止，Retry 处理可恢复失败，幂等键防止重试重复副作用，Compensation 用业务语义修正已经提交的效果；这些机制不能互相替代。

**8. 暂停与并发**

人工审批应建模为持久化的 Pause 状态和带身份的决定事件；并行分支还需限制 Fan-out、外部限流和共享状态写冲突，并采用确定性聚合或并发控制。

**9. 选型原则**

固定且短的路径用普通代码，独立后台任务用任务队列，跨进程长任务用持久工作流引擎；只有路径确实需要模型动态决定时，才在受控 Node 中引入 Agent 或 Agent Workflow 框架。

### 高频对比

| 方案 | 主要解决的问题 | 自带的流程状态 | 典型适用场景 |
| --- | --- | --- | --- |
| 普通代码 | 单进程内控制流 | 通常没有 | 短、固定、失败后可整体重来 |
| 任务队列 | 异步投递、削峰和 Worker 扩缩 | 通常只到消息与 Ack | 相互独立的后台任务 |
| 持久工作流引擎 | 跨进程状态、Timer、恢复和补偿 | 有 | 长时间、多步骤、必须恢复的业务流程 |
| Agent Workflow 框架 | 模型驱动节点与受控编排结合 | 视框架和存储配置而定 | 路径部分动态且需要工具、审批或 Agent Loop |

### 高频问题

#### 问题1：为什么保存 Checkpoint 仍不能保证工具副作用只发生一次？

进程可能在工具已经成功、但完成事件尚未持久化的窗口崩溃，恢复后只能重新投递。应向下游传递稳定的幂等键或执行对账，不能把 Checkpoint 当成端到端 Exactly-once 保证。

#### 问题2：为什么有任务队列还可能需要持久工作流引擎？

队列主要保存待处理消息及其投递状态，不一定知道多步骤业务已经完成到哪里、正在等待什么、该如何补偿。工作流引擎在队列之上维护 Run、状态转移、Timer、依赖和恢复语义。

#### 问题3：什么时候多个节点可以安全并行？

节点之间没有数据依赖，写入不会相互覆盖，副作用的顺序不构成业务约束，而且外部限流与聚合规则明确时才适合并行。并行会缩短关键路径，但会增加瞬时负载、竞争和部分失败处理成本。

#### 问题4：长时间运行的 Workflow 如何安全升级代码？

Run 必须绑定定义版本，旧事件在新代码下仍需产生兼容的决策；常见方案是旧 Worker 继续服务旧版本、使用显式版本分支，或在受控迁移后切换。直接修改已运行路径可能让 Replay 与历史不一致。

#### 问题5：取消一个已经部分成功的 Workflow 应该怎么做？

取消通常是协作式状态转移，不代表瞬间撤销已发生的外部效果。系统应停止派发新工作，等待或终止可取消的 Activity，再按业务规则执行补偿；补偿失败必须进入可观察、可重试或人工修复的状态。

---

## Workflow 固定执行边界，Orchestration 推进执行实例

第 12 章解决“下一步行动如何选择”，本章解决“选择之后怎样可靠地运行”。两者的分界很重要：模型可以判断一封工单属于退款还是技术支持，但只有运行时才能强制检查权限、写入状态、控制重试，并保证进程重启后仍知道这张工单已经执行到哪一步。

Workflow 是定义，不是某一次函数调用。它描述有哪些步骤、步骤依赖什么、在哪些条件下转移以及完成和失败分别意味着什么。Orchestration 则是运行时职责：创建一次 Run，读取当前状态，选择可执行节点，把任务派给 Worker，接收结果，写入事件，然后决定继续、暂停、补偿还是终止。

Anthropic 在其工程分类中把预定义代码路径称为 Workflow，把由模型动态控制过程和工具使用的系统称为 Agent。这个区分描述的是**路径控制权**，不是技术栈：Workflow 可以包含 LLM Node，Agent Loop 也可以作为 Workflow 的一个 Node；Orchestrator-Workers 中的 Orchestrator 甚至可以由模型动态生成子任务，但并发上限、权限和完成条件仍由外层代码执行。

```text
Workflow Definition（带版本）
   │  节点、依赖、转移、策略
   ↓
Orchestrator ──────→ 持久状态 / 事件历史
   │                       ↑
   ├── 派发 Activity ─→ Worker ─→ 外部系统
   │
   └── 暂停 ─→ 人工审批 ─→ 决定事件 ─→ 恢复
```

图中需要观察的是两个边界：Orchestrator 管理**执行控制**，外部 Activity 产生**真实副作用**；持久化 Run 状态连接两者，但不能自动把两个系统合并成一个原子事务。

## Run 是不断演化的业务状态，不是函数调用栈

可靠编排首先需要明确几个对象。

**Workflow Definition** 是流程模板，至少包含定义版本、Node、Edge 和每个节点的执行策略。**Workflow Run** 是模板的一次实例，应有稳定的 `workflow_id` 或 `run_id`。同一个订单流程可以同时有成千上万个 Run，每个 Run 的输入、当前节点、审批和失败记录彼此独立。

**State** 只保存恢复和决策真正需要的事实，例如输入、已完成步骤、结构化输出、预算、审批状态与错误分类。把整个 Python 对象图、数据库连接或未序列化的 SDK 对象塞进 State，会让跨进程恢复和版本迁移失去基础。消息历史可以是 State 的一部分，但 State 不等于聊天记录。

**Node** 是一次有边界的计算。纯计算 Node 可以根据 State 产生新 State；模型、HTTP、数据库和文件操作等外部 I/O 通常作为 Activity Node。**Edge** 表示下一步的依赖或转移条件。**Event** 是已经发生且不可随意改写的事实，例如 `PaymentRequested`、`PaymentCompleted` 或 `ApprovalRejected`；命令则是希望发生的动作，两者不能混为一谈。

一次推进可以抽象为：

```text
读取 Run 状态
   ↓
找出满足依赖的 Node
   ↓
记录派发意图 / 创建任务
   ↓
Worker 执行 Activity
   ↓
校验并持久化结果事件
   ↓
归约出新状态 → 继续 / 暂停 / 完成 / 失败 / 补偿
```

“先执行再记录”与“先记录再执行”都会留下崩溃窗口。成熟系统不是假装窗口不存在，而是通过持久任务、重投递、幂等键和对账，使重复执行与不确定结果能够被正确处理。

## 组合模式的差异在依赖和决策来源

Sequential Workflow 把前一步输出交给后一步，适合存在真实数据依赖的链路。Prompt Chaining 属于这一类：先生成提纲，通过程序 Gate 后再生成正文。它用更多调用和延迟换取每一步更小、更明确的任务，但不应为了“看起来像 Agent”把一次足够的调用机械拆开。

Parallel Workflow 有两种常见目的：把独立子任务分区并发以降低总延迟，或者让多个尝试分别判断同一对象后再投票或聚合。并行安全必须同时满足数据、状态和副作用条件；仅仅因为两个函数都能异步调用，并不表示它们在业务上可以并行。总耗时受最慢分支和汇合点支配，瞬时 Token、连接和限流压力通常会上升。

Routing 先识别输入类别，再进入专用流程；Conditional Workflow 则是更一般的状态谓词分支，例如“金额大于阈值则审批”。路由判断可以来自普通规则、分类器或 LLM，但结果应受枚举 Schema 和允许边集合约束。模型输出一个不存在的节点名时，Runtime 应拒绝或走 Fallback，而不是执行任意字符串。

Orchestrator-Workers 适合事前不知道子任务数量的场景。中央 Orchestrator 根据输入产生结构化任务清单，Worker 隔离执行，最后由聚合器合并。例如代码修改可能涉及多少文件无法预先固定。它与静态 Parallel 的关键差异不是图形上都有 Fan-out，而是 Worker 集合由运行时动态产生。

Evaluator-Optimizer 让 Generator 生成候选，再由 Evaluator 按 Rubric 给出反馈，直到通过或耗尽预算。它只适合评价标准足够清楚、迭代确有可测收益的任务。没有通过阈值、最大轮数和外部验证时，这个循环很容易把同一模型的偏差重复放大。

## DAG、状态机和事件驱动编排回答不同问题

有向无环图（Directed Acyclic Graph，DAG）擅长表达静态依赖和可并行拓扑。只要上游完成，就能调度下游；拓扑排序可以检测环。它适合数据管道、批处理和有明确结束点的步骤图，但“等待审批后重试”“Evaluator 不通过则返回生成”天然包含环，强行展开为有限 DAG 会变得笨重。

有限状态机把系统表示为状态与合法转移，例如：

```text
RUNNING ──需要审批──→ PAUSED ──批准──→ RUNNING
   │                       └──拒绝──→ COMPENSATING
   ├──成功────────────────────────→ COMPLETED
   ├──永久失败────────────────────→ COMPENSATING ─→ FAILED
   └──取消请求────────────────────→ COMPENSATING ─→ CANCELLED
```

状态机最重要的价值不是画图，而是拒绝非法转移：已完成 Run 不能再次审批，旧 Worker 不能覆盖新状态，`COMPENSATION_FAILED` 不能伪装成已回滚。

事件驱动编排让服务通过事件异步协作。它降低时间耦合并便于扩缩，但事件顺序、重复、Schema 演进和最终一致性必须显式处理。没有中央 Orchestrator、由各服务响应事件自行推进的形式常被称为 Choreography；参与者少时很轻量，跨服务链路变长后则更难回答“整个业务现在在哪里”和“下一步由谁负责”。工程上常用 DAG 描述依赖，用状态机约束生命周期，再用事件和队列运输工作。

## Durable Execution 的核心是持久事实与可重复决策

Durable Execution（持久执行）意味着 Run 的生命周期不依赖某个 Web 请求、进程或 Worker。API 可以立即返回 `run_id`，后台 Worker 通过队列继续执行，调用方再用轮询、事件流或 Webhook 获取进度。Timer 也不应由进程中的 `sleep` 承担，而应被保存为一个带截止时间的持久等待条件。

不同引擎的恢复实现并不相同。Checkpoint 可以保存某个安全边界的状态快照；事件溯源保存有序历史，再通过归约或 Replay 重建状态；实际系统也会结合快照与历史以控制恢复时间。把 Checkpoint 只写在内存中不能跨进程恢复，历史无限增长也会增加存储与 Replay 成本，因此需要保留策略、快照或 Continue-as-new 一类的历史切分机制。

以事件历史 Replay 为例：

```text
第一次执行                         Worker 重启后

代码发出 Activity A               从头运行确定性控制代码
   ↓                                  ↓
历史记录 A 已完成 ───────────────→ 读取历史中的 A 结果，不再重做已记录工作
   ↓                                  ↓
代码等待审批                       重建到“等待审批”状态
   ↓                                  ↓
进程退出                           收到决定事件后继续
```

可重放的 Workflow 代码必须在相同历史下作出兼容决策。直接读取系统时间、随机数或当前网络响应可能让恢复路径与历史冲突，因此引擎通常提供可记录的时间、Timer 和 Side Effect API。LLM 调用尤其不确定：模型版本、采样和服务响应都可能变化，它应被放进 Activity；完成结果进入历史后，Replay 复用结果，而不是再次调用模型。

这里仍有一个容易被忽略的边界：**Replay 不重做已确认完成的 Activity，不代表 Activity 永远只执行一次。**如果 Worker 已经让外部系统产生效果，却在完成结果被记录前崩溃，任务会被再次派发。持久执行解决“控制状态不会丢”，幂等性和对账解决“外部效果不能重复”。

## 队列传输任务，但通常不理解完整业务

任务队列解决异步投递、削峰、Worker 扩缩和故障重投递。以常见的手动 Ack 模型为例，Worker 处理成功后确认消息；若连接在确认前断开，Broker 可以重新投递。这提供 At-least-once 语义，也意味着 Consumer 必须能接收重复消息。

队列中的一条消息通常不知道整个 Run 的拓扑、已经完成的兄弟节点、等待中的 Timer、人工审批或补偿栈。开发者当然可以在数据库中自行实现这些状态，但此时已经在构建一个工作流运行时。反过来，持久工作流引擎内部也常依赖任务队列把 Activity 派给 Worker；二者是上下层能力，不是竞争品牌。

选型可以从最小充分机制开始：

- 一次请求内可完成、路径固定且整体重试安全，使用普通代码。
- 每个任务相互独立，只需要异步、限流和重投递，使用任务队列。
- 任务跨分钟到数月，含多步骤依赖、Timer、审批、恢复或补偿，使用持久工作流引擎。
- 在上述流程的一部分中，子任务和路径无法预先写死，再加入结构化的模型路由、Agent Loop 或 Agent Workflow 框架。

框架不是可靠性的替代品。采用 Agent 编排框架前应确认它的 Checkpointer 是否为持久存储，节点失败后的重放边界是什么，暂停如何关联同一 Run，以及生产环境是否支持并发控制、版本迁移和数据保留。

## 失败必须转换成可处理的状态

Timeout、Cancellation、Retry 和 Compensation 处理的是不同问题。

Timeout 表示等待超过预算，但超时方往往不知道下游是否已经成功。需要区分单次 Attempt Timeout、无进展的 Idle Timeout 和整个 Run Deadline。超时后立刻重试有副作用的请求，可能把一个未知结果变成重复结果。

Retry 只适合暂时性失败，例如限流、短暂网络异常或服务端错误。参数校验失败、权限拒绝和业务规则冲突通常不会因等待而恢复。重试策略至少需要最大次数或总预算、指数退避和随机抖动；调用链每一层都独立重试会产生乘法放大。

Idempotency（幂等性）要求同一个逻辑意图重复提交时，不产生首次之外的新效果。比“对参数做 Hash”更清晰的做法，是由调用方生成稳定的 Idempotency Key，并让下游把 Key、请求语义和原始结果绑定保存。同一个 Key 不能被复用于另一笔金额或另一个用户；不同 Retry Attempt 也不能每次生成新 Key，否则无法去重。

Cancellation 通常是协作式的。Orchestrator 先记录取消请求，不再派发新节点，并向可取消的 Activity 传播信号；已经提交的支付或邮件无法靠杀死线程撤销。终止（Terminate）可以强制停止控制流程，但同样不自动修复外部世界。

Compensation（补偿）是与既有业务效果相反的后续动作，不是数据库回滚。Saga 原始模型为每个已提交的局部事务定义语义补偿，并在失败时逆序执行；取消航班预订可以抵消预订，但不能把数据库恢复成当时的字节状态，因为其间可能有其他事务运行。补偿本身也可能失败，因此必须可重试、幂等、可观测，并准备人工修复。某些不可逆动作没有真正补偿，只能在执行前审批，或通过追加更正记录降低损失。

## Human-in-the-loop 是一种持久等待状态

人工介入不应实现为 Worker 阻塞等待输入。Orchestrator 应先保存 Checkpoint 或事件，把 Run 转为 `PAUSED`，向外暴露待决事项，然后释放计算资源。审批记录至少应包含目标 Run、具体动作和参数摘要、风险、发起版本、审批人、决定、时间与过期策略。

恢复必须使用同一个持久身份，并重新验证环境。审批等待期间价格、权限或资源状态可能已经变化；“昨天批准过”不能自动授权今天已变更的参数。拒绝、取消与超时也应各有明确转移，不能都压成一个布尔值后丢失原因。

某些图运行时在恢复时会从发生 Interrupt 的 Node 开头重新执行，因此 Interrupt 之前的副作用必须幂等，或者拆到独立 Node 中。更稳妥的结构通常是：

```text
准备并持久化待审批命令
   ↓
PAUSED：展示动作、参数和风险
   ↓
批准事件 ──重新校验权限与前置条件──→ 执行副作用 Activity
拒绝/过期 ───────────────────────→ 取消或补偿
```

第 14 章会继续讨论澄清、审批疲劳、进度反馈和责任边界；本章只建立它们依赖的持久状态机。

## 确定性 Runtime 应包围模型的动态决策

把所有路径写死会失去模型处理开放任务的价值，把所有控制交给模型又会失去可预测性。更实用的结构是让模型在局部产生结构化提议，由确定性 Runtime 验证并执行：

```text
确定性入口与权限检查
   ↓
模型路由 / 任务分解 → Schema 校验 → Allowlist 与预算检查
   ↓                                      │
静态分支、动态 Worker 或受限 Agent Loop ←─┘
   ↓
确定性完成条件、审批、持久化与结果发布
```

模型可以决定已允许边集合中的下一条 Edge、生成 Worker 清单或判断是否需要继续搜索；它不应自行覆盖最大 Fan-out、并发配额、费用预算、审批条件和终止状态。Evaluator-Optimizer 也应由 Runtime 检查机器可验证条件，而不是只接受 Evaluator 的自然语言“已经很好”。

并发调度还需要三个控制面。第一，按依赖只释放 Ready Node；第二，用 Semaphore、Worker Pool 或配额限制模型和工具的瞬时并发；第三，用乐观版本号、单 Run Lease 或事务防止两个 Worker 同时推进同一状态。并行分支汇合时应定义稳定的排序、冲突解决和部分失败策略，不能依赖“谁先返回就覆盖谁”。

## 版本、Trace 和恢复测试决定系统能否长期运行

长时间 Run 会跨越代码发布。Definition Version 应进入 Run 的持久状态；删除 Node、改变 Edge 或在 Replay 路径中增加非确定分支，都可能让旧历史无法由新 Worker解释。常见策略是保留旧 Worker、在代码中加入与历史兼容的版本分支，或显式迁移尚未完成的 Run。模型和 Prompt 版本也应进入 Activity 元数据，但已记录的旧结果不应因发布新 Prompt 而被偷偷重算。

Trace 至少要把 `workflow_id/run_id`、Definition Version、Node/Activity、Attempt、Operation ID、事件序号、队列等待、执行耗时、Retry 原因、Pause 时长、审批人、取消原因和补偿结果关联起来。只记录最终答案，无法区分模型路由错误、Worker 未消费、下游超时、状态冲突或补偿卡住。

验证不能只跑 Happy Path。至少应覆盖：

- Worker 在 Activity 前、外部效果后和结果持久化后分别崩溃；
- 重复投递、乱序事件、并发推进和陈旧版本写入；
- Retry 耗尽、超时但下游实际成功、取消与补偿失败；
- 审批跨进程恢复、审批过期和参数变化后重新校验；
- 旧事件历史在新版本 Workflow 代码下 Replay；
- 并行 Fan-out 的限流、部分成功和确定性聚合。

评测除最终业务成功率外，还应观察恢复成功率、重复副作用率、人工修复率、P95/P99 端到端时延、队列等待、每 Run Attempt 数、暂停时长和补偿成功率。对于包含模型决策的路径，再按第 08、09 章的方法把路由质量和 Trace 过程指标纳入回归集。

## 最小实现验证崩溃恢复与副作用边界

本章示例 [`durable_workflow.py`](../../examples/13-workflow-orchestration/durable_workflow.py) 不依赖工作流框架，使用 SQLite 事件日志实现一个顺序 Orchestrator。它通过事件归约重建 Run State，每次追加都带 `expected_seq` 以拒绝陈旧 Worker；定义版本不一致时禁止直接恢复。

关键的 Operation ID 由 Run、定义版本、逻辑步骤和动作类型构成，在 Retry 时保持不变：

```python
operation_id = f"{run_id}:{definition.version}:{step.name}:execute"
```

示例把下游系统建模为独立的 `IdempotentEffectStore`。测试故意让进程在下游已经写入效果、`StepCompleted` 尚未进入事件历史时崩溃；新 Engine 恢复后会再次调用 Activity，但下游凭同一个 Operation ID 返回原结果，因此发生两次调用、只有一次业务效果。这验证的是 At-least-once 条件下的幂等边界，而不是声称跨数据库事务实现 Exactly-once。

12 项测试还覆盖跨 Engine 恢复、审批暂停、拒绝和取消后的逆序补偿、暂时失败重试、永久失败、补偿失败、乐观并发、定义版本以及幂等键语义冲突。示例没有实现分布式 Lease、Timer Service、加密、保留策略和数据库迁移，不能直接作为生产工作流引擎。

## 参考资料

- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)，Anthropic 官方工程文章；用于核对 Workflow/Agent 的路径控制边界，以及 Prompt Chaining、Routing、Parallelization、Orchestrator-Workers 和 Evaluator-Optimizer 的适用条件；最后核验日期：2026-07-23。
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)，LangChain 官方文档；用于核对低层 Agent Orchestration、持久执行、Human-in-the-loop，以及确定性步骤与模型驱动步骤混合的框架定位；最后核验日期：2026-07-23。
- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)，LangChain 官方文档；用于核对 Checkpointer、线程级 Graph State、跨 Run Store、故障恢复与持久存储边界；最后核验日期：2026-07-23。
- [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)，LangChain 官方文档；用于核对持久化暂停、同一 Thread 恢复、Node 重新执行，以及 Interrupt 前副作用必须幂等的限制；最后核验日期：2026-07-23。
- [Temporal Workflows](https://docs.temporal.io/workflows)，Temporal 官方文档；用于核对 Event History、确定性 Replay、恢复时复用已记录 Activity 结果，以及把 API、数据库、LLM 和文件 I/O 隔离到 Activity 的机制；最后核验日期：2026-07-23。
- [Temporal Workflow Execution overview](https://docs.temporal.io/workflow-execution)，Temporal 官方文档；用于核对 Workflow Definition/Execution、Command/Event、持久状态、Replay、Timer、取消与生命周期状态；最后核验日期：2026-07-23。
- [Reliability Guide](https://www.rabbitmq.com/docs/reliability)，RabbitMQ 官方文档；用于核对手动确认、故障重投递、At-least-once 交付和 Consumer 幂等要求；最后核验日期：2026-07-23。
- [Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)，Amazon Builders' Library；用于核对重试副作用、调用方请求标识和同一幂等键不得表达不同意图；最后核验日期：2026-07-23。
- [Sagas](https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf)，Garcia-Molina 与 Salem，ACM SIGMOD 1987 原始论文；用于核对长事务拆分、局部事务的语义补偿、逆序补偿，以及补偿不等同于恢复旧数据库快照；最后核验日期：2026-07-23。
