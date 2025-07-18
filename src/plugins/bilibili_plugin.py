#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import logging
import time
import aiohttp
import asyncio
import qrcode
import tempfile
import base64
import io
from PIL import Image
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional, Union

# 导入Plugin基类和工具函数
from src.plugin_system import Plugin
from src.plugins.utils import handle_at_command, extract_command, is_at_bot

logger = logging.getLogger("LCHBot")

class BilibiliPlugin(Plugin):
    """
    哔哩哔哩专属插件
    
    基础功能:
    - @机器人 /bili.bind <uid> - 绑定B站账号
    - @机器人 /bili.login - 扫码登录
    - @机器人 /bili.unbind - 解绑B站账号
    - @机器人 /bili.info - 查看已绑定的账号信息
    - @机器人 /bili.up <uid/用户名> - 查询UP主信息
    - @机器人 /bili.video <BV号> - 查询视频信息
    
    会员专享功能:
    - @机器人 /bili.sub <uid/用户名> - 订阅UP主更新和开播通知
    - @机器人 /bili.unsub <uid/用户名> - 取消订阅
    - @机器人 /bili.subs - 查看订阅列表
    - @机器人 /bili.hot - 获取B站热门推送
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "BilibiliPlugin"
        
        # 命令模式
        self.command_patterns = {
            'bind': re.compile(r'^/bili\.bind\s+(\d+)$'),  # 绑定账号
            'login': re.compile(r'^/bili\.login$'),  # 扫码登录
            'unbind': re.compile(r'^/bili\.unbind$'),  # 解绑账号
            'info': re.compile(r'^/bili\.info$'),  # 查看账号信息
            'up': re.compile(r'^/bili\.up\s+(.+)$'),  # 查询UP主信息
            'video': re.compile(r'^/bili\.video\s+(\w+)$'),  # 查询视频信息
            'sub': re.compile(r'^/bili\.sub\s+(.+)$'),  # 订阅UP主
            'unsub': re.compile(r'^/bili\.unsub\s+(.+)$'),  # 取消订阅
            'subs': re.compile(r'^/bili\.subs$'),  # 查看订阅列表
            'hot': re.compile(r'^/bili\.hot$'),  # 获取热门推送
            'help': re.compile(r'^/bili\.help$'),  # 显示帮助信息
        }
        
        # 管理员命令模式
        self.admin_command_patterns = {
            'add_member': re.compile(r'^/bili\.admin\s+add_member\s+(\d+)$'),  # 添加会员
            'remove_member': re.compile(r'^/bili\.admin\s+remove_member\s+(\d+)$'),  # 移除会员
            'list_members': re.compile(r'^/bili\.admin\s+list_members$'),  # 查看会员列表
            'notify': re.compile(r'^/bili\.admin\s+notify\s+(on|off)$'),  # 设置当前群通知开关
            'help': re.compile(r'^/bili\.admin$'),  # 显示管理员帮助信息
        }
        
        # 数据文件路径
        self.data_file = "data/bilibili_data.json"
        
        # 加载数据
        self.data = self.load_json(self.data_file, {
            "bindings": {},  # {qq_id: {uid: xxx, username: xxx, ...}}
            "subscriptions": {},  # {qq_id: [{up_uid: xxx, up_name: xxx}, ...]}
            "members": [],  # 会员QQ号列表
            "notification_groups": {},  # {group_id: {enabled: True, users: [xxx, ...]}}
            "last_check": {}  # {up_uid: timestamp}
        })
        
        # 检查数据结构
        self._check_data_structure()
        
        # API配置
        self.api_base = "https://api.bilibili.com"
        self.live_api_base = "https://api.live.bilibili.com"
        
        # 启动订阅检查任务
        self.check_task = None
        
        logger.info(f"插件 {self.name} 已初始化，当前绑定用户数: {len(self.data['bindings'])}")
        
    def _check_data_structure(self):
        """确保数据结构完整"""
        if "bindings" not in self.data:
            self.data["bindings"] = {}
        if "subscriptions" not in self.data:
            self.data["subscriptions"] = {}
        if "members" not in self.data:
            self.data["members"] = []
        if "notification_groups" not in self.data:
            self.data["notification_groups"] = {}
        if "last_check" not in self.data:
            self.data["last_check"] = {}
            
    def load_json(self, file_path: str, default_value: Any) -> Dict:
        """从文件加载JSON数据，如果文件不存在则返回默认值"""
        if not os.path.exists(file_path):
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            # 写入默认值
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(default_value, f, ensure_ascii=False, indent=2)
            return default_value
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"加载JSON文件 {file_path} 失败: {e}")
            return default_value
            
    def save_json(self) -> None:
        """保存数据到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
                
            logger.debug(f"B站插件数据保存成功")
        except Exception as e:
            logger.error(f"保存JSON文件 {self.data_file} 失败: {e}")
    
    def is_member(self, user_id: str) -> bool:
        """检查用户是否是会员"""
        return user_id in self.data["members"]
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        nickname = event.get('sender', {}).get('nickname', '用户')
        message = event.get('raw_message', '')
        
        # 先尝试处理管理员命令
        if await self.handle_admin_command(event):
            return True
            
        # 检查是否是哔哩哔哩小程序分享卡片
        if '[CQ:json' in message and 'com.tencent.miniapp_01' in message and 'appid":"1109937557"' in message:
            logger.info(f"检测到B站分享卡片消息，来自: {user_id}")
            return await self._handle_bilibili_card(event)
        
        # 获取机器人QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否是@机器人的消息
        if not is_at_bot(event, bot_qq):
            return False
            
        # 提取命令
        command = extract_command(event, bot_qq)
        if not command.startswith("/bili."):
            return False
            
        # 处理各种命令
        for cmd, pattern in self.command_patterns.items():
            is_at_command, match, _ = handle_at_command(event, self.bot, pattern)
            if is_at_command and match:
                logger.info(f"接收到B站插件命令: {cmd}, 来自: {user_id}")
                
                # 会员专享功能检查
                if cmd in ['sub', 'unsub', 'subs', 'hot'] and not self.is_member(user_id):
                    await self.bot.send_msg(
                        message_type=message_type,
                        user_id=int(user_id) if message_type == 'private' else None,
                        group_id=int(group_id) if message_type == 'group' else None,
                        message=f"抱歉，{cmd}是会员专享功能，开通会员后即可使用！"
                    )
                    return True
                
                # 执行对应的命令处理函数
                handler = getattr(self, f"_handle_{cmd}", None)
                if handler:
                    return await handler(event, match)
                    
        return False
        
    async def _handle_bilibili_card(self, event: Dict[str, Any]) -> bool:
        """处理哔哩哔哩小程序分享卡片"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)
        message = event.get('raw_message', '')
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        try:
            # 从卡片中提取视频信息
            import re
            import json
            import html
            
            # 提取JSON数据
            json_match = re.search(r'\[CQ:json,data=(.+?)\]', message)
            if not json_match:
                return False
                
            # 解码HTML实体
            json_str = html.unescape(json_match.group(1))
            
            try:
                # 解析JSON数据
                json_data = json.loads(json_str)
                
                # 检查是否为B站小程序
                if "meta" in json_data and "detail_1" in json_data["meta"]:
                    detail = json_data["meta"]["detail_1"]
                    
                    # 检查是否为哔哩哔哩
                    if detail.get("appid") == "1109937557":
                        title = detail.get("title", "未知视频")
                        desc = detail.get("desc", "无描述")
                        url = detail.get("qqdocurl", "")
                        
                        # 从url中提取视频ID
                        bv_match = re.search(r'BV\w+', url)
                        if bv_match:
                            bvid = bv_match.group(0)
                            logger.info(f"从B站卡片中提取到视频BV号: {bvid}")
                            
                            # 使用提取到的BV号获取视频详细信息
                            await self._get_and_send_video_info(bvid, event)
                            return True
                        else:
                            # 如果没有找到BV号，可能是短链接，需要进一步处理
                            if "b23.tv" in url:
                                logger.info(f"检测到B站短链接: {url}")
                                # 请求短链接获取重定向后的实际URL
                                async with aiohttp.ClientSession() as session:
                                    async with session.get(url, allow_redirects=True) as resp:
                                        final_url = str(resp.url)
                                        logger.info(f"短链接解析结果: {final_url}")
                                        
                                        # 从重定向后的URL中提取BV号
                                        bv_match = re.search(r'BV\w+', final_url)
                                        if bv_match:
                                            bvid = bv_match.group(0)
                                            logger.info(f"从短链接中提取到视频BV号: {bvid}")
                                            
                                            # 使用提取到的BV号获取视频详细信息
                                            await self._get_and_send_video_info(bvid, event)
                                            return True
                            
                            # 如果无法提取视频ID，则返回原始信息
                            await self.bot.send_msg(
                                message_type=message_type,
                                user_id=int(user_id) if message_type == 'private' else None,
                                group_id=int(group_id) if message_type == 'group' else None,
                                message=f"{reply_code}检测到B站视频分享: {title}\n{desc}\n无法解析视频ID，请使用原始链接查看"
                            )
                            return True
            except json.JSONDecodeError as e:
                logger.error(f"解析B站卡片JSON失败: {e}")
                return False
                
        except Exception as e:
            logger.error(f"处理B站卡片消息失败: {e}", exc_info=True)
            return False
            
        return False
        
    async def _get_and_send_video_info(self, bvid: str, event: Dict[str, Any]) -> None:
        """获取并发送视频信息"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 添加请求头以模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://www.bilibili.com'
        }
        
        try:
            # 尝试获取视频信息，重试最多3次
            max_retries = 3
            retry_count = 0
            video_info = None
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                        logger.info(f"正在请求B站视频API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                retry_count += 1
                                await asyncio.sleep(1)
                                continue
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                retry_count += 1
                                await asyncio.sleep(1)
                                continue
                                
                            video_info = data["data"]
                            break
                except Exception as e:
                    logger.error(f"请求B站视频API失败: {e}")
                    retry_count += 1
                    await asyncio.sleep(1)
                    
            if not video_info:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}获取视频信息失败，请稍后重试"
                )
                return
                
            # 提取视频信息
            title = video_info["title"]
            cover = video_info["pic"]
            up_name = video_info["owner"]["name"]
            up_uid = video_info["owner"]["mid"]
            desc = video_info.get("desc", "").split("\n")[0][:50] + "..." if video_info.get("desc", "") else "无简介"
            duration = video_info.get("duration", 0)
            view_count = video_info["stat"]["view"]
            danmaku_count = video_info["stat"]["danmaku"]
            reply_count = video_info["stat"]["reply"]
            like_count = video_info["stat"]["like"]
            coin_count = video_info["stat"]["coin"]
            favorite_count = video_info["stat"]["favorite"]
            share_count = video_info["stat"]["share"]
            
            # 将秒数转换为分:秒格式
            duration_str = f"{duration // 60}:{duration % 60:02d}"
            
            # 构建响应消息
            cover_img = f"[CQ:image,file={cover}]"
            message = f"{reply_code}{cover_img}\n"
            message += f"标题: {title}\n"
            message += f"UP主: {up_name} (UID: {up_uid})\n"
            message += f"时长: {duration_str}\n"
            message += f"播放: {view_count} | 弹幕: {danmaku_count}\n"
            message += f"点赞: {like_count} | 投币: {coin_count} | 收藏: {favorite_count}\n"
            message += f"简介: {desc}\n"
            message += f"链接: https://www.bilibili.com/video/{bvid}"
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=message
            )
            
        except Exception as e:
            logger.error(f"获取B站视频信息失败: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}获取视频信息失败: {str(e)}"
            )
    
    async def _handle_bind(self, event: Dict[str, Any], match) -> bool:
        """处理绑定账号命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        uid = match.group(1)
        
        # 检查是否已经绑定
        if user_id in self.data["bindings"]:
            old_uid = self.data["bindings"][user_id].get("uid", "未知")
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}您已绑定B站账号(UID: {old_uid})，如需重新绑定，请先解绑。"
            )
            return True
        
        # 获取账号信息
        try:
            # 添加请求头以模拟浏览器访问
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://space.bilibili.com/',
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': 'https://space.bilibili.com'
            }
            
            # 尝试获取用户信息，增加重试机制
            max_retries = 3
            retry_count = 0
            user_info = None
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        # 使用v2的API，无需签名
                        api_url = f"{self.api_base}/x/space/acc/info?mid={uid}"
                        logger.info(f"正在请求B站API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                logger.error(f"获取账号信息失败，HTTP状态码: {resp.status}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)  # 等待1秒后重试
                                    continue
                                else:
                                    await self.bot.send_msg(
                                        message_type=message_type,
                                        user_id=int(user_id) if message_type == 'private' else None,
                                        group_id=int(group_id) if message_type == 'group' else None,
                                        message=f"{reply_code}获取账号信息失败，请检查UID是否正确或稍后再试。"
                                    )
                                    return True
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                logger.error(f"获取账号信息失败，API返回错误: {data['message']}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)  # 等待1秒后重试
                                    continue
                                else:
                                    await self.bot.send_msg(
                                        message_type=message_type,
                                        user_id=int(user_id) if message_type == 'private' else None,
                                        group_id=int(group_id) if message_type == 'group' else None,
                                        message=f"{reply_code}获取账号信息失败：{data['message']}"
                                    )
                                    return True
                            
                            user_info = data["data"]
                            break  # 成功获取数据，跳出循环
                            
                except aiohttp.ClientError as e:
                    logger.error(f"请求B站API时发生网络错误: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"正在进行第{retry_count+1}次重试...")
                        await asyncio.sleep(1)  # 等待1秒后重试
                    else:
                        await self.bot.send_msg(
                            message_type=message_type,
                            user_id=int(user_id) if message_type == 'private' else None,
                            group_id=int(group_id) if message_type == 'group' else None,
                            message=f"{reply_code}网络连接错误，请稍后再试: {str(e)}"
                        )
                        return True
            
            # 如果成功获取用户信息
            if user_info:
                # 保存账号信息
                self.data["bindings"][user_id] = {
                    "uid": uid,
                    "username": user_info["name"],
                    "face": user_info["face"],
                    "level": user_info["level"],
                    "sign": user_info["sign"],
                    "bind_time": int(time.time())
                }
                self.save_json()
                
                # 发送成功消息
                avatar = f"[CQ:image,file={user_info['face']}]"
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}绑定成功！\n{avatar}\nUID: {uid}\n用户名: {user_info['name']}\n等级: {user_info['level']}"
                )
                
                return True
            else:
                # 如果所有重试都失败了
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}绑定失败，无法获取用户信息，请稍后再试。"
                )
                return True
                
        except Exception as e:
            logger.error(f"绑定B站账号失败: {e}")
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}绑定失败: {str(e)}"
            )
            return True
    
    async def _handle_unbind(self, event: Dict[str, Any], match) -> bool:
        """处理解绑账号命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 检查是否已经绑定
        if user_id not in self.data["bindings"]:
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}您尚未绑定B站账号。"
            )
            return True
        
        # 保存绑定信息用于显示
        old_binding = self.data["bindings"][user_id].copy()
        
        # 解除绑定
        del self.data["bindings"][user_id]
        
        # 同时删除该用户的所有订阅
        if user_id in self.data["subscriptions"]:
            del self.data["subscriptions"][user_id]
        
        # 保存数据
        self.save_json()
        
        # 发送成功消息
        await self.bot.send_msg(
            message_type=message_type,
            user_id=int(user_id) if message_type == 'private' else None,
            group_id=int(group_id) if message_type == 'group' else None,
            message=f"{reply_code}解绑成功！您已解除与B站账号 {old_binding.get('username', '未知')}(UID: {old_binding.get('uid', '未知')}) 的绑定。"
        )
        
        return True
    
    async def _handle_info(self, event: Dict[str, Any], match) -> bool:
        """处理查看账号信息命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 检查是否已经绑定
        if user_id not in self.data["bindings"]:
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}您尚未绑定B站账号，请使用 /bili.bind <UID> 进行绑定。"
            )
            return True
        
        binding = self.data["bindings"][user_id]
        
        # 添加请求头以模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://space.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://space.bilibili.com'
        }
        
        try:
            uid = binding.get("uid", "")
            if not uid:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}绑定信息不完整，请重新绑定账号。"
                )
                return True
            
            # 检查是否有cookie，如果有优先使用cookie获取信息
            if "cookies" in binding:
                # 使用cookie获取个人信息
                user_info = await self._get_user_info(binding["cookies"])
                if user_info:
                    # 更新绑定信息
                    binding["uid"] = str(user_info.get("mid", uid))
                    binding["username"] = user_info.get("name", binding.get("username", "未知"))
                    binding["face"] = user_info.get("face", binding.get("face", ""))
                    binding["level"] = user_info.get("level", binding.get("level", 0))
                    binding["coins"] = user_info.get("coins", 0)
                    binding["sign"] = user_info.get("sign", binding.get("sign", ""))
                    binding["last_update"] = int(time.time())
                    self.save_json()
            
            # 尝试获取最新的用户信息，重试最多3次
            user_info = None
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = f"{self.api_base}/x/space/acc/info?mid={uid}"
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                retry_count += 1
                                if retry_count < max_retries:
                                    await asyncio.sleep(1)
                                    continue
                                break
                                
                            data = await resp.json()
                            if data["code"] == 0:
                                user_info = data["data"]
                                # 更新绑定信息
                                binding["username"] = user_info["name"]
                                binding["face"] = user_info["face"]
                                binding["level"] = user_info["level"]
                                binding["sign"] = user_info["sign"]
                                binding["last_update"] = int(time.time())
                                self.save_json()
                                break
                            else:
                                retry_count += 1
                                if retry_count < max_retries:
                                    await asyncio.sleep(1)
                                    continue
                                break
                except Exception as e:
                    logger.error(f"获取B站用户信息失败: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        await asyncio.sleep(1)
                        continue
                    break
            
            # 构建并发送响应消息
            # 无论API是否成功，都显示本地保存的信息
            username = binding.get("username", "未知")
            uid = binding.get("uid", "未知")
            level = binding.get("level", "未知")
            coins = binding.get("coins", "未知") if "coins" in binding else "未知"
            sign = binding.get("sign", "无")
            face = binding.get("face", "")
            bind_time = binding.get("bind_time", 0)
            last_update = binding.get("last_update", 0)
            
            bind_time_str = datetime.fromtimestamp(bind_time).strftime("%Y-%m-%d %H:%M:%S") if bind_time else "未知"
            last_update_str = datetime.fromtimestamp(last_update).strftime("%Y-%m-%d %H:%M:%S") if last_update else "未知"
            
            # 添加头像
            avatar = f"[CQ:image,file={face}]" if face else ""
            
            message = f"{reply_code}您的B站账号信息:\n{avatar}\n"
            message += f"用户名: {username}\n"
            message += f"UID: {uid}\n"
            message += f"等级: {level}\n"
            if coins != "未知":
                message += f"硬币: {coins}\n"
            message += f"签名: {sign}\n"
            message += f"绑定时间: {bind_time_str}\n"
            message += f"最后更新: {last_update_str}"
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=message
            )
            
        except Exception as e:
            logger.error(f"处理B站账号信息查询失败: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}获取账号信息失败: {str(e)}"
            )
        
        return True

    async def _handle_up(self, event: Dict[str, Any], match) -> bool:
        """处理查询UP主信息命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        up_identifier = match.group(1).strip()
        
        # 添加请求头以模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://space.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://space.bilibili.com'
        }
        
        # 检查是否是UID还是用户名
        uid = None
        if up_identifier.isdigit():
            # 是UID
            uid = up_identifier
        else:
            # 是用户名，需要搜索
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}正在搜索UP主：{up_identifier}..."
            )
            
            # 搜索用户名
            try:
                search_url = "https://api.bilibili.com/x/web-interface/search/type"
                params = {
                    "search_type": "bili_user",
                    "keyword": up_identifier
                }
                
                max_retries = 2
                retry_count = 0
                
                while retry_count < max_retries:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(search_url, params=params, headers=headers) as resp:
                                if resp.status != 200:
                                    logger.warning(f"搜索UP主失败，HTTP状态码: {resp.status}")
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        logger.info(f"正在进行第{retry_count+1}次重试...")
                                        await asyncio.sleep(1)
                                        continue
                                    else:
                                        await self.bot.send_msg(
                                            message_type=message_type,
                                            user_id=int(user_id) if message_type == 'private' else None,
                                            group_id=int(group_id) if message_type == 'group' else None,
                                            message=f"{reply_code}搜索UP主失败，请稍后再试。"
                                        )
                                        return True
                                
                                data = await resp.json()
                                if data["code"] != 0:
                                    logger.warning(f"搜索UP主失败，API返回错误: {data['message']}")
                                    retry_count += 1
                                    if retry_count < max_retries:
                                        logger.info(f"正在进行第{retry_count+1}次重试...")
                                        await asyncio.sleep(1)
                                        continue
                                    else:
                                        await self.bot.send_msg(
                                            message_type=message_type,
                                            user_id=int(user_id) if message_type == 'private' else None,
                                            group_id=int(group_id) if message_type == 'group' else None,
                                            message=f"{reply_code}搜索UP主失败：{data['message']}"
                                        )
                                        return True
                                
                                result = data["data"]["result"]
                                if not result:
                                    await self.bot.send_msg(
                                        message_type=message_type,
                                        user_id=int(user_id) if message_type == 'private' else None,
                                        group_id=int(group_id) if message_type == 'group' else None,
                                        message=f"{reply_code}未找到UP主：{up_identifier}"
                                    )
                                    return True
                                
                                # 取第一个结果
                                uid = result[0]["mid"]
                                break
                    except aiohttp.ClientError as e:
                        logger.error(f"搜索UP主时发生网络错误: {e}")
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.info(f"正在进行第{retry_count+1}次重试...")
                            await asyncio.sleep(1)
                        else:
                            await self.bot.send_msg(
                                message_type=message_type,
                                user_id=int(user_id) if message_type == 'private' else None,
                                group_id=int(group_id) if message_type == 'group' else None,
                                message=f"{reply_code}网络连接错误，请稍后再试: {str(e)}"
                            )
                            return True
            except Exception as e:
                logger.error(f"搜索UP主失败: {e}")
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}搜索UP主失败: {str(e)}"
                )
                return True
                
        # 如果没有找到UID，则返回错误
        if not uid:
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}获取UP主信息失败，未找到有效UID。"
            )
            return True
            
        # 获取UP主信息
        try:
            max_retries = 2
            retry_count = 0
            user_info = None
            stat_info = None
            upstat_info = None
            
            # 获取基本信息
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        # 获取用户基本信息
                        api_url = f"{self.api_base}/x/space/acc/info?mid={uid}"
                        logger.info(f"正在请求B站UP主信息API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                logger.warning(f"获取UP主信息失败，HTTP状态码: {resp.status}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    await self.bot.send_msg(
                                        message_type=message_type,
                                        user_id=int(user_id) if message_type == 'private' else None,
                                        group_id=int(group_id) if message_type == 'group' else None,
                                        message=f"{reply_code}获取UP主信息失败，请稍后再试。"
                                    )
                                    return True
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                logger.warning(f"获取UP主信息失败，API返回错误: {data['message']}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    await self.bot.send_msg(
                                        message_type=message_type,
                                        user_id=int(user_id) if message_type == 'private' else None,
                                        group_id=int(group_id) if message_type == 'group' else None,
                                        message=f"{reply_code}获取UP主信息失败：{data['message']}"
                                    )
                                    return True
                            
                            user_info = data["data"]
                            break
                except aiohttp.ClientError as e:
                    logger.error(f"请求B站API时发生网络错误: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"正在进行第{retry_count+1}次重试...")
                        await asyncio.sleep(1)
                    else:
                        await self.bot.send_msg(
                            message_type=message_type,
                            user_id=int(user_id) if message_type == 'private' else None,
                            group_id=int(group_id) if message_type == 'group' else None,
                            message=f"{reply_code}网络连接错误，请稍后再试: {str(e)}"
                        )
                        return True
            
            # 获取关注和粉丝数据
            retry_count = 0
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = f"{self.api_base}/x/relation/stat?vmid={uid}"
                        logger.info(f"正在请求B站UP主关系信息API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                logger.warning(f"获取UP主关系数据失败，HTTP状态码: {resp.status}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    stat_info = {"following": "获取失败", "follower": "获取失败"}
                                    break
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                logger.warning(f"获取UP主关系数据失败，API返回错误: {data['message']}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    stat_info = {"following": "获取失败", "follower": "获取失败"}
                                    break
                            
                            stat_info = data["data"]
                            break
                except aiohttp.ClientError as e:
                    logger.error(f"请求B站关系API时发生网络错误: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"正在进行第{retry_count+1}次重试...")
                        await asyncio.sleep(1)
                    else:
                        stat_info = {"following": "获取失败", "follower": "获取失败"}
                        break
            
            # 获取UP主数据状态
            retry_count = 0
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = f"{self.api_base}/x/space/upstat?mid={uid}"
                        logger.info(f"正在请求B站UP主状态信息API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                logger.warning(f"获取UP主状态数据失败，HTTP状态码: {resp.status}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    upstat_info = {"archive": {"view": "获取失败"}, "article": {"view": "获取失败"}}
                                    break
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                logger.warning(f"获取UP主状态数据失败，API返回错误: {data['message']}")
                                retry_count += 1
                                if retry_count < max_retries:
                                    logger.info(f"正在进行第{retry_count+1}次重试...")
                                    await asyncio.sleep(1)
                                    continue
                                else:
                                    upstat_info = {"archive": {"view": "获取失败"}, "article": {"view": "获取失败"}}
                                    break
                            
                            upstat_info = data["data"]
                            break
                except aiohttp.ClientError as e:
                    logger.error(f"请求B站状态API时发生网络错误: {e}")
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.info(f"正在进行第{retry_count+1}次重试...")
                        await asyncio.sleep(1)
                    else:
                        upstat_info = {"archive": {"view": "获取失败"}, "article": {"view": "获取失败"}}
                        break
            
            # 生成信息消息
            if not user_info:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}获取UP主信息失败，请稍后再试。"
                )
                return True
            
            # 格式化数据
            following = stat_info.get("following", "获取失败") if stat_info else "获取失败"
            follower = stat_info.get("follower", "获取失败") if stat_info else "获取失败"
            video_view = upstat_info.get("archive", {}).get("view", "获取失败") if upstat_info else "获取失败"
            article_view = upstat_info.get("article", {}).get("view", "获取失败") if upstat_info else "获取失败"
            
            # 发送消息
            avatar = f"[CQ:image,file={user_info['face']}]"
            message = f"{reply_code}UP主信息：\n"
            message += f"{avatar}\n"
            message += f"用户名: {user_info['name']}\n"
            message += f"UID: {user_info['mid']}\n"
            message += f"性别: {user_info.get('sex', '未知')}\n"
            message += f"等级: {user_info.get('level', '未知')}\n"
            message += f"签名: {user_info.get('sign', '无')}\n"
            message += f"关注数: {following}\n"
            message += f"粉丝数: {follower}\n"
            message += f"视频播放量: {video_view}\n"
            message += f"专栏阅读量: {article_view}\n"
            
            if user_info.get("vip", {}).get("status") == 1:
                vip_type = user_info.get("vip", {}).get("type", 0)
                vip_label = "大会员" if vip_type == 2 else "会员"
                message += f"会员状态: {vip_label}\n"
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=message
            )
            
            return True
            
        except Exception as e:
            logger.error(f"查询UP主信息失败: {e}")
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}查询UP主信息失败: {str(e)}"
            )
            return True
    
    async def _handle_video(self, event: Dict[str, Any], match) -> bool:
        """处理查询视频信息命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        bvid = match.group(1).strip()
        
        # 处理可能的BV号前缀
        if bvid.lower().startswith("bv"):
            bvid = bvid
        else:
            bvid = "BV" + bvid
            
        # 添加请求头以模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://www.bilibili.com'
        }
        
        try:
            # 尝试获取视频信息，重试最多3次
            max_retries = 3
            retry_count = 0
            video_info = None
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
                        logger.info(f"正在请求B站视频API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                retry_count += 1
                                await asyncio.sleep(1)
                                continue
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                retry_count += 1
                                await asyncio.sleep(1)
                                continue
                                
                            video_info = data["data"]
                            break
                except Exception as e:
                    logger.error(f"请求B站视频API失败: {e}")
                    retry_count += 1
                    await asyncio.sleep(1)
                    
            if not video_info:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}获取视频信息失败，请稍后重试"
                )
                return True
                    
            # 提取视频信息
            title = video_info["title"]
            cover = video_info["pic"]
            up_name = video_info["owner"]["name"]
            up_uid = video_info["owner"]["mid"]
            desc = video_info.get("desc", "").split("\n")[0][:50] + "..." if video_info.get("desc", "") else "无简介"
            duration = video_info.get("duration", 0)
            view_count = video_info["stat"]["view"]
            danmaku_count = video_info["stat"]["danmaku"]
            reply_count = video_info["stat"]["reply"]
            like_count = video_info["stat"]["like"]
            coin_count = video_info["stat"]["coin"]
            favorite_count = video_info["stat"]["favorite"]
            share_count = video_info["stat"]["share"]
            
            # 将秒数转换为分:秒格式
            duration_str = f"{duration // 60}:{duration % 60:02d}"
            
            # 构建响应消息
            cover_img = f"[CQ:image,file={cover}]"
            message = f"{reply_code}{cover_img}\n"
            message += f"标题: {title}\n"
            message += f"UP主: {up_name} (UID: {up_uid})\n"
            message += f"时长: {duration_str}\n"
            message += f"播放: {view_count} | 弹幕: {danmaku_count}\n"
            message += f"点赞: {like_count} | 投币: {coin_count} | 收藏: {favorite_count}\n"
            message += f"简介: {desc}\n"
            message += f"链接: https://www.bilibili.com/video/{bvid}"
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=message
            )
            
        except Exception as e:
            logger.error(f"获取B站视频信息失败: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}获取视频信息失败: {str(e)}"
            )
        
        return True

    async def _handle_sub(self, event: Dict[str, Any], match) -> bool:
        """处理订阅UP主命令（会员专享）"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        
        # 获取查询参数
        query = match.group(1).strip()
        
        try:
            # 判断是UID还是用户名
            uid = None
            up_name = None
            if query.isdigit():
                uid = query
                # 获取UP主名称
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.api_base}/x/space/acc/info?mid={uid}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data["code"] == 0:
                                up_name = data["data"]["name"]
                            else:
                                await self.bot.send_msg(
                                    message_type=message_type,
                                    user_id=int(user_id) if message_type == 'private' else None,
                                    group_id=int(group_id) if message_type == 'group' else None,
                                    message=f"未找到UID为 {query} 的UP主"
                                )
                                return True
                        else:
                            await self.bot.send_msg(
                                message_type=message_type,
                                user_id=int(user_id) if message_type == 'private' else None,
                                group_id=int(group_id) if message_type == 'group' else None,
                                message="获取UP主信息失败，请稍后重试"
                            )
                            return True
            else:
                # 通过用户名搜索
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.api_base}/x/web-interface/search/type?search_type=bili_user&keyword={query}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data["code"] == 0 and data["data"]["result"]:
                                # 取第一个结果
                                uid = data["data"]["result"][0]["mid"]
                                up_name = data["data"]["result"][0]["uname"]
                            else:
                                await self.bot.send_msg(
                                    message_type=message_type,
                                    user_id=int(user_id) if message_type == 'private' else None,
                                    group_id=int(group_id) if message_type == 'group' else None,
                                    message=f"未找到名为 {query} 的UP主"
                                )
                                return True
                        else:
                            await self.bot.send_msg(
                                message_type=message_type,
                                user_id=int(user_id) if message_type == 'private' else None,
                                group_id=int(group_id) if message_type == 'group' else None,
                                message="搜索UP主失败，请稍后重试"
                            )
                            return True
            
            # 确保订阅列表存在
            if user_id not in self.data["subscriptions"]:
                self.data["subscriptions"][user_id] = []
                
            # 检查是否已订阅
            for sub in self.data["subscriptions"][user_id]:
                if str(sub["up_uid"]) == str(uid):
                    await self.bot.send_msg(
                        message_type=message_type,
                        user_id=int(user_id) if message_type == 'private' else None,
                        group_id=int(group_id) if message_type == 'group' else None,
                        message=f"您已订阅UP主: {up_name}({uid})，无需重复订阅"
                    )
                    return True
            
            # 添加订阅
            self.data["subscriptions"][user_id].append({
                "up_uid": uid,
                "up_name": up_name,
                "sub_time": int(time.time()),
                "last_video": None,  # 最新视频BV号
                "last_live": False,  # 是否正在直播
            })
            
            # 初始化最近检查时间
            if uid not in self.data["last_check"]:
                self.data["last_check"][uid] = int(time.time())
                
            # 保存数据
            self.save_json()
            
            # 如果是群聊且该群未启用通知，则提示用户
            if message_type == 'group':
                if group_id not in self.data["notification_groups"] or not self.data["notification_groups"][group_id].get("enabled", False):
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=int(group_id),
                        message=f"订阅成功！UP主: {up_name}({uid})\n注意：当前群未开启B站通知功能，管理员可使用 /bili.notify on 开启"
                    )
                    return True
            
            # 发送成功消息
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"订阅成功！UP主: {up_name}({uid})"
            )
            
            # 启动订阅检查任务(如果还未启动)
            self.start_check_task()
            
        except Exception as e:
            logger.error(f"订阅UP主失败: {e}")
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"订阅UP主失败: {str(e)}"
            )
        
        return True
    
    async def _handle_unsub(self, event: Dict[str, Any], match) -> bool:
        """处理取消订阅UP主命令（会员专享）"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        
        # 获取查询参数
        query = match.group(1).strip()
        
        # 检查用户是否有订阅
        if user_id not in self.data["subscriptions"] or not self.data["subscriptions"][user_id]:
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message="您当前没有订阅任何UP主"
            )
            return True
        
        try:
            # 判断是UID还是用户名
            up_found = False
            up_index = -1
            
            if query.isdigit():
                # 按UID查找
                for i, sub in enumerate(self.data["subscriptions"][user_id]):
                    if str(sub["up_uid"]) == str(query):
                        up_found = True
                        up_index = i
                        break
            else:
                # 按名称查找
                for i, sub in enumerate(self.data["subscriptions"][user_id]):
                    if query.lower() in sub["up_name"].lower():
                        up_found = True
                        up_index = i
                        break
            
            if not up_found:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"未找到您订阅的UP主: {query}"
                )
                return True
            
            # 获取待取消的UP主信息
            target_up = self.data["subscriptions"][user_id][up_index]
            
            # 移除订阅
            self.data["subscriptions"][user_id].pop(up_index)
            
            # 如果该用户没有订阅了，删除该键
            if not self.data["subscriptions"][user_id]:
                del self.data["subscriptions"][user_id]
            
            # 保存数据
            self.save_json()
            
            # 发送成功消息
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"已取消订阅UP主: {target_up['up_name']}({target_up['up_uid']})"
            )
            
        except Exception as e:
            logger.error(f"取消订阅UP主失败: {e}")
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"取消订阅UP主失败: {str(e)}"
            )
        
        return True
    
    async def _handle_subs(self, event: Dict[str, Any], match) -> bool:
        """处理查看订阅列表命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 检查是否已经绑定
        if user_id not in self.data["bindings"]:
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}您尚未绑定B站账号，请先使用 /bili.bind <UID> 或 /bili.login 进行绑定。"
            )
            return True
        
        # 获取订阅列表
        if user_id not in self.data["subscriptions"] or not self.data["subscriptions"][user_id]:
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}您当前没有订阅任何UP主"
            )
            return True
        
        # 构建订阅列表消息
        subs = self.data["subscriptions"][user_id]
        subs_count = len(subs)
        subs_text = "\n".join([f"{i+1}. {sub['up_name']} (UID: {sub['up_uid']})" for i, sub in enumerate(subs)])
        message = f"{reply_code}您当前订阅了 {subs_count} 个UP主:\n{subs_text}"
        
        await self.bot.send_msg(
            message_type=message_type,
            user_id=int(user_id) if message_type == 'private' else None,
            group_id=int(group_id) if message_type == 'group' else None,
            message=message
        )
        
        return True
    
    async def _handle_hot(self, event: Dict[str, Any], match) -> bool:
        """处理获取热门推送命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 添加请求头以模拟浏览器访问
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://www.bilibili.com'
        }
        
        try:
            # 尝试获取热门视频，最多重试3次
            max_retries = 3
            retry_count = 0
            hot_videos = None
            
            while retry_count < max_retries:
                try:
                    async with aiohttp.ClientSession() as session:
                        api_url = "https://api.bilibili.com/x/web-interface/popular"
                        logger.info(f"正在请求B站热门API: {api_url}")
                        
                        async with session.get(api_url, headers=headers) as resp:
                            if resp.status != 200:
                                retry_count += 1
                                await asyncio.sleep(1)
                                continue
                            
                            data = await resp.json()
                            if data["code"] != 0:
                                retry_count += 1
                                await asyncio.sleep(1)
                                continue
                                
                            hot_videos = data["data"]["list"][:5]  # 只取前5个热门视频
                            break
                            
                except Exception as e:
                    logger.error(f"请求B站热门API失败: {e}")
                    retry_count += 1
                    await asyncio.sleep(1)
            
            if not hot_videos:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}获取热门视频失败，请稍后重试"
                )
                return True
                    
            # 生成热门视频推送消息
            message = f"{reply_code}B站热门视频推送（TOP 5）:\n\n"
            
            for i, video in enumerate(hot_videos):
                title = video["title"]
                bvid = video["bvid"]
                author = video["owner"]["name"]
                play_count = video["stat"]["view"]
                
                message += f"{i+1}. {title}\n"
                message += f"   UP主: {author}\n"
                message += f"   播放: {play_count}\n"
                message += f"   链接: https://www.bilibili.com/video/{bvid}\n\n"
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=message
            )
            
        except Exception as e:
            logger.error(f"获取B站热门视频失败: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}获取热门视频失败: {str(e)}"
            )
        
        return True
    
    async def _handle_help(self, event: Dict[str, Any], match) -> bool:
        """处理帮助命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 帮助信息
        help_text = """B站插件命令帮助:
基础功能:
/bili.bind <UID> - 绑定B站账号
/bili.login - B站扫码登录（推荐）
/bili.unbind - 解绑B站账号
/bili.info - 查看已绑定的账号信息
/bili.up <UID或用户名> - 查询UP主信息
/bili.video <BV号> - 查询视频信息

会员专享功能:
/bili.sub <UID或用户名> - 订阅UP主更新和开播通知
/bili.unsub <UID或用户名> - 取消订阅
/bili.subs - 查看订阅列表
/bili.hot - 获取B站热门推送"""
        
        # 发送回复
        await self.bot.send_msg(
            message_type=message_type,
            user_id=int(user_id) if message_type == 'private' else None,
            group_id=int(group_id) if message_type == 'group' else None,
            message=f"{reply_code}{help_text}"
        )
        
        return True

    async def _handle_login(self, event: Dict[str, Any], match) -> bool:
        """处理扫码登录命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 告知用户开始生成二维码
        await self.bot.send_msg(
            message_type=message_type,
            user_id=int(user_id) if message_type == 'private' else None,
            group_id=int(group_id) if message_type == 'group' else None,
            message=f"{reply_code}正在生成B站登录二维码，请稍等..."
        )
        
        temp_file_path = None
                
        try:
            # 获取B站二维码
            qrcode_data = await self._get_bilibili_qrcode()
            if not qrcode_data:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"{reply_code}获取登录二维码失败，请稍后再试。"
                )
                return True
            
            qrcode_url = qrcode_data['url']
            qrcode_key = qrcode_data['qrcode_key']
            
            # 确保临时目录存在
            temp_dir = os.path.join("resources", "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            # 生成二维码图片
            img = qrcode.make(qrcode_url)
            temp_file_path = os.path.join(temp_dir, f"bilibili_login_{user_id}.png")
            
            # 保存图片 (以二进制方式打开文件)
            with open(temp_file_path, 'wb') as f:
                img.save(f)
            
            # 发送二维码图片和说明
            message = (
                f"{reply_code}请使用B站APP扫描下方二维码登录：\n"
                f"[CQ:image,file=file:///{os.path.abspath(temp_file_path)}]\n"
                f"二维码有效期为3分钟，扫码后请在手机上确认登录。"
            )
            
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=message
            )
            
            # 开始轮询登录状态
            cookies = await self._poll_login_status(qrcode_key, user_id, message_type, group_id, message_id)
            if cookies:
                # 登录成功，保存cookies
                self.data["bindings"][user_id] = {
                    "cookies": cookies,
                    "last_update": int(time.time()),
                    "bind_time": int(time.time())  # 添加绑定时间
                }
                self.save_json()
                
                # 获取账号信息并绑定
                user_info = await self._get_user_info(cookies)
                if user_info:
                    uid = user_info.get("mid", "")
                    username = user_info.get("name", "")
                    if uid:
                        self.data["bindings"][user_id]["uid"] = str(uid)
                        self.data["bindings"][user_id]["username"] = username
                        self.data["bindings"][user_id]["face"] = user_info.get("face", "")
                        self.save_json()
            
            return True
            
        except Exception as e:
            logger.error(f"B站扫码登录出错: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}登录过程中出现错误: {str(e)}"
            )
            return True
        finally:
            # 清理临时文件
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.error(f"删除临时二维码文件失败: {e}")
    
    async def _get_bilibili_qrcode(self) -> Dict[str, Any]:
        """获取B站登录二维码"""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Referer': 'https://www.bilibili.com/',
                }
                
                api_url = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
                async with session.get(api_url, headers=headers) as resp:
                    resp_json = await resp.json()
                    if resp_json['code'] == 0:
                        return resp_json['data']
                    else:
                        logger.error(f"获取B站登录二维码失败: {resp_json}")
                        return {}
        except Exception as e:
            logger.error(f"获取B站登录二维码异常: {e}", exc_info=True)
            return {}
    
    async def _poll_login_status(self, qrcode_key: str, user_id: str, message_type: str, 
                                group_id: str, message_id: int) -> Dict[str, str]:
        """轮询登录状态"""
        reply_code = f"[CQ:reply,id={message_id}]"
        try:
            max_tries = 18  # 3分钟超时 (10秒一次轮询)
            for i in range(max_tries):
                async with aiohttp.ClientSession() as session:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Referer': 'https://www.bilibili.com/',
                    }
                    
                    api_url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}"
                    async with session.get(api_url, headers=headers) as resp:
                        resp_json = await resp.json()
                        if resp_json['code'] == 0:
                            data = resp_json['data']
                            code = data.get('code', -1)
                            
                            # 0: 扫码登录成功
                            if code == 0:
                                # 提取cookies
                                cookies = {}
                                url = data.get('url', '')
                                for item in ["DedeUserID", "DedeUserID__ckMd5", "SESSDATA", "bili_jct", "sid"]:
                                    value = self._extract_cookie_value(url, item)
                                    if value:
                                        cookies[item] = value
                                
                                await self.bot.send_msg(
                                    message_type=message_type,
                                    user_id=int(user_id) if message_type == 'private' else None,
                                    group_id=int(group_id) if message_type == 'group' else None,
                                    message=f"{reply_code}登录成功！您已成功绑定B站账号。"
                                )
                                return cookies
                            
                            # 86038: 二维码已失效
                            elif code == 86038:
                                await self.bot.send_msg(
                                    message_type=message_type,
                                    user_id=int(user_id) if message_type == 'private' else None,
                                    group_id=int(group_id) if message_type == 'group' else None,
                                    message=f"{reply_code}二维码已失效，请重新发送 /bili.login 获取新的二维码。"
                                )
                                return {}
                            
                            # 86090: 二维码已扫码未确认
                            elif code == 86090:
                                await self.bot.send_msg(
                                    message_type=message_type,
                                    user_id=int(user_id) if message_type == 'private' else None,
                                    group_id=int(group_id) if message_type == 'group' else None,
                                    message=f"{reply_code}二维码已扫描，请在手机上确认登录。"
                                )
                            
                            # 86101: 未扫码
                            # 不发送任何消息，继续轮询
                            
                await asyncio.sleep(10)  # 每10秒查询一次状态
            
            # 超时
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}登录超时，请重新发送 /bili.login 获取新的二维码。"
            )
            return {}
        except Exception as e:
            logger.error(f"轮询B站登录状态异常: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message=f"{reply_code}登录过程出现错误: {str(e)}"
            )
            return {}
    
    def _extract_cookie_value(self, url: str, name: str) -> str:
        """从URL中提取Cookie值"""
        try:
            if name in url:
                pattern = f"{name}=([^&;]+)"
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            return ""
        except:
            return ""
    
    async def _get_user_info(self, cookies: Dict[str, str]) -> Dict[str, Any]:
        """获取用户信息"""
        try:
            cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Referer': 'https://space.bilibili.com/',
                'Cookie': cookie_string
            }
            
            async with aiohttp.ClientSession() as session:
                api_url = "https://api.bilibili.com/x/space/myinfo"
                async with session.get(api_url, headers=headers) as resp:
                    resp_json = await resp.json()
                    if resp_json['code'] == 0:
                        return resp_json['data']
            return {}
        except Exception as e:
            logger.error(f"获取B站用户信息异常: {e}", exc_info=True)
            return {}
    
    def start_check_task(self):
        """启动订阅检查任务"""
        if self.check_task is None or self.check_task.done():
            logger.info("启动B站订阅检查任务")
            self.check_task = asyncio.create_task(self._check_subscriptions_loop())
    
    async def _check_subscriptions_loop(self):
        """定期检查订阅的UP主更新和直播状态"""
        try:
            while True:
                logger.debug("开始检查B站订阅更新")
                all_subs = {}
                
                # 收集所有订阅的UP主
                for user_id, subs in self.data["subscriptions"].items():
                    for sub in subs:
                        up_uid = sub["up_uid"]
                        if up_uid not in all_subs:
                            all_subs[up_uid] = []
                        all_subs[up_uid].append({
                            "user_id": user_id,
                            "sub_data": sub
                        })
                
                # 检查每个UP主的最新动态
                for up_uid, subscribers in all_subs.items():
                    await self._check_up_updates(up_uid, subscribers)
                    # 避免频繁请求
                    await asyncio.sleep(5)
                
                # 每30分钟检查一次
                await asyncio.sleep(30 * 60)
        except asyncio.CancelledError:
            logger.info("B站订阅检查任务已取消")
        except Exception as e:
            logger.error(f"B站订阅检查任务出错: {e}")
            # 10分钟后重启任务
            await asyncio.sleep(10 * 60)
            self.start_check_task()
    
    async def _check_up_updates(self, up_uid: str, subscribers: List[Dict]):
        """检查UP主更新"""
        try:
            # 检查视频更新
            latest_video = None
            video_updated = False
            
            # 检查直播状态
            is_live = False
            live_title = ""
            live_room_id = 0
            live_cover = ""
            live_changed = False
            
            # 获取最新视频
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_base}/x/space/arc/search?mid={up_uid}&ps=1&pn=1") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data["code"] == 0 and data["data"]["list"]["vlist"]:
                            latest_video = data["data"]["list"]["vlist"][0]
                
                # 获取直播状态
                async with session.get(f"{self.api_base}/x/space/acc/info?mid={up_uid}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data["code"] == 0 and data["data"].get("live_room"):
                            live_room = data["data"]["live_room"]
                            is_live = live_room.get("liveStatus") == 1
                            live_title = live_room.get("title", "")
                            live_room_id = live_room.get("roomid", 0)
                            live_cover = live_room.get("cover", "")
            
            # 检查是否有新视频
            if latest_video:
                for subscriber in subscribers:
                    sub_data = subscriber["sub_data"]
                    last_video = sub_data.get("last_video")
                    
                    if last_video != latest_video["bvid"]:
                        video_updated = True
                        sub_data["last_video"] = latest_video["bvid"]
            
            # 检查直播状态变化
            for subscriber in subscribers:
                sub_data = subscriber["sub_data"]
                last_live = sub_data.get("last_live", False)
                
                if last_live != is_live:
                    live_changed = True
                    sub_data["last_live"] = is_live
            
            # 如果有更新，保存数据
            if video_updated or live_changed:
                self.save_json()
                
            # 如果有新视频，向订阅者发送通知
            if video_updated and latest_video:
                pub_time = datetime.fromtimestamp(latest_video['created']).strftime('%Y-%m-%d %H:%M')
                up_name = subscribers[0]["sub_data"]["up_name"]
                
                notify_message = f"您订阅的UP主【{up_name}】发布了新视频！\n"
                notify_message += f"标题: {latest_video['title']}\n"
                notify_message += f"发布时间: {pub_time}\n"
                notify_message += f"链接: https://www.bilibili.com/video/{latest_video['bvid']}\n"
                
                await self._send_subscription_notices(subscribers, notify_message)
            
            # 如果直播状态改变，向订阅者发送通知
            if live_changed:
                up_name = subscribers[0]["sub_data"]["up_name"]
                
                if is_live:
                    notify_message = f"您订阅的UP主【{up_name}】开播啦！\n"
                    notify_message += f"直播标题: {live_title}\n"
                    notify_message += f"直播间链接: https://live.bilibili.com/{live_room_id}\n"
                    
                    # 添加直播封面(如果有)
                    if live_cover:
                        notify_message = f"[CQ:image,file={live_cover}]\n" + notify_message
                else:
                    notify_message = f"您订阅的UP主【{up_name}】下播了\n"
                
                await self._send_subscription_notices(subscribers, notify_message)
                
        except Exception as e:
            logger.error(f"检查UP主({up_uid})更新失败: {e}")
    
    async def _send_subscription_notices(self, subscribers: List[Dict], message: str):
        """向订阅者发送通知"""
        for subscriber in subscribers:
            user_id = subscriber["user_id"]
            
            # 尝试私聊通知
            try:
                await self.bot.send_msg(
                    message_type="private",
                    user_id=int(user_id),
                    message=message
                )
            except Exception as e:
                logger.error(f"向用户 {user_id} 发送私聊通知失败: {e}")
                
            # 查找该用户所在的启用了通知的群
            for group_id, group_data in self.data["notification_groups"].items():
                if not group_data.get("enabled", False):
                    continue
                    
                if user_id in group_data.get("users", []):
                    try:
                        # 在群里@用户发送通知
                        group_message = f"[CQ:at,qq={user_id}] {message}"
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=int(group_id),
                            message=group_message
                        )
                        # 每个通知只在一个群发送，避免刷屏
                        break
                    except Exception as e:
                        logger.error(f"在群 {group_id} 发送通知失败: {e}")
                        
    async def _init_plugin(self):
        """插件初始化，在bot启动后调用"""
        # 启动订阅检查任务
        if self.data["subscriptions"]:
            self.start_check_task()

    async def _shutdown_plugin(self):
        """插件关闭，在bot关闭前调用"""
        # 取消订阅检查任务
        if self.check_task:
            self.check_task.cancel() 

    # 会员管理相关功能
    def add_member(self, user_id: str) -> bool:
        """添加会员用户"""
        user_id = str(user_id)
        if user_id in self.data["members"]:
            return False  # 已经是会员
        
        self.data["members"].append(user_id)
        self.save_json()
        return True
    
    def remove_member(self, user_id: str) -> bool:
        """移除会员用户"""
        user_id = str(user_id)
        if user_id not in self.data["members"]:
            return False  # 不是会员
        
        self.data["members"].remove(user_id)
        self.save_json()
        return True
    
    def set_group_notification(self, group_id: str, enabled: bool) -> None:
        """设置群组通知开关"""
        group_id = str(group_id)
        if group_id not in self.data["notification_groups"]:
            self.data["notification_groups"][group_id] = {
                "enabled": enabled,
                "users": []
            }
        else:
            self.data["notification_groups"][group_id]["enabled"] = enabled
        
        self.save_json()
    
    def add_group_notify_user(self, group_id: str, user_id: str) -> None:
        """添加群组通知用户"""
        group_id = str(group_id)
        user_id = str(user_id)
        
        if group_id not in self.data["notification_groups"]:
            self.data["notification_groups"][group_id] = {
                "enabled": True,
                "users": [user_id]
            }
        else:
            if user_id not in self.data["notification_groups"][group_id].get("users", []):
                if "users" not in self.data["notification_groups"][group_id]:
                    self.data["notification_groups"][group_id]["users"] = []
                self.data["notification_groups"][group_id]["users"].append(user_id)
                
        self.save_json()
        
    def remove_group_notify_user(self, group_id: str, user_id: str) -> bool:
        """移除群组通知用户"""
        group_id = str(group_id)
        user_id = str(user_id)
        
        if group_id not in self.data["notification_groups"]:
            return False
            
        users = self.data["notification_groups"][group_id].get("users", [])
        if user_id in users:
            users.remove(user_id)
            self.save_json()
            return True
        
        return False
    
    # 管理员命令处理
    async def handle_admin_command(self, event: Dict[str, Any]) -> bool:
        """处理管理员命令"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id', 0)) if message_type == 'group' else '0'
        
        # 获取机器人QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        
        # 检查是否是@机器人的消息，管理员命令必须@机器人
        if not is_at_bot(event, bot_qq):
            return False
        
        # 检查是否是管理员
        is_admin = user_id in self.bot.config.get("bot", {}).get("superusers", [])
        if not is_admin:
            return False
            
        # 获取消息内容
        command = extract_command(event, bot_qq)
        
        # 检查是否是管理员命令
        if not command.startswith("/bili.admin"):
            return False
            
        # 管理员帮助命令
        if self.admin_command_patterns['help'].match(command):
            await self.bot.send_msg(
                message_type=message_type,
                user_id=int(user_id) if message_type == 'private' else None,
                group_id=int(group_id) if message_type == 'group' else None,
                message="B站插件管理命令：\n/bili.admin add_member <QQ号> - 添加会员\n/bili.admin remove_member <QQ号> - 移除会员\n/bili.admin list_members - 查看会员列表\n/bili.admin notify <on/off> - 设置当前群通知开关"
            )
            return True
                
        # 处理添加会员命令
        match = self.admin_command_patterns['add_member'].match(command)
        if match:
            target_user_id = match.group(1)
            if self.add_member(target_user_id):
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"已成功添加会员：{target_user_id}"
                )
            else:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"用户 {target_user_id} 已经是会员"
                )
            return True
                
        # 处理移除会员命令
        match = self.admin_command_patterns['remove_member'].match(command)
        if match:
            target_user_id = match.group(1)
            if self.remove_member(target_user_id):
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"已成功移除会员：{target_user_id}"
                )
            else:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"用户 {target_user_id} 不是会员"
                )
            return True
                
        # 处理查看会员列表命令
        if self.admin_command_patterns['list_members'].match(command):
            members = self.data["members"]
            if not members:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message="当前没有会员用户"
                )
            else:
                members_str = "\n".join(members)
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=int(user_id) if message_type == 'private' else None,
                    group_id=int(group_id) if message_type == 'group' else None,
                    message=f"会员列表（共{len(members)}人）：\n{members_str}"
                )
            return True
                
        # 处理设置群通知命令
        match = self.admin_command_patterns['notify'].match(command)
        if match and message_type == 'group':
            option = match.group(1)
            if option.lower() == 'on':
                self.set_group_notification(group_id, True)
                await self.bot.send_msg(
                    message_type='group',
                    group_id=int(group_id),
                    message="已开启本群B站订阅通知功能"
                )
            elif option.lower() == 'off':
                self.set_group_notification(group_id, False)
                await self.bot.send_msg(
                    message_type='group',
                    group_id=int(group_id),
                    message="已关闭本群B站订阅通知功能"
                )
            return True
                
        return False 

# 导出插件类，确保插件加载器能找到它
plugin_class = BilibiliPlugin 