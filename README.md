# AI Agent 全景知识库

一套面向有 CS 或后端基础、希望转向 AI Agent 并准备求职的读者的中文知识库，用于系统、全面地学习核心机制、工程边界与面试知识。

第 00 章作为全书 Overview，直接建立 Agent 系统骨架；第 01 章起采用“前部面试速记、后部完整教材”的双层结构。面试速记包含覆盖知识主干的背诵提纲、按需添加的高频对比，以及 3～5 个沿核心机制深入且附带回答要点的追问。项目提供面试速查、系统学习和实践验证三条阅读路线，三条路线共享同一套正文。

第一次学习应先阅读全局知识地图和第 00 章，在完整 Agent 系统骨架上定位后续概念，再按 `SUMMARY.md` 的能力递增顺序逐章学习。

## 文档入口

| 文档 | 作用 |
|---|---|
| [学习线路](docs/LEARNING_PATH.md) | 项目的知识范围和资料入口 |
| [全局知识地图](docs/KNOWLEDGE_MAP.md) | Agent 系统骨架、组件关系和跨章节依赖 |
| [项目说明](docs/PROJECT.md) | 项目目标、内容边界、工作流和交付标准 |
| [内容架构](docs/CONTENT_ARCHITECTURE.md) | 信息层级、阅读路线和第一部分目标结构 |
| [内容规范](docs/CONTENT_SPEC.md) | 双层文章结构与正文质量要求 |
| [知识库目录](SUMMARY.md) | 章节划分和正文导航 |
| [生成 Prompt](PROMPT.md) | 让 AI 检索资料并生成 Markdown 初稿 |
| [Agent 协作规范](AGENTS.md) | AI 在仓库内新增和修改内容时必须遵守的规则 |
| [更新记录](CHANGELOG.md) | 记录结构、内容和资料更新 |

## 项目目录

```text
ai-agent-handbook/
├── README.md
├── SUMMARY.md
├── PROMPT.md
├── AGENTS.md
├── CHANGELOG.md
├── docs/
│   ├── PROJECT.md
│   ├── KNOWLEDGE_MAP.md
│   ├── CONTENT_ARCHITECTURE.md
│   ├── CONTENT_SPEC.md
│   └── LEARNING_PATH.md
├── chapters/        # 正文与待审核初稿
│   ├── 0-overview/
│   │   └── 00｜AI Agent 系统全景与学习地图.md
│   ├── 1-llm-foundations/
│   │   ├── 01｜LLM 的训练与推理.md
│   │   ├── 02｜模型 API 与推理工程.md
│   │   └── 03｜Prompt 与输出控制.md
│   └── ...          # 后续篇目录继续使用全书连续正文编号
├── research/        # 检索过程与研究笔记
├── sources/         # 来源索引
├── examples/        # 可运行代码
└── assets/          # 图片和架构图
```

## 工作流

```text
学习线路确定范围，SUMMARY.md 确定严格编写顺序
→ AI 检索并生成 research/
→ AI 生成 chapters/ Markdown 初稿
→ 人工审核事实、引用与代码
→ 发布到语雀
→ 将语雀中的修改同步回仓库
```

**本地/GitHub Markdown 是唯一内容源，语雀是发布端。**
