import logging
import json
from typing import Dict, Any, List, Optional

from src.plugin_system import Plugin

logger = logging.getLogger('LCHBot')

class MessageFilter(Plugin):
    """消息过滤插件，用于过滤来自特定QQ号的消息"""
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "MessageFilter"
        self.priority = 999  # 设置高优先级，确保在其他插件之前处理
        
        # 需要屏蔽的QQ号列表
        self.blocked_qq_list = [
            2854196310,  # Q群管家
            # 可以添加更多需要屏蔽的QQ号
        ]
        
        # 记录屏蔽消息统计
        self.blocked_count = 0
        
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化，当前屏蔽用户数: {len(self.blocked_qq_list)}")

    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件，返回True表示消息被屏蔽，不再继续处理"""
        # 只处理群聊消息
        if event.get('message_type') != 'group':
            return False
            
        # 获取发送者QQ号
        user_id = event.get('user_id')
        if not user_id:
            return False
            
        # 检查是否在屏蔽列表中
        if user_id in self.blocked_qq_list:
            sender_name = event.get('sender', {}).get('nickname', str(user_id))
            group_id = event.get('group_id', '未知群')
            message = event.get('raw_message', '')[:30]  # 只记录前30个字符
            
            logger.info(f"已屏蔽来自 {sender_name}({user_id}) 在群 {group_id} 的消息: {message}...")
            self.blocked_count += 1
            
            # 返回True表示消息已处理，阻止其他插件处理
            return True
            
        return False
        
    async def handle_notice(self, event: Dict[str, Any]) -> bool:
        """处理通知事件"""
        # 可以根据需要屏蔽特定用户的通知事件
        return False
        
    async def handle_request(self, event: Dict[str, Any]) -> bool:
        """处理请求事件"""
        # 可以根据需要屏蔽特定用户的请求事件
        return False

# 导出插件类，确保插件加载器能找到它
plugin_class = MessageFilter 