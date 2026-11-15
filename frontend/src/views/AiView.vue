<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '@/api'
import AiPanel from '@/components/AiPanel.vue'

const logs = ref<{ id: number; kind: string; input: string; mode: string; chars: number }[]>([])
const aiMode = ref('local')

async function load() {
  try {
    logs.value = (await api.aiLogs()).slice(0, 6)
    const meta = await api.meta()
    aiMode.value = meta.ai.mode
  } catch {
    /* 未登录也能看助手，只是没有记录 */
  }
}

const capabilities = [
  { icon: '🏫', title: '校园事务问答', desc: '图书馆、食堂、教务、宿舍、奖学金，26 类都能问' },
  { icon: '🧰', title: 'Agent 工具调用', desc: '先想再查：知识库、帖子、兴趣标签一个个翻，查到了才回答' },
  { icon: '✍️', title: '发帖写作助手', desc: '起标题、改正文、挑分类和标签，顺便看看有没有说不得的词' },
  { icon: '🤝', title: '搭子匹配', desc: '按标签和简介找人，还会告诉你为什么觉得你俩合得来' },
]

onMounted(load)
</script>

<template>
  <main class="mx-auto max-w-[1100px] px-5 pb-24 pt-6">
    <div class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <AiPanel />

      <aside class="space-y-4">
        <section class="card p-4">
          <div class="mb-3 text-sm font-bold">✨ AI 能做什么</div>
          <div class="space-y-3">
            <div v-for="item in capabilities" :key="item.title" class="flex gap-2.5">
              <span class="text-base">{{ item.icon }}</span>
              <div>
                <div class="text-[13px] font-semibold">{{ item.title }}</div>
                <div class="text-[11.5px] text-slate-400">{{ item.desc }}</div>
              </div>
            </div>
          </div>
        </section>

        <section class="rounded-2xl border border-slate-200 bg-white p-4 text-[12px] dark:border-slate-800 dark:bg-slate-900">
          <div class="mb-1 text-xs font-bold">🧠 当前 AI 模式</div>
          <p v-if="aiMode === 'cloud'" class="text-slate-500">
            配置里接的是 DeepSeek，正常情况由大模型回答。请求失败会自动退回本地知识库，回答下方会标「本地引擎」。
          </p>
          <p v-else class="text-slate-500">
            现在跑的是本地引擎，靠内置的校园知识库检索，断网也能用。想接 DeepSeek 的话，在 backend/.env 里填上
            <code class="rounded bg-slate-100 px-1 dark:bg-slate-800">DEEPSEEK_API_KEY</code> 就自动切过去了。
          </p>
        </section>

        <section v-if="logs.length" class="card p-4">
          <div class="mb-2 text-sm font-bold">最近 AI 调用</div>
          <div v-for="log in logs" :key="log.id" class="border-b border-slate-100 py-1.5 last:border-0 dark:border-slate-800">
            <div class="text-[12px]">
              {{ log.kind === 'chat' ? '💬' : log.kind === 'agent' ? '🧰' : log.kind === 'write' ? '✍️' : '🤝' }} {{ log.input }}
            </div>
            <div class="text-[11px] text-slate-400">{{ log.mode === 'cloud' ? '云端' : '本地' }} · {{ log.chars }} 字</div>
          </div>
        </section>

        <section class="rounded-2xl border border-slate-200 bg-white p-4 text-[12px] text-slate-500 dark:border-slate-800 dark:bg-slate-900">
          <div class="mb-1 text-xs font-bold">⚠️ 使用边界</div>
          它只给建议，不会自己发帖、评论、私信。要不要用，你点一下才算数。
        </section>
      </aside>
    </div>
  </main>
</template>
