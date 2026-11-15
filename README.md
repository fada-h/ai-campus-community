# AI校园社区

> 校园里的事，本该问一声就有人答。

面向高校学生的 AI 社区。查资料、找搭子、写帖子这三件最常卡住的事，都交给一个能看见调用过程的 AI 助手，
但它不会替你发帖、评论、私信——要不要用，你自己点。

- 参赛赛项：2026 第九届传智杯全国大学生数智创新与AI应用大赛 · AI Web 网页开发挑战赛
- 命题方向：**AI 社交与社区应用**
- 代码仓库：<https://github.com/fada-h/ai-campus-community>
- 在线演示：`（部署后补）`
- 演示账号：`linxiaoman / 123456`（管理员）　`zhouyihang / 123456`（普通用户）

## 界面预览

| 首页 | AI 助手（能看到工具轨迹） |
|---|---|
| ![首页](docs/screenshot-home.png) | ![AI 助手](docs/screenshot-ai.png) |

| 私信 | 后台管理 |
|---|---|
| ![私信](docs/screenshot-messages.png) | ![后台](docs/screenshot-admin.png) |

---

## 一、选题：为什么是校园社区

校园里的信息是散的：通知在教务系统，问路在班级群，二手在朋友圈，找搭子在群公告。
真到要用的时候，翻半天也翻不到，最后还是「算了，问室友」。

我们没打算做「又一个论坛」，而是把最常卡住的三个地方搬到一起：

| 卡在哪 | 我们怎么做 |
|---|---|
| 有话没处问 | 校园问答：26 类校内事务，答案带来源和置信度 |
| 有话说不清 | 发帖助手：把口语捋顺，给标题、分类、标签，顺手查违规词 |
| 想找同频的人 | 搭子匹配：按兴趣标签和简介挑人，并说明为什么推荐 |

AI 在这里不是加一个聊天框，而是嵌进「问 → 写 → 找人」这条真实动线里。

---

## 二、功能清单

### 社区
- 注册 / 登录（scrypt 加盐哈希 + HMAC 签名 Token，无第三方 JWT 依赖）
- 个人资料与兴趣标签（专业、年级、简介、最多 8 个标签）
- 帖子发布 / 浏览 / 搜索 / 分类筛选 / 最新与最热排序
- 5 个板块：学习互助、社团活动、二手闲置、失物招领、校园生活
- 点赞、评论、浏览量、热度排序
- 私信：会话列表、历史消息、WebSocket 实时推送、在线状态
- 后台管理：数据概览、帖子删除、用户权限
- 暗色模式、响应式布局

### AI
| 能力 | 入口 | 说明 |
|---|---|---|
| Agent 问答 | AI 助手页 / 右下悬浮球 | 先规划再调工具，工具轨迹实时可见 |
| 校园问答（RAG） | 同上 | 26 条校园知识，TF-IDF 检索 + 来源 + 置信度 |
| 发帖写作助手 | 发帖弹窗「AI 帮我润色」 | 标题、正文、分类、标签、摘要、违规检测 |
| 搭子匹配 | 个人主页「AI 搭子匹配」 | 标签 Jaccard + 简介文本相似度，输出匹配度与理由 |

> 所有 AI 输出标注「仅供参考」；AI 不会自动发帖、评论或私信。

---

## 三、AI 技术方案

### 1. 整体链路

```
用户提问
   └─ Agent 规划（云端 Function Calling / 本地规则兜底）
        ├─ check_safety      违规词检查
        ├─ search_knowledge  知识库检索（RAG）
        ├─ search_posts      社区帖子检索（二元词打分）
        ├─ match_buddies     兴趣标签匹配
        └─ draft_post        帖子草稿生成
   └─ 组织回答 → SSE 流式输出（step / meta / delta / done）
```

前端会把每一步「想了什么、调了哪个工具、查到几条」画出来，AI 不是黑箱。

### 2. RAG 检索

- 语料：26 条校园事务（图书馆、食堂、教务、宿舍、校园卡、奖学金、场馆、报修等），人工整理成口语文本。
- 切词：中文 bigram（权重 1）+ 单字（权重 0.5），英文数字整词；停用词表过滤「然后」「就是」这类虚词。
- 打分：TF-IDF 向量 + 余弦相似度。
- 阈值：相似度换算的置信度低于 0.45 就不硬答，转去社区或让用户换个说法。
- 可解释：命中时返回 `topic`、`source`（如「校图书馆官网」）、`confidence`。

### 3. Agent 与工具调用

- 云端：DeepSeek Function Calling，最多 3 轮工具循环，模型自己决定查什么。
- 本地：没有 Key 或请求失败时，规则规划器按意图路由（写帖子 / 找搭子 / 查资料 / 翻帖子），
  真实调用同一批工具，然后组织成人话。断网也能演示完整流程。
- 工具返回值统一成 `{summary, data}`：`summary` 给人看（工具轨迹），`data` 给模型看。

### 4. 安全与可控

| 风险 | 处理 |
|---|---|
| 违规内容 | 18 个敏感词，发帖前检测，AI 回答前也先过一遍 |
| AI 越权 | AI 只产出建议，发帖要用户点「应用到正文」再发布 |
| 答非所问 | 置信度阈值 + 工具查不到就说「不确定」 |
| 模型不可用 | 自动降级本地引擎，页面标注当前模式 |
| 密钥泄露 | 只读环境变量，`.env` / `.secret` 在 `.gitignore` 与 `.dockerignore` 里排除 |

### 5. 工程细节

- SSE 流式：先推 `step`（思考/工具），再推 `meta`（模式、来源），最后逐块推 `delta`。
- 多轮上下文：最近 6 轮对话一起送，追问「那周末呢」接得上。
- 失败重试：前端带「↻ 重试」，后端异常也有兜底话术。
- 调用留痕：`ai_logs` 记录每次调用的输入、模式、字数。

---

## 四、技术栈与目录

**FastAPI + SQLAlchemy 2.0 + MySQL 8.0（可退 SQLite）+ Vue 3 + Vite + TailwindCSS + TypeScript**

```
ai-community-app
├─ 一键安装.cmd / 启动.cmd         # Windows 双击即跑
├─ Dockerfile / render.yaml        # 单服务部署（前端 dist 由 FastAPI 托管）
├─ backend/
│  ├─ requirements.txt
│  ├─ .env.example                 # 环境变量模板
│  ├─ sql/schema.sql               # MySQL 建表脚本
│  ├─ scripts/init_db.py           # 建库 + 建表 + 演示数据
│  └─ app/
│     ├─ main.py config.py db.py models.py schemas.py security.py
│     ├─ seed.py                   # 演示数据（8 用户 / 14 帖 / 12 评论 / 8 私信）
│     ├─ ws.py                     # WebSocket 私信
│     ├─ ai/
│     │  ├─ agent.py               # Agent：工具定义 + 规划 + 兜底
│     │  ├─ engine.py              # 本地引擎：分词 / 检索 / 分类 / 匹配
│     │  ├─ knowledge.py           # 26 条校园知识库
│     │  └─ service.py             # DeepSeek 编排 + 降级
│     └─ routers/                  # auth users posts ai messages admin meta
└─ frontend/
   └─ src/
      ├─ views/    Home Post Ai Profile Login Messages Admin
      ├─ components/ NavBar PostCard Composer AiPanel ToastHost
      ├─ api/      client.ts（SSE / WebSocket）、index.ts
      └─ stores/   轻量状态管理
```

---

## 五、快速开始

### 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 3.12 已验证 |
| Node.js | 18+ | 20 / 24 已验证 |
| MySQL | 8.0 | 可选，连不上会自动用 SQLite |
| DeepSeek API Key | — | 可选，没有 Key 用本地引擎 |

### 方式一：双击脚本（推荐）

1. 双击 **`一键安装.cmd`**：建虚拟环境、装依赖、生成 `backend/.env`、建表、写演示数据。
2. 双击 **`启动.cmd`**：起后端 8000、前端 5173，等两边就绪后自动打开浏览器。

脚本会检查端口占用、依赖是否装好，出错会停在报错那一行，不会一闪而过。

### 方式二：命令行

```bash
# 后端
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts\init_db.py
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 前端（另开一个终端）
cd frontend
npm install
npm run dev
```

- 前端：<http://127.0.0.1:5173>
- 接口文档：<http://127.0.0.1:8000/docs>

### 数据库

`backend/.env` 里二选一，**不配也能跑**：

```ini
# 方式一：完整 URL
DATABASE_URL=mysql+pymysql://root:你的密码@127.0.0.1:3306/campus_ai_community?charset=utf8mb4

# 方式二：由 MYSQL_* 拼装（DATABASE_URL 留空时生效）
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的密码
MYSQL_DATABASE=campus_ai_community
```

- MySQL 库不存在会自动创建（`AUTO_CREATE_DATABASE=1`）；
- MySQL 连不上（没装、密码错、服务没开）会自动降级 `backend/data/campus.db`，
  `/api/health` 的 `note` 字段会写明降级原因；
- 想彻底关掉降级：`ALLOW_SQLITE_FALLBACK=0`。

### 接入 DeepSeek（可选）

```ini
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

不填就用本地引擎，AI 页会显示「本地引擎」，Agent 仍然可用。

### 演示账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| `linxiaoman` | `123456` | 管理员 |
| `zhouyihang` | `123456` | 普通用户 |

其余账号密码相同：`suwanqing`、`chenmo`、`guxingye`、`heyinuo`、`shenzhiyao`、`jiangyuan`。

---

## 六、5 分钟演示脚本（对应演示视频）

1. **首页**（30s）：信息流、板块筛选、热度、深色模式；说明选题痛点。
2. **Agent 问答**（90s）：问「图书馆几点关门」→ 看得到「检查违规词 → 查校园资料 → 命中知识库 75%」的轨迹；
   再问「社区里有人出二手显示器吗」→ Agent 改去翻帖子并给出结果。
3. **找搭子**（40s）：个人主页 →「开始匹配」→ 匹配度与理由。
4. **发帖 + 写作助手**（70s）：输入一段口语 → AI 出标题、分类、标签、违规提示 → 点「应用到正文」才算数。
5. **私信**（40s）：两个浏览器窗口分别登录，消息实时到达。
6. **后台**（30s）：管理员看数据、删帖、调权限。
7. **降级演示**（30s）：拔掉 Key 或断网，Agent 仍然跑通，只是换成「本地引擎」。

---

## 七、评分维度对照

| 评分维度（权重） | 对应设计 |
|---|---|
| AI 技术深度（35%） | 大模型集成（Prompt + 降级）、Agent Function Calling 工具循环、RAG 检索与置信度阈值、内容安全与兜底 |
| 创新性（25%） | 选题落在真实校园动线；Agent 工具轨迹可视化；「AI 只建议、不代发」的交互边界 |
| 前端工程质量（10%） | TypeScript、组件拆分（8 个 view + 5 个 component）、路由懒加载、SSE 流式渲染 |
| 实用性（10%） | 校内事务、二手、失物、找搭子都是高频需求；无 Key 也能用 |
| 用户体验（10%） | 流式输出、工具轨迹、加载/空/错误态、暗色模式、移动端适配 |
| 社会价值与商业潜力（10%） | 降低校园信息获取成本；可复用到其他高校，后端可换任意 OpenAI 兼容模型 |

---

## 八、接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（含数据库模式与降级说明） |
| GET | `/api/meta` | 应用信息、板块、AI 模式、统计 |
| POST | `/api/auth/register` `/api/auth/login` | 注册 / 登录 |
| GET | `/api/auth/me` | 当前用户 |
| PUT | `/api/users/me` | 更新资料与标签 |
| GET | `/api/users/{id}` | 用户主页 + TA 的帖子 |
| GET | `/api/posts` | 列表（category / q / sort / limit） |
| POST | `/api/posts` | 发帖 |
| GET | `/api/posts/{id}` | 详情 + 评论 + 相关推荐 |
| POST | `/api/posts/{id}/like` | 点赞 / 取消 |
| GET/POST | `/api/posts/{id}/comments` | 评论列表 / 发表 |
| POST | `/api/ai/agent` | Agent 问答（SSE，带工具轨迹） |
| POST | `/api/ai/chat` | 校园问答（SSE，轻量版） |
| POST | `/api/ai/write` | 写作助手 |
| POST | `/api/ai/match` | 搭子匹配 |
| GET | `/api/messages/conversations` | 会话列表 |
| GET/POST | `/api/messages/{peer_id}` | 历史消息 / 发送 |
| WS | `/ws?token=...` | 私信实时推送 |
| GET | `/api/admin/overview` `/api/admin/users` | 后台数据 |
| DELETE | `/api/admin/posts/{id}` | 删除帖子 |

---

## 九、团队信息

| 角色 | 姓名 | 学校 / 专业 | 负责 |
|---|---|---|---|
| 队长 / 全栈 | （待填） | （待填） | 架构、后端、AI 方案 |
| 前端 | （待填） | （待填） | 页面与交互 |
| AI / 文档 | （待填） | （待填） | Prompt、演示视频、技术文档 |

> 报名时每人只能进一支队伍，队名与成员请按组委会要求填写。

---

## 十、提交材料清单

| 材料 | 要求 | 本仓库对应 |
|---|---|---|
| 代码仓库 | GitHub / Gitee，公开或给评审权限 | 由你上传，保留提交历史 |
| README | 项目介绍、架构、运行指南、团队信息 | 本文件（团队信息待填） |
| 环境配置 | 环境变量模板 + 依赖清单 | `backend/.env.example`、`backend/requirements.txt`、`frontend/package.json` |
| 演示视频 | 5–8 分钟，1080p，普通话 | 按第六节脚本录 |
| 技术文档 | PDF，≤30 页 | 建议按第三节 + 架构图扩写 |
| 在线演示 | 可选加分，需保持可用 | `render.yaml` / `Dockerfile` 可直接部署 |

---

## 十一、常见问题

**Q：启动脚本一闪就没了？**
在 cmd 里进项目目录手动跑 `启动.cmd`，报错会停在窗口里。

**Q：后端起来了但页面 500 / 连不上数据库？**
看 `http://127.0.0.1:8000/api/health` 的 `note`：写了降级就说明 MySQL 没连上，已改用 SQLite；
想继续用 MySQL 就把 `.env` 里的账号密码改对，或确认 MySQL80 服务在跑。

**Q：端口被占？**
启动脚本会直接提示被占用；改端口要同时改 `backend/.env` 的 `PORT` 和 `frontend/vite.config.ts` 的代理目标。

**Q：AI 页显示「本地引擎」？**
说明没配 `DEEPSEEK_API_KEY`，或者 Key 失效（401）。本地引擎功能完整，只是话没那么活。

**Q：想重置演示数据？**
删库重跑：MySQL 执行 `DROP DATABASE campus_ai_community`，再 `python scripts/init_db.py`；
SQLite 直接删 `backend/data/campus.db`。

**Q：前端改端口后 WebSocket 不工作？**
`vite.config.ts` 里 `/ws` 代理的 `ws: true` 不能删。
