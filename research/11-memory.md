# 第 11 章研究记录：Memory

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Agent Memory 与 State、Session、Context、Retrieval 和模型参数知识的边界是什么？
2. 语义、情景和程序性 Memory 是强制存储结构，还是帮助设计的认知分类？
3. 写入、合并、更新、冲突、过期和删除需要哪些不变量？
4. 如何防止跨用户召回、错误推断和外部恶意内容造成长期污染？
5. 如何分别评测 Memory 写入、召回、使用和系统治理？

## 范围边界

- 本章聚焦跨 Run/跨 Session 的长期信息；Thread 内消息历史、Checkpoint 和 Context Compaction 已在第 06、07 章说明，只在边界处引用。
- 第 10 章的检索技术可以复用于 Memory Recall，但“Memory 写什么、何时更新和怎样遗忘”是新增的数据生命周期问题。
- 语义、情景、程序性分类来自认知架构研究及工程文档，是有用的设计视角，不宣称等同于人类记忆或构成唯一标准。
- 安全与隐私在本章作为 Memory 特有写入和隔离约束说明；完整威胁模型留给第 24 章。

## 一手资料与采用结论

### 1. Cognitive Architectures for Language Agents

- 来源：Sumers 等，TMLR 论文（arXiv v3）。
- 链接：https://arxiv.org/abs/2309.02427
- 采用结论：CoALA 用模块化 Memory、内部/外部 Action Space 和决策过程组织 Language Agent；正文借用工作、语义、情景和程序性 Memory 的分类作为工程分析框架，而不是产品必须照搬的数据库 Schema。
- 正文用途：建立 Memory 在 Agent 认知架构中的位置和分类边界。
- 最后核验日期：2026-07-22。

### 2. Generative Agents: Interactive Simulacra of Human Behavior

- 来源：Park 等，UIST 2023 原始论文。
- 链接：https://arxiv.org/abs/2304.03442
- 采用结论：论文架构以自然语言保存经历，按需动态召回并把经历综合为更高层 Reflection，再用于 Planning；其目标是交互模拟中的可信行为，不应把该实验直接当作生产个性化系统的质量证明。
- 正文用途：说明 Event → Recall → Consolidation/Reflection → Action 的可行架构，以及“保存全部经历”在生产中仍需治理。
- 最后核验日期：2026-07-22。

### 3. MemGPT: Towards LLMs as Operating Systems

- 来源：Packer 等原始论文。
- 链接：https://arxiv.org/abs/2310.08560
- 采用结论：论文用操作系统层级存储的类比提出 Virtual Context Management，在有限 Context Window 与外部存储之间移动信息；这说明持久化 Memory 与本次模型可见 Context 是两个不同层次。
- 正文用途：支持“存储不等于可见、Recall/Context 编排不可省略”的边界。
- 最后核验日期：2026-07-22。

### 4. Memory overview

- 来源：LangChain/LangGraph 官方概念文档。
- 链接：https://docs.langchain.com/oss/python/concepts/memory
- 采用结论：当前文档把短期 Memory 作为 Thread-scoped State，把长期 Memory 放入跨 Thread 的自定义 Namespace；还区分语义、情景和程序性 Memory、Profile 与 Collection，以及 Hot Path 与 Background 写入。
- 正文用途：核对当前工程术语、表示方法和两类写入时机的权衡。
- 最后核验日期：2026-07-22。

### 5. LangMem Core Concepts

- 来源：LangMem 官方文档。
- 链接：https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- 采用结论：当前文档把提取、更新、删除和合并视为 Memory Manager 的转换，把持久化作为独立集成层；Namespace 可按组织、用户和应用分层，检索支持 Direct Access、Semantic Search 和 Metadata Filtering。
- 正文用途：支持“形成 Memory 与保存/查询 Memory 分层”、Namespace 隔离和按 Key 直接读取的工程设计。
- 最后核验日期：2026-07-22。

### 6. Sessions

- 来源：OpenAI Agents SDK Python 官方文档。
- 链接：https://openai.github.io/openai-agents-python/sessions/
- 采用结论：截至核验日，SDK Session 会在 Run 前加载该 Session 历史、Run 后保存新增 Items，并支持限制历史和 Compaction；这属于会话连续性，不自动完成跨 Session 的事实提取、冲突治理或长期 Recall。
- 正文用途：澄清厂商文档中的“session memory”与本章长期 Memory 的边界。
- 最后核验日期：2026-07-22。

## 术语与工程决策

### Profile 不是第四种认知 Memory

Profile 是语义事实的一种结构化表示：固定 Schema、按 Key 直接读取、更新时需要合并整个对象或 Patch。Collection 将事实拆成多条记录，更适合搜索和增量写入，但增加去重、冲突和完整性组合成本。正文将“类型”和“表示”分开讲解。

### Memory Write 不是数据库 Insert

写入前必须经历候选提取、价值判断、用户/组织政策、敏感性和来源校验；写入后仍需版本、冲突、TTL、删除和反馈。模型生成的候选只是提议，不是可信事实。程序性 Memory 会改变 Agent 行为，默认要求人工或受控 Eval 审批。

### 召回必须先隔离再排序

Owner、Organization、Application Namespace 和 ACL 先定义合法候选集，随后才按 Query relevance、时间、置信度和重要性排序。已知 Profile Key 使用直接读取，比语义搜索更准确、更便宜。

### 删除语义

本章示例把同一逻辑 Key 的所有版本内容做 Redaction 并移除 Active Pointer。生产环境还要把删除传播到向量索引、缓存、备份保留流程和下游派生物；仅加一条 `deleted=true` 而长期保留明文不等同于完成遗忘。

## 示例设计

`examples/11-memory/memory_store.py` 使用 Python 标准库实现：

- Memory Candidate 与 Durable Record 分离；
- 低置信候选、未经确认的敏感信息和未经审批的程序性 Memory 被拒绝；
- Owner/Namespace 预过滤、已知 Key 直接读取和带来源引用的搜索；
- 乐观并发版本、删除后仍单调递增的 Revision、幂等 Operation ID、旧版本 Supersede；
- TTL 过期与同一逻辑 Key 全版本 Redaction。

搜索使用可解释的词项、置信度、重要性和时间组合，只用于验证顺序与生命周期，不冒充生产语义检索器。

## 待人工审核项

- [ ] 目标产品对敏感信息、显式同意、保留期和删除传播的具体政策尚未确定，本章仅提供工程控制点。
- [ ] 程序性 Memory 是否允许自动提议、由谁审批、怎样灰度和回滚，需要在具体 Agent 的 Eval 与发布流程中决定。
- [ ] 示例为内存实现；生产落地需要事务数据库、加密、审计、备份删除与索引一致性设计。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
