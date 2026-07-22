# 01｜LLM 与模型 API 基础：研究记录

## 1. 研究范围

本章只回答 Agent 开发所需的模型与 API 基础问题：

- LLM 在 Agent 系统中承担什么职责
- 主流模型 API 的共同契约和关键差异
- Token、上下文窗口、用量和成本如何关联
- 采样参数与推理参数分别控制什么
- Streaming、限流和瞬时错误如何处理
- 如何基于任务评测选择和路由模型

Prompt 设计、Structured Output、Tool Calling、Agent Loop、Context Engineering 和完整可靠性机制分别留给后续章节。

最后核验日期：2026-07-22。

## 2. 关键结论

### 2.1 模型不是 Agent

LLM 是根据当前输入生成输出的模型。Agent 是围绕模型增加指令、上下文、工具、循环、状态和权限控制后形成的系统。即使厂商 API 在一次请求内部执行多个工具，也不能把“模型”“模型 API”和完整 Agent 系统视为同义词。

### 2.2 不存在统一的消息 API

三家当前接口具有相似要素，但对象模型并不相同：

- OpenAI 推荐新项目使用 Responses API，以类型化 Item 表示消息、函数调用和函数结果，并可通过 `previous_response_id` 延续服务端状态。
- Anthropic Messages API 支持单轮和无状态多轮调用，`system` 是顶层参数，输入消息没有 `system` 角色。
- Gemini 当前推荐的 Interactions API 面向 Agent 工作流和服务端状态；`generateContent` 仍是另一套内容生成接口。

正文只提取共同契约，不设计一个假装所有厂商语义完全一致的万能结构。

### 2.3 上下文窗口不等于长期记忆

上下文窗口是一次推理可用的工作空间，通常包含输入、历史、工具定义、工具结果、输出预算以及部分模型的推理 Token。服务端保存会话或传入上一响应 ID 只改变状态传递方式，不自动消除上下文占用和计费。

### 2.4 参数必须按模型能力设置

传统生成模型常暴露 `temperature`、`top_p`、最大输出长度和停止条件。推理模型还可能暴露 `reasoning effort` 或相似参数。不同模型可能忽略、限制或移除传统采样参数，因此不能维护一份不检查模型能力的全局参数字典。

### 2.5 模型选择必须由任务评测驱动

选型顺序是先确定任务质量目标，再在满足目标的模型中优化延迟和成本。排行榜、厂商总榜和上下文窗口大小不能替代使用真实 Prompt、工具和数据的任务评测。

## 3. 来源差异与版本说明

| 问题 | OpenAI | Anthropic | Google Gemini | 写作处理 |
|---|---|---|---|---|
| 当前推荐接口 | Responses API | Messages API | Interactions API | 讲共同契约，分别标注接口名 |
| 输入对象 | 字符串或类型化 Items | `system` 加 `messages`/内容块 | `input` 或 `Content`/`Part` | 不强行统一字段名 |
| 多轮状态 | 可用 `previous_response_id` 或自行重放 | Messages API 可用于无状态多轮，调用方提交历史 | Interactions 面向服务端状态，Generate Content 可提交历史 | 区分传输便利与真实上下文成本 |
| 模型版本 | 模型别名和可固定快照并存 | 新版模型 ID 本身固定 | Stable、Preview、Latest、Experimental 并存 | 生产优先固定稳定版本，升级前回归评测 |
| 限流 | 请求、Token 等维度，429 可能表示速率或额度 | RPM、ITPM、OTPM，返回 `retry-after` | RPM、TPM、日配额及消费保护 | 读取错误类型和响应头，不对所有 429 盲目重试 |

## 4. 主要来源

| 标题 | 来源 | 用于核对的内容 | 最后核验日期 |
|---|---|---|---|
| [Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses) | OpenAI | Responses API、Items、状态和新项目推荐接口 | 2026-07-22 |
| [Conversation State](https://developers.openai.com/api/docs/guides/conversation-state) | OpenAI | `previous_response_id`、存储、计费和上下文窗口 | 2026-07-22 |
| [Streaming API Responses](https://developers.openai.com/api/docs/guides/streaming-responses) | OpenAI | SSE 事件流和流式响应 | 2026-07-22 |
| [Model Selection](https://developers.openai.com/api/docs/guides/model-selection) | OpenAI | 质量、延迟和成本的选型顺序 | 2026-07-22 |
| [Rate Limits](https://developers.openai.com/api/docs/guides/rate-limits) | OpenAI | 限流目的和处理原则 | 2026-07-22 |
| [Error Codes](https://developers.openai.com/api/docs/guides/error-codes) | OpenAI | 401、429、500、503 等错误语义 | 2026-07-22 |
| [Create a Message](https://platform.claude.com/docs/en/api/messages/create) | Anthropic | Messages API、内容块、无状态多轮和顶层 `system` | 2026-07-22 |
| [Token Counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) | Anthropic | 请求前 Token 估算及其误差边界 | 2026-07-22 |
| [Context Windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) | Anthropic | 上下文组成、输出和推理 Token、缓存占用 | 2026-07-22 |
| [Rate Limits](https://platform.claude.com/docs/en/api/rate-limits) | Anthropic | RPM、ITPM、OTPM、Token Bucket 和 `retry-after` | 2026-07-22 |
| [Model IDs and Versioning](https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions) | Anthropic | 固定模型 ID 的版本语义 | 2026-07-22 |
| [Gemini API Reference](https://ai.google.dev/api) | Google | Interactions、Generate Content、Streaming、Live 和 Batch 端点 | 2026-07-22 |
| [Gemini Models](https://ai.google.dev/gemini-api/docs/models) | Google | Stable、Preview、Latest、Experimental 命名语义 | 2026-07-22 |
| [Gemini Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits) | Google | RPM、TPM、日配额和消费限制 | 2026-07-22 |

## 5. 待正文发布前复核

- 三家推荐接口、模型 ID 和参数支持情况变化较快，发布到语雀前必须重新核验。
- 正文不固化价格数字；成本示例由调用方传入单价，避免短期过时。
- 示例使用 OpenAI Python SDK 和 `gpt-5.6-terra`，仅用于展示 API 契约，不能推导为行业统一接口。
- Gemini Interactions API 较新，正文只说明当前推荐方向，不展开其 Agent 工作流能力。
