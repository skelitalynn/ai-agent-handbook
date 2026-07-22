# 01｜LLM 的训练与推理

> 本章沿一条完整计算链解释大语言模型：文本如何被切成 Token，Token 如何变成向量，Decoder-only Transformer 如何计算下一个 Token 的分布，训练如何修改参数，推理又如何在参数不变的情况下逐 Token 生成。Token、Embedding 和 Transformer 不拆成孤立章节，因为它们共同解释同一个因果过程。

## 面试速记

### 背诵提纲

**定义**

大语言模型通常是以 Decoder-only Transformer 为骨干的自回归模型。它根据已有 Token 计算下一个 Token 的条件概率，通过不断把新 Token 追加到前缀中完成文本生成。

**完整计算链**

```text
训练：文本 → Token ID → Embedding → Transformer → logits
           → next-token loss → 反向传播 → 更新参数

推理：输入文本 → Token ID → Prefill → next-token logits
           → 选择 Token → Decode → 重复生成直到停止
```

**Tokenization**

Tokenizer 把文本切分为词表中的 Token 并映射成整数 ID。Token 不一定等于字符或单词；不同模型使用的词表不同，同一段文本的 Token 数、上下文占用和费用也可能不同。

**Embedding 与位置信息**

Token Embedding 是可学习的查表矩阵，用于把离散 Token ID 转换为连续向量；经过多层 Transformer 后得到的是随上下文变化的隐藏表示。位置信息用于区分 Token 的先后顺序，常见实现包括原始位置编码和 RoPE。

**Decoder-only Transformer**

Decoder-only Transformer 由多层带因果约束的 Transformer Block 堆叠而成。每个 Block 通常包含归一化、Self-Attention、残差连接和 MLP，最终由 LM Head 将隐藏向量投影为整个词表的 logits。

**Self-Attention**

Self-Attention 将输入投影为 Query、Key 和 Value。Query 与 Key 的匹配分数决定当前位置从哪些位置读取信息，Value 提供被加权聚合的内容；Multi-Head Attention 会在多个表示子空间中并行执行这一过程。

**Causal Mask**

Causal Mask 保证第 $t$ 个位置只能关注自己和左侧 Token，不能读取未来答案。它使训练时每个位置的可见信息与推理时“只根据已有前缀预测下一个 Token”的条件保持一致。

**训练目标**

自回归训练把序列错开一位构造输入和标签，并以真实下一个 Token 的交叉熵作为损失。训练阶段执行前向计算、反向传播和优化器更新，会改变 Embedding、Attention、MLP 和输出层等模型参数。

**训练阶段**

Pretraining 从大规模数据中学习通用语言和模式能力；Supervised Fine-Tuning 使用指令—回答示例训练指令遵循；Preference Optimization 根据人类或模型偏好调整输出倾向；Reasoning-focused Training 则进一步训练模型分配中间推理和测试时计算。不同阶段目标不同，不能把它们统称为一次微调。

**Prefill**

Prefill 一次处理全部输入 Token，各输入位置可以并行计算，并产生首个 next-token logits 和初始 KV Cache。它主要受输入长度影响，是首 Token 延迟的重要组成部分。

**Decode**

Decode 每一步生成一个新 Token。后一个 Token 依赖前一步刚生成的结果，因此单条序列在时间维度上必须串行执行，输出越长，Decode 步数和总生成时间通常越多。

**KV Cache**

KV Cache 保存历史 Token 在各层 Attention 中的 Key 和 Value，使后续 Decode 不必重新计算整个前缀。它以显存换取速度，大小会随层数、缓存 Token 数、KV Head 数、Head Dimension 和并发序列数增长；新 Query 仍需读取并关注历史缓存。

**logits 与采样**

logits 是 LM Head 为词表候选 Token 产生的未归一化分数，Softmax 将其转换为概率。Greedy、Temperature、Top-k 和 Top-p 决定如何选择 Token，只改变生成分布，不会补充模型缺少的知识，也不会自动验证答案。

**In-context Learning**

Zero-shot、One-shot 和 Few-shot 都通过改变当前输入 Context 来影响模型行为，不执行反向传播，也不更新参数。模型在一个会话中使用了示例，不代表它已经永久学会该任务。

**Chain-of-Thought 与 Reasoning Model**

Chain-of-Thought 让生成过程包含中间推理 Token，使后续步骤可以读取前面的中间结果；Reasoning Model 通常还经过针对推理行为的训练，并可能使用更多测试时计算。中间推理仍可能出错，不能代替工具结果、代码测试、来源证据或业务验证器。

**能力边界**

LLM 本质上仍是条件概率生成器。参数知识不是可查询数据库，Context Window 不是长期记忆，偏好对齐不是权限控制，低 Temperature 也不等于事实正确；Agent Runtime 仍需负责外部知识、状态、验证、权限和副作用控制。

### 高频对比

| 对比项 | 训练 | 推理 |
|---|---|---|
| 参数 | 通过梯度和优化器更新 | 保持冻结 |
| 输入 | 已知完整训练序列，可构造 next-token 标签 | 只有当前可见前缀，没有未来标签 |
| 主要计算 | 前向计算、Loss、反向传播、优化器更新 | Prefill、Decode 和 Token 选择 |
| 序列并行性 | 可借助 Causal Mask 同时计算多个目标位置 | Decode 在时间维度逐 Token 串行 |

| 对比项 | Prefill | Decode |
|---|---|---|
| 处理对象 | 全部输入 Token | 每一步新增的一个 Token |
| 并行特征 | 输入位置可以并行计算 | 单条序列的生成步骤相互依赖 |
| 主要影响 | 首 Token 延迟 | 输出速度和总完成时间 |
| KV Cache | 创建输入前缀的初始缓存 | 读取历史缓存并追加新 Token 的缓存 |

### 高频追问

#### 追问：只预测下一个 Token，为什么能表现出问答、翻译和代码生成能力？

为了在大规模、多领域语料中持续降低 next-token loss，模型必须学习词法、句法、语义、实体关系和任务模式的可复用表示。能力来自数据、模型容量和训练过程共同形成的统计泛化，但训练目标仍然只是条件概率建模，并不直接保证事实性、逻辑正确或遵循业务规则。

#### 追问：为什么训练时可以并行预测所有位置，推理时却要逐 Token 生成？

训练时完整目标序列已经存在，Causal Mask 可以在一次前向计算中同时为每个位置构造只看左侧的表示。推理时下一个 Token 尚不存在，而再下一个 Token 又依赖刚生成的结果，因此 Decode 在序列维度上具有无法消除的自回归依赖。

#### 追问：为什么使用 KV Cache 后，长上下文仍然会变慢并占用更多显存？

KV Cache 只避免重新计算历史 Token 的 Key 和 Value，新 Query 仍要读取并关注允许访问的历史缓存；缓存大小也会随层数、序列长度、KV Head 数、Head Dimension 和并发序列数增长。它降低了重复计算，不会让历史长度变成零成本。

#### 追问：Temperature 设为 0，模型输出就完全确定了吗？

它通常表示使用 Greedy Decoding 或近似确定性路径，但完整服务仍可能受模型版本、数值精度、并行归约、批处理和后端实现影响。即使字节级输出稳定，也只说明复现性更强，不说明答案正确。

#### 追问：Chain-of-Thought 和 Reasoning Model 的关系是什么？

Chain-of-Thought 是让生成过程包含中间推理步骤的一类提示或输出方式；Reasoning Model 通常还经过针对推理行为的训练，并可能在推理时使用更多 Token、搜索或验证计算。两者都可能提高复杂任务表现，但中间文本仍可能出错，不能代替工具结果、测试或业务验证器。

---

## 1. 从文本到文本的完整计算链

如果把 Token、Embedding、Transformer、训练和推理分别记成五个定义，很容易知道每个词，却不知道它们为什么必须按这个顺序出现。更有用的心智模型是一条从数据到参数、再从参数到生成结果的因果链。

```text
训练语料
   ↓ 清洗、去重、切分
Token 序列
   ↓ Embedding + 位置信息
向量序列
   ↓ 多层 Decoder-only Transformer
每个位置的 logits
   ↓ 与真实下一个 Token 计算交叉熵
Loss
   ↓ 反向传播 + 优化器
更新模型参数

训练完成后冻结参数
   ↓
输入文本 → Token → Prefill → 首个 next-token logits
                                ↓ 采样一个 Token
                           Decode + KV Cache
                                ↓
                         重复直到停止 → 文本
```

这条链同时解释了三个边界。Tokenizer 不是无关的预处理，因为它决定模型实际接收的离散序列；Transformer 不是独立于语言模型目标的架构名，因为参数要靠 next-token loss 才学到行为；推理也不是“把训练再运行一次”，因为推理只有前向计算和生成，不更新参数。

本章以当前文本 LLM 中最常见的 Decoder-only Transformer 为主。原始 Transformer 是为机器翻译提出的 Encoder–Decoder 架构；BERT 一类模型以 Encoder 为主，T5 一类模型保留 Encoder–Decoder，而 GPT、Llama 等生成式文本模型通常采用 Decoder-only。并非所有序列模型都必须使用 Transformer，但这不影响本章对主流 LLM 的解释。

## 2. Token：模型处理的不是“字”或“单词”

神经网络接收数值张量，不能直接对 Unicode 字符串做矩阵乘法。Tokenizer（分词器）首先把文本转换成固定词表中的 Token ID：

```text
文本："Agent 调用工具"
          ↓ tokenizer.encode
Token： ["Agent", " 调", "用", "工具"]   ← 仅为示意，真实切分取决于词表
          ↓ 查词表
ID：    [18342, 721, 1048, 9231]
```

Token 既不必等于一个单词，也不必等于一个字符。常见分词方法会在字符、字节和完整单词之间学习一组可复用的子词单元，使有限词表能够表示开放文本。高频片段可能占一个 Token，罕见词、代码标识符、数字或不同语言的文本可能被拆成多个 Token；特殊 Token 还可以表示文本结束、消息边界或填充位置。

以 Byte Pair Encoding（BPE）为代表的子词方法，可以从较小单元出发，反复合并训练数据中高频的相邻单元。实际 LLM 也可能使用 Unigram、byte-level BPE 或其他变体，因此不要背诵某个英文单词固定对应几个 Token。Token 数量必须由目标模型实际使用的 Tokenizer 计算。

Tokenizer 会直接产生工程影响：

| 机制 | 工程后果 |
|---|---|
| 不同模型使用不同词表 | 同一段文本的输入长度和费用可能不同 |
| 罕见字符串被拆成很多 Token | UUID、Base64、日志和压缩数据会快速消耗上下文 |
| Token 是模型的生成单位 | Streaming 通常先收到 Token 片段，字符边界可能尚未完整 |
| 输入和输出共享有限窗口 | 工具定义、历史消息和检索结果都会挤占生成空间 |
| 特殊 Token 表示结构边界 | Chat Template 错误会让模型看到与训练时不同的序列 |

“一个汉字等于一个 Token”“一个 Token 等于一个英文单词”都不是可靠规则。对于 Agent，更不能只按消息条数管理 Context；一条包含大段工具输出的消息可能比数十轮短对话更昂贵。

## 3. Embedding：从离散 ID 到可计算表示

词表中的 Token ID 只是编号，`18342` 比 `721` 大并没有语义。Token Embedding 是一个可学习矩阵：

$$
E \in \mathbb{R}^{|V| \times d}
$$

其中 $|V|$ 是词表大小，$d$ 是模型隐藏维度。ID 为 $i$ 的 Token 通过查表得到向量 $E_i$。训练开始时这些向量通常没有人类可读的含义；随着 loss 反向传播，处于相似上下文中的 Token 会形成对预测有用的几何结构。

必须区分两类表示：

- Token Embedding 是输入层查表得到的初始向量，同一 Token 在进入网络时取到相同参数行。
- Contextual Representation 是经过多层 Attention 和 MLP 后的位置表示，会随前后文变化。同一个“bank”出现在金融和河岸语境中，最终隐藏状态可以不同。

仅有 Token Embedding 还无法表示顺序。若模型只看到一组向量，它无法区分“模型调用工具”和“工具调用模型”。原始 Transformer 将位置编码加入输入；现代 Decoder-only LLM 也常用 Rotary Position Embedding（RoPE，旋转位置编码）等方式把位置信息作用于 Attention 中的 Query 和 Key。具体实现会变化，但共同目的都是让注意力计算能够区分位置及相对距离。

完成 Token Embedding 和位置信息注入后，长度为 $T$ 的输入就成为矩阵：

$$
X \in \mathbb{R}^{T \times d}
$$

后续 Transformer Block 始终在向量序列上工作。最后的 LM Head 再把隐藏向量投影回词表维度，形成每个候选 Token 的分数。

## 4. Decoder-only Transformer 如何计算下一个 Token

一个典型 Decoder-only 模型会重复堆叠 Transformer Block，再通过归一化层和 LM Head 输出 logits：

```text
Token IDs
   ↓
Token Embedding + Position Information
   ↓
┌────────────────────────────────────────────┐
│ Transformer Block × N                      │
│                                            │
│  x ─→ Norm ─→ Causal Self-Attention ─┐     │
│  └────────────────────────────────────+→ x' │
│                                            │
│  x' ─→ Norm ─→ MLP / FFN ────────────┐     │
│  └────────────────────────────────────+→ y  │
└────────────────────────────────────────────┘
   ↓
Final Norm
   ↓
LM Head：隐藏维度 d → 词表大小 |V|
   ↓
Next-token logits
```

图中的残差连接让 Block 学习对已有表示的增量变换，Normalization 有助于稳定优化，Attention 在不同位置之间交换信息，MLP 则对每个位置的表示做非线性变换。两个子层缺一不可：Attention 负责“从哪些位置读取什么”，MLP 负责对读到的信息进行逐位置计算和特征变换。

### Self-Attention

对输入 $X$ 做三组线性投影，可以得到 Query、Key 和 Value：

$$
Q=XW_Q, \qquad K=XW_K, \qquad V=XW_V
$$

Scaled Dot-Product Attention 为：

$$
\operatorname{Attention}(Q,K,V)
=\operatorname{softmax}\left(\frac{QK^\top}{\sqrt{d_k}}+M\right)V
$$

$QK^\top$ 衡量一个位置的 Query 与各位置 Key 的匹配程度，除以 $\sqrt{d_k}$ 用于控制数值尺度，Softmax 将分数转成权重，最后对 Value 加权求和。Multi-Head Attention 会在多个子空间并行执行这一过程，再合并各 Head 的结果。

Attention Weight 并不是完整的人类解释，也不等价于因果归因。它只是该层前向计算中的一个中间量；模型行为还经过所有层的残差、MLP 和后续投影。

### Causal Mask

自回归模型要求第 $t$ 个位置只能使用 $1 \ldots t$ 的信息，不能偷看右侧真实答案。Causal Mask 将未来位置的 Attention Score 设为负无穷，Softmax 后相应权重变为零：

```text
              可被当前行关注的 Key 位置
Query 位置      1     2     3     4
    1           ✓     ×     ×     ×
    2           ✓     ✓     ×     ×
    3           ✓     ✓     ✓     ×
    4           ✓     ✓     ✓     ✓
```

这就是训练可以一次处理整段序列、却仍然遵守自回归条件的关键。若训练时没有 Causal Mask，模型可以直接从右侧读到目标 Token，loss 看似很低，部署时却没有未来答案可读，训练条件和推理条件就不一致。

### 原始 Transformer 与现代文本 LLM

Transformer 是架构族，不是永远不变的一张结构图。理解原始机制后，还应认识常见演化方向，但不要把某个模型家族的配置当成所有 LLM 的定义。

| 维度 | 原始 Transformer 的典型设计 | 现代 Decoder-only LLM 中的常见选择 | 主要动机 |
|---|---|---|---|
| 主体 | Encoder–Decoder | 只保留带 Causal Mask 的 Decoder | 自回归文本生成 |
| 位置 | 正弦位置编码 | RoPE 等相对或旋转位置方法 | 表示位置关系、支持上下文扩展 |
| 归一化 | 常见为子层后的 LayerNorm | Pre-Norm、RMSNorm 等 | 训练稳定性和实现效率 |
| MLP | ReLU FFN | GELU、SwiGLU 等 | 改善表达和训练效果 |
| Attention Head | Multi-Head Attention | MHA、MQA 或 GQA | 在质量、KV Cache 和解码速度间取舍 |
| 参数使用 | Dense Block | Dense 或 Mixture-of-Experts | 在激活计算量与模型容量间取舍 |

这些变化不会改变本章主链：输入仍被表示为序列，层间仍在变换表示，输出仍形成对候选 Token 的分布。

## 5. 训练：用已知后文学习预测未来

给定 Token 序列 $x_1, x_2, \ldots, x_T$，自回归语言模型将联合概率分解为：

$$
P(x_1,\ldots,x_T)=\prod_{t=1}^{T}P(x_t\mid x_{<t})
$$

训练通常最小化真实下一个 Token 的负对数似然，也就是对各位置做交叉熵：

$$
\mathcal{L}=-\sum_{t=1}^{T}\log P_\theta(x_t\mid x_{<t})
$$

例如，训练序列经过移位后形成输入和标签：

```text
原始序列： <BOS>  我  喜欢  AI  <EOS>
模型输入： <BOS>  我  喜欢  AI
监督标签：   我   喜欢  AI  <EOS>
```

完整目标序列在训练数据中已经存在，因此 GPU 可以同时计算所有位置的 logits；Causal Mask 保证每个位置只使用合法前缀。这种用真实历史 Token 预测下一项的训练方式通常称为 Teacher Forcing。它高效，但也意味着训练时看到的前缀来自数据，推理时的前缀可能包含模型自己先前生成的错误，错误因而可能逐步累积。

一次训练更新的过程是：

```text
数据样本
   ↓ Tokenize、拼接、截断、分 Batch
input_ids 与 next-token labels
   ↓ Forward Pass
logits
   ↓ Cross-Entropy Loss
标量 loss
   ↓ Backpropagation
每个参数的梯度
   ↓ Optimizer Step
更新后的 Embedding、Attention、MLP 和输出层参数
```

训练不是把语料逐条原样写入可查询数据库。优化器只根据梯度调整大量浮点参数，使正确 Token 在相似前缀下获得更高概率。模型可能近似记住部分训练片段，也可能学到可迁移模式；仅凭生成结果通常无法区分某条内容来自记忆、组合还是猜测。

### 从 Base Model 到可交互模型

“训练一个 LLM”往往包含多个目标不同的阶段，而不是只运行一次 next-token 训练。

| 阶段 | 主要数据和目标 | 主要获得什么 | 不能保证什么 |
|---|---|---|---|
| Pretraining | 大规模文本或多模态序列上的预测目标 | 通用语言、知识和模式能力 | 稳定遵循用户指令 |
| Continued Pretraining | 领域语料上的继续预训练 | 领域分布和术语适应 | 自动学会任务格式和安全边界 |
| Supervised Fine-Tuning | 指令—理想回答示例 | 对话格式、任务示范和指令遵循 | 偏好排序一定合理 |
| Preference Optimization | 成对偏好、评分或奖励信号 | 更偏向有帮助、安全或符合风格的输出 | 事实和推理永远正确 |
| Reasoning-focused Training | 可验证任务、推理轨迹或结果奖励 | 更有效地分配中间推理与测试时计算 | 对任意任务都值得增加计算 |

RLHF（基于人类反馈的强化学习）是一类流程：先从比较数据中学习奖励信号，再在约束下优化策略模型。DPO（Direct Preference Optimization，直接偏好优化）则把偏好对直接转化为分类式目标，省去显式训练并在线使用奖励模型的部分复杂度。它们是不同训练方法，不是“对齐”一词的唯一实现。

对 Agent 开发者而言，最重要的不是复现大型训练集群，而是理解模型层级差异。Base Model 可能更像文本续写器；Instruction Model 更适合遵循消息与工具格式；Reasoning Model 可能愿意为复杂问题使用更多推理 Token。模型名称相近，也不代表训练目标、工具能力、上下文长度和输出行为相同。

模型规模也不是唯一变量。在固定训练计算量下，参数量、训练 Token 数量与数据质量需要共同权衡；“参数更多必然更好”既不是训练规律，也不是应用选型方法。

## 6. 推理：冻结参数后逐 Token 生成

推理时没有标签、loss、反向传播和优化器更新。服务将输入转换成 Token，运行前向计算得到最后位置的 logits，选择一个新 Token，把它接到序列末尾，再计算下一个 Token。

```text
前缀：[用户, 问题, ...]
            ↓ Forward
P(Token₁ | 前缀)
            ↓ 选择 Token₁
前缀：[用户, 问题, ..., Token₁]
            ↓ Forward
P(Token₂ | 前缀, Token₁)
            ↓
持续生成，直到 EOS、Stop Sequence、长度限制或外部取消
```

### Prefill 与 Decode

生产推理通常将一次生成分成两个性能特征不同的阶段：

| 阶段 | 处理内容 | 并行特征 | 用户常见感知 | 主要资源压力 |
|---|---|---|---|---|
| Prefill | 一次处理全部输入 Token | 序列位置可并行计算 | 首 Token 延迟的一部分 | 长输入的计算量和 Attention 中间结果 |
| Decode | 每步生成一个新 Token | 单条序列在时间维度串行 | 输出速度、总完成时间 | 模型权重读取和不断增长的 KV Cache |

因此，输入 Token 和输出 Token 对延迟的影响并不对称。很长的 Prompt 会增加 Prefill 工作；很长的回答会增加 Decode 步数。Agent 每执行一次工具再调用模型，通常又要进行一次新的生成过程，Context 设计会直接放大端到端延迟和费用。

### KV Cache 为什么有效

每层 Self-Attention 都会为历史 Token 计算 Key 和 Value。生成第 $t+1$ 个 Token 时，历史 $1\ldots t$ 的 Key、Value 没有变化；若每一步都重新计算整个前缀，会重复大量工作。KV Cache 保存各层历史位置的 Key 和 Value，新一步只计算新 Token 的表示，并让新 Query 读取缓存。

```text
没有 KV Cache：
Step 1  计算 [A B C]
Step 2  重新计算 [A B C] + [D]
Step 3  重新计算 [A B C D] + [E]

使用 KV Cache：
Prefill  计算并保存 KV[A B C]
Step 1   只计算 D，保存 KV[D]
Step 2   只计算 E，保存 KV[E]
```

缓存不是免费的。对标准 Attention，单条序列的 KV Cache 大小大致随以下乘积线性增长：

```text
层数 × 缓存 Token 数 × KV Head 数 × Head Dimension × K/V 两份 × 数值字节数
```

并发请求会各自保存缓存，长上下文因而可能先受显存容量限制。MQA 和 GQA 通过让多个 Query Head 共享较少的 Key/Value Head，正是为了降低这部分缓存与读取压力。Prefix Cache 则可复用完全相同前缀的 KV，但只有严格匹配且隔离策略正确的前缀才能安全复用。

## 7. 从 logits 到生成文本

LM Head 为词表中的每个 Token 产生一个未经归一化的分数 $z_i$，即 logit。Softmax 将其转成概率：

$$
P(x_i)=\frac{e^{z_i/\tau}}{\sum_j e^{z_j/\tau}}
$$

$\tau$ 是 Temperature。较低 Temperature 会放大分数差异，使分布更集中；较高 Temperature 使分布更平坦。Temperature 不会改变模型参数，也不会验证候选内容，只改变本次如何从已有分布中选择。

| 解码策略 | 做法 | 适合场景 | 主要风险 |
|---|---|---|---|
| Greedy | 每步选择最高概率 Token | 需要低随机性的抽取或格式任务 | 局部最优、重复、并非全序列最优 |
| Temperature Sampling | 按温度缩放后的分布采样 | 需要多样性的生成 | 波动和低概率错误增加 |
| Top-k | 只保留概率最高的 k 个候选 | 限制长尾候选 | 固定 k 不适应分布形状 |
| Top-p | 保留累计概率达到 p 的最小候选集 | 自适应控制候选范围 | 仍然具有随机性和参数敏感性 |

下面的教学实现把前述组件连接成一个可训练、可生成的最小 Decoder-only 模型。它使用单头 Attention 和学习式位置 Embedding，没有 KV Cache、Batch 调度和数值优化；重点是暴露因果链，而不是模拟生产模型规模。

```python
import math

import torch
from torch import nn
from torch.nn import functional as F


class CausalSelfAttention(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.query = nn.Linear(hidden_size, hidden_size, bias=False)
        self.key = nn.Linear(hidden_size, hidden_size, bias=False)
        self.value = nn.Linear(hidden_size, hidden_size, bias=False)
        self.output = nn.Linear(hidden_size, hidden_size, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, seq_len, hidden_size = x.shape
        q, k, v = self.query(x), self.key(x), self.value(x)
        scores = q @ k.transpose(-2, -1) / math.sqrt(hidden_size)

        future = torch.triu(
            torch.ones(seq_len, seq_len, device=x.device, dtype=torch.bool),
            diagonal=1,
        )
        weights = F.softmax(scores.masked_fill(future, float("-inf")), dim=-1)
        return self.output(weights @ v)


class TransformerBlock(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.attention_norm = nn.LayerNorm(hidden_size)
        self.attention = CausalSelfAttention(hidden_size)
        self.mlp_norm = nn.LayerNorm(hidden_size)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_size, 4 * hidden_size),
            nn.GELU(),
            nn.Linear(4 * hidden_size, hidden_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attention(self.attention_norm(x))
        return x + self.mlp(self.mlp_norm(x))


class TinyCausalLM(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 64,
        max_seq_len: int = 128,
        num_layers: int = 2,
    ) -> None:
        super().__init__()
        self.max_seq_len = max_seq_len
        self.token_embedding = nn.Embedding(vocab_size, hidden_size)
        self.position_embedding = nn.Embedding(max_seq_len, hidden_size)
        self.blocks = nn.ModuleList(
            TransformerBlock(hidden_size) for _ in range(num_layers)
        )
        self.final_norm = nn.LayerNorm(hidden_size)
        self.lm_head = nn.Linear(hidden_size, vocab_size, bias=False)
        self.lm_head.weight = self.token_embedding.weight

    def forward(
        self,
        input_ids: torch.Tensor,
        targets: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        _, seq_len = input_ids.shape
        if seq_len > self.max_seq_len:
            raise ValueError("sequence exceeds the model context window")

        positions = torch.arange(seq_len, device=input_ids.device)
        x = self.token_embedding(input_ids) + self.position_embedding(positions)
        for block in self.blocks:
            x = block(x)

        logits = self.lm_head(self.final_norm(x))
        loss = None
        if targets is not None:
            loss = F.cross_entropy(
                logits.reshape(-1, logits.size(-1)),
                targets.reshape(-1),
            )
        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        input_ids: torch.Tensor,
        *,
        max_new_tokens: int,
        temperature: float = 1.0,
        top_k: int | None = None,
        eos_token_id: int | None = None,
    ) -> torch.Tensor:
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        if input_ids.size(0) != 1:
            raise ValueError("this teaching generator only supports batch size 1")
        if top_k is not None and top_k <= 0:
            raise ValueError("top_k must be positive")

        for _ in range(max_new_tokens):
            visible = input_ids[:, -self.max_seq_len :]
            logits, _ = self(visible)
            next_logits = logits[:, -1, :] / temperature

            if top_k is not None:
                k = min(top_k, next_logits.size(-1))
                threshold = torch.topk(next_logits, k).values[:, -1, None]
                next_logits = next_logits.masked_fill(
                    next_logits < threshold,
                    float("-inf"),
                )

            probabilities = F.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probabilities, num_samples=1)
            input_ids = torch.cat((input_ids, next_token), dim=1)

            if eos_token_id is not None and torch.all(next_token == eos_token_id):
                break

        return input_ids
```

训练调用只需把同一序列错开一位：

```python
model = TinyCausalLM(vocab_size=32)
tokens = torch.tensor([[1, 8, 5, 13, 2]])

_, loss = model(tokens[:, :-1], targets=tokens[:, 1:])
assert loss is not None
loss.backward()

generated = model.generate(tokens[:, :2], max_new_tokens=4, top_k=5)
```

代码中的 `loss.backward()` 计算梯度，但示例没有调用优化器；真实训练还需 `optimizer.step()`、梯度清零、Batch、验证集、Checkpoint 和分布式执行。`generate()` 每步重新计算可见前缀，正好暴露了没有 KV Cache 的低效；生产实现不会用这段教学代码提供服务。

## 8. In-context Learning、Chain-of-Thought 与测试时计算

训练结束并不意味着模型只能复现一个固定函数接口。Prompt 中的指令和示例会改变当前 Token 序列，从而改变层内激活与后续条件分布；参数没有更新，但模型可以根据上下文临时呈现任务模式，这称为 In-context Learning（上下文学习）。

| 方式 | Prompt 中提供什么 | 是否更新模型参数 |
|---|---|---:|
| Zero-shot | 任务指令，不给示例 | 否 |
| One-shot | 一个输入—输出示例 | 否 |
| Few-shot | 少量示例 | 否 |
| Fine-tuning | 训练数据在离线训练中使用 | 是 |

Chain-of-Thought（CoT，思维链）提示进一步要求或示范若干中间步骤。它可能有效，是因为模型获得了更多生成 Token 来表示中间结果、分解问题，并让后一步以这些中间 Token 为条件；这是一种测试时计算，而不是对参数的在线训练。

```text
直接回答：问题 → 答案

Chain-of-Thought：问题 → 中间步骤₁ → 中间步骤₂ → 答案
                          ↑ 后续 Token 可读取前面的中间结果
```

但“写得更长”不等于“想得更对”。错误的第一步也会进入后续前缀，形成自洽却错误的解释；简单任务强制长推理还会增加延迟、费用和偏离格式的机会。对于数学、代码和工具执行，外部计算器、测试、检索证据、Verifier 或多次采样后的选择，通常比相信一段流畅推理文本更可靠。

Reasoning Model 是模型训练与推理策略层面的更大集合。它可能通过监督轨迹、结果可验证的强化学习或其他方法，学会在困难任务上使用更多中间计算；服务还可能自适应分配推理预算。推理 Token 越多通常意味着更高延迟和成本，而且收益取决于任务难度：如果基础模型几乎不会做，盲目增加采样未必有效；如果任务本来很简单，额外计算也可能浪费。

对 Agent 系统还有一个重要边界：模型内部或隐藏的 Chain-of-Thought 不应被当作审计日志。系统应记录可观察的输入、Tool Call、工具结果、状态变化、证据和最终输出；需要解释时，可以要求简洁的决策依据，但不能把自然语言推理当成权限证明或执行事实。

ReAct 会在第 04 章讨论。它不是 Transformer 内部结构，而是把推理、行动和环境观察组织成 Agent Loop 的控制模式；理解本章的自回归生成后，才能解释为什么每次工具 Observation 会成为下一轮模型生成的新条件。

## 9. 从生成机制推导模型边界

LLM 的强大和局限来自同一机制：它根据当前可见前缀产生条件分布。下面的结论不是额外背诵项，而可以直接从训练与推理过程推出。

### 参数知识不是可查询数据库

训练把数据的统计规律压入参数，不保存稳定的“事实记录 ID → 值”接口。模型可能混合相似实体、使用过时内容或生成训练中从未出现的组合。要求引用、时效性或权限过滤时，应使用外部数据源和 Retrieval，而不是让模型凭参数回忆。

### Context Window 是容量上限，不是理解保证

文本能够放入窗口，只表示服务可以接收这些 Token，不表示模型会同等重视每一处信息，也不表示应用有权把它们放进去。位置、噪声、冲突指令和检索质量都会影响结果。Context Engineering 需要选择、排序和隔离信息，而不是只追求最长窗口。

### Hallucination 不是一个可关闭的开关

模型被训练为给前缀续写高概率 Token，而不是在每次生成前查询真值判定器。当上下文缺少证据、问题含错误前提或模型置信校准不足时，流畅续写仍可能产生。降低 Temperature 能减少随机分支，却不能把错误的最高概率候选变成事实。

### 对齐不等于授权

Instruction Tuning 和 Preference Optimization 可以使模型更愿意遵循指令或拒绝部分请求，但模型仍处理来自用户、工具、网页和文件的 Token。真正的身份、权限、预算和副作用控制必须由 Agent Runtime 的确定性机制执行。

## 10. 这些原理怎样影响 Agent 工程

Agent 开发者通常不训练基础模型，但每天都在承受训练与推理机制的工程后果。

| 模型机制 | Agent 中的直接后果 |
|---|---|
| Tokenizer 决定序列长度 | Context 预算必须按 Token 计算，工具输出需要裁剪或摘要 |
| 模型只看本轮可见 Token | 未写入 Context 的 State 对模型等于不存在 |
| 自回归生成 | 输出越长 Decode 越慢，循环多轮会累积延迟和成本 |
| Causal Attention | 工具结果必须出现在 Tool Call 之后，消息顺序会改变条件分布 |
| KV Cache 占用随上下文增长 | 长会话和高并发需要显存、缓存淘汰与隔离策略 |
| logits 是候选分数 | Tool Call 也可能选错工具或生成无效参数，必须校验 |
| In-context Learning 不改参数 | Few-shot 示例只对当前可见上下文生效，不会永久教会模型 |
| CoT 仍是生成 Token | 推理文本不能代替外部证据、测试和权限判断 |
| 对齐改变行为倾向 | “模型通常会拒绝”不能成为安全边界 |
| 参数在单次推理中冻结 | 新事实必须通过 Context、工具、RAG 或重新训练提供 |

一次异常输出可以沿本章计算链定位：

```text
原始输入是否正确？
   ↓
Tokenizer / Chat Template 是否得到预期 Token？
   ↓
关键指令和证据是否位于可见 Context？
   ↓
模型与训练类型是否适合任务？
   ↓
logits 是否被不合适的采样参数放大了波动？
   ↓
是否因长度限制、EOS 或 Stop 条件提前结束？
   ↓
Runtime 是否验证了结构、事实和工具副作用？
```

只修改 Prompt 并不能修复所有层。输入被错误截断需要修 Context；模型缺乏领域能力可能需要换模型、RAG 或 Fine-tuning；输出随机性过高可以调整采样；业务字段即使语法正确仍需验证器；事实必须由可信数据源核验。

## 常见误区

### Embedding 就是模型对一个词的最终理解

Embedding 只是初始查表向量。真正用于当前预测的是经过多层、结合上下文后的隐藏表示；同一 Token 在不同语境中的表示可以不同。

### Self-Attention 等于模型在搜索训练资料

Self-Attention 在本次输入序列的表示之间计算权重，不会自动访问训练语料、互联网或数据库。外部搜索必须通过工具或 Retrieval 显式完成。

### 模型训练后会在对话中继续学习并更新参数

普通推理不会反向传播。把一条事实告诉模型，只是将它加入当前 Context；新会话是否还能使用，取决于应用是否保存并重新提供，而不是模型自动完成了训练。

### 更大的 Context Window 等于更强的长期记忆

窗口是一次前向计算可见的 Token 容量。长期 Memory 还需要持久化、更新、召回、权限和删除策略，两者处于不同系统层。

### Chain-of-Thought 是模型正确性的证明

中间步骤和最终答案一样都是模型生成，可能合理、错误或事后自洽。可验证任务应检查计算结果、代码测试、来源证据和环境最终状态。

## 学习检查

读完本章后，应当能够：

1. 从文本开始，画出 Token、Embedding、Transformer、logits、loss 和生成结果之间的完整因果链。
2. 写出自回归概率分解，并解释 next-token labels 为什么要相对输入错开一位。
3. 用 Query、Key、Value 和 Causal Mask 解释 Decoder-only Self-Attention。
4. 区分 Pretraining、Supervised Fine-Tuning、Preference Optimization 和推理。
5. 解释 Prefill 与 Decode 的性能差异，以及 KV Cache 节省了什么、付出了什么。
6. 区分 logits、概率、Temperature、Top-k 和 Top-p，不把低随机性等同于正确性。
7. 说明 In-context Learning、Chain-of-Thought 和 Fine-tuning 是否更新参数，以及各自的适用边界。
8. 从模型机制推导 Agent 为什么仍需要 Context 管理、工具校验、外部知识、Evals 和 Runtime 安全控制。

## 参考资料与结论对应关系

- [Neural Machine Translation of Rare Words with Subword Units](https://arxiv.org/abs/1508.07909)，Sennrich、Haddow 与 Birch，用于核对子词单元和 BPE 将罕见词表示为更小单元、缓解固定词表开放文本问题的原始机制，最后核验日期：2026-07-22。
- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)，Vaswani 等，用于核对原始 Encoder–Decoder Transformer、Scaled Dot-Product Attention、Multi-Head Attention、位置编码、残差连接、前馈网络与自回归掩码，最后核验日期：2026-07-22。
- [RoFormer: Enhanced Transformer with Rotary Position Embedding](https://arxiv.org/abs/2104.09864)，Su 等，用于核对 RoPE 将位置信息作用于 Query 和 Key、表达相对位置关系的机制；正文只将其列为现代架构常见选择之一，最后核验日期：2026-07-22。
- [GLU Variants Improve Transformer](https://arxiv.org/abs/2002.05202)，Shazeer，用于核对 GEGLU、SwiGLU 等门控前馈层相对原始 ReLU FFN 的架构演化，最后核验日期：2026-07-22。
- [GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints](https://arxiv.org/abs/2305.13245)，Ainslie 等，用于核对 MQA/GQA 减少 Key-Value Head、在质量与 Decoder 推理效率之间取舍的机制，最后核验日期：2026-07-22。
- [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165)，Brown 等，用于核对不更新参数、仅通过文本指令和少量示例完成 Zero-shot、One-shot 与 Few-shot 任务的 In-context Learning 现象，最后核验日期：2026-07-22。
- [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155)，Ouyang 等，用于核对监督示范、输出排序、奖励模型和基于人类反馈的强化学习在指令对齐中的不同阶段，最后核验日期：2026-07-22。
- [Direct Preference Optimization: Your Language Model is Secretly a Reward Model](https://arxiv.org/abs/2305.18290)，Rafailov 等，用于核对 DPO 直接使用偏好数据优化语言模型、无需显式拟合并在 RL 中使用独立奖励模型的核心区别，最后核验日期：2026-07-22。
- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903)，Wei 等，用于核对通过少量带中间推理步骤的示例改善部分算术、常识和符号推理任务的实验结论；正文没有把这一结果外推为所有模型和任务的保证，最后核验日期：2026-07-22。
- [Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314)，Snell 等，用于核对测试时计算方法的效果取决于问题难度、计算应按任务自适应分配，以及增加推理计算并非无条件有效，最后核验日期：2026-07-22。
- [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556)，Hoffmann 等，用于核对固定训练计算预算下模型参数量与训练 Token 数需要共同扩展，而非只扩大参数量，最后核验日期：2026-07-22。
- [Caching](https://huggingface.co/docs/transformers/main/cache_explanation)，Hugging Face Transformers 官方文档，用于核对自回归推理中 KV Cache 保存历史 Key/Value、避免每一步重复计算，以及缓存仅应用于推理的机制，最后核验日期：2026-07-22。
