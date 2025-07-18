#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import aiohttp
import base64
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union, Tuple
import urllib.parse

# 导入Plugin基类
from plugin_system import Plugin

logger = logging.getLogger("LCHBot")

class AdminMenu(Plugin):
    """
    管理员菜单插件
    功能：提供机器人的管理功能，如机器人设置、群管理等
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        # 设置命令模式
        self.command_patterns = {
            "admin": re.compile(r"^/admin$"),
            "set_name": re.compile(r"^/set_name\s+(.+)$"),
            "set_card": re.compile(r"^/set_card\s+(.+)$"),
            "set_avatar": re.compile(r"^/set_avatar$"),  # 新增设置头像命令
            "join_group": re.compile(r"^/join_group\s*(\d+)$"),  # 修改正则表达式，使空格可选
        }
        
        # 保存管理员列表
        self.admin_ids = set(bot.config.get("bot", {}).get("superusers", []))
        
        # 创建图片缓存目录
        self.avatar_cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "resources", "temp")
        os.makedirs(self.avatar_cache_dir, exist_ok=True)
        
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化")
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        from plugins.utils import handle_at_command, is_at_bot
        
        # 获取消息类型和机器人QQ号
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        message = event.get('raw_message', '')
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 只有特定命令需要@机器人
        at_required_cmds = ["admin", "set_name", "set_card", "set_avatar"]
        
        # 检查发送者是否是管理员
        if str(user_id) not in self.admin_ids:
            return False
            
        # 管理菜单
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns["admin"])
        if is_at_command and match:
            logger.info("接收到管理菜单命令")
            
            # 获取管理菜单文本
            menu_text = self._get_admin_menu_text()
            
            # 发送响应
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id if message_type == "private" else None,
                group_id=group_id if message_type == "group" else None,
                message=menu_text
            )
            return True
        
        # 设置昵称
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns["set_name"])
        if is_at_command and match:
            new_name = match.group(1).strip()
            logger.info(f"接收到设置昵称命令，新昵称: {new_name}")
            
            # 调用API设置昵称
            result = await self._set_bot_name(new_name)
            
            # 发送响应
            response = f"✅ 已设置机器人昵称为: {new_name}" if result else "❌ 设置昵称失败，请稍后再试"
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id if message_type == "private" else None,
                group_id=group_id if message_type == "group" else None,
                message=response
            )
            return True
        
        # 设置群名片
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns["set_card"])
        if is_at_command and match and message_type == "group":
            new_card = match.group(1).strip()
            logger.info(f"接收到设置群名片命令，群: {group_id}, 新名片: {new_card}")
            
            # 调用API设置群名片
            if group_id is not None:  # 确保group_id不为None
                result = await self._set_bot_card(group_id, new_card)
                
                # 发送响应
                response = f"✅ 已设置机器人在本群的名片为: {new_card}" if result else "❌ 设置群名片失败，请稍后再试"
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=response
                )
                return True
        
        # 设置头像
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_patterns["set_avatar"])
        if is_at_command and match:
            # 检查消息中是否包含图片
            image_url = self._extract_image_url(event)
            if not image_url:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=user_id if message_type == "private" else None,
                    group_id=group_id if message_type == "group" else None,
                    message="❌ 请在命令中附带要设置的头像图片"
                )
                return True
                
            logger.info(f"接收到设置头像命令，图片URL: {image_url}")
            
            # 下载并设置头像
            result = await self._set_bot_avatar(image_url)
            
            # 发送响应
            if result:
                response = "✅ 已成功设置机器人头像"
            else:
                response = "❌ 设置头像失败，请确保图片格式正确且大小合适"
                
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id if message_type == "private" else None,
                group_id=group_id if message_type == "group" else None,
                message=response
            )
            return True
        
        # 申请加群命令 - 英文版，私聊命令
        # 首先检查是否是私聊消息
        if message_type == "private":
            logger.info(f"收到私聊消息: {message}")
            match = self.command_patterns["join_group"].search(message)
            if match:
                group_id_to_join = match.group(1)
                logger.info(f"成功匹配join_group命令，目标群号: {group_id_to_join}")
                
                # 调用API申请加入群
                result = await self._join_group(group_id_to_join)
                
                # 发送响应
                if result:
                    response = f"✅ 已发送加入群 {group_id_to_join} 的申请"
                else:
                    response = f"❌ 申请加入群 {group_id_to_join} 失败，请检查群号是否正确或机器人是否已在该群中"
                    
                await self.bot.send_msg(
                    message_type="private",
                    user_id=user_id,
                    message=response
                )
                return True
            else:
                logger.debug(f"私聊消息不匹配join_group命令: {message}")
            
        # 旧的申请加群命令（保持向后兼容）
        join_group_pattern = re.compile(r"申请加入此群\s+(\d+)")
        match = join_group_pattern.search(message)
        if match and is_at_bot(event, bot_qq):
            group_id_to_join = match.group(1)
            logger.info(f"接收到申请加入群命令（旧格式），目标群号: {group_id_to_join}")
            
            # 提醒用户使用新命令
            reminder = "提示：此命令已更新为私聊命令，请私聊机器人使用 /join_group <群号> 命令\n\n"
            
            # 调用API申请加入群
            result = await self._join_group(group_id_to_join)
            
            # 发送响应
            if result:
                response = reminder + f"✅ 已发送加入群 {group_id_to_join} 的申请"
            else:
                response = reminder + f"❌ 申请加入群 {group_id_to_join} 失败，请检查群号是否正确或机器人是否已在该群中"
                
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id if message_type == "private" else None,
                group_id=group_id if message_type == "group" else None,
                message=response
            )
            return True
        
        return False
        
    def _get_admin_menu_text(self) -> str:
        """获取管理菜单文本"""
        return """【管理员菜单】

📝 基础设置命令：
1. /set_name <新名称> - 设置机器人QQ昵称
2. /set_card <新名片> - 设置机器人在当前群的群名片
3. /set_avatar <图片> - 设置机器人QQ头像

🔐 授权管理命令：
1. /auth add <群号> [天数] - 为群添加授权，不填天数默认30天
2. /auth remove <群号> - 移除指定群的授权
3. /auth list - 列出所有已授权的群及其状态
4. /auth info - 查看当前群的授权信息

💰 积分系统命令：
1. /sign_set base <数值> - 设置基础签到积分
2. /sign_set bonus <天数> <数值> - 设置连续签到奖励
3. /points_add @用户 <数值> - 为用户添加/减少积分
4. /shop_add <名称> <所需积分> <描述> - 添加兑换项目

🤖 AI聊天命令：
1. /switch_persona <人格名> - 切换聊天人格
2. /clear_context - 清除当前群的聊天上下文
3. /debug_context - 显示当前群的上下文内容

🔍 查询功能命令：
1. /weather <城市名> - 查询指定城市的天气预报
2. /university <大学名称> - 查询大学详细信息
   或 /大学 <大学名称> - 同上，中文命令

⚙️ 群管理命令：
1. /verify enable - 启用进群验证功能
2. /verify disable - 禁用进群验证功能
3. /rate enable - 启用访问限制功能
4. /rate disable - 禁用访问限制功能
5. /suspicious enable - 在当前群启用可疑邀请者检测
6. /suspicious disable - 在当前群禁用可疑邀请者检测
7. /suspicious status - 查看可疑邀请者检测状态
8. /suspicious config <参数> <值> - 配置当前群的检测参数
9. /suspicious global <参数> <值> - 配置全局检测参数(仅超级用户)
10. /join_group <群号> - 私聊机器人，让机器人申请加入指定群

👤 黑名单管理命令：
1. /blacklist add <@用户|QQ号> [原因] - 将用户添加到全局黑名单
2. /blacklist remove <@用户|QQ号> - 将用户从全局黑名单中移除
3. /blacklist list - 查看全局黑名单列表
4. /blacklist check <@用户|QQ号> - 检查用户是否在黑名单中

🎮 文字游戏命令：
1. /game start 成语接龙 - 开始成语接龙游戏
2. /game start 猜词 - 开始猜词游戏
3. /game start 数字炸弹 [最小值] [最大值] - 开始数字炸弹游戏
4. /game start 文字接龙 - 开始文字接龙游戏
5. /game start 恶魔轮盘 - 开始恶魔轮盘射击游戏
6. /game rules <游戏名> - 查看游戏规则
7. /game status - 查看当前游戏状态
8. /game stop - 停止当前游戏

✨ 可用人格: ailixiya (爱莉希雅), xiadie (遐蝶), teresiya (特雷西娅)"""
        
    async def _set_bot_name(self, name: str) -> bool:
        """设置机器人昵称"""
        try:
            # 调用API
            api_url = "/set_qq_profile"
            data = {"nickname": name}
            result = await self.bot._call_api(api_url, data)
            
            # 检查结果
            if result.get("status") == "ok":
                return True
            else:
                logger.error(f"设置昵称失败: {result}")
                return False
        except Exception as e:
            logger.error(f"设置昵称出错: {e}")
            return False
            
    async def _set_bot_card(self, group_id: int, card: str) -> bool:
        """设置机器人群名片"""
        try:
            # 获取机器人QQ号
            bot_qq = self.bot.config.get("bot", {}).get("self_id", "")
            
            # 调用API
            api_url = "/set_group_card"
            data = {
                "group_id": group_id,
                "user_id": bot_qq,
                "card": card
            }
            result = await self.bot._call_api(api_url, data)
            
            # 检查结果
            if result.get("status") == "ok":
                return True
            else:
                logger.error(f"设置群名片失败: {result}")
                return False
        except Exception as e:
            logger.error(f"设置群名片出错: {e}")
            return False
            
    def _extract_image_url(self, event: Dict[str, Any]) -> Optional[str]:
        """从消息中提取图片URL"""
        # 获取消息内容
        message = event.get('message', [])
        
        # 检查是否是列表格式的消息段
        if isinstance(message, list):
            # 遍历消息段找图片
            for segment in message:
                if isinstance(segment, dict) and segment.get('type') == 'image':
                    return segment.get('data', {}).get('url')
        else:
            # 如果是字符串格式，尝试解析CQ码
            message_str = str(message)
            image_pattern = re.compile(r'\[CQ:image,.*?url=([^,\]]+)')
            match = image_pattern.search(message_str)
            if match:
                return urllib.parse.unquote(match.group(1))
                
        return None
        
    async def _set_bot_avatar(self, image_url: str) -> bool:
        """设置机器人头像"""
        try:
            # 生成本地文件路径
            timestamp = int(time.time())
            local_path = os.path.join(self.avatar_cache_dir, f"avatar_{timestamp}.jpg")
            
            # 下载图片
            if image_url.startswith("http://") or image_url.startswith("https://"):
                # 下载网络图片
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            with open(local_path, 'wb') as f:
                                f.write(await resp.read())
                        else:
                            logger.error(f"下载图片失败，状态码: {resp.status}")
                            return False
            else:
                # 尝试从BASE64解码
                if "base64://" in image_url:
                    base64_data = image_url.split("base64://")[1]
                    try:
                        with open(local_path, 'wb') as f:
                            f.write(base64.b64decode(base64_data))
                    except Exception as e:
                        logger.error(f"解码BASE64图片失败: {e}")
                        return False
                else:
                    logger.error(f"不支持的图片URL格式: {image_url}")
                    return False
            
            # 检查文件是否存在
            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                logger.error("图片下载失败或文件为空")
                return False
                
            # 设置头像
            api_url = "/set_qq_avatar"
            data = {"file": f"file://{local_path}"}
            result = await self.bot._call_api(api_url, data)
            
            # 检查结果
            if result.get("status") == "ok":
                logger.info(f"成功设置头像: {local_path}")
                return True
            else:
                logger.error(f"设置头像失败: {result}")
                return False
        except Exception as e:
            logger.error(f"设置头像出错: {e}")
            return False
            
    async def _join_group(self, group_id: str) -> bool:
        """申请加入QQ群"""
        try:
            # 调用API
            api_url = "/set_group_add_request"
            try:
                # 首先尝试直接用入群请求API
                data = {
                    "group_id": int(group_id),
                    "type": "group",
                    "approve": True
                }
                result = await self.bot._call_api(api_url, data)
                
                # 检查结果
                if result.get("status") == "ok":
                    return True
            except Exception as e:
                logger.warning(f"第一种方法申请加入群失败: {e}")
                
            # 如果第一种方法失败，尝试使用另一种API
            try:
                api_url = "/send_group_join_request"
                data = {
                    "group_id": int(group_id),
                    "reason": "机器人自动申请加入群组"
                }
                result = await self.bot._call_api(api_url, data)
                
                # 检查结果
                if result.get("status") == "ok":
                    return True
                else:
                    logger.error(f"申请加入群失败: {result}")
                    return False
            except Exception as e:
                logger.error(f"第二种方法申请加入群出错: {e}")
                return False
                
        except Exception as e:
            logger.error(f"申请加入群出错: {e}")
            return False
                
# 导出插件类，确保插件加载器能找到它
plugin_class = AdminMenu 