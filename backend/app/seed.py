"""演示数据：首次启动时写入 8 位用户 / 14 篇帖子 / 12 条评论。

演示账号：linxiaoman / 123456（管理员），其余账号密码相同。
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Comment, Message, Post, PostLike, User
from .security import hash_password

DEMO_PASSWORD = "123456"

_now = datetime.utcnow()


def _ago(hours: float) -> datetime:
    return _now - timedelta(hours=hours)


USERS = [
    {
        "username": "linxiaoman", "nickname": "林小满", "avatar": "🌿", "color": "#6366f1",
        "major": "计算机科学与技术", "grade": "大三",
        "bio": "二战 408，图书馆五楼靠窗那张桌子常年被我占着。咖啡喝太多，晚上照样睡不着。"
        "缺个能盯着我别摸鱼的搭子。",
        "tags": ["考研", "算法", "咖啡", "摄影"], "is_admin": True, "created_at": _ago(24 * 40),
    },
    {
        "username": "zhouyihang", "nickname": "周亦航", "avatar": "🎸", "color": "#ec4899",
        "major": "软件工程", "grade": "大二",
        "bio": "吉他社副社长。周三晚上在活动中心排练，缺键盘手，会弹个《卡农》开头就行。"
        "白天写前端，晚上被 bug 追。",
        "tags": ["篮球", "吉他", "前端", "社团"], "created_at": _ago(24 * 36),
    },
    {
        "username": "suwanqing", "nickname": "苏晚晴", "avatar": "📖", "color": "#10b981",
        "major": "汉语言文学", "grade": "大一",
        "bio": "大一，喜欢旧书摊，五块钱三本那种。想找人一起晨读，我起得来，但坚持不住。",
        "tags": ["读书", "写作", "志愿服务", "摄影"], "created_at": _ago(24 * 30),
    },
    {
        "username": "chenmo", "nickname": "陈默", "avatar": "🔧", "color": "#f59e0b",
        "major": "电子信息工程", "grade": "研一",
        "bio": "研一，嵌入式，实验室常驻。晚上九点去操场跑五公里，配速一般。跑完回来接着调板子。",
        "tags": ["嵌入式", "跑步", "考研", "实验室"], "created_at": _ago(24 * 26),
    },
    {
        "username": "guxingye", "nickname": "顾星野", "avatar": "🎨", "color": "#8b5cf6",
        "major": "数字媒体艺术", "grade": "大三",
        "bio": "数媒大三，接一点校园约拍，收费看心情。喜欢傍晚的光，和便宜的咖啡。",
        "tags": ["设计", "摄影", "咖啡", "插画"], "created_at": _ago(24 * 22),
    },
    {
        "username": "heyinuo", "nickname": "何一诺", "avatar": "🏸", "color": "#14b8a6",
        "major": "会计学", "grade": "大二",
        "bio": "羽毛球校队替补，就是坐板凳那个。最近在备考初级，周末烤饼干分室友，烤糊了也分。",
        "tags": ["羽毛球", "自习", "考研", "烘焙"], "created_at": _ago(24 * 18),
    },
    {
        "username": "shenzhiyao", "nickname": "沈知遥", "avatar": "🚴", "color": "#0ea5e9",
        "major": "英语", "grade": "大四",
        "bio": "英语大四，在准备 MTI。帮人改简历和文书，改完请我喝一杯就行。周末骑车绕城，很慢。",
        "tags": ["翻译", "读书", "骑行", "考研"], "created_at": _ago(24 * 14),
    },
    {
        "username": "jiangyuan", "nickname": "江予安", "avatar": "🎮", "color": "#ef4444",
        "major": "人工智能", "grade": "大二",
        "bio": "算法竞赛退役，现在捣鼓小游戏。蓝桥杯想组队，缺个图论稳的。篮球也打，打得一般。",
        "tags": ["算法", "竞赛", "篮球", "游戏"], "created_at": _ago(24 * 10),
    },
]

POSTS = [
    (0, "study", "找一起冲 408 的研友，图书馆五楼长期自习",
     "二战了，一个人复习真的容易走神。\n\n"
     "现在数据结构刚过完第二轮，想找个节奏差不多的，互相盯着点。周一到周五晚上六点半到十点，"
     "周末全天，五楼靠窗。\n\n"
     "真题和笔记我按章节整理过，可以共享。就一个要求：别三天打鱼两天晒网，我这个人容易被带跑。",
     ["考研", "408", "自习"], 2, 186),
    (7, "study", "蓝桥杯组队，缺一个会写图论的队友",
     "报了蓝桥杯 Java B 组，现在两个人。一个偏 DP，一个数据结构还行，图论和搜索这块我俩都不太行。\n\n"
     "周六下午在信息楼 402 刷往年题，有空调有插座。目标先省一，能进国赛最好。\n\n"
     "C++ 也欢迎，语言不是问题，思路对就行。",
     ["竞赛", "蓝桥杯", "算法"], 5, 243),
    (1, "club", "吉他社秋季招新，零基础也欢迎",
     "吉他社招新，这周四、周五晚上六点在活动中心一楼摆摊。\n\n"
     "不会弹也能来，每周有一次免费教学课，从按和弦开始教。社里有木吉他、电吉他、键盘、鼓，"
     "就是缺键盘手，会一点钢琴的赶紧来。\n\n现场有小演出，来听也行。",
     ["社团", "吉他", "招新"], 9, 512),
    (4, "market", "出二手显示器 24 寸 2K，九成新",
     "去年双十一买的 AOC 24 寸 2K，换了带鱼屏，这个就闲置了。\n\n"
     "无坏点无划痕，原箱和配件都在，线是 HDMI 的。原价 1099，现在 520，能小刀一点点。\n\n"
     "西区宿舍楼下自提，可以先看再决定，看完不买也没关系。",
     ["二手", "显示器", "闲置"], 13, 328),
    (2, "lost", "在南门捡到一张校园卡，姓李",
     "中午在南门快递驿站门口捡到一张校园卡，姓李，卡号后四位 3721。\n\n"
     "已经交到保卫处了，失主带学生证去行政楼一楼领。\n\n认识的帮忙说一声，谢谢。",
     ["失物招领", "校园卡"], 20, 96),
    (5, "life", "二食堂新出的番茄牛腩饭，值得跑一趟",
     "二食堂二楼新开的窗口，番茄牛腩饭 16 块。牛腩给得挺实在，汤泡饭很香，我一个人能干两碗。\n\n"
     "缺点是要排队，十二点以后人特别多，建议十一点半之前去。\n\n酸梅汤免费续，这点好评。",
     ["食堂", "美食", "推荐"], 26, 671),
    (6, "study", "免费帮同学改英文简历 / 留学文书",
     "刚忙完申请季，手上空下来了。\n\n"
     "英文简历、个人陈述，语法和表达都能帮你看，一次二十分钟左右，看完把问题标给你。"
     "不代写，只给建议。\n\n需要的评论一下，我私信约时间。人可能有点多，排队。",
     ["英语", "简历", "留学"], 30, 402),
    (3, "life", "晚上操场跑步搭子，配速 6 分左右",
     "在准备半马，一个人跑太容易放弃了。\n\n"
     "每周二、四、日晚上八点半，操场东侧集合，配速六分到六分半，跑五到八公里。\n\n"
     "新手也能来，可以慢点跑，我陪你加量。下雨自动取消。",
     ["跑步", "运动", "搭子"], 34, 219),
    (7, "market", "求购一本《算法导论》第三版，中文版",
     "中文版优先，有笔记也收，价格好说。信息楼附近我自己过去拿。",
     ["二手", "求购", "教材"], 40, 74),
    (0, "life", "图书馆五楼空调太冷了，有人有同感吗",
     "靠窗那排正对着出风口，坐俩小时手都僵了，写字都写不利索。\n\n"
     "提醒一下要去自习的同学，带件外套，或者别坐那一排。\n\n"
     "已经在后勤的小程序上提了，不知道管不管用。",
     ["图书馆", "吐槽", "自习"], 46, 288),
    (2, "club", "周末去市图书馆做志愿者，还差 2 人",
     "这周六九点到四点，市图书馆少儿区，帮忙整理书、带小朋友。\n\n"
     "有志愿工时，管午饭，地铁票能报。\n\n还差两个人，想去的评论一下。",
     ["志愿", "公益", "周末"], 52, 157),
    (4, "life", "校园约拍，秋日光影计划",
     "在拍一组校园秋天的人像，想找几个同学当模特。\n\n"
     "免费，成片精修五张，风格可以商量。周末下午拍，老教学楼和梧桐道那片。\n\n"
     "不用会摆姿势，我会带。",
     ["摄影", "约拍", "校园"], 58, 634),
    (5, "study", "求推荐安静的自习教室，晚上开放到 11 点",
     "图书馆十点就闭馆了，太早。\n\n"
     "想找个能坐到十一点的地方，最好有插座、有热水、人别太多。\n\n"
     "有推荐的吗，评论区救救孩子。",
     ["自习", "教室", "推荐"], 66, 341),
    (1, "lost", "宿舍楼下有人掉了一把黑伞，放在门卫室了",
     "下午在 6 号楼下捡到一把黑色长柄伞，交给门卫大叔了。失主自己去拿就行。",
     ["失物招领", "雨伞"], 72, 61),
]

COMMENTS = [
    (0, 5, "我我我！我也在五楼，一般坐中间那排，晚上七点以后都在。", 1),
    (0, 3, "408 第二轮了就直接上真题吧，选择题提分快，别在书上耗太久。", 1),
    (1, 0, "图论我可以，不过我写 C++，跨语言行不行？", 4),
    (2, 2, "键盘手是要钢琴还是电子琴啊？我会一点钢琴，弹得不多。", 8),
    (2, 1, "都行都行，周四来摊位聊两句～", 7),
    (3, 7, "还在吗？能小刀到 480 吗，今晚就能过去拿。", 11),
    (3, 4, "在的，480 行，你几点过来？", 10),
    (5, 3, "昨天去吃了，牛腩确实多，就是有点咸，我让阿姨少浇了点汤。", 24),
    (6, 0, "太需要了！我的 CV 自己看怎么看怎么别扭，求指点。", 28),
    (11, 2, "报名！想拍一组梧桐道的，就是我拍照很僵。", 56),
    (12, 6, "信息楼 402，开到十一点，有插座，人不多。就是晚上有点冷。", 64),
    (7, 5, "六分半的配速能跟上吗？我刚开始跑，怕拖后腿。", 33),
]

LIKES = {
    0: [3, 5, 6], 1: [0, 3, 4, 5], 2: [2, 4, 5, 6, 7], 3: [7], 4: [0, 1],
    5: [0, 3, 6, 7], 6: [0, 2, 4], 7: [0, 5], 8: [], 9: [2, 5],
    10: [1, 2], 11: [0, 1, 2, 5, 6], 12: [0, 5], 13: [],
}

# 私信演示数据：(发件人, 收件人, 内容, 几小时前, 收件人是否已读)
MESSAGES = [
    (5, 0, "看到你找 408 研友的帖子，我基础不太好，能跟吗？", 3, True),
    (0, 5, "能啊，先来坐两天看看节奏，五楼靠窗。", 2.5, True),
    (5, 0, "好，我明晚六点半到，带两杯咖啡。", 2, True),
    (0, 5, "行，我请你，别买。", 1.6, False),
    (6, 0, "简历能帮我看一下吗，英文的。", 1.2, True),
    (0, 6, "可以，发我，今晚给你标出来。", 1, False),
    (7, 1, "键盘手找到了吗？我会一点钢琴。", 5, True),
    (1, 7, "还没！周四来摊位聊。", 4.5, True),
]


def seed_if_empty(db: Session) -> bool:
    """数据库为空时写入演示数据，返回是否写入。"""
    count = db.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        return False

    users: list[User] = []
    for item in USERS:
        user = User(
            username=item["username"],
            password_hash=hash_password(DEMO_PASSWORD),
            nickname=item["nickname"],
            avatar=item["avatar"],
            color=item["color"],
            major=item["major"],
            grade=item["grade"],
            bio=item["bio"],
            tags=item["tags"],
            is_admin=item.get("is_admin", False),
            created_at=item["created_at"],
        )
        db.add(user)
        users.append(user)
    db.flush()

    posts: list[Post] = []
    for author_index, category, title, content, tags, hours, views in POSTS:
        post = Post(
            author_id=users[author_index].id,
            category=category,
            title=title,
            content=content,
            tags=tags,
            views=views,
            created_at=_ago(hours),
        )
        db.add(post)
        posts.append(post)
    db.flush()

    for post_index, author_index, content, hours in COMMENTS:
        db.add(
            Comment(
                post_id=posts[post_index].id,
                author_id=users[author_index].id,
                content=content,
                created_at=_ago(hours),
            )
        )

    for post_index, user_indexes in LIKES.items():
        for user_index in user_indexes:
            db.add(PostLike(post_id=posts[post_index].id, user_id=users[user_index].id))

    for sender, receiver, content, hours, is_read in MESSAGES:
        db.add(
            Message(
                sender_id=users[sender].id,
                receiver_id=users[receiver].id,
                content=content,
                is_read=is_read,
                created_at=_ago(hours),
            )
        )

    db.commit()
    return True
