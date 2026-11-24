# Godot 4 流场寻路（Flow Field Pathfinding）实战：让上千个单位共享同一条路

> 日期：2026-11-25
> 系列：Godot AI 编程 · 每日一篇
> 关键词：Flow Field、流场寻路、Integration Field、Dijkstra Map、向量场、RTS、群体寻路、Pathfinding

## 来源链接

- Vav Labs：*Flow Field Pathfinding in Godot — Crowds & RTS*
  <https://vav-labs.com/blog/godot-flow-fields-shared-goal/>
- Leif Node：*Flow Field Pathfinding*（整理自 Elijah Emerson / *Planetary Annihilation*）
  <https://leifnode.com/2013/12/flow-field-pathfinding/>
- Game AI Pro 第 24 章：*Efficient Crowd Simulation for Mobile Games*（Fieldrunners 2 的流场实现）
  <http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter24_Efficient_Crowd_Simulation_for_Mobile_Games.pdf>
- Patil 等：*Directing Crowd Simulations Using Navigation Fields*（2010，导航场学术论文）
  <https://ics-websites.science.uu.nl/docs/vakken/mcrws/papers_new/Patil%20et%20al%20-%202010%20-%20Directing%20crowd%20simulations%20using%20navigation%20fields.pdf>

---

## 一、当 A* 被问了一百遍同一个问题

假设你在做一款 RTS：玩家框选 200 个步兵，右键点击地图另一侧的集结点。接下来的一帧，经典做法会发生什么？

每个单位各自调用一次 `AStarGrid2D.get_point_path()`，从"我这里"到"目标那里"算一条最短路径。200 个单位就是 200 次 A*。问题不在于单次 A* 慢，而在于**这 200 次搜索高度重复**：它们要绕开的是同一堵墙、要穿过的是同一条走廊、要重新发现的是同一个拐点。大量算力花在"问了一百遍同一个问题"上，最终表现为目标点一移动，整帧就卡出一个尖刺。

A* 回答的是**单个单位**的问题：给定起点和终点，最便宜的路线是什么？但当一群单位共享同一个目的地时，这是个错误的问题。正确的问题应该反过来问一次：

> **如果我站在这张地图的任意一个格子上，目标在哪个方向？**

把这个问题对整张地图回答一遍，存下来，单位就再也不用"搜索"了——它低头看一眼脚下格子里存的方向向量，照着走就行。这张预计算好的方向表，就是**流场（Flow Field）**。

一句话定义：

> 流场是覆盖在关卡网格上的一个向量场，每个可走格子存一个单位向量，指向沿最低代价路线通往目标的下一格。一次计算，全场受益。

它是《Planetary Annihilation》《Fieldrunners 2》《最高指挥官》这类"海量单位共享目标"游戏的寻路基石，也是 RTS / 塔防 / 人群模拟里替代逐单位 A* 的标准方案。

---

## 二、把问题倒过来：从目标出发算全场

流场的核心洞察是**反转搜索方向**。A* 从起点向目标搜；流场从目标向全场扩散。具体分两步（外加一个前置的代价场）。

### 2.1 代价场（Cost Field）：地形的"过路费"

代价场是和寻路网格同尺寸的一张标量表，每个格子记录"走进这格要花多少代价"：

- 普通可走格：代价 `1`；
- 草地 / 沼泽：代价 `2~5`（减速区）；
- 墙 / 障碍：代价 `0`（表示不可走，单独标记）。

代价场让寻路不只是"能走 / 不能走"，还能表达"哪条路更费劲"。

### 2.2 积分场（Integration Field）：从目标到每格的最低累计代价

以目标格为起点（代价 `0`），向四邻扩散，每走一步累加代价场里的过路费；若发现某格能以更低代价到达，就更新它（松弛，relaxation）。这正是 Dijkstra 算法从目标反向跑一遍，得到的就是一张"每格到目标的最短距离"热力图——学术界也叫 **Dijkstra Map**。

### 2.3 流场（Flow Field）：每格指向最优邻居

积分场算完后，对每个可走格，环视它的邻居，挑出**积分值最小**的那个邻居，把"我 → 它"的方向存下来。这就是该格的流向向量。整张图连起来，就是一条条从任意位置汇入目标的"河流"。

单位的每帧行为退化成一次数组查表：

```text
cell = 脚下格子坐标
velocity = flow[cell] * speed
```

没有搜索、没有开放集、没有优先级队列——O(1) 一次查表。1000 个单位和 1 个单位的寻路成本几乎一样。

---

## 三、Godot 4 完整实现

下面用纯 GDScript 实现一个可直接运行的流场：一个 `FlowField` 类负责构建三张场，一个 `FlowAgent`（CharacterBody2D）负责查表移动，一个主场景负责画网格、生成障碍、生成上百个单位，并支持点击切换目标。

### 3.1 `FlowField.gd`：构建三张场

```gdscript
class_name FlowField
extends RefCounted

## 网格尺寸（列、行）与每格像素大小
var grid_size: Vector2i
var cell_size: float = 32.0

## 代价场：0 = 不可走，>0 = 进入该格的代价
var cost_field: PackedByteArray
## 积分场：每格到目标的最低累计代价（INF = 不可达）
var integration: PackedFloat32Array
## 流场：每格指向下一最优格的单位向量
var flow: PackedVector2Array
## 当前目标格
var goal: Vector2i = Vector2i(-1, -1)

func _init(cols: int, rows: int, cs: float = 32.0) -> void:
	grid_size = Vector2i(cols, rows)
	cell_size = cs
	cost_field.resize(cols * rows)
	cost_field.fill(1)            # 默认每格可走、代价 1
	integration.resize(cols * rows)
	flow.resize(cols * rows)

func _idx(x: int, y: int) -> int:
	return y * grid_size.x + x

func in_bounds(x: int, y: int) -> bool:
	return x >= 0 and y >= 0 and x < grid_size.x and y < grid_size.y

func is_walkable(x: int, y: int) -> bool:
	return in_bounds(x, y) and cost_field[_idx(x, y)] > 0

func set_blocked(x: int, y: int, blocked: bool) -> void:
	if in_bounds(x, y):
		cost_field[_idx(x, y)] = 0 if blocked else 1

## 八方向邻居，含"不可斜穿墙角"的约束
func _neighbors(c: Vector2i) -> Array[Vector2i]:
	var result: Array[Vector2i] = []
	for dy in range(-1, 2):
		for dx in range(-1, 2):
			if dx == 0 and dy == 0:
				continue
			var nx := c.x + dx
			var ny := c.y + dy
			if not in_bounds(nx, ny) or not is_walkable(nx, ny):
				continue
			# 斜向移动时，两个正交邻居必须都可走，避免穿墙角
			if dx != 0 and dy != 0:
				if not is_walkable(c.x + dx, c.y) or not is_walkable(c.x, c.y + dy):
					continue
			result.push_back(Vector2i(nx, ny))
	return result

## 正交步长 1.0，对角步长 √2
func _step_cost(a: Vector2i, b: Vector2i) -> float:
	return 1.414 if (a.x != b.x and a.y != b.y) else 1.0

## 给定目标格，重建积分场与流场
func build(goal_cell: Vector2i) -> void:
	goal = goal_cell
	integration.fill(INF)
	flow.fill(Vector2.ZERO)
	if not is_walkable(goal_cell.x, goal_cell.y):
		return

	# ---- 第一步：从目标出发做队列松弛（SPFA 风格，正确处理非负权重）----
	integration[_idx(goal_cell.x, goal_cell.y)] = 0.0
	var queue: Array[Vector2i] = [goal_cell]
	var head := 0
	while head < queue.size():
		var c: Vector2i = queue[head]
		head += 1
		var base_cost := integration[_idx(c.x, c.y)]
		for n in _neighbors(c):
			var ni := _idx(n.x, n.y)
			var step := base_cost + float(cost_field[ni]) * _step_cost(c, n)
			if step < integration[ni]:
				integration[ni] = step
				queue.push_back(n)

	# ---- 第二步：每格指向积分值最小的邻居，形成流场 ----
	for y in range(grid_size.y):
		for x in range(grid_size.x):
			var i := _idx(x, y)
			if not is_walkable(x, y):
				flow[i] = Vector2.ZERO
				continue
			var best := integration[i]
			var best_dir := Vector2.ZERO
			for n in _neighbors(Vector2i(x, y)):
				var ni := _idx(n.x, n.y)
				if integration[ni] < best:
					best = integration[ni]
					best_dir = Vector2(n.x - x, n.y - y).normalized()
			flow[i] = best_dir
```

> 说明：上面的扩散用了"队列松弛"（只要发现更短路径就把该格重新入队），对非负权重是正确的，等价于 Dijkstra 的思想但实现更紧凑。若地图很大、代价差异悬殊，可把 `queue` 换成二叉堆优先级队列，让代价最小的前沿格优先扩展，进一步提速。

### 3.2 `FlowAgent.gd`：每帧查表移动

```gdscript
class_name FlowAgent
extends CharacterBody2D

@export var speed: float = 120.0
var field: FlowField = null

func _physics_process(_delta: float) -> void:
	if field == null:
		return
	# 把世界坐标换算成格子坐标，直接查流场
	var cell := (global_position / field.cell_size).floor()
	if not field.in_bounds(cell.x, cell.y):
		return
	var i := cell.y * field.grid_size.x + cell.x
	var dir: Vector2 = field.flow[i]
	velocity = dir * speed
	move_and_slide()
```

注意单位的移动逻辑里**完全没有寻路计算**，只有一次数组读取。这就是流场能撑住海量单位的原因。

### 3.3 `Main.gd`：演示场景（生成障碍、生成单位、点击换目标）

挂在一个 `Node2D` 上即可运行，会用 `_draw()` 把积分场渲染成热力图、把流场画成箭头：

```gdscript
extends Node2D

const FlowField = preload("res://FlowField.gd")
const FlowAgent = preload("res://FlowAgent.gd")

var field: FlowField
var agents: Array[FlowAgent] = []

const COLS := 40
const ROWS := 24
const CELL := 24.0

func _ready() -> void:
	randomize()
	field = FlowField.new(COLS, ROWS, CELL)
	_generate_walls(28)
	field.build(Vector2i(COLS - 2, ROWS / 2))   # 初始目标在右侧
	_spawn_agents(150)
	queue_redraw()

## 随机撒一些矩形障碍
func _generate_walls(count: int) -> void:
	for i in range(count):
		var bx := randi() % (COLS - 6) + 3
		var by := randi() % (ROWS - 6) + 3
		var bw := randi() % 4 + 1
		var bh := randi() % 4 + 1
		for y in range(by, by + bh):
			for x in range(bx, bx + bw):
				field.set_blocked(x, y, true)

## 在左侧可走区域批量生成单位
func _spawn_agents(n: int) -> void:
	for i in range(n):
		var a := FlowAgent.new()
		add_child(a)
		var tries := 0
		while tries < 60:
			var cx := randi() % 8
			var cy := randi() % ROWS
			if field.is_walkable(cx, cy):
				a.global_position = Vector2(cx, cy) * CELL + Vector2.ONE * CELL * 0.5
				break
			tries += 1
		a.field = field
		agents.append(a)

## 点击任意可走格 = 切换目标，整批单位自动改道
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		var cell := (event.position / CELL).floor()
		if field.is_walkable(cell.x, cell.y):
			field.build(cell)
			queue_redraw()

## 渲染：积分场热力图 + 流向箭头 + 目标格
func _draw() -> void:
	for y in range(ROWS):
		for x in range(COLS):
			var rect := Rect2(Vector2(x, y) * CELL, Vector2.ONE * CELL)
			if not field.is_walkable(x, y):
				draw_rect(rect, Color(0.18, 0.18, 0.22))
				continue
			var i := y * COLS + x
			var heat := clamp(field.integration[i] / 40.0, 0.0, 1.0)
			draw_rect(rect, Color(0.10, 0.14, 0.24).lerp(Color(0.95, 0.55, 0.20), heat), 0.85)
			var dir := field.flow[i]
			if dir != Vector2.ZERO:
				var center := rect.position + rect.size * 0.5
				draw_line(center, center + dir * CELL * 0.4, Color(0.95, 0.95, 0.95, 0.75), 1.5)
	# 高亮目标格
	var g := Vector2(field.goal.x, field.goal.y) * CELL
	draw_rect(Rect2(g, Vector2.ONE * CELL), Color(0.25, 0.95, 0.45), false, 2.0)
```

### 3.4 场景搭建步骤

1. 新建 2D 场景，根节点选 `Node2D`，命名 `Main`，挂上上面的 `Main.gd`；
2. 把 `FlowField.gd`、`FlowAgent.gd` 放在 `res://` 根目录（或修改 `preload` 路径）；
3. 运行。你会看到 150 个单位从左侧涌出，沿着热力图最凉的方向（离目标最近）绕过障碍汇入右侧目标；
4. **在地图任意可走位置点击**，目标点立刻迁移，全场向量箭头同时转向，所有单位无缝改道——这正是流场"一次重算、全员生效"的威力。

---

## 四、实践要点

### 4.1 何时该用流场，何时该回到 A*

判断标准是**单位数与不同目标数的比值**：

- **多单位、少目标**（RTS 集结、塔防出兵口、人群涌向同一个出口）→ 流场的主场，一个场摊销给全场，单位越多越划算；
- **少单位、多目标**（几个角色各去各的地方）→ 为单个目标建整张积分场是浪费，A* 更合适；
- 真实游戏通常两者并存：共享目标的大群走流场，落单的个体走 A*，共用同一张网格。

### 4.2 动态目标与变化的地图

流场只对"构建它时的目标和地图"有效。目标移动、开门、放建筑都会让场失效。注意：

- **按变化重建，而不是按帧重建**：只在目标真的移动或网格真的改变时重算；
- **限频**：对不断游走的目标，每秒重建 2~4 次的粗略场，往往比每帧都精确的场更流畅；
- **局部修复**：障碍只改变一小片区域时，只重新扩散受影响的积分场区域，而不是整张图重建。

### 4.3 与影响图（Influence Map）合体

流场的 `cost_field` 不只能放地形代价——可以把"危险度"叠进去。把上一篇文章里的影响图数值加进代价场，积分场就会自然地让人群**绕开火力网**，而不只是绕开墙。这是 RTS 战术移动的经典组合：危险场调制寻路代价，流场负责执行。

### 4.4 避免单位叠成一团

纯流场只给方向，不做相互避让，单位会重叠成一坨。常见做法是在 `velocity` 上叠加一层**短程分离力**（可以直接复用本系列 Boids 那篇的 separation 规则），让单位沿流向前进的同时彼此错开。

### 4.5 性能细节

- `PackedFloat32Array` / `PackedVector2Array` 比 `Array` 连续内存、更省 GC，大网格优先用；
- 积分场重建是 O(格子数)，40×24 的小图毫秒级；若做 200×200 以上的大图，考虑分块（hierarchical flow field）或只在视野内重建；
- 单位查表是 O(1)，真正的瓶颈通常变成 `move_and_slide` 的物理与碰撞，而非寻路。

---

## 五、延伸阅读

- Vav Labs：*Flow fields in Godot: pathfinding for crowds that share a destination*（本文主要参考，含 Godot 代码与基准测试）
  <https://vav-labs.com/blog/godot-flow-fields-shared-goal/>
- Vav Labs：*Moving 10,000 agents in Godot*（逐单位 A* 在 500 单位崩塌 vs 共享流场撑到 10000 的实测对比）
  <https://vav-labs.com/blog/moving-10000-agents-in-godot/>
- Leif Node：*Flow Field Pathfinding*（整理自 Elijah Emerson 的经典讲解，含图示）
  <https://leifnode.com/2013/12/flow-field-pathfinding/>
- Game AI Pro 第 24 章：*Efficient Crowd Simulation for Mobile Games*（Fieldrunners 2 的工程化流场实现）
  <http://www.gameaipro.com/GameAIPro/GameAIPro_Chapter24_Efficient_Crowd_Simulation_for_Mobile_Games.pdf>
- Patil et al. (2010)：*Directing Crowd Simulations Using Navigation Fields*（导航场的学术奠基论文）
  <https://ics-websites.science.uu.nl/docs/vakken/mcrws/papers_new/Patil%20et%20al%20-%202010%20-%20Directing%20crowd%20simulations%20using%20navigation%20fields.pdf>
- Vav Labs：*Influence maps in Godot*（如何用危险场调制流场代价，与本文组合使用）
  <https://vav-labs.com/blog/godot-influence-maps-tactical-awareness/>
