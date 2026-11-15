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
  </div>
</template>

<style scoped>
.canvas-wrap {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  min-height: 400px;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.canvas-host {
  flex: 1 1 auto;
  min-width: 0;
  height: 100%;
}
</style>