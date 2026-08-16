# 文龙运行时 V0.1

运行时负责加载正式宪制、组织上下文、调用可替换模型能力，并可靠保存会话与追踪元数据。它不是文龙身份本身。

## 配置

通过环境变量设置兼容中转站的模型调用配置：

```text
WENLONG_API_KEY=...
WENLONG_BASE_URL=https://你的中转站地址
WENLONG_MODEL=中转站提供的模型名
```

三项配置均为必填。密钥只从环境变量读取，不会写入会话或追踪文件；运行时不会要求任何官方服务地址，也不限制模型名。

## 启动

```bash
python -m wenlong new
python -m wenlong resume <session_id>
python -m wenlong sessions
```

`new` 创建并显示会话标识后进入交互；`resume` 恢复指定会话；`sessions` 列出会话标识、创建时间和更新时间。

默认运行数据位于 `~/.wenlong/`：会话在 `sessions/`，追踪元数据在 `traces/`。可通过 `WENLONG_HOME` 覆盖运行目录，真实会话不会写入 Git 仓库。

会话以 JSON 保存，更新采用临时文件写入后原子替换。每次成功轮次同时保存主公输入与文龙回答；模型失败不会写入半截轮次。会话历史只用于运行连续性，不等于正式长期记忆。

每次启动都会从正式文件加载 Kernel 与 Memory Constitution，并记录各自 SHA-256。`wenlong/persona.md` 当前为 Draft，不会加载。

## 测试

```bash
python -m unittest discover -s tests
```

## WorkBuddy 接入

启动本机 Bridge：

```bash
python -m wenlong serve
python -m wenlong serve --port 8766
```

默认地址为 `http://127.0.0.1:8765/v1`，只监听本机，不会开放到局域网或公网。启动前除上游运行配置外，还必须设置 `WENLONG_BRIDGE_API_KEY`。

WorkBuddy Custom Model 使用以下设置：

```text
URL: http://127.0.0.1:8765/v1
API Key: WENLONG_BRIDGE_API_KEY 的值
Model: wenlong
```

WorkBuddy 是交互前台，不是文龙身份来源；实际底层模型仍完全由 Wenlong Runtime 的上游配置决定。WorkBuddy 当前任务历史由 WorkBuddy 管理，Bridge 不会将其复制进文龙 CLI 会话，也不会自动写入正式长期记忆。

Bridge 提供 `/health`、`/v1/models` 与 `/v1/chat/completions`。外部 system 与 developer 消息不会获得 Kernel 或 Memory Constitution 的权威；Skills、MCP 与 tool calling 尚未接入。

客户端请求 `stream=true` 时，Bridge 会在获得完整上游结果后按 SSE 协议发送一个内容块和 `[DONE]`。这是协议兼容，不是真正的上游逐 token 流式传输。

## 原生页面

运行 `python -m wenlong serve` 后，访问 `http://127.0.0.1:8765/` 即可使用本机页面。页面只使用离线 HTML、CSS 和原生 JavaScript；Bridge API Key 仅保存在当前页面内存，刷新页面即丢失。

页面维护的前台 history 不等于 Wenlong CLI Session，也不等于正式长期记忆。每次发送固定使用 `stream: false`，且页面同一时刻只允许一个请求，避免重复并发调用。页面不会发送 system、developer 或任何工具调用字段。
