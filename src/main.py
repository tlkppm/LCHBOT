#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import importlib
import importlib.util
import yaml
import json
import asyncio
import aiohttp
import time
import platform
import psutil
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import List, Dict, Any, Optional, Union, Set

# 添加当前目录到模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from aiohttp import web

# 导入插件系统和工具函数
from plugin_system import Plugin, PluginManager
from plugins.utils import handle_at_command, extract_command, is_at_bot

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("LCHBot")

# 群组活跃度跟踪类
class GroupActivityTracker:
    def __init__(self, retention_days=7):
        self.retention_days = retention_days
        # 格式: {group_id: {date_str: {user_id: message_count}}}
        self.daily_activity = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        # 格式: {group_id: {user_id: last_active_time}}
        self.last_active = defaultdict(lambda: defaultdict(float))
        # 消息类型统计 {group_id: {date_str: {msg_type: count}}}
        self.message_types = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        # 活跃时段统计 {group_id: {date_str: {hour: count}}}
        self.active_hours = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        
    def track_message(self, group_id: int, user_id: int, message_type: str, timestamp: float):
        """记录一条消息"""
        date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        hour = datetime.fromtimestamp(timestamp).hour
        
        # 记录用户活跃度
        self.daily_activity[group_id][date_str][user_id] += 1
        self.last_active[group_id][user_id] = timestamp
        
        # 记录消息类型
        self.message_types[group_id][date_str][message_type] += 1
        
        # 记录活跃时段
        self.active_hours[group_id][date_str][hour] += 1
        
        # 清理过期数据
        self._cleanup_old_data()
        
    def _cleanup_old_data(self):
        """清理过期数据"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_str = cutoff_date.strftime('%Y-%m-%d')
        
        for group_id in list(self.daily_activity.keys()):
            for date_str in list(self.daily_activity[group_id].keys()):
                if date_str < cutoff_str:
                    del self.daily_activity[group_id][date_str]
                    
        for group_id in list(self.message_types.keys()):
            for date_str in list(self.message_types[group_id].keys()):
                if date_str < cutoff_str:
                    del self.message_types[group_id][date_str]
                    
        for group_id in list(self.active_hours.keys()):
            for date_str in list(self.active_hours[group_id].keys()):
                if date_str < cutoff_str:
                    del self.active_hours[group_id][date_str]
    
    def get_group_activity(self, group_id: int, days: int = 1) -> Dict[str, Any]:
        """获取群组活跃度信息"""
        result = {
            "total_messages": 0,
            "active_users": 0,
            "most_active_users": [],
            "message_types": {},
            "peak_hours": {},
            "daily_stats": {}
        }
        
        # 计算日期范围
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 用户消息计数
        user_counts = Counter()
        
        # 收集统计数据
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            
            # 当天的用户活跃度
            daily_user_activity = self.daily_activity[group_id].get(date_str, {})
            daily_total = sum(daily_user_activity.values())
            result["total_messages"] += daily_total
            
            # 记录到每日统计
            result["daily_stats"][date_str] = {
                "messages": daily_total,
                "active_users": len(daily_user_activity)
            }
            
            # 更新用户总消息计数
            for user_id, count in daily_user_activity.items():
                user_counts[user_id] += count
            
            # 消息类型统计
            for msg_type, count in self.message_types[group_id].get(date_str, {}).items():
                if msg_type not in result["message_types"]:
                    result["message_types"][msg_type] = 0
                result["message_types"][msg_type] += count
            
            # 活跃时段统计
            for hour, count in self.active_hours[group_id].get(date_str, {}).items():
                if hour not in result["peak_hours"]:
                    result["peak_hours"][hour] = 0
                result["peak_hours"][hour] += count
            
            current_date += timedelta(days=1)
        
        # 计算活跃用户数和最活跃用户
        result["active_users"] = len(user_counts)
        result["most_active_users"] = [
            {"user_id": user_id, "message_count": count}
            for user_id, count in user_counts.most_common(10)
        ]
        
        return result

# 内置命令处理类
class SystemCommandHandler:
    def __init__(self, bot):
        self.bot = bot
        self.command_patterns = {
            'system': re.compile(r'^/system$'),
            'activity': re.compile(r'^/activity\s*(\d+)?$'),
            'plugins': re.compile(r'^/plugins$')
        }
        
    async def handle_system_command(self, event: Dict[str, Any]) -> bool:
        """处理系统命令"""
        message_type = event.get('message_type', '')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 获取机器人QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否是@机器人的消息
        if not is_at_bot(event, bot_qq):
            return False
            
        # 提取命令
        command = extract_command(event, bot_qq)
        
        # 系统信息命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['system'])
        if is_at_command and match:
            return await self._handle_system_info(event)
            
        # 群组活跃度命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['activity'])
        if is_at_command and match:
            days_str = match.group(1)
            days = int(days_str) if days_str else 7
            return await self._handle_group_activity(event, days)
            
        # 插件列表命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['plugins'])
        if is_at_command and match:
            return await self._handle_plugin_list(event)
            
        return False
            
    async def _handle_system_info(self, event: Dict[str, Any]) -> bool:
        """处理系统信息命令"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        logger.info("接收到系统信息命令")
        
        # 获取系统信息
        try:
            # 构建系统信息响应
            system_info = {
                "系统": platform.system(),
                "版本": platform.version(),
                "Python版本": platform.python_version(),
                "CPU使用率": f"{psutil.cpu_percent()}%",
                "内存使用": f"{psutil.virtual_memory().percent}%",
                "启动时间": f"{datetime.fromtimestamp(psutil.boot_time()).strftime('%Y-%m-%d %H:%M:%S')}",
                "机器名": platform.node()
            }
        except Exception as e:
            # 如果psutil出错
            logger.error(f"获取系统信息出错: {e}")
            system_info = {
                "系统": platform.system(),
                "版本": platform.version(),
                "Python版本": platform.python_version(),
                "机器名": platform.node()
            }
        
        # 获取机器人信息
        bot_info = {
            "名称": self.bot.config['bot']['name'],
            "QQ号": self.bot.config.get("bot", {}).get("self_id", "未知"),
            "插件数量": len(self.bot.plugin_manager.get_all_plugins()),
            "活跃插件": len(self.bot.plugin_manager.get_active_plugins()),
            "HTTP服务": f"{self.bot.http_host}:{self.bot.http_port}"
        }
        
        # 构建响应消息
        response = "系统信息：\n"
        for key, value in system_info.items():
            response += f"- {key}: {value}\n"
            
        response += "\n机器人信息：\n"
        for key, value in bot_info.items():
            response += f"- {key}: {value}\n"
        
        # 发送响应
        await self.bot.send_msg(
            message_type=message_type,
            user_id=user_id,
            group_id=group_id,
            message=response
        )
        
        return True
        
    async def _handle_group_activity(self, event: Dict[str, Any], days: int = 7) -> bool:
        """处理群组活跃度命令"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 只在群聊中有效
        if message_type != 'group' or not group_id:
            if message_type == 'private':
                await self.bot.send_msg(
                    message_type='private',
                    user_id=user_id,
                    message="活跃度命令只能在群聊中使用"
                )
            return True
        
        logger.info(f"接收到群活跃度命令，群号: {group_id}, 天数: {days}")
        
        # 限制天数范围
        days = max(1, min(days, 30))
            
        # 获取群活跃度数据
        activity_data = self.bot.activity_tracker.get_group_activity(group_id, days)
        
        # 构建响应消息
        response = f"【群 {group_id} 活跃度统计 (近{days}天)】\n"
        response += f"总消息数: {activity_data['total_messages']}\n"
        response += f"活跃用户数: {activity_data['active_users']}\n"
        
        # 添加最活跃用户
        if activity_data['most_active_users']:
            response += "\n最活跃的用户:\n"
            rank = 1
            for user in activity_data['most_active_users'][:5]:  # 只显示前5名
                response += f"{rank}. {user['user_id']} - {user['message_count']}条消息\n"
                rank += 1
        
        # 添加消息类型分布
        if activity_data['message_types']:
            response += "\n消息类型分布:\n"
            for msg_type, count in sorted(activity_data['message_types'].items(), key=lambda x: x[1], reverse=True):
                response += f"- {msg_type}: {count}条\n"
        
        # 添加峰值时段
        if activity_data['peak_hours']:
            peak_hours = sorted(activity_data['peak_hours'].items(), key=lambda x: x[1], reverse=True)
            response += "\n活跃时段 (24小时制):\n"
            for hour, count in peak_hours[:3]:  # 只显示前3个高峰时段
                response += f"- {hour}时: {count}条消息\n"
        
        # 发送响应
        await self.bot.send_msg(
            message_type='group',
            group_id=group_id,
            message=response
        )
        
        return True
        
    async def _handle_plugin_list(self, event: Dict[str, Any]) -> bool:
        """处理插件列表命令"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        logger.info("接收到插件列表命令")
        
        # 获取所有插件
        all_plugins = self.bot.plugin_manager.get_all_plugins()
        
        # 构建响应消息
        response = "【插件列表】\n"
        if not all_plugins:
            response += "当前没有加载任何插件。\n"
        else:
            # 按状态分类
            active_plugins = []
            disabled_plugins = []
            error_plugins = []
            
            for plugin in all_plugins:
                if plugin.status == "active":
                    active_plugins.append(plugin)
                elif plugin.status == "disabled":
                    disabled_plugins.append(plugin)
                elif plugin.status == "error":
                    error_plugins.append(plugin)
            
            # 活跃插件
            response += f"\n活跃插件 ({len(active_plugins)}):\n"
            for plugin in active_plugins:
                response += f"- [{plugin.id}] {plugin.name}\n"
            
            # 禁用插件
            if disabled_plugins:
                response += f"\n禁用插件 ({len(disabled_plugins)}):\n"
                for plugin in disabled_plugins:
                    reason = f": {plugin.error_message}" if plugin.error_message else ""
                    response += f"- [{plugin.id}] {plugin.name}{reason}\n"
            
            # 错误插件
            if error_plugins:
                response += f"\n错误插件 ({len(error_plugins)}):\n"
                for plugin in error_plugins:
                    error = f": {plugin.error_message}" if plugin.error_message else ""
                    response += f"- [{plugin.id}] {plugin.name}{error}\n"
        
        # 发送响应
        await self.bot.send_msg(
            message_type=message_type,
            user_id=user_id,
            group_id=group_id,
            message=response
        )
        
        return True

class LCHBot:
    """LCHBot主类，用于管理机器人的生命周期和事件处理"""
    
    def __init__(self, config_path: str = "config/config.yml"):
        # 加载配置
        self.config_path = config_path
        self.config = self._load_config()
        
        # 设置属性
        self.plugin_manager = PluginManager(self)
        self.session = None
        self.plugins = []
        self.http_host = self.config.get("http_server", {}).get("host", "127.0.0.1")
        self.http_port = self.config.get("http_server", {}).get("port", 8080)
        
        # 初始化HTTP应用
        self.app = web.Application()
        
        # 活跃度追踪器
        self.activity_tracker = GroupActivityTracker()
        
        # 系统命令处理器
        self.system_handler = SystemCommandHandler(self)
        
        # 插件运行状态 {plugin_id: bool}
        self.plugin_status = {}
        
        # 插件调用计数 {plugin_id: count}
        self.plugin_calls = Counter()
        
        # 重载计数
        self.reload_count = 0
        
        logger.info(f"LCHBot初始化完成，使用配置文件: {config_path}")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"配置加载成功")
                return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            # 返回默认配置
            return {
                "bot": {"name": "LCHBot", "self_id": ""},
                "llonebot": {
                    "http_api": {
                        "base_url": "http://127.0.0.1:5700",
                        "token": ""
                    }
                },
                "http_server": {"host": "127.0.0.1", "port": 8080},
                "plugins": {"disabled": []}
            }
    
    def save_config(self) -> None:
        """保存配置文件"""
        try:
            # 确保配置路径存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # 写入配置文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, indent=4, default_flow_style=False, allow_unicode=True)
                
            logger.info(f"配置保存成功: {self.config_path}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}", exc_info=True)

    async def initialize(self):
        """初始化机器人"""
        # 创建HTTP会话
        self.session = aiohttp.ClientSession()
        
        # 加载插件
        await self.load_plugins()
        
        # 初始化内联调试插件
        self.inline_debug_plugin = InlineDebugPlugin(self)
        logger.info(f"内联调试插件已初始化")
        
        logger.info(f"{self.config['bot']['name']} ({self.config['bot']['name']}) 初始化完成")

    async def load_plugins(self):
        """加载插件"""
        # 清空插件管理器
        self.plugin_manager = PluginManager(self)
        
        plugin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        logger.debug(f"插件目录: {plugin_dir}")
        
        # 打印更多调试信息
        logger.debug(f"当前工作目录: {os.getcwd()}")
        logger.debug(f"sys.path: {sys.path}")
        logger.debug(f"当前文件路径: {__file__}")
        
        if not os.path.exists(plugin_dir):
            os.makedirs(plugin_dir)
            logger.info(f"创建插件目录: {plugin_dir}")
            
        enabled_plugins = self.config["plugins"]["enabled"]
        disabled_plugins = self.config["plugins"]["disabled"]
        
        logger.debug(f"启用的插件: {enabled_plugins}")
        logger.debug(f"禁用的插件: {disabled_plugins}")
        
        # 初始化插件目录
        init_file = os.path.join(plugin_dir, "__init__.py")
        if not os.path.exists(init_file):
            with open(init_file, "w", encoding="utf-8") as f:
                f.write("# 插件包初始化文件\n")
            
        # 获取插件目录下的所有Python文件
        for filename in os.listdir(plugin_dir):
            if not filename.endswith(".py") or filename.startswith("__"):
                continue
            
            plugin_name = filename[:-3]
            if plugin_name in disabled_plugins:
                logger.info(f"跳过已禁用的插件: {plugin_name}")
                continue
                
            if enabled_plugins and plugin_name not in enabled_plugins:
                logger.info(f"跳过未启用的插件: {plugin_name}")
                continue
            
            try:
                # 导入插件模块
                try:
                    # 使用spec方法直接从文件导入
                    plugin_path = os.path.join(plugin_dir, filename)
                    module_name = f"plugins.{plugin_name}"
                    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                    if not spec or not spec.loader:
                        logger.error(f"无法为插件 {plugin_name} 创建模块规格")
                        continue
                    
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    logger.debug(f"成功导入插件模块: {plugin_name}")
                    
                except Exception as e:
                    logger.error(f"导入插件模块 {plugin_name} 失败: {e}", exc_info=True)
                    continue
                
                # 查找插件类
                plugin_found = False
                if hasattr(module, 'plugin_class'):
                    # 优先查找 plugin_class 变量
                    try:
                        plugin_class = getattr(module, 'plugin_class')
                        logger.debug(f"找到plugin_class: {plugin_class}")
                        logger.debug(f"plugin_class类型: {type(plugin_class)}")
                        logger.debug(f"是否是类型: {isinstance(plugin_class, type)}")
                        
                        # 使用类名比较而不是类型比较
                        if (isinstance(plugin_class, type) and 
                            hasattr(plugin_class, "__name__") and
                            plugin_class.__name__ != "Plugin"):
                            # 实例化插件
                            plugin_instance = plugin_class(self)
                            self.plugin_manager.register_plugin(plugin_instance)
                            logger.info(f"已加载插件: {plugin_instance.name} (ID: {plugin_instance.id})")
                            plugin_found = True
                    except Exception as e:
                        logger.error(f"通过 plugin_class 加载插件 {plugin_name} 失败: {e}", exc_info=True)
                
                # 如果没有 plugin_class 变量或加载失败，则尝试查找类定义
                if not plugin_found:
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        # 检查是否为类，是否继承自Plugin，不是Plugin本身，且在当前模块中定义
                        if (isinstance(attr, type) and 
                            issubclass(attr, Plugin) and 
                            attr != Plugin):
                            try:
                                # 实例化插件
                                plugin_instance = attr(self)
                                self.plugin_manager.register_plugin(plugin_instance)
                                logger.info(f"已加载插件: {plugin_instance.name} (ID: {plugin_instance.id})")
                                plugin_found = True
                            except Exception as e:
                                logger.error(f"实例化插件 {attr_name} 失败: {e}", exc_info=True)
                
                if not plugin_found:
                    logger.warning(f"在模块 {plugin_name} 中没有找到有效的插件类")
                    
            except Exception as e:
                logger.error(f"加载插件 {plugin_name} 失败: {e}", exc_info=True)

    async def handle_event(self, event: Dict[str, Any]):
        """处理事件"""
        event_type = event.get("post_type")
        
        if event_type == "message":
            message_type = event.get("message_type", "unknown")
            sender = event.get("sender", {}).get("nickname", "未知用户")
            user_id = event.get("user_id", "未知ID")
            raw_message = event.get("raw_message", "")
            message_content = event.get("message", "")
            logger.info(f"收到{message_type}消息 - 来自: {sender}({user_id}) - 内容: {raw_message}")
            
            # 如果是群消息，记录活跃度数据
            if message_type == 'group' and 'group_id' in event:
                self.activity_tracker.track_message(
                    group_id=event['group_id'],
                    user_id=user_id,
                    message_type=event.get('sub_type', 'normal'),
                    timestamp=event.get('time', time.time())
                )
            
            # 先尝试处理内联调试插件
            if self.inline_debug_plugin:
                try:
                    logger.debug(f"尝试使用内联调试插件处理消息")
                    if await self.inline_debug_plugin.handle_message(event):
                        logger.info(f"消息已被内联调试插件处理")
                        return
                except Exception as e:
                    logger.error(f"内联调试插件处理消息出错: {e}", exc_info=True)
            
            # 再尝试处理系统命令
            if await self.system_handler.handle_system_command(event):
                return
                
            # 最后使用插件系统处理消息
            await self.plugin_manager.dispatch_message(event)
            
        elif event_type == "notice":
            notice_type = event.get("notice_type", "unknown")
            sub_type = event.get("sub_type", "unknown")
            group_id = event.get("group_id", "未知群")
            user_id = event.get("user_id", "未知用户")
            
            # 记录详细的通知事件信息
            log_msg = f"收到通知事件: {notice_type}"
            if sub_type != "unknown":
                log_msg += f", 子类型: {sub_type}"
            if group_id != "未知群":
                log_msg += f", 群ID: {group_id}"
            if user_id != "未知用户":
                log_msg += f", 用户ID: {user_id}"
                
            # 检测邀请事件
            if "invit" in str(event).lower() or "邀请" in str(event).lower():
                # 专门处理邀请相关事件
                logger.info(f"检测到可能的邀请事件: {json.dumps(event, ensure_ascii=False)}")
                
                # 检查新版邀请事件格式
                templ_id = event.get('templId')
                templ_param = event.get('templParam', {})
                if templ_id == '10179' and templ_param and 'invitor' in templ_param:
                    invitor = templ_param.get('invitor', '未知')
                    invitee = templ_param.get('invitee', '未知')
                    logger.info(f"收到新人被邀请进群消息: 邀请人={invitor}, 被邀请人={invitee}, 群ID={group_id}")
            else:
                logger.info(log_msg)
            
            # 使用插件系统处理通知
            await self.plugin_manager.dispatch_notice(event)
        
        elif event_type == "request":
            request_type = event.get("request_type", "unknown")
            logger.info(f"收到请求事件: {request_type}, 详情: {json.dumps(event, ensure_ascii=False)}")
            await self.plugin_manager.dispatch_request(event)
        
        else:
            logger.warning(f"未知的事件类型: {event_type}, 详情: {json.dumps(event, ensure_ascii=False)}")

    async def handle_event_http(self, request: web.Request) -> web.Response:
        """HTTP事件处理函数"""
        try:
            event_data = await request.json()
            # 打印完整的事件数据以便调试
            logger.debug(f"收到HTTP事件: {json.dumps(event_data, ensure_ascii=False, indent=2)}")
            
            # 异步处理事件，避免阻塞响应
            asyncio.create_task(self.handle_event(event_data))
            
            # 返回空对象表示成功接收
            return web.json_response({})
        except Exception as e:
            logger.error(f"处理HTTP事件时出错: {e}")
            return web.json_response({"status": "failed", "error": str(e)})

    async def run(self):
        """运行机器人"""
        await self.initialize()
        
        # 设置HTTP路由
        self.app.router.add_post("/", self.handle_event_http)
        
        # 启动HTTP服务器
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.http_host, int(self.http_port))
        
        try:
            await site.start()
            logger.info(f"HTTP事件服务器已启动，监听地址: http://{self.http_host}:{self.http_port}/")
            
            # 保持运行
            while True:
                await asyncio.sleep(3600)  # 每小时检查一次
                
        except asyncio.CancelledError:
            logger.info("机器人运行被取消")
        finally:
            # 关闭服务
            await runner.cleanup()
            logger.info("HTTP服务已关闭")

    async def close(self):
        """关闭机器人"""
        if self.session:
            await self.session.close()
            logger.info("HTTP会话已关闭")
    
    def reload_plugins(self):
        """重新加载插件"""
        async def _reload():
            logger.info("正在重新加载插件...")
            await self.load_plugins()
            logger.info("插件重新加载完成")
            
        # 创建异步任务
        asyncio.create_task(_reload())
        return True

    async def _call_api(self, url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """调用LLOneBot API"""
        if not self.session:
            logger.error("HTTP会话未初始化")
            return {"status": "failed", "error": "HTTP会话未初始化"}
            
        # 记录API调用信息
        logger.info(f"API调用: {url} - 参数: {json.dumps(data, ensure_ascii=False)[:100]}...")
            
        # 重试设置
        max_retries = 3
        retry_delay = 1.0  # 初始重试延迟（秒）
        attempt = 0
            
        while attempt < max_retries:
            try:
                api_base_url = self.config.get("llonebot", {}).get("http_api", {}).get("base_url", "")
                if not api_base_url:
                    logger.error("未配置LLOneBot API地址")
                    return {"status": "failed", "error": "未配置LLOneBot API地址"}
                    
                token = self.config.get("llonebot", {}).get("http_api", {}).get("token", "")
                headers = {"Authorization": f"Bearer {token}"} if token else {}
                
                full_url = f"{api_base_url}{url}"
                logger.debug(f"调用API: {full_url}, 数据: {json.dumps(data, ensure_ascii=False)}")
                
                # 添加超时设置
                timeout = aiohttp.ClientTimeout(total=10, connect=5)
                
                async with self.session.post(full_url, json=data, headers=headers, timeout=timeout) as response:
                    result = await response.json()
                    
                    if isinstance(result, dict) and result.get("status") == "failed":
                        logger.error(f"API调用失败: {result.get('error')}")
                    else:
                        logger.info(f"API调用成功: {url} - 响应: {json.dumps(result, ensure_ascii=False)[:100]}...")
                        
                    return result
            except asyncio.TimeoutError:
                attempt += 1
                if attempt >= max_retries:
                    logger.error(f"API调用超时，已重试{max_retries}次")
                    return {"status": "failed", "error": "连接超时，请检查LLOneBot服务是否正常运行"}
                logger.warning(f"API调用超时，正在重试({attempt}/{max_retries})...")
                await asyncio.sleep(retry_delay * attempt)  # 指数退避策略
            except aiohttp.ClientConnectorError:
                attempt += 1
                if attempt >= max_retries:
                    logger.error(f"无法连接到LLOneBot服务器，已重试{max_retries}次")
                    return {"status": "failed", "error": "无法连接到LLOneBot服务器，请确保服务已启动"}
                logger.warning(f"连接LLOneBot服务器失败，正在重试({attempt}/{max_retries})...")
                await asyncio.sleep(retry_delay * attempt)
            except aiohttp.ServerDisconnectedError:
                attempt += 1
                if attempt >= max_retries:
                    logger.error(f"服务器断开连接，已重试{max_retries}次")
                    return {"status": "failed", "error": "服务器断开连接，请检查LLOneBot服务是否稳定"}
                logger.warning(f"服务器断开连接，正在重试({attempt}/{max_retries})...")
                await asyncio.sleep(retry_delay * attempt)
            except Exception as e:
                logger.error(f"调用API出错: {e}")
                return {"status": "failed", "error": str(e)}
        
        # 如果所有重试都失败但没有触发特定异常，确保返回一个字典
        return {"status": "failed", "error": "未知错误，API调用失败"}

    async def send_msg(self, message_type: str, user_id: Optional[int] = None, 
                     group_id: Optional[int] = None, message: Union[str, List[Dict[str, Any]]] = "",
                     auto_escape: bool = False) -> Dict[str, Any]:
        """发送消息"""
        data = {
            "message_type": message_type,
            "message": message,
            "auto_escape": auto_escape
        }
        
        if user_id is not None:
            data["user_id"] = user_id
            logger.info(f"发送{message_type}消息 - 目标用户: {user_id} - 内容: {message}")
            
        if group_id is not None:
            data["group_id"] = group_id
            logger.info(f"发送{message_type}消息 - 目标群组: {group_id} - 内容: {message}")
            
        return await self._call_api("/send_msg", data)
        
    async def get_group_member_info(self, group_id: int, user_id: int) -> Dict[str, Any]:
        """获取群成员信息"""
        data = {
            "group_id": group_id,
            "user_id": user_id
        }
        
        result = await self._call_api("/get_group_member_info", data)
        logger.info(f"获取群{group_id}成员{user_id}信息: {json.dumps(result, ensure_ascii=False)[:100]}...")
        return result
        
    async def set_group_kick(self, group_id: int, user_id: int, reject_add_request: bool = False) -> Dict[str, Any]:
        """将用户踢出群组"""
        data = {
            "group_id": group_id,
            "user_id": user_id,
            "reject_add_request": reject_add_request
        }
        
        result = await self._call_api("/set_group_kick", data)
        logger.info(f"将用户{user_id}踢出群{group_id}: {json.dumps(result, ensure_ascii=False)[:100]}...")
        return result

    # 其他API方法保持不变...
    # ... (这里省略其他API方法)

# 为调试目的添加内联插件类
class InlineDebugPlugin(Plugin):
    """内联调试插件，用于测试插件系统"""
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "InlineDebugPlugin"
        self.command_pattern = re.compile(r'^/debug$')
        logger.info(f"插件 {self.name} 已初始化")
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 获取机器人QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否是@机器人的消息
        if not is_at_bot(event, bot_qq):
            return False
            
        # 提取命令
        command = extract_command(event, bot_qq)
        if command == "/debug":
            logger.info(f"接收到调试插件命令: {command}")
            
            # 构建详细的调试信息
            debug_info = "【调试信息】\n"
            debug_info += f"- 消息类型: {message_type}\n"
            debug_info += f"- 发送者ID: {user_id}\n"
            
            if group_id:
                debug_info += f"- 群组ID: {group_id}\n"
                
            # 添加更多技术细节
            debug_info += "\n【事件数据】\n"
            for key, value in event.items():
                if key not in ['message', 'raw_message', 'sender']:
                    debug_info += f"- {key}: {value}\n"
            
            # 原始消息内容
            raw_message = event.get('raw_message', '')
            debug_info += f"\n【原始消息】\n{raw_message}\n"
            
            # 提取的命令
            debug_info += f"\n【提取的命令】\n{command}\n"
            
            # 发送回复
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=debug_info
            )
            
            return True
            
        return False

# 主程序逻辑
async def main():
    """主函数"""
    # 确保日志目录存在
    os.makedirs('logs', exist_ok=True)
    
    # 确保能正确导入src目录下的模块
    src_dir = os.path.dirname(os.path.abspath(__file__))  # src目录
    base_dir = os.path.dirname(src_dir)  # 项目根目录
    
    # 将项目根目录和src目录添加到Python搜索路径
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    
    logger.debug(f"项目根目录: {base_dir}")
    logger.debug(f"src目录: {src_dir}")
    logger.debug(f"Python路径: {sys.path}")
    
    try:
        # 实例化并运行机器人
        bot = LCHBot("config/config.yml")
        await bot.run()
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")
    except Exception as e:
        logger.error(f"运行时错误: {e}", exc_info=True)
    finally:
        await bot.close()

if __name__ == "__main__":
    # 创建日志目录
    os.makedirs("logs", exist_ok=True)
    
    # 启动异步事件循环
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main()) 