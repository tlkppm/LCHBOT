#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Set, Optional

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command, extract_command, is_at_bot

logger = logging.getLogger("LCHBot")

class GroupAuth(Plugin):
    """
    群组授权插件：控制哪些群可以使用机器人
    管理员命令：
    - @机器人 /auth add 群号 天数 - 为指定群添加授权（天数可选，默认30天）
    - @机器人 /auth remove 群号 - 移除指定群的授权
    - @机器人 /auth list - 列出所有已授权的群
    - @机器人 /auth info - 查看当前群的授权信息
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "GroupAuth"
        # 管理员命令模式
        self.admin_patterns = {
            'add_auth': re.compile(r'^/auth\s+add\s+(\d+)(?:\s+(\d+))?$'),  # 添加授权
            'remove_auth': re.compile(r'^/auth\s+remove\s+(\d+)$'),  # 移除授权
            'list_auth': re.compile(r'^/auth\s+list$'),  # 列出所有授权
            'info_auth': re.compile(r'^/auth\s+info$')   # 查看当前群授权信息
        }
        # 插件优先级设为最高，确保在其他插件前运行
        self.priority = 100
        
        # 授权数据文件路径
        self.auth_file = "data/group_auth.json"
        # 授权数据 {group_id: {"expire_time": timestamp, "added_by": user_id, "added_time": timestamp}}
        self.auth_data = self.load_auth_data()
        
        # 警告消息发送间隔（秒）
        self.warning_interval = 3600  # 默认1小时发送一次警告
        # 最近警告时间记录 {group_id: last_warning_time}
        self.last_warnings = {}
        
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化，当前授权群数量: {len(self.auth_data)}")
        
    def load_auth_data(self) -> Dict[str, Dict[str, Any]]:
        """加载授权数据"""
        if not os.path.exists(self.auth_file):
            # 创建目录（如果不存在）
            os.makedirs(os.path.dirname(self.auth_file), exist_ok=True)
            # 创建空的授权数据文件
            return {}
        
        try:
            with open(self.auth_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"加载授权数据失败: {e}")
            return {}
            
    def save_auth_data(self) -> None:
        """保存授权数据"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.auth_file), exist_ok=True)
            
            with open(self.auth_file, 'w', encoding='utf-8') as f:
                json.dump(self.auth_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存授权数据失败: {e}")
    
    def is_authorized(self, group_id: int) -> bool:
        """检查群是否已授权"""
        # 调试日志
        logger.debug(f"检查群组 {group_id} 的授权状态")
        
        # 超级用户的群永久授权
        if str(group_id) in self.auth_data:
            auth_info = self.auth_data[str(group_id)]
            current_time = time.time()
            # 检查是否永久授权或授权未过期
            if auth_info.get("expire_time") == -1 or auth_info.get("expire_time", 0) > current_time:
                logger.debug(f"群组 {group_id} 已授权，状态: {auth_info}")
                return True
            else:
                # 授权已过期，但保留记录以便管理员查看
                logger.debug(f"群组 {group_id} 授权已过期，状态: {auth_info}")
                return False
        
        logger.debug(f"群组 {group_id} 未找到授权记录")
        return False
        
    def is_admin(self, user_id: int) -> bool:
        """检查用户是否是管理员"""
        superusers = self.bot.config.get("bot", {}).get("superusers", [])
        return str(user_id) in superusers
        
    def add_auth(self, group_id: int, days: int, user_id: int) -> bool:
        """添加授权"""
        current_time = time.time()
        expire_time = -1 if days <= 0 else current_time + (days * 86400)  # 负数或0表示永久授权
        
        self.auth_data[str(group_id)] = {
            "expire_time": expire_time,
            "added_by": user_id,
            "added_time": current_time
        }
        self.save_auth_data()
        return True
        
    def remove_auth(self, group_id: int) -> bool:
        """移除授权"""
        if str(group_id) in self.auth_data:
            del self.auth_data[str(group_id)]
            self.save_auth_data()
            return True
        return False
        
    def format_expire_time(self, expire_time: float) -> str:
        """格式化过期时间"""
        if expire_time == -1:
            return "永久授权"
            
        # 计算剩余时间
        now = time.time()
        if expire_time <= now:
            return "已过期"
            
        remaining = expire_time - now
        days = int(remaining // 86400)
        hours = int((remaining % 86400) // 3600)
        
        if days > 0:
            return f"剩余 {days} 天 {hours} 小时"
        else:
            minutes = int((remaining % 3600) // 60)
            return f"剩余 {hours} 小时 {minutes} 分钟"
    
    def get_auth_info(self, group_id: int) -> str:
        """获取授权信息"""
        if str(group_id) not in self.auth_data:
            return "此群未授权"
            
        auth_info = self.auth_data[str(group_id)]
        expire_time = auth_info.get("expire_time", 0)
        added_by = auth_info.get("added_by", "未知")
        added_time = auth_info.get("added_time", 0)
        
        added_time_str = datetime.fromtimestamp(added_time).strftime("%Y-%m-%d %H:%M:%S")
        expire_status = self.format_expire_time(expire_time)
        
        return f"授权信息:\n- 群号: {group_id}\n- 授权状态: {expire_status}\n- 授权时间: {added_time_str}\n- 授权人: {added_by}"
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id', 0)  # 设置默认值为0，确保类型为整数
        group_id = event.get('group_id') if message_type == 'group' else None
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 只处理群消息
        if message_type != 'group' or not group_id:
            return False
            
        # 先处理管理员命令
        if self.is_admin(int(user_id)):  # 确保转换为整数
            # 添加授权命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['add_auth'])
            if is_at_command and match:
                target_group = int(match.group(1))
                days = int(match.group(2)) if match.group(2) else 30
                
                self.add_auth(target_group, days, int(user_id))  # 确保转换为整数
                
                # 发送授权成功消息，使用回复
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}✅ 授权成功！\n群号: {target_group}\n授权时间: {'永久' if days <= 0 else f'{days}天'}\n授权添加时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return True
                
            # 移除授权命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['remove_auth'])
            if is_at_command and match:
                target_group = int(match.group(1))
                
                if self.remove_auth(target_group):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}✅ 已移除群 {target_group} 的授权"
                    )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}❌ 群 {target_group} 未授权"
                    )
                return True
                
            # 列出所有授权群
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['list_auth'])
            if is_at_command and match:
                if not self.auth_data:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}📝 当前没有授权的群"
                    )
                    return True
                
                # 格式化授权列表
                current_time = time.time()
                auth_list = ["📝 授权群列表:"]
                
                # 统计信息
                total_count = len(self.auth_data)
                active_count = 0
                expired_count = 0
                permanent_count = 0
                
                # 按状态分类群组
                active_groups = []
                expired_groups = []
                permanent_groups = []
                
                for g_id, info in self.auth_data.items():
                    expire_time = info.get("expire_time", 0)
                    if expire_time == -1:
                        status = "永久授权"
                        permanent_count += 1
                        permanent_groups.append(f"- 群号: {g_id} | {status}")
                    elif expire_time > current_time:
                        status = self.format_expire_time(expire_time)
                        active_count += 1
                        active_groups.append(f"- 群号: {g_id} | {status}")
                    else:
                        status = "已过期"
                        expired_count += 1
                        expired_groups.append(f"- 群号: {g_id} | {status}")
                
                auth_list.append(f"统计: 共{total_count}个群 (活跃:{active_count} 永久:{permanent_count} 过期:{expired_count})")
                auth_list.append("\n【永久授权群】")
                auth_list.extend(permanent_groups)
                auth_list.append("\n【有效授权群】")
                auth_list.extend(active_groups)
                auth_list.append("\n【已过期群】")
                auth_list.extend(expired_groups if expired_groups else ["- 无"])
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}\n" + "\n".join(auth_list)
                )
                return True
                
            # 查看当前群授权信息
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['info_auth'])
            if is_at_command and match:
                info = self.get_auth_info(group_id)
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}{info}"
                )
                return True
        
        # 检查群授权状态，如果未授权则发送提示并拦截消息
        if not self.is_authorized(group_id):
            # 检查是否@了机器人
            is_at_bot_msg = is_at_bot(event, self.bot)
            
            # 添加调试日志
            logger.warning(f"收到来自未授权群 {group_id} 的消息，is_at_bot={is_at_bot_msg}")
            
            # 控制警告频率，避免刷屏
            current_time = time.time()
            last_warning = self.last_warnings.get(group_id, 0)
            
            # 只有被@时才发送警告 或者 间隔超过24小时发送一次提醒
            if is_at_bot_msg or (current_time - last_warning >= 86400):  # 24小时 = 86400秒
                self.last_warnings[group_id] = current_time
                
                # 发送未授权警告
                message = (
                    "⚠️ 此群未授权，机器人功能已限制\n\n"
                    "请联系机器人管理员获取授权\n"
                    "管理员QQ: " + ", ".join(self.bot.config.get("bot", {}).get("superusers", [])) + "\n\n"
                    "授权后即可使用完整功能"
                )
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}{message}"
                )
            
            # 拦截其他插件处理此消息
            return True
            
        # 群已授权，检查是否即将过期
        if str(group_id) in self.auth_data:
            auth_info = self.auth_data[str(group_id)]
            expire_time = auth_info.get("expire_time", 0)
            
            # 永久授权不需要提醒
            if expire_time != -1:
                current_time = time.time()
                # 授权剩余不足3天时发送提醒
                if expire_time - current_time < 259200:  # 3天 = 259200秒
                    # 控制提醒频率
                    last_warning = self.last_warnings.get(group_id, 0)
                    if current_time - last_warning >= self.warning_interval:
                        self.last_warnings[group_id] = current_time
                        
                        remain_time = self.format_expire_time(expire_time)
                        message = f"⚠️ 授权提醒: 本群授权即将到期\n{remain_time}\n请及时联系管理员续期"
                        
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}{message}"
                        )
        
        # 群已授权，允许其他插件处理消息
        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = GroupAuth 