# 03｜Prompt 与输出控制：研究记录

## 1. 研究范围

本章建立从任务定义到可消费输出的完整控制链：

- Prompt 的角色、指令、上下文、数据和示例如何组织
- Zero-shot 与 Few-shot 应如何选择，示例为什么会同时提供能力和偏置
- 自由文本、JSON Mode 与 Structured Outputs 的实质差异
- JSON Schema 约束、运行时业务校验和失败恢复如何分层
- Prompt、模型参数、Schema 和示例如何版本化并通过评测演进
- 为什么指令层级与分隔符不能替代授权、隔离和安全控制

模型 API 的传输、Streaming、Usage 和网络重试已在第 02 章说明；工具参数 Schema 留到第 05 章；完整 Prompt Injection 防御留到第 24 章。

最后核验日期：2026-07-22。

## 2. 关键结论

### 2.1 Prompt 是运行时输入契约

Prompt 不只是自然语言问题，而是把任务目标、输入数据、约束、示例和成功条件序列化进模型上下文的运行时契约。高质量 Prompt 的起点不是措辞技巧，而是可判定的成功标准和代表性测试集。

### 2.2 指令与数据应显式分离

应用级规则、用户请求和外部数据承担不同职责，应通过消息角色和结构化边界区分。OpenAI 当前文档把 `developer` 指令置于 `user` 之前；Anthropic Messages API 使用顶层 `system` 和用户消息。共同原则是不要把不可信变量直接拼入高优先级指令。

### 2.3 Few-shot 是上下文内示范，不是免费增益

Few-shot 用少量输入输出示例让模型在上下文中模仿任务模式，不更新参数。示例必须覆盖有代表性的差异并与规则一致；错误、单一或相互矛盾的示例会引入偏置、占用上下文并增加维护成本。

### 2.4 输出控制至少有两层

Structured Outputs 可约束 JSON 结构，普通 JSON Mode 只保证可解析 JSON；二者都不能证明字段值在业务上正确。应用必须继续验证枚举、范围、跨字段约束、外部事实、权限与状态。

### 2.5 Schema 支持是厂商和模型相关的

OpenAI 与 Anthropic 都声明 Structured Outputs 只支持 JSON Schema 的一个子集或带有限制，并且字段、模型兼容范围和迁移方式会变化。正文使用厂商无关 Schema 示例，不把某个 SDK 参数形状写成行业标准。

### 2.6 Prompt 优化必须由评测驱动

Prompt 版本应与模型版本、生成参数、Schema 版本和示例集共同记录。每次修改都需要在固定测试集上比较任务质量、格式成功率、拒绝率、延迟和 Token，而不是根据少数人工对话凭感觉判断。

## 3. 来源差异与版本说明

| 问题 | OpenAI | Anthropic | 写作处理 |
|---|---|---|---|
| 高优先级应用指令 | `developer` 消息；部分接口仍可见 `system` 形态 | Messages API 顶层 `system` | 先讲应用规则与用户数据的职责，再标厂商字段 |
| 结构化响应 | Responses 使用 `text.format` 等当前接口形态 | 当前使用 `output_config.format`，旧 `output_format` 处于迁移期 | 正文不固化万能参数封装 |
| Schema 范围 | 支持 JSON Schema 子集 | 支持 JSON Schema，但有关键字和复杂度限制 | 生产前按目标模型验证 Schema |
| 异常输出 | 拒绝等内容需单独分支处理 | 拒绝或 `max_tokens` 时可能不符合正常 Schema | 先检查终态，再解析和校验 |
| 推理提示 | 官方对推理模型建议简洁直接，不机械要求逐步思考 | 最佳实践随模型能力演进 | 不把“think step by step”当作通用口诀 |

## 4. 主要来源

| 标题 | 来源 | 用于核对的内容 | 最后核验日期 |
|---|---|---|---|
| [Prompt Engineering](https://developers.openai.com/api/docs/guides/prompt-engineering) | OpenAI | 指令角色、Prompt 组织、Few-shot 与示例要求 | 2026-07-22 |
| [Text Generation](https://developers.openai.com/api/docs/guides/text) | OpenAI | `developer`、`user`、`assistant` 的职责和优先级 | 2026-07-22 |
| [Structured Model Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | OpenAI | Structured Outputs、JSON Mode、Schema 子集、拒绝处理 | 2026-07-22 |
| [Reasoning Best Practices](https://developers.openai.com/api/docs/guides/reasoning-best-practices) | OpenAI | 推理模型的直接提示、分隔符、Zero-shot/Few-shot 与逐步思考边界 | 2026-07-22 |
| [API Changelog](https://developers.openai.com/api/docs/changelog) | OpenAI | Prompt 与 Responses 相关接口持续变化，需要版本化与复核 | 2026-07-22 |
| [Prompt Engineering Overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview) | Anthropic | 先定义成功标准和评测，再进行 Prompt 优化 | 2026-07-22 |
| [Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices) | Anthropic | 清晰指令、示例和 XML/结构化分隔的当前建议 | 2026-07-22 |
| [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) | Anthropic | `output_config.format`、Schema 限制、拒绝与截断分支 | 2026-07-22 |
| [Mitigate Jailbreaks and Prompt Injections](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks) | Anthropic | 指令与不可信内容分离、JSON 编码和最小权限的安全边界 | 2026-07-22 |
| [JSON Schema 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core) | JSON Schema | JSON Schema 的数据模型、Schema 与 Instance、断言与注解 | 2026-07-22 |
| [JSON Schema 2020-12 Validation](https://json-schema.org/draft/2020-12/json-schema-validation) | JSON Schema | 类型、范围、枚举、必填等结构验证关键字的标准语义 | 2026-07-22 |

## 5. 待正文发布前复核

- OpenAI Docs MCP 在当前环境中仍因本机权限不可用，OpenAI 结论使用官方开发者网页、模型文档和 Changelog 交叉核对。
- Structured Outputs 的模型支持、Schema 子集和 Anthropic `output_format` 迁移状态变化较快，发布前必须重查。
- 正文不宣称 Schema 保证业务正确，也不把分隔符描述为 Prompt Injection 的完整防线。
- 示例只使用 Python 标准库验证应用侧契约，不连接厂商 API。

## 6. 初稿自检记录

- 事实：已检查 OpenAI 与 Anthropic 的 Prompt 指南、Structured Outputs 文档、当前接口迁移说明和 Release Notes，并用 JSON Schema 2020-12 规范核对 Schema 与 Instance 的标准边界。
- 边界：正文没有把 Prompt 技巧描述为模型能力升级，没有把 Schema 合规描述为事实或业务正确，也没有把标签和 JSON 编码描述为完整安全防线。
- Markdown：背诵提纲为 1～9 连续编号，高频问题为 1～5 连续编号，面试层后只有一条分隔线，路径与 `SUMMARY.md` 一致。
- 代码：`python -m unittest discover -s examples/03-prompt-output-control -p "test_*.py" -v` 共 6 项通过；示例仅使用标准库，并验证额外字段、类型陷阱、跨字段规则和 Prompt 指纹。
- 审核状态：待人工审核初稿，未发布到语雀。
