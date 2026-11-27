# Godot 4 AI Director 实战：用玩家强度与动态难度做出张弛节奏

- **日期**：2026-11-28（Asia/Shanghai）
- **适用版本**：Godot 4.x（GDScript，无需插件、素材或外部服务）
- **难度**：进阶
- **主题关键词**：AI Director、动态难度调整、DDA、玩家强度、节奏控制、Build Up、Peak Fade、Relax、主动式调整
- **来源链接**：
  - [cite:1] [Michael Booth / Valve：Replayable Cooperative Game Design: Left 4 Dead](https://media.cdn.queniuqe.com/apps/valve/2009/GDC2009_ReplayableCooperativeGameDesign_Left4Dead.pdf)
  - [cite:2] [Robin Hunicke & Vernell Chapman：AI for Dynamic Difficulty Adjustment in Games](https://cdn.aaai.org/Workshops/2004/WS-04-04/WS04-04-019.pdf)
  - [cite:3] [PaceMaker: A Practical Tool for Pacing Video Games](https://arxiv.org/abs/2408.15001)
  - [cite:4] [Godot 官方文档：Using signals](https://docs.godotengine.org/en/4.4/getting_started/step_by_step/signals.html)

> 与历史文章的边界：本文不让单个敌人选择动作，也不做寻路、行为树、Utility AI 或强化学习，而是实现位于整场战斗之上的**宏观导演 AI**：估计玩家压力与表现，控制下一场遭遇的时机、强度和休整段。历史 Utility AI 文章解决“某个敌人此刻做什么”，本文解决“整场游戏下一段时间该给玩家多少压力”。

---

## 一、为什么固定刷怪器容易产生疲劳

最简单的刷怪逻辑是每隔固定秒数生成一个敌人。它容易实现，却把游戏体验压成一条平线：玩家状态好时觉得单调，状态差时又可能被连续压力压垮。直接按血量做反向补偿也不理想，例如“血量低就立刻降低敌人伤害”，虽然能救场，却容易让玩家察觉系统在暗中操纵结果。

AI Director 的思路是把问题拆成两个尺度：

- **微观 AI**：某个敌人如何追击、攻击或撤退；
- **宏观导演**：何时制造遭遇、遭遇持续多久、何时停止增援并给出恢复窗口。

Valve 在《Left 4 Dead》的 GDC 讲义中描述了后一种机制：估计每位幸存者的情绪强度，跟踪团队中的最大强度；强度过高时停止主要威胁，否则生成有趣的敌人组合。其目标不是让玩家永远安全，而是制造可重复游玩的强度峰谷。[cite:1]

这也揭示了导演 AI 的一条重要原则：**好的动态难度不是一直降低难度，而是控制压力随时间的形状。**

## 二、核心概念

### 2.1 区分“游戏参数”与“体验参数”

PaceMaker 将节奏相关的数据区分为两类：[cite:3]

- **Artifact parameters（制品参数）**：设计者能直接改变的量，例如敌人数量、刷新间隔、遭遇类型；
- **Experience parameters（体验参数）**：玩家实际感受到的量，例如紧张度、叙事强度、投入程度。

程序可以精确读取“场上有 6 个敌人”，却不能直接读取“玩家现在有 0.73 的紧张感”。因此，导演需要用可观察事件构造一个**近似值**。本文把受伤、倒地和近距离击杀转换为强度增量，把脱离战斗后的时间转换为衰减。

这个数值不是心理测量结果，只是一个可调试的设计代理。应把它写成“估计强度”，不要把它包装成对玩家真实情绪的确定判断。

### 2.2 强度模型：事件脉冲 + 条件衰减

本文使用归一化强度 `I ∈ [0, 1]`：

```text
受伤：       I += damage / 100 × 0.9
倒地：       I = 1
近距离击杀： I += lerp(0.02, 0.12, proximity)
脱离战斗：   I -= decay_per_second × delta
```

近距离击杀也增加强度，是因为敌人倒在玩家附近通常仍属于激烈交战的一部分，不等于“安全”。这与 Valve 讲义中的方向一致：受伤会提高强度，附近敌人死亡也会按距离增加强度；有敌人正在交战时，强度不应自然衰减。[cite:1]

其中 `proximity = 1 - clamp(distance / 600, 0, 1)`。距离越近，击杀带来的强度增量越大。实际项目可以把事件换成《Godot》游戏自身的机制，例如被包围、弹药告急、限时目标将失败等。

### 2.3 四阶段节奏：不是只有一个“困难/休息”开关

本文实现四个阶段：

| 阶段 | 导演行为 | 离开条件 |
|---|---|---|
| `BUILD_UP` | 按当前能力估计持续生成威胁 | 强度达到动态峰值阈值 |
| `SUSTAIN_PEAK` | 到达峰值后仍维持短时间压力 | 持续 4 秒 |
| `PEAK_FADE` | 停止新增威胁，让当前战斗自然收尾 | 场上敌人清空且强度降到休息阈值 |
| `RELAX` | 不生成主要威胁，发出补给事件 | 演示中休息 8 秒 |

`PEAK_FADE` 很关键。若刚跨过峰值就立即进入固定时长休息，而场上敌人仍在交战，就会出现“计时器说该休息，玩家却还在挨打”的错位。Valve 的原始设计同样把 Peak Fade 与 Relax 分开：先停止主要增援，等当前交战出现自然断点后再进入放松段。[cite:1]

示例为了便于观察，将休整段缩短为 8 秒，峰值维持缩短为 4 秒；这不是任何游戏的通用推荐值。原讲义中提到的 Relax 为 30～45 秒，并也可由玩家向下一安全区域的推进提前结束。[cite:1]

### 2.4 DDA 调什么：优先调整尚未发生的遭遇

动态难度调整（DDA）关注玩家能力与游戏挑战之间的失配。Hunicke 与 Chapman 的 Hamlet 系统会监测游戏数据、判断是否需要干预，再执行调整；论文特别区分两类动作：[cite:2]

- **Reactive（反应式）**：直接改变已经交战的敌人，例如临时降低其命中率；
- **Proactive（主动式）**：改变尚未登场的敌人或遭遇，例如推迟刷新、调整下一场敌人组合。

本文采用主动式方案。玩家表现估计 `skill` 会影响：

1. **峰值阈值**：`0.60 → 0.82`，表现越好，导演越愿意让战斗升压；
2. **生成间隔**：`2.0 → 0.9` 秒，表现越好，下一场遭遇越密集；
3. **遭遇强度**：普通/精英权重及新敌人的 `power`。

`skill` 同样是可调的启发式估计，不是玩家能力的客观排名。示例使用血量与命中率的加权值，并以约 8 秒时间常数做指数平滑，避免一次走运或失误就改写整局难度。

## 三、单文件可运行示例

### 3.1 运行方法

1. 新建 Godot 4 项目，创建一个根节点为 `Node2D` 的场景；
2. 新建 `ai_director_demo.gd`，粘贴下方完整代码并挂到根节点；
3. 按 F5 运行。演示会自动模拟玩家与敌人的交战，并绘制最近一段时间的强度曲线；
4. 按 **Space** 注入 18 点受伤事件，按 **K** 模拟一次近距击杀，按 **H** 切换高手模式；
5. 观察 `BUILD_UP → SUSTAIN_PEAK → PEAK_FADE → RELAX` 循环，以及高手模式下阈值、刷新间隔和敌人强度如何变化。

### 3.2 完整 GDScript

```gdscript
extends Node2D
## Godot 4.x：AI Director + 简化 DDA 单文件演示。
## Space：受伤；K：近距击杀；H：切换高手模式。


class AIDirector:
	extends RefCounted

	signal threat_requested(kind: String, power: float)
	signal relief_requested
	signal phase_changed(new_phase: int)

	enum Phase { BUILD_UP, SUSTAIN_PEAK, PEAK_FADE, RELAX }

	const RELAX_THRESHOLD := 0.32
	const MAX_ACTIVE := 10
	const PEAK_HOLD_SECONDS := 4.0
	const RELAX_SECONDS := 8.0 # 演示缩短；生产项目应按关卡节奏调整。
	const DECAY_PER_SECOND := 0.16
	const SKILL_TIME_CONSTANT := 8.0

	var phase: int = Phase.BUILD_UP
	var intensity := 0.0
	var skill := 0.5
	var phase_time := 0.0
	var spawn_clock := 0.0
	var rng := RandomNumberGenerator.new()


	func _init() -> void:
		rng.randomize()


	func report_damage(amount: float) -> void:
		intensity = clampf(
			intensity + maxf(amount, 0.0) / 100.0 * 0.9,
			0.0,
			1.0
		)


	func report_incapacitated() -> void:
		intensity = 1.0


	func report_nearby_kill(distance: float) -> void:
		var proximity := 1.0 - clampf(distance / 600.0, 0.0, 1.0)
		intensity = clampf(
			intensity + lerpf(0.02, 0.12, proximity),
			0.0,
			1.0
		)


	func update(
		delta: float,
		active_enemies: int,
		health_ratio: float,
		accuracy: float
	) -> void:
		# 用可观察指标近似玩家近期表现，再慢速更新，避免难度跳变。
		var performance := clampf(
			health_ratio * 0.55 + accuracy * 0.45,
			0.0,
			1.0
		)
		var blend := 1.0 - exp(-delta / SKILL_TIME_CONSTANT)
		skill = lerpf(skill, performance, blend)

		# 仍在交战时不衰减；敌人清空后才逐步恢复平静。
		if active_enemies <= 0:
			intensity = maxf(0.0, intensity - DECAY_PER_SECOND * delta)

		phase_time += delta
		spawn_clock = maxf(0.0, spawn_clock - delta)

		match phase:
			Phase.BUILD_UP:
				if intensity >= peak_threshold():
					_enter_phase(Phase.SUSTAIN_PEAK)
				else:
					_populate(active_enemies)
			Phase.SUSTAIN_PEAK:
				_populate(active_enemies)
				if phase_time >= PEAK_HOLD_SECONDS:
					_enter_phase(Phase.PEAK_FADE)
			Phase.PEAK_FADE:
				# 停止新增威胁，等待当前交战结束并降到休息区间。
				if active_enemies == 0 and intensity <= RELAX_THRESHOLD:
					_enter_phase(Phase.RELAX)
			Phase.RELAX:
				if phase_time >= RELAX_SECONDS:
					_enter_phase(Phase.BUILD_UP)


	func peak_threshold() -> float:
		return lerpf(0.60, 0.82, skill)


	func _populate(active_enemies: int) -> void:
		if spawn_clock > 0.0 or active_enemies >= MAX_ACTIVE:
			return

		spawn_clock = lerpf(2.0, 0.9, skill)
		var elite := skill > 0.68 and rng.randf() < 0.25
		var kind := "elite" if elite else "normal"
		var power := lerpf(0.85, 1.25, skill) * (1.35 if elite else 1.0)
		threat_requested.emit(kind, power)


	func _enter_phase(next_phase: int) -> void:
		phase = next_phase
		phase_time = 0.0
		spawn_clock = 0.0
		phase_changed.emit(phase)
		if phase == Phase.RELAX:
			relief_requested.emit()


const PHASE_NAMES := ["BUILD_UP", "SUSTAIN_PEAK", "PEAK_FADE", "RELAX"]
const GRAPH_SAMPLES := 240
const GRAPH_ORIGIN := Vector2(64, 350)
const GRAPH_SIZE := Vector2(840, 190)

var director := AIDirector.new()
var health := 1.0
var accuracy := 0.50
var expert_mode := false
var enemy_powers: Array[float] = []
var battle_clock := 0.0
var graph_clock := 0.0
var elapsed := 0.0
var last_event := "导演开始建立第一轮压力"
var history: Array[float] = []


func _ready() -> void:
	director.threat_requested.connect(_on_threat_requested)
	director.relief_requested.connect(_on_relief_requested)
	director.phase_changed.connect(_on_phase_changed)


func _process(delta: float) -> void:
	elapsed += delta
	battle_clock += delta
	graph_clock += delta

	if battle_clock >= 0.9:
		battle_clock = fmod(battle_clock, 0.9)
		_simulate_combat_beat()

	if enemy_powers.is_empty() and director.phase == AIDirector.Phase.RELAX:
		health = minf(1.0, health + delta * 0.035)

	director.update(
		delta,
		enemy_powers.size(),
		health,
		0.88 if expert_mode else accuracy
	)

	if graph_clock >= 0.1:
		graph_clock = fmod(graph_clock, 0.1)
		history.append(director.intensity)
		if history.size() > GRAPH_SAMPLES:
			history.pop_front()

	queue_redraw()


func _simulate_combat_beat() -> void:
	if enemy_powers.is_empty():
		return

	# 每个敌人保存生成时的 power；后续生成不会篡改已有敌人。
	var power: float = enemy_powers.pop_front()
	director.report_nearby_kill(110.0)

	var hit_chance := lerpf(0.70, 0.28, director.skill)
	if director.rng.randf() < hit_chance:
		var damage := director.rng.randf_range(6.0, 13.0) * power
		_apply_damage(damage)

	accuracy = clampf(
		accuracy + director.rng.randf_range(-0.025, 0.025),
		0.35,
		0.75
	)


func _apply_damage(amount: float) -> void:
	health = maxf(0.0, health - amount / 100.0)
	director.report_damage(amount)
	if health <= 0.0:
		director.report_incapacitated()
		enemy_powers.clear()
		health = 0.65 # 演示用“重新站起”，让循环可以继续观察。
		last_event = "玩家倒地：强度置为 1，等待压力消退"


func _on_threat_requested(kind: String, power: float) -> void:
	enemy_powers.append(power)
	last_event = "生成 %s 敌人，power=%.2f" % [kind, power]
	print("[%6.1fs] %s" % [elapsed, last_event])


func _on_relief_requested() -> void:
	# 只发放恢复机会，不删除仍在场上的敌人。
	health = minf(1.0, health + 0.20)
	last_event = "进入休整：发放一次恢复机会"
	print("[%6.1fs] %s" % [elapsed, last_event])


func _on_phase_changed(new_phase: int) -> void:
	print("[%6.1fs] 阶段 -> %s" % [elapsed, PHASE_NAMES[new_phase]])


func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		return

	match event.keycode:
		KEY_SPACE:
			_apply_damage(18.0)
			get_viewport().set_input_as_handled()
		KEY_K:
			if not enemy_powers.is_empty():
				enemy_powers.pop_front()
				director.report_nearby_kill(80.0)
				last_event = "手动近距击杀：强度上升"
			get_viewport().set_input_as_handled()
		KEY_H:
			expert_mode = not expert_mode
			last_event = "高手模式：%s（能力估计将缓慢靠拢）" % str(expert_mode)
			get_viewport().set_input_as_handled()


func _draw() -> void:
	var font := ThemeDB.fallback_font
	draw_rect(Rect2(Vector2.ZERO, Vector2(970, 620)), Color(0.035, 0.05, 0.08))
	draw_string(
		font, Vector2(64, 52), "Godot 4 AI Director / DDA",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 28, Color(0.90, 0.95, 1.0)
	)
	draw_string(
		font, Vector2(64, 94), "阶段：%s" % PHASE_NAMES[director.phase],
		HORIZONTAL_ALIGNMENT_LEFT, -1, 21, Color(0.45, 0.82, 1.0)
	)
	draw_string(
		font, Vector2(64, 128),
		"强度 %.2f  |  能力估计 %.2f  |  敌人 %d  |  HP %.0f%%" % [
			director.intensity, director.skill, enemy_powers.size(), health * 100.0,
		],
		HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.80, 0.86, 0.94)
	)
	draw_string(
		font, Vector2(64, 162), last_event,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.95, 0.76, 0.36)
	)
	draw_string(
		font, Vector2(64, 205), "Space：受伤    K：近距击杀    H：高手模式",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.72, 0.78, 0.86)
	)

	# 强度曲线、动态峰值阈值和休息阈值。
	draw_rect(
		Rect2(GRAPH_ORIGIN, GRAPH_SIZE),
		Color(0.09, 0.13, 0.19)
	)
	var peak_y := GRAPH_ORIGIN.y + GRAPH_SIZE.y * (1.0 - director.peak_threshold())
	var relax_y := GRAPH_ORIGIN.y + GRAPH_SIZE.y * (
		1.0 - AIDirector.RELAX_THRESHOLD
	)
	draw_line(
		Vector2(GRAPH_ORIGIN.x, peak_y),
		Vector2(GRAPH_ORIGIN.x + GRAPH_SIZE.x, peak_y),
		Color(1.0, 0.38, 0.32), 1.0
	)
	draw_line(
		Vector2(GRAPH_ORIGIN.x, relax_y),
		Vector2(GRAPH_ORIGIN.x + GRAPH_SIZE.x, relax_y),
		Color(0.35, 0.85, 0.55), 1.0
	)
	draw_string(
		font, Vector2(GRAPH_ORIGIN.x + 8, peak_y - 7), "动态峰值",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(1.0, 0.55, 0.48)
	)
	draw_string(
		font, Vector2(GRAPH_ORIGIN.x + 8, relax_y - 7), "休息阈值",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.48, 0.90, 0.62)
	)

	var points := PackedVector2Array()
	var step := GRAPH_SIZE.x / float(GRAPH_SAMPLES - 1)
	var start_x := GRAPH_ORIGIN.x + GRAPH_SIZE.x - float(history.size() - 1) * step
	for i in range(history.size()):
		points.append(Vector2(
			start_x + float(i) * step,
			GRAPH_ORIGIN.y + GRAPH_SIZE.y * (1.0 - history[i])
		))
	if points.size() >= 2:
		draw_polyline(points, Color(0.35, 0.72, 1.0), 2.0, true)

	draw_string(
		font, Vector2(64, 580),
		"红线：峰值阈值    绿线：休息阈值    蓝线：估计强度",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.68, 0.75, 0.84)
	)
```

### 3.3 代码导读

- **导演不依赖具体敌人类**：`AIDirector` 只发出 `threat_requested(kind, power)`。由游戏层决定生成 2D 敌人、3D 敌人还是其他遭遇；因此导演逻辑不必知道场景路径、碰撞层或导航网格。
- **导演也不直接操纵场景树**：信号把“决定生成什么”和“如何实例化”解耦。Godot 自定义信号可以像内置信号一样通过 `connect()` 连接，并用 `emit()` 发出。[cite:4]
- **敌人保存自己的强度**：`enemy_powers.append(power)` 在生成时记录参数，战斗结算时从对应条目读取。这样调整下一场遭遇不会追溯性地改变已经存在的敌人。
- **Peak Fade 不新增威胁**：场上敌人仍可继续战斗；只有敌人清空且强度充分衰减，才进入 Relax。
- **休整不等于清场**：进入 Relax 时只发出一次恢复事件，不删除活着的敌人。若游戏要求绝对安全房，应另外用关卡规则实现，而不是藏进通用导演中。
- **所有时间推进统一使用 `delta`**：强度衰减、阶段计时和能力平滑都不会因帧率不同而改变设计速度。

## 四、如何验证导演是否真的有效

不要只看“玩家最后有没有赢”。至少记录以下时间序列：

| 数据 | 用途 |
|---|---|
| `intensity` | 检查峰谷是否出现、是否长期贴满 1 |
| `phase` 与阶段持续时间 | 找出卡在 Peak Fade 或 Relax 过短的问题 |
| 场上敌人数与总生成数 | 区分“导演没生成”和“玩家没清理” |
| 玩家血量、资源与受伤速率 | 检查强度代理是否漏掉主要压力来源 |
| `skill` 与触发时的新敌人参数 | 判断调整是否过快、过强或方向相反 |

建议做三组对照实验：

1. **固定难度组**：锁定 `skill = 0.5`，但保留节奏阶段，观察纯导演节奏的影响；
2. **无导演组**：固定刷新间隔、不进入 Relax，作为基线；
3. **自适应导演组**：运行本文完整逻辑。

比较时不只统计死亡率，还应统计连续高压时长、休整段资源恢复量、玩家重复游玩意愿和主观公平感。DDA 研究的目标不是简单消除失败，而是在合适时机提供可理解、不过度的干预。[cite:2]

还可以用确定性回放排查问题：把 `RandomNumberGenerator.seed` 固定，记录每次 `report_damage()`、`report_nearby_kill()` 和阶段转换。相同输入与种子应能重现导演决策，便于判断问题来自节奏逻辑还是战斗模拟。

## 五、实践要点

### 5.1 不要让自适应变成明显的“橡皮筋”

如果玩家每次残血都立刻获得补给、每次连胜都马上刷精英，系统会很快被看穿。可采用以下约束：

- 只在新遭遇开始前应用较大的参数变化；
- 用平滑、冷却和最短阶段时长限制调整频率；
- 给随机组合保留空间，不把每个结果都精确补偿到同一水平；
- 保留玩家选择的后果，不因一次失误自动抹除所有威胁；
- 对剧情 Boss、教学段或竞技模式设置禁用区域。

### 5.2 阈值附近要防止阶段抖动

示例通过“高阈值进入峰值、低阈值进入休整”形成回差，而不是用同一个阈值反复开关。还可以增加：

- 最短 Build Up 时间，避免开局一次爆炸伤害直接跳峰；
- Peak Fade 最大时长与设计师审核的兜底策略；
- Relax 提前结束条件，例如玩家主动进入下一遭遇区域；
- 多名玩家时先保存每人强度，再按设计目标取最大值或分位数。

多人合作游戏不能未经验证就把四人强度简单平均：一名玩家濒临倒地可能被其他人的轻松状态掩盖。Valve 的示例选择跟踪团队中的最大强度，是值得测试的起点，而不是所有合作游戏的固定答案。[cite:1]

### 5.3 优先调整内容组合，再调整数值

把敌人速度或伤害乘一个系数最容易，却不一定最有趣。更可读的导演动作包括：

- 改变远程/近战敌人的比例；
- 选择不同遭遇模板，而不是无限堆怪；
- 调整补给出现的位置与路径风险；
- 在 Relax 中安排探索、叙事或资源决策；
- 用音景和动画预告压力上升，让玩家有反应时间。

PaceMaker 对强度与玩法类别随时间变化的可视化也提示我们：节奏不仅是“难度数值”，还包括战斗、探索、奖励等不同活动如何交替。[cite:3]

### 5.4 导演与敌人 AI 应分层协作

推荐的职责划分是：

```text
AI Director：选择下一场遭遇与整体节奏
    ↓ kind / power / spawn_region
遭遇管理器：实例化敌人、跟踪存活数、处理补给
    ↓
行为树 / FSM / Utility AI：控制每个敌人的具体行为
    ↓
NavigationAgent / 移动控制器：执行移动
```

导演可以接收导航系统的安全刷怪点，但不应亲自计算每个敌人的路径；敌人 AI 可以读取自身状态，但不应擅自切换整局节奏。分层后，才能分别测试“刷怪时机是否合理”和“敌人行为是否正确”。

### 5.5 保留人工设计与关闭开关

导演不是自动关卡设计师。Boss 战、剧情节拍和教学关通常需要明确的作者控制。建议提供：

- `enabled`：在竞技或固定挑战模式中关闭自适应；
- `intensity_override`：让剧情事件直接指定目标区间；
- 阶段与参数日志：供关卡设计师复盘；
- 参数资源：把阈值、持续时间、遭遇表放入自定义 `Resource`，避免散落魔法数字。

## 六、延伸阅读

- [cite:1] [Valve：Replayable Cooperative Game Design: Left 4 Dead](https://media.cdn.queniuqe.com/apps/valve/2009/GDC2009_ReplayableCooperativeGameDesign_Left4Dead.pdf) —— 阅读 Survivor Intensity、Build Up、Sustain Peak、Peak Fade、Relax 与程序化敌群的原始讲义。
- [cite:2] [AI for Dynamic Difficulty Adjustment in Games](https://cdn.aaai.org/Workshops/2004/WS-04-04/WS04-04-019.pdf) —— 了解 Hamlet 如何监测玩家状态，以及 Reactive 与 Proactive 调整在玩家沉浸感上的差异。
- [cite:3] [PaceMaker: A Practical Tool for Pacing Video Games](https://arxiv.org/abs/2408.15001) —— 学习用节奏图、强度曲线与玩法类别描述非线性游戏体验。
- [cite:4] [Godot 官方文档：Using signals](https://docs.godotengine.org/en/4.4/getting_started/step_by_step/signals.html) —— 将导演决策通过信号接入真实刷怪器、UI 与音频系统。
- [Valve Publications](https://www.valvesoftware.com/en/publications) —— 查找 Valve 公开发布的其他 AI 与游戏设计资料。

## 来源

- [cite:1] [Michael Booth / Valve：Replayable Cooperative Game Design: Left 4 Dead](https://media.cdn.queniuqe.com/apps/valve/2009/GDC2009_ReplayableCooperativeGameDesign_Left4Dead.pdf)
- [cite:2] [Robin Hunicke & Vernell Chapman：AI for Dynamic Difficulty Adjustment in Games](https://cdn.aaai.org/Workshops/2004/WS-04-04/WS04-04-019.pdf)
- [cite:3] [Julian Geheeb, Daniel Dyrda & Sebastian Geheeb：PaceMaker](https://arxiv.org/abs/2408.15001)
- [cite:4] [Godot Engine：Using signals](https://docs.godotengine.org/en/4.4/getting_started/step_by_step/signals.html)
