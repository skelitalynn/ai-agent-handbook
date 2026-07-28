# 第 17 章研究记录：Agent Framework

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-23。

## 研究问题

1. Agent Framework 与 Runtime、Harness、SDK、Workflow Engine 的边界是什么？
2. 怎样按抽象中心理解组件框架、图运行时、Provider-native SDK 和 Data/RAG Framework？
3. LangChain、LangGraph、LlamaIndex、OpenAI Agents SDK 和 Claude Agent SDK 当前各自强调什么？
4. 怎样从 Hard Requirement、Contract、Behavior 和 Operational Gate 完成可复现选型？
5. Multi-provider Interface 为什么不能消除 Provider 行为差异？
6. Framework State、Checkpoint、Event 和 Domain Model 怎样隔离？
7. 怎样比较成功率、延迟、成本和可观测性而不使用失真的总分？
8. Framework Upgrade 为什么必须覆盖旧 Checkpoint 和正在运行的任务？
9. 初学者如何学习框架而不把 API 当成 Agent 原理？

## 范围边界

- 第 16 章已经建立 Runtime/Harness 职责，本章据此评估实现产品，不重复 Runtime 原理。
- 不写所有框架的安装与 Quickstart，也不依据 Star 或流行度排名。
- 正文只使用当前官方文档说明抽象中心，不宣称表格是永久 Feature Matrix。
- 示例验证选型门禁与 Adapter 思路，不依赖第三方框架，不伪造真实 Benchmark。

## 一手资料与采用结论

### 1. LangChain: Frameworks, runtimes, and harnesses

- 来源：LangChain 官方概念文档。
- 链接：https://docs.langchain.com/oss/python/concepts/products
- 采用结论：当前文档区分高层 Agent Framework、低层 Runtime 和更完整 Harness；LangChain 1.x 建在 LangGraph 上，LangGraph 强调 Durable Runtime，Deep Agents 是更完整 Harness。
- 正文用途：建立产品类型分层，并提醒类别会重叠。
- 最后核验日期：2026-07-23。

### 2. LangChain: Agents 与 Middleware

- 来源：LangChain 官方文档。
- 链接：https://docs.langchain.com/oss/python/langchain/agents
- 采用结论：当前 Agent API 组合 Standard Model Interface、Tool、Structured Output、State 和 Middleware；Middleware 可以修改模型输入、Tool 执行、错误和动态模型选择。
- 正文用途：说明组件/Agent Framework 的抽象中心和 Middleware Contract 需要测试。
- 版本说明：文档说明当前 `langchain 1.0` 行为；正文不复制易变化参数。
- 最后核验日期：2026-07-23。

### 3. LangGraph Overview 与 Persistence

- 来源：LangGraph 官方文档。
- 链接：https://docs.langchain.com/oss/python/langgraph/overview
- 补充链接：https://docs.langchain.com/oss/python/langgraph/persistence
- 采用结论：LangGraph 是可独立使用的低层 Stateful Orchestration Runtime，重点是 Durable Execution、Streaming、HITL 和 Persistence。Checkpoint 以 Thread/Super-step 组织，并有 Pending Write 恢复等具体语义。
- 正文用途：说明“支持 Checkpoint”不是布尔功能，必须检查提交与恢复边界。
- 最后核验日期：2026-07-23。

### 4. LlamaIndex Framework

- 来源：LlamaIndex 官方文档。
- 链接：https://developers.llamaindex.ai/python/framework/
- 采用结论：LlamaIndex 当前定位围绕 Context-augmented LLM Application，提供 Data Connector、Index、Query/Chat Engine、Agent、Observability/Eval Integration 和 Event-driven Workflow。
- 正文用途：说明 Data/RAG Framework 的选型理由应来自数据链，而不仅是存在 Agent 类。
- 最后核验日期：2026-07-23。

### 5. OpenAI Agents SDK

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/
- 采用结论：SDK 当前强调少量原语，内置 Agent Loop、Python Orchestration、Agents as Tools/Handoff、Sandbox Agent、Guardrails、Sessions 和 Tracing。
- 正文用途：作为 Provider-native Agent SDK/Harness 实例，说明贴近模型能力与迁移抽象之间的取舍。
- 版本说明：SDK Release 变化快，正文按 2026-07-23 文档核对，不写死完整 API 和版本号。
- 最后核验日期：2026-07-23。

### 6. Claude Agent SDK Overview

- 来源：Anthropic Claude Code 官方文档。
- 链接：https://code.claude.com/docs/en/agent-sdk/overview
- 采用结论：SDK 把 Claude Code 的 Loop、Context 与内置文件/命令 Tool 作为 Python/TypeScript Library，提供 Hooks、Subagents、MCP、Permissions、Sessions、Skills 和 Plugins；Agent SDK 在自有进程运行，Managed Agents 则托管 Agent、Sandbox 和 Event Log。
- 正文用途：说明同一供应商内 Library 与 Managed Service 也具有不同 State/Compute/Tool 所有权。
- 最后核验日期：2026-07-23。

## 术语与工程决策

### 不做永久排名

框架能力、默认值和产品边界变化快。正文用“抽象中心 + 当前核验日期”表达，不用星级榜单或未绑定版本的全量 Feature Matrix。

### 先 Hard Gate 后 Benchmark

缺少稳定身份、持久化或运行环境能力的候选不能用其他分数补偿。通过 Hard Gate 后才比较同一任务集上的质量和系统代价。

### 保留 Pareto Trade-off

示例不设主观加权总分。一个更准但更贵的候选与稍弱但更快的候选可能同时合理，由产品 SLO 决定。

### 应用拥有 Canonical Contract

Domain State、Policy、Artifact 和 Canonical Event 不直接依赖 Framework DTO；Opaque Checkpoint 可以保留，但必须有版本、迁移和退出计划。

### 统一接口不能隐藏 Capability

公共接口用于基础可移植性，Provider-native 能力通过显式、有版本的 Extension 暴露，并用 Contract Test 验证。

## 示例设计

`examples/17-agent-framework/framework_selection.py` 使用 Python 标准库实现：

- Stable/Experimental/Missing Capability Profile；
- Release Channel、State Ownership 和 Checkpoint Portability Hard Gate；
- 禁止 `latest`/`*` 的精确 Version Pin；
- Success、P95、Mean Cost、Trace Completeness Benchmark Gate；
- 不同 Suite 拒绝互比和 Profile/Version 去重；
- 多目标 Pareto Frontier，不合成单分；
- Framework/Version/Schema-aware Event Adapter；
- Schema Drift 和未知 Event Kind 的显式失败。

## 待人工审核项

- [ ] 各框架能力变化快，发布前需重新核对 Stable/Preview、Python/TypeScript 和托管/自托管边界。
- [ ] 正文表格是抽象中心，不是完整 Feature Matrix，需确认读者不会误读为框架优劣排名。
- [ ] 实际组织的 License、Security Review、人才与运维约束需要加入自己的 Hard Gate。
- [ ] 真实 Benchmark Threshold 必须由业务 SLO 和成本价值定义，示例数字仅用于单元测试。
- [ ] Opaque Checkpoint 是否可接受取决于任务时长、迁移窗口和供应商退出策略。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
