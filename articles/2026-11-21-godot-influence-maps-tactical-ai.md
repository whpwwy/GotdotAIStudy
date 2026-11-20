# Godot 4 影响图（Influence Map）实战：给网格装上战术危险感

> 日期：2026-11-21
> 系列：Godot AI 编程 · 每日一篇
> 关键词：Influence Map、影响图、战术 AI、危险场、空间推理、AStarGrid2D、影响传播

## 来源链接

- Vav Labs：*Influence maps in Godot: giving a grid a sense of danger*
  <https://vav-labs.com/blog/godot-influence-maps-tactical-awareness/>
- Avery, Louis & Avery：*Evolving Spatial Tactics using Influence Maps*（IEEE CIG 2009）
  <https://www.cse.unr.edu/~sushil/pubs/newestPapers/ogre/newestPapers/2009/cig09/CIG2009/cig09.pdf>
- Godot 官方文档：`AStarGrid2D` 类参考
  <https://docs.godotengine.org/en/stable/classes/class_astargrid2d.html>

---

## 一、最短路径，往往不是活路

在任意一款战术游戏里，你几乎都会遇到这个场景：你命令小队绕过掩体前进，单位却选了那条"数学上最优"的路线——穿过无遮无拦的开阔地，正好落在三个敌人的交叉火力里，几秒钟后全灭。

`AStarGrid2D` 做错了吗？没有。它只被教会了一件事：**距离**。单元格要么能走、要么不能走，能走的里面挑最短的。它不知道哪条走廊被三把枪盯着，不知道开阔地是屠宰场，也不知道玩家凭直觉会选的那条"看着绕远、其实最稳"的路。

想解决这个问题，有两条常见路线：

1. 在寻路之外写一堆 if/else 特判"经过某区域就减速/换路"——很快失控；
2. 把"这片区域有多危险"提前压缩成一张**标量场**，让寻路在常数时间里查表。

第二条路就是我们今天的主角：**影响图（Influence Map，简称 IM）**。

一句话定义：

> 影响图是一张覆盖在关卡网格上的数值场。每个"战术实体"（敌人、友军、目标点、掩体、视野）往自己所在格子盖一个值，再让它向外扩散衰减；任意格子的数值，就是这个位置的"危险/机会"综合评分。

它是《帝国时代》《星际争霸》一类 RTS 的经典 AI 基础设施，也是很多战术射击游戏里"AI 会守点、会包抄、会躲枪线"的底层原因。

---

## 二、影响图到底存了什么

### 2.1 数值按格存储，正负表达立场

影响图与寻路共用同一套格子坐标，因此查表几乎零成本：

```
influence[cell] = Σ(所有来源对该格子的贡献)
```

- **敌人** → 负值（危险）；
- **友军 / 掩体 / 补给点** → 正值（安全、收益）；
- **中立目标** → 正值或单独一层。

把所有来源相加后，任何一个格子都是一个数字。这个数字回答一个问题：**这里被谁控制、争夺得有多激烈。**

### 2.2 传播：让"点"变成"场"

如果只把敌人盖在自己那一格，那么危险就是一个孤立像素点，寻路只能在正好踩到敌人时才知道危险——毫无意义。真实战场上，一个敌人的威胁会向周围弥散：离得越近越危险，越远越安全。

于是影响图构建分两步：

1. **盖章（stamp）**：把每个来源的强度写进它所在格子；
2. **传播（propagate）**：做若干次模糊/扩散，让数值向外渗开，并乘上衰减系数。

两个调参旋钮：

| 参数 | 作用 | 调大 | 调小 |
|---|---|---|---|
| `passes`（扩散次数） | 影响能传多远 | 危险区范围大，整张图都"红" | 只有敌人身边一小圈危险 |
| `decay`（每次衰减） | 数值衰减速度 | 接近 1，影响传得远且平缓 | 接近 0，影响出门就没了 |

### 2.3 读表：O(1) 的战术判断

影响图最大的价值在于**把昂贵的空间推理提前算完**。寻路时不需要再问"这个格子能被几个敌人看到、距离多少"，只需要：

```gdscript
var danger := maxf(-influence_map.get_influence(cell), 0.0)
```

一次数组访问，常数时间。代价是精度：影响图是**近似**，它不知道真实的视线遮挡，只是把"敌人附近大概率危险"编码成了一个场。用误差换性能，这是所有战术层的共同交易。

### 2.4 同一张图，多种战术视角

关键在于"来源如何组合"：

- **威胁图（Threat Map）**：只有敌方影响 → 哪里会被打。
- **控制图（Control Map）**：友方 − 敌方 → 哪边是前线、哪边是己方腹地。
- **张力图（Tension Map）**：双方影响绝对值之和 → 哪里争夺最激烈，适合放狙击/远程。
- **机会图（Opportunity Map）**：目标点 + 补给 + 高地 → 哪里值得去。

工程上通常保留**多层影响图**（danger / ally / objective / cover），运行时按权重合成，而不是把所有东西硬塞进一个数组。

---

## 三、完整可运行示例

### 3.1 准备

- Godot **4.3+**（示例使用 `AStarGrid2D.region`，4.2 及更早版本应改用 `size`）；
- 新建一个 2D 场景，根节点用 `Node2D`，挂载下面的 `demo.gd`；
- 不需要任何美术资源，全部用 `_draw()` 绘制。

项目里新建两个脚本文件：`influence_map.gd` 与 `danger_aware_grid.gd`。

### 3.2 `influence_map.gd`：影响场本体

```gdscript
class_name InfluenceMap
extends RefCounted

var width: int
var height: int
var values := PackedFloat32Array()

func _init(w: int, h: int) -> void:
	width = w
	height = h
	values.resize(w * h)
	values.fill(0.0)

func clear() -> void:
	values.fill(0.0)

func is_in_bounds(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < width and cell.y < height

func index_of(cell: Vector2i) -> int:
	return cell.y * width + cell.x

## 往某个格子叠加影响：敌人用负数，友方/掩体用正数。
func add_influence(cell: Vector2i, strength: float) -> void:
	if is_in_bounds(cell):
		values[index_of(cell)] += strength

func get_influence(cell: Vector2i) -> float:
	if not is_in_bounds(cell):
		return 0.0
	return values[index_of(cell)]

## 若干次邻域平均 + 衰减，把点状影响扩散成场。
func propagate(passes: int, decay: float) -> void:
	var scratch := PackedFloat32Array()
	scratch.resize(values.size())

	for _pass in range(passes):
		for y in range(height):
			for x in range(width):
				var idx := y * width + x
				var total := values[idx]
				var samples := 1.0
				if x > 0:
					total += values[idx - 1]
					samples += 1.0
				if x < width - 1:
					total += values[idx + 1]
					samples += 1.0
				if y > 0:
					total += values[idx - width]
					samples += 1.0
				if y < height - 1:
					total += values[idx + width]
					samples += 1.0
				scratch[idx] = (total / samples) * decay
		values = scratch.duplicate()

## 把峰值归一化到 [-1, 1]，便于统一调参（示例用，生产环境可保留物理量纲）。
func normalize() -> void:
	var peak := 0.0
	for v in values:
		peak = maxf(peak, absf(v))
	if peak < 0.0001:
		return
	var inv := 1.0 / peak
	for i in range(values.size()):
		values[i] *= inv

## 沿梯度找"更安全"的相邻格：返回邻域内影响值最高的格子。
func safest_neighbor(cell: Vector2i, is_blocked: Callable) -> Vector2i:
	var best := cell
	var best_value := get_influence(cell)
	for offset in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]:
		var neighbor: Vector2i = cell + offset
		if not is_in_bounds(neighbor) or is_blocked.call(neighbor):
			continue
		var v := get_influence(neighbor)
		if v > best_value:
			best_value = v
			best = neighbor
	return best
```

几个实现细节值得注意：

- **必须用 `PackedFloat32Array`**。格子数量动辄上万，用普通 `Array[float]` 会产生装箱开销、内存也不连续。
- 传播是**双缓冲**的：如果原地更新，先被修改的格子会污染同一次扩散里的邻居，导致结果依赖遍历顺序（各向异性）。`scratch` 专门解决这个问题。
- `normalize()` 让"最大危险 = 1.0"，这样 `caution` 参数在不同关卡之间可以复用；代价是丢失了绝对强度（一个普通兵和一个精英狙的危险值会被拉到同一量级）。生产项目如果要做"不同敌人不同威胁"，应保留原始量纲、改为按来源加权。

### 3.3 `danger_aware_grid.gd`：把危险塞进寻路成本

Godot 的 `AStarGrid2D` 提供了现成的挂钩：`set_point_weight_scale()`。这个权重会乘进"进入该格子的代价"，于是危险地形"变贵"，但**不是不可通行**——绕路太远时，单位仍会咬牙穿过轻度危险区，这正是我们想要的拟人行为。

```gdscript
class_name DangerAwareGrid
extends RefCounted

var astar := AStarGrid2D.new()
var influence: InfluenceMap

func setup(w: int, h: int, cell_size: int, map: InfluenceMap) -> void:
	influence = map
	astar.region = Rect2i(0, 0, w, h)
	astar.cell_size = Vector2(cell_size, cell_size)
	astar.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	astar.default_compute_heuristic = AStarGrid2D.HEURISTIC_OCTILE
	astar.default_estimate_heuristic = AStarGrid2D.HEURISTIC_OCTILE
	astar.update()

func set_blocked(cell: Vector2i, blocked: bool) -> void:
	astar.set_point_solid(cell, blocked)

func is_blocked(cell: Vector2i) -> bool:
	return astar.is_point_solid(cell)

## 危险抬高"进入成本"：cost = 距离 × (1 + caution × danger)
## caution 越大，单位越怕死（愿意绕更远的路）。
func refresh_weights(caution: float) -> void:
	for y in range(influence.height):
		for x in range(influence.width):
			var cell := Vector2i(x, y)
			if astar.is_point_solid(cell):
				continue
			var danger := maxf(-influence.get_influence(cell), 0.0)
			astar.set_point_weight_scale(cell, 1.0 + caution * danger)

func find_path(from: Vector2i, to: Vector2i) -> Array[Vector2i]:
	if astar.is_point_solid(from) or astar.is_point_solid(to):
		return []
	return astar.get_id_path(from, to)
```

> `AStarGrid2D` 的 `weight_scale` 是**乘性**的，并且会影响启发式估计，所以它不保证严格最短路径——这正好符合"战术上更合理"的诉求，但不要在需要严格最短路的场景（如轨道跟随）里用它。

### 3.4 `demo.gd`：可视化演示

```gdscript
extends Node2D

const CELL_SIZE := 32
const GRID_W := 24
const GRID_H := 14
const SPEED := 160.0

var influence := InfluenceMap.new(GRID_W, GRID_H)
var nav_grid := DangerAwareGrid.new()

var path: Array[Vector2i] = []
var agent_cell := Vector2i(2, 11)
var agent_pos := Vector2.ZERO
var goal_cell := Vector2i(21, 2)
var caution := 6.0

func _ready() -> void:
	nav_grid.setup(GRID_W, GRID_H, CELL_SIZE, influence)
	# 一段不可通行的墙体（实心格子）
	for x in range(9, 12):
		nav_grid.set_blocked(Vector2i(x, 7), true)

	agent_pos = _center(agent_cell)
	_rebuild_influence()

## 盖章 → 传播 → 归一化 → 刷新寻路权重
func _rebuild_influence() -> void:
	influence.clear()
	for enemy_cell in [Vector2i(13, 5), Vector2i(15, 3), Vector2i(12, 9)]:
		influence.add_influence(enemy_cell, -20.0)      # 敌人 = 负影响
	influence.add_influence(Vector2i(4, 5), 10.0)       # 友方据点
	influence.add_influence(Vector2i(20, 11), 10.0)     # 补给点
	influence.propagate(7, 0.93)
	influence.normalize()
	nav_grid.refresh_weights(caution)
	_repath()

func _repath() -> void:
	path = nav_grid.find_path(agent_cell, goal_cell)
	if not path.is_empty() and path[0] == agent_cell:
		path.remove_at(0)
	queue_redraw()

func _process(delta: float) -> void:
	if path.is_empty():
		return
	var target := _center(path[0])
	agent_pos = agent_pos.move_toward(target, SPEED * delta)
	if agent_pos.distance_to(target) < 0.5:
		agent_cell = path[0]
		path.remove_at(0)
		if path.is_empty():
			queue_redraw()

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed \
			and event.button_index == MOUSE_BUTTON_LEFT:
		var cell := Vector2i((event.position / CELL_SIZE).floor())
		if influence.is_in_bounds(cell) and not nav_grid.is_blocked(cell):
			goal_cell = cell
			_repath()
	elif event is InputEventKey and event.pressed and event.keycode == KEY_SPACE:
		# 空格切换"莽夫 / 谨慎"两档
		caution = 0.0 if caution > 0.0 else 6.0
		nav_grid.refresh_weights(caution)
		_repath()

func _draw() -> void:
	for y in range(GRID_H):
		for x in range(GRID_W):
			var cell := Vector2i(x, y)
			var rect := Rect2(Vector2(cell) * CELL_SIZE, Vector2.ONE * CELL_SIZE)
			draw_rect(rect, _cell_color(cell))
			draw_rect(rect, Color(1, 1, 1, 0.05), false, 1.0)

	for i in range(path.size() - 1):
		draw_line(_center(path[i]), _center(path[i + 1]), Color(1.0, 0.8, 0.2), 2.0)

	draw_circle(_center(goal_cell), CELL_SIZE * 0.22, Color(0.95, 0.85, 0.25))
	draw_circle(agent_pos, CELL_SIZE * 0.3, Color(0.25, 0.65, 1.0))
	draw_string(
		ThemeDB.fallback_font, Vector2(8, 20),
		"caution = %.1f  |  左键设置目标，空格切换 0 / 6" % caution,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color(0.9, 0.9, 0.9)
	)

func _cell_color(cell: Vector2i) -> Color:
	if nav_grid.is_blocked(cell):
		return Color(0.08, 0.08, 0.10)
	var value := influence.get_influence(cell)
	var base := Color(0.14, 0.15, 0.19)
	if value < 0.0:
		return base.lerp(Color(0.85, 0.2, 0.2), clampf(-value, 0.0, 1.0) * 0.85)
	if value > 0.0:
		return base.lerp(Color(0.2, 0.75, 0.45), clampf(value, 0.0, 1.0) * 0.85)
	return base

func _center(cell: Vector2i) -> Vector2:
	return Vector2(cell) * CELL_SIZE + Vector2.ONE * CELL_SIZE * 0.5
```

### 3.5 运行效果

运行后你会看到：

- 红色渐变的"火力覆盖区"围绕三个敌人散开，绿色区域是友方据点与补给点；
- 蓝色单位从右下角前往右上角时，路径会**贴着火力的边缘绕行**，而不是直线穿过最红的格子；
- 按空格把 `caution` 从 `6` 切到 `0`，同一目标点会立刻变回"最短直穿"路线——这是最直观的对照实验；
- 左键点任意空格，单位会重新规划路线。

这个"按一下空格"的对比，就是影响图存在的全部理由。

---

## 四、进阶用法

### 4.1 用梯度做"逃离"与"站位"

`propagate()` 之后，影响场天然带有梯度：数值上升的方向就是变安全的方向。`safest_neighbor()` 就是最朴素的梯度上升：

```gdscript
# 受击后撤退：每帧朝更安全的邻格移动一格
if health_ratio < 0.3 and is_blocked.call == null:
	var escape_cell := influence.safest_neighbor(agent_cell, nav_grid.is_blocked)
	if escape_cell != agent_cell:
		goal_cell = escape_cell
		_repath()
```

同样的梯度可以反过来用：远程单位寻找"能打到敌人、但自己所在地危险值较低"的格子，本质上就是一次带约束的局部搜索，比暴力枚举所有掩体便宜得多。

### 4.2 多层叠加

真实项目里建议分层，再按角色合成：

```gdscript
# 每一层都是独立的 InfluenceMap
var danger := InfluenceMap.new(w, h)     # 敌方火力
var control := InfluenceMap.new(w, h)    # 己方控制
var cover := InfluenceMap.new(w, h)      # 掩体质量

func combined(cell: Vector2i) -> float:
	return (
		-1.0 * danger.get_influence(cell)
		+ 0.6 * control.get_influence(cell)
		+ 1.2 * cover.get_influence(cell)
	)
```

权重就是"性格"：把 `cover` 权重调高，AI 会变成谨慎的掩体流；把 `danger` 权重调低，它会变成敢死队。同一个场，配合每单位一个 `caution` 参数，就能生成一整条从新兵到老兵的难度曲线。

### 4.3 更新预算：不要每帧重建

影响图最大的性能陷阱是"每帧全量重建"。实际上战术态势的变化是以**人**的感知尺度发生的，0.2~0.5 秒更新一次完全够用。常见做法：

- **节流重建**：`if Engine.get_physics_frames() % 15 == 0: _rebuild_influence()`；
- **脏区域重建**：只有少量敌人移动时，清空并重盖它们影响的局部窗口，再只对该窗口做几次扩散；
- **分层更新频率**：静态掩体层只建一次；目标点层 1 秒一次；敌人层 0.25 秒一次。

用 1/4 秒的"过期危险"换 60 帧的稳定性能，在任何游戏里都是划算的——一个对 0.25 秒前敌情做出反应的 AI，依然比完全不知道危险的 AI 聪明得多。

### 4.4 与 Dijkstra map / 流场配合

影响图只回答"哪里危险"，不回答"怎么去目标"。生产环境里通常三者并存：

| 结构 | 回答的问题 | 适合场景 |
|---|---|---|
| 影响图 | 哪里安全 / 哪里收益高 | 战术选点、危险绕行 |
| Dijkstra map | 每个格子到目标的距离与方向 | 灵活目标、逃跑、吸引（attraction） |
| 流场（Flow Field） | 每个格子的固定方向 | 大量单位共享同一目的地 |

三者可以叠加：单位沿 Dijkstra map 朝目标推进，同时用影响图对代价加权，于是"同样近的两条路里选更安全的那条"。

### 4.5 参考论文里的用法

Avery 等人的论文把影响图当作**进化算法的基因组**：每个个体由若干影响图构成，再把这些图叠加成空间目标，交给 A* 生成航点。这提示了一个很有意思的扩展方向——影响图的**权重**（而不只是位置）本身就是可学习的参数。你可以先用 `caution`、层权重做手工调参，后面再把它们交给遗传算法或强化学习去优化。

---

## 五、实践要点

1. **危险只加成本，不封路。** 用 `weight_scale` 而非 `solid`。封路会让 AI 在"无路可走"和"必死"之间二选一，而加权能在两者之间给出合理折中。
2. **先盖章，再传播，最后归一化。** 顺序错了（比如先传播后盖章）会让危险只有孤立的一点，整个系统形同虚设。
3. **一定用双缓冲传播。** 原地更新会让扩散方向依赖遍历顺序，出现"往左上偏"的诡异条纹。
4. **`passes` 和 `decay` 必须一起调。** 只加 `passes` 会让整张图发红；只加 `decay` 会让影响传不出去。经验起点：`passes = 6~8`、`decay = 0.9~0.95`，再用归一化兜底。
5. **每个单位一个 `caution`。** 侦察兵低、重装兵高，一行参数就能拉开行为差异，比写十套状态机便宜。
6. **只用负值算危险。** `maxf(-value, 0.0)` 保证友方据点被误当成"负危险"导致寻路偏爱危险区——这是最容易犯的符号错误。
7. **可视化调试必须做。** 影响图是隐形的；用 `_draw()` 或 `TileMapLayer` 把热力图画出来，否则你永远不知道 AI 为什么绕路。生产项目建议再叠一层"为什么这条路径更贵"的路径代价标注。
8. **注意数值量纲。** 示例归一化是为了教学；真实项目中若需要区分"精英狙"和"杂兵"，请保留原始强度并只调整 `caution` 的上下限。
9. **地图边界要特殊处理。** 位于边缘的格子邻居更少，传播时如果不按实际邻居数取平均，边界会系统性地偏亮或偏暗。
10. **它不替代视线检测。** 影响图是近似；需要精确"是否能看见"时，仍需 `RayCast` / 视野锥（见本系列感知系统一篇）。

## 六、常见坑速查

| 现象 | 可能原因 | 修复 |
|---|---|---|
| 路径完全不避让 | `refresh_weights()` 未调用，或 `caution = 0` | 在 `_repath()` 前刷新权重 |
| 整张图全是红的 | `passes` 过多 / `decay` 过高 / 未归一化 | 降参数或归一化 |
| 危险值恒为 0 | 敌人盖的是正值，读取时取反后为 0 | 敌人用负值盖章 |
| 扩散出现方向性条纹 | 原地更新（无双缓冲） | 用 `scratch` 双缓冲 |
| 边界数值异常 | 邻居数未按实际计算 | 用 `samples` 记录真实邻居数 |
| 帧率骤降 | 每帧全量重建 | 节流 + 脏区域重建 |
| 找不到路径 | 起点/终点是 `solid` | 检查目标点是否可走 |

---

## 七、延伸阅读

- Vav Labs：*Influence maps in Godot: giving a grid a sense of danger*
  <https://vav-labs.com/blog/godot-influence-maps-tactical-awareness/>
- Vav Labs：*Dijkstra maps for roguelike AI in Godot*
  <https://vav-labs.com/blog/dijkstra-maps-for-roguelike-ai/>
- Vav Labs：*Flow fields in Godot: pathfinding for crowds that share a destination*
  <https://vav-labs.com/blog/godot-flow-fields-shared-goal/>
- Avery, P., Louis, S. J., & Avery, B.：*Evolving Spatial Tactics using Influence Maps*（IEEE CIG 2009）
  <https://www.cse.unr.edu/~sushil/pubs/newestPapers/ogre/newestPapers/2009/cig09/CIG2009/cig09.pdf>
- Godot 文档：`AStarGrid2D` 类参考
  <https://docs.godotengine.org/en/stable/classes/class_astargrid2d.html>
- Godot 文档：*Using NavigationAgents*（与本系列寻路篇搭配阅读）
  <https://docs.godotengine.org/en/stable/tutorials/navigation/navigation_using_navigationagents.html>
