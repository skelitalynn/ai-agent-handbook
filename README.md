# AI Agent 全景知识库

一套面向已有 AI Agent 基础的求职者的中文知识库，用于系统、全面地梳理核心机制、工程边界与面试知识。

每篇正文提供两种阅读方式：时间紧时可以只读简短且可独立成立的“面试回答”和追问；需要系统理解时，再继续阅读工作原理、最小实现和工程实践。工程实践与代码用于解释和验证知识，不构成独立教学主线。

## 文档入口

| 文档 | 作用 |
|---|---|
| [学习线路](docs/LEARNING_PATH.md) | 项目的知识范围和资料入口 |
| [项目说明](docs/PROJECT.md) | 项目目标、内容边界、工作流和交付标准 |
| [内容规范](docs/CONTENT_SPEC.md) | 单篇知识文档的固定结构与写作要求 |
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
│   ├── CONTENT_SPEC.md
│   └── LEARNING_PATH.md
├── chapters/        # 面向读者的正文与待审核初稿
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
