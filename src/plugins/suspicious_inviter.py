#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Set, Optional

# 导入Plugin基类
import os
import sys
# 添加项目根目录到系统路径，以便正确导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.plugin_system import Plugin
from src.plugins.utils import handle_at_command, extract_command, is_at_bot

logger = logging.getLogger("LCHBot")

class SuspiciousInviter(Plugin):
    """
    可疑邀请者检测插件
    功能：检测加入群后不发言但邀请大量成员的可疑用户，并将其踢出
    支持按群组单独配置
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "SuspiciousInviter"
        
        # 可疑邀请者检测机制说明：
        # 1. 当用户加入群聊后，系统开始监控其邀请行为
        # 2. 如果用户在监控时间（默认3分钟）内邀请超过设定阈值（默认3人）的成员，则被视为可疑
        # 3. 即使用户发言，只要在监控时间内邀请人数超过阈值，也会被踢出
        # 4. 系统会自动排除管理员、群主和长期群成员（默认超过30天）
        # 5. 白名单中的用户和群组不受此插件影响
        
        # 命令模式
        self.command_patterns = {
            'enable': re.compile(r'^/suspicious\s+enable$'),    # 启用插件
            'disable': re.compile(r'^/suspicious\s+disable$'),  # 禁用插件
            'status': re.compile(r'^/suspicious\s+status$'),    # 查看状态
            'config': re.compile(r'^/suspicious\s+config\s+(\w+)\s+(.+)$'),  # 配置参数
            'global': re.compile(r'^/suspicious\s+global\s+(\w+)\s+(.+)$')   # 全局配置参数
        }
        
        # 数据文件路径
        self.data_dir = "data"
        self.data_file = os.path.join(self.data_dir, "suspicious_inviter.json")
        
        # 默认全局配置
        self.default_global_config = {
            "enabled": False,              # 默认全局禁用
            "monitor_time": 3,             # 监控时间（分钟）
            "max_invites": 3,              # 最大邀请人数
            "whitelist_groups": [],        # 白名单群组
            "whitelist_users": [2854196310],  # 白名单用户（默认包含Q群管家）
            "reject_add_request": True,    # 踢出时是否拒绝再次加群请求
        }
        
        # 默认群组配置
        self.default_group_config = {
            "enabled": True,               # 默认启用
            "monitor_time": 3,             # 监控时间（分钟）
            "max_invites": 3,              # 最大邀请人数
            "reject_add_request": True,    # 踢出时是否拒绝再次加群请求
        }
        
        # 加载配置
        self.config = self.load_config()
        
        # 跟踪数据
        # 格式: {group_id: {user_id: {"join_time": timestamp, "has_spoken": bool, "invite_count": int}}}
        self.user_data = {}
        
        # 跟踪最近踢出的用户，避免重复发送警告
        # 格式: {group_id: {user_id: {"last_kicked": timestamp, "invited_users": []}}}
        self.recent_kicks = {}
        
        # 设置插件优先级为较高级别，确保能在关键事件后被处理
        self.priority = 10
        
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化，全局状态: {'启用' if self.config['global']['enabled'] else '禁用'}, 优先级: {self.priority}")
        logger.info(f"可疑邀请者检测配置: 监控时间={self.config['global']['monitor_time']}分钟, 最大邀请数={self.config['global']['max_invites']}人, 按群组单独配置")
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置"""
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 初始化配置结构
        config = {
            "global": self.default_global_config.copy(),
            "groups": {}  # 格式: {group_id: {配置项}}
        }
        
        # 如果文件不存在，创建默认配置
        if not os.path.exists(self.data_file):
            self.save_config(config)
            return config
        
        # 读取配置文件
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
                
                # 确保全局配置包含所有默认配置项
                if "global" not in loaded_config:
                    loaded_config["global"] = self.default_global_config.copy()
                else:
                    for key, value in self.default_global_config.items():
                        if key not in loaded_config["global"]:
                            loaded_config["global"][key] = value
                
                # 确保groups键存在
                if "groups" not in loaded_config:
                    loaded_config["groups"] = {}
                
                return loaded_config
        except Exception as e:
            logger.error(f"加载可疑邀请者配置失败: {e}")
            return config
    
    def save_config(self, config: Optional[Dict[str, Any]] = None) -> None:
        """保存配置"""
        if config is None:
            config = self.config
        
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存可疑邀请者配置失败: {e}")
    
    def get_group_config(self, group_id: int) -> Dict[str, Any]:
        """获取群组配置，如果不存在则使用默认配置"""
        str_group_id = str(group_id)
        if str_group_id not in self.config["groups"]:
            # 从全局配置继承部分可自定义的设置
            group_config = self.default_group_config.copy()
            group_config["monitor_time"] = self.config["global"]["monitor_time"]
            group_config["max_invites"] = self.config["global"]["max_invites"]
            group_config["reject_add_request"] = self.config["global"]["reject_add_request"]
            self.config["groups"][str_group_id] = group_config
            self.save_config()
        
        return self.config["groups"][str_group_id]
    
    def update_group_config(self, group_id: int, key: str, value: Any) -> bool:
        """更新群组配置"""
        str_group_id = str(group_id)
        group_config = self.get_group_config(group_id)
        
        if key not in group_config:
            return False
        
        group_config[key] = value
        self.config["groups"][str_group_id] = group_config
        self.save_config()
        return True
    
    def update_global_config(self, key: str, value: Any) -> bool:
        """更新全局配置"""
        if key not in self.config["global"]:
            return False
        
        self.config["global"][key] = value
        self.save_config()
        return True
    
    def is_group_in_whitelist(self, group_id: int) -> bool:
        """检查群是否在白名单中"""
        return group_id in self.config["global"].get("whitelist_groups", [])
    
    def is_user_in_whitelist(self, user_id: int) -> bool:
        """检查用户是否在白名单中"""
        return user_id in self.config["global"].get("whitelist_users", [])
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 只处理群消息
        if message_type != 'group' or not group_id or not user_id:
            return False
            
        # 转为整数
        user_id = int(user_id)
        group_id = int(group_id)
        
        # 处理管理员命令
        if await self._check_and_handle_admin_command(event, group_id, user_id):
            return True
            
        # 获取群组配置
        group_config = self.get_group_config(group_id)
            
        # 如果插件在此群被禁用，不处理
        if not group_config.get("enabled", True) and not self.config["global"].get("enabled", True):
            return False
            
        # 如果群在白名单中，不处理
        if self.is_group_in_whitelist(group_id):
            return False
            
        # 如果用户在白名单中，不处理
        if self.is_user_in_whitelist(user_id):
            return False
            
        # 记录用户发言
        if group_id in self.user_data and user_id in self.user_data[group_id]:
            self.user_data[group_id][user_id]["has_spoken"] = True
            
        return False
    
    async def handle_notice(self, event: Dict[str, Any]) -> bool:
        """处理通知事件"""
        notice_type = event.get('notice_type')
        sub_type = event.get('sub_type', '')
        
        # 调试日志
        logger.debug(f"可疑邀请者检测插件收到通知事件: {event}")
        
        # 获取群ID
        group_id = event.get('group_id')
        if not group_id:
            # 尝试从templParam中获取群ID
            if 'templParam' in event and isinstance(event.get('templParam'), dict):
                templ_param = event.get('templParam', {})
                if 'group_id' in templ_param:
                    group_id = templ_param.get('group_id')
                    logger.debug(f"从templParam中提取到群ID: {group_id}")
            
            # 如果还是没有群ID，则不处理
            if not group_id:
                logger.debug("事件中未找到群ID，不处理")
                return False
        
        try:
            group_id = int(group_id)
        except (ValueError, TypeError):
            logger.warning(f"无效的群ID: {group_id}")
            return False
        
        # 获取群组配置
        group_config = self.get_group_config(group_id)
        
        # 如果插件在此群被禁用，不处理通知
        global_enabled = self.config["global"].get("enabled", False)
        group_enabled = group_config.get("enabled", True)
        if not global_enabled and not group_enabled:
            logger.debug(f"插件在群 {group_id} 被禁用 (全局状态: {'启用' if global_enabled else '禁用'}, 群组状态: {'启用' if group_enabled else '禁用'})")
            return False
            
        # 如果群在白名单中，不处理
        if self.is_group_in_whitelist(group_id):
            logger.debug(f"群 {group_id} 在白名单中，不处理通知")
            return False
        
        # 处理明确的邀请事件
        if notice_type == 'group_increase' and sub_type == 'invite':
            logger.info(f"处理明确的group_increase + invite事件: {event}")
            return await self._handle_group_invite(event, group_config)
            
        # 处理其他可能的邀请事件
        if self._is_invite_event(event):
            logger.info(f"处理其他类型的邀请事件: {event}")
            return await self._handle_group_invite(event, group_config)
        
        # 处理普通的group_increase事件
        if notice_type == 'group_increase' and sub_type != 'invite':
            logger.debug(f"处理普通进群事件: {event}")
            return await self._handle_group_increase(event, group_config)
            
        # 其他类型的通知不处理
        logger.debug(f"未处理的通知类型: {notice_type}, 子类型: {sub_type}")
        return False
        
    async def handle_request(self, event: Dict[str, Any]) -> bool:
        """处理请求事件，主要是群邀请请求"""
        request_type = event.get('request_type')
        sub_type = event.get('sub_type', '')
        
        # 记录详细信息用于调试
        logger.info(f"可疑邀请者检测插件收到请求事件: {event}")
        
        # 只处理群请求
        if request_type != 'group':
            return False
            
        # 获取请求信息
        group_id = event.get('group_id')
        user_id = event.get('user_id')  # 被邀请人
        invitor_id = event.get('invitor_id')  # 邀请人
        flag = event.get('flag', '')  # 用于处理请求的标识
        comment = event.get('comment', '')  # 附加消息
        
        if not group_id or not user_id:
            logger.warning("请求事件缺少必要信息，无法处理")
            return False
            
        # 转为整数
        try:
            group_id = int(group_id)
            user_id = int(user_id)
            if invitor_id:
                invitor_id = int(invitor_id)
        except (ValueError, TypeError):
            logger.warning(f"请求事件中的ID无法转为整数: group_id={group_id}, user_id={user_id}, invitor_id={invitor_id}")
            return False
        
        # 获取群组配置
        group_config = self.get_group_config(group_id)
        
        # 如果插件在此群被禁用，不处理请求
        global_enabled = self.config["global"].get("enabled", False)
        group_enabled = group_config.get("enabled", True)
        if not global_enabled and not group_enabled:
            return False
            
        # 如果群在白名单中，不处理
        if self.is_group_in_whitelist(group_id):
            return False
        
        # 确保群数据存在
        if group_id not in self.user_data:
            self.user_data[group_id] = {}
            
        # 如果是加群请求且由他人邀请
        if sub_type == 'add' and invitor_id:
            # 如果邀请者在白名单中，不处理
            if self.is_user_in_whitelist(invitor_id):
                return False
                
            # 检查邀请者是否是管理员或长期群成员
            is_long_term = await self._is_long_term_member(group_id, invitor_id)
            if is_long_term:
                logger.info(f"邀请者 {invitor_id} 是管理员或长期群成员，不进行可疑行为检测")
                return False
                
            # 为邀请者创建监控记录（如果不存在）
            if invitor_id not in self.user_data[group_id]:
                self.user_data[group_id][invitor_id] = {
                    "join_time": time.time(),  # 邀请者可能已经在群里，使用当前时间
                    "has_spoken": False,       # 假设没有发言
                    "invite_count": 0,         # 初始邀请计数
                    "invited_users": []        # 邀请的用户列表
                }
                
            # 检查邀请者是否在监控列表中
            user_data = self.user_data[group_id][invitor_id]
            current_time = time.time()
            join_time = user_data.get("join_time", 0)
            has_spoken = user_data.get("has_spoken", False)
            
            # 计算加入时间
            minutes_since_join = (current_time - join_time) / 60
            
            # 获取监控时间和最大邀请数
            monitor_time = group_config.get("monitor_time", 3)
            max_invites = group_config.get("max_invites", 3)
            
            # 增加邀请计数
            user_data["invite_count"] += 1
            
            # 记录被邀请者
            if "invited_users" not in user_data:
                user_data["invited_users"] = []
            
            # 记录更详细的被邀请者信息
            invited_user_info = {
                "user_id": user_id,
                "time": current_time,
                "nickname": None
            }
            
            # 尝试获取被邀请者的昵称
            try:
                result = await self.bot._call_api("/get_stranger_info", {
                    "user_id": user_id,
                    "no_cache": True
                })
                if result.get("status") == "ok" and result.get("data"):
                    invited_user_info["nickname"] = result.get("data").get("nickname", "")
                    logger.info(f"获取到被邀请者 {user_id} 的昵称: {invited_user_info['nickname']}")
            except Exception as e:
                logger.debug(f"获取被邀请者 {user_id} 昵称失败: {e}")
            
            # 添加到邀请者的被邀请用户列表中
            if user_id not in [u.get("user_id") for u in user_data["invited_users"]]:
                user_data["invited_users"].append(invited_user_info)
            
            logger.info(f"用户 {invitor_id} 在群 {group_id} 已邀请 {user_data['invite_count']} 人，加入时间：{minutes_since_join:.1f}分钟，阈值：{max_invites}人")
            
            # 检查邀请数是否超过阈值（移除了minutes_since_join的判断）
            if user_data["invite_count"] >= max_invites:
                # 检查是否最近已经踢出过，避免重复操作
                if group_id in self.recent_kicks and invitor_id in self.recent_kicks[group_id]:
                    last_kicked = self.recent_kicks[group_id][invitor_id].get("last_kicked", 0)
                    if current_time - last_kicked < 30:  # 30秒内不重复踢出同一用户
                        logger.info(f"用户 {invitor_id} 最近已被踢出，跳过重复操作，直接拒绝加群请求")
                        
                        # 拒绝被邀请者的加群请求
                        try:
                            await self.bot._call_api("/set_group_add_request", {
                                "flag": flag,
                                "sub_type": "add",
                                "approve": False,
                                "reason": "邀请者存在可疑行为，已被系统移出群聊"
                            })
                            logger.info(f"已拒绝用户 {user_id} 的加群请求，原因：邀请者 {invitor_id} 存在可疑行为")
                            return True
                        except Exception as e:
                            logger.error(f"拒绝加群请求失败: {e}")
                
                # 踢出邀请者
                logger.warning(f"用户 {invitor_id} 在短时间内邀请了 {user_data['invite_count']} 人，符合可疑行为，执行踢出操作")
                
                # 使用完整的踢出用户函数，包含详细的被邀请者信息
                await self._kick_suspicious_user(group_id, invitor_id, user_data, group_config)
                
                # 拒绝被邀请者的加群请求
                try:
                    await self.bot._call_api("/set_group_add_request", {
                        "flag": flag,
                        "sub_type": "add",
                        "approve": False,
                        "reason": "邀请者存在可疑行为，已被系统移出群聊"
                    })
                    logger.info(f"已拒绝用户 {user_id} 的加群请求，原因：邀请者 {invitor_id} 存在可疑行为")
                except Exception as e:
                    logger.error(f"拒绝加群请求失败: {e}")
                
                # 记录最近踢出信息
                if group_id not in self.recent_kicks:
                    self.recent_kicks[group_id] = {}
                self.recent_kicks[group_id][invitor_id] = {
                    "last_kicked": current_time,
                    "invited_users": user_data.get("invited_users", [])
                }
                
                # 移除监控数据
                if invitor_id in self.user_data[group_id]:
                    del self.user_data[group_id][invitor_id]
                    
                return True
        elif sub_type == 'add' and not invitor_id:
            # 这是用户自己申请入群，不是被邀请的，仅记录日志
            logger.info(f"用户 {user_id} 自行申请加入群 {group_id}，不涉及邀请者，不干预")
        
        # 没有干预请求，让其他插件或默认行为处理
        return False
    
    async def _handle_group_increase(self, event: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        """处理成员进群事件"""
        group_id = event.get('group_id')
        user_id = event.get('user_id')
        sub_type = event.get('sub_type', '')
        operator_id = event.get('operator_id')  # 可能是邀请者ID
        
        # 调试日志
        logger.info(f"处理成员进群事件: 群ID={group_id}, 用户ID={user_id}, 类型={sub_type}, 操作者ID={operator_id}")
        
        if not group_id or not user_id:
            return False
            
        # 转为整数
        try:
            group_id = int(group_id)
            user_id = int(user_id)
            if operator_id:
                operator_id = int(operator_id)
        except (ValueError, TypeError):
            logger.warning(f"无效的群ID或用户ID: 群={group_id}, 用户={user_id}")
            return False
            
        # 如果用户在白名单中，不处理
        if self.is_user_in_whitelist(user_id):
            return False
            
        # 检查用户是否是管理员或长期群成员
        is_long_term = await self._is_long_term_member(group_id, user_id)
        if is_long_term:
            logger.info(f"用户 {user_id} 是管理员或长期群成员，不进行监控")
            return False
            
        # 记录用户进群时间
        if group_id not in self.user_data:
            self.user_data[group_id] = {}
            
        # 添加用户到监控列表
        self.user_data[group_id][user_id] = {
            "join_time": time.time(),
            "has_spoken": False,
            "invite_count": 0,
            "invited_users": [],
            # 如果是被邀请进来的，记录邀请者
            "invited_by": operator_id if sub_type == "invite" and operator_id else None
        }
        
        # 如果是被邀请进来的用户，记录到邀请者的invited_users列表中
        if sub_type == "invite" and operator_id and group_id in self.user_data and operator_id in self.user_data[group_id]:
            if "invited_users" not in self.user_data[group_id][operator_id]:
                self.user_data[group_id][operator_id]["invited_users"] = []
                
            # 记录更详细的被邀请者信息
            invited_user_info = {
                "user_id": user_id,
                "time": time.time(),
                "nickname": None
            }
            
            # 尝试获取被邀请者的昵称
            try:
                result = await self.bot._call_api("/get_stranger_info", {
                    "user_id": user_id,
                    "no_cache": True
                })
                if result.get("status") == "ok" and result.get("data"):
                    invited_user_info["nickname"] = result.get("data").get("nickname", "")
            except Exception as e:
                logger.debug(f"获取被邀请者 {user_id} 昵称失败: {e}")
                
            # 添加到邀请者的被邀请用户列表中
            if user_id not in [u.get("user_id") if isinstance(u, dict) else u for u in self.user_data[group_id][operator_id]["invited_users"]]:
                self.user_data[group_id][operator_id]["invited_users"].append(invited_user_info)
                
            logger.info(f"用户 {user_id} 由 {operator_id} 邀请加入群 {group_id}，已记录关联")
        
        logger.info(f"用户 {user_id} 加入群 {group_id}，开始监控")
        return True
    
    def _is_invite_event(self, event: Dict[str, Any]) -> bool:
        """检查事件是否是邀请事件"""
        notice_type = event.get('notice_type')
        sub_type = event.get('sub_type')
        
        # 记录完整事件以便调试
        logger.debug(f"检查是否是邀请事件: {event}")
        
        # 明确的邀请事件 - group_increase + invite子类型
        if notice_type == 'group_increase' and sub_type == 'invite':
            logger.info(f"检测到标准邀请事件格式: notice_type={notice_type}, sub_type={sub_type}")
            return True
            
        # 明确的邀请事件
        if notice_type == 'group_invite':
            logger.info(f"检测到group_invite类型事件")
            return True
            
        # notify子类型为invite的事件
        if notice_type == 'notify' and sub_type == 'invite':
            logger.info(f"检测到notify类型invite子类型事件")
            return True
            
        # 检查templId和templParam，新版go-cqhttp的邀请事件格式
        templ_id = event.get('templId')
        templ_param = event.get('templParam')
        if templ_id == '10179' and templ_param and 'invitor' in templ_param:
            logger.info(f"检测到新版邀请事件格式: templId={templ_id}, templParam={templ_param}")
            return True
        
        # 重要：不再单纯依靠operator_id判断邀请事件
        # 检查事件中是否明确包含邀请关键字，仅限事件文本中明确提及"邀请"的情况
        event_str = str(event).lower()
        if '"sub_type": "invite"' in event_str or '"invite"' in event_str:
            logger.info(f"通过明确的invite关键词检测到邀请事件: {event_str[:200]}...")
            return True
            
        # 未检测到邀请事件
        logger.debug("未检测到邀请事件特征")
        return False

    async def _handle_group_invite(self, event: Dict[str, Any], group_config: Dict[str, Any]) -> bool:
        """处理邀请事件"""
        group_id = event.get('group_id')
        operator_id = event.get('operator_id')  # 邀请人的QQ号
        user_id = event.get('user_id')  # 被邀请人的QQ号
        
        # 调试日志
        logger.info(f"开始处理邀请事件: 群ID={group_id}, 邀请者ID={operator_id}, 被邀请者ID={user_id}, 事件类型={event.get('notice_type')}, 子类型={event.get('sub_type')}")
        
        # 如果找不到operator_id，尝试其他字段
        if not operator_id:
            # 详细日志记录
            logger.debug(f"未直接找到operator_id，尝试从其他字段提取")
            
            # 尝试从不同格式中提取邀请者ID
            if 'user_id' in event and 'sub_type' in event and event.get('sub_type') == 'invite':
                # 在group_increase+invite事件中，user_id是被邀请者，operator_id是邀请者
                # operator_id应该已经存在，这里不需要重新赋值
                logger.debug(f"标准邀请事件格式，operator_id={operator_id}, user_id={user_id}")
                
            # 新版go-cqhttp邀请事件格式
            elif 'templParam' in event and isinstance(event.get('templParam'), dict):
                templ_param = event.get('templParam', {})
                if 'invitor' in templ_param:
                    operator_id = templ_param.get('invitor')
                    logger.debug(f"从templParam.invitor字段提取operator_id: {operator_id}")
                    
                # 如果没有group_id，尝试从事件中获取
                if not group_id and 'group_id' in templ_param:
                    group_id = templ_param.get('group_id')
                    logger.debug(f"从templParam.group_id字段提取group_id: {group_id}")
        
        # 确认操作者ID不是被邀请者ID，如果是同一人则可能是事件处理错误
        if operator_id and user_id and str(operator_id) == str(user_id):
            logger.warning(f"检测到邀请者ID与被邀请者ID相同，可能是事件识别错误: operator_id={operator_id}, user_id={user_id}")
            return False
        
        if not group_id or not operator_id:
            logger.warning(f"邀请事件缺少必要信息，无法处理: 群ID={group_id}, 邀请者ID={operator_id}")
            return False
            
        # 转为整数
        try:
            group_id = int(group_id)
            operator_id = int(operator_id)
            if user_id:
                user_id = int(user_id)
        except (ValueError, TypeError):
            logger.warning(f"群号或操作者ID无法转为整数: group_id={group_id}, operator_id={operator_id}")
            return False
            
        # 如果用户在白名单中，不处理
        if self.is_user_in_whitelist(operator_id):
            logger.info(f"邀请者 {operator_id} 在白名单中，不处理")
            return False
            
        # 检查邀请者是否是管理员或长期群成员
        is_long_term = await self._is_long_term_member(group_id, operator_id)
        if is_long_term:
            logger.info(f"邀请者 {operator_id} 是管理员或长期群成员，不进行可疑行为检测")
            return False
            
        # 检查操作者是否在监控列表中
        if group_id in self.user_data and operator_id in self.user_data[group_id]:
            user_data = self.user_data[group_id][operator_id]
            current_time = time.time()
            join_time = user_data.get("join_time", 0)
            has_spoken = user_data.get("has_spoken", False)
            
            # 计算加入时间
            minutes_since_join = (current_time - join_time) / 60
            
            # 获取监控时间和最大邀请数
            monitor_time = group_config.get("monitor_time", 3)
            max_invites = group_config.get("max_invites", 3)
            
            # 移除时间限制，只要邀请数量超过阈值就进行处理
            # 检查被邀请者是否已经在列表中
            already_invited = False
            for invited_user in user_data["invited_users"]:
                if isinstance(invited_user, dict) and invited_user.get("user_id") == user_id:
                    already_invited = True
                    logger.info(f"用户 {user_id} 已经在 {operator_id} 的邀请列表中，不重复计数")
                    break
                elif not isinstance(invited_user, dict) and invited_user == user_id:
                    already_invited = True
                    logger.info(f"用户 {user_id} 已经在 {operator_id} 的邀请列表中，不重复计数")
                    break
                
                # 只有没有被记录过的用户才会增加邀请计数
                if not already_invited:
                    # 增加邀请计数
                    user_data["invite_count"] += 1
                    
                    # 记录更详细的被邀请者信息
                    invited_user_info = {
                        "user_id": user_id,
                        "time": current_time,
                        "nickname": None
                    }
                    
                    # 尝试获取被邀请者的昵称
                    try:
                        result = await self.bot._call_api("/get_stranger_info", {
                            "user_id": user_id,
                            "no_cache": True
                        })
                        if result.get("status") == "ok" and result.get("data"):
                            invited_user_info["nickname"] = result.get("data").get("nickname", "")
                            logger.info(f"获取到被邀请者 {user_id} 的昵称: {invited_user_info['nickname']}")
                    except Exception as e:
                        logger.debug(f"获取被邀请者 {user_id} 昵称失败: {e}")
                    
                    # 添加到邀请者的被邀请用户列表中
                    if user_id not in [u.get("user_id") if isinstance(u, dict) else u for u in user_data["invited_users"]]:
                        user_data["invited_users"].append(invited_user_info)
                    
                    has_spoken_text = "已发言" if user_data.get("has_spoken") else "未发言"
                    logger.info(f"用户 {operator_id} 在 {minutes_since_join:.1f} 分钟内已邀请 {user_data['invite_count']} 人({has_spoken_text})，阈值为 {max_invites}")
                    
                    # 如果超过阈值，踢出用户，不再检查是否发言
                    if user_data["invite_count"] >= max_invites:
                        # 检查是否最近已经踢出过，避免重复操作
                        if group_id in self.recent_kicks and operator_id in self.recent_kicks[group_id]:
                            last_kicked = self.recent_kicks[group_id][operator_id].get("last_kicked", 0)
                            if current_time - last_kicked < 10:  # 10秒内不重复踢出同一用户
                                logger.info(f"用户 {operator_id} 最近已被踢出，跳过重复操作")
                                return True
                        
                        await self._kick_suspicious_user(group_id, operator_id, user_data, group_config)
                        
                        # 记录最近踢出信息
                        if group_id not in self.recent_kicks:
                            self.recent_kicks[group_id] = {}
                        self.recent_kicks[group_id][operator_id] = {
                            "last_kicked": current_time,
                            "invited_users": user_data.get("invited_users", [])
                        }
                        
                        # 移除监控数据
                        if operator_id in self.user_data[group_id]:
                            del self.user_data[group_id][operator_id]
                            
                        return True
                    # 没有超过阈值，继续观察
                    logger.info(f"用户 {operator_id} 暂不符合踢出条件，继续观察")
                else:
                    logger.info(f"用户 {user_id} 已在邀请列表中，跳过计数")
        else:
            logger.info(f"用户 {operator_id} 不在监控列表中，可能是管理员或已经在群里很久的成员")
        
        return False
        
    async def _kick_suspicious_user(self, group_id: int, user_id: int, user_data: Dict[str, Any], group_config: Dict[str, Any]) -> None:
        """踢出可疑用户"""
        try:
            invite_count = user_data.get("invite_count", 0)
            minutes_since_join = (time.time() - user_data.get("join_time", time.time())) / 60
            invited_users = user_data.get("invited_users", [])
            
            # 记录日志
            logger.warning(f"踢出可疑用户 {user_id} 从群 {group_id}，该用户加入群聊 {minutes_since_join:.1f} 分钟内邀请了 {invite_count} 人")
            
            # 构建警告消息，包含被邀请者信息
            base_message = f"⚠️ 警告: 检测到可疑行为\n用户 {user_id} 在加入群聊短时间内({minutes_since_join:.1f}分钟)邀请了 {invite_count} 人，已被移出群聊。"
            
            # 添加被邀请者信息
            if invited_users:
                invited_message = "\n\n被邀请用户: "
                user_details = []
                
                # 为每个被邀请用户添加详细信息
                for invited_user in invited_users:
                    # 处理新旧两种数据结构
                    if isinstance(invited_user, dict):
                        # 新数据结构
                        invited_id = invited_user.get("user_id")
                        nickname = invited_user.get("nickname")
                        
                        # 基本信息：QQ号
                        if nickname:
                            user_info = f"{invited_id} ({nickname})"
                        else:
                            user_info = f"{invited_id}"
                    else:
                        # 旧数据结构
                        invited_id = invited_user
                        user_info = f"{invited_id}"
                        
                        # 尝试获取用户昵称
                        try:
                            # 尝试从QQ获取用户信息
                            result = await self.bot._call_api("/get_stranger_info", {
                                "user_id": invited_id,
                                "no_cache": True
                            })
                            if result.get("status") == "ok" and result.get("data"):
                                nickname = result.get("data").get("nickname", "")
                                if nickname:
                                    user_info = f"{invited_id} ({nickname})"
                        except Exception as e:
                            logger.debug(f"获取用户 {invited_id} 信息失败: {e}")
                    
                    # 添加@标记和用户信息
                    user_details.append(f"[CQ:at,qq={invited_id}] {user_info}")
                
                # 合并所有用户信息
                if user_details:
                    invited_message += "\n" + "\n".join(user_details)
                    base_message += invited_message
                else:
                    base_message += "\n\n被邀请用户: 无法获取详细信息"
            
            # 发送通知到群
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=base_message
            )
            
            # 踢出用户
            reject = group_config.get("reject_add_request", True)
            await self.bot.set_group_kick(
                group_id=group_id,
                user_id=user_id,
                reject_add_request=reject
            )
        except Exception as e:
            logger.error(f"踢出可疑用户 {user_id} 失败: {e}")
    
    async def _check_and_handle_admin_command(self, event: Dict[str, Any], group_id: int, user_id: int) -> bool:
        """检查和处理管理员命令"""
        # 检查是否是管理员
        is_admin = await self._is_admin(group_id, user_id)
        if not is_admin:
            return False
            
        # 获取机器人QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否有@机器人
        if '[CQ:at,qq=' not in event.get('raw_message', ''):
            return False
        
        # 检查是否@了机器人
        if not is_at_bot(event, bot_qq):
            return False
            
        # 提取命令
        command = extract_command(event, bot_qq)
        
        # 处理启用命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['enable'])
        if is_at_command and match:
            group_config = self.get_group_config(group_id)
            group_config["enabled"] = True
            self.config["groups"][str(group_id)] = group_config
            self.save_config()
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message="✅ 已在当前群启用可疑邀请者检测功能"
            )
            return True
            
        # 处理禁用命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['disable'])
        if is_at_command and match:
            group_config = self.get_group_config(group_id)
            group_config["enabled"] = False
            self.config["groups"][str(group_id)] = group_config
            self.save_config()
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message="❌ 已在当前群禁用可疑邀请者检测功能"
            )
            return True
            
        # 处理状态查询命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['status'])
        if is_at_command and match:
            group_config = self.get_group_config(group_id)
            global_config = self.config["global"]
            
            group_status = "启用" if group_config.get("enabled", True) else "禁用"
            global_status = "启用" if global_config.get("enabled", True) else "禁用"
            monitor_time = group_config.get("monitor_time", 3)
            max_invites = group_config.get("max_invites", 3)
            
            message = f"可疑邀请者检测状态:\n"
            message += f"• 全局状态: {global_status}\n"
            message += f"• 当前群状态: {group_status}\n"
            message += f"• 监控时间: {monitor_time} 分钟\n"
            message += f"• 最大邀请数: {max_invites} 人\n"
            message += f"• 全局白名单群组数: {len(global_config.get('whitelist_groups', []))}\n"
            message += f"• 全局白名单用户数: {len(global_config.get('whitelist_users', []))}"
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=message
            )
            return True
            
        # 处理配置命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['config'])
        if is_at_command and match:
            param_name = match.group(1)
            param_value = match.group(2)
            
            # 获取群组配置
            group_config = self.get_group_config(group_id)
            
            if param_name in ["monitor_time", "max_invites"]:
                try:
                    value = int(param_value)
                    group_config[param_name] = value
                    self.config["groups"][str(group_id)] = group_config
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已设置当前群 {param_name} = {value}"
                    )
                except ValueError:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"❌ 无效的值: {param_value}，请提供一个整数"
                    )
            elif param_name == "reject_add_request":
                if param_value.lower() in ["true", "yes", "1", "on"]:
                    group_config[param_name] = True
                    self.config["groups"][str(group_id)] = group_config
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已设置当前群拒绝再次加群请求: 是"
                    )
                elif param_value.lower() in ["false", "no", "0", "off"]:
                    group_config[param_name] = False
                    self.config["groups"][str(group_id)] = group_config
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已设置当前群拒绝再次加群请求: 否"
                    )
                else:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"❌ 无效的值: {param_value}，请使用 true/false, yes/no, 1/0, on/off"
                    )
            else:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"❌ 未知参数: {param_name}，可用参数: monitor_time, max_invites, reject_add_request"
                )
                
            return True
        
        # 处理全局配置命令 (仅超级用户可用)
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns['global'])
        if is_at_command and match:
            # 检查是否是超级用户
            superusers = self.bot.config.get("bot", {}).get("superusers", [])
            if str(user_id) not in superusers:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message="⚠️ 只有超级用户才能修改全局配置"
                )
                return True
                
            param_name = match.group(1)
            param_value = match.group(2)
            
            if param_name in ["monitor_time", "max_invites"]:
                try:
                    value = int(param_value)
                    self.config["global"][param_name] = value
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已设置全局 {param_name} = {value}"
                    )
                except ValueError:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"❌ 无效的值: {param_value}，请提供一个整数"
                    )
            elif param_name == "reject_add_request":
                if param_value.lower() in ["true", "yes", "1", "on"]:
                    self.config["global"][param_name] = True
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已设置全局拒绝再次加群请求: 是"
                    )
                elif param_value.lower() in ["false", "no", "0", "off"]:
                    self.config["global"][param_name] = False
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已设置全局拒绝再次加群请求: 否"
                    )
                else:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"❌ 无效的值: {param_value}，请使用 true/false, yes/no, 1/0, on/off"
                    )
            elif param_name == "enabled":
                if param_value.lower() in ["true", "yes", "1", "on"]:
                    self.config["global"][param_name] = True
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已全局启用可疑邀请者检测功能"
                    )
                elif param_value.lower() in ["false", "no", "0", "off"]:
                    self.config["global"][param_name] = False
                    self.save_config()
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"✅ 已全局禁用可疑邀请者检测功能"
                    )
                else:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"❌ 无效的值: {param_value}，请使用 true/false, yes/no, 1/0, on/off"
                    )
            else:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"❌ 未知全局参数: {param_name}，可用全局参数: monitor_time, max_invites, reject_add_request, enabled"
                )
                
            return True
            
        return False
        
    async def _is_admin(self, group_id: int, user_id: int) -> bool:
        """检查用户是否是管理员"""
        # 首先检查是否是超级用户
        superusers = self.bot.config.get("bot", {}).get("superusers", [])
        if str(user_id) in superusers:
            return True
            
        try:
            # 获取群成员信息
            info = await self.bot.get_group_member_info(group_id=group_id, user_id=user_id)
            role = info.get('data', {}).get('role', 'member')
            # 检查是否是群主或管理员
            return role in ['owner', 'admin']
        except Exception as e:
            logger.error(f"获取群成员信息失败: {e}")
            return False

    async def _is_long_term_member(self, group_id: int, user_id: int) -> bool:
        """检查用户是否是群内长期成员或管理员
        
        参数:
            group_id: 群号
            user_id: 用户QQ号
        
        返回:
            如果用户是群管理员、群主或长期群成员(超过30天)则返回True
        """
        try:
            # 获取群成员信息
            result = await self.bot._call_api("/get_group_member_info", {
                "group_id": group_id,
                "user_id": user_id,
                "no_cache": True
            })
            
            # 检查是否成功获取信息
            if result.get("status") == "ok" and result.get("data"):
                member_info = result.get("data")
                
                # 如果是群主或管理员，直接返回True
                role = member_info.get("role", "")
                if role in ["owner", "admin"]:
                    logger.info(f"用户 {user_id} 是群 {group_id} 的{role}，不进行检测")
                    return True
                
                # 获取入群时间
                join_time = member_info.get("join_time", 0)
                current_time = int(time.time())
                days_in_group = (current_time - join_time) / (60 * 60 * 24)  # 转换为天
                
                # 检查是否是今天加入的群
                join_date = datetime.fromtimestamp(join_time).date()
                current_date = datetime.fromtimestamp(current_time).date()
                
                if join_date == current_date:
                    # 今天加入的群，使用固定的3分钟监控时间
                    logger.info(f"用户 {user_id} 在群 {group_id} 是今天({join_date})加入的，使用3分钟监控时间")
                    return False
                
                # 如果在群内超过30天，认为是长期成员
                if days_in_group > 30:
                    logger.info(f"用户 {user_id} 在群 {group_id} 超过30天({days_in_group:.1f}天)，认为是长期成员")
                    return True
                    
                logger.info(f"用户 {user_id} 在群 {group_id} {days_in_group:.1f}天，需要继续监控")
                return False
        except Exception as e:
            logger.warning(f"检查用户 {user_id} 在群 {group_id} 的状态时出错: {e}")
            return False  # 如果出错，为了安全起见返回False
            
        return False

# 插件实例
plugin_class = SuspiciousInviter