# LCHBot - 基于LLOneBot的QQ机器人框架

LCHBot是一个基于[LLOneBot](https://llonebot.com/zh-CN)的QQ机器人框架，支持插件系统，使用YAML配置文件。

## 项目结构

```
LCHBot/
├── config/                 # 配置文件目录
│   └── config.yml          # 主配置文件
├── logs/                   # 日志目录
├── src/                    # 源码目录
│   ├── plugins/            # 插件目录
│   │   ├── __init__.py
│   │   ├── echo.py         # Echo插件
│   │   ├── help.py         # 帮助插件
│   │   ├── info.py         # 信息插件
│   │   ├── complex_msg.py  # 复杂消息插件
│   │   ├── debug.py        # 调试插件
│   │   ├── onebot_demo.py  # OneBot API示例插件
│   │   └── activity_tracker.py # 群活跃度分析插件
│   ├── plugin_system.py    # 插件系统核心
│   └── main.py             # 主程序
├── start.bat               # Windows启动脚本
├── start_go_cqhttp.bat     # go-cqhttp启动脚本
├── requirements.txt        # Python依赖
└── README.md               # 项目说明文档
```

## 安装和配置

### 依赖项

1. Python 3.7+
2. 依赖包：
   - aiohttp
   - pyyaml
   - psutil (用于系统监控)
   - qrcode

### 安装步骤

1. 克隆或下载本项目
2. 安装依赖：
   ```
   pip install -r requirements.txt
   ```
3. 配置 `config/config.yml` 文件，设置LLOneBot连接参数和机器人信息

### 配置说明

编辑 `config/config.yml` 文件：

```yaml
# LCHBot 配置文件

# 机器人基本设置
bot:
  name: "LCHBot"
  log_level: "INFO"  # 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
  command_prefix: "/"
  superusers: ["12345678"]  # 管理员QQ号列表，请替换为实际QQ号

# HTTP事件服务器设置（接收LLOneBot推送的事件）
http_server:
  host: "127.0.0.1"
  port: 1100

# LLOneBot连接设置
llonebot:
  http_api:
    base_url: "http://127.0.0.1:3000"  # LLOneBot服务地址
    token: "your_token_here"  # 访问令牌，如果有

# 插件设置
plugins:
  enabled:  # 启用的插件列表
    - "echo"
    - "help"
    - "info"
    - "complex_msg"
    - "debug"
    - "onebot_demo"
    - "activity_tracker"
  disabled: []  # 禁用的插件列表
```

## 重要权限说明

### 机器人需要的群权限

为了正常使用所有功能，机器人需要在群内具有**管理员权限**。以下功能特别依赖于管理员权限：

1. **禁言功能** - 需要管理员权限才能禁言成员

2.**其他插件由于涉及其他信息已被删除，包含进群插件，相关插件** - 需要管理员权限才能禁言成员
如果机器人没有管理员权限：
- 进群验证和可疑邀请者检测仍会记录数据，但无法执行踢出操作
- 一些依赖管理员权限的命令（如禁言）将无法使用
- 机器人会在日志中记录权限不足的警告

### 插件权限级别

插件功能按照所需权限级别分类：

**普通成员权限**：
- 聊天、签到、查询等基本功能
- 游戏和娱乐功能
- 信息查询功能

**管理员权限**：
- 配置修改（如更改验证时间）
- 上下文管理（清除聊天记录）
- 人格切换

**群主/超级管理员权限**：
- 全局配置修改
- 群组授权管理
- 机器人敏感设置调整

在实际部署时，请确保为机器人分配足够的权限，以便所有功能正常运行。未授予足够权限可能导致部分功能不可用，但机器人核心功能仍将正常运行。

## 使用方法

### 启动机器人

Windows系统：双击 `start.bat` 文件

或者手动启动：

```bash
python src/main.py
```

### 基本命令

#### 系统命令
- `@机器人 /system` - 显示系统状态信息
- `@机器人 /plugins` - 显示所有已加载的插件
- `@机器人 /activity [天数]` - 显示群组活跃度统计

#### 插件命令
- `/help` - 显示所有可用的插件和命令
- `/echo <内容>` - 让机器人回复你发送的内容
- `/info` - 显示系统和机器人信息
- `/debug` - 显示消息的详细信息
- `/image <URL>` - 发送图片
- `/mixed <文本>` - 发送图文混合消息

#### 群组活跃度分析命令
- `/activity.report` - 生成详细活跃度报告
- `/activity.user <用户ID>` - 查看指定用户的活跃度
- `/activity.trend` - 查看群组活跃度趋势

## 开发插件

### 插件结构

每个插件应该是一个继承自 `Plugin` 基类的Python类，保存在 `src/plugins` 目录下。
插件类导出时需要在模块底部定义 `plugin_class` 变量，指向插件类。

基本插件模板：

```python
# 如果在插件目录中创建插件，使用绝对导入
from src.plugin_system import Plugin

class MyPlugin(Plugin):
    """
    插件描述和帮助信息
    命令格式: /命令 参数
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        # 初始化代码
        
    async def handle_message(self, event):
        """处理消息事件"""
        # 处理逻辑
        return False  # 如果已处理返回True，否则返回False
        
    async def handle_notice(self, event):
        """处理通知事件"""
        return False
        
    async def handle_request(self, event):
        """处理请求事件"""
        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = MyPlugin
```

### 插件系统特性

每个插件都有以下特性：
- 唯一ID：通过 `plugin.id` 访问
- 状态：active、disabled 或 error，通过 `plugin.status` 访问
- 错误信息：如果插件出错，通过 `plugin.error_message` 访问错误信息

插件管理器提供了以下方法：
- `register_plugin(plugin)` - 注册一个插件
- `unregister_plugin(plugin_id)` - 注销一个插件
- `get_plugin_by_id(plugin_id)` - 根据ID获取插件
- `get_plugin_by_name(name)` - 根据名称获取插件
- `get_active_plugins()` - 获取所有活跃的插件
- `get_all_plugins()` - 获取所有插件

### 发送消息

可以使用机器人对象的 `send_msg` 方法发送消息：

```python
await self.bot.send_msg(
    message_type='private',  # 'private' 或 'group'
    user_id=123456,  # 用户QQ号
    group_id=None,  # 群号（如果是群消息）
    message='Hello, world!'  # 消息内容
)
```

### 启用插件

1. 将插件文件放入 `src/plugins` 目录
2. 确保插件模块末尾有 `plugin_class = YourPluginClass` 声明
3. 在 `config/config.yml` 的 `plugins.enabled` 列表中添加插件名（不带.py后缀）

## 群组活跃度统计

LCHBot内置了群组活跃度统计功能，包括：

- 跟踪群组成员发言情况
- 统计每日活跃用户数
- 统计消息类型分布
- 分析活跃时段
- 生成活跃度趋势报告

可以通过以下命令查看群组活跃度：
- `@机器人 /activity [天数]` - 显示基本群组活跃度统计
- `/activity.report` - 生成详细活跃度报告
- `/activity.user <用户ID>` - 查看指定用户的活跃度
- `/activity.trend` - 查看群组活跃度趋势

## 关于 LLOneBot

[LLOneBot](https://llonebot.com/zh-CN) 是一个遵循 [OneBot](https://onebot.dev/) 标准的QQ机器人实现，提供了与QQ进行交互的接口。

在使用本框架前，您需要：

1. 安装和配置LLOneBot
2. 确保LLOneBot已成功连接到QQ
3. 获取LLOneBot的API访问地址和token（如果有）

## 许可证

本项目采用 [MIT 许可证](LICENSE) 开源。 
