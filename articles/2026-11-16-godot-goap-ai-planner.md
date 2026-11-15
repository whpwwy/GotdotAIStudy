# Godot 4 GOAP 实战：让敌人自己「想」出行动序列

> **日期**：2026-11-16（Asia/Shanghai）
> **适用版本**：Godot 4.4+（4.x 通用）
> **主题**：GOAP / 目标导向行动规划、STRIPS、世界状态、动作前置条件、A\* 规划、运行时重规划
> **主要来源**：
> - [GOAP — Godot Asset Library](https://godotengine.org/asset-library/asset/4888)
> - [godot-goap — RodZill4（Godot Asset Store）](https://godotassetstore.org/assets/scripts/gh:RodZill4:godot-goap)
> - [Exploring Goal Oriented Action Planning — Bentebent](https://bentebent.github.io/posts/goap/)
> - [Three States and a Plan: The AI of F.E.A.R. — Jeff Orkin, GDC 2005](https://web.cs.wpi.edu/~rich/courses/imgd4100-b11/lectures/L-Planning.pdf)
> - [Building the AI of F.E.A.R. with GOAP — Game History](https://gamehistory.com/design/building-the-ai-of-f-e-a-r-with-goal-oriented-action-planning)

---

## 一、从「写死行为」到「自己规划」

行为树和状态机解决的是「**当前该进入哪个分支 / 哪个状态**」的问题。它们的共同前提是：**设计师已经预想到所有合理的组合**。于是当敌人需要「先捡枪、再装弹、再接近、最后开火」这种跨多个条件、且顺序会随环境变化而改变的行为时，你只能在树里堆大量 `Sequence` 与条件节点，或者在状态机里画出一堆交叉箭头。

GOAP（Goal-Oriented Action Planning，目标导向行动规划）换了一个思路：

> **不写「怎么一步步做」，只写「每个动作需要什么、会产生什么」，让程序自己搜索出一条能达到目标的动作序列。**

这套思路来自 STRIPS 规划，最早在 2005 年的《F.E.A.R.》中被大规模用于游戏 AI。其 AI 主程 Jeff Orkin 在 GDC 演讲里有一句被反复引用的总结：*「A planner is a state machine that writes itself.」*——规划器就是一台**自己把自己写出来的状态机**。

三种方案的分工可以这样理解：

| 方案 | 你负责写 | 运行时决定 | 适合 |
|---|---|---|---|
| 状态机（FSM） | 状态、转换条件 | 下一步进哪个状态 | 行为数量少、转换明确 |
| 行为树（BT） | 树结构与优先级 | 从根到叶走哪条分支 | 行为层级清晰、强调优先级 |
| GOAP | 动作的「前置条件 + 效果 + 成本」 | **达成目标要按什么顺序做哪些动作** | 多条件耦合、顺序会变、需要涌现感 |

GOAP 不是来替代前两者的：一个 GOAP 动作的内部实现，往往仍然是一个小的 FSM 或动画状态机；而「选择哪个目标」也常由行为树或优先级列表完成。**它替换的是「动作序列的编排方式」这一层。**

## 二、核心概念

### 2.1 世界状态（World State）

世界状态是一组**关于当前世界的事实**，通常用布尔值表示：

```gdscript
{
    "has_weapon": false,
    "ammo_full": true,
    "player_visible": true,
    "player_in_melee": false,
    "player_dead": false,
}
```

两条设计铁律：

1. **用事实，不用动作**。键名应该是 `player_in_melee`（玩家是否在近战范围内），而不是 `attack_player`。动作是动词，状态是形容词。
2. **只记录规划需要的部分**。世界状态不是「游戏存档」，把 `hp`、`position` 这类连续量也塞进去，会让状态空间爆炸。位置信息应该在动作执行阶段去查。

### 2.2 动作 = 前置条件 + 效果 + 成本

每个动作就是一段「契约」：

```gdscript
GoapAction.new(
    "Attack",                    # 名字
    1.0,                         # 成本
    0.8,                         # 执行耗时（秒）
    {"player_in_melee": true, "has_weapon": true, "ammo_full": true},  # 前置条件
    {"player_dead": true}                                            # 效果
)
```

- **前置条件（preconditions）**：全部满足，动作才可用。这是规划器的「边」。
- **效果（effects）**：执行后对世界状态的改动。这是规划器的「转移函数」。
- **成本（cost）**：多个可行计划之间的取舍依据。成本不必是时间，也可以是「暴露风险」「资源消耗」。

### 2.3 目标与优先级

目标就是「我希望世界变成什么样」：

```gdscript
{"name": "KillPlayer",   "priority": 10, "desired": {"player_dead": true}}
{"name": "ArmYourself",  "priority": 5,  "desired": {"has_weapon": true}}
```

运行时先尝试高优先级目标；如果它在当前状态下**根本规划不出计划**（例如玩家不可见、又没有远程手段），就降级尝试下一个。这就是 GOAP 里「目标选择」与「规划」分离带来的灵活性。

### 2.4 规划 = 在状态空间里搜索

规划器要回答的问题：**从当前世界状态出发，用最少的成本，经过哪些动作可以满足目标？**

这本质上是一张图的最短路径问题：

- **节点** = 世界状态；
- **边** = 一个前置条件被满足的动作；
- **边权** = 动作成本；
- **终点** = 包含目标事实的状态。

所以直接上 A\* 即可，启发函数取「目标中尚未满足的事实的数量」。状态空间小（几个布尔量）时它几乎瞬间完成；这也是为什么 GOAP 能**每帧重算**而不卡。

> 商业实现里常用「反向搜索」（从目标反推前置条件），可以减少无关节点的展开。本文示例用正向 A\*，逻辑更直观，效果等价。

### 2.5 重规划（Re-planning）

计划执行到一半，世界变了：枪被打掉、玩家躲进掩体、队友先开了火。此时**不需要中断整个 AI**，只要：

1. 保留已完成的动作效果；
2. 检查计划里的**下一个动作**前置条件是否还成立；
3. 不成立就丢弃剩余计划，用**最新世界状态**重新规划。

这就是 GOAP 最有「智能感」的地方：行为不是被写死的分支，而是每次根据当下状态**现算**出来的。

## 三、完整可运行示例

新建一个 Godot 4 项目，场景根节点用 `Node`，挂上下面的 `goap_demo.gd`，按 F5 即可在输出面板看到完整决策过程。

示例模拟一个敌人：初始没有武器、玩家在视野内。它会自己规划「装备武器 → 接近 → 攻击」；中途武器被打落，它会**自动重新规划**，先捡回武器再攻击。

```gdscript
extends Node
## goap_demo.gd —— 最小可运行的 GOAP（目标导向行动规划）示例
## 运行后观察输出面板：目标选择 → 规划 → 执行 → 世界突变 → 重规划

# ============================================================ 动作
class GoapAction:
	var id: String          # 动作名，仅用于日志
	var cost: float         # 成本，规划器据此挑更便宜的序列
	var duration: float     # 执行耗时（秒），真实项目里由动画/移动决定
	var pre: Dictionary     # 前置条件：必须全部满足
	var post: Dictionary    # 效果：执行后写入世界状态

	func _init(p_id: String, p_cost: float, p_duration: float,
			p_pre: Dictionary, p_post: Dictionary) -> void:
		id = p_id
		cost = p_cost
		duration = p_duration
		pre = p_pre
		post = p_post

	func can_run(state: Dictionary) -> bool:
		for k in pre:
			if state.get(k) != pre[k]:
				return false
		return true

	func apply(state: Dictionary) -> void:
		for k in post:
			state[k] = post[k]

# ============================================================ 状态
var _world: Dictionary = {}
var _actions: Array = []
var _goals: Array = []      # 每项：{name, priority, desired}
var _plan: Array = []       # 待执行的 GoapAction 队列

func _ready() -> void:
	# 1) 初始世界状态：没有武器，但弹匣是满的，玩家在视野内
	_world = {
		"has_weapon": false,
		"ammo_full": true,
		"at_ammo_box": false,
		"player_visible": true,
		"player_in_melee": false,
		"player_dead": false,
	}

	# 2) 动作库：只描述“要什么 / 给什么 / 多贵”，不描述顺序
	_actions = [
		GoapAction.new("EquipWeapon", 1.0, 0.6,
			{"has_weapon": false}, {"has_weapon": true}),
		GoapAction.new("Approach", 2.0, 1.2,
			{"player_visible": true, "player_in_melee": false},
			{"player_in_melee": true}),
		GoapAction.new("Attack", 1.0, 0.8,
			{"player_in_melee": true, "has_weapon": true, "ammo_full": true},
			{"player_dead": true}),
		GoapAction.new("GoToAmmoBox", 3.0, 1.5,
			{"at_ammo_box": false}, {"at_ammo_box": true}),
		GoapAction.new("Reload", 1.0, 1.0,
			{"at_ammo_box": true, "ammo_full": false}, {"ammo_full": true}),
	]

	# 3) 目标：高优先级优先，不可达时自动降级
	_goals = [
		{"name": "KillPlayer", "priority": 10, "desired": {"player_dead": true}},
		{"name": "ArmYourself", "priority": 5, "desired": {"has_weapon": true}},
	]

	# 4) 演示：1.5 秒后武器被打落，触发重规划
	get_tree().create_timer(1.5).timeout.connect(_on_weapon_dropped)

	_run_loop()

# ============================================================ 主循环
func _run_loop() -> void:
	while is_inside_tree():
		var action = _next_action()
		if action == null:
			if _all_goals_done():
				print("[GOAP] 所有目标已达成，演示结束")
				return
			print("[GOAP] 当前无可行计划，等待环境变化…")
			await get_tree().create_timer(0.5).timeout
			continue
		await _execute(action)

func _next_action():
	# 首次执行，或在执行过程中发现前置条件失效 → 重新规划
	if _plan.is_empty():
		_plan = _make_plan()
	elif not _plan[0].can_run(_world):
		print("[GOAP] 世界状态变化，丢弃剩余计划并重新规划")
		_plan = _make_plan()

	if _plan.is_empty():
		return null
	return _plan.pop_front()

func _execute(action) -> void:
	print("[GOAP] 执行：%s（预计 %.1fs）" % [action.id, action.duration])
	await get_tree().create_timer(action.duration).timeout
	action.apply(_world)
	print("[GOAP] 完成：%s → %s" % [action.id, _state_text(_world)])

func _on_weapon_dropped() -> void:
	_world["has_weapon"] = false
	print("[世界] 武器被打落！has_weapon = false")

# ============================================================ 规划
func _make_plan() -> Array:
	var sorted_goals := _goals.duplicate()
	sorted_goals.sort_custom(func(a, b): return a.priority > b.priority)

	for goal in sorted_goals:
		if _satisfies(_world, goal.desired):
			continue                        # 已满足，试下一个目标
		var plan := _plan_for(goal.desired)
		if not plan.is_empty():
			print("[GOAP] 选定目标：%s｜计划：%s" % [goal.name, _plan_text(plan)])
			return plan
	return []

func _plan_for(desired: Dictionary) -> Array:
	# A*：节点是世界状态，边是动作，边权是动作成本
	var start := _world.duplicate()
	var open: Array = [{
		"state": start,
		"g": 0.0,
		"h": _heuristic(start, desired),
		"plan": [],
	}]
	var best_cost := {_state_key(start): 0.0}

	while not open.is_empty():
		open.sort_custom(func(a, b): return (a.g + a.h) < (b.g + b.h))
		var node: Dictionary = open.pop_front()
		var state: Dictionary = node.state

		if _satisfies(state, desired):
			return node.plan

		for action in _actions:
			if not action.can_run(state):
				continue
			var next_state := state.duplicate()
			action.apply(next_state)

			var key := _state_key(next_state)
			var new_g: float = node.g + action.cost
			if best_cost.has(key) and best_cost[key] <= new_g:
				continue                    # 已有更便宜的到达方式
			best_cost[key] = new_g

			var new_plan: Array = node.plan.duplicate()
			new_plan.append(action)
			open.append({
				"state": next_state,
				"g": new_g,
				"h": _heuristic(next_state, desired),
				"plan": new_plan,
			})
	return []                               # 无解

func _heuristic(state: Dictionary, desired: Dictionary) -> float:
	# 还没满足的目标事实数量；每个动作最多满足一个事实，因此是可采纳下界
	var n := 0
	for k in desired:
		if state.get(k) != desired[k]:
			n += 1
	return float(n)

func _satisfies(state: Dictionary, desired: Dictionary) -> bool:
	for k in desired:
		if state.get(k) != desired[k]:
			return false
	return true

func _all_goals_done() -> bool:
	for goal in _goals:
		if not _satisfies(_world, goal.desired):
			return false
	return true

# ============================================================ 工具
func _state_key(state: Dictionary) -> String:
	var keys := state.keys()
	keys.sort()
	var parts := PackedStringArray()
	for k in keys:
		parts.append("%s=%s" % [k, state[k]])
	return "|".join(parts)

func _plan_text(plan: Array) -> String:
	var names := PackedStringArray()
	for a in plan:
		names.append(a.id)
	return " → ".join(names)

func _state_text(state: Dictionary) -> String:
	var keys := state.keys()
	keys.sort()
	var parts := PackedStringArray()
	for k in keys:
		parts.append("%s=%s" % [k, state[k]])
	return "{" + ", ".join(parts) + "}"
```

运行后的典型输出（时间顺序）：

```text
[GOAP] 选定目标：KillPlayer｜计划：EquipWeapon → Approach → Attack
[GOAP] 执行：EquipWeapon（预计 0.6s）
[GOAP] 完成：EquipWeapon → {...has_weapon=true...}
[GOAP] 执行：Approach（预计 1.2s）
[世界] 武器被打落！has_weapon = false
[GOAP] 完成：Approach → {...has_weapon=false...}
[GOAP] 世界状态变化，丢弃剩余计划并重新规划
[GOAP] 选定目标：KillPlayer｜计划：EquipWeapon → Attack
[GOAP] 执行：EquipWeapon（预计 0.6s）
[GOAP] 完成：EquipWeapon → {...has_weapon=true...}
[GOAP] 执行：Attack（预计 0.8s）
[GOAP] 完成：Attack → {...player_dead=true...}
[GOAP] 所有目标已达成，演示结束
```

请注意第 3 步：计划原本是 `EquipWeapon → Approach → Attack`，武器被打落后重新规划的结果是 `EquipWeapon → Attack`——因为 `player_in_melee` 这个事实仍然成立，规划器**自动复用了已完成的进展**，没有重走一遍「接近」。

## 四、代码逐段讲解

### 4.1 为什么动作不写「执行逻辑」

`GoapAction` 里只有 `pre` / `post` / `cost`，没有任何 `execute()`。这是刻意的：**规划阶段只做纯数据推演，不碰场景**。如果把移动、播放动画写进动作，A\* 会在一瞬间「执行」成千上万个动作。

真正的执行在 `_execute()` 里，而真实项目中它通常长这样：

```gdscript
func _execute(action) -> void:
	match action.id:
		"Approach":
			_nav.target_position = _player.global_position   # NavigationAgent2D
			await _nav.navigation_finished
		"EquipWeapon":
			_anim.play("equip")
			await _anim.animation_finished
		"Attack":
			_anim.play("attack")
			await _anim.animation_finished
			_deal_damage()
		_:
			await get_tree().process_frame
	action.apply(_world)                                     # 最后才写世界状态
```

这样「决策」与「表现」彻底解耦：规划器的输出只是一串动作名，执行器才负责寻路、动画、伤害判定。

### 4.2 `_next_action()` 是整个 AI 的调度中枢

它一共只做三件事：

1. 没有计划 → 规划；
2. 有计划但队首动作不可用 → 丢计划重规划；
3. 返回队首动作，交给执行器。

第 2 条是运行时灵活性的关键。注意判断的是**「下一个动作是否能跑」**，不是在执行中打断——这样重规划只发生在动作边界，不会把动画切碎。

### 4.3 A\* 里的 `best_cost` 防止重复展开

同一个世界状态可能有多种到达方式（比如先装弹再捡枪 vs 先捡枪再装弹）。`best_cost` 记录「到达该状态的最低成本」，只有更便宜时才继续展开，避免指数级重复搜索。去掉它，小状态空间勉强能跑；动作一多就会卡死。

### 4.4 启发函数为什么可以这样写

`_heuristic` 数的是「目标里还有几个事实没满足」。在每个动作最多改变一个目标事实的前提下，这个计数不会高估真实剩余成本（可采纳），A\* 才能保证找到最优解。如果你的动作能一次满足多个事实，记得改成更保守的估计，否则可能返回次优计划——对游戏 AI 来说通常无所谓，但自己要知道代价。

### 4.5 `_make_plan()` 的目标优先级只是「尝试顺序」

它不是「高优先级目标一定被满足」。当高优先级目标无解时，`_plan_for` 返回空数组，循环继续尝试下一个目标。这个「降级」行为让 AI 不会因为一个不可达目标而僵住——比硬编码的优先级分支更稳。

## 五、接进真实项目

### 5.1 世界状态从哪来：感知层

示例里的 `_world` 是手工填的。真实项目需要一个感知层定期刷新事实，例如：

```gdscript
func _update_perception() -> void:
	var space := get_world_2d().direct_space_state
	var query := PhysicsRayQueryParameters2D.create(
		global_position, _player.global_position, 1)   # 碰撞层 1 = 遮挡物
	var hit := space.intersect_ray(query)
	_world["player_visible"] = hit.is_empty()

	_world["player_in_melee"] = global_position.distance_to(
		_player.global_position) < 48.0
	_world["has_weapon"] = not _weapon_slot.is_empty()
	_world["ammo_full"] = _magazine == _magazine_size
```

感知可以每 0.1～0.2 秒跑一次，**不需要每帧**。GOAP 的规划开销很低，但物理查询和射线不是。

### 5.2 与 NavigationAgent2D 配合

`Approach` 这类动作不要自己算方向，直接设置 `target_position`，等 `navigation_finished` 信号。这样导航网格的避障、动态障碍处理全都白送。注意**动作成功不等于到达**：`navigation_finished` 也可能因为路径被堵而超时，此时应该让 `_execute` 返回失败，并把 `player_visible` 置为 `false`，让下一次规划换方案。

### 5.3 与动画 / 技能系统配合

把「动作」和「动画片段」一一对应是最省事的映射：一个 GOAP 动作 = 一个可被动画事件驱动的原子行为。若某个动作需要中途被打断（受击、死亡），在受击回调里清空 `_plan` 并设置对应事实即可，下一轮调度会自动重规划。

### 5.4 调试可视化

GOAP 最难调的不是代码，而是「它为什么选了这个计划」。三条低成本手段：

1. 每次规划打印 `目标 + 计划 + 使用的世界状态`（示例已做）；
2. 在屏幕上用 `draw_string` 显示当前计划队列，运行时能直接看到它在想什么；
3. 维护一个「本帧考虑过的动作」列表，规划失败时打印出来，能立刻定位是前置条件写错还是事实没刷新。

官方 Asset Library 里的 [GOAP 插件](https://godotengine.org/asset-library/asset/4888) 自带编辑器调试器，可实时查看世界状态与计划图，适合直接借鉴其调试面板的设计。

## 六、实践要点

### 6.1 状态设计决定成败

- **键太多**：状态空间按 2ⁿ 增长，规划变慢、可读性变差。控制在 6～12 个布尔事实以内，超过就说明该拆成多个子系统或分层。
- **键太抽象**：`is_combat_ready` 这种复合事实会让前置条件难以复用，尽量拆成 `has_weapon`、`ammo_full` 这种原子事实。
- **漏掉负向事实**：只有 `player_dead` 没有 `player_alive` 是可以的，但动作效果里「把某事实改回 false」必须显式写出来，否则重规划会读到过期状态。

### 6.2 动作粒度：宁可小，不要大

一个动作只做一件可观测的事。`KillPlayer` 这种「一动作达成目标」的写法在 Demo 里没问题，在项目里会让 AI 完全失去规划的意义。拆成 `Approach → Aim → Fire → Reload` 之后，成本差异和条件耦合才会真正体现出来。

### 6.3 成本要能动态变化

成本不必是常量。距离、暴露度、剩余弹药都可以参与：

```gdscript
func _cost_of(action) -> float:
	var c: float = action.cost
	if action.id == "Approach":
		c *= global_position.distance_to(_player.global_position) / 128.0
	return c
```
这样 AI 在远处会倾向远程手段、近处才考虑贴脸，行为自然很多。

### 6.4 重规划要节流

每次感知刷新都重规划是浪费。常见做法：

- 只在**下一个动作不可用**时重规划（示例做法，最省）；
- 或给世界状态算哈希，变化超过阈值才重规划；
- 高优先级目标达成/失效时强制重规划。

### 6.5 常见坑

| 现象 | 原因 | 处理 |
|---|---|---|
| 规划返回空、AI 站着不动 | 动作的前置条件互相死锁 | 打印所有动作的 `pre`，检查是否有事实永远无法变 true |
| AI 反复执行同一动作 | 动作效果没有真正改变状态 | 确保 `apply()` 写入的效果与目标事实一致 |
| 计划执行到一半卡住 | 执行器没有 `await`，动作瞬间“完成” | 每个动作都要等一个真实信号或计时 |
| 状态越跑越乱 | 世界状态被多处以不同方式修改 | 只允许感知层与 `action.apply()` 写 `_world` |

### 6.6 什么时候不该用 GOAP

行为种类少于 10 个、顺序基本固定的场景（比如平台跳跃游戏的巡逻兵），FSM 更简单也更好调试。GOAP 的收益来自「组合爆炸」和「动态重排」——没有这两点，它只是给你多加了一层间接。

## 七、延伸阅读

- [GOAP — Godot Asset Library](https://godotengine.org/asset-library/asset/4888)：纯 GDScript、零依赖的 Godot 4 GOAP 插件，含反向链式 A\* 规划器、优先级目标选择、运行时重规划与编辑器调试器，附可运行的生存示例。
- [godot-goap — RodZill4](https://godotassetstore.org/assets/scripts/gh:RodZill4:godot-goap)：另一个轻量实现，代码短，适合通读理解「世界状态 + 前置条件 + 效果」的最小结构。
- [Exploring Goal Oriented Action Planning — Bentebent](https://bentebent.github.io/posts/goap/)：从 `CheckPreconditions` 讲起，把规划器的数据结构和搜索流程拆得很清楚。
- [Three States and a Plan: The AI of F.E.A.R. — Jeff Orkin, GDC 2005](https://web.cs.wpi.edu/~rich/courses/imgd4100-b11/lectures/L-Planning.pdf)：GOAP 在商业游戏里落地的经典演讲，STRIPS 规划与 FSM 的分工讲得最透。
- [Building the AI of F.E.A.R. with GOAP — Game History](https://gamehistory.com/design/building-the-ai-of-f-e-a-r-with-goal-oriented-action-planning)：回顾 F.E.A.R. 的开发历程，理解「规划器 = 自己写自己的状态机」这句话的上下文。
- [Godot 4 导航文档](https://docs.godotengine.org/en/stable/tutorials/navigation/index.html)：把示例里的 `Approach` 换成真实 `NavigationAgent2D` 寻路时的官方参考。
