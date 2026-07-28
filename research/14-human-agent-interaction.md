# 第 14 章研究记录：Human-Agent Interaction

> 状态：待人工审核的资料核验记录。最后核验日期：2026-07-23。

## 研究问题

1. Human-in-the-loop 除了 Tool Approval，还包含哪些交互和控制点？
2. Clarification、Elicitation 与 Approval 为什么不能共享同一语义？
3. 怎样按风险、可逆性、作用域和预授权选择自动化程度？
4. Interrupt、Pause、Resume 与 Cancel 如何映射到持久 Workflow State？
5. 如何展示进度与中间 Artifact，而不把 Token 或 Chain-of-Thought 当成业务进度？
6. 用户纠正怎样使 Plan、Approval、Cache 和下游结果失效？
7. 怎样呈现拒绝、失败、部分成功和结果未知，并设计人工接管？
8. 如何减少 Approval Fatigue，同时保持高风险动作的有效控制？
9. 人、Agent、Runtime、Tool 和组织之间如何划分责任并评测控制效果？

## 范围边界

- 第 13 章已解释 Durable Workflow、Checkpoint、Pause/Resume、Cancel 与 Compensation；本章从人的信息和控制需求出发，不重复工作流引擎实现。
- 第 16～18 章将讨论 MCP 和其他协议；本章只使用 Elicitation 说明结构化的人类输入语义。
- 第 21、22 章将系统讨论权限、Prompt Injection、身份和审计；本章只覆盖审批与交互直接依赖的安全边界。
- 不把隐藏 Chain-of-Thought 视为用户可见进度或审计材料，只展示结构化短依据、环境结果和 Artifact。

## 一手资料与采用结论

### 1. OpenAI Agents SDK: Human-in-the-loop

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/human_in_the_loop/
- 采用结论：工具可声明静态或按调用决定的审批条件；未决 Tool Call 作为 Interruption 暂停 Run，转换为 `RunState` 后记录批准或拒绝，再以原始顶层 Agent 恢复。Run State 支持序列化以处理长时间审批，并应保存 Agent/SDK 版本标记。
- 正文用途：核对 Tool Approval、Run-wide Interruption、跨进程恢复、Session 与持久状态的实现边界。
- 版本说明：SDK API 变化快，正文只保留机制，不复制所有当前参数枚举。
- 最后核验日期：2026-07-23。

### 2. OpenAI Agents SDK: Streaming

- 来源：OpenAI Agents SDK 官方文档。
- 链接：https://openai.github.io/openai-agents-python/streaming/
- 采用结论：Streaming 可产生 Raw Response Event 与更高层 Run Item/Agent Event；流需要消费完毕才可判断 Run 状态，最后可见 Token 后仍可能有持久化、审批 bookkeeping 或 Compaction。审批暂停与流结束可以同时发生，恢复应从 `RunState` 继续。
- 正文用途：区分 Token Streaming、语义进度和 Run Completion。
- 最后核验日期：2026-07-23。

### 3. Trustworthy agents in practice

- 来源：Anthropic 官方研究文章，2026-04-09。
- 链接：https://www.anthropic.com/research/trustworthy-agents
- 采用结论：人类控制依赖可配置工具权限和恰当的监督粒度；逐动作重复确认会产生摩擦并被忽略，计划级审查可以把判断提升到策略层。Agent 应区分可以从环境查询的事实与只能由用户决定的偏好/意图。
- 正文用途：支持风险分级、Approval Fatigue、计划级审批与澄清边界。
- 最后核验日期：2026-07-23。

### 4. MCP Elicitation 2025-11-25

- 来源：Model Context Protocol 正式规范。
- 链接：https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation
- 采用结论：Server 可经 Client 请求额外信息；当前正式版包含 Form 与 URL 两种模式，响应明确区分 Accept、Decline 和 Cancel。双方应验证 Schema，Client 应显示请求来源与用途；Form Mode 不得请求密码/API Key，URL Mode 有独立安全限制。
- 正文用途：区分协议级 Elicitation、自然语言 Clarification 和副作用 Approval。
- 版本说明：`docs/LEARNING_PATH.md` 原入口为 2025-06-18；按项目规则采用更新的 2025-11-25 正式版本，Draft 未作为正文事实来源。
- 最后核验日期：2026-07-23。

### 5. Guidelines for Human-AI Interaction

- 来源：Amershi 等，CHI 2019 原始论文；Microsoft Research 发布页。
- 链接：https://www.microsoft.com/en-us/research/publication/guidelines-for-human-ai-interaction/
- 采用结论：论文综合 150 余条建议形成 18 条一般指南，并经三轮评估；正文采用“说明系统能力与局限”“按上下文选择打断时机”“支持高效纠正”“不确定时收缩服务”“说明系统行为原因”等具体指南。
- 正文用途：建立进度、失败、不确定性和纠正的交互原则，而不是只讨论后端状态。
- 最后核验日期：2026-07-23。

### 6. NIST AI RMF Appendix C

- 来源：NIST AI Resource Center，AI RMF 1.0 附录。
- 链接：https://airc.nist.gov/airmf-resources/airmf/appendices/app-c-ai-risk-management-and-human-ai-interaction/
- 采用结论：Human-AI 配置可以从完全自动到完全人工；组织应明确区分 AI 系统使用者、交互者、性能监督者和治理责任。是否需要人类监督取决于上下文与风险，不是所有 AI 功能都使用同一监督强度。
- 正文用途：说明自动化程度、组织责任和 Human Oversight 不是一个 UI 开关。
- 版本说明：NIST 页面说明 AI RMF 1.0 正在更新；正文只使用现行 1.0 中稳定的角色与监督原则。
- 最后核验日期：2026-07-23。

## 术语与工程决策

### 有效控制需要可理解、可拒绝和来得及

仅记录“用户点击同意”不能证明有效控制。审批请求必须显示具体意图和影响，Decision 必须有拒绝/取消路径，且在副作用前发生；审批人还需具备身份、权限和理解任务的能力。

### 风险由 Runtime Policy 计算

模型不能通过输出 `risk="low"` 给自己授权。Tool Policy 提供基础风险，Runtime 再结合参数、身份、资源和范围决定 Auto/Require/Block；Prohibited 动作没有人工绕过入口。

### Approval 绑定 Action Snapshot

示例以 Run、Action ID、Tool、Arguments、Policy Version 和 Plan Revision 计算 Digest，并设置 Expiry。Resume 前重新计算；参数变化或过期都会使批准失效。

### Cancel 不抹除在途结果

Cancel 停止新工作和未决审批，但已执行的调用可能晚到。示例允许在 Run Cancelled 后记录 Executing Action 的最终结果，以支持对账与补偿。

### Correction 沿依赖传播

纠正使目标及其传递依赖者失效，并递增 Plan Revision。已完成外部副作用不能标成“未发生”，示例拒绝直接 Correction，要求先进入 Compensation 或人工修复流程。

## 示例设计

`examples/14-human-agent-interaction/interaction_controller.py` 使用 Python 标准库实现：

- Runtime-owned `ToolRule` 与 Auto/Require/Block；
- 绑定 Action Digest、Policy Version、审批人和 TTL 的 Approval Request；
- `accept`、`decline`、`cancel` 三态决定；
- Clarification/Elicitation Request 与最小必填字段验证；
- `InteractionState` JSON 序列化和恢复；
- Action 依赖、Correction 失效传播和 Plan Revision；
- Cancel 后停止未决工作并保留在途晚到结果；
- 不包含 Tool Arguments 的 Public Progress Projection。

## 待人工审核项

- [ ] 具体风险等级、双人复核、预授权范围和审批 TTL 需由产品、安全、合规和业务共同定义。
- [ ] UI 是否足以让用户理解动作后果，需要可用性测试，不能只凭后端字段完整判断。
- [ ] 敏感 Run State 的加密、租户隔离、保留期、删除和审计策略需要结合部署环境确定。
- [ ] NIST AI RMF 1.0 正在更新，人工发布前应再次核对正式修订状态和 Appendix C 对应内容。
- [ ] MCP 正文使用 2025-11-25 正式规范；发布前应确认是否已有更新正式版本，Draft 不自动替代正式版。

## 自检记录

- [x] 正文结构符合 `docs/CONTENT_SPEC.md`
- [x] 面试提纲连续编号，问题均由教材正文支撑
- [x] Markdown 结构、链接和 UTF-8 编码通过检查
- [x] 示例通过单元测试与实际运行检查
- [x] 正文路径、编号和标题与 `SUMMARY.md` 一致
- [x] 00、01 正文未修改
