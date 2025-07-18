#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional, Union

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command, extract_command, is_at_bot

logger = logging.getLogger("LCHBot")

class UserItemManager(Plugin):
    """
    用户物品管理和专属头衔管理插件
    
    用户命令：
    - @机器人 /title list - 查看可用头衔列表
    - @机器人 /title set <头衔名> - 设置自己的专属头衔
    - @机器人 /title clear - 清除自己的专属头衔
    - @机器人 /title info - 查看自己的当前头衔信息
    
    管理员命令：
    - @机器人 /title add <名称> <积分> <描述> - 添加新头衔到商店
    - @机器人 /title del <名称> - 从商店删除头衔
    - @机器人 /title give <@用户> <头衔名> - 直接授予用户头衔
    - @机器人 /title admin <@用户> <头衔名> - 管理员强制设置用户头衔
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "UserItemManager"
        # 设置插件优先级
        self.priority = 30
        
        # 用户命令模式
        self.user_patterns = {
            'title_list': re.compile(r'^/title\s+list$'),
            'title_set': re.compile(r'^/title\s+set\s+(.+)$'),
            'title_clear': re.compile(r'^/title\s+clear$'),
            'title_info': re.compile(r'^/title\s+info$'),
        }
        
        # 管理员命令模式
        self.admin_patterns = {
            'title_add': re.compile(r'^/title\s+add\s+([^\s]+)\s+(\d+)\s+(.+)$'),
            'title_del': re.compile(r'^/title\s+del\s+([^\s]+)$'),
            'title_give': re.compile(r'^/title\s+give\s+\[CQ:at,qq=(\d+)(?:,name=.*?)?\]\s+(.+)$'),
            'title_admin': re.compile(r'^/title\s+admin\s+\[CQ:at,qq=(\d+)(?:,name=.*?)?\]\s+(.+)$'),
        }
        
        # 数据文件路径
        self.titles_data_file = "data/user_titles.json"
        # 头衔数据
        self.titles_data = self.load_titles_data()
        
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化")
        
    def load_titles_data(self) -> Dict[str, Any]:
        """加载头衔数据"""
        if not os.path.exists(self.titles_data_file):
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(self.titles_data_file), exist_ok=True)
            
            # 创建默认数据
            default_data = {
                "titles": {
                    "初级成员": {"points": 0, "description": "新人专属头衔"},
                    "活跃成员": {"points": 500, "description": "活跃的群组成员"},
                    "资深成员": {"points": 1000, "description": "在群内长期活跃的成员"},
                    "群内大佬": {"points": 2000, "description": "德高望重的群内成员"}
                },
                "users": {}  # 格式: {"群号": {"用户QQ": {"title": "头衔名", "set_time": 时间戳}}}
            }
            
            # 保存默认数据
            with open(self.titles_data_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
                
            return default_data
        
        try:
            with open(self.titles_data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"加载头衔数据失败: {e}")
            return {"titles": {}, "users": {}}
            
    def save_titles_data(self) -> None:
        """保存头衔数据"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.titles_data_file), exist_ok=True)
            
            with open(self.titles_data_file, 'w', encoding='utf-8') as f:
                json.dump(self.titles_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存头衔数据失败: {e}")
            
    def get_available_titles(self) -> Dict[str, Dict[str, Any]]:
        """获取可用的头衔列表"""
        return self.titles_data.get("titles", {})
        
    def get_user_title(self, group_id: str, user_id: str) -> Optional[str]:
        """获取用户当前的头衔"""
        return self.titles_data.get("users", {}).get(group_id, {}).get(user_id, {}).get("title")
        
    def set_user_title(self, group_id: str, user_id: str, title: str) -> bool:
        """设置用户头衔"""
        if title not in self.titles_data.get("titles", {}):
            return False
            
        # 确保数据结构存在
        if "users" not in self.titles_data:
            self.titles_data["users"] = {}
            
        if group_id not in self.titles_data["users"]:
            self.titles_data["users"][group_id] = {}
            
        # 设置头衔
        self.titles_data["users"][group_id][user_id] = {
            "title": title,
            "set_time": int(time.time())
        }
        
        self.save_titles_data()
        return True
        
    def clear_user_title(self, group_id: str, user_id: str) -> bool:
        """清除用户头衔"""
        if (group_id in self.titles_data.get("users", {}) and 
            user_id in self.titles_data["users"].get(group_id, {})):
            del self.titles_data["users"][group_id][user_id]
            self.save_titles_data()
            return True
        return False
        
    def add_title(self, title_name: str, points: int, description: str) -> bool:
        """添加新头衔"""
        if "titles" not in self.titles_data:
            self.titles_data["titles"] = {}
            
        self.titles_data["titles"][title_name] = {
            "points": points,
            "description": description
        }
        
        self.save_titles_data()
        return True
        
    def delete_title(self, title_name: str) -> bool:
        """删除头衔"""
        if title_name in self.titles_data.get("titles", {}):
            del self.titles_data["titles"][title_name]
            self.save_titles_data()
            return True
        return False
    
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否是管理员"""
        superusers = self.bot.config.get("bot", {}).get("superusers", [])
        return str(user_id) in superusers
        
    async def set_group_special_title(self, group_id: int, user_id: int, title: str) -> bool:
        """设置群成员专属头衔"""
        try:
            # 调用go-cqhttp的API
            response = await self.bot._call_api('set_group_special_title', {
                'group_id': group_id,
                'user_id': user_id,
                'special_title': title,
                'duration': -1  # 永久
            })
            
            if response.get("status") == "ok":
                logger.info(f"成功为用户 {user_id} 在群 {group_id} 设置头衔: {title}")
                return True
            else:
                logger.error(f"设置头衔失败: {response}")
                return False
        except Exception as e:
            logger.error(f"设置头衔时出错: {e}")
            return False
    
    async def check_bot_permission(self, group_id: int) -> bool:
        """检查机器人是否有管理员权限"""
        try:
            # 获取机器人自身QQ号
            bot_qq = int(self.bot.config.get("bot", {}).get("self_id", "0"))
            
            # 获取机器人在群内的角色
            response = await self.bot._call_api('get_group_member_info', {
                'group_id': group_id,
                'user_id': bot_qq
            })
            
            if response.get("status") == "ok" and response.get("data"):
                role = response.get("data", {}).get("role", "member")
                return role in ["admin", "owner"]
            
            return False
        except Exception as e:
            logger.error(f"检查机器人权限时出错: {e}")
            return False
    
    async def format_title_list(self) -> str:
        """格式化头衔列表信息"""
        titles = self.get_available_titles()
        
        if not titles:
            return "当前没有可用的头衔"
            
        result = ["🏆 可用头衔列表："]
        
        # 按积分要求排序
        sorted_titles = sorted(titles.items(), key=lambda x: x[1].get("points", 0))
        
        for title_name, title_info in sorted_titles:
            points = title_info.get("points", 0)
            description = title_info.get("description", "无描述")
            
            result.append(f"· {title_name} - {points}积分")
            result.append(f"  {description}")
            
        result.append("\n💡 使用 /title set <头衔名> 设置头衔")
        
        return "\n".join(result)
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id', 0)
        group_id = event.get('group_id') if message_type == 'group' else None
        message_id = event.get('message_id', 0)
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 只处理群消息
        if message_type != 'group' or not group_id:
            return False
            
        # 处理管理员命令
        if self.is_admin(int(user_id)):
            # 添加头衔命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['title_add'])
            if is_at_command and match:
                title_name = match.group(1)
                points = int(match.group(2))
                description = match.group(3)
                
                if self.add_title(title_name, points, description):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}✅ 成功添加头衔 \"{title_name}\"，需要{points}积分\n描述: {description}"
                    )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}❌ 添加头衔失败"
                    )
                return True
                
            # 删除头衔命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['title_del'])
            if is_at_command and match:
                title_name = match.group(1)
                
                if self.delete_title(title_name):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}✅ 成功删除头衔 \"{title_name}\""
                    )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}❌ 未找到头衔 \"{title_name}\""
                    )
                return True
                
            # 直接授予用户头衔命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['title_give'])
            if is_at_command and match:
                target_user_id = match.group(1)
                title_name = match.group(2)
                
                # 检查头衔是否存在
                if title_name not in self.get_available_titles():
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}❌ 未找到头衔 \"{title_name}\""
                    )
                    return True
                
                # 设置用户头衔数据
                self.set_user_title(str(group_id), target_user_id, title_name)
                
                # 检查机器人是否有管理员权限
                has_admin = await self.check_bot_permission(group_id)
                
                if has_admin:
                    # 尝试设置专属头衔
                    if await self.set_group_special_title(group_id, int(target_user_id), title_name):
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}✅ 成功为用户 {target_user_id} 设置头衔 \"{title_name}\"，并已自动更新群内显示"
                        )
                    else:
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}⚠️ 已为用户 {target_user_id} 记录头衔 \"{title_name}\"，但设置群内显示失败"
                        )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}⚠️ 已为用户 {target_user_id} 记录头衔 \"{title_name}\"，但机器人无管理权限，无法设置群内显示"
                    )
                return True
                
            # 管理员强制设置用户头衔
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['title_admin'])
            if is_at_command and match:
                target_user_id = match.group(1)
                special_title = match.group(2)
                
                # 检查机器人是否有管理员权限
                has_admin = await self.check_bot_permission(group_id)
                
                if has_admin:
                    # 直接设置专属头衔
                    if await self.set_group_special_title(group_id, int(target_user_id), special_title):
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}✅ 成功为用户 {target_user_id} 设置专属头衔 \"{special_title}\""
                        )
                    else:
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}❌ 设置专属头衔失败"
                        )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}❌ 机器人无管理权限，无法设置专属头衔"
                    )
                return True
        
        # 处理用户命令
        
        # 查看头衔列表命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['title_list'])
        if is_at_command and match:
            result = await self.format_title_list()
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}{result}"
            )
            return True
            
        # 设置头衔命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['title_set'])
        if is_at_command and match:
            title_name = match.group(1)
            titles = self.get_available_titles()
            
            # 检查头衔是否存在
            if title_name not in titles:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}❌ 未找到头衔 \"{title_name}\""
                )
                return True
                
            # 检查是否有足够积分
            title_points = titles[title_name].get("points", 0)
            
            # 获取用户积分 - 从SignPoints插件获取
            user_points = 0
            sign_points_plugin = self.bot.plugin_manager.get_plugin_by_name("SignPoints")
            if sign_points_plugin:
                user_points = sign_points_plugin.get_user_sign_info(str(group_id), str(user_id)).get("total_points", 0)
                
            if user_points < title_points:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}❌ 积分不足，需要{title_points}积分，您当前有{user_points}积分"
                )
                return True
                
            # 设置用户头衔数据
            self.set_user_title(str(group_id), str(user_id), title_name)
            
            # 检查机器人是否有管理员权限
            has_admin = await self.check_bot_permission(group_id)
            
            if has_admin:
                # 尝试设置专属头衔
                if await self.set_group_special_title(group_id, user_id, title_name):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}✅ 成功设置头衔 \"{title_name}\"，并已自动更新群内显示"
                    )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}⚠️ 已记录您的头衔 \"{title_name}\"，但设置群内显示失败"
                    )
            else:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}⚠️ 已记录您的头衔 \"{title_name}\"，但机器人无管理权限，无法设置群内显示"
                )
            return True
            
        # 清除头衔命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['title_clear'])
        if is_at_command and match:
            self.clear_user_title(str(group_id), str(user_id))
            
            # 检查机器人是否有管理员权限
            has_admin = await self.check_bot_permission(group_id)
            
            if has_admin:
                # 尝试清除专属头衔
                if await self.set_group_special_title(group_id, user_id, ""):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}✅ 成功清除头衔，并已自动更新群内显示"
                    )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}⚠️ 已清除您的头衔记录，但更新群内显示失败"
                    )
            else:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}⚠️ 已清除您的头衔记录，但机器人无管理权限，无法更新群内显示"
                )
            return True
            
        # 查看头衔信息命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['title_info'])
        if is_at_command and match:
            current_title = self.get_user_title(str(group_id), str(user_id))
            
            if not current_title:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}您当前没有设置头衔"
                )
            else:
                title_info = self.get_available_titles().get(current_title, {})
                description = title_info.get("description", "无描述")
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}您当前的头衔：{current_title}\n描述：{description}"
                )
            return True
            
        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = UserItemManager 