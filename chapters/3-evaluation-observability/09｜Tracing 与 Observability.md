# Tracing 与 Observability

> 本文建立 Agent 的可观测数据模型：用 Trace、Span、Event、Metric 和结构化 Log 还原一次 Run 的因果链，并处理跨服务传播、采样、成本和敏感内容。它为第 08 章的 Trace Grading 提供证据，也为后续可靠性与生产运维奠定基础。

## 面试速记

### 背诵提纲

**1. 定义**

Observability 是根据系统输出信号理解内部状态的能力；Tracing 通过带父子或链接关系的 Span，记录一次请求跨组件的因果执行路径。

**2. 三类信号**

Metric 适合聚合趋势和告警，Log 记录离散事件及细节，Trace 连接一次 Run 的端到端路径；三者应通过 Trace ID、Run ID 和版本字段关联。

**3. Trace 数据模型**

Trace 由多个 Span 构成，Span 至少包含 Trace ID、Span ID、Parent、名称、起止时间、Status、Attributes 与 Events；异步因果关系可使用 Link。

**4. Agent Span 层次**

Run 作为根 Span，模型调用、Context 构建、检索、工具执行、Guardrail、Handoff、Checkpoint 和审批作为子 Span；一次重试应产生独立 Attempt，不能覆盖原失败。

**5. 完整遥测链路**

```text
埋点 → 传播 Trace Context → Export → Collector 处理与采样
     → Trace / Log / Metric Backend → 查询、告警、Eval 与故障分析
```

**6. 跨边界传播**

HTTP 可使用 W3C `traceparent` 与 `tracestate`，队列和后台任务也要显式携带传播字段；外来 Trace Context 必须校验，且不得承载 PII 或业务 Secret。

**7. Agent 专属字段**

应记录模型、Prompt、Tool、Context 与 Runtime 版本，以及 Token、延迟、停止原因、工具调用 ID、错误类别和最终状态；原始内容不是默认必采字段。

**8. 采样与隐私**

Head Sampling 简单但无法按最终错误选样，Tail Sampling 可保留错误和慢 Trace 但成本更高；Prompt、Tool Payload 和用户数据应默认最小化、脱敏、分权与限期保存。

**9. 与 Eval 的关系**

Tracing 保留发生了什么，Evals 定义这些行为是否成功；Trace 能定位失败但不自动产生正确评分，Eval 也不能在缺少完整证据时可靠诊断。

### 高频对比

| 信号 | 最擅长回答 | 典型数据 | 不适合单独完成的事 |
| --- | --- | --- | --- |
| Metrics | 是否异常、趋势怎样 | 成功率、P95 延迟、Token、成本 | 还原单次复杂因果链 |
| Logs | 某时发生了什么细节 | 错误、状态变化、业务事件 | 自动连接跨服务完整路径 |
| Traces | 一次 Run 在哪里耗时或失败 | Span 树、属性、事件、链接 | 低成本保存所有高基数原文 |

### 高频问题

#### 问题1：为什么消息历史不能替代 Agent Trace？

消息历史只覆盖模型可见交互，通常没有 Context 选择、工具内部耗时、重试、权限检查、Checkpoint 和跨服务调用。Trace 面向执行因果链，消息只是其中可能被引用的一类数据。

#### 问题2：一个工具调用跨越 API、队列和 Worker 时，怎样保持为同一条 Trace？

调用方把标准 Trace Context 注入请求或消息，接收方校验后以远程 Parent 创建子 Span；异步一对多或延后消费可用 Span Link 表达，业务 `tool_call_id` 仍要作为独立属性保留。

#### 问题3：线上报错却找不到 Trace，最可能是什么原因？

先检查 Context 是否在边界丢失、Span 是否在进程退出前 Flush，以及 Head Sampling 是否提前丢弃该请求。要求保留错误时通常需要 Tail Sampling、强制错误样本或独立错误日志兜底。

#### 问题4：为什么不能把完整 Prompt 和 Tool Result 全部写进 Trace？

其中可能含 PII、凭证、商业数据和 Prompt Injection 内容，还会显著增加存储与访问风险。默认记录哈希、长度、版本、引用和统计值，仅在受控调试或 Eval 环境按授权捕获必要原文。

#### 问题5：如何利用 Trace 区分模型问题和工具问题？

检查模型 Span 的输入版本与 Tool Call、工具 Span 的参数和返回、以及后续模型是否正确消费结果。模型选错工具属于决策问题，正确调用返回错误属于工具问题，正确结果被忽略则更可能是 Context 或后续决策问题。

---

## 可观测性不是“多打日志”

Agent 的一次 Run 可能包含多次模型推理、并行检索、工具副作用、重试、人工审批和跨进程恢复。若每个组件只打印一行日志，团队只能看到许多相邻事件，却难以证明它们属于同一个用户请求、谁触发了谁，以及延迟消耗在哪一层。

Observability（可观测性）关注系统是否产生足够且可关联的外部信号，使工程人员能从未知症状反推内部状态。Monitoring（监控）通常基于这些信号持续检查已知指标和阈值。两者不是互斥工具：前者提供诊断能力，后者把其中稳定的判断自动化。

```text
Agent Runtime
├── Traces：一次 Run 的因果路径
├── Metrics：跨大量 Run 的聚合趋势
└── Logs：离散事件和详细记录
        │
        └── 共同字段：run_id、trace_id、版本、租户边界
```

第 08 章已经定义 Evals 负责判断“好不好”。本章解决另一个问题：系统是否保留了足够证据解释“为什么”。没有 Evals，Trace 只是可浏览记录；没有 Trace，Eval 失败通常只能停留在最终输出层。

## Trace 由有因果关系的 Span 构成

在 OpenTelemetry 的通用模型中，Span 表示一个有开始和结束的工作单元，包含名称、父 Span、时间、Span Context、Attributes、Events、Links 和 Status。多个共享 Trace ID 的 Span 组成一次分布式 Trace。

最小字段的职责如下：

| 字段 | 作用 |
| --- | --- |
| `trace_id` | 关联整条端到端路径 |
| `span_id` | 唯一标识一个工作单元 |
| `parent_span_id` | 表达嵌套调用的直接因果关系 |
| Name | 表达稳定、低基数的操作类型 |
| Start / End | 计算时间线和 Duration |
| Status | 标记操作是否出错，不替代业务结果 |
| Attributes | 描述整个 Span 的可查询维度 |
| Events | 记录 Span 内某个时间点发生的变化 |
| Links | 关联非树形、异步或批处理因果关系 |

Attribute 适合“这个模型调用使用了哪个模型”这类 Span 级事实，Event 适合“第 2 次重试开始”这类瞬时记录。大段内容不应塞进 Span Name，也不应把用户 ID、Prompt 或错误消息直接做成 Metric Label，否则会造成高基数、成本和隐私问题。

### Run ID 与 Trace ID 不相互替代

`run_id` 是第 06 章定义的领域身份，决定恢复、权限和业务生命周期；`trace_id` 是遥测身份，决定观测系统中的关联。简单同步 Run 可以一一对应，但真实系统可能出现：

- 一个 Run 在恢复前后产生多条 Trace；
- 一个入口 Trace 触发多个子 Run；
- 一个后台任务链接到原 Trace，却拥有新的根 Span；
- 一次重试保留相同 Run ID，但需要新的 Attempt Span。

因此应在根 Span 中记录 `run_id`，并在 Checkpoint 或业务事件中记录对应 Trace ID。不能拿可公开传播的 Trace ID 直接充当授权凭据，也不能只凭 Trace ID 加载业务 State。

## Agent Span 树要覆盖控制和副作用

一个常见的 Span 层次如下：

```text
agent.run
├── context.build
│   ├── memory.retrieve
│   └── knowledge.retrieve
├── model.generate [turn=1]
├── tool.execute [tool=lookup_order, attempt=1]
├── model.generate [turn=2]
├── guardrail.check
├── checkpoint.save
├── approval.wait
└── tool.execute [tool=cancel_order, attempt=1]
```

根 Span 表示一次可解释的 Run 或 Workflow，子 Span 表示真正可能失败或产生显著延迟的操作。模型 Span 至少要能关联 Model、Prompt、Tool Set 和 Context Manifest 版本，并记录输入输出 Token、停止原因、Provider Request ID、首 Token 与总延迟。工具 Span 则记录工具名、`tool_call_id`、参数 Schema 版本、Attempt、超时、结果状态和外部操作 ID。

不要把整个 Agent Loop 压成单个 `model_call` Span，也不要为每个 Token 创建 Span。前者无法定位工具与控制问题，后者会制造巨大数据量。Span 边界应对应可独立耗时、失败、重试或产生副作用的工作单元。

OpenAI Agents SDK 当前默认对 Runner、Task、Turn、Agent、Generation、Function Tool、Guardrail 和 Handoff 等操作建立 Trace/Span。其他框架可能使用不同名称；核心语义是保留父子关系和稳定属性，而不是要求所有系统复制某一厂商的层次。

### 错误、重试和业务失败要分开

Span Status `error` 表示该操作执行异常，例如 HTTP 超时或 Schema 解析失败。工具正常返回“订单不存在”可能是业务结果而非遥测异常；Agent 最终未完成任务则由 Run 最终状态和 Eval 判定。把三者全部记成异常会导致错误率失真。

重试不能覆盖原 Span 的 Duration 和错误。每次 Attempt 应有独立 Span 或明确 Event，共享稳定的逻辑 `tool_call_id`，并增加 `attempt`。这样既能看到最终成功，也能计算重试放大的延迟、Token 和外部调用量。

## 跨进程传播才能形成端到端因果链

同一进程内可以通过语言的上下文机制自动继承 Parent；跨 HTTP、RPC、消息队列或后台 Worker 时，必须显式序列化 Span Context。W3C Trace Context 定义了 `traceparent` 和 `tracestate` Header，使不同实现能够传播 Trace ID、当前 Parent 和采样标志。

```text
API Span
   │ inject traceparent
   ↓
Queue Message ─────────────→ Worker
                               │ extract + validate
                               ↓
                          Tool Child Span
```

接收方要把 Header 当作不可信输入：校验版本、长度、十六进制格式和全零 ID，不能让畸形值破坏遥测管线。W3C 规范明确要求 `traceparent` 与 `tracestate` 不承载个人身份或其他敏感信息，它们只用于关联。

树形 Parent 适合直接同步调用。消息被多个 Consumer 处理、批任务合并多个上游请求，或任务隔很久才执行时，强行选择唯一 Parent 会歪曲因果关系；Span Link 更适合表达“与这些上游 Span 有因果关联”。Session ID、Run ID、Tool Call ID 和业务 Operation ID 仍应作为独立相关键记录。

## 从 Trace 聚合 Metrics，但控制基数

Trace 适合单次诊断，Metrics 适合跨大量 Run 做趋势、SLO 和告警。常见 Agent Metrics 包括：

- Run 成功率、失败率、取消率和人工接管率；
- 模型与工具调用次数、错误率和重试率；
- 首 Token、模型、工具和端到端延迟分布；
- 输入、输出、缓存与推理 Token，以及估算成本；
- Context 压缩、Checkpoint 冲突和死循环拦截次数；
- 按模型、工具、版本和风险级别分组的 Eval 分数。

Metrics Label 必须保持有限集合。`model`、`tool_name`、`status` 和受控版本通常可接受；`user_id`、`run_id`、原始错误消息和 Prompt 会产生近乎每次请求唯一的时间序列，应留在 Trace 或受控 Log 中按需查询。需要从告警跳到具体 Trace 时，可使用 Trace ID、Exemplar 或时间窗口关联，而不是把 Trace ID 设为 Label。

Log 也应结构化，并携带 `trace_id`、`span_id` 和 `run_id`。同一个错误不必在每层重复打印完整堆栈；应在负责处理的边界记录一次，并让 Span Status 和异常 Event 指向同一事件。

## Sampling 决定看见哪些现实

全量 Trace 成本可能不可接受，但采样会改变团队看到的故障分布。Head Sampling 在 Trace 刚开始时决定保留与否，简单高效，却还不知道最终是否失败或超时；仅使用 1% Head Sampling 可能恰好丢掉关键事故。

Tail Sampling 在看到全部或大部分 Span 后，根据最终错误、总延迟、版本或风险属性决定。它可以优先保留：

- 所有错误、超时和取消 Trace；
- 高风险写操作与人工审批；
- 新版本、小流量实验和 Eval Trial；
- P95/P99 慢请求和异常高成本请求；
- 正常流量中的代表性概率样本。

代价是 Collector 必须暂存 Trace 并维护状态，部署和容量更复杂。采样器自身也要有丢弃量、延迟和内存监控。无论采用哪种策略，关键安全审计事件不能只依赖可能被采样的调试 Trace；审计日志需要独立、明确的保留和完整性策略。

## 内容捕获默认遵循最小化原则

Prompt、模型输出、检索片段和 Tool Payload 对调试很有价值，也最容易包含 PII、凭证、合同、源代码和用户上传内容。Tracing Pipeline 必须把“记录元数据”和“记录原文”拆成两个开关。

默认可以记录哈希、大小、Token 数、内容类型、版本、Artifact ID 和安全分类，而不记录正文。需要原文时，应限制在授权的开发或 Eval 环境，对字段做脱敏，加密传输与存储，控制角色访问，记录访问审计，并设置比普通 Metrics 更短的保留期。哈希也可能用于关联敏感数据，仍要纳入数据治理。

OpenAI Agents SDK 当前文档说明 Generation 和 Function Span 可能保存模型与工具输入输出，并提供关闭敏感数据捕获的配置。这是一个具体框架能力；使用任何平台时都应显式核对默认值，不能假设“Tracing 默认安全”。

Trace 不需要保存隐藏 Chain-of-Thought。可诊断性来自可观察事实：输入与配置版本、模型提出的结构化行动、工具参数与结果、控制状态和最终 Outcome。要求或记录模型私有推理既不稳定，也会扩大数据风险。

## 最小 Tracer 验证父子关系和传播

仓库中的 [`mini_tracer.py`](../../examples/09-tracing-observability/mini_tracer.py) 使用 Python `ContextVar` 保存当前 Span。嵌套上下文自动复用 Trace ID 并把当前 Span ID 设为 Parent：

```python
with tracer.start_span("agent.run", attributes={"run_id": "run-42"}):
    with tracer.start_span(
        "model.generate",
        attributes={"model": "example-model", "prompt": "private"},
    ) as span:
        span.set_attribute("input_tokens", 120)
```

默认 `capture_content=False`，因此 `prompt`、`input`、`output`、工具参数和 Secret 等演示字段会被替换为 `[REDACTED]`，而 `input_tokens` 等统计值保留。异常会把 Status 设为 `error`，添加只含异常类型的 Event，并继续向上抛出。

示例还实现最小 `traceparent` 生成与解析。接收 Worker 可解析远程 Parent，再创建共享 Trace ID 的子 Span。9 个测试覆盖父子关系、上下文恢复、异常、内容和 Event 脱敏、Duration、Header 往返、远程 Parent 以及畸形和全零 ID 拒绝。

它没有实现 OpenTelemetry SDK 的采样、Batch Export、Resource、Span Link、Baggage 和 Collector 协议，也没有解决线程池和进程间自动传播。生产环境应使用成熟遥测 SDK 和标准 Backend；教学实现只证明 Span 关系、错误和传播为什么成立。

## 从告警到原因需要稳定查询路径

完整的运维路径应该能够从聚合症状逐层下钻：

```text
告警：新版本 Run 失败率升高
   ↓ 按 model / prompt_version / tool_version 切片
Metrics：cancel_order 错误集中于 v3
   ↓ 选择错误 Exemplar 或时间范围
Trace：模型参数正确，Tool Span 超时并重试三次
   ↓ 关联结构化 Log 与外部 operation_id
原因：下游限流；Checkpoint 在第三次成功后写入冲突
   ↓
生成新的 Regression Task，修复后用 Eval 验证
```

这条链路要求版本字段、状态枚举和错误分类保持稳定。若 Span Name 包含随机 Prompt，或不同服务对 `timeout`、`cancelled` 使用不同含义，Dashboard 无法可靠聚合。遥测 Schema 也需要版本、兼容策略和测试，尤其是快速演进的 GenAI Semantic Conventions。

完成 Evals 与 Tracing 后，系统第一次具备了“定义成功—观察行为—定位失败—验证修复”的闭环。接下来引入 Retrieval、RAG 与 Memory 时，不再只凭 Demo 判断效果，而是能够分别测量召回、证据使用、最终 Outcome 和新增成本。

## 参考资料

- [Traces](https://opentelemetry.io/docs/concepts/signals/traces/)，OpenTelemetry 官方文档；用于核对 Trace、Span、Span Context、Attributes、Events、Links、Status 和父子关系的数据模型；最后核验日期：2026-07-22。
- [Trace Context](https://www.w3.org/TR/trace-context/)，W3C Recommendation；用于核对 `traceparent`、`tracestate` 的跨系统传播、校验、隐私和安全边界；最后核验日期：2026-07-22。
- [Tracing](https://openai.github.io/openai-agents-python/tracing/)，OpenAI Agents SDK 官方文档；用于核对当前 SDK 的默认 Agent Span 类型、Trace/Span 字段和敏感内容捕获配置；最后核验日期：2026-07-22。
- [Sampling](https://opentelemetry.io/docs/concepts/sampling/)，OpenTelemetry 官方文档；用于核对 Head Sampling 与 Tail Sampling 的决策时机、能力和基础设施代价；最后核验日期：2026-07-22。
- [Trace grading](https://developers.openai.com/api/docs/guides/trace-grading)，OpenAI API 官方文档；用于核对结构化 Trace 评分对工作流诊断、回归定位和 Eval 的作用；最后核验日期：2026-07-22。
