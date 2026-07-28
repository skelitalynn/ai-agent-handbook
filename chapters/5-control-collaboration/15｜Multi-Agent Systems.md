# Multi-Agent Systems

> 本文讨论何时应把一个任务拆给多个具有独立上下文和执行循环的 Agent，以及如何设计它们之间的控制权、任务契约、状态、权限、失败与评测。它是第五篇的最后一章：读者已经掌握 Planning、Workflow 和 Human-in-the-loop，现在可以判断增加协作者是否真的比单 Agent 更好。

## 面试速记

### 背诵提纲

**1. 定义**

Multi-Agent System 是多个具有独立指令、上下文、工具或生命周期的 Agent，通过明确协议协作完成共同目标的系统；多写几个角色 Prompt 或多调用几次模型，不一定构成 Multi-Agent。

**2. 适用条件**

- **上下文隔离**：不同子任务需要大量不同资料，只把压缩结果交回协调者。
- **并行探索**：任务可以拆成相互独立的方向，并行收益大于协调成本。
- **能力边界**：不同子任务确实需要不同模型、工具、权限、知识或维护团队。
- **独立生命周期**：子任务需要单独排队、暂停、恢复、取消和追踪。

**3. Manager 与 Worker**

Manager 负责分解、分派、预算和最终合并，Worker 在受限上下文中完成有边界的任务并返回结构化结果；Manager 保持全局控制和用户会话所有权。

**4. Handoff**

Handoff 把当前会话的控制权转交给另一个 Agent，由接收者继续直接面对用户；它不同于调用子 Agent 完成一个任务后把结果返回 Manager。

**5. 协作契约**

任务应显式声明目标、输入引用、输出 Schema、依赖、允许的工具、预算、截止时间、写集合和失败语义，不能只发送一句模糊的自然语言指令。

**6. 状态与上下文**

全局 Run State 和任务依赖由 Orchestrator 管理，Worker 只接收完成任务所需的 Context Projection；大结果写入 Artifact Store，并通过引用和来源信息传递。

**7. 并行与合并**

只有无数据依赖、无共享写冲突且预算允许的任务才能并行；聚合器必须检查覆盖范围、证据、冲突和缺失，不能把多份答案简单拼接。

**8. 成本与失败**

Multi-Agent 会增加模型调用、Token、尾延迟、权限面和故障组合；需要限制 Fan-out、深度、总预算与重试，并处理重复工作、任务遗漏、Worker 失败和结果过期。

**9. 评测原则**

必须以简化的单 Agent 或 Workflow 为基线，同时评测最终质量、委派正确性、重复与遗漏、合并质量、P95 延迟、Token/工具成本、权限违规和故障恢复；只有收益稳定超过新增复杂度才保留 Multi-Agent。

### 高频对比

| 模式 | 谁拥有用户会话 | 子任务完成后控制权 | 适合场景 |
| --- | --- | --- | --- |
| Agent as Tool / Manager-Worker | Manager | 返回 Manager 合并 | 多个专家提供有边界的中间结果 |
| Handoff | 接收方 Agent | 接收方继续对话，直到再次转交或结束 | 客服分流、阶段性专家接管 |
| Router + Workflow | 由应用决定 | 按代码定义的路径流转 | 分类边界稳定、希望延迟和成本可预测 |

### 高频问题

#### 问题1：怎样证明一个任务值得使用 Multi-Agent？

先实现单 Agent 或确定性 Workflow 基线，再在同一测试集比较质量、延迟、Token、工具调用和失败率。只有独立上下文、并行或权限隔离带来的增益稳定超过协调成本，才有充分理由增加 Agent。

#### 问题2：多个 Worker 同时运行，为什么端到端延迟仍可能变高？

总延迟受最慢 Worker、并发限流、队列等待和最终合并约束，而不是只看平均 Worker 时间。应设置 Deadline、处理 Straggler，并允许在覆盖充分时使用部分结果或降级。

#### 问题3：如何减少子 Agent 的重复工作和任务遗漏？

Manager 应输出可校验的任务图，为每个 Worker 指定边界、输入、期望产物和覆盖标签，并在合并前做 Coverage Check。自然语言角色名不能替代任务契约和依赖验证。

#### 问题4：一个 Worker 失败时是否应该重跑整个系统？

通常只重试可恢复且幂等的失败分支，并跳过依赖该分支的任务；独立成功分支和已验证 Artifact 应保留。若缺失分支是最终结果的必要条件，则系统应明确返回部分完成或失败，不能由 Manager 猜补。

#### 问题5：把工具分给不同 Agent 是否已经实现权限隔离？

没有。Prompt 中的工具列表只是模型可见能力，Runtime 和外部系统仍需按 Agent 身份、Task Scope 和具体参数强制授权；跨 Agent 消息也应视为不可信输入，防止越权委派和 Prompt Injection 传播。

---

## Multi-Agent 是有成本的隔离与协作机制

单 Agent 已经可以规划、调用多个工具并循环执行。把“研究员、程序员、审查员”三个名称写进 Prompt，然后顺序调用同一个模型，可能只是 Prompt Chaining；让三个模型分别生成答案再投票，可能只是 Parallel Workflow。判断是否属于 Multi-Agent，更有用的标准是：每个参与者是否拥有独立的指令和上下文，是否能在自己的执行循环中观察环境并采取行动，以及系统是否必须处理它们之间的委派、控制权和状态边界。

这个定义并不要求 Agent 来自不同厂商，也不要求彼此自由聊天。两个实例可以使用同一基础模型，只要它们的上下文、工具或生命周期确实独立；相反，换了三个模型却始终由一段确定性代码分别完成单次分类，仍更接近 Workflow。

```text
用户目标
   ↓
Coordinator / Manager：保存全局状态、拆分任务、分配预算
   ├── Worker A：独立 Context + Tool Loop → Artifact A
   ├── Worker B：独立 Context + Tool Loop → Artifact B
   └── Worker C：独立 Context + Tool Loop → Artifact C
                                  ↓
                    Coverage / Conflict / Evidence Check
                                  ↓
                            最终结果或降级
```

多个 Agent 的价值主要来自“分开”：分开的上下文可以扩大总信息处理容量，分开的执行者可以并行探索，分开的权限可以缩小单个任务的能力面，分开的生命周期可以让长任务独立恢复。代价也来自“分开”：信息需要压缩和传递，状态可能不一致，结果需要合并，错误会跨边界传播。

## 先判断真正需要分开的是什么

引入 Multi-Agent 前，应从最简单的替代方案向上检查。工具太多时，可以先按 Namespace 或 Tool Search 动态加载；专业知识太多时，可以让单 Agent 按需加载 Skill 或检索上下文；路径固定时，使用 Workflow；只是希望得到多个观点时，使用并行模型调用。只有这些方案仍不能提供所需隔离或自治，才需要多个 Agent Loop。

Multi-Agent 常见的充分理由有四类。

第一类是上下文容量与注意力隔离。开放式研究可能有多个方向，每个方向都需要大量搜索和中间判断。Worker 在自己的 Context Window 中处理细节，只向 Manager 返回压缩结论和证据引用，可以避免所有原始材料挤入一个上下文。这里的收益不是“角色更专业”这句抽象描述，而是可测量的输入隔离和信息压缩。

第二类是可并行的探索。只有子任务之间数据依赖较少，才会获得真实墙钟时间收益。广度搜索、独立安全审查和多个候选方案探索通常适合；大量共享上下文、每一步都依赖上一步结果的任务，会把时间消耗在同步和等待上。

第三类是能力和权限边界。例如检索 Worker 只能访问只读搜索工具，代码 Worker 在隔离沙箱中运行，发布 Agent 才能请求高风险审批。这个边界必须由 Runtime 和外部授权系统实现；给 Agent 一句“不要调用发布工具”不是权限隔离。

第四类是组织与生命周期边界。不同团队可以独立维护某个 Agent 的 Prompt、工具、数据和 Eval；后台 Worker 也可以拥有独立 Checkpoint、Deadline 和取消状态。但如果这些边界并不存在，Multi-Agent 只会把一个可理解的程序拆成更多网络调用。

Anthropic 在 2025 年公开的 Research 系统是一个有边界的实例：开放式研究可以并行追踪多个方向，Subagent 用独立上下文搜索，再由 Lead Agent 合并。其内部结果不能泛化为所有任务；文章同时指出，共享上下文多、依赖密集的任务并不适合当前 Multi-Agent。

## Manager、Handoff 和 Router 分配的是不同控制权

Manager-Worker 模式中，Manager 拥有用户会话和全局目标。Worker 像一个有自治能力的 Tool：收到有边界的任务，在独立循环中工作，返回 Result 或 Artifact，随后退出或等待新任务。OpenAI Agents SDK 将这种关系称为 Agents as Tools；它适合需要一个中心统一合并、执行公共 Guardrail 并产生最终答案的系统。

Handoff 则把当前会话的主动控制权转移给接收方。Triage Agent 判断用户需要退款支持后，Refund Agent 成为接下来直接回应用户的 Agent，并使用自己的指令、工具和会话视图。Handoff 的输入应包含原因、优先级等小型结构化元数据；应用状态仍由 Runtime 保存，接收方能看到哪些历史应通过 Context Filter 明确决定。

Router 是路由决策，不必是 Agent。分类规则稳定时，一段普通代码或小模型就能选择后续处理器；选中的处理器也可能只是函数或 Workflow。不要为了画出多个方框，就把每个方框命名为 Agent。

Evaluator-Optimizer 同样是一种交互拓扑，不天然属于 Multi-Agent。如果 Generator 和 Evaluator 只是两个受代码控制的单次模型调用，它是 Workflow；如果二者分别有自己的工具、状态和多步循环，并通过反馈契约协作，才具有更强的 Multi-Agent 性质。架构判断应根据执行语义，而不是模式名称。

| 问题 | Manager-Worker | Handoff | Router + Workflow |
| --- | --- | --- | --- |
| 谁合并最终结果 | Manager | 当前接管者 | 代码定义的聚合步骤 |
| Specialist 是否直接面对用户 | 通常不直接 | 是 | 取决于应用 |
| 上下文隔离 | 强，可只传任务 Projection | 需过滤会话历史 | 由每个步骤输入决定 |
| 并行能力 | 适合独立 Worker | 通常强调顺序接管 | 可由代码显式并行 |
| 可预测性 | 中等 | 较低 | 最高 |

## 委派应是类型化任务，而不是一句角色指令

“调查竞争对手”没有说明调查哪些维度、何时停止、应返回什么，也无法判断多个 Worker 是否重复。可靠委派至少需要以下字段：

- 稳定的 `run_id`、`task_id` 和父任务，用于 Trace、幂等和恢复；
- 目标、范围、排除项和成功条件；
- 输入 Artifact 引用及版本，而不是整段复制全局聊天；
- 输出 Schema、必须产生的 Artifact 和来源要求；
- 依赖任务、读集合和可能发生冲突的写集合；
- Agent 身份、允许工具、资源 Scope 和是否需要人工审批；
- Token、工具调用、时间、Fan-out 和重试预算；
- 失败、取消、部分结果和结果过期的语义。

Manager 可以使用模型提出任务分解，但 Orchestrator 应在执行前验证 Task ID 唯一、依赖图无环、能力和权限可满足、预算没有超配。动态规划不等于放弃结构化约束。

```text
Manager 生成 Task Graph
         ↓
Runtime 校验：DAG？能力？权限？预算？写冲突？
   ├── 不通过 → 要求重新规划 / 人工介入
   └── 通过
         ↓
按依赖释放 Ready Tasks，并把最小 Context 投影给 Worker
```

Worker 输出也必须验证。一个 Worker 声称“完成了”并不代表必需 Artifact 存在，也不代表它只用了获准工具。模型生成的摘要是候选结果；Runtime 要检查 Schema、来源、预算、工具 Trace 和状态转换。

## 全局 State 集中管理，Context 按任务投影

让所有 Agent 共享并任意修改一份长聊天历史，看似省去了接口设计，实际会制造覆盖、过期读取和权限泄漏。更稳妥的结构是由 Orchestrator 保存权威 Run State，包括 Task Graph、Owner、Status、Budget、Artifact Reference 和版本；每个 Worker 只获得完成当前任务所需的只读 Projection。

Worker 的过程性思考不应自动进入其他 Agent 的上下文。应传递可验证的事实、结构化短依据和 Artifact。代码、报告、数据集等大结果写入 Artifact Store，Manager 只接收引用、摘要、来源和版本；需要细节时按权限读取。这样既减少 Token 复制，也降低多次摘要造成的“传话失真”。

共享状态仍需并发控制。两个 Worker 如果都要修改同一文件、订单或报告段落，不能仅因为它们没有显式依赖就同时执行。Orchestrator 可以通过 Write Set、乐观版本或资源锁串行化冲突；对外部副作用仍沿用第 13 章的幂等键、补偿和对账机制。

跨 Agent 消息不是更高可信度的系统指令。Research Worker 可能从网页带回 Prompt Injection，Reviewer 也可能生成错误建议。接收方应知道消息来源和数据等级，Runtime 不应允许一个低权限 Worker 通过“请 Manager 替我调用”形成 Confused Deputy（混淆代理）攻击。

## 并行调度受依赖、资源和尾延迟约束

可并行的最低条件是没有数据依赖、没有共享状态冲突、外部服务允许相应并发，而且结果存在明确的合并方法。并行并不会降低总 Token；它主要把可独立工作的墙钟时间重叠，并可能用更多探索换取覆盖率。

真实延迟通常由最慢分支决定。某个 Worker 被限流、进入无效搜索或等待工具，会让所有已完成分支在聚合点等待。生产系统需要 Task Deadline、全局 Deadline、取消传播和 Straggler 策略：必要结果未到时失败，非必要结果超时时使用已完成覆盖并标记缺失，或者启动受限的替代 Worker。盲目重试最慢分支会进一步争抢限流配额。

Fan-out 也必须有硬上限。Manager 能创建 Worker、Worker 又能创建 Worker 时，调用数量可能按深度快速增长。Runtime 应限制最大并发、总任务数、嵌套深度、每层 Fan-out、总 Token 和工具调用；预算是跨 Agent 的共享资源，不能只让每个 Worker 各自认为自己“没有超标”。

## 合并的核心是覆盖、证据和冲突

聚合器不应只是把 Worker 输出粘在一起再让一个大模型润色。它首先要回答三个可验证问题：计划要求的每个维度是否都有结果，结论是否保留可追踪证据，不同 Worker 是否对同一事实产生冲突。

一种实用方法是让任务携带 Coverage Tag，并要求 Artifact 输出 Claim、Evidence Reference、Freshness 和 Limitation。聚合阶段先做确定性检查：缺少必需标签则任务未完成，引用不可访问则证据无效，同一实体的互斥值进入 Conflict Set；之后才让模型组织表达或决定需要追加调查。

重复不是投票。多个 Worker 从同一搜索结果生成相同说法，只代表相关错误，不代表三个独立证据。若目标确实是提高置信度，任务分解应主动增加方法、来源或模型的独立性，并预先定义多数票、否决条件或人工复核规则。

失败分支也不能由 Manager 靠语言流畅度掩盖。独立分支成功时可保留其 Artifact；依赖失败分支的任务应标记 `SKIPPED`；若缺失的是必要覆盖，则最终状态应是 Failed 或 Partially Completed。第 14 章的用户界面需要明确展示哪些部分完成、哪些缺失以及能否重试。

## 多 Agent 需要分层 Trace 和基于结果的评测

Trace 至少形成 `Run → Task → Agent Turn → Model/Tool Call → Artifact` 层级，并记录委派原因、输入 Projection、预算、Agent/Prompt/Tool 版本、Handoff、重试和取消。只保留最终聊天会丢失最关键的问题：Manager 是否拆错、Worker 是否选错、上下文是否遗漏，还是聚合器丢掉了正确结果。

评测应从单 Agent 基线开始，并分三层：

- **最终结果**：任务成功、正确性、完整性、证据质量和最终环境状态；
- **协作质量**：路由准确率、任务覆盖、重复率、依赖正确性、Handoff 成功、冲突发现和 Artifact Contract 通过率；
- **系统代价**：模型调用、输入输出 Token、工具次数、P50/P95 延迟、最慢分支、重试、并发峰值和权限违规。

端到端结果相同但成本增加数倍，不是改进；平均质量提高但高风险任务出现更多越权，也不能上线。还应做消融实验：移除某个 Worker、改成普通 Tool、禁止并行或让 Manager 单独完成，判断收益究竟来自上下文隔离、更多 Token、模型差异还是协作结构。

Anthropic 的 Research 案例报告其特定内部评测相对单 Agent 有明显提升，同时多 Agent Token 约为普通聊天的 15 倍。这组数字只能说明“性能增益与资源投入必须一起测”，不能作为其他模型和业务的预期收益。

## 最小实现验证协调边界

本章示例 [`multi_agent_orchestrator.py`](../../examples/15-multi-agent-systems/multi_agent_orchestrator.py) 使用 Python 标准库实现一个 Manager-Worker Runtime。它不调用真实模型，而把 Worker 作为可替换函数，专门验证框架不应隐藏的控制逻辑。

`TaskSpec` 明确声明 Capability、Dependency、Requested Tools、Expected Outputs、Write Keys 和 Token Budget。Coordinator 先检查任务 ID 和 DAG，再选择满足能力与工具要求且权限面最小的 Agent。Worker 只能看到直接依赖产生的 Artifact：

```python
visible = {
    key: artifact
    for key, artifact in artifacts.items()
    if artifact.source_task_id in allowed_sources
}
```

调度器把独立任务放入同一批并发执行，但重叠的 Write Key 会被串行化；Worker 返回后还要验证 Token、实际工具和必需产物。Artifact 使用 `task_id:name` 命名，避免不同 Worker 的同名结果互相覆盖。失败分支只使传递依赖者跳过，不会抹掉无关的成功分支。

13 项测试覆盖最小权限选 Agent、无可用能力、重复 Task、依赖环、并发、写冲突、Context Projection、未授权工具、输出契约、分支失败、Token 预算和 Artifact 命名空间。示例没有实现真实模型、分布式队列、持久化、重试、身份系统或 Handoff UI；这些属于 Runtime、可靠性与生产章节继续补全的边界。

## 参考资料

- [Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/)，OpenAI Agents SDK 官方文档；用于核对 LLM 编排与代码编排、Agents as Tools、Handoff、并行调用及二者组合的当前语义；最后核验日期：2026-07-23。
- [Handoffs](https://openai.github.io/openai-agents-python/handoffs/)，OpenAI Agents SDK 官方文档；用于核对 Handoff 是控制权转移、结构化 Handoff Input、Context Filter 和接收方历史可见性；最后核验日期：2026-07-23。
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)，Anthropic Engineering；用于核对 Lead Agent 与并行 Subagent 架构、任务委派、上下文隔离、Token 成本、同步瓶颈、Artifact 传递和 Multi-Agent Eval；最后核验日期：2026-07-23。
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)，Anthropic Engineering；用于核对 Routing、Parallelization、Orchestrator-Workers、Evaluator-Optimizer 的执行语义，以及只在评测证明收益时增加复杂度的原则；最后核验日期：2026-07-23。
- [Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)，LangChain 官方文档；用于交叉核对 Subagents、Handoffs、Skills、Router 的边界，以及不同模式的模型调用、上下文隔离和成本取舍；最后核验日期：2026-07-23。
