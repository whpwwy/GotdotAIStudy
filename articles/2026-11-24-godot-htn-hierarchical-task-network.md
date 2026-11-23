# Godot 4 分层任务网络实战：用 HTN 让敌人自己拆解行动序列

- **日期**：2026-11-24（Asia/Shanghai）
- **引擎版本**：Godot 4.x（本文以 Godot 4.4.1 验证，GDScript）
- **难度**：进阶（无需插件、训练数据或外部服务）
- **主题关键词**：HTN、分层任务网络、Hierarchical Task Network、compound task、primitive task、method、任务分解、回滚 rollback
- **来源链接**：
  - [cite:1] [Game AI Pro 第 12 章：Exploring HTN Planners through Example](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter12_Exploring_HTN_Planners_through_Example.pdf)
  - [cite:2] [UMCP：A Sound and Complete Procedure for Hierarchical Task-Network Planning（Erol, Nau, Subrahmanian）](http://www.cs.umd.edu/~nau/papers/erol1994umcp.pdf)
  - [cite:3] [Fluid HTN（Godot 4.1 ~ 4.6）—— Godot 官方资产库](https://godotengine.org/asset-library/asset/2944)
  - [cite:4] [fnaith/godot-fluid-hierarchical-task-network（GitHub 源码）](https://github.com/fnaith/godot-fluid-hierarchical-task-network)

> 本文与历史文章的边界：此前文章覆盖了 GOAP（目标回归，用 A\* 在状态空间里向目标搜索动作序列）、行为树（每帧从根节点向下 tick）、Utility AI（给候选动作打分选最高）、MCTS（随机模拟统计）。本文不写“满足哪个目标状态”、不维护行为节点的运行时状态、不给动作打分、也不做随机模拟；而是从一个抽象的**复合任务**出发，用**方法**把它递归拆成更小的子任务，直到全部变成可执行的**原语任务**，形成一个行动序列。这里的“层级”是任务之间的分解关系，不是行为树的父子节点。

---

## 一、为什么用一个士兵 AI 理解 HTN

分层任务网络（Hierarchical Task Network，HTN）是经典的 AI 规划方法：它不直接问“我要达到什么世界状态”，而是问“我现在要完成哪个任务，这个任务可以拆成哪些子任务”。每个**复合任务**有若干种**方法**，每种方法在满足适用条件时给出一个子任务列表；规划器不断分解，直到只剩下**原语任务**（可直接执行、会改变世界状态的动作），就得到一个计划。[cite:1][cite:2]

用一个士兵 AI 来理解它最直观：

- 顶层任务 `be_soldier`：如果发现了敌人就交战，否则去巡逻；
- `engage_enemy`：在射程内且有弹药就解决战斗，在射程内但没弹药就先补给，不在射程内就先移动再交战；
- `resolve_combat`：先尝试远程狙杀，没命中就回滚到近战攻击；
- `patrol`：走到下一个巡逻点，然后扫描周围。

这些描述天然就是“任务 → 子任务”的层级，写出来几乎和策划文档一致。Game AI Pro 第 12 章用“Trunk Thumper”敌人展示了同样的思路：抽象任务 `AttackEnemy` 有多种分解方式，规划器负责在当前世界状态下挑出一条可行的分解链。[cite:1]

HTN 不是银弹。它的表达力来自人工编写的方法，方法写死了“怎么做”；当目标是方法没覆盖的新情形时，它不会像 GOAP 那样自动搜索出全新的动作组合。它的优势是：**计划速度快、行为可预期、层级结构与设计文档同构**，非常适合敌人日常行为、NPC 日程、任务系统等“知道该怎么做、只想让 AI 按当前情况挑一条路”的场景。

---

## 二、核心概念：任务、方法、分解与回滚

一个最小可用的 HTN 规划器只有四个核心元素。[cite:1]

| 元素 | 要解决的问题 | 本文实现 |
|---|---|---|
| 原语任务 Primitive Task | 能直接执行、会改变世界状态的动作 | `Operator`：有 `applicable(state)` 和 `execute(state)`，返回是否成功 |
| 复合任务 Compound Task | 抽象目标，不能直接执行，必须分解 | 以任务名为键登记在 `methods` 里 |
| 方法 Method | 在什么条件下，可以把复合任务拆成哪些子任务 | `Method`：`applicable(state)` + `subtasks`（子任务名数组） |
| 分解 + 回滚 Decompose & Rollback | 子任务走不通时，恢复状态试下一种方法 | 尝试方法前对状态做快照，失败则还原 |

### 2.1 原语任务与复合任务

- **原语任务**对应游戏里的原子动作：移动、攻击、装填、扫描。它有两个判断：`applicable`（当前状态下能不能做）和 `execute`（做了之后怎么改状态、成不成功）。例如 `attack` 只有在“有目标、目标在射程内、有弹药”时才适用，执行后消耗一发弹药并消灭目标。
- **复合任务**是抽象指令：`be_soldier`、`engage_enemy`、`patrol`。它自己不改状态，只提供若干种分解方法。

### 2.2 方法：把复合任务拆成子任务

方法 = 适用条件 + 子任务序列。比如 `engage_enemy` 有三种方法：

1. 有目标、在射程内、有弹药 → `[resolve_combat]`
2. 有目标、在射程内、没弹药 → `[resupply_ammo, resolve_combat]`
3. 有目标、不在射程内 → `[move_to_target, engage_enemy]`（递归分解自己）

规划器按顺序尝试方法，第一个适用且能完整分解到底的方法胜出。子任务既可以是原语，也可以是另一个复合任务，因此分解是递归的。

### 2.3 分解与回滚：为什么要保存状态快照

分解过程中，原语的 `execute` 会修改状态。如果一条分解链在某个子任务上失败（例如 `long_range_shot` 未命中返回 `false`），前面已经施加的状态变化必须**撤销**，否则后续尝试的方法会在一个被污染的状态上判断条件，得到错误结论。[cite:1]

本文的做法是：每尝试一个方法前，对状态做一次深拷贝作为快照；如果该方法的任意子任务失败，就把状态还原成快照，再试下一个方法。这正是 HTN 规划里“回溯/回滚”的核心。

### 2.4 HTN 与 GOAP 的关键区别

| 维度 | HTN（本文） | GOAP（历史文章） |
|---|---|---|
| 出发点 | 一个要完成的**任务** | 一个要满足的**目标状态** |
| 搜索方向 | 任务递归分解（task decomposition） | 动作前向/后向搜索（goal regression） |
| 领域知识载体 | 方法（怎么拆任务） | 动作的前置条件与效果 |
| 能否想出新组合 | 受限于已写方法 | 可在状态空间搜索出未预设的动作链 |
| 规划成本 | 通常更低、更可控 | 状态空间大时可能昂贵 |
| 适合 | 敌人日常行为、NPC 日程、脚本化层级 | 需要灵活达成目标、探索动作组合 |

两者并不互斥：大型项目常用 HTN 做上层行为编排，在某个复合任务的叶子节点调用 GOAP 或 Utility AI 做局部决策。

---

## 三、单文件可运行示例

### 3.1 运行方法

1. 新建 Godot 4 项目和一个 2D 场景，根节点选择 `Node2D`；
2. 新建 `htn_soldier.gd`，粘贴下面完整代码并挂到根节点；
3. 按 F5 运行。会自动生成一个计划并逐步执行，画面显示巡逻点、士兵、目标、当前计划与执行日志；
4. 按 **空格** 基于当前世界状态重新规划并执行；按 **B** 切换“弹药箱是否在附近”，观察 `resupply_ammo` 选择拾取还是装填。

示例用固定随机种子，便于复现。`long_range_shot` 有 40% 命中率，未命中会返回失败，用来演示**回滚**：规划阶段会撤销弹药消耗并改用 `attack`。

### 3.2 完整 GDScript

```gdscript
extends Node2D
## Godot 4.x：HTN 分层任务网络单文件示例。
## 新建 Node2D 根节点并挂载本脚本，按 F5 运行；
## 空格：重新规划并执行；B：切换弹药箱是否临近。

const K_HAS_TARGET := "has_target"
const K_TARGET_IN_RANGE := "target_in_range"
const K_HAS_AMMO := "has_ammo"
const K_AMMO := "ammo"
const K_MAX_AMMO := 3
const K_AMMO_BOX_NEARBY := "ammo_box_nearby"
const K_PATROL_INDEX := "patrol_index"
const K_PATROL_COUNT := 4
const K_TARGET_ALIVE := "target_alive"

const TICK_INTERVAL := 0.7
const LOG_MAX := 12

var rng := RandomNumberGenerator.new()
var world_state: Dictionary = {}
var operators: Dictionary = {}   # String -> Operator
var methods: Dictionary = {}     # String -> Array[Method]
var plan: Array = []
var plan_step := 0
var executing := false
var tick_accum := 0.0
var log_lines: Array[String] = []


class Operator:
	var name: String
	var applicable_fn: Callable
	var execute_fn: Callable
	func _init(p_name: String, p_app: Callable, p_exe: Callable) -> void:
		name = p_name
		applicable_fn = p_app
		execute_fn = p_exe
	func applicable(state: Dictionary) -> bool:
		return applicable_fn.call(state)
	func execute(state: Dictionary) -> bool:
		return execute_fn.call(state)


class Method:
	var name: String
	var applicable_fn: Callable
	var subtasks: Array
	func _init(p_name: String, p_app: Callable, p_subs: Array) -> void:
		name = p_name
		applicable_fn = p_app
		subtasks = p_subs
	func applicable(state: Dictionary) -> bool:
		return applicable_fn.call(state)


func _ready() -> void:
	rng.seed = 20261124
	world_state = {
		K_HAS_TARGET: false,
		K_TARGET_IN_RANGE: false,
		K_HAS_AMMO: true,
		K_AMMO: K_MAX_AMMO,
		K_AMMO_BOX_NEARBY: false,
		K_PATROL_INDEX: 0,
		K_TARGET_ALIVE: true,
	}
	_build_operators()
	_build_methods()
	_run_planner()
	queue_redraw()


# ---------------- 原语任务（算子） ----------------

func _build_operators() -> void:
	operators["scan_for_target"] = Operator.new(
		"scan_for_target",
		func(_s: Dictionary) -> bool: return true,
		func(s: Dictionary) -> bool:
			s[K_HAS_TARGET] = true
			s[K_TARGET_IN_RANGE] = false
			s[K_TARGET_ALIVE] = true
			return true
	)
	operators["move_to_target"] = Operator.new(
		"move_to_target",
		func(s: Dictionary) -> bool:
			return s[K_HAS_TARGET] and not s[K_TARGET_IN_RANGE],
		func(s: Dictionary) -> bool:
			s[K_TARGET_IN_RANGE] = true
			return true
	)
	operators["long_range_shot"] = Operator.new(
		"long_range_shot",
		func(s: Dictionary) -> bool:
			return s[K_HAS_TARGET] and s[K_TARGET_IN_RANGE] and s[K_HAS_AMMO],
		func(s: Dictionary) -> bool:
			s[K_AMMO] = int(s[K_AMMO]) - 1
			if int(s[K_AMMO]) <= 0:
				s[K_HAS_AMMO] = false
			# 40% 命中消灭目标；未命中返回失败，触发回滚。
			if rng.randf() < 0.4:
				s[K_HAS_TARGET] = false
				s[K_TARGET_ALIVE] = false
				return true
			return false
	)
	operators["attack"] = Operator.new(
		"attack",
		func(s: Dictionary) -> bool:
			return s[K_HAS_TARGET] and s[K_TARGET_IN_RANGE] and s[K_HAS_AMMO],
		func(s: Dictionary) -> bool:
			s[K_AMMO] = int(s[K_AMMO]) - 1
			if int(s[K_AMMO]) <= 0:
				s[K_HAS_AMMO] = false
			s[K_HAS_TARGET] = false
			s[K_TARGET_ALIVE] = false
			return true
	)
	operators["reload"] = Operator.new(
		"reload",
		func(s: Dictionary) -> bool:
			return not s[K_HAS_AMMO],
		func(s: Dictionary) -> bool:
			s[K_AMMO] = K_MAX_AMMO
			s[K_HAS_AMMO] = true
			return true
	)
	operators["pickup_ammo_box"] = Operator.new(
		"pickup_ammo_box",
		func(s: Dictionary) -> bool:
			return s[K_AMMO_BOX_NEARBY],
		func(s: Dictionary) -> bool:
			s[K_AMMO] = K_MAX_AMMO
			s[K_HAS_AMMO] = true
			s[K_AMMO_BOX_NEARBY] = false
			return true
	)
	operators["advance_to_next_patrol_point"] = Operator.new(
		"advance_to_next_patrol_point",
		func(_s: Dictionary) -> bool: return true,
		func(s: Dictionary) -> bool:
			s[K_PATROL_INDEX] = (int(s[K_PATROL_INDEX]) + 1) % K_PATROL_COUNT
			return true
	)


# ---------------- 复合任务的方法 ----------------

func _build_methods() -> void:
	methods["be_soldier"] = [
		Method.new("有敌人时交战",
			func(s: Dictionary) -> bool: return s[K_HAS_TARGET],
			["engage_enemy"]),
		Method.new("巡逻搜索",
			func(_s: Dictionary) -> bool: return true,
			["patrol"]),
	]
	methods["engage_enemy"] = [
		Method.new("射程内有弹药",
			func(s: Dictionary) -> bool:
				return s[K_HAS_TARGET] and s[K_TARGET_IN_RANGE] and s[K_HAS_AMMO],
			["resolve_combat"]),
		Method.new("射程内缺弹药",
			func(s: Dictionary) -> bool:
				return s[K_HAS_TARGET] and s[K_TARGET_IN_RANGE] and not s[K_HAS_AMMO],
			["resupply_ammo", "resolve_combat"]),
		Method.new("接敌移动",
			func(s: Dictionary) -> bool:
				return s[K_HAS_TARGET] and not s[K_TARGET_IN_RANGE],
			["move_to_target", "engage_enemy"]),
	]
	methods["resolve_combat"] = [
		Method.new("尝试远程狙杀",
			func(_s: Dictionary) -> bool: return true,
			["long_range_shot"]),
		Method.new("稳妥近战",
			func(_s: Dictionary) -> bool: return true,
			["attack"]),
	]
	methods["resupply_ammo"] = [
		Method.new("拾取弹药箱",
			func(s: Dictionary) -> bool: return s[K_AMMO_BOX_NEARBY],
			["pickup_ammo_box"]),
		Method.new("装填弹药",
			func(_s: Dictionary) -> bool: return true,
			["reload"]),
	]
	methods["patrol"] = [
		Method.new("巡逻",
			func(_s: Dictionary) -> bool: return true,
			["advance_to_next_patrol_point", "scan_area"]),
	]
	methods["scan_area"] = [
		Method.new("扫描",
			func(_s: Dictionary) -> bool: return true,
			["scan_for_target"]),
	]


# ---------------- HTN 规划器：分解 + 回滚 ----------------

func make_plan(root_task: String, state: Dictionary) -> Array:
	var working: Dictionary = state.duplicate(true)
	var result: Array = []
	if _decompose(root_task, working, result):
		return result
	return []


func _decompose(task_name: String, state: Dictionary, out_plan: Array) -> bool:
	# 原语任务：校验适用条件，执行并记录。
	if operators.has(task_name):
		var op: Operator = operators[task_name]
		if not op.applicable(state):
			return false
		if op.execute(state):
			out_plan.append(task_name)
			return true
		return false
	# 复合任务：依次尝试每种方法，失败则回滚。
	if not methods.has(task_name):
		return false
	for method in methods[task_name]:
		if not method.applicable(state):
			continue
		var snapshot: Dictionary = state.duplicate(true)
		var branch: Array = []
		var success := true
		for sub in method.subtasks:
			if not _decompose(sub, state, branch):
				success = false
				break
		if success:
			out_plan.append_array(branch)
			return true
		# 回滚：把状态恢复到尝试该方法之前。
		state.clear()
		for key in snapshot:
			state[key] = snapshot[key]
	return false


# ---------------- 规划与执行 ----------------

func _run_planner() -> void:
	var new_plan := make_plan("be_soldier", world_state)
	if new_plan.is_empty():
		log("规划失败：be_soldier 无法分解")
		return
	plan = new_plan
	plan_step = 0
	executing = true
	log("—— 新计划（%d 步）——" % plan.size())
	for i in plan.size():
		log("  %d. %s" % [i + 1, plan[i]])


func _process(delta: float) -> void:
	if not executing:
		return
	tick_accum += delta
	if tick_accum < TICK_INTERVAL:
		return
	tick_accum = 0.0
	_execute_next_step()
	queue_redraw()


func _execute_next_step() -> void:
	if plan_step >= plan.size():
		executing = false
		log("计划执行完毕。按空格基于当前状态重新规划。")
		return
	var task_name: String = plan[plan_step]
	var op: Operator = operators[task_name]
	# 真实世界在规划后可能已变化，执行前重新校验适用条件。
	if not op.applicable(world_state):
		log("执行中断：%s 已不再适用，触发重新规划" % task_name)
		plan.clear()
		plan_step = 0
		executing = false
		_run_planner()
		return
	var ok := op.execute(world_state)
	log("执行 [%d/%d] %s => %s" % [
		plan_step + 1, plan.size(), task_name, "成功" if ok else "失败"
	])
	plan_step += 1
	if not ok:
		log("原语失败，中止当前计划并重新规划")
		plan.clear()
		plan_step = 0
		executing = false
		_run_planner()


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			_run_planner()
			queue_redraw()
		elif event.keycode == KEY_B:
			world_state[K_AMMO_BOX_NEARBY] = not world_state[K_AMMO_BOX_NEARBY]
			log("切换 ammo_box_nearby = %s" % str(world_state[K_AMMO_BOX_NEARBY]))
			queue_redraw()


# ---------------- 日志与绘制 ----------------

func log(msg: String) -> void:
	log_lines.append(msg)
	while log_lines.size() > LOG_MAX:
		log_lines.pop_front()
	print(msg)


func _draw() -> void:
	var font := ThemeDB.fallback_font
	draw_string(font, Vector2(40, 40), "Godot 4 | HTN 分层任务网络",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 26, Color(0.92, 0.95, 1.0))
	var state_line := "has_target=%s in_range=%s ammo=%d/%d box=%s patrol=%d" % [
		str(world_state.get(K_HAS_TARGET, false)),
		str(world_state.get(K_TARGET_IN_RANGE, false)),
		int(world_state.get(K_AMMO, 0)),
		K_MAX_AMMO,
		str(world_state.get(K_AMMO_BOX_NEARBY, false)),
		int(world_state.get(K_PATROL_INDEX, 0)),
	]
	draw_string(font, Vector2(40, 68), state_line,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.7, 0.8, 0.92))
	draw_string(font, Vector2(40, 92), "空格：重新规划并执行    B：切换弹药箱临近",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 15, Color(0.55, 0.65, 0.8))

	# 巡逻点与士兵
	var origin := Vector2(60, 150)
	var spacing := 110
	for i in K_PATROL_COUNT:
		var center := origin + Vector2(i * spacing, 0)
		var is_current := int(world_state.get(K_PATROL_INDEX, 0)) == i
		draw_circle(center, 26.0, Color(0.2, 0.28, 0.4) if is_current else Color(0.12, 0.15, 0.22))
		draw_arc(center, 26.0, 0.0, TAU, 32, Color(0.42, 0.52, 0.66), 2.0, true)
		draw_string(font, center + Vector2(-8, 5), "P%d" % i,
			HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.8, 0.88, 1.0))
	var soldier_pos := origin + Vector2(int(world_state.get(K_PATROL_INDEX, 0)) * spacing, -6)
	draw_circle(soldier_pos, 12.0, Color(0.3, 0.9, 0.55))
	if bool(world_state.get(K_HAS_TARGET, false)):
		var target_pos := soldier_pos + Vector2(0, -50)
		draw_circle(target_pos, 10.0, Color(0.95, 0.35, 0.35))
		draw_string(font, target_pos + Vector2(8, 4), "目标",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.95, 0.7, 0.7))

	# 当前计划
	draw_string(font, Vector2(40, 220), "当前计划：",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.85, 0.9, 1.0))
	for i in plan.size():
		var y := 250 + i * 24
		var done := i < plan_step
		var current := i == plan_step and executing
		var color := Color(0.7, 0.85, 0.6) if done else (Color(1.0, 0.95, 0.5) if current else Color(0.7, 0.75, 0.85))
		var mark := "✓ " if done else ("> " if current else "  ")
		draw_string(font, Vector2(56, y), "%s%s" % [mark, plan[i]],
			HORIZONTAL_ALIGNMENT_LEFT, -1, 15, color)

	# 执行日志
	draw_string(font, Vector2(330, 220), "执行日志：",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.85, 0.9, 1.0))
	for i in log_lines.size():
		draw_string(font, Vector2(330, 250 + i * 20), log_lines[i],
			HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(0.72, 0.78, 0.88))
```

### 3.3 代码导读

- **规划器与领域知识解耦**：`operators` 和 `methods` 描述“这个士兵会什么、任务怎么拆”；`make_plan()` / `_decompose()` 完全不认识具体任务名，只负责递归分解和回滚。换一个 NPC 时，替换这两张表即可，规划器不用改。
- **状态必须深拷贝**：`make_plan()` 先 `world_state.duplicate(true)`，规划过程只改副本；`_decompose()` 每尝试一个方法再做一次快照。两层拷贝保证：真实世界不被规划污染，失败分支能完整回滚。
- **回滚是 HTN 正确性的关键**：`resolve_combat` 先试 `long_range_shot`，未命中时 `execute` 返回 `false`，`_decompose` 会把状态恢复到方法尝试前（弹药被加回去），再试 `attack`。没有这步，弹药会在规划阶段被错误地扣掉。
- **规划与执行分离**：计划只是一串原语名字。执行时（`_execute_next_step`）对真实世界重新校验 `applicable`，若世界已变化则丢弃旧计划重新规划——这是“反应式重规划”，而不是拿着过期计划硬执行。
- **递归分解**：`engage_enemy` 的“接敌移动”方法把子任务写成 `[move_to_target, engage_enemy]`，规划器会再次进入 `engage_enemy`，最终停在原语上，形成 `[move_to_target, ...]` 的完整链。

---

## 四、先验证规划器，再接入行为

HTN 的 bug 往往藏在“状态没回滚”或“方法适用条件写反”里，表现为计划偶尔多走一步、偶尔少扣弹药。建议先用确定状态做断言。

### 4.1 三个最小断言

把下面函数加到脚本里，临时在 `_ready()` 末尾调用 `_run_planner_tests()`，通过后移除。

```gdscript
func _run_planner_tests() -> void:
	# 1) 有目标、在射程内、有弹药：不应出现 move_to_target。
	var s1 := {K_HAS_TARGET: true, K_TARGET_IN_RANGE: true, K_HAS_AMMO: true, K_AMMO: 3}
	var p1 := make_plan("be_soldier", s1)
	assert(not p1.is_empty(), "有目标时应能规划")
	assert(not p1.has("move_to_target"), "已在射程内不应移动")

	# 2) 有目标但不在射程内：计划必须包含 move_to_target。
	var s2 := {K_HAS_TARGET: true, K_TARGET_IN_RANGE: false, K_HAS_AMMO: true, K_AMMO: 3}
	var p2 := make_plan("be_soldier", s2)
	assert(p2.has("move_to_target"), "不在射程内应先移动")

	# 3) 无目标：应走巡逻分支，包含 advance_to_next_patrol_point。
	var s3 := {K_HAS_TARGET: false}
	var p3 := make_plan("be_soldier", s3)
	assert(p3.has("advance_to_next_patrol_point"), "无目标时应巡逻")

	# 4) 回滚验证：传入规划的状态在 make_plan 后不应被修改。
	var before := s3.duplicate(true)
	make_plan("be_soldier", s3)
	assert(s3 == before, "规划不应污染传入状态")
	print("HTN 规划器最小测试通过")
```

断言失败时 Godot 调试器会停在对应行，比“看 AI 行为不对劲”容易定位得多。注意第 4 条尤其重要：一旦发现 `make_plan` 改了输入状态，说明某处漏掉了 `duplicate(true)`。

### 4.2 一个常见的回滚错误

如果只在 `make_plan` 入口做一次状态拷贝、而在每个方法尝试前不做快照，那么：

- `resolve_combat` 试 `long_range_shot` 失败后，弹药已经被扣掉；
- 接着试 `attack` 时，`applicable` 判断“有弹药”可能已经是 `false`，于是整个复合任务失败；
- 表现为“明明有弹药却无法攻击”，而且时好时坏，极难排查。

正确做法就是本文的两层快照：入口拷贝隔离真实世界，方法级快照隔离兄弟方法。

---

## 五、实践要点与性能边界

### 5.1 规划与执行分离，世界会变

规划得到的是一张“快照上的处方”。执行期间玩家可能移动、目标可能死亡、弹药可能被别的逻辑改掉。因此：

- 执行每个原语前都要重新校验 `applicable`（本文已做）；
- 关键状态变化（目标消失、受伤）应主动触发重规划，而不是等到某个原语失败；
- 计划执行频率不必每帧一次；通常按固定间隔（如 0.5s）或事件触发即可，把规划成本摊薄。

### 5.2 控制方法数量与递归深度

方法越多、分解越深，回溯成本越高。本文是全序（totally ordered）方法，子任务按数组顺序执行；若引入偏序（部分任务可并行），还需处理任务间约束，复杂度明显上升。对游戏 AI 而言，常见做法是：

- 顶层 2~3 层复合任务足够覆盖日常行为；
- 把高频、低风险的反应（被击中、听到声音）交给状态机或感知系统，不让它们进入规划器；
- 给规划加一个最大递归深度或最大节点数上限，防止方法互相递归导致死循环（例如 `engage_enemy` 调自己时，必须保证每轮都有原语推进状态，否则要加保护）。

### 5.3 何时用 HTN，何时不用

- **适合**：敌人/友军的日常行为、NPC 日程与任务链、脚本化但需要按当前情况选分支的关卡 AI、需要“可解释计划”的系统（策划能读懂 `[move_to_target, attack]`）。
- **不太适合**：需要凭空探索新动作组合的开放目标（用 GOAP）、需要在连续空间里实时权衡的局部决策（用 Utility AI / 转向行为）、纯反应式追逐闪避（用状态机）。

Game AI Pro 的案例和 Godot 资产库中的 Fluid HTN 都证明了：HTN 特别适合“行为层级清晰、想保留人工设计感、又希望 AI 能根据状态自己挑路”的中型敌人 AI。[cite:1][cite:3]

---

## 六、把示例迁移到自己的敌人 AI

推荐按以下顺序改造：

1. 先把世界状态收敛成一个小的 `Dictionary`（或自定义 `WorldState` 类），只放规划真正关心的键；
2. 用“设计文档里的动词”命名复合任务（`be_soldier`、`guard_area`、`flee`），先写方法再写原语，保持命名与设计一致；
3. 给每个原语写 `applicable` + `execute`，并规定 `execute` 的副作用只改状态、不碰场景节点；
4. 用确定状态写断言验证分解与回滚，再接入真实执行循环；
5. 执行阶段负责把原语映射成动画/移动/特效（例如 `move_to_target` 触发 `NavigationAgent2D` 寻路），规划器保持纯逻辑、可单测；
6. 复杂项目可在原语层接入 GOAP/Utility AI，让 HTN 管上层编排、下层规划器管局部决策。

Fluid HTN 用 Builder 模式把任务、方法、算子串成可读的声明式结构，并支持运行时域修改，可作为工程化实现的参考。[cite:3][cite:4]

---

## 七、延伸阅读

- [cite:1] [Game AI Pro 第 12 章：Exploring HTN Planners through Example](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter12_Exploring_HTN_Planners_through_Example.pdf)：用“Trunk Thumper”敌人逐步拆解 HTN 规划器的实现，是游戏开发者最友好的入门材料。
- [cite:2] [UMCP：A Sound and Complete Procedure for HTN Planning](http://www.cs.umd.edu/~nau/papers/erol1994umcp.pdf)：HTN 的经典形式化与完备性证明，理解分解、方法与回溯的理论基础。
- [cite:3] [Fluid HTN（Godot 4.1 ~ 4.6）官方资产库页面](https://godotengine.org/asset-library/asset/2944)：查看 Godot 社区现成的 HTN 插件，支持 Builder 风格声明。
- [cite:4] [fnaith/godot-fluid-hierarchical-task-network](https://github.com/fnaith/godot-fluid-hierarchical-task-network)：阅读其 GDScript 源码，对比本文手写规划器与工程化插件在结构上的差异。

## 来源

- [cite:1] [Champandard 等：Exploring HTN Planners through Example，Game AI Pro 第 12 章](http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter12_Exploring_HTN_Planners_through_Example.pdf)
- [cite:2] [Erol, Nau, Subrahmanian：UMCP: A Sound and Complete Procedure for Hierarchical Task-Network Planning](http://www.cs.umd.edu/~nau/papers/erol1994umcp.pdf)
- [cite:3] [Fluid HTN — Godot Asset Library](https://godotengine.org/asset-library/asset/2944)
- [cite:4] [fnaith：godot-fluid-hierarchical-task-network（GitHub）](https://github.com/fnaith/godot-fluid-hierarchical-task-network)
