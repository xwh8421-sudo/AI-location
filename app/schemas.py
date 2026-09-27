"""数据模型定义：镜头输入、AI 结构化分析结果、检测出的问题。"""
from typing import List, Optional, Literal

from pydantic import BaseModel, Field


class Character(BaseModel):
    """单个角色在某一镜头中的信息。"""

    name: str = ""
    # 在画面中的位置：left 左 / center 中 / right 右 / unknown 无法判断
    screen_side: str = "unknown"
    # 朝向：left 朝左 / right 朝右 / toward_camera 面向镜头 / away 背对镜头 / unknown
    facing: str = "unknown"
    pose: str = ""          # 姿势，如：站立、坐着、奔跑
    action: str = ""        # 本镜头的主要动作
    start_state: str = ""   # 镜头开始瞬间的动作/状态
    end_state: str = ""     # 镜头结束瞬间的动作/状态
    wardrobe: str = ""      # 稳定的服装与显著外形，如：黑色外套、戴眼镜


class Prop(BaseModel):
    """关键道具在某一镜头中的状态。"""

    name: str = ""          # 道具名，如：咖啡杯、手枪、红色行李箱
    holder: str = ""        # 持有者角色名；不在人物手中填“环境”，无法判断留空
    location: str = ""      # 具体位置，如：桌上、角色A右手、车门旁


class ShotAnalysis(BaseModel):
    """AI 对单个镜头抽取的结构化结果。"""

    summary: str = ""
    shot_size: str = ""     # 景别：远景 / 全景 / 中景 / 近景 / 特写 ...
    camera_angle: str = ""  # 机位角度：平视 / 俯拍 / 仰拍 ...
    characters: List[Character] = Field(default_factory=list)
    props: List[Prop] = Field(default_factory=list)
    scene_notes: str = ""   # 场景等连续性信息（时间、地点、光线）


class ShotIn(BaseModel):
    """一个待检测镜头：可以是视频 prompt 文本，也可以是分镜故事板图片。"""

    id: str
    kind: Literal["text", "image"]
    text: Optional[str] = None            # 文本 prompt，或图片的补充说明
    caption: Optional[str] = None
    image_data_url: Optional[str] = None  # data:image/...;base64,xxx
    analysis: Optional[ShotAnalysis] = None  # 演示模式下使用的预置结果


class Issue(BaseModel):
    """检测出的一个连续性问题。"""

    # 越轴 / 视线匹配 / 人物站位 / 道具连续性 / 动作衔接 / 服装连续性
    type: str
    severity: str           # high / medium / low
    shots: List[int] = Field(default_factory=list)  # 涉及镜头（从 1 开始）
    problem: str = ""
    suggestion: str = ""
    suggested_prompt: str = ""  # 可直接复制使用的修正 prompt


class AnalyzeRequest(BaseModel):
    shots: List[ShotIn]
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
