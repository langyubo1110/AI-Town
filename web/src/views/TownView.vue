<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import TownCanvas from '@/components/TownCanvas.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import EventFeed from '@/components/EventFeed.vue'
import NpcStrip from '@/components/NpcStrip.vue'
import { fetchNpcs } from '@/api/npc'
import { fetchPlans } from '@/api/town'
import { createSession } from '@/api/session'
import { ApiError } from '@/api/http'
import type { ChatOut, Npc, NpcPlan, TownEvent } from '@/types/api'

const STORAGE_KEY = 'aitown.playerName'

/** WebSocket 没连上时的兜底刷新间隔。
 *  为什么需要：playerId 只有聊过一次天才拿得到，在那之前 WS 连不上，
 *  而"打开页面就能看到小镇自己动"是演示的第一印象。
 */
const POLL_MS = 30_000

const npcs = ref<Npc[]>([])
const plans = ref<NpcPlan[]>([])
const loading = ref(true)
const error = ref('')
const plansLoading = ref(false)

/** 选中 NPC 的今日计划：传给对话面板，只有选中时才显示他的任务 */
const selectedPlan = computed(
  () => plans.value.find((plan) => plan.npc_id === selected.value?.id) ?? null,
)

/** 画布头顶浮标：选中的人在做什么（没选中就为空） */
const selectedTask = computed(() => {
  if (!selected.value) return null
  const step = selectedPlan.value?.steps.find((item) => item.status === 'pending')
  return {
    id: selected.value.id,
    text: step ? `现在 ${step.at} ${step.goal}` : '今天的安排都完成了',
  }
})
const selected = ref<Npc | null>(null)
const playerName = ref(localStorage.getItem(STORAGE_KEY) || '小明')
const playerId = ref<number | null>(null)

watch(playerName, (name) => {
  localStorage.setItem(STORAGE_KEY, name)
  // 换名字等于换玩家：旧的事件流不再属于他
  playerId.value = null
  void ensureSession()
})

/** 和服务端握手，拿到签名 Cookie 后再谈"我是谁"。
 *  失败不阻塞页面：接口还有 query 回退，只是服务端会记一条 identity_unsigned。
 */
async function ensureSession(): Promise<void> {
  try {
    const session = await createSession(playerName.value)
    playerId.value = session.player_id
  } catch {
    /* 静默失败：不影响看小镇 */
  }
}

/** 位置没变就不替换数组：TownCanvas 的 watch 会重建全部精灵，
 *  每 30 秒重建一次画面会闪。
 */
function sameLocations(a: Npc[], b: Npc[]): boolean {
  if (a.length !== b.length) return false
  return a.every((npc, i) => npc.id === b[i].id && npc.location === b[i].location)
}

/** silent=true：后台刷新，不闪 loading、不覆盖已有报错 */
async function loadNpcs(silent = false) {
  if (!silent) {
    loading.value = true
    error.value = ''
  }
  try {
    const data = await fetchNpcs()
    if (silent && sameLocations(npcs.value, data.items)) return
    npcs.value = data.items
  } catch (err) {
    if (!silent) {
      error.value =
        err instanceof ApiError
          ? `加载失败（${err.status}）：${err.message}`
          : '加载失败：未知错误'
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadPlans() {
  plansLoading.value = true
  try {
    const data = await fetchPlans()
    plans.value = data.items
  } catch {
    // 计划面板失败不该影响主流程：静默，等下一次轮询
  } finally {
    plansLoading.value = false
  }
}

/** 实时事件 → 按需刷新。plan_step 意味着有人换了房间、计划状态也变了 */
function onTownEvent(event: TownEvent) {
  if (event.event_type === 'plan_step') {
    loadPlans()
    loadNpcs(true)
  }
}

function onChatted(result: ChatOut) {
  // 第一次聊天后才知道自己在数据库里的 id（后端 get_or_create 出来的）
  playerId.value = result.player_id
  loadPlans()
}

/** 点计划卡片 → 选中这个 NPC，右侧面板就变成和他的对话 */
function onPlanSelect(npcId: number) {
  const npc = npcs.value.find((item) => item.id === npcId)
  if (npc) selected.value = npc
}

let pollTimer: ReturnType<typeof setInterval> | undefined

onMounted(async () => {
  // 先握手拿身份 Cookie，再拉数据：后面的请求就都带签名身份了
  await ensureSession()
  await loadNpcs()
  loadPlans()
  pollTimer = setInterval(() => {
    loadPlans()
    loadNpcs(true)
  }, POLL_MS)
})

onBeforeUnmount(() => clearInterval(pollTimer))
</script>

<template>
  <main class="town">
    <header class="bar">
      <div class="brand">
        <h1>AI Town</h1>
        <p class="sub">WASD / 方向键移动 · 走近 NPC 按 E 对话</p>
      </div>

      <div class="meta">
        <span class="chip">居民 {{ npcs.length }}</span>
        <span class="chip">今日计划 {{ plans.filter((p) => p.total > 0).length }} 份</span>
        <label class="who">
          我是
          <input v-model="playerName" maxlength="16" spellcheck="false" />
        </label>
      </div>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <div v-else-if="error" class="error">
      <p>{{ error }}</p>
      <button @click="loadNpcs()">重试</button>
    </div>

    <template v-else>
      <!-- 左：小镇 + 今日计划；右：对话 + 事件流。
           左右分栏是为了把画布撑高 —— 上下堆叠时画布被压扁，
           世界的上下边缘会被裁掉。 -->
      <div class="stage">
        <!-- 左：画布（占满）+ 底部居民进度条 -->
        <section class="left">
          <div class="canvas-slot">
            <TownCanvas
              :npcs="npcs"
              :selected-task="selectedTask"
              @select="(npc) => (selected = npc)"
              @request-chat="(npc) => (selected = npc)"
            />
          </div>
          <NpcStrip :plans="plans" :selected-id="selected?.id ?? null" @select="onPlanSelect" />
        </section>

        <!-- 中：对话（选中的人才有他的今日计划） -->
        <section class="side">
          <ChatPanel
            :npc="selected"
            :player-name="playerName"
            :plan="selectedPlan"
            @chatted="onChatted"
          />
        </section>

        <!-- 右：小镇动态 -->
        <aside class="feed-slot">
          <EventFeed :player-id="playerId" @event="onTownEvent" />
        </aside>
      </div>
    </template>
  </main>
</template>

<style scoped>
.town {
  max-width: 1580px;
  margin: 0 auto;
  padding: 16px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  /* 桌面端锁死一屏：面板各自内部滚动，页面整体不滚 —— 画布才能拿到最大高度 */
  height: 100vh;
  min-height: 620px;
}

/* ---------- 顶栏 ---------- */
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.brand h1 { font-size: 20px; }
.sub { color: var(--muted); font-size: 12px; margin-top: 2px; }

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  font-size: 11px;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 2px 9px;
  white-space: nowrap;
}

.who {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
.who input {
  width: 104px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 5px 9px;
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.who input:focus { border-color: var(--accent); }

/* ---------- 分栏 ---------- */
.stage {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  /* 三列：画布（大） | 对话 | 动态
     计划不再独占一列 —— 三个 NPC × 4 步会占满一列还空一片，
     玩家真正关心的是"谁在干什么"，所以收进画布下方的居民进度条，
     选中谁、谁的计划才在对话面板里展开。 */
  grid-template-columns: minmax(0, 1fr) 336px 352px;
  grid-template-areas: "left side feed";
  gap: 12px;
}

.left {
  grid-area: left;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

/* 画布吃掉左列剩余高度；min-height:0 是关键，否则会被内容顶破 */
.canvas-slot {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
}

.side {
  grid-area: side;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.feed-slot {
  grid-area: feed;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 中等屏：画布仍占左侧整高，右列对话/动态上下分 */
@media (max-width: 1439px) {
  .stage {
    grid-template-columns: minmax(0, 1fr) 396px;
    grid-template-rows: minmax(0, 1.05fr) minmax(0, 1fr);
    grid-template-areas:
      "left side"
      "left feed";
  }
}

/* 窄屏：完全取消分栏，上下堆叠并允许整页滚动 */
@media (max-width: 1180px) {
  .town { height: auto; min-height: 100vh; }
  .stage {
    grid-template-columns: 1fr;
    grid-template-rows: none;
    grid-template-areas: "left" "side" "feed";
  }
  .left { height: clamp(460px, 62vh, 680px); }
  .side { height: 440px; }
  .feed-slot { height: 340px; }
}

.hint { color: var(--muted); margin-top: 16px; }

.error {
  border: 1px solid #5a2a2a;
  background: #1e1416;
  color: #ffb4b4;
  border-radius: 10px;
  padding: 16px;
}
.error button {
  margin-top: 10px;
  background: none;
  border: 1px solid #5a2a2a;
  color: #ffb4b4;
  border-radius: 6px;
  padding: 4px 12px;
  cursor: pointer;
}
</style>