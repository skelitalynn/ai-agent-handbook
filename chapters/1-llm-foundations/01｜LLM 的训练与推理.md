# 01｜LLM 的训练与推理

> 本章沿一条完整计算链解释大语言模型：文本如何被切成 Token，Token 如何变成向量，Decoder-only Transformer 如何计算下一个 Token 的分布，训练如何修改参数，推理又如何在参数不变的情况下逐 Token 生成。Token、Embedding 和 Transformer 不拆成孤立章节，因为它们共同解释同一个因果过程。

## 面试速记

### 背诵提纲

**1. 定义**

大语言模型通常是以 Decoder-only Transformer 为骨干的自回归模型。它根据已有 Token 计算下一个 Token 的条件概率，通过不断把新 Token 追加到前缀中完成文本生成。

**2. 完整计算链**

```text
训练：文本 → Token ID → Embedding → Transformer → logits
           → next-token loss → 反向传播 → 更新参数

推理：输入文本 → Token ID → Prefill → next-token logits
           → 选择 Token → Decode → 重复生成直到停止
```

**3. 输入表示**

- **Tokenization**：把文本切分为 Token 并映射成整数 ID；Token 不等于固定的字符或单词。
- **Embedding**：把离散 Token ID 转换为连续向量。
- **位置信息**：让模型能够区分 Token 的顺序和相对位置。

**4. Transformer**

- **Self-Attention**：通过 Query、Key 和 Value 聚合序列中其他位置的信息。
- **Causal Mask**：禁止当前位置关注未来 Token，使训练条件与自回归推理一致。
- **MLP**：对每个位置的隐藏表示进行非线性变换。

**5. 训练**

- **训练目标**：根据已有 Token 预测下一个 Token，通常使用交叉熵计算 Loss。
- **参数更新**：训练包含前向计算、反向传播和优化器更新。
- **训练阶段**：通常包括预训练、监督微调和偏好优化，三者的训练数据与目标不同。

**6. 推理**

- **Prefill**：并行处理全部输入 Token，并生成初始 KV Cache。
- **Decode**：每次生成一个 Token，在时间维度上必须串行执行。
- **KV Cache**：缓存历史 Key 和 Value，避免重复计算前缀，本质上是用显存换速度。
- **采样**：Temperature、Top-k 和 Top-p 改变 Token 选择分布，不保证答案正确。

**7. 上下文学习与推理**

- **In-context Learning**：通过当前 Prompt 中的指令和示例改变输出，不更新模型参数。
- **Chain-of-Thought**：生成中间推理 Token，增加测试时计算，但不能保证推理正确。

**8. 能力边界**

参数知识不是数据库，Context Window 不是长期记忆，偏好对齐不是权限控制，低随机性也不等于事实正确。

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

### 高频问题

#### 问题1：只预测下一个 Token，为什么能表现出问答、翻译和代码生成能力？

为了在大规模、多领域语料中持续降低 next-token loss，模型必须学习词法、句法、语义、实体关系和任务模式的可复用表示。能力来自数据、模型容量和训练过程共同形成的统计泛化，但训练目标仍然只是条件概率建模，并不直接保证事实性、逻辑正确或遵循业务规则。

#### 问题2：为什么训练时可以并行预测所有位置，推理时却要逐 Token 生成？

训练时完整目标序列已经存在，Causal Mask 可以在一次前向计算中同时为每个位置构造只看左侧的表示。推理时下一个 Token 尚不存在，而再下一个 Token 又依赖刚生成的结果，因此 Decode 在序列维度上具有无法消除的自回归依赖。

#### 问题3：为什么使用 KV Cache 后，长上下文仍然会变慢并占用更多显存？

KV Cache 只避免重新计算历史 Token 的 Key 和 Value，新 Query 仍要读取并关注允许访问的历史缓存；缓存大小也会随层数、序列长度、KV Head 数、Head Dimension 和并发序列数增长。它降低了重复计算，不会让历史长度变成零成本。

#### 问题4：Temperature 设为 0，模型输出就完全确定了吗？

它通常表示使用 Greedy Decoding 或近似确定性路径，但完整服务仍可能受模型版本、数值精度、并行归约、批处理和后端实现影响。即使字节级输出稳定，也只说明复现性更强，不说明答案正确。

#### 问题5：Chain-of-Thought 和 Reasoning Model 的关系是什么？

Chain-of-Thought 是让生成过程包含中间推理步骤的一类提示或输出方式；Reasoning Model 通常还经过针对推理行为的训练，并可能在推理时使用更多 Token、搜索或验证计算。两者都可能提高复杂任务表现，但中间文本仍可能出错，不能代替工具结果、测试或业务验证器。

---

## 1. 先看全程：LLM 怎样学会并完成一次续写

先用一句未完成的话贯穿全章：输入是“今天天气很”，模型需要继续生成“好”。这不是一次从文字到答案的直接跳转，而是一串连续的计算。

```text
文本“今天天气很”
   ↓ Tokenizer
Token ID 序列
   ↓ Embedding + 位置信息
向量序列
   ↓ Decoder-only Transformer
词表中每个候选 Token 的分数（logits）
   ↓ 选择一个 Token
“好”
   ↓ 把“好”追加到原序列，继续计算
后续 Token，直到满足停止条件
```

上图说明了计算顺序，但还没有说明这些部件在模型结构中的位置。把一次生成拆开，可以得到下面这张模型剖面图：

```text
模型外部                                      Decoder-only LLM 内部

文本“今天天气很”
   ↓
Tokenizer
   ↓ Token ID
   └──────────────────────────────────────→ Token Embedding
                                                ↓
                                          初始隐藏状态
                                                ↓
                                    ┌─────────────────────────┐
                                    │ Transformer Block 1     │
                                    │  Self-Attention + MLP   │
                                    └─────────────────────────┘
                                                ↓
                                    ┌─────────────────────────┐
                                    │ Transformer Block 2     │
                                    │  Self-Attention + MLP   │
                                    └─────────────────────────┘
                                                ↓
                                               ...
                                                ↓
                                    ┌─────────────────────────┐
                                    │ Transformer Block N     │
                                    │  Self-Attention + MLP   │
                                    └─────────────────────────┘
                                                ↓
                                         Final Norm
                                                ↓
                                            LM Head
                                                ↓
模型外部  Token 选择  ←────────────────────── logits
              ↓
          下一个 Token“好”
```

这张图先建立四个位置关系。Tokenizer 把文本变成 ID，通常不属于神经网络的前向计算；Token Embedding 位于模型入口，每个 Token 在进入 Block 堆叠前查表一次；Self-Attention 和 MLP 位于每个 Transformer Block 内，会随着 Block 重复多次；LM Head 位于模型出口，把最终隐藏状态映射为词表 logits。采样或 Greedy 选择读取 logits，但通常由模型服务的生成逻辑执行，不是 Transformer Block 的一部分。

还要区分“Transformer”的两种常见用法。有时它指包含 Embedding、Block 堆叠和 LM Head 的整个模型；更严格地讨论内部结构时，Transformer Block 指中间重复的核心单元。本章后文使用“Block”时，特指图中重复 `N` 次的部分。

位置信息的具体注入点取决于架构。绝对位置编码可以在模型入口与 Token Embedding 结合；RoPE 则通常在每个 Self-Attention 内作用于 Query 和 Key。为了建立心智模型，可以先把它们都理解为“让 Attention 获得顺序信息”，但不能把所有实现都想成入口处的一次向量相加。

训练和推理共用同一个模型，但目的不同：

```text
训练：给出正确后文 → 计算预测误差 → 反向传播 → 修改参数
推理：只给当前前缀 → 计算下一个 Token → 追加结果 → 参数不变
```

接下来的 Token、Embedding、Transformer、Loss 和 KV Cache，都在解释这条主线中的某一步。先记住它们的位置，再理解各自内部机制。

本章以主流文本 LLM 常见的 Decoder-only Transformer 为主。原始 Transformer 是 Encoder–Decoder 架构；BERT 一类模型主要使用 Encoder，T5 一类模型保留 Encoder–Decoder。它们属于同一个架构家族，但任务形式不同。

## 2. 第一步：把文本变成模型能计算的序列

### 2.1 Tokenizer 把文本切成离散单元

神经网络只能计算数字。Tokenizer 先切分文本，再把每个片段映射为词表中的整数 ID。

```text
文本：   “今天天气很”
           ↓ Tokenizer
Token：  [“今天”, “天气”, “很”]       ← 仅为示意
           ↓ 查词表
Token ID：[4182, 9021, 317]
```

Token 不固定等于一个字或一个单词。常见 Tokenizer 使用子词或字节片段：高频片段可能只占一个 Token，生僻词、代码标识符、UUID 或 Base64 则可能被拆成很多 Token。实际数量必须用目标模型的 Tokenizer 计算。

BPE 是常见的子词方法之一。它从较小单元开始，反复合并语料中高频的相邻单元。现代模型也可能使用 Unigram、byte-level BPE 或其他变体；理解“有限词表如何表示开放文本”即可，不要把某种切分结果背成通用规则。

Tokenizer 会直接影响工程成本：

| 现象 | 直接后果 |
|---|---|
| 同一文本在不同模型中被不同方式切分 | 输入长度和费用可能不同 |
| 日志、代码或编码数据被切成很多 Token | 很快占满 Context Window |
| 输入与输出共享有限窗口 | 历史消息和工具结果会挤占生成空间 |
| 消息边界由特殊 Token 表示 | 错误的 Chat Template 会改变模型实际看到的序列 |

### 2.2 Embedding 把编号变成向量

Token ID 只是编号。`9021` 比 `317` 大，不表示语义更多。模型用一个可训练的 Embedding 矩阵把 ID 查成向量：

```text
E ∈ R^(|V| × d)
```

`|V|` 是词表大小，`d` 是隐藏维度。ID 为 `i` 的 Token 取矩阵第 `i` 行，得到向量 `E[i]`。训练会不断调整这些向量，使它们更有利于预测下一个 Token。

回到本章开头的模型剖面图，Embedding 是 Token ID 进入第一个 Transformer Block 之前的入口层。它不是每个 Block 都重新查一次；后续 Block 接收的是上一层产生的 Contextual Representation。

这里要区分两件事：

| 表示 | 何时产生 | 是否随上下文变化 |
|---|---|---|
| Token Embedding | 进入模型时查表得到 | 同一 Token 初始值相同 |
| Contextual Representation | 经过多层 Transformer 后得到 | 会随前后文变化 |

例如，“bank”出现在“river bank”和“bank account”中，初始 Token Embedding 可以相同，经过上下文计算后的表示却可以不同。Embedding 因此只是起点，不是模型对一个词的最终理解。

### 2.3 位置信息让模型知道先后顺序

只有 Token 向量还不够。若没有位置信息，模型无法区分“模型调用工具”和“工具调用模型”。原始 Transformer 把位置编码加入输入；现代 Decoder-only 模型也常使用 RoPE，把位置信息作用到 Attention 的 Query 和 Key 上。

实现方式可以不同，目的相同：让模型知道每个 Token 在哪里，以及不同 Token 相距多远。完成这一步后，长度为 `T` 的输入成为一个向量矩阵：

```text
X ∈ R^(T × d)
```

到这里，“今天天气很”已经从字符串变成了带有顺序的向量序列，但各位置还没有读取上下文。下一步，Transformer 才会把这些局部表示组合起来。

## 3. 第二步：Transformer 根据上下文计算候选分数

Decoder-only Transformer 会重复堆叠多个 Block。每个 Block 都让当前位置读取已有上下文，再加工读到的信息。下面把模型剖面图中的一个 Block 放大。示意图采用一种 Pre-Norm 排列；具体模型可能移动 Normalization、改变子层实现或采用并行分支，因此这张图用于定位主干，不代表所有模型的精确计算图。

```text
来自 Embedding 或上一个 Block 的隐藏状态 x
   │
   ├──────────────────────────────────────┐
   ↓                                      │ 第一条残差路径
Normalization                             │
   ↓                                      │
Causal Self-Attention                     │
   │  ├─ 生成 Query、Key、Value            │
   │  ├─ 注入位置关系（例如 RoPE）          │
   │  └─ Causal Mask 遮住未来位置           │
   ↓                                      │
Residual Add  ←───────────────────────────┘
   ↓ 得到中间状态 h
   │
   ├──────────────────────────────────────┐
   ↓                                      │ 第二条残差路径
Normalization                             │
   ↓                                      │
MLP / FFN                                 │
   ↓                                      │
Residual Add  ←───────────────────────────┘
   ↓
输出隐藏状态，交给下一个 Block 或 Final Norm
```

Self-Attention 因此不是整个模型只执行一次的独立步骤，而是每个 Block 中负责跨 Token 读取信息的子层。MLP 紧随其后，在每个 Token 位置内部加工已经聚合的信息；残差路径则让这两个子层学习对原状态的增量修改。

### 3.1 Self-Attention 决定当前位置读取什么

在这张 Block 图中，Self-Attention 位于第一条残差分支内。它先把每个位置的向量投影成 Query、Key 和 Value：

```text
Q = X × W_Q
K = X × W_K
V = X × W_V
```

可以先用一句不严格但好记的话理解：Query 表示“我在找什么”，Key 表示“我能否匹配这个需求”，Value 表示“匹配后实际提供什么信息”。计算式为：

```text
Attention(Q, K, V) = softmax((Q × K^T) / √d_k + M) × V
```

`Q × K^T` 计算匹配分数，Softmax 把分数转成权重，再对 Value 加权求和。Multi-Head Attention 会并行做多组这类计算，让模型能同时关注不同关系。

Attention Weight 只是一次前向计算中的中间量。模型后面还有 MLP、残差连接和更多 Block，所以它不能单独作为完整解释，更不等于因果证明。

### 3.2 Causal Mask 阻止模型偷看未来

预测“好”时，模型只能使用“今天天气很”，不能提前看到正确答案。Causal Mask 会把未来位置挡住：

```text
              可读取的 Key 位置
Query 位置      1     2     3     4
    1           ✓     ×     ×     ×
    2           ✓     ✓     ×     ×
    3           ✓     ✓     ✓     ×
    4           ✓     ✓     ✓     ✓
```

训练时，完整句子已经在数据中，因此所有位置可以一次并行计算；Causal Mask 又保证每个位置只看左侧。没有它，模型会在训练时偷看答案，部署时却拿不到未来 Token，训练条件和推理条件便不一致。

### 3.3 MLP、残差连接和归一化完成一层变换

Attention 负责跨位置取信息，MLP 负责在每个位置上做非线性变换。残差连接把原表示直接带到下一步，使 Block 学习增量变化；Normalization 用来稳定数值和训练。

现代 LLM 会替换这些部件的具体实现，例如使用 RoPE、RMSNorm、SwiGLU、GQA 或 MoE。它们分别改善位置表示、训练稳定性、表达能力或推理效率，但不改变本章主线：序列表示经过多层变换，最后得到每个候选 Token 的 logits。

到这里，模型已经能为“今天天气很”的下一位置计算一组候选分数，但这些分数是否合理取决于参数。训练要解决的正是“怎样让正确后文获得更高分”。

## 4. 第三步：训练用正确答案修改参数

在模型剖面图中，Loss 和 Optimizer 都不是部署后仍参与前向计算的网络层。训练时，Loss 在模型外比较 logits 与正确 Token，反向传播再沿 LM Head、所有 Transformer Block 和 Embedding 把梯度传回去，Optimizer 据此修改模型参数。

### 4.1 Next-token Loss 衡量预测有多错

给定 Token 序列 `x[1], x[2], ..., x[T]`，自回归模型把整段文本的概率写成：

```text
P(x[1], ..., x[T])
  = P(x[1])
  × P(x[2] | x[1])
  × ...
  × P(x[T] | x[1], ..., x[T-1])
```

训练时，把同一序列错开一位，得到输入和标签：

```text
原始序列： <BOS>  今天天气  很  好  <EOS>
模型输入： <BOS>  今天天气  很  好
监督标签：   今天天气   很  好  <EOS>
```

模型在每个位置预测下一个 Token，再用交叉熵计算真实 Token 与预测分布的差异：

```text
Loss = -Σ_(t=1..T) log P_model(x[t] | x[1], ..., x[t-1])
```

因为训练数据已经包含完整后文，GPU 可以同时计算多个位置。每个位置仍受 Causal Mask 限制，只能看到合法前缀。这种把真实历史作为输入的做法通常称为 Teacher Forcing。

### 4.2 反向传播把误差传回所有参数

```text
Token 序列与标签
   ↓ 前向计算
logits
   ↓ 交叉熵
Loss
   ↓ 反向传播
每个参数的梯度
   ↓ Optimizer Step
更新 Embedding、Attention、MLP 和输出层参数
```

训练并不是把语料原样写入一个可查询数据库。优化器只是在调整大量浮点参数，让正确 Token 在相似前缀下获得更高概率。模型可能记住部分片段，也可能组合出新内容；仅看一次生成结果，通常无法判断它是在回忆、泛化还是猜测。

训练时使用真实前缀，推理时使用模型自己刚生成的前缀。早期生成一旦出错，错误就会进入后续输入并继续累积，这也是自回归生成的基本风险。

### 4.3 不同训练阶段解决不同问题

“训练 LLM”通常包含多个阶段，而不是一次训练完成所有目标。

| 阶段 | 主要目的 | 不能保证什么 |
|---|---|---|
| Pretraining | 从大规模语料学习语言、知识和通用模式 | 稳定遵循用户指令 |
| Continued Pretraining | 适应领域语料和术语 | 自动学会任务格式和安全边界 |
| Supervised Fine-Tuning | 用理想回答示范指令遵循 | 输出偏好一定合理 |
| Preference Optimization | 让输出更符合人类或产品偏好 | 事实和推理永远正确 |
| Reasoning-focused Training | 改善复杂任务中的中间计算 | 所有任务都值得增加推理成本 |

RLHF 通常先从人类比较数据中学习奖励信号，再优化模型；DPO 则直接用偏好对优化模型。二者是不同方法，都不能把行为倾向变成事实保证或权限控制。

对 Agent 开发者，关键是识别模型类型。Base Model 更接近文本续写器；Instruction Model 更适合遵循消息和工具格式；Reasoning Model 可能在复杂任务上使用更多推理计算。名字相近的模型，训练目标和行为也可能不同。

到这里，训练数据已经通过 Loss 和梯度改变了模型参数。部署后的模型不再拿正确后文修改自己，而是冻结这些参数，用当前前缀真正生成未知的后续 Token。

## 5. 第四步：推理冻结参数并逐 Token 生成

推理没有标签、Loss、反向传播和参数更新。模型先计算“今天天气很”之后的 logits，选出“好”，再把“好”追加到前缀中，继续预测下一个 Token。

```text
前缀：“今天天气很”
   ↓ 前向计算
P(下一个 Token | 当前前缀)
   ↓ 选择“好”
新前缀：“今天天气很好”
   ↓ 再次计算
继续生成，直到 EOS、Stop Sequence、长度上限或外部取消
```

### 5.1 Prefill 处理输入，Decode 逐步生成

| 阶段 | 处理什么 | 计算特征 | 主要影响 |
|---|---|---|---|
| Prefill | 一次处理全部输入 Token | 输入位置可并行 | 首 Token 延迟 |
| Decode | 每一步处理一个新 Token | 生成步骤前后依赖 | 输出速度和总耗时 |

长 Prompt 增加 Prefill 工作；长回答增加 Decode 步数。Agent 每执行一次工具再调用模型，通常会开启新一轮推理，所以长 Context 和多轮循环会同时放大延迟与费用。

### 5.2 KV Cache 避免重复计算历史前缀

每层 Attention 都会为历史 Token 计算 Key 和 Value。生成新 Token 时，历史位置的 Key 和 Value 没有变化，可以缓存起来。

放回模型剖面图，KV Cache 不是夹在两个 Block 之间的新网络层，而是每个 Block 的 Self-Attention 在推理期间保存的一份运行时状态。模型有 `N` 个 Block，就会在对应层分别保存和读取 Key、Value；这些缓存不是训练得到的模型参数，也不是应用的长期 Memory。

```text
没有 KV Cache：每一步重新计算整个历史前缀

使用 KV Cache：
Prefill  计算并保存 KV[今天天气很]
Step 1   只计算“好”，再保存 KV[好]
Step 2   只计算下一个新 Token
```

KV Cache 用显存换速度。它会随层数、上下文长度、KV Head 数、Head Dimension 和并发请求数增长。新 Query 仍要读取历史缓存，因此长上下文并不会变成零成本。MQA 和 GQA 通过减少 KV Head 数降低这部分压力。

### 5.3 logits 和采样决定下一步选哪个 Token

LM Head 为词表中的每个候选 Token 生成一个 logit。Softmax 把 logits 变成概率：

```text
P(x[i]) = exp(z[i] / temperature)
          / Σ_j exp(z[j] / temperature)
```

`temperature` 是 Temperature 参数。较低 Temperature 让分布更集中，较高 Temperature 让候选更分散。它只改变选择方式，不会检查答案是否正确。

| 策略 | 怎样选择 | 主要取舍 |
|---|---|---|
| Greedy | 选择概率最高的 Token | 波动小，但不保证整段最优 |
| Temperature Sampling | 按调整后的分布采样 | 更多样，也更不稳定 |
| Top-k | 只在概率最高的 k 个候选中选择 | 简单，但固定 k 不适应分布形状 |
| Top-p | 保留累计概率达到 p 的候选集 | 候选范围更自适应，仍有随机性 |

因此，Temperature 低不等于事实正确。若最高概率候选本来就是错的，Greedy 只会更稳定地选中它。

至此，“今天天气很”经过 Prefill 得到首个候选分布，模型选出“好”并把它加入前缀，再进入下一次 Decode。训练与推理的共同计算骨架和关键差异已经接上了。

## 6. 第五步：Prompt 改变本次计算，但不会在线训练模型

### 6.1 In-context Learning 改变的是当前 Context

Prompt 中的指令和示例会改变输入 Token 序列，从而改变模型当前的隐藏状态和输出分布。参数没有更新，但模型可以临时表现出某种任务模式，这称为 In-context Learning。

| 方式 | 当前 Prompt 中提供什么 | 是否更新参数 |
|---|---|---:|
| Zero-shot | 只有任务指令 | 否 |
| One-shot | 一个输入—输出示例 | 否 |
| Few-shot | 少量示例 | 否 |
| Fine-tuning | 离线训练数据 | 是 |

这解释了为什么 Few-shot 示例只在当前可见 Context 中生效。换一个没有这些示例的请求，模型不会自动保留刚才学到的格式。

### 6.2 Chain-of-Thought 增加中间计算 Token

Chain-of-Thought（CoT）让模型先生成中间步骤，再生成答案：

```text
直接回答：问题 → 答案

CoT：问题 → 中间步骤 1 → 中间步骤 2 → 答案
                     ↑ 后续 Token 可以读取前面的中间结果
```

它有时能改善复杂任务，因为模型获得了更多步骤来分解问题。但中间步骤仍是模型生成的 Token：第一步出错，后面可能得到一段流畅、自洽却错误的解释。简单任务强制长推理，还会增加延迟、费用和格式偏离。

Reasoning Model 通常还经过面向推理行为的训练，并可能按任务投入更多测试时计算。它和 CoT 有关，但不等同。无论内部推理多长，数学结果仍应计算验证，代码仍应运行测试，外部事实仍应查证。

模型内部推理也不应充当 Agent 审计日志。系统应记录可观察的输入、Tool Call、工具结果、状态变化和最终输出。ReAct 会在第 04 章作为 Agent Loop 的控制方式讨论，不属于 Transformer 的内部结构。

## 7. 从生成机制推导 Agent 工程边界

LLM 的能力和局限来自同一机制：它根据当前可见前缀生成下一个 Token。下面这些边界不是额外规定，而是可以从前面的计算过程直接推出。

### 7.1 参数知识不是数据库

训练把统计规律压入参数，却没有提供稳定的“记录 ID → 事实值”查询接口。模型可能混合相似实体、使用过时信息或补出不存在的细节。需要时效性、引用或权限过滤时，应连接外部数据源或 Retrieval。

### 7.2 Context Window 不是长期 Memory

Context Window 只是一次推理可见的 Token 容量。文本能放进去，不代表模型会同等重视每一处信息，也不代表应用有权提供这些信息。长期 Memory 还需要持久化、检索、更新、权限和删除策略。

### 7.3 Hallucination 不能靠一个参数关闭

模型的目标是继续生成高概率 Token，而不是先查询真值判定器。当 Context 缺少证据、问题含错误前提或模型判断失准时，它仍可能生成流畅但错误的内容。降低 Temperature 只能减少随机分支，不能完成事实验证。

### 7.4 对齐不等于授权

指令微调和偏好优化会改变模型的行为倾向，但模型仍然只是在处理 Token。身份、权限、预算和高风险副作用必须由 Runtime 中的确定性代码控制。

### 7.5 调试时沿计算链逐层定位

```text
原始输入是否正确？
   ↓
Tokenizer / Chat Template 是否符合预期？
   ↓
关键指令和证据是否位于可见 Context？
   ↓
模型类型是否适合任务？
   ↓
采样参数是否带来过大波动？
   ↓
结果是否被长度或停止条件截断？
   ↓
Runtime 是否验证了结构、事实和工具副作用？
```

只改 Prompt 不能修复所有层。输入被截断要修 Context；模型缺少最新事实要接入数据源；输出格式不稳定要做结构化约束和校验；工具参数即使语法正确，也要由业务规则验证。

| 模型机制 | Agent 中的直接后果 |
|---|---|
| Tokenizer 决定序列长度 | Context 预算应按 Token 管理，工具输出需要裁剪 |
| 模型只看当前可见 Token | 未写入 Context 的 State 对模型不可见 |
| Decode 逐 Token 串行 | 输出越长、循环越多，延迟和费用越高 |
| logits 只是候选分数 | Tool Call 可能选错工具或生成无效参数，必须校验 |
| In-context Learning 不改参数 | Few-shot 示例不会永久教会模型 |
| 对齐只改变行为倾向 | “模型通常会拒绝”不能作为安全边界 |

## 学习检查

读完本章后，应当能够：

- 从文本开始，画出 Token、Embedding、Transformer、logits、Loss 和生成结果之间的完整因果链；
- 解释 Self-Attention、Causal Mask、MLP 在 Decoder-only Transformer 中各自解决什么问题；
- 说明 next-token labels 为什么要与输入错开一位，以及反向传播如何修改参数；
- 区分 Pretraining、Supervised Fine-Tuning、Preference Optimization 和推理；
- 解释 Prefill、Decode 与 KV Cache 的性能关系；
- 区分 logits、概率、Temperature、Top-k 和 Top-p，不把低随机性等同于正确性；
- 说明 In-context Learning、Chain-of-Thought 和 Fine-tuning 是否更新参数；
- 从生成机制推导 Agent 为什么仍需要外部知识、结果校验、Evals 和 Runtime 安全控制。

## 参考资料与结论对应关系

- [Neural Machine Translation of Rare Words with Subword Units](https://arxiv.org/abs/1508.07909)，Sennrich、Haddow 与 Birch，用于核对子词单元和 BPE 表示罕见词的原始机制，最后核验日期：2026-07-22。
- [Attention Is All You Need](https://arxiv.org/abs/1706.03762)，Vaswani 等，用于核对原始 Encoder–Decoder Transformer、Scaled Dot-Product Attention、Multi-Head Attention、位置编码、残差连接、前馈网络与自回归掩码，最后核验日期：2026-07-22。
- [RoFormer: Enhanced Transformer with Rotary Position Embedding](https://arxiv.org/abs/2104.09864)，Su 等，用于核对 RoPE 将位置信息作用于 Query 和 Key 的机制，最后核验日期：2026-07-22。
- [GLU Variants Improve Transformer](https://arxiv.org/abs/2002.05202)，Shazeer，用于核对 SwiGLU 等门控前馈层相对原始 ReLU FFN 的架构演化，最后核验日期：2026-07-22。
- [GQA: Training Generalized Multi-Query Transformer Models from Multi-Head Checkpoints](https://arxiv.org/abs/2305.13245)，Ainslie 等，用于核对 MQA/GQA 减少 Key-Value Head、在质量与推理效率之间取舍的机制，最后核验日期：2026-07-22。
- [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165)，Brown 等，用于核对不更新参数、仅通过指令和少量示例完成任务的 In-context Learning 现象，最后核验日期：2026-07-22。
- [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155)，Ouyang 等，用于核对监督示范、奖励模型和 RLHF 在指令对齐中的不同阶段，最后核验日期：2026-07-22。
- [Direct Preference Optimization: Your Language Model is Secretly a Reward Model](https://arxiv.org/abs/2305.18290)，Rafailov 等，用于核对 DPO 直接使用偏好数据优化语言模型的核心区别，最后核验日期：2026-07-22。
- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903)，Wei 等，用于核对带中间推理步骤的示例可改善部分推理任务的实验结论，最后核验日期：2026-07-22。
- [Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters](https://arxiv.org/abs/2408.03314)，Snell 等，用于核对测试时计算的效果取决于问题难度，增加推理计算并非无条件有效，最后核验日期：2026-07-22。
- [Training Compute-Optimal Large Language Models](https://arxiv.org/abs/2203.15556)，Hoffmann 等，用于核对固定训练计算预算下参数量与训练 Token 数需要共同权衡，最后核验日期：2026-07-22。
- [Caching](https://huggingface.co/docs/transformers/main/cache_explanation)，Hugging Face Transformers 官方文档，用于核对自回归推理中 KV Cache 保存历史 Key/Value、避免重复计算的机制，最后核验日期：2026-07-22。
