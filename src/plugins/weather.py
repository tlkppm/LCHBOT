#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import json
import logging
import http.client
import urllib.parse
import datetime
import os
import tempfile
from typing import Dict, Any, Optional, List, Tuple, Union, TypedDict

# 初始化logger
logger = logging.getLogger("LCHBot")

# 尝试导入PIL库
PIL_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    logger.error("Pillow库未安装，请安装: pip install pillow")
    PIL_AVAILABLE = False

# 导入Plugin基类和工具函数
from plugin_system import Plugin
from plugins.utils import handle_at_command

# 定义字体字典类型
class FontDict(TypedDict):
    title: Optional[Union[ImageFont.ImageFont, ImageFont.FreeTypeFont]]
    large: Optional[Union[ImageFont.ImageFont, ImageFont.FreeTypeFont]]
    normal: Optional[Union[ImageFont.ImageFont, ImageFont.FreeTypeFont]]
    small: Optional[Union[ImageFont.ImageFont, ImageFont.FreeTypeFont]]

class Weather(Plugin):
    """
    天气预报插件，用于查询指定城市的天气情况
    命令格式: @机器人 /weather 城市名
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.command_pattern = re.compile(r'^/weather\s+(.+)$')
        # 新API不需要API密钥
        self.base_url = "v2.xxapi.cn"
        # 星期几中文表示
        self.weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        # 天气图标映射
        self.weather_icons = {
            "晴": "☀️",
            "多云": "⛅️",
            "阴": "☁️",
            "小雨": "🌦️",
            "中雨": "🌧️",
            "大雨": "🌧️",
            "暴雨": "⛈️",
            "雷阵雨": "⛈️",
            "小雪": "🌨️",
            "中雪": "🌨️",
            "大雪": "❄️",
            "雾": "🌫️",
            "霾": "🌫️"
        }
        # 创建插件目录用于存储临时图片
        self.temp_dir = os.path.join(tempfile.gettempdir(), "lchbot_weather")
        os.makedirs(self.temp_dir, exist_ok=True)
        
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        message_type = event.get('message_type', '')
        user_id = event.get('user_id')
        group_id = event.get('group_id') if message_type == 'group' else None
        message_id = event.get("message_id", 0)  # 获取消息ID用于回复
        
        # 使用工具函数处理@机器人命令
        is_at_command, match, _ = handle_at_command(event, self.bot, self.command_pattern)
        
        if is_at_command and match:
            city = match.group(1).strip()
            logger.info(f"接收到天气查询命令，城市：{city}")
            
            # 构建回复CQ码（如果是群聊）
            reply_code = f"[CQ:reply,id={message_id}]" if message_type == 'group' else ""
            
            # 查询天气
            weather_data = await self.query_weather(city)
            
            if not weather_data:
                await self.bot.send_msg(
                    message_type=message_type,
                    user_id=user_id,
                    group_id=group_id,
                    message=f"{reply_code}抱歉，无法获取 {city} 的天气信息，请检查城市名称是否正确。"
                )
                return True
            
            # 生成天气信息
            if PIL_AVAILABLE:
                try:
                    # 尝试生成天气图片
                    image_path = self.generate_weather_image(weather_data)
                    
                    # 构建图片CQ码
                    image_cq = f"[CQ:image,file=file:///{image_path}]"
                    
                    # 发送图片消息
                    await self.bot.send_msg(
                        message_type=message_type,
                        user_id=user_id,
                        group_id=group_id,
                        message=f"{reply_code}{image_cq}"
                    )
                    return True
                except Exception as e:
                    logger.error(f"生成天气图片失败: {e}", exc_info=True)
                    # 如果图片生成失败，回退到文本格式
            
            # 使用文本格式回复（PIL不可用或图片生成失败）
            weather_info = self.format_weather_info(weather_data)
            await self.bot.send_msg(
                message_type=message_type,
                user_id=user_id,
                group_id=group_id,
                message=f"{reply_code}{weather_info}"
            )
            
            return True  # 表示已处理该消息
            
        return False  # 未处理该消息

    async def query_weather(self, city: str) -> Optional[Dict[str, Any]]:
        """查询指定城市的天气信息"""
        try:
            conn = http.client.HTTPSConnection(self.base_url)
            
            # 使用新的API地址
            path = f"/api/weather?city={urllib.parse.quote(city)}"
            logger.debug(f"请求天气API: {path}")
            
            conn.request("GET", path)
            response = conn.getresponse()
            data = response.read().decode('utf-8')
            
            # 解析返回的JSON数据
            result = json.loads(data)
            
            # 检查API返回状态
            if result.get("code") == 200:
                return result.get("data", {})
            else:
                logger.error(f"天气API返回错误: {result.get('msg')}")
                return None
            
        except Exception as e:
            logger.error(f"查询天气时发生错误: {e}", exc_info=True)
            return None
    
    def get_weekday_names(self) -> List[str]:
        """获取从今天开始的六天的星期几名称"""
        today = datetime.datetime.now()
        result = []
        
        for i in range(6):
            day = today + datetime.timedelta(days=i)
            # 星期一到星期日对应0到6
            weekday_index = day.weekday()
            result.append(self.weekdays[weekday_index])
            
        return result
    
    def get_weather_icon(self, weather: str) -> str:
        """获取天气对应的图标"""
        for key in self.weather_icons:
            if key in weather:
                return self.weather_icons[key]
        return "☁️"  # 默认图标
    
    def find_system_fonts(self) -> List[str]:
        """查找系统中可能存在的中文字体"""
        font_paths = []
        
        # 项目内字体
        project_font = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                  "resources", "fonts", "simhei.ttf")
        if os.path.exists(project_font):
            font_paths.append(project_font)
            
        # Windows系统字体
        win_fonts = [
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), "Fonts", "simhei.ttf"),
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), "Fonts", "msyh.ttc"),
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), "Fonts", "simsun.ttc"),
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), "Fonts", "msyh.ttf"),
            os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), "Fonts", "simsun.ttf"),
        ]
        
        # Linux系统字体
        linux_fonts = [
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc"
        ]
        
        # 检查所有可能的字体路径
        for path in win_fonts + linux_fonts:
            if os.path.exists(path):
                font_paths.append(path)
                
        return font_paths
    
    def load_fonts(self) -> FontDict:
        """加载字体并返回字体字典"""
        # 默认值
        fonts: FontDict = {
            'title': None,
            'large': None, 
            'normal': None,
            'small': None
        }
        
        if not PIL_AVAILABLE:
            return fonts
            
        try:
            # 尝试查找系统字体
            font_paths = self.find_system_fonts()
            if font_paths:
                logger.info(f"找到可用字体: {font_paths[0]}")
                try:
                    fonts['title'] = ImageFont.truetype(font_paths[0], 20)
                    fonts['large'] = ImageFont.truetype(font_paths[0], 36)
                    fonts['normal'] = ImageFont.truetype(font_paths[0], 16)
                    fonts['small'] = ImageFont.truetype(font_paths[0], 14)
                    return fonts
                except Exception as e:
                    logger.error(f"加载字体失败: {e}", exc_info=True)
                
            # 使用默认字体
            logger.warning("未找到中文字体，使用默认字体")
            default_font = ImageFont.load_default()
            fonts['title'] = default_font
            fonts['large'] = default_font
            fonts['normal'] = default_font
            fonts['small'] = default_font
            
        except Exception as e:
            logger.error(f"加载字体失败: {e}", exc_info=True)
            # 在出错的情况下，返回None值的字典
            pass
            
        return fonts
    
    def generate_weather_image(self, weather_data: Dict[str, Any]) -> str:
        """生成天气信息图片 - 采用简洁灰色风格"""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow库未安装")
            
        city = weather_data.get("city", "未知城市")
        forecast = weather_data.get("data", [])
        
        if not forecast:
            raise ValueError("天气数据为空")
        
        # 获取系统日期对应的星期几
        weekday_names = self.get_weekday_names()
        
        # 创建一个灰色背景的图片 - 与示例相似
        width, height = 350, 260  # 更适合的尺寸
        bg_color = (122, 138, 153)  # 灰蓝色背景
        image = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(image)
        
        # 加载字体 - 尽可能使用系统字体
        font_paths = self.find_system_fonts()
        font_path = font_paths[0] if font_paths else None
        
        # 字体大小定义
        try:
            if font_path:
                logger.info(f"使用字体: {font_path}")
                header_font = ImageFont.truetype(font_path, 14)
                large_font = ImageFont.truetype(font_path, 48)  # 大字体显示温度
                normal_font = ImageFont.truetype(font_path, 16)
                small_font = ImageFont.truetype(font_path, 14)
            else:
                # 使用默认字体
                default = ImageFont.load_default()
                header_font = default
                large_font = default
                normal_font = default
                small_font = default
        except Exception as e:
            logger.error(f"加载字体失败: {e}", exc_info=True)
            default = ImageFont.load_default()
            header_font = default
            large_font = default
            normal_font = default
            small_font = default
            
        # 填充颜色定义
        text_color = (255, 255, 255)  # 白色文字
        light_text = (220, 220, 220)  # 浅色文字
        divider_color = (200, 200, 200, 100)  # 分隔线颜色
        
        # 头部 - 城市和更新时间
        now = datetime.datetime.now()
        time_str = now.strftime("%H:%M更新")
        draw.text((10, 10), f"{city} {time_str}", fill=text_color, font=header_font)
        
        # 水平分隔线
        draw.line([(0, 30), (width, 30)], fill=divider_color, width=1)
        
        # 今天的天气详情
        today = forecast[0]
        today_weather = today.get('weather', '未知')
        today_temp = today.get('temperature', '未知')
        today_wind = today.get('wind', '未知')
        today_air = today.get('air_quality', '未知')
        
        # 提取温度数字
        temp_match = re.search(r'(\d+)-(\d+)', today_temp)
        if temp_match:
            max_temp = temp_match.group(2)  # 高温
        else:
            max_temp = "25"  # 默认值
            
        # 主区域 - 左侧显示温度
        draw.text((30, 45), f"{max_temp}°", fill=text_color, font=large_font)
        
        # 右侧显示风况、空气质量等信息
        draw.text((width-120, 45), f"{today_wind}", fill=text_color, font=small_font)
        draw.text((width-120, 75), f"空气质量 {today_air}", fill=text_color, font=small_font)
        draw.text((width-120, 105), f"温度 {today_temp}", fill=text_color, font=small_font)
        
        # 天气状况
        draw.text((30, 110), f"{today_weather}", fill=text_color, font=normal_font)
        
        # 水平分隔线
        draw.line([(0, 170), (width, 170)], fill=divider_color, width=1)
        
        # 未来天气预报 - 最多显示3天
        forecast_count = min(3, len(forecast)-1)
        col_width = width // forecast_count
        
        for i, day in enumerate(forecast[1:4], 1):
            date = weekday_names[i] if i < len(weekday_names) else day.get("date", "")
            weather = day.get("weather", "未知")
            temperature = day.get("temperature", "未知")
            
            # 计算位置 - 居中对齐
            x = (i-1) * col_width + (col_width // 2) - 20
            
            # 显示星期几
            draw.text((x, 180), date, fill=text_color, font=small_font)
            
            # 显示天气状况和温度
            draw.text((x, 210), weather, fill=text_color, font=small_font)
            draw.text((x, 235), temperature, fill=light_text, font=small_font)
        
        # 数据来源
        source_text = "数据来源:xxapi.cn"
        draw.text((width-80, height-15), source_text, fill=light_text, font=ImageFont.load_default())
        
        # 保存图片
        timestamp = int(datetime.datetime.now().timestamp())
        image_path = os.path.join(self.temp_dir, f"weather_{city}_{timestamp}.png")
        image.save(image_path)
        
        return image_path
    
    def format_weather_info(self, weather_data: Dict[str, Any]) -> str:
        """格式化天气信息(文本备用)"""
        try:
            # 提取城市名
            city = weather_data.get("city", "未知城市")
            
            # 提取天气预报列表
            forecast = weather_data.get("data", [])
            
            if not forecast:
                return f"【{city}】未获取到天气数据。"
            
            # 获取系统日期对应的星期几
            weekday_names = self.get_weekday_names()
            
            # 构造回复内容
            weather_info = f"【{city} 天气预报】\n\n"
            
            # 今天的天气
            today = forecast[0]
            weather_info += f"今日({weekday_names[0]}):\n"
            weather_info += f"☁️ 天气: {today.get('weather', '未知')}\n"
            weather_info += f"🌡️ 温度: {today.get('temperature', '未知')}\n"
            weather_info += f"💨 风况: {today.get('wind', '未知')}\n"
            weather_info += f"🏭 空气: {today.get('air_quality', '未知')}\n\n"
            
            # 未来天气预报
            weather_info += "【未来天气预报】\n"
            for i, day in enumerate(forecast[1:], 1):  # 从第二天开始
                if i < len(weekday_names):
                    date = weekday_names[i]
                else:
                    date = day.get("date", "")
                    
                weather = day.get("weather", "")
                temperature = day.get("temperature", "")
                air = day.get("air_quality", "")
                
                weather_info += f"{date}: {weather}, {temperature}, 空气{air}\n"
            
            return weather_info
        
        except Exception as e:
            logger.error(f"格式化天气信息时发生错误: {e}", exc_info=True)
            return f"获取到天气信息，但格式化时出错。"

# 导出插件类，确保插件加载器能找到它
plugin_class = Weather 