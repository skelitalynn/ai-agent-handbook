# 00｜AI Agent 系统全景与学习地图

> 本章先给出一张可以贯穿全书的系统骨架：用户目标如何进入 Agent Runtime，模型如何提出回答或行动，工具如何改变外部环境，State 与 Context 如何连接每一轮，以及 Evals、Tracing、Reliability 和 Security 为什么必须包围整个执行过程。后续章节不是重新发明一套术语，而是逐层展开这张图中的组件。

## 1. 先建立完整系统，再学习局部概念

学习 Agent 最容易走入两个极端：一种从 Transformer 开始不断向下钻，却不知道模型最终如何进入业务系统；另一种直接学习框架、MCP、Memory 和 Multi-Agent，记住很多产品名，却没有一张图说明它们为什么存在。

本书采用相反的顺序：先观察一个最小但完整的 Agent，再逐层拆解。读者暂时不需要知道每个组件的全部实现，只需要先回答三个问题：信息从哪里来，谁能改变外部世界，系统如何知道应该继续还是结束。

一个 Agent Run 的最小闭环是：

```text
用户提出目标
   ↓
系统构造本轮 Context
   ↓
调用模型
   ↓
模型返回最终答案或行动请求
   ├── 最终答案 → 校验结果 → 完成
   └── 行动请求
         ↓
      校验并执行工具
         ↓
      获得环境观察
         ↓
      更新 State
         ↓
      判断继续、失败、暂停或人工介入
         └──────────────→ 下一轮 Context
```

这条循环已经包含后续大部分主题：Prompt 影响模型如何理解目标，Tool Calling 表达行动，State 保存运行事实，Context Engineering 决定模型看到什么，RAG 和 Memory 提供外部信息，Planning 影响下一步决策，Workflow 约束路径，Runtime/Harness 承担执行控制，Evals 和 Trace 判断系统是否有效。

## 2. 什么样的系统才需要 Agent

“使用了 LLM”不是判断标准。更有用的标准是：模型是否在运行时控制了执行过程中的重要选择，并且这些选择是否会根据环境观察动态改变。

| 系统形态 | 路径由谁决定 | 是否与环境形成多轮闭环 | 典型场景 |
|---|---|---:|---|
| 普通代码 | 代码完全决定 | 否 | 权限判断、金额计算、状态转换 |
| 单次 LLM 调用 | 代码决定调用，模型只生成一次结果 | 否 | 摘要、分类、改写、结构化抽取 |
| LLM Workflow | 代码预先定义主要步骤，模型处理局部语义任务 | 可能有，但路径主要固定 | 审核流水线、路由、生成后校验 |
| Agent | 模型根据目标、State 和观察动态选择部分步骤或工具 | 是 | 开放式研究、编码、复杂支持任务 |
| Multi-Agent System | 多个独立执行者协作、委派或并行探索 | 是 | 上下文隔离、权限分离、大规模并行探索 |

这些形态是一条连续谱，而不是互斥标签。生产 Agent 往往把确定性 Workflow 作为外框，只在确实需要语义判断和动态探索的位置交给模型。

判断是否值得引入 Agent，可以从任务约束出发：

- 路径是否难以预先穷举，需要根据中间结果调整？
- 任务是否依赖非结构化信息和语义判断？
- 系统是否拥有足够清晰、安全且可观察的工具？
- 是否能够定义成功、失败、预算和人工介入条件？
- Agent 相比规则、搜索、Workflow 或人工流程，是否带来可评测的收益？

如果最后两个问题无法回答，项目通常还没有准备好增加自治程度。

## 3. 一张贯穿全书的 Agent 架构图

下面的架构图不是某个框架的类图，而是厂商无关的职责划分。读者应重点观察两条边界：模型只产生候选输出；Runtime 才能通过工具改变外部环境。

```text
                         用户与业务目标
                               ↓
┌──────────────────────────────────────────────────────────┐
│                    Agent Application                     │
│                                                          │
│  API / UI · 身份入口 · 进度展示 · 人工审批 · 最终结果       │
└──────────────────────────┬───────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────┐
│                      Agent Runtime                       │
│                                                          │
│  ┌──────────────┐      ┌────────────────┐                │
│  │ State Store  │ ───→ │ Context Builder│                │
│  │ / Session    │      └───────┬────────┘                │
│  └──────↑───────┘              ↓                         │
│         │              ┌────────────────┐                │
│         │              │ Model Gateway  │                │
│         │              └───────┬────────┘                │
│         │                      ↓                         │
│         │            文本 / 结构化结果 / Tool Call        │
│         │                      ↓                         │
│  ┌──────┴───────┐      ┌────────────────┐                │
│  │ Loop Control │ ←─── │ Tool Executor  │                │
│  │ / Workflow   │      └───────┬────────┘                │
│  └──────────────┘              ↓                         │
│                       Sandbox / External Systems          │
│                                                          │
│  Policy · Budget · Retry · Checkpoint · Trace             │
└──────────────────────────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ↓            ↓            ↓
           Evals       Observability   Security
                                     Reliability
```

### Application 与 Runtime

Application 面向用户和业务，负责身份入口、交互、结果展示和产品规则。Runtime 面向执行过程，负责组织模型调用、工具分发、状态变化和循环控制。同一个 Runtime 可以被 CLI、Web、IDE 或后台任务使用；同一个产品也可能根据任务选择不同 Runtime。

### Model Gateway

Model Gateway 负责把业务请求映射到具体模型服务，并保留类型化输出、停止原因、Usage、请求 ID 和错误。模型不是数据库或权限系统，它只根据可见 Context 生成文本、结构化对象或行动请求。

### Tool Executor 与 Environment

Tool Executor 将模型提出的行动映射到真实函数、API、文件系统、浏览器或 Sandbox。Environment 是行动发生并留下结果的世界，可能是数据库中的订单状态、代码仓库、浏览器页面或模拟环境。工具结果必须作为观察写回系统，模型才能根据真实结果调整下一步。

### Loop Control 与 Workflow

Loop Control 决定本轮之后是继续、完成、失败、暂停、取消还是交给人工。Workflow 可以用状态机、条件分支、队列和确定性代码约束执行路径。模型可以参与决策，但不应成为唯一的预算、权限和终止控制器。

## 4. State、Context、History 与 Memory

这四个词经常被混用，但它们属于不同层级。

| 概念 | 回答的问题 | 典型内容 | 是否必须全部交给模型 |
|---|---|---|---:|
| State | 系统现在真实处于什么状态 | 当前步骤、工具结果、预算、审批、任务产物 | 否 |
| Session | 哪些状态属于同一段交互或任务 | 用户、会话 ID、Run、Checkpoint | 否 |
| History | 过去发生了哪些交互 | 用户消息、模型输出、工具调用和结果 | 否 |
| Context | 本轮模型能够看到什么 | 指令、选定历史、工具定义、检索片段 | 是 |
| Memory | 哪些信息值得跨轮次或跨会话保存并召回 | 用户偏好、事件、事实、工作方法 | 召回后的相关部分才需要 |

最重要的方向是：

```text
完整 State + 外部知识 + 规则
             ↓ 选择、压缩、排序、隔离
          本轮 Context
             ↓
          模型输出
             ↓ 校验和执行
          更新 State
```

因此 Context 不是 State 的别名，也不是把全部历史拼接起来。State 应可持久化、审计和恢复；Context 受窗口、相关性、权限和成本限制。Memory 也不是越多越好，它需要明确的写入、更新、冲突、召回和删除策略。

## 5. 谁来做决定：模型还是代码

Agent 工程的核心不是让模型控制一切，而是把不同类型的决策交给合适的执行者。

| 更适合模型 | 更适合确定性代码 |
|---|---|
| 理解自然语言意图 | 身份认证和权限判断 |
| 在开放选项中提出候选方案 | 金额、计数和精确计算 |
| 判断非结构化内容的语义相关性 | Schema、类型和业务不变量校验 |
| 根据观察选择可能的下一步工具 | 幂等键、副作用去重和事务 |
| 生成解释、草稿和计划 | 超时、最大步数和成本预算 |
| 处理难以穷举的模糊情况 | 状态转换、审计和合规策略 |

这条边界不是固定不变的。某个模型判断只有在代表性任务上达到可接受质量、失败能够检测、代价能够承受时，才适合进入自动路径。高风险操作即使模型选择准确，也可能仍需要人工审批。

隐藏思维链也不是系统控制接口。Runtime 应依赖可观察的 Tool Call、计划、证据、测试结果和状态变化，而不是要求模型暴露完整内部推理过程。

## 6. 最小 Agent Loop

下面的代码不绑定任何厂商 SDK，只保留 Agent 的结构。`call_model` 返回最终文本或 Tool Call，Runtime 负责查找、校验和执行工具，再把观察加入历史。

```python
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelTurn:
    final_text: str | None
    tool_calls: list[ToolCall]


CallModel = Callable[[list[dict[str, Any]]], ModelTurn]
ToolHandler = Callable[..., Any]


def run_agent(
    user_input: str,
    *,
    call_model: CallModel,
    tools: dict[str, ToolHandler],
    max_steps: int = 8,
) -> str:
    history: list[dict[str, Any]] = [
        {"role": "user", "content": user_input},
    ]

    for step in range(max_steps):
        turn = call_model(history)
        history.append({"role": "assistant", "turn": turn})

        if turn.final_text is not None and not turn.tool_calls:
            return turn.final_text

        if not turn.tool_calls:
            raise RuntimeError("model returned neither an answer nor a tool call")

        for tool_call in turn.tool_calls:
            handler = tools.get(tool_call.name)
            if handler is None:
                observation = {"error": "unknown_tool"}
            else:
                try:
                    # Production code validates schema, identity, permission,
                    # budget, idempotency and approval before execution.
                    result = handler(**tool_call.arguments)
                    observation = {"result": result}
                except Exception as error:
                    observation = {"error": type(error).__name__}

            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": observation,
                }
            )

    raise RuntimeError("agent exceeded its step budget")
```

这段代码展示了五个不可省略的事实：模型输出需要解析；工具由 Runtime 执行；工具结果必须写回；循环需要显式终止；错误必须转成系统可以处理的状态。

它仍不是生产实现。真实 Runtime 还要处理异步和并行、参数 Schema、认证授权、超时取消、重试与幂等、部分成功、Checkpoint、上下文预算、Streaming、Trace 和人工审批。后续章节会逐一把这些占位注释变成可验证实现。

## 7. 一次 Run 的执行顺序

架构图说明“有哪些组件”，下面的时序图说明“谁在什么时候做什么”。重点观察：工具结果先回到 Runtime 和 State，再由下一轮 Context 送给模型；外部系统不应直接伪装成高权限指令。

```text
User        Application      Runtime        Model        Tool        Environment
 │               │              │              │            │              │
 │──提出目标────→│              │              │            │              │
 │               │──创建 Run───→│              │            │              │
 │               │              │──构造 Context→│            │              │
 │               │              │──调用模型────→│            │              │
 │               │              │←──Tool Call───│            │              │
 │               │              │──校验参数与权限│            │              │
 │               │              │────────────执行 Tool──────→│              │
 │               │              │              │            │──改变/读取──→│
 │               │              │              │            │←──结果────────│
 │               │              │←────────Observation────────│              │
 │               │              │──更新 State  │            │              │
 │               │              │──下一轮 Context→           │              │
 │               │              │──调用模型────→│            │              │
 │               │              │←──最终回答────│            │              │
 │               │←──完成 Run───│              │            │              │
 │←──展示结果────│              │              │            │              │
```

如果 Tool Call 具有副作用，网络超时后不能简单假设“没有执行”。Runtime 需要业务请求 ID、幂等键或查询状态的方法。若模型在工具失败后继续循环，也必须消耗统一的步数、时间和成本预算。

## 8. Trace、Outcome 与 Evals

普通聊天产品可能只保存最终文本，Agent 还会改变外部环境。评估“回答说已经完成”远远不够，真正的 Outcome 是环境是否达到目标状态。

一次 Run 至少需要关联：

- 输入目标、身份、模型和 Prompt 版本
- 每轮 Context 或其可审计引用
- 模型输出、停止原因和 Usage
- Tool Call、参数、权限决策、执行结果和耗时
- State 转换、Checkpoint、错误和重试
- 最终状态、外部副作用和人工介入

这些信息组成 Trace。Trace 用于定位失败，Eval 则定义成功标准并对结果评分：

```text
Task：输入、环境和成功标准
   ↓
Trial：执行一次 Agent Run
   ↓
Trace：记录模型、工具和状态轨迹
   ↓
Outcome：检查环境最终状态
   ↓
Grader：计算任务成功、质量、安全、成本和延迟
   ↓
Regression：模型、Prompt、Tool 或 Runtime 变化后重新运行
```

最终答案正确但执行了越权工具，不算成功；调用轨迹看起来合理但数据库没有产生预期记录，也不算成功。Evals 和 Tracing 必须在系统复杂化之前建立，否则增加 RAG、Memory、Planning 或 Multi-Agent 后，只会得到更多无法解释的波动。

## 9. 从最终失败反查责任层

“Agent 失败了”不是可操作的诊断。应先定位失败发生在哪一层，再选择修复手段。

| 责任层 | 典型症状 | 应检查的证据 |
|---|---|---|
| 任务定义 | 不同评审对正确结果理解不同 | 成功标准、样例、边界和禁止行为 |
| Context | 模型没有看到关键规则或证据 | 实际提交内容、裁剪、权限和顺序 |
| Model | 工具选择或语义判断反复错误 | 固定版本、输出类型、任务切片和多次试验 |
| Tool Schema | 参数经常缺失、混淆或无法表达任务 | 工具名、描述、字段约束和错误反馈 |
| Tool Runtime | 超时、部分执行、重复副作用 | 请求 ID、幂等记录、外部状态和错误日志 |
| State | 工具已成功但下一轮仍重复调用 | 状态写入、事务、Checkpoint 和 Context 投影 |
| Loop Control | 死循环、提前结束或预算失控 | 步数、终止原因、重复检测和预算事件 |
| Output Validation | JSON 合法但业务字段错误 | Schema、业务不变量、引用和验证器结果 |

更强的模型可能改善模型层问题，却不会自动修复权限、幂等、状态事务和模糊成功标准。相反，如果工具始终返回缺失数据，继续修改 Prompt 也不会创造真实观察。

## 10. 全书怎样填充这副骨架

本书不是把 Agent 术语平铺成百科目录，而是让系统能力逐步增长。

```text
第 00 章：看到完整 Agent 系统
   ↓
第一篇：理解并实现一次受控模型生成
   ↓
第二篇：形成 Tool + State + Context 的单 Agent 闭环
   ↓
第三篇：建立 Evals 和 Trace
   ↓
第四篇：加入 RAG 与 Memory
   ↓
第五篇：处理 Planning、Workflow、人工和 Multi-Agent
   ↓
第六篇：理解 Runtime、Harness、Framework、MCP、Skills、A2A
   ↓
第七篇：组合产品架构、多模态、实时和环境操作
   ↓
第八篇：完成可靠性、安全和生产部署
```

| 学习阶段 | 学完后应能完成的事情 |
|---|---|
| 模型与单次生成 | 解释从文本到输出的计算链，实现带 Usage、停止原因和验证的模型客户端 |
| Agent 闭环 | 实现工具校验、状态更新、上下文预算和明确终止的单 Agent |
| 评测与观测 | 建立任务集、评分规则和完整 Trace，能够定位失败层 |
| 知识与记忆 | 建立有权限、引用和回归测试的 RAG，并设计 Memory 生命周期 |
| 复杂控制 | 判断何时使用 Planning、Workflow、人工介入或 Multi-Agent |
| Runtime 与协议 | 透过框架识别底层职责，判断 API、MCP、Skill 和 A2A 的边界 |
| 产品与生产 | 处理交互、异步任务、可靠性、安全、容量、成本和部署 |

第一次阅读时应严格按 `SUMMARY.md` 推进。已有经验的读者可以先用 [全局知识地图](../../docs/KNOWLEDGE_MAP.md) 定位薄弱组件，再回到对应章节补齐前置依赖。面试复习则从 `SUMMARY.md` 进入对应正文的面试层，不改变教材正文顺序。

## 常见误区

### Agent 等于一个更强、更自主的模型

自治程度来自模型能力与 Runtime 授予的工具、权限、循环和环境共同作用。更强模型不会自动获得数据库访问权，也不会自动具备安全终止和状态恢复。

### 工具越多，Agent 能力越强

工具数量增加会扩大选择空间、上下文占用和权限风险。工具应有清晰边界、可区分描述、结构化参数、稳定错误语义和独立评测；不相关工具应按需发现或加载。

### 把全部历史放进 Context 就不会丢状态

历史文本不是可靠状态存储。它可能被截断、压缩、误读或超出窗口，业务状态应保存在模型上下文之外，再按本轮需要投影给模型。

### 设置最大步数就解决了死循环

最大步数只限制损失。仍需检查工具结果不足、State 未更新、重复调用检测失效、模型没有合法退出路径或成功标准不明确。

### 先选一个 Agent Framework，再学习底层概念

框架会把 Loop、State、Tool、Checkpoint 和 Trace 包装成自己的对象。若不了解这些机制，读者只能记 API，无法判断抽象是否适合任务，也难以在失败时定位责任层。

## 学习检查

读完本章后，应当能够：

1. 不依赖框架名，画出一个包含 Application、Runtime、Model、Tool、State、Context 和 Environment 的 Agent 架构图。
2. 沿一次 Run 解释目标、模型调用、Tool Call、观察、状态更新和终止的顺序。
3. 区分 State、Session、History、Context 和 Memory。
4. 为一个业务步骤判断应该使用模型、确定性代码、Workflow 还是人工审批。
5. 根据 Trace 判断错误更可能来自 Context、Model、Tool、State 还是 Loop Control。
6. 说明为什么 Evals、Tracing、Reliability 和 Security 必须贯穿整个 Agent 生命周期。
7. 把后续每一篇知识挂回本章的系统骨架，而不是把它当成孤立名词。

## 参考资料与结论对应关系

- [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)，Anthropic，用于核对 Workflow 与 Agent 的控制边界、从简单可组合模式开始以及 Routing、Parallelization、Orchestrator-Workers、Evaluator-Optimizer 等模式的定位，最后核验日期：2026-07-22。
- [A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)，OpenAI，用于核对 Agent 代表用户独立完成任务、模型控制工作流执行，以及模型、工具、指令和编排是 Agent 设计基础，最后核验日期：2026-07-22。
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)，Yao 等，用于核对推理、行动与环境观察交错的任务轨迹；正文没有把自由文本思维链作为 Runtime 的必要接口，最后核验日期：2026-07-22。
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)，Anthropic，用于核对多轮 Agent 会调用工具、修改状态并根据中间结果调整，以及 Task、Trial、Trace、Outcome、Grader 和 Evaluation Harness 的区分，最后核验日期：2026-07-22。
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)，OpenAI，用于核对环境、工具、反馈循环、可观测性和结构化知识对长时间 Agent 工作的作用；其中具体生产数据仅属于该案例，正文没有将其外推为通用性能结论，最后核验日期：2026-07-22。
