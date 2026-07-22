# 01｜LLM 的训练与推理基础：研究记录

## 1. 研究范围

本章为 Agent 工程建立必要的模型前置知识，覆盖：

- Tokenization、Embedding 和自回归语言模型目标
- Decoder-only Transformer、Causal Self-Attention、Prefill、Decode 和 KV Cache
- 预训练、监督微调、RLHF、DPO 和后训练风险
- In-context Learning、Few-shot、Chain-of-Thought、Self-Consistency 和测试时推理投入
- 参数知识、上下文、检索、工具、确定性代码和幻觉诊断

本章不展开大规模分布式训练实现，不把 Prompt 技巧、ReAct、RAG Pipeline 和模型 API 细节提前写成正文。

最后核验日期：2026-07-22。

## 2. 关键写作决策

### 2.1 不把 Transformer 作为装饰性前置词

正文必须能够从 Token 表示、Scaled Dot-Product Attention 和 Causal Mask 推导自回归生成，再连接到 Prefill、Decode、KV Cache、上下文与延迟。只有实际使用这些机制时才引用 Transformer 论文。

### 2.2 区分训练阶段与推理阶段

预训练、SFT、偏好优化会更新参数；In-context Learning、Few-shot 和普通模型调用通常只改变当前条件输入。后训练改变模型倾向，不提供事实正确性证明。

### 2.3 CoT 属于推理方法，不等于 ReAct

本章解释 CoT 如何通过中间 Token 增加测试时计算，以及其不忠实和错误传播边界。ReAct 必须包含外部行动和观察，留到 Agent Loop 章节。

### 2.4 幻觉拆成系统可观测错误

正文不把知识缺失、检索失败、工具未调用、工具误读、推理错误、伪造引用和格式臆造全部归为不可操作的“模型幻觉”。每类错误对应不同修复位置。

## 3. 来源与正文映射

| 来源 | 正文使用内容 | 最后核验日期 |
|---|---|---|
| [Attention Is All You Need](https://arxiv.org/abs/1706.03762) | Scaled Dot-Product Attention、Multi-Head、位置表示、残差、归一化和自回归 Mask | 2026-07-22 |
| [SentencePiece](https://arxiv.org/abs/1808.06226) | 从原始文本训练语言无关子词模型的目标 | 2026-07-22 |
| [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165) | 自回归语言模型、Zero/One/Few-shot 和无梯度更新的上下文任务条件化 | 2026-07-22 |
| [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155) | SFT、偏好排序、奖励模型、PPO 式 RLHF，以及规模不自动保证指令遵循 | 2026-07-22 |
| [Direct Preference Optimization](https://arxiv.org/abs/2305.18290) | 直接从偏好对优化策略、避免显式奖励模型和在线 RL | 2026-07-22 |
| [Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903) | Few-shot CoT 的定义和原始任务结果 | 2026-07-22 |
| [Self-Consistency Improves Chain of Thought Reasoning](https://arxiv.org/abs/2203.11171) | 多路径采样与答案聚合 | 2026-07-22 |
| [ReAct](https://arxiv.org/abs/2210.03629) | 只用于界定推理与外部行动、观察交错的边界 | 2026-07-22 |
| [PagedAttention](https://arxiv.org/abs/2309.06180) | KV Cache 的动态增长、碎片与 Serving 并发问题 | 2026-07-22 |
| [Retrieval-Augmented Generation](https://arxiv.org/abs/2005.11401) | 参数化模型与非参数检索结合的动机，不用于保证 RAG 正确性 | 2026-07-22 |

## 4. 发布前复核

- 检查所有公式符号和 NumPy 示例维度。
- 不把特定厂商未公开的后训练配方写成事实。
- Reasoning Model 的参数和产品行为放到模型 API 章节按版本核验。
- 检查 CoT 说明是否明确区分“可读中间步骤”“内部计算”和“可验证证据”。
- 检查 KV Cache 与 Prompt Cache 是否始终保持不同层级的定义。
