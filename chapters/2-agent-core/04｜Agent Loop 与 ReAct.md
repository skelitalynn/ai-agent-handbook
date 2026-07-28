# 04｜Agent Loop 与 ReAct

> 前三章解决了一次模型调用如何产生受控输出；本文把单次调用扩展成“模型决策—执行行动—接收观察—再次决策”的闭环。学完后，读者应能解释 ReAct 与现代 Tool Calling 的关系，实现一个具有类型化决策、明确终态、执行预算、重复调用检测和 Trace 的最小 Agent Runtime。工具契约在第 05 章展开，持久化状态在第 06 章展开，复杂规划与工作流分别在第 12、13 章展开。

## 面试速记

### 背诵提纲

**1. 定义**

Agent Loop 是由 Runtime 驱动的迭代控制过程：模型根据当前任务和 Observation 决定下一步，Runtime 执行工具并写回结果，循环直到完成、暂停、失败或预算耗尽。

**2. 完整执行链**

```text
用户请求 → 调用模型 → 最终答案？ ── 是 → 校验并完成
                      └── 否 → 工具调用？ ── 是 → 校验并执行工具
                                             → 写回 Observation → 再次调用模型
                              └── 需要用户输入 → 保存状态并暂停
任一步骤触发错误、取消或预算上限 → 失败、降级或安全停止
```

**3. ReAct**

ReAct 的核心是让推理与行动交错进行：模型依据当前信息选择 Action，环境返回 Observation，模型再据此更新后续决策；现代实现通常用类型化 Tool Call 和运行状态承载这一闭环，不要求公开完整思维链。

**4. 模型决策契约**

- **Tool Call**：模型提出工具名和参数，但不直接执行工具。
- **Final Answer**：模型声明任务已得到可交付结果，仍需通过输出和业务校验。
- **Need User Input**：信息不足或需要审批时请求暂停，而不是猜测或继续行动。

**5. Runtime 的职责**

Runtime 负责校验决策、执行工具、关联调用与结果、更新历史、控制权限和并发，并依据步数、时间、成本、取消和错误等确定性规则控制生命周期。

**6. Observation 与进展**

Observation 是环境对 Action 的结构化反馈，应明确成功、输出和错误并准确写回；只有状态发生了与目标相关的变化，循环才算取得进展。

**7. 终止与暂停**

完成要求最终输出有效且没有待执行行动；最大步数、截止时间、成本预算、取消和不可恢复错误属于硬停止，缺少输入或等待审批属于可恢复暂停。

**8. 循环故障**

重复工具与参数、不同动作交替但状态不变、工具错误反复重试和 Observation 未写回都是无进展循环；最大步数只能限制损失，根因仍需通过 Trace 和进展检测定位。

**9. 适用边界**

步骤固定、规则明确且结果要求高度可预测时优先使用普通代码或确定性 Workflow；只有路径难以预先枚举、环境反馈会改变下一步且收益覆盖额外成本与风险时，才适合 Agent Loop。

### 高频对比

| 维度 | Agent Loop | 确定性 Workflow |
|---|---|---|
| 下一步由谁决定 | 模型在运行时依据上下文决定 | 代码按预定义节点和条件决定 |
| 执行路径 | 步数与路径难以预先枚举 | 路径有限且可以显式审查 |
| 灵活性 | 高 | 受代码定义限制 |
| 可预测性与测试难度 | 较低，需轨迹与统计评测 | 较高，可逐分支测试 |
| 延迟与成本 | 常有多次模型和工具调用 | 通常更容易估算和控制 |
| 典型场景 | 开放式检索、编码、动态排障 | 审批流、固定数据处理、规则明确的业务流程 |

### 高频问题

#### 问题1：如何判断 Agent Loop 应该终止？

同时检查模型是否给出有效最终答案、是否仍有待执行行动，以及最大步数、时间、成本、取消、不可恢复错误和人工审批状态。不能只依赖模型自行声称任务完成。

#### 问题2：为什么设置最大步数仍然不能彻底解决死循环？

最大步数只是限制最坏损失，不能修复 Observation 丢失、状态未更新、工具结果不足、重复检测失效或目标不明确等根因。仍需用 Trace 和进展指标定位循环为何没有推进。

#### 问题3：多个工具调用什么时候可以并行？

工具之间没有数据依赖、共享状态冲突和不可控副作用时才可以并行；还要考虑幂等性、外部限流、成本预算以及结果如何按调用 ID 合并回上下文。

#### 问题4：什么情况下不应该使用 Agent Loop？

执行步骤固定、分支可枚举、规则明确且结果要求高度可预测时，应优先使用普通代码或确定性 Workflow。引入模型动态决策只会增加延迟、成本、评测难度和失控风险。

#### 问题5：如何判断一次 Agent 失败是模型问题还是工具问题？

查看完整 Trace：模型是否选择了正确工具和参数，Runtime 是否正确校验与路由，工具是否返回成功且 Observation 是否原样写回，模型收到结果后是否合理决策。只看最终答案无法定位故障层。

---

## 1. 先看完整 Run：模型提出行动，Runtime 控制循环

前三章中的模型调用到返回结果就结束。现在考虑一个无法靠模型参数直接回答的任务：

> 查明订单 A-17 为什么还没有发货，并告诉用户下一步应该怎么办；只能读取信息，不能修改订单。

模型一开始既不知道订单状态，也不知道库存和地址是否有效。它必须先查询环境，再根据查询结果决定下一步。一次可用的执行不能只是“让模型持续思考”，而要形成下面这条闭环：

```text
用户请求
   ↓
┌──────────────────────── Agent Runtime ────────────────────────┐
│ Run State：历史、预算、待处理调用、取消信号、当前状态          │
│                                                               │
│  调用模型                                                     │
│     ↓                                                         │
│  类型化决策                                                   │
│     ├── FinalAnswer ─→ 输出校验 ─→ COMPLETED                  │
│     ├── NeedUserInput ─→ 保存现场 ─→ INTERRUPTED              │
│     └── ToolCall                                              │
│            ↓                                                  │
│       工具存在？参数有效？权限允许？预算足够？                 │
│            ├── 否 ─→ Observation 或 FAILED                    │
│            └── 是                                             │
│                  ↓                                            │
│              执行工具 ───────────────→ 外部环境               │
│                  ↑                        │                    │
│                  └──── 结果或错误 ────────┘                    │
│                         ↓                                     │
│                  ToolObservation                              │
│                         ↓                                     │
│                  写入历史与状态                               │
│                         └────────────→ 再次调用模型            │
└───────────────────────────────────────────────────────────────┘

任一步骤触发取消、截止时间、预算上限或不可恢复错误
   → CANCELLED 或 FAILED
```

这张图先确定各组件的位置。模型位于循环中的“决策点”，只提出下一步；工具位于外部环境的执行边界；Observation 把环境事实带回循环；Runtime 包住整个过程，持有状态、预算和终止权。模型没有直接访问数据库，也不能自行把 Run 标记为成功。

从初始请求到某个终态的一次完整执行称为 **Run**。一次模型决策可以记作一个 **Step**，但不同 SDK 对 Step、Turn 或工具阶段的计数并不完全相同。工程系统因此不应只保存一个含义模糊的 `step_count`，而应分别记录模型调用数、工具调用数、耗时、Token 和成本。

本章承接第 03 章的输入与输出校验。学完本章后，读者应能实现一个进程内最小 Runtime；工具参数、安全和副作用由第 05 章展开，跨进程暂停与恢复由第 06 章展开。

## 2. 第一步：让每次模型调用落入明确的决策分支

### 2.1 先区分回答、行动和暂停

面对订单 A-17，模型还没有足够事实，直接回答只会猜测。它应该先提出：

```text
ToolCall(
  call_id = "call-1",
  tool_name = "lookup_order",
  arguments = {"order_id": "A-17"}
)
```

这是一个行动请求，不是工具执行本身。可靠 Runtime 应先把模型输出解析成封闭的决策类型，再进入不同分支：

```text
模型响应
   ↓
Runtime 解析并检查响应是否完整
   ↓
类型化决策
   ├── ToolCall / ToolCall[]
   │      ↓
   │   行动候选
   │      ↓
   │   工具、参数、权限与预算校验
   │      ├── 通过 → 执行工具 → Observation → 进入下一次模型决策
   │      └── 拒绝 → 错误 Observation 或 FAILED
   │
   ├── FinalAnswer
   │      ↓
   │   输出与业务成功条件校验
   │      ├── 通过 → COMPLETED
   │      └── 失败 → 恢复、重新决策或 FAILED
   │
   ├── NeedUserInput
   │      ↓
   │   保存当前 Run State → INTERRUPTED
   │
   └── Refusal / 策略阻断
          ↓
       安全结束或转人工
```

观察这张图，只有 Runtime 有权把“模型提出的内容”转换成真实执行或系统状态。`ToolCall` 分支会绕回下一次模型决策；其他分支则可能形成完成、暂停或安全结束，但仍要先通过对应的确定性检查。

| 决策 | 解决的问题 | Runtime 的下一步 | 是否结束当前 Run |
|---|---|---|---|
| `ToolCall` | 需要外部事实或动作 | 校验并执行，形成 Observation | 否 |
| `FinalAnswer` | 模型认为已有可交付结果 | 校验输出和业务成功条件 | 通过后完成 |
| `NeedUserInput` | 缺少信息或等待审批 | 保存当前状态并返回问题 | 暂停 |
| `Refusal` 或策略阻断 | 请求不能继续 | 按产品策略安全结束或转人工 | 通常结束 |

如果用户只说“查一下我的订单”却没有订单号，正确分支是 `NeedUserInput`，而不是猜一个 ID 或调用无效工具。如果模型给出文字的同时仍附带待执行 Tool Call，Runtime 也不能因为“已经有文本”就宣布完成。

为了突出最小闭环，本章示例每个 Step 只处理一个 `ToolCall`。真实模型响应也可能在行动分支中包含多个调用；每个调用仍需独立的 `call_id` 和校验结果，Runtime 再根据第 5 节的依赖条件决定串行或并行。

类型化决策只解决“模型提出了什么”，不证明这个决定可以执行。工具是否存在、参数是否符合 Schema、调用者是否有权限以及写操作是否需要审批，都必须由 Runtime 和工具层检查。

### 2.2 ReAct 的关键是让环境反馈进入下一次决策

只生成推理文本时，模型无法取得订单的当前状态；只生成行动而不读取结果时，后续步骤又无法依据现实更新。ReAct 论文把推理与行动交错起来：

```text
Reason：根据目标和已有事实判断下一步
   ↓
Action：向环境提出一个动作
   ↓
Observation：环境返回结果或错误
   ↓
Reason：依据新事实更新下一步
   ↓
继续行动，或者给出最终答案
```

真正形成闭环的是 `Action → Observation → 下一次决策`，不是三个英文标签。若 `lookup_order` 已经成功，但 Runtime 没有把结果写入模型下一次可见的历史，模型仍然只能基于旧信息猜测或重复查询。

原始 ReAct 实验常用 `Thought → Action → Observation` 文本轨迹。现代实现可以使用类型化 Tool Call、调用 ID 和工具结果表达同一控制关系，不要求把完整思维链写进日志或展示给用户。应用真正需要审计的是：模型选择了什么行动、Runtime 是否允许、工具返回了什么、状态如何变化，以及 Run 为什么结束。

到这里，模型的职责已经被限制为“提出一种决策”。下一步由 Runtime 判断这个决策能否转化成真实行动。

## 3. 第二步：Runtime 把 Tool Call 变成可信 Observation

### 3.1 先校验，再执行

收到 `lookup_order` 后，Runtime 不能把模型生成的工具名和参数直接转发给数据库。它至少要依次处理：

```text
收到 ToolCall
   ↓
call_id 是否唯一且可以关联？
   ↓
工具是否存在？
   ↓
参数是否满足工具 Schema？
   ↓
权限、审批和风险策略是否允许？
   ↓
超时、重试和调用预算是否足够？
   ↓
执行工具
```

订单案例中的工具是只读查询，因此可以在参数和权限通过后执行。假设环境返回：

```text
ToolObservation(
  call_id = "call-1",
  tool_name = "lookup_order",
  ok = true,
  output = {
    "status": "paid",
    "sku": "P-9",
    "address_id": "ADR-4",
    "shipment_id": null
  }
)
```

`call_id` 把结果与原 Tool Call 关联起来；`ok` 区分成功与失败；`output` 只保留后续决策需要的字段。若工具超时，Runtime 应返回明确的错误 Observation，而不是伪装成 `shipment_id = null`。前者表示基础设施失败，后者表示查询成功但尚未生成物流单，两者会导向完全不同的下一步。

工具失败通常可以先写回模型，让它决定换参数、换工具或解释暂时不可用。但鉴权配置错误、预算耗尽、策略拒绝和不可恢复的数据损坏不应无限交给模型重试，Runtime 可以直接失败或转人工。

### 3.2 Observation 必须进入状态，而不只是拼进一段文本

Runtime 收到订单 Observation 后，要同时做三件事：

1. 将结构化结果写入模型下一次可见的历史；
2. 更新本地 Run State，例如已取得订单、仍缺少发货原因；
3. 记录 Trace，使后续能够证明模型实际看到了哪些事实。

模型现在知道订单已支付、没有物流单，并取得了商品和地址标识。它可以继续提出两个读取行动：

```text
check_inventory(sku="P-9")
validate_address(address_id="ADR-4")
```

如果 Runtime 只把工具原始 JSON 随意拼进 Prompt，没有成功状态、调用关联或大小限制，模型就可能把错误当空结果、把旧结果当新结果，或被无关字段淹没。Observation 是运行协议的一部分，不是“补充一点上下文”。

### 3.3 只有目标相关状态变化才算进展

工具成功不等于任务有进展。对订单排查来说，下面这些变化才有意义：

- 获得订单当前状态；
- 排除库存不足；
- 发现地址缺少邮编；
- 确认没有待执行的查询；
- 得到足以向用户解释原因的证据。

如果模型连续调用 `lookup_order(order_id="A-17")`，每次都得到相同结果，历史虽然越来越长，任务状态却没有变化。Runtime 可以用工具名与规范化参数形成调用签名，并结合新增记录 ID、未解决约束数量或业务版本号检测无进展。

无进展也可能表现为两个行动来回振荡、同一错误类别反复出现，或模型完全忽略已经写回的 Observation。模型可以评估语义进展，但它不能取代 Runtime 的重复阈值、预算和硬停止。

到这里，外部事实已经通过 Observation 进入下一次模型决策。接下来必须定义什么时候继续、暂停，以及什么结果才真正算完成。

## 4. 第三步：由 Runtime 判定完成、暂停、失败和取消

### 4.1 最终文本只是完成候选

假设库存工具返回“有库存”，地址工具返回“缺少邮编”。模型随后给出：

> 订单 A-17 已支付且库存正常，但收货地址缺少邮编，因此尚未创建物流单。请补充邮编后重新提交发货检查。

Runtime 仍要检查：输出是否符合第 03 章定义的 Output Contract，结论是否由 Observation 支持，是否还有待处理 Tool Call，以及任务是否违反了“只读、不修改订单”的边界。全部通过后，Run 才能进入 `COMPLETED`。

完整生命周期至少区分四种结果：

| 状态 | 触发条件 | 调用方应如何处理 |
|---|---|---|
| `COMPLETED` | 最终输出有效、没有待执行行动、满足业务成功条件 | 交付结果并保存 Trace |
| `INTERRUPTED` | 等待用户信息、审批或外部事件 | 保存可恢复状态并返回中断原因 |
| `FAILED` | 协议错误、不可恢复工具错误、无进展或预算耗尽 | 返回结构化失败和诊断信息 |
| `CANCELLED` | 用户、上游或运维系统发出取消信号 | 停止新动作，清理资源并确认副作用状态 |

暂停和失败不能混为一谈。缺少订单号时，补充信息后仍可继续；权限配置错误则必须修复系统。第 06 章会讨论怎样持久化暂停现场，本章只要求 Runtime 返回明确状态，而不是用空字符串或异常消息代替生命周期。

### 4.2 最大步数只限制损失，不证明任务正确

若 Agent 连续十次查询 A-17，把 `max_steps` 从 20 改成 5 只会让它更早失败。重复的根因可能是 Observation 没有写回、工具缺少必要字段、模型误解了错误，或者成功标准根本没有定义。

Runtime 通常需要组合多种硬限制：

- 最大模型调用数和工具调用数；
- 单工具超时和整个 Run 的截止时间；
- 输入、输出与上下文 Token 预算；
- 成本或外部配额预算；
- 相同行动及周期性行动的重复阈值；
- 外部取消信号和系统熔断状态。

这些限制解决不同问题。最大步数挡不住第一步就执行高风险错误操作；成本预算不保证按时结束；超时也不能说明远端写操作是否已经产生副作用。因此，最大步数是最后的熔断护栏，权限、幂等和审批仍要在行动执行前完成。

一个可读的终止判断顺序是：

```text
是否收到取消或触发硬预算？
   ├── 是 → CANCELLED 或 FAILED
   └── 否
        ↓
是否需要用户输入或审批？
   ├── 是 → INTERRUPTED
   └── 否
        ↓
是否存在待执行行动？
   ├── 是 → 继续执行
   └── 否
        ↓
最终输出与业务成功条件是否通过？
   ├── 是 → COMPLETED
   └── 否 → 恢复、重新决策或 FAILED
```

## 5. 第四步：Runtime 决定串行、并行，还是改用 Workflow

### 5.1 并行之前先证明行动相互独立

订单查询返回商品 `P-9` 和地址 `ADR-4` 后，库存检查与地址检查都只依赖第一次查询的结果，彼此没有数据依赖，也不修改共享资源。在外部限流和预算允许时，Runtime 可以并行执行它们：

```text
lookup_order("A-17")
   ↓
   ├── check_inventory("P-9") ───────┐
   └── validate_address("ADR-4") ────┤ 并行读取
                                      ↓
                           按 call_id 合并 Observation
                                      ↓
                                再次调用模型
```

“模型一次返回多个 Tool Call”不等于“可以并行”。安全并行至少要求：

1. 一个调用的参数不依赖另一个调用的结果；
2. 不会竞争同一可变资源，或底层已有明确并发控制；
3. 失败、超时和重试不会产生不可接受的重复副作用；
4. 外部服务限流、连接数和成本预算允许并发；
5. 每个结果保留调用 ID，合并顺序不会改变语义。

先创建工单再上传附件必须串行，因为第二步需要工单 ID；同时修改同一订单也不能因为“调用不同工具”就并行。部分成功、部分失败时，Runtime 还要规定是全部写回、只写回成功项、取消其余调用，还是执行补偿。并发库只能运行任务，不能替系统做这些语义决策。

### 5.2 路径可以预先枚举时，不要使用开放循环

如果每个订单都固定执行“查询订单—检查库存—验证地址—生成说明”，这条路径已经可以由代码完整表达。此时确定性 Workflow 更容易测试、估算成本和审查，不需要让模型每轮选择下一步。

Agent Loop 适合的是路径会被中间事实显著改变的任务。例如订单可能涉及库存、地址、支付风控、仓库故障或物流商异常，下一项检查无法在运行前完整确定。选择前可以问：

1. 下一步是否能由业务规则完整枚举？
2. 环境返回的未知信息是否会改变执行路径？
3. 模型动态选择带来的收益是否覆盖额外延迟、成本和错误风险？

高风险系统通常组合两者：

```text
确定性入口校验
   ↓
低风险 Agent Loop：读取信息、排查原因、提出方案
   ↓
确定性策略边界
   ├── 只读结果 → 自动返回
   └── 修改订单、退款或提权 → 固定审批 Workflow
```

是否调用了 LLM 不是区分标准。固定路径中可以使用模型做分类或生成；真正的区别是下一步由代码预定义，还是由模型根据 Observation 在运行时动态选择。

## 6. 把闭环写成最小 Runtime

### 6.1 代码只保留本章必须证明的机制

本章示例位于 [`examples/04-agent-loop-react/`](../../examples/04-agent-loop-react/)。模型被抽象为 `decide(history)`，只返回 `ToolCall`、`FinalAnswer` 或 `NeedUserInput`；Runtime 持有工具表、历史、重复计数和终止状态。

正文只截取实际实现中的控制主干；完整的 `RunResult` 构造、Trace 写入和辅助方法保留在示例文件中：

```python
for step in range(1, self._max_steps + 1):
    decision = self._model.decide(tuple(history))

    if isinstance(decision, FinalAnswer):
        if not decision.text.strip():
            return self._failed("empty final answer", history, trace, step)
        return RunResult(
            status="completed",
            final_answer=decision.text,
            pending_question=None,
            error=None,
            history=tuple(history),
            trace=tuple(trace),
        )

    if isinstance(decision, NeedUserInput):
        return RunResult(
            status="interrupted",
            final_answer=None,
            pending_question=decision.question,
            error=None,
            history=tuple(history),
            trace=tuple(trace),
        )

    signature = self._call_signature(decision)
    call_counts[signature] += 1
    if call_counts[signature] > self._max_identical_calls:
        return self._failed(
            f"repeated tool call: {decision.tool_name}",
            history,
            trace,
            step,
        )

    observation = self._execute(decision)
    history.append(observation)

return self._failed(
    f"maximum steps exceeded: {self._max_steps}",
    history,
    trace,
    self._max_steps,
)
```

这段代码中，模型不能直接执行工具，也不能修改 Run 状态。`execute_tool` 会把未知工具和异常统一转换成 `ToolObservation`，使模型能够看到明确失败；Observation 被加入 `history` 后，下一次决策才真正依据环境更新。

完整示例还用 `TraceEvent` 记录模型决策、工具 Observation 和终态。它故意不实现 Tool Schema、权限审批、并发、成本统计、上下文裁剪和 Checkpoint，因为这些机制分别属于后续章节。教学骨架要证明的是：

```text
模型只提出决策
   ↓
Runtime 执行确定性控制
   ↓
工具结果变成 Observation
   ↓
Observation 进入下一次决策
   ↓
Run 落入明确终态
```

### 6.2 用确定性替身测试控制流

示例使用 `ScriptedModel` 按脚本返回决策，不连接真实模型。这样，单元测试可以稳定验证 Runtime，而不会把网络和生成随机性混进控制流测试。

现有测试覆盖六条关键路径：

| 测试 | 证明的控制性质 |
|---|---|
| 工具结果在第二次决策前写回 | Observation 真正闭环 |
| 请求用户输入 | Run 可以暂停而不是猜测 |
| 相同调用超过阈值 | 重复行动会被提前停止 |
| 不同调用超过最大步数 | 硬上限能够熔断 |
| 工具异常转 Observation | 可恢复错误不会伪装成空结果 |
| 未知工具转 Observation | 协议错误对模型和 Trace 可见 |

这些测试不能证明真实模型会做出正确决策。模型质量要用第 08 章的 Evals 验证；本章只把 Runtime 的确定性职责单独测清。

## 7. 用 Trace 判断故障发生在哪一层

最终答案“查不到订单”无法解释系统为何失败。一次可诊断的 Trace 至少要记录：

```text
Run 42 / Step 1
  模型决策：lookup_order(order_id="A-17")
  Runtime：工具存在，参数与权限通过
  工具结果：timeout，耗时 3.0 s
  写回：ToolObservation(ok=false, error="timeout")

Run 42 / Step 2
  模型决策：lookup_order(order_id="A-17")
  重复检测：第 2 次，允许
  工具结果：timeout，耗时 3.0 s

Run 42 / Step 3
  模型决策：lookup_order(order_id="A-17")
  重复检测：超过阈值
  Run 终态：FAILED / no_progress
```

沿这条链，可以把失败定位到不同边界：

| 层次 | 需要查看的证据 | 可能的修复方向 |
|---|---|---|
| 模型决策 | 是否选对工具、参数是否符合任务、是否忽略 Observation | 改进上下文、工具描述、模型或决策评测 |
| Runtime | 是否正确校验和路由、call_id 是否关联、Observation 是否写回 | 修复状态转换并增加单元测试 |
| 工具与环境 | 是否超时、权限失败、契约变化或返回业务错误 | 修复适配、重试策略或外部依赖 |
| 任务与产品 | 成功标准是否明确、输入是否足够、风险边界是否缺失 | 澄清任务、请求输入、增加审批或改用 Workflow |

调试时不要只修改 Prompt。先确认模型实际看到了什么，Runtime 实际执行了什么，环境实际返回了什么，再判断问题属于哪一层。第 09 章会继续定义 Span、关联 ID、敏感信息处理和线上指标；本章只要求 Agent Loop 从第一天就产生可重建因果链的控制事件。

## 学习检查

完成本章后，应能：

- 画出 Model、Runtime、Tool、Observation 和 Run State 在 Agent Loop 中的位置；
- 区分 `ToolCall`、`FinalAnswer`、`NeedUserInput` 与系统终态；
- 解释 ReAct 的核心为何是环境反馈闭环，而不是公开完整思维链；
- 把工具结果或错误转换成可关联的 Observation，并写入下一次决策；
- 区分完成、暂停、失败和取消，组合步数、时间、成本与重复阈值；
- 根据数据依赖、共享状态和副作用判断工具能否并行；
- 判断一项任务应使用 Agent Loop、确定性 Workflow 还是二者组合；
- 用最小 Runtime 和 Trace 定位模型、Runtime、工具与任务层故障。

## 参考资料与结论对应关系

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)，Shunyu Yao 等；用于核对推理轨迹与任务行动交错、Action 从环境取得 Observation 的原始机制；最后核验日期：2026-07-22。
- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)，Anthropic Engineering；用于核对 Workflow 与 Agent 的边界、环境反馈循环、适用场景、停止条件和复合错误风险；最后核验日期：2026-07-22。
- [Running agents](https://openai.github.io/openai-agents-python/running_agents/)，OpenAI Agents SDK；用于核对模型调用、最终输出、工具结果写回、`max_turns` 和错误终态；最后核验日期：2026-07-22。
- [Results](https://openai.github.io/openai-agents-python/results/)，OpenAI Agents SDK；用于核对最终输出、运行事件、中断状态，以及流式可见最后一个 Token 不等于 Run 已完成；最后核验日期：2026-07-22。
- [A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)，OpenAI；用于核对 Run Loop 和常见退出条件；最后核验日期：2026-07-22。
- [Reasoning best practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices)，OpenAI API；用于核对推理模型不需要通过 Prompt 公开逐步 Chain-of-Thought，以及现代 Agent 应保留可观察控制信息；最后核验日期：2026-07-22。
