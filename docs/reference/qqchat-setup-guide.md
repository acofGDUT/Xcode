# QQ Chat 配置教程

> 本教程面向 pull 项目后想要使用 QQ Chat 功能的用户。

## 前置条件

- Python >= 3.10
- 已安装 Xcode CLI：`pip install -e .`
- 已安装 WebSocket 依赖：`pip install websocket-client`
- 拥有 QQ 开放平台的机器人账号

## 第一步：申请 QQ 机器人

1. 访问 [QQ 开放平台](https://q.qq.com/) 并登录
2. 创建一个机器人应用
3. 记录机器人的 **AppID** 和 **AppSecret**
4. 在机器人能力中启用：
   - 单聊能力（用于私聊机器人）
   - 群聊@能力（用于在群里 @机器人）
5. 事件接收方式选择 **WebSocket**（推荐，不需要公网 IP）

## 第二步：配置环境变量

### Windows PowerShell

临时设置（当前会话有效）：
```powershell
$env:QQ_BOT_APP_ID = "你的AppID"
$env:QQ_BOT_CLIENT_SECRET = "你的AppSecret"
```

永久设置（需重启终端）：
```powershell
setx QQ_BOT_APP_ID "你的AppID"
setx QQ_BOT_CLIENT_SECRET "你的AppSecret"
```

### Windows CMD

```cmd
set QQ_BOT_APP_ID=你的AppID
set QQ_BOT_CLIENT_SECRET=你的AppSecret
```

### Linux/macOS

```bash
export QQ_BOT_APP_ID="你的AppID"
export QQ_BOT_CLIENT_SECRET="你的AppSecret"
```

如需永久保存，添加到 `~/.bashrc` 或 `~/.zshrc`。

## 第三步：启动 Xcode 并开启 QQ Chat

```bash
# 启动 Xcode
xcode chat

# 在交互界面中启动 QQ Chat
> /QQchat start
```

启动成功后会显示：
```
QQChat service started.
```

## 第四步：验证连接

查看 QQ Chat 状态：
```
> /QQchat status
```

正常状态应显示：
- Service State: running
- Gateway: connected
- Messages Processed: 0（刚启动时）

## 第五步：测试消息收发

1. **单聊测试**：在 QQ 中找到你的机器人，发送一条消息
2. **群聊测试**：在群里 @机器人 并发送消息
3. 观察 Xcode 终端是否收到消息并自动回复

## 常用命令

| 命令 | 说明 |
|------|------|
| `/QQchat start` | 启动 QQ Chat 服务 |
| `/QQchat stop` | 停止 QQ Chat 服务 |
| `/QQchat status` | 查看服务状态和统计信息 |

## 配置文件（可选）

除了环境变量，还可以使用配置文件：

### 用户级配置（推荐存储密钥）

创建 `~/.xcode/qqchat.json`：
```json
{
  "app_id": "你的AppID",
  "client_secret": "你的AppSecret"
}
```

### 项目级配置（不存储密钥）

在项目根目录创建 `.xcode/config.json`：
```json
{
  "qqchat": {
    "enabled": true,
    "enable_c2c": true,
    "enable_group_at": true,
    "group_allowlist": [],
    "owner_openids": [],
    "max_reply_chars": 1800,
    "group_turn_timeout_seconds": 240,
    "c2c_turn_timeout_seconds": 900
  }
}
```

**注意：** 项目级配置中的 `client_secret` 会被忽略，必须通过环境变量或用户级配置提供。

## 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `enabled` | `true` | 是否启用 QQ Chat |
| `enable_c2c` | `true` | 是否允许单聊 |
| `enable_group_at` | `true` | 是否允许群聊@ |
| `group_allowlist` | `[]` | 群白名单（为空则允许所有群） |
| `owner_openids` | `[]` | 用户白名单（为空则允许所有用户） |
| `max_reply_chars` | `1800` | 最大回复字符数 |
| `group_turn_timeout_seconds` | `240` | 群聊消息超时时间（秒） |
| `c2c_turn_timeout_seconds` | `900` | 单聊消息超时时间（秒） |

## 安全机制

QQ Chat 默认采用保守的安全策略：

1. **工具限制**：QQ 用户只能使用只读工具（`read_file`、`grep`、`glob`、`task_list`）
2. **危险操作禁止**：不能执行 `write_file`、`edit_file`、`run_shell` 等操作
3. **会话隔离**：每个 QQ 用户/群有独立的会话，互不干扰
4. **超时控制**：群聊消息 240 秒过期，单聊消息 900 秒过期

## 常见问题

### Q: 提示 "missing app id" 或 "missing client secret"

**原因：** 未配置 AppID 或 AppSecret

**解决：** 
1. 检查环境变量是否设置正确
2. 或检查 `~/.xcode/qqchat.json` 是否存在且内容正确
3. 重启终端后重试

### Q: 提示 "gateway fetch failed"

**原因：** 无法获取 WebSocket 网关地址

**解决：**
1. 检查网络连接
2. 确认 AppID 和 AppSecret 是否正确
3. 确认机器人已在 QQ 开放平台启用

### Q: WebSocket 连接后立即断开

**原因：** 可能是认证失败或网络问题

**解决：**
1. 检查 `/QQchat status` 查看错误信息
2. 尝试 `/QQchat stop` 后重新 `/QQchat start`
3. 检查机器人是否已启用 WebSocket 事件订阅

### Q: QQ 发消息后没有收到回复

**原因：** 可能是权限问题或消息超时

**解决：**
1. 确认机器人已启用单聊/群聊能力
2. 群聊时确认已 @机器人
3. 检查消息是否超过超时时间（群聊 240 秒，单聊 900 秒）
4. 查看 `/QQchat status` 确认消息是否被处理

### Q: 回复内容被截断

**原因：** 回复超过最大字符数限制

**解决：** 在配置中增加 `max_reply_chars`：
```json
{
  "qqchat": {
    "max_reply_chars": 3000
  }
}
```

### Q: 如何限制只允许特定群或用户使用

**解决：** 配置白名单：
```json
{
  "qqchat": {
    "group_allowlist": ["group-openid-1", "group-openid-2"],
    "owner_openids": ["user-openid-1", "user-openid-2"]
  }
}
```

## 获取 OpenID

如果需要配置白名单，需要获取群或用户的 OpenID：

1. 启动 QQ Chat：`/QQchat start`
2. 让目标用户发消息或在目标群发消息
3. 查看 Xcode 日志中的 OpenID 信息
4. 将 OpenID 添加到配置文件

## 限制说明

1. **被动回复窗口**：群聊 5 分钟，单聊 60 分钟
2. **回复次数限制**：每条消息最多回复 5 次
3. **仅支持文本**：不支持图片、文件等富媒体
4. **无主动推送**：只能被动回复，不能主动发送消息

## 相关文档

- [QQ 机器人官方文档](https://bot.q.qq.com/wiki/develop/api/)
- [技术设计文档](./qq-bot-integration-guide.md)
