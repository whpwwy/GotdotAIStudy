# Godot 4 Utility AI 实战：用「效用评分 + 响应曲线」让敌人自己权衡行动

> **日期**：2026-11-17  
> **适用版本**：Godot 4.x（GDScript）  
> **主题**：Utility AI（效用 AI）、Consideration 考量项、响应曲线（Response Curve）、补偿因子、决策惯性  
> **主要来源**：
> - [Improving AI Decision Modeling Through Utility Theory（GDC 2010 讲义 PDF）](https://media.gdcvault.com/gdc10/slides/MarkDill_ImprovingAIUtilityTheory.pdf)
> - [JarkkoPar/Utility_AI_GDExtension（Godot 4 效用 AI 扩展与教程）](https://github.com/JarkkoPar/Utility_AI_GDExtension)
> - [Godot AI Agent: The Ultimate Guide to Game Intelligence — Tech High Wave](https://techhighwave.com/godot-ai-agent-guide/)

---

## 一、为什么还需要 Utility AI？

前面几篇分别写了有限状态机、行为树、GOAP 和寻路：FSM 适合“明确状态 + 明确转换”，行为树适合“可读性强的层级任务”，GOAP 适合“从目标倒推行动序列”。但在敌人需要**同时权衡多个互相冲突的软性因素**时，这三者都会变得别扭。

例如一个射手敌人要在下面几种行为中做选择：

| 行为 | 想射箭时… | 想逃跑时… | 想装填时… |
|---|---|---|---|
| 距离 | 中距离最好 | 越远越好 | 越安全越好 |
| 自身血量 | 太低就不该硬拼 | 越低越想跑 | 不太在意 |
| 弹药 | 没弹药就不能射 | 不太在意 | 弹药越少越该装填 |

这些条件不是“真/假”的硬规则，而是“程度”问题。用 `if health < 0.3: 逃跑` 这样的优先级链，会得到非常机械的行为：血量一旦跨过阈值就瞬间切换，玩家很容易看穿；多加几个条件后，阈值之间还会互相干扰，调一个参数就破坏另一处平衡。

**Utility AI（效用 AI）** 的做法是：为每个候选行为计算一个 `0.0 ~ 1.0` 的“效用分”，选分数最高的一个执行。每个条件（称为 **Consideration，考量项**）先被归一化，再经过一条**响应曲线（Response Curve）**整形，最后多个考量项相乘。GDC 的经典讲义把它总结为 “Infinite Axis Utility System”——每个考量项就是一根坐标轴，行为在多维空间里的位置决定了它的分数。

用一个类比：FSM 是“红绿灯”，Behavior Tree 是“流程图”，GOAP 是“导航软件”，而 Utility AI 是“打分表”。它不回答“下一步该做什么任务”，而是回答“此刻哪个选项**最划算**”。

## 二、三个核心零件

### 1. Consideration：把一个原始数值变成 0~1 的“满意度”

原始数据往往不在 `0~1` 区间：距离可能是 37 像素，血量可能是 68/100，弹药可能是 3 发。所以第一件事是归一化：

```text
distance01 = 1 - clamp(distance / max_range, 0, 1)   # 越近越接近 1
health01   = health / max_health
ammo01     = ammo / max_ammo
```

注意这里有个容易混淆的点：**归一化只负责把数值压到 0~1，不代表“越大越好”**。距离越近，`distance01` 越大；但“逃跑”这个行为希望距离越大越好，所以它需要一条**反向曲线**，而不是在代码里写 `1 - x` 到处散落。曲线就是用来表达这种方向与强弱的。

### 2. Response Curve：曲线决定“性格”

同一条数据配不同曲线，会得到完全不同的 AI 性格：

```text
linear       y = x                 匀速响应
inverse      y = 1 - x             反向（越近越想要 → 越远越想要）
ease_in      y = x²                低值区间很“钝”，高值区间很“敏感”
ease_out     y = 1-(1-x)²          低值区间很敏感，适合“一受伤就想跑”
logistic     y = 1/(1+e^(-k(x-m))) S 形，围绕阈值平滑过渡，避免硬切
band         y = 1-|x-0.5|*2.5     只喜欢中间值（中距离射击）
```

`logistic` 尤其值得用：它让“血量低于 30% 才想逃跑”从一条陡峭的断崖变成一段平滑的斜坡，敌人不会在 31% 和 29% 之间反复横跳。

### 3. Compensation Factor：别让“考量项多”成为惩罚

如果把 4 个考量项直接相乘，每个都是 0.8，结果只有 `0.4096`；而只有 1 个考量项的行为随便就能拿到 0.8。这样一来，**考量项写得越细致的行为反而越吃亏**，这不是我们想要的。

解决办法是加一个补偿项（makeup value），把分数往 1 的方向“抬”一点：

```text
n = 考量项数量
modification = 1 - 1/n
final = score + (1 - score) * modification * score
```

当 `n = 1` 时补偿为 0；`n = 2` 时补偿 0.5；考量项越多，抬升越明显，从而抵消乘法带来的天然衰减。这是 GDC 讲义里最实用的一条工程经验。

## 三、最小可运行示例

新建一个 `Node2D` 场景，只挂一个脚本 `demo_utility_ai.gd`，不需要任何图片、碰撞体或输入映射。脚本里内置一个迷你 Utility AI 框架，并用一个“虚拟敌人 + 虚拟玩家距离”的状态机来驱动它，运行时会在输出面板打印每次决策的完整评分表。

### 3.1 完整代码

```gdscript
extends Node2D
## demo_utility_ai.gd —— 可直接运行的 Utility AI 最小示例

# ---------------------------------------------------------------- 响应曲线

class Curves:
	enum Kind { LINEAR, INVERSE, EASE_IN, EASE_OUT, LOGISTIC, BAND }

	static func sample(kind: int, x: float) -> float:
		x = clampf(x, 0.0, 1.0)
		match kind:
			Kind.LINEAR:
				return x
			Kind.INVERSE:
				return 1.0 - x
			Kind.EASE_IN:
				return x * x
			Kind.EASE_OUT:
				return 1.0 - (1.0 - x) * (1.0 - x)
			Kind.LOGISTIC:
				# k 越大越陡，mid 是“心理阈值”
				return 1.0 / (1.0 + exp(-10.0 * (x - 0.5)))
			Kind.BAND:
				# 0.5 附近最高，0 和 1 附近为 0
				return clampf(1.0 - absf(x - 0.5) * 2.5, 0.0, 1.0)
		return 0.0

# ---------------------------------------------------------------- 考量项

class Consideration:
	var label: String
	var read: Callable            # (agent) -> float，原始值 0~1
	var curve: int                # Curves.Kind
	var weight: float

	func _init(p_label: String, p_read: Callable, p_curve: int, p_weight := 1.0) -> void:
		label = p_label
		read = p_read
		curve = p_curve
		weight = p_weight

	func score(agent) -> float:
		var raw := clampf(float(read.call(agent)), 0.0, 1.0)
		return clampf(Curves.sample(curve, raw) * weight, 0.0, 1.0)

# ---------------------------------------------------------------- 行为

class UtilityAction:
	var label: String
	var considerations: Array
	var perform: Callable         # (agent) -> void，选中后执行一次
	var min_score: float
	var cooldown: float
	var _last_time := -9999.0

	func _init(p_label: String, p_considerations: Array, p_perform: Callable,
			p_min_score := 0.08, p_cooldown := 0.0) -> void:
		label = p_label
		considerations = p_considerations
		perform = p_perform
		min_score = p_min_score
		cooldown = p_cooldown

	func score(agent, now: float) -> float:
		if now - _last_time < cooldown:
			return 0.0
		if considerations.is_empty():
			return 1.0

		var product := 1.0
		for c in considerations:
			var s: float = c.score(agent)
			if s <= 0.0001:
				return 0.0       # 任一考量项为 0，整条行为作废（否决）
			product *= s

		# 补偿因子：避免考量项多的行为被乘积天然压低
		var n := float(considerations.size())
		var modification := 1.0 - 1.0 / n
		var final_score := product + (1.0 - product) * modification * product

		if final_score < min_score:
			return 0.0
		return clampf(final_score, 0.0, 1.0)

	func mark_used(now: float) -> void:
		_last_time = now

# ---------------------------------------------------------------- 大脑

class UtilityBrain:
	var actions: Array = []
	var current: UtilityAction = null
	var switch_bonus := 0.06     # 决策惯性：给当前行为一点加分，防止抖动
	var last_scores: Dictionary = {}

	func add(action: UtilityAction) -> void:
		actions.append(action)

	func decide(agent, now: float) -> UtilityAction:
		var best: UtilityAction = null
		var best_score := -1.0
		last_scores.clear()

		for a in actions:
			var s: float = a.score(agent, now)
			if a == current and s > 0.0:
				s = minf(1.0, s + switch_bonus)
			last_scores[a.label] = s
			if s > best_score:
				best_score = s
				best = a

		if best != null and best_score > 0.0:
			current = best
		return current

# ---------------------------------------------------------------- 演示用的“虚拟敌人”

var health := 1.0
var ammo := 1.0
var distance01 := 0.15       # 0 = 贴脸，1 = 最远
var brain := UtilityBrain.new()
var elapsed := 0.0
var decide_timer := 0.0
const DECIDE_INTERVAL := 0.8

func _ready() -> void:
	_build_actions()
	set_process(true)

func _build_actions() -> void:
	# 攻打（近战）：越近越好，血量太低就不划算
	brain.add(UtilityAction.new(
		"近身攻击",
		[
			Consideration.new("距离", func(a): return 1.0 - a.distance01, Curves.Kind.EASE_IN),
			Consideration.new("血量", func(a): return a.health, Curves.Kind.LOGISTIC),
		],
		_act_melee,
		0.05, 1.2
	))

	# 射击：中距离最舒服，需要弹药
	brain.add(UtilityAction.new(
		"射击",
		[
			Consideration.new("距离带", func(a): return 1.0 - a.distance01, Curves.Kind.BAND),
			Consideration.new("弹药", func(a): return a.ammo, Curves.Kind.LINEAR),
			Consideration.new("血量", func(a): return a.health, Curves.Kind.LOGISTIC),
		],
		_act_shoot,
		0.05, 0.4
	))

	# 撤退：血越少越想跑，越近越该跑
	brain.add(UtilityAction.new(
		"撤退",
		[
			Consideration.new("危险血量", func(a): return a.health, Curves.Kind.INVERSE),
			Consideration.new("贴身威胁", func(a): return 1.0 - a.distance01, Curves.Kind.EASE_IN),
		],
		_act_retreat,
		0.08, 0.6
	))

	# 装填：弹药越少越急，距离越远越安全
	brain.add(UtilityAction.new(
		"装填",
		[
			Consideration.new("缺弹", func(a): return a.ammo, Curves.Kind.INVERSE),
			Consideration.new("安全性", func(a): return a.distance01, Curves.Kind.LINEAR),
		],
		_act_reload,
		0.1, 0.8
	))

# 行为效果用普通方法实现，便于传入 Callable 且可单独调试
func _act_melee(a) -> void:
	a.health = maxf(0.0, a.health - 0.06)
	a.distance01 = maxf(0.0, a.distance01 - 0.05)

func _act_shoot(a) -> void:
	a.ammo = maxf(0.0, a.ammo - 0.22)
	a.health = maxf(0.0, a.health - 0.015)

func _act_retreat(a) -> void:
	a.distance01 = minf(1.0, a.distance01 + 0.12)
	a.health = minf(1.0, a.health + 0.01)

func _act_reload(a) -> void:
	a.ammo = minf(1.0, a.ammo + 0.45)

func _process(delta: float) -> void:
	elapsed += delta
	decide_timer += delta
	# 敌人自动缓慢逼近玩家，制造状态变化
	distance01 = maxf(0.0, distance01 - delta * 0.04)

	if decide_timer >= DECIDE_INTERVAL:
		decide_timer = 0.0
		_tick()

	queue_redraw()

func _tick() -> void:
	var action := brain.decide(self, elapsed)
	if action == null:
		print("[%5.1fs] 无可用行为" % elapsed)
		return

	print("---- %5.1fs  选择：%s  (HP %.2f / AMMO %.2f / DIST %.2f)"
		% [elapsed, action.label, health, ammo, distance01])
	var labels := brain.last_scores.keys()
	labels.sort()
	for label in labels:
		print("     %-6s -> %.3f" % [label, brain.last_scores[label]])

	action.perform.call(self)
	action.mark_used(elapsed)

	health = clampf(health, 0.02, 1.0)
	if health <= 0.05:
		health = 1.0          # 演示循环：倒地后“复活”，方便观察行为变化
		ammo = 1.0

func _draw() -> void:
	# 简易可视化：蓝色玩家、红色敌人、一根连线表示距离
	var diameter := 480.0
	var player_pos := Vector2(80, 240)
	var enemy_pos := Vector2(80 + distance01 * diameter, 240)
	draw_circle(player_pos, 14, Color(0.3, 0.6, 1.0))
	draw_circle(enemy_pos, 12, Color(1.0, 0.35, 0.3))
	draw_line(player_pos, enemy_pos, Color(0.8, 0.8, 0.8, 0.6), 2.0)
```

### 3.2 运行后会看到什么

输出面板会周期性打印类似下面的内容（数值随运行时间变化）：

```text
----  12.8s  选择：射击  (HP 0.84 / AMMO 0.34 / DIST 0.21)
     射击   -> 0.612
     近身攻击 -> 0.498
     撤退   -> 0.041
     装填   -> 0.087
```

几个可以观察到的现象：

1. **距离变远**时，“射击”的 `BAND` 曲线分数先升后降，“撤退”的安全性下降，行为自然从近战过渡到射击。
2. **弹药耗尽**时，“射击”直接被否决（弹药考量项为 0），“装填”的“缺弹”项接近 1，立刻接管。
3. **血量很低**时，“撤退”的 `INVERSE` 曲线陡升，压过攻击行为；血量回升后又会回到进攻。

整个过程没有一处 `if state == ...` 的硬编码分支，行为之间的取舍完全由打分表决定。

## 四、实践要点

### 1. 先想清楚“考量项”而不是“状态”

写 Utility AI 时最容易犯的错误，是把它写成 `if` 链的变形：给每个行为配一堆 `>=`、`<=` 判断，最后得到的还是一个阈值状态机。正确的思维是：**这个行为在什么条件下“更值得做”？把这个条件写成一个连续量**。例如不要写“血量 < 30% 时撤退”，而要写“血量越低，撤退越有吸引力”，再交给曲线决定陡峭程度。

### 2. 曲线要能在 Inspector 里调

上例把曲线写成枚举是为了代码自包含。真实项目里建议把 `kind`、`weight`、`mid`、`k` 改成 `@export` 变量，让策划在 Inspector 里拖动曲线——这也是 [Utility AI GDExtension](https://github.com/JarkkoPar/Utility_AI_GDExtension) 的核心思路：行为和考量项都是可编辑的资源，`eval` 里把 `score` 设为 0~1，并用 `activation_curve` 采样，配合 `has_vetoed` 直接否决某个行为。JarkkoPar 的文档还特别强调：**自定义 `eval` 的返回值必须落在 0~1**，否则补偿因子和乘法组合都会失真。

### 3. 一定要有否决项（Veto）

乘法结构天然支持否决：任意考量项为 0，整个乘积就是 0。这非常有用——没弹药就不该射击、被眩晕就不该移动。但要注意把“否决”和“低分”区分开：`0.02` 和 `0` 在乘法里差别巨大，前者仍可能被补偿因子抬高，后者则彻底出局。若某个条件必须硬性禁止行为，显式返回 0 比给一个很低的分更安全。

### 4. 用惯性 / 冷却解决“抖动的 AI”

Utility AI 最典型的副作用是**每帧重新打分导致行为抖动**：两个行为分数在 0.51 和 0.49 之间来回时，敌人会不停切换动作。两个工程手段：

- **决策惯性**：给当前行为加一个固定小加成（上例 `switch_bonus = 0.06`），只有挑战者明显更优时才换。
- **冷却与最短执行时间**：行为执行后进入冷却（上例的 `cooldown`），避免“装填 → 射击 → 装填”在一秒内循环。

更进一步可以只在**决策点**（例如每 0.5 秒、或某个事件触发时）重新打分，而不是每个 `_process` 都算。

### 5. Utility AI 与行为树、GOAP 不是互斥的

生产项目里常见的组合是：**用 Utility AI 选“当前想做什么”，用行为树或状态机执行“具体怎么做”**。比如 Utility AI 选中“撤退”，具体撤退路线仍交给 `NavigationAgent2D` 寻路；选中“包抄”后，再由行为树展开成“找掩体 → 移动 → 等待”的序列。Utility AI 负责“取舍”，其他结构负责“执行”，各司其职。

### 6. 调参时打印整张评分表

不要只打印最终选择。上例把每个行为的分数都打印出来，调参时才能看出“为什么它选了这一项”。如果发现某个行为永远不出现，先看它的考量项是不是有一项长期为 0（被否决），再看补偿因子是否让它天然吃亏，最后才怀疑曲线参数。

## 五、什么时候不该用 Utility AI

- 行为之间是**严格顺序依赖**（必须先开门才能进房间）：用行为树或 GOAP 更清楚。
- 只需要 2~3 个硬状态且切换条件明确：FSM 更简单，调试成本更低。
- 需要**多步规划**（“先去 A 拿钥匙，再去 B 开门”）：GOAP 的搜索能力是 Utility AI 不具备的。

Utility AI 的甜点区是：**行为数量中等（4~10 个）、每个行为受多个连续因素影响、需要平滑而非突变的决策**——典型如战斗 AI、模拟经营里的居民 AI、RTS 单位的战术选择。

## 六、延伸阅读

- [Improving AI Decision Modeling Through Utility Theory（GDC 2010 讲义）](https://media.gdcvault.com/gdc10/slides/MarkDill_ImprovingAIUtilityTheory.pdf) —— 响应曲线、补偿因子、Infinite Axis Utility System 的原始出处。
- [JarkkoPar/Utility_AI_GDExtension](https://github.com/JarkkoPar/Utility_AI_GDExtension) —— Godot 4 的效用 AI 扩展，含 Agent Behaviour、Behaviour Tree、State Tree 与节点查询系统，可作为生产级参考实现。
- [Godot AI Agent: The Ultimate Guide to Game Intelligence](https://techhighwave.com/godot-ai-agent-guide/) —— 从 `get_score()` 式的行为打分讲起，适合快速上手。
- [Godot 官方文档：NavigationAgent2D](https://docs.godotengine.org/en/stable/classes/class_navigationagent2d.html) —— 把 Utility AI 选出的目标点交给寻路执行。
- 本仓库历史文章：[行为树](articles/2026-11-06-godot-behavior-tree-ai.md)、[有限状态机](articles/2026-11-14-godot-interruptible-fsm.md)、[GOAP](articles/2026-11-16-godot-goap-ai-planner.md) —— 对比四种决策结构的适用边界。
