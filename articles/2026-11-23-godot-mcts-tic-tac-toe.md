# Godot 4 蒙特卡洛树搜索实战：用 MCTS 打造会思考的井字棋对手

- **日期**：2026-11-23（Asia/Shanghai）
- **引擎版本**：Godot 4.x（本文以 Godot 4.4.1 验证，GDScript）
- **难度**：进阶（无需插件、训练数据或外部服务）
- **主题关键词**：蒙特卡洛树搜索、Monte Carlo Tree Search、MCTS、UCT、UCB1、随机模拟、选择扩展回传、回合制 AI、井字棋
- **来源链接**：
  - [cite:1] [Bandit based Monte-Carlo planning（UCT 原始论文）](https://link.springer.com/chapter/10.1007/11871842_29)
  - [cite:2] [Monte Carlo Tree Search: A Review of Recent Modifications and Applications](https://arxiv.org/html/2103.04931v3)
  - [cite:3] [Godot Forum：Adapting MCTS algorithm to GDScript](https://forum.godotengine.org/t/adapting-mcts-algorithm-to-gdscript/39800)
  - [cite:4] [Godot MCTS：Godot 4 通用 MCTS 与异步搜索项目](https://gitlab.com/disintegrator/godot_mcts_player)

> 本文与历史文章的边界：此前文章覆盖了行为树、状态机、GOAP、Utility AI、Q-Learning 和遗传算法。本文不编写行为节点、不规划动作前置条件、不计算效用评分，也不更新 Q 表或进化种群；而是在当前棋局上反复执行**选择、扩展、随机模拟、反向传播**，用模拟统计决定下一步。这里的“搜索树”也不是行为树：节点表示游戏状态，边表示一步行动。

---

## 一、为什么用井字棋理解 MCTS

蒙特卡洛树搜索（Monte Carlo Tree Search，MCTS）适合规则可模拟、行动离散的序贯决策问题。它不需要人工给每个棋局写评分公式，而是从候选状态继续模拟到终局，把胜负结果回传到搜索树中。UCT（Upper Confidence Bounds applied for Trees）则把多臂老虎机中的置信上界思想用于树搜索，在“选择当前表现好的行动”和“尝试了解不足的行动”之间取得平衡。[cite:1][cite:2]

井字棋足够小，可以把注意力放在算法本身：

- 状态只是一个长度为 9 的数组；
- 每步的合法行动就是所有空格；
- 终局结果明确：AI 胜、玩家胜或平局；
- 随机模拟不需要场景、物理、动画或网络；
- 同一套框架之后可以替换为黑白棋、四子棋或回合制战棋规则。

MCTS 不是必然最优的保证。有限模拟预算会带来估计误差；随机模拟策略很弱时，统计结果也可能有偏。它的优势是**无需手工评估中间棋局，并能通过增加模拟预算通常获得更好的决策**，而不是用少量计算替代一切游戏 AI。

---

## 二、核心概念：一次迭代经历什么

经典 MCTS 的每次迭代包含四个阶段。[cite:1][cite:2]

| 阶段 | 要解决的问题 | 本文实现 |
|---|---|---|
| 选择 Selection | 沿已有树走向哪个子节点？ | 用 UCT 分数选择子节点，直到遇到可扩展或终局节点 |
| 扩展 Expansion | 哪个尚未尝试的行动值得加入树中？ | 从未尝试行动中随机取一个，生成新棋局节点 |
| 模拟 Simulation / Rollout | 从这个新状态继续走下去结果如何？ | 双方随机落子，直到胜负或平局 |
| 反向传播 Backpropagation | 模拟结果应更新哪些统计？ | 沿父节点回传，递增访问次数并累计 AI 收益 |

### 2.1 节点保存什么

每个节点至少保存：

- `board`：到达该节点后的棋盘；
- `player`：在该节点即将行棋的一方；
- `move`：从父节点走到这里的落子位置；
- `untried_moves`：尚未扩展的合法行动；
- `visits`：该节点被访问的次数；
- `ai_score`：所有经过该节点的模拟收益之和，**始终站在 AI 视角**。

本文约定 AI 胜为 `+1`、玩家胜为 `-1`、平局为 `0`。统一视角可以避免“这一层为 AI 最大化、下一层却忘记切换”的隐蔽错误。

### 2.2 UCT 如何兼顾利用与探索

对子节点 \(i\)，本文使用：

\[
UCT_i = direction \times \frac{ai\_score_i}{visits_i}
+ c\sqrt{\frac{\ln visits_{parent}}{visits_i}}
\]

其中：

- 平均值是**利用项**，表示已有模拟中的表现；
- 根号项是**探索项**，访问越少的子节点奖励越高；
- 本文取 \(c=\sqrt{2}\)，作为常用起点而不是所有游戏的最佳参数；
- 当前节点轮到 AI 时，`direction = +1`，最大化 AI 平均收益；
- 当前节点轮到玩家时，`direction = -1`，相当于寻找让 AI 收益更低的走法。

Godot 论坛中的移植讨论特别提醒：Python 的 `argmax` 不是对最后一个分数调用 `max()`，而是比较所有子节点分数并返回最高分对应的元素。GDScript 可以用一次循环维护 `best_value` 与 `best_child`，不需要额外分配分数数组。[cite:3]

### 2.3 为什么最终按访问次数选步

搜索结束后，本文选择根节点下**访问次数最多**的子节点，即常见的 robust child 策略。搜索过程中，UCT 用平均值和探索项引导访问；经过较多迭代后，有前景的分支通常会被访问更多次。并列时再用 AI 平均收益打破平局。

这不同于直接选当前平均收益最高的节点：一个只被访问一两次、结果偶然很好的分支，平均值可能很高，但统计并不可靠。

---

## 三、单文件可运行示例

### 3.1 运行方法

1. 新建 Godot 4 项目和一个 2D 场景，根节点选择 `Node2D`；
2. 新建 `mcts_tic_tac_toe.gd`，粘贴下面完整代码并挂到根节点；
3. 按 F5 运行。玩家执 X，点击空格落子，AI 随后执 O；
4. 每次 AI 会执行 1500 次迭代，输出所选落点、根节点访问次数与耗时；按 R 重新开始。

示例采用固定随机种子，便于复现。为突出算法，搜索在主线程同步执行；井字棋规模较小，这样足够直观。复杂游戏不要直接照搬同步预算，应改用时间预算和后台搜索。

### 3.2 完整 GDScript

```gdscript
extends Node2D
## Godot 4.x：玩家执 X，MCTS AI 执 O。
## 新建 Node2D 根节点并挂载本脚本，直接运行即可；按 R 重开。

const EMPTY := 0
const HUMAN := 1
const AI := 2
const GRID_SIZE := 3
const CELL_SIZE := 120
const BOARD_PIXELS := GRID_SIZE * CELL_SIZE
const BOARD_ORIGIN := Vector2(80, 100)
const SEARCH_ITERATIONS := 1500
const EXPLORATION := 1.41421356237 # sqrt(2)

const WIN_LINES := [
	[0, 1, 2], [3, 4, 5], [6, 7, 8],
	[0, 3, 6], [1, 4, 7], [2, 5, 8],
	[0, 4, 8], [2, 4, 6],
]

var rng := RandomNumberGenerator.new()
var board: Array[int] = [0, 0, 0, 0, 0, 0, 0, 0, 0]
var status_text := "轮到你（X）：点击一个空格"
var ai_busy := false
var last_search_ms := 0.0


class MCTSNode:
	var board: Array
	var player: int
	var move: int
	var parent: MCTSNode
	var children: Array[MCTSNode] = []
	var untried_moves: Array[int] = []
	var visits := 0
	var ai_score := 0.0 # 始终以 AI 视角累计：胜 +1、负 -1、平 0。

	func _init(
		p_board: Array,
		p_player: int,
		p_move: int = -1,
		p_parent: MCTSNode = null
	):
		board = p_board
		player = p_player
		move = p_move
		parent = p_parent


func _ready() -> void:
	rng.seed = 20261123
	queue_redraw()


# ---------------- 游戏规则 ----------------

func _opponent(player: int) -> int:
	return HUMAN if player == AI else AI


func _legal_moves(state: Array) -> Array[int]:
	var moves: Array[int] = []
	for i in state.size():
		if state[i] == EMPTY:
			moves.append(i)
	return moves


func _winner(state: Array) -> int:
	for line in WIN_LINES:
		var a: int = line[0]
		var b: int = line[1]
		var c: int = line[2]
		if state[a] != EMPTY and state[a] == state[b] and state[a] == state[c]:
			return state[a]
	return EMPTY


func _is_terminal(state: Array) -> bool:
	return _winner(state) != EMPTY or _legal_moves(state).is_empty()


func _new_node(
	state: Array,
	player: int,
	move: int = -1,
	parent: MCTSNode = null
) -> MCTSNode:
	var node := MCTSNode.new(state, player, move, parent)
	node.untried_moves = _legal_moves(state)
	return node


# ---------------- MCTS 四阶段 ----------------

func _find_best_move(state: Array, player: int, iterations: int) -> int:
	var started := Time.get_ticks_usec()
	var root := _new_node(state.duplicate(), player)
	if _is_terminal(root.board):
		return -1

	for i in iterations:
		var node := root

		# 1. 选择：沿已有树向下，直到还有行动未扩展或到达终局。
		while (
			not _is_terminal(node.board)
			and node.untried_moves.is_empty()
			and not node.children.is_empty()
		):
			node = _select_uct_child(node)

		# 2. 扩展：加入一个此前未尝试的合法行动。
		if not _is_terminal(node.board) and not node.untried_moves.is_empty():
			node = _expand(node)

		# 3. 模拟：从该状态随机对弈至终局，结果始终按 AI 视角计分。
		var result := _rollout(node.board, node.player)

		# 4. 回传：更新从该节点到根节点沿线的统计。
		while node != null:
			node.visits += 1
			node.ai_score += result
			node = node.parent

	var best_child: MCTSNode = null
	for child in root.children:
		if best_child == null:
			best_child = child
			continue
		var child_mean := child.ai_score / float(child.visits)
		var best_mean := best_child.ai_score / float(best_child.visits)
		if (
			child.visits > best_child.visits
			or (child.visits == best_child.visits and child_mean > best_mean)
		):
			best_child = child

	last_search_ms = (Time.get_ticks_usec() - started) / 1000.0
	if best_child == null:
		return -1
	print(
		"AI 落点 %d | 根访问 %d | 本步均值 %.3f | 耗时 %.2f ms" % [
			best_child.move,
			root.visits,
			best_child.ai_score / float(best_child.visits),
			last_search_ms,
		]
	)
	return best_child.move


func _select_uct_child(node: MCTSNode) -> MCTSNode:
	var best_child: MCTSNode = null
	var best_value := -INF
	for child in node.children:
		var exploit := child.ai_score / float(child.visits)
		# 对手节点最小化 AI 收益；探索项仍鼓励访问统计不足的分支。
		if node.player == HUMAN:
			exploit = -exploit
		var explore := EXPLORATION * sqrt(
			log(float(node.visits)) / float(child.visits)
		)
		var value := exploit + explore
		if value > best_value:
			best_value = value
			best_child = child
	return best_child


func _expand(node: MCTSNode) -> MCTSNode:
	var index := rng.randi_range(0, node.untried_moves.size() - 1)
	var move: int = node.untried_moves[index]
	node.untried_moves.remove_at(index)

	var next_board: Array = node.board.duplicate()
	next_board[move] = node.player
	var child := _new_node(
		next_board,
		_opponent(node.player),
		move,
		node
	)
	node.children.append(child)
	return child


func _rollout(start_board: Array, start_player: int) -> float:
	var sim_board: Array = start_board.duplicate()
	var player := start_player

	while not _is_terminal(sim_board):
		var moves := _legal_moves(sim_board)
		var move: int = moves[rng.randi_range(0, moves.size() - 1)]
		sim_board[move] = player
		player = _opponent(player)

	var winner := _winner(sim_board)
	if winner == AI:
		return 1.0
	if winner == HUMAN:
		return -1.0
	return 0.0


# ---------------- 对局交互 ----------------

func _unhandled_input(event: InputEvent) -> void:
	if ai_busy:
		return
	if (
		event is InputEventMouseButton
		and event.button_index == MOUSE_BUTTON_LEFT
		and event.pressed
	):
		var local: Vector2 = event.position - BOARD_ORIGIN
		var bounds := Rect2(Vector2.ZERO, Vector2(BOARD_PIXELS, BOARD_PIXELS))
		if not bounds.has_point(local):
			return
		var col := int(local.x / CELL_SIZE)
		var row := int(local.y / CELL_SIZE)
		var index := row * GRID_SIZE + col
		if board[index] != EMPTY or _is_terminal(board):
			return

		board[index] = HUMAN
		if _update_after_move():
			return
		ai_busy = true
		status_text = "AI 思考中：进行 1500 次 MCTS 迭代..."
		queue_redraw()
		# 先让“思考中”状态绘制，再开始本教学示例的同步搜索。
		call_deferred("_run_ai_turn")


func _unhandled_key_input(event: InputEvent) -> void:
	if (
		event is InputEventKey
		and event.pressed
		and not event.echo
		and event.keycode == KEY_R
		and not ai_busy
	):
		board = [0, 0, 0, 0, 0, 0, 0, 0, 0]
		status_text = "轮到你（X）：点击一个空格"
		last_search_ms = 0.0
		queue_redraw()


func _run_ai_turn() -> void:
	var move := _find_best_move(board, AI, SEARCH_ITERATIONS)
	if move >= 0:
		board[move] = AI
	ai_busy = false
	_update_after_move()
	queue_redraw()


func _update_after_move() -> bool:
	var winner := _winner(board)
	if winner == HUMAN:
		status_text = "你获胜！按 R 再来一局"
	elif winner == AI:
		status_text = "AI（O）获胜，按 R 再挑战"
	elif _legal_moves(board).is_empty():
		status_text = "平局，按 R 再来一局"
	else:
		status_text = "轮到你（X）：点击一个空格"
		queue_redraw()
		return false
	queue_redraw()
	return true


# ---------------- 绘制 ----------------

func _draw() -> void:
	var font := ThemeDB.fallback_font
	draw_string(
		font, Vector2(80, 52), "Godot 4 | Monte Carlo Tree Search",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 26, Color(0.92, 0.95, 1.0)
	)
	draw_string(
		font, Vector2(80, 80), "你：X    AI：O    每步 1500 次迭代",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.65, 0.75, 0.88)
	)

	for i in range(1, GRID_SIZE):
		var offset := i * CELL_SIZE
		draw_line(
			BOARD_ORIGIN + Vector2(offset, 0),
			BOARD_ORIGIN + Vector2(offset, BOARD_PIXELS),
			Color(0.42, 0.50, 0.62), 3.0
		)
		draw_line(
			BOARD_ORIGIN + Vector2(0, offset),
			BOARD_ORIGIN + Vector2(BOARD_PIXELS, offset),
			Color(0.42, 0.50, 0.62), 3.0
		)

	for i in board.size():
		var center := BOARD_ORIGIN + Vector2(
			(i % GRID_SIZE) * CELL_SIZE + CELL_SIZE * 0.5,
			(i / GRID_SIZE) * CELL_SIZE + CELL_SIZE * 0.5
		)
		if board[i] == HUMAN:
			var d := 34.0
			draw_line(center - Vector2(d, d), center + Vector2(d, d), Color.SKY_BLUE, 6.0)
			draw_line(
				center + Vector2(-d, d), center + Vector2(d, -d), Color.SKY_BLUE, 6.0
			)
		elif board[i] == AI:
			draw_arc(center, 34.0, 0.0, TAU, 48, Color.ORANGE, 6.0, true)

	draw_string(
		font, Vector2(500, 150), status_text,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color(0.92, 0.95, 1.0)
	)
	draw_string(
		font, Vector2(500, 195), "模拟收益：AI 胜 +1 / 玩家胜 -1 / 平局 0",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(500, 230), "上次搜索耗时：%.2f ms" % last_search_ms,
		HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(500, 285), "点击棋盘落子",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
	draw_string(
		font, Vector2(500, 318), "按 R 重新开始",
		HORIZONTAL_ALIGNMENT_LEFT, -1, 17, Color(0.68, 0.76, 0.86)
	)
```

### 3.3 代码导读

- **树与游戏规则解耦**：`_legal_moves()`、`_winner()` 和 `_is_terminal()` 描述游戏；`_find_best_move()` 只依赖这些规则接口。换游戏时，首先替换状态、合法行动与终局结果。
- **状态必须复制**：扩展和模拟都对数组执行 `duplicate()`，避免一次随机模拟污染真实棋盘，或让兄弟节点共享同一份后续修改。
- **AI 视角始终不变**：`_rollout()` 只返回 AI 的 `+1 / -1 / 0`；`_select_uct_child()` 在玩家行棋节点反转利用项，因此双方形成对抗，而不是一起帮 AI 找高分。
- **每轮只扩展一个节点**：新节点会立即参与一次终局模拟并回传，之后才可能继续向下选择。
- **最终走法与真实棋盘分离**：搜索结束后只返回整数 `move`，由 `_run_ai_turn()` 修改真实棋盘。搜索过程不触碰场景中的按钮、绘制状态或输入状态。

---

## 四、先验证算法，再增加预算

MCTS 的错误常常不是“AI 不够聪明”，而是状态复制、行动生成或收益视角出错。建议先用确定棋局做断言，再观察整局表现。

### 4.1 三个最小测试

可以在 `_ready()` 中临时调用下面的检查；测试完再移除。断言失败时，Godot 会在调试器中停住并指出对应行。

```gdscript
func _run_tests() -> void:
	# AI 在顶行可以直接获胜，应选择 2。
	var win_now: Array = [2, 2, 0, 1, 1, 0, 0, 0, 0]
	assert(_find_best_move(win_now, AI, 1500) == 2)

	# 玩家在顶行下一手将获胜，AI 应先在 2 阻挡。
	var must_block: Array = [1, 1, 0, 0, 2, 0, 0, 0, 0]
	assert(_find_best_move(must_block, AI, 1500) == 2)

	# 棋盘满且没有胜者时，没有合法行动。
	assert(_legal_moves([1, 2, 1, 1, 2, 2, 2, 1, 1]).is_empty())
	print("MCTS 最小测试通过")
```

在 `_ready()` 的 `rng.seed = 20261123` 后加入：

```gdscript
_run_tests()
```

测试使用固定种子便于定位问题，但战术检查不应只依赖一个种子。进一步验证时，可循环更换 `rng.seed`，分别测试必胜、必挡和终局不再落子。

### 4.2 一个常见的视角错误

如果把模拟结果改成“当前行棋方获胜就返回 +1”，却不随层切换解释方式，AI 可能把玩家的胜局也当成好结果积累。统一保存 AI 收益、只在选择阶段根据 `node.player` 反转利用项，能让符号约定更容易检查。

另一个常见问题是只给刚扩展的节点加分，忘记沿 `parent` 一直回传到根。这样根节点访问次数为零，UCT 的对数与后续选择也会失去正确依据。

---

## 五、实践要点与性能边界

### 5.1 用时间预算替代固定迭代数

固定迭代数适合教学与复现实验，不同设备的耗时却不同。真实项目可以记录开始时间，在预算内持续迭代，例如每步 20 ms 或 50 ms。预算耗尽时仍应返回当前已经搜索出的最佳行动，并确保根节点至少完成一次有效扩展。

如果搜索预算过小，根节点甚至可能尚未覆盖所有合法行动。不能直接把“尚未访问”当成“不合法”，也不要在未初始化统计时计算对数或除法。

### 5.2 大搜索放到后台，但不要跨线程碰场景树

本文同步运行是为了让代码集中。Godot 4 的通用 MCTS 项目已经展示了把搜索放入异步后台 worker、减少界面卡顿的工程方式。[cite:4] 实际项目中可使用 `WorkerThreadPool` 或独立 `Thread`，但需要遵守：

- 搜索只处理复制出来的纯数据状态；
- 不在工作线程读写 UI、场景节点或共享棋盘；
- 不在多线程间不加保护地共享同一个 `RandomNumberGenerator`；
- 主线程收到结果后，先确认棋局版本仍匹配，再应用落子。

如果等待期间玩家已经重开或撤销，旧搜索结果应丢弃，而不是落到新棋局上。

### 5.3 随机模拟可以加入轻量规则

纯随机 rollout 简单通用，但可能产生不合常理的长线对局。可以先加入确定性很强的规则，例如“有立即获胜点就直接获胜”“对手下一手必胜时优先阻挡”，其余行动仍随机。这样会改变模拟分布，通常比盲目增加迭代更有效，但也把领域知识引入算法，需要测试是否产生偏差。

### 5.4 哪些游戏不适合直接套用

- **隐藏信息**：玩家手牌不可见时，需要信息集或确定化等额外处理；
- **连续行动**：移动方向与速度是连续值时，需要先离散化或采用连续 MCTS 变体；
- **模拟极昂贵**：每次 rollout 都加载完整场景和物理世界，预算会迅速耗尽；
- **超长回合**：终局太远时，需要深度限制和状态评估，但这也重新引入了评估函数；
- **只需局部反应**：简单追逐或巡逻用状态机、转向行为通常更直接。

MCTS 最适合“规则能快速复制与模拟、当前决策值得花预算”的场景，而不是替代所有敌人行为系统。

---

## 六、把示例迁移到自己的回合制游戏

推荐按以下顺序改造：

1. 定义不可被搜索副作用污染的纯棋局结构；
2. 提供复制状态、枚举合法行动、应用行动、判断终局四个基本能力；
3. 用极小的确定局面检查胜负、行动和回传方向；
4. 先使用纯随机 rollout 跑通，再逐项加入领域启发式；
5. 将固定次数改为时间预算，并把搜索移到后台；
6. 保存每步根节点的子节点访问数、平均收益和耗时，观察参数修改是否真的改善决策。

这样，UI、动画与游戏规则保持独立，MCTS 只是“根据当前状态推荐一个行动”的模块。

---

## 七、延伸阅读

- [cite:1] [Bandit based Monte-Carlo planning](https://link.springer.com/chapter/10.1007/11871842_29)：阅读 UCT 的原始定义、置信上界思想与理论分析。
- [cite:2] [MCTS 近期改进与应用综述](https://arxiv.org/html/2103.04931v3)：继续了解树策略、动作缩减、提前终止、并行化与不同游戏类型中的变体。
- [cite:3] [Godot Forum：MCTS 移植到 GDScript](https://forum.godotengine.org/t/adapting-mcts-algorithm-to-gdscript/39800)：对照 Python `argmax` 与 GDScript 单循环选最大值的写法。
- [cite:4] [Godot MCTS 通用实现与 Reversi 示例](https://gitlab.com/disintegrator/godot_mcts_player)：研究 Callable 规则适配、不可变状态和异步后台搜索的工程结构。

## 来源

- [cite:1] [Kocsis & Szepesvári：Bandit based Monte-Carlo planning](https://link.springer.com/chapter/10.1007/11871842_29)
- [cite:2] [Świechowski 等：Monte Carlo Tree Search: A Review of Recent Modifications and Applications](https://arxiv.org/html/2103.04931v3)
- [cite:3] [Godot Forum：Adapting MCTS algorithm to GDScript](https://forum.godotengine.org/t/adapting-mcts-algorithm-to-gdscript/39800)
- [cite:4] [Disintegrator：Godot MCTS](https://gitlab.com/disintegrator/godot_mcts_player)
