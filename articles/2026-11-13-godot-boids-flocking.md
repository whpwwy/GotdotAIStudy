# Godot 群体行为 AI：用 Boids（鸟群算法）实现鸟群/鱼群模拟

> **日期**：2026-11-13
> **主题**：Godot 4 Boids Flocking 群体行为模拟（GDScript 实现）
> **主要来源**：
> - [How to Implement Boids Flocking in Godot Engine - BioErrorLog](https://en.bioerrorlog.work/entry/boids-flocking-godot)（2025-03-22 更新）
> - [Boids: Godot 2D example | Godot Playground](https://godotplayground.com/examples/boids)

---

## 一、为什么要学 Boids？

做游戏时你可能想做一群鸟飞过天空、一群鱼在水中游动、或者一群怪物朝玩家涌来。如果手动给每只个体写路径，既死板又难维护。

**Boids（Bird-oid，"像鸟的东西"）** 是 Craig Reynolds 于 1987 年在论文 *Flocks, Herds, and Schools: A Distributed Behavioral Model* 中提出的**人工生命**模型。它的魅力在于：**只靠三条极其简单的局部规则，就能涌现出逼真的群体行为**——没有任何中央指挥，每只鸟只看自己周围的邻居。

这和我们上一篇讲的**行为树**完全是两个方向：

| | 行为树（BT） | Boids |
|---|---|---|
| 关注点 | 单个实体的决策流程 | 群体的涌现行为 |
| 核心思想 | 节点组合 + 优先级 | 局部规则 + 力的叠加 |
| 适用场景 | 敌人 AI、NPC 行为 | 鸟群、鱼群、人群 |

两者并不冲突，实战中常见的组合是：**群体移动用 Boids，个体决策用行为树/状态机**。

## 二、三条核心规则

每只 Boid 每一帧只做一件事：**检查感知半径内的邻居，计算三种力，叠加后改变速度**。

| 规则 | 英文 | 作用 | 一句话理解 |
|---|---|---|---|
| **分离** | Separation | 避免和邻居靠太近 | "别挤我！" |
| **对齐** | Alignment | 朝向和邻居平均速度一致 | "大家往哪飞我也往哪飞" |
| **凝聚** | Cohesion | 朝邻居的中心聚拢 | "往大伙中间靠" |

三条规则各自算出一个"期望转向力"（steering force），按权重加权求和，就是这一帧的加速度。

> 关键直觉：**分离半径通常小于感知半径**——只有特别近的邻居才会触发分离，否则群体永远聚不起来。

## 三、转向力（Steering Force）的概念

直接给速度赋值会让运动显得生硬。经典做法是用 **Steering Force**：

```
steering = (desired_velocity - current_velocity).limit(MAX_FORCE)
```

- `desired_velocity`：我"想要"的速度（方向 × 最大速度）
- `current_velocity`：我现在的速度
- 差值就是需要施加的力，再限制最大力（MAX_FORCE),避免瞬时转向过猛

这样运动就有了**惯性**，看起来更自然。下面是一个辅助函数：

```gdscript
# 把"期望速度"转成"转向力"
func steer(desired: Vector2, current: Vector2, max_speed: float, max_force: float) -> Vector2:
	return (desired.normalized() * max_speed - current).limit_length(max_force)
```

## 四、单只 Boid 的实现

我们把每只鸟做成一个 `Node2D`（带视觉显示），用一个独立的 `Main` 节点统一管理所有 boid 的位置和速度数组——这是 Godot Playground 示例里的性能优化技巧：**数据用数组集中存储，避免每帧遍历大量节点调用方法**。

### 1. 单只 Boid 的逻辑（面向对象版，便于理解）

先看逐对象版本，理解原理；后面再给高性能数组版。

```gdscript
# boid.gd
class_name Boid
extends Node2D

@export var max_speed: float = 200.0
@export var max_force: float = 80.0
@export var perception_radius: float = 80.0
@export var separation_radius: float = 30.0  # 必须 < perception_radius

# 三个权重
@export var separation_weight: float = 1.8
@export var alignment_weight: float = 1.0
@export var cohesion_weight: float = 1.0

var velocity: Vector2 = Vector2.ZERO
var acceleration: Vector2 = Vector2.ZERO

func _ready() -> void:
	# 随机初始速度
	velocity = Vector2.RIGHT.rotated(randf_range(0, TAU)) * max_speed

func _process(delta: float) -> void:
	var flock: Array[Boid] = get_tree().get_first_node_in_group("boids").get_children()
	apply_flocking(flock)
	velocity = (velocity + acceleration * delta).limit_length(max_speed)
	position += velocity * delta
	rotation = velocity.angle()
	acceleration = Vector2.ZERO  # 每帧重置加速度
```

### 2. 三条规则的计算

```gdscript
func apply_flocking(flock: Array[Boid]) -> void:
	var sep := Vector2.ZERO
	var ali := Vector2.ZERO
	var coh := Vector2.ZERO
	var sep_count := 0
	var ali_count := 0

	for other in flock:
		if other == self:
			continue
		var d: float = position.distance_to(other.position)
		if d > perception_radius:
			continue

		# 对齐 + 凝聚：用所有感知到的邻居
		ali += other.velocity
		coh += other.position
		ali_count += 1

		# 分离：只用更近的邻居
		if d < separation_radius and d > 0.001:
			var diff: Vector2 = (position - other.position).normalized() / d
			sep += diff
			sep_count += 1

	if sep_count > 0:
		sep /= sep_count
		acceleration += steer(sep, velocity) * separation_weight

	if ali_count > 0:
		ali /= ali_count
		acceleration += steer(ali, velocity) * alignment_weight
		coh = coh / ali_count - position
		acceleration += steer(coh, velocity) * cohesion_weight

func steer(desired: Vector2, _current: Vector2) -> Vector2:
	return (desired.normalized() * max_speed - velocity).limit_length(max_force)
```

**注意几个细节**：

1. **分离用 `normalized() / d`**：距离越近，推力越大，符合"越近越要躲"的直觉。
2. **`d > 0.001` 的判断**：避免和自己位置完全重合时除以零。
3. **每帧重置 `acceleration`**：力是瞬时的，不累积。

## 五、高性能数组版（推荐用于大量 Boid）

上面的面向对象写法在 boid 数量 > 100 时会明显掉帧，因为每只都要 `get_tree()` 并遍历整个 flock。**Godot Playground 的做法是把所有位置和速度放进 `PackedVector2Array`，由一个主脚本统一计算**，性能提升非常明显。

```gdscript
# main.gd
extends Node

const COUNT := 120
const MAX_SPEED := 200.0
const MAX_FORCE := 330.0
const PERCEPTION := 90.0
const SEPARATION_RANGE := 32.0

const W_SEP := 1.7
const W_ALI := 1.1
const W_COH := 0.9

var positions := PackedVector2Array()
var velocities := PackedVector2Array()
var sprites: Array[Polygon2D] = []

func _ready() -> void:
	var view := get_viewport().get_visible_rect().size
	for i in COUNT:
		positions.append(Vector2(randf_range(50, view.x - 50), randf_range(50, view.y - 50)))
		velocities.append(Vector2.RIGHT.rotated(randf_range(0, TAU)) * MAX_SPEED)
		var hull := Polygon2D.new()
		hull.polygon = PackedVector2Array([Vector2(12, 0), Vector2(-8, 6), Vector2(-8, -6)])
		add_child(hull)
		sprites.append(hull)

func _process(delta: float) -> void:
	for i in COUNT:
		var sep := Vector2.ZERO
		var ali := Vector2.ZERO
		var coh := Vector2.ZERO
		var neighbors := 0
		var sep_count := 0

		for j in COUNT:
			if j == i:
				continue
			var offset := positions[j] - positions[i]
			var d := offset.length()
			if d > PERCEPTION:
				continue

			ali += velocities[j]
			coh += positions[j]
			neighbors += 1

			if d < SEPARATION_RANGE and d > 0.001:
				sep -= offset.normalized() * (SEPARATION_RANGE - d)
				sep_count += 1

		var force := Vector2.ZERO
		if neighbors > 0:
			force += steer(ali / neighbors, velocities[i]) * W_ALI
			force += steer(coh / neighbors - positions[i], velocities[i]) * W_COH
		if sep_count > 0:
			force += steer(sep, velocities[i]) * W_SEP

		velocities[i] = (velocities[i] + force * delta).limit_length(MAX_SPEED)
		positions[i] += velocities[i] * delta

		sprites[i].position = positions[i]
		sprites[i].rotation = velocities[i].angle()

func steer(desired: Vector2, current: Vector2) -> Vector2:
	return (desired.normalized() * MAX_SPEED - current).limit_length(MAX_FORCE)
```

> 这个版本 O(n²) 的复杂度在几百只 boid 时仍然可用。如果要上千只，需要引入**空间分区**（比如 Godot 的 `Area2D` 或手动网格）来减少邻居查询。

## 六、加一点趣味：追逐食物

BioErrorLog 的实现里加了一个"追逐食物"的行为——给所有 boid 一个目标点（鼠标位置或食物坐标），它们会整体朝那个方向移动，同时保持群体形态：

```gdscript
# 在主循环里叠加一个追逐力
func chase_food(food_pos: Vector2, current_pos: Vector2) -> Vector2:
	if current_pos.distance_to(food_pos) < 20.0:
		return Vector2.ZERO  # 已经够近，不推
	return steer(food_pos - current_pos, Vector2.ZERO) * 1.5
```

把这个力加到 `force` 上，就能看到鸟群像被食物吸引一样整体移动，非常有"活物"的感觉。

## 七、边界处理

如果不处理边界，boid 会飞出屏幕。两种常见做法：

**做法 A：环绕（无缝地图）**

```gdscript
func wrap(pos: Vector2, view: Vector2) -> Vector2:
	if pos.x < 0: pos.x += view.x
	elif pos.x > view.x: pos.x -= view.x
	if pos.y < 0: pos.y += view.y
	elif pos.y > view.y: pos.y -= view.y
	return pos
```

**做法 B：边界斥力（让群体自然掉头）**

```gdscript
func edge_force(at: Vector2, view: Vector2, margin: float = 80.0) -> Vector2:
	var f := Vector2.ZERO
	if at.x < margin: f.x = 400.0
	elif at.x > view.x - margin: f.x = -400.0
	if at.y < margin: f.y = 400.0
	elif at.y > view.y - margin: f.y = -400.0
	return f
```

边界斥力的效果更自然——鸟群碰到屏幕边缘会优雅地转向，而不是瞬移。

## 八、实践要点

1. **权重调参是关键**：`SEPARATION > ALIGNMENT > COHESION` 是常见的起点，分离不够会撞成一团，凝聚不够会散成一盘沙。
2. **分离半径 ≠ 感知半径**：感知半径决定"和谁做朋友"，分离半径决定"离谁太近要躲"。一般 `separation_radius = perception_radius / 2 ~ 1/3`。
3. **每帧重置加速度**：steering force 是瞬时力，不重置会越积越快。
4. **性能优化路径**：对象版 → 数组版 → 空间分区（Grid/Quadtree）→ 多线程/Compute Shader。
5. **和 AI 决策结合**：Boids 只管"怎么动"，不管"为什么动"。可以让状态机/行为树决定 boid 群体当前是"巡逻"、"逃跑"还是"攻击"，切换不同的权重或目标点。
6. **3D 版本同理**：把 `Vector2` 全换成 `Vector3`，`Polygon2D` 换成 `MeshInstance3D`，逻辑完全一致。

## 九、延伸阅读

- [How to Implement Boids Flocking in Godot Engine - BioErrorLog](https://en.bioerrorlog.work/entry/boids-flocking-godot) —— 本文主要参考，含追逐食物的完整实现
- [Boids: Godot 2D example | Godot Playground](https://godotplayground.com/examples/boids) —— 高性能数组版在线可运行示例
- [Flocks, Herds, and Schools: A Distributed Behavioral Model (Craig Reynolds, 1987)](https://scholar.google.com/scholar?q=Flocks+Herds+and+Schools+A+Distributed+Behavioral+Model+Reynolds) —— Boids 原始论文
- [Boids - Wikipedia](https://en.wikipedia.org/wiki/Boids) —— 概念与伪代码总览
- [Steering Behaviors For Autonomous Characters - Craig Reynolds](https://www.red3d.com/cwr/steer/) —— Reynolds 本人的 Steering Behaviors 主页，含 seek/flee/pursue/evade 等更多行为
- [beehave - Godot 行为树插件](https://github.com/bitbrain/beehave) —— 与 Boids 配合的决策层工具
- [Godot Asset Library: Boids (2D/3D flocking)](https://godotengine.org/asset-library/asset/3284) —— 现成的 Godot 4 Boids 插件
