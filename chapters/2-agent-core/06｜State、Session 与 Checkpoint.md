# State、Session 与 Checkpoint

> 本文建立 Agent 的持久化执行模型：区分 Session、Run、State、Checkpoint 与业务数据，解释暂停恢复、并发更新和外部副作用的一致性边界。第 07 章将在此基础上讨论如何把已保存的信息选择性地编排成模型 Context。

## 面试速记

### 背诵提纲

**1. 基本定义**

Session 是组织多轮交互的逻辑容器，Run 是一次具体执行，State 是系统保存的事实，Checkpoint 是恢复某个 Run 所需的版本化状态快照。

**2. 对象关系**

一个用户可以拥有多个 Session，一个 Session 可以包含多个 Run，一个 Run 又包含多个 Step；用户身份、`session_id` 与 `run_id` 不能相互替代。

**3. 完整恢复链路**

```text
加载 Checkpoint → 校验租户、版本与状态 → 注入审批或工具结果
                → 从确定位置继续执行 → 写入新版本 Checkpoint
```

**4. Session 与模型历史**

Session 可以保存消息和工具交互，但厂商 Conversation ID 或响应链通常只负责模型交互历史，不等于完整的应用 Session 和 Run State。

**5. Checkpoint 内容**

Checkpoint 至少应记录 Run 身份、执行状态、当前位置、业务输入或引用、挂起动作、预算、版本及幂等标识；只保存消息无法可靠恢复执行。

**6. 状态机约束**

恢复不是重新执行整个任务，而是从合法的中间状态继续；完成、失败或取消等终态通常不能直接回到运行态。

**7. 并发一致性**

应使用版本号和条件更新等乐观并发控制，拒绝陈旧写入覆盖新状态；同一 Session 的并发 Run 还要明确顺序与冲突策略。

**8. 外部副作用**

Checkpoint 只能记录 Runtime 对副作用的认知，无法与邮件、支付或第三方 API 自动组成事务；恢复时仍需幂等键、操作 ID、状态查询或补偿机制。

**9. 生命周期与安全**

持久化状态需要 Schema 版本、迁移、加密、访问隔离、保留期限和删除策略；不能因为对象可序列化就把密钥和无界历史全部保存。

### 高频对比

| 对象 | 主要作用 | 典型生命周期 | 不能替代什么 |
| --- | --- | --- | --- |
| Session | 组织一段连续交互 | 多个请求或 Run | 用户身份、Run 执行状态 |
| Run | 表示一次执行实例 | 从输入到完成、暂停、失败或取消 | 跨 Run 的会话容器 |
| Checkpoint | 保存 Run 的可恢复快照 | Run 执行期间产生多个版本 | 外部系统的真实业务状态 |

### 高频问题

#### 问题1：为什么有完整消息历史仍然不能可靠恢复 Agent？

消息历史通常没有记录当前节点、剩余预算、挂起审批、已确认的工具副作用和状态版本。重新把历史发给模型只能重新决策，不能证明执行会从原位置继续。

#### 问题2：Checkpoint 应该在什么时候写入？

应在可恢复的一致性边界写入，例如节点完成后、等待人工审批前后以及副作用状态得到确认后。写得过少会扩大重放范围，写得过多则增加延迟、存储和并发冲突。

#### 问题3：两个 Worker 同时恢复同一个 Run 怎么办？

使用版本号或租约进行条件更新，只允许一个 Worker 提交下一版本；失败的一方必须重新加载，而不是覆盖新状态。高风险操作还要在工具侧使用相同幂等键。

#### 问题4：工具已经成功，但写 Checkpoint 前进程崩溃，恢复后如何避免重复执行？

Checkpoint 本身无法消除这个不确定窗口。应让工具接受稳定的幂等键，或先查询外部操作 ID 的状态；无法幂等时需要人工确认或补偿流程。

#### 问题5：什么时候可以只用厂商托管的 Conversation，而不自建 Checkpoint？

当应用只需连续对话、没有可恢复的多步控制流和高风险副作用时，托管历史可能足够。一旦需要跨进程暂停、审批、并发控制或精确恢复，就应拥有独立的应用状态与 Checkpoint。

---

## 1. 先看完整恢复问题：进程退出后怎样继续同一个 Run

普通的一问一答可以近似看成无状态函数：提交输入，得到输出。Agent Loop 引入工具调用、多轮决策、等待、重试和人工审批后，一次请求可能持续数分钟甚至数天，也可能跨越多个进程。此时“把消息保存下来”只能回答模型看过什么，不能回答系统执行到了哪里、哪些动作已经发生、下一步是否允许继续。

继续使用第 05 章的订单任务。模型已经查到 A-17 可以取消，Runtime 也完成授权，但真正执行 `cancel_order` 前需要用户批准。等待期间原 Worker 可以退出；数小时后，另一个 Worker 收到批准并继续。完整过程是：

```text
用户请求取消订单 A-17
   ↓
Session 记录本轮交互
   ↓
Run 42 开始，状态为 running
   ↓
模型提出 cancel_order(A-17)
   ↓
Runtime 需要审批
   ↓
Checkpoint v3
  - tenant_id / session_id / run_id
  - status = interrupted
  - pending_action = cancel_order(A-17)
  - 当前步骤、预算、幂等键与版本
   ↓
原 Worker 退出
   ...
用户批准
   ↓
新 Worker 加载 Checkpoint v3
   ↓ 校验租户、状态、版本和挂起动作
Checkpoint v4：status = running
   ↓
使用原幂等键执行 cancel_order
   ↓
记录外部操作 ID 与结果
   ↓
Checkpoint v5：completed 或进入下一步
```

这张图说明了三个不同问题。Session 负责把交互归在一起；Run 表示这一次取消任务的生命周期；Checkpoint 保存新 Worker 恢复 Run 所需的控制事实。订单是否真的取消，仍由订单系统决定，不会因为本地 Checkpoint 写了 `completed` 就自动成立。

一个可恢复的 Agent 至少同时面对五类信息：

| 信息 | 例子 | 主要所有者 |
| --- | --- | --- |
| Run 控制状态 | 当前节点、状态、预算、挂起审批 | Agent Runtime |
| Session 交互历史 | 用户消息、模型输出、工具调用与结果 | 会话层 |
| 模型 Context | 本轮真正发送给模型的指令、历史和检索结果 | Context 编排层 |
| 业务状态 | 订单是否取消、退款是否到账 | 业务系统 |
| 长期记忆 | 跨会话偏好、稳定事实 | Memory 系统 |

State 是系统已经保存的事实集合，Context 则是从这些事实中挑选并编码给模型的本轮输入。完整 State 往往比 Context 大得多，也不应全部进入 Prompt。长期记忆的写入、检索和治理将在第 11 章展开；本章只处理 Session 内以及单个 Run 的可恢复状态。

## 2. 第一步：先分清 Session、Run、State 与业务对象

推荐先建立下面的身份关系：

```text
Tenant / User
   └── Session：一次逻辑会话
         ├── Run A：处理一次用户输入
         │     ├── Step 0
         │     ├── Step 1
         │     └── Checkpoint v0、v1、v2 ...
         └── Run B：处理下一次用户输入

外部业务系统
   └── Order / Payment / Ticket：独立的真实业务对象
```

`user_id` 标识主体，`session_id` 标识交互容器，`run_id` 标识一次执行。把三者合并会造成实际问题：用户无法拥有多段会话，同一会话的并发请求难以区分，运行失败后的重试也无法与原执行建立明确关系。多租户系统还应把 `tenant_id` 纳入每次查询和写入边界，而不能只在接口入口检查一次。

### 2.1 Session 负责组织交互

Session 通常保存或关联消息、模型输出、工具调用与工具结果。一次新 Run 开始前，会话层读取相关历史；Run 结束后，再把新增 Item 写回。历史可以由应用自己维护，也可以部分交给模型厂商托管。

以当前 OpenAI API 为例，应用可以手动携带历史，也可以使用带持久 ID 的 Conversation，或者通过 `previous_response_id` 串联响应。OpenAI Agents SDK 的 Session 则会在 Run 前读取历史、在 Run 后保存新增 Item。Anthropic Messages API 的请求由客户端提交 `messages` 数组，因此应用需要自己组织多轮历史。这些是 API 和 SDK 的具体选择，不改变核心边界：厂商保存的模型交互记录并不知道你的订单状态、审批策略或任务预算。

Session 也不等于“把所有旧消息永远拼回输入”。历史保留属于存储问题，哪些内容进入模型属于 Context Engineering 问题。把两者分开后，系统才能独立进行历史裁剪、摘要、权限过滤和成本控制。

### 2.2 Run 负责表达一次执行

Run 从一个明确输入开始，最终进入完成、暂停、失败或取消状态。一次 Session 可以连续产生多个 Run，也可能因为并发请求产生重叠 Run。Run 应拥有独立的预算、Trace、错误和状态版本，否则无法判断某次工具调用究竟属于哪次执行。

一个最小状态机可以表示为：

```text
                 ┌───────────────┐
                 │               ↓
running ─────→ interrupted ─────→ running
   │                 │               │
   ├──→ completed    ├──→ failed     ├──→ completed
   ├──→ failed       └──→ cancelled  ├──→ failed
   └──→ cancelled                    └──→ cancelled

completed / failed / cancelled：终态，不直接恢复为 running
```

“失败后重试”通常应该创建新的 Attempt，或从失败前的有效 Checkpoint 派生新 Run，而不是随意把终态改回运行态。这样才能保留审计链并区分原失败和后续重试。

到这里，对象层次已经明确：Session 不能替代 Run，Run 也不能替代外部订单。接下来要决定在什么边界保存哪些字段，才能让另一台 Worker 从唯一合法位置继续。

## 3. 第二步：Checkpoint 保存恢复所需的语义

Checkpoint 是某个 Run 在一个确定执行边界上的版本化快照。它的判断标准不是“序列化是否成功”，而是：换一台 Worker、隔一段时间重新加载后，Runtime 是否能够判断已经发生了什么，并从唯一且合法的位置继续。

一个生产 Checkpoint 通常需要覆盖：

- 身份与隔离：`tenant_id`、`session_id`、`run_id`；
- 控制状态：Run 状态、当前节点或步骤、循环次数、时间和成本预算；
- 数据状态：业务输入或稳定引用、节点输出、消息或 Artifact 引用；
- 挂起状态：待审批的具体 Tool Call、审批要求、恢复令牌或等待事件；
- 副作用证据：`tool_call_id`、幂等键、外部操作 ID 和已确认结果；
- 可重现元数据：模型、Prompt、工具定义、Workflow 与 Runtime 的版本；
- 治理元数据：Checkpoint 版本、State Schema 版本、创建时间和 Trace 关联 ID。

这不意味着所有字段都应复制进一个巨大 JSON。大对象可以放在 Artifact Store，Checkpoint 只保存不可变引用和完整性信息。密钥、访问令牌等 Secret 应通过运行时安全注入获取，不能因为恢复方便而写入普通序列化状态。

### 3.1 消息历史不能回答执行到了哪里

假设模型已经提出 `cancel_order(A-17)`，Runtime 正在等待人工批准。消息历史可能包含工具调用，但未必说明：审批属于哪个租户、谁有批准权、预算是否已耗尽、工具是否已经执行，以及拒绝后应该进入哪个节点。若仅把消息重新发给模型，模型可能再次提出相同调用，却无法恢复原调用的控制状态。

因此，消息历史可以成为 Checkpoint 的一部分或引用对象，却不是 Checkpoint 的同义词。前者面向模型交互，后者面向 Runtime 恢复。

对 A-17 的取消任务，Checkpoint 必须明确保存“正在等待哪一次调用的审批、批准后应从哪里继续、原幂等键是什么”。如果只有一条“模型建议取消订单”的消息，新 Worker 无法判断该重新请求审批、直接执行，还是任务已经被用户拒绝。

## 4. 第三步：把暂停和恢复实现成受约束的状态转换

人工审批是最直观的恢复场景。一个可靠流程不是阻塞进程等待，而是把等待变成持久状态：

```text
Runtime        Checkpoint Store        审批系统          Tool
   │                   │                  │               │
   ├─产生待审批调用────→│ 保存 interrupted │               │
   │                   ├─返回 run/version │               │
   │                   │                  │               │
   │                   │←────审批决定─────┤               │
   ├─加载并校验版本────→│                  │               │
   ├─写入 running 新版─→│                  │               │
   ├──────────────────────────────────────→│ 执行动作      │
   │←──────────────────────────────────────┤ 返回操作 ID   │
   └─保存结果与下一步──→│                  │               │
```

恢复入口必须同时验证租户、Run 状态、Checkpoint 版本和挂起动作 ID。批准不能只携带一个 `run_id`，否则陈旧页面可能批准已经变更或取消的动作。审批决定也应进入审计记录，而不是覆盖原始待审批数据。

Checkpoint 的写入频率取决于可接受的重放范围。每个细粒度计算后都落盘可以缩小丢失窗口，却增加 I/O、延迟和冲突；只在 Run 结束时写入则无法恢复中间过程。通常选择具有业务语义的边界：节点完成后、进入等待前、收到恢复事件后，以及外部副作用得到确认后。

进入等待前写入 v3，使原 Worker 可以安全退出；收到批准后写入新的 `running` 版本，使并发恢复者能够看到所有权已经变化。版本递增不是审计装饰，而是拒绝陈旧 Worker 覆盖新状态的条件。

### 4.1 用版本条件拒绝并发恢复产生的陈旧写入

同一个 Run 可能因为消息重复投递、Worker 超时或用户重复点击而被同时恢复。若采用“最后写入者获胜”，较慢 Worker 会把新状态覆盖成旧状态。最小防线是乐观并发控制（Optimistic Concurrency Control，OCC）：

```sql
UPDATE run_checkpoints
SET version = :old_version + 1, state_json = :new_state
WHERE tenant_id = :tenant_id
  AND run_id = :run_id
  AND version = :old_version;
```

受影响行数为零，表示状态已经被其他执行者修改或删除。当前 Worker 必须停止提交并重新读取，不能自动用旧结果覆盖。对于执行时间很长的节点，还可以结合带过期时间的租约，但租约过期同样不能证明旧 Worker 已经停止，因此提交时仍需版本或 fencing token 校验。

同一 Session 的不同 Run 也可能冲突。例如用户先发出“取消订单”，紧接着又发出“不要取消”。系统必须明确采用串行队列、因果版本、业务对象锁还是允许并发后冲突检测。Session ID 只是归组标识，本身不提供顺序保证。

### 4.2 Checkpoint 无法自动覆盖外部副作用

最危险的失败窗口是：工具已经成功，进程却在保存结果之前崩溃。恢复后只看到旧 Checkpoint，Runtime 无法仅凭本地数据库判断外部动作是否发生；盲目重试可能重复扣款、重复发邮件或重复创建工单。

```text
写前 Checkpoint ─→ 调用外部工具 ─→ 工具成功 ─X→ 写后 Checkpoint
                                      ↑
                          崩溃后最难判断的窗口
```

这也是“Checkpoint 提供 exactly-once 执行”的说法不成立的原因。常见控制手段是：

- 向工具传递由 `run_id + tool_call_id` 派生的稳定幂等键；
- 保存外部系统返回的操作 ID，并在恢复时先查询状态；
- 对本地可控的消息发送采用事务性 Outbox，再由独立投递器发送；
- 无法查询或幂等的高风险动作进入人工确认；
- 对已经发生且无法撤销的动作设计语义明确的补偿操作。

工具侧的幂等语义已在第 05 章建立；更完整的持久化 Workflow、重试与补偿将在第 23 章展开。本章需要记住的边界是：Checkpoint 恢复 Runtime，业务系统仍是外部事实的权威来源。

在 A-17 案例中，最危险的不是“忘记保存一条消息”，而是订单系统已经取消成功，本地却仍停留在执行前的 v4。恢复时必须使用原幂等键或外部操作 ID 查询结果，不能仅凭旧 Checkpoint 再次取消。

## 5. 用最小 SQLite Store 验证恢复语义

仓库中的完整示例位于 [`examples/06-state-session-checkpoint/`](../../examples/06-state-session-checkpoint/)，使用 Python 标准库和 SQLite 展示三个核心机制：持久化存储、租户隔离和带版本条件的更新。数据模型保留了 Run 状态、步骤、JSON State、挂起动作和 State Schema 版本。

创建 Run 时版本从 `0` 开始；每次保存都要求调用者持有当前版本：

```python
cursor = self._connection.execute(
    """
    UPDATE run_checkpoints
    SET session_id = ?, version = ?, status = ?, step = ?,
        state_json = ?, pending_action_json = ?, state_schema_version = ?
    WHERE tenant_id = ? AND run_id = ? AND version = ?
    """,
    (
        updated.session_id,
        updated.version,
        updated.status.value,
        updated.step,
        json.dumps(updated.state, ensure_ascii=False, sort_keys=True),
        self._dump_optional(updated.pending_action),
        updated.state_schema_version,
        updated.tenant_id,
        updated.run_id,
        checkpoint.version,
    ),
)
if cursor.rowcount != 1:
    raise CheckpointConflict("checkpoint was changed or removed")
```

示例还用显式状态转换表拒绝从终态恢复，并禁止步骤倒退。单元测试验证了文件数据库关闭后重新打开仍能读取、错误租户无法访问、两个读取者中的陈旧写入被拒绝，以及中断状态可以在注入决定后继续。

这个实现只用于验证状态语义，并非完整生产存储：它没有历史版本表、加密、租约、事件日志、备份或数据库级行权限，也没有处理外部副作用的 Outbox。生产设计应按故障模型选择关系数据库、Workflow Engine 或框架提供的持久化后端，而不是机械放大示例。

## 6. 跨版本恢复必须同时治理 Schema 与数据生命周期

跨小时或跨天恢复意味着“写入状态的代码版本”可能不同于“读取状态的代码版本”。只给数据库表做迁移还不够，JSON State、Prompt、工具参数和 Workflow 拓扑也会演进。Checkpoint 应保存 `state_schema_version` 以及必要的定义版本；加载时要么执行受测试的迁移，要么明确拒绝恢复并转人工处理。

版本记录不是为了完全重放模型的随机输出。它的作用是让系统知道当前状态适用于哪套解释规则，并能定位升级造成的不兼容。对长期挂起任务，OpenAI Agents SDK 的官方文档也提醒应记录 Agent 定义或 SDK 版本，并谨慎处理序列化 Context 中的 Secret。

最后，持久化能力必须配套生命周期治理：

- 按租户和用户授权读取，避免通过可猜测的 Run ID 越权；
- 对静态数据加密，并对日志、备份和导出采用相同保护；
- 给完成 Run、失败 Run 和会话历史设置不同保留期限；
- 支持隐私删除，同时处理 Checkpoint、Artifact、Trace 和索引中的副本；
- 监控挂起过久、版本冲突激增、迁移失败和存储无界增长。

完成这一层后，系统已经能够可靠保存“有什么”和“执行到哪里”。下一章要解决另一个问题：在有限的 Context Window 中，应该把哪些状态、以什么顺序和格式提供给模型。

## 学习检查

完成本章后，应能：

- 画出 Tenant、User、Session、Run、Step、Checkpoint 与外部业务对象的层次；
- 解释消息历史、厂商 Conversation 和 Runtime Checkpoint 各自保存什么；
- 为等待 `cancel_order(A-17)` 审批的 Run 设计可恢复 Checkpoint；
- 区分 `running`、`interrupted` 与终态，并拒绝非法状态回退；
- 使用版本条件更新阻止两个 Worker 同时提交同一 Run；
- 解释工具成功但 Checkpoint 未写入时为什么会产生未知结果窗口；
- 使用幂等键、外部操作 ID、状态查询或补偿协调外部副作用；
- 为 State Schema 迁移、租户隔离、加密、保留和删除制定治理规则。

## 参考资料与结论对应关系

- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)，OpenAI API 官方文档；用于核对客户端历史、Conversation 对象与 `previous_response_id` 的状态延续方式；最后核验日期：2026-07-22。
- [Sessions](https://openai.github.io/openai-agents-python/sessions/)，OpenAI Agents SDK 官方文档；用于核对 Session 在 Run 前后读取和保存交互历史，以及恢复时的 Session 后端要求；最后核验日期：2026-07-22。
- [Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)，OpenAI Agents SDK 官方文档；用于核对 `RunState` 的序列化、跨进程恢复、审批流程、版本记录和 Secret 风险；最后核验日期：2026-07-22。
- [Create a Message](https://platform.claude.com/docs/en/api/messages/create)，Anthropic Claude API Reference；用于核对 Messages API 由客户端组织消息历史的接口语义；最后核验日期：2026-07-22。
- [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)，LangGraph 官方文档；用于核对 Checkpoint、Thread 与跨 Thread Store 的边界，以及持久化对恢复、人工介入和容错的作用；最后核验日期：2026-07-22。
