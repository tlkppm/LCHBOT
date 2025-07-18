#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
from typing import Dict, Any

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command

logger = logging.getLogger("LCHBot")

class Echo(Plugin):
    """
    Echo插件，用于回复用户的消息
    命令格式: @机器人 /echo 内容
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/echo\s+(.+)$')
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 使用工具函数处理@机器人命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_pattern)
        
        if is_at_command and match:
            content = match.group(1).strip()
            logger.info(f"接收到 echo 命令，内容：{content}")
            
            # 发送回复
            response_data = await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=content
            )
            
            if response_data.get('status') == 'failed':
                logger.error(f"Echo 回复失败：{response_data.get('error')}")
            
            return True  # 表示已处理该消息
            
        return False  # 未处理该消息

# 导出插件类，确保插件加载器能找到它
plugin_class = Echo 