# Godot 4 机器学习插件实战：把训练好的神经网络装进游戏做实时推理

> 日期：2026-11-26
> 系列：Godot AI 编程 · 每日一篇
> 关键词：机器学习插件、神经网络推理、ONNX Runtime、ncnn、GDScript MLP、前向传播、模型部署

## 来源链接

- Godot Asset Library：*Godot AI Kit*（纯 GDScript 的 MLP / DQN / CNN 算法库）
  <https://godotengine.org/asset-library/asset/1477>
- Godot Asset Library：*MLGodotKit*（C++ GDExtension，提供 `LRNode` / `DTreeNode` / `NNNode`）
  <https://godotassetlibrary.com/asset/UTAhQ8/mlgodotkit>
- Godot Asset Library：*Godot Native Reinforcement Learning*（用 ncnn 原生推理部署训练好的策略）
  <https://godotengine.org/asset-library/asset/5358>
- minigraphx：*ncnn vs ONNX Runtime — a deployment decision guide*（三种原生推理路线对比）
  <https://github.com/minigraphx/godot-native-rl/blob/main/docs/ncnn_vs_onnx.md>
- joemarshall：*godot_onnx_extension*（原生 C++ ONNX Runtime GDExtension，无需 .NET）
  <https://github.com/joemarshall/godot_onnx_extension>

---

## 一、训练是炼丹，上线是搬砖

过去几天的文章里，我们已经用 Q-Learning 从零训练过会追人的敌人（[2026-11-18](../articles/2026-11-18-godot-q-learning-reinforcement.md)），也用过遗传算法进化行为参数。但真正做游戏时，你会遇到一个更日常、也更工程化的问题：

> **模型已经在 Python 里训练好了，怎么把它塞进 Godot，让几百个敌人每帧都能实时决策？**

这属于「推理（inference）」问题，而不是「训练（training）」问题。两者目标完全不同：

| | 训练（training） | 推理（inference） |
|---|---|---|
| 在哪跑 | 训练框架（PyTorch / Stable-Baselines3 / 自己的脚本） | 游戏运行时（Godot 进程内） |
| 需要什么 | 反向传播、梯度下降、大量样本、GPU | 只做前向计算：输入 → 输出 |
| 关注点 | 收敛、奖励设计、泛化 | 帧预算、内存、跨平台导出、模型体积 |
| 常见载体 | `.pt` / `.pth` / `.onnx` | `.onnx` / `.ncnn` / 导出成 JSON 的权重 |

游戏里绝不该带着训练框架跑。我们要的只是几层矩阵乘加。理解这一点，就能明白为什么 Godot 生态里会出现一批「机器学习插件」：它们做的不是训练，而是**让游戏进程以极低的成本执行一个小型神经网络**。

本文分两层展开：先手写一个无任何依赖、可直接运行的 GDScript 推理内核，把「前向传播」这件事彻底讲透；再看现成插件和原生方案各自适合什么场景。

---

## 二、核心概念：一次前向传播到底发生了什么

### 2.1 多层感知机（MLP）就是几个矩阵乘加

一个三层感知机：

```
输入 x（3 维） → 隐藏层 h（5 维，ReLU） → 输出 y（3 维，Softmax）
```

计算只有两步，对每一层重复：

```
z = W · x + b
h = activation(z)
```

其中 `W` 是「输出神经元数 × 输入神经元数」的权重矩阵，`b` 是偏置向量。以隐藏层为例，第 `i` 个神经元的输出是：

```
h[i] = relu( b[i] + Σ_j W[i][j] * x[j] )
```

没有任何魔法。所谓「模型」，本质就是一堆 `float` 和它们之间的乘加顺序。只要知道权重怎么存，你完全可以在 GDScript 里手写推理，不需要任何插件。

### 2.2 激活函数决定了「能表达什么」

- **ReLU**：`max(0, z)`。计算最便宜，是隐藏层默认选择。
- **Sigmoid**：把值压到 `(0, 1)`，适合二分类/门控。
- **Softmax**：把一组分数变成概率分布，适合「在若干行为里选一个」。

Softmax 要做数值稳定处理——先减去最大值再取指数：

```
softmax(z)[i] = exp(z[i] - max(z)) / Σ_k exp(z[k] - max(z))
```

否则分数一大就溢出成 `inf`。这个细节手写推理时最容易踩。

### 2.3 输入特征工程：游戏 AI 的胜负手

神经网络只认数字，且对量纲敏感。把「玩家距离 = 347 像素」直接喂进去，和训练时用的分布一旦不一致，推理结果就会崩。所以观测（observation）必须**归一化**，并且**与训练时完全一致**（业界叫 obs parity）。

本文示例用三个传感器输入：

| 输入 | 含义 | 归一化 |
|---|---|---|
| `d` | 到玩家的距离 | `clamp(dist / 400, 0, 1)` |
| `f` | 是否面朝玩家 | `forward · dir`，天然落在 `[-1, 1]` |
| `hp` | 剩余血量 | `clamp(hp, 0, 1)` |

三个输出对应三种行为：`chase`（追击）、`flee`（逃跑）、`strafe`（绕行）。取概率最大的那个即可（`argmax`）。

---

## 三、把模型装进 Godot 的三条路线

根据 *ncnn vs ONNX Runtime* 部署指南的整理，目前「不带 Python 服务器、在游戏内原生推理」主要有三条路：

| 路线 | 运行时 | 需要 .NET | 载入格式 | 适合场景 |
|---|---|---|---|---|
| 官方 `godot_rl_agents` ONNX 路径 | ONNX Runtime（经 Mono/.NET） | 是 | `.onnx` 直接载入 | 桌面端、快速迭代、已在用 .NET |
| 原生 ORT GDExtension（`godot_onnx_extension`） | ONNX Runtime，C++ 原生 | 否 | `.onnx` 直接载入 | 桌面 / Android，需要完整算子集与 ORT 加速 |
| ncnn GDExtension（`godot-native-rl`） | ncnn，静态链接 C++ | 否 | `.ncnn`（需从 ONNX 转换） | Web/WASM、主机、移动端，追求小体积与 INT8 |

几条关键事实（据各项目文档）：

- 官方 `.NET` ONNX 路径**无法导出到 Web**（Godot 的 C# Web 导出能力受限），所以要做 HTML5 版本就得考虑 ncnn 或纯 GDScript。
- 原生 ORT 扩展能直接吃 `.onnx`、无需转换，但该项目定位是概念验证，最后一次提交较早，用于 Godot 4.5+ 可能需要自行适配。
- ncnn 方案多了一步「ONNX → ncnn（经 pnnx）」转换，换来的是静态链接、约 3.4 MB 的轻量体积、Web/WASM 与 INT8 量化能力。
- 纯 GDScript 或纯 GDScript 插件（如 Godot AI Kit）零依赖、可直接跑，但只适合**很小的网络**；规模上来后应换成原生扩展。

如果只是教学、原型或几层的小 MLP，最省事的其实是**自己写推理**。下面就把这条路走通。

---

## 四、可运行实战：纯 GDScript 的极小推理引擎

目标：不安装任何插件，复制两个脚本就能让一个敌人根据「距离 / 朝向 / 血量」在追击、逃跑、绕行之间切换。

### 4.1 权重文件格式

我们把模型存成 JSON。`layers` 是有序的层数组，每层包含：

- `weights`：二维数组，`weights[i][j]` 表示第 `i` 个输出神经元对第 `j` 个输入的权重；
- `biases`：一维数组，长度等于该层输出神经元数；
- `activation`：`"relu"` / `"sigmoid"` / `"softmax"` / `"linear"`。

把下面内容保存为 `res://models/enemy_policy.json`（没有该文件时脚本会自动使用内置演示权重）：

```json
{
  "layers": [
    {
      "activation": "relu",
      "weights": [
        [-3.0, 0.0, 0.0],
        [3.0, 0.0, 0.0],
        [0.0, 0.0, 3.0],
        [0.0, 0.0, -3.0],
        [0.0, 2.0, 0.0]
      ],
      "biases": [0.9, -1.2, -1.2, 1.2, 0.5]
    },
    {
      "activation": "softmax",
      "weights": [
        [3.0, 0.0, 2.0, -5.0, 1.0],
        [0.0, -0.5, -1.0, 3.0, 0.0],
        [0.0, 1.0, 0.2, 0.0, 0.5]
      ],
      "biases": [0.0, 0.0, 0.0]
    }
  ]
}
```

这份权重是手工构造的「可解释策略」：隐藏层 5 个神经元分别近似「离得近」「离得远」「血多」「血少」「面朝玩家」，输出层据此给三种行为打分。真实项目里，这些数字来自离线训练后的导出。

### 4.2 `mlp_inference.gd`：推理内核

新建脚本 `mlp_inference.gd`，它就是一个纯粹的数学工具，不依赖任何节点：

```gdscript
class_name MLPInference
extends RefCounted

## 一个最小可用的多层感知机推理器。
## 只做前向传播，不含训练逻辑，可在任意 Node 中 new() 后复用。

var _layers: Array = []


## 从字典加载模型（通常来自 JSON.parse_string 的结果）。
## 返回 true 表示加载成功。
func load_from_dict(data: Dictionary) -> bool:
	_layers.clear()
	var raw_layers: Array = data.get("layers", [])
	for layer in raw_layers:
		var w: Array = layer.get("weights", [])
		var b: Array = layer.get("biases", [])
		if w.is_empty() or b.is_empty() or w.size() != b.size():
			push_error("MLPInference: 层结构非法（weights/biases 为空或维度不一致）")
			return false
		_layers.append({
			"weights": w,
			"biases": b,
			"activation": str(layer.get("activation", "linear")),
		})
	if _layers.is_empty():
		push_error("MLPInference: 模型没有任何层")
		return false
	return true


## 从文件加载模型，路径支持 res:// 与 user://。
func load_from_file(path: String) -> bool:
	if not FileAccess.file_exists(path):
		return false
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("MLPInference: 无法打开模型文件 %s" % path)
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("MLPInference: 模型 JSON 解析失败")
		return false
	return load_from_dict(parsed)


## 前向传播：输入一维数组，输出一维数组。
func forward(inputs: Array) -> Array:
	var x: Array = inputs.duplicate()
	for layer in _layers:
		var weights: Array = layer["weights"]
		var biases: Array = layer["biases"]
		var out: Array = []
		for i in range(biases.size()):
			var row: Array = weights[i]
			if row.size() != x.size():
				push_error("MLPInference: 维度不匹配，期望 %d 个输入，实际 %d" % [x.size(), row.size()])
				return []
			var acc: float = float(biases[i])
			for j in range(row.size()):
				acc += float(row[j]) * float(x[j])
			out.append(acc)
		x = _apply_activation(out, layer["activation"])
	return x


func _apply_activation(values: Array, activation: String) -> Array:
	match activation:
		"relu":
			for i in range(values.size()):
				values[i] = maxf(0.0, float(values[i]))
		"sigmoid":
			for i in range(values.size()):
				values[i] = 1.0 / (1.0 + exp(-float(values[i])))
		"softmax":
			var max_value: float = -1e20
			for v in values:
				max_value = maxf(max_value, float(v))
			var total: float = 0.0
			for i in range(values.size()):
				values[i] = exp(float(values[i]) - max_value)
				total += float(values[i])
			if total > 0.0:
				for i in range(values.size()):
					values[i] = float(values[i]) / total
		_:
			pass  # linear：保持原样
	return values
```

### 4.3 `enemy_brain.gd`：把推理接到游戏循环

新建 `CharacterBody2D` 节点的脚本 `enemy_brain.gd`：

```gdscript
extends CharacterBody2D

const MODEL_PATH := "res://models/enemy_policy.json"
const ACTION_NAMES := ["chase", "flee", "strafe"]
const MAX_SENSE_DISTANCE := 400.0

@export var player: Node2D
@export var move_speed: float = 120.0
@export var health: float = 1.0

var _brain := MLPInference.new()
var _last_action := ""


func _ready() -> void:
	if not _brain.load_from_file(MODEL_PATH):
		print("[brain] 未找到 %s，使用内置演示权重" % MODEL_PATH)
		_brain.load_from_dict(_demo_weights())


func _physics_process(_delta: float) -> void:
	if player == null:
		return
	var probs: Array = _brain.forward(_observe())
	if probs.is_empty():
		return
	var action_index := _argmax(probs)
	var action: String = ACTION_NAMES[action_index]
	if action != _last_action:
		print("[brain] 行为切换 -> %s（概率 %.2f）" % [action, float(probs[action_index])])
		_last_action = action
	_apply_action(action_index)


## 三个归一化后的观测输入，必须与训练时保持一致。
func _observe() -> Array:
	var to_player := player.global_position - global_position
	var distance := to_player.length()
	var facing := 1.0
	if distance > 0.001:
		var forward := Vector2.RIGHT.rotated(rotation)
		facing = forward.dot(to_player / distance)
	return [
		clampf(distance / MAX_SENSE_DISTANCE, 0.0, 1.0),
		clampf(facing, -1.0, 1.0),
		clampf(health, 0.0, 1.0),
	]


func _apply_action(action_index: int) -> void:
	var to_player := (player.global_position - global_position).normalized()
	var move_dir := Vector2.ZERO
	match action_index:
		0:  # chase
			move_dir = to_player
		1:  # flee
			move_dir = -to_player
		2:  # strafe
			move_dir = to_player.orthogonal()
	velocity = move_dir * move_speed
	move_and_slide()


func _argmax(values: Array) -> int:
	var best := 0
	for i in range(1, values.size()):
		if float(values[i]) > float(values[best]):
			best = i
	return best


## 演示用权重：3 输入 → 5 隐藏（ReLU）→ 3 输出（Softmax）。
func _demo_weights() -> Dictionary:
	return {
		"layers": [
			{
				"activation": "relu",
				"weights": [
					[-3.0, 0.0, 0.0],   # h0: 距离近时激活
					[3.0, 0.0, 0.0],    # h1: 距离远时激活
					[0.0, 0.0, 3.0],    # h2: 血量高时激活
					[0.0, 0.0, -3.0],   # h3: 血量低时激活
					[0.0, 2.0, 0.0],    # h4: 面朝玩家时激活
				],
				"biases": [0.9, -1.2, -1.2, 1.2, 0.5],
			},
			{
				"activation": "softmax",
				"weights": [
					[3.0, 0.0, 2.0, -5.0, 1.0],   # chase
					[0.0, -0.5, -1.0, 3.0, 0.0],  # flee
					[0.0, 1.0, 0.2, 0.0, 0.5],    # strafe
				],
				"biases": [0.0, 0.0, 0.0],
			},
		],
	}
```

### 4.4 场景搭建与运行

1. 新建 2D 场景，根节点用 `CharacterBody2D`，挂上 `enemy_brain.gd`；
2. 场景里放一个代表玩家的 `Node2D`（可加个 `ColorRect` 或 `Sprite2D` 方便观察），拖到敌人的 `player` 导出属性上；
3. 给玩家写一个最简单的 WASD 移动脚本；
4. 运行。当玩家靠近且敌人血量健康时，日志会显示 `chase`；靠近但血量低时会切到 `flee`；距离远且血量低时倾向于 `strafe`。

这套代码没有任何外部依赖，`MLPInference` 也可以被其它 AI 复用——它只认权重数组，不认具体游戏规则。

---

## 五、换成现成插件：三种典型写法

自己写推理适合理解和掌控细节；生产中更常见的是直接接入插件。

### 5.1 MLGodotKit：C++ GDExtension 的 `NNNode`

MLGodotKit 通过 C++ 绑定（基于 Eigen）直接暴露节点，自带 `Linear Regression`、`Decision Tree` 和 `Neural Network`。它的 `NNNode` 同时支持训练与推理，接口大致如下：

```gdscript
var nn := NNNode.new()
nn.set_learning_rate(0.1)
nn.add_layer(3, 8, "relu")
nn.add_layer(8, 3, "softmax")

# 推理：输入一帧观测，得到行为概率
var probs: Array = nn.forward([obs])
```

注意它目前标记为 `v1.0.0-exp`，适合原型与小模型；损失函数等仍需自行补齐。

### 5.2 Godot AI Kit：纯 GDScript 算法库

Godot AI Kit（MIT）用纯 GDScript 实现了简单神经网络、带 SGD/ADAM 优化的多层网络、Minimax、Q-Learning/SARSA、DQN 以及用于图像识别的 CNN。它的优势是**零编译、跨平台、可直接读源码**，适合教学与中小规模实验；缺点是纯脚本在大批量智能体上会有明显的 CPU 开销。

### 5.3 ncnn / ONNX：把训练好的策略原样部署

如果你的模型来自 `godot_rl_agents`（Python + Stable-Baselines3 训练），标准流水线是：

1. 在 Python 中用 PPO/SAC 等算法训练策略；
2. 导出 `.onnx`；
3. 若走 ncnn，用 `pnnx` 把 ONNX 转成 ncnn 模型；
4. 在 Godot 中挂载对应的 Runner 节点，把观测数组喂进去，拿到动作。

`godot-native-rl` 把这条链路封装成了一个 GDExtension，并提供 `NcnnRunner` 节点、传感器库（射线、相对位置、像素、网格、导航网格等）与奖励构建工具。据其文档，它支持 Web/WASM、INT8 量化、批量推理和 LSTM 状态携带，适合需要「一套策略跑多端」的项目。

而 `godot_onnx_extension` 则省掉转换步骤，直接加载 `.onnx`，代价是需要自行编译、且目前主要覆盖 Windows/Android。

---

## 六、实践要点

1. **先对齐观测，再谈模型。** 90% 的「模型在 Python 里好好的，进游戏就变傻」都是归一化或特征顺序不一致。把观测定义写成一份共享规范，训练和推理都引用它。
2. **输入/输出顺序是契约。** `ACTION_NAMES` 的顺序必须与训练时的动作索引完全一致，改顺序等于换了一个模型。
3. **Softmax 一定做数值稳定。** 先减最大值再 `exp`，否则大 logits 会溢出。
4. **控制推理频率。** 小 MLP 每帧算一次没问题；上百个智能体时，可以按 `Engine.get_physics_frames() % N` 错峰推理，或降低决策频率（例如 10 Hz），移动仍保持每帧插值。
5. **避免每帧分配。** 高频路径上尽量复用数组；本文为了可读性用了 `duplicate()`，规模化时可改为预分配缓冲区。
6. **模型要版本化。** 在 JSON 里加 `"model_version"` 字段并在加载时校验，避免旧存档配新模型导致行为错乱。
7. **按发布平台选运行时。** 只发桌面且已在用 .NET，可走官方 ONNX 路径；要发 Web/主机/移动，优先考虑 ncnn；只在原型阶段，纯 GDScript 最省事。
8. **模型文件随包走。** 用 `res://models/...` 打包进导出模板；需要热更新时再考虑 `user://` 或远程下载。

---

## 七、延伸阅读

- Godot AI Kit（纯 GDScript 神经网络 / DQN / CNN）：<https://godotengine.org/asset-library/asset/1477>
- MLGodotKit（C++ GDExtension，`LRNode` / `DTreeNode` / `NNNode`）：<https://godotassetlibrary.com/asset/UTAhQ8/mlgodotkit>
- Godot Native Reinforcement Learning（ncnn 原生推理 + `NcnnRunner`）：<https://godotengine.org/asset-library/asset/5358>
- ncnn vs ONNX Runtime 部署决策指南：<https://github.com/minigraphx/godot-native-rl/blob/main/docs/ncnn_vs_onnx.md>
- godot_onnx_extension（原生 ONNX Runtime GDExtension）：<https://github.com/joemarshall/godot_onnx_extension>
- 本系列前作：用 Q-Learning 从零训练会追人的敌人（训练侧）：[2026-11-18](../articles/2026-11-18-godot-q-learning-reinforcement.md)
