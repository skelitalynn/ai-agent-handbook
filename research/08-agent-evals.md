# 第 08 章研究记录：Agent Evals

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Agent Eval 与普通输出评测相比，为什么还要检查 Trace、工具调用和环境最终状态？
2. Task、Trial、Trace、Outcome、Grader、Dataset 与 Eval Harness 分别是什么？
3. 如何组合代码、模型和人工评分器，并校准模型评分器？
4. 如何处理非确定性，`pass@k` 与 `pass^k` 分别表达什么产品要求？
5. 如何把能力评测、回归集、线上样本和发布门禁连接起来？

## 范围边界

- 本章定义“什么叫成功”、构造数据集并聚合评分。
- 第 09 章负责完整记录和查询 Run Trace；本章把 Trace 视为评分输入，不展开遥测实现。
- 第 23 章负责重试、降级和 SLO 等可靠性控制；本章提供证明这些控制有效的测量方法。
- 第 24 章展开安全威胁；本章只要求安全行为进入独立、不可被平均分掩盖的门禁。
- 附录 B 将把本章方法应用到贯穿式项目。

## 一手资料与采用结论

### 1. Evaluate agent workflows

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/agent-evals
- 核对内容：Agent 工作流可结合 Trace、Grader、Dataset 与 Eval Run；Trace Grading 可检查工具、Handoff、指令和安全策略行为。
- 采用结论：最终结果评分与轨迹评分互补；产品无关的核心对象先于具体平台 API 讲解。
- 最后核验日期：2026-07-22。

### 2. Evaluation best practices

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/evaluation-best-practices
- 核对内容：尽早采用 Eval-driven Development、使用任务特定数据、持续评测、记录日志、自动化评分，并用人工反馈校准；模型评分更适合明确标准下的分类、打分或成对比较。
- 采用结论：Eval 不是上线前一次性 Benchmark；评分目标、数据、指标、比较和持续运行构成闭环。
- 最后核验日期：2026-07-22。

### 3. Trace grading

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/trace-grading
- 核对内容：Trace Grading 为端到端决策、工具调用和中间步骤分配结构化标签或分数，用于定位回归和工作流问题。
- 采用结论：Trace Grader 用于诊断原因，但不能因为轨迹“看起来合理”就替代环境 Outcome 验证。
- 最后核验日期：2026-07-22。

### 4. Demystifying evals for AI agents

- 来源：Anthropic Engineering。
- 链接：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- 核对内容：Task、Trial、Grader、Transcript、Outcome 和 Evaluation Harness 的定义；代码、模型与人工三类评分器；能力集与回归集的区别；多 Trial 的 `pass@k` 和 `pass^k`。
- 采用结论：环境最终状态优先于 Agent 自述；不同 Grader 各有偏差；小型真实失败集可以先启动，成熟后再扩充并提高统计能力。
- 最后核验日期：2026-07-22。

### 5. τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains

- 来源：Yao 等，原始论文。
- 链接：https://arxiv.org/abs/2406.12045
- 核对内容：通过对话终态数据库与标注目标状态比较来评测工具 Agent，并提出 `pass^k` 衡量多次 Trial 全部成功的一致性。
- 采用结论：正文使用“终态验证”和 `pass^k` 的机制，不照搬论文中已过时的具体模型成绩。
- 最后核验日期：2026-07-22。

## 术语决策

### Task 与 Trial

Task 是带输入、初始环境和成功标准的测试用例；Trial 是 Agent 对该 Task 的一次实际尝试。非确定系统应对同一 Task 运行多个 Trial。

### Trace 与 Outcome

Trace 是一次 Trial 的执行记录；Outcome 是执行结束后的可观察结果或环境状态。Agent 声称“已取消订单”属于输出，订单数据库状态才属于 Outcome。

### Capability Eval 与 Regression Eval

Capability Eval 探索当前能力边界，允许较低初始通过率；Regression Eval 保护已经可靠工作的行为，应设置严格发布门禁。通过稳定的能力项可以晋升为回归项。

### pass@k 与 pass^k

本章用 `pass@k` 表示 k 次尝试至少一次成功的 Task 比例，用 `pass^k` 表示 k 次尝试全部成功的 Task 比例。前者适合允许多次候选的任务，后者衡量每次都可靠的产品体验。

## 示例设计

`examples/08-agent-evals/eval_harness.py` 使用标准库实现：

- Task、Trial、Event、Grade 与 SuiteReport；
- 基于环境 Outcome 的确定性评分；
- 必须和禁止的工具调用及参数评分；
- 步数与成本预算评分；
- 多次 Trial 的总体成功率、`pass@k` 与 `pass^k`；
- 按 Tag 聚合失败，帮助维护分层数据集。

示例不调用真实模型，不实现模型评分器；目的在于先验证 Eval Harness 的数据和聚合语义。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
