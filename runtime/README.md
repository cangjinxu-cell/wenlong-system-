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
