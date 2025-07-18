#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
from typing import Dict, Any

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command

logger = logging.getLogger("LCHBot")

class Help(Plugin):
    """
    帮助插件，显示可用命令列表
    命令格式: @机器人 /help
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/help$')
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        
        # 使用工具函数处理@机器人命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_pattern)
        
        if is_at_command and match:
            logger.info(f"接收到 help 命令")
            
            # 构建帮助信息
            help_text = """LCHBot 使用帮助：
            
【提示：所有命令都需要艾特机器人才能使用】

基本命令：
@机器人 /help - 显示此帮助信息
@机器人 /echo <内容> - 回复您发送的内容
@机器人 /info - 显示系统和机器人信息
@机器人 /debug - 显示消息的详细信息

系统命令:
@机器人 /system - 显示系统状态信息
@机器人 /plugins - 显示所有已加载的插件
@机器人 /activity [天数] - 显示群组活跃度统计

签到与积分命令:
@机器人 /sign - 每日签到获取积分
@机器人 /mysign - 查看个人签到统计
@机器人 /points - 查看自己的积分
@机器人 /rank - 查看群内积分排行榜
@机器人 /shop - 查看积分兑换商店
@机器人 /exchange <ID> - 兑换积分商店物品
@机器人 /bag - 查看个人背包
@机器人 /use <物品ID> - 使用背包中的物品

头衔管理命令:
@机器人 /title list - 查看可用头衔列表
@机器人 /title set <头衔名> - 设置自己的专属头衔
@机器人 /title clear - 清除自己的专属头衔
@机器人 /title info - 查看自己的当前头衔信息

抽奖系统:
@机器人 /draw <次数> - 参与抽奖，消耗积分获得随机物品
@机器人 /draw_info - 查看抽奖信息和概率

聊天功能：
@机器人 <任意文本> - 与当前人格聊天
@机器人 /switch_persona <人格名> - 切换聊天人格(仅管理员)
  - 可用人格: ailixiya(爱莉希雅)、xiadie(遐蝶)、teresiya(特雷西娅)
@机器人 /clear_context - 清除当前群的聊天上下文(仅管理员)
@机器人 /debug_context - 显示当前群的上下文内容(仅管理员)

娱乐功能：
@机器人 /meme [@用户] - 生成坟前表情包（使用被@用户头像和发送者头像）
@机器人 /meme <名称> [@用户] - 生成表情包（使用被@用户的头像）
@机器人 /meme help - 查看支持的表情包列表

管理员命令：
@机器人 /admin - 显示管理员菜单
@机器人 /set_name <名称> - 设置机器人QQ昵称
@机器人 /set_card <名片> - 设置机器人群名片
@机器人 /points_add <@用户|QQ号> <数值> - 为用户添加/减少积分

群组授权命令(仅超管)：
@机器人 /auth add <群号> [天数] - 为群添加授权，不填天数为30天，填0为永久
@机器人 /auth remove <群号> - 移除指定群的授权
@机器人 /auth list - 列出所有已授权的群及其状态
@机器人 /auth info - 查看当前群的授权信息

黑名单管理命令(仅超管)：
@机器人 /blacklist add <@用户|QQ号> [原因] - 将用户添加到全局黑名单
@机器人 /blacklist remove <@用户|QQ号> - 将用户从全局黑名单中移除
@机器人 /blacklist list - 查看全局黑名单列表
@机器人 /blacklist check <@用户|QQ号> - 检查用户是否在黑名单中

高级命令：
@机器人 /image <URL> - 发送图片
@机器人 /mixed <文本> - 发送图文混合消息
@机器人 /weather <城市名> - 查询指定城市的天气预报(支持图片显示)
@机器人 /university <大学名称> - 查询大学详细信息
@机器人 /大学 <大学名称> - 同上，使用中文命令

哔哩哔哩功能：
@机器人 /bili.help - 显示B站插件帮助
@机器人 /bili.bind <uid> - 绑定B站账号
@机器人 /bili.info - 查看已绑定的账号信息
@机器人 /bili.up <uid/用户名> - 查询UP主信息
@机器人 /bili.video <BV号> - 查询视频信息
@机器人 /bili.sub <uid/用户名> - 订阅UP主更新和开播通知(会员专享)
@机器人 /bili.subs - 查看订阅列表(会员专享)
@机器人 /bili.hot - 获取B站热门推送(会员专享)

群组分析命令：
@机器人 /activity.report - 生成详细活跃度报告
@机器人 /activity.user <用户ID> - 查看指定用户的活跃度
@机器人 /activity.trend - 查看群组活跃度趋势
@机器人 /join_time [人数] - 显示入群时间最长的成员，默认显示前10名

进群验证命令(管理员)：
@机器人 /verify enable - 启用进群验证功能
@机器人 /verify disable - 禁用进群验证功能
@机器人 /verify set time <分钟> - 设置验证等待时间
@机器人 /verify set message <消息> - 设置验证消息
@机器人 /verify add whitelist group <群ID> - 添加群到白名单
@机器人 /verify remove whitelist group <群ID> - 从白名单移除群
@机器人 /verify settings - 显示验证设置

访问限制命令(仅超管)：
@机器人 /rate enable - 启用访问限制功能
@机器人 /rate disable - 禁用访问限制功能
@机器人 /rate set window <秒> - 设置时间窗口
@机器人 /rate set max <次数> - 设置最大请求次数
@机器人 /rate set duration <分钟> - 设置拉黑时间
@机器人 /rate unblock <用户ID> - 解除用户拉黑
@机器人 /rate settings - 显示限制设置

文字游戏命令：
@机器人 /game start 成语接龙 - 开始成语接龙游戏
@机器人 /game start 猜词 - 开始猜词游戏
@机器人 /game start 数字炸弹 [最小值] [最大值] - 开始数字炸弹游戏
@机器人 /game start 文字接龙 - 开始文字接龙游戏
@机器人 /game start 恶魔轮盘 - 开始恶魔轮盘射击游戏
@机器人 /game rules <游戏名> - 查看游戏规则
@机器人 /game status - 查看当前游戏状态
@机器人 /game stop - 停止当前游戏
            
更多功能正在开发中..."""
            
            # 发送回复
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=help_text
            )
            
            return True  # 表示已处理该消息
            
        return False  # 未处理该消息

# 导出插件类，确保插件加载器能找到它
plugin_class = Help 