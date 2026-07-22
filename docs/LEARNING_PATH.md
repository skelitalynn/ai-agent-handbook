# AI Agent 学习线路（持续更新中）

> 本文用于界定项目的知识范围并汇总资料入口，不代表正文编写顺序。正文严格按照根目录 `SUMMARY.md` 从第一章开始逐章完成。项目默认读者已有 AI Agent 基础，基础主题用于系统复习和概念校准，而非零基础教学。

# 编程语言

## 1\.Python\-最快上手

Python 的优势是：

- LLM SDK 和 Agent 框架支持完整

- 最容易上手

- 数据处理方便

- FastAPI、Pydantic 等生态成熟

- 教程和示例最多

推荐资料：

- [Python 官方教程](https://docs.python.org/3/tutorial/)

- [Python asyncio 概念介绍](https://docs.python.org/3/howto/a-conceptual-overview-of-asyncio.html)

- [FastAPI 官方教程](https://fastapi.tiangolo.com/tutorial/)

- [Docker Get Started](https://docs.docker.com/get-started/)

Agent 通常需要同时调用模型、数据库和多个外部工具，因此应当理解协程、任务、超时、取消和并发执行等异步编程概念。

## 2\.TypeScript\-全栈开发

已经熟悉前端、Node\.js 或 NestJS ，也可以选择 TypeScript。

推荐资料：

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)

- [OpenAI Agents SDK TypeScript](https://github.com/openai/openai-agents-js)

TypeScript 特别适合构建：

- Web Agent 产品

- 全栈应用

- 浏览器扩展

- 实时聊天界面

- Node\.js 工具服务

# 0\.前置知识



需要掌握的最小集：

- 必要数学

- Transformer

- 神经网络与梯度下降

- 预训练、后训练与推理的概念



如果有时间、想要扎实基础：

- CS224N：理解和使用深度学习模型处理语言，是 NLP → Transformer → LLM 应用路线。 

- CS336：从零训练一个语言模型，是 Transformer 实现 → GPU 优化 → 分布式训练 → 数据工程 → 对齐训练路线。

# 1\.Prompt 工程

需要掌握的最小集

- System Prompt

- 明确描述任务与边界

- 使用分隔符组织上下文

- Few\-shot Examples

- 输出格式约束

- Structured Outputs

- Tool Description

- Prompt Template

- Prompt Version

- Prompt Eval

推荐资料：

- [OpenAI Prompt Engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)

- [OpenAI Prompting](https://developers.openai.com/api/docs/guides/prompting)

- [Anthropic Prompt Engineering](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)

- [Anthropic Prompting Best Practices](https://docs.anthropic.com/claude/prompt-library)

# 2\.Agent 核心：Tool Calling 与 Agent Loop

## Agent 的核心循环

这是整个路线最重要的一步，其实Agent 的核心只有一个循环：

```Plain Text
User
  ↓
LLM
  ↓
是否需要调用 Tool？
  ├── 否 → Final Answer
  └── 是
        ↓
   Validate Arguments
        ↓
   Execute Tool
        ↓
   Append Tool Result
        ↓
       LLM
```

一定要亲手写，如果这一层理解了，理解这一层以后，大部分 Agent Framework 都只是对模型调用、工具分发、状态管理和循环控制的进一步封装。

## 最小代码结构

```Python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": user_input},
]

for step in range(MAX_STEPS):
    response = call_model(
        messages=messages,
        tools=tool_schemas,
    )

    messages.append(response.message)

    if not response.tool_calls:
        return response.final_text

    for call in response.tool_calls:
        handler = tool_handlers.get(call.name)

        if handler is None:
            result = {"error": "unknown_tool"}
        else:
            try:
                args = validate_arguments(call.name, call.arguments)
                result = handler(**args)
            except Exception as error:
                result = {"error": str(error)}

        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": serialize(result),
        })

raise MaxStepsExceeded()
```

## 推荐学习资料

### Learn Claude Code（优先阅读，其他随意）

[Learn Claude Code](https://github.com/shareAI-lab/learn-claude-code)

这是一个从极简 Bash Agent 开始，逐步加入工具、状态、子 Agent、Skills 和上下文管理的教学项目，适合理解 Agent Harness 的核心结构。

### Hello Agents

[Datawhale：Hello Agents](https://datawhalechina.github.io/hello-agents/)

这是一套系统性的中文 Agent 教程，适合不习惯直接阅读英文官方文档的初学者。

### Hugging Face Agents Course

[Hugging Face AI Agents Course](https://huggingface.co/learn/agents-course/unit0/introduction)

课程覆盖 Agent、Messages、Tools、Think\-Act\-Observe 循环、框架实践和最终评测项目。

### OpenAI Agents SDK

- [OpenAI Agents SDK 文档](https://developers.openai.com/api/docs/guides/agents)

- [Python SDK](https://github.com/openai/openai-agents-python)

- [TypeScript SDK](https://github.com/openai/openai-agents-js)

### Claude Agent SDK

- [Claude Agent SDK](https://docs.anthropic.com/en/docs/claude-code/sdk)

- [Python SDK](https://github.com/anthropics/claude-agent-sdk-python)

Claude Agent SDK 提供与 Claude Code 相似的 Agent Loop、文件读取、命令执行、代码搜索、Hooks、Subagents、MCP、权限和 Session 能力。

# 3\.Agent Framework

随着 Agent 工程的发展，LangChain 等早期框架经常被批评抽象过多、调试困难。但这不意味着框架没有价值，毕竟来时路，但是学习重点不用放在这上面。

## LangChain

仓库：[LangChain](https://github.com/langchain-ai/langchain)

适合学习：

- Model Adapter

- Prompt Template

- Tool

- Retriever

- Middleware

- Provider Integration

它更适合快速组合 LLM 应用组件。

## LangGraph

仓库：[LangGraph](https://github.com/langchain-ai/langgraph)

推荐资料：

- [LangGraph 官方文档](https://docs.langchain.com/oss/python/langgraph/overview)

- [LangGraph Academy](https://academy.langchain.com/courses/intro-to-langgraph)

适合学习：

- State

- Node

- Edge

- Conditional Routing

- Checkpoint

- Human\-in\-the\-loop

- Durable Execution

- 长时间运行任务

LangGraph 是独立于 LangChain 高层 API 的低层编排框架，更强调对 Agent 工作流的状态和控制。

## LlamaIndex

推荐资料：

- [LlamaIndex 官方文档](https://developers.llamaindex.ai/python/framework/)

- [LlamaIndex RAG Introduction](https://developers.llamaindex.ai/python/framework/understanding/rag/)

- [LlamaIndex Starter Tutorial](https://developers.llamaindex.ai/python/framework/getting_started/starter_example/)

LlamaIndex 更适合学习围绕数据、索引、检索、RAG 和工作流构建 Agent。

## 框架选择建议

初学阶段不需要同时深入学习所有框架。

选择一种组合即可：

```Plain Text
原生 SDK
+
LangGraph
```

或者：

```Plain Text
OpenAI / Claude Agents SDK
+
自己编写业务层
```

如果项目主要围绕文档与数据检索，则可以选择：

```Plain Text
LlamaIndex
+
FastAPI
```

# 4\.RAG\-项目实战参考：做一个自己的RAG

RAG？Grep？

## RAG：适合自然语言知识库

典型流程：

```Plain Text
文档
  ↓
切分 Chunk
  ↓
Embedding
  ↓
向量数据库
  ↓
相似度检索
  ↓
Rerank
  ↓
将结果放入上下文
  ↓
LLM 回答
```

### RAG From Scratch

推荐LangChain官方视频RAG From Scratch，对检索优化有比较深入的阐述，同时提供配套代码和代码仓。

视频：[www\.youtube\.com](https://www.youtube.com/playlist?list=PLfaIDFEXuae2LXbO1_PKyVJiQ23ZztA0x)

代码仓：[github\.com](https://github.com/langchain-ai/rag-from-scratch)

### LlamaIndex

一个比较适合rag的框架LlamaIndex

视频：[www\.bilibili\.com](https://www.bilibili.com/video/BV1p4GVzxEpz/?spm_id_from=333.1387.upload.video_card.click&vd_source=81bfbf91cfd2d9c7f25ac8785b6c8670)

文档：[LlamaIndex \| AI Agents for Document OCR \+ Workflows](https://www.llamaindex.ai/)

## Grep：代码检索

Claude Code 的代码检索方式。

一个典型流程是：

```Plain Text
用户提出代码问题
        ↓
Agent 分析需要寻找什么
        ↓
Glob：找到可能相关的文件
        ↓
Grep：搜索函数名、类名、字符串
        ↓
Read：读取目标文件的相关内容
        ↓
继续 Grep：搜索调用方或依赖
        ↓
运行测试、Git 或 Bash 命令
        ↓
形成答案或修改代码
```

Anthropic 官方文档明确将 `Glob`、`Grep` 和 `Read` 描述为代码库探索工具；其中 `Grep` 用于搜索文件内容，底层通常采用类似 ripgrep 的高速文本检索能力，`Glob` 用于按照路径模式寻找文件。

需要注意，不同 Claude Code 版本和安装方式中，`Grep`、`Glob` 可能作为独立工具暴露，也可能通过内置搜索能力或 Bash 执行；但总体检索思想仍然是基于文件系统的主动探索，而不是固定的一次向量召回。

# 4\.Coding Agent\-项目实战参考：做一个自己的Coding Agent

## Pi

[GitHub \- earendil\-works/pi: AI agent toolkit: unified LLM API, agent loop, TUI, coding agent CLI](https://github.com/earendil-works/pi)

Pi 是一个极简、可扩展的终端 Coding Agent Harness，可以用来观察统一模型接口、Agent Runtime、工具调用、Session 和扩展系统如何组合

放弃cc拥抱Pi？实战指南：pi\+截图的插件（pi reasonix），你就得到了免费的DeepSeekV4

## Claude Code 与 Claude Agent SDK

- [Claude Code Overview](https://docs.anthropic.com/en/docs/claude-code/overview)

- [Claude Code Best Practices](https://www.anthropic.com/engineering/claude-code-best-practices)

- [Claude Agent SDK](https://docs.anthropic.com/en/docs/claude-code/sdk)

## Codex

[GitHub \- openai/codex: Lightweight coding agent that runs in your terminalght coding agent that runs in your terminal](https://github.com/openai/codex)

# 5\.Memory

## 短期记忆

通常包括：

- Conversation History

- 当前任务计划

- 中间工具结果

- 当前文件

- 临时变量

- Running Summary

短期记忆主要解决上下文窗口内的连续任务。

## 长期记忆

### Profile Memory

用户的稳定资料和偏好。

### Semantic Memory

从历史对话中提取的事实和知识。

### Episodic Memory

过去发生过的具体事件和任务经历。

### Procedural Memory

Agent 完成某类任务的方法、规范和经验。

## Memory 工程真正需要解决的问题

- 什么信息值得保存

- 什么时候保存

- 如何更新旧记忆

- 如何处理冲突

- 如何删除过期记忆

- 如何隔离不同用户

- 如何防止错误信息长期污染

- 如何召回相关记忆

- 如何评测记忆是否真的有帮助

## 推荐资料

- [LangGraph Memory Concepts](https://docs.langchain.com/oss/python/concepts/memory)

- [LangMem](https://langchain-ai.github.io/langmem/)

- [LangMem Long\-term Memory Guide](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)

- [Mem0 Documentation](https://docs.mem0.ai/introduction)

- [Mem0 Memory Types](https://docs.mem0.ai/core-concepts/memory-types)

LangMem 提供记忆提取、更新、搜索和 Prompt 优化能力；Mem0 则将 Conversation、Session、User 和 Organization 等不同层级的记忆进行区分。

# 6\.MCP

MCP，即 Model Context Protocol，是连接 AI 应用和外部系统的开放协议。

```Plain Text
Host
  ↓
MCP Client
  ↓
MCP Server
```

Model Context Protocol：[https://modelcontextprotocol\.io/](https://modelcontextprotocol.io/)



# 7\.Skills 

1\.Skills的基本认知：https://www\.bilibili\.com/video/BV1qv6eBZErD/?spm\_id\_from=333\.337\.search\-card\.all\.click\&vd\_source=58b60e4508f7a035b82921e19d021e3b

2\.好用的skills推荐：https://github\.com/mattpocock/skills（暂时找不到介绍视频，记得补充）

# 8\.Harness 

harness的基本认知：https://walkinglabs\.github\.io/learn\-harness\-engineering/zh/

其他学习资料：

- [Learn Harness Engineering](https://walkinglabs.github.io/learn-harness-engineering/zh/)

- [Learn Claude Code](https://github.com/shareAI-lab/learn-claude-code)

- [Anthropic：Effective Harnesses for Long\-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

- [OpenAI：Harness Engineering](https://openai.com/index/harness-engineering/)

- [Hugging Face Context Course：Nano Harness](https://huggingface.co/learn/context-course/en/unit0/introduction)



# 9\.Evals、Tracing 与 Observability

## 为什么需要 Evals？

传统函数通常相对确定，而 Agent 会受到以下因素影响：

- 模型版本

- Prompt

- Tool Description

- 检索结果

- 上下文顺序

- 采样

- 工具异常

- 环境状态

因此，修改一段 Prompt 或新增一个工具，都可能导致其他任务退化。OpenAI 的评测指南建议采用 Eval\-driven Development：尽早建立任务测试集，持续自动评测并记录所有执行数据。

## Agent 评测指标

### 任务层

- Task Success Rate

- 最终答案正确率

- 任务完成步数

- 死循环率

- 提前终止率

### Tool 层

- Tool Selection Accuracy

- 参数正确率

- 不必要工具调用率

- Tool Error Recovery Rate

- 越权工具调用率

### 检索层

- Recall@K

- Precision@K

- Hit Rate@K

- Citation Correctness

- Faithfulness

### 工程层

- 总延迟

- 首 Token 延迟

- Token 消耗

- API 成本

- Retry 次数

- 并发成功率

## Trace

每次 Agent Run 至少记录：

```Plain Text
run_id
user_id
session_id
model
prompt_version
tool_calls
tool_arguments
tool_results
latency
token_usage
errors
final_status
```

Trace 不只是聊天记录，而是完整的执行轨迹。

OpenAI 的 Trace Grading 可以对模型调用、工具调用、决策步骤和完整 Agent Trace 进行结构化评分。

## 推荐资料

- [OpenAI Agent Evals](https://developers.openai.com/api/docs/guides/agent-evals)

- [OpenAI Evaluation Best Practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)

- [OpenAI Trace Grading](https://developers.openai.com/api/docs/guides/trace-grading)

- [Anthropic：Demystifying Evals for AI Agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

- [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation)

- [LangSmith Observability](https://docs.langchain.com/langsmith/observability)

LangSmith 可以记录完整 Trace，并支持离线数据集评测与线上质量监控。

## 阶段项目：建立 Agent 测试集

为前面的校园 Agent 或 Coding Agent 建立至少 50 条测试：

```Plain Text
20 条正常请求
10 条模糊请求
10 条工具异常
5 条越权请求
5 条 Prompt Injection
```

每次修改 Prompt、工具和工作流后，自动重新运行并生成报告。

---

# 10\.安全与 Guardrails

## 输入安全

- Prompt Injection

- 恶意网页

- 恶意文档

- 超长输入

- 文件类型检查

- URL 检查

## 工具安全

- Tool Allowlist

- 参数 Schema

- 最小权限

- 读写权限分离

- 高风险操作确认

- Timeout

- Rate Limit

- 幂等性

- 审计日志

## 执行安全

- Sandbox

- 网络隔离

- 文件系统边界

- Secret 隔离

- 命令过滤

- 资源限制

- 最大执行步数

- Cancellation

## 输出安全

- 敏感信息检测

- 引用检查

- 内容过滤

- 确定性 Fallback

- 人工审核

典型攻击链：

```Plain Text
Agent 读取不可信网页或 README
        ↓
内容中包含 Prompt Injection
        ↓
模型受到恶意指令影响
        ↓
调用高权限 Tool
        ↓
泄露数据或执行危险操作
```

连接器、MCP Server、插件和网页都会把外部内容带入 Agent 上下文，因此即使连接器本身可信，读取的数据也不一定可信。权限最小化和工具隔离可以降低攻击影响范围。

推荐资料：

- [OpenAI：Safety in Building Agents](https://developers.openai.com/api/docs/guides/agent-builder-safety)

- [Claude Code Security](https://docs.anthropic.com/en/docs/claude-code/security)

- [Anthropic：How We Contain Claude](https://www.anthropic.com/engineering/how-we-contain-claude)

# 11\.Multi\-Agent

不要太早学习 Multi\-Agent。大部分学生项目并不需要多个 Agent。很多所谓 Multi\-Agent，只是把同一个模型换了几个角色名，多调用了几次 API。

## 什么时候才需要 Multi\-Agent？

### 上下文隔离

不同子任务需要读取大量不同资料，不希望污染主 Agent 上下文。

### 并行探索

多个 Agent 可以同时搜索不同方向。

### 工具和权限不同

不同 Agent 拥有不同 Tool、模型或权限。

### 生命周期不同

子任务需要后台执行、单独暂停、恢复和追踪。

### 专业边界明确

不同 Agent 需要不同的 Prompt、知识库和评测标准。

## 常见模式

### Manager

```Plain Text
Manager Agent
    ├── Research Agent
    ├── Coding Agent
    └── Review Agent
```

### Handoff

```Plain Text
Triage Agent
    ↓
Specialist Agent
    ↓
Human Agent
```

### Orchestrator\-Workers

```Plain Text
Orchestrator
    ├── Worker A
    ├── Worker B
    └── Worker C
```

### Evaluator\-Optimizer

```Plain Text
Generator
    ↓
Evaluator
    ↓
不通过则重新生成
```

## 推荐博客

### Anthropic：How We Built Our Multi\-Agent Research System

[How We Built Our Multi\-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)

适合学习：

- 主 Agent 与子 Agent

- 并行搜索

- 任务分解

- 上下文隔离

- 结果汇总

- Token 成本

Anthropic 的研究系统使用主 Agent 规划任务，并由多个子 Agent 并行探索；其分析也说明 Multi\-Agent 的提升通常伴随显著增加的 Token 和工具调用成本。

### OpenAI Agent Manager 与 Handoff

[OpenAI Agent Guide](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)

### 开源实现

- [OpenAI Agents SDK Examples](https://github.com/openai/openai-agents-python/tree/main/examples)

- [LangChain Multi\-Agent 文档](https://docs.langchain.com/oss/python/langchain/multi-agent)

- [Claude Code Subagents](https://docs.anthropic.com/en/docs/claude-code/sub-agents)



# 12\.生产工程化

Agent 项目最终需要回归普通软件工程。

## 日志与 Trace

- 结构化日志

- Request ID

- Run ID

- Session ID

- Tool Trace

- Error Stack

- Token Usage

- Cost

## 错误处理

- Retry

- Exponential Backoff

- Circuit Breaker

- Timeout

- Cancellation

- Fallback Model

- Fallback Tool

- Dead Letter Queue

## Token 与上下文控制

- Context Budget

- 历史消息截断

- Summary

- Compaction

- 按需读取

- Tool 延迟加载

- 检索结果去重

- 大结果先用代码过滤

## Cache

- Prompt Cache

- Tool Result Cache

- Retrieval Cache

- HTTP Cache

- Semantic Cache

注意不要缓存带有强时效性或用户权限差异的数据。

## 权限

- RBAC

- Tool Permission

- 用户数据隔离

- Workspace 隔离

- Secret 管理

- Human Approval

- Audit Log

## 成本优化

- 大小模型路由

- 并行调用控制

- 减少无效 Tool Call

- Prompt Cache

- 缩短 Tool Result

- Context Compaction

- 设置最大步数

- 成本预算

- 失败提前终止

## 部署

建议至少接触：

- FastAPI 或 NestJS

- PostgreSQL

- Redis

- 消息队列

- Docker

- 对象存储

- CI/CD

- Monitoring

- Sandbox

---

# 13\.微调：LoRA 与 QLoRA（选修）

## 不要一开始就微调

优先尝试：

```Plain Text
Prompt
→ Structured Output
→ Tool
→ RAG
→ Memory
→ Skill
→ Workflow
→ Evals
→ 最后才考虑 Fine-tuning
```

动态知识更新不应该主要依赖微调，应该使用 RAG、数据库或工具。本地小模型微调后的性能，未必比得上原生大模型\+约束。

## 适合微调的场景

- 稳定的输出风格

- 特定格式

- 领域表达习惯

- 固定分类任务

- 小模型工具选择

- 专有任务行为

- 降低长 Prompt 依赖

## 需要掌握

- Dataset

- Chat Template

- SFT

- Train / Validation Split

- LoRA

- QLoRA

- PEFT

- Learning Rate

- Overfitting

- 模型评测

- Catastrophic Forgetting

LoRA 通过冻结基础模型并训练低秩适配参数，减少需要训练的参数量；QLoRA 则在量化基础模型上训练 LoRA Adapter，以进一步降低显存需求。

推荐资料：

- [Hugging Face Fine\-tuning Course](https://huggingface.co/learn/smol-course/unit1/1)

- [LoRA and PEFT](https://huggingface.co/learn/smol-course/unit1/3a)

- [PEFT Documentation](https://huggingface.co/docs/peft/index)

- [TRL SFT Trainer](https://huggingface.co/docs/trl/sft_trainer)

- [QLoRA Paper](https://arxiv.org/abs/2305.14314)

# 后续：兴趣学习

## 好玩的框架

OpenClaw：https://github\.com/openclaw/openclaw

Hermes：https://github\.com/NousResearch/hermes\-agent

## LLM Wiki

推荐将学习的知识沉淀成文档，整理成自己的LLM Wiki知识库：

思路参考：https://gist\.github\.com/karpathy/442a6bf555914893e9891c11519de94f\#llm\-wiki

## 低代码平台

- Dify

- Coze

不过我觉得既然你都会写代码了，那为啥还用低代码平台？

## 趣味阅读：

### 软件工程

- 《Clean Code》

- 《Designing Data\-Intensive Applications》

- 《Release It\!》

- 《Site Reliability Engineering》

- 《The Pragmatic Programmer》

### AI 工程

- 《AI Engineering》

- 《Designing Machine Learning Systems》

- 《Build a Large Language Model From Scratch》

- ReAct 论文：[ReAct](https://arxiv.org/abs/2210.03629)

- Toolformer 论文：[Toolformer](https://arxiv.org/abs/2302.04761)

- Reflexion 论文：[Reflexion](https://arxiv.org/abs/2303.11366)

- RAG 原始论文：[Retrieval\-Augmented Generation](https://arxiv.org/abs/2005.11401)



## AI资讯获取

1\.企业官方博客: OpenAI、Anthropic、Cursor

2\.研究者个人: 苏神、Lilian Weng、Zhang Junlin、Eugene Yan（推特）

3\.行业访谈资讯平台: Latent Space、Hacker News

4\.开源评测机构专栏: TML、LangChain、LMSys
