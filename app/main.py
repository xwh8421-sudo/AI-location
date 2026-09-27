"""FastAPI 入口：提供前端页面与检测接口。"""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import demo as demo_data
from . import llm, rules
from .schemas import AnalyzeRequest, ShotIn

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

# 自动读取项目根目录下的 .env（已存在的系统环境变量优先）
load_dotenv(BASE_DIR / ".env", override=False)

app = FastAPI(title="AI-location 分镜连续性检测")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache_static(request, call_next):
    """本地工具：禁用浏览器缓存，保证改完前端刷新即生效。"""
    resp = await call_next(request)
    if request.url.path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _shot_out(shot: ShotIn):
    return {
        "id": shot.id,
        "kind": shot.kind,
        "text": shot.text,
        "caption": shot.caption,
        "analysis": shot.analysis.model_dump() if shot.analysis else None,
    }


def _build_response(shots: list[ShotIn], analyses: list, extra_issues: list | None = None):
    issues = rules.check_sequence(analyses)
    if extra_issues:
        issues.extend(extra_issues)
    issues.sort(key=lambda x: (_SEVERITY_ORDER.get(x.severity, 9), x.shots[0] if x.shots else 0))
    pair = rules.find_main_pair(analyses)
    return {
        "shots": [_shot_out(s) for s in shots],
        "issues": [i.model_dump() for i in issues],
        "main_pair": list(pair) if pair else None,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not req.shots:
        raise HTTPException(status_code=400, detail="请至少添加一个镜头")

    cfg = llm.resolve_config(req.api_key, req.base_url, req.model)
    need_llm = any(s.analysis is None for s in req.shots)
    if need_llm and not cfg["api_key"]:
        raise HTTPException(
            status_code=400,
            detail="尚未配置 API Key。请点右上角“API 设置”填写多模态模型的 Key，或先点“载入示例”体验演示。",
        )

    analyses = []
    for shot in req.shots:
        if shot.analysis is None:
            try:
                shot.analysis = llm.analyze_shot(shot, cfg)
            except Exception as exc:  # 模型调用失败时给出可读的错误
                raise HTTPException(
                    status_code=502,
                    detail=f"镜头分析失败（模型：{cfg['model']}）：{exc}",
                )
        analyses.append(shot.analysis)

    continuity_issues = []
    if cfg["api_key"]:
        try:
            continuity_issues = llm.check_continuity(req.shots, analyses, cfg)
        except Exception:
            # 站位/越轴结果仍可返回；语义连续性检查失败不阻塞主流程
            continuity_issues = []

    return _build_response(req.shots, analyses, continuity_issues)


@app.post("/api/demo")
def run_demo():
    shots, analyses, continuity_issues = demo_data.build_demo()
    return _build_response(shots, analyses, continuity_issues)
