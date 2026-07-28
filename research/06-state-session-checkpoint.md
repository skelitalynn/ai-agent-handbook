# 第 06 章研究记录：State、Session 与 Checkpoint

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-22。

## 研究问题

1. Run State、Session History、模型上下文、业务状态和长期 Memory 的边界是什么？
2. 客户端历史、厂商托管 Conversation 和 `previous_response_id` 分别解决什么问题？
3. Checkpoint 必须保存哪些内容，怎样保证暂停后可以跨进程恢复？
4. 并发更新、重复恢复、Schema 演进和数据隔离应如何处理？
5. 为什么恢复 Checkpoint 不能自动撤销或证明外部 Tool 副作用？

## 范围边界

- 本章关注一次或多次 Run 的可恢复执行状态与会话边界。
- 第 07 章讲从已存状态中选择哪些内容进入模型 Context，不把“存储”与“提示模型”混为一谈。
- 第 11 章讲跨 Session 的长期 Memory。
- 第 13、14 章分别展开复杂 Workflow 和 Human-in-the-loop。
- 第 23 章展开分布式 Durable Execution、重试、补偿和故障恢复。

## 一手资料与采用结论

### 1. Conversation state

- 来源：OpenAI API 官方文档
- 链接：https://developers.openai.com/api/docs/guides/conversation-state
- 核对内容：请求可以由客户端手动携带历史；Conversations API 提供带持久 ID 的长生命周期对象并保存消息、Tool Call 和 Tool Output；也可用 `previous_response_id` 链接响应。
- 采用结论：厂商 Conversation/Response ID 是模型交互历史的延续机制，不等于应用的完整 Session、业务状态或可恢复 Runtime Checkpoint。
- 最后核验日期：2026-07-22

### 2. OpenAI Agents SDK Sessions

- 来源：OpenAI Agents SDK 官方文档
- 链接：https://openai.github.io/openai-agents-python/sessions/
- 核对内容：Session 在 Run 前读取历史并在 Run 后保存新 Item；中断恢复应继续使用同一 Session 后端；不同持久化后端、历史裁剪和 Session 生命周期。
- 采用结论：Session 主要提供按会话组织的交互历史；它可以辅助恢复，但不应被等同为包含审批、预算、挂起动作和执行版本的 Run State。
- 最后核验日期：2026-07-22

### 3. OpenAI Agents SDK Human-in-the-loop

- 来源：OpenAI Agents SDK 官方文档
- 链接：https://openai.github.io/openai-agents-python/human_in_the_loop/
- 核对内容：工具审批会中断 Run；`RunState` 可序列化、跨进程加载、批准或拒绝后恢复；序列化状态包含应用 Context 与 Runtime 元数据；长期挂起任务需保存定义或 SDK 版本标记。
- 采用结论：Checkpoint 必须保存可恢复控制状态和版本，而不只是消息；Secret 不应无意进入序列化 Context；审批必须绑定具体挂起调用。
- 最后核验日期：2026-07-22

### 4. Claude Messages API: Create a Message

- 来源：Anthropic Claude API Reference
- 链接：https://platform.claude.com/docs/en/api/messages/create
- 核对内容：Messages 请求通过 `messages` 数组提交对话输入，客户端负责组织多轮历史和 Tool Result 顺序。
- 采用结论：不同厂商是否托管历史、如何链接响应属于 API 差异；应用仍需拥有自己的身份、生命周期、隔离和恢复模型。
- 最后核验日期：2026-07-22

### 5. LangGraph Persistence

- 来源：LangGraph 官方文档
- 链接：https://docs.langchain.com/oss/python/langgraph/persistence
- 核对内容：Checkpointer 按 Thread 保存图状态，用于会话连续性、Human-in-the-loop、Time Travel 和容错；Store 保存跨 Thread 的应用数据；内存 Checkpointer 不跨重启，持久 Checkpoint 需要保留策略。
- 采用结论：Checkpoint 是特定执行线程的状态快照，跨线程长期数据属于另一存储层；生产恢复必须使用持久后端并控制无限增长。
- 最后核验日期：2026-07-22

## 术语决策

### Session 与 Run

Session 是多次交互的逻辑容器，一个 Session 可以包含多个 Run；Run 是从一次输入开始到完成、暂停、失败或取消的执行实例。正文使用独立 `session_id` 与 `run_id`，不把用户 ID 直接当 Session ID。

### Checkpoint 与消息历史

消息历史是可供模型消费的交互 Item 集合；Checkpoint 是恢复 Runtime 所需的状态快照，除历史引用外还应包含当前状态、步数、挂起动作、预算、版本和幂等信息。两者可以共享部分数据，但语义不同。

### Context 与 State

State 是系统保存的事实；Context 是本轮选择并编码给模型的输入。完整 State 往往大于 Context。第 07 章负责选择、压缩与编排 Context。

### Checkpoint 与外部副作用

数据库快照只能记录“Runtime 认为发生了什么”。它不会与邮件、支付或第三方 API 自动组成同一事务。恢复前仍要利用幂等键、外部操作 ID 或状态查询协调副作用。

## 示例设计

`examples/06-state-session-checkpoint/checkpoint_store.py` 使用标准库 SQLite 实现：

- 以 `(tenant_id, run_id)` 隔离和定位 Run；
- 保存 `session_id`、状态、步数、JSON Payload、挂起动作和 `state_schema_version`；
- 使用版本号和条件更新实现 Optimistic Concurrency Control；
- 验证 Run 状态转换，拒绝从终态恢复；
- 文件后端证明跨 Store 实例读取，内存模式只用于演示；
- 示例不声称与外部副作用构成分布式事务。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
