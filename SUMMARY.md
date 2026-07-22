# AI Agent 全景知识库目录

> 本文件是正式教材目录和严格学习顺序。具体知识范围与资料入口见 [学习线路](docs/LEARNING_PATH.md)，组件关系和跨章节依赖见 [全局知识地图](docs/KNOWLEDGE_MAP.md)。正文按照能力递增顺序编写：先建立完整 Agent 骨架，再逐层增加模型调用、行动、状态、知识、协作和生产能力。

## 骨架章节

- [00｜AI Agent 系统全景与学习地图](<chapters/0-overview/00｜AI Agent 系统全景与学习地图.md>)

读者先在一个最小 Agent 中看到 Model、Tool、State、Context、Runtime、Environment、Evals 和 Trace 的完整关系。后续章节分别深入这些组件。

## 第一篇｜模型如何完成一次受控生成

- [01｜LLM 的训练与推理](<chapters/1-llm-foundations/01｜LLM 的训练与推理.md>)
- [02｜模型 API 与推理工程](<chapters/1-llm-foundations/02｜模型 API 与推理工程.md>)
- [03｜Prompt 与输出控制](<chapters/1-llm-foundations/03｜Prompt 与输出控制.md>)

阶段成果：理解从文本到模型输出的完整计算链，并实现能够处理类型化结果、Usage、停止原因和输出验证的模型客户端。

## 第二篇｜模型调用如何形成 Agent 闭环

- [04｜Agent Loop 与 ReAct](<chapters/2-agent-core/04｜Agent Loop 与 ReAct.md>)
- [05｜Tool Engineering](<chapters/2-agent-core/05｜Tool Engineering.md>)
- [06｜State、Session 与 Checkpoint](<chapters/2-agent-core/06｜State、Session 与 Checkpoint.md>)
- [07｜Context Engineering](<chapters/2-agent-core/07｜Context Engineering.md>)

阶段成果：实现具有工具参数校验、明确终止条件、可恢复状态和上下文预算的单 Agent。

## 第三篇｜如何判断 Agent 是否有效

- [08｜Agent Evals](<chapters/3-evaluation-observability/08｜Agent Evals.md>)
- [09｜Tracing 与 Observability](<chapters/3-evaluation-observability/09｜Tracing 与 Observability.md>)

阶段成果：建立任务测试集、评分规则和完整 Run Trace，使后续能力扩展都可以回归和定位。

## 第四篇｜Agent 如何获得外部知识与长期信息

- [10｜Retrieval、RAG 与 Agentic Search](<chapters/4-knowledge-memory/10｜Retrieval、RAG 与 Agentic Search.md>)
- [11｜Memory](<chapters/4-knowledge-memory/11｜Memory.md>)

阶段成果：实现具有数据摄取、权限过滤、引用和评测的知识型 Agent，并为长期信息建立写入、更新、召回和删除策略。

## 第五篇｜Agent 如何处理复杂任务与协作

- [12｜Planning、Reasoning 与决策控制](<chapters/5-control-collaboration/12｜Planning、Reasoning 与决策控制.md>)
- [13｜Workflow 与 Orchestration](<chapters/5-control-collaboration/13｜Workflow 与 Orchestration.md>)
- [14｜Human-Agent Interaction](<chapters/5-control-collaboration/14｜Human-Agent Interaction.md>)
- [15｜Multi-Agent Systems](<chapters/5-control-collaboration/15｜Multi-Agent Systems.md>)

阶段成果：能够根据任务确定性、失败代价、暂停恢复和并行需求，选择普通代码、Workflow、单 Agent、人工介入或 Multi-Agent。

## 第六篇｜Agent 如何运行、扩展和互操作

- [16｜Runtime 与 Harness](<chapters/6-runtime-extensions/16｜Runtime 与 Harness.md>)
- [17｜Agent Framework](<chapters/6-runtime-extensions/17｜Agent Framework.md>)
- [18｜MCP](<chapters/6-runtime-extensions/18｜MCP.md>)
- [19｜Skills 与扩展机制](<chapters/6-runtime-extensions/19｜Skills 与扩展机制.md>)
- [20｜Agent 间通信与 A2A](<chapters/6-runtime-extensions/20｜Agent 间通信与 A2A.md>)

阶段成果：理解框架背后的运行时职责，并判断普通 API、MCP、Skill、插件和 A2A 分别应该解决什么问题。

## 第七篇｜Agent 产品与交互形态

- [21｜Agent 应用架构模式](<chapters/7-agent-products/21｜Agent 应用架构模式.md>)
- [22｜Multimodal、Realtime 与 Computer Use](<chapters/7-agent-products/22｜Multimodal、Realtime 与 Computer Use.md>)

阶段成果：把前述组件组合成可交互产品，并处理事件流、用户打断、多模态上下文和环境操作。

## 第八篇｜质量、安全与生产

- [23｜Agent Reliability Engineering](<chapters/8-production/23｜Agent Reliability Engineering.md>)
- [24｜Agent Security](<chapters/8-production/24｜Agent Security.md>)
- [25｜生产基础设施与部署](<chapters/8-production/25｜生产基础设施与部署.md>)

阶段成果：为 Agent 建立超时、重试、幂等、恢复、权限、隔离、审计、容量、成本和发布机制。

## 附录

- [附录 A｜Fine-tuning](<chapters/appendix/A｜Fine-tuning.md>)
- [附录 B｜贯穿式实践项目](<chapters/appendix/B｜贯穿式实践项目.md>)
- [附录 C｜术语索引](<chapters/appendix/C｜术语索引.md>)
- [附录 D｜参考资料索引](<chapters/appendix/D｜参考资料索引.md>)

## 编写状态说明

目录表示目标知识结构，不表示对应正文已经完成或发布。新增、删除、移动文章时必须同步更新本文件；章节只有在研究、正文、示例、事实核验、代码核验和人工审核均完成后，才能进入发布流程。
