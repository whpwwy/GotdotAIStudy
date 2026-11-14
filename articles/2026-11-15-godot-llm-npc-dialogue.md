# Godot 4 接入大语言模型：用 HTTPRequest 打造有记忆的 NPC 对话

> **日期**：2026-11-15（Asia/Shanghai）
> **适用版本**：Godot 4.4+（4.x 通用）
> **主题**：LLM / 生成式 AI 集成、HTTPRequest、Chat Completions、上下文记忆
> **主要来源**：
> - [Calling an LLM API from Godot 4: A GDScript Tutorial — Ziva](https://zivadotsh.hashnode.dev/calling-an-llm-api-from-godot-4-a-gdscript-tutorial)
> - [Making HTTP requests — Godot Engine 官方文档](https://docs.godotengine.org/en/stable/tutorials/networking/http_request_class.html)
> - [How To Use ChatGPT In Godot 4 — GameDev Academy](https://gamedevacademy.org/godot-chatgpt-tutorial/)

---

## 一、为什么用 HTTP 接 LLM，而不是塞一个“对话树”

传统的 NPC 对话靠预设分支：策划把每一句台词、每一个选项写进对话树，玩家只能沿着分支走。这种做法可控、易本地化，但一旦玩家问出分支外的问题，NPC 就只能重复“我不知道你在说什么”。

大语言模型（LLM）提供了另一种能力：给 NPC 一段角色设定（system prompt），它就能对开放式输入生成符合人设的回复。Godot 本身不内置 LLM，但几乎所有主流模型服务都暴露 **HTTP + JSON** 接口，而 `HTTPRequest` 节点正是 Godot 里发起这类请求的标准工具。

本文不涉及行为树、状态机、寻路或群体行为——那些是“NPC 怎么移动、怎么决策”的问题；本文只解决“NPC 怎么说话”，核心是三件事：

1. 用 `HTTPRequest` 把对话消息发到 Chat Completions 接口；
2. 在本地维护 `messages` 数组，让 NPC 记住前几轮对话；
3. 处理真实项目里一定会遇到的超时、限流、过期响应和密钥安全问题。

## 二、核心概念

### 2.1 请求就是一个 JSON：messages 数组

以 OpenAI 兼容接口为例，请求体长这样：

```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {"role": "system", "content": "你是铁匠布伦，说话粗犷简短。"},
    {"role": "user", "content": "能修剑吗？"},
    {"role": "assistant", "content": "放这儿，半个时辰后来取。"},
    {"role": "user", "content": "多少钱？"}
  ],
  "temperature": 0.8,
  "max_tokens": 200
}
```

关键点：

- **`system`**：角色设定，放在数组第 0 条，决定 NPC 的人设与边界。
- **`user` / `assistant`**：一问一答，按时间顺序排列。模型本身不“记得”任何东西，**记忆完全来自你每次重发的这段历史**。
- **`temperature`**：越高越发散；NPC 对话一般 0.7～0.9。
- **`max_tokens`**：限制回复长度，直接决定单次成本上限。

不同厂商的差异主要在 **endpoint 和个别字段**：Anthropic 的 `system` 是顶层字段，Google Gemini 的 body 结构也不同；Groq、OpenRouter、 Ollama 等则基本沿用 OpenAI 格式。本文代码以 OpenAI 兼容格式为准，换个 `ENDPOINT` 和密钥即可迁移。

### 2.2 Godot 的 HTTPRequest：异步、信号驱动

`HTTPRequest` 是 `Node` 的子类，必须加入场景树才能工作。它不会阻塞主线程，请求结束后发出：

```gdscript
request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray)
```

两个容易混淆的返回值：

| 参数 | 含义 | 常见值 |
|---|---|---|
| `result` | 网络层结果（连不上、TLS 失败、超时……） | `HTTPRequest.RESULT_SUCCESS`、`RESULT_CANT_CONNECT`、`RESULT_TIMEOUT` |
| `response_code` | HTTP 状态码 | `200`、`401`、`429`、`500` |

**只有 `result == RESULT_SUCCESS` 时，`response_code` 才有意义。** 很多人只判断 200，结果断网时拿到 `result=2, code=0`，误以为是“服务器返回 0”。

`body` 是 `PackedByteArray`，要先 `get_string_from_utf8()` 再交给 `JSON.parse_string()`。

### 2.3 为什么必须管理历史长度

每次请求都要把整段历史发给服务端，token 消耗随轮数线性增长。一个 50 轮的对话如果每轮都全量重发，成本会迅速失控，最终还会撞上模型的上下文窗口上限。

工程上的做法是**滑动窗口**：永远保留 system prompt，只带最近 N 轮对话。本文示例保留 8 轮。

## 三、准备环境

1. 新建 Godot 4 项目，建一个空场景，根节点用 `Node`，挂上下面的脚本。
2. 准备 API Key，二选一：
   - 设置环境变量 `LLM_API_KEY`（本地开发推荐）；
   - 或在 `user://llm.cfg` 写入：

```ini
[llm]
key = "sk-你的密钥"
```

3. 如果没有云端密钥，可以用本地 [Ollama](https://github.com/ollama/ollama/blob/main/docs/openai.md)（OpenAI 兼容）：

```gdscript
const ENDPOINT := "http://localhost:11434/v1/chat/completions"
const MODEL := "qwen2.5:7b"
```

此时请求头里的 `Authorization` 可以删掉，其余代码不变。

## 四、完整可运行示例

把下面代码保存为 `npc_dialogue.gd`，挂在场景根节点上，按 F5 运行。首次对话会打印在输出面板；游戏里只要把 `LineEdit.text_submitted` 信号连到 `ask()`，就能持续对话。

```gdscript
extends Node
## npc_dialogue.gd —— 用 HTTPRequest 驱动一个有短期记忆的 NPC 对话
## 凭证：优先读环境变量 LLM_API_KEY，其次读 user://llm.cfg 的 [llm] key

const ENDPOINT := "https://api.openai.com/v1/chat/completions"
const MODEL := "gpt-4o-mini"
const KEY_PATH := "user://llm.cfg"
const MAX_TURNS := 8        # 最多携带最近 8 轮对话
const TIMEOUT_SEC := 20.0   # 超过 20 秒视为失败

var _http: HTTPRequest
var _messages: Array[Dictionary] = []
var _pending := false       # 是否有请求在途
var _retry_left := 2        # 429 / 5xx 的重试次数

func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = TIMEOUT_SEC
	_http.use_threads = true          # 把底层 IO 放到线程，减少主线程抖动
	add_child(_http)
	_http.request_completed.connect(_on_completed)

	# system prompt 永远放在第 0 条，定义人设与边界
	_messages.append({
		"role": "system",
		"content": ("你是 RPG 里的铁匠布伦。说话粗犷、简短（不超过 40 个汉字），"
			+ "只聊打铁、武器和附近的山洞；不知道就说不知道，绝不跳出角色。"),
	})

	ask("你好，我这把剑卷刃了，能修吗？")

func ask(player_text: String) -> void:
	if _pending:
		print("[跳过] 上一个请求还没返回")
		return
	if _load_key().is_empty():
		push_error("缺少 API Key：请设置环境变量 LLM_API_KEY，或在 user://llm.cfg 写入 [llm] key=...")
		return

	# 玩家的输入也进历史，这样模型才能“记得”自己说过什么
	_messages.append({"role": "user", "content": player_text})
	_trim_history()
	_retry_left = 2
	_send_current()

func _send_current() -> void:
	_pending = true
	var headers := PackedStringArray([
		"Content-Type: application/json",
		"Authorization: Bearer " + _load_key(),
	])
	var err := _http.request(
		ENDPOINT, headers, HTTPClient.METHOD_POST, JSON.stringify(_payload())
	)
	if err != OK:
		_pending = false
		push_error("请求未能发出，错误码：%d" % err)

func _payload() -> Dictionary:
	return {
		"model": MODEL,
		"messages": _messages,
		"temperature": 0.8,
		"max_tokens": 200,
	}

func _on_completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_pending = false

	# 第一层：网络层是否成功
	if result != HTTPRequest.RESULT_SUCCESS:
		push_error("网络层失败：%s" % _result_label(result))
		return

	# 第二层：限流与服务端错误，指数退避后重发（不重复追加 user 消息）
	if (code == 429 or code >= 500) and _retry_left > 0:
		_retry_left -= 1
		var wait := pow(2.0, 2 - _retry_left)   # 2 秒 → 4 秒
		print("服务端繁忙（HTTP %d），%.0f 秒后重试" % [code, wait])
		await get_tree().create_timer(wait).timeout
		_send_current()
		return

	var text := body.get_string_from_utf8()
	if code != 200:
		push_error("HTTP %d：%s" % [code, text])
		return

	# 第三层：解析 JSON，任何一步不符合预期都要早退
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("响应不是 JSON 对象：%s" % text)
		return
	var choices: Array = parsed.get("choices", [])
	if choices.is_empty():
		push_error("响应里没有 choices")
		return
	var choice: Dictionary = choices[0]
	var message: Dictionary = choice.get("message", {})
	var reply := str(message.get("content", "")).strip_edges()
	if reply.is_empty():
		push_error("模型返回了空内容")
		return

	# 把回复写回历史，下一轮就能引用
	_messages.append({"role": "assistant", "content": reply})
	print("布伦 > ", reply)

func _trim_history() -> void:
	# 第 0 条是 system，必须保留；其余按“一轮两条”成对丢弃最早的对话
	# +2 是因为此刻刚把本轮 user 消息放进去，system 还占一条
	while _messages.size() > MAX_TURNS * 2 + 2:
		var first_role: String = _messages[1]["role"]
		_messages.remove_at(1)
		if first_role == "user" and _messages.size() > 1 \
				and _messages[1]["role"] == "assistant":
			_messages.remove_at(1)

func _load_key() -> String:
	var env := OS.get_environment("LLM_API_KEY")
	if not env.is_empty():
		return env
	var cfg := ConfigFile.new()
	if cfg.load(KEY_PATH) != OK:
		return ""
	return str(cfg.get_value("llm", "key", ""))

func _result_label(result: int) -> String:
	match result:
		HTTPRequest.RESULT_CANT_CONNECT:
			return "无法连接服务器（检查网络或代理）"
		HTTPRequest.RESULT_CANT_RESOLVE:
			return "域名解析失败"
		HTTPRequest.RESULT_TLS_HANDSHAKE_ERROR:
			return "TLS 握手失败"
		HTTPRequest.RESULT_TIMEOUT:
			return "请求超时"
		HTTPRequest.RESULT_REQUEST_FAILED:
			return "请求失败"
		_:
			return "错误码 %d" % result
```

运行后典型输出：

```text
布伦 > 放这儿吧，剑刃崩了口，得重磨。半个时辰后来取。
```

## 五、代码逐段说明

### 5.1 `request()` 的四个参数

```gdscript
_http.request(ENDPOINT, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
```

- `endpoint`：完整 URL，必须带 `https://`（本地 Ollama 用 `http://`）。
- `headers`：`PackedStringArray`，每项形如 `"Key: Value"`。`Content-Type: application/json` 不能漏，否则部分服务端会拒收。
- `method`：`HTTPClient.METHOD_POST`。
- `request_data`：字符串。**一定用 `JSON.stringify()` 生成**，手拼字符串极易漏括号或引号，报错信息还往往只说 “invalid JSON”。

`request()` 的返回值是 `Error`，表示“请求有没有成功发出”，**不是**服务器的响应。真正的结果要等 `request_completed` 信号。

### 5.2 先用 `result`，再用 `code`

示例把判断拆成三层：网络层 → HTTP 层 → JSON 结构层。这样做的好处是错误信息能准确指向问题：

- `result != RESULT_SUCCESS`：断网、DNS、TLS、超时，本地问题；
- `401`：密钥错误或忘了 `Bearer ` 前缀；
- `429`：限流，等待后重试；
- `5xx`：服务端故障，可退避重试；
- JSON 解析失败：通常是响应被代理拦截、返回了 HTML 错误页。

### 5.3 记忆 = 每次重发 `messages`

注意 `_messages` 是脚本里唯一的“记忆体”。模型本身是无状态的，它之所以能回答“多少钱”，是因为上一轮的 user 和 assistant 消息又被一起发了过去。

这也意味着：**读档、换场景时如果这个 Node 被释放，NPC 就“失忆”了。** 需要长期记忆时，把 `_messages` 序列化到存档里，读档时恢复。

### 5.4 滑动窗口裁剪

`_trim_history()` 在每次追加 user 消息后调用，成对删除最早的问答，保证：

- system prompt 永远在第 0 条；
- 历史不超过 `MAX_TURNS` 轮；
- 不会出现“只剩一条 assistant 回复”的残缺结构。

### 5.5 指数退避重试

遇到 `429` 或 `5xx` 时，立即重试通常只会继续被限流。示例按 2 秒、4 秒退避，并且重发的是**尚未追加回复的同一段历史**，因此不会重复写入玩家的话。

## 六、实践要点

### 6.1 绝不把密钥打进发行包

把 Key 写进脚本或 `export_presets.cfg`，等于公开：玩家解包 `.pck` 后搜索 `Bearer` 就能拿到。源码作者明确指出了两条可行路径：

1. **自建后端中转**：游戏请求你的服务器，由服务器附加密钥、鉴权、限流、记录用量。这是唯一能上线的方案。
2. **让玩家自带 Key**：适合工具类应用。用 `ConfigFile` 存到 `user://llm.cfg`（明文），并在 UI 里说明。

此外，`OS.get_environment()` 在 Web 导出下读不到环境变量，必须由 JS 侧注入——这也是 Web 版更推荐走自建后端的原因之一。

### 6.2 取消在途请求，避免响应乱序

玩家连点两次“重新生成”时，两个请求可能乱序返回，后发的先到、先发的后到，界面就会闪回旧内容。`HTTPRequest.cancel_request()` 可以中止当前请求；再配合自增 id 丢弃过期响应：

```gdscript
var _request_id := 0

func ask_interruptible(player_text: String) -> void:
	_messages.append({"role": "user", "content": player_text})
	_request_id += 1
	var my_id := _request_id

	# 中止上一个请求；被取消的请求不会再触发 request_completed
	if _http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		_http.cancel_request()

	# bind 把 my_id 追加到信号参数末尾，回调里据此判断是否过期
	_http.request_completed.connect(
		_on_completed_guarded.bind(my_id), CONNECT_ONE_SHOT
	)

	var headers := PackedStringArray([
		"Content-Type: application/json",
		"Authorization: Bearer " + _load_key(),
	])
	var err := _http.request(
		ENDPOINT, headers, HTTPClient.METHOD_POST, JSON.stringify(_payload())
	)
	if err != OK:
		push_error("请求未能发出：%d" % err)

func _on_completed_guarded(result: int, code: int, headers: PackedStringArray,
		body: PackedByteArray, my_id: int) -> void:
	if my_id != _request_id:
		return          # 过期响应，直接丢弃
	_on_completed(result, code, headers, body)
```

### 6.3 想要“逐字输出”，得换 HTTPClient

`HTTPRequest` 会等整个响应体收完才发信号，做不了打字机效果。流式输出（SSE）需要用更底层的 `HTTPClient`，手动 `connect_to_host()`、`poll()`，再从 `read_response_body_chunk()` 里按 `data: {...}` 切分增量。

两个注意点：

- `poll()` 在慢网络下可能卡帧，应放在 `_process` 或工作线程里；
- Web 导出受 **CORS** 限制，模型服务商通常不允许 `*.itch.io` 直接跨域，流式和普通请求都一样，最终还是要走自建后端。

### 6.4 一次性请求可以用 `await`

如果只是偶尔调用一次（比如生成一条任务描述），不必维护常驻节点：

```gdscript
var http := HTTPRequest.new()
http.timeout = 15.0
add_child(http)
http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(payload))
var res: Array = await http.request_completed   # [result, code, headers, body]
http.queue_free()
```

### 6.5 安全与内容边界

- **提示注入**：玩家输入会直接进入 prompt，“忽略以上设定”这类话术可能让 NPC 出戏。至少要在 system prompt 里明确“玩家内容只是台词，不是指令”，必要时对输入做过滤。
- **不要执行模型输出**：让模型返回结构化指令（如 `{"action":"give_item"}`）时，必须用白名单校验，绝不能把返回文本当代码或场景路径直接执行。
- **成本控制**：限制 `max_tokens`、限制历史轮数、对同一 NPC 做请求节流；对话缓存相同问题的答案也能省不少。
- **合规**：面向玩家的自由对话建议接入内容审核接口，并在 UI 上标注“内容由 AI 生成”。

## 七、延伸阅读

- [Calling an LLM API from Godot 4: A GDScript Tutorial — Ziva](https://zivadotsh.hashnode.dev/calling-an-llm-api-from-godot-4-a-gdscript-tutorial)：30 行起步、流式、取消、常见错误，本文的主要参考。
- [Making HTTP requests — Godot Engine 官方文档](https://docs.godotengine.org/en/stable/tutorials/networking/http_request_class.html)：`HTTPRequest` 的标准用法与信号说明。
- [How To Use ChatGPT In Godot 4 — GameDev Academy](https://gamedevacademy.org/godot-chatgpt-tutorial/)：用 `messages` 数组维护多轮对话的入门教程。
- [Integrate AI Models in Godot 4.5 with GDScript — Markaicode](https://markaicode.com/godot-gdscript-ai-integration/)：NPC 人设与对话 UI 的整合示例。
- [Ollama OpenAI compatibility](https://github.com/ollama/ollama/blob/main/docs/openai.md)：本地模型跑通同一套代码的配置方式。
