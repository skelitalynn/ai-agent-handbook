# 02｜模型 API 与推理工程：研究记录

## 1. 研究范围

本章只回答 Agent 开发所需的模型 API 与推理工程问题：

- 模型 API 与模型内部推理的边界是什么
- 主流模型 API 的共同请求、响应与状态契约是什么
- Streaming 为什么必须作为类型化事件协议处理
- 状态引用、上下文窗口、Usage 和成本如何关联
- Streaming、限流和瞬时错误如何处理
- 如何基于任务评测选择和路由模型

Prompt 设计、Structured Output、Tool Calling、Agent Loop、Context Engineering 和跨步骤可靠性机制分别留给后续章节。

最后核验日期：2026-07-22。

## 2. 关键结论

### 2.1 模型 API 不是模型，也不是 Agent

LLM 是根据当前输入生成输出的模型；模型 API 是访问远程推理能力的协议接口；Agent 则是围绕模型增加上下文、工具、循环、状态和权限控制后形成的系统。即使厂商 API 在一次请求内部提供托管能力，也不能把三者视为同义词。

### 2.2 不存在语义完全统一的模型 API

不同厂商接口具有相似要素，但对象模型并不相同：

- OpenAI 推荐新项目使用 Responses API，以类型化 Item 表示消息、函数调用和函数结果，并可通过 `previous_response_id` 延续服务端状态。
- Anthropic Messages API 支持单轮和无状态多轮调用，`system` 是顶层参数，输入消息没有 `system` 角色。
正文只提取共同契约，不设计一个假装所有厂商语义完全一致的万能结构。

### 2.3 上下文窗口不等于长期记忆

上下文窗口是一次推理可用的工作空间，通常包含输入、历史、工具定义、工具结果、输出预算以及部分模型的推理 Token。服务端保存会话或传入上一响应 ID 只改变状态传递方式，不自动消除上下文占用和计费。

### 2.4 Streaming 是事件状态机

OpenAI Responses 与 Anthropic Messages 都通过 SSE 返回类型化事件。HTTP 200 后仍可能出现流内错误；连接在终态事件前断开时，已收到的部分文本不能默认作为完整结果。客户端应按事件类型组装，并对未知的非关键事件保持向前兼容。

### 2.5 参数必须按模型能力设置

传统生成模型常暴露 `temperature`、`top_p`、最大输出长度和停止条件。推理模型还可能暴露 `reasoning effort` 或相似参数。不同模型可能忽略、限制或移除传统采样参数，因此不能维护一份不检查模型能力的全局参数字典。

### 2.6 模型选择必须由任务评测驱动

选型顺序是先确定任务质量目标，再在满足目标的模型中优化延迟和成本。排行榜、厂商总榜和上下文窗口大小不能替代使用真实 Prompt、工具和数据的任务评测。

## 3. 来源差异与版本说明

| 问题 | OpenAI | Anthropic | 写作处理 |
|---|---|---|---|
| 当前基础接口 | Responses API | Messages API | 讲共同契约，分别标注接口名 |
| 输入对象 | 字符串或类型化 Items | `system` 加 `messages`/内容块 | 不强行统一字段名 |
| 多轮状态 | 可用 `previous_response_id`、Conversation 或自行重放 | Messages API 可用于无状态多轮，调用方提交历史 | 区分传输便利与真实上下文成本 |
| 流式输出 | Response 生命周期与内容增量事件 | Message 与内容块生命周期事件 | 统一为内部事件类型，但保留厂商扩展 |
| 限流与错误 | 读取错误类别和限流响应头 | SDK 可对瞬时错误退避并尊重 `retry-after` | 不对所有错误盲目重试 |

## 4. 主要来源

| 标题 | 来源 | 用于核对的内容 | 最后核验日期 |
|---|---|---|---|
| [Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses) | OpenAI | Responses API、Items、状态和新项目推荐接口 | 2026-07-22 |
| [Conversation State](https://developers.openai.com/api/docs/guides/conversation-state) | OpenAI | `previous_response_id`、存储、计费和上下文窗口 | 2026-07-22 |
| [Streaming API Responses](https://developers.openai.com/api/docs/guides/streaming-responses) | OpenAI | SSE 事件流和流式响应 | 2026-07-22 |
| [Model Selection](https://developers.openai.com/api/docs/guides/model-selection) | OpenAI | 质量、延迟和成本的选型顺序 | 2026-07-22 |
| [Rate Limits](https://developers.openai.com/api/docs/guides/rate-limits) | OpenAI | 限流目的和处理原则 | 2026-07-22 |
| [Error Codes](https://developers.openai.com/api/docs/guides/error-codes) | OpenAI | 401、429、500、503 等错误语义 | 2026-07-22 |
| [API Changelog](https://developers.openai.com/api/docs/changelog) | OpenAI | Responses API、模型别名和能力的近期演进 | 2026-07-22 |
| [Create a Message](https://platform.claude.com/docs/en/api/messages/create) | Anthropic | Messages API、内容块、无状态多轮和顶层 `system` | 2026-07-22 |
| [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming) | Anthropic | SSE 事件顺序、内容块增量、流内错误和未知事件 | 2026-07-22 |
| [Stop Reasons and Fallback](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) | Anthropic | 各类停止原因及调用方处理分支 | 2026-07-22 |
| [Claude API Errors](https://platform.claude.com/docs/en/api/errors) | Anthropic | HTTP 错误、流内错误、请求 ID、退避与 `retry-after` | 2026-07-22 |
| [Claude Platform Release Notes](https://platform.claude.com/docs/en/release-notes/overview) | Anthropic | 停止原因、Usage 细分项和 Messages API 能力的近期变化 | 2026-07-22 |

## 5. 待正文发布前复核

- 厂商推荐接口、模型 ID 和参数支持情况变化较快，发布到语雀前必须重新核验。
- 正文不固化价格数字；成本示例由调用方传入单价，避免短期过时。
- 示例采用 Python 标准库和模拟传输验证内部协议，不依赖 API Key，也不把某个厂商 SDK 当作行业统一接口。
- OpenAI 官方文档 MCP 在当前环境中因本机权限无法安装，本轮改用 OpenAI 官方域名页面核验；人工审核前可在 MCP 可用时再次交叉复核。

## 6. 初稿自检记录

- 事实：已交叉检查 OpenAI 与 Anthropic 的功能指南、API Reference 可访问部分、模型页面和 Release Notes；正文没有固化价格、上下文长度或限流额度。
- 链接：正文引用的官方页面在 2026-07-22 均可访问；OpenAI Responses API Reference 的动态页面无法由当前网页读取器直接抓取，相关对象语义改由官方迁移指南和功能指南交叉核对。
- Markdown：背诵提纲为 1～9 连续编号，高频问题为 1～5 连续编号，面试层后只有一条分隔线，正文路径与 `SUMMARY.md` 一致。
- 代码：`python -m unittest discover -s examples/02-model-api-inference -p "test_*.py" -v` 共 5 项通过；`py_compile` 与 `git diff --check` 通过。
- 审核状态：待人工审核初稿，未发布到语雀。
