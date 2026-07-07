<script setup>
import { computed } from 'vue'
import { ArrowRight } from 'lucide-vue-next'

const props = defineProps({
  paper: { type: Object, required: true },
  reason: { type: String, default: '' },
  source: { type: String, default: 'tag' }, // 'admin' | 'tag'
})

const emit = defineEmits(['view'])

// 领域 → 稳定色相，仅用于左侧一条细色条（信息编码：一眼辨领域），卡片主体保持中性白
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
      <!-- 来源区分：填充=管理员精选，描边=系统按兴趣推荐（同形同字号，务实克制） -->
      <span class="badge" :class="source === 'admin' ? 'badge-solid' : 'badge-outline'">
        {{ source === 'admin' ? '精选' : '推荐' }}
      </span>
      <span v-if="paper.field" class="field-chip">{{ paper.field }}</span>
    </div>

    <h3 class="card-title" :title="title">{{ title }}</h3>

    <div class="divider"></div>

    <p class="card-author">{{ authorLine }}</p>

    <!-- admin 卡已有「精选」徽章，理由（管理员精选）冗余，仅 tag 卡显示命中理由 -->
    <p class="reason-line" v-if="reason && source !== 'admin'">{{ reason }}</p>

    <div class="card-foot">
      <span class="read-link">去阅读 <ArrowRight class="read-icon" /></span>
    </div>
  </div>
</template>

<style scoped>
.recommend-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 180px;
  padding: 14px 16px 14px 18px;
  border: 1px solid #e5e7eb;
  border-left: 3px solid hsl(var(--hue), 55%, 55%); /* 学科色条：唯一的彩色信息编码 */
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}
.recommend-card:hover {
  transform: translateY(-2px);
  border-color: #d1d5db;
  border-left-color: hsl(var(--hue), 60%, 48%);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.1);
}

.card-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

/* 徽章：统一尺寸/字号，仅填充 vs 描边区分来源 */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  font-size: 0.72rem;
  font-weight: 600;
  border-radius: 6px;
  letter-spacing: 0.3px;
}
.badge-solid {
  color: #fff;
  background: #4f46e5;
}
.badge-outline {
  color: #4f46e5;
  background: transparent;
  border: 1px solid #c7d2fe;
}

.field-chip {
  margin-left: auto;
  padding: 2px 9px;
  font-size: 0.7rem;
  font-weight: 500;
  color: #6b7280;
  background: #f3f4f6;
  border-radius: 6px;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.45;
  color: #111827;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.divider {
  height: 1px;
  margin: 10px 0;
  background: #f0f0f0;
}

.card-author {
  margin: 0;
  font-size: 0.8rem;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reason-line {
  margin: 8px 0 0;
  font-size: 0.76rem;
  color: #9ca3af;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  font-size: 0.8rem;
  font-weight: 600;
  color: #4f46e5;
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
