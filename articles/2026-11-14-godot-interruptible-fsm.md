# Godot AI 有限状态机：用 enter/exit 与历史状态实现可中断 AI

> **日期**：2026-11-14  
> **适用版本**：Godot 4.x  
> **主题**：有限状态机（FSM）、状态生命周期、中断与恢复  
> **主要来源**：
> - [Managing AI and Player States with a State Machine — UhiyamaLab](https://uhiyama-lab.com/en/notes/godot/state-machine-ai-player/)
> - [Godot 4 State Machine Tutorial: The Pattern Every Game Needs — Coding Quests](https://www.codingquests.io/blog/godot-4-state-machine-tutorial)

---

## 一、有限状态机解决什么问题？

NPC 同时只有“巡逻”“警戒”“眩晕”中的一种状态时，用一个 `current_state` 表达它，往往比维护 `is_patrolling`、`is_alerted`、`is_stunned` 等多个布尔值更可靠。布尔组合可能出现“既警戒又眩晕”的矛盾，而**有限状态机（Finite State Machine，FSM）要求任一时刻只有一个当前状态**，转换必须通过明确规则发生。

UhiyamaLab 的教程从 `enum + match` 讲到状态类，Coding Quests 则展示了用 `enter()`、`exit()` 和统一转换入口组织状态的方式。本文在此基础上专注一个容易踩坑的主题：**正在执行的状态被眩晕等突发事件打断后，怎样安全地恢复。**

本文示例的三个状态是：

| 状态 | 行为 | 离开条件 |
|---|---|---|
| `PATROL` | 在两个巡逻点之间移动 | 玩家进入侦测半径 |
| `ALERT` | 停下、转向玩家，延迟后发出一次警报 | 玩家离开更大的丢失半径，或被眩晕 |
| `STUNNED` | 停止移动并旋转，表示失去行动能力 | 眩晕计时结束，返回被打断前的状态 |

这里没有行为树的 Sequence/Selector，也不涉及导航寻路或群体转向力；重点是**状态本身的进入、退出和恢复语义**。

## 二、转换要走唯一入口，生命周期要有明确职责

一个可靠的转换函数通常按下面的顺序工作：

```text
_exit_state(旧状态)
        ↓
current_state = 新状态
        ↓
重置本状态计时器
        ↓
_enter_state(新状态)
```

把转换集中到 `change_state()`，可以避免某个分支忘记清理旧状态。两类生命周期函数分别适合处理：

- `enter`：播放一次进入动画、重置本状态计时、初始化“本状态是否已经报警”等标记。
- `exit`：停止音效、清理临时效果、恢复旋转或修正其他仅属于该状态的视觉表现。

每帧持续执行移动和判断的代码则放在 `_update_*()` 中。这样，“进入时只执行一次”和“激活期间每帧执行”不会混在一起。

## 三、最小可运行场景

新建一个 2D 场景，只需三个节点，不需要图片、碰撞体或输入映射配置：

```text
Main (Node2D)
├─ Player (Node2D)  ← 挂载 player.gd
└─ Enemy (Node2D)   ← 挂载 enemy.gd
```

在 Inspector 中把 `Player` 的位置设为 `(340, 420)`，把 `Enemy` 的位置设为 `(140, 180)`。保存并运行 `Main` 后：

1. 用方向键移动蓝色玩家；Godot 默认提供 `ui_left`、`ui_right`、`ui_up`、`ui_down`。
2. 绿色敌人会往返巡逻；靠近后，敌人变黄、转向玩家，并在 1.5 秒后打印一次警报。
3. 按空格或回车（默认 `ui_accept`）让敌人眩晕 2 秒；灰色状态结束后，它会返回被打断前的状态。

为了让示例聚焦 AI，演示使用 `Node2D` 直接更新位置。实际项目需要碰撞时，可把移动部分替换为 `CharacterBody2D.velocity` 与 `move_and_slide()`，状态机结构不变。

### player.gd

```gdscript
extends Node2D

@export var move_speed: float = 220.0

func _ready() -> void:
	add_to_group("player")

func _physics_process(delta: float) -> void:
	var input_vector := Input.get_vector(
		"ui_left", "ui_right", "ui_up", "ui_down"
	)
	position += input_vector * move_speed * delta

func _draw() -> void:
	draw_circle(Vector2.ZERO, 14.0, Color("4dabf7"))
```

### enemy.gd

```gdscript
extends Node2D

enum State { PATROL, ALERT, STUNNED }

@export var patrol_points: Array[Vector2] = [
	Vector2(140, 180),
	Vector2(520, 180)
]
@export var patrol_speed: float = 90.0
@export var arrival_distance: float = 8.0
@export var detection_radius: float = 220.0
@export var lose_target_multiplier: float = 1.25
@export var alert_delay: float = 1.5

var current_state: State = State.PATROL
var state_before_stun: State = State.PATROL
var state_time: float = 0.0
var stun_remaining: float = 0.0
var patrol_index: int = 0
var alarm_raised: bool = false
var velocity: Vector2 = Vector2.ZERO
var target: Node2D

func _ready() -> void:
	# 初始状态也必须经过 enter，保证初始化路径一致。
	_enter_state(current_state)

func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_accept"):
		stun(2.0)

func _physics_process(delta: float) -> void:
	if not is_instance_valid(target):
		target = get_tree().get_first_node_in_group("player") as Node2D

	state_time += delta
	match current_state:
		State.PATROL:
			_update_patrol()
		State.ALERT:
			_update_alert(delta)
		State.STUNNED:
			_update_stunned(delta)

	position += velocity * delta
	queue_redraw()

func change_state(next_state: State) -> void:
	if next_state == current_state:
		return

	_exit_state(current_state)
	var previous_state := current_state
	current_state = next_state
	state_time = 0.0
	_enter_state(current_state)
	print("%s -> %s" % [
		State.keys()[previous_state],
		State.keys()[current_state]
	])

func stun(duration: float) -> void:
	if current_state == State.STUNNED:
		# 连续受击只延长剩余时间，不覆盖真正的历史状态。
		stun_remaining = maxf(stun_remaining, duration)
		return

	state_before_stun = current_state
	stun_remaining = duration
	change_state(State.STUNNED)

func _enter_state(state: State) -> void:
	match state:
		State.ALERT:
			alarm_raised = false
			velocity = Vector2.ZERO
		State.STUNNED:
			velocity = Vector2.ZERO
		_:
			pass

func _exit_state(state: State) -> void:
	match state:
		State.STUNNED:
			rotation = 0.0
		_:
			pass

func _update_patrol() -> void:
	if patrol_points.is_empty():
		velocity = Vector2.ZERO
	else:
		var point := patrol_points[patrol_index]
		if global_position.distance_to(point) <= arrival_distance:
			patrol_index = (patrol_index + 1) % patrol_points.size()
			point = patrol_points[patrol_index]

		velocity = global_position.direction_to(point) * patrol_speed
		rotation = velocity.angle()

	if _target_within(detection_radius):
		change_state(State.ALERT)

func _update_alert(delta: float) -> void:
	velocity = Vector2.ZERO

	if is_instance_valid(target):
		var direction := global_position.direction_to(target.global_position)
		if direction.length_squared() > 0.001:
			rotation = lerp_angle(
				rotation,
				direction.angle(),
				1.0 - exp(-10.0 * delta)
			)

	# 丢失半径大于发现半径，避免玩家在边界时状态来回闪烁。
	if not _target_within(detection_radius * lose_target_multiplier):
		change_state(State.PATROL)
		return

	if state_time >= alert_delay and not alarm_raised:
		alarm_raised = true
		print("警报：发现入侵者！")

func _update_stunned(delta: float) -> void:
	velocity = Vector2.ZERO
	rotation += 8.0 * delta
	stun_remaining -= delta

	if stun_remaining <= 0.0:
		# 重新进入原状态，而不是直接改写 current_state。
		change_state(state_before_stun)

func _target_within(radius: float) -> bool:
	return (
		is_instance_valid(target)
		and global_position.distance_to(target.global_position) <= radius
	)

func _draw() -> void:
	var body_color := Color("51cf66")
	match current_state:
		State.ALERT:
			body_color = Color("ffd43b")
		State.STUNNED:
			body_color = Color("868e96")

	draw_arc(
		Vector2.ZERO,
		detection_radius,
		0.0,
		TAU,
		64,
		Color(1.0, 1.0, 1.0, 0.15),
		1.0,
		true
	)
	draw_circle(Vector2.ZERO, 18.0, body_color)
	draw_line(Vector2.ZERO, Vector2.RIGHT * 26.0, Color.WHITE, 2.0, true)
```

## 四、这段实现最关键的三个设计

### 1. 中断前保存状态，但重复眩晕不覆盖历史

第一次调用 `stun()` 时，先把 `PATROL` 或 `ALERT` 保存到 `state_before_stun`。如果眩晕期间再次受击，只刷新 `stun_remaining`，不再执行 `state_before_stun = current_state`。否则第二次调用会把历史写成 `STUNNED`，计时结束后就可能尝试“恢复到眩晕”，失去原来的行为。

### 2. “重新进入”与“从原进度续播”不是一回事

本例恢复时调用 `change_state(state_before_stun)`，因此是**重新进入原状态**：`state_time` 会清零，警戒状态的 `alarm_raised` 也会重新初始化。这种语义适合“被眩晕打断后重新确认威胁”。

如果设计要求从打断前的精确进度继续，例如恢复尚未播完的攻击动作，则还要保存状态内计时器、动画位置和临时数据，并使用单独的 `resume_state()`，不能简单复用 `enter`。

### 3. 发现与丢失使用不同半径，形成滞后区

玩家进入 `220` 像素时触发警戒，但要离开到 `220 × 1.25 = 275` 像素才解除警戒。两个阈值之间的区域称为**滞后区（hysteresis）**。如果进入和离开都使用同一个距离，玩家站在边界附近时，微小移动就会让 AI 在巡逻与警戒之间反复切换。

## 五、实践要点

1. **不要绕过转换入口**：业务代码调用 `change_state()`，不要直接给 `current_state` 赋值，否则 `exit` 清理和 `enter` 初始化都会被跳过。
2. **转换后及时 `return`**：如果同一帧不应继续执行旧状态逻辑，在 `change_state()` 后立即返回。本例 `_update_alert()` 返回巡逻时就是这样处理的。
3. **区分状态时间与全局时间**：`state_time` 在每次转换时清零，适合报警延迟、状态超时；冷却等跨状态计时应放在角色或独立系统中。
4. **保存真正需要的历史**：只有“中断后可恢复”的状态才需要历史。死亡这类终止状态通常应禁止被普通眩晕覆盖，可在 `stun()` 或统一的转换规则里增加优先级判断。
5. **限制每个状态的职责**：状态负责“现在做什么、何时离开”，视野射线、伤害结算、导航和动画可以交给独立节点，避免状态脚本变成新的巨型 `if` 集合。
6. **状态继续膨胀时再升级结构**：平行状态、大量共享转换或复杂优先级出现时，可以考虑分层状态机、并发状态机或行为树；不要一开始就给简单 NPC 引入过重框架。

## 六、延伸阅读

- [GDScript 基础：枚举、match 与类型语法 — Godot 官方文档](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/gdscript_basics.html)
- [使用 AnimationTree — Godot 4.4 简体中文文档](https://docs.godotengine.org/zh-cn/4.4/tutorials/animation/animation_tree.html)：了解动画状态机与本文逻辑状态机的职责差异。
- [How to Build a State Machine in Godot 4 — Ziva](https://ziva.sh/blogs/godot-state-machine)：对照阅读节点式状态机的组织方式。
