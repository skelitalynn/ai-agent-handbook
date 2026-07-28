# 第 07 章研究记录：Context Engineering

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Context Engineering 与 Prompt Engineering、Session State、RAG 和 Memory 的边界是什么？
2. 一个 Agent 每轮模型调用的 Context 由哪些部分组成，应该如何分配 Token 预算？
3. 为什么“能装进 Context Window”不等于“模型能够可靠使用”？
4. 选择、排序、压缩、按需加载和隔离分别解决什么问题？
5. 如何测试 Context Builder，而不是只凭最终答案猜测上下文是否合理？

## 范围边界

- 第 03 章负责指令层次、示例和输出约束；本章负责每轮完整模型输入的动态编排。
- 第 06 章负责保存 State；本章负责从 State 与外部信息中选择本轮 Context。
- 第 10 章展开 Retrieval、RAG、摄取与检索质量；本章只把检索结果视为一种候选 Context。
- 第 11 章展开 Memory 的写入、更新、召回和删除；本章只讨论被召回内容怎样进入 Context。
- 第 15 章展开 Multi-Agent；本章只说明隔离上下文可以减少注意力干扰，并不把多 Agent 当作默认解法。

## 一手资料与采用结论

### 1. Effective context engineering for AI agents

- 来源：Anthropic Engineering。
- 链接：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- 核对内容：Context 是采样时提供给模型的 Token 集合；Context Engineering 是在每次推理前持续策划和维护这些 Token；长任务可使用按需加载、Compaction、结构化笔记和隔离的子任务上下文。
- 采用结论：Context 是有限的注意力预算，核心目标不是填满窗口，而是提供足以支持当前决策的最小高信号信息；压缩必须在 Recall 与 Precision 之间评测。
- 最后核验日期：2026-07-22。

### 2. Compaction

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/compaction
- 核对内容：Responses API 支持服务端阈值触发和独立端点两种 Compaction；压缩结果用于以更少 Token 延续后续请求；独立端点的返回窗口应整体作为下一次输入。
- 采用结论：Compaction 是有损的状态转换，不应被写成简单截断；厂商托管结果可能是不可读的专用 Item，应用不能假设所有实现都返回人类摘要。
- 最后核验日期：2026-07-22。

### 3. Prompt caching

- 来源：OpenAI API 官方文档。
- 链接：https://developers.openai.com/api/docs/guides/prompt-caching
- 核对内容：缓存命中依赖完全相同的前缀；稳定指令和示例应位于前部，动态用户内容位于后部；缓存指标可用于验证效果。
- 采用结论：Context 的顺序同时影响语义和推理工程；稳定前缀有利于缓存，但不能为了命中率破坏指令层次或工具消息协议。
- 最后核验日期：2026-07-22。

### 4. Context management

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/context/
- 核对内容：SDK 明确区分本地应用 Context 与模型可见 Context；`RunContextWrapper.context` 不会自动发送给模型；会话历史属于另一个问题。
- 采用结论：工程术语 `context` 常被重载。正文统一用 Model Context 表示发送给模型的输入，用 Runtime Context 表示代码侧依赖与状态，并提醒读者查看具体框架定义。
- 最后核验日期：2026-07-22。

### 5. Lost in the Middle: How Language Models Use Long Contexts

- 来源：Liu 等，Transactions of the Association for Computational Linguistics 原始论文。
- 链接：https://arxiv.org/abs/2307.03172
- 核对内容：在论文所评测的多文档问答和键值检索设置中，相关信息的位置变化会显著影响表现，常出现开头和结尾更好、中间更差的 U 型曲线；扩展窗口不必然提高有效利用能力。
- 采用结论：将论文结论限定在其评测模型和任务，不把它写成所有现代模型的固定规律；工程上仍应按目标模型测试长度、位置和干扰项敏感性。
- 最后核验日期：2026-07-22。

## 术语决策

### Context Window 与 Context

Context Window 是模型一次请求可处理的 Token 容量限制；Context 是本次请求实际呈现给模型的 Token 序列。窗口容量是上限，不是质量目标。

### Prompt Engineering 与 Context Engineering

Prompt Engineering 主要设计指令、示例和输出约束；Context Engineering 设计每轮完整输入的来源、选择、顺序、压缩、隔离和生命周期。前者是后者的重要组成部分，不是竞争关系。

### Compaction 与 Truncation

Truncation 按长度机械删除内容；Compaction 试图保留任务目标、决策、未完成项和必要证据，同时用更少 Token 表达。Compaction 仍可能丢失信息，必须评测。

### State 与 Context

State 是已经持久化的事实和执行状态；Context 是当前调用选择出来的模型输入投影。未进入 Context 的 State 不会被模型自动感知。

## 示例设计

`examples/07-context-engineering/context_builder.py` 使用 Python 标准库实现确定性 Context Builder：

- 从 Context Window 中先扣除输出预留；
- 必选项超预算时显式失败，不静默删除系统约束或当前请求；
- 对相同逻辑 ID 保留最新版本，防止新旧事实同时进入 Context；
- 在剩余预算内按优先级选择可选项；
- 按稳定指令、参考资料、历史、工具结果、当前用户输入的顺序渲染；
- 对不可信数据加边界标记，但明确这不是完整安全隔离；
- 返回使用量和省略项，便于 Trace 与评测。

Token 数由调用方使用目标模型的 Tokenizer 对最终序列核算；示例中的显式 `tokens` 只为隔离和测试预算算法，不冒充通用字符估算。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
