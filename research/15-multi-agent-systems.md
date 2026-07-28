# 第 15 章研究记录：Multi-Agent Systems

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-23。

## 研究问题

1. 多次模型调用、角色 Prompt、Workflow 和 Multi-Agent 的边界是什么？
2. 上下文隔离、并行、权限和独立生命周期何时足以抵消协调成本？
3. Manager-Worker、Agent as Tool、Handoff、Router 与 Evaluator-Optimizer 如何分配控制权？
4. 委派契约需要哪些字段，怎样验证动态 Task Graph？
5. 全局 State、Worker Context 和 Artifact 应怎样分离？
6. 怎样处理依赖、写冲突、Fan-out、Deadline、Straggler 和失败分支？
7. 聚合阶段怎样检查覆盖、证据、冲突和重复？
8. 怎样以单 Agent 为基线评测质量、协作和系统代价？
9. 多 Agent 的身份、权限和跨 Agent Prompt Injection 有什么额外风险？

## 范围边界

- 第 12 章已解释 Planning，第 13 章已解释 Durable Workflow，本章只讨论多个独立 Agent Context/Loop 之间的协作。
- 第 20 章将讨论跨系统 Agent 通信与 A2A；本章的参与者默认受同一应用 Orchestrator 控制，不展开互操作协议。
- 第 23～25 章将系统讨论可靠性、安全和部署；本章只建立多 Agent 特有的协调边界。
- 不把多个角色名、并行 LLM Call 或固定 Evaluator-Optimizer Workflow 自动归类为 Multi-Agent。

## 一手资料与采用结论

### 1. OpenAI Agents SDK: Agent orchestration

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/multi_agent/
- 采用结论：编排可以由 LLM 动态决定或由代码确定；Agents as Tools 让 Manager 保持会话与最终合并控制，Handoff 让 Specialist 接管后续交互；独立任务可以通过代码并行。
- 正文用途：确定 Manager-Worker、Handoff 和代码 Orchestration 的控制权边界。
- 版本说明：正文使用机制，不复制易变化的完整 SDK 参数。
- 最后核验日期：2026-07-23。

### 2. OpenAI Agents SDK: Handoffs

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/handoffs/
- 采用结论：Handoff 在模型侧表现为 Tool，但语义是把执行交给指定 Agent；`input_type` 承载模型在转交时生成的小型元数据，不替代应用 State；`input_filter` 决定接收方看到的历史。
- 正文用途：说明 Handoff 不是 Subagent Call，Context History 不能隐式全量传播。
- 最后核验日期：2026-07-23。

### 3. Anthropic: Multi-agent research system

- 来源：Anthropic Engineering，2025-06-13。
- 链接：https://www.anthropic.com/engineering/multi-agent-research-system
- 采用结论：Lead Agent 分解开放式研究并并行创建 Subagent；独立 Context 适合广度探索和信息压缩。文章同时记录 Token 成本、同步瓶颈、状态一致性、错误传播、任务重复/遗漏、分层 Trace 和 Artifact Store 的工程问题。
- 正文用途：作为完整生产案例，而不是把内部质量和成本数字泛化为行业结论。
- 最后核验日期：2026-07-23。

### 4. Anthropic: Building effective agents

- 来源：Anthropic Engineering。
- 链接：https://www.anthropic.com/engineering/building-effective-agents
- 采用结论：Routing、Parallelization、Orchestrator-Workers 和 Evaluator-Optimizer 是可组合执行模式；固定路径优先 Workflow，只有评测证明价值时才增加 Agentic Complexity。
- 正文用途：区分 Pattern Topology 与“是否具有多个自治 Agent”的执行语义。
- 最后核验日期：2026-07-23。

### 5. LangChain Multi-agent

- 来源：LangChain 官方文档。
- 链接：https://docs.langchain.com/oss/python/langchain/multi-agent
- 采用结论：多 Agent 常用于 Context Management、分布式维护和并行；Subagents、Handoffs、Skills、Router 具有不同控制与成本特征。单 Agent 加动态工具或 Skill 可能已经足够。
- 正文用途：交叉核对模式边界与 Context Engineering 是多 Agent 设计核心的结论。
- 最后核验日期：2026-07-23。

## 术语与工程决策

### 以执行边界而不是角色名定义 Multi-Agent

正文采用实践定义：参与者具有独立指令、Context、Tool 或生命周期，并存在委派、Handoff、状态与失败协调。单次 LLM Call 的角色流水线仍可视为 Workflow。

### Manager 生成计划，Runtime 验证计划

动态分解不能绕过 Task ID、DAG、Capability、Tool、Budget 和 Write Conflict 校验。模型负责提出候选 Task Graph，Runtime 决定能否执行。

### Worker 只接收 Context Projection

示例只把直接依赖的 Artifact 传给 Worker，不共享全局内部状态；Artifact 通过来源 Task 命名空间避免覆盖。

### 并行不仅检查 Dependency

无依赖任务若写入同一资源仍需串行。示例以 `write_keys` 做保守冲突控制，并把 Token Budget 作为批次准入条件。

### Worker Output 仍是不可信候选结果

Coordinator 验证实际 Tool Call、Token Usage 和 Expected Output；未授权工具或缺失产物会使任务失败，依赖分支被跳过。

## 示例设计

`examples/15-multi-agent-systems/multi_agent_orchestrator.py` 使用 Python 标准库实现：

- `AgentSpec` 的 Capability 与 Tool Boundary；
- `TaskSpec` 的 Dependency、Output Contract、Write Set 和 Token Budget；
- DAG、重复 ID 和能力可满足性校验；
- 最小权限 Agent 选择；
- 无依赖且无写冲突任务的有界并发；
- 只包含依赖 Artifact 的 Worker Context Projection；
- Worker Token、Tool 和 Output 验证；
- Failure/Skipped 传播与独立分支保留；
- Artifact 来源命名空间和层级 Run Report。

## 待人工审核项

- [ ] “独立 Agent”的组织定义可能因产品和框架不同，需要保持正文采用的是工程判定标准而非唯一学术定义。
- [ ] Anthropic 的 90.2% 内部质量提升与约 15 倍 Token 仅适用于其公开案例，发布时不得脱离任务、模型和评测背景。
- [ ] 实际业务的 Fan-out、并发、Deadline、Token 和 Tool Budget 需要通过容量与价值评测确定。
- [ ] 多团队维护 Agent 时的 Schema Version、兼容性和发布所有权需要结合组织流程补充。
- [ ] OpenAI Agents SDK 和 LangChain API 变化较快，人工发布前应再次核对 Handoff 与 Subagent 当前语义。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
