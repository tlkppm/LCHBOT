#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import time
import json
import os
import sys
from typing import Dict, Any, List, Set, Optional, Tuple
from datetime import datetime, timedelta

# 添加项目根目录到系统路径，以便正确导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 导入Plugin基类
from plugin_system import Plugin

logger = logging.getLogger("LCHBot")

class RateLimiter(Plugin):
    """
    用户访问限制插件
    功能：限制用户API调用频率，防止刷屏，超过访问限制会被临时拉黑
    这是一个全局生效的插件，不区分群组
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        # 从配置文件加载设置
        self.config = self.bot.config.get("rate_limiter", {})
        # 默认时间窗口（秒）
        self.time_window = self.config.get("time_window", 60)
        # 默认最大请求次数
        self.max_requests = self.config.get("max_requests", 5)
        # 默认拉黑时间（分钟）
        self.blacklist_duration = self.config.get("blacklist_duration", 10)
        # 是否启用功能
        self.enabled = self.config.get("enabled", True)
        # 白名单用户
        self.whitelist_users = set(self.config.get("whitelist_users", []))
        # 添加Q群管家到白名单
        self.whitelist_users.add(2854196310)  # Q群管家QQ号
        
        # 用户请求记录 {user_id: [(timestamp, count)]}
        self.user_requests: Dict[int, List[Tuple[float, int]]] = {}
        # 被拉黑用户 {user_id: expiry_time}
        self.blacklisted_users: Dict[int, float] = {}
        # 已提示过的拉黑用户（避免重复提示）
        self.notified_users: Set[int] = set()
        
        # 持久化数据文件
        self.data_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                    "data", "rate_limiter.json")
        
        # 创建数据目录（如果不存在）
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        
        # 加载数据
        self.load_data()
        
        logger.info(f"访问限制插件已初始化，全局生效模式")
    
    def save_data(self) -> None:
        """保存数据到文件"""
        data = {
            "blacklisted_users": {
                str(user_id): expiry_time for user_id, expiry_time in self.blacklisted_users.items()
            },
            "user_requests": {
                str(user_id): requests for user_id, requests in self.user_requests.items()
            },
            "notified_users": list(self.notified_users)
        }
        
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"保存访问限制数据失败: {e}", exc_info=True)
    
    def load_data(self) -> None:
        """从文件加载数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 加载拉黑用户
                    blacklisted_users = data.get("blacklisted_users", {})
                    self.blacklisted_users = {
                        int(user_id): expiry_time 
                        for user_id, expiry_time in blacklisted_users.items()
                    }
                    
                    # 加载用户请求记录
                    user_requests = data.get("user_requests", {})
                    self.user_requests = {
                        int(user_id): requests 
                        for user_id, requests in user_requests.items()
                    }
                    
                    # 加载已提示用户
                    self.notified_users = set(data.get("notified_users", []))
                    
                    # 清理过期的拉黑记录
                    self.cleanup_expired()
                    
                    logger.info(f"加载访问限制数据: {len(self.blacklisted_users)} 个拉黑用户, {len(self.user_requests)} 个用户请求记录")
        except Exception as e:
            logger.error(f"加载访问限制数据失败: {e}", exc_info=True)
            self.blacklisted_users = {}
            self.user_requests = {}
            self.notified_users = set()
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        from plugins.utils import extract_command, is_at_bot
        
        user_id = event.get('user_id')
        message_type = event.get('message_type', '')
        
        # 确保user_id是整数类型
        if user_id is None:
            return False
            
        user_id = int(user_id)
        
        # 如果是私聊，直接放行
        if message_type == 'private':
            return False
        
        # 如果用户在白名单中，直接放行
        if user_id in self.whitelist_users:
            return False
            
        # 如果功能未启用，直接放行
        if not self.enabled:
            return False
        
        # 获取原始消息
        message = event.get('raw_message', '')
        
        # 如果消息中有@机器人，处理管理员命令
        if '[CQ:at,qq=' in message:
            bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
            if is_at_bot(event, bot_qq) and self.is_admin_command(event):
                return await self.handle_admin_command(event)
        
        # 检查用户是否被拉黑
        if self.is_blacklisted(user_id):
            # 如果用户被拉黑且没有收到通知
            if user_id not in self.notified_users:
                # 发送一次拉黑通知
                # 使用直接访问字典而不是get方法
                expiry_time = self.blacklisted_users[user_id] if user_id in self.blacklisted_users else 0
                remaining_minutes = max(0, int((expiry_time - time.time()) / 60))
                
                if message_type == 'group':
                    group_id = event.get('group_id')
                    if group_id is not None:
                        await self.bot.send_msg(
                            message_type='group',
                            group_id=int(group_id),
                            message=f"[CQ:at,qq={user_id}] 您的消息发送过于频繁，已被临时限制 {remaining_minutes} 分钟。"
                        )
                
                # 标记为已通知
                self.notified_users.add(user_id)
                self.save_data()
                
            return True  # 拦截此消息
        
        # 记录用户请求并检查是否超过限制
        if self.add_request(user_id):
            logger.info(f"用户 {user_id} 超过访问限制，已临时拉黑 {self.blacklist_duration} 分钟")
            
            # 发送拉黑通知
            if message_type == 'group':
                group_id = event.get('group_id')
                if group_id is not None:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=int(group_id),
                        message=f"[CQ:at,qq={user_id}] 您的消息发送过于频繁，已被临时限制 {self.blacklist_duration} 分钟。"
                    )
            
            # 标记为已通知
            self.notified_users.add(user_id)
            self.save_data()
            
            return True  # 拦截此消息
        
        return False  # 允许继续处理
    
    def is_admin_command(self, event: Dict[str, Any]) -> bool:
        """判断是否是管理员命令"""
        from plugins.utils import extract_command, is_at_bot
        
        # 获取原始消息
        message = event.get('raw_message', '')
        
        # 如果消息中有@机器人，则提取命令部分
        if '[CQ:at,qq=' in message:
            bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
            if is_at_bot(event, bot_qq):
                message = extract_command(event, bot_qq)
                
                # 检查是否是设置参数的命令
                if re.match(r'^/rate\s+set\s+(window|max|duration)\s+\d+$', message):
                    return True
                    
                # 检查是否是启用/禁用限制的命令
                if re.match(r'^/rate\s+(enable|disable)$', message):
                    return True
                
                # 检查是否是添加/移除白名单的命令
                if re.match(r'^/rate\s+(add|remove)\s+whitelist\s+\d+$', message):
                    return True
                    
                # 检查是否是列出设置的命令
                if message == '/rate settings':
                    return True
                
                # 检查是否是解除拉黑的命令
                if re.match(r'^/rate\s+unblock\s+\d+$', message):
                    return True
        
        return False
    
    async def handle_admin_command(self, event: Dict[str, Any]) -> bool:
        """处理管理员命令"""
        from plugins.utils import extract_command, is_at_bot
        
        # 获取原始消息
        message = event.get('raw_message', '')
        
        # 如果消息中有@机器人，则提取命令部分
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        if is_at_bot(event, bot_qq):
            message = extract_command(event, bot_qq)
        else:
            # 如果没有@机器人，直接返回
            return False
        
        user_id = event.get('user_id')
        group_id = event.get('group_id')
        
        # 确保user_id和group_id是整数类型
        if user_id is None or group_id is None:
            return False
            
        user_id = int(user_id)
        group_id = int(group_id)
        
        # 检查是否是超级用户
        if str(user_id) not in self.bot.config.get("bot", {}).get("superusers", []):
            return False
        
        # 设置参数
        param_match = re.match(r'^/rate\s+set\s+(window|max|duration)\s+(\d+)$', message)
        if param_match:
            param_type = param_match.group(1)
            value = int(param_match.group(2))
            
            # 初始化配置（如果不存在）
            if "rate_limiter" not in self.bot.config:
                self.bot.config["rate_limiter"] = {}
            
            if param_type == 'window':
                self.time_window = value
                self.bot.config["rate_limiter"]["time_window"] = value
                param_name = "时间窗口"
                unit = "秒"
            elif param_type == 'max':
                self.max_requests = value
                self.bot.config["rate_limiter"]["max_requests"] = value
                param_name = "最大请求次数"
                unit = "次"
            elif param_type == 'duration':
                self.blacklist_duration = value
                self.bot.config["rate_limiter"]["blacklist_duration"] = value
                param_name = "拉黑时间"
                unit = "分钟"
            
            # 保存配置
            self.bot.save_config()
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"已设置{param_name}为 {value} {unit}"
            )
            logger.info(f"管理员 {user_id} 设置访问限制参数 {param_type} = {value}")
            return True
        
        # 启用/禁用限制
        enable_match = re.match(r'^/rate\s+(enable|disable)$', message)
        if enable_match:
            enable = enable_match.group(1) == 'enable'
            self.enabled = enable
            
            # 初始化配置（如果不存在）
            if "rate_limiter" not in self.bot.config:
                self.bot.config["rate_limiter"] = {}
                
            self.bot.config["rate_limiter"]["enabled"] = enable
            self.bot.save_config()
            
            status = "启用" if enable else "禁用"
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"已{status}访问限制功能"
            )
            logger.info(f"管理员 {user_id} {status}了访问限制功能")
            return True
        
        # 添加/移除白名单
        whitelist_match = re.match(r'^/rate\s+(add|remove)\s+whitelist\s+(\d+)$', message)
        if whitelist_match:
            action = whitelist_match.group(1)  # add/remove
            target_id = int(whitelist_match.group(2))
            
            if action == 'add':
                self.whitelist_users.add(target_id)
                action_text = "添加到"
            else:  # remove
                if target_id in self.whitelist_users:
                    self.whitelist_users.remove(target_id)
                action_text = "从"
            
            # 初始化配置（如果不存在）
            if "rate_limiter" not in self.bot.config:
                self.bot.config["rate_limiter"] = {}
                
            self.bot.config["rate_limiter"]["whitelist_users"] = list(self.whitelist_users)
            self.bot.save_config()
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"已{action_text}白名单移除用户 {target_id}"
            )
            logger.info(f"管理员 {user_id} {action_text}白名单移除用户 {target_id}")
            return True
        
        # 列出设置
        if message == '/rate settings':
            # 统计有效拉黑用户
            current_time = time.time()
            active_blacklist = sum(1 for expiry in self.blacklisted_users.values() if expiry > current_time)
            
            settings = f"""访问限制设置:
- 功能状态: {'启用' if self.enabled else '禁用'}
- 时间窗口: {self.time_window} 秒
- 最大请求次数: {self.max_requests} 次
- 拉黑时间: {self.blacklist_duration} 分钟
- 白名单用户数: {len(self.whitelist_users)}
- 当前拉黑用户数: {active_blacklist}"""
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=settings
            )
            return True
        
        # 解除拉黑
        unblock_match = re.match(r'^/rate\s+unblock\s+(\d+)$', message)
        if unblock_match:
            target_id = int(unblock_match.group(1))
            
            if target_id in self.blacklisted_users:
                del self.blacklisted_users[target_id]
                if target_id in self.notified_users:
                    self.notified_users.remove(target_id)
                self.save_data()
                
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"已解除用户 {target_id} 的访问限制"
                )
                logger.info(f"管理员 {user_id} 解除了用户 {target_id} 的访问限制")
            else:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"用户 {target_id} 当前未被限制"
                )
            return True
        
        return False
    
    def is_blacklisted(self, user_id: int) -> bool:
        """检查用户是否被拉黑"""
        # 确保user_id是整数类型
        if user_id is None:
            return False
            
        user_id = int(user_id)
        
        if user_id not in self.blacklisted_users:
            return False
            
        current_time = time.time()
        # 使用直接访问字典而不是get方法
        expiry_time = self.blacklisted_users[user_id]
        
        # 如果拉黑已过期
        if current_time > expiry_time:
            # 清理过期记录
            if user_id in self.blacklisted_users:
                del self.blacklisted_users[user_id]
            if user_id in self.notified_users:
                self.notified_users.remove(user_id)
            self.save_data()
            return False
        
        return True
    
    def add_request(self, user_id: int) -> bool:
        """添加用户请求记录，如果超过限制则拉黑并返回True"""
        # 确保user_id是整数类型
        if user_id is None:
            return False
            
        user_id = int(user_id)
        
        current_time = time.time()
        
        # 初始化用户记录
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # 清理过期记录
        cutoff_time = current_time - self.time_window
        self.user_requests[user_id] = [
            (ts, count) for ts, count in self.user_requests[user_id]
            if ts > cutoff_time
        ]
        
        # 计算时间窗口内的请求总数
        total_requests = sum(count for _, count in self.user_requests[user_id])
        
        # 添加新的请求记录
        self.user_requests[user_id].append((current_time, 1))
        
        # 判断是否超过限制
        if total_requests + 1 > self.max_requests:
            # 拉黑用户
            expiry_time = current_time + (self.blacklist_duration * 60)
            self.blacklisted_users[user_id] = expiry_time
            self.save_data()
            return True  # 超过限制
            
        return False  # 未超过限制
    
    def cleanup_expired(self) -> None:
        """清理过期的拉黑和请求记录"""
        current_time = time.time()
        cutoff_time = current_time - self.time_window
        
        # 清理过期的拉黑记录
        expired_users = [
            user_id for user_id, expiry_time in self.blacklisted_users.items()
            if current_time > expiry_time
        ]
        
        for user_id in expired_users:
            del self.blacklisted_users[user_id]
            if user_id in self.notified_users:
                self.notified_users.remove(user_id)
        
        # 清理过期的请求记录
        for user_id in list(self.user_requests.keys()):
            self.user_requests[user_id] = [
                (ts, count) for ts, count in self.user_requests[user_id]
                if ts > cutoff_time
            ]
            
            # 如果用户没有活跃请求，删除记录
            if not self.user_requests[user_id]:
                del self.user_requests[user_id]
        
        if expired_users:
            self.save_data()
            logger.info(f"清理了 {len(expired_users)} 个过期的拉黑记录")

# 导出插件类，确保插件加载器能找到它
plugin_class = RateLimiter 

# 当直接运行此文件时的测试代码
if __name__ == "__main__":
    print("Rate Limiter Plugin - Test Mode")
    print("This plugin should be loaded by the plugin system, not run directly.") 