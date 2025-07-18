#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Set

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command, extract_command, is_at_bot

logger = logging.getLogger("LCHBot")

class Blacklist(Plugin):
    """
    全局黑名单插件：管理禁止使用机器人的用户
    
    管理员命令：
    - @机器人 /blacklist add <@用户|QQ号> [原因] - 将用户添加到全局黑名单
    - @机器人 /blacklist remove <@用户|QQ号> - 将用户从全局黑名单中移除
    - @机器人 /blacklist list - 查看全局黑名单列表
    - @机器人 /blacklist check <@用户|QQ号> - 检查用户是否在黑名单中
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "Blacklist"
        # 设置插件优先级为最高，确保在其他插件前运行
        self.priority = 110  # 比GroupAuth还高
        
        # 命令模式
        self.admin_patterns = {
            'add_blacklist': re.compile(r'^/blacklist\s+add\s+(?:\[CQ:at,qq=(\d+)[^\]]*\]|(\d+))(?:\s+(.+))?$'),
            'remove_blacklist': re.compile(r'^/blacklist\s+remove\s+(?:\[CQ:at,qq=(\d+)[^\]]*\]|(\d+))$'),
            'list_blacklist': re.compile(r'^/blacklist\s+list$'),
            'check_blacklist': re.compile(r'^/blacklist\s+check\s+(?:\[CQ:at,qq=(\d+)[^\]]*\]|(\d+))$'),
        }
        
        # 数据文件路径
        self.blacklist_file = "data/global_blacklist.json"
        
        # 黑名单数据结构：{
        #   "users": {
        #     "QQ号": {
        #       "added_by": "管理员QQ号",
        #       "added_time": 添加时间戳,
        #       "reason": "原因"
        #     }
        #   }
        # }
        self.blacklist_data = self.load_blacklist_data()
        
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化")
        
    def load_blacklist_data(self) -> Dict[str, Any]:
        """加载黑名单数据"""
        if not os.path.exists(self.blacklist_file):
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(self.blacklist_file), exist_ok=True)
            # 创建默认黑名单数据
            default_data = {"users": {}}
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            return default_data
        
        try:
            with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"加载黑名单数据失败: {e}")
            return {"users": {}}
            
    def save_blacklist_data(self) -> None:
        """保存黑名单数据"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.blacklist_file), exist_ok=True)
            
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                json.dump(self.blacklist_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存黑名单数据失败: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否是管理员"""
        superusers = self.bot.config.get("bot", {}).get("superusers", [])
        return str(user_id) in superusers
        
    def is_blacklisted(self, user_id: str) -> bool:
        """检查用户是否在黑名单中"""
        return user_id in self.blacklist_data.get("users", {})
        
    def add_to_blacklist(self, user_id: str, admin_id: str, reason: Optional[str] = None) -> bool:
        """添加用户到黑名单"""
        if "users" not in self.blacklist_data:
            self.blacklist_data["users"] = {}
            
        if user_id in self.blacklist_data["users"]:
            # 更新已存在的黑名单记录
            self.blacklist_data["users"][user_id].update({
                "added_by": admin_id,
                "added_time": int(time.time()),
                "reason": reason or self.blacklist_data["users"][user_id].get("reason", "未提供原因")
            })
        else:
            # 创建新的黑名单记录
            self.blacklist_data["users"][user_id] = {
                "added_by": admin_id,
                "added_time": int(time.time()),
                "reason": reason or "未提供原因"
            }
            
        self.save_blacklist_data()
        return True
        
    def remove_from_blacklist(self, user_id: str) -> bool:
        """从黑名单移除用户"""
        if user_id in self.blacklist_data.get("users", {}):
            del self.blacklist_data["users"][user_id]
            self.save_blacklist_data()
            return True
        return False
        
    def get_blacklist_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取黑名单中用户的信息"""
        return self.blacklist_data.get("users", {}).get(user_id)
        
    def format_blacklist_info(self, user_id: str) -> str:
        """格式化黑名单信息"""
        info = self.get_blacklist_info(user_id)
        if not info:
            return f"用户 {user_id} 不在黑名单中"
            
        # 格式化添加时间
        added_time_str = datetime.fromtimestamp(info.get("added_time", 0)).strftime("%Y-%m-%d %H:%M:%S")
        
        return (f"用户 {user_id} 的黑名单信息:\n"
                f"- 添加者: {info.get('added_by', '未知')}\n"
                f"- 添加时间: {added_time_str}\n"
                f"- 原因: {info.get('reason', '未提供原因')}")
                
    def format_blacklist(self) -> str:
        """格式化黑名单列表"""
        if not self.blacklist_data.get("users"):
            return "黑名单为空"
            
        lines = ["📋 全局黑名单列表:"]
        
        # 为了方便阅读，按添加时间排序
        sorted_users = sorted(
            self.blacklist_data["users"].items(),
            key=lambda x: x[1].get("added_time", 0),
            reverse=True  # 最近添加的排在前面
        )
        
        for user_id, info in sorted_users:
            added_time_str = datetime.fromtimestamp(info.get("added_time", 0)).strftime("%Y-%m-%d %H:%M:%S")
            reason = info.get("reason", "未提供原因")
            lines.append(f"- QQ: {user_id}, 时间: {added_time_str}, 原因: {reason}")
            
        return "\n".join(lines)
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id', 0)
        group_id = event.get('group_id') if message_type == 'group' else None
        message_id = event.get('message_id', 0)
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 优先检查发送者是否在黑名单中
        if self.is_blacklisted(str(user_id)):
            # 如果是在群聊中，有一定概率回复（避免刷屏）
            if message_type == 'group' and is_at_bot(event, self.bot):
                # 获取黑名单信息
                info = self.get_blacklist_info(str(user_id))
                reason = info.get("reason", "未提供原因") if info else "未知原因"
                
                await self.bot.send_msg(
                    message_type=message_type,
                    group_id=group_id,
                    message=f"{reply_code}您已被列入机器人全局黑名单，无法使用任何功能。\n原因：{reason}\n如有疑问请联系管理员。"
                )
                
            # 拦截消息，不让其他插件处理
            return True
            
        # 只有管理员可以使用黑名单管理命令
        if not self.is_admin(user_id):
            return False
            
        # 添加黑名单命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['add_blacklist'])
        if is_at_command and match:
            target_id = match.group(1) or match.group(2)  # 第一个组是@方式，第二个组是直接QQ号
            reason = match.group(3) or "未提供原因"
            
            # 不能将管理员添加到黑名单
            if self.is_admin(int(target_id)):
                await self.bot.send_msg(
                    message_type=message_type,
                    group_id=group_id,
                    message=f"{reply_code}❌ 无法将管理员添加到黑名单"
                )
                return True
            
            # 添加到黑名单
            self.add_to_blacklist(target_id, str(user_id), reason)
            
            await self.bot.send_msg(
                message_type=message_type,
                group_id=group_id,
                message=f"{reply_code}✅ 已将用户 {target_id} 添加到全局黑名单\n原因: {reason}"
            )
            return True
            
        # 移除黑名单命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['remove_blacklist'])
        if is_at_command and match:
            target_id = match.group(1) or match.group(2)
            
            # 从黑名单移除
            if self.remove_from_blacklist(target_id):
                await self.bot.send_msg(
                    message_type=message_type,
                    group_id=group_id,
                    message=f"{reply_code}✅ 已将用户 {target_id} 从全局黑名单中移除"
                )
            else:
                await self.bot.send_msg(
                    message_type=message_type,
                    group_id=group_id,
                    message=f"{reply_code}❌ 用户 {target_id} 不在黑名单中"
                )
            return True
            
        # 列出黑名单命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['list_blacklist'])
        if is_at_command and match:
            blacklist_str = self.format_blacklist()
            
            await self.bot.send_msg(
                message_type=message_type,
                group_id=group_id,
                message=f"{reply_code}{blacklist_str}"
            )
            return True
            
        # 检查黑名单命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['check_blacklist'])
        if is_at_command and match:
            target_id = match.group(1) or match.group(2)
            info_str = self.format_blacklist_info(target_id)
            
            await self.bot.send_msg(
                message_type=message_type,
                group_id=group_id,
                message=f"{reply_code}{info_str}"
            )
            return True
            
        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = Blacklist 