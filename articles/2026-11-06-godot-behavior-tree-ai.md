# 用行为树（Behavior Tree）设计 Godot AI：从原理到实战

> **日期**：2026-11-06
> **主题**：Godot 4 行为树 AI 设计（GDScript 实现）
> **主要来源**：[Designing AI with Behavior Trees - GDScript Implementation and Enemy AI | UhiyamaLab](https://uhiyama-lab.com/en/notes/godot/behavior-tree-ai-design/)（2026-10-10 更新，基于 Godot 4.7 验证）

---

## 一、为什么需要行为树？

用一堆 `if` 语句写敌人 AI，条件一多就没法维护；状态机（State Machine）虽然好用，但状态变多后会遭遇**「状态爆炸」**——状态之间的转换关系会缠成一张网。

而「发现玩家就追击并攻击、没发现就巡逻、血量低了会逃跑」这种**有优先级的复杂行为**，正是行为树（Behavior Tree，简称 BT）擅长的场景。

**核心区别**：

| | 状态机 | 行为树 |
|---|---|---|
| 结构 | 状态 + 转换组成的「网」 | 任务组成的「树」 |
| 优先级 | 隐含在转换条件里 | 直接由分支顺序表达 |
| 扩展方式 | 加状态、加转换（易纠缠） | 加分支（子树可复用） |

> **注意**：Godot 没有内置行为树功能。可以先手写理解原理，项目变大后再换 [beehave](https://github.com/bitbrain/beehave) 这类可视化插件。

## 二、四种节点类型

BT 只由四种节点组合而成。每个节点都通过 `tick()` 求值，返回三种状态之一：

- `SUCCESS`：成功
- `FAILURE`：失败
- `RUNNING`：进行中（BT 特有，比如「还在移动中」）

| 节点 | 作用 | 返回逻辑 |
|---|---|---|
| **Sequence**（序列） | 按顺序执行子节点（AND） | 全部成功才 SUCCESS；一个失败立即 FAILURE |
| **Selector**（选择） | 按顺序尝试子节点（OR） | 一个成功即 SUCCESS；全部失败才 FAILURE |
| **Decorator**（装饰） | 变换子节点结果（取反、重复等） | 变换后的结果 |
| **Leaf**（叶子） | 实际干活（移动、攻击、等待） | 三种状态都可能 |

一句话记住：**Sequence 遇失败即停，Selector 遇成功即停**——两者互为镜像。

## 三、代码实现

### 1. 基类

```gdscript
# bt_node.gd
class_name BTNode
extends Node

enum Status { SUCCESS, FAILURE, RUNNING }

# 子类覆写此求值方法
func tick(actor: Node, blackboard: Dictionary) -> Status:
	return Status.FAILURE
```

- `actor`：运行这棵树的实体（比如敌人角色）
- `blackboard`：节点间共享数据的字典（见第五节）

### 2. Sequence（AND）：全部做完才算完

```gdscript
# bt_sequence.gd
class_name BTSequence
extends BTNode

func tick(actor: Node, blackboard: Dictionary) -> Status:
	for child in get_children():
		var status: Status = child.tick(actor, blackboard)
		if status == Status.FAILURE:
			return Status.FAILURE   # 任一子节点失败，立即中止
		if status == Status.RUNNING:
			return Status.RUNNING   # 还在进行，本帧到此为止
	return Status.SUCCESS           # 全部成功
```

### 3. Selector（OR）：第一个成功的胜出

```gdscript
# bt_selector.gd
class_name BTSelector
extends BTNode

func tick(actor: Node, blackboard: Dictionary) -> Status:
	for child in get_children():
		var status: Status = child.tick(actor, blackboard)
		if status == Status.SUCCESS:
			return Status.SUCCESS   # 提交第一个成功分支
		if status == Status.RUNNING:
			return Status.RUNNING
	return Status.FAILURE           # 全部失败
```

### 4. Leaf：真正的游戏逻辑

叶子节点负责具体行为，**保持小而单一职责**，方便在别的树里复用。例如「向目标移动」：

```gdscript
# bt_move_to_target.gd
class_name BTMoveToTarget
extends BTNode

@export var move_speed: float = 100.0
@export var arrival_distance: float = 40.0  # 要大于碰撞体接触距离

func tick(actor: Node, blackboard: Dictionary) -> Status:
	var target: Node2D = blackboard.get("target")
	if target == null:
		return Status.FAILURE             # 没有目标 = 失败
	var dist: float = actor.global_position.distance_to(target.global_position)
	if dist <= arrival_distance:
		return Status.SUCCESS             # 到达 = 成功
	# 还远，继续移动
	var dir: Vector2 = actor.global_position.direction_to(target.global_position)
	actor.velocity = dir * move_speed
	actor.move_and_slide()
	return Status.RUNNING                 # 移动中 = 进行中
```

`RUNNING` 的妙处：下一帧继续执行该节点，「移动完成后才进入下一个任务」自然就实现了。想要绕开障碍物，把移动逻辑换成 `NavigationAgent2D` 即可。

## 四、实战：组装一个敌人 AI

目标行为：**玩家在附近就战斗，否则巡逻**。树结构如下（根节点用 Selector，天然表达「战斗优先」）：

```
Enemy (CharacterBody2D)
└─ BehaviorTree (BTSelector)      # 先尝试上面的战斗分支
   ├─ CombatSequence (BTSequence) # 战斗：条件缺一不可
   │  ├─ HasTarget   (条件：有目标吗？)
   │  ├─ MoveToTarget(接近)
   │  └─ Attack      (攻击)
   └─ Patrol (BTPatrol)           # 战斗不可用时兜底巡逻
```

三个叶子节点脚本：

```gdscript
# bt_has_target.gd —— 条件判断
class_name BTHasTarget
extends BTNode

func tick(_actor: Node, blackboard: Dictionary) -> Status:
	return Status.SUCCESS if blackboard.get("target") else Status.FAILURE
```

```gdscript
# bt_attack.gd —— 攻击（演示用：每秒打印一次）
class_name BTAttack
extends BTNode

var last_attack := -100.0

func tick(_actor: Node, _blackboard: Dictionary) -> Status:
	var now := Time.get_ticks_msec() / 1000.0
	if now - last_attack < 1.0:
		return Status.RUNNING         # 攻击冷却中
	last_attack = now
	print("Attack!")
	return Status.SUCCESS
```

```gdscript
# bt_patrol.gd —— 巡逻：依次访问巡逻点
class_name BTPatrol
extends BTNode

@export var move_speed: float = 60.0
var index := 0

func tick(actor: Node, blackboard: Dictionary) -> Status:
	var points: Array = blackboard.get("patrol_points", [])
	if points.is_empty():
		return Status.FAILURE
	var point: Vector2 = points[index]
	if actor.global_position.distance_to(point) < 5.0:
		index = (index + 1) % points.size()  # 到达后前往下一点
	actor.velocity = actor.global_position.direction_to(point) * move_speed
	actor.move_and_slide()
	return Status.RUNNING
```

敌人本体：每帧把「玩家是否在附近」写进 Blackboard，然后对根节点 `tick()` 一次（玩家需加入 `player` 组）：

```gdscript
# enemy.gd
extends CharacterBody2D

@onready var bt_root: BTNode = $BehaviorTree
var blackboard := {}

func _ready() -> void:
	blackboard["patrol_points"] = [Vector2(100, 100), Vector2(300, 100)]

func _physics_process(_delta: float) -> void:
	# 把侦测结果写入 Blackboard（侦测本身可以交给独立系统）
	var player := get_tree().get_first_node_in_group("player")
	var near := player and global_position.distance_to(player.global_position) < 200
	blackboard["target"] = player if near else null
	# 驱动整棵树
	bt_root.tick(self, blackboard)
```

## 五、Blackboard：节点间的松耦合通信

Blackboard 就是一个共享字典，**节点之间绝不直接引用，只通过它传数据**：

```gdscript
# 写入（由侦测系统或角色本体负责）
blackboard["target"] = player
blackboard["health"] = 78
blackboard["is_alerted"] = true

# 读取（在各节点的 tick 内部）
if blackboard.get("is_alerted"):
	pass  # 进入警戒行为
```

`MoveToTarget` 不需要知道 `target` 是谁写进去的——数据集中管理，调试方便，是和信号（Signal）并列的解耦利器。

## 六、实践要点

1. **优先级 = 分支顺序**：Selector 从上往下尝试，想调整优先级只需拖动分支顺序。
2. **决策与执行分离**：「看见玩家了吗」交给视野系统（Area2D/RayCast），「怎么走」交给 NavigationAgent2D，BT 只负责决策。
3. **叶子要小而专一**：一个叶子只做一件事，才能在多棵树间复用。
4. **RUNNING 的局限**：本实现每帧从根节点重新求值。小树没问题，树大了要加「记住上次 RUNNING 位置并从中恢复」的优化。
5. **Decorator 提升表达力**：`Inverter`（取反）、`Repeater`（重复）、`Timeout`（限时）等装饰器能表达「尝试 N 秒」「把失败当成功」这类需求。
6. **BT 与状态机不是对立关系**：常见做法是上层用大状态机、每个状态内部用 BT 处理细节。

## 七、延伸阅读

- [Managing AI and Player States with State Machines](https://uhiyama-lab.com/en/notes/godot/state-machine-ai-player/) —— 状态机，AI 设计的另一半
- [Stealth Game Vision Systems](https://uhiyama-lab.com/en/notes/godot/stealth-fov-system/) —— 视野侦测，为 BT 提供「是否发现玩家」
- [Pathfinding with NavigationAgent2D](https://uhiyama-lab.com/en/notes/godot/navigation-agent2d/) —— 寻路，可放进 MoveToTarget 内部
- [beehave - Godot 行为树插件（GitHub）](https://github.com/bitbrain/beehave) —— 生产级可视化 BT 插件
- [Godot 4 Enemy AI Tutorial: Patrol, Chase, and Attack](https://www.codingquests.io/blog/godot-4-enemy-ai-tutorial) —— 3D 敌人 AI 完整教程
- [How to Make AI in Godot 4: A Step-by-Step Guide](https://www.summerengine.com/blog/how-to-make-ai-in-godot) —— 入门向 AI 状态机指南
