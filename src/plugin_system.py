#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import hashlib
from typing import Dict, Any, Optional, List

logger = logging.getLogger("LCHBot")

def generate_plugin_id(plugin_name: str) -> int:
    """
    生成唯一的插件ID，使用类名的哈希来确保相同插件名总是获得相同ID
    
    参数:
        plugin_name: 插件类名
    返回:
        插件ID (100-999范围)
    """
    # 计算插件名称的哈希值
    name_hash = hashlib.md5(plugin_name.encode('utf-8')).hexdigest()
    
    # 使用哈希值的前8个字符转换为整数
    hash_int = int(name_hash[:8], 16)
    
    # 将结果映射到100-999范围内
    # 100是保留给系统插件的最小值，999是最大值
    plugin_id = 100 + (hash_int % 900)
    
    logger.debug(f"为插件 {plugin_name} 生成ID: {plugin_id}")
    return plugin_id

# 插件基类
class Plugin:
    """插件基类，所有插件必须继承此类"""
    
    def __init__(self, bot):
        self.bot = bot
        self.name = self.__class__.__name__
        self.id = generate_plugin_id(self.name)  # 使用哈希生成唯一ID
        self.status = "active"  # 插件状态: active, disabled, error
        self.error_message = None  # 如果插件出错，存储错误信息
        self.priority = 0  # 插件优先级，数值越大优先级越高，默认为0
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化")

    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件，返回是否已处理"""
        return False

    async def handle_notice(self, event: Dict[str, Any]) -> bool:
        """处理通知事件，返回是否已处理"""
        return False

    async def handle_request(self, event: Dict[str, Any]) -> bool:
        """处理请求事件，返回是否已处理"""
        return False
        
    def disable(self, reason: Optional[str] = None) -> None:
        """禁用插件"""
        self.status = "disabled"
        if reason:
            self.error_message = reason
        logger.info(f"插件 {self.name} (ID: {self.id}) 已禁用: {reason or '无原因'}")
        
    def enable(self) -> None:
        """启用插件"""
        self.status = "active"
        self.error_message = None
        logger.info(f"插件 {self.name} (ID: {self.id}) 已启用")
        
    def set_error(self, error_message: str) -> None:
        """设置插件错误状态"""
        self.status = "error"
        self.error_message = error_message
        logger.error(f"插件 {self.name} (ID: {self.id}) 出错: {error_message}")

# 插件管理器
class PluginManager:
    """插件管理器，负责插件的加载、管理和调用"""
    
    def __init__(self, bot=None):
        self.plugins: List[Plugin] = []
        self.inline_plugins: List[Plugin] = []  # 专门用于存储内联插件
        self.bot = bot  # 保存机器人实例引用
        
    def register_plugin(self, plugin: Plugin) -> None:
        """注册一个插件"""
        self.plugins.append(plugin)
        
    def register_inline_plugin(self, plugin: Plugin) -> None:
        """注册一个内联插件，将优先处理消息"""
        self.inline_plugins.append(plugin)
        logger.info(f"内联插件 {plugin.name} (ID: {plugin.id}) 已注册")
        
    def unregister_plugin(self, plugin_id: int) -> bool:
        """注销一个插件"""
        # 先检查内联插件列表
        for i, plugin in enumerate(self.inline_plugins):
            if plugin.id == plugin_id:
                self.inline_plugins.pop(i)
                logger.info(f"内联插件 {plugin.name} (ID: {plugin.id}) 已注销")
                return True
                
        # 再检查普通插件列表
        for i, plugin in enumerate(self.plugins):
            if plugin.id == plugin_id:
                self.plugins.pop(i)
                logger.info(f"插件 {plugin.name} (ID: {plugin.id}) 已注销")
                return True
        return False
        
    def get_plugin_by_id(self, plugin_id: int) -> Optional[Plugin]:
        """根据ID获取插件"""
        # 先检查内联插件
        for plugin in self.inline_plugins:
            if plugin.id == plugin_id:
                return plugin
        
        # 再检查普通插件
        for plugin in self.plugins:
            if plugin.id == plugin_id:
                return plugin
        return None
        
    def get_plugin_by_name(self, name: str) -> Optional[Plugin]:
        """根据名称获取插件"""
        # 先检查内联插件
        for plugin in self.inline_plugins:
            if plugin.name == name:
                return plugin
                
        # 再检查普通插件
        for plugin in self.plugins:
            if plugin.name == name:
                return plugin
        return None
        
    def get_active_plugins(self) -> List[Plugin]:
        """获取所有活跃的插件"""
        return ([p for p in self.inline_plugins if p.status == "active"] + 
                [p for p in self.plugins if p.status == "active"])
        
    def get_all_plugins(self) -> List[Plugin]:
        """获取所有插件"""
        return self.inline_plugins.copy() + self.plugins.copy()
        
    async def dispatch_message(self, event: Dict[str, Any]) -> bool:
        """分发消息事件到插件"""
        # 首先尝试使用内联插件处理消息
        # 对内联插件按优先级排序
        sorted_inline_plugins = sorted([p for p in self.inline_plugins if p.status == "active"], 
                                    key=lambda p: p.priority, reverse=True)
                                    
        for plugin in sorted_inline_plugins:
            try:
                logger.debug(f"尝试使用内联插件 {plugin.name} (ID: {plugin.id}, 优先级: {plugin.priority}) 处理消息")
                if await plugin.handle_message(event):
                    logger.info(f"消息已被内联插件 {plugin.name} (ID: {plugin.id}) 处理")
                    return True
            except Exception as e:
                plugin.set_error(str(e))
                logger.error(f"内联插件 {plugin.name} (ID: {plugin.id}) 处理消息事件出错: {e}", exc_info=True)
        
        # 再使用普通插件处理，按优先级排序
        active_plugins = sorted([p for p in self.plugins if p.status == "active"], 
                              key=lambda p: p.priority, reverse=True)
        logger.debug(f"尝试处理消息事件，活跃插件数量: {len(active_plugins)}")
        
        for plugin in active_plugins:
            try:
                logger.debug(f"尝试使用插件 {plugin.name} (ID: {plugin.id}, 优先级: {plugin.priority}) 处理消息")
                if await plugin.handle_message(event):
                    logger.info(f"消息已被插件 {plugin.name} (ID: {plugin.id}) 处理")
                    return True
            except Exception as e:
                plugin.set_error(str(e))
                logger.error(f"插件 {plugin.name} (ID: {plugin.id}) 处理消息事件出错: {e}", exc_info=True)
                
        return False  # 没有插件处理此消息
        
    async def dispatch_notice(self, event: Dict[str, Any]) -> bool:
        """分发通知事件到插件"""
        # 合并内联和普通活跃插件，并按优先级排序
        active_plugins = sorted(
            [p for p in self.inline_plugins if p.status == "active"] + 
            [p for p in self.plugins if p.status == "active"],
            key=lambda p: p.priority, reverse=True
        )
        
        for plugin in active_plugins:
            try:
                if await plugin.handle_notice(event):
                    logger.info(f"通知已被插件 {plugin.name} (ID: {plugin.id}) 处理")
                    return True
            except Exception as e:
                plugin.set_error(str(e))
                logger.error(f"插件 {plugin.name} (ID: {plugin.id}) 处理通知事件出错: {e}", exc_info=True)
                
        return False  # 没有插件处理此通知
        
    async def dispatch_request(self, event: Dict[str, Any]) -> bool:
        """分发请求事件到插件"""
        # 合并内联和普通活跃插件，并按优先级排序
        active_plugins = sorted(
            [p for p in self.inline_plugins if p.status == "active"] + 
            [p for p in self.plugins if p.status == "active"],
            key=lambda p: p.priority, reverse=True
        )
        
        for plugin in active_plugins:
            try:
                if await plugin.handle_request(event):
                    logger.info(f"请求已被插件 {plugin.name} (ID: {plugin.id}) 处理")
                    return True
            except Exception as e:
                plugin.set_error(str(e))
                logger.error(f"插件 {plugin.name} (ID: {plugin.id}) 处理请求事件出错: {e}", exc_info=True)
                
        return False  # 没有插件处理此请求 