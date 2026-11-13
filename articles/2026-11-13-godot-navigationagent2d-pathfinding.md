# Godot 2D 寻路 AI：用 NavigationAgent2D 实现路径跟随与点击移动

> **日期**：2026-11-13  
> **主题**：Godot 4 NavigationAgent2D、NavigationRegion2D 与 2D 路径跟随  
> **适用版本**：Godot 4.x（以文中所列 4.x / stable 官方文档为准）  
> **主要来源**：
> - [2D 导航概述 — Godot Engine 4.x 简体中文文档](https://docs.godotengine.org/zh-cn/4.x/tutorials/navigation/navigation_introduction_2d.html)
> - [Using NavigationAgents — Godot Engine stable documentation](https://docs.godotengine.org/en/stable/tutorials/navigation/navigation_using_navigationagents.html)
> - [NavigationAgent2D — Godot Engine stable class reference](https://docs.godotengine.org/en/stable/classes/class_navigationagent2d.html)

---

## 一、为什么“朝目标直线移动”不够用

最直觉的敌人追击写法是计算目标方向，再让角色每帧前进：

```gdscript
velocity = global_position.direction_to(target.global_position) * speed
```

空旷场景里这样做没有问题，但只要中间隔着墙壁，角色就会顶着墙滑动，永远到不了目标。寻路系统要解决的问题不是“目标在哪个方向”，而是“从当前位置到目标，应该依次经过哪些可行走的位置”。

Godot 的 2D 网格导航方案把这项工作拆成两层：**NavigationRegion2D 提供可行走区域，NavigationAgent2D 查询并跟随路径，角色脚本负责实际移动**。需要特别注意，NavigationAgent2D 不会替角色移动，也不会自动避开物理碰撞体；它提供路径信息，移动仍由自己的代码完成。[cite:1][cite:2]

这套方案适合敌人绕墙追击、点击移动、NPC 前往工作地点等“目标可以是区域中任意位置”的场景。如果游戏只有规则方格和离散格子目标，官方文档建议也可以考虑更直接的 AStarGrid2D。[cite:1]

## 二、先理解五个角色

| 对象 | 职责 | 不负责什么 |
|---|---|---|
| `NavigationPolygon` | 描述二维可行走多边形，也就是导航网格数据 | 不控制角色运动 |
| `NavigationRegion2D` | 持有导航多边形，并把区域交给导航服务器 | 不是敌人或玩家控制器 |
| `NavigationServer2D` | 同步导航地图、区域与代理，执行底层导航操作 | 不替场景角色写移动逻辑 |
| `NavigationAgent2D` | 设置目标、查询路径、推进内部路径索引 | 不移动父节点 |
| `CharacterBody2D` | 根据下一路径点设置 `velocity`，调用 `move_and_slide()` | 不自动知道哪条路线可通行 |

一次典型的路径跟随流程如下：

```text
设置 target_position
        ↓
NavigationAgent2D 查询路径
        ↓
每个物理帧调用一次 get_next_path_position()
        ↓
角色朝返回的位置设置 velocity
        ↓
move_and_slide() 执行移动与物理碰撞
        ↓
is_navigation_finished() 为 true 后停止查询并停下
```

这里最重要的分工是：**导航系统决定“往哪里走”，角色控制器决定“怎么走”**。因此，同一种路径数据可以搭配不同的速度、加速度、动画和角色控制器。

## 三、搭建最小可运行场景

在 Godot 4 中新建 2D 场景，组织成下面的结构：

```text
Main (Node2D)
├─ NavigationRegion2D
└─ Player (CharacterBody2D)  ← 挂载本文完整脚本
   ├─ CollisionShape2D
   ├─ Polygon2D
   └─ NavigationAgent2D
```

按以下步骤配置：

1. 选中 `NavigationRegion2D`，在 Inspector 中新建 `NavigationPolygon`。
2. 用导航多边形工具画出角色的可行走区域，绕开墙体等障碍，然后点击 **Bake NavigationPolygon**。
3. 给 `Player` 的 `CollisionShape2D` 新建一个圆形或胶囊形碰撞形状。
4. 给 `Polygon2D` 填一个简单三角形或矩形，便于观察角色；也可以换成自己的 Sprite2D。
5. 将下节脚本保存为 `click_to_move.gd`，挂到 `Player` 上并运行场景。左键点击可行走区域，角色就会沿导航路径移动。

> 导航多边形表示的是**角色中心点可以到达的区域**，不是精灵图片的轮廓。多边形边缘应与墙体碰撞体之间保留足够边距，否则路径本身合法，角色的碰撞形状却可能卡在墙角。[cite:1]

## 四、完整 GDScript：点击目标并沿路径移动

```gdscript
# click_to_move.gd
extends CharacterBody2D

@export var movement_speed: float = 180.0

@onready var navigation_agent: NavigationAgent2D = $NavigationAgent2D

func _ready() -> void:
	# 这些值需要结合角色速度、碰撞体尺寸和地图比例调整。
	navigation_agent.path_desired_distance = 8.0
	navigation_agent.target_desired_distance = 8.0
	navigation_agent.path_max_distance = 48.0

	# 不在 _ready() 中立即请求路径；延迟到导航地图完成首次同步之后。
	_initialize_navigation.call_deferred()

func _initialize_navigation() -> void:
	await get_tree().physics_frame
	# 初始目标设为当前位置，让代理以有效目标开始工作。
	navigation_agent.target_position = global_position

func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventMouseButton):
		return

	var mouse_event := event as InputEventMouseButton
	if mouse_event.button_index == MOUSE_BUTTON_LEFT and mouse_event.pressed:
		# target_position 使用全局坐标，而不是 viewport 或本地坐标。
		navigation_agent.target_position = get_global_mouse_position()

func _physics_process(_delta: float) -> void:
	# 必须先判断是否结束；到终点后继续取下一路径点可能造成原地抖动。
	if navigation_agent.is_navigation_finished():
		velocity = Vector2.ZERO
	else:
		# 此调用不仅读取位置，也会推进代理内部的路径跟随状态。
		var next_path_position: Vector2 = navigation_agent.get_next_path_position()
		velocity = global_position.direction_to(next_path_position) * movement_speed

	# NavigationAgent2D 不会移动父节点，实际移动仍由 CharacterBody2D 完成。
	move_and_slide()
```

这段示例包含三个容易遗漏的环节：

- **等待首次同步**：导航地图在第一帧可能还没有同步区域数据，过早请求会得到空路径。示例使用延迟调用并等待一次 `physics_frame`。[cite:1]
- **先结束判断，再取路径点**：`get_next_path_position()` 会更新代理内部状态，不应在路径结束后继续调用。[cite:2]
- **最后执行物理移动**：取得下一路径点后，仍需自行计算速度并调用 `move_and_slide()`。[cite:2]

## 五、六个关键 API 与参数

### 1. `target_position`

给它设置一个**全局坐标**后，代理会在当前导航地图上查询新路径。玩家点击、敌人追击和 NPC 领取目的地，最终都可以统一成“设置目标位置”。

不要无意义地每个物理帧重复设置同一个目标。对于不断移动的目标，也应采用定时或距离阈值重算，避免路径起点频繁变化造成角色来回摆动。[cite:2]

### 2. `get_next_path_position()`

它返回当前应该前往的路径点，同时负责推进内部路径索引和触发相关状态更新。官方建议在每个 `_physics_process()` 中调用一次，直到 `is_navigation_finished()` 表明路径结束。[cite:2]

### 3. `is_navigation_finished()`

这是路径跟随循环的退出条件。到达后应将 `velocity` 清零，不再请求下一路径点。

### 4. `path_desired_distance`

角色距离“当前下一路径点”多近时，代理推进到后续路径点。值太小，快速角色可能一帧越过判定范围，再掉头回来；值太大，则可能过早切弯。应结合速度和物理帧率调整。[cite:2]

### 5. `target_desired_distance`

角色距离最终目标多近时视为到达。它决定停止容差，不应机械地设为 0。

### 6. `path_max_distance`

角色偏离理想路径超过这个距离时，代理会请求新路径。它适合处理角色被击退、挤压或外力推离路线的情况，但设置过小会导致过于频繁的重算。[cite:2]

## 六、从点击移动改成敌人追击

追击移动目标时，不需要每帧重算。可以先采用每 0.25 秒更新一次目标的简单节流策略：

```gdscript
@export var chase_target: Node2D
@export var repath_interval: float = 0.25
var _repath_remaining: float = 0.0

func update_chase_target(delta: float) -> void:
	if not is_instance_valid(chase_target):
		return

	_repath_remaining -= delta
	if _repath_remaining > 0.0:
		return

	navigation_agent.target_position = chase_target.global_position
	_repath_remaining = repath_interval
```

在完整示例的 `_physics_process(delta)` 开头调用 `update_chase_target(delta)`，并移除点击输入的目标设置，就能让角色持续追击 `chase_target`。路径点读取、结束判断和 `move_and_slide()` 部分保持不变。

这里的 0.25 秒只是便于上手的初始值，不是固定标准：目标变向很快时可以缩短间隔，大量敌人同时寻路时可以增大间隔，或让不同敌人错开重算时间。若目标只是缓慢移动，还可以在“目标距上次记录位置超过阈值”时才重算。

## 七、寻路、局部避障与物理碰撞不是一回事

这三个系统经常被混用：

| 系统 | 回答的问题 | 典型对象 |
|---|---|---|
| 寻路 | 绕过静态墙体应该走哪条路线 | NavigationRegion2D、NavigationAgent2D |
| 局部避障 | 附近移动代理挡路时，当前安全速度是什么 | 启用 avoidance 的 NavigationAgent2D、NavigationObstacle2D |
| 物理碰撞 | 本帧移动是否与碰撞体重叠，如何滑动或停止 | CharacterBody2D、CollisionShape2D |

启用代理避障需要设置 `avoidance_enabled = true`，把期望速度传给代理，并使用 `velocity_computed` 信号返回的安全速度移动父节点。避障计算本身不会改变寻路路径；NavigationObstacle2D 也只影响避障速度，不会把障碍自动刻进导航网格。若一堵墙应当改变全局路线，仍需修改并重新烘焙导航数据。[cite:1][cite:2]

因此，不要指望“加了 NavigationAgent2D 就自动穿墙绕障”，也不要把 Boids 的转向力当成导航网格寻路。前者解决拓扑路线，后者主要组织局部运动，两者可以组合但职责不同。

## 八、常见故障排查与实践要点

1. **路径一直为空**：先确认 NavigationPolygon 已烘焙、角色与目标对应同一导航地图，再检查是否在首次同步前设置了目标。
2. **角色完全不动**：确认脚本实际调用了 `move_and_slide()`；NavigationAgent2D 只提供路径，不产生位移。
3. **角色在终点抖动**：把 `is_navigation_finished()` 放在 `get_next_path_position()` 之前，并适当增大 `target_desired_distance`。
4. **角色越过路点后回头**：适当增大 `path_desired_distance`，尤其是高速角色；同时避免每帧无条件重设目标。
5. **路线正确但卡在墙角**：给导航多边形与墙体之间留边距，并检查碰撞形状是否大于预留通道。
6. **点击后朝奇怪方向走**：检查是否混用了全局坐标与本地坐标；`target_position` 应接收全局位置。
7. **大量敌人同时寻路导致开销上升**：降低重算频率、错开各代理的更新时间，只在目标明显移动或路径失效时重算。
8. **调试时先观察路径，再调运动**：先确认目标与导航区域正确，再调速度和距离容差。把寻路错误与动画、加速度、碰撞问题分开，会更容易定位原因。

## 九、小结

NavigationAgent2D 的核心用法可以浓缩为一句话：**等待地图同步，设置全局目标，每个物理帧在安全的前提下取得下一路径点，再由角色控制器完成移动**。

掌握这条主流程后，点击移动、巡逻和敌人追击只是目标来源不同；继续叠加状态机或行为树，可以决定“何时追击、何时放弃”，叠加局部避障，则能改善多个移动代理相遇时的表现。

## Sources（延伸阅读）

- [cite:1] [2D 导航概述 — Godot Engine 4.x 简体中文文档](https://docs.godotengine.org/zh-cn/4.x/tutorials/navigation/navigation_introduction_2d.html)：导航对象分工、最小场景搭建、首次同步与导航多边形边距。
- [cite:2] [Using NavigationAgents — Godot Engine stable documentation](https://docs.godotengine.org/en/stable/tutorials/navigation/navigation_using_navigationagents.html)：路径跟随、距离参数、常见问题与 RVO 避障的完整说明。
- [cite:3] [NavigationAgent2D — Godot Engine stable class reference](https://docs.godotengine.org/en/stable/classes/class_navigationagent2d.html)：属性、方法与信号的逐项 API 参考。
