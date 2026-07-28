# 第 16 章研究记录：Runtime 与 Harness

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-23。

## 研究问题

1. Runtime 与 Agent Loop、进程、Orchestrator 的边界是什么？
2. Harness 是哪些组件的组合，为什么它没有单一行业定义？
3. Application、Runtime、Harness、Framework 和 Compute 怎样分层？
4. Run State、Local Context、Model Context 与 Artifact 为什么不能混用？
5. Lifecycle Event 和 Hook 应怎样处理顺序、失败、重放与安全策略？
6. Workspace、Artifact Store 和 Sandbox 分别解决什么问题？
7. 长任务怎样跨 Context Window、进程和 Sandbox 恢复？
8. 怎样证明 Harness 机制而非模型本身带来质量变化？
9. 最小实现可以验证哪些不变量，又不能冒充哪些生产安全能力？

## 范围边界

- 第 04～07 章已分别解释 Loop、Tool、State 和 Context；本章只说明 Runtime 如何拥有并组合这些职责。
- 第 13 章已解释 Durable Workflow；本章聚焦 Agent Run 和执行环境，不重复工作流引擎语义。
- 第 17 章讨论 Framework 选型与抽象代价；本章先建立厂商无关的职责清单。
- 第 23～25 章将深化可靠性、安全和部署；本章只解释 Runtime/Harness 必须提供的接缝。

## 一手资料与采用结论

### 1. OpenAI Agents SDK: Running agents

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/running_agents/
- 采用结论：Runner 执行 Model、Tool、Handoff 和 Final Output 循环，支持同步、异步和 Streaming；状态延续策略、最大轮次、异常与 Durable Integration 是不同运行职责。
- 正文用途：核对 Runtime Loop、Termination、State Continuation 和恢复集成。
- 最后核验日期：2026-07-23。

### 2. OpenAI Agents SDK: Context management

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/context/
- 采用结论：本地 `RunContextWrapper` 保存代码侧数据与依赖，不自动发送给 LLM；模型 Context 通过 Instructions、Input、Tools 或 Retrieval 进入 Conversation。序列化 Run State 时需避免把 Secret 放入将持久化或传输的对象。
- 正文用途：建立 Run State、Local Context 和 Model Context 三分。
- 最后核验日期：2026-07-23。

### 3. OpenAI Agents SDK: Lifecycle

- 来源：OpenAI Agents SDK API Reference。
- 链接：https://openai.github.io/openai-agents-python/ref/lifecycle/
- 采用结论：Run 和 Agent Scope 分别提供 Model、Tool、Agent 与 Handoff 前后事件；Hook 是 Lifecycle Callback，不等同于所有安全策略都应放在 Callback 中。
- 正文用途：核对当前事件面，并据此讨论 Observer、Transformer 与 Policy Gate 的工程分类。
- 最后核验日期：2026-07-23。

### 4. OpenAI: The next evolution of the Agents SDK

- 来源：OpenAI 官方产品文章，2026-04-15。
- 链接：https://openai.com/index/the-next-evolution-of-the-agents-sdk/
- 采用结论：更新后的 Python Agents SDK 将 Model-native Harness、受控 Workspace、Manifest 和 Native Sandbox 组合，并强调 Harness/Compute 分离对 Credential 隔离、外部化 State、Snapshot/Rehydrate 和多 Sandbox 扩展的作用。
- 正文用途：支持 Workspace/Sandbox/Harness/Compute 分层和当前产品实例。
- 版本说明：文章说明能力已 GA、先在 Python 提供；正文只使用架构机制，不复制完整 0.14.0 API。
- 最后核验日期：2026-07-23。

### 5. Anthropic: Effective harnesses for long-running agents

- 来源：Anthropic Engineering，2025-11-26。
- 链接：https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- 采用结论：Compaction 不能独自解决跨窗口连续工作；首轮 Initializer、结构化 Feature List、单项增量进展、Git/Progress File、干净交接和端到端测试降低“做太多”和“过早完成”的失败。
- 正文用途：说明长任务 Harness 需要环境和 Artifact 交接，而非只保留聊天摘要。
- 适用边界：原实验是长时间 Web App Coding，正文只抽取可迁移原则，不宣称所有领域必须采用同样文件。
- 最后核验日期：2026-07-23。

### 6. OpenAI: Harness engineering

- 来源：OpenAI Engineering，2026-02-11。
- 链接：https://openai.com/index/harness-engineering/
- 采用结论：案例把仓库内版本化知识作为事实源，让短 `AGENTS.md` 充当导航，以 Progressive Disclosure、结构检查、可执行计划和本地 Observability 构造 Agent 可读环境与反馈回路。
- 正文用途：说明 Harness 的知识入口和环境反馈应可导航、可验证，而不是一份巨型 Prompt。
- 适用边界：文章是 Codex 驱动软件工程案例，正文不把团队吞吐数字当作通用效果指标。
- 最后核验日期：2026-07-23。

## 术语与工程决策

### Runtime 是唯一执行权威

模型、UI 和 Observer 只能提出或展示；Tool Policy、State Transition、Budget 和 Terminal Status 必须由 Runtime 强制。

### Harness 采用广义工程定义

本文把 Runtime 视为 Harness 内核，把 Instructions、Tools、Context、Workspace、Sandbox Adapter、Artifact 和 Feedback Loop 视为装配层；明确该术语无唯一规范定义。

### Hook 不能默认承担安全

示例 Observer 只能读取不可变 Event，失败写入诊断但不改变 Run。Tool Allowlist 直接位于 Runtime Executor，避免漏注册 Hook 绕过。

### Workspace 示例不声称是 Sandbox

示例只验证 Virtual Mount、只读和路径逃逸；真实 Sandbox 还需 OS/VM 层的 Network、Process、Credential 和 Resource 隔离。

### Artifact 必须显式提升

只有 Publish Mount 下的文件可以进入 Artifact Store，并带 Run、Step 和 Content Digest；普通 Workspace 文件仍是临时状态。

## 示例设计

`examples/16-runtime-harness/runtime_harness.py` 使用 Python 标准库实现：

- `Harness` 组合 Model、Tools、Policy、Workspace、Artifact、Observer 与 Local Context；
- `Runtime` 强制 Loop、Status、Step/Tool Budget、Cancel 与 Tool Allowlist；
- Created/Running/Paused/Completed/Failed/Cancelled 状态；
- 有序、不可变 Lifecycle Event 和 Observer Error 隔离；
- Local Context 与 Model Request 的结构隔离；
- Virtual Mount、Read-only、Path Traversal 与 Publish Mount 检查；
- Artifact SHA-256、来源 Step 和稳定 ID；
- Run State JSON Round-trip 后 Resume。

## 待人工审核项

- [ ] Harness 没有单一正式定义，发布时需要确认术语说明不会被读成某厂商专有抽象。
- [ ] OpenAI Agents SDK Harness/Sandbox 在 2026-04 更新较大，人工发布前需检查 Python/TypeScript 支持和 GA 状态是否变化。
- [ ] Sandbox 强度必须结合威胁模型、宿主平台和第三方 Provider 验证，本文不提供通用“安全容器”结论。
- [ ] Hook 的 Fail-open/Fail-closed、Timeout 和 Delivery 语义需要在具体 Framework/Runtime 中逐项确认。
- [ ] 长任务 Artifact 和知识导航原则来自 Coding 案例，迁移到研究、数据或客服系统时需重新评测。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
