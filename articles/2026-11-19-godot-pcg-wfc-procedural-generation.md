# Godot 4 PCG 实战：用 Wave Function Collapse 与噪声生成程序化地牢

- **日期**：2026-11-19（Asia/Shanghai）
- **主题**：PCG 程序化生成、Wave Function Collapse、约束传播、FastNoiseLite
- **引擎版本**：Godot 4.3+（使用 `TileMapLayer`）
- **来源**：
  - [Procedural Generation in Godot 4: 5 Patterns from Real Indie Games — Ziva](https://ziva.sh/blogs/godot-procedural-generation)
  - [AlexeyBond/godot-constraint-solving（Godot 4 的 WFC / 约束求解器）](https://github.com/AlexeyBond/godot-constraint-solving)
  - [mxgmn/WaveFunctionCollapse（WFC 算法原始实现）](https://github.com/mxgmn/WaveFunctionCollapse)
  - [Godot 4 Procedural Dungeon Generator Tutorial — Coding Quests](https://codingquests.io/quests/3d-roguelike-dungeon-run)
  - [FastNoiseLite 类参考 — Godot 官方文档](https://docs.godotengine.org/en/stable/classes/class_fastnoiselite.html)

---

## 一、为什么 PCG 是「AI 编程」的一部分

在游戏 AI 的语境里，**PCG（Procedural Content Generation，程序化内容生成）** 与行为树、寻路、GOAP 属于同一条工具链：前者生成「世界」，后者驱动「角色」。一个会自己规划路径的敌人，如果每次都走在同一张手工关卡里，体验会迅速枯竭；而程序化生成能持续提供新的空间结构，让 AI 有东西可探索、可战斗、可决策。

本篇文章聚焦两种最容易落地、又最常被组合使用的技术：

1. **Wave Function Collapse（WFC，波函数坍缩）**：从局部邻接规则出发，生成整体协调的关卡布局。
2. **FastNoiseLite 噪声**：生成连续、自然的生物群系/地形权重。

二者可以叠加：WFC 负责「结构」，噪声负责「气候」。本文先给出一份可直接运行的 WFC 实现，再说明如何把噪声接进来。

---

## 二、核心概念

### 2.1 WFC 的直觉：叠加态 → 观测 → 传播

WFC 借用了量子力学的一个比喻，但算法本身非常朴素：

- **叠加态（Superposition）**：每个格子初始都可能是所有图块之一。
- **观测（Observe / Collapse）**：挑一个最「确定」的格子（可选图块最少，即**熵最小**），按权重随机选定一个图块。
- **传播（Propagate）**：该选择会限制邻居的可选项，邻居再限制它们的邻居……逐层收缩，直到稳定。
- 若某个格子的可选项被削减为 0，说明出现**矛盾（contradiction）**，本次生成失败，换一个种子重来。

这套「最小熵优先 + 约束传播」的策略，就是 WFC 能在几十毫秒内生成协调布局的原因。

### 2.2 三个关键工程细节

| 细节 | 说明 |
|---|---|
| **邻接规则** | 决定「什么能挨着什么」。可以从示例地图中学习，也可以像本文一样手写对称规则。 |
| **熵最小化** | 每次只坍缩最确定的格子，能显著降低矛盾率。 |
| **确定性种子** | 用 `RandomNumberGenerator.seed` 固定随机源，同一个种子必然复现同一张地图，便于调试与分享。 |

### 2.3 与噪声的分工

| 技术 | 擅长 | 不适合 |
|---|---|---|
| WFC | 房间、走廊、城市街区等**离散结构** | 连续起伏的地表高度 |
| FastNoiseLite | 高度、湿度、温度等**连续场** | 精确的房间连通性 |

实践中的常见做法是：先用噪声算出每格的「生物群系倾向」，再把它作为 WFC 坍缩时的**权重**，让水塘更愿意出现在低洼处、石堆更愿意出现在高处。

---

## 三、可运行代码：WFC 地牢生成器

### 3.1 场景准备

新建场景，结构如下：

```
WFCLevel (Node2D)          # 挂载 wfc_level.gd
├── Ground (TileMapLayer)  # 需要配置好 TileSet
└── Camera2D
```

在 `Ground` 的 `TileSet` 中准备 4 个图块（草地、沙地、水、石头），并把它们的 `source_id` / `atlas_coords` 填到下面的导出变量里。地图尺寸 32×18、每格 16px 时，把 `Camera2D` 的缩放调到约 `2.2` 即可完整看到。

### 3.2 完整脚本 `wfc_level.gd`

```gdscript
extends Node2D
## 基于 Wave Function Collapse 的程序化地牢生成器（Godot 4.3+）
##
## 思路：每个格子维护一个「可选图块」位掩码；
## 反复执行 1) 选熵最小的格子坍缩  2) 约束传播，
## 直到所有格子只剩一个图块，最后写入 TileMapLayer。

@export var map_size: Vector2i = Vector2i(32, 18)
@export var seed_value: int = 0
@export var max_attempts: int = 20

@export_group("TileSet 映射")
@export var source_id: int = 0
@export var grass_atlas: Vector2i = Vector2i(0, 0)
@export var sand_atlas: Vector2i = Vector2i(1, 0)
@export var water_atlas: Vector2i = Vector2i(2, 0)
@export var stone_atlas: Vector2i = Vector2i(3, 0)

@onready var ground: TileMapLayer = $Ground

enum Tile { GRASS, SAND, WATER, STONE }
const TILE_COUNT := 4
const DIRS: Array[Vector2i] = [
	Vector2i.RIGHT, Vector2i.DOWN, Vector2i.LEFT, Vector2i.UP
]

## 对称邻接表：key 的图块四周允许出现 value 中的图块。
## 注意：规则必须对称，即 a 允许 b 时，b 也必须允许 a。
const ADJACENT := {
	Tile.GRASS: [Tile.GRASS, Tile.GRASS, Tile.SAND, Tile.STONE],
	Tile.SAND:  [Tile.SAND, Tile.GRASS, Tile.WATER],
	Tile.WATER: [Tile.WATER, Tile.WATER, Tile.SAND],
	Tile.STONE: [Tile.STONE, Tile.GRASS, Tile.SAND],
}

## 坍缩权重：草地最多，石头最少。
const WEIGHTS := [0.42, 0.24, 0.22, 0.12]

var _w: int
var _h: int
var _domains := PackedInt32Array()   # 每个格子的可选图块位掩码
var _rng := RandomNumberGenerator.new()

func _ready() -> void:
	generate()

func generate() -> void:
	_w = map_size.x
	_h = map_size.y
	ground.clear()

	for attempt in max_attempts:
		var used_seed := seed_value + attempt
		if _try_generate(used_seed):
			_render()
			print("WFC 生成成功，种子 = ", used_seed)
			return
		push_warning("WFC 第 %d 次出现矛盾，重试……" % (attempt + 1))

	push_error("WFC 连续 %d 次失败，请放宽邻接规则。" % max_attempts)

func _try_generate(used_seed: int) -> bool:
	_rng.seed = used_seed
	_domains.resize(_w * _h)
	_domains.fill((1 << TILE_COUNT) - 1)   # 全部图块都可能是候选

	# 预置一角为草地，给生成一个确定性的起点
	_domains[0] = 1 << Tile.GRASS

	while true:
		var idx := _pick_min_entropy_cell()
		if idx == -1:
			return true                    # 所有格子都已确定
		_collapse(idx)
		if not _propagate(idx):
			return false                   # 出现矛盾，放弃本次尝试
	return true

## 返回熵最小（候选最少）且未确定的格子索引；并列时随机挑一个。
func _pick_min_entropy_cell() -> int:
	var best_count := TILE_COUNT + 1
	var candidates: Array[int] = []
	for i in _domains.size():
		var c := _popcount(_domains[i])
		if c <= 1:
			continue
		if c < best_count:
			best_count = c
			candidates.clear()
			candidates.append(i)
		elif c == best_count:
			candidates.append(i)
	if candidates.is_empty():
		return -1
	return candidates[_rng.randi_range(0, candidates.size() - 1)]

## 按权重在候选图块中随机选定一个。
func _collapse(idx: int) -> void:
	var options := _tiles_of(_domains[idx])
	var total := 0.0
	for t in options:
		total += WEIGHTS[t]
	var roll := _rng.randf() * total
	var chosen: int = options[0]
	for t in options:
		roll -= WEIGHTS[t]
		if roll <= 0.0:
			chosen = t
			break
	_domains[idx] = 1 << chosen

## 约束传播：邻居的可选项必须与当前格子的选择相容。
func _propagate(start: int) -> bool:
	var stack: Array[int] = [start]
	while not stack.is_empty():
		var idx: int = stack.pop_back()
		var x := idx % _w
		var y := idx / _w

		for d in DIRS:
			var nx := x + d.x
			var ny := y + d.y
			if nx < 0 or nx >= _w or ny < 0 or ny >= _h:
				continue

			var n_idx := ny * _w + nx
			var allowed_mask := 0
			for t in _tiles_of(_domains[idx]):
				for nt in ADJACENT[t]:
					allowed_mask |= 1 << nt

			var new_mask: int = _domains[n_idx] & allowed_mask
			if new_mask == 0:
				return false                   # 邻居无路可走 → 矛盾
			if new_mask != _domains[n_idx]:
				_domains[n_idx] = new_mask
				stack.append(n_idx)
	return true

func _render() -> void:
	for y in _h:
		for x in _w:
			var t: int = _tiles_of(_domains[y * _w + x])[0]
			ground.set_cell(Vector2i(x, y), source_id, _atlas_of(t))

func _atlas_of(t: int) -> Vector2i:
	match t:
		Tile.GRASS: return grass_atlas
		Tile.SAND:  return sand_atlas
		Tile.WATER: return water_atlas
		Tile.STONE: return stone_atlas
	return grass_atlas

func _tiles_of(mask: int) -> Array[int]:
	var out: Array[int] = []
	for t in TILE_COUNT:
		if mask & (1 << t):
			out.append(t)
	return out

func _popcount(mask: int) -> int:
	var c := 0
	while mask != 0:
		c += mask & 1
		mask >>= 1
	return c
```

### 3.3 如何验证它真的能跑

1. 把脚本挂到根节点 `WFCLevel`，确认 `Ground` 已配置 `TileSet`。
2. 设置相同的 `source_id` 与四个 `atlas_coords`。
3. 按 F6 运行：输出面板应打印「WFC 生成成功，种子 = …」。
4. 改变 `seed_value` 会得到不同但同样合理的布局；改回原值则完全复现。

---

## 四、把噪声接进来：生物群系权重

WFC 的权重不一定是常数。用 `FastNoiseLite` 生成一张连续场，就能让地图出现「低洼多水、高地多石」的倾向，而结构仍然由 WFC 保证协调。

```gdscript
extends Node
## 用噪声为每个格子计算「湿度」，作为 WFC 坍缩时的权重偏置。

var noise := FastNoiseLite.new()

func _ready() -> void:
	noise.seed = 20261119
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.06
	noise.fractal_octaves = 3
	noise.fractal_lacunarity = 2.0
	noise.fractal_gain = 0.5

## 返回形如 [草地, 沙地, 水, 石头] 的权重数组。
func biome_weights(x: int, y: int) -> Array[float]:
	var n := (noise.get_noise_2d(x, y) + 1.0) * 0.5   # 归一化到 [0, 1]
	var water := lerpf(0.06, 0.40, n * n)             # 湿度低 → 更可能出水
	var stone := lerpf(0.08, 0.30, 1.0 - n * 0.6)     # 高处 → 更多石头
	var sand := 0.20
	var grass := maxf(0.05, 1.0 - water - stone - sand)
	return [grass, sand, water, stone]
```

接入方式只有一行：把 `_collapse()` 里的 `WEIGHTS[t]` 换成 `_weights_for(idx)[t]`。这样「结构靠 WFC、气候靠噪声」的分层设计就完成了。

---

## 五、实践要点

1. **先跑通再美化**。把 `TILE_COUNT` 缩到 2–3 种图块、把地图缩到 10×6，五分钟内就能验证算法是否正确。
2. **规则必须对称**。`a` 允许 `b`，就必须让 `b` 也允许 `a`，否则传播会在边界反复抖动甚至死循环。
3. **留出重试机制**。WFC 出现矛盾是正常现象，`max_attempts` + 种子偏移是最简单可靠的兜底。
4. **固定种子便于复现**。调试时打印实际使用的种子，玩家侧则可以用「种子码」分享地图。
5. **性能观察点**。最小熵搜索是 O(格子数)，传播是局部的；32×18 的规模在 Godot 里通常一帧内完成。真正的地图变大时，优先考虑分块生成，而不是优化位运算。
6. **生成后再烘焙导航**。若敌人需要寻路，请在生成完 `TileMapLayer` 之后重建 `NavigationRegion2D` 的多边形，否则 `NavigationAgent2D` 会按旧地形计算路径。
7. **不要手改自动产物**。如果你把本文接入每日自动归档脚本，`README.md` 与 `INDEX.md` 都应由脚本重建，避免人工编辑导致统计漂移。

---

## 六、延伸阅读

- [Procedural Generation in Godot 4: 5 Patterns from Real Indie Games](https://ziva.sh/blogs/godot-procedural-generation) —— BSP、噪声、WFC 等五种实战模式对比
- [AlexeyBond/godot-constraint-solving](https://github.com/AlexeyBond/godot-constraint-solving) —— Godot 4 的 WFC 与通用约束求解插件，生产可用
- [mxgmn/WaveFunctionCollapse](https://github.com/mxgmn/WaveFunctionCollapse) —— Maxim Gumin 的原始实现，理解算法的最佳起点
- [Godot 4 Procedural Dungeon Generator Tutorial](https://codingquests.io/quests/3d-roguelike-dungeon-run) —— 从 GridMap 到运行时生成完整地牢
- [FastNoiseLite 类参考](https://docs.godotengine.org/en/stable/classes/class_fastnoiselite.html) —— 噪声类型、分形参数与频率调节
- [NavigationAgent2D 类参考](https://docs.godotengine.org/en/stable/classes/class_navigationagent2d.html) —— 生成地形后为敌人重建寻路
