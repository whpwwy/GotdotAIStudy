# Godot 4 遗传算法实战：用选择、交叉与变异进化敌人 AI

- **日期**：2026-11-22（Asia/Shanghai）
- **引擎版本**：Godot 4.x（GDScript）
- **难度**：进阶（无需插件、神经网络或外部训练环境）
- **主题关键词**：遗传算法、Genetic Algorithm、进化计算、适应度函数、锦标赛选择、均匀交叉、高斯变异、精英保留
- **来源链接**：
  - [Godot 官方文档：Random number generation](https://docs.godotengine.org/en/stable/tutorials/math/random_number_generation.html)
  - [Evolving Platform Game Agents with a Genetic Algorithm](https://loicdescotte.github.io/posts/genetic-algorithm-scala3/)
  - [Evolving a Better Adversary: A Case Study in a German Castle](https://vigir.ee.missouri.edu/~gdesouza/Research/Conference_CDs/IEEE_SSCI_2007/Artificial%20Life%20-%20ALife%202007/data/papers/ALIFE/S009P002.pdf)
  - [Efficient Reinforcement Learning Through Evolving Neural Network Topologies](https://nn.cs.utexas.edu/?stanley:gecco02b)

> 本文与历史文章的边界：此前的 Q-Learning 文章通过状态—动作价值和 Bellman 更新学习策略；本文不建立 Q 表、不计算 TD 误差，也不实现行为树或状态机，而是把敌人的战斗参数编码为基因组，通过**种群评估、选择、交叉和变异**逐代优化。

---

## 一、遗传算法适合解决什么问题

有些敌人 AI 的行为框架已经确定，但参数很难手调：

- 远程敌人与玩家保持多远，才能兼顾输出和生存？
- 移动速度、侧向绕行和开火频率怎样配合？
- 怎样找到一组在多种战斗场景中都不错的参数，而不是凭感觉反复试？

遗传算法（Genetic Algorithm，GA）把每个候选参数组合看成一个“个体”，让一批个体在同一环境中接受评估。表现好的个体更有机会繁殖，下一代通过交叉继承双方参数，再通过少量变异引入新可能。经过若干代后，种群整体通常会向高适应度区域集中。

它尤其适合：

1. **参数可编码**：速度、距离、权重、冷却时间等能表示为一组数值；
2. **结果可评分**：能够用伤害、生存、耗时、资源消耗等定义好坏；
3. **模拟成本可控**：候选个体可以在离线或加速环境中运行；
4. **不依赖可微分**：不需要梯度，也不要求游戏逻辑可微。

GA 不保证找到全局最优解。若模拟非常昂贵、评价目标含糊，或一个手工公式已经足够，直接调参往往更合适。

---

## 二、核心概念：从基因组到下一代

| 概念 | 含义 | 本文示例 |
|---|---|---|
| 基因 Gene | 一个可优化的数值 | 理想距离、移动速度、绕行倾向、开火间隔 |
| 基因组 Genome | 一个个体的完整基因序列 | 长度为 4、每项位于 `[0, 1]` 的数组 |
| 个体 Individual | 基因组及其评价结果 | 一组敌人参数和它的适应度 |
| 种群 Population | 同代所有个体 | 每代 36 个候选敌人 |
| 适应度 Fitness | 个体在当前任务中的得分 | 期望伤害 + 剩余生命奖励 |
| 选择 Selection | 决定哪些个体成为父代 | 3 个候选者中取得分最高者 |
| 交叉 Crossover | 组合两个父代的基因 | 每个基因随机继承父亲或母亲 |
| 变异 Mutation | 小幅扰动基因以维持探索 | 按概率加入高斯噪声并裁剪 |
| 精英保留 Elitism | 最优个体原样进入下一代 | 每代保留前 4 名 |

### 2.1 为什么基因先归一化到 `[0, 1]`

四个参数的量纲完全不同：距离是像素，速度是像素/秒，开火间隔是秒。如果直接在原数值上叠加相同噪声，变异幅度会失衡。

本文让基因始终落在 `[0, 1]`，只在执行行为时解码：

```text
preferred_range = lerp(80, 230, gene[0])
move_speed      = lerp(90, 220, gene[1])
orbit_strength  = lerp(-1, 1, gene[2])
fire_interval   = lerp(0.22, 0.85, gene[3])
```

这样，相同的变异强度对每个基因都代表“搜索区间的一定比例”。

### 2.2 锦标赛选择、精英保留与变异的分工

- **锦标赛选择**负责“优胜劣汰”：随机抽取 3 个个体，取适应度最高者作为父代。增大锦标赛规模会提高选择压力，也可能更快损失多样性。
- **均匀交叉**负责“组合已有方案”：子代的每个基因独立来自任一父代。
- **高斯变异**负责“探索附近的新方案”：小噪声更常见，大噪声较少见，最后必须裁剪到合法范围。
- **精英保留**负责“防止最好结果倒退”：最优若干个体不交叉、不变异，直接进入下一代。

### 2.3 适应度函数就是进化目标

本文采用：

```text
fitness = expected_damage + 0.6 × remaining_health
```

敌人靠得太近会承受更高压力，离得太远又会降低命中率；高速绕行有利于规避，但移动本身也会降低射击精度。进化需要在这些相互冲突的因素之间寻找折中。

注意：适应度奖励什么，种群就会优化什么。如果只奖励伤害，可能进化出“贴脸换血”的敌人；如果只奖励生存，又可能得到永远逃跑的敌人。目标函数必须与实际设计意图一致。

---

## 三、单文件可运行示例

### 3.1 运行方法

1. 新建 Godot 4 项目和一个 2D 场景，根节点选择 `Node2D`；
2. 新建 `genetic_enemy_demo.gd`，粘贴下面完整代码并挂到根节点；
3. 按 F5 运行。脚本会先在 `_ready()` 中完成 30 代进化，再展示当代最优个体；
4. 观察输出日志中的每代最高适应度，以及画面中的最佳基因与解码参数。

示例用固定随机种子保证结果可复现；用“期望伤害”而不是逐次随机判定命中，避免某个个体仅因一次走运而获得不公平优势。整个训练过程只有约 17 万次轻量模拟步，适合作为教学演示。

### 3.2 完整 GDScript

```gdscript
extends Node2D
## Godot 4.x：用遗传算法优化远程敌人的四个行为参数。
## 新建 Node2D 根节点并挂载本脚本，直接运行即可。

const GENE_COUNT := 4
const POPULATION_SIZE := 36
const GENERATIONS := 30
const ELITE_COUNT := 4
const TOURNAMENT_SIZE := 3
const MUTATION_RATE := 0.12
const MUTATION_STRENGTH := 0.12

const SIM_DT := 0.05
const SIM_STEPS := 160 # 每个个体模拟 8 秒
const ARENA := Rect2(40, 92, 760, 430)

var rng := RandomNumberGenerator.new()
var population: Array = []
var generation := 0
var best_genes := PackedFloat32Array()
var best_fitness := 0.0

# 演示状态
var demo_enemy := Vector2(140, 320)
var demo_player := Vector2(620, 320)
var demo_health := 100.0
var demo_damage := 0.0
var demo_cooldown := 0.0
var demo_time := 0.0
var shot_flash := 0.0
var trail := PackedVector2Array()


func _ready() -> void:
	# 独立 RNG 实例：不影响项目其他随机逻辑；固定种子便于复现实验。
	rng.seed = 20261122
	_evolve()
	_reset_demo()
	print("最佳基因：", best_genes)
	print("解码参数：", _decode(best_genes))


# ---------------- 遗传算法 ----------------

func _evolve() -> void:
	population.clear()
	for i in POPULATION_SIZE:
		population.append({
			"genes": _random_genome(),
			"fitness": 0.0,
		})

	for gen in GENERATIONS:
		generation = gen + 1
		for individual in population:
			individual["fitness"] = _evaluate(individual["genes"])

		population.sort_custom(
			func(a, b): return a["fitness"] > b["fitness"]
		)
		best_genes = population[0]["genes"].duplicate()
		best_fitness = population[0]["fitness"]
		print("第 %02d 代 | 最佳适应度 %.3f" % [generation, best_fitness])

		var next_population: Array = []
		# 精英原样保留，避免交叉或变异破坏当前最佳方案。
		for i in ELITE_COUNT:
			next_population.append({
				"genes": population[i]["genes"].duplicate(),
				"fitness": population[i]["fitness"],
			})

		while next_population.size() < POPULATION_SIZE:
			var parent_a := _tournament_select()
			var parent_b := _tournament_select()
			var child := _crossover(parent_a, parent_b)
			child = _mutate(child)
			next_population.append({"genes": child, "fitness": 0.0})

		population = next_population


func _random_genome() -> PackedFloat32Array:
	var genes := PackedFloat32Array()
	for i in GENE_COUNT:
		genes.append(rng.randf())
	return genes


func _tournament_select() -> PackedFloat32Array:
	var best: Dictionary = population[rng.randi_range(0, population.size() - 1)]
	for i in range(1, TOURNAMENT_SIZE):
		var candidate: Dictionary = population[rng.randi_range(0, population.size() - 1)]
		if candidate["fitness"] > best["fitness"]:
			best = candidate
	return best["genes"]


func _crossover(a: PackedFloat32Array, b: PackedFloat32Array) -> PackedFloat32Array:
	var child := PackedFloat32Array()
	for i in GENE_COUNT:
		child.append(a[i] if rng.randf() < 0.5 else b[i])
	return child


func _mutate(genes: PackedFloat32Array) -> PackedFloat32Array:
	for i in GENE_COUNT:
		if rng.randf() < MUTATION_RATE:
			genes[i] = clampf(
				genes[i] + rng.randfn(0.0, MUTATION_STRENGTH),
				0.0,
				1.0
			)
	return genes


# ---------------- 参数解码与战斗模型 ----------------

func _decode(genes: PackedFloat32Array) -> Dictionary:
	return {
		"preferred_range": lerpf(80.0, 230.0, genes[0]),
		"move_speed": lerpf(90.0, 220.0, genes[1]),
		"orbit_strength": lerpf(-1.0, 1.0, genes[2]),
		"fire_interval": lerpf(0.22, 0.85, genes[3]),
	}


func _evaluate(genes: PackedFloat32Array) -> float:
	var params := _decode(genes)
	var enemy := Vector2(140, 320)
	var player := Vector2(620, 320)
	var health := 100.0
	var damage := 0.0
	var cooldown := 0.0

	for step in SIM_STEPS:
		var time := step * SIM_DT
		player = Vector2(620, 320 + sin(time * 1.4) * 110.0)
		enemy = _movement_step(enemy, player, params, SIM_DT)
		cooldown -= SIM_DT

		var distance := enemy.distance_to(player)
		if cooldown <= 0.0:
			cooldown += params["fire_interval"]
			# 使用期望伤害而非随机命中：所有个体面对同一评价尺度。
			damage += 12.0 * _hit_chance(distance, params)

		# 玩家对近处目标施压；高速侧向绕行可降低压力。
		var dodge := clampf(
			absf(params["orbit_strength"]) * params["move_speed"] / 220.0,
			0.0,
			1.0
		)
		var pressure := maxf(0.0, 1.0 - distance / 300.0)
		health = maxf(0.0, health - 11.0 * pressure * (1.0 - 0.55 * dodge) * SIM_DT)
		if health <= 0.0:
			break

	return damage + 0.6 * health


func _movement_step(
	enemy: Vector2,
	player: Vector2,
	params: Dictionary,
	delta: float
) -> Vector2:
	var to_player := player - enemy
	var distance := maxf(to_player.length(), 0.001)
	var radial := to_player / distance

	# 距离大于理想值时接近，小于理想值时后撤。
	var approach := clampf(
		(distance - params["preferred_range"]) / 120.0,
		-1.0,
		1.0
	)
	var tangent := Vector2(-radial.y, radial.x) * params["orbit_strength"]
	var motion := radial * approach + tangent
	if motion.length() > 1.0:
		motion = motion.normalized()

	var next := enemy + motion * params["move_speed"] * delta
	next.x = clampf(next.x, ARENA.position.x + 12.0, ARENA.end.x - 12.0)
	next.y = clampf(next.y, ARENA.position.y + 12.0, ARENA.end.y - 12.0)
	return next


func _hit_chance(distance: float, params: Dictionary) -> float:
	# 距离、移动速度和过高射速都会损失精度，形成参数间的取舍。
	var speed_penalty := (params["move_speed"] - 90.0) / 600.0
	var rapid_fire_penalty := (0.85 - params["fire_interval"]) * 0.25
	return clampf(
		1.05 - distance / 480.0 - speed_penalty - rapid_fire_penalty,
		0.05,
		0.95
	)


# ---------------- 最优个体演示 ----------------

func _reset_demo() -> void:
	demo_enemy = Vector2(140, 320)
	demo_player = Vector2(620, 320)
	demo_health = 100.0
	demo_damage = 0.0
	demo_cooldown = 0.0
	demo_time = 0.0
	shot_flash = 0.0
	trail.clear()


func _physics_process(delta: float) -> void:
	if best_genes.is_empty():
		return

	demo_time += delta
	if demo_time >= SIM_STEPS * SIM_DT or demo_health <= 0.0:
		_reset_demo()
		return

	var params := _decode(best_genes)
	demo_player = Vector2(620, 320 + sin(demo_time * 1.4) * 110.0)
	demo_enemy = _movement_step(demo_enemy, demo_player, params, delta)
	demo_cooldown -= delta
	shot_flash = maxf(0.0, shot_flash - delta)

	var distance := demo_enemy.distance_to(demo_player)
	if demo_cooldown <= 0.0:
		demo_cooldown += params["fire_interval"]
		demo_damage += 12.0 * _hit_chance(distance, params)
		shot_flash = 0.12

	var dodge := clampf(
		absf(params["orbit_strength"]) * params["move_speed"] / 220.0,
		0.0,
		1.0
	)
	var pressure := maxf(0.0, 1.0 - distance / 300.0)
	demo_health = maxf(
		0.0,
		demo_health - 11.0 * pressure * (1.0 - 0.55 * dodge) * delta
	)

	trail.append(demo_enemy)
	if trail.size() > 140:
		trail.remove_at(0)
	queue_redraw()


func _draw() -> void:
	draw_rect(ARENA, Color(0.09, 0.11, 0.15))
	draw_rect(ARENA, Color(0.35, 0.40, 0.52), false, 2.0)

	if trail.size() >= 2:
		for i in range(1, trail.size()):
			var alpha := float(i) / trail.size() * 0.55
			draw_line(trail[i - 1], trail[i], Color(0.35, 0.75, 1.0, alpha), 2.0)

	draw_circle(demo_player, 14.0, Color(1.0, 0.35, 0.35))
	draw_circle(demo_enemy, 13.0, Color(0.35, 0.75, 1.0))
	draw_line(
		demo_enemy,
		demo_player,
		Color(1.0, 0.9, 0.4, 0.9 if shot_flash > 0.0 else 0.12),
		3.0 if shot_flash > 0.0 else 1.0
	)

	var font := ThemeDB.fallback_font
	draw_string(
		font,
		Vector2(40, 36),
		"Genetic Algorithm | 第 %d 代最佳 | 适应度 %.2f" % [generation, best_fitness],
		HORIZONTAL_ALIGNMENT_LEFT,
		-1,
		20,
		Color(0.92, 0.95, 1.0)
	)
	if not best_genes.is_empty():
		var p := _decode(best_genes)
		draw_string(
			font,
			Vector2(40, 66),
			"距离 %.1f | 速度 %.1f | 绕行 %.2f | 开火间隔 %.2f s | 演示伤害 %.1f | 生命 %.1f" % [
				p["preferred_range"], p["move_speed"], p["orbit_strength"],
				p["fire_interval"], demo_damage, demo_health
			],
			HORIZONTAL_ALIGNMENT_LEFT,
			-1,
			15,
			Color(0.72, 0.80, 0.92)
		)

	draw_string(
		font,
		Vector2(40, 552),
		"蓝点：进化后的敌人    红点：移动目标    蓝线：敌人运动轨迹",
		HORIZONTAL_ALIGNMENT_LEFT,
		-1,
		16,
		Color(0.72, 0.76, 0.84)
	)
```

### 3.3 代码导读

- **公平评估**：`_evaluate()` 给所有个体相同出生点、目标轨迹和模拟时长。命中使用概率乘以单发伤害得到期望值，评价过程本身不消耗随机数。
- **行为与优化解耦**：`_movement_step()` 只负责执行参数，遗传算法只负责寻找参数。之后可以把同一组最佳参数交给 `CharacterBody2D` 敌人使用。
- **父代不会被变异污染**：精英基因通过 `duplicate()` 复制；子代使用新的 `PackedFloat32Array`，变异只作用于子代。
- **结果可复现**：`RandomNumberGenerator` 使用独立固定种子，避免依赖全局随机状态。要验证算法稳定性时，应改用多个不同种子分别实验，而不是只保留最好的一次。
- **演示不是实战物理**：教学模型用距离公式表达战斗压力。正式项目应把 `_evaluate()` 替换为真实场景模拟，并复用实际移动、武器和伤害逻辑。

---

## 四、实践要点与常见陷阱

### 4.1 先验证“评分确实代表好玩”

适应度不是越复杂越好，而是必须可解释、可比较。建议打印若干最优个体的实际战斗录像或轨迹，检查是否出现：

- 利用评分漏洞原地刷分；
- 只在单一出生点有效；
- 数值很高但行为呆板；
- 为追求胜率而让战斗拖得过长。

如果最优解“分数高但不好玩”，先修改环境与评分，不要急着增大种群。

### 4.2 区分训练场景与验证场景

所有世代都在同一条目标轨迹上评估，可能过拟合这条轨迹。正式项目可以准备固定训练场景组，再用未参与进化的验证场景组复测。比较不同个体时必须使用同一批场景和相同评价规则。

### 4.3 控制选择压力和多样性

- 最佳适应度连续多代不变：检查是否变异太弱、锦标赛压力过大，或搜索已经到达当前模型的上限；
- 每代结果剧烈波动：检查评价是否含随机性、精英是否保留成功；
- 所有个体很快变得几乎一样：降低锦标赛规模、提高变异概率，或增加种群规模；
- 高适应度个体在验证场景失败：通常不是“进化不够久”，而是训练场景太单一。

不要盲目同时调大种群和代数。先用小规模实验确认编码与评分，再逐步增加预算。

### 4.4 离线训练，运行时只加载结果

本文为了便于运行，在主线程一次性完成轻量训练。真实项目的模拟成本更高，宜在编辑器工具、独立测试场景或 CI 中离线运行，把最佳基因组保存为 JSON 或自定义 `Resource`。正式游戏启动时只读取参数，不让玩家等待进化。

### 4.5 遗传算法不等于神经进化

本文只优化固定长度的 4 个参数，没有神经网络。若把网络权重作为基因，可以做固定拓扑的神经进化；NEAT 则进一步演化网络拓扑，并通过历史标记、物种保护等机制处理结构创新。它扩展了搜索空间，也显著增加实现与调试成本，不应作为所有项目的第一步。

---

## 五、把示例接入真实敌人

可以按以下顺序改造：

1. 保留 `_random_genome()`、选择、交叉和变异；
2. 将 `_evaluate()` 换成一个可重复重置的战斗场景，返回真实战斗统计；
3. 让实际敌人从 `Resource` 读取解码参数，而不是在脚本里写死；
4. 用多组出生点、玩家策略和关卡布局评估，并保留独立验证组；
5. 将最佳个体和实验种子一起归档，确保结果能够复现和回放。

这样，遗传算法负责“离线寻找好参数”，线上敌人仍然只是执行轻量逻辑，不需要承担训练成本。

---

## 六、延伸阅读

- [Godot：随机数生成与固定种子](https://docs.godotengine.org/en/stable/tutorials/math/random_number_generation.html)：了解全局随机函数和独立 `RandomNumberGenerator` 实例。
- [遗传算法进化平台游戏智能体](https://loicdescotte.github.io/posts/genetic-algorithm-scala3/)：查看固定环境、锦标赛选择、精英保留和停滞处理的另一种实现。
- [Evolving a Better Adversary](https://vigir.ee.missouri.edu/~gdesouza/Research/Conference_CDs/IEEE_SSCI_2007/Artificial%20Life%20-%20ALife%202007/data/papers/ALIFE/S009P002.pdf)：了解遗传算法在对抗型游戏 AI 中的应用案例。
- [NEAT 论文主页](https://nn.cs.utexas.edu/?stanley:gecco02b)：从固定参数优化继续阅读神经网络拓扑进化。
