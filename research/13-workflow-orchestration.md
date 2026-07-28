# 第 13 章研究记录：Workflow 与 Orchestration

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-23。

## 研究问题

1. Workflow、Orchestration、Agent 和 Workflow Run 的边界是什么？
2. Sequential、Parallel、Routing、Conditional、Orchestrator-Workers 与 Evaluator-Optimizer 分别改变了什么？
3. DAG、状态机和事件驱动编排如何组合，而不是互相替代？
4. Checkpoint、Event History、Replay、Pause 与 Resume 如何形成 Durable Execution？
5. 为什么 Queue、Checkpoint 或 Replay 都不能单独保证外部副作用 Exactly-once？
6. Timeout、Cancellation、Retry、Idempotency 与 Compensation 应如何分工？
7. 怎样把模型的动态决策放入确定性 Runtime，并验证崩溃恢复和版本兼容？

## 范围边界

- 第 06 章已解释 State、Session 与 Checkpoint 的基础对象；本章关注跨步骤、跨进程的编排语义，不重复会话状态设计。
- 第 12 章已解释模型如何选择下一步；本章把模型决策视为受约束 Node，重点讨论调度、持久化和失败恢复。
- 第 14 章继续讨论人机交互；本章只把审批建模为可持久化的等待状态与决定事件。
- 第 15 章继续讨论 Multi-Agent；本章的 Worker 可以是普通函数、服务、模型调用或 Agent，不把并行 Worker 自动称为 Multi-Agent。
- 第 23 章将系统讨论可靠性指标与故障模式；本章只覆盖 Workflow 正确运行所必需的可靠性机制。

## 一手资料与采用结论

### 1. Building Effective AI Agents

- 来源：Anthropic 官方工程文章。
- 链接：https://www.anthropic.com/engineering/building-effective-agents
- 采用结论：Workflow 通过预定义代码路径编排 LLM 与工具，Agent 由 LLM 动态控制过程与工具；常见组合包括 Prompt Chaining、Routing、Parallelization、Orchestrator-Workers 和 Evaluator-Optimizer。复杂度会增加延迟与成本，应从最简单的充分方案开始。
- 正文用途：建立 Workflow/Agent 边界、组合模式和选型原则。
- 最后核验日期：2026-07-23。

### 2. LangGraph overview

- 来源：LangChain 官方文档。
- 链接：https://docs.langchain.com/oss/python/langgraph/overview
- 采用结论：LangGraph 定位为面向长时间、有状态 Agent 的低层 Orchestration Framework/Runtime，核心能力包括 Persistence、Human-in-the-loop 和 Streaming；同一 Graph 可混合确定性步骤与 LLM 驱动步骤。
- 正文用途：说明 Agent Workflow 框架解决的运行时问题及确定性/动态混合边界。
- 最后核验日期：2026-07-23。

### 3. LangGraph Persistence

- 来源：LangChain 官方文档。
- 链接：https://docs.langchain.com/oss/python/langgraph/persistence
- 采用结论：Checkpointer 保存单一 Thread 的 Graph State，用于会话连续性、HITL、Time Travel 与故障恢复；Store 保存跨 Thread 的应用数据。In-memory Saver 不能跨进程重启持久化，Checkpoint 需要保留策略。
- 正文用途：区分 Workflow Checkpoint、长期 Store 和仅内存状态。
- 最后核验日期：2026-07-23。

### 4. LangGraph Interrupts

- 来源：LangChain 官方文档。
- 链接：https://docs.langchain.com/oss/python/langgraph/interrupts
- 采用结论：Interrupt 依赖 Checkpointer 与稳定 Thread ID，在 Resume 时从所在 Node 开头重新执行，因此 Interrupt 之前的副作用应幂等、放在 Interrupt 之后，或拆成单独 Node。
- 正文用途：核对人工审批的 Pause/Resume 与副作用重放边界。
- 最后核验日期：2026-07-23。

### 5. Temporal Workflows

- 来源：Temporal 官方文档。
- 链接：https://docs.temporal.io/workflows
- 采用结论：Workflow Execution 通过 Event History 恢复；Replay 从头重新运行控制代码，以历史重建原状态。Workflow 决策必须确定，时间、随机性和外部 I/O 需要使用可记录 API 或 Activity；已完成 Activity 的结果在 Replay 时复用。
- 正文用途：解释 Event History、Replay、确定性代码和 Activity 隔离。
- 限定：文档中“Replay 不重新执行已完成 Activity”不等价于端到端 Exactly-once；Activity 在完成未被确认的窗口仍需按可重试副作用设计。
- 最后核验日期：2026-07-23。

### 6. Temporal Workflow Execution overview

- 来源：Temporal 官方文档。
- 链接：https://docs.temporal.io/workflow-execution
- 采用结论：Definition 是代码模板，Execution 是运行实例；Command 导致 Event 进入历史，Replay 从最后记录的事实恢复。开放状态包含 Running/Paused，关闭状态包含 Completed、Failed、Cancelled、Terminated 与Timed Out；Timer、Activity、Signal 和 Child Workflow 都可以成为等待对象。
- 正文用途：核对 Definition/Run、Command/Event、生命周期和持久等待。
- 最后核验日期：2026-07-23。

### 7. RabbitMQ Reliability Guide

- 来源：RabbitMQ 官方文档。
- 链接：https://www.rabbitmq.com/docs/reliability
- 采用结论：Consumer Ack 与 Publisher Confirm 表示应用层责任转移；使用 Ack 可获得 At-least-once 交付，但故障窗口可能导致重复投递，Consumer 应去重或幂等。
- 正文用途：区分任务队列投递与完整 Workflow 状态，并解释重复消费。
- 最后核验日期：2026-07-23。

### 8. Making retries safe with idempotent APIs

- 来源：Amazon Builders' Library。
- 链接：https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/
- 采用结论：超时会让调用方无法判断有副作用操作是否完成；调用方提供唯一请求标识，比仅从参数推断重复意图更明确。同一标识配合不同参数需要作为语义冲突处理。
- 正文用途：设计稳定 Operation ID 和下游去重契约。
- 最后核验日期：2026-07-23。

### 9. Sagas

- 来源：Hector Garcia-Molina 与 Kenneth Salem，ACM SIGMOD 1987 原始论文。
- 链接：https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf
- 采用结论：长事务可拆分为局部事务序列，并为已完成步骤定义语义补偿；失败时可逆序执行补偿。补偿不必、也通常不能恢复事务执行前的数据库快照，其他事务可能已经观察或改变中间状态。
- 正文用途：解释 Compensation 与数据库 Rollback 的边界。
- 最后核验日期：2026-07-23。

## 术语与工程决策

### Workflow、Orchestrator 与 Worker 分层

Workflow Definition 描述可行路径与策略；Orchestrator 持有 Run 的控制状态；Worker 执行 Activity；外部系统持有真实业务效果。Agent 可以成为动态决策 Node，但不能取代 Orchestrator 的持久化、权限和预算约束。

### 持久执行不承诺端到端 Exactly-once

控制事件与外部副作用通常不在同一原子事务中。示例采用 At-least-once 重投递 + 稳定 Operation ID + 下游幂等结果存储，并明确保留未知结果、对账和人工修复的生产边界。

### Version 是 Run 状态的一部分

事件 Replay 要求相同历史下产生兼容决策。示例直接拒绝 Definition Version 不一致的 Worker；生产系统可以选择保留旧 Worker、使用显式版本分支或迁移 Run，但不能无条件用新拓扑解释旧历史。

### Compensation 是新的业务动作

Compensation 逆序处理已完成且定义了补偿的步骤。它可以失败，也可能不存在完全逆操作，因此需要独立 Attempt Budget、幂等键、状态和人工修复入口。

## 示例设计

`examples/13-workflow-orchestration/durable_workflow.py` 使用 Python 标准库实现：

- SQLite Append-only Event Store 与按 Run 递增的事件序号；
- `expected_seq` 乐观并发控制，拒绝陈旧 Worker 覆盖新状态；
- Definition Version、Run State 投影与跨 Engine 恢复；
- 顺序 Activity、审批暂停与恢复；
- Retryable/Permanent Failure 分类与有界 Attempt；
- 取消、逆序 Compensation 和 `COMPENSATION_FAILED`；
- 基于稳定 Operation ID 的独立 Idempotent Effect Store；
- 注入“外部效果成功、完成事件未写入”崩溃窗口，验证重复调用只产生一次效果。

## 待人工审核项

- [ ] 生产选型时需要按部署环境决定使用任务队列、Temporal、LangGraph 或其他引擎；正文不为具体厂商给出无条件推荐。
- [ ] Operation ID 的保留期、租户隔离、请求语义比对和敏感数据处理需要结合业务合规要求确定。
- [ ] 不可逆动作、补偿失败和超时后结果未知时的人工修复 Runbook 需要由具体业务定义。
- [ ] 长时间 Run 的版本兼容策略、旧 Worker 保留周期和事件/Checkpoint 清理策略需要在部署前制定。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
