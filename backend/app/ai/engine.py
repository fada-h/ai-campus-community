"""本地 AI 引擎（纯 Python，无第三方依赖）。

提供三种能力：
  1. 校园问答：TF-IDF + 余弦相似度检索知识库（RAG 思路）
  2. 发帖助手：分类 / 标签 / 润色 / 摘要 / 安全检测
  3. 搭子匹配：兴趣标签 Jaccard + 文本相似度
"""
import math
import re
from collections import Counter

from .knowledge import CATEGORY_MAP, KNOWLEDGE, SECURITY_WORDS

STOP_WORDS = {
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "那", "这个", "那个", "什么", "怎么", "可以", "我们", "他们",
    "但是", "因为", "所以", "如果", "然后", "现在", "今天",
    "the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "on", "with",
}

GENERIC_BIGRAMS = {
    "想找", "找人", "一起", "有没", "没有", "想和", "和的", "我的", "你的", "他的",
    "这个", "那个", "什么", "怎么", "可以", "我们", "你们", "他们", "就是", "觉得",
    "知道", "如果", "因为", "所以", "但是", "然后", "现在", "今天", "明天", "昨天",
    "时候", "一个", "一些", "不是", "还是", "已经", "正在", "希望", "想要", "需要",
    "比较", "非常", "特别", "真的", "应该", "可能", "或者", "而且", "不过", "虽然",
    "于是", "因此", "这样", "那样", "这里", "那里", "上面", "下面", "东西", "事情",
}

DOMAIN_TERMS = [
    "考研", "保研", "自习", "图书馆", "食堂", "宿舍", "社团", "志愿", "公益",
    "摄影", "篮球", "羽毛球", "跑步", "健身", "咖啡", "读书", "写作", "吉他",
    "编程", "前端", "后端", "算法", "竞赛", "蓝桥杯", "实习", "校招", "简历",
    "快递", "失物", "二手", "显示器", "教材", "约拍", "骑行", "游戏", "设计",
    "插画", "英语", "翻译", "留学", "实验室", "嵌入式", "烘焙", "招新", "组队",
]

CJK = re.compile(r"[\u4e00-\u9fa5]")


def normalize(text: str) -> str:
    """保留中英文数字，其余替换为空格并转小写。"""
    return re.sub(r"[^\u4e00-\u9fa5a-z0-9]+", " ", str(text or "").lower()).strip()


def tokenize(text: str) -> list[tuple[str, float]]:
    """中文 bigram（权重 1）+ 单字（权重 0.5），英文数字整词。"""
    tokens: list[tuple[str, float]] = []
    for run in normalize(text).split():
        if CJK.search(run):
            chars = list(run)
            for i, ch in enumerate(chars):
                if ch in STOP_WORDS:
                    continue
                tokens.append((ch, 0.5))
                if i + 1 < len(chars):
                    bigram = ch + chars[i + 1]
                    if bigram not in STOP_WORDS:
                        tokens.append((bigram, 1.0))
        else:
            tokens.append((run, 1.0))
    return tokens


def _vector(tokens: list[tuple[str, float]], idf: dict[str, float]) -> dict[str, float]:
    vec: dict[str, float] = {}
    for term, weight in tokens:
        vec[term] = vec.get(term, 0.0) + weight * idf.get(term, 1.0)
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: v / norm for k, v in vec.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(value * b.get(term, 0.0) for term, value in a.items())


# ---------------- 知识库索引（模块加载时构建一次） ----------------
_DOCS = [
    {
        "item": item,
        "tokens": tokenize(
            item["topic"] + " " + " ".join(item["keywords"]) + " " + item["content"]
        ),
    }
    for item in KNOWLEDGE
]

_DF: Counter = Counter()
for _doc in _DOCS:
    _DF.update(set(term for term, _ in _doc["tokens"]))

_Idf: dict[str, float] = {
    term: math.log((len(_DOCS) + 1) / (df + 0.5)) + 1.0 for term, df in _DF.items()
}

for _doc in _DOCS:
    _doc["vector"] = _vector(_doc["tokens"], _Idf)


# ---------------- 1. 校园问答 ----------------
# 短句闲聊：不查知识库，也别硬拉回校园话题
CHAT_PATTERNS = [
    (r"(谢谢|多谢|感谢|thx|thanks)", "不客气，还有事随时问。"),
    (r"(累|烦|emo|难受|焦虑|压力|崩溃|不开心)", "听着今天不太好过。要不先把手上的事放一放，去操场走两圈？"
     "实在扛不住，心理中心在大学生活动中心 3 楼，免费，也保密。"),
    (r"(晚安|先睡|睡了)", "晚安，早点睡，明天的事明天再说。"),
    (r"(哈哈|笑死|太绝了|离谱)", "哈哈，那确实。还有别的想问的吗？"),
    (r"(你真|好厉害|牛啊|太强了)", "过奖了，我就是记性好一点。"),
]


def answer_question(question: str) -> dict:
    text = str(question or "").strip()
    if not text:
        return {
            "answer": "想问什么直接说就行。图书馆几点关门、校园卡丢了怎么办，这种都问我。",
            "sources": [],
            "confidence": 0.0,
            "kind": "empty",
            "suggestions": ["图书馆开放时间", "校园卡挂失", "奖学金怎么申请"],
        }

    if re.match(r"^(你好|hi|hello|嗨|在吗)", text, re.I):
        return {
            "answer": "在的。校园里的事、帖子怎么写顺、想找搭子，都能问我。你先说，我听着。",
            "sources": [],
            "confidence": 1.0,
            "kind": "greeting",
            "suggestions": ["图书馆几点关门？", "帮我找一起自习的搭子", "校园网连不上怎么办"],
        }

    if re.search(r"(你是谁|能做什么|有什么功能|介绍一下自己)", text):
        return {
            "answer": "我是这个社区的 AI 助手，平时干三件事：\n"
            "查校园里的事，图书馆、食堂、教务、宿舍、奖学金这些，大概 26 类；\n"
            "帮你改帖子，起标题、挑分类和标签、看看有没有说不得的词；\n"
            "按兴趣给你找搭子，匹配理由我也会写清楚。\n"
            "不用联网也能用，就是答得没那么灵活。",
            "sources": ["AI 能力说明"],
            "confidence": 1.0,
            "kind": "capability",
            "suggestions": ["图书馆开放时间", "怎么申请奖学金", "帮我找考研搭子"],
        }

    if len(text) <= 12:
        for pattern, reply in CHAT_PATTERNS:
            if re.search(pattern, text, re.I):
                return {
                    "answer": reply,
                    "sources": [],
                    "confidence": 0.9,
                    "kind": "chat",
                    "suggestions": ["图书馆几点关门？", "校园卡丢了怎么办？", "帮我找一起自习的搭子"],
                }

    query = _vector(tokenize(text), _Idf)
    ranked = sorted(
        ((doc, _cosine(query, doc["vector"])) for doc in _DOCS),
        key=lambda pair: pair[1],
        reverse=True,
    )
    best_doc, best_score = ranked[0]

    if best_score < 0.06:
        return {
            "answer": "这个我还真不确定，知识库里没写。你换个说法再问一次？"
            "或者直接发到「学习互助」板块，同学比我靠谱。",
            "sources": [],
            "confidence": round(best_score, 3),
            "kind": "no-answer",
            "suggestions": ["图书馆开放时间", "校园卡怎么补办", "奖学金申请时间"],
        }

    related = [doc["item"] for doc, score in ranked[1:2] if score > best_score * 0.6]
    return {
        "answer": best_doc["item"]["content"],
        "sources": [best_doc["item"]["source"]] + [item["source"] for item in related],
        "confidence": round(min(0.99, best_score * 1.6 + 0.15), 3),
        "kind": "knowledge",
        "topic": best_doc["item"]["topic"],
        "suggestions": [item["topic"] for item in related[:2]],
    }


# ---------------- 2. 发帖助手 ----------------
CATEGORY_RULES = {
    "study": ["作业", "高数", "期末", "复习", "题", "笔记", "组队", "竞赛", "考研", "保研",
              "实验室", "课程", "自习", "论文", "答辩"],
    "club": ["社团", "招新", "活动", "演出", "比赛", "志愿", "讲座", "晚会", "报名", "乐队", "篮球赛"],
    "market": ["出", "收", "二手", "闲置", "转", "便宜", "卖", "买", "价", "甩", "求购", "九成新"],
    "lost": ["丢", "捡到", "失物", "招领", "校园卡", "钥匙", "钱包", "身份证", "耳机", "水杯"],
    "life": ["食堂", "宿舍", "天气", "吐槽", "推荐", "求助", "表白", "校园", "饭", "快递", "心情", "emo"],
}


def classify(text: str) -> dict:
    normalized = normalize(text)
    scores = {}
    for cid, words in CATEGORY_RULES.items():
        scores[cid] = sum(1 for word in words if normalize(word) in normalized)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(score for _, score in ranked)
    cid, score = ranked[0]
    return {
        "category": cid if score > 0 else "life",
        "confidence": round(score / total, 2) if total > 0 else 0.3,
        "scores": scores,
    }


def extract_tags(text: str, limit: int = 5) -> list[str]:
    normalized = normalize(text)
    found: list[str] = []
    for term in DOMAIN_TERMS:
        if normalize(term) in normalized and term not in found:
            found.append(term)

    counter = Counter(
        term for term, weight in tokenize(text) if weight == 1.0 and term not in STOP_WORDS
    )
    merged = list(found)
    for term, _ in counter.most_common():
        if len(merged) >= limit:
            break
        if term in GENERIC_BIGRAMS:
            continue
        if any(term in item or item in term for item in merged):
            continue
        merged.append(term)
    return merged[:limit]


def summarize(text: str, max_length: int = 90) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?；;])", str(text or "")) if s.strip()]
    if not sentences:
        return ""
    summary = sentences[0]
    if len(sentences) > 1 and len(summary) < max_length:
        summary += max(sentences[1:], key=len)
    return summary[:max_length] + ("…" if len(summary) > max_length else "")


def safety_check(text: str) -> dict:
    normalized = normalize(text)
    hits = [word for word in SECURITY_WORDS if normalize(word) in normalized]
    return {
        "safe": not hits,
        "hits": hits,
        "message": (
            "「" + "」「".join(hits) + "」这种词社区不让发，改一下再发哈。"
            if hits
            else "没看出什么问题，发吧。"
        ),
    }


def suggest_title(text: str) -> str:
    clean = re.sub(r"\s+", " ", str(text or "").strip())
    if not clean:
        return ""
    first = re.split(r"[。！？!?\n，,；;]", clean)[0] or clean
    title = first[:26] + ("…" if len(first) > 26 else "")
    return title.lstrip("，,、 ")


def polish_content(text: str) -> dict:
    raw = str(text or "")
    issues: list[str] = []
    trimmed = raw.strip()

    if len(trimmed) < 20:
        issues.append("太短了，补两句背景，不然别人看不明白。")
    if trimmed and not re.search(r"[。！？!?…]$", trimmed):
        issues.append("结尾没标点，给你补了个句号。")
    if re.match(r"^[^。！？!?\n]{80,}$", trimmed):
        issues.append("一整段太长了，按句子拆成了几段，好读一点。")
    if re.search(r"(.)\1{3,}", trimmed):
        issues.append("有几个字连着重复，删到只剩一个了。")
    if re.search(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", raw):
        issues.append("里面混了看不见的控制字符，清掉了。")

    text2 = re.sub(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]", "", raw)
    text2 = re.sub(r"\s+", " ", text2).strip()
    text2 = re.sub(r"(.)\1{3,}", r"\1", text2)
    if text2 and not re.search(r"[。！？!?…]$", text2):
        text2 += "。"

    sentences = [s for s in re.split(r"(?<=[。！？!?；;])", text2) if s]
    paragraphs: list[str] = []
    buffer = ""
    for sentence in sentences:
        buffer += sentence
        if len(buffer) >= 70:
            paragraphs.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        paragraphs.append(buffer.strip())

    content = "\n\n".join(paragraphs)
    return {"content": content, "issues": issues, "changed": content != raw.strip()}


def writing_assistant(text: str) -> dict:
    polished = polish_content(text)
    classification = classify(text)
    tags = extract_tags(text)
    safety = safety_check(text)
    category = CATEGORY_MAP.get(classification["category"], CATEGORY_MAP["life"])

    tips: list[str] = []
    if len(tags) < 2:
        tips.append("标签少了点，补上课程名、地点、时间，别人更容易搜到你。")
    if not safety["safe"]:
        tips.append("违规词删了再发。")
    if not polished["issues"]:
        tips.append("读着挺顺的，直接发就行。")

    return {
        "title": suggest_title(polished["content"]) or suggest_title(text),
        "content": polished["content"],
        "category": category["id"],
        "category_name": category["name"],
        "category_confidence": classification["confidence"],
        "tags": tags or ["校园", "互助"],
        "summary": summarize(polished["content"]),
        "issues": polished["issues"],
        "tips": tips,
        "safety": safety,
        "changed": polished["changed"],
    }


# ---------------- 3. 搭子匹配 ----------------
def jaccard(a: list[str] | None, b: list[str] | None) -> float:
    set_a = {normalize(x) for x in (a or []) if normalize(x)}
    set_b = {normalize(x) for x in (b or []) if normalize(x)}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def match_buddies(me: dict, users: list[dict]) -> dict:
    my_tags = me.get("tags") or []
    my_bio = _vector(tokenize(me.get("bio") or ""), _Idf)

    results = []
    for user in users:
        if user["id"] == me["id"]:
            continue
        tag_score = jaccard(my_tags, user.get("tags") or [])
        bio_score = _cosine(my_bio, _vector(tokenize(user.get("bio") or ""), _Idf))
        score = tag_score * 0.75 + bio_score * 0.25
        if score <= 0:
            continue
        common = [
            tag
            for tag in my_tags
            if any(normalize(tag) == normalize(other) for other in (user.get("tags") or []))
        ]
        results.append({"user": user, "score": score, "common": common})

    results.sort(key=lambda item: item["score"], reverse=True)
    results = results[:3]

    if not results:
        return {
            "matches": [],
            "message": "没找到太合适的。简介和标签再补几个吧，「考研」「摄影」这种具体的词，"
            "匹配起来准一些。",
        }

    matches = []
    for item in results:
        reasons = []
        if item["common"]:
            reasons.append("你俩都爱「" + "」「".join(item["common"]) + "」")
        if item["user"].get("major") and me.get("major") and item["user"]["major"] == me["major"]:
            reasons.append("同一个专业，课表都差不多")
        if item["score"] > 0.5:
            reasons.append("兴趣重合挺多的，估计聊两句就熟")
        elif item["score"] > 0.2:
            reasons.append("共同话题不少，可以认识一下")
        else:
            reasons.append("有点交集，从学校的事聊起就行")
        matches.append(
            {
                "user": item["user"],
                "score": round(item["score"], 3),
                "reason": "；".join(reasons) + "。",
            }
        )

    return {
        "matches": matches,
        "message": "按标签和简介挑的，就 " + str(len(matches)) + " 个，先看看合不合眼缘。",
    }


def chunk_text(text: str, size: int = 3):
    """把回答切成小块，用于 SSE 流式输出。"""
    for index in range(0, len(text), size):
        yield text[index : index + size]
