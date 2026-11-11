<script setup lang="ts">
import type { Npc } from '@/types/api'

defineProps<{ npc: Npc }>()
</script>

<template>
  <article class="card">
    <header>
      <h3>{{ npc.name }}</h3>
      <span class="title">{{ npc.title }}</span>
    </header>
    <p class="location">📍 {{ npc.location }}</p>
    <p class="line"><b>专长</b> {{ npc.expertise }}</p>
    <p class="line"><b>风格</b> {{ npc.style }}</p>
    <p class="line muted">{{ npc.personality }}</p>
  </article>
</template>

<style scoped>
.card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
header { display: flex; align-items: baseline; gap: 8px; }
h3 { font-size: 16px; }
.title {
  font-size: 12px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 0 8px;
}
.location { font-size: 12px; color: var(--muted); }
.line { font-size: 13px; }
.line b { color: var(--muted); font-weight: 500; margin-right: 6px; }
.muted { color: var(--muted); }
</style>