#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工具类模块，提供消息段构造等功能
"""

import re
import logging
from typing import Dict, Any, List, Union, Optional, Tuple

logger = logging.getLogger("LCHBot")

class MessageSegment:
    """消息段构造工具类"""
    
    @staticmethod
    def text(text: str) -> Dict[str, Any]:
        """
        纯文本消息段
        
        参数:
            text: 文本内容
        """
        return {"type": "text", "data": {"text": text}}
    
    @staticmethod
    def face(id: int) -> Dict[str, Any]:
        """
        QQ表情
        
        参数:
            id: 表情ID
        """
        return {"type": "face", "data": {"id": str(id)}}
    
    @staticmethod
    def image(file: str, type: Optional[str] = None, cache: bool = True, proxy: bool = True, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        图片消息段
        
        参数:
            file: 图片文件名、URL、路径或Base64编码
            type: 图片类型，flash表示闪照，show表示秀图
            cache: 是否使用已缓存的文件
            proxy: 是否通过代理下载文件
            timeout: 下载超时时间
        """
        data = {"file": file}
        if type is not None:
            data["type"] = type
        if not cache:
            data["cache"] = "0"
        if not proxy:
            data["proxy"] = "0"
        if timeout is not None:
            data["timeout"] = str(timeout)
        return {"type": "image", "data": data}
    
    @staticmethod
    def record(file: str, magic: bool = False, cache: bool = True, proxy: bool = True, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        语音消息段
        
        参数:
            file: 语音文件名、URL、路径或Base64编码
            magic: 是否为变声
            cache: 是否使用已缓存的文件
            proxy: 是否通过代理下载文件
            timeout: 下载超时时间
        """
        data = {"file": file}
        if magic:
            data["magic"] = "1"
        if not cache:
            data["cache"] = "0"
        if not proxy:
            data["proxy"] = "0"
        if timeout is not None:
            data["timeout"] = str(timeout)
        return {"type": "record", "data": data}
    
    @staticmethod
    def video(file: str, cache: bool = True, proxy: bool = True, timeout: Optional[int] = None) -> Dict[str, Any]:
        """
        短视频消息段
        
        参数:
            file: 视频文件名、URL、路径或Base64编码
            cache: 是否使用已缓存的文件
            proxy: 是否通过代理下载文件
            timeout: 下载超时时间
        """
        data = {"file": file}
        if not cache:
            data["cache"] = "0"
        if not proxy:
            data["proxy"] = "0"
        if timeout is not None:
            data["timeout"] = str(timeout)
        return {"type": "video", "data": data}
    
    @staticmethod
    def at(qq: Union[int, str]) -> Dict[str, Any]:
        """
        @某人
        
        参数:
            qq: 要@的QQ号，all表示@全体成员
        """
        return {"type": "at", "data": {"qq": str(qq)}}
    
    @staticmethod
    def rps() -> Dict[str, Any]:
        """猜拳魔法表情"""
        return {"type": "rps", "data": {}}
    
    @staticmethod
    def dice() -> Dict[str, Any]:
        """掷骰子魔法表情"""
        return {"type": "dice", "data": {}}
    
    @staticmethod
    def shake() -> Dict[str, Any]:
        """窗口抖动（戳一戳）"""
        return {"type": "shake", "data": {}}
    
    @staticmethod
    def poke(type: int, id: int) -> Dict[str, Any]:
        """
        戳一戳
        
        参数:
            type: 类型
            id: ID
        """
        return {"type": "poke", "data": {"type": str(type), "id": str(id)}}
    
    @staticmethod
    def anonymous(ignore: bool = False) -> Dict[str, Any]:
        """
        匿名发消息
        
        参数:
            ignore: 是否忽略匿名失败，如果为True，则匿名失败时仍然发送消息
        """
        data = {}
        if ignore:
            data["ignore"] = "1"
        return {"type": "anonymous", "data": data}
    
    @staticmethod
    def share(url: str, title: str, content: Optional[str] = None, image: Optional[str] = None) -> Dict[str, Any]:
        """
        链接分享
        
        参数:
            url: 链接URL
            title: 标题
            content: 内容描述
            image: 图片URL
        """
        data = {"url": url, "title": title}
        if content is not None:
            data["content"] = content
        if image is not None:
            data["image"] = image
        return {"type": "share", "data": data}
    
    @staticmethod
    def contact(type: str, id: int) -> Dict[str, Any]:
        """
        推荐联系人/群
        
        参数:
            type: 类型，group或qq
            id: 联系人/群的ID
        """
        return {"type": "contact", "data": {"type": type, "id": str(id)}}
    
    @staticmethod
    def location(lat: float, lon: float, title: Optional[str] = None, content: Optional[str] = None) -> Dict[str, Any]:
        """
        位置
        
        参数:
            lat: 纬度
            lon: 经度
            title: 标题
            content: 内容描述
        """
        data = {"lat": str(lat), "lon": str(lon)}
        if title is not None:
            data["title"] = title
        if content is not None:
            data["content"] = content
        return {"type": "location", "data": data}
    
    @staticmethod
    def music(type: str, id: int) -> Dict[str, Any]:
        """
        音乐分享
        
        参数:
            type: 类型，qq、163、xm分别表示QQ音乐、网易云音乐、虾米音乐
            id: 音乐ID
        """
        return {"type": "music", "data": {"type": type, "id": str(id)}}
    
    @staticmethod
    def music_custom(url: str, audio: str, title: str, content: Optional[str] = None, image: Optional[str] = None) -> Dict[str, Any]:
        """
        自定义音乐分享
        
        参数:
            url: 点击后跳转的URL
            audio: 音乐URL
            title: 标题
            content: 内容描述
            image: 图片URL
        """
        data = {"type": "custom", "url": url, "audio": audio, "title": title}
        if content is not None:
            data["content"] = content
        if image is not None:
            data["image"] = image
        return {"type": "music", "data": data}
    
    @staticmethod
    def reply(id: int) -> Dict[str, Any]:
        """
        回复
        
        参数:
            id: 回复的消息ID
        """
        return {"type": "reply", "data": {"id": str(id)}}
    
    @staticmethod
    def forward(id: str) -> Dict[str, Any]:
        """
        合并转发
        
        参数:
            id: 合并转发ID
        """
        return {"type": "forward", "data": {"id": id}}
    
    @staticmethod
    def node(id: int) -> Dict[str, Any]:
        """
        合并转发节点（引用）
        
        参数:
            id: 节点消息ID
        """
        return {"type": "node", "data": {"id": str(id)}}
    
    @staticmethod
    def node_custom(user_id: int, nickname: str, content: Union[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        合并转发自定义节点
        
        参数:
            user_id: 发送者QQ号
            nickname: 发送者昵称
            content: 消息内容，可以是字符串或消息段列表
        """
        data = {"user_id": str(user_id), "nickname": nickname}
        if isinstance(content, str):
            data["content"] = content
        else:
            # 消息段列表需要转换为消息对象
            data["content"] = message_segment_to_cq_code(content)
        return {"type": "node", "data": data}
    
    @staticmethod
    def xml(data: str) -> Dict[str, Any]:
        """
        XML消息
        
        参数:
            data: XML内容
        """
        return {"type": "xml", "data": {"data": data}}
    
    @staticmethod
    def json(data: str) -> Dict[str, Any]:
        """
        JSON消息
        
        参数:
            data: JSON内容
        """
        return {"type": "json", "data": {"data": data}}

class Message(list):
    """消息类，继承自list，提供一系列操作消息的便捷方法"""
    
    def __init__(self, message: Union[str, List[Dict[str, Any]], Dict[str, Any], "Message", None] = None):
        """
        初始化消息对象
        
        参数:
            message: 消息内容，可以是字符串、消息段、消息段列表或None
        """
        super().__init__()
        if message is None:
            return
        elif isinstance(message, Message):
            self.extend(message)
        elif isinstance(message, list):
            self.extend(message)
        elif isinstance(message, dict):
            self.append(message)
        elif isinstance(message, str):
            self.append(MessageSegment.text(message))
    
    def append(self, obj: Union[str, Dict[str, Any], "Message"]) -> "Message":
        """
        添加消息段到消息中
        
        参数:
            obj: 要添加的消息段
            
        返回:
            添加后的消息对象（即self）
        """
        if isinstance(obj, str):
            super().append(MessageSegment.text(obj))
        elif isinstance(obj, dict):
            super().append(obj)
        elif isinstance(obj, Message):
            for segment in obj:
                super().append(segment)
        else:
            raise TypeError(f"Unsupported type: {type(obj)}")
        return self
    
    def extend(self, obj: Union[List[Dict[str, Any]], "Message"]) -> "Message":
        """
        扩展消息段到消息中
        
        参数:
            obj: 要扩展的消息段列表
            
        返回:
            扩展后的消息对象（即self）
        """
        if isinstance(obj, list):
            for segment in obj:
                self.append(segment)
        elif isinstance(obj, Message):
            for segment in obj:
                super().append(segment)
        else:
            raise TypeError(f"Unsupported type: {type(obj)}")
        return self
    
    def extract_plain_text(self) -> str:
        """
        提取消息中的纯文本部分
        
        返回:
            消息中的纯文本部分
        """
        result = ""
        for segment in self:
            if segment["type"] == "text":
                result += segment["data"]["text"]
        return result
    
    def __add__(self, other: Union[str, Dict[str, Any], List[Dict[str, Any]], "Message"]) -> "Message":
        """
        连接两个消息对象
        
        参数:
            other: 要连接的另一个消息对象
            
        返回:
            连接后的新消息对象
        """
        result = Message(self)
        if isinstance(other, str):
            result.append(MessageSegment.text(other))
        elif isinstance(other, dict):
            result.append(other)
        elif isinstance(other, list):
            result.extend(other)
        elif isinstance(other, Message):
            result.extend(other)
        else:
            raise TypeError(f"Unsupported type: {type(other)}")
        return result
    
    def __str__(self) -> str:
        """
        将消息转换为字符串形式
        
        返回:
            消息的字符串形式
        """
        return message_segment_to_cq_code(self)
    
    def __repr__(self) -> str:
        """
        返回消息的调试字符串表示
        
        返回:
            消息的调试字符串表示
        """
        return f"Message({list(self).__repr__()})"

def escape(text: str) -> str:
    """
    对CQ码中的特殊字符进行转义
    
    参数:
        text: 要转义的文本
        
    返回:
        转义后的文本
    """
    return text.replace("&", "&amp;") \
        .replace("[", "&#91;") \
        .replace("]", "&#93;") \
        .replace(",", "&#44;")

def unescape(text: str) -> str:
    """
    对CQ码中的特殊字符进行反转义
    
    参数:
        text: 要反转义的文本
        
    返回:
        反转义后的文本
    """
    return text.replace("&amp;", "&") \
        .replace("&#91;", "[") \
        .replace("&#93;", "]") \
        .replace("&#44;", ",")

def cq_code_to_message_segment(cq_code: str) -> List[Dict[str, Any]]:
    """
    将CQ码字符串转换为消息段列表
    
    参数:
        cq_code: CQ码字符串
        
    返回:
        消息段列表
    """
    msg = Message()
    text_begin = 0
    
    # 匹配CQ码
    cq_code_pattern = r'\[CQ:([^,\]]+)(?:,([^\]]+))?]'
    for match in re.finditer(cq_code_pattern, cq_code):
        # 添加CQ码之前的纯文本部分
        if match.start() > text_begin:
            text = unescape(cq_code[text_begin:match.start()])
            if text:
                msg.append(MessageSegment.text(text))
        text_begin = match.end()
        
        # 解析CQ码
        type_ = match.group(1)
        params_str = match.group(2) or ''
        
        # 解析参数
        params = {}
        for param in params_str.split(','):
            if not param:
                continue
            key, *value = param.split('=', 1)
            params[key] = unescape(value[0]) if value else True
        
        # 创建消息段
        if type_ == 'text':
            msg.append(MessageSegment.text(params.get('text', '')))
        else:
            msg.append({"type": type_, "data": params})
    
    # 添加剩余的纯文本部分
    if text_begin < len(cq_code):
        text = unescape(cq_code[text_begin:])
        if text:
            msg.append(MessageSegment.text(text))
    
    return msg

def message_segment_to_cq_code(message: Union[List[Dict[str, Any]], Message]) -> str:
    """
    将消息段列表转换为CQ码字符串
    
    参数:
        message: 消息段列表或Message对象
        
    返回:
        CQ码字符串
    """
    cq_code = ""
    for segment in message:
        type_ = segment["type"]
        data = segment["data"]
        
        if type_ == "text":
            cq_code += escape(data["text"])
        else:
            params = ",".join(f"{key}={escape(str(value))}" for key, value in data.items())
            cq_code += f"[CQ:{type_}" + (f",{params}" if params else "") + "]"
    
    return cq_code

# === 新增的消息处理工具函数 ===

def is_at_bot(event: Dict[str, Any], bot_qq: str) -> bool:
    """
    检查消息是否@了机器人
    
    参数:
        event: 消息事件
        bot_qq: 机器人QQ号
        
    返回:
        是否@了机器人
    """
    # 获取原始消息
    raw_message = event.get('raw_message', '')
    
    # 检查消息段中是否有@机器人
    message_array = event.get("message", [])
    for segment in message_array:
        if segment.get("type") == "at" and segment.get("data", {}).get("qq") == bot_qq:
            return True
    
    # 检查原始消息中的CQ码
    if "[CQ:at,qq=" in raw_message:
        if f"[CQ:at,qq={bot_qq}" in raw_message:
            return True
    
    return False

def extract_command(event: Dict[str, Any], bot_qq: str) -> str:
    """
    从消息中提取命令（去除@机器人的部分）
    
    参数:
        event: 消息事件
        bot_qq: 机器人QQ号
        
    返回:
        提取出的命令（去除前后空格）
    """
    # 获取原始消息和消息数组
    raw_message = event.get('raw_message', '')
    message_array = event.get("message", [])
    
    # 方法1: 从消息数组中提取
    extracted_command = ""
    for i, segment in enumerate(message_array):
        if segment.get("type") == "at" and segment.get("data", {}).get("qq") == bot_qq:
            # 收集@之后的文本内容
            remaining_segments = message_array[i+1:]
            for text_segment in remaining_segments:
                if text_segment.get("type") == "text":
                    extracted_command += text_segment.get("data", {}).get("text", "")
            break
    
    # 方法2: 从原始消息中提取@后面的命令
    if not extracted_command and "[CQ:at,qq=" in raw_message:
        at_pattern = f"\\[CQ:at,qq={bot_qq}(,name=[^\\]]*)?\\]"
        message_parts = re.split(at_pattern, raw_message, maxsplit=1)
        if len(message_parts) > 1:
            extracted_command = message_parts[1].strip()
    
    # 确保去除命令前后的空格
    return extracted_command.strip()

def match_command(command: str, pattern: re.Pattern) -> Optional[re.Match]:
    """
    匹配命令与模式
    
    参数:
        command: 命令字符串
        pattern: 正则表达式模式
        
    返回:
        匹配结果，如果不匹配则返回None
    """
    return pattern.match(command)

def handle_at_command(event: Dict[str, Any], bot, command_pattern: re.Pattern) -> Tuple[bool, Optional[re.Match], str]:
    """
    处理@机器人的命令消息
    
    参数:
        event: 消息事件
        bot: 机器人对象
        command_pattern: 命令模式（正则表达式）
        
    返回:
        (是否是有效的@命令, 匹配结果, 提取的命令)
    """
    # 获取机器人的QQ号
    bot_qq = str(bot.config.get("bot", {}).get("self_id", ""))
    
    # 检查是否@了机器人
    if not is_at_bot(event, bot_qq):
        return False, None, ""
    
    # 提取命令
    command = extract_command(event, bot_qq)
    logger.debug(f"从消息中提取到命令: '{command}'")
    
    # 匹配命令
    match = match_command(command, command_pattern)
    
    return True, match, command 