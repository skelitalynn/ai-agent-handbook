# Memory

> 本文讨论 Agent 如何跨 Run、跨 Session 保存并使用长期信息。重点不是某个向量数据库，而是 Memory 从候选提取到写入、合并、召回、注入、更新和遗忘的完整生命周期，并明确它与 State、Session、Context 和第 10 章 Retrieval 的边界。

## 面试速记

### 背诵提纲

**1. 定义**

Agent Memory 是由应用管理、可跨运行持久化并在未来按需召回的信息；模型不会因为完成一次对话就自动获得可更新、可删除的长期记忆。

**2. 概念边界**

State 保存当前执行事实，Session 组织同一会话历史，Context 是本次模型实际可见输入，Retrieval 是查找方法；长期 Memory 负责跨 Session 的信息生命周期，召回后仍需经过 Context 构建。

**3. Memory 类型**

语义 Memory 保存事实和偏好，情景 Memory 保存具体经历与结果，程序性 Memory 保存完成任务的规则；这是设计分类，不是必须照搬的数据库 Schema。

**4. 表示方式**

Profile 用固定 Schema 保存一组稳定事实，适合按 Key 直接读取；Collection 把 Memory 拆成独立记录，便于增量写入和搜索，但需要去重、冲突处理和结果组合。

**5. 完整生命周期**

```text
交互与事件 → 提取候选 → 价值/权限/敏感性校验 → 合并或写入
           → 索引 → 授权召回 → Context 注入 → 使用反馈
           → 更新、过期或删除
```

**6. 写入策略**

Hot Path 写入可立即生效和向用户展示，但增加延迟并干扰主任务；Background 写入便于批量去重和合并，但存在新鲜度、并发与失败恢复问题。

**7. 一致性与遗忘**

每条 Memory 应保留 Owner、Namespace、来源、时间、置信度和版本；冲突通过乐观并发、Supersede 或并存的时间事实处理，删除必须传播到历史版本、索引、缓存和下游派生物。

**8. 召回与 Context**

召回先按 Tenant、用户、应用和 ACL 建立合法候选集，再结合相关性、时间、重要性和置信度排序；已知 Profile 字段优先直接读取，召回结果还需去重并受 Token 预算约束。

**9. 安全与评测**

模型提取的 Memory 只是候选，敏感信息和行为规则不能未经确认长期保存；评测应拆分写入准确率、冲突更新、Recall、实际使用、越权隔离、删除完整性和端到端收益。

### 高频对比

| 维度 | Profile | Collection |
| --- | --- | --- |
| 数据形态 | 一个或少量固定 Schema 对象 | 多条独立 Memory 记录 |
| 读取方式 | 已知 Key 直接读取 | 过滤、关键词或语义搜索 |
| 优势 | 完整、稳定、易验证字段 | 易增量扩展，适合长尾事实 |
| 主要难点 | 整体更新可能覆盖字段，Schema 会膨胀 | 去重、冲突、低精度写入与上下文拼装 |
| 适用场景 | 语言、时区、明确偏好等稳定属性 | 事件、经验、开放式兴趣和历史反馈 |

### 高频问题

#### 问题1：为什么不能把完整聊天记录直接当作长期 Memory？

聊天记录包含大量临时信息、错误推断、敏感内容和已经失效的上下文，全部保存会降低召回精度并扩大隐私风险。长期 Memory 需要经过选择、结构化、来源记录、冲突治理和保留期控制。

#### 问题2：新对话与旧 Memory 冲突时应该覆盖哪一个？

不能只按“最后写入”覆盖；先比较来源可信度、用户是否明确确认、事实的有效时间和写入时看到的版本。稳定 Profile 可用乐观并发更新，时间性事实可保留多个有效区间，无法裁决时应保留冲突并请求确认。

#### 问题3：为什么召回不能只按向量相似度排序？

相似度只描述 Query 与文本的语义接近程度，不表示 Memory 仍有效、来源可信、属于当前用户或值得进入有限 Context。权限和有效期先过滤，相关性再与置信度、重要性、时间及任务类型共同决策。

#### 问题4：何时选择 Hot Path，何时选择 Background Memory Write？

用户明确要求“记住”、下一步立即依赖该信息或需要即时确认时适合 Hot Path；大量对话归纳、去重和 Reflection 更适合 Background。生产系统常组合两者，并用幂等键、队列和版本检查处理重复与乱序。

#### 问题5：怎样证明 Memory 真的改善了 Agent，而不是只让回答更像个性化？

先分别测该记的是否写入、不该记的是否拒绝、目标 Memory 是否召回及是否被正确使用，再比较启用和禁用 Memory 的任务成功率、纠错次数与用户评价。还必须加入跨用户 Canary、过期事实、冲突和删除测试，否则平均质量提升可能掩盖严重治理失败。

---

## Memory 是受治理的长期数据，不是模型的隐藏能力

一次模型调用结束后，模型参数不会因该对话自动更新。应用可以保存消息、数据库记录或向量，但“存下来了”仍不等于形成了可用 Memory：系统还要判断信息是否值得长期保留、它属于谁、何时有效、与旧信息是否冲突，以及未来什么任务应该看到它。

因此，Agent Memory 更适合被定义为一套跨运行的数据生命周期。它接收对话、工具结果、用户反馈和任务结果，形成候选；经政策与事实校验后持久化；在后续请求中按身份和任务召回；最后根据纠正、过期和删除请求继续演化。数据库、Embedding 和 LLM 都只是其中的实现组件。

CoALA（Cognitive Architectures for Language Agents）用模块化 Memory、内部与外部 Action 以及决策过程组织 Language Agent。MemGPT 则用操作系统层级存储类比说明：有限 Context Window 类似昂贵的工作区，外部存储可以更大，但信息必须经过调入才能参与当前计算。这两个视角共同揭示了一个工程事实：持久化容量不能消除 Context 选择问题。

## 先把 State、Session、Context、Retrieval 与 Memory 分层

第 06 章已经把 State 定义为一次 Run 或 Thread 中恢复执行所需的结构化事实，Session/Conversation 则组织连续交互。某些 SDK 把持久化消息历史称为“session memory”；例如截至 2026-07-22，OpenAI Agents SDK Session 会在 Run 前加载会话 Items，并在 Run 后保存新增 Items。这能维持同一 Session 的连续性，但不会自动提取跨 Session 偏好、裁决冲突或实现可治理遗忘。

第 07 章的 Context 是一次模型调用真正可见的 Token 集合。历史消息、当前 State、工具结果、RAG 证据和长期 Memory 都只是 Context 候选；未被选入 Context 的持久化数据不会影响本次推理。Context Compaction 生成的摘要也主要服务当前 Thread 连续性，除非系统明确把其中某些结论提交为长期 Memory。

第 10 章的 Retrieval 是从集合中查找相关对象的能力。长期 Memory 可以复用关键词、向量、混合检索和重排，但它比知识库多出形成、身份、冲突和遗忘语义。同一套向量数据库既可保存产品文档也可保存用户偏好，不代表两类数据具有相同的可信来源、更新策略和权限边界。

```text
持久化层
   ├── Checkpoint / Session History → 恢复某个 Thread
   ├── Knowledge Base              → 检索外部领域知识
   └── Long-term Memory            → 跨 Thread 保存选定事实、经历与规则
                                            │
                                            ↓ Recall
本次 Run State ─────────────────────→ Context Builder ─→ Model Input
```

这张图的观察重点不是存储介质，而是消费语义。相同文本位于不同层时，生命周期和授权规则也不同。

## Memory 类型回答“保存什么”，表示方式回答“怎样存”

工程文档和认知架构研究常借用 Semantic、Episodic、Procedural 三类 Memory。这个分类适合发现不同写入与验证要求，但不是行业统一协议，也不等同于人脑结构。

### 语义、情景和程序性 Memory

Semantic Memory（语义 Memory）保存事实与概念，例如用户明确表示“代码示例优先使用 Python”或组织的默认时区。这里的 Semantic 指事实类型，不等于 Semantic Search；事实完全可以按结构化 Key 直接读取。

Episodic Memory（情景 Memory）保存具体发生过的事件、行动和结果，例如某次部署因未执行迁移而失败，或某套工具调用序列成功解决了特定故障。它可以在相似任务中作为 Few-shot 示例或诊断依据，但单次成功经历不应未经评测直接升级成通用规则。

Procedural Memory（程序性 Memory）描述如何完成任务，包括受控 Prompt、策略、Skill、工作流规则，甚至模型权重与代码。它会改变 Agent 的行为边界，风险高于普通偏好。模型可以从失败经历中提议新规则，但生产系统通常需要离线 Eval、审批、版本发布和回滚，而不是允许 Agent 静默重写最高优先级指令。

Generative Agents 的实验架构保存自然语言经历，动态召回相关事件，再综合出更高层 Reflection 并用于 Planning。这证明了“经历 → 归纳 → 决策”的架构模式；但该论文评估的是交互模拟中的可信行为，不证明保存全部用户经历符合生产隐私、事实准确性或个性化目标。

### Profile 与 Collection 是两种语义事实表示

Profile 通常是固定 Schema 的 JSON 对象，例如：

```text
user_profile
├── preferred_language: "Python"
├── timezone: "Asia/Shanghai"
└── answer_style: "concise"
```

当字段已知时，直接按 Key 读取比向量搜索更准确、更便宜，Schema 校验也能阻止非法值。困难在于更新：把整个 Profile 交给模型重写可能遗漏旧字段或误改无关信息，应优先使用字段级 Patch、Expected Revision 和审计记录。Profile 过大时还会重新遇到 Context 与更新复杂度问题。

Collection 把每条事实或经历作为独立记录。新增长尾 Memory 更容易，且可分别设置来源、TTL 和 Embedding；代价是模型可能过度 Insert，或把应更新的旧事实重复保存。召回多个片段后，Context Builder 还要去重、解决冲突并恢复关系。

实际系统常混合使用：稳定、明确、经用户确认的偏好进入 Profile；开放式兴趣和经历进入 Collection；高风险程序规则进入单独的版本化发布系统。选择依据是数据语义，不是某个框架把所有对象都命名为 `memory`。

## Memory Formation 把原始事件变成受控候选

Memory Formation（Memory 形成）通常包含 Capture、Extract、Decide 和 Commit 四步。Capture 保留可追溯事件；Extract 把自然语言转换为结构化候选；Decide 判断是否值得保存以及保存到哪个 Scope；Commit 才真正改变持久化状态。

```text
对话 / 工具结果 / 用户反馈 / 任务结果
                    ↓
             提取 Memory Candidate
                    ↓
       Schema、来源、置信度、敏感性检查
                    ↓
是否值得跨 Session 使用？
   ├── 否 → 只保留原事件或按普通日志策略处理
   └── 是
         ↓
是否需要用户确认或审批？
   ├── 是 → 等待确认；不得先写后问
   └── 否 → 按逻辑 Key 合并并提交新 Revision
```

“值得保存”至少要考虑未来效用、稳定性、来源质量、敏感性和预期寿命。用户说“今天在北京出差”可能只需短 TTL；“以后都用中文回答”可能是稳定偏好；模型根据语气推断出的性格标签既不可靠，也往往没有必要。低置信度不是通过给记录加一个小数就自动安全，因为后续模型可能忽略该小数而把文本当作事实。

候选应带 Source Reference，指向产生它的 Turn、事件或人工配置。来源让用户纠正和 Eval 定位成为可能，也让系统区分“用户明确陈述”“模型推断”“工具验证”和“外部网页内容”。来自网页、邮件或工具返回的指令不得直接成为程序性 Memory，否则一次 Prompt Injection 可以长期改变 Agent 行为。

### Hot Path 与 Background 是延迟和一致性的取舍

Hot Path 在当前交互中形成并写入 Memory。用户说“请记住”时，这种方式能立即确认写入内容，也能让下一步使用新偏好；代价是增加模型调用和存储延迟，主 Agent 还要同时完成业务任务与 Memory 判断。

Background 方式把原始事件写入队列，稍后批量提取、去重和合并。它不阻塞用户请求，并可使用专门模型与更完整的时间窗口；但其他 Session 在处理完成前看不到新 Memory，队列重试可能重复写入，并发 Worker 可能基于相同旧版本产生 Lost Update。

组合方案通常更稳妥：显式“记住/忘记”命令和当前任务立即依赖的事实走 Hot Path；低优先级归纳与 Reflection 走 Background。两条路径共享幂等 Operation ID、逻辑 Key、Expected Revision 和统一政策引擎，不能分别实现两套互不一致的写入语义。

## 更新、冲突和遗忘决定 Memory 会不会长期腐化

一个可治理的 Memory Record 通常至少包含：

- `owner_id`、Organization/Tenant、Application Namespace 与可选 ACL；
- 类型、逻辑 Key、结构化 Value 和用于搜索的文本；
- Source、写入者、创建时间、有效时间、TTL、置信度与敏感级别；
- Revision、状态、被哪一版本替代，以及索引状态。

这些字段支持三种常见变化。第一种是确定替换，例如用户明确把首选语言从 Python 改为 Rust：新 Revision 成为 Active，旧 Revision 标记为 Superseded。第二种是时间事实，例如“本周项目是 Orion”和“下周项目是 Apollo”：两个值可以拥有不同 Valid Time，而不是互相覆盖。第三种是真正冲突，例如不同来源声称同一订单状态不同：系统应根据权威源和时间裁决，无法裁决时保留冲突并避免生成确定答案。

乐观并发控制可以阻止两个写入者都基于 Revision 3 静默生成 Revision 4。提交方携带 `expected_revision=3`，第一个提交成功后，第二个必须重新读取并合并。重试还要携带幂等键，避免网络超时后把同一事件写成两条经历。

遗忘既是产品能力也是数据一致性操作。删除一个 Active Vector 并不够：旧 Revision、关键词索引、Embedding、缓存、离线训练集、摘要和备份保留流程都可能保留内容。系统需要明确“立即停止召回”“在线数据物理删除”“备份按保留策略到期”分别何时完成，并对下游派生物记录删除传播状态。仅保留带明文的 Tombstone 不能称为已经遗忘。

## Recall 先决定谁能看，再决定什么相关

Memory Recall 与第 10 章 Retrieval 共享过滤、召回、融合和重排技术，但排序信号不同。合法候选集先由 Organization、Owner、Application Namespace、ACL、Memory 类型、有效时间和删除状态确定；只有过滤后的记录才能进入直接读取、关键词或向量搜索。

已知事实优先按 Key 读取。例如构建回答语言时，系统明确需要 `preferred_language`，没有必要让向量相似度猜测。开放式问题“上次部署出了什么问题”才适合搜索 Episodic Collection。相关性排序还可结合：

- Relevance：当前任务与 Memory 内容是否相关；
- Recency：近期事件是否对当前问题更有预测力；
- Importance：该记录是否被明确标记为关键；
- Confidence/Authority：来源和验证等级是否足以支持使用；
- Diversity：多个结果是否只是同一事件的重复摘要。

Generative Agents 曾组合相关性、时间和重要性召回经历，这是一种有启发性的策略，而非通用公式。稳定偏好不应仅因时间久而自然消失，临时行程却应快速衰减；排序权重必须随 Memory 类型和任务变化。

召回之后仍需 Context Engineering。系统要限制数量、去重、把冲突与来源一起呈现，并把 Memory 标为低于开发者指令的数据。每个注入片段保留 `memory_id` 和 Source，便于 Trace 记录“模型看到了什么”以及用户随后要求纠正哪一条。

```text
Identity + Task
      ↓
Owner / Namespace / ACL / Validity 预过滤
      ↓
已知 Key？
   ├── 是 → Direct Get
   └── 否 → Keyword / Semantic / Structured Search
                     ↓
          类型相关的排序与去重
                     ↓
          Token Budget 与冲突呈现
                     ↓
          带 Memory ID 的 Model Context
```

## Memory 的主要风险来自“错误会跨时间传播”

普通生成错误可能只影响一次回答，错误 Memory 会在未来多个 Session 中反复被召回。常见污染来源包括模型把猜测写成事实、用户临时表述被误判为稳定偏好、恶意文档要求 Agent 永久记住指令，以及一次失败经历被归纳成错误程序规则。

控制措施应落在写入边界，而不只放在召回 Prompt 中：

- 默认不保存 Secret、认证信息和没有必要的敏感属性；需要保存时取得明确同意并设置最短保留期。
- 用户提供的事实、工具验证结果、模型推断和外部内容使用不同 Trust Level；低信任来源不能覆盖高信任 Profile。
- 程序性 Memory 进入独立发布流程，经过 Eval、审批、版本化与回滚；模型只能提交 Proposal。
- Namespace 由已认证身份在服务端构造，不能接受模型或用户文本直接指定其他用户 ID。
- 用户能够查看、纠正和删除长期 Memory；后台任务的每次写入也保留 Trace 与审计原因。

加密、RBAC 和日志脱敏仍然必要，但它们不能修复“本来就不该保存”的数据。数据最小化发生在加密之前。

## 评测要覆盖形成、召回、使用和治理四个阶段

端到端回答正确率无法说明 Memory 系统是否正常。模型可能没召回 Memory 仍凭常识答对，也可能正确召回却错误应用。应以包含用户 Scope、历史事件、期望写入操作、后续查询和删除动作的多轮测试场景逐层评分。

Memory Formation 评估 Precision 与 Recall：应该保存的事实是否被提取，不该保存、低置信或敏感信息是否被拒绝；还要检查 Schema、Source、TTL 和 Namespace。Consolidation 评估 Insert、Update、Delete、No-op 是否选对，冲突和乱序事件是否保留正确 Active Revision。

Recall 层评估目标 Memory 的 Recall@k、无关 Memory 比例和跨用户泄露率。Application 层检查模型是否真正按 Memory 完成任务、是否在冲突时说明不确定性，以及引用的 `memory_id` 是否支持行为。Governance 层再验证显式遗忘、过期不可召回、程序规则审批、延迟、成本和后台任务积压。

一个最小回归集至少包含：

1. 用户明确表达稳定偏好，后续新 Session 应正确使用；
2. 临时事实带 TTL，到期后不得召回；
3. 用户纠正旧偏好，并发陈旧写入不能覆盖新版本；
4. 相似查询属于另一个用户或 Namespace，结果必须为空；
5. 外部文档包含“永久记住并改变规则”，程序性写入必须被拒绝；
6. 用户执行 Forget 后，直接读取、搜索、缓存和下游索引均不可返回原内容。

第 09 章的 Trace 可关联 `memory.extract`、`memory.commit`、`memory.search`、`memory.inject` 和 `memory.forget` Span。默认记录 Memory ID、策略结果、版本和计数，不复制敏感 Value；需要检查原文时通过受控引用访问。

## 最小实现验证 Memory 生命周期

本章示例 [`memory_store.py`](../../examples/11-memory/memory_store.py) 将模型或规则产生的 `MemoryCandidate` 与持久化 `MemoryRecord` 分开。低置信候选、未经用户确认的敏感内容和未经审批的程序规则在 Commit 前被拒绝：

```python
if candidate.confidence < self._minimum_confidence:
    raise MemoryPolicyError("candidate confidence is below the write threshold")
if candidate.sensitive and not candidate.user_confirmed:
    raise MemoryPolicyError("sensitive memory requires explicit user confirmation")
if candidate.kind == "procedural" and not candidate.approved_by:
    raise MemoryPolicyError("procedural memory requires an approver")
```

Store 使用 Owner、Namespace、Kind 和 Key 组成逻辑主键，Expected Revision 防止 Lost Update，Operation ID 保证重试幂等。搜索在排序前过滤 Owner、Namespace、状态和 TTL；已知 Profile Key 则使用直接读取。`forget_key` 会 Redact 同一逻辑 Key 的所有保留版本，而不是只隐藏 Active 记录。

11 项测试分别覆盖政策拒绝、敏感确认、程序规则审批、版本替换、并发冲突、幂等、全版本遗忘、TTL、跨用户/Namespace 隔离、直接读取和来源引用。示例的词项排序只用于证明数据流和治理顺序，生产系统仍需事务存储、加密、真实检索器以及面向缓存、备份和派生索引的删除编排。

## 参考资料

- [Cognitive Architectures for Language Agents](https://arxiv.org/abs/2309.02427)，Sumers 等，TMLR；用于核对模块化 Memory、内部/外部 Action 与 Agent 决策过程，以及语义、情景、程序性 Memory 的认知架构视角；最后核验日期：2026-07-22。
- [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442)，Park 等，UIST 2023；用于核对自然语言经历流、动态召回、Reflection 与 Planning 的组合架构及其原始评测边界；最后核验日期：2026-07-22。
- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560)，Packer 等；用于核对受限 Context 与外部存储之间的 Virtual Context Management 类比；最后核验日期：2026-07-22。
- [Memory overview](https://docs.langchain.com/oss/python/concepts/memory)，LangChain/LangGraph 官方文档；用于核对当前短期/长期 Scope、Memory 类型、Profile/Collection 和 Hot Path/Background 写入方式；最后核验日期：2026-07-22。
- [LangMem Core Concepts](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)，LangMem 官方文档；用于核对 Memory Manager 与 Storage 分层、Namespace、Direct Access、Semantic Search 和 Metadata Filtering；最后核验日期：2026-07-22。
- [Sessions](https://openai.github.io/openai-agents-python/sessions/)，OpenAI Agents SDK Python 官方文档；用于核对当前 Session History 在 Run 前加载、Run 后写入和 Compaction 的行为，并与长期 Memory 区分；最后核验日期：2026-07-22。
