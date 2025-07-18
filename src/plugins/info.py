#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import platform
import sys
import os
from typing import Dict, Any

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command

logger = logging.getLogger("LCHBot")

class Info(Plugin):
    """
    信息插件，用于显示系统和机器人信息
    命令格式: @机器人 /info
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/info$')
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 使用工具函数处理@机器人命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_pattern)
        
        if is_at_command and match:
            logger.info(f"接收到 info 命令")
            
            # 获取系统信息
            system_info = {
                "系统": platform.system(),
                "版本": platform.version(),
                "Python版本": sys.version.split()[0],
                "机器名": platform.node()
            }
            
            # 获取机器人信息
            plugin_manager = self.bot.plugin_manager
            bot_info = {
                "名称": self.bot.config['bot']['name'],
                "插件数量": len(plugin_manager.get_all_plugins()),
                "已加载插件": ', '.join([p.name for p in plugin_manager.get_active_plugins()]),
                "HTTP服务": f"{self.bot.http_host}:{self.bot.http_port}"
            }
            
            # 构建回复消息
            response = "系统信息：\n"
            for key, value in system_info.items():
                response += f"- {key}: {value}\n"
                
            response += "\n机器人信息：\n"
            for key, value in bot_info.items():
                response += f"- {key}: {value}\n"
            
            # 发送回复
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=response
            )
            
            return True  # 表示已处理该消息
            
        return False  # 未处理该消息 

# 导出插件类，确保插件加载器能找到它
plugin_class = Info 