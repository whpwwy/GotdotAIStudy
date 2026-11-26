# Godot AI 学习文章

每天自动生成一篇 **Godot AI 编程** 学习文章，并归档到本仓库。

- 文章目录：[`articles/`](articles/)
- 去重索引：[`INDEX.md`](INDEX.md)
- 自动化脚本：[`scripts/godot_ai_daily.py`](scripts/godot_ai_daily.py)

选题覆盖方向：行为树 / 状态机、寻路（NavigationAgent）、群体行为（Boids、Flocking）、
程序化生成（PCG）、强化学习 / 机器学习插件、LLM 与生成式 AI 集成、敌人 AI 等。
每次选题都会与历史文章做关键词、来源 URL、核心内容三重去重。

## 文章统计

- 累计文章：**17** 篇
- 最新更新：**2026-11-27**
- 文章文件数：**17** 个

## 最新文章

| 日期 | 标题 | 主题关键词 | 文件 |
|---|---|---|---|
| 2026-11-27 | Godot 4 对抗搜索实战：用 Negamax 与 Alpha-Beta 剪枝打造四子棋 AI | Minimax, Negamax, Alpha-Beta Pruning, 对抗搜索, 极大极小, 四子棋, Connect Four, 着法排序, 深度限制 | articles/2026-11-27-godot-negamax-alpha-beta-connect-four.md |
| 2026-11-26 | Godot 4 机器学习插件实战：把训练好的神经网络装进游戏做实时推理 | 机器学习插件, 神经网络推理, ONNX Runtime, ncnn, GDScript MLP, 前向传播, 模型部署 | articles/2026-11-26-godot-ml-plugin-neural-inference.md |
| 2026-11-25 | Godot 4 流场寻路（Flow Field Pathfinding）实战：让上千个单位共享同一条路 | Flow Field, 流场寻路, Integration Field, Dijkstra Map, 向量场, RTS, 群体寻路, Pathfinding | articles/2026-11-25-godot-flow-field-pathfinding.md |
| 2026-11-24 | Godot 4 分层任务网络实战：用 HTN 让敌人自己拆解行动序列 | HTN, 分层任务网络, Hierarchical Task Network, compound task, primitive task, method, 任务分解, 回滚 rollback | articles/2026-11-24-godot-htn-hierarchical-task-network.md |
| 2026-11-23 | Godot 4 蒙特卡洛树搜索实战：用 MCTS 打造会思考的井字棋对手 | 蒙特卡洛树搜索, Monte Carlo Tree Search, MCTS, UCT, UCB1, 随机模拟, 选择扩展回传, 回合制 AI, 井字棋 | articles/2026-11-23-godot-mcts-tic-tac-toe.md |
| 2026-11-22 | Godot 4 遗传算法实战：用选择、交叉与变异进化敌人 AI | 遗传算法, Genetic Algorithm, 进化计算, 适应度函数, 锦标赛选择, 均匀交叉, 高斯变异, 精英保留 | articles/2026-11-22-godot-genetic-algorithm-enemy-ai.md |
| 2026-11-21 | Godot 4 影响图（Influence Map）实战：给网格装上战术危险感 | Influence Map, 影响图, 战术 AI, 危险场, 空间推理, AStarGrid2D, 影响传播, 权重寻路 | articles/2026-11-21-godot-influence-maps-tactical-ai.md |
| 2026-11-20 | Godot 4 敌人感知系统实战：视野锥、视线遮挡与听觉怀疑度 | AI 感知系统, Perception System, 视野锥, FOV, 点积视角判定, 视线遮挡, RayCast3D, 听觉感知, 怀疑度, suspicion | articles/2026-11-20-godot-enemy-perception-fov.md |
| 2026-11-19 | Godot 4 PCG 实战：用 Wave Function Collapse 与噪声生成程序化地牢 | PCG, 程序化生成, Wave Function Collapse, WFC, 约束传播, 熵最小化, FastNoiseLite, 种子随机, TileMapLayer, 程序化地牢 | articles/2026-11-19-godot-pcg-wfc-procedural-generation.md |
| 2026-11-18 | Godot 4 强化学习入门：用 Q-Learning 训练一个会自己学追人的敌人 | 强化学习, Reinforcement Learning, Q-Learning, Q表, Bellman方程, epsilon-greedy, 奖励函数, 马尔可夫决策过程 | articles/2026-11-18-godot-q-learning-reinforcement.md |
| 2026-11-17 | Godot 4 Utility AI 实战：用效用评分与响应曲线让敌人自己权衡行动 | Utility AI, 效用AI, 考量项, Consideration, 响应曲线, Response Curve, 补偿因子, 行为评分, 决策惯性 | articles/2026-11-17-godot-utility-ai.md |
| 2026-11-16 | Godot 4 GOAP 实战：让敌人自己「想」出行动序列 | GOAP, Goal-Oriented Action Planning, STRIPS, 目标导向行动规划, 行动规划, 前置条件, 世界状态, 重规划, A*规划 | articles/2026-11-16-godot-goap-ai-planner.md |
| 2026-11-15 | Godot 4 接入大语言模型：用 HTTPRequest 打造有记忆的 NPC 对话 | LLM, 大语言模型, HTTPRequest, NPC 对话, 生成式 AI, OpenAI API, 上下文记忆, Chat Completions | articles/2026-11-15-godot-llm-npc-dialogue.md |
| 2026-11-14 | Godot AI 有限状态机：用 enter/exit 与历史状态实现可中断 AI | finite state machine, state machine, FSM, 有限状态机, enter/exit, 状态转换, 中断恢复 | articles/2026-11-14-godot-interruptible-fsm.md |
| 2026-11-13 | Godot 群体行为 AI：用 Boids（鸟群算法）实现鸟群/鱼群模拟 | boids, flocking, 群体行为, separation, alignment, cohesion, steering, 转向力, 人工生命 | [articles/2026-11-13-godot-boids-flocking.md](articles/2026-11-13-godot-boids-flocking.md) |
| 2026-11-13 | Godot 2D 寻路 AI：用 NavigationAgent2D 实现路径跟随与点击移动 | NavigationAgent2D, NavigationRegion2D, NavigationPolygon, 2D寻路, 路径跟随, target_position | articles/2026-11-13-godot-navigationagent2d-pathfinding.md |
| 2026-11-06 | 用行为树（Behavior Tree）设计 Godot AI：从原理到实战 | behavior tree, 行为树, Sequence, Selector, Leaf, Blackboard, 敌人AI | [articles/2026-11-06-godot-behavior-tree-ai.md](articles/2026-11-06-godot-behavior-tree-ai.md) |

## 自动化说明

每日定时任务执行 `scripts/godot_ai_daily.py`：

1. `prepare` —— 校验凭证、同步仓库、输出去重所需的历史索引；
2. 选题去重 —— 关键词、来源 URL、核心内容三重比对，重复则换方向重新检索；
3. `publish` —— 归档文章到 `articles/YYYY-MM-DD-slug.md`、追加 `INDEX.md`、**重建本 README**、提交并推送到 `main`。

> 本 README 由脚本根据 `INDEX.md` 自动生成，请勿手动编辑。
