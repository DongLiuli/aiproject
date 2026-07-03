<script setup>
import { computed } from 'vue'
import { Flame, ArrowRight, Lightbulb } from 'lucide-vue-next'

const props = defineProps({
  paper: { type: Object, required: true },
  reason: { type: String, default: '' },
  source: { type: String, default: 'tag' }, // 'admin' | 'tag'
})

const emit = defineEmits(['view'])

// 领域 → 稳定色相（无 field 用默认蓝），用于整卡渐变与色标
const hue = computed(() => {
  const field = props.paper.field
  if (!field) return 220
  let h = 0
  for (let i = 0; i < field.length; i++) h = (h * 31 + field.charCodeAt(i)) % 360
  return h
})

const authorLine = computed(() => {
  const authors = props.paper.authors || []
  if (authors.length === 0) return props.paper.field || '未知作者'
  return authors.length > 1 ? `${authors[0]} 等` : authors[0]
})

const title = computed(() => props.paper.title || props.paper.file_name || '未命名论文')

function handleClick() {
  emit('view', props.paper)
}
</script>

<template>
  <div
    class="recommend-card"
    :style="{ '--hue': hue }"
    @click="handleClick"
    role="button"
    tabindex="0"
    @keydown.enter="handleClick"
  >
    <div class="card-top">
      <span v-if="source === 'admin'" class="badge-featured">
        <Flame class="badge-icon" />
        精选
      </span>
      <span v-else class="badge-featured badge-tag">
        <Flame class="badge-icon" />
        推荐
      </span>
      <span v-if="paper.field" class="field-chip">{{ paper.field }}</span>
    </div>

    <h3 class="card-title" :title="title">{{ title }}</h3>

    <div class="divider"></div>

    <p class="card-author">{{ authorLine }}</p>

    <div class="reason-pill" v-if="reason">
      <Lightbulb class="reason-icon" />
      <span>{{ reason }}</span>
    </div>

    <div class="card-foot">
      <span class="read-link">去阅读 <ArrowRight class="read-icon" /></span>
    </div>
  </div>
</template>

<style scoped>
.recommend-card {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 190px;
  padding: 16px 18px;
  border-radius: 16px;
  cursor: pointer;
  border: 1px solid hsla(var(--hue), 60%, 70%, 0.35);
  background:
    linear-gradient(135deg, hsla(var(--hue), 85%, 96%, 0.95) 0%, hsla(var(--hue), 70%, 99%, 0.9) 55%, #ffffff 100%);
  box-shadow: 0 2px 10px hsla(var(--hue), 40%, 60%, 0.12);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.recommend-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 28px hsla(var(--hue), 45%, 55%, 0.28);
}
/* hover 光泽扫过 */
.recommend-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: -70%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    120deg,
    transparent 0%,
    hsla(0, 0%, 100%, 0.55) 50%,
    transparent 100%
  );
  transform: skewX(-20deg);
  transition: left 0.6s ease;
  pointer-events: none;
}
.recommend-card:hover::before {
  left: 130%;
}

.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.badge-featured {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  font-size: 0.72rem;
  font-weight: 600;
  color: #fff;
  border-radius: 999px;
  background: linear-gradient(135deg, #f97316, #ef4444);
}
.badge-featured.badge-tag {
  background: linear-gradient(135deg, hsl(var(--hue), 75%, 58%), hsl(var(--hue), 70%, 45%));
}
.badge-icon {
  width: 12px;
  height: 12px;
}
.field-chip {
  margin-left: auto;
  padding: 2px 9px;
  font-size: 0.7rem;
  font-weight: 500;
  color: hsl(var(--hue), 60%, 35%);
  background: hsla(var(--hue), 70%, 88%, 0.7);
  border-radius: 999px;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-title {
  margin: 0;
  font-size: 0.98rem;
  font-weight: 600;
  line-height: 1.4;
  color: #1f2937;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.divider {
  height: 1px;
  margin: 10px 0;
  background: hsla(var(--hue), 40%, 70%, 0.35);
}
.card-author {
  margin: 0;
  font-size: 0.8rem;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reason-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-top: 12px;
  padding: 4px 10px;
  font-size: 0.75rem;
  color: hsl(var(--hue), 55%, 32%);
  background: hsla(var(--hue), 75%, 90%, 0.75);
  border-radius: 999px;
  max-width: 100%;
}
.reason-pill span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.reason-icon {
  width: 13px;
  height: 13px;
  flex-shrink: 0;
}

.card-foot {
  margin-top: auto;
  padding-top: 12px;
  display: flex;
  justify-content: flex-end;
}
.read-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.82rem;
  font-weight: 600;
  color: hsl(var(--hue), 65%, 45%);
}
.read-icon {
  width: 14px;
  height: 14px;
  transition: transform 0.2s ease;
}
.recommend-card:hover .read-icon {
  transform: translateX(3px);
}
</style>
