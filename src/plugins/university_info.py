#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import logging
import json
import aiohttp
import sys
import os
import tempfile
import datetime
from typing import Dict, Any, List, Optional

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 导入Plugin基类
from plugin_system import Plugin

logger = logging.getLogger("LCHBot")

# 尝试导入PIL库
PIL_AVAILABLE = False
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    logger.error("Pillow库未安装，请安装: pip install pillow")
    PIL_AVAILABLE = False

class UniversityInfo(Plugin):
    """
    大学信息查询插件
    功能：查询国内外大学信息
    使用方法：@机器人 /university [大学名称]
    """
    
    def __init__(self, bot):
        super().__init__(bot)
        self.name = "UniversityInfo"
        # 同时支持英文和中文命令
        self.command_pattern_en = re.compile(r'^/university\s+(.+)$')
        self.command_pattern_zh = re.compile(r'^/大学\s+(.+)$')
        # 请调用你自己的API
        self.api_url = "https://api.000"
        # 创建临时目录用于存储生成的图片
        self.temp_dir = tempfile.gettempdir()
        logger.info(f"插件 {self.name} (ID: {self.id}) 已初始化")
    
    async def handle_message(self, event: Dict[str, Any]) -> bool:
        """处理消息事件"""
        from plugins.utils import extract_command, is_at_bot
        
        # 判断是否是群消息
        if event.get('message_type') != 'group':
            return False
        
        # 获取原始消息
        message = event.get('raw_message', '')
        
        # 如果消息中有@机器人，则提取命令部分
        if '[CQ:at,qq=' in message:
            bot_qq = str(self.bot.config.get("bot", {}).get("self_id", ""))
            if is_at_bot(event, bot_qq):
                message = extract_command(event, bot_qq)
                
                # 检查英文命令
                match_en = self.command_pattern_en.match(message)
                if match_en:
                    university_name = match_en.group(1).strip()
                    return await self.query_university(event, university_name)
                
                # 检查中文命令
                match_zh = self.command_pattern_zh.match(message)
                if match_zh:
                    university_name = match_zh.group(1).strip()
                    return await self.query_university(event, university_name)
        
        return False
    
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
    
    def generate_university_image(self, uni_name: str, data: Dict[str, Any]) -> str:
        """生成大学信息图片"""
        if not PIL_AVAILABLE:
            raise ImportError("Pillow库未安装")
        
        # 创建一个合适尺寸的图片，给大学详细介绍留出足够空间
        width, height = 800, 1000
        bg_color = (245, 245, 245)  # 浅灰色背景
        image = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(image)
        
        # 加载字体
        font_paths = self.find_system_fonts()
        font_path = font_paths[0] if font_paths else None
        
        try:
            if font_path:
                logger.info(f"使用字体: {font_path}")
                title_font = ImageFont.truetype(font_path, 36)
                header_font = ImageFont.truetype(font_path, 24)
                normal_font = ImageFont.truetype(font_path, 18)
                small_font = ImageFont.truetype(font_path, 16)
            else:
                # 使用默认字体
                default = ImageFont.load_default()
                title_font = default
                header_font = default
                normal_font = default
                small_font = default
        except Exception as e:
            logger.error(f"加载字体失败: {e}", exc_info=True)
            default = ImageFont.load_default()
            title_font = default
            header_font = default
            normal_font = default
            small_font = default
        
        # 颜色定义
        title_color = (0, 51, 102)  # 深蓝色标题
        header_color = (51, 51, 153)  # 蓝紫色小标题
        text_color = (51, 51, 51)  # 深灰色文本
        light_color = (102, 102, 102)  # 浅灰色文本
        divider_color = (220, 220, 220)  # 分隔线颜色
        
        # 页眉 - 大学名称和更新时间
        now = datetime.datetime.now()
        time_str = now.strftime("%Y-%m-%d %H:%M")
        
        # 标题居中
        # 在新版PIL中，textsize已弃用，使用更新的方法
        if hasattr(title_font, 'getbbox'):
            title_width = title_font.getbbox(uni_name)[2]
        else:
            title_width = 0
            
        title_x = (width - title_width) // 2 if title_width > 0 else 30
        
        draw.text((title_x, 30), uni_name, fill=title_color, font=title_font)
        draw.text((width-200, 40), time_str, fill=light_color, font=small_font)
        
        # 水平分隔线
        draw.line([(30, 80), (width-30, 80)], fill=divider_color, width=2)
        
        # 基本信息区域
        y_pos = 100
        
        # 信息项目
        info_items = [
            ("创建时间", data.get("founding", "未知")),
            ("占地面积", data.get("area", "未知")),
            ("隶属于", data.get("affiliate", "未知")),
            ("学校代码", data.get("encode", "未知")),
            ("地址", data.get("address", "未知")),
            ("国家重点学科", data.get("discipline", "未知")),
            ("重点实验室", data.get("laboratory", "未知")),
            ("博士学科", data.get("doctor", "未知")),
            ("硕士学科", data.get("master", "未知"))
        ]
        
        # 绘制基本信息标题
        draw.text((30, y_pos), "基本信息", fill=header_color, font=header_font)
        y_pos += 40
        
        # 绘制信息项目
        for label, value in info_items:
            draw.text((50, y_pos), f"{label}:", fill=text_color, font=normal_font)
            
            # 处理可能过长的值，比如地址
            max_width = width - 200  # 预留左边距和右边距
            value_lines = self._wrap_text(value, normal_font, max_width)
            
            for i, line in enumerate(value_lines):
                draw.text((200, y_pos + i * 25), line, fill=text_color, font=normal_font)
            
            # 根据行数增加垂直间距
            y_pos += max(30, len(value_lines) * 25 + 5)
        
        # 绘制简介
        y_pos += 20
        draw.text((30, y_pos), "学校简介", fill=header_color, font=header_font)
        y_pos += 40
        
        # 处理简介文本
        intro = data.get("intro", "暂无简介")
        intro_lines = self._wrap_text(intro, normal_font, width - 80)
        
        for i, line in enumerate(intro_lines):
            # 检查是否超出图片范围
            if y_pos + i * 25 >= height - 100:  # 预留底部空间
                # 如果超出范围，调整图片高度
                new_height = y_pos + (len(intro_lines) + 5) * 25 + 100  # 增加足够的空间
                new_image = Image.new('RGB', (width, new_height), bg_color)
                new_image.paste(image, (0, 0))
                image = new_image
                draw = ImageDraw.Draw(image)
                height = new_height
                break
                
        for i, line in enumerate(intro_lines):
            draw.text((40, y_pos + i * 25), line, fill=text_color, font=normal_font)
        
        y_pos += len(intro_lines) * 25 + 30
        
        # 处理详细介绍
        if data.get("detail"):
            draw.text((30, y_pos), "详细介绍", fill=header_color, font=header_font)
            y_pos += 40
            
            # 清理HTML标签
            detail = data.get("detail", "")
            detail = re.sub(r'<.*?>', '', detail)  # 移除HTML标签
            detail = re.sub(r'&lt;.*?&gt;', '', detail)  # 移除转义的HTML标签
            
            # 处理详细文本
            detail_lines = self._wrap_text(detail, small_font, width - 80)
            
            # 检查是否需要扩展图片高度
            required_height = y_pos + len(detail_lines) * 22 + 50
            if required_height > height:
                new_image = Image.new('RGB', (width, required_height), bg_color)
                new_image.paste(image, (0, 0))
                image = new_image
                draw = ImageDraw.Draw(image)
                height = required_height
            
            for i, line in enumerate(detail_lines):
                draw.text((40, y_pos + i * 22), line, fill=text_color, font=small_font)
            
            y_pos += len(detail_lines) * 22 + 30
        
        # 底部版权信息
        footer_text = "数据来源: api.52vmy.cn"
        draw.text((width-200, height-30), footer_text, fill=light_color, font=small_font)
        
        # 保存图片
        timestamp = int(datetime.datetime.now().timestamp())
        image_path = os.path.join(self.temp_dir, f"university_{uni_name}_{timestamp}.png")
        image.save(image_path)
        
        return image_path
    
    def _wrap_text(self, text: str, font, max_width: int) -> List[str]:
        """将文本按照最大宽度换行"""
        if not text:
            return ["暂无数据"]
        
        lines = []
        current_line = ""
        
        # 分割字符串为单词（中文处理为单个字符）
        for char in text:
            # 检查添加当前字符后是否会超出最大宽度
            test_line = current_line + char
            line_width = font.getbbox(test_line)[2] if hasattr(font, 'getbbox') else 0
            
            # 如果超出宽度，开始新行
            if line_width > max_width:
                lines.append(current_line)
                current_line = char
            else:
                current_line += char
        
        # 添加最后一行
        if current_line:
            lines.append(current_line)
        
        return lines
    
    async def query_university(self, event: Dict[str, Any], university_name: str) -> bool:
        """查询大学信息"""
        user_id = event.get('user_id')
        group_id = event.get('group_id')
        message_id = event.get('message_id', 0)  # 获取消息ID用于回复
        
        # 构建回复CQ码
        reply_code = f"[CQ:reply,id={message_id}]"
        
        if not university_name:
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"{reply_code}请输入要查询的大学名称"
            )
            return True
        
        logger.info(f"查询大学信息: {university_name}")
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "daxue": university_name
                }
                async with session.get(self.api_url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"查询大学信息失败: {response.status} - {error_text}")
                        await self.bot.send_msg(
                            message_type='group',
                            group_id=group_id,
                            message=f"{reply_code}查询失败，API返回错误: {response.status}"
                        )
                        return True
                    
                    result = await response.json()
                    if result.get("code") != 200:
                        logger.error(f"查询大学信息API返回错误: {result}")
                        await self.bot.send_msg(
                            message_type='group',
                            group_id=group_id,
                            message=f"{reply_code}查询失败，API返回错误: {result.get('msg', '未知错误')}"
                        )
                        return True
                    
                    data = result.get("data", {})
                    if not data:
                        await self.bot.send_msg(
                            message_type='group',
                            group_id=group_id,
                            message=f"{reply_code}未找到与 \"{university_name}\" 相关的大学信息"
                        )
                        return True
                    
                    # 尝试生成图片回复
                    if PIL_AVAILABLE:
                        try:
                            logger.info(f"开始生成大学信息图片: {university_name}")
                            image_path = self.generate_university_image(university_name, data)
                            
                            # 构建图片CQ码
                            image_cq = f"[CQ:image,file=file:///{image_path}]"
                            
                            # 发送图片消息
                            await self.bot.send_msg(
                                message_type='group',
                                group_id=group_id,
                                message=f"{reply_code}为您查询到的大学信息：\n{image_cq}"
                            )
                            return True
                        except Exception as e:
                            logger.error(f"生成大学信息图片失败: {e}", exc_info=True)
                            # 如果图片生成失败，回退到文本格式
                            logger.info("图片生成失败，回退到文本格式")
                    
                    # 如果PIL不可用或图片生成失败，使用文本回复
                    # 格式化大学信息
                    response_message = f"{reply_code}大学信息如下:\n\n"
                    response_message += f"学校名称: {university_name}\n"
                    
                    # 添加基本信息
                    if data.get('founding'):
                        response_message += f"创建时间: {data.get('founding', '未知')}\n"
                    if data.get('area'):
                        response_message += f"占地面积: {data.get('area', '未知')}\n"
                    if data.get('affiliate'):
                        response_message += f"隶属于: {data.get('affiliate', '未知')}\n"
                    if data.get('encode'):
                        response_message += f"学校代码: {data.get('encode', '未知')}\n"
                    if data.get('address'):
                        response_message += f"地址: {data.get('address', '未知')}\n"
                    if data.get('discipline'):
                        response_message += f"国家重点学科: {data.get('discipline', '未知')}\n"
                    if data.get('laboratory'):
                        response_message += f"重点实验室: {data.get('laboratory', '未知')}\n"
                    if data.get('doctor'):
                        response_message += f"博士学科: {data.get('doctor', '未知')}\n"
                    if data.get('master'):
                        response_message += f"硕士学科: {data.get('master', '未知')}\n"
                    
                    # 添加简介
                    if data.get('intro'):
                        intro = data.get('intro', '')
                        # 确保简介不会过长，QQ限制大约为5000字
                        if len(intro) > 800:
                            intro = intro[:800] + "..."
                        response_message += f"\n简介: {intro}\n"
                    
                    # 处理详细介绍
                    if data.get('detail'):
                        # 清理HTML标签
                        detail = data.get('detail', '')
                        detail = re.sub(r'<.*?>', '', detail)  # 移除HTML标签
                        detail = re.sub(r'&lt;.*?&gt;', '', detail)  # 移除转义的HTML标签
                        
                        # 提取重点内容，只保留前500字
                        if len(detail) > 500:
                            detail = detail[:500] + "..."
                            
                        # 确保总消息不会超过QQ限制
                        max_message_length = 4500
                        if len(response_message) + len(detail) > max_message_length:
                            # 如果添加详细介绍会超过限制，则减少保留的字数
                            available_space = max_message_length - len(response_message) - 10  # 保留一些空间给省略号
                            if available_space > 100:  # 至少保留100个字符
                                detail = detail[:available_space] + "..."
                            else:
                                # 如果空间太小，就不添加详细介绍
                                detail = ""
                        
                        if detail:
                            response_message += f"\n详细介绍: {detail}\n"
                    
                    await self.bot.send_msg(
                        message_type='group',
                        group_id=group_id,
                        message=response_message
                    )
                    return True
                    
        except Exception as e:
            logger.error(f"查询大学信息出错: {e}", exc_info=True)
            await self.bot.send_msg(
                message_type='group',
                group_id=group_id,
                message=f"{reply_code}查询出错: {str(e)}"
            )
            return True

# 导出插件类，确保插件加载器能找到它
plugin_class = UniversityInfo 

# 如果直接运行该文件，打印使用说明
if __name__ == "__main__":
    print("大学信息查询插件")
    print("功能：查询国内外大学信息")
    print("使用方法：@机器人 /university [大学名称]")
    print("或：@机器人 /大学 [大学名称]")
    print("例如：@机器人 /university 北京大学")
    print("该插件应当作为LCHBot的插件运行，而非直接运行。") 
