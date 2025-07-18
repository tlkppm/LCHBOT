#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
import os

# 导入Plugin基类和工具函数
from src.plugin_system import Plugin
from src.plugins.utils import handle_at_command

logger = logging.getLogger("LCHBot")

class ActivityTracker(Plugin):
    """
    群组活跃度分析插件，提供更详细的群组活跃度分析功能
    命令格式：
    @机器人 /activity.report - 生成详细活跃度报告
    @机器人 /activity.user <用户ID> - 查看指定用户的活跃度
    @机器人 /activity.trend - 查看群组活跃度趋势
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/activity\.([a-z]+)(?:\s+(.+))?$')
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 只在群聊中有效
        if message_type != 'group' or not group_id:
            return False
        
        # 使用工具函数处理@机器人命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_pattern)
        
        if not is_at_command or not match:
            return False
            
        subcommand = match.group(1)
        param = match.group(2).strip() if match.group(2) else ""
        
        logger.info(f"接收到活跃度分析命令: {subcommand}, 参数: {param}")
        
        if subcommand == "report":
            return await self._generate_report(event, group_id)
        elif subcommand == "user":
            try:
                target_user_id = int(param)
                return await self._user_activity(event, group_id, target_user_id)
            except ValueError:
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message="请提供有效的用户ID，例如: @机器人 /activity.user 12345678"
                )
                return True
        elif subcommand == "trend":
            return await self._activity_trend(event, group_id)
        else:
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"未知子命令: {subcommand}，可用命令: report, user, trend"
            )
            return True
            
    async def _generate_report(self, event: Dict[str, Any], group_id: int) -> bool:
        """生成群组活跃度报告"""
        # 获取过去7天的数据
        activity_data = self.bot.activity_tracker.get_group_activity(group_id, 7)
        
        # 构建详细报告
        report = f"【群 {group_id} 活跃度详细报告】\n\n"
        
        # 总体统计
        report += "【总体统计】\n"
        report += f"• 总消息数: {activity_data['total_messages']}\n"
        report += f"• 活跃用户数: {activity_data['active_users']}\n"
        report += f"• 人均消息数: {activity_data['total_messages'] / activity_data['active_users'] if activity_data['active_users'] > 0 else 0:.2f}\n\n"
        
        # 最活跃用户
        report += "【活跃用户排行】\n"
        if activity_data['most_active_users']:
            for i, user in enumerate(activity_data['most_active_users'][:10]):
                report += f"{i+1}. 用户 {user['user_id']} - {user['message_count']}条消息\n"
        else:
            report += "暂无活跃用户数据\n"
        report += "\n"
        
        # 消息类型分布
        report += "【消息类型分布】\n"
        if activity_data['message_types']:
            total = sum(activity_data['message_types'].values())
            for msg_type, count in sorted(activity_data['message_types'].items(), key=lambda x: x[1], reverse=True):
                percentage = count / total * 100 if total > 0 else 0
                report += f"• {msg_type}: {count}条 ({percentage:.1f}%)\n"
        else:
            report += "暂无消息类型数据\n"
        report += "\n"
        
        # 活跃时段
        report += "【活跃时段分析】\n"
        peak_hours = sorted(activity_data['peak_hours'].items())
        if peak_hours:
            most_active_hour = max(peak_hours, key=lambda x: x[1])[0]
            report += f"• 最活跃时段: {most_active_hour}:00 - {most_active_hour+1}:00\n"
            report += "• 时段分布:\n"
            for hour, count in peak_hours:
                report += f"  {hour:02d}:00 - {hour+1:02d}:00: {count}条消息\n"
        else:
            report += "暂无活跃时段数据\n"
        report += "\n"
        
        # 每日统计
        report += "【每日活跃度】\n"
        for date_str, stats in sorted(activity_data['daily_stats'].items()):
            report += f"• {date_str}: {stats['messages']}条消息, {stats['active_users']}位活跃用户\n"
            
        # 发送报告
        await self.bot.send_msg(
            message_type='group',
            group_id=group_id,
            message=report
        )
        
        return True
        
    async def _user_activity(self, event: Dict[str, Any], group_id: int, target_user_id: int) -> bool:
        """分析特定用户的活跃度"""
        # 在这个简化版本中，我们只显示用户在总活跃度中的排名
        activity_data = self.bot.activity_tracker.get_group_activity(group_id, 7)
        
        # 查找用户
        user_found = False
        user_rank = 0
        user_messages = 0
        
        for i, user in enumerate(activity_data['most_active_users']):
            if user['user_id'] == target_user_id:
                user_found = True
                user_rank = i + 1
                user_messages = user['message_count']
                break
                
        if not user_found:
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"用户 {target_user_id} 在过去7天内未发言或不在本群"
            )
        else:
            # 计算百分比
            total_messages = activity_data['total_messages']
            percentage = user_messages / total_messages * 100 if total_messages > 0 else 0
            
            response = f"用户 {target_user_id} 活跃度分析:\n"
            response += f"• 消息数量: {user_messages}条\n"
            response += f"• 活跃度排名: 第{user_rank}名\n"
            response += f"• 占总消息比例: {percentage:.1f}%\n"
            
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=response
            )
            
        return True
        
    async def _activity_trend(self, event: Dict[str, Any], group_id: int) -> bool:
        """显示群组活跃度趋势"""
        activity_data = self.bot.activity_tracker.get_group_activity(group_id, 7)
        
        # 提取每日数据
        dates = []
        message_counts = []
        user_counts = []
        
        for date_str, stats in sorted(activity_data['daily_stats'].items()):
            dates.append(date_str)
            message_counts.append(stats['messages'])
            user_counts.append(stats['active_users'])
            
        if not dates:
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message="暂无足够的数据生成趋势图"
            )
            return True
            
        # 生成简单的文本趋势
        response = f"群 {group_id} 过去7天活跃度趋势:\n\n"
        response += "日期        消息数  活跃用户\n"
        response += "-------------------------\n"
        
        for i in range(len(dates)):
            response += f"{dates[i]}  {message_counts[i]:6d}  {user_counts[i]:8d}\n"
            
        response += "\n趋势分析:\n"
        
        # 计算趋势
        if len(message_counts) >= 2:
            if message_counts[-1] > message_counts[0]:
                msg_trend = f"消息数量呈上升趋势，增长了 {message_counts[-1] - message_counts[0]} 条"
            elif message_counts[-1] < message_counts[0]:
                msg_trend = f"消息数量呈下降趋势，减少了 {message_counts[0] - message_counts[-1]} 条"
            else:
                msg_trend = "消息数量保持稳定"
                
            response += f"• {msg_trend}\n"
            
        if len(user_counts) >= 2:
            if user_counts[-1] > user_counts[0]:
                user_trend = f"活跃用户呈上升趋势，增加了 {user_counts[-1] - user_counts[0]} 人"
            elif user_counts[-1] < user_counts[0]:
                user_trend = f"活跃用户呈下降趋势，减少了 {user_counts[0] - user_counts[-1]} 人"
            else:
                user_trend = "活跃用户数量保持稳定"
                
            response += f"• {user_trend}\n"
            
        # 发送趋势分析
        await self.bot.send_msg(
            message_type='group',
            group_id=group_id,
            message=response
        )
        
        return True

# 导出插件类，确保插件加载器能找到它
plugin_class = ActivityTracker 