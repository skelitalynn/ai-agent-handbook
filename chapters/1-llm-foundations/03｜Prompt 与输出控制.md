# 03｜Prompt 与输出控制

> 第 02 章讲清了模型 API 怎样返回结果、用量和错误。本章继续解决两个问题：给模型什么输入，以及怎样确认它的输出可以交给业务程序使用。本章将这组可测试、可版本化的约定称为 `Prompt Contract`；这是本书使用的工程抽象，不是某家厂商定义的正式协议。

## 面试速记

### 背诵提纲

**1. 定义**

Prompt 是一次推理中提供给模型的指令、上下文、输入数据和示例；`Prompt Contract` 进一步约定任务目标、输入边界、输出格式与失败处理。

**2. 完整控制链**

```text
定义成功标准 → 构造 Input Contract → 调用模型
             → 检查终态 → 验证 Output Contract
             → 接受、修复、重试、降级或转人工
```

**3. Input Contract**

- **应用指令**：由受控代码提供任务、边界和不可由普通用户覆盖的业务规则。
- **用户请求**：表达本次任务参数，不应通过字符串拼接进入应用指令。
- **外部数据**：网页、文档和工具结果只是待处理的不可信数据，不因放入标签或 JSON 而获得指令权限。

**4. 行为引导**

Zero-shot 适合建立最小基线；Few-shot 只应用来演示确实存在的决策边界，否则会引入 Token 开销、示例偏差和顺序效应。

**5. Output Contract**

- **自由文本**：表达力最强，但机器解析最不稳定。
- **JSON Mode**：通常只保证合法 JSON，不保证符合业务 Schema。
- **Structured Outputs**：在模型和 Schema 子集支持范围内约束结构，但不保证字段值的事实和业务正确性。

**6. 运行时验证**

先检查模型调用终态，再依次做语法解析、Schema 校验、领域规则、跨字段约束和外部状态验证；任何一层失败都不能直接触发业务动作。

**7. Failure Handling**

可确定的格式噪声可以修复；信息不足、语义冲突、拒绝和连续失败应分别采取补充上下文、修改规则、降级或转人工，不能无限使用同一输入重试。

**8. 版本与评测**

Prompt 模板、变量、示例、Output Schema、模型和生成参数共同决定行为，必须联合版本化并在固定数据集上回归。

**9. 能力边界**

Prompt 只能改变生成分布，不会更新模型参数，也不是权限、事实校验或 Prompt Injection 防御的确定性边界。

### 高频对比

| 维度 | 自由文本 | JSON Mode | Structured Outputs |
| --- | --- | --- | --- |
| 可解析 JSON | 不保证 | 保证或强约束 | 保证或强约束 |
| Schema 一致性 | 不保证 | 不保证 | 在厂商支持的 Schema 子集内保证 |
| 表达灵活性 | 最高 | 中等 | 受 Schema 限制 |
| 应用侧校验 | 必须 | 必须 | 仍必须验证业务语义 |
| 典型场景 | 面向人的回答和创作 | 不支持严格 Schema 时的兼容方案 | 分类、抽取、UI 数据和机器处理结果 |

### 高频问题

#### 问题1：为什么 Structured Outputs 已经符合 Schema，应用仍然必须校验？

Schema 只能证明结构、类型和部分取值约束成立，不能证明摘要忠于原文、金额来自权威系统或操作符合当前权限。领域规则、跨字段关系和外部事实仍需确定性验证。

#### 问题2：为什么增加 Few-shot 示例有时反而让效果变差？

模型会同时学习示例中的正确模式、偶然措辞和错误偏差；示例与文字规则冲突、覆盖面单一或顺序不当时，输出会被拉向错误分布。是否保留示例应由消融评测决定。

#### 问题3：输出校验失败后，为什么不能一直把错误回传给模型重试？

相同输入往往产生相关失败，盲目重试只会累积延迟和成本。应先区分格式、缺失信息、Schema 设计、模型能力和业务冲突，再选择修复、有限重试、降级或人工处理。

#### 问题4：为什么把外部内容放进 XML 标签或 JSON 仍不能防住 Prompt Injection？

结构化边界只能帮助模型识别来源，不能让攻击文字失去影响生成的能力。真正的安全边界来自最小权限、工具参数校验、隔离、审批和输出验证。

#### 问题5：如何判断一次 Prompt 修改可以上线？

固定模型与参数，在包含正常、边界、历史故障和对抗样本的数据集上比较任务成功率、Schema 通过率、严重错误、拒绝率、延迟和 Token。通过离线门槛后仍应灰度发布并监控线上回归。

---

## 1. 先看一次完整的模型调用

### 1.1 从工单分类开始

假设我们要做一个客服工单分类器。用户提交一段文字，模型需要返回：

```json
{
  "category": "billing",
  "priority": 3,
  "summary": "用户反馈账单被重复扣款",
  "needs_human": false
}
```

这个任务不能只靠一句“请帮我分类”。模型可能返回一段解释而不是 JSON，也可能漏掉字段。即使 JSON 格式完全正确，分类和优先级仍然可能是错的。

如果程序直接使用这些结果，就可能把高风险工单送进错误的处理流程。因此，一次能进入业务系统的模型调用，需要完成以下链路：

```text
明确业务目标
   ↓
组织模型输入
   ↓
调用模型
   ↓
检查和验证输出
   ↓
接受结果，或者修复、重试和转人工
```

### 1.2 Prompt Contract 是这条链路的说明书

`Prompt Contract` 主要回答四个问题：

- 模型要完成什么任务？
- 模型可以看到哪些内容？
- 模型应该返回什么？
- 模型失败时，程序应该怎么办？

它不能保证模型一定听话。它的作用是把一次模型调用的输入、输出和失败分支写清楚，让它们可以被检查、测试和修改。

## 2. 先把模型输入说清楚

### 2.1 先定义什么结果算成功

写 Prompt 之前，应该先定义成功标准。

“回答得专业一些”不是有效标准，因为它无法稳定判断。对工单分类来说，更清楚的标准是：

- `category` 必须来自规定的分类；
- `priority` 必须是 1～5 的整数；
- 高风险工单不能漏掉人工审核；
- 返回结果必须符合指定格式；
- 信息不足时不能猜测，而要设置 `needs_human=true`。

这些标准会直接决定后面的设计。因为程序需要读取分类，所以需要固定字段；因为高风险工单必须审核，所以需要 `needs_human`。Prompt 不是从措辞开始设计的，而是从业务要求开始设计的。

### 2.2 把应用规则、用户请求和外部资料分开

模型输入通常来自三个地方：

| 内容 | 示例 | 应该怎样处理 |
| --- | --- | --- |
| 应用规则 | 分类标准、高风险处理规则 | 由程序固定提供 |
| 用户请求 | 本次提交的工单 | 作为待处理数据 |
| 外部资料 | 订单信息、知识库和检索结果 | 作为参考数据 |

这三类内容不能随意拼成一段话。例如：

```python
prompt = f"请按照系统规则分类。用户输入：{user_text}"
```

如果 `user_text` 中包含“忽略前面的规则”，这句话也会进入模型上下文。更清楚的做法是把固定规则和动态数据分开：

```text
[TASK]
根据固定规则对工单进行分类。

[INPUT]
{"ticket": "用户实际提交的内容"}

[OUTPUT]
返回 category、priority、summary 和 needs_human。
```

OpenAI 使用 `developer` 消息表达应用规则，Anthropic Messages API 使用顶层 `system` 参数承载系统指令。字段名称不同，原则是一样的：固定规则由程序提供，用户和外部内容作为数据传入。

这种分离可以减少歧义，但不是安全沙箱。模型仍然会读取 JSON 或 XML 里的攻击语句，后面仍然需要权限检查和输出验证。

### 2.3 遇到明确歧义时，再加 Few-shot 示例

建议先使用 Zero-shot，也就是只给任务、规则和输入，不提供示例。先运行一组测试，看模型具体错在哪里。

例如，模型经常混淆“申请退款”和“咨询退款政策”。这时可以分别提供一个示例，说明两者应该如何分类。

如果失败是因为工单里根本没有订单状态，增加再多示例也没有用。正确做法应该是查询订单系统，或者请用户补充信息。

```text
先运行 Zero-shot
   ↓
错误是否来自明确的分类歧义？
   ├── 是 → 加入少量对照示例，再重新评测
   └── 否 → 检查信息、规则、模型能力或任务拆分
```

Few-shot 不是越多越好。示例会占用上下文，也可能把旧规则和错误偏差带给模型。是否保留某组示例，应该由测试结果决定。

## 3. 让模型输出变成可读取的数据

### 3.1 自由文本、JSON Mode 和 Structured Outputs 分别解决什么

如果输出只给人阅读，自由文本通常足够。如果程序需要根据结果继续执行，就需要更严格的输出格式。

| 方式 | 能保证什么 | 不能保证什么 |
| --- | --- | --- |
| 自由文本 | 表达灵活 | 不保证格式稳定 |
| JSON Mode | 输出可以解析为 JSON | 不保证字段符合要求 |
| Structured Outputs | 字段和类型符合受支持的 Schema | 不保证内容真实、合理 |

例如，JSON Mode 可能返回：

```json
{
  "type": "billing"
}
```

它是合法 JSON，但业务需要的字段是 `category`、`priority`、`summary` 和 `needs_human`，所以程序仍然无法使用。

Structured Outputs 可以进一步约束字段和类型。但它只解决“返回的数据是什么形状”，不解决“返回的内容是不是对的”。

### 3.2 Schema 应该简单、稳定，并且留有不确定分支

工单分类的 Schema 可以规定：

- `category` 必须从固定分类中选择；
- `priority` 必须是 1～5 的整数；
- `summary` 必须是一定长度内的字符串；
- `needs_human` 必须是布尔值；
- 不接受没有声明的额外字段。

字段名称要尽量明确。`status` 可能是工单状态、支付状态或模型状态，`ticket_status` 就更容易理解。

Schema 也不是越复杂越好。层级过深会增加生成难度，也更容易超出不同厂商支持的范围。同时，Schema 需要留出“不确定”或“转人工”的路径，否则模型可能被迫选择一个错误答案。

OpenAI 和 Anthropic 都支持结构化输出，但两家支持的 JSON Schema 范围不完全相同。上线前必须使用实际模型和实际 Schema 测试，不能默认标准中的所有写法都被支持。

### 3.3 拒绝和截断不是正常输出

第 02 章已经讲过，HTTP 请求成功不等于模型已经正常完成任务。模型可能拒绝回答，也可能因达到长度上限而截断。

因此，程序应该先判断模型是否正常完成，再解析 JSON。如果对所有 HTTP 200 响应都直接执行 `json.loads`，正常的拒绝也会被错误记录为 JSON 故障。

## 4. 验证结果，并根据原因处理失败

### 4.1 格式正确不等于业务正确

假设模型返回：

```json
{
  "category": "billing",
  "priority": 5,
  "summary": "用户询问账单下载方式",
  "needs_human": false
}
```

这份数据可以完全符合 Schema，但如果业务规定“优先级为 5 时必须人工审核”，它仍然是错的。如果原工单只是普通咨询，`priority=5` 本身也可能是误判。

Structured Outputs 可以减少格式错误，但不会把模型变成数据库或权限系统。

### 4.2 按固定顺序验证

模型返回结果后，程序应该依次检查：

```text
调用是否正常完成？
   ↓
结果能否解析？
   ↓
字段和类型是否正确？
   ↓
业务规则是否成立？
   ↓
外部数据和用户权限是否有效？
```

对工单分类来说，这五步分别表示：

1. 检查模型是否正常完成，而不是拒绝或截断。
2. 检查返回内容能否解析成 JSON。
3. 检查是否包含所有必填字段，字段类型是否正确。
4. 检查 `priority=5` 时是否设置了人工审核。
5. 如果后续要修改真实工单，再检查工单是否存在，用户是否有权操作。

任何一步失败，都不能直接执行后续业务动作。

### 4.3 校验失败后不要只会重试

不同失败需要不同处理：

| 失败原因 | 处理方式 |
| --- | --- |
| JSON 外面多了允许的代码围栏 | 用程序去掉围栏，再重新校验 |
| 缺少必填字段 | 把具体错误返回给模型，有限重试 |
| 用户没有提供必要信息 | 请求补充信息，或调用外部系统 |
| 业务规则互相冲突 | 修改 Prompt、Schema 或规则源 |
| 模型拒绝回答 | 按产品规则降级或转人工 |
| 多次出现相同错误 | 停止重试，记录问题样本 |

确定性修复只适合不改变语义的问题，例如去掉已允许的代码围栏。不能用正则表达式猜测缺失的金额、类别或日期。

重试也只是再给模型一次机会，不会自动解决根本原因。如果 Schema 没有“不确定”分支，模型每次都被迫选择一个错误分类，那么重试十次也没有意义。

## 5. 把这条链路写成可测试代码

### 5.1 最小示例验证了什么

本章示例位于 [`examples/03-prompt-output-control/`](../../examples/03-prompt-output-control/)。它不调用真实模型，只验证应用程序能确定控制的部分：

| 示例代码 | 验证的问题 |
| --- | --- |
| `PromptContract.render` | 固定模板是否与用户数据分开 |
| `parse_classification` | 输出是否通过结构和业务规则检查 |
| `PromptContract.fingerprint` | 日志和评测结果能否定位到具体版本 |

模板把用户文本编码进 JSON，而不是直接插入固定规则：

```python
def render(self, ticket: str) -> str:
    if not ticket.strip():
        raise ValueError("ticket must not be empty")
    input_json = json.dumps({"ticket": ticket}, ensure_ascii=False)
    return TEMPLATE.format(input_json=input_json)
```

解析器则对结构和业务规则分别检查。例如：

```python
priority = value["priority"]
if isinstance(priority, bool) or not isinstance(priority, int):
    raise OutputContractError("priority must be an integer")
if not 1 <= priority <= 5:
    raise OutputContractError("priority must be between 1 and 5")
if priority == 5 and not value["needs_human"]:
    raise OutputContractError("priority 5 requires human review")
```

类型和范围是结构要求，“优先级 5 必须人工审核”是业务规则。真实项目可以使用 JSON Schema、Pydantic 或语言原生类型库完成结构检查，但业务规则仍然需要单独验证。

### 5.2 模型行为由多个版本共同决定

一次模型调用的结果不只由 Prompt 文本决定。示例、Schema、模型版本和生成参数也会改变结果。

因此，一次可复现运行至少应记录：

```text
Prompt 版本
Schema 版本
示例集版本
模型及其版本
生成与推理参数
评测数据集版本
```

示例代码会根据固定模板、Schema 和版本号计算指纹。这不是为了隐藏 Prompt，而是为了在出错时回答：这次运行究竟使用了哪一版设置？

### 5.3 用评测结果决定能否上线

评测集应该包含正常样本、边界样本、历史故障和对抗输入。工单分类可以检查分类准确率、高风险漏判率、Schema 通过率、延迟和 Token 消耗。

比较两版 Prompt 时，应该尽量固定模型、Schema 和其他参数。如果同时更换模型、增加示例并修改 Schema，即使结果变好，也无法确定是哪项修改起了作用。

一次人工测试成功不能证明可以上线。通过离线测试后，仍应先小流量发布，再观察错误率、拒绝率、重试率和成本。第 08 章会完整讲解 Agent Evals，第 25 章会继续讲生产发布。

## 6. 最后讲清 Prompt 做不到什么

### 6.1 Prompt 不是安全边界

把用户输入放进 JSON 或 XML，可以让结构更清楚，但不能让其中的攻击语句失效。外部网页、邮件、文档和工具结果仍然可能影响模型输出。

真正的安全措施是限制模型能使用的权限，在执行工具前检查参数，并对高风险操作要求人工确认。第 05 章会讲工具执行，第 24 章会完整讲 Prompt Injection 和 Agent Security。

### 6.2 Prompt 不是保密存储

系统 Prompt 对用户不可见，不等于其中的内容无法被推断。密钥、访问令牌和不必要的敏感数据不应放入 Prompt。真正的凭证应保留在模型看不到的执行环境中。

日志也不应默认完整保存所有用户输入和模型输出。为了调试保留足够的信息是必要的，但仍需要脱敏、保留期限和访问控制。

### 6.3 厂商 API 不应直接进入业务代码

OpenAI 和 Anthropic 表达指令、消息和结构化输出的字段不完全相同，而且这些字段会随 API 版本变化。

如果业务代码到处都直接操作厂商请求对象，模型升级或更换厂商时就需要修改大量代码。更稳定的做法是：业务层使用自己的 `PromptContract`、`ModelResult` 和 `ValidationError`，再由一层转换代码映射到具体厂商 API。

## 学习检查

完成本章后，应能：

- 沿“业务目标—模型输入—模型调用—输出验证—失败处理”复述完整链路；
- 写清一项任务的成功标准、输入边界、输出格式和失败处理；
- 区分应用规则、用户请求和外部资料；
- 根据具体错误决定是否需要 Few-shot；
- 区分自由文本、JSON Mode 和 Structured Outputs；
- 按固定顺序验证模型输出，并根据原因选择修复、重试、降级或人工处理；
- 记录 Prompt、Schema、示例、模型和参数版本，并用测试数据决定是否上线。

## 参考资料与结论对应关系

- [Prompt Engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)，OpenAI；用于核对指令角色、Prompt 组织、Few-shot 机制与示例多样性；最后核验日期：2026-07-22。
- [Text Generation](https://developers.openai.com/api/docs/guides/text)，OpenAI；用于核对 `developer`、`user` 与 `assistant` 消息的当前职责和优先级；最后核验日期：2026-07-22。
- [Structured Model Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)，OpenAI；用于核对 Structured Outputs 与 JSON Mode 的差异、Schema 子集和拒绝分支；最后核验日期：2026-07-22。
- [API Changelog](https://developers.openai.com/api/docs/changelog)，OpenAI；用于核对 Prompt、模型与 Responses API 持续变化，支持版本记录和发布前复核；最后核验日期：2026-07-22。
- [Prompt Engineering Overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)，Anthropic；用于核对成功标准和评测是 Prompt 优化的前置条件；最后核验日期：2026-07-22。
- [Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)，Anthropic；用于核对清晰指令、示例和结构化分隔的当前建议；最后核验日期：2026-07-22。
- [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)，Anthropic；用于核对 `output_config.format`、Schema 限制、拒绝和截断分支；最后核验日期：2026-07-22。
- [Mitigate Jailbreaks and Prompt Injections](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks)，Anthropic；用于核对结构化分隔必须与最小权限、隔离和测试组合使用；最后核验日期：2026-07-22。
- [JSON Schema 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation)，JSON Schema；用于核对类型、枚举、范围和必填等验证关键字；最后核验日期：2026-07-22。
