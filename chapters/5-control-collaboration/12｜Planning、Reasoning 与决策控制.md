# Planning、Reasoning 与决策控制

> 本文讨论 Agent 如何把目标转换为下一步行动，以及工程系统如何约束这种选择。它在第 04 章 Agent Loop 之上加入任务分解、动态重规划、反馈改进、不确定性处理和确定性 Runtime Control，并为第 13 章的持久化 Workflow 建立决策模型。

## 面试速记

### 背诵提纲

**1. 概念边界**

Planning 产生可检查的目标、步骤和依赖，Reasoning 是模型为生成决策投入的内部计算，Decision 是可执行的结构化选择；生产控制依赖 Plan、Action、Observation 和验证结果，不依赖暴露隐藏 Chain-of-Thought。

**2. 可观察决策链**

```text
Goal → Plan / Next Action → Runtime 校验 → Execute → Observation
        ↑                                      ↓
        └──── Continue / Replan / Ask / Stop ──┘
```

**3. 任务分解**

好的 Step 有明确输入、输出、依赖、完成条件和失败边界；可并行性来自依赖关系，不来自模型一次返回多个 Tool Call。

**4. 三种控制模式**

Plan-and-Execute 先规划后执行，ReAct 边行动边根据观察调整，Evaluator-Optimizer 用明确 Rubric 反复生成与评价；任务越动态，越需要短规划视野和环境反馈。

**5. 动态重规划**

工具失败、前提失效、发现新约束或证据不足时可以修改未完成步骤，但应保留完成事实、失败证据、版本和变更原因，不能用新计划抹掉旧副作用。

**6. Reflection 与验证**

Self-Critique 在当前输出上查漏，Reflection 把 Trial 反馈转成后续策略，Evaluator 独立按标准评分；三者可能共享模型盲点，必须优先使用环境状态、测试和确定性断言。

**7. Runtime Control**

模型可以提议 Act、Replan、Ask、Finish 或 Escalate，Runtime 强制执行依赖、Allowlist、审批、最大步数、时间、Token、成本、重复动作检测和完成条件。

**8. 不确定性与人工介入**

缺少可检索事实时可先探索，缺少用户意图或偏好时必须澄清，高风险或越权决策应请求审批或升级；不能用更长 Reasoning 猜测只有人能决定的信息。

**9. Reasoning 预算与评测**

Reasoning Effort 是模型特定的测试时资源配置，可能提高复杂任务质量，也会增加 Token、延迟和成本；应以多 Trial 的任务结果、过程约束和资源指标选择，而非默认最高档。

### 高频对比

| 模式 | 决策时机 | 最适合 | 主要风险 |
| --- | --- | --- | --- |
| Plan-and-Execute | 执行前形成较完整计划 | 目标清晰、依赖稳定、需要预审方案 | 早期假设错误会让后续步骤整体失效 |
| ReAct / 交错决策 | 每次 Observation 后选择下一步 | 环境动态、工具结果会改变路径 | 调用次数多，容易局部循环和目标漂移 |
| Evaluator-Optimizer | 生成与按 Rubric 评价循环 | 评价标准明确且反馈能稳定改进结果 | Generator 与 Evaluator 可能共享盲点并无限润色 |

### 高频问题

#### 问题1：为什么复杂任务不一定应该先生成一份完整计划？

完整计划会在尚未观察环境时锁定大量假设，首个工具结果变化后，后续步骤可能全部失效。动态任务更适合先确定短期里程碑，执行后根据真实 Observation 滚动规划。

#### 问题2：为什么让同一个模型 Self-Critique 不能替代测试或外部验证？

Generator 与 Critic 可能共享知识缺口、错误假设和 Prompt 偏差，批评写得合理也不代表 Environment Outcome 正确。能用 Schema、单元测试、数据库状态或政策规则验证的条件，应交给确定性检查。

#### 问题3：为什么最大步数不能彻底解决 Agent 死循环？

最大步数只限制损失，不解释循环原因，也可能在最后一步前截断有效任务。还要检测等价 Action、状态是否产生进展、失败是否被消费、计划是否更新，并在 Trace 中记录停止原因。

#### 问题4：Agent 应该自己搜索补充信息，还是向用户澄清？

事实缺口若存在授权、低成本且可验证的数据源，可先搜索；涉及用户意图、偏好、不可逆取舍或授权扩展时必须询问。判断依据是“信息能否从环境可靠获得”，而不是模型主观置信度高低。

#### 问题5：怎样评测一个 Plan 的质量？

不要只比较计划文字是否像人写的，应检查依赖是否合法、关键约束是否覆盖、Step 是否可验证，以及执行后的成功率、重规划率、无效动作、成本和人工介入。模型具有随机性时，同一 Task 要运行多个 Trial。

---

## Planning 的产物应能改变执行，而不只是解释执行

Agent 面对复杂目标时，需要在多个可能动作中选择下一步。Planning（规划）把目标转换为可以执行和验证的结构；Reasoning（推理）常指模型在一次调用中为产生答案或决策投入的计算；Decision Control（决策控制）则决定模型的提议是否允许执行、执行后怎样更新状态以及何时停止。

这三个对象必须分开。模型可以消耗更多 Reasoning Token，却仍然选择越权工具；也可以输出一篇详细计划，却没有任何 Step ID、依赖或完成条件，Runtime 无法据此调度。相反，一个很短的结构化决策只要引用当前状态、动作参数和验证条件，就足以驱动可靠执行。

生产系统不应把隐藏 Chain-of-Thought 当作控制接口或正确性证据。应用真正需要的是可观察、可持久化且最小充分的信息：目标、计划版本、下一动作、简短依据、使用的证据、环境观察、预算和停止原因。模型内部如何形成这些输出可以由模型实现变化，外层契约仍保持稳定。

```text
不可作为稳定接口                  可作为工程接口
────────────────                  ──────────────
隐藏的内部推理全文                 Goal 与 Success Criteria
模型“感觉应该完成了”               Step Status 与 Environment Assertion
自由文本中的隐含工具意图           Action Name + Validated Arguments
自我评价“结果很好”                 Test / Policy / State Grader
```

## Plan 是带不变量的任务状态，不是待办列表

一个 Plan 至少需要回答：现在追求什么结果、有哪些 Step、Step 之间有哪些依赖、每一步何时算完成，以及失败后允许怎样变化。对于可能产生副作用的动作，还要标记权限、审批和补偿边界。

最简单的线性计划可以按顺序执行；当子任务存在依赖和并行关系时，更适合表示为有向无环图（DAG）。Step B 依赖 Step A，意味着 A 的完成断言通过之前，B 不可运行。两个 Step 没有数据依赖、共享可变状态或冲突副作用时才可能并行；模型一次生成两个动作不是并行安全证明。

```text
Goal：发布新版本

inspect ─→ change ─→ test ─→ deploy
                  └─→ docs ─────┘

约束：
- change 只能消费 inspect 的已验证输出
- test 与 docs 可在 change 后并行
- deploy 同时依赖 test、docs 和人工审批
```

Step 的粒度也需要权衡。一个 Step 写成“完成整个项目”无法单独验证；拆成每一行代码又会增加模型调用、状态和调度成本。合适粒度通常对应一个可观察产物或里程碑，例如“得到目标表 Schema”“迁移在影子库通过”“生成等待审批的发布计划”。

Plan Validity 可以先由确定性规则检查：Step ID 唯一、依赖存在、无环、动作在 Allowlist 中、必要审批节点存在。语义层面再检查是否覆盖用户约束和关键风险。两者不能互相替代。

## 规划视野取决于环境可预测性

Plan-and-Execute 先生成较完整计划，再由执行器逐步完成。它适合依赖稳定、方案需要提前向人展示或多个 Worker 要共享路线的任务。完整计划还能在高风险操作前做整体审阅，避免用户只看到一个个孤立审批请求。

它的弱点是 Open-loop Assumption：计划形成时尚未获得后续 Observation。网页结构、代码测试、库存和外部 API 都可能与预期不同。若执行器机械跑完原计划，后续步骤会建立在已经失效的前提上。

ReAct 原始方法把面向任务的推理与 Action 交错，让外部结果能够更新计划和处理异常。工程实现可以保留这种反馈结构，而不要求输出论文实验中的自由文本推理轨迹：模型每轮只需返回结构化的 `action`、参数、目标 Step 和一条可审计依据；Runtime 执行后写回 Observation。

```text
较稳定环境：Goal → 完整 Plan → 审批 → Execute Steps → Verify

动态环境：  Goal → 短期 Plan → Act → Observe
                       ↑              │
                       └── Replan ────┘
```

规划视野不是二选一。常见做法是先建立里程碑级 Plan，保证目标和高风险边界可见；每个里程碑内部再采用 ReAct 式滚动决策。这样既避免完全无计划的局部游走，也避免把遥远未知步骤假装成确定事实。

## Observation 必须来自环境，而不是模型自述

动作执行后，Runtime 应产生结构化 Observation：调用是否成功、返回了什么事实、修改了哪些状态、成本多少、错误是否可重试。工具返回 HTTP 200 不一定意味着业务成功，模型说“文件已修改”也不证明磁盘内容正确；完成条件要落在实际 Environment Outcome 上。

例如代码修改 Step 的验证器可以运行测试并检查工作树；支付 Step 可以查询交易状态和幂等键；检索 Step 可以检查所需证据是否进入候选。只有 Observation 通过对应 Grader，Step 才从 Pending 进入 Completed。

```text
Model Decision: act(tool="run_tests", step="verify")
        ↓ Runtime 校验
Tool Execution
        ↓
Observation: exit_code=1, failed_tests=[...]
        ↓
Evaluator: Step 未完成；错误可修复
        ↓
Model Decision: replan(reason="接口假设与测试不符")
```

这也是动态重规划的触发点。工具失败、发现新依赖、用户约束变化、证据冲突或预算不足时，可以替换未完成步骤；已经完成的事实、产生的副作用和审批记录不能因 Replan 消失。生产 Plan 应带版本，Trace 记录从哪个版本变到哪个版本以及触发 Observation。

若动作已经产生不可逆副作用，Replan 不是回滚。系统必须执行预先定义的补偿、人工处置或安全终止。真正跨进程、可恢复的补偿和 Durable Execution 属于下一章 Workflow 的范围。

## Reflection、Self-Critique 与 Evaluator-Optimizer 不是同一个机制

Self-Critique 通常在当前生成后让模型检查遗漏、矛盾或格式问题，再尝试修订。它不改变模型权重，也不自动跨 Trial 保存经验。适合低成本发现表面缺陷，但同一模型可能无法看见导致第一次错误的知识盲区。

Reflexion 论文提出把任务反馈转成语言 Reflection，保存到 Episodic Memory Buffer，在后续 Trial 中影响决策。这更接近“从失败经历形成可召回策略”，仍然是 Context 层学习，而非传统强化学习中的权重更新。Reflection 的质量取决于外部反馈：错误测试、误判的成功信号或模型自己编造的失败原因，都可能把后续 Trial 引向错误方向。

Evaluator-Optimizer 是一种显式 Workflow：Generator 产出候选，Evaluator 按 Rubric 给出反馈，Optimizer 修订，直到通过或达到轮数上限。它适合“人类能明确指出如何改进，而且模型也能按同一标准给出有用反馈”的任务。若 Rubric 模糊，循环容易退化成措辞润色；若 Generator 与 Evaluator 使用同一模型和相似 Context，二者可能共享偏差。

可靠性优先级通常是：

1. 能由代码或环境验证的事实，使用确定性 Grader；
2. 需要语义判断时，提供清晰 Rubric、证据要求和校准样本；
3. 高风险或主观取舍保留人工评审；
4. Self-Critique 作为补充候选，不作为唯一通过条件。

任何反馈循环都要设置最大轮数、最小改进阈值和停止原因。连续两轮输出没有实质差异，或评分提高但任务 Outcome 不变时，应终止而不是继续消耗 Token。

## 确定性 Runtime 为概率决策设置硬边界

模型适合根据开放 Context 选择候选动作，但它不能同时成为权限、预算和完成状态的最终裁判。Runtime 接收结构化 Decision 后，先验证再执行：

```text
Decision
   ↓
Schema 与 Plan Version 是否有效？
   ↓
Step 依赖是否完成？Action 是否在 Allowlist？
   ↓
是否需要审批？是否还有步数、时间、Token 和成本预算？
   ↓
是否与近期 Action 等价且没有进展？
   ├── 是 → Loop Detected / Replan / Escalate
   └── 否 → Execute → Observe → Evaluate
```

常用 Decision 类型包括：

- `Act`：对指定 Step 执行一个被允许的动作；
- `Replan`：基于新 Observation 提交新 Plan Version；
- `Ask`：缺少用户才能提供的意图或偏好，暂停等待输入；
- `Finish`：声明完成，但 Runtime 仍检查所有必要断言；
- `Escalate`：风险、冲突或不可恢复错误超出自治范围。

最大步数、时间和成本是 Blast Radius Limit（损失半径限制），不是循环根治方案。Runtime 还应检测相同 Action Signature、相同错误反复出现、状态哈希不变、没有新增证据，以及计划在两个版本之间来回切换。检测到循环后可以要求一次专门 Replan；仍无进展则停止或升级。

完成条件也必须由 Runtime 定义。模型返回 Final Answer 只说明它选择停止，不能覆盖未完成 Step、失败测试或缺少审批。相反，所有必要断言已满足时，Runtime 可以阻止模型继续无意义优化。

## 澄清、探索和升级取决于信息来源

Agent 遇到不确定性时，不应一律追问，也不应一律自主猜测。先判断缺失信息属于哪一类。

Epistemic Uncertainty（事实性不确定）指环境中存在答案，例如当前库存、API Schema 或某文件内容。只要数据源已授权、查询成本合理且结果可验证，Agent 可以先用工具探索。Preference/Intent Uncertainty（偏好或意图不确定）没有独立事实源，例如用户更看重价格还是时间、是否接受破坏兼容性的迁移；这类问题必须由用户决定。

高风险操作即使目标清晰，也可能需要 Approval。审批请求应展示计划、将发生的副作用、关键参数和可回滚性，而不是一段隐藏推理。权限不足、政策冲突、预算耗尽或连续不可恢复失败则适合 Escalate，保留当前 State 和 Trace 供人继续处理。

Anthropic 当前对可信 Agent 的描述同样强调 Plan、Act、Observe、Adjust，并在完成或需要人类输入时停止。工程难点是校准暂停频率：每一步都询问会失去自治价值，从不询问则会把模型假设变成现实副作用。权限等级、可逆性和信息来源比模型自报的置信百分比更可靠。

## Reasoning Effort 是资源旋钮，不是控制平面

Reasoning Model 可以在输出前投入更多 Test-time Computation。具体 API 可能提供 Effort、Mode 或 Reasoning Token 选项，但取值和默认值属于模型版本能力，不是统一协议。较高设置可能改善需要多步推导、搜索和验证的任务，也会增加延迟、Token 和成本，并不保证简单任务更正确。

以 2026-07-22 的 OpenAI Model Guidance 为例，官方建议在代表性任务上比较不同 Reasoning 配置，并同时测量任务成功、证据完整性、Token、延迟和成本，而不是假设最高配置总是最佳。正文不复制当前枚举，因为模型名称和参数支持会变化。

模型 Reasoning 与 Agent Planning 的区别可以从控制权看出：Effort 决定一次模型调用内部可投入多少计算；Plan/Runtime 决定跨调用执行哪些动作、如何使用工具结果、何时审批和终止。提高前者不能替代后者。

常见路由策略是先按任务特征选择低成本基线，对已被 Eval 证明受益的复杂任务提高 Effort；工具返回新信息后再调用模型，而不是一次高 Effort 猜完整个未知环境。变更模型或 Effort 时保持同一任务集、工具和控制策略，才能隔离真实收益。

## 评测同时检查 Transcript 与 Environment Outcome

一份语言流畅的 Plan 可能执行失败，一条看似绕路的轨迹也可能安全地达到更好 Outcome。Planning Eval 因此不能只让 Judge 给计划文字打分。测试用例应定义初始 Environment、用户目标、硬约束、允许工具、预算、可注入故障和最终成功断言。

过程指标可以包括：计划依赖合法率、关键约束覆盖率、无效/重复 Action 数、Replan 次数、首次有效动作时间、审批违规、澄清是否必要、终止原因和每个 Step 的验证通过率。结果指标检查真实 Environment Outcome、用户目标完成度、是否产生禁止副作用，以及恢复或补偿是否完成。

Agent 输出具有随机性，同一 Task 要运行多个 Trial，报告成功率和分布，而不是只展示最佳轨迹。代码 Grader、模型 Grader 与人工 Grader 各自适合不同断言；高风险语义 Judge 需要用人工样本校准。第 08 章的 Eval Harness 与第 09 章 Trace 在这里结合：Eval 定义正确，Trace 说明每次 Decision 为什么被允许、执行后观察到什么以及失败在哪里传播。

最小回归集至少覆盖：

- 依赖未完成时模型请求后续动作，Runtime 必须拒绝；
- 工具返回可重试与不可重试错误，Agent 采取不同策略；
- 相同动作没有进展地重复，循环检测早于最大步数触发；
- 高风险动作在执行前暂停，审批拒绝不会产生副作用；
- 模型提前声称完成，但 Environment Assertion 尚未通过；
- 缺失事实可由工具获得，缺失偏好则向用户澄清；
- 提高 Reasoning Effort 的质量收益是否覆盖额外延迟与成本。

## 最小实现验证外层控制不变量

本章示例 [`decision_controller.py`](../../examples/12-planning-reasoning-control/decision_controller.py) 使用标准库实现 Plan DAG 校验和结构化 `Act`、`Replan`、`Ask`、`Finish`、`Escalate`。模型侧只提供不超过 240 字符的 `observable_basis`，不请求隐藏 Chain-of-Thought。

Runtime 在工具执行前检查依赖、Allowlist、高风险审批、估算成本、Tool Call Budget 和重复 Action；执行后由 Observation 与外部 Evaluator 决定 Step 是否完成：

```python
accepted = observation.success and evaluate(
    self._step_by_id(plan, decision.step_id), observation
)
if accepted:
    plan = self._set_step_status(plan, decision.step_id, "completed")
```

11 项测试验证依赖环和未知依赖、成功计划、越序动作、提前 Finish、高风险暂停、重复动作、成本预算、失败后 Replan、结构化澄清和 Decision 上限。示例只建模单进程控制；跨进程持久化、Timer、Queue、Exactly-once 语义的局限与补偿事务将在第 13 章继续展开。

## 参考资料

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)，Yao 等，ICLR 2023；用于核对面向任务的推理与 Action 交错、外部 Observation 更新计划和处理异常的原始方法；最后核验日期：2026-07-22。
- [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366)，Shinn 等，NeurIPS 2023；用于核对语言 Reflection、任务反馈与 Episodic Memory Buffer 对后续 Trial 的作用，并区分于权重更新；最后核验日期：2026-07-22。
- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)，Anthropic 官方工程文章；用于核对 Workflow/Agent 边界、Evaluator-Optimizer、环境 Ground Truth、停止条件和 Agent 复杂度取舍；最后核验日期：2026-07-22。
- [Trustworthy agents in practice](https://www.anthropic.com/research/trustworthy-agents)，Anthropic 官方研究文章；用于核对 Plan—Act—Observe—Adjust 循环、澄清、人工控制和高风险决策边界；最后核验日期：2026-07-22。
- [Model guidance](https://developers.openai.com/api/docs/guides/latest-model)，OpenAI API 官方文档；用于核对当前模型特定 Reasoning 配置的质量、Token、延迟和成本评测原则；最后核验日期：2026-07-22。
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)，Anthropic 官方工程文章；用于核对 Task、Trial、Transcript、Outcome、Grader 与多 Trial Agent Eval 结构；最后核验日期：2026-07-22。
