# Godot 4 敌人感知系统实战：视野锥、视线遮挡与听觉怀疑度

- **日期**：2026-11-20（Asia/Shanghai）
- **主题**：AI 感知系统、视野锥（FOV）、点积视角判定、视线遮挡、听觉感知、怀疑度
- **引擎版本**：Godot 4.3+（3D，`PhysicsDirectSpaceState3D` / `PhysicsRayQueryParameters3D`）
- **来源**：
  - [[Godot] Stealth Game Vision Systems — Building an FOV with Area3D and RayCast3D — UhiyamaLab](https://uhiyama-lab.com/en/notes/godot/stealth-fov-system/)
  - [How to make zombies that see, hear and alert each other in Godot 4 — Godot Forum](https://forum.godotengine.org/t/how-to-make-zombies-that-see-hear-and-alert-each-other-in-godot-4/147450)
  - [RayCast3D 类参考 — Godot 官方文档](https://docs.godotengine.org/en/stable/classes/class_raycast3d.html)
  - [Ray-casting 教程 — Godot 官方文档](https://docs.godotengine.org/en/stable/tutorials/physics/ray-casting.html)

---

## 一、为什么先做「感知」，再做「决策」

前面几篇已经聊过状态机、行为树、GOAP、Utility AI——它们解决的都是「**知道该做什么之后，怎么选动作**」。但在此之前还有一个更底层的问题：

> 敌人到底「知道」什么？

如果感知层只是每帧算一次 `player.global_position`，就会得到一堆反直觉的行为：隔着一堵墙穷追不舍、玩家绕到背后仍被盯着、蹲在矮墙后整个人凭空消失。**感知质量决定了 AI 是否可信**，而它恰好是最便宜、最容易见效的一环。

一篇完整的敌人感知应当拆成三件事：

| 通道 | 回答的问题 | 常用实现 |
|---|---|---|
| 视觉 | 看得到吗？ | 距离 + 视野角 + 射线遮挡 |
| 听觉 | 听到了吗？ | 噪声事件 + 半径衰减 |
| 记忆 | 刚才在哪？ | `last_known_position` + 怀疑度衰减 |

本文给出一份可直接挂到 `CharacterBody3D` 上的组件式实现，并说明如何与已有的状态机/行为树对接。

---

## 二、核心概念：三级视觉判定，从便宜到贵

视觉检测不是「一条射线打过去」那么简单。正确顺序是**由便宜到昂贵，逐级淘汰**：

### 2.1 第一级：距离

最便宜，一次 `length()` 就够。距离外的目标直接丢弃，避免后续所有计算。

### 2.2 第二级：视角（点积）

「只看前方」靠的是**点积**，而不是反三角函数：

```
dot = forward · direction
```

两个单位向量的点积等于夹角的余弦：

| 点积值 | 含义 |
|---|---|
| `1.0` | 完全正前方（0°） |
| `0.5` | 偏 60° |
| `0.0` | 正侧方（90°） |
| `-1.0` | 正后方（180°） |

所以 120° 视野（半角 60°）的阈值就是 `cos(60°) = 0.5`：**`dot >= 0.5` 才算在视野内**。一次比较代替一次 `acos`，这是 AI 里最常见的优化手法之一。

⚠️ Godot 3D 中「前方」是 **-Z**，即 `-global_basis.z`；2D 中则是 `+X`（`transform.x`），不要混用。

### 2.3 第三级：遮挡（射线）

前两级都通过后，才允许发射线。命中墙体 → 看不见；第一个命中的就是目标 → 看得见。

单条射线会漏掉「只露出头」的情况，所以实际项目通常向**头、胸、脚**各打一条，任一可见即判定为可见。

### 2.4 从「看见」到「警觉」：怀疑度

瞬间发现玩家会显得很假，也会让潜行失去乐趣。用 0–100 的**怀疑度（suspicion）** 做缓冲：

- 可见时按 `suspicion_rise` 上升，不可见时按 `suspicion_decay` 下降；
- `0` → `UNAWARE`（巡逻），`>0` → `SUSPICIOUS`（停下查看），`>=100` → `ALERT`（追击）。

这一层天然带出「躲一会儿敌人就放弃」的潜行节奏，也能把视觉和听觉**合并到同一个量表**里。

---

## 三、可运行代码

### 3.1 场景结构

```
Enemy (CharacterBody3D)          # collision_layer 无关，sight_block_mask 决定射线挡谁
├── CollisionShape3D
├── MeshInstance3D               # 模型朝向 -Z
└── EnemySenses (Node3D)         # 挂载下面的脚本，位置在脚底
```

项目设置里给 Player 加分组 `player`；建议碰撞层约定为：

- Layer 1：墙体 / 遮挡物
- Layer 2：玩家
- 其余装饰物不要放进 `sight_block_mask`

### 3.2 完整脚本 `enemy_senses.gd`

```gdscript
class_name EnemySenses
extends Node3D
## 敌人感知组件：视觉（距离/视角/遮挡）+ 听觉 + 怀疑度。
## 挂到敌人脚下，敌人本体的朝向需为 -Z。

signal spotted(target: Node3D)          # 第一次看见目标
signal lost                             # 目标从视野中消失
signal alert_level_changed(level: int)  # 警觉等级变化

enum Alert { UNAWARE, SUSPICIOUS, ALERT }

@export var sight_range: float = 15.0          # 视野距离（米）
@export var fov_degrees: float = 120.0         # 水平视野角（度）
@export var eye_height: float = 1.6            # 眼睛离地高度
@export var close_aware_radius: float = 1.5    # 贴脸时无视背后的死角
@export_flags_3d_physics var sight_block_mask: int = 1  # 遮挡层（默认 Layer 1 墙体）

@export var suspicion_rise: float = 60.0       # 看见时每秒上升
@export var suspicion_decay: float = 20.0      # 失去目标时每秒下降
@export var alert_threshold: float = 100.0
@export var sense_interval: float = 0.2        # 感知 tick 间隔（秒）
@export var player_group: StringName = &"player"

# 射线采样点：相对目标脚底原点的偏移
const SAMPLE_OFFSETS: Array[Vector3] = [
	Vector3(0.0, 1.7, 0.0),  # 头
	Vector3(0.0, 1.0, 0.0),  # 胸
	Vector3(0.0, 0.1, 0.0),  # 脚
]

var last_known_position := Vector3.ZERO
var suspicion := 0.0
var alert_level: int = Alert.UNAWARE

var _visible_target: Node3D = null
var _timer: Timer

func _ready() -> void:
	last_known_position = global_position
	_timer = Timer.new()
	_timer.wait_time = sense_interval
	_timer.autostart = true
	_timer.timeout.connect(_scan)
	add_child(_timer)

func _physics_process(delta: float) -> void:
	# 用上一次扫描的缓存结果累积怀疑度，避免每帧做射线检测
	_update_suspicion(_visible_target != null, delta)

# ---------------------------------------------------------------- 听觉

func hear_noise(origin: Vector3, radius: float) -> void:
	if alert_level == Alert.ALERT:
		return
	if global_position.distance_to(origin) > radius:
		return
	last_known_position = origin
	# 声音只把怀疑度推到「可疑」，不会立刻锁定玩家
	suspicion = maxf(suspicion, alert_threshold * 0.35)

# ---------------------------------------------------------------- 视觉

func _scan() -> void:
	var found: Node3D = null
	for node in get_tree().get_nodes_in_group(player_group):
		if node != self and node is Node3D and _can_see(node):
			found = node
			break

	if found != _visible_target:
		_visible_target = found
		if found != null:
			spotted.emit(found)
		else:
			lost.emit()

	if _visible_target != null:
		last_known_position = _visible_target.global_position

func _can_see(target: Node3D) -> bool:
	var to_target := target.global_position - global_position
	var flat := Vector3(to_target.x, 0.0, to_target.z)
	var distance := flat.length()

	# 1) 距离（最便宜）
	if distance > sight_range:
		return false

	# 2) 视角（点积）——贴脸时允许 360° 感知
	if distance > close_aware_radius and flat.length_squared() > 0.0001:
		var forward := -global_basis.z
		forward.y = 0.0
		var cos_half := cos(deg_to_rad(fov_degrees * 0.5))
		if forward.normalized().dot(flat.normalized()) < cos_half:
			return false

	# 3) 遮挡（最贵，放到最后）
	return _has_line_of_sight(target)

func _has_line_of_sight(target: Node3D) -> bool:
	var space := get_world_3d().direct_space_state
	var eye := global_position + Vector3.UP * eye_height

	# 排除自身刚体，避免射线从身体内部出发就撞到自己
	var exclude: Array[RID] = []
	var body := owner as CollisionObject3D
	if body != null:
		exclude.append(body.get_rid())

	for offset in SAMPLE_OFFSETS:
		var point := target.global_position + offset
		var query := PhysicsRayQueryParameters3D.create(
			eye, point, sight_block_mask, exclude
		)
		var hit := space.intersect_ray(query)
		# 没挡住，或第一个挡住的就是目标本身 → 视为可见
		if hit.is_empty() or hit.collider == target:
			return true
	return false

# ---------------------------------------------------------------- 怀疑度

func _update_suspicion(can_see: bool, delta: float) -> void:
	if can_see:
		suspicion = minf(suspicion + suspicion_rise * delta, alert_threshold)
	else:
		suspicion = maxf(suspicion - suspicion_decay * delta, 0.0)

	var next := Alert.UNAWARE
	if suspicion >= alert_threshold - 0.001:
		next = Alert.ALERT
	elif suspicion > 0.001:
		next = Alert.SUSPICIOUS

	if next != alert_level:
		alert_level = next
		alert_level_changed.emit(alert_level)
```

### 3.3 全局噪声总线（Autoload）

新建 `res://autoload/noise_bus.gd`，在「项目设置 → 自动加载」中注册为 `NoiseBus`：

```gdscript
extends Node
## 全局噪声总线：任何东西都能「发声」，感知组件自行判断是否听得到。

signal noise(origin: Vector3, radius: float)

func emit_noise(origin: Vector3, radius: float = 15.0) -> void:
	noise.emit(origin, radius)
```

敌人侧接上：

```gdscript
func _ready() -> void:
	# ... 原有初始化代码
	NoiseBus.noise.connect(_on_noise)

func _on_noise(origin: Vector3, radius: float) -> void:
	hear_noise(origin, radius)
```

玩家侧在开枪、奔跑、落地时调用：

```gdscript
NoiseBus.emit_noise(global_position, 28.0)  # 枪声
NoiseBus.emit_noise(global_position, 9.0)   # 奔跑脚步
NoiseBus.emit_noise(global_position, 2.5)   # 潜行脚步
```

### 3.4 接上状态机

感知层不负责移动，只广播事实，决策层订阅：

```gdscript
@onready var senses: EnemySenses = $EnemySenses
@onready var agent: NavigationAgent3D = $NavigationAgent3D

func _ready() -> void:
	senses.alert_level_changed.connect(_on_alert_changed)

func _on_alert_changed(level: int) -> void:
	match level:
		EnemySenses.Alert.UNAWARE:
			_state = State.PATROL
		EnemySenses.Alert.SUSPICIOUS:
			_state = State.INVESTIGATE
			agent.target_position = senses.last_known_position
		EnemySenses.Alert.ALERT:
			_state = State.CHASE
			agent.target_position = senses.last_known_position
```

追击中断线后的行为由 `INVESTIGATE` 承担：走到**最后已知位置**四处张望，而不是直接读取玩家实时坐标——这正是「躲在墙后敌人会来你刚才的位置找人」的来源。

### 3.5 可选的视野调试绘制

调参时最痛苦的是「视野到底有多大」。用 `ImmediateMesh` 画一个扇形（发布前关闭）：

```gdscript
@export var debug_draw := true

var _fan := ImmediateMesh.new()
var _fan_instance := MeshInstance3D.new()

func _ready() -> void:
	# ... 原有初始化
	_fan_instance.mesh = _fan
	_fan_instance.top_level = true
	_fan_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(1.0, 0.3, 0.2, 0.25)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_fan_instance.material_override = mat
	add_child(_fan_instance)

func _process(_delta: float) -> void:
	if not debug_draw:
		return
	_fan.clear_surfaces()
	_fan.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	var origin := global_position + Vector3.UP * 0.05
	var forward := -global_basis.z
	forward.y = 0.0
	forward = forward.normalized()
	var half := deg_to_rad(fov_degrees * 0.5)
	var steps := 16
	for i in steps:
		var a1 := -half + 2.0 * half * float(i) / float(steps)
		var a2 := -half + 2.0 * half * float(i + 1) / float(steps)
		_fan.surface_add_vertex(origin)
		_fan.surface_add_vertex(origin + forward.rotated(Vector3.UP, a1) * sight_range)
		_fan.surface_add_vertex(origin + forward.rotated(Vector3.UP, a2) * sight_range)
	_fan.surface_end()
```

---

## 四、实践要点

1. **感知降频，怀疑度不降频**
   射线检测放在 0.1–0.2s 的 `Timer` 里；`suspicion` 的累积仍在 `_physics_process` 中用真实的 `delta`。如果把 `delta` 也换成定时器间隔，警觉会慢好几倍。

2. **先距离、再角度、后射线**
   100 个敌人里只有 3 个进入距离范围时，就只打 3×3 条射线。顺序反了，性能会差一个量级。

3. **图层比射线更重要**
   `sight_block_mask` 只包含墙体与玩家。若把草丛、粒子、装饰物放进去，会出现「明明没墙却看不见」的玄学 bug。

4. **射线起点要抬高到眼睛**
   从脚底发射线会被自己的台阶、矮墙误挡；也不要忘了用 `exclude` 排除自身 `RID`。

5. **多射线的数量控制在 2–3 条**
   头/胸/脚已经能覆盖绝大多数蹲伏场景；继续增加收益很低，开销线性上涨。

6. **贴脸感知补丁**
   `close_aware_radius` 让玩家碰到后背时仍会被发现，避免「贴脸潜行」的滑稽感。

7. **听觉与视觉共用怀疑度**
   枪声推到 35、脚步推到 35，视觉再补满——玩家会自然学会「跑动更危险」。

8. **保留记忆与滞后**
   `last_known_position` + `suspicion_decay` 就是「躲起来等它走」这一玩法的全部技术基础。

9. **同一个组件可直接复用到 2D**
   把 `Node3D` 换成 `Node2D`、`Vector3` 换成 `Vector2`、`PhysicsRayQueryParameters3D` 换成 `PhysicsRayQueryParameters2D`，三级结构完全不变。

---

## 五、延伸阅读

- [Godot 官方文档：RayCast3D](https://docs.godotengine.org/en/stable/classes/class_raycast3d.html)
- [Godot 官方文档：Ray-casting（射线查询与 `intersect_ray`）](https://docs.godotengine.org/en/stable/tutorials/physics/ray-casting.html)
- [UhiyamaLab：Stealth Game Vision Systems（Area3D + 点积 + RayCast3D）](https://uhiyama-lab.com/en/notes/godot/stealth-fov-system/)
- [Godot Forum：会看、会听、会呼救的僵尸 AI](https://forum.godotengine.org/t/how-to-make-zombies-that-see-hear-and-alert-each-other-in-godot-4/147450)
- [Godot 官方文档：NavigationAgent3D（把「发现目标」变成「追过去」）](https://docs.godotengine.org/en/stable/classes/class_navigationagent3d.html)
