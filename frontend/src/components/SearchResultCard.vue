<script setup>
import { computed } from 'vue'
import { Quote, Users, Calendar, BookMarked, Plus, Check } from 'lucide-vue-next'

const props = defineProps({
  paper: { type: Object, required: true },
  index: { type: Number, required: true },
  selected: { type: Boolean, default: false },
  adding: { type: Boolean, default: false },
  added: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-select', 'add', 'open'])

const canAdd = computed(() => !!props.paper.pdf_url)

const authorsText = computed(() => {
  const a = props.paper.authors || []
  if (!a.length) return '未知作者'
  return a.length > 3 ? a.slice(0, 3).join('、') + ' 等' : a.join('、')
})

// 客户端派生「被选中理由」：主研究方向 + 高被引提示（避免额外 LLM 成本）
const reason = computed(() => {
  const parts = []
  const topTopic = (props.paper.topics || [])[0]
  if (topTopic?.name) parts.push(`研究方向：${topTopic.name}`)
  const cited = props.paper.cited_by_count || 0
  if (cited >= 100) parts.push(`高被引 ${cited} 次`)
  return parts.join(' · ')
})
</script>

<template>
  <div class="result-card" :class="{ selected }">
    <input
      type="checkbox"
      class="select-box"
      :checked="selected"
      @click.stop="emit('toggle-select', index)"
    />

    <div class="card-body" @click="emit('open', paper)">
      <h3 class="card-title">{{ paper.title }}</h3>

      <div class="card-meta">
        <span class="meta"><Users class="mi" />{{ authorsText }}</span>
        <span v-if="paper.year" class="meta"><Calendar class="mi" />{{ paper.year }}</span>
        <span v-if="paper.venue" class="meta"><BookMarked class="mi" />{{ paper.venue }}</span>
        <span class="meta cited"><Quote class="mi" />被引 {{ paper.cited_by_count || 0 }}</span>
      </div>

      <div v-if="reason" class="card-reason">{{ reason }}</div>
    </div>

    <div class="card-actions">
      <button
        v-if="added"
        class="add-btn done"
        disabled
      >
        <Check class="ai" />已加入
      </button>
      <button
        v-else
        class="add-btn"
        :disabled="!canAdd || adding"
        :title="canAdd ? '下载开放获取 PDF 并加入知识库' : '无开放获取 PDF，无法加入'"
        @click.stop="emit('add', paper)"
      >
        <Plus class="ai" />{{ adding ? '加入中…' : '加入知识库' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.result-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  transition: box-shadow 0.2s, border-color 0.2s;
}

.result-card:hover {
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
  border-color: #c7d2fe;
}

.result-card.selected {
  border-color: #7c3aed;
  background: #faf5ff;
}

.select-box {
  margin-top: 4px;
  width: 16px;
  height: 16px;
  cursor: pointer;
  flex-shrink: 0;
}

.card-body {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
  line-height: 1.4;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 0.82rem;
  color: #6b7280;
}

.meta {
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta.cited {
  color: #7c3aed;
  font-weight: 600;
}

.mi {
  width: 14px;
  height: 14px;
}

.card-reason {
  margin-top: 8px;
  font-size: 0.8rem;
  color: #9333ea;
  background: #f5f3ff;
  padding: 4px 10px;
  border-radius: 6px;
  display: inline-block;
}

.card-actions {
  flex-shrink: 0;
}

.add-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border: none;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 0.85rem;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.2s;
}

.add-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.add-btn:disabled {
  background: #e5e7eb;
  color: #9ca3af;
  cursor: not-allowed;
}

.add-btn.done {
  background: #dcfce7;
  color: #16a34a;
}

.ai {
  width: 15px;
  height: 15px;
}
</style>
