<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import TownCanvas from '@/components/TownCanvas.vue'
import ChatPanel from '@/components/ChatPanel.vue'
import EventFeed from '@/components/EventFeed.vue'
import { fetchNpcs } from '@/api/npc'
import { ApiError } from '@/api/http'
import type { ChatOut, Npc } from '@/types/api'

const STORAGE_KEY = 'aitown.playerName'

const npcs = ref<Npc[]>([])
const loading = ref(true)
const error = ref('')
const selected = ref<Npc | null>(null)
const playerName = ref(localStorage.getItem(STORAGE_KEY) || '小明')
const playerId = ref<number | null>(null)

watch(playerName, (name) => {
  localStorage.setItem(STORAGE_KEY, name)
  // 换名字等于换玩家：旧的事件流不再属于他
  playerId.value = null
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchNpcs()
    npcs.value = data.items
  } catch (err) {
    error.value =
      err instanceof ApiError
        ? `加载失败（${err.status}）：${err.message}`
        : '加载失败：未知错误'
  } finally {
    loading.value = false
  }
}

function onChatted(result: ChatOut) {
  // 第一次聊天后才知道自己在数据库里的 id（后端 get_or_create 出来的）
  playerId.value = result.player_id
}

onMounted(load)
</script>

<template>
  <main class="town">
    <header class="bar">
      <div>
        <h1>AI Town</h1>
        <p class="sub">在镇子上走走，遇到人就聊两句</p>
      </div>
      <label class="who">
        我是
        <input v-model="playerName" maxlength="16" spellcheck="false" />
      </label>
    </header>

    <p v-if="loading" class="hint">加载中…</p>
    <div v-else-if="error" class="error">
      <p>{{ error }}</p>
      <button @click="load">重试</button>
    </div>

    <template v-else>
      <TownCanvas
        :npcs="npcs"
        @select="(npc) => (selected = npc)"
        @request-chat="(npc) => (selected = npc)"
      />

      <div class="panels">
        <ChatPanel :npc="selected" :player-name="playerName" @chatted="onChatted" />
        <EventFeed :player-id="playerId" />
      </div>
    </template>
  </main>
</template>

<style scoped>
.town {
  max-width: 1180px;
  margin: 0 auto;
  padding: 24px 20px 60px;
}

.bar {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
h1 { font-size: 22px; }
.sub { color: var(--muted); font-size: 13px; margin-top: 2px; }

.who {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--muted);
}
.who input {
  width: 110px;
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

.panels {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(0, 1fr);
  gap: 16px;
  margin-top: 16px;
  align-items: start;
}

@media (max-width: 900px) {
  .panels { grid-template-columns: 1fr; }
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