# 第 09 章研究记录：Tracing 与 Observability

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Log、Metric、Trace 与 Eval 分别回答什么问题，如何关联？
2. Agent Run 应怎样拆分 Span，才能定位模型、工具、检索、审批和状态故障？
3. Trace ID、Span ID、Parent、Event、Attribute、Status 与 Link 的语义是什么？
4. 如何跨 HTTP、队列、后台任务和子 Agent 传播因果关系？
5. 如何在可诊断性、隐私、成本与高基数之间权衡？

## 范围边界

- 第 08 章定义成功标准并消费 Trace 做评分；本章负责生成、关联、存储和查询运行证据。
- 第 23 章用 Metrics、Trace 和 SLO 驱动可靠性控制；本章只建立观测数据模型。
- 第 24 章完整展开安全与隐私；本章聚焦遥测内容捕获、脱敏和访问控制。
- 本章不要求或保存模型隐藏 Chain-of-Thought，只记录外部可观察的输入版本、行动、结果和状态。

## 一手资料与采用结论

### 1. Traces

- 来源：OpenTelemetry 官方文档。
- 链接：https://opentelemetry.io/docs/concepts/signals/traces/
- 核对内容：Span 是工作或操作单元，包含名称、父 Span、起止时间、Span Context、Attributes、Events、Links 与 Status；嵌套 Span 表达子操作。
- 采用结论：Agent Run 使用一个根 Span，模型、工具、检索和控制节点作为子 Span；瞬时变化使用 Event，整个操作的维度使用 Attribute。
- 最后核验日期：2026-07-22。

### 2. Trace Context

- 来源：W3C Recommendation。
- 链接：https://www.w3.org/TR/trace-context/
- 核对内容：`traceparent` 与 `tracestate` 的传播和校验；Trace ID 与 Parent ID 的更新；隐私和安全注意事项。
- 采用结论：跨服务和队列传播标准 Trace Context；Header 只用于关联，不放 PII 或业务 Secret；所有外来 Header 都按不可信输入解析。
- 最后核验日期：2026-07-22。

### 3. Tracing

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/tracing/
- 核对内容：SDK Trace 与 Span 层次；Runner、Task、Turn、Agent、Generation、Function、Guardrail 与 Handoff 的默认 Span；Generation 和 Function Span 可能捕获敏感输入输出，可关闭内容捕获。
- 采用结论：使用该文档说明框架映射，不把其 Span 类型当成厂商无关强制标准；原始 Prompt 与工具 Payload 默认不应无条件记录。
- 最后核验日期：2026-07-22。

### 4. Sampling

- 来源：OpenTelemetry 官方文档。
- 链接：https://opentelemetry.io/docs/concepts/sampling/
- 核对内容：Head Sampling 在看到完整 Trace 前决定，简单高效但不能保证保留所有错误；Tail Sampling 可依据错误、延迟和属性决定，但需要有状态基础设施。
- 采用结论：错误、高风险写操作和 Eval Trial 应优先保留；采样策略本身需要监控，不能让只剩成功样本。
- 最后核验日期：2026-07-22。

### 5. Trace grading

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/trace-grading
- 核对内容：为端到端 Trace 的决策、工具调用和中间步骤分配结构化标签或分数，用于定位工作流回归。
- 采用结论：Trace 的结构化字段应足以支持第 08 章的 Grader；观测与评测共用证据，但生命周期和采样要求不同。
- 最后核验日期：2026-07-22。

## 术语决策

### Trace、Span 与 Event

Trace 表示一次分布式因果链；Span 表示有开始和结束的工作单元；Event 是 Span 内某个时间点发生的记录。工具重试应是多个 Attempt Span 或事件，而不是覆盖第一次结果。

### Observability 与 Monitoring

Observability 是通过外部信号理解系统内部状态的能力；Monitoring 是其中面向已知指标、阈值和告警的持续运行活动。本章不把两者写成互斥产品类别。

### Run ID 与 Trace ID

Run ID 是 Agent 领域身份，Trace ID 是遥测关联身份。二者通常一对一或一对多映射，但不能相互替代；重试、后台续作和跨系统关联要显式记录。

## 示例设计

`examples/09-tracing-observability/mini_tracer.py` 使用 Python 标准库实现：

- ContextVar 维护当前 Span，自动形成父子关系；
- 记录 Trace ID、Span ID、起止时间、Attributes、Events 与 Status；
- 异常时标记错误并保留异常类型；
- 默认脱敏 Prompt、输入输出、工具参数和 Secret 字段；
- 生成与解析最小 W3C `traceparent`，用于跨边界传播；
- 内存 Exporter 便于单元测试。

示例只验证数据模型和上下文传播，不替代 OpenTelemetry SDK、Collector 和生产 Backend。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
