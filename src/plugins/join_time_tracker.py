#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import time
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command

logger = logging.getLogger("LCHBot")

class JoinTimeTracker(Plugin):
    """
    入群时间计算插件，获取群成员的入群时间，并显示入群时间最长的成员
    命令格式: 
    - /join_time [人数] 
    - @机器人 /join_time [人数]
    默认显示入群时间最长的前10名成员
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/join_time(?:\s+(\d+))?$')
        # 缓存群成员信息，格式：{群号: {成员QQ: {"join_time": 时间戳, "nickname": 昵称}}}
        self.group_members_cache = {}
        # 缓存过期时间（秒）
        self.cache_expire_time = 3600  # 1小时
        # 缓存最后更新时间，格式：{群号: 时间戳}
        self.cache_update_time = {}
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 只在群聊中有效
        if message_type != 'group' or not group_id:
            return False
        
        # 使用工具函数处理@机器人命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_pattern)
        
        if is_at_command and match:
            # 提取人数参数
            limit = int(match.group(1)) if match.group(1) else 10
            return await self._process_join_time_command(event, group_id, limit)
            
        return False
    
    async def _process_join_time_command(self, event: Dict[str, Any], group_id: int, limit: int) -> bool:
        """处理入群时间命令的核心逻辑"""
        logger.info(f"接收到入群时间查询命令，群号: {group_id}，显示人数: {limit}")
        
        # 发送处理中提示
        await self.bot.send_msg(
            message_type='group',
            group_id=group_id,
            message="正在获取群成员信息，请稍候..."
        )
        
        # 获取群成员信息
        try:
            members = await self._get_group_members(group_id)
            if not members:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message="获取群成员信息失败，请稍后再试"
                )
                return True
                
            # 按入群时间排序
            sorted_members = sorted(members, key=lambda x: x.get('join_time', 0))
            
            # 生成结果消息
            current_time = time.time()
            result_msg = f"【入群时间最长的{min(limit, len(sorted_members))}位成员】\n"
            
            for i, member in enumerate(sorted_members[:limit]):
                nickname = member.get('nickname', '未知')
                user_id = member.get('user_id', '未知')
                join_time = member.get('join_time', 0)
                
                if join_time > 0:
                    # 计算入群天数
                    days = int((current_time - join_time) / (24 * 3600))
                    join_date = datetime.fromtimestamp(join_time).strftime('%Y-%m-%d')
                    result_msg += f"{i+1}. {nickname}({user_id}) - {join_date} - 已入群{days}天\n"
                else:
                    result_msg += f"{i+1}. {nickname}({user_id}) - 入群时间未知\n"
            
            # 发送结果
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=result_msg
            )
            
            return True
            
        except Exception as e:
            logger.error(f"获取群成员入群时间出错: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"获取群成员入群时间出错: {str(e)}"
            )
            return True
    
    async def _get_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        """获取群成员信息，带缓存"""
        current_time = time.time()
        
        # 检查缓存是否有效
        if (
            group_id in self.group_members_cache and 
            group_id in self.cache_update_time and 
            current_time - self.cache_update_time[group_id] < self.cache_expire_time
        ):
            logger.debug(f"使用缓存的群成员信息，群号: {group_id}")
            return list(self.group_members_cache[group_id].values())
        
        # 缓存无效或不存在，重新获取
        logger.debug(f"重新获取群成员信息，群号: {group_id}")
        
        # 调用OneBot API获取群成员列表
        data = {
            "group_id": group_id
        }
        
        try:
            result = await self.bot._call_api("/get_group_member_list", data)
            
            if result.get("status") == "failed":
                logger.error(f"获取群成员列表失败: {result.get('error')}")
                return []
                
            # 更新缓存
            members = result.get("data", [])
            
            # 初始化群缓存
            self.group_members_cache[group_id] = {}
            
            for member in members:
                user_id = member.get("user_id")
                if user_id:
                    self.group_members_cache[group_id][user_id] = member
                    
            # 更新缓存时间
            self.cache_update_time[group_id] = current_time
            
            return members
            
        except Exception as e:
            logger.error(f"调用获取群成员API出错: {e}", exc_info=True)
            return []

# 导出插件类，确保插件加载器能找到它
plugin_class = JoinTimeTracker 