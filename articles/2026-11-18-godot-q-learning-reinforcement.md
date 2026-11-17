# Godot 4 强化学习入门：用 Q-Learning 训练一个会自己学追人的敌人

- **日期**：2026-11-18（Asia/Shanghai）
- **引擎版本**：Godot 4.x（GDScript）
- **难度**：进阶（需要了解节点、`_process`、`_draw`）
- **主题关键词**：强化学习、Reinforcement Learning、Q-Learning、Q 表、Bellman 方程、epsilon-greedy、奖励函数、马尔可夫决策过程

> 本文与历史文章的边界：此前已经覆盖了行为树、状态机、NavigationAgent 寻路、Boids 群体行为、GOAP、Utility AI 和 LLM 对话。这些都属于「规则/规划驱动」的 AI；本篇换成**学习驱动**——不写任何追击逻辑，让敌人通过试错自己学出策略。文中不重复寻路 API 与行为树写法。

---

## 一、为什么游戏 AI 需要强化学习

传统游戏 AI 的思路是「人把策略写出来」：

- 行为树：人设计节点与优先级；
- 状态机：人设计状态与转换条件；
- GOAP / Utility AI：人设计行动、前置条件与评分曲线。

强化学习（Reinforcement Learning，RL）换了一个方向：**人只定义状态、动作和奖励，策略由智能体自己试错得到**。这适合那些「规则很难写清、但好坏容易判断」的场景，例如：

- 敌人如何在掩体之间走位；
- NPC 如何学会资源采集与风险规避；
- 赛车 AI 如何学会过弯；
- 关卡机器人如何自动探索地图。

代价是：训练需要时间，行为可解释性弱，奖励设计（reward shaping）非常关键。因此工业界常见做法是**规则 AI 打底，强化学习做局部增强**，而不是全部替换。

---

## 二、核心概念：把游戏变成 MDP

Q-Learning 把问题抽象成**马尔可夫决策过程**（MDP），由五元组描述：

| 概念 | 含义 | 在本文示例中的对应 |
|---|---|---|
| 状态 State `s` | 智能体感知到的局面 | 敌人与目标的相对位置 + 四周是否有墙 |
| 动作 Action `a` | 智能体可执行的操作 | 上 / 下 / 左 / 右移动一格 |
| 奖励 Reward `r` | 动作的即时好坏 | 抓到目标 +10，撞墙 -1，每步 -0.02 |
| 转移 Transition | 执行动作后到达的新状态 | 网格移动后的新位置 |
| 折扣因子 `γ` | 未来奖励的权重（0~1） | 0.95，越接近 1 越「有远见」 |

### 2.1 Q 值是什么

`Q(s, a)` 表示「在状态 s 下执行动作 a，之后一直按最优策略行动，能拿到的**累计折扣奖励**的期望」。

Q-Learning 的核心更新公式（Bellman 最优方程的时间差分形式）：

```
Q(s, a) ← Q(s, a) + α · [ r + γ · max Q(s', a') − Q(s, a) ]
```

- `α`（学习率）：新经验覆盖旧估计的幅度；
- `r + γ · max Q(s', a')`：本次的「目标值」（TD target）；
- 方括号内是 TD 误差，误差越大，更新越多。

当 `s'` 是终止状态时，目标值退化为 `r`，不再加未来项。

### 2.2 探索与利用：epsilon-greedy

只按当前 Q 值选最大动作，会永远困在早期偶然发现的策略里。常用做法是 **ε-greedy**：

- 以概率 `ε` 随机选动作（探索）；
- 以概率 `1 − ε` 选 Q 值最大的动作（利用）。

训练初期 `ε` 接近 1，后期逐步衰减到接近 0，让策略从「乱试」过渡到「稳定执行」。

### 2.3 表格法 vs 深度强化学习

| 路线 | 代表 | 优点 | 缺点 |
|---|---|---|---|
| 表格型 Q-Learning | 本文手写实现 | 无依赖、可读、可嵌入游戏运行时 | 状态必须离散，状态多时会爆炸 |
| 深度 RL | [Godot RL Agents](https://pypi.org/project/godot-rl/) + Stable Baselines3 / RLlib | 可处理像素、连续动作、复杂 3D 场景 | 需要 Python 环境与较长训练 |

本文先用手写表格法把概念跑通；文末再说明如何接入 Godot RL Agents。

---

## 三、实战：单文件可运行的 Q-Learning 敌人

### 3.1 场景搭建（30 秒）

1. 新建 Godot 4 项目；
2. 新建 2D 场景，根节点用 `Node2D`；
3. 新建脚本 `q_learning_demo.gd`，把下面完整代码贴进去并挂到根节点；
4. 直接 F5 运行。

运行后，脚本会先在内存里训练几千个回合，然后进入演示模式：蓝点（敌人）用学到的贪心策略实时追红点（目标），红点被抓到后会随机换位置。没有贴图、没有外部依赖，所有内容都由 `_draw()` 绘制。

### 3.2 完整代码

```gdscript
extends Node2D
## 单文件表格型 Q-Learning 演示（Godot 4.x）
## 用法：新建 2D 场景，根节点挂本脚本，直接运行。

# ---------------- 网格与环境 ----------------
const CELL := 48
const GRID := Vector2i(12, 8)
const ACTIONS := [
	Vector2i(1, 0),   # 0 右
	Vector2i(-1, 0),  # 1 左
	Vector2i(0, 1),   # 2 下
	Vector2i(0, -1),  # 3 上
]

# ---------------- 超参数 ----------------
const EPISODES := 4000      # 训练回合数
const MAX_STEPS := 80       # 单回合最大步数，防止死循环
const ALPHA := 0.15         # 学习率
const GAMMA := 0.95         # 折扣因子
const EPS_START := 1.0      # 初始探索率
const EPS_MIN := 0.02       # 最小探索率
const EPS_DECAY := 0.999    # 每个回合衰减一次
const STEP_PENALTY := -0.02 # 每走一步的惩罚
const WALL_PENALTY := -1.0  # 撞墙惩罚
const GOAL_REWARD := 10.0   # 抓到目标的奖励
const DEMO_INTERVAL := 0.10 # 演示模式下每步间隔（秒）

var q_table: Dictionary = {}          # key: String -> value: Array[4]
var walls: Dictionary = {}            # Vector2i -> true
var agent_cell := Vector2i(1, 1)
var target_cell := Vector2i(10, 6)
var demo_timer := 0.0
var demo_episode := 0
var trained_ms := 0


func _ready() -> void:
	randomize()
	_build_walls()
	_reset_episode()
	train()
	_reset_episode()
	print("训练完成：%d 回合，%d ms，Q 表状态数 %d" % [EPISODES, trained_ms, q_table.size()])


func _build_walls() -> void:
	# 一道带缺口的横墙，迫使策略绕行，而不是只会「直线冲脸」
	for x in range(3, 9):
		walls[Vector2i(x, 3)] = true
	for y in range(0, 3):
		walls[Vector2i(9, y)] = true


# ---------------- 状态编码 ----------------
# 状态 = 相对位移（裁剪到 [-4, 4]）+ 四邻接墙位掩码
# 相对位移让策略具备一定平移泛化能力，墙位掩码帮助它提前避开死角。
func _state_key(a: Vector2i, t: Vector2i) -> String:
	var rel := t - a
	rel.x = clampi(rel.x, -4, 4)
	rel.y = clampi(rel.y, -4, 4)
	var wall_bits := 0
	for i in ACTIONS.size():
		if walls.has(a + ACTIONS[i]):
			wall_bits |= 1 << i
	return "%d,%d,%d" % [rel.x + 4, rel.y + 4, wall_bits]


func _q_values(state: String) -> Array:
	if not q_table.has(state):
		q_table[state] = [0.0, 0.0, 0.0, 0.0]
	return q_table[state]


func _max_q(values: Array) -> float:
	return maxf(maxf(values[0], values[1]), maxf(values[2], values[3]))


func _choose_action(state: String, epsilon: float) -> int:
	if randf() < epsilon:
		return randi() % ACTIONS.size()
	var q := _q_values(state)
	var best := 0
	for i in range(1, ACTIONS.size()):
		if q[i] > q[best]:
			best = i
	return best


# ---------------- 环境交互 ----------------
func _manhattan(a: Vector2i, b: Vector2i) -> int:
	var d := a - b
	return absi(d.x) + absi(d.y)


func _step(action: int) -> Dictionary:
	var next := agent_cell + ACTIONS[action]
	var reward := STEP_PENALTY
	var done := false

	# 越界或撞墙：位置不变，给予惩罚
	if next.x < 0 or next.y < 0 or next.x >= GRID.x or next.y >= GRID.y or walls.has(next):
		reward = WALL_PENALTY
	else:
		var old_dist := _manhattan(agent_cell, target_cell)
		agent_cell = next
		var new_dist := _manhattan(agent_cell, target_cell)
		# 势能型奖励塑形：靠近目标给一点正反馈，加速早期学习
		reward += 0.1 * float(old_dist - new_dist)
		if agent_cell == target_cell:
			reward = GOAL_REWARD
			done = true

	return {
		"state": _state_key(agent_cell, target_cell),
		"reward": reward,
		"done": done,
	}


func _random_free_cell() -> Vector2i:
	while true:
		var c := Vector2i(randi_range(0, GRID.x - 1), randi_range(0, GRID.y - 1))
		if not walls.has(c):
			return c
	return Vector2i.ZERO


func _reset_episode() -> void:
	agent_cell = _random_free_cell()
	target_cell = _random_free_cell()
	while target_cell == agent_cell:
		target_cell = _random_free_cell()


# ---------------- 训练 ----------------
func train() -> void:
	var start := Time.get_ticks_msec()
	var epsilon := EPS_START

	for episode in EPISODES:
		_reset_episode()
		var state := _state_key(agent_cell, target_cell)

		for step in MAX_STEPS:
			var action := _choose_action(state, epsilon)
			var result := _step(action)
			var next_state: String = result["state"]
			var reward: float = result["reward"]
			var done: bool = result["done"]

			var q := _q_values(state)
			var target := reward
			if not done:
				target += GAMMA * _max_q(_q_values(next_state))

			# Bellman 更新
			q[action] += ALPHA * (target - q[action])

			state = next_state
			if done:
				break

		epsilon = maxf(EPS_MIN, epsilon * EPS_DECAY)

	trained_ms = Time.get_ticks_msec() - start


# ---------------- 演示 ----------------
func _process(delta: float) -> void:
	demo_timer += delta
	if demo_timer >= DEMO_INTERVAL:
		demo_timer = 0.0
		_demo_step()
		queue_redraw()


func _demo_step() -> void:
	var state := _state_key(agent_cell, target_cell)
	var q := _q_values(state)
	var action := 0
	for i in range(1, ACTIONS.size()):
		if q[i] > q[action]:
			action = i

	var result := _step(action)
	if result["done"]:
		demo_episode += 1
		target_cell = _random_free_cell()
		while target_cell == agent_cell:
			target_cell = _random_free_cell()


# ---------------- 绘制 ----------------
func _draw() -> void:
	var origin := Vector2(40, 72)
	draw_rect(Rect2(origin, Vector2(GRID) * CELL), Color(0.10, 0.11, 0.15))

	for x in GRID.x:
		for y in GRID.y:
			var c := Vector2i(x, y)
			var r := Rect2(origin + Vector2(c) * CELL, Vector2(CELL, CELL))
			if walls.has(c):
				draw_rect(r.grow(-1.0), Color(0.24, 0.26, 0.34))
			else:
				draw_rect(r.grow(-1.0), Color(0.15, 0.17, 0.22))

	var tpos := origin + (Vector2(target_cell) + Vector2(0.5, 0.5)) * CELL
	var apos := origin + (Vector2(agent_cell) + Vector2(0.5, 0.5)) * CELL
	draw_line(apos, tpos, Color(1, 1, 1, 0.12), 2.0)
	draw_circle(tpos, CELL * 0.30, Color(0.95, 0.35, 0.35))
	draw_circle(apos, CELL * 0.32, Color(0.35, 0.70, 1.00))

	var font := ThemeDB.fallback_font
	draw_string(
		font, Vector2(40, 36),
		"Q-Learning  |  Q 表状态: %d  |  演示抓捕: %d 次" % [q_table.size(), demo_episode],
		HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.90, 0.95, 1.00)
	)
	draw_string(
		font, Vector2(40, 72 + GRID.y * CELL + 28),
		"蓝点 = 敌人（学习后策略）   红点 = 目标   撞墙/绕行均由奖励塑造",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.70, 0.75, 0.85)
	)
```

### 3.3 代码导读

- **状态设计**：把「敌人—目标」的相对位置裁剪到 `[-4, 4]`，既压缩了状态空间，又让同一套策略可以复用到地图不同位置；额外拼上四邻接墙的 4 位掩码，避免敌人学会「面壁」。
- **奖励塑形**：`0.1 × (旧距离 − 新距离)` 是经典的**势能型奖励**，只在靠近时给正反馈，不改变最优策略，但能显著加快收敛。
- **终止条件**：抓到目标立即 `break`，并且 TD target 不再加未来项，避免把「下一个随机目标」的价值错误地算进来。
- **演示阶段**：`_demo_step()` 只取 argmax，不再探索。若想看训练过程，可把 `_process` 中改为持续训练并降低 `DEMO_INTERVAL`。

### 3.4 Q 表的保存与加载

游戏里通常希望「训练一次，长期复用」。Q 表的键是 String、值是 4 个 float，可以直接序列化为 JSON：

```gdscript
func save_q_table(path: String) -> void:
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(q_table))


func load_q_table(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var file := FileAccess.open(path, FileAccess.READ)
	var data = JSON.parse_string(file.get_as_text())
	if typeof(data) != TYPE_DICTIONARY:
		return false
	q_table.clear()
	for key in data:
		var arr: Array = data[key]
		q_table[key] = [float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3])]
	return true
```

把导出的 JSON 放进 `res://data/q_table.json`，启动时先 `load_q_table()`，失败再 `train()`，就能兼顾「开箱即用」与「可继续学习」。

---

## 四、接入 Godot RL Agents（深度强化学习）

当状态是屏幕像素、射线阵列或连续速度时，表格法会失效，此时可用 [Godot RL Agents](https://pypi.org/project/godot-rl/)：

1. `pip install godot-rl`（建议在虚拟环境中）；
2. 从官方示例（BallChase、JumperHard 等）复制工程；
3. 在训练场景中加入 `Sync` 节点，负责 Godot 与 Python 之间的 TCP 通信；
4. 用 `gdrl` 启动训练，Stable Baselines3 / Sample Factory / RLlib 均可作为后端；
5. 训练完成后导出 ONNX，在游戏端做推理。

它的设计思想与本文一致：环境侧只负责**观测、动作、奖励、重置**，学习算法交给 Python。区别只是函数近似从「字典」换成了「神经网络」。论文见 [Godot Reinforcement Learning Agents (arXiv:2112.03636)](https://arxiv.org/abs/2112.03636)。

---

## 五、实践要点与踩坑清单

1. **先离散化，再谈学习**：状态粒度太细（例如直接用浮点坐标）会让表格法永远学不完；先用网格/分桶。
2. **奖励是设计问题，不是算法问题**：只给终点奖励会导致稀疏反馈、收敛极慢；只给距离奖励可能学会「绕圈刷分」。势能型塑形是目前较稳妥的折中。
3. **探索率要衰减**：固定 `ε=0.3` 会让演示阶段仍然乱走；固定 `ε=0` 则可能从未探索到关键路径。
4. **训练与渲染分离**：训练循环放在 `_ready()` 只适合小规模示例；正式项目应分帧训练或离线训练，避免卡住主线程。
5. **防止状态爆炸**：状态数 ≈ 相对位置数 × 墙掩码数。本文约 1300 个状态，几秒可收敛；若扩到 64×64 地图，就需要函数近似。
6. **可解释性与调试**：打印 `Q(s,·)`、可视化最优动作箭头，比盯着数值更快定位「奖励写错」。
7. **上线策略要关闭探索**：发布版本使用纯贪心，并考虑对 Q 值做平滑/温度采样，避免敌人在两个等价动作间抖动。
8. **与规则 AI 结合**：用状态机管理「巡逻 / 追击 / 搜索」，只在追击层用 RL 选位，既稳定又易调试。

---

## 六、延伸阅读

- [Godot RL Agents（PyPI 文档与示例）](https://pypi.org/project/godot-rl/)
- [Godot Reinforcement Learning Agents 论文](https://arxiv.org/abs/2112.03636)
- [Gymnasium：训练你的第一个智能体（Bellman 更新与 ε-greedy 的官方讲解）](https://gymnasium.farama.org/introduction/train_agent/)
- [DTDA ML：纯 GDScript 的 KNN / 决策树 / 表格 Q-Learning 插件](https://godotengine.org/asset-library/asset/3359)
- [Godot Native Reinforcement Learning（ncnn 原生推理）](https://godotengine.org/asset-library/asset/5358)
- [Sutton & Barto《Reinforcement Learning: An Introduction》](http://incompleteideas.net/book/the-book-2nd.html)

---

## 七、小结

本文用不到 200 行 GDScript，把「状态编码 → 动作选择 → 奖励设计 → Bellman 更新 → 贪心演示」完整跑了一遍。强化学习并不神秘，它的工程难点主要在**状态怎么设计、奖励怎么给、训练怎么落地**。当你的敌人规则越写越复杂时，不妨留出一层，让它自己学。
