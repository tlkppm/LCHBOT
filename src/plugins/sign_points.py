#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import os
import json
import logging
import time
import random
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional, Union

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command, extract_command, is_at_bot

logger = logging.getLogger("LCHBot")

class SignPoints(Plugin):
    """
    签到与积分系统插件：提供群内签到、积分管理和兑换功能
    用户命令：
    - @机器人 /sign - 每日签到
    - @机器人 /mysign - 查看个人签到统计
    - @机器人 /points - 查看自己的积分
    - @机器人 /rank - 查看群内积分排行榜
    - @机器人 /exchange <项目ID> - 兑换积分项目
    - @机器人 /shop - 查看积分兑换商店
    - @机器人 /bag - 查看个人背包
    - @机器人 /use <物品ID> - 使用背包物品
    
    管理员命令：
    - @机器人 /sign_set base <数值> - 设置基础签到积分
    - @机器人 /sign_set bonus <天数> <数值> - 设置连续签到奖励
    - @机器人 /points_add <@用户> <数值> - 为用户添加积分
    - @机器人 /shop_add <名称> <所需积分> <描述> - 添加兑换项目
    - @机器人 /item_mark <物品ID> usable|unusable - 标记物品是否可使用
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "SignPoints"
        
        # 用户命令模式
        self.user_patterns = {
            'sign': re.compile(r'^/sign$'),  # 每日签到
            'mysign': re.compile(r'^/mysign$'),  # 查看个人签到统计
            'points': re.compile(r'^/points$'),  # 查看自己的积分
            'rank': re.compile(r'^/rank$'),  # 查看群内积分排行榜
            'exchange': re.compile(r'^/exchange\s+(\d+)$'),  # 兑换积分项目
            'shop': re.compile(r'^/shop$'),  # 查看积分兑换商店
            'bag': re.compile(r'^/bag$'),  # 查看个人背包
            'use': re.compile(r'^/use\s+(\d+)$'),  # 使用背包物品
            'draw': re.compile(r'^/draw\s+(\d+)$'),  # 抽奖命令，参数为抽奖次数
            'draw_info': re.compile(r'^/draw_info$'),  # 查看抽奖信息
        }
        
        # 管理员命令模式
        self.admin_patterns = {
            'set_base': re.compile(r'^/sign_set\s+base\s+(\d+)$'),  # 设置基础签到积分
            'set_bonus': re.compile(r'^/sign_set\s+bonus\s+(\d+)\s+(\d+)$'),  # 设置连续签到奖励
            'add_points': re.compile(r'^/points_add\s+\[CQ:at,qq=(\d+)[^\]]*\]\s+(-?\d+)$'),  # 为用户添加积分(AT方式)
            'add_points_direct': re.compile(r'^/points_add\s+(\d+)\s+(-?\d+)$'),  # 为用户添加积分(直接QQ号)
            'shop_add': re.compile(r'^/shop_add\s+(.+?)\s+(\d+)\s+(.+)$'),  # 添加兑换项目
            'mark_usable': re.compile(r'^/item_mark\s+(\d+)\s+(usable|unusable)$'),  # 标记物品是否可使用
        }

        # 物品类型和用途
        self.item_types = {
            "改名卡": {"usable": True, "description": "可以修改自己的群名片"},
            "专属头衔": {"usable": True, "description": "可以获取一个专属头衔"},
            "抽奖券": {"usable": True, "description": "可以参与一次抽奖活动"},
            "群活跃报告": {"usable": True, "description": "获取群活跃度详细报告"},
            "置顶发言": {"usable": True, "description": "可以请求将一条消息设为精华"},
            "经验卡": {"usable": True, "description": "使用后可获得额外积分"},
            "双倍签到卡": {"usable": True, "description": "使用后下次签到双倍积分"},
            "禁言卡": {"usable": True, "description": "可以对指定成员使用禁言"},
            "解除禁言卡": {"usable": True, "description": "可以解除指定成员的禁言"},
            "超级禁言卡": {"usable": True, "description": "可以对指定成员使用长时间禁言"},
        }
        
        # 抽奖池配置
        self.draw_config = {
            "cost_per_draw": 100,  # 每次抽奖消耗的积分
            "pools": {
                "common": {  # 普通奖池
                    "weight": 70,  # 抽中概率70%
                    "items": [
                        {"name": "经验卡", "weight": 40, "min_points": 10, "max_points": 30},
                        {"name": "抽奖券", "weight": 30, "description": "可以参与一次抽奖活动"},
                        {"name": "双倍签到卡", "weight": 20, "description": "使用后下次签到双倍积分"},
                        {"name": "禁言卡", "weight": 10, "description": "可以对指定成员使用禁言(1分钟)"}
                    ]
                },
                "rare": {  # 稀有奖池
                    "weight": 25,  # 抽中概率25%
                    "items": [
                        {"name": "改名卡", "weight": 40, "description": "可以修改自己的群名片"},
                        {"name": "专属头衔", "weight": 25, "description": "可以获取一个专属头衔"},
                        {"name": "群活跃报告", "weight": 20, "description": "获取群活跃度详细报告"},
                        {"name": "解除禁言卡", "weight": 15, "description": "可以解除指定成员的禁言"}
                    ]
                },
                "epic": {  # 史诗奖池
                    "weight": 5,  # 抽中概率5%
                    "items": [
                        {"name": "置顶发言", "weight": 50, "description": "可以请求将一条消息设为精华"},
                        {"name": "超级禁言卡", "weight": 30, "description": "可以对指定成员使用长时间禁言(30分钟)"},
                        {"name": "大额经验卡", "weight": 20, "min_points": 100, "max_points": 300}
                    ]
                }
            }
        }

        # 数据文件路径
        self.sign_data_file = "data/sign_data.json"
        self.shop_data_file = "data/shop_data.json"
        
        # 默认配置
        self.default_config = {
            "base_points": 5,  # 基础签到积分
            "random_range": 5,  # 随机浮动范围
            "consecutive_bonus": {  # 连续签到奖励配置
                "3": 3,   # 连续签到3天，额外奖励3积分
                "7": 10,  # 连续签到7天，额外奖励10积分
                "30": 50  # 连续签到30天，额外奖励50积分
            }
        }
        
        # 加载数据
        self.sign_data = self.load_json(self.sign_data_file, {})
        self.shop_data = self.load_json(self.shop_data_file, {"global": [], "groups": {}})
        
        # 确保所有群的配置都存在
        for group_id in self.sign_data:
            self.ensure_group_config(group_id)
            
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化，当前记录用户数: {self.count_total_users()}")
        
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
            
    def save_json(self, file_path: str, data: Dict) -> None:
        """保存数据到JSON文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存JSON文件 {file_path} 失败: {e}")
            
    def ensure_group_config(self, group_id: str) -> None:
        """确保群配置存在"""
        if group_id not in self.sign_data:
            self.sign_data[group_id] = {
                "users": {},  # 用户签到数据
                "config": self.default_config.copy(),  # 复制默认配置
                "statistics": {  # 群统计信息
                    "total_signs": 0,
                    "total_points": 0
                }
            }
            self.save_json(self.sign_data_file, self.sign_data)
            
    def count_total_users(self) -> int:
        """统计所有用户数"""
        total = 0
        for group_data in self.sign_data.values():
            total += len(group_data.get("users", {}))
        return total
        
    def is_admin(self, user_id: int, group_id: Optional[str] = None) -> bool:
        """检查用户是否是管理员"""
        superusers = self.bot.config.get("bot", {}).get("superusers", [])
        return str(user_id) in superusers
        
    def get_today_date(self) -> str:
        """获取今天的日期字符串 (YYYY-MM-DD)"""
        return datetime.now().strftime("%Y-%m-%d")
        
    def can_sign_today(self, group_id: str, user_id: str) -> bool:
        """检查用户今天是否可以签到"""
        user_data = self.sign_data.get(group_id, {}).get("users", {}).get(user_id, {})
        last_sign = user_data.get("last_sign_date", "")
        return last_sign != self.get_today_date()
        
    async def perform_sign(self, event: Dict[str, Any]) -> str:
        """执行签到操作，返回签到结果消息"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id')) if message_type == 'group' else "0"
        nickname = event.get('sender', {}).get('nickname', '用户')
        
        # 确保群配置存在
        self.ensure_group_config(group_id)
        
        # 检查今天是否已经签到
        if not self.can_sign_today(group_id, user_id):
            user_data = self.sign_data[group_id]["users"][user_id]
            # 添加QQ头像
            avatar_url = f"[CQ:image,file=https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640]"
            return f"{avatar_url}\nQQ: {user_id}\n您今天已经签到过了\n当前积分: {user_data['total_points']}\n连续签到: {user_data['consecutive_days']}天"
            
        # 计算签到积分
        points, consecutive_days, bonus_messages = await self.calc_sign_points(group_id, user_id)
        
        # 更新用户数据
        if user_id not in self.sign_data[group_id]["users"]:
            self.sign_data[group_id]["users"][user_id] = {
                "total_points": 0,
                "sign_count": 0,
                "consecutive_days": 0,
                "last_sign_date": "",
                "history": []
            }
            
        # 更新签到记录
        user_data = self.sign_data[group_id]["users"][user_id]
        user_data["total_points"] += points
        user_data["sign_count"] += 1
        user_data["consecutive_days"] = consecutive_days
        user_data["last_sign_date"] = self.get_today_date()
        user_data["history"].append({
            "date": self.get_today_date(),
            "points": points,
            "time": int(time.time())
        })
        
        # 限制历史记录长度，只保留最近30条
        if len(user_data["history"]) > 30:
            user_data["history"] = user_data["history"][-30:]
            
        # 更新群统计数据
        self.sign_data[group_id]["statistics"]["total_signs"] += 1
        self.sign_data[group_id]["statistics"]["total_points"] += points
        
        # 保存数据
        self.save_json(self.sign_data_file, self.sign_data)
        
        # 构建签到成功消息
        sign_rank = self.get_sign_rank_today(group_id, user_id)
        # 添加QQ头像
        avatar_url = f"[CQ:image,file=https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640]"
        message = [
            f"{avatar_url}",
            f"✅ {nickname} (QQ: {user_id}) 签到成功！",
            f"🎯 获得积分: +{points}",
            f"🔄 连续签到: {consecutive_days}天",
            f"💰 当前积分: {user_data['total_points']}",
            f"🏆 今日排名: 第{sign_rank}位"
        ]
        
        # 添加奖励消息
        if bonus_messages:
            message.extend(bonus_messages)
            
        return "\n".join(message)
        
    def get_sign_rank_today(self, group_id: str, user_id: str) -> int:
        """获取用户今日签到排名"""
        today = self.get_today_date()
        signed_users = []
        
        # 收集今天签到的用户及其时间
        for uid, data in self.sign_data.get(group_id, {}).get("users", {}).items():
            if data.get("last_sign_date") == today:
                # 找到该用户当天的签到记录
                for record in data.get("history", []):
                    if record.get("date") == today:
                        signed_users.append((uid, record.get("time", 0)))
                        break
                        
        # 按签到时间排序
        signed_users.sort(key=lambda x: x[1])
        
        # 查找用户排名
        for i, (uid, _) in enumerate(signed_users):
            if uid == user_id:
                return i + 1
                
        # 如果没找到，返回总签到人数+1
        return len(signed_users) + 1
        
    def get_points_rank(self, group_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取群积分排行榜"""
        users = self.sign_data.get(group_id, {}).get("users", {})
        # 按积分排序
        sorted_users = sorted(users.items(), key=lambda x: x[1].get("total_points", 0), reverse=True)
        
        # 构建排行榜
        rank_list = []
        for i, (uid, data) in enumerate(sorted_users[:limit]):
            rank_list.append({
                "rank": i + 1,
                "user_id": uid,
                "points": data.get("total_points", 0),
                "sign_count": data.get("sign_count", 0),
                "consecutive_days": data.get("consecutive_days", 0)
            })
            
        return rank_list
        
    async def generate_rank_message(self, group_id: str, limit: int = 10) -> str:
        """生成排行榜消息"""
        rank_list = self.get_points_rank(group_id, limit)
        
        if not rank_list:
            return "暂无积分排行数据"
            
        # 查询用户昵称
        for user in rank_list:
            try:
                # 获取群成员信息
                member_info = await self.bot.get_group_member_info(
                    group_id=int(group_id),
                    user_id=int(user["user_id"])
                )
                # 使用群名片或昵称
                user["nickname"] = member_info.get("data", {}).get("card") or member_info.get("data", {}).get("nickname", "未知用户")
            except Exception as e:
                logger.error(f"获取用户 {user['user_id']} 信息失败: {e}")
                user["nickname"] = f"用户{user['user_id']}"
                
        # 构建排行榜消息
        lines = ["📊 积分排行榜TOP10 📊"]
        for user in rank_list:
            medal = "🥇" if user["rank"] == 1 else "🥈" if user["rank"] == 2 else "🥉" if user["rank"] == 3 else f"{user['rank']}."
            lines.append(f"{medal} {user['nickname']}(QQ: {user['user_id']}): {user['points']}积分 | 签到{user['sign_count']}次 | 连续{user['consecutive_days']}天")
            
        # 添加群统计信息
        statistics = self.sign_data.get(group_id, {}).get("statistics", {})
        lines.append(f"\n📝 群统计: {statistics.get('total_signs', 0)}次签到 | {statistics.get('total_points', 0)}总积分")
        
        return "\n".join(lines)
        
    def get_user_sign_info(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """获取用户签到信息"""
        default_info = {
            "total_points": 0,
            "sign_count": 0,
            "consecutive_days": 0,
            "last_sign_date": "",
            "history": []
        }
        
        return self.sign_data.get(group_id, {}).get("users", {}).get(user_id, default_info)
        
    def get_user_sign_detail(self, group_id: str, user_id: str) -> str:
        """获取用户签到详细信息"""
        user_info = self.get_user_sign_info(group_id, user_id)
        
        # 计算签到率
        days_registered = len(user_info.get("history", []))
        sign_count = user_info.get("sign_count", 0)
        sign_rate = (sign_count / max(1, days_registered)) * 100 if days_registered > 0 else 0
        
        # 构建消息
        lines = [
            "📋 个人签到统计",
            f"💰 积分: {user_info.get('total_points', 0)}",
            f"📝 总签到: {sign_count}次",
            f"🔄 连续签到: {user_info.get('consecutive_days', 0)}天",
            f"📊 签到率: {sign_rate:.1f}%"
        ]
        
        # 添加最近签到记录
        recent_history = user_info.get("history", [])[-5:]  # 最近5条记录
        if recent_history:
            lines.append("\n📜 最近签到记录:")
            for record in recent_history:
                lines.append(f"- {record.get('date')}: +{record.get('points')}积分")
                
        # 签到提醒
        today = self.get_today_date()
        if user_info.get("last_sign_date") != today:
            lines.append("\n⏰ 提醒: 今天还没有签到，发送 /sign 立即签到")
            
        return "\n".join(lines)
        
    # 商店功能
    def get_shop_items(self, group_id: str) -> List[Dict[str, Any]]:
        """获取可兑换的商店物品"""
        # 合并全局商品和群特定商品
        global_items = self.shop_data.get("global", [])
        group_items = self.shop_data.get("groups", {}).get(group_id, [])
        
        # 为每个项目添加ID和是否可用标记
        all_items = []
        for i, item in enumerate(global_items):
            item_copy = item.copy()
            item_copy["id"] = i + 1
            item_copy["type"] = "global"
            # 检查物品类型是否可用
            item_name = item_copy.get("name", "")
            item_copy["usable"] = self.item_types.get(item_name, {}).get("usable", False)
            all_items.append(item_copy)
            
        group_start_id = len(global_items) + 1
        for i, item in enumerate(group_items):
            item_copy = item.copy()
            item_copy["id"] = group_start_id + i
            item_copy["type"] = "group"
            # 检查物品类型是否可用
            item_name = item_copy.get("name", "")
            item_copy["usable"] = self.item_types.get(item_name, {}).get("usable", False)
            all_items.append(item_copy)
            
        return all_items
        
    def get_shop_list(self, group_id: str) -> str:
        """获取商店列表文本"""
        items = self.get_shop_items(group_id)
        
        if not items:
            return "商店中暂无可兑换物品"
            
        lines = ["🛍️ 积分兑换商店 🛍️"]
        for item in items:
            item_type = "【全局】" if item["type"] == "global" else "【本群】"
            usable_mark = "🔹" if item.get("usable", False) else "🔸"
            lines.append(f"{item['id']}. {usable_mark} {item_type} {item['name']} - {item['points']}积分\n   {item['description']}")
            
        lines.append("\n💡 使用 /exchange <ID> 兑换物品")
        if any(item.get("usable", False) for item in items):
            lines.append("🔹 标记的物品可以使用 /use <物品ID> 命令使用")
        return "\n".join(lines)
        
    def add_shop_item(self, group_id: str, name: str, points: int, description: str, is_global: bool = False) -> bool:
        """添加商店物品"""
        item = {
            "name": name,
            "points": points,
            "description": description,
            "created_time": int(time.time())
        }
        
        if is_global:
            self.shop_data["global"].append(item)
        else:
            if group_id not in self.shop_data["groups"]:
                self.shop_data["groups"][group_id] = []
            self.shop_data["groups"][group_id].append(item)
            
        # 保存商店数据
        self.save_json(self.shop_data_file, self.shop_data)
        return True
        
    def exchange_item(self, group_id: str, user_id: str, item_id: int) -> Tuple[bool, str]:
        """兑换物品"""
        items = self.get_shop_items(group_id)
        
        # 查找商品
        target_item = None
        for item in items:
            if item["id"] == item_id:
                target_item = item
                break
        
        if not target_item:
            return False, f"未找到ID为{item_id}的物品"
            
        # 获取用户积分
        user_points = self.get_user_sign_info(group_id, user_id).get("total_points", 0)
        
        # 检查积分是否足够
        if user_points < target_item["points"]:
            return False, f"积分不足，需要{target_item['points']}积分，您当前有{user_points}积分"
            
        # 扣除积分
        self.sign_data[group_id]["users"][user_id]["total_points"] -= target_item["points"]
        
        # 记录兑换历史
        if "exchanges" not in self.sign_data[group_id]["users"][user_id]:
            self.sign_data[group_id]["users"][user_id]["exchanges"] = []
            
        # 添加到用户背包
        if "bag" not in self.sign_data[group_id]["users"][user_id]:
            self.sign_data[group_id]["users"][user_id]["bag"] = []
            
        # 为物品生成唯一ID
        bag_item_id = int(time.time() * 1000) % 1000000
        
        # 获取物品过期时间设置（如果有）
        expires_in_days = target_item.get("expires_in_days", None)
        expire_time = None
        
        if expires_in_days is not None and expires_in_days > 0:
            # 计算过期时间戳
            expire_time = int(time.time() + expires_in_days * 86400)  # 转换为秒
            
        # 添加到背包
        bag_item = {
            "id": bag_item_id,
            "shop_id": item_id,
            "name": target_item["name"],
            "description": target_item["description"],
            "obtained_time": int(time.time()),
            "obtained_date": self.get_today_date(),
            "used": False,
            "usable": target_item.get("usable", False),
            "expire_time": expire_time  # 添加过期时间字段
        }
        
        self.sign_data[group_id]["users"][user_id]["bag"].append(bag_item)
        
        # 记录兑换记录
        self.sign_data[group_id]["users"][user_id]["exchanges"].append({
            "item_id": item_id,
            "item_name": target_item["name"],
            "points": target_item["points"],
            "time": int(time.time()),
            "date": self.get_today_date(),
            "bag_item_id": bag_item_id
        })
        
        # 保存数据
        self.save_json(self.sign_data_file, self.sign_data)
        
        # 构建返回消息
        expire_info = ""
        if expire_time:
            expire_date = time.strftime("%Y-%m-%d %H:%M", time.localtime(expire_time))
            expire_info = f"（{expires_in_days}天后过期，过期时间：{expire_date}）"
            
        return True, f"兑换成功！消费{target_item['points']}积分兑换了 {target_item['name']} {expire_info}\n物品已添加到您的背包，使用 /bag 命令查看\n当前剩余积分: {self.sign_data[group_id]['users'][user_id]['total_points']}"
        
    def get_user_bag(self, group_id: str, user_id: str) -> List[Dict[str, Any]]:
        """获取用户背包内容"""
        return self.sign_data.get(group_id, {}).get("users", {}).get(user_id, {}).get("bag", [])

    def format_bag_message(self, group_id: str, user_id: str) -> str:
        """格式化背包消息"""
        bag_items = self.get_user_bag(group_id, user_id)
        
        if not bag_items:
            return "您的背包中暂无物品"
        
        lines = ["🎒 您的物品背包 🎒"]
        
        # 清理已过期的物品
        current_time = int(time.time())
        valid_bag_items = []
        expired_count = 0
        
        for item in bag_items:
            expire_time = item.get("expire_time")
            if expire_time is not None and expire_time < current_time:
                # 物品已过期
                expired_count += 1
            else:
                valid_bag_items.append(item)
                
        # 如果有过期物品，更新用户背包
        if expired_count > 0:
            self.sign_data[group_id]["users"][user_id]["bag"] = valid_bag_items
            self.save_json(self.sign_data_file, self.sign_data)
            lines.append(f"\n⚠️ {expired_count} 个物品已过期并被自动清理")
            
        if not valid_bag_items:
            lines.append("\n您的背包中暂无有效物品")
            return "\n".join(lines)
        
        # 分类显示，同时对相同物品进行计数
        usable_items = []
        used_items = []
        other_items = []
        
        # 创建一个临时字典来统计相同物品
        item_counts = {}
        
        for item in valid_bag_items:
            item_key = f"{item.get('name')}-{item.get('description')}-{item.get('used', False)}-{item.get('usable', False)}"
            if item_key not in item_counts:
                item_counts[item_key] = {
                    "item": item,
                    "count": 1,
                    "ids": [item['id']]
                }
            else:
                item_counts[item_key]["count"] += 1
                item_counts[item_key]["ids"].append(item['id'])
        
        # 将统计结果分类
        for item_data in item_counts.values():
            item = item_data["item"]
            if item.get("used", False):
                used_items.append((item, item_data["count"], item_data["ids"]))
            elif item.get("usable", False):
                usable_items.append((item, item_data["count"], item_data["ids"]))
            else:
                other_items.append((item, item_data["count"], item_data["ids"]))
        
        # 显示可使用的物品
        if usable_items:
            lines.append("\n🔹 可使用物品:")
            for item_tuple in usable_items:
                item, count, ids = item_tuple
                obtain_date = item.get("obtained_date", "未知日期")
                
                # 如果是多个相同物品，只显示一个ID
                if count == 1:
                    item_line = f"  {item['id']}: {item['name']} - {obtain_date}"
                else:
                    item_line = f"  {ids[0]}: {item['name']} - {obtain_date} (x{count})"
                
                # 添加过期信息
                expire_time = item.get("expire_time")
                if expire_time is not None:
                    days_left = (expire_time - current_time) // 86400
                    hours_left = ((expire_time - current_time) % 86400) // 3600
                    if days_left > 0:
                        item_line += f" (剩余{days_left}天{hours_left}小时)"
                    else:
                        item_line += f" (剩余{hours_left}小时)"
                
                lines.append(item_line)
                lines.append(f"    {item['description']}")
        
        # 显示其他物品
        if other_items:
            lines.append("\n🔸 收藏品:")
            for item_tuple in other_items:
                item, count, ids = item_tuple
                obtain_date = item.get("obtained_date", "未知日期")
                
                # 如果是多个相同物品，只显示一个ID
                if count == 1:
                    item_line = f"  {item['id']}: {item['name']} - {obtain_date}"
                else:
                    item_line = f"  {ids[0]}: {item['name']} - {obtain_date} (x{count})"
                
                # 添加过期信息
                expire_time = item.get("expire_time")
                if expire_time is not None:
                    days_left = (expire_time - current_time) // 86400
                    hours_left = ((expire_time - current_time) % 86400) // 3600
                    if days_left > 0:
                        item_line += f" (剩余{days_left}天{hours_left}小时)"
                    else:
                        item_line += f" (剩余{hours_left}小时)"
                        
                lines.append(item_line)
        
        # 显示已使用物品
        if used_items:
            lines.append("\n✅ 已使用物品:")
            for item_tuple in used_items:
                item, count, ids = item_tuple
                obtain_date = item.get("obtained_date", "未知日期")
                
                # 如果是多个相同物品，只显示一个ID
                if count == 1:
                    item_line = f"  {item['id']}: {item['name']} - {obtain_date}"
                else:
                    item_line = f"  {ids[0]}: {item['name']} - {obtain_date} (x{count})"
                
                lines.append(item_line)
        
        lines.append("\n💡 使用 /use <物品ID> 使用物品")
        return "\n".join(lines)
        
    def update_points(self, group_id: str, user_id: str, points: int) -> int:
        """更新用户积分
        
        参数:
            group_id: 群号
            user_id: 用户QQ号
            points: 要添加的积分（可为负数）
            
        返回:
            用户当前总积分
        """
        # 确保群配置存在
        self.ensure_group_config(group_id)
        
        # 如果用户不存在，创建用户数据
        if user_id not in self.sign_data[group_id]["users"]:
            self.sign_data[group_id]["users"][user_id] = {
                "total_points": 0,
                "sign_count": 0,
                "consecutive_days": 0,
                "last_sign_date": "",
                "history": []
            }
            
        # 更新积分
        self.sign_data[group_id]["users"][user_id]["total_points"] += points
        
        # 确保积分不为负数
        if self.sign_data[group_id]["users"][user_id]["total_points"] < 0:
            self.sign_data[group_id]["users"][user_id]["total_points"] = 0
            
        # 保存数据
        self.save_json(self.sign_data_file, self.sign_data)
        
        # 返回更新后的积分
        return self.sign_data[group_id]["users"][user_id]["total_points"]
        
    async def perform_draw(self, event: Dict[str, Any], group_id: str, user_id: str, draw_times: int = 1) -> Tuple[bool, str]:
        """执行抽奖
        
        参数:
            event: 事件数据
            group_id: 群号
            user_id: 用户QQ号
            draw_times: 抽奖次数
            
        返回:
            (是否成功, 结果消息)
        """
        # 检查次数合法性
        if draw_times <= 0:
            return False, "抽奖次数必须为正数"
        if draw_times > 10:
            return False, "单次最多抽奖10次"
            
        # 计算总消耗积分
        total_cost = self.draw_config["cost_per_draw"] * draw_times
        
        # 获取用户积分
        user_points = self.get_user_sign_info(group_id, user_id).get("total_points", 0)
        
        # 检查积分是否足够
        if user_points < total_cost:
            return False, f"积分不足，需要{total_cost}积分，您当前有{user_points}积分"
            
        # 扣除积分
        remaining_points = self.update_points(group_id, user_id, -total_cost)
        
        # 执行抽奖
        draw_results = []
        for _ in range(draw_times):
            result = self._draw_once(group_id, user_id)
            draw_results.append(result)
            
        # 统计结果
        items_by_pool = {"common": [], "rare": [], "epic": []}
        for item in draw_results:
            items_by_pool[item["pool"]].append(item)
            
        # 构建结果消息
        nickname = event.get("sender", {}).get("nickname", "用户")
        result_lines = [
            f"🎊 {nickname} (QQ: {user_id}) 的抽奖结果 🎊",
            f"抽奖次数: {draw_times}次",
            f"消耗积分: {total_cost}",
            f"当前剩余: {remaining_points}积分"
        ]
        
        # 按奖池分类显示结果
        if items_by_pool["epic"]:
            result_lines.append("\n🌟 史诗物品:")
            for item in items_by_pool["epic"]:
                result_lines.append(f"- {item['name']}" + (f" (积分+{item['bonus_points']})" if "bonus_points" in item else ""))
                
        if items_by_pool["rare"]:
            result_lines.append("\n💎 稀有物品:")
            for item in items_by_pool["rare"]:
                result_lines.append(f"- {item['name']}" + (f" (积分+{item['bonus_points']})" if "bonus_points" in item else ""))
                
        if items_by_pool["common"]:
            result_lines.append("\n📦 普通物品:")
            for item in items_by_pool["common"]:
                result_lines.append(f"- {item['name']}" + (f" (积分+{item['bonus_points']})" if "bonus_points" in item else ""))
                
        result_lines.append("\n💡 所有物品已自动添加到背包，使用 /bag 命令查看")
        
        # 返回结果
        return True, "\n".join(result_lines)
        
    def _draw_once(self, group_id: str, user_id: str) -> Dict[str, Any]:
        """执行一次抽奖
        
        参数:
            group_id: 群号
            user_id: 用户QQ号
            
        返回:
            抽奖结果
        """
        # 随机选择奖池
        pools = self.draw_config["pools"]
        pool_weights = [(pool_name, pool_info["weight"]) for pool_name, pool_info in pools.items()]
        pool_name = self._weighted_choice([p[0] for p in pool_weights], [p[1] for p in pool_weights])
        
        # 随机选择物品
        pool = pools[pool_name]
        items = pool["items"]
        item_weights = [item["weight"] for item in items]
        selected_item = items[self._weighted_index(item_weights)]
        
        # 复制物品信息
        item_result = selected_item.copy()
        item_result["pool"] = pool_name
        
        # 处理特殊物品（如经验卡，需要随机生成积分）
        if "min_points" in item_result and "max_points" in item_result:
            bonus_points = random.randint(item_result["min_points"], item_result["max_points"])
            item_result["bonus_points"] = bonus_points
            # 为用户添加积分
            self.update_points(group_id, user_id, bonus_points)
            item_result["description"] = f"获得{bonus_points}积分的经验卡"
        
        # 将物品添加到用户背包
        self._add_item_to_bag(group_id, user_id, item_result)
        
        return item_result
        
    def _weighted_choice(self, items: List[Any], weights: List[int]) -> Any:
        """根据权重随机选择一项
        
        参数:
            items: 可选项列表
            weights: 对应的权重列表
            
        返回:
            选中的项
        """
        total_weight = sum(weights)
        rand_val = random.random() * total_weight
        
        cumulative_weight = 0
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if rand_val <= cumulative_weight:
                return items[i]
                
        # 防止浮点误差，返回最后一项
        return items[-1]
        
    def _weighted_index(self, weights: List[int]) -> int:
        """根据权重随机选择索引
        
        参数:
            weights: 权重列表
            
        返回:
            选中的索引
        """
        total_weight = sum(weights)
        rand_val = random.random() * total_weight
        
        cumulative_weight = 0
        for i, weight in enumerate(weights):
            cumulative_weight += weight
            if rand_val <= cumulative_weight:
                return i
                
        # 防止浮点误差，返回最后一个索引
        return len(weights) - 1
        
    def _add_item_to_bag(self, group_id: str, user_id: str, item: Dict[str, Any]) -> None:
        """将物品添加到用户背包
        
        参数:
            group_id: 群号
            user_id: 用户QQ号
            item: 物品信息
        """
        # 确保用户数据存在
        if user_id not in self.sign_data[group_id]["users"]:
            self.sign_data[group_id]["users"][user_id] = {
                "total_points": 0,
                "sign_count": 0,
                "consecutive_days": 0,
                "last_sign_date": "",
                "history": []
            }
            
        # 确保背包存在
        if "bag" not in self.sign_data[group_id]["users"][user_id]:
            self.sign_data[group_id]["users"][user_id]["bag"] = []
            
        # 为物品生成唯一ID
        bag_item_id = int(time.time() * 1000) % 1000000 + random.randint(1, 999)
        
        # 检查物品是否需要设置过期时间
        expires_in_days = item.get("expires_in_days", None)
        expire_time = None
        
        if expires_in_days is not None and expires_in_days > 0:
            # 计算过期时间戳
            expire_time = int(time.time() + expires_in_days * 86400)  # 转换为秒
        
        # 构建背包物品
        bag_item = {
            "id": bag_item_id,
            "name": item["name"],
            "description": item.get("description", self.item_types.get(item["name"], {}).get("description", "未知物品")),
            "obtained_time": int(time.time()),
            "obtained_date": self.get_today_date(),
            "used": False,
            "usable": self.item_types.get(item["name"], {}).get("usable", False),
            "source": "抽奖",
            "pool": item.get("pool", "unknown"),
            "expire_time": expire_time  # 添加过期时间字段
        }
        
        # 添加到背包
        self.sign_data[group_id]["users"][user_id]["bag"].append(bag_item)
        
        # 保存数据
        self.save_json(self.sign_data_file, self.sign_data)
        
    def get_draw_info(self) -> str:
        """获取抽奖信息
        
        返回:
            抽奖信息字符串
        """
        config = self.draw_config
        cost = config["cost_per_draw"]
        
        lines = [
            "🎰 米池抽奖系统 🎰",
            f"每次抽奖消耗 {cost} 积分",
            f"使用命令: /draw <次数> 参与抽奖 (最多10次)",
            "\n📊 奖池信息:"
        ]
        
        # 添加奖池信息
        for pool_name, pool_info in config["pools"].items():
            if pool_name == "common":
                lines.append("📦 普通奖池 (70%):")
            elif pool_name == "rare":
                lines.append("💎 稀有奖池 (25%):")
            elif pool_name == "epic":
                lines.append("🌟 史诗奖池 (5%):")
                
            # 添加物品信息
            for item in pool_info["items"]:
                item_name = item["name"]
                item_weight = item["weight"]
                pool_weight = pool_info["weight"]
                
                # 计算实际概率 (池权重 * 物品在池中权重)
                total_pool_weight = sum(i["weight"] for i in pool_info["items"])
                item_prob = (pool_weight / 100) * (item_weight / total_pool_weight) * 100
                
                # 格式化物品信息
                if "min_points" in item and "max_points" in item:
                    lines.append(f"  - {item_name} ({item['min_points']}~{item['max_points']}积分) [{item_prob:.2f}%]")
                else:
                    lines.append(f"  - {item_name} [{item_prob:.2f}%]")
                    
        return "\n".join(lines)

    async def use_item(self, event: Dict[str, Any], group_id: str, user_id: str, item_id: int) -> Tuple[bool, str]:
        """使用物品"""
        bag_items = self.get_user_bag(group_id, user_id)
        
        # 查找物品
        target_item = None
        item_index = -1
        for i, item in enumerate(bag_items):
            if item["id"] == item_id:
                target_item = item
                item_index = i
                break
        
        if not target_item:
            return False, f"未找到ID为{item_id}的物品"
        
        # 检查是否已经使用
        if target_item.get("used", False):
            return False, f"该物品已经被使用过了"
            
        # 检查是否可使用
        if not target_item.get("usable", False):
            return False, f"该物品不可使用，仅作收藏"
            
        # 检查物品是否过期
        expire_time = target_item.get("expire_time")
        if expire_time is not None and expire_time < int(time.time()):
            # 删除过期物品
            self.sign_data[group_id]["users"][user_id]["bag"].pop(item_index)
            self.save_json(self.sign_data_file, self.sign_data)
            return False, f"该物品已过期无法使用"
        
        # 根据物品类型执行不同操作
        item_name = target_item.get("name")
        result_msg = f"使用了物品: {item_name}"
        
        if item_name == "经验卡" or item_name == "大额经验卡":
            # 增加积分
            if item_name == "经验卡":
                bonus_points = random.randint(10, 50)
            else:
                bonus_points = random.randint(100, 300)
            self.update_points(group_id, user_id, bonus_points)
            result_msg = f"使用了{item_name}，获得额外{bonus_points}积分！"
            
        elif item_name == "双倍签到卡":
            # 添加双倍签到标记
            if "buffs" not in self.sign_data[group_id]["users"][user_id]:
                self.sign_data[group_id]["users"][user_id]["buffs"] = {}
            
            # 设置双倍签到Buff，持续1天
            self.sign_data[group_id]["users"][user_id]["buffs"]["double_sign"] = {
                "expires": int(time.time()) + 86400,  # 24小时后过期
                "multiplier": 2
            }
            result_msg = f"使用了{item_name}，您的下次签到将获得双倍积分！(24小时内有效)"
            
        elif item_name == "禁言卡" or item_name == "超级禁言卡":
            # 启动禁言流程，先要求用户输入要禁言的对象
            target_user_id = await self._ask_for_target_user(event, group_id, user_id, f"请@要禁言的成员，或直接发送其QQ号")
            
            if not target_user_id:
                return False, "操作已取消或超时"
                
            # 设置禁言时长
            mute_time = 60  # 普通禁言卡：1分钟
            if item_name == "超级禁言卡":
                mute_time = 30 * 60  # 超级禁言卡：30分钟
                
            # 执行禁言操作
            try:
                await self.bot._call_api("/set_group_ban", {
                    "group_id": int(group_id),
                    "user_id": int(target_user_id),
                    "duration": mute_time
                })
                
                # 获取使用者和目标用户的昵称
                user_nickname = event.get("sender", {}).get("nickname", "用户")
                target_nickname = "未知用户"
                
                # 尝试获取目标用户的昵称
                try:
                    # 先尝试获取群名片
                    result = await self.bot._call_api("/get_group_member_info", {
                        "group_id": int(group_id),
                        "user_id": int(target_user_id),
                        "no_cache": True
                    })
                    # LLOneBot API返回格式为 {"status": "ok", "data": {...}}
                    if result.get("status") == "ok" and result.get("data"):
                        member_info = result.get("data")
                        target_nickname = member_info.get("card", "") or member_info.get("nickname", "未知用户")
                except Exception as e:
                    logger.warning(f"获取目标用户昵称失败: {e}")
                
                # 添加@被禁言用户的CQ码
                at_code = f"[CQ:at,qq={target_user_id}]"
                result_msg = f"{user_nickname}({user_id}) 使用了{item_name}，成功禁言 {at_code}({target_user_id}, {target_nickname}) {mute_time//60}分钟"
            except Exception as e:
                logger.error(f"禁言操作失败: {e}")
                return False, f"禁言操作失败: {str(e)}"
                
        elif item_name == "解除禁言卡":
            # 启动解除禁言流程，先要求用户输入要解除禁言的对象
            target_user_id = await self._ask_for_target_user(event, group_id, user_id, f"请@要解除禁言的成员，或直接发送其QQ号")
            
            if not target_user_id:
                return False, "操作已取消或超时"
                
            # 执行解除禁言操作
            try:
                await self.bot._call_api("/set_group_ban", {
                    "group_id": int(group_id),
                    "user_id": int(target_user_id),
                    "duration": 0  # 设置为0表示解除禁言
                })
                
                # 获取使用者和目标用户的昵称
                user_nickname = event.get("sender", {}).get("nickname", "用户")
                target_nickname = "未知用户"
                
                # 尝试获取目标用户的昵称
                try:
                    # 先尝试获取群名片
                    result = await self.bot._call_api("/get_group_member_info", {
                        "group_id": int(group_id),
                        "user_id": int(target_user_id),
                        "no_cache": True
                    })
                    # LLOneBot API返回格式为 {"status": "ok", "data": {...}}
                    if result.get("status") == "ok" and result.get("data"):
                        member_info = result.get("data")
                        target_nickname = member_info.get("card", "") or member_info.get("nickname", "未知用户")
                except Exception as e:
                    logger.warning(f"获取目标用户昵称失败: {e}")
                
                # 添加@被解除禁言用户的CQ码
                at_code = f"[CQ:at,qq={target_user_id}]"
                result_msg = f"{user_nickname}({user_id}) 使用了{item_name}，成功解除 {at_code}({target_user_id}, {target_nickname}) 的禁言"
            except Exception as e:
                logger.error(f"解除禁言操作失败: {e}")
                return False, f"解除禁言操作失败: {str(e)}"
        
        elif item_name == "群活跃报告":
            # 直接调用活跃度报告功能
            try:
                # 直接调用主类中的群活跃度报告功能
                await self.bot.system_handler._handle_group_activity(event, 7)  # 默认显示7天的数据
                result_msg = f"已使用{item_name}，活跃度报告已生成"
            except Exception as e:
                logger.error(f"生成群活跃报告失败: {e}")
                return False, f"生成群活跃报告失败: {str(e)}"
            
        elif item_name in ["改名卡", "抽奖券", "置顶发言"]:
            # 这些物品需要管理员处理，只标记为已使用，并通知管理员
            nickname = event.get("sender", {}).get("nickname", "用户")
            admins = self.bot.config.get("bot", {}).get("superusers", [])
            admin_notice = f"用户 {nickname}({user_id}) 使用了 {item_name}，请及时处理！"
            
            # 向群内所有在线管理员发送通知
            for admin_id in admins:
                try:
                    await self.bot.send_msg(
                        message_type="private",
                        user_id=int(admin_id),
                        message=admin_notice
                    )
                except Exception as e:
                    logger.error(f"向管理员 {admin_id} 发送通知失败: {e}")
            
            result_msg = f"使用了{item_name}，已通知管理员处理，请耐心等待"
        
        elif item_name == "专属头衔":
            # 先要求用户输入想要的头衔
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"[CQ:reply,id={event.get('message_id', 0)}]请输入您想要设置的专属头衔(30秒内回复)："
            )
            
            # 等待用户回复
            try:
                # 设置等待超时时间
                timeout = 30  # 30秒超时
                start_time = time.time()
                
                while time.time() - start_time < timeout:
                    # 等待消息
                    await asyncio.sleep(0.5)
                    
                    # 检查是否有新消息
                    new_events = self.bot.get_events(user_id=int(user_id), group_id=int(group_id))
                    
                    for new_event in new_events:
                        # 检查是否是同一个用户在同一个群的消息
                        if (new_event.get('user_id') == int(user_id) and 
                            new_event.get('group_id') == int(group_id) and
                            new_event.get('message_type') == 'group' and
                            new_event.get('time', 0) > event.get('time', 0)):
                            
                            # 获取用户输入的头衔
                            special_title = new_event.get('raw_message', '').strip()
                            
                            # 检查头衔长度
                            if len(special_title) > 20:
                                await self.bot.send_msg(
                                    message_type="group",
                                    group_id=int(group_id),
                                    message=f"[CQ:reply,id={new_event.get('message_id', 0)}]头衔过长，最多支持20个字符，请重新设置"
                                )
                                return False, "头衔设置失败：内容过长"
                            
                            # 检查机器人是否有管理员权限
                            try:
                                # 获取机器人自身QQ号
                                bot_qq = int(self.bot.config.get("bot", {}).get("self_id", "0"))
                                
                                # 获取机器人在群内的角色
                                response = await self.bot._call_api('get_group_member_info', {
                                    'group_id': int(group_id),
                                    'user_id': bot_qq
                                })
                                
                                has_admin = False
                                if response.get("status") == "ok" and response.get("data"):
                                    role = response.get("data", {}).get("role", "member")
                                    has_admin = role in ["admin", "owner"]
                                
                                if not has_admin:
                                    await self.bot.send_msg(
                                        message_type="group",
                                        group_id=int(group_id),
                                        message=f"[CQ:reply,id={new_event.get('message_id', 0)}]机器人没有管理员权限，无法设置专属头衔"
                                    )
                                    return False, "头衔设置失败：机器人权限不足"
                                
                                # 调用API设置专属头衔
                                set_response = await self.bot._call_api('set_group_special_title', {
                                    'group_id': int(group_id),
                                    'user_id': int(user_id),
                                    'special_title': special_title,
                                    'duration': -1  # 永久
                                })
                                
                                if set_response.get("status") == "ok":
                                    result_msg = f"成功设置专属头衔：{special_title}"
                                else:
                                    result_msg = f"头衔设置失败，可能是接口限制或网络问题"
                                
                            except Exception as e:
                                logger.error(f"设置专属头衔失败: {e}")
                                result_msg = f"头衔设置失败：{str(e)}"
                            
                            # 退出等待循环
                            return True, result_msg
                
                # 超时处理
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"[CQ:reply,id={event.get('message_id', 0)}]操作超时，头衔设置已取消"
                )
                return False, "头衔设置失败：操作超时"
                
            except Exception as e:
                logger.error(f"设置专属头衔过程中出错: {e}")
                return False, f"头衔设置过程中出错: {str(e)}"
        
        # 标记物品为已使用
        self.sign_data[group_id]["users"][user_id]["bag"][item_index]["used"] = True
        self.sign_data[group_id]["users"][user_id]["bag"][item_index]["use_time"] = int(time.time())
        self.sign_data[group_id]["users"][user_id]["bag"][item_index]["use_date"] = self.get_today_date()
        
        # 保存数据
        self.save_json(self.sign_data_file, self.sign_data)
        
        return True, result_msg
        
    async def _ask_for_target_user(self, event: Dict[str, Any], group_id: str, user_id: str, prompt: str) -> Optional[str]:
        """询问用户输入目标用户
        
        参数:
            event: 事件数据
            group_id: 群号
            user_id: 用户QQ号
            prompt: 提示信息
            
        返回:
            目标用户QQ号，如果取消或超时则返回None
        """
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 发送提示信息
        await self.bot.send_msg(
            message_type="group",
            group_id=int(group_id),
            message=f"{reply_code}{prompt}，30秒内回复，发送'取消'可取消操作"
        )
        
        # 记录当前用户正在进行的操作
        if not hasattr(self, "pending_operations"):
            self.pending_operations = {}
            
        # 设置操作状态，用于后续消息处理
        operation_id = f"{group_id}_{user_id}_{int(time.time())}"
        self.pending_operations[operation_id] = {
            "type": "waiting_for_target",
            "expire_time": time.time() + 30,  # 30秒超时
            "result": None
        }
        
        # 等待用户回复
        for _ in range(30):  # 最多等待30秒
            if self.pending_operations[operation_id]["result"]:
                # 用户已回复
                target_user = self.pending_operations[operation_id]["result"]
                del self.pending_operations[operation_id]  # 清理操作记录
                return target_user
                
            if time.time() > self.pending_operations[operation_id]["expire_time"]:
                # 超时
                del self.pending_operations[operation_id]
                return None
                
            await asyncio.sleep(1)
            
        # 超时
        del self.pending_operations[operation_id]
        return None

    async def calc_sign_points(self, group_id: str, user_id: str) -> Tuple[int, int, List[str]]:
        """计算签到获得的积分"""
        group_config = self.sign_data.get(group_id, {}).get("config", self.default_config)
        user_data = self.sign_data.get(group_id, {}).get("users", {}).get(user_id, {
            "total_points": 0,
            "sign_count": 0,
            "consecutive_days": 0,
            "last_sign_date": "",
            "history": []
        })
        
        # 基础积分
        base_points = group_config.get("base_points", 5)
        
        # 随机浮动
        random_range = group_config.get("random_range", 5)
        random_points = random.randint(-random_range, random_range)
        points = max(1, base_points + random_points)  # 确保至少获得1积分
        
        # 检查连续签到
        last_sign_date = user_data.get("last_sign_date", "")
        today = self.get_today_date()
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        
        consecutive_days = user_data.get("consecutive_days", 0)
        
        # 如果昨天签到了，连续天数+1，否则重置为1
        if last_sign_date == yesterday:
            consecutive_days += 1
        else:
            consecutive_days = 1
            
        # 计算连续签到奖励
        bonus_points = 0
        bonus_messages = []
        consecutive_bonus = group_config.get("consecutive_bonus", {})
        
        for days, bonus in consecutive_bonus.items():
            if consecutive_days == int(days):
                bonus_points += bonus
                bonus_messages.append(f"🎉 连续签到{days}天奖励: +{bonus}积分")
                
        # 检查是否有双倍签到Buff
        buffs = user_data.get("buffs", {})
        if "double_sign" in buffs and buffs["double_sign"]["expires"] > time.time():
            multiplier = buffs["double_sign"]["multiplier"]
            original_points = points + bonus_points
            points = int(original_points * multiplier)
            bonus_points = points - original_points
            bonus_messages.append(f"🎭 双倍签到卡生效: 额外 +{bonus_points}积分")
            # 使用后移除Buff
            del buffs["double_sign"]
        
        # 总积分 = 基础积分 + 随机浮动 + 连续奖励 + Buff加成
        total_points = points + bonus_points
        
        return total_points, consecutive_days, bonus_messages
        
    # 处理消息事件
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = str(event.get('user_id', 0))
        group_id = str(event.get('group_id')) if message_type == 'group' else "0"
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        raw_message = event.get('raw_message', '')  # 获取原始消息内容
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 只处理群消息
        if message_type != 'group' or not group_id:
            return False

        # 检查群是否已授权（如果存在授权插件）
        auth_plugin = self.bot.plugin_manager.get_plugin_by_name("GroupAuth")
        if auth_plugin and hasattr(auth_plugin, "is_authorized"):
            if not auth_plugin.is_authorized(int(group_id)):
                return False  # 如果群未授权，跳过处理
                
        # 处理等待用户输入的情况
        if hasattr(self, "pending_operations") and self.pending_operations:
            # 检查是否有等待中的操作
            for operation_id, operation in list(self.pending_operations.items()):
                if operation["expire_time"] < time.time():
                    # 操作已过期，移除
                    del self.pending_operations[operation_id]
                    continue
                    
                if operation["type"] == "waiting_for_target" and operation_id.startswith(f"{group_id}_{user_id}_"):
                    # 用户正在为使用物品选择目标
                    if raw_message.lower() in ["取消", "cancel"]:
                        # 用户取消操作
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=int(group_id),
                            message=f"{reply_code}操作已取消"
                        )
                        del self.pending_operations[operation_id]
                        return True
                        
                    # 解析目标用户ID
                    at_pattern = r'\[CQ:at,qq=(\d+)[^\]]*\]'
                    at_match = re.search(at_pattern, raw_message)
                    
                    if at_match:
                        # 用户使用@方式指定目标
                        target_user_id = at_match.group(1)
                    elif raw_message.strip().isdigit():
                        # 用户直接发送QQ号
                        target_user_id = raw_message.strip()
                    else:
                        # 无效输入
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=int(group_id),
                            message=f"{reply_code}无效的用户，请@用户或直接发送QQ号"
                        )
                        return True
                        
                    # 设置操作结果
                    operation["result"] = target_user_id
                    return True

        # 处理用户命令
        # 签到命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['sign'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 执行签到命令")
            result = await self.perform_sign(event)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{result}"
            )
            return True

        # 个人签到统计命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['mysign'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 查看个人签到统计")
            result = self.get_user_sign_detail(group_id, user_id)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{result}"
            )
            return True

        # 查看积分命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['points'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 查看积分")
            points = self.get_user_sign_info(group_id, user_id).get("total_points", 0)
            # 添加QQ头像
            avatar_url = f"[CQ:image,file=https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640]"
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{avatar_url}\nQQ: {user_id}\n💰 您当前的积分为: {points}"
            )
            return True

        # 排行榜命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['rank'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 查看积分排行榜")
            result = await self.generate_rank_message(group_id)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{result}"
            )
            return True

        # 查看背包命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['bag'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 查看背包")
            result = self.format_bag_message(group_id, user_id)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{result}"
            )
            return True
            
        # 抽奖信息命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['draw_info'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 查看抽奖信息")
            result = self.get_draw_info()
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{result}"
            )
            return True
            
        # 抽奖命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['draw'])
        if is_at_command and match:
            draw_times = int(match.group(1))
            logger.info(f"用户 {user_id} 在群 {group_id} 发起抽奖 {draw_times} 次")
            success, message = await self.perform_draw(event, group_id, user_id, draw_times)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{message}"
            )
            return True

        # 使用物品命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['use'])
        if is_at_command and match:
            item_id = int(match.group(1))
            logger.info(f"用户 {user_id} 在群 {group_id} 尝试使用物品 {item_id}")
            success, message = await self.use_item(event, group_id, user_id, item_id)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{message}"
            )
            return True

        # 兑换商店命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['shop'])
        if is_at_command and match:
            logger.info(f"用户 {user_id} 在群 {group_id} 查看积分商店")
            result = self.get_shop_list(group_id)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{result}"
            )
            return True

        # 兑换物品命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.user_patterns['exchange'])
        if is_at_command and match:
            item_id = int(match.group(1))
            logger.info(f"用户 {user_id} 在群 {group_id} 尝试兑换物品 {item_id}")
            success, message = self.exchange_item(group_id, user_id, item_id)
            await self.bot.send_msg(
                message_type="group",
                group_id=int(group_id),
                message=f"{reply_code}{message}"
            )
            return True

        # 处理管理员命令
        if self.is_admin(int(user_id)):
            # 设置基础积分命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['set_base'])
            if is_at_command and match:
                base_points = int(match.group(1))
                self.ensure_group_config(group_id)
                self.sign_data[group_id]["config"]["base_points"] = base_points
                self.save_json(self.sign_data_file, self.sign_data)
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"{reply_code}✅ 已设置群 {group_id} 的基础签到积分为 {base_points}"
                )
                return True

            # 设置连续签到奖励命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['set_bonus'])
            if is_at_command and match:
                days = match.group(1)
                bonus = int(match.group(2))
                self.ensure_group_config(group_id)
                self.sign_data[group_id]["config"]["consecutive_bonus"][days] = bonus
                self.save_json(self.sign_data_file, self.sign_data)
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"{reply_code}✅ 已设置连续签到 {days} 天的奖励为 {bonus} 积分"
                )
                return True

            # 添加积分命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['add_points'])
            if is_at_command and match:
                target_user = match.group(1)
                points_to_add = int(match.group(2))
                new_points = self.update_points(group_id, target_user, points_to_add)
                
                operation = "增加" if points_to_add > 0 else "减少"
                points_abs = abs(points_to_add)
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"{reply_code}✅ 已为用户 {target_user} {operation} {points_abs} 积分\n当前积分: {new_points}"
                )
                return True
                
            # 添加积分命令(直接QQ号)
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['add_points_direct'])
            if is_at_command and match:
                target_user = match.group(1)
                points_to_add = int(match.group(2))
                new_points = self.update_points(group_id, target_user, points_to_add)
                
                operation = "增加" if points_to_add > 0 else "减少"
                points_abs = abs(points_to_add)
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"{reply_code}✅ 已为用户 {target_user} {operation} {points_abs} 积分\n当前积分: {new_points}"
                )
                return True

            # 添加商店物品命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['shop_add'])
            if is_at_command and match:
                name = match.group(1)
                points = int(match.group(2))
                description = match.group(3)
                
                self.add_shop_item(group_id, name, points, description)
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"{reply_code}✅ 已添加商品 {name} 到商店\n价格: {points} 积分\n描述: {description}"
                )
                return True

            # 标记物品是否可使用命令
            is_at_command, match, _ = handle_at_command(event, self.bot, self.admin_patterns['mark_usable'])
            if is_at_command and match:
                item_id = int(match.group(1))
                state = match.group(2)
                self.ensure_group_config(group_id)
                for item in self.shop_data["global"]:
                    if item["id"] == item_id:
                        item["usable"] = (state == "usable")
                for group_items in self.shop_data["groups"].values():
                    for item in group_items:
                        if item["id"] == item_id:
                            item["usable"] = (state == "usable")
                self.save_json(self.shop_data_file, self.shop_data)
                await self.bot.send_msg(
                    message_type="group",
                    group_id=int(group_id),
                    message=f"{reply_code}✅ 已将ID为{item_id}的物品标记为{'可使用' if state == 'usable' else '不可使用'}"
                )
                return True

        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = SignPoints 