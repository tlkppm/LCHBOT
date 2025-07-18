#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import time
import random
import asyncio
from typing import Dict, Any, List, Set, Tuple, Optional

# 导入Plugin基类和工具函数
from src.plugin_system import Plugin
from src.plugins.utils import handle_at_command

logger = logging.getLogger("LCHBot")

class WordGames(Plugin):
    """
    文字游戏插件，支持成语接龙、猜词游戏、数字炸弹、文字接龙等多种游戏
    命令格式：
    - /game start 成语接龙 - 开始成语接龙游戏
    - /game start 猜词 - 开始猜词游戏
    - /game start 数字炸弹 [最小值] [最大值] - 开始数字炸弹游戏
    - /game start 文字接龙 - 开始文字接龙游戏
    - /game stop - 停止当前游戏
    - 直接回复内容参与游戏
    - @机器人 /game - 同样可用于游戏操作
    - /game rules <游戏名> - 查看游戏规则
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        # 命令格式
        self.command_pattern = re.compile(r'^/game\s+(start|stop|rules|status)(?:\s+(.+))?$')
        # 添加调试日志
        logger.info("WordGames插件初始化，命令模式: " + str(self.command_pattern))
        
        # 数字炸弹游戏的参数解析
        self.number_bomb_pattern = re.compile(r'^数字炸弹(?:\s+(\d+))?(?:\s+(\d+))?$')
        # 恶魔轮盘参数解析
        self.evil_roulette_pattern = re.compile(r'^恶魔轮盘$')
        
        # 定义游戏房间类，用于更好地管理游戏状态
        class GameRoom:
            def __init__(self, game_type: str, host_id: int, host_name: str, group_id: int):
                self.game_type = game_type               # 游戏类型
                self.status = "waiting"                  # 状态: waiting(等待玩家), running(游戏中), ended(已结束)
                self.host_id = host_id                   # 房主ID
                self.host_name = host_name               # 房主昵称
                self.group_id = group_id                 # 群组ID
                self.players = [host_id]                 # 玩家列表，房主自动加入
                self.player_names = {host_id: host_name} # 玩家昵称
                self.create_time = int(time.time())      # 创建时间
                self.start_time = 0                      # 开始时间
                self.last_activity = int(time.time())    # 最后活动时间
                self.round = 0                           # 当前回合数
                self.game_data = {}                      # 游戏特定数据
                self.current_player_index = 0            # 当前玩家索引
                self.target_player_id = None             # 当前目标玩家ID (用于恶魔轮盘)
                self.mentioned_player_id = None          # 当前被@的玩家ID
                self.current_bullet_type = 0             # 当前子弹类型(恶魔轮盘) 0=未装填, 1=空包弹, 2=实弹, 3=双弹
                self.skip_next_player = None             # 跳过下一个指定玩家的回合
                self.bullets = []  # 存储当前回合的所有子弹类型
                
            def add_player(self, player_id: int, player_name: str) -> bool:
                """添加玩家到房间"""
                if player_id in self.players:
                    return False  # 玩家已在房间中
                self.players.append(player_id)
                self.player_names[player_id] = player_name
                self.last_activity = int(time.time())
                return True
                
            def start_game(self) -> bool:
                """开始游戏"""
                if self.status != "waiting" or len(self.players) < 2:
                    return False
                self.status = "running"
                self.start_time = int(time.time())
                self.last_activity = int(time.time())
                self.round = 1
                random.shuffle(self.players)  # 随机打乱玩家顺序
                self.current_player_index = 0  # 从第一个玩家开始
                return True
                
            def update_activity(self) -> None:
                """更新最后活动时间"""
                self.last_activity = int(time.time())
                
            def is_inactive(self, timeout_seconds: int = 300) -> bool:
                """检查房间是否不活跃"""
                return (int(time.time()) - self.last_activity) > timeout_seconds
                
            def is_host(self, user_id: int) -> bool:
                """检查用户是否是房主"""
                return user_id == self.host_id
                
            def is_player(self, user_id: int) -> bool:
                """检查用户是否是玩家"""
                return user_id in self.players
                
            def get_player_count(self) -> int:
                """获取玩家数量"""
                return len(self.players)
                
            def get_player_list_text(self) -> str:
                """获取玩家列表文本"""
                return "\n".join([
                    f"{'👑 ' if player_id == self.host_id else '🎮 '}{name}"
                    for player_id, name in self.player_names.items()
                ])
                
            def format_room_info(self) -> str:
                """格式化房间信息"""
                status_text = "等待中" if self.status == "waiting" else "游戏中" if self.status == "running" else "已结束"
                return (
                    f"【{self.game_type}】房间信息\n"
                    f"状态: {status_text}\n"
                    f"房主: {self.host_name}\n"
                    f"玩家数: {len(self.players)}/8\n\n"
                    f"玩家列表:\n{self.get_player_list_text()}\n\n"
                    f"{'🎮 输入「加入游戏」参与\n⏱️ 人数满2人后，房主可发送「开始游戏」' if self.status == 'waiting' else ''}"
                )
                
            def get_current_player_id(self) -> int:
                """获取当前回合玩家ID"""
                if not self.players:
                    return 0
                return self.players[self.current_player_index]
                
            def get_current_player_name(self) -> str:
                """获取当前回合玩家名称"""
                player_id = self.get_current_player_id()
                return self.player_names.get(player_id, str(player_id))
                
            def next_player(self) -> int:
                """切换到下一个玩家，返回新的玩家ID"""
                if not self.players:
                    return 0
                    
                # 检查游戏数据中的已淘汰玩家列表
                game_data = self.game_data
                eliminated_players = game_data.get("eliminated_players", []) if game_data else []
                
                # 循环找到下一个未淘汰的玩家
                for _ in range(len(self.players)):
                    self.current_player_index = (self.current_player_index + 1) % len(self.players)
                    next_player_id = self.get_current_player_id()
                    
                    # 如果玩家已被淘汰，继续找下一个
                    if next_player_id in eliminated_players:
                        continue
                    
                    # 检查是否需要跳过此玩家
                    if self.skip_next_player == next_player_id:
                        self.skip_next_player = None  # 重置跳过标志
                        continue  # 跳过此玩家，继续找下一个
                    
                    # 找到未淘汰且不需跳过的玩家
                    return next_player_id
                    
                # 如果遍历了所有玩家都没找到合适的（理论上不应该发生，因为游戏应该在只剩一名未淘汰玩家时结束）
                # 返回当前玩家ID（可能是已淘汰的）
                return self.get_current_player_id()
                
            def load_bullet(self) -> int:
                """随机装填子弹，返回子弹类型"""
                # 子弹类型: 1=空包弹(50%), 2=实弹(50%)
                bullet_types = [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]
                self.current_bullet_type = random.choice(bullet_types)
                return self.current_bullet_type
                
            def generate_bullets(self, count: int) -> list:
                """生成指定数量的子弹类型"""
                bullet_types = [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]  # 50%空包弹，50%实弹
                self.bullets = [random.choice(bullet_types) for _ in range(count)]
                return self.bullets
                
            def get_bullet_name(self) -> str:
                """获取当前子弹类型名称"""
                if self.current_bullet_type == 1:
                    return "空包弹"
                elif self.current_bullet_type == 2:
                    return "实弹"
                else:
                    return "未知"
                
            def get_bullet_emoji(self) -> str:
                """获取当前子弹类型的表情符号"""
                if self.current_bullet_type == 1:
                    return "🎭"  # 空包弹
                elif self.current_bullet_type == 2:
                    return "🔴"  # 实弹
                else:
                    return "❓"  # 未知
        
        # 游戏房间类
        self.GameRoom = GameRoom
        
        # 游戏状态，格式：{群号: GameRoom对象}
        self.games = {}
        
        # 成语列表（示例，实际使用需要更多成语）
        self.idioms = [
            "一举两得", "两全其美", "美不胜收", "收获颇丰", "丰功伟绩", 
            "绩效考核", "核心价值", "值此机会", "会心一笑", "笑逐颜开",
            "开天辟地", "地动山摇", "摇头晃脑", "脑洞大开", "开门见山",
            "山明水秀", "秀外慧中", "中流砥柱", "柱天立地", "地久天长",
            "长此以往", "往来无阻", "阻断电路", "路遥知马力", "力挽狂澜",
            "澜沧江水", "水滴石穿", "穿针引线", "线路规划", "规划蓝图"
        ]
        
        # 猜词词库（示例，实际使用需要更多词语）
        self.words_for_guessing = [
            "电脑", "手机", "书籍", "音乐", "电影", "运动", "食物", "动物", 
            "植物", "城市", "国家", "职业", "季节", "天气", "颜色", "交通",
            "学校", "医院", "商店", "银行", "餐厅", "公园", "海洋", "山脉"
        ]
        
        # 文字接龙词库
        self.word_chain_words = [
            "苹果", "橙子", "香蕉", "西瓜", "菠萝", "草莓", "蓝莓", "樱桃",
            "荔枝", "龙眼", "芒果", "葡萄", "柚子", "石榴", "山楂", "杨梅",
            "猕猴桃", "柠檬", "李子", "桃子", "梨子", "椰子", "榴莲", "枇杷"
        ]
        
        # 恶魔轮盘道具列表
        self.roulette_items = [
            {"name": "护盾", "description": "抵挡一次攻击，不减血", "rarity": 3},
            {"name": "连发", "description": "向目标连开两枪", "rarity": 3},
            {"name": "医疗包", "description": "恢复1点血量", "rarity": 2},
            {"name": "狙击枪", "description": "造成2点伤害", "rarity": 3},
            {"name": "闪避", "description": "有50%几率闪避下一次攻击", "rarity": 2},
            {"name": "跳过", "description": "跳过指定玩家的下一个回合", "rarity": 4},
            {"name": "偷窥", "description": "预先了解下一个玩家的回合信息", "rarity": 1},
            {"name": "防弹衣", "description": "将下次受到的伤害减少1点", "rarity": 2},
            {"name": "手榴弹", "description": "对所有其他玩家造成1点伤害", "rarity": 5}
        ]
        
        # 游戏规则说明
        self.game_rules = {
            "成语接龙": "【成语接龙规则】\n1. 机器人给出一个成语作为开始\n2. 玩家需要回复一个以上一个成语最后一个字开头的成语\n3. 成语不能重复使用\n4. 回复的必须是标准成语（四个汉字）",
            "猜词": "【猜词游戏规则】\n1. 机器人随机选择一个词语作为答案\n2. 玩家可以猜测单个汉字或整个词语\n3. 猜中单个汉字后，对应位置会显示出来\n4. 猜中全部字或直接猜出完整词语即为获胜\n5. 有10次猜测机会",
            "数字炸弹": "【数字炸弹规则】\n1. 机器人会在指定范围内(默认1-100)随机选择一个数字作为炸弹\n2. 玩家轮流猜测一个数字\n3. 每次猜测后，机器人会提示炸弹在更小的范围内\n4. 猜中炸弹的玩家输掉游戏",
            "文字接龙": "【文字接龙规则】\n1. 机器人给出一个词语作为开始\n2. 玩家需要回复一个以上一个词语最后一个字开头的新词语\n3. 词语不能重复使用\n4. 回复必须是常用词语，可以是任意长度",
            "恶魔轮盘": "【恶魔轮盘规则】\n1. 每个玩家有3点血量\n2. 每回合会随机装填空包弹(无伤害)、实弹(1点伤害)\n3. 轮到玩家回合时，必须@一名玩家并开枪\n4. 玩家可以对自己开枪\n5. 玩家可使用道具修改游戏规则\n6. 血量为0时淘汰，最后存活的玩家获胜\n7. 可用道具: 护盾、医疗包、连发、狙击枪、闪避、跳过、偷窥、防弹衣、手榴弹"
        }

    def is_admin(self, user_id: int, group_id: int) -> bool:
        """检查用户是否是管理员"""
        # 超级用户总是管理员
        superusers = self.bot.config.get("bot", {}).get("superusers", [])
        if str(user_id) in superusers:
            return True
            
        # 检查群内角色
        try:
            asyncio.get_event_loop().create_task(self._check_admin_role(user_id, group_id))
            # 这里只能同步返回，实际授权由异步任务完成
            return False
        except Exception as e:
            logger.error(f"检查管理员权限时发生错误: {e}")
            return False
    
    async def _check_admin_role(self, user_id: int, group_id: int) -> bool:
        """异步检查用户在群内的角色"""
        try:
            # 获取群成员信息
            response = await self.bot._call_api('/get_group_member_info', {
                'group_id': group_id,
                'user_id': user_id
            })
            
            if response.get("status") == "ok" and response.get("data"):
                role = response.get("data", {}).get("role", "member")
                return role in ["owner", "admin"]
            return False
        except Exception as e:
            logger.error(f"获取群成员信息失败: {e}")
            return False
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        raw_message = event.get('raw_message', '')
        user_id = event.get('user_id', 0)  # 设置默认值为0，确保类型为整数
        group_id = event.get('group_id') if message_type == 'group' else None
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 只在群聊中有效
        if message_type != 'group' or not group_id:
            return False
            
        # 添加调试日志
        logger.info(f"WordGames收到消息: {raw_message}")
        
        # 检查消息中是否包含@某人
        at_matches = re.findall(r'\[CQ:at,qq=(\d+)(?:,name=.*?)?\]', raw_message)
        mentioned_user_ids = [int(qq) for qq in at_matches]
            
        # 处理游戏中的回复（不需要@机器人）
        if group_id in self.games:
            # 检查游戏是否已经结束，如果已经结束则清理
            if self.games[group_id].status == "ended":
                logger.info(f"游戏已结束，清理游戏数据: 群组ID={group_id}")
                del self.games[group_id]
                # 如果游戏已结束，继续处理当前消息，可能是新游戏命令
            else:
                game_type = self.games[group_id].game_type
            
                # 如果消息中@了其他用户，保存被@的用户ID
                if mentioned_user_ids:
                    # 只关注第一个被@的用户
                    self.games[group_id].mentioned_player_id = mentioned_user_ids[0]
            
            if game_type == "成语接龙":
                return await self._handle_idiom_chain_reply(event, group_id, raw_message)
            elif game_type == "猜词":
                return await self._handle_word_guessing_reply(event, group_id, raw_message)
            elif game_type == "数字炸弹":
                return await self._handle_number_bomb_reply(event, group_id, raw_message)
            elif game_type == "文字接龙":
                return await self._handle_word_chain_reply(event, group_id, raw_message)
            elif game_type == "恶魔轮盘":
                return await self._handle_evil_roulette_reply(event, group_id, raw_message)
        
        # 获取机器人QQ号
        bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
        # 检查是否@了机器人
        at_pattern = f"\\[CQ:at,qq={bot_qq}(,name=.*?)?\\]"
        
        if re.search(at_pattern, raw_message):
            # 移除@机器人部分，获取实际命令内容
            clean_message = re.sub(at_pattern, "", raw_message).strip()
            logger.info(f"WordGames: 检测到@命令, 处理内容: {clean_message}")
            
            # 检查是否是游戏命令
            match = self.command_pattern.match(clean_message)
            if match:
                action = match.group(1)
                param = match.group(2) if match.group(2) else ""
                logger.info(f"WordGames: @命令解析 - action={action}, param={param}")
                
                # 使用_handle_game_command处理命令
                return await self._handle_game_command(event, group_id, action, param)
            else:
                logger.info(f"WordGames: @命令格式不匹配: {clean_message}")
                return False
        
        # 检查非@机器人的命令 (必须以/game开头)
        if raw_message.startswith("/game"):
            match = self.command_pattern.match(raw_message)
            if match:
                action = match.group(1)
                param = match.group(2) if match.group(2) else ""
                logger.info(f"WordGames: 非@命令解析 - action={action}, param={param}")
                
                # 使用_handle_game_command处理命令
                return await self._handle_game_command(event, group_id, action, param)
            else:
                logger.info(f"WordGames: 命令格式不匹配: {raw_message}")
                return False
                
        logger.info(f"WordGames: 消息不以/game开头且非@命令，跳过处理")
        return False
    
    async def _handle_game_command(self, event: Dict[str, Any], group_id: int, action: str, param: str) -> bool:
        """处理游戏命令"""
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        logger.info(f"处理游戏命令: action={action}, param={param}")
        
        # 处理规则查询命令
        if action == "rules" and param:
            return await self._show_game_rules(event, group_id, param)
            
        # 处理状态查询命令
        elif action == "status":
            return await self._show_game_status(event, group_id)
            
        # 处理停止游戏命令
        elif action == "stop":
            return await self._stop_game(event, group_id)
            
        # 处理开始游戏命令
        elif action == "start" and param:
            # 检查是否已有游戏在进行
            if group_id in self.games:
                # 如果游戏已经结束，则可以创建新游戏
                if self.games[group_id].status == "ended":
                    logger.info(f"游戏已结束，清理游戏数据以开始新游戏: 群组ID={group_id}")
                    del self.games[group_id]
                else:
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=f"当前群已有一个{self.games[group_id].game_type}游戏正在进行，请先使用 /game stop 停止当前游戏"
                    )
                    return True
                
            # 根据游戏类型启动不同的游戏
            if param == "成语接龙":
                return await self._start_idiom_chain_game(event, group_id)
            elif param == "猜词":
                return await self._start_word_guessing_game(event, group_id)
            elif param == "文字接龙":
                return await self._start_word_chain_game(event, group_id)
            elif param == "恶魔轮盘":
                return await self._start_evil_roulette_game(event, group_id)
            else:
                # 检查是否是数字炸弹游戏及其参数
                number_bomb_match = self.number_bomb_pattern.match(param)
                if number_bomb_match:
                    min_val = int(number_bomb_match.group(1)) if number_bomb_match.group(1) else 1
                    max_val = int(number_bomb_match.group(2)) if number_bomb_match.group(2) else 100
                    return await self._start_number_bomb_game(event, group_id, min_val, max_val)
                else:
                    # 检查是否仅提供了数字炸弹游戏的参数
                    parts = param.split()
                    if len(parts) >= 1 and parts[0] == "数字炸弹":
                        min_val = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
                        max_val = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100
                        return await self._start_number_bomb_game(event, group_id, min_val, max_val)
                
                # 未知游戏类型
                game_types = ["成语接龙", "猜词", "数字炸弹", "文字接龙", "恶魔轮盘"]
                await self.bot.send_msg(
                    message_type='group',
                    group_id=group_id,
                    message=f"未知的游戏类型: {param}\n可用的游戏类型: {', '.join(game_types)}"
                )
                return True
                
        return False

    async def _show_game_rules(self, event: Dict[str, Any], group_id: int, game_type: str) -> bool:
        """显示游戏规则"""
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        
        if game_type in self.game_rules:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}{self.game_rules[game_type]}"
            )
            return True
        else:
            games_list = "可用游戏类型:\n- 成语接龙\n- 猜词\n- 数字炸弹\n- 文字接龙"
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}未找到该游戏类型的规则\n{games_list}"
            )
            return True

    async def _start_number_bomb_game(self, event: Dict[str, Any], group_id: int, min_val: int = 1, max_val: int = 100) -> bool:
        """开始数字炸弹游戏"""
        message_id = event.get('message_id', 0)
        user_id = int(event.get('user_id', 0))
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 检查是否有正在进行的游戏
        # 注意：_handle_game_command 已经处理了游戏结束的情况，这里不需要重复检查
        if group_id in self.games:
            game_type = self.games[group_id].game_type
            status = self.games[group_id].status
            status_text = "等待玩家加入" if status == "waiting" else "进行中"
            
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}已经有一个{game_type}游戏正在{status_text}，请先使用 /game stop 停止当前游戏"
            )
            return True
            
        # 调整参数范围
        min_val = max(1, min_val)
        max_val = min(1000, max_val)
        if min_val >= max_val:
            min_val = 1
            max_val = 100
            
        # 创建游戏房间
        game_room = self.GameRoom("数字炸弹", user_id, nickname, group_id)
        
        # 初始化游戏数据
        bomb_number = random.randint(min_val, max_val)
        game_room.game_data = {
            "bomb_number": bomb_number,
            "current_min": min_val,
            "current_max": max_val,
            "guesses": []  # 记录所有猜测
        }
        
        # 保存游戏房间
        self.games[group_id] = game_room
        
        # 发送游戏创建成功通知
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}【数字炸弹】游戏房间创建成功！\n\n"
                    f"房主: {nickname}\n"
                    f"炸弹范围: {min_val} 到 {max_val}\n\n"
                    f"🎮 输入「加入游戏」参与\n"
                    f"⏱️ 人数满2人后，房主可发送「开始游戏」正式开始"
        )
        
        # 启动超时检查
        asyncio.create_task(self._check_game_timeout(group_id))
        
        return True
        
    async def _show_game_status(self, event: Dict[str, Any], group_id: int) -> bool:
        """显示游戏房间状态"""
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 检查是否有游戏
        if group_id not in self.games:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}当前没有正在进行的游戏"
            )
            return True
            
        # 获取游戏房间信息
        room = self.games[group_id]
        
        # 发送房间信息
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}{room.format_room_info()}"
        )
        
        return True
        
    async def _handle_number_bomb_reply(self, event: Dict[str, Any], group_id: int, message: str) -> bool:
        """处理数字炸弹游戏的回复"""
        # 检查游戏是否存在
        if group_id not in self.games or self.games[group_id].game_type != "数字炸弹":
            return False
            
        room = self.games[group_id]
        game_data = room.game_data
        user_id = int(event.get('user_id', 0))
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        message = message.strip()
        
        # 更新房间活动时间
        room.update_activity()
        
        # 等待玩家阶段
        if room.status == "waiting":
            # 处理加入游戏请求
            if message == "加入游戏":
                if room.is_player(user_id):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}你已经在游戏中了"
                    )
                else:
                    success = room.add_player(user_id, nickname)
                    if success:
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}{nickname} 加入了游戏！当前 {room.get_player_count()} 人参与。"
                        )
                        
                        # 提示房主开始游戏
                        if room.get_player_count() >= 2:
                            await self.bot.send_msg(
                                message_type="group",
                                group_id=group_id,
                                message=f"人数已满足游戏要求！房主 {room.host_name} 可以发送「开始游戏」正式开始~"
                            )
                return True
                
            # 处理开始游戏命令
            elif message == "开始游戏":
                if not room.is_host(user_id):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}只有房主 {room.host_name} 才能开始游戏"
                    )
                    return True
                    
                if room.get_player_count() < 2:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}至少需要2名玩家才能开始游戏"
                    )
                    return True
                    
                # 开始游戏
                room.start_game()
                
                # 获取数字炸弹游戏数据
                min_val = game_data["current_min"]
                max_val = game_data["current_max"]
                
                # 发送游戏开始通知
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【数字炸弹】游戏正式开始！\n\n"
                            f"炸弹在 {min_val} 到 {max_val} 之间的某个数字\n"
                            f"请直接发送数字进行猜测\n"
                            f"猜中炸弹数字的人就输了！"
                )
                return True
                
            # 其他消息在等待阶段不处理
            return False
        
        # 游戏进行中，处理数字猜测
        if room.status == "running":
            # 检查是否是玩家
            if not room.is_player(user_id):
                # 非玩家的消息不处理
                return False
                
            # 检查是否是数字
            if not message.isdigit():
                return False
            
            # 获取猜测的数字
            guess = int(message)
            
            # 获取游戏数据
            bomb_number = game_data["bomb_number"]
            current_min = game_data["current_min"]
            current_max = game_data["current_max"]
            
            # 检查数字是否在当前范围内
            if guess <= current_min or guess >= current_max:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}请猜测 {current_min} 到 {current_max} 之间的数字"
                )
                return True
            
            # 记录猜测数据
            game_data["guesses"].append({
                "user_id": user_id,
                "nickname": nickname,
                "value": guess,
                "time": time.time()
            })
            
            # 检查是否猜中炸弹
            if guess == bomb_number:
                # 游戏结束，当前玩家输了
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}💥 轰！炸弹爆炸了！\n{nickname} 猜中了炸弹数字 {bomb_number}，游戏结束！"
                )
                # 结束游戏
                del self.games[group_id]
                return True
            
            # 更新范围
            if guess < bomb_number:
                game_data["current_min"] = guess
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}{nickname} 猜测: {guess}\n\n🔍 炸弹在 {guess} 到 {current_max} 之间"
                )
            else:  # guess > bomb_number
                game_data["current_max"] = guess
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}{nickname} 猜测: {guess}\n\n🔍 炸弹在 {current_min} 到 {guess} 之间"
                )
            
            return True
        
        return False

    async def _start_word_chain_game(self, event: Dict[str, Any], group_id: int) -> bool:
        """开始文字接龙游戏"""
        message_id = event.get('message_id', 0)
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        reply_code = f"[CQ:reply,id={message_id}]"
        
        if group_id in self.games and self.games[group_id]["status"] == "running":
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}已经有一个{self.games[group_id]['type']}游戏在进行中，请先使用 /game stop 停止当前游戏"
            )
            return True
            
        # 选择初始词语
        start_word = random.choice(self.word_chain_words)
        
        # 初始化游戏数据
        self.games[group_id] = {
            "type": "文字接龙",
            "status": "running",
            "data": {
                "start_word": start_word,
                "current_word": start_word,
                "used_words": [start_word],
                "players": [user_id],  # 创建者自动加入
                "round": 0,
                "waiting_for_players": True,  # 等待玩家加入
                "host": user_id,  # 房主
                "no_response_count": 0
            }
        }
        
        # 发送游戏开始通知
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}【文字接龙】游戏创建成功！\n\n房主: {nickname}\n首个词语: {start_word}\n\n🎮 请输入「加入游戏」参与\n⏱️ 人数满2人后，房主可发送「开始游戏」正式开始"
        )
        
        # 启动超时检查
        asyncio.create_task(self._check_game_timeout(group_id))
        
        return True
        
    async def _handle_word_chain_reply(self, event: Dict[str, Any], group_id: int, message: str) -> bool:
        """处理文字接龙游戏的回复"""
        # 检查游戏是否存在
        if group_id not in self.games or self.games[group_id]["type"] != "文字接龙":
            return False
            
        game_data = self.games[group_id]["data"]
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 处理等待玩家加入阶段
        if game_data["waiting_for_players"]:
            # 处理加入游戏请求
            if message.strip() == "加入游戏":
                if user_id in game_data["players"]:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}你已经在游戏中了"
                    )
                else:
                    game_data["players"].append(user_id)
                    player_count = len(game_data["players"])
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}{nickname} 加入了游戏！当前 {player_count} 人参与。"
                    )
                    
                    # 提示房主开始游戏
                    if player_count >= 2:
                        host_nickname = "房主"  # 如果需要，可以查询房主昵称
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"人数已满足游戏要求！{host_nickname}可以发送「开始游戏」正式开始~"
                        )
                return True
            
            # 处理房主开始游戏命令
            elif message.strip() == "开始游戏" and user_id == game_data["host"]:
                if len(game_data["players"]) < 2:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}至少需要2名玩家才能开始游戏"
                    )
                else:
                    # 开始正式游戏
                    game_data["waiting_for_players"] = False
                    game_data["round"] = 1
                    
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}【文字接龙】游戏正式开始！\n\n首个词语: {game_data['current_word']}\n请回复一个以「{game_data['current_word'][-1]}」开头的词语"
                    )
                return True
            
            # 其他消息在等待阶段不处理
            return False
        
        # 正式游戏阶段，处理接龙
        word = message.strip()
        
        # 检查词语是否有效
        if len(word) < 2:
            return False  # 忽略太短的词
        
        # 检查是否以上一个词的最后一个字开头
        last_char = game_data["current_word"][-1]
        if word[0] != last_char:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}❌ 请发送以「{last_char}」开头的词语"
            )
            return True
        
        # 检查是否已经使用过
        if word in game_data["used_words"]:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}❌ 「{word}」已经被使用过了，请换一个"
            )
            return True
        
        # 接龙成功
        game_data["used_words"].append(word)
        game_data["current_word"] = word
        game_data["round"] += 1
        game_data["no_response_count"] = 0
        
        # 发送成功消息
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}✅ {nickname} 接龙成功！\n当前词语: {word}\n请回复一个以「{word[-1]}」开头的词语"
        )
        
        return True
        
    async def _start_idiom_chain_game(self, event: Dict[str, Any], group_id: int) -> bool:
        """开始成语接龙游戏"""
        message_id = event.get('message_id', 0)
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        reply_code = f"[CQ:reply,id={message_id}]"
        
        if group_id in self.games and self.games[group_id]["status"] == "running":
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}已经有一个{self.games[group_id]['type']}游戏在进行中，请先使用 /game stop 停止当前游戏"
            )
            return True
            
        # 选择初始成语
        start_idiom = random.choice(self.idioms)
        
        # 初始化游戏数据
        self.games[group_id] = {
            "type": "成语接龙",
            "status": "running",
            "data": {
                "start_idiom": start_idiom,
                "current_idiom": start_idiom,
                "used_idioms": [start_idiom],
                "players": [user_id],  # 创建者自动加入
                "round": 0,
                "waiting_for_players": True,  # 等待玩家加入
                "host": user_id,  # 房主
                "no_response_count": 0
            }
        }
        
        # 发送游戏开始通知
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}【成语接龙】游戏创建成功！\n\n房主: {nickname}\n首个成语: {start_idiom}\n\n🎮 请输入「加入游戏」参与\n⏱️ 人数满2人后，房主可发送「开始游戏」正式开始"
        )
        
        # 启动超时检查
        asyncio.create_task(self._check_game_timeout(group_id))
        
        return True
        
    async def _handle_idiom_chain_reply(self, event: Dict[str, Any], group_id: int, message: str) -> bool:
        """处理成语接龙游戏的回复"""
        # 检查游戏是否存在
        if group_id not in self.games or self.games[group_id]["type"] != "成语接龙":
            return False
            
        game_data = self.games[group_id]["data"]
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 处理等待玩家加入阶段
        if game_data["waiting_for_players"]:
            # 处理加入游戏请求
            if message.strip() == "加入游戏":
                if user_id in game_data["players"]:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}你已经在游戏中了"
                    )
                else:
                    game_data["players"].append(user_id)
                    player_count = len(game_data["players"])
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}{nickname} 加入了游戏！当前 {player_count} 人参与。"
                    )
                    
                    # 提示房主开始游戏
                    if player_count >= 2:
                        host_nickname = "房主"  # 如果需要，可以查询房主昵称
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"人数已满足游戏要求！{host_nickname}可以发送「开始游戏」正式开始~"
                        )
                return True
                
            # 处理房主开始游戏命令
            elif message.strip() == "开始游戏" and user_id == game_data["host"]:
                if len(game_data["players"]) < 2:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}至少需要2名玩家才能开始游戏"
                    )
                else:
                    # 开始正式游戏
                    game_data["waiting_for_players"] = False
                    game_data["round"] = 1
                    
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}【成语接龙】游戏正式开始！\n\n首个成语: {game_data['current_idiom']}\n请回复一个以「{game_data['current_idiom'][-1]}」开头的成语"
                    )
                return True
            
            # 其他消息在等待阶段不处理
            return False
            
        # 正式游戏阶段，处理接龙
        idiom = message.strip()
        
        # 检查是否是有效的成语（这里简化处理，实际可能需要更复杂的验证）
        if len(idiom) != 4:
            return False  # 忽略非四字成语
            
        # 检查是否以上一个成语的最后一个字开头
        last_char = game_data["current_idiom"][-1]
        if idiom[0] != last_char:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}❌ 请发送以「{last_char}」开头的成语"
            )
            return True
            
        # 检查是否已经使用过
        if idiom in game_data["used_idioms"]:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}❌ 「{idiom}」已经被使用过了，请换一个"
            )
            return True
            
        # 成语接龙成功
        game_data["used_idioms"].append(idiom)
        game_data["current_idiom"] = idiom
        game_data["round"] += 1
        game_data["no_response_count"] = 0
        
        # 发送成功消息
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}✅ {nickname} 接龙成功！\n当前成语: {idiom}\n请回复一个以「{idiom[-1]}」开头的成语"
        )
        
        return True
        
    async def _start_word_guessing_game(self, event: Dict[str, Any], group_id: int) -> bool:
        """开始猜词游戏"""
        message_id = event.get('message_id', 0)
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        reply_code = f"[CQ:reply,id={message_id}]"
        
        if group_id in self.games and self.games[group_id]["status"] == "running":
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}已经有一个{self.games[group_id]['type']}游戏在进行中，请先使用 /game stop 停止当前游戏"
            )
            return True
            
        # 选择要猜的词
        target_word = random.choice(self.words_for_guessing)
        
        # 初始化游戏数据
        self.games[group_id] = {
            "type": "猜词",
            "status": "running",
            "data": {
                "target_word": target_word,
                "guessed_chars": set(),  # 已猜过的字符
                "mask": ["_"] * len(target_word),  # 用于显示已猜中的字符位置
                "attempts": 0,  # 猜测次数
                "max_attempts": 10,  # 最大猜测次数
                "players": [user_id],  # 创建者自动加入
                "waiting_for_players": True,  # 等待玩家加入
                "host": user_id,  # 房主
                "no_response_count": 0
            }
        }
        
        # 发送游戏开始通知
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}【猜词】游戏创建成功！\n\n房主: {nickname}\n词语长度: {len(target_word)}个字\n\n🎮 请输入「加入游戏」参与\n⏱️ 人数满2人后，房主可发送「开始游戏」正式开始"
        )
        
        # 启动超时检查
        asyncio.create_task(self._check_game_timeout(group_id))
        
        return True
        
    async def _handle_word_guessing_reply(self, event: Dict[str, Any], group_id: int, message: str) -> bool:
        """处理猜词游戏的回复"""
        # 检查游戏是否存在
        if group_id not in self.games or self.games[group_id]["type"] != "猜词":
            return False
            
        game_data = self.games[group_id]["data"]
        user_id = event.get('user_id')
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 处理等待玩家加入阶段
        if game_data["waiting_for_players"]:
            # 处理加入游戏请求
            if message.strip() == "加入游戏":
                if user_id in game_data["players"]:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}你已经在游戏中了"
                    )
                else:
                    game_data["players"].append(user_id)
                    player_count = len(game_data["players"])
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}{nickname} 加入了游戏！当前 {player_count} 人参与。"
                    )
                    
                    # 提示房主开始游戏
                    if player_count >= 2:
                        host_nickname = "房主"  # 如果需要，可以查询房主昵称
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"人数已满足游戏要求！{host_nickname}可以发送「开始游戏」正式开始~"
                        )
                return True
                
            # 处理房主开始游戏命令
            elif message.strip() == "开始游戏" and user_id == game_data["host"]:
                if len(game_data["players"]) < 2:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}至少需要2名玩家才能开始游戏"
                    )
                else:
                    # 开始正式游戏
                    game_data["waiting_for_players"] = False
                    
                    # 显示初始状态
                    mask_display = " ".join(game_data["mask"])
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}【猜词】游戏正式开始！\n\n词语: {mask_display}\n剩余机会: {game_data['max_attempts']}\n请猜测一个汉字或完整词语"
                    )
                return True
            
            # 其他消息在等待阶段不处理
            return False
            
        # 正式游戏阶段，处理猜测
        message = message.strip()
            
        # 如果是单个字的猜测
        if len(message) == 1 and '\u4e00' <= message <= '\u9fff':
            # 更新已猜测的字符
            game_data["guessed_chars"].add(message)
            game_data["attempts"] += 1
            
            # 更新提示
            new_mask = []
            found = False
            for char in game_data["target_word"]:
                if char == message or char in game_data["guessed_chars"]:
                    new_mask.append(char)
                    if char == message:
                        found = True
                else:
                    new_mask.append("_")
            game_data["mask"] = new_mask
            
            # 判断是否猜中某个字
            if found:
                nickname = event.get("sender", {}).get("nickname", "玩家")
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【猜词游戏】{nickname} 猜对了一个字！\n\n当前提示：{''.join(game_data['mask'])}\n\n剩余尝试次数：{game_data['max_attempts'] - game_data['attempts']}"
                )
            else:
                nickname = event.get("sender", {}).get("nickname", "玩家")
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【猜词游戏】{nickname} 猜错了！\n\n当前提示：{''.join(game_data['mask'])}\n\n剩余尝试次数：{game_data['max_attempts'] - game_data['attempts']}"
                )
                
            # 检查是否已经全部猜出
            if "_" not in game_data["mask"]:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【猜词游戏】恭喜大家猜出了所有字！\n\n答案是：{game_data['target_word']}\n\n游戏结束！"
                )
                self.games[group_id]["status"] = "stopped"
                
            # 检查是否达到最大尝试次数
            if game_data["attempts"] >= game_data["max_attempts"]:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【猜词游戏】已达到最大尝试次数！\n\n答案是：{game_data['target_word']}\n\n游戏结束！"
                )
                self.games[group_id]["status"] = "stopped"
                
            return True
            
        # 不处理其他回复
        return False
        
    async def _stop_game(self, event: Dict[str, Any], group_id: int) -> bool:
        """停止游戏"""
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        user_id = event.get('user_id', 0)        # 获取停止游戏的用户ID
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 添加调试日志
        logger.info(f"执行停止游戏命令: 群组ID={group_id}, 用户ID={user_id}")
        
        # 检查游戏是否存在
        if group_id not in self.games:
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}当前没有正在进行的游戏"
            )
            return True
            
        # 获取游戏房间对象
        room = self.games[group_id]
            
        # 检查游戏状态
        if room.status == "ended":
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}当前游戏已经结束"
            )
            
            # 删除已结束的游戏，允许创建新游戏
            del self.games[group_id]
            return True
            
        # 获取游戏信息
        game_type = room.game_type
        game_data = room.game_data
        
        # 检查权限：只有管理员或房主可以停止游戏
        is_admin = self.is_admin(int(user_id), group_id)
        is_host = room.host_id == user_id
        
        if not (is_admin or is_host):
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=f"{reply_code}⚠️ 只有游戏房主或管理员才能停止游戏"
            )
            return True
        
        # 根据游戏类型构建不同的停止游戏消息
        stop_message = f"{reply_code}【{game_type}】游戏已被"
        stop_message += " 管理员" if is_admin and not is_host else " 房主"
        stop_message += " 停止！\n"
        
        # 添加额外信息
        if game_type == "猜词":
            stop_message += f"\n正确答案是：{game_data.get('target_word', '未知')}"
        elif game_type == "数字炸弹":
            stop_message += f"\n炸弹数字是：{game_data.get('bomb_number', '未知')}"
            
        # 显示参与玩家信息
        players = room.players
        if players:
            stop_message += f"\n\n共有 {len(players)} 名玩家参与了游戏"
        
        # 发送停止游戏消息
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=stop_message
        )
        
        # 完全删除游戏数据，确保资源被释放
        if group_id in self.games:
            del self.games[group_id]
        
        return True
        
    async def _check_game_timeout(self, group_id: int) -> None:
        """检查游戏超时"""
        waiting_timeout = 300  # 等待玩家加入阶段的超时时间（秒）
        running_timeout = 600  # 游戏进行中的超时时间（秒）
        check_interval = 30   # 每30秒检查一次
        
        while group_id in self.games:
            await asyncio.sleep(check_interval)
            
            # 如果游戏已经结束或者被删除，退出循环
            if group_id not in self.games:
                break
                
            room = self.games[group_id]
            current_time = int(time.time())
            
            # 检查是否超时
            if room.status == "waiting":
                # 等待玩家阶段的超时检查
                if (current_time - room.last_activity) > waiting_timeout:
                    logger.info(f"游戏房间 {group_id} 等待玩家加入超时")
                    
                    # 发送超时消息
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"【{room.game_type}】房间由于长时间无人加入，已自动关闭！"
                    )
                    
                    # 删除游戏房间
                    del self.games[group_id]
                    break
            elif room.status == "running":
                # 游戏进行中的超时检查
                if (current_time - room.last_activity) > running_timeout:
                    logger.info(f"游戏房间 {group_id} 游戏进行中超时")
                    
                    # 根据游戏类型构建消息
                    message = f"【{room.game_type}】由于长时间无人回应，游戏自动结束！"
                    
                    if room.game_type == "数字炸弹":
                        bomb_number = room.game_data.get("bomb_number", "未知")
                        message += f"\n\n炸弹数字是: {bomb_number}"
                    elif room.game_type == "猜词":
                        target_word = room.game_data.get("target_word", "未知")
                        message += f"\n\n正确答案是: {target_word}"
                        
                    # 发送超时消息
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=message
                    )
                    
                    # 删除游戏房间
                    del self.games[group_id]
                    break

    async def _start_evil_roulette_game(self, event: Dict[str, Any], group_id: int) -> bool:
        """开始恶魔轮盘游戏"""
        message_id = event.get('message_id', 0)
        user_id = int(event.get('user_id', 0))
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        reply_code = f"[CQ:reply,id={message_id}]"
        
        # 检查是否已有游戏在进行
        # 注意：_handle_game_command 已经处理了游戏结束的情况，这里不需要重复检查
        if group_id in self.games:
                game_type = self.games[group_id].game_type
                status = self.games[group_id].status
                status_text = "等待玩家加入" if status == "waiting" else "进行中"
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}已经有一个{game_type}游戏正在{status_text}，请先使用 /game stop 停止当前游戏"
                )
                return True
            
        # 创建游戏房间
        game_room = self.GameRoom("恶魔轮盘", user_id, nickname, group_id)
        
        # 初始化游戏数据
        game_room.game_data = {
            "players_health": {user_id: 3},  # 初始3点血量
            "players_items": {user_id: []},  # 初始无道具
            "players_effects": {user_id: {}}, # 玩家状态效果
            "last_shot": {},                 # 上一次开枪记录
            "shot_history": [],              # 所有开枪记录
            "round_counter": 0,              # 回合计数器
            "eliminated_players": [],        # 已淘汰玩家
            "bullets_remaining": 0,          # 当前回合剩余子弹数
            "bullets_per_round": 1           # 初始回合子弹数量
        }
        
        # 保存游戏房间
        self.games[group_id] = game_room
        
        # 发送游戏创建成功通知
        await self.bot.send_msg(
            message_type="group",
            group_id=group_id,
            message=f"{reply_code}【恶魔轮盘】游戏房间创建成功！\n\n"
                    f"房主: {nickname}\n"
                    f"玩家初始血量: 3\n\n"
                    f"🎮 输入「加入游戏」参与\n"
                    f"⏱️ 人数满2人后，房主可发送「开始游戏」正式开始\n"
                    f"📜 发送 /game rules 恶魔轮盘 可查看详细规则"
        )
        
        # 启动超时检查
        asyncio.create_task(self._check_game_timeout(group_id))
        
        return True

    async def _handle_evil_roulette_reply(self, event: Dict[str, Any], group_id: int, message: str) -> bool:
        """处理恶魔轮盘游戏的回复"""
        # 检查游戏是否存在
        if group_id not in self.games or self.games[group_id].game_type != "恶魔轮盘":
            return False
            
        room = self.games[group_id]
        game_data = room.game_data
        user_id = int(event.get('user_id', 0))
        nickname = event.get('sender', {}).get('nickname', str(user_id))
        message_id = event.get('message_id', 0)
        reply_code = f"[CQ:reply,id={message_id}]"
        message = message.strip()
        
        # 更新房间活动时间
        room.update_activity()
        
        # 等待玩家阶段
        if room.status == "waiting":
            # 处理加入游戏请求
            if message == "加入游戏":
                # 限制最多4名玩家
                if room.get_player_count() >= 4:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}当前房间已满，最多支持4名玩家参与"
                    )
                    return True
                
                if room.is_player(user_id):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}你已经在游戏中了"
                    )
                else:
                    success = room.add_player(user_id, nickname)
                    if success:
                        # 为新玩家初始化数据
                        game_data["players_health"][user_id] = 3
                        game_data["players_items"][user_id] = []
                        game_data["players_effects"][user_id] = {}
                        
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"{reply_code}{nickname} 加入了游戏！当前 {room.get_player_count()} 人参与。"
                        )
                        
                        # 提示房主开始游戏
                        if room.get_player_count() >= 2:
                            await self.bot.send_msg(
                                message_type="group",
                                group_id=group_id,
                                message=f"人数已满足游戏要求！房主 {room.host_name} 可以发送「开始游戏」正式开始~"
                            )
                return True
                
            # 处理开始游戏命令
            elif message == "开始游戏":
                if not room.is_host(user_id):
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}只有房主 {room.host_name} 才能开始游戏"
                    )
                    return True
                    
                if room.get_player_count() < 2:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}至少需要2名玩家才能开始游戏"
                    )
                    return True
                
                # 开始游戏
                room.start_game()
                game_data["round_counter"] = 1
                # 设置第一回合的子弹数量
                game_data["bullets_per_round"] = 3  # 初始3发子弹
                game_data["bullets_remaining"] = game_data["bullets_per_round"]
                
                # 随机分配初始道具
                for pid in room.players:
                    # 每个玩家随机获得一个道具
                    item = random.choice(self.roulette_items)
                    if pid in game_data["players_items"]:
                        game_data["players_items"][pid].append(item["name"])
                
                # 准备玩家顺序信息
                player_order = "\n".join([f"{i+1}. {room.player_names[pid]}" for i, pid in enumerate(room.players)])
                
                # 先生成子弹分布
                room.bullets = room.generate_bullets(game_data["bullets_per_round"])
                
                # 生成子弹分布显示文本
                bullet_distribution = []
                for bullet_type in room.bullets:
                    if bullet_type == 1:
                        bullet_distribution.append("空包弹")
                    else:
                        bullet_distribution.append("实弹")
                random.shuffle(bullet_distribution)  # 打乱显示顺序
                bullet_distribution_text = "、".join(bullet_distribution)
                
                # 获取当前玩家
                current_player = room.get_current_player_name()
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【恶魔轮盘】游戏正式开始！\n\n"
                            f"玩家行动顺序:\n{player_order}\n\n"
                            f"🔫 第 1 回合，散弹枪已装填\n"
                            f"本回合可能的子弹: {bullet_distribution_text}\n"
                            f"请 {current_player} @某人 进行射击\n"
                            f"💊 每位玩家获得了一个随机道具，可输入「查看道具」\n"
                            f"❤️ 初始血量为3点，血量归零即被淘汰"
                )
                return True
                
            # 其他消息在等待阶段不处理
            return False
        
        # 游戏进行中
        if room.status == "running":
            # 检查是否是玩家
            if not room.is_player(user_id):
                # 非玩家的消息不处理
                return False
                
            # 处理查看道具请求
            if message == "查看道具":
                # 获取玩家道具
                player_items = game_data["players_items"].get(user_id, [])
                item_text = "你当前没有道具" if not player_items else "你当前拥有的道具:\n" + "\n".join([f"- {item}" for item in player_items])
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}{item_text}"
                )
                return True
                
            # 处理查看状态请求
            elif message == "查看状态":
                # 生成玩家状态信息
                status_lines = []
                for pid in room.players:
                    if pid in game_data["eliminated_players"]:
                        continue
                    health = game_data["players_health"].get(pid, 0)
                    name = room.player_names.get(pid, str(pid))
                    effects = []
                    if pid in game_data["players_effects"]:
                        for effect, value in game_data["players_effects"][pid].items():
                            if effect == "defense":
                                effects.append("🛡️")
                            elif effect == "evasion":
                                effects.append("👟")
                    
                    effects_text = " ".join(effects)
                    status_lines.append(f"{name}: {'❤️' * health} {effects_text}")
                
                status_text = "\n".join(status_lines)
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}【玩家状态】\n{status_text}"
                )
                return True
            
            # 处理使用道具请求
            elif message.startswith("使用") and len(message) > 2:
                item_name = message[2:].strip()
                player_items = game_data["players_items"].get(user_id, [])
                
                if item_name not in player_items:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}你没有【{item_name}】道具"
                    )
                    return True
                
                # 检查是否是当前轮到的玩家
                current_player_id = room.get_current_player_id()
                if user_id != current_player_id and item_name not in ["护盾", "闪避", "防弹衣"]:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"{reply_code}现在不是你的回合，只能使用防御类道具"
                    )
                    return True
                
                # 从玩家道具中移除该道具
                game_data["players_items"][user_id].remove(item_name)
                
                # 根据道具类型执行不同效果
                effect_msg = ""
                if item_name == "护盾":
                    # 护盾效果在被攻击时处理
                    effect_msg = "你激活了【护盾】，将在本回合抵挡一次伤害"
                    game_data["players_effects"][user_id]["shield"] = True
                elif item_name == "医疗包":
                    # 回复1点血量，上限3点
                    current_health = game_data["players_health"].get(user_id, 0)
                    if current_health < 3:
                        game_data["players_health"][user_id] = min(3, current_health + 1)
                        effect_msg = f"你使用了【医疗包】，恢复1点血量，当前血量: {game_data['players_health'][user_id]}"
                    else:
                        effect_msg = "你的血量已满，无法使用【医疗包】"
                        # 返回道具
                        game_data["players_items"][user_id].append(item_name)
                elif item_name == "连发":
                    # 连发效果在开枪时处理
                    effect_msg = "你装填了【连发】弹夹，本回合将连续射击两次"
                    game_data["double_shot"] = True
                elif item_name == "狙击枪":
                    # 狙击枪效果在开枪时处理
                    effect_msg = "你准备了【狙击枪】，本回合射击将造成2点伤害"
                    game_data["sniper_shot"] = True
                elif item_name == "闪避":
                    # 闪避效果在被攻击时处理
                    effect_msg = "你激活了【闪避】，有50%几率躲避下一次攻击"
                    game_data["players_effects"][user_id]["evasion"] = True
                elif item_name == "跳过":
                    # 需要指定跳过哪个玩家
                    if not room.mentioned_player_id:
                        effect_msg = "你需要@一名玩家来使用【跳过】道具"
                        # 返回道具
                        game_data["players_items"][user_id].append(item_name)
                    else:
                        target_id = room.mentioned_player_id
                        if target_id not in room.players:
                            effect_msg = "你@的用户不在游戏中"
                            # 返回道具
                            game_data["players_items"][user_id].append(item_name)
                        else:
                            target_name = room.player_names.get(target_id, str(target_id))
                            effect_msg = f"你对 {target_name} 使用了【跳过】道具，Ta的下个回合将被跳过"
                            room.skip_next_player = target_id
                elif item_name == "偷窥":
                    # 查看下一个玩家的子弹类型
                    # 先保存当前玩家索引
                    current_index = room.current_player_index
                    # 临时获取下一个玩家
                    next_player_id = room.next_player()
                    # 恢复当前玩家索引
                    room.current_player_index = current_index
                    
                    next_player_name = room.player_names.get(next_player_id, str(next_player_id))
                    # 预先生成下一个玩家的子弹，但不显示类型
                    bullet_type = room.load_bullet()
                    
                    # 偷窥道具应该显示子弹类型
                    bullet_name = room.get_bullet_name()
                    bullet_emoji = room.get_bullet_emoji()
                    effect_msg = f"你偷看了下一个玩家 {next_player_name} 的子弹，发现是 {bullet_emoji} {bullet_name}！"
                elif item_name == "防弹衣":
                    # 减少1点伤害
                    effect_msg = "你穿上了【防弹衣】，下次受到的伤害将减少1点"
                    game_data["players_effects"][user_id]["defense"] = True
                elif item_name == "手榴弹":
                    # 对所有其他玩家造成1点伤害
                    effect_msg = "你投出了【手榴弹】，对所有其他玩家造成1点伤害！"
                    affected_players = []
                    
                    for pid in room.players:
                        if pid == user_id or pid in game_data["eliminated_players"]:
                            continue
                        
                        # 检查玩家是否有护盾
                        if pid in game_data["players_effects"] and game_data["players_effects"][pid].get("shield"):
                            player_name = room.player_names.get(pid, str(pid))
                            effect_msg += f"\n🛡️ {player_name} 的护盾抵挡了伤害！"
                            del game_data["players_effects"][pid]["shield"]
                            continue
                        
                        # 检查玩家是否有闪避
                        if pid in game_data["players_effects"] and game_data["players_effects"][pid].get("evasion"):
                            if random.random() < 0.5:  # 50%几率闪避
                                player_name = room.player_names.get(pid, str(pid))
                                effect_msg += f"\n👟 {player_name} 闪避了伤害！"
                                del game_data["players_effects"][pid]["evasion"]
                                continue
                        
                        # 检查玩家是否有防弹衣
                        damage = 1
                        if pid in game_data["players_effects"] and game_data["players_effects"][pid].get("defense"):
                            damage = max(0, damage - 1)
                            del game_data["players_effects"][pid]["defense"]
                        
                        if damage > 0:
                            current_health = game_data["players_health"].get(pid, 3)
                            new_health = max(0, current_health - damage)
                            game_data["players_health"][pid] = new_health
                            
                            player_name = room.player_names.get(pid, str(pid))
                            health_text = f"剩余血量: {'❤️' * new_health}"
                            effect_msg += f"\n💥 {player_name} 受到 {damage} 点伤害，{health_text}"
                            affected_players.append((pid, player_name, new_health))
                    
                    # 检查是否有玩家被淘汰
                    for pid, player_name, health in affected_players:
                        if health <= 0 and pid not in game_data["eliminated_players"]:
                            game_data["eliminated_players"].append(pid)
                            effect_msg += f"\n💀 {player_name} 血量归零，已被淘汰！"
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}{effect_msg}"
                )
                
                # 检查游戏是否结束（使用手榴弹可能导致游戏结束）
                alive_players = [p for p in room.players if p not in game_data["eliminated_players"]]
                if len(alive_players) <= 1:
                    # 游戏结束，存活的玩家获胜
                    if alive_players:
                        winner_id = alive_players[0]
                        winner_name = room.player_names.get(winner_id, str(winner_id))
                        
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"🏆 游戏结束！{winner_name} 是最后的幸存者，获得胜利！"
                        )
                    else:
                        await self.bot.send_msg(
                            message_type="group",
                            group_id=group_id,
                            message=f"游戏结束，所有玩家都被淘汰了！"
                        )
                    
                    # 结束游戏
                    room.status = "ended"
                
                return True
            
            # 处理开枪动作（需要@某人）
            current_player_id = room.get_current_player_id()
            
            # 检查是否是当前玩家的回合
            if user_id != current_player_id:
                return False
            
            # 检查当前玩家是否被淘汰
            if user_id in game_data["eliminated_players"]:
                # 玩家已被淘汰，自动跳到下一个玩家
                next_player_id = room.next_player()
                next_player_name = room.player_names.get(next_player_id, str(next_player_id))
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}你已经被淘汰了，无法继续游戏\n请 {next_player_name} @某人 进行射击"
                )
                return True
            
            # 检查是否@了其他玩家
            mentioned_player_id = room.mentioned_player_id
            
            if not mentioned_player_id:
                # 没有@任何人，提示需要@
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}你需要@一名玩家进行射击"
                )
                return True
            
            # 检查被@的玩家是否在游戏中
            if mentioned_player_id not in room.players:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}你@的用户不在游戏中"
                )
                room.mentioned_player_id = None  # 清除@记录
                return True
            
            # 检查被@的玩家是否已经被淘汰
            if mentioned_player_id in game_data["eliminated_players"]:
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"{reply_code}你@的玩家已经被淘汰了"
                )
                room.mentioned_player_id = None  # 清除@记录
                return True
            
            # 检查是否@了自己
            if mentioned_player_id == user_id:
                # 不再阻止对自己开枪
                # 继续执行，不返回
                pass
            
            # 清除@记录，避免下次重复使用
            target_id = mentioned_player_id
            room.mentioned_player_id = None
            
            # 获取当前子弹类型
            if len(room.bullets) > 0 and game_data["bullets_remaining"] > 0:
                bullet_type = room.bullets.pop(0)  # 从子弹列表中取出第一发子弹
                room.current_bullet_type = bullet_type  # 更新当前子弹类型
            else:
                # 如果没有预先生成的子弹，则随机生成一个
                bullet_type = room.load_bullet()
                
            bullet_name = "空包弹" if bullet_type == 1 else "实弹"
            bullet_emoji = "🎭" if bullet_type == 1 else "🔴"
            
            # 初始伤害值
            base_damage = 0 if bullet_type == 1 else 1  # 空包弹无伤害，实弹1点伤害
            damage = base_damage
            
            # 检查是否使用了狙击枪
            if "sniper_shot" in game_data and game_data["sniper_shot"]:
                damage = 2  # 狙击枪固定2点伤害
                del game_data["sniper_shot"]  # 使用后删除
            
            # 记录本次射击
            shot_record = {
                "round": game_data["round_counter"],
                "shooter_id": user_id,
                "shooter_name": nickname,
                "target_id": mentioned_player_id,
                "target_name": room.player_names.get(mentioned_player_id, str(mentioned_player_id)),
                "bullet_type": bullet_type,
                "damage": damage,
                "time": int(time.time())
            }
            game_data["shot_history"].append(shot_record)
            game_data["last_shot"] = shot_record
            
            # 检查目标玩家是否有防御效果
            target_had_shield = False
            target_evaded = False
            damage_reduced = False
            
            # 处理护盾效果
            if mentioned_player_id in game_data["players_effects"] and game_data["players_effects"][mentioned_player_id].get("shield"):
                target_had_shield = True
                del game_data["players_effects"][mentioned_player_id]["shield"]
                damage = 0  # 护盾完全抵消伤害
            
            # 处理闪避效果
            elif mentioned_player_id in game_data["players_effects"] and game_data["players_effects"][mentioned_player_id].get("evasion"):
                if random.random() < 0.5:  # 50%几率闪避
                    target_evaded = True
                    del game_data["players_effects"][mentioned_player_id]["evasion"]
                    damage = 0  # 闪避成功，不受伤害
            
            # 处理防弹衣效果
            elif damage > 0 and mentioned_player_id in game_data["players_effects"] and game_data["players_effects"][mentioned_player_id].get("defense"):
                damage_reduced = True
                damage = max(0, damage - 1)  # 防弹衣减少1点伤害
                del game_data["players_effects"][mentioned_player_id]["defense"]
            
            # 应用伤害
            if damage > 0:
                current_health = game_data["players_health"].get(mentioned_player_id, 3)
                new_health = max(0, current_health - damage)
                game_data["players_health"][mentioned_player_id] = new_health
                
                # 检查玩家是否被淘汰
                if new_health <= 0 and mentioned_player_id not in game_data["eliminated_players"]:
                    game_data["eliminated_players"].append(mentioned_player_id)
                    # 淘汰玩家失去所有道具
                    if mentioned_player_id in game_data["players_items"]:
                        del game_data["players_items"][mentioned_player_id]
            
            # 构建开枪消息
            shot_result = f"{nickname} 向 {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 开火！\n💥 {bullet_emoji} {bullet_name}！\n"
            
            if target_had_shield:
                shot_result += f"🛡️ {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 的护盾抵挡了伤害！\n"
            elif target_evaded:
                shot_result += f"👟 {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 闪避了攻击！\n"
            elif damage_reduced:
                shot_result += f"🦺 {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 的防弹衣减少了伤害！\n"
                
            if damage > 0:
                current_health = game_data["players_health"].get(mentioned_player_id, 0)
                shot_result += f"{room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 受到 {damage} 点伤害，剩余血量: {'❤️' * current_health}\n"
                
                if mentioned_player_id in game_data["eliminated_players"]:
                    shot_result += f"💀 {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 血量归零，已被淘汰！\n"
            else:
                shot_result += f"{room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 没有受到伤害\n"
            
            # 发送开枪结果消息
            await self.bot.send_msg(
                message_type="group",
                group_id=group_id,
                message=shot_result
            )
            
            # 减少剩余子弹数
            game_data["bullets_remaining"] -= 1
            
            # 检查是否需要连射
            double_shot = False
            if "double_shot" in game_data and game_data["double_shot"]:
                double_shot = True
                del game_data["double_shot"]  # 使用后删除
                
                # 如果连射，再发射一枪，但需要检查是否还有足够的子弹
                if game_data["bullets_remaining"] > 0:
                    # 获取第二发子弹类型
                    if len(room.bullets) > 0:
                        bullet_type = room.bullets.pop(0)  # 从子弹列表中取出下一发子弹
                        room.current_bullet_type = bullet_type  # 更新当前子弹类型
                    else:
                        # 如果没有预先生成的子弹，则随机生成一个
                        bullet_type = room.load_bullet()
                        
                    bullet_name = "空包弹" if bullet_type == 1 else "实弹"
                    bullet_emoji = "🎭" if bullet_type == 1 else "🔴"
                    
                    # 计算伤害
                    damage = 0 if bullet_type == 1 else 1
                    
                    # 记录连发射击
                    shot_record = {
                        "round": game_data["round_counter"],
                        "shooter_id": user_id,
                        "shooter_name": nickname,
                        "target_id": mentioned_player_id,
                        "target_name": room.player_names.get(mentioned_player_id, str(mentioned_player_id)),
                        "bullet_type": bullet_type,
                        "damage": damage,
                        "time": int(time.time()),
                        "is_double_shot": True
                    }
                    game_data["shot_history"].append(shot_record)
                    
                    # 检查目标玩家是否有防御效果 (第二发不考虑护盾等防御效果，因为已经用过了)
                    
                    # 应用第二发伤害
                    if damage > 0 and mentioned_player_id not in game_data["eliminated_players"]:
                        current_health = game_data["players_health"].get(mentioned_player_id, 3)
                        new_health = max(0, current_health - damage)
                        game_data["players_health"][mentioned_player_id] = new_health
                        
                        # 检查是否被淘汰
                        if new_health <= 0 and mentioned_player_id not in game_data["eliminated_players"]:
                            game_data["eliminated_players"].append(mentioned_player_id)
                            # 淘汰玩家失去所有道具
                            if mentioned_player_id in game_data["players_items"]:
                                del game_data["players_items"][mentioned_player_id]
                    
                    # 构建第二发开枪消息
                    second_shot_result = f"连发效果触发！{nickname} 向 {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 发射第二枪！\n💥 {bullet_emoji} {bullet_name}！\n"
                    
                    if damage > 0:
                        current_health = game_data["players_health"].get(mentioned_player_id, 0)
                        second_shot_result += f"{room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 受到 {damage} 点伤害，剩余血量: {'❤️' * current_health}\n"
                        
                        if mentioned_player_id in game_data["eliminated_players"]:
                            second_shot_result += f"💀 {room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 血量归零，已被淘汰！\n"
                    else:
                        second_shot_result += f"{room.player_names.get(mentioned_player_id, str(mentioned_player_id))} 没有受到伤害\n"
                    
                    # 发送第二发开枪结果
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=second_shot_result
                    )
                    
                    # 减少剩余子弹数
                    game_data["bullets_remaining"] -= 1
                else:
                    # 如果没有足够的子弹，提示连发失效
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"连发效果因子弹不足而失效！"
                    )
            
            # 检查游戏是否结束
            alive_players = [p for p in room.players if p not in game_data["eliminated_players"]]
            if len(alive_players) <= 1:
                # 游戏结束，存活的玩家获胜
                if alive_players:
                    winner_id = alive_players[0]
                    winner_name = room.player_names.get(winner_id, str(winner_id))
                    
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"🏆 游戏结束！{winner_name} 是最后的幸存者，获得胜利！"
                    )
                else:
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"游戏结束，所有玩家都被淘汰了！"
                    )
                
                # 结束游戏
                room.status = "ended"
                return True
            
            # 空包弹不结束当前玩家回合，继续由当前玩家射击
            if bullet_type == 1 and mentioned_player_id == user_id:  # 空包弹且射击自己
                # 检查是否还有剩余子弹
                if game_data["bullets_remaining"] <= 0:
                    # 如果子弹已用完，进入新回合
                    # 回合计数器+1
                    game_data["round_counter"] += 1
                    
                    # 更新子弹数量（随回合递增，起始3发，最多8发）
                    game_data["bullets_per_round"] = min(8, game_data["round_counter"] + 2)
                    game_data["bullets_remaining"] = game_data["bullets_per_round"]
                    
                    # 清空所有玩家的道具
                    for pid in room.players:
                        if pid not in game_data["eliminated_players"] and pid in game_data["players_items"]:
                            game_data["players_items"][pid] = []
                    
                    # 随机为玩家发放新道具（每回合每个玩家可能获得一个道具）
                    for pid in room.players:
                        if pid in game_data["eliminated_players"]:
                            continue
                            
                        # 50%概率获得道具
                        if random.random() < 0.5:
                            new_item = random.choice(self.roulette_items)
                            if pid in game_data["players_items"]:
                                game_data["players_items"][pid].append(new_item["name"])
                    
                    # 进入下一位玩家的回合
                    next_player_id = room.next_player()
                    next_player_name = room.player_names.get(next_player_id, str(next_player_id))
                    
                    # 先生成子弹分布
                    room.bullets = room.generate_bullets(game_data["bullets_per_round"])
                    
                    # 生成子弹分布显示文本
                    bullet_distribution = []
                    for bullet_type in room.bullets:
                        if bullet_type == 1:
                            bullet_distribution.append("空包弹")
                        else:
                            bullet_distribution.append("实弹")
                    random.shuffle(bullet_distribution)  # 打乱显示顺序
                    bullet_distribution_text = "、".join(bullet_distribution)
                    
                    # 发送回合更新消息
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"🔄 第 {game_data['round_counter']} 回合，散弹枪已装填\n"
                                f"本回合可能的子弹: {bullet_distribution_text}\n"
                                f"请 {next_player_name} @某人 进行射击\n"
                                f"💊 玩家道具已重置，有机会获得新道具"
                    )
                else:
                    # 发送继续射击提示
                    await self.bot.send_msg(
                        message_type="group",
                        group_id=group_id,
                        message=f"空包弹不会造成伤害，{nickname} 继续射击\n"
                                f"本回合剩余 {game_data['bullets_remaining']} 发子弹\n"
                                f"请 {nickname} @某人 进行射击"
                    )
                    
                    # 清除@记录
                    room.mentioned_player_id = None
                    room.target_player_id = None
                    
                    return True
            
            # 如果子弹已用完，进入新回合
            if game_data["bullets_remaining"] <= 0:
                # 回合计数器+1
                game_data["round_counter"] += 1
                
                # 更新子弹数量（随回合递增，起始3发，最多8发）
                game_data["bullets_per_round"] = min(8, game_data["round_counter"] + 2)
                game_data["bullets_remaining"] = game_data["bullets_per_round"]
                
                # 清空所有玩家的道具
                for pid in room.players:
                    if pid not in game_data["eliminated_players"] and pid in game_data["players_items"]:
                        game_data["players_items"][pid] = []
                
                # 随机为玩家发放新道具（每回合每个玩家可能获得一个道具）
                for pid in room.players:
                    if pid in game_data["eliminated_players"]:
                        continue
                        
                    # 50%概率获得道具
                    if random.random() < 0.5:
                        new_item = random.choice(self.roulette_items)
                        if pid in game_data["players_items"]:
                            game_data["players_items"][pid].append(new_item["name"])
                
                # 进入下一位玩家的回合
                next_player_id = room.next_player()
                next_player_name = room.player_names.get(next_player_id, str(next_player_id))
                
                # 先生成子弹分布
                room.bullets = room.generate_bullets(game_data["bullets_per_round"])
                
                # 生成子弹分布显示文本
                bullet_distribution = []
                for bullet_type in room.bullets:
                    if bullet_type == 1:
                        bullet_distribution.append("空包弹")
                    else:
                        bullet_distribution.append("实弹")
                random.shuffle(bullet_distribution)  # 打乱显示顺序
                bullet_distribution_text = "、".join(bullet_distribution)
                
                # 发送回合更新消息
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"🔄 第 {game_data['round_counter']} 回合，散弹枪已装填\n"
                            f"本回合可能的子弹: {bullet_distribution_text}\n"
                            f"请 {next_player_name} @某人 进行射击\n"
                            f"💊 玩家道具已重置，有机会获得新道具"
                )
            else:
                # 进入下一位玩家的回合
                next_player_id = room.next_player()
                next_player_name = room.player_names.get(next_player_id, str(next_player_id))
                
                # 生成子弹分布显示文本
                bullet_distribution = []
                for bullet_type in room.bullets:
                    if bullet_type == 1:
                        bullet_distribution.append("空包弹")
                    else:
                        bullet_distribution.append("实弹")
                # 只显示剩余的子弹
                bullet_distribution = bullet_distribution[:game_data['bullets_remaining']]
                random.shuffle(bullet_distribution)  # 打乱显示顺序
                bullet_distribution_text = "、".join(bullet_distribution)
                
                await self.bot.send_msg(
                    message_type="group",
                    group_id=group_id,
                    message=f"下一轮: 散弹枪已装填\n"
                            f"本回合可能的子弹: {bullet_distribution_text}\n"
                            f"请 {next_player_name} @某人 进行射击"
                )
            
            # 清除@记录
            room.mentioned_player_id = None
            room.target_player_id = None
            
            return True
        
        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = WordGames 