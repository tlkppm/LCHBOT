#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import json
from typing import Dict, Any

# 导入Plugin基类和工具函数
from src.plugin_system import Plugin
from src.plugins.utils import handle_at_command, extract_command

logger = logging.getLogger("LCHBot")

class ComplexMsg(Plugin):
    """
    复杂消息插件，用于发送图文混合等复杂消息
    命令格式：
    @机器人 /image <URL> - 发送图片
    @机器人 /mixed <文本> - 发送图文混合消息
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_patterns = {
            'image': re.compile(r'^/image\s+(.+)$'),
            'mixed': re.compile(r'^/mixed\s+(.+)$')
        }
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 获取机器人的QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否是@机器人的消息
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 提取命令
        is_at = handle_at_command(event, self.bot, re.compile(r'^/'))[0]
        if not is_at:
            return False
            
        # 提取完整命令
        command = extract_command(event, bot_qq)
        
        # 检查图片命令
        image_match = self.command_patterns['image'].match(command)
        if image_match:
            image_url = image_match.group(1).strip()
            logger.info(f"接收到图片命令，URL：{image_url}")
            
            # 构造图片消息
            image_msg = f"[CQ:image,file={image_url}]"
            
            # 发送回复
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=image_msg
            )
            
            return True
            
        # 检查混合消息命令
        mixed_match = self.command_patterns['mixed'].match(command)
        if mixed_match:
            content = mixed_match.group(1).strip()
            logger.info(f"接收到混合消息命令，内容：{content}")
            
            # 构造默认的图文混合消息
            mixed_msg = (
                f"{content}\n"
                f"[CQ:image,file=https://api.moedog.org/images/random-img.php]"
            )
            
            # 发送回复
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=mixed_msg
            )
            
            return True
            
        return False  # 未处理该消息

# 导出插件类，确保插件加载器能找到它
plugin_class = ComplexMsg 