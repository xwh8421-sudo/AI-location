"""封装对多模态大模型（OpenAI 兼容接口）的调用。

两次调用：
  analyze_shot     —— 每个镜头调用一次：图片/文本 → 结构化 ShotAnalysis
  check_continuity —— 整组镜头调用一次：动作衔接 / 服装连续性 / 道具连续性
                      （站位、越轴等空间规则由 rules.py 确定性校验，不交给模型）
"""
import json
import os
import re
from typing import Optional

from openai import OpenAI

from . import prompts
from .schemas import Issue, ShotAnalysis, ShotIn

# 兼容模型偶尔返回中文枚举值
_SIDE_MAP = {
    "left": "left", "左": "left", "左侧": "left", "左边": "left", "画面左": "left", "l": "left",
    "right": "right", "右": "right", "右侧": "right", "右边": "right", "画面右": "right", "r": "right",
    "center": "center", "中": "center", "中间": "center", "中央": "center", "居中": "center", "c": "center",
}
_FACING_MAP = {
    "left": "left", "向左": "left", "朝左": "left", "面朝左": "left", "脸朝左": "left",
    "right": "right", "向右": "right", "朝右": "right", "面朝右": "right", "脸朝右": "right",
    "toward_camera": "toward_camera", "面向镜头": "toward_camera", "朝向镜头": "toward_camera",
    "正对镜头": "toward_camera", "正面": "toward_camera", "朝前": "toward_camera",
    "away": "away", "背对镜头": "away", "背向镜头": "away", "背对": "away", "向后": "away",
}
_VALID_ISSUE_TYPES = {"动作衔接", "服装连续性", "道具连续性"}


def _map_enum(value: str, table: dict) -> str:
    key = (value or "").strip().lower()
    return table.get(key, "unknown")


def _strip_fences(text: str) -> str:
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    return match.group(1).strip() if match else text.strip()


def resolve_config(api_key: Optional[str], base_url: Optional[str], model: Optional[str]) -> dict:
    return {
        "api_key": (api_key or "").strip() or os.getenv("OPENAI_API_KEY", ""),
        "base_url": (base_url or "").strip() or os.getenv("OPENAI_BASE_URL", ""),
        "model": (model or "").strip() or os.getenv("MODEL_NAME", "gpt-4o"),
    }


def _chat(cfg: dict, messages: list) -> str:
    client = OpenAI(api_key=cfg["api_key"] or "missing", base_url=cfg["base_url"] or None)
    kwargs = {"model": cfg["model"], "messages": messages, "temperature": 0.2}
    try:
        # 多数 OpenAI 兼容服务支持 json_mode；不支持时降级为普通调用
        resp = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
    except Exception:
        resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or "{}"


def _parse_shot(raw: str) -> ShotAnalysis:
    data = json.loads(_strip_fences(raw))
    characters = []
    for ch in data.get("characters", []):
        characters.append({
            "name": str(ch.get("name", "")).strip(),
            "screen_side": _map_enum(str(ch.get("screen_side", "")), _SIDE_MAP),
            "facing": _map_enum(str(ch.get("facing", "")), _FACING_MAP),
            "pose": str(ch.get("pose", "")).strip(),
            "action": str(ch.get("action", "")).strip(),
            "start_state": str(ch.get("start_state", "")).strip(),
            "end_state": str(ch.get("end_state", "")).strip(),
            "wardrobe": str(ch.get("wardrobe", "")).strip(),
        })
    props = []
    for p in data.get("props", []):
        name = str(p.get("name", "")).strip()
        if name:
            props.append({
                "name": name,
                "holder": str(p.get("holder", "")).strip(),
                "location": str(p.get("location", "")).strip(),
            })
    return ShotAnalysis(
        summary=str(data.get("summary", "")).strip(),
        shot_size=str(data.get("shot_size", "")).strip(),
        camera_angle=str(data.get("camera_angle", "")).strip(),
        characters=characters,
        props=props,
        scene_notes=str(data.get("scene_notes", "")).strip(),
    )


def analyze_shot(shot: ShotIn, cfg: dict) -> ShotAnalysis:
    """让多模态模型分析单个镜头（图片或文本 prompt）。"""
    content = [{"type": "text", "text": prompts.build_shot_user(shot.kind, shot.text or shot.caption)}]
    if shot.kind == "image" and shot.image_data_url:
        content.append({"type": "image_url", "image_url": {"url": shot.image_data_url}})
    messages = [
        {"role": "system", "content": prompts.SHOT_SYSTEM},
        {"role": "user", "content": content},
    ]
    return _parse_shot(_chat(cfg, messages))


def check_continuity(shots: list[ShotIn], analyses: list[ShotAnalysis], cfg: dict) -> list[Issue]:
    """让模型判断跨镜头的动作衔接、服装连续性、道具连续性。"""
    lines = []
    for i, an in enumerate(analyses, start=1):
        char_lines = []
        for c in an.characters:
            char_lines.append(
                f"    - {c.name}｜位置={c.screen_side}｜朝向={c.facing}｜姿势={c.pose or '未知'}"
                f"｜服装={c.wardrobe or '未知'}"
                f"｜镜头开始={c.start_state or '未知'}｜镜头结束={c.end_state or '未知'}"
            )
        prop_lines = [
            f"    - {p.name}｜持有者={p.holder or '未知'}｜位置={p.location or '未知'}"
            for p in an.props if p.name
        ]
        block = f"镜头{i}：{an.summary or '（无概述）'}\n" + "\n".join(char_lines)
        if prop_lines:
            block += "\n    道具：\n" + "\n".join(prop_lines)
        if an.scene_notes:
            block += f"\n    场景：{an.scene_notes}"
        lines.append(block)

    raw = _chat(cfg, [
        {"role": "system", "content": prompts.CONTINUITY_SYSTEM},
        {"role": "user", "content": prompts.build_continuity_user(lines)},
    ])
    data = json.loads(_strip_fences(raw))

    issues = []
    for item in data.get("issues", []):
        try:
            shot_ids = [int(x) for x in item.get("shots", []) if int(x) >= 1]
        except (TypeError, ValueError):
            shot_ids = []
        severity = str(item.get("severity", "medium")).lower()
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        issue_type = str(item.get("type", "")).strip()
        if issue_type not in _VALID_ISSUE_TYPES:
            issue_type = "动作衔接"  # 兜底归类
        issues.append(Issue(
            type=issue_type,
            severity=severity,
            shots=shot_ids,
            problem=str(item.get("problem", "")).strip(),
            suggestion=str(item.get("suggestion", "")).strip(),
            suggested_prompt=str(item.get("suggested_prompt", "")).strip(),
        ))
    return issues
