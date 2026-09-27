"""确定性的空间/道具规则校验（不依赖大模型，结果稳定可复现）。

包含三类检查：
  ① 越轴（180° 轴线规则）——多人场景下对“每一对同框角色”分别建立并追踪轴线；
  ② 视线匹配 / 人物站位 ——同框角色朝向、单人镜头的画面方位一致性；
  ③ 道具持有者突变 ——同一道具在相邻出现的镜头中换了手持者且无交代。

服装与动作的语义连续性由大模型判断（见 llm.py 的 check_continuity）。
"""
from collections import Counter
from itertools import combinations
from typing import Optional

from .schemas import Issue, ShotAnalysis

HORIZONTAL = {"left", "right"}
_SIDE_CN = {"left": "左", "right": "右", "center": "中央"}
# 非人物持有的 holder 取值统一视为“环境中”
_ENV_HOLDERS = {"", "环境", "无", "未知", "unknown", "none", "n/a", "na"}


def _name(value: str) -> str:
    return (value or "").strip()


def _side(value: str) -> str:
    value = (value or "").strip().lower()
    return value if value in ("left", "right", "center") else "unknown"


def _char_map(an: ShotAnalysis) -> dict[str, object]:
    return {_name(c.name): c for c in an.characters if _name(c.name)}


def find_pairs(analyses: list[ShotAnalysis]) -> Counter:
    """统计每对角色的同框次数：同框 ≥2 次的角色对视为存在关系轴线。"""
    counter: Counter = Counter()
    for an in analyses:
        names = sorted({_name(c.name) for c in an.characters if _name(c.name)})
        for pair in combinations(names, 2):
            counter[pair] += 1
    return counter


def find_main_pair(analyses: list[ShotAnalysis]) -> Optional[tuple[str, str]]:
    """同框次数最多的角色对（用于前端示意图高亮）。"""
    counter = find_pairs(analyses)
    return counter.most_common(1)[0][0] if counter else None


def check_sequence(analyses: list[ShotAnalysis]) -> list[Issue]:
    issues: list[Issue] = []
    pair_counts = find_pairs(analyses)
    active_pairs = {pair for pair, count in pair_counts.items() if count >= 2}

    # pair -> 上一次两人同框且左右位置明确的镜头下标
    pair_prev: dict[tuple[str, str], int] = {}
    # 角色名 -> (镜头下标, 画面位置)，用于单人镜头方位一致性
    last_known: dict[str, tuple[int, str]] = {}
    crossed_shots: set[int] = set()

    for idx, an in enumerate(analyses):
        chars = _char_map(an)

        # ---------- ① 多人轴线：逐对检查 ----------
        for pair in combinations(sorted(chars), 2):
            a, b = pair
            ca, cb = chars[a], chars[b]
            sa, sb = _side(ca.screen_side), _side(cb.screen_side)
            fa, fb = _side(ca.facing), _side(cb.facing)
            clear_two_shot = sa in HORIZONTAL and sb in HORIZONTAL and sa != sb

            # 视线匹配：两人水平朝向相同 → 无法对视（仅对同框 ≥2 次的稳定对话关系报警）
            if pair in active_pairs and fa in HORIZONTAL and fb in HORIZONTAL and fa == fb:
                issues.append(Issue(
                    type="视线匹配", severity="medium", shots=[idx + 1],
                    problem=(f"镜头{idx + 1}中 {a} 与 {b} 同时朝向画面{_SIDE_CN[fa]}侧，"
                             "两人视线朝向同一方向，无法形成对话/对视的视线匹配。"),
                    suggestion="对话双方的水平朝向应相反（一人朝左、一人朝右）形成视线交接；"
                               "若两人是在共同看画外第三人/物，可忽略此提示。",
                ))

            # 越轴：与“这一对角色”上一次明确同框镜头相比，左右整体对调
            if clear_two_shot and pair in pair_prev:
                pidx = pair_prev[pair]
                prev_chars = _char_map(analyses[pidx])
                psa = _side(prev_chars[a].screen_side)
                psb = _side(prev_chars[b].screen_side)
                if psa in HORIZONTAL and psb in HORIZONTAL and psa != psb \
                        and sa != psa and sb != psb:
                    crossed_shots.add(idx)
                    issues.append(Issue(
                        type="越轴", severity="high", shots=[pidx + 1, idx + 1],
                        problem=(
                            f"镜头{pidx + 1}中 {a} 在画面{_SIDE_CN[psa]}侧、{b} 在画面{_SIDE_CN[psb]}侧；"
                            f"镜头{idx + 1}两人左右位置整体对调（{a}→{_SIDE_CN[sa]}侧、{b}→{_SIDE_CN[sb]}侧），"
                            "机位越过了这对角色的关系轴线，违反 180 度轴线规则，观众会产生方向错乱。"),
                        suggestion=(
                            "把机位放回轴线同一侧，保持两人的画面左右与前一镜头一致；"
                            "若剧情必须越轴，应在两镜之间插入中性镜头（正面镜头、主观镜头或沿轴线运动的镜头）作过渡。"),
                    ))

            if clear_two_shot:
                pair_prev[pair] = idx

        # ---------- ② 单人镜头：画面方位应与已建立的轴线一致 ----------
        for name, ch in chars.items():
            if idx in crossed_shots:
                continue
            side = _side(ch.screen_side)
            if side in HORIZONTAL and name in last_known:
                pidx, pside = last_known[name]
                if pside in HORIZONTAL and side != pside:
                    issues.append(Issue(
                        type="人物站位", severity="medium", shots=[pidx + 1, idx + 1],
                        problem=(f"{name} 在镜头{pidx + 1}位于画面{_SIDE_CN[pside]}侧，"
                                 f"镜头{idx + 1}变为画面{_SIDE_CN[side]}侧，单人镜头的画面方位与已建立的轴线不一致。"),
                        suggestion="同一场景中，同一角色在相邻镜头里应保持在画面同一侧；"
                                   "若角色确实走位换位，需要用走动镜头交代换位过程。",
                    ))
            if side in HORIZONTAL:
                last_known[name] = (idx, side)

    # ---------- ③ 道具持有者突变 ----------
    issues.extend(_check_prop_holders(analyses))
    return issues


def _norm_holder(holder: str) -> str:
    holder = _name(holder)
    return "" if holder.lower() in _ENV_HOLDERS else holder


def _norm_prop_name(name: str) -> str:
    return _name(name).lower()


def _check_prop_holders(analyses: list[ShotAnalysis]) -> list[Issue]:
    """道具名（归一化）-> 依次出现时的 (镜头下标, 持有者) 时间线。"""
    timeline: dict[str, list[tuple[int, str]]] = {}
    for idx, an in enumerate(analyses):
        seen_this_shot: set[str] = set()
        for prop in an.props:
            key = _norm_prop_name(prop.name)
            if not key or key in seen_this_shot:
                continue
            seen_this_shot.add(key)
            timeline.setdefault(key, []).append((idx, _norm_holder(prop.holder)))

    issues: list[Issue] = []
    for key, records in timeline.items():
        for (i1, h1), (i2, h2) in zip(records, records[1:]):
            # 两次出现都在“不同的具名角色”手中，才判定为无交代的持有者突变
            if h1 and h2 and h1 != h2:
                issues.append(Issue(
                    type="道具连续性", severity="medium", shots=[i1 + 1, i2 + 1],
                    problem=(f"道具「{key}」在镜头{i1 + 1}由 {h1} 持有，"
                             f"镜头{i2 + 1}变为由 {h2} 持有，中间没有递接/转移的交代。"),
                    suggestion="补一个两人递接道具的镜头，或让其中一个镜头里道具仍在原持有者手中/放到指定位置。",
                ))
    return issues
