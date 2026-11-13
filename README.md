# Godot AI 学习文章

每天自动生成一篇 **Godot AI 编程** 学习文章，并归档到本仓库。

- 文章目录：[`articles/`](articles/)
- 去重索引：[`INDEX.md`](INDEX.md)
- 自动化脚本：[`scripts/godot_ai_daily.py`](scripts/godot_ai_daily.py)

选题覆盖方向：行为树 / 状态机、寻路（NavigationAgent）、群体行为（Boids、Flocking）、
程序化生成（PCG）、强化学习 / 机器学习插件、LLM 与生成式 AI 集成、敌人 AI 等。
每次选题都会与历史文章做关键词、来源 URL、核心内容三重去重。

## 文章统计

- 累计文章：**2** 篇
- 最新更新：**2026-11-13**
- 文章文件数：**2** 个

## 最新文章

| 日期 | 标题 | 主题关键词 | 文件 |
|---|---|---|---|
| 2026-11-13 | Godot 群体行为 AI：用 Boids（鸟群算法）实现鸟群/鱼群模拟 | boids, flocking, 群体行为, separation, alignment, cohesion, steering, 转向力, 人工生命 | [articles/2026-11-13-godot-boids-flocking.md](articles/2026-11-13-godot-boids-flocking.md) |
| 2026-11-06 | 用行为树（Behavior Tree）设计 Godot AI：从原理到实战 | behavior tree, 行为树, Sequence, Selector, Leaf, Blackboard, 敌人AI | [articles/2026-11-06-godot-behavior-tree-ai.md](articles/2026-11-06-godot-behavior-tree-ai.md) |

## 自动化说明

每日定时任务执行 `scripts/godot_ai_daily.py`：

1. `prepare` —— 校验凭证、同步仓库、输出去重所需的历史索引；
2. 选题去重 —— 关键词、来源 URL、核心内容三重比对，重复则换方向重新检索；
3. `publish` —— 归档文章到 `articles/YYYY-MM-DD-slug.md`、追加 `INDEX.md`、**重建本 README**、提交并推送到 `main`。

> 本 README 由脚本根据 `INDEX.md` 自动生成，请勿手动编辑。
