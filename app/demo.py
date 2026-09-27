"""内置示例：一段咖啡馆对话戏（4 个镜头，含 3 人场景），
故意包含越轴、服装矛盾、道具消失、动作断裂等问题，
方便在没有配置 API Key 时直接体验全部检测能力。"""
from .schemas import Issue, ShotAnalysis, ShotIn

_DEMO_PROMPTS = [
    "全景，平视，日景咖啡馆内。角色A坐在桌子左侧、面朝画面右侧，角色B坐在桌子右侧、面朝画面左侧，两人面对面交谈，桌上有两杯咖啡，背景处角色C（服务员）站在画面中央背对镜头在整理吧台。",
    "中景过肩镜头，角色A位于画面左侧、面朝右，穿深色外套，一边说话一边把桌上的咖啡杯端起来，镜头结束时咖啡杯刚举到嘴边。",
    "中景，角色A出现在画面右侧、面朝左，角色B出现在画面左侧、面朝右，角色B穿着一件深色外套，情绪激动，猛地从椅子上站起身。",
    "近景，角色B穿着浅色衬衫，坐在汽车驾驶座上，双手握着方向盘，正在开车，神情紧张。",
]

_DEMO_ANALYSES = [
    ShotAnalysis(
        summary="咖啡馆内角色A与角色B面对面坐着交谈的建立镜头，服务员角色C在后景",
        shot_size="全景", camera_angle="平视",
        characters=[
            {"name": "角色A", "screen_side": "left", "facing": "right", "pose": "坐着",
             "action": "坐在桌前与角色B交谈", "start_state": "坐在椅子上，双手放在桌上",
             "end_state": "仍然坐着，正在说话", "wardrobe": "深色外套、白T恤"},
            {"name": "角色B", "screen_side": "right", "facing": "left", "pose": "坐着",
             "action": "坐在对面听角色A说话", "start_state": "坐在椅子上看着角色A",
             "end_state": "坐着，目光看向角色A", "wardrobe": "浅色衬衫"},
            {"name": "角色C", "screen_side": "center", "facing": "away", "pose": "站立",
             "action": "在吧台背对镜头整理杯具", "start_state": "站在吧台后",
             "end_state": "仍在吧台整理杯具", "wardrobe": "白色服务生围裙"},
        ],
        props=[
            {"name": "咖啡杯", "holder": "环境", "location": "桌上，两杯"},
        ],
        scene_notes="日景、咖啡馆内、暖色光，木桌",
    ),
    ShotAnalysis(
        summary="角色A的过肩中景，端起咖啡杯说话",
        shot_size="中景", camera_angle="平视",
        characters=[
            {"name": "角色A", "screen_side": "left", "facing": "right", "pose": "坐着",
             "action": "说话并端起咖啡杯", "start_state": "双手放在桌上，正在说话",
             "end_state": "咖啡杯举到嘴边，准备喝", "wardrobe": "深色外套、白T恤"},
        ],
        props=[
            {"name": "咖啡杯", "holder": "角色A", "location": "右手，举到嘴边"},
        ],
        scene_notes="咖啡馆内，暖色光",
    ),
    ShotAnalysis(
        summary="机位跳到另一侧的双人中景，角色B猛地站起",
        shot_size="中景", camera_angle="平视",
        characters=[
            {"name": "角色A", "screen_side": "right", "facing": "left", "pose": "坐着",
             "action": "抬头看站起的角色B", "start_state": "坐在椅子上抬头",
             "end_state": "坐在原位，仰头看角色B", "wardrobe": "深色外套、白T恤"},
            {"name": "角色B", "screen_side": "left", "facing": "right", "pose": "从坐姿站起",
             "action": "情绪激动地猛站起身", "start_state": "坐在椅子上，身体前倾",
             "end_state": "刚刚站直，仍在咖啡馆桌边", "wardrobe": "深色外套"},
        ],
        props=[],
        scene_notes="咖啡馆内，桌面已清空，身后是咖啡馆的桌椅",
    ),
    ShotAnalysis(
        summary="角色B已经在汽车驾驶座开车",
        shot_size="近景", camera_angle="平视",
        characters=[
            {"name": "角色B", "screen_side": "center", "facing": "away", "pose": "坐着",
             "action": "驾驶汽车", "start_state": "已经坐在驾驶座，双手握方向盘正在开车",
             "end_state": "继续开车，看向前方", "wardrobe": "浅色衬衫、系着安全带"},
        ],
        props=[],
        scene_notes="日景、汽车内部",
    ),
]

# 以下是“语义类”检查的预置结果（真实使用时由大模型生成）；
# 越轴 / 站位 / 道具持有者突变等空间规则由 rules.py 实时算出。
_DEMO_CONTINUITY_ISSUES = [
    Issue(
        type="服装连续性", severity="medium", shots=[2, 3],
        problem=("角色B 在镜头1、2中穿浅色衬衫，镜头3却变成深色外套，且没有穿外套的动作交代，"
                 "同一时间线内服装颜色发生矛盾；镜头4又变回浅色衬衫。"),
        suggestion="让镜头3、4中的角色B保持浅色衬衫；若剧情需要他穿上外套，需补一个拿起外套穿上的镜头。",
        suggested_prompt="中景，平视。角色B穿浅色衬衫，在画面左侧、面朝右，情绪激动地从椅子上猛地站起身，角色A坐在画面右侧抬头看他，咖啡馆桌面保持原样。",
    ),
    Issue(
        type="道具连续性", severity="medium", shots=[2, 3],
        problem="镜头2中咖啡杯刚被角色A举到嘴边，镜头3桌面已经完全清空、咖啡杯消失，中间没有人收走杯子的交代。",
        suggestion="镜头3的桌面上保留咖啡杯（仍在角色A手中或放回桌上），或加一个角色A把杯子放回桌面的动作。",
        suggested_prompt="中景，平视。角色B在画面左侧猛地站起身，画面右侧的角色A坐在原位，右手刚把咖啡杯放回桌上，桌上仍能看到两杯咖啡。",
    ),
    Issue(
        type="动作衔接", severity="high", shots=[3, 4],
        problem=("镜头3结束时角色B刚刚在咖啡馆桌边站起身，镜头4开场他已经坐在汽车驾驶座上开车，"
                 "中间缺少起身离开、出门、上车等动作与空间过渡，属于明显的动作/空间断裂。"),
        suggestion=("方案一：在镜头3与镜头4之间补过渡镜头（走向门口、上车关门）；"
                    "方案二：把镜头4改成角色B站起动作的直接延续，之后再切到车内。"),
        suggested_prompt="中景，平视，跟拍。角色B从咖啡馆桌边猛地站直后，转身快步走向咖啡馆门口，镜头横向跟随移动，保持角色B位于画面左侧、向画面左侧运动，穿过桌椅推开玻璃门走出画面。",
    ),
]


def build_demo():
    shots = [
        ShotIn(id=f"demo-{i + 1}", kind="text", text=prompt, analysis=_DEMO_ANALYSES[i])
        for i, prompt in enumerate(_DEMO_PROMPTS)
    ]
    return shots, _DEMO_ANALYSES, _DEMO_CONTINUITY_ISSUES
