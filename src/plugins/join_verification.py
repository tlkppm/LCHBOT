#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import time
import asyncio
import json
import os
import sys
from typing import Dict, Any, List, Set, Optional
from datetime import datetime, timedelta

# 添加项目根目录到系统路径，以便正确导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 导入Plugin基类和工具函数
from plugin_system import Plugin

logger = logging.getLogger("LCHBot")

class JoinVerification(Plugin):
    """
    进群验证插件
    功能：新用户进群后必须在指定时间内发言，否则踢出
    这是一个按群组单独生效的插件，每个群组可以单独配置
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        # 从配置文件加载设置
        self.config = self.bot.config.get("join_verification", {})
        # 默认等待时间（分钟）
        self.default_wait_time = self.config.get("default_wait_time", 5)
        # 是否启用功能
        self.enabled = self.config.get("enabled", True)
        # 验证消息
        self.verification_message = self.config.get("verification_message", 
            "欢迎新成员加入！请在{time}分钟内发送任意消息，否则将被移出群聊。")
        # 白名单群聊
        self.whitelist_groups = set(self.config.get("whitelist_groups", []))
        # 白名单用户（不需要验证的用户，比如机器人）
        self.whitelist_users = set(self.config.get("whitelist_users", []))
        # 添加Q群管家到白名单
        self.whitelist_users.add(2854196310)  # Q群管家QQ号
        # 添加机器人自己到白名单
        bot_qq = int(self.bot.config.get("bot", {}).get("self_id", "0"))
        if bot_qq > 0:
            self.whitelist_users.add(bot_qq)
            logger.info(f"将机器人自己(QQ:{bot_qq})添加到进群验证白名单")
        
        # 保存等待验证的用户
        # 格式: {group_id: {user_id: expiry_time}}
        self.pending_users: Dict[int, Dict[int, float]] = {}
        
        # 保存群管理员列表
        # 格式: {group_id: [admin_id1, admin_id2, ...]}
        self.group_admins: Dict[int, List[int]] = {}
        
        # 持久化数据文件
        self.data_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                    "data", "join_verification.json")
        
        # 创建数据目录（如果不存在）
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        
        # 加载数据
        self.load_data()
        
        # 启动清理过期用户的任务
        asyncio.create_task(self.cleanup_expired_users())
        
        logger.info(f"进群验证插件已初始化，按群组单独生效模式")
    
    def save_data(self) -> None:
        """保存数据到文件"""
        data = {
            "pending_users": {
                str(group_id): {str(user_id): expiry_time 
                               for user_id, expiry_time in users.items()}
                for group_id, users in self.pending_users.items()
            },
            "group_admins": {
                str(group_id): admins for group_id, admins in self.group_admins.items()
            }
        }
        
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"保存进群验证数据失败: {e}", exc_info=True)
    
    def load_data(self) -> None:
        """从文件加载数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 加载等待验证的用户
                    pending_users = data.get("pending_users", {})
                    self.pending_users = {
                        int(group_id): {int(user_id): expiry_time 
                                      for user_id, expiry_time in users.items()}
                        for group_id, users in pending_users.items()
                    }
                    
                    # 加载群管理员
                    group_admins = data.get("group_admins", {})
                    self.group_admins = {
                        int(group_id): admins for group_id, admins in group_admins.items()
                    }
                    
                    logger.info(f"加载进群验证数据: {len(self.pending_users)} 个群, {sum(len(users) for users in self.pending_users.values())} 个待验证用户")
        except Exception as e:
            logger.error(f"加载进群验证数据失败: {e}", exc_info=True)
            self.pending_users = {}
            self.group_admins = {}
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        from plugins.utils import extract_command, is_at_bot
        
        # 判断是否是群消息
        if event.get('message_type') != 'group':
            return False
        
        user_id = event.get('user_id')
        group_id = event.get('group_id')
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 确保user_id和group_id是整数类型
        if user_id is None or group_id is None:
            return False
            
        user_id = int(user_id)
        group_id = int(group_id)
        
        # 获取原始消息
        message = event.get('raw_message', '')
        
        # 如果消息中有@机器人，处理管理员命令
        is_admin = await self.is_admin(group_id, user_id)
        if '[CQ:at,qq=' in message:
            bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
            if is_at_bot(event, bot_qq) and is_admin and self.is_admin_command(event):
                return await self.handle_admin_command(event)
        
        # 处理用户验证
        if self.is_user_pending(group_id, user_id):
            # 用户已经发言，从待验证列表移除
            self.remove_pending_user(group_id, user_id)
            logger.info(f"用户 {user_id} 在群 {group_id} 验证成功")
            
            # 使用回复方式通知用户验证成功
            reply_code = f"[CQ:reply,id={message_id}]"
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"{reply_code}验证成功，欢迎加入！"
            )
            
            return True  # 已处理此消息
        
        return False  # 未处理此消息
    
    async def handle_notice(self, event: Dict[str, Any]) -> bool:
        """处理通知事件"""
        notice_type = event.get('notice_type')
        
        # 处理群成员变动事件
        if notice_type == 'group_increase':
            return await self.handle_group_increase(event)
        
        # 处理管理员变动事件
        if notice_type == 'group_admin':
            await self.handle_group_admin(event)
            return True
        
        return False
    
    async def handle_group_increase(self, event: Dict[str, Any]) -> bool:
        """处理群成员增加事件"""
        group_id = event.get('group_id')
        user_id = event.get('user_id')
        
        # 确保user_id和group_id是整数类型
        if user_id is None or group_id is None:
            return False
            
        group_id = int(group_id)
        user_id = int(user_id)
        
        # 检查是否是机器人自己进群
        bot_qq = int(self.bot.config.get("bot", {}).get("self_id", "0"))
        if user_id == bot_qq:
            logger.info(f"机器人自己(QQ:{bot_qq})加入群 {group_id}，不需要验证")
            return False
        
        # 检查群是否在白名单中
        if group_id in self.whitelist_groups:
            logger.info(f"群 {group_id} 在白名单中，不需要验证")
            return False
        
        # 检查用户是否在白名单中
        if user_id in self.whitelist_users:
            logger.info(f"用户 {user_id} 在白名单中，不需要验证")
            return False
        
        # 如果功能未启用，直接返回
        if not self.enabled:
            return False
            
        # 检查机器人在群内的权限
        try:
            bot_info = await self.bot._call_api("/get_group_member_info", {
                "group_id": group_id,
                "user_id": bot_qq,
                "no_cache": True
            })
            
            if bot_info.get("status") == "ok" and bot_info.get("data"):
                bot_role = bot_info.get("data", {}).get("role", "member")
                
                # 如果机器人不是管理员或群主，则不进行验证
                if bot_role not in ["admin", "owner"]:
                    logger.info(f"机器人在群 {group_id} 没有管理员权限，不进行验证")
                    return False
        except Exception as e:
            logger.error(f"获取机器人在群 {group_id} 的权限失败: {e}")
        
        # 添加到待验证列表
        wait_time = self.default_wait_time * 60  # 转换为秒
        expiry_time = time.time() + wait_time
        self.add_pending_user(group_id, user_id, expiry_time)
        
        # 发送验证消息
        verification_msg = self.verification_message.format(time=self.default_wait_time)
        await self.bot.send_msg(
            message_type='group',
            group_id=group_id,
            message=f"[CQ:at,qq={user_id}] {verification_msg}"
        )
        
        logger.info(f"用户 {user_id} 加入群 {group_id}，已添加到验证队列，等待时间: {self.default_wait_time} 分钟")
        
        # 保存数据
        self.save_data()
        
        # 启动定时检查任务
        asyncio.create_task(self.check_user_timeout(group_id, user_id, expiry_time))
        
        return True
    
    async def handle_group_admin(self, event: Dict[str, Any]) -> None:
        """处理群管理员变动事件"""
        group_id = event.get('group_id')
        user_id = event.get('user_id')
        sub_type = event.get('sub_type')  # set/unset
        
        # 确保user_id和group_id是整数类型
        if user_id is None or group_id is None:
            return
            
        group_id = int(group_id)
        user_id = int(user_id)
        
        if group_id not in self.group_admins:
            self.group_admins[group_id] = []
            
        if sub_type == 'set':
            # 添加管理员
            if user_id not in self.group_admins[group_id]:
                self.group_admins[group_id].append(user_id)
                logger.info(f"用户 {user_id} 成为群 {group_id} 的管理员")
        elif sub_type == 'unset':
            # 移除管理员
            if user_id in self.group_admins[group_id]:
                self.group_admins[group_id].remove(user_id)
                logger.info(f"用户 {user_id} 不再是群 {group_id} 的管理员")
        
        # 保存数据
        self.save_data()
    
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
                
                # 检查是否是设置验证时间的命令
                if re.match(r'^/verify\s+set\s+time\s+\d+$', message):
                    return True
                    
                # 检查是否是启用/禁用验证的命令
                if re.match(r'^/verify\s+(enable|disable)$', message):
                    return True
                
                # 检查是否是设置验证消息的命令
                if re.match(r'^/verify\s+set\s+message\s+.+$', message):
                    return True
                
                # 检查是否是添加/移除白名单的命令
                if re.match(r'^/verify\s+(add|remove)\s+whitelist\s+(group|user)\s+\d+$', message):
                    return True
                
                # 检查是否是列出设置的命令
                if message == '/verify settings':
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
        
        # 检查是否是超级用户或群管理员
        is_admin = await self.is_admin(group_id, user_id)
        if not is_admin:
            return False
            
        # 设置验证时间
        time_match = re.match(r'^/verify\s+set\s+time\s+(\d+)$', message)
        if time_match:
            wait_time = int(time_match.group(1))
            if wait_time > 0 and wait_time <= 60:  # 限制在1-60分钟
                self.default_wait_time = wait_time
                # 更新配置
                if "join_verification" not in self.bot.config:
                    self.bot.config["join_verification"] = {}
                self.bot.config["join_verification"]["default_wait_time"] = wait_time
                self.bot.save_config()
                
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"已设置验证等待时间为 {wait_time} 分钟"
                )
                logger.info(f"管理员 {user_id} 设置群 {group_id} 的验证等待时间为 {wait_time} 分钟")
            else:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"等待时间必须在1-60分钟之间"
                )
            return True
        
        # 启用/禁用验证
        enable_match = re.match(r'^/verify\s+(enable|disable)$', message)
        if enable_match:
            enable = enable_match.group(1) == 'enable'
            self.enabled = enable
            # 更新配置
            if "join_verification" not in self.bot.config:
                self.bot.config["join_verification"] = {}
            self.bot.config["join_verification"]["enabled"] = enable
            self.bot.save_config()
            
            status = "启用" if enable else "禁用"
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"已{status}进群验证功能"
            )
            logger.info(f"管理员 {user_id} {status}了群 {group_id} 的进群验证功能")
            return True
        
        # 设置验证消息
        message_match = re.match(r'^/verify\s+set\s+message\s+(.+)$', message)
        if message_match:
            new_message = message_match.group(1)
            if '{time}' in new_message:
                self.verification_message = new_message
                # 更新配置
                if "join_verification" not in self.bot.config:
                    self.bot.config["join_verification"] = {}
                self.bot.config["join_verification"]["verification_message"] = new_message
                self.bot.save_config()
                
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"已设置验证消息为:\n{new_message}"
                )
                logger.info(f"管理员 {user_id} 设置群 {group_id} 的验证消息")
            else:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message="验证消息必须包含 {time} 占位符"
                )
            return True
        
        # 添加/移除白名单
        whitelist_match = re.match(r'^/verify\s+(add|remove)\s+whitelist\s+(group|user)\s+(\d+)$', message)
        if whitelist_match:
            action = whitelist_match.group(1)  # add/remove
            wl_type = whitelist_match.group(2)  # group/user
            wl_id = int(whitelist_match.group(3))
            
            if wl_type == 'group':
                whitelist = self.whitelist_groups
                type_name = "群"
            else:  # user
                whitelist = self.whitelist_users
                type_name = "用户"
            
            if action == 'add':
                whitelist.add(wl_id)
                action_name = "添加到"
            else:  # remove
                if wl_id in whitelist:
                    whitelist.remove(wl_id)
                action_name = "从"
            
            # 更新配置
            if "join_verification" not in self.bot.config:
                self.bot.config["join_verification"] = {}
            
            self.bot.config["join_verification"]["whitelist_groups"] = list(self.whitelist_groups)
            self.bot.config["join_verification"]["whitelist_users"] = list(self.whitelist_users)
            self.bot.save_config()
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"已{action_name}白名单移除{type_name} {wl_id}"
            )
            logger.info(f"管理员 {user_id} {action_name}白名单移除{type_name} {wl_id}")
            return True
        
        # 列出设置
        if message == '/verify settings':
            settings = f"""进群验证设置:
- 功能状态: {'启用' if self.enabled else '禁用'}
- 验证等待时间: {self.default_wait_time} 分钟
- 验证消息: {self.verification_message}
- 白名单群数量: {len(self.whitelist_groups)}
- 白名单用户数量: {len(self.whitelist_users)}
- 当前待验证用户: {sum(len(users) for users in self.pending_users.values())}"""
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=settings
            )
            return True
        
        return False
    
    def add_pending_user(self, group_id: int, user_id: int, expiry_time: float) -> None:
        """添加待验证用户"""
        # 确保group_id和user_id是整数类型
        if group_id is None or user_id is None:
            return
            
        group_id = int(group_id)
        user_id = int(user_id)
        
        if group_id not in self.pending_users:
            self.pending_users[group_id] = {}
        
        self.pending_users[group_id][user_id] = expiry_time
    
    def remove_pending_user(self, group_id: int, user_id: int) -> None:
        """移除待验证用户"""
        # 确保group_id和user_id是整数类型
        if group_id is None or user_id is None:
            return
            
        group_id = int(group_id)
        user_id = int(user_id)
        
        if group_id in self.pending_users and user_id in self.pending_users[group_id]:
            del self.pending_users[group_id][user_id]
            # 如果群里没有待验证用户了，删除这个群的记录
            if not self.pending_users[group_id]:
                del self.pending_users[group_id]
            # 保存数据
            self.save_data()
    
    def is_user_pending(self, group_id: int, user_id: int) -> bool:
        """检查用户是否在待验证列表中"""
        # 确保group_id和user_id是整数类型
        if group_id is None or user_id is None:
            return False
            
        group_id = int(group_id)
        user_id = int(user_id)
        
        return group_id in self.pending_users and user_id in self.pending_users[group_id]
    
    async def check_user_timeout(self, group_id: int, user_id: int, expiry_time: float) -> None:
        """检查用户是否超时未验证"""
        # 确保group_id和user_id是整数类型
        if group_id is None or user_id is None:
            return
            
        group_id = int(group_id)
        user_id = int(user_id)
        
        # 等待直到过期时间
        wait_time = expiry_time - time.time()
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # 再次检查用户是否还在等待验证
        if self.is_user_pending(group_id, user_id):
            # 检查机器人是否有踢人的权限
            bot_qq = int(self.bot.config.get("bot", {}).get("self_id", "0"))
            has_permission = False
            
            try:
                bot_info = await self.bot._call_api("/get_group_member_info", {
                    "group_id": group_id,
                    "user_id": bot_qq,
                    "no_cache": True
                })
                
                if bot_info.get("status") == "ok" and bot_info.get("data"):
                    bot_role = bot_info.get("data", {}).get("role", "member")
                    has_permission = bot_role in ["admin", "owner"]
                    
                if not has_permission:
                    logger.warning(f"机器人在群 {group_id} 没有管理员权限，无法踢出用户 {user_id}")
                    # 从待验证列表移除
                    self.remove_pending_user(group_id, user_id)
                    return
            except Exception as e:
                logger.error(f"获取机器人权限失败: {e}")
                # 从待验证列表移除
                self.remove_pending_user(group_id, user_id)
                return
            
            # 用户超时未验证，踢出群聊
            try:
                await self.bot.set_group_kick(
                    group_id=group_id,
                    user_id=user_id,
                    reject_add_request=False  # 允许再次申请加群
                )
                logger.info(f"用户 {user_id} 在群 {group_id} 验证超时，已踢出")
                
                # 发送提示消息
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"用户 {user_id} 验证超时，已被移出群聊"
                )
            except Exception as e:
                logger.error(f"踢出用户 {user_id} 失败: {e}", exc_info=True)
            
            # 从待验证列表移除
            self.remove_pending_user(group_id, user_id)
    
    async def cleanup_expired_users(self) -> None:
        """定期清理过期的待验证用户"""
        while True:
            try:
                current_time = time.time()
                groups_to_check = list(self.pending_users.keys())
                
                for group_id in groups_to_check:
                    if group_id not in self.pending_users:
                        continue
                    
                    # 检查机器人是否有踢人的权限
                    bot_qq = int(self.bot.config.get("bot", {}).get("self_id", "0"))
                    has_permission = False
                    
                    try:
                        bot_info = await self.bot._call_api("/get_group_member_info", {
                            "group_id": group_id,
                            "user_id": bot_qq,
                            "no_cache": True
                        })
                        
                        if bot_info.get("status") == "ok" and bot_info.get("data"):
                            bot_role = bot_info.get("data", {}).get("role", "member")
                            has_permission = bot_role in ["admin", "owner"]
                    except Exception as e:
                        logger.error(f"获取机器人在群 {group_id} 的权限失败: {e}")
                        has_permission = False
                        
                    users = list(self.pending_users[group_id].items())
                    for user_id, expiry_time in users:
                        if current_time > expiry_time:
                            # 用户已超时
                            if has_permission:
                                try:
                                    await self.bot.set_group_kick(
                                        group_id=group_id,
                                        user_id=user_id,
                                        reject_add_request=False
                                    )
                                    logger.info(f"定时清理: 用户 {user_id} 在群 {group_id} 验证超时，已踢出")
                                    
                                    # 发送提示消息
                                    await self.bot.send_msg(
                                        message_type='group',
                                        group_id=group_id,
                                        message=f"用户 {user_id} 验证超时，已被移出群聊"
                                    )
                                except Exception as e:
                                    logger.error(f"定时清理: 踢出用户 {user_id} 失败: {e}", exc_info=True)
                            else:
                                logger.warning(f"定时清理: 机器人在群 {group_id} 没有管理员权限，无法踢出用户 {user_id}")
                            
                            # 从待验证列表移除
                            self.remove_pending_user(group_id, user_id)
            except Exception as e:
                logger.error(f"清理过期用户出错: {e}", exc_info=True)
            
            # 每分钟检查一次
            await asyncio.sleep(60)
    
    async def is_admin(self, group_id: int, user_id: int) -> bool:
        """检查用户是否是管理员"""
        # 检查是否是超级用户
        if str(user_id) in self.bot.config.get("bot", {}).get("superusers", []):
            return True
        
        # 检查本地缓存
        if group_id in self.group_admins and user_id in self.group_admins[group_id]:
            return True
        
        # 通过API检查
        try:
            info = await self.bot.get_group_member_info(
                group_id=group_id,
                user_id=user_id
            )
            role = info.get("role", "")
            is_admin = role in ["owner", "admin"]
            
            # 更新缓存
            if is_admin:
                if group_id not in self.group_admins:
                    self.group_admins[group_id] = []
                if user_id not in self.group_admins[group_id]:
                    self.group_admins[group_id].append(user_id)
                    self.save_data()
            
            return is_admin
        except Exception as e:
            logger.error(f"检查用户 {user_id} 是否是群 {group_id} 管理员失败: {e}")
            return False

# 导出插件类，确保插件加载器能找到它
plugin_class = JoinVerification

# 当直接运行此文件时的测试代码
if __name__ == "__main__":
    print("Join Verification Plugin - Test Mode")
    print("This plugin should be loaded by the plugin system, not run directly.") 