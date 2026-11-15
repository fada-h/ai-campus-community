"""AI Agent：把一次提问拆成「想一下 → 查工具 → 再说人话」。

工具清单：
    查校园资料   知识库检索（RAG，带来源与置信度）
    搜社区帖子   按关键词在帖子里找相关讨论
    找搭子       按兴趣标签匹配同学
    写帖子草稿   标题 / 正文 / 标签 / 违规检测
    查敏感词     发帖前的合规检查

有 DeepSeek Key 时走 Function Calling，模型自己决定调哪个工具；
没有 Key 或请求失败时走本地启发式规划，同样真实调用这些工具，
所以断网也能演示完整的 Agent 流程。
"""
from __future__ import annotations

import json
import re
from typing import Callable

from . import engine, service
from .knowledge import CATEGORY_MAP

# 知识库相似度低于这个值就当作「没查到」，避免硬答无关问题
KNOWLEDGE_MIN_CONFIDENCE = 0.45

# ---------------------------------------------------------------------------
# 工具定义（OpenAI / DeepSeek 兼容的 function calling schema）
# ---------------------------------------------------------------------------
TOOL_SPECS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "查校园事务资料：图书馆、食堂、教务、宿舍、校园卡、奖学金、场馆、报修等。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "要查的问题"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_posts",
            "description": "在社区帖子里按关键词找相关讨论，返回标题与摘要。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "关键词，比如 自习、二手、吉他"},
                    "category": {
                        "type": "string",
                        "enum": ["study", "club", "market", "lost", "life"],
                        "description": "可选，限定板块",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "match_buddies",
            "description": "根据当前用户的兴趣标签与简介，找兴趣相投的同学。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_post",
            "description": "把用户口语化的描述变成一条可发布的帖子草稿：标题、正文、分类、标签、违规检测。",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "用户的原始描述"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_safety",
            "description": "检查一段文字里有没有社区不允许的词。",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "要检查的文字"}},
                "required": ["text"],
            },
        },
    },
]


class Toolbox:
    """工具的真实实现。每个工具返回 {summary, data}，summary 用于展示调用轨迹。"""

    def __init__(
        self,
        me: dict | None = None,
        post_search: Callable[[str, str | None, int], list[dict]] | None = None,
        user_search: Callable[[int], list[dict]] | None = None,
    ) -> None:
        self.me = me or {}
        self._post_search = post_search
        self._user_search = user_search

    # -- 工具实现 ---------------------------------------------------------
    def search_knowledge(self, query: str, min_confidence: float = KNOWLEDGE_MIN_CONFIDENCE) -> dict:
        result = engine.answer_question(query)
        confidence = float(result.get("confidence") or 0)
        if result["kind"] != "knowledge" or confidence < min_confidence:
            return {"summary": "知识库里对不上，别硬答。", "data": None}
        return {
            "summary": f"命中「{result.get('topic', '校园资料')}」（{round(confidence * 100)}%）",
            "data": {
                "topic": result.get("topic", ""),
                "answer": result["answer"],
                "sources": result["sources"],
                "confidence": confidence,
            },
        }

    def search_posts(self, query: str, category: str | None = None) -> dict:
        rows = self._post_search(query, category, 4) if self._post_search else []
        if not rows:
            return {"summary": "帖子里也没翻到相关的。", "data": None}
        return {"summary": f"翻到 {len(rows)} 条相关帖子", "data": rows}

    def match_buddies(self) -> dict:
        if not self.me or not self._user_search:
            return {"summary": "还没登录，匹配不了。", "data": None}
        result = engine.match_buddies(self.me, self._user_search(self.me["id"]))
        if not result["matches"]:
            return {"summary": "没找到兴趣接近的同学。", "data": None}
        picks = [
            {
                "nickname": item["user"]["nickname"],
                "score": item["score"],
                "reason": item["reason"],
            }
            for item in result["matches"]
        ]
        return {"summary": f"挑了 {len(picks)} 位兴趣接近的同学", "data": picks}

    def draft_post(self, text: str) -> dict:
        cleaned = clean_draft_input(text)
        result = engine.writing_assistant(cleaned or text)
        category = CATEGORY_MAP.get(result["category"], CATEGORY_MAP["life"])
        # 只用命中的领域词当标签，避免出现「出二」「手耳」这种半截词
        tags = [tag for tag in result["tags"] if tag in engine.DOMAIN_TERMS][:4]
        for fallback in ("校园", "互助"):
            if len(tags) < 2 and fallback not in tags:
                tags.append(fallback)
        return {
            "summary": f"起了个草稿，建议发「{category['name']}」",
            "data": {
                "title": result["title"],
                "content": result["content"],
                "category_name": category["name"],
                "tags": tags,
                "safe": result["safety"]["safe"],
                "issues": result["issues"],
                "summary": result["summary"],
                "too_short": len((cleaned or "").strip()) < 4,
            },
        }

    def check_safety(self, text: str) -> dict:
        result = engine.safety_check(text)
        return {
            "summary": "没发现违规词" if result["safe"] else "有违规词：" + "、".join(result["hits"]),
            "data": result,
        }

    def call(self, name: str, arguments: dict) -> dict:
        if name == "search_knowledge":
            return self.search_knowledge(str(arguments.get("query") or ""))
        if name == "search_posts":
            return self.search_posts(str(arguments.get("query") or ""), arguments.get("category") or None)
        if name == "match_buddies":
            return self.match_buddies()
        if name == "draft_post":
            return self.draft_post(str(arguments.get("text") or ""))
        if name == "check_safety":
            return self.check_safety(str(arguments.get("text") or ""))
        return {"summary": f"没有这个工具：{name}", "data": None}


# ---------------------------------------------------------------------------
# 本地规划：没有云端模型时的兜底，规则简单但真的会调工具
# ---------------------------------------------------------------------------
MATCH_WORDS = ("搭子", "组队", "队友", "同好", "一起自习", "一起跑", "一起打球", "找人一起")
DRAFT_WORDS = ("发帖", "怎么发", "帮我写", "写一条", "写个", "起个标题", "润色", "改得", "改一下")
SELL_HINTS = ("出", "卖", "求购", "转让", "闲置", "拼单", "收一个")
POST_WORDS = ("有没有", "谁有", "谁在", "推荐", "帖子", "社区里", "有人")

INSTRUCTION_HEAD = re.compile(r"^(帮我|请|麻烦|能不能|可以)?\s*(写|发|拟|润色|改|起)(一条|一篇|一个|一下|下)?\s*")
INSTRUCTION_TAIL = re.compile(r"(的)?(帖子|文案|内容|标题|文字|草稿)$")


def clean_draft_input(text: str) -> str:
    """把「帮我写一条出二手耳机的帖子」里的指令词去掉，只留内容。"""
    cleaned = INSTRUCTION_HEAD.sub("", text.strip())
    cleaned = INSTRUCTION_TAIL.sub("", cleaned.strip())
    return cleaned.strip(" ：:，,。.;；、")


def _tool_step(name: str, tool_input: str, result: dict) -> dict:
    return {
        "type": "tool",
        "name": name,
        "input": tool_input,
        "result": result["summary"],
        "ok": result.get("data") is not None,
    }


def _plan_locally(box: Toolbox, question: str) -> tuple[list[dict], str]:
    """返回 (工具调用轨迹, 最终回答)。"""
    steps: list[dict] = [{"type": "think", "text": "先看这句话想让我做什么。"}]
    text = question.strip()

    # 0) 打招呼、闲聊这类，不用查东西，直接接话
    chat = engine.answer_question(text)
    if chat["kind"] in ("greeting", "chat") and len(text) <= 12:
        return steps, chat["answer"]

    safety = box.check_safety(text)
    steps.append(_tool_step("check_safety", "这句话", safety))
    if not safety["data"]["safe"]:
        return steps, "这句话里有社区不让发的词，我帮不了。改一下再问我。"

    # 「怎么发帖」这类是问流程，不是要稿子
    if re.search(r"(怎么|如何|怎样|新手).{0,8}(发帖|发一条|写帖|润色|发布|用这个)", text):
        return steps, (
            "点右上角「发帖」，正文写完点一下「AI 帮我润色」，它会给你标题、分类和标签；"
            "不满意就接着改，确认没问题再点「发布帖子」。"
        )

    # 1) 写帖子：明确说要写，或者直接抛来一段二手/求购描述
    wants_draft = any(word in text for word in DRAFT_WORDS)
    wants_draft = wants_draft or (
        len(text) >= 12
        and any(word in text for word in SELL_HINTS)
        and "吗" not in text
        and "谁" not in text
    )
    if wants_draft:
        draft_box = box.draft_post(text)
        steps.append(_tool_step("draft_post", clean_draft_input(text)[:24] or text[:24], draft_box))
        draft = draft_box["data"]
        if draft["too_short"]:
            return steps, (
                "光看这句还写不出来。你补两句：想做什么、什么时候、在哪儿、希望对方什么样，"
                "我再帮你捋顺。"
            )
        tail = "" if len(clean_draft_input(text)) >= 20 else " 字少了点，能再补一句更具体的，回复率会高很多。"
        return steps, (
            "按你说的写了一版，你看看还要不要改：\n\n"
            f"标题：{draft['title']}\n\n{draft['content']}\n\n"
            f"建议发「{draft['category_name']}」，标签用 {'、'.join(draft['tags'])}。{tail}"
        )

    # 2) 找搭子
    if any(word in text for word in MATCH_WORDS):
        match_box = box.match_buddies()
        steps.append(_tool_step("match_buddies", "我的兴趣标签", match_box))
        if match_box["data"]:
            lines = [
                f"{item['nickname']}：{item['reason']}（{round(item['score'] * 100)}%）"
                for item in match_box["data"]
            ]
            return steps, "给你找了这几个，看看合不合眼缘：\n" + "\n".join(lines) + "\n\n想聊就去 TA 主页。"
        return steps, match_box["summary"] + " 把简介和标签补具体点再试试。"

    # 3) 查校园资料
    knowledge = box.search_knowledge(text)
    steps.append(_tool_step("search_knowledge", text[:24], knowledge))
    if knowledge["data"]:
        return steps, knowledge["data"]["answer"]

    # 4) 翻社区帖子
    posts = box.search_posts(text)
    steps.append(_tool_step("search_posts", text[:24], posts))
    if posts["data"]:
        lines = [f"《{item['title']}》— {item['author']}" for item in posts["data"]]
        return steps, "社区里聊过类似的，你可以去看看：\n" + "\n".join(lines)

    # 5) 闲聊兜底
    chat = engine.answer_question(text)
    if chat["kind"] in ("chat", "greeting"):
        return steps, chat["answer"]
    if any(word in text for word in POST_WORDS):
        return steps, "社区里暂时没人聊这个。要不你发一条？写两句发出去，看到的人会回你。"
    return steps, "这个我还真不确定。换个说法再问一次？或者发到「学习互助」，同学比我靠谱。"


# ---------------------------------------------------------------------------
# 云端规划：Function Calling 循环（失败自动回落到本地规划）
# ---------------------------------------------------------------------------
AGENT_PROMPT = (
    "你是「AI校园社区」的 AI 助手，像个热心的学长。说话短、口语化，不端着。\n"
    "用户问校园事务、找同学、写帖子时，先调用工具拿资料，再基于工具结果回答。\n"
    "规则：\n"
    "1. 涉及时间、地点、金额、办理流程，必须以工具返回的资料为准，不要自己编；\n"
    "2. 工具没查到就直说「这个我不确定」，并建议去社区发帖问同学；\n"
    "3. 回答控制在 3 句话以内，除非用户要详细；\n"
    "4. 不要提「工具」「函数」「检索」这些词，像人一样说话；\n"
    "5. 不要用「首先」「其次」「总之」，也别列一二三四。\n"
)


def _json(text: str) -> dict:
    try:
        data = json.loads(text or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _plan_with_model(box: Toolbox, question: str, history: list[dict]) -> tuple[list[dict], str]:
    messages: list[dict] = [{"role": "system", "content": AGENT_PROMPT}]
    for turn in history[-6:]:
        role = turn.get("role")
        content = str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:400]})
    messages.append({"role": "user", "content": question})

    steps: list[dict] = [{"type": "think", "text": "想一下该查什么。"}]
    for _ in range(3):
        message = service.chat_message(messages, tools=TOOL_SPECS, temperature=0.4, max_tokens=600)
        if not message:
            raise RuntimeError("模型无响应")

        calls = message.get("tool_calls") or []
        if not calls:
            answer = (message.get("content") or "").strip()
            if not answer:
                raise RuntimeError("模型没有给出内容")
            return steps, answer

        messages.append(message)
        for call in calls:
            name = call["function"]["name"]
            arguments = _json(call["function"].get("arguments"))
            result = box.call(name, arguments)
            steps.append(_tool_step(name, json.dumps(arguments, ensure_ascii=False)[:60], result))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "content": json.dumps(result["data"], ensure_ascii=False)[:1200],
                }
            )

    raise RuntimeError("工具调用轮次超限")


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def plan(question: str, box: Toolbox, history: list[dict] | None = None) -> tuple[list[dict], str, str]:
    """返回 (步骤, 回答, 模式)。优先云端，失败回落本地。"""
    history = history or []
    if service.settings.deepseek_api_key:
        try:
            steps, answer = _plan_with_model(box, question, history)
            return steps, answer, "cloud"
        except Exception:  # noqa: BLE001 - 云端失败静默回落，保证演示不断
            pass

    steps, answer = _plan_locally(box, question)
    return steps, answer, "local"


TOOL_LABELS = {
    "search_knowledge": "校园知识库",
    "search_posts": "社区帖子",
    "match_buddies": "兴趣标签",
    "draft_post": "帖子草稿",
    "check_safety": "合规检查",
}


def source_list(steps: list[dict]) -> list[str]:
    """把工具轨迹里查到东西的来源抽出来，挂在回答下面。"""
    sources: list[str] = []
    for step in steps:
        if not step.get("ok"):
            continue
        label = TOOL_LABELS.get(step.get("name", ""))
        if label and label not in sources and step.get("name") != "check_safety":
            sources.append(label)
    return sources
