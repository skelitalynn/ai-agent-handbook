# 第 04 章研究记录：Agent Loop 与 ReAct

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Agent Loop 的最小闭环由哪些状态和转换组成？
2. ReAct 原论文提出的机制是什么，它与现代 Tool Calling Runtime 有什么关系？
3. 模型与 Runtime 各自应负责什么，哪些控制不能交给模型自行决定？
4. 一次 Run 应如何完成、暂停或失败，最大步数能解决什么、不能解决什么？
5. 如何识别无进展循环、判断并行条件，并定位模型、工具与编排故障？

## 范围边界

- 本章讲“模型—行动—观察—再决策”的控制闭环。
- 第 05 章单独讲 Tool Schema、参数校验、副作用、幂等和权限。
- 第 06 章单独讲跨进程持久化、Session、Checkpoint 与恢复。
- 第 08、09 章分别系统讲 Evals 与 Trace/Observability。
- 第 12 章再展开 Planning、Reasoning 与决策控制策略。
- 第 13 章再展开固定 Workflow、状态图与复杂 Orchestration。

## 一手资料与采用结论

### 1. ReAct: Synergizing Reasoning and Acting in Language Models

- 来源：Shunyu Yao 等，ICLR 2023 / arXiv v3
- 链接：https://arxiv.org/abs/2210.03629
- 核对内容：论文把推理轨迹与任务行动交错生成；推理用于维护和更新行动计划、处理异常，行动用于从知识库或环境取得外部信息。
- 采用结论：用 `Reason/Action/Observation` 解释 ReAct 的原始思想，但不把公开自由文本思维链写成现代 Agent 的必要接口。
- 最后核验日期：2026-07-22

### 2. Building effective agents

- 来源：Anthropic Engineering
- 链接：https://www.anthropic.com/engineering/building-effective-agents
- 核对内容：Workflow 走预定义代码路径，Agent 由模型动态决定过程与工具；Agent 通常是模型依据环境反馈循环使用工具；开放任务更适合 Agent，但会增加成本、延迟和复合错误，需要停止条件、沙箱、护栏与测试。
- 采用结论：用“决策路径是否由模型在运行时动态选择”划分 Agent Loop 和确定性 Workflow；环境 Observation 是下一步决策的事实输入。
- 最后核验日期：2026-07-22

### 3. OpenAI Agents SDK: Running agents

- 来源：OpenAI Agents SDK 官方文档
- 链接：https://openai.github.io/openai-agents-python/running_agents/
- 核对内容：Runner 循环调用模型；最终输出结束，Handoff 更新当前 Agent 后继续，工具调用执行并追加结果后继续；超过 `max_turns` 产生错误；最终输出还要求没有待执行工具调用。
- 采用结论：把一次模型调用记作一步，把工具结果写回历史后再调用模型；最终文本、工具调用、暂停与错误是不同终态或转换，不能仅凭出现文本判断完成。
- 最后核验日期：2026-07-22

### 4. OpenAI Agents SDK: Results

- 来源：OpenAI Agents SDK 官方文档
- 链接：https://openai.github.io/openai-agents-python/results/
- 核对内容：运行结果区分 `final_output`、`new_items`、原始响应和可恢复状态；审批中断时最终输出可以为空；流式可见最后一个 Token 不等于 Run 已完成。
- 采用结论：Runtime 应返回明确的完成、暂停或失败状态，并保留结构化 Trace；面向用户的最终答案不能代替运行状态。
- 最后核验日期：2026-07-22

### 5. A practical guide to building agents

- 来源：OpenAI
- 链接：https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
- 核对内容：Agent Run 的核心是循环执行直到满足退出条件；常见条件包括特定输出、无工具调用、错误或最大轮数。
- 采用结论：停止条件必须由 Runtime 实现为可检查的规则，而不是只提示模型“完成后停止”。
- 最后核验日期：2026-07-22

### 6. Reasoning best practices

- 来源：OpenAI API 官方文档
- 链接：https://developers.openai.com/api/docs/guides/reasoning-best-practices
- 核对内容：推理模型通常不需要“逐步思考”或“解释推理过程”一类 Chain-of-Thought Prompt；复杂 Tool Calling 场景还需正确延续相关推理 Items。
- 采用结论：现代 ReAct 工程实现应保留可审计的决策、行动、参数、Observation 和状态变化，不应要求模型把隐藏推理完整输出给用户或日志。
- 最后核验日期：2026-07-22

## 来源分歧与术语决策

### ReAct 是 Prompt 格式，还是 Agent 架构？

原论文中的 ReAct 是一种让推理轨迹和行动交错生成的方法；工程实践常把相似的“决策—行动—观察”循环也称为 ReAct Agent。正文会分别使用“原始 ReAct 轨迹”和“现代 Agent Loop”，避免把论文中的文本格式与某个厂商 API 的 Tool Call 数据结构视为同一协议。

### 最大步数是否属于终止条件？

属于硬停止条件，但只是损失上限。它不能判断任务是否真正完成，也不能修复 Observation 丢失、状态未更新、工具不可用或重复决策等根因。正文称其为 Circuit Breaker（熔断护栏），同时要求进展检测和 Trace 定位。

### 是否展示模型的完整思维链？

不要求。教材只讨论可观察、可验证的控制面信息：模型选择了什么动作、参数是什么、工具返回什么、运行状态如何变化，以及必要的简短依据或证据。内部推理表示由模型和 API 管理，不作为应用协议的必需字段。

## 示例设计

`examples/04-agent-loop-react/agent_loop.py` 使用标准库实现：

- `ToolCall`、`FinalAnswer`、`NeedUserInput` 三种模型决策；
- 工具执行结果统一转换为 `ToolObservation`；
- Runtime 独立负责最大步数、重复调用检测、未知工具、异常捕获和终态；
- `TraceEvent` 记录可观察控制事件，不记录隐藏思维链；
- 示例使用脚本模型验证循环本身，不依赖厂商 SDK 或网络。

本例故意不实现 Tool Schema、审批、持久化和并发执行，它们分别属于后续章节。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过 6 项单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
