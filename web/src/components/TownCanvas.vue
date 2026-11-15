<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { TownScene } from '@/scene/town'
import type { Npc } from '@/types/api'

const props = defineProps<{
  npcs: Npc[]
  /** 选中的 NPC + 他当前那一步（显示在头顶浮标里） */
  selectedTask?: { id: number; text: string } | null
}>()
const emit = defineEmits<{
  select: [npc: Npc | null]
  requestChat: [npc: Npc]
}>()

const host = ref<HTMLDivElement | null>(null)
let scene: TownScene | null = null
let observer: ResizeObserver | null = null

onMounted(async () => {
  if (!host.value) return
  scene = new TownScene({
    onSelect: (npc) => emit('select', npc),
    onRequestChat: (npc) => emit('requestChat', npc),
  })
  try {
    await scene.mount(host.value)
    scene.setNpcs(props.npcs)
    scene.setSelectedTask(
      props.selectedTask?.id ?? null,
      props.selectedTask?.text ?? null,
    )

    // PixiJS 的 resizeTo 只跟 window resize；布局变化（栅格列数切换、
    // 计划面板加载后把画布撑高）它感知不到，画布会用着旧尺寸把世界画偏。
    // 用 ResizeObserver 盯住真实尺寸，变化就同步过去。
    observer = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect
      if (rect && rect.width > 0 && rect.height > 0) {
        scene?.resize(rect.width, rect.height)
      }
    })
    observer.observe(host.value)
  } catch (err) {
    // 场景初始化失败不能让页面静默白屏——把原因打出来
    console.error('[TownCanvas] 场景初始化失败：', err)
  }
})

watch(
  () => props.npcs,
  (next) => scene?.setNpcs(next),
)

// 选中的人变了 → 把他"现在在干什么"浮在头顶
watch(
  () => props.selectedTask,
  (next) => {
    scene?.setSelectedTask(next?.id ?? null, next?.text ?? null)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
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