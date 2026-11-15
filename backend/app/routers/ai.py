"""AI 接口：写作助手、搭子匹配、校园问答（SSE 流式）、Agent 工具调用。"""
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai import agent, service
from ..ai import engine as ai_engine
from ..ai.engine import chunk_text
from ..ai.knowledge import CATEGORY_MAP
from ..config import settings
from ..db import SessionLocal, get_db
from ..deps import get_current_user, get_optional_user
from ..models import AiLog, Post, User
from ..schemas import AiTextIn, AiWriteOut, ChatIn, MatchOut
from ..serializers import user_out

router = APIRouter(prefix="/api/ai", tags=["AI"])


def _log(db: Session, user_id: int, kind: str, text: str, mode: str, chars: int) -> None:
    db.add(
        AiLog(
            user_id=user_id,
            kind=kind,
            input=text[:200],
            mode=mode,
            chars=chars,
        )
    )
    db.commit()


@router.post("/write", response_model=AiWriteOut)
def ai_write(
    body: AiTextIn,
    db: Session = Depends(get_db),
    current: User | None = Depends(get_optional_user),
):
    text = body.text.strip()
    result = service.write(text)
    _log(db, current.id if current else 0, "write", text, result["mode"], len(result["content"]))
    return result


@router.post("/match", response_model=MatchOut)
def ai_match(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    users = db.scalars(select(User)).all()
    payload = [
        {
            "id": item.id,
            "nickname": item.nickname or item.username,
            "avatar": item.avatar,
            "color": item.color,
            "major": item.major,
            "grade": item.grade,
            "bio": item.bio,
            "tags": item.tags or [],
        }
        for item in users
    ]
    me = {
        "id": user.id,
        "tags": user.tags or [],
        "bio": user.bio or "",
        "major": user.major or "",
    }
    result = service.match(me, payload)

    matches = []
    for item in result["matches"]:
        full = db.get(User, item["user"]["id"])
        matches.append(
            {
                "user": user_out(full),
                "score": item["score"],
                "reason": item["reason"],
            }
        )

    _log(db, user.id, "match", "、".join(me["tags"]), result["mode"], 0)
    return {"matches": matches, "message": result["message"], "mode": result["mode"]}


async def _stream_answer(message: str, history: list[dict] | None = None):
    """SSE 生成器：先推送 meta，再逐块推送 delta，最后 done。"""
    result = await asyncio.to_thread(service.answer, message, history)

    # 记录调用（独立会话，避免请求级会话在流式期间关闭）
    try:
        with SessionLocal() as log_db:
            log_db.add(
                AiLog(kind="chat", input=message[:200], mode=result["mode"], chars=len(result["answer"]))
            )
            log_db.commit()
    except Exception:  # noqa: BLE001 - 记录失败不影响回答
        pass

    meta = {
        "mode": result["mode"],
        "kind": result.get("kind", "chat"),
        "confidence": result.get("confidence"),
        "sources": result.get("sources", []),
        "topic": result.get("topic", ""),
        "suggestions": result.get("suggestions", []),
    }
    yield "event: meta\ndata: " + json.dumps(meta, ensure_ascii=False) + "\n\n"

    for chunk in chunk_text(result["answer"]):
        yield "event: delta\ndata: " + json.dumps({"text": chunk}, ensure_ascii=False) + "\n\n"
        await asyncio.sleep(0.016)

    yield "event: done\ndata: " + json.dumps({"length": len(result["answer"])}) + "\n\n"


@router.post("/chat")
def ai_chat(body: ChatIn):
    history = [{"role": turn.role, "content": turn.content} for turn in body.history]
    return StreamingResponse(
        _stream_answer(body.message.strip(), history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Agent：模型（或本地规则）先规划，再调用工具，最后组织回答
# ---------------------------------------------------------------------------
def _build_box(db: Session, viewer: User | None) -> agent.Toolbox:
    """把数据库查询包成 Agent 的工具。"""

    def post_search(query: str, category: str | None, limit: int) -> list[dict]:
        keyword = (query or "").strip()
        if not keyword:
            return []
        stmt = select(Post)
        if category in CATEGORY_MAP:
            stmt = stmt.where(Post.category == category)
        rows = db.scalars(stmt.order_by(Post.created_at.desc()).limit(300)).all()

        # 用二元词重合度打分：比 LIKE 整句更耐口语（「社区里有人出显示器吗」也能命中）
        grams = [term for term, weight in ai_engine.tokenize(keyword) if weight >= 1.0 and len(term) >= 2]
        scored = []
        for post in rows:
            haystack = post.title + " " + post.content
            score = sum(1 for gram in grams if gram in haystack)
            if score >= 2:
                scored.append((score, post))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        result = []
        for _, post in scored[:limit]:
            author = db.get(User, post.author_id)
            result.append(
                {
                    "id": post.id,
                    "title": post.title,
                    "author": author.nickname if author else "同学",
                    "summary": post.content[:80],
                }
            )
        return result

    def user_search(_: int) -> list[dict]:
        return [
            {
                "id": item.id,
                "nickname": item.nickname or item.username,
                "major": item.major,
                "grade": item.grade,
                "bio": item.bio,
                "tags": item.tags or [],
            }
            for item in db.scalars(select(User)).all()
        ]

    me = None
    if viewer is not None:
        me = {
            "id": viewer.id,
            "tags": viewer.tags or [],
            "bio": viewer.bio or "",
            "major": viewer.major or "",
        }
    return agent.Toolbox(me=me, post_search=post_search, user_search=user_search)


def _suggestions(kind: str) -> list[str]:
    if kind == "draft":
        return ["帮我改得口语一点", "这条能发到哪个板块", "再换个标题"]
    return ["图书馆几点关门？", "帮我找一起自习的搭子", "社区里有人出二手显示器吗"]


async def _stream_agent(message: str, history: list[dict], viewer_id: int | None):
    """SSE：先推 step（思考 / 工具调用），再推 meta、delta、done。"""
    with SessionLocal() as db:
        viewer = db.get(User, viewer_id) if viewer_id else None
        box = _build_box(db, viewer)
        try:
            steps, answer, mode = await asyncio.to_thread(agent.plan, message, box, history)
        except Exception:  # noqa: BLE001 - Agent 出错也要给出人话提示
            steps, answer, mode = [], "这次没想明白，你换个说法再问一次？", "local"

        for step in steps:
            yield "event: step\ndata: " + json.dumps(step, ensure_ascii=False) + "\n\n"
            await asyncio.sleep(0.06)

        meta = {
            "mode": mode,
            "kind": "agent",
            "sources": agent.source_list(steps),
            "confidence": None,
            "tools": [step["name"] for step in steps if step.get("type") == "tool"],
            "suggestions": _suggestions("draft" if "draft_post" in [s.get("name") for s in steps] else "chat"),
        }
        yield "event: meta\ndata: " + json.dumps(meta, ensure_ascii=False) + "\n\n"

        try:
            with SessionLocal() as log_db:
                log_db.add(
                    AiLog(
                        user_id=viewer_id or 0,
                        kind="agent",
                        input=message[:200],
                        mode=mode,
                        chars=len(answer),
                    )
                )
                log_db.commit()
        except Exception:  # noqa: BLE001
            pass

        for chunk in chunk_text(answer):
            yield "event: delta\ndata: " + json.dumps({"text": chunk}, ensure_ascii=False) + "\n\n"
            await asyncio.sleep(0.012)

        yield "event: done\ndata: " + json.dumps({"length": len(answer), "steps": len(steps)}) + "\n\n"


@router.post("/agent")
def ai_agent(body: ChatIn, current: User | None = Depends(get_optional_user)):
    history = [{"role": turn.role, "content": turn.content} for turn in body.history]
    return StreamingResponse(
        _stream_agent(body.message.strip(), history, current.id if current else None),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/logs")
def ai_logs(db: Session = Depends(get_db)):
    logs = db.scalars(select(AiLog).order_by(AiLog.id.desc()).limit(20)).all()
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "input": item.input,
            "mode": item.mode,
            "chars": item.chars,
            "created_at": item.created_at,
        }
        for item in logs
    ]


@router.get("/status")
def ai_status():
    return {**service.ai_status(), "disclaimer": settings.ai_disclaimer}
