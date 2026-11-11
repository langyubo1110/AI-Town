<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { TownScene } from '@/scene/town'
import type { Npc } from '@/types/api'

const props = defineProps<{ npcs: Npc[] }>()
const emit = defineEmits<{
  select: [npc: Npc | null]
  requestChat: [npc: Npc]
}>()

const host = ref<HTMLDivElement | null>(null)
let scene: TownScene | null = null

onMounted(async () => {
  if (!host.value) return
  scene = new TownScene({
    onSelect: (npc) => emit('select', npc),
    onRequestChat: (npc) => emit('requestChat', npc),
  })
  try {
    await scene.mount(host.value)
    scene.setNpcs(props.npcs)
  } catch (err) {
    // 场景初始化失败不能让页面静默白屏——把原因打出来
    console.error('[TownCanvas] 场景初始化失败：', err)
  }
})

watch(
  () => props.npcs,
  (next) => scene?.setNpcs(next),
)

onBeforeUnmount(() => {
  scene?.destroy()
  scene = null
})
</script>

<template>
  <div class="canvas-wrap">
    <div ref="host" class="canvas-host" />
    <p class="hint">WASD / 方向键 移动 · 走近 NPC 按 E 对话</p>
  </div>
</template>

<style scoped>
.canvas-wrap {
  position: relative;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.canvas-host {
  width: 100%;
  height: 480px;
}

.hint {
  position: absolute;
  left: 12px;
  bottom: 10px;
  font-size: 11px;
  color: var(--muted);
  background: rgba(10, 12, 16, 0.6);
  padding: 2px 8px;
  border-radius: 999px;
  pointer-events: none;
  user-select: none;
}
</style>