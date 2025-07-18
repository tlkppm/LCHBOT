#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging
import aiohttp
import asyncio
from io import BytesIO
from typing import Dict, Any, Tuple, Optional, List, Union, cast
from PIL import Image

# 导入Plugin基类和工具函数
from src.plugin_system import Plugin
from src.plugins.utils import handle_at_command, extract_command, Message

logger = logging.getLogger("LCHBot")

class MemeGenerator(Plugin):
    """
    表情包生成插件
    命令格式：
    @机器人 /meme [@用户] - 生成坟前表情包（使用被@用户头像和发送者头像）
    @机器人 /meme <名称> [@用户] - 生成表情包（使用被@用户的头像）
    @机器人 /meme help - 查看支持的表情包列表
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/meme(?:\s+(\S+))?(?:\s+(.+))?$')
        
        # 确保表情包模板路径存在
        self.resource_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "resources", "meme")
        os.makedirs(self.resource_dir, exist_ok=True)
        
        # 模板图片路径
        self.template_path = os.path.join(self.resource_dir, "kibgh.jpg")
        
        # 红色和蓝色区域的坐标和大小（左上角坐标，宽度，高度）
        # 注意：这些坐标需要根据实际图片进行调整
        self.red_area = (150, 140, 120, 120)  # 红色区域 (x, y, width, height) - 墓碑上的头像
        self.blue_area = (400, 340, 120, 120)  # 蓝色区域 (x, y, width, height) - 扶额的人头像
        
        # 支持的表情包类型
        self.meme_types = {
            "default": {"description": "坟前表情包，需要两个头像"},
            "help": {"description": "显示可用的表情包列表"}
        }
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        raw_message = event.get('raw_message', '')
        
        # 获取机器人的QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否是@机器人的消息并且包含/meme命令
        is_at_command, match, command = handle_at_command(event, self.bot, self.command_pattern)
        if not is_at_command:
            return False
            
        # 确认命令是/meme，否则不处理
        if not command or not command.startswith("/meme"):
            logger.debug(f"命令不是/meme，而是: {command}")
            return False
        
        # 记录原始消息用于调试    
        logger.debug(f"表情包生成插件收到原始消息: {raw_message}")
        
        # 提取子命令和参数
        if match:
            meme_type = match.group(1) if match.group(1) else "default"
            after_command = match.group(2) if match.group(2) else ""
        else:
            meme_type = "default"
            after_command = ""
        
        # 如果命令是help，显示帮助信息
        if meme_type == "help":
            help_text = "可用的表情包列表：\n"
            for meme_name, info in self.meme_types.items():
                if meme_name != "help":
                    help_text += f"- {meme_name}: {info['description']}\n"
            help_text += "\n使用方法：@机器人 /meme [类型] [@用户]"
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=help_text
            )
            return True
            
        # 提取被@的用户ID
        mentioned_user = None
        # 在命令后面的内容或整个消息中查找@用户
        at_pattern = r'\[CQ:at,qq=(\d+)(?:,name=[^\]]*)?]'
        at_matches = re.findall(at_pattern, raw_message)
        
        # 过滤掉@机器人自己的情况
        filtered_matches = [qq for qq in at_matches if qq != bot_qq]
        
        if filtered_matches:
            # 使用找到的第一个非机器人@用户
            mentioned_user = int(filtered_matches[0])
            logger.debug(f"找到的@用户: {mentioned_user}")
        else:
            logger.debug("没有找到被@的用户，将使用发送者自己")
            
        # 确保user_id不为None且为int类型
        if user_id is None:
            logger.error("用户ID为空")
            return False
            
        sender_id = int(user_id)
        target_id = mentioned_user if mentioned_user is not None else sender_id
        
        logger.info(f"接收到表情包生成命令，类型: {meme_type}, 生成用户: {sender_id}, 被@用户: {target_id}")
        
        try:
            # 生成表情包
            result_path = await self._generate_meme(sender_id, target_id, meme_type)
            if result_path:
                # 构造图片消息
                image_msg = f"[CQ:image,file=file:///{result_path}]"
                
                # 发送回复
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=user_id,
                    group_id=group_id,
                    message=image_msg
                )
                return True
        except Exception as e:
            logger.error(f"生成表情包出错: {e}", exc_info=True)
            
            # 发送错误消息
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=f"生成表情包失败: {str(e)}"
            )
            return True
            
        return False
        
    async def _get_avatar(self, user_id: int) -> BytesIO:
        """
        获取用户头像
        
        参数:
            user_id: QQ号
            
        返回:
            BytesIO对象，包含头像图片数据
        """
        # QQ头像URL
        avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(avatar_url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        return BytesIO(data)
                    else:
                        logger.error(f"获取头像失败，状态码: {resp.status}")
                        raise Exception(f"获取头像失败，状态码: {resp.status}")
            except Exception as e:
                logger.error(f"获取头像出错: {e}")
                raise Exception(f"获取头像出错: {e}")
                
    async def _generate_meme(self, sender_id: int, mentioned_id: int, meme_type: str = "default") -> str:
        """
        生成表情包
        
        参数:
            sender_id: 发送者QQ号
            mentioned_id: 被@用户QQ号
            meme_type: 表情包类型
            
        返回:
            生成的表情包图片路径
        """
        # 检查模板是否存在
        if not os.path.exists(self.template_path):
            raise FileNotFoundError(f"找不到表情包模板: {self.template_path}")
            
        # 获取头像
        mentioned_avatar_data = await self._get_avatar(mentioned_id)
        sender_avatar_data = await self._get_avatar(sender_id)
        
        # 打开头像图片
        mentioned_avatar = Image.open(mentioned_avatar_data).convert("RGBA")
        sender_avatar = Image.open(sender_avatar_data).convert("RGBA")
        
        # 打开模板图片
        template = Image.open(self.template_path).convert("RGBA")
        
        # 调整头像大小
        mentioned_avatar = mentioned_avatar.resize((self.red_area[2], self.red_area[3]), Image.Resampling.LANCZOS)
        sender_avatar = sender_avatar.resize((self.blue_area[2], self.blue_area[3]), Image.Resampling.LANCZOS)
        
        # 将头像粘贴到模板上
        template.paste(mentioned_avatar, (self.red_area[0], self.red_area[1]), mentioned_avatar)
        template.paste(sender_avatar, (self.blue_area[0], self.blue_area[1]), sender_avatar)
        
        # 生成结果文件名
        result_filename = f"meme_{sender_id}_{mentioned_id}_{self.id}.png"
        result_path = os.path.join(self.resource_dir, result_filename)
        
        # 保存结果
        template.save(result_path)
        
        return result_path

# 导出插件类，确保插件加载器能找到它
plugin_class = MemeGenerator 