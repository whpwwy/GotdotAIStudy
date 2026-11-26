# Godot 4 对抗搜索实战：用 Negamax 与 Alpha-Beta 剪枝打造四子棋 AI

- **日期**：2026-11-27（Asia/Shanghai）
- **适用版本**：Godot 4.x（GDScript，无需插件或外部服务）
- **难度**：进阶
- **主题关键词**：Minimax、Negamax、Alpha-Beta Pruning、对抗搜索、极大极小、四子棋、Connect Four、着法排序、深度限制
- **来源链接**：
  - [cite:1] [Knuth & Moore：An Analysis of Alpha-Beta Pruning](http://www-public.telecom-sudparis.eu/~gibson/Teaching/Teaching-ReadingMaterial/KnuthMoore75.pdf)
  - [cite:2] [Exploring Board Game AI Algorithms: Minimax](https://balkarjun.github.io/blog/minimax-connect-four/)
  - [cite:3] [Charles University：Depth-Limited Searching and Alpha-Beta Pruning](https://ksvi.mff.cuni.cz/~dingle/2022-3/prog_2/notes_11.html)
  - [cite:4] [Godot Asset Library：Chess（Negamax 与 Alpha-Beta 项目）](https://godotengine.org/asset-library/asset/5484)

> 与历史文章的边界：此前的 MCTS 文章通过随机模拟、访问次数和 UCB1 选择行动；本文不使用随机 rollout、不维护模拟统计，也不训练模型，而是对确定棋局执行**极大极小对抗搜索**，用 Negamax 统一分数视角，再用 Alpha-Beta 剪去不可能影响最终决策的分支。案例也从井字棋改为具有重力落子规则的 6×7 四子棋。

---

## 一、为什么四子棋适合学习对抗搜索

四子棋由双方轮流把棋子投入七列之一，棋子落到该列最低的空位；任意一方先在水平、垂直或对角方向连成四子即获胜。标准棋盘为 6 行 7 列，因此状态可以紧凑地保存为长度为 42 的数组。[cite:2]

这个案例同时具备三个适合教学的特征：

- **完全信息**：双方都能看到完整棋盘，不需要推断隐藏状态；
- **离散行动**：每一步只需从尚未填满的列中选择一列；
- **明确终局**：一方连成四子或棋盘满员，搜索就能给出确定结果。

Minimax 的思想是：己方节点选择分数最高的后继，对手节点选择分数最低的后继。Negamax 利用零和对抗中的对称关系，把每一层都写成“当前行棋方最大化分数”，子节点返回值取负即可。这样不必在代码中交替维护 `max` 与 `min` 两套分支。[cite:2]

但四子棋不能总是在可接受的时间内穷举到终局。实际做法是限制搜索深度，到达叶子时用启发式函数估计局面价值。深度限制让计算量可控，也意味着非终局叶子的分数只是估计，而不是必胜或必败证明。[cite:3]

---

## 二、核心概念

### 2.1 从 Minimax 到 Negamax

传统 Minimax 可以始终站在 AI 视角计分：AI 层取最大值，玩家层取最小值。Negamax 改为始终站在**当前行棋方**视角计分，并使用下面的递归关系：

\[
value(s, player) = \max_{move}\left(-value(apply(s, move), opponent)\right)
\]

代码中的关键一行是：

```gdscript
score = -_negamax(next_state, _opponent(player), depth - 1, -beta, -alpha)
```

这里同时发生了两件事：

1. 子节点分数取负，因为“对手越好”就意味着“当前方越差”；
2. 交换并取负 `alpha`、`beta`，把当前搜索窗口转换成对手视角。

如果递归时只把分数取负，却原样传递窗口，剪枝条件就会失去正确语义。

### 2.2 Alpha-Beta 为什么能安全剪枝

Alpha-Beta 在搜索路径上维护一个窗口：

- `alpha`：当前 maximizing 一方已经能够保证的最好结果；
- `beta`：对手允许当前方达到的上界；
- 当 `alpha >= beta` 时，剩余兄弟分支不可能改变祖先节点的最终选择，可以停止搜索。

Alpha-Beta 不是用近似结果换速度。在相同深度、相同终局判断和相同评估函数下，正确实现不会改变完整 Minimax 所选择的行动，只会避免访问无关分支。Knuth 与 Moore 的论文给出了正确性证明和性能分析；四子棋教程也用逐步搜索树解释了截止条件。[cite:1][cite:2]

本示例使用 fail-soft 写法：`value` 可以超出原始窗口，发生截止时直接返回当前已找到的值。根节点只使用 `score > best_score` 更新最佳行动，因此同分时保留着法顺序中更早的列。

### 2.3 为什么先搜索中间列

`MOVE_ORDER = [3, 2, 4, 1, 5, 0, 6]` 让中间列优先，再向两侧交替展开。着法排序不会改变无深度限制的博弈值，但会改变 Alpha-Beta 多快收窄窗口：越早发现强着，后续无效分支越容易被剪掉。[cite:1]

中心优先同时是适合四子棋的轻量启发式，因为中心位置能参与更多潜在连线。不过，**搜索顺序与局面评分是两回事**：前者决定访问次序，后者决定深度耗尽时如何评价叶子，不应混为一个参数。

### 2.4 深度耗尽后怎样评分

示例评估函数从当前行棋方视角计算：

\[
evaluation = positional(player) - positional(opponent)
\]

`positional()` 扫描所有长度为四的窗口：

| 窗口内容 | 计分 | 含义 |
|---|---:|---|
| 只有 1 枚己方棋子，其余为空 | +1 | 保留一个潜在方向 |
| 只有 2 枚己方棋子，其余为空 | +12 | 已形成弱威胁 |
| 只有 3 枚己方棋子，其余为空 | +120 | 下一手可能形成强威胁 |
| 中心列的一枚棋子 | 额外 +4 | 轻量位置偏好 |

对手使用同一函数计分，再从己方得分中减去。终局不依赖这些较小的启发式分数，而是返回 `WIN_SCORE + depth`：胜利必须压倒普通位置分；剩余深度越大，表示从根节点越快获胜，因此优先选择更快的胜利，并尽量推迟不可避免的失败。

---

## 三、单文件可运行示例

### 3.1 运行方法

1. 新建 Godot 4 项目和一个 2D 场景，根节点选择 `Node2D`；
2. 新建 `negamax_connect_four.gd`，粘贴下面完整代码并挂到根节点；
3. 按 F5 运行，点击棋盘某一列，玩家执蓝色棋子并先手；
4. AI 执橙色棋子，默认搜索 5 ply；输出最佳列、访问节点数和耗时；
5. 按 R 重新开始。设备性能较低时，可先把 `SEARCH_DEPTH` 改为 4。

搜索采用同步写法，便于集中观察算法。较大深度会阻塞主线程，工程化改造见后文。

### 3.2 完整 GDScript

```gdscript
extends Node2D
## Godot 4.x：玩家执蓝先手，Negamax + Alpha-Beta AI 执橙。
## 新建 Node2D 根节点并挂载本脚本；点击列落子，按 R 重开。

const EMPTY := 0
const HUMAN := 1
const AI := 2
const ROWS := 6
const COLS := 7
const CELL_COUNT := ROWS * COLS
const SEARCH_DEPTH := 5
const WIN_SCORE := 1000000.0

const CELL_SIZE := 78.0
const BOARD_ORIGIN := Vector2(60, 120)
const BOARD_SIZE := Vector2(COLS * CELL_SIZE, ROWS * CELL_SIZE)
const MOVE_ORDER := [3, 2, 4, 1, 5, 0, 6]
const DIRECTIONS := [
	Vector2i(1, 0),   # 水平
	Vector2i(0, 1),   # 垂直
	Vector2i(1, 1),   # 右下对角线
	Vector2i(1, -1),  # 右上对角线
]

var board: Array[int] = []
var ai_busy := false
var status_text := "轮到你：点击一列投入蓝色棋子"
var nodes_visited := 0
var last_search_ms := 0.0


func _ready() -> void:
	_reset_board()


func _reset_board() -> void:
	board.clear()
	board.resize(CELL_COUNT)
	board.fill(EMPTY)
	ai_busy = false
	status_text = "轮到你：点击一列投入蓝色棋子"
	nodes_visited = 0
	last_search_ms = 0.0
	queue_redraw()


# ---------------- 基本规则 ----------------

func _index(row: int, col: int) -> int:
	return row * COLS + col


func _opponent(player: int) -> int:
	return HUMAN if player == AI else AI


func _inside(row: int, col: int) -> bool:
	return row >= 0 and row < ROWS and col >= 0 and col < COLS


func _ordered_moves(state: Array) -> Array[int]:
	var moves: Array[int] = []
	# 顶行为空说明该列仍可落子，同时按中心优先排序。
	for col in MOVE_ORDER:
		if state[col] == EMPTY:
			moves.append(col)
	return moves


func _drop(state: Array, col: int, player: int) -> int:
	# 从底行向上寻找最低空位，返回落子行；列满时返回 -1。
	for row in range(ROWS - 1, -1, -1):
		var i := _index(row, col)
		if state[i] == EMPTY:
			state[i] = player
			return row
	return -1


func _has_won(state: Array, player: int) -> bool:
	for row in range(ROWS):
		for col in range(COLS):
			if state[_index(row, col)] != player:
				continue
			for direction in DIRECTIONS:
				var end_row: int = row + direction.y * 3
				var end_col: int = col + direction.x * 3
				if not _inside(end_row, end_col):
					continue
				var matched := true
				for step in range(1, 4):
					var next_row: int = row + direction.y * step
					var next_col: int = col + direction.x * step
					if state[_index(next_row, next_col)] != player:
						matched = false
						break
				if matched:
					return true
	return false


# ---------------- 启发式评估 ----------------

func _positional_score(state: Array, player: int) -> int:
	var total := 0

	# 中心列轻微加分，不让位置偏好压倒真实连线威胁。
	for row in range(ROWS):
		if state[_index(row, 3)] == player:
			total += 4

	for row in range(ROWS):
		for col in range(COLS):
			for direction in DIRECTIONS:
				var end_row: int = row + direction.y * 3
				var end_col: int = col + direction.x * 3
				if not _inside(end_row, end_col):
					continue

				var own := 0
				var other := 0
				for step in range(4):
					var next_row: int = row + direction.y * step
					var next_col: int = col + direction.x * step
					var cell: int = state[_index(next_row, next_col)]
					if cell == player:
						own += 1
					elif cell != EMPTY:
						other += 1

				# 同时含双方棋子的窗口已经无法连成四子，不计分。
				if other == 0:
					match own:
						1:
							total += 1
						2:
							total += 12
						3:
							total += 120
	return total


func _evaluate(state: Array, player: int) -> float:
	var own := _positional_score(state, player)
	var other := _positional_score(state, _opponent(player))
	return float(own - other)


# ---------------- Negamax + Alpha-Beta ----------------

func _negamax(
	state: Array,
	player: int,
	depth: int,
	alpha: float,
	beta: float
) -> float:
	nodes_visited += 1
	var moves := _ordered_moves(state)
	if moves.is_empty():
		return 0.0 # 棋盘满且父节点未检测到胜利，判定为平局。
	if depth <= 0:
		return _evaluate(state, player)

	var value := -INF
	var current_alpha := alpha
	for col in moves:
		var next_state: Array = state.duplicate()
		_drop(next_state, col, player)

		var score := 0.0
		if _has_won(next_state, player):
			# 剩余深度越多，代表越快获胜。
			score = WIN_SCORE + depth
		else:
			score = -_negamax(
				next_state,
				_opponent(player),
				depth - 1,
				-beta,
				-current_alpha
			)

		value = maxf(value, score)
		current_alpha = maxf(current_alpha, value)
		if current_alpha >= beta:
			break # Beta cut-off：余下着法不会改变祖先决策。
	return value


func _find_best_move(start_state: Array, player: int, depth: int) -> int:
	var started := Time.get_ticks_usec()
	nodes_visited = 0
	var best_move := -1
	var best_score := -INF
	var alpha := -INF
	var beta := INF

	for col in _ordered_moves(start_state):
		var next_state: Array = start_state.duplicate()
		_drop(next_state, col, player)

		var score := 0.0
		if _has_won(next_state, player):
			score = WIN_SCORE + depth
		else:
			score = -_negamax(
				next_state, _opponent(player), depth - 1, -beta, -alpha
			)

		if score > best_score:
			best_score = score
			best_move = col
		alpha = maxf(alpha, best_score)

	last_search_ms = (Time.get_ticks_usec() - started) / 1000.0
	print(
		"AI 列 %d | 分数 %.1f | 节点 %d | 深度 %d | %.2f ms" % [
			best_move, best_score, nodes_visited, depth, last_search_ms,
		]
	)
	return best_move


# ---------------- 对局交互 ----------------

func _unhandled_input(event: InputEvent) -> void:
	if ai_busy:
		return
	if not (
		event is InputEventMouseButton
		and event.button_index == MOUSE_BUTTON_LEFT
		and event.pressed
	):
		return

	var mouse_event := event as InputEventMouseButton
	var local: Vector2 = mouse_event.position - BOARD_ORIGIN
	if not Rect2(Vector2.ZERO, BOARD_SIZE).has_point(local):
		return
	if _has_won(board, HUMAN) or _has_won(board, AI):
		return

	var col := int(local.x / CELL_SIZE)
	if _drop(board, col, HUMAN) == -1:
		status_text = "这一列已满，请选择其他列"
		queue_redraw()
		return

	if _update_after_move():
		return

	ai_busy = true
	status_text = "AI 思考中：搜索 %d ply..." % SEARCH_DEPTH
	queue_redraw()
	# 先让“思考中”状态进入绘制队列，再执行本教学示例的同步搜索。
	call_deferred("_run_ai_turn")


func _unhandled_key_input(event: InputEvent) -> void:
	if (
		event is InputEventKey
		and event.pressed
		and not event.echo
		and event.keycode == KEY_R
		and not ai_busy
	):
		_reset_board()


func _run_ai_turn() -> void:
	var move := _find_best_move(board, AI, SEARCH_DEPTH)
	if move >= 0:
		_drop(board, move, AI)
	ai_busy = false
	_update_after_move()
	queue_redraw()


func _update_after_move() -> bool:
	if _has_won(board, HUMAN):
		status_text = "你获胜！按 R 再来一局"
	elif _has_won(board, AI):
		status_text = "AI 获胜，按 R 再挑战"
	elif _ordered_moves(board).is_empty():
		status_text = "平局，按 R 再来一局"
	else:
		status_text = "轮到你：点击一列投入蓝色棋子"
		queue_redraw()
		return false
	queue_redraw()
	return true


# ---------------- 绘制 ----------------

func _draw() -> void:
	var font := ThemeDB.fallback_font
	draw_string(
		font, Vector2(60, 48), "Godot 4 | Negamax + Alpha-Beta",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 28, Color(0.92, 0.95, 1.0)
	)
	draw_string(
		font, Vector2(60, 82), "Connect Four | 你：蓝色 | AI：橙色",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color(0.65, 0.75, 0.88)
	)
	draw_rect(Rect2(BOARD_ORIGIN, BOARD_SIZE), Color(0.10, 0.20, 0.38))

	for row in range(ROWS):
		for col in range(COLS):
			var center := BOARD_ORIGIN + Vector2(
				(col + 0.5) * CELL_SIZE,
				(row + 0.5) * CELL_SIZE
			)
			var color := Color(0.035, 0.055, 0.10)
			match board[_index(row, col)]:
				HUMAN:
					color = Color(0.20, 0.65, 1.0)
				AI:
					color = Color(1.0, 0.55, 0.16)
			draw_circle(center, CELL_SIZE * 0.39, color)

	draw_string(
		font, Vector2(670, 150), status_text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(0.92, 0.95, 1.0)
	)
	draw_string(
		font, Vector2(670, 205), "搜索深度：%d ply" % SEARCH_DEPTH,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(670, 240), "上次访问节点：%d" % nodes_visited,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(670, 275), "上次搜索耗时：%.2f ms" % last_search_ms,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(670, 325), "着法顺序：中间优先，向两侧展开",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(670, 360), "按 R 重新开始",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
```

### 3.3 代码导读

- **真实棋盘与搜索棋盘隔离**：每个候选行动都执行 `state.duplicate()`，递归只修改副本；真实 `board` 仅在玩家点击或 AI 返回最终列后改变。
- **终局优先于叶子评估**：每次落子后先调用 `_has_won()`。只有没有获胜且深度耗尽时，才调用 `_evaluate()`，避免用启发式分数覆盖确定的胜负。
- **Negamax 只有一个最大化分支**：每层都为当前 `player` 选最高分，递归时换玩家、分数取负，并传递 `-beta, -alpha`。
- **平局先于深度评估**：合法行动为空时直接返回 0。这样满棋盘不会被误认为某方的位置优势。
- **根节点保留行动信息**：`_negamax()` 只返回分数，`_find_best_move()` 额外记录产生最高分的列。搜索过程不操作按钮、绘制节点或输入状态。

---

## 四、先用确定局面验证正确性

对抗搜索最容易出现的是符号、终局和状态复制错误，而不是“深度还不够”。可以把下面的测试函数加入同一脚本，并在 `_ready()` 的 `_reset_board()` 后临时调用 `_run_tests()`。

```gdscript
func _run_tests() -> void:
	# 空棋盘在第 3 列落子，应落到最底行（第 5 行）。
	var gravity_board: Array[int] = []
	gravity_board.resize(CELL_COUNT)
	gravity_board.fill(EMPTY)
	var landed_row := _drop(gravity_board, 3, HUMAN)
	assert(landed_row == 5)
	assert(gravity_board[_index(5, 3)] == HUMAN)

	# AI 在底行已有三子，必须选择第 3 列完成四连。
	var win_now: Array[int] = []
	win_now.resize(CELL_COUNT)
	win_now.fill(EMPTY)
	for col in [0, 1, 2]:
		_drop(win_now, col, AI)
	assert(_find_best_move(win_now, AI, 2) == 3)

	# 玩家在底行已有三子，AI 必须选择第 3 列阻挡。
	var must_block: Array[int] = []
	must_block.resize(CELL_COUNT)
	must_block.fill(EMPTY)
	for col in [0, 1, 2]:
		_drop(must_block, col, HUMAN)
	assert(_find_best_move(must_block, AI, 2) == 3)

	# 搜索不得污染传入棋盘。
	var before: Array = must_block.duplicate()
	_find_best_move(must_block, AI, 2)
	assert(must_block == before)
	print("Negamax / Alpha-Beta 最小测试通过")
```

还可以做一项高价值对照实验：临时移除 `if current_alpha >= beta: break`，在相同局面比较最佳列与最终分数。两者应一致，而访问节点数通常不同。若最佳列或分数改变，应优先检查窗口传递、当前玩家视角和终局处理，而不是把问题归因于“剪枝误差”。[cite:1][cite:2]

---

## 五、实践要点与性能边界

### 5.1 不要把搜索深度当成唯一强度旋钮

增加深度通常能让 AI 看到更远的威胁，但也会增加节点数量。更实用的调参顺序是：

1. 用立即获胜、立即必挡和状态不污染测试保证规则正确；
2. 检查评分是否始终站在当前行棋方视角；
3. 用中心优先等着法排序帮助剪枝；
4. 再逐步增加深度，并记录节点数与耗时；
5. 针对具体失误改进评估函数，而不是只盲目加深搜索。

Alpha-Beta 的收益依赖访问次序。若随机打乱 `MOVE_ORDER`，相同搜索仍应给出相同的完整深度结果，但节点数可能明显变化。应把“决策正确性”和“搜索效率”分开测试。

### 5.2 同步深度搜索适合演示，不适合无限加深

示例为了便于阅读，在主线程一次性搜索 5 ply。更深的搜索或更复杂的规则可能让界面停顿。Godot 官方资源库中的 Chess 项目展示了更完整的工程组合：Negamax、Alpha-Beta、迭代加深、时间预算、置换表以及 killer-move／history 着法排序。[cite:4]

迭代加深的含义是依次搜索深度 1、2、3……，在时间耗尽时采用最近一次完整深度的结果。它比“只设定一个很大深度”更容易控制响应时间。需要注意：只有最近一次深度完整搜索完，才能把其结果当成正式结果；中途被截断的一层可以服务于着法排序，但不应贸然覆盖已知最佳行动。

### 5.3 后台搜索只处理纯数据

把搜索迁移到 `Thread` 或 `WorkerThreadPool` 时，应遵守以下边界：

- 工作线程只读取复制出来的棋盘、玩家和深度，不访问 UI 或场景树；
- 不在主线程与工作线程同时修改同一个数组；
- 返回结果时携带棋局版本号，重开或撤销后丢弃旧结果；
- 最终落子和界面更新仍由主线程执行；
- 统计节点数时使用线程局部变量，避免无保护地累加共享计数。

本示例的全局 `nodes_visited` 只适合单线程演示。多线程版本应让每次搜索拥有自己的统计对象。

### 5.4 评估函数不是终局证明

深度限制叶子上的 `+120` 只表示存在一个三连窗口，不代表强制获胜。相反，若搜索已经发现一方连成四子，就应立即返回大幅胜负分，不再执行普通评估。诊断 AI 行为时，可以先打印根节点每一列的分数，区分以下情况：

- 所有非挡着都返回接近 `-WIN_SCORE`：对手存在立即胜利；
- 某列返回接近 `+WIN_SCORE`：搜索发现了确定胜线；
- 各列都只有几十或几百分：当前结果主要来自启发式估计；
- 同分都集中在中心列：可能是着法顺序决定并列结果，不一定是唯一最佳行动。

### 5.5 与 MCTS 的选用差异

| 维度 | Negamax + Alpha-Beta | MCTS |
|---|---|---|
| 叶子信息 | 终局结果或人工评估函数 | 随机或策略引导的模拟结果 |
| 节点选择 | 当前方最大化，窗口剪枝 | UCB1 等公式平衡利用与探索 |
| 必需知识 | 非终局通常需要可靠评估 | 需要可快速模拟的规则与终止条件 |
| 主要优化 | 着法排序、迭代加深、置换表 | 模拟策略、树策略、预算与并行化 |
| 本文与历史案例 | 四子棋确定性深度搜索 | 井字棋随机模拟统计 |

两者都能用于回合制游戏，但“都建立搜索树”不代表算法相同。若评估函数很难设计而终局模拟很便宜，MCTS 值得考虑；若已有可靠评估、希望获得确定性的深度搜索，并需要利用窗口剪枝，Negamax + Alpha-Beta 更直接。[cite:1][cite:2]

---

## 六、迁移到自己的游戏

可以按下面的接口拆分规则与搜索：

1. `ordered_moves(state)`：生成合法行动并决定访问顺序；
2. `apply(state, move)`：返回行动后的新状态，避免共享可变数据；
3. `terminal_value(state, player)`：识别胜负和平局；
4. `evaluate(state, player)`：仅为非终局叶子估计当前方优势；
5. `negamax(...)`：保持与具体游戏规则无关；
6. `find_best_move(...)`：保存根节点行动、分数、深度和统计信息。

迁移到国际象棋、黑白棋或其他离散对抗游戏时，不能只替换绘制代码。行动生成、撤销或复制、终局判断、分数视角和状态缓存键必须一起验证。Godot Chess 项目可以作为一个更复杂的后续阅读对象，但应先确保本示例的最小测试全部通过。[cite:4]

---

## 七、延伸阅读

- [cite:1] [An Analysis of Alpha-Beta Pruning](http://www-public.telecom-sudparis.eu/~gibson/Teaching/Teaching-ReadingMaterial/KnuthMoore75.pdf)：阅读 Alpha-Beta 的形式化定义、正确性证明、深度截止与运行时间分析。
- [cite:2] [Exploring Board Game AI Algorithms: Minimax](https://balkarjun.github.io/blog/minimax-connect-four/)：对照另一种四子棋棋盘表示、Negamax 推导、深度限制与 Alpha-Beta 优化过程。
- [cite:3] [Charles University：Week 11 Notes](https://ksvi.mff.cuni.cz/~dingle/2022-3/prog_2/notes_11.html)：继续学习深度限制、启发式估计以及 alpha／beta 截止条件。
- [cite:4] [Godot Asset Library：Chess](https://godotengine.org/asset-library/asset/5484)：研究 Godot 4 项目如何组合 Negamax、迭代加深、时间预算、置换表与更复杂的着法排序。

## 来源

- [cite:1] [Donald E. Knuth & Ronald W. Moore：An Analysis of Alpha-Beta Pruning](http://www-public.telecom-sudparis.eu/~gibson/Teaching/Teaching-ReadingMaterial/KnuthMoore75.pdf)
- [cite:2] [Arjun Balakrishnan：Exploring Board Game AI Algorithms: Minimax](https://balkarjun.github.io/blog/minimax-connect-four/)
- [cite:3] [Charles University：Depth-Limited Searching and Alpha-Beta Pruning](https://ksvi.mff.cuni.cz/~dingle/2022-3/prog_2/notes_11.html)
- [cite:4] [Godot Asset Library：Chess v1.0.0](https://godotengine.org/asset-library/asset/5484)
