# 第 12 章研究记录：Planning、Reasoning 与决策控制

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Planning、模型内部 Reasoning、可观察决策与 Runtime Control 分别是什么？
2. 预先完整规划、边行动边调整和 Evaluator-Optimizer 各自适合什么任务？
3. Reflection 与 Self-Critique 为什么可能有效，又为什么不能替代外部验证？
4. 怎样控制动态重规划、重复动作、成本预算、澄清和人工升级？
5. 如何评测计划质量，而不把某一条漂亮轨迹误当作成功证明？

## 范围边界

- 第 04 章已解释最小 Agent Loop 和 ReAct 起源；本章关注复杂任务中的计划表示、修改、验证和确定性外层控制，不重复 Tool Calling 协议。
- 第 13 章将系统讲解持久化 Workflow 与 Orchestration；本章只讨论单次决策循环中“下一步怎么选”和“Runtime 如何约束”。
- 不要求模型输出或应用保存隐藏 Chain-of-Thought。可观察层只保留 Goal、Plan、Action、Observation、简短依据、证据和停止原因。
- Reasoning 参数是具体模型的 API 能力，不把某厂商当前取值写成跨模型标准。

## 一手资料与采用结论

### 1. ReAct: Synergizing Reasoning and Acting in Language Models

- 来源：Yao 等，ICLR 2023 原始论文。
- 链接：https://arxiv.org/abs/2210.03629
- 采用结论：ReAct 将面向任务的行动与中间推理交错，使外部观察能够更新行动计划并处理异常。正文使用其“Action → Observation → 调整”的控制结构，不要求生产系统暴露论文实验中的自由文本推理轨迹。
- 正文用途：解释 Interleaved Planning 相对一次性完整计划的反馈优势。
- 最后核验日期：2026-07-22。

### 2. Reflexion: Language Agents with Verbal Reinforcement Learning

- 来源：Shinn 等，NeurIPS 2023 原始论文。
- 链接：https://arxiv.org/abs/2303.11366
- 采用结论：Reflexion 不更新模型权重，而是把任务反馈转换为语言 Reflection 并写入 Episodic Buffer，以影响后续 Trial。该机制依赖反馈质量，不能证明模型对自己的所有批评都正确。
- 正文用途：区分同一 Run 的 Self-Critique、跨 Trial Reflection 和权重更新。
- 最后核验日期：2026-07-22。

### 3. Building Effective AI Agents

- 来源：Anthropic 官方工程文章。
- 链接：https://www.anthropic.com/engineering/building-effective-agents
- 采用结论：官方区分预定义代码路径的 Workflow 与模型动态控制过程的 Agent；Evaluator-Optimizer 适合标准清晰且迭代有可测收益的任务；开放任务的 Agent 依靠环境 Ground Truth 调整，并应设置停止条件与 Guardrails。
- 正文用途：核对 Pattern 适用边界、复杂度—延迟—成本取舍和外部反馈的重要性。
- 最后核验日期：2026-07-22。

### 4. Trustworthy agents in practice

- 来源：Anthropic 官方研究文章，2026-04-09。
- 链接：https://www.anthropic.com/research/trustworthy-agents
- 采用结论：Agent 循环表现为 Plan、Act、Observe、Adjust，并在完成或需要人类输入时停止；不确定性有时可通过查询环境解决，有时涉及偏好和意图，只能交还用户。
- 正文用途：支持澄清、审批、暂停和人类控制边界。
- 最后核验日期：2026-07-22。

### 5. Model guidance

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/latest-model
- 采用结论：截至核验日，当前模型系列提供模型特定的 Reasoning Effort/Mode 选项；官方建议在代表性任务上比较质量、Token、延迟和成本，而非假定最高 Effort 总是最佳。
- 正文用途：说明 Test-time Reasoning 是可评测的资源配置，不等于 Agent Runtime 的计划与权限控制。
- 版本说明：具体模型名、取值和默认值变化快，正文不复制当前枚举。
- 最后核验日期：2026-07-22。

### 6. Demystifying evals for AI agents

- 来源：Anthropic 官方工程文章。
- 链接：https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- 采用结论：Agent Eval 应区分 Task、Trial、Transcript/Trace 和最终 Environment Outcome，并通过多 Trial 与多类 Grader 处理非确定性和过程/结果差异。
- 正文用途：设计 Planning 与决策控制的分层指标和回归集。
- 最后核验日期：2026-07-22。

## 术语与工程决策

### 不把 Planning 等同于 Chain-of-Thought

Plan 是可持久化、可检查的任务结构；Action 是对工具或环境的请求；Observable Basis 是一条可审计的短依据；Reasoning 可指模型内部的 Test-time Computation。系统正确性依赖前四类外部对象和环境结果，不依赖获得隐藏推理全文。

### 外层控制属于确定性 Runtime

模型可以提议 Replan、Ask、Act、Finish 或 Escalate，但 Runtime 强制执行依赖、Allowlist、审批、成本、最大步数、重复动作和完成条件。模型声称“完成”不能覆盖未通过的状态断言。

### Reflection 不是验证器

Self-Critique 可能补充遗漏，但同一模型的 Generator 和 Critic 可能共享盲点。优先使用单元测试、Schema、数据库状态和独立政策规则；使用模型 Evaluator 时明确 Rubric、校准并限制轮数。

## 示例设计

`examples/12-planning-reasoning-control/decision_controller.py` 使用 Python 标准库实现：

- 带依赖与状态的 Plan，并拒绝未知依赖和环；
- 结构化 `Act`、`Replan`、`Ask`、`Finish` 和 `Escalate`；
- Allowlist、依赖、High-risk Approval、估算/实际成本和 Tool Call Budget；
- 重复 Action Signature 检测、最大 Decision 数和完成声明验证；
- 外部 Observation 与 Evaluator 决定 Step 是否完成；
- Trace 只记录简短 Observable Basis，不请求隐藏 Chain-of-Thought。

## 待人工审核项

- [ ] 不同产品的 High-risk Action 分类、审批粒度与预算阈值需要按业务风险确定。
- [ ] OpenAI 当前 Reasoning 参数只作为 2026-07-22 的厂商示例，发布前需再次核对具体模型文档。
- [ ] 示例中的 Replacement Plan 会替换当前计划；生产系统是否保留已完成步骤、怎样迁移依赖和审批状态，需要与第 13 章 Durable Workflow 一并设计。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
