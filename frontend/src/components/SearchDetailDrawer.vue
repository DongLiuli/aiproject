<script setup>
import { computed } from 'vue'
import { X, ExternalLink, Plus, Check, Quote } from 'lucide-vue-next'

const props = defineProps({
  paper: { type: Object, default: null },
  adding: { type: Boolean, default: false },
  added: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'add'])

const canAdd = computed(() => !!props.paper?.pdf_url)
const authorsText = computed(() => {
  const a = props.paper?.authors || []
  return a.length ? a.join('、') : '未知作者'
})
</script>

<template>
  <div v-if="paper" class="drawer-mask" @click.self="emit('close')">
    <aside class="drawer">
      <button class="close-btn" @click="emit('close')"><X class="ci" /></button>

      <h2 class="d-title">{{ paper.title }}</h2>

      <div class="d-meta">
        <span>{{ authorsText }}</span>
        <span v-if="paper.year"> · {{ paper.year }}</span>
        <span v-if="paper.venue"> · {{ paper.venue }}</span>
      </div>
      <div class="d-cited"><Quote class="ci" />被引 {{ paper.cited_by_count || 0 }} 次</div>

      <div v-if="(paper.topics || []).length" class="d-topics">
        <span v-for="t in paper.topics.slice(0, 4)" :key="t.name" class="topic-tag">{{ t.name }}</span>
      </div>

      <h3 class="d-sub">摘要</h3>
      <p class="d-abstract">{{ paper.abstract || '（该论文未提供摘要）' }}</p>

      <div class="d-actions">
        <a v-if="paper.url" :href="paper.url" target="_blank" rel="noopener" class="link-btn">
          <ExternalLink class="ci" />查看原文
        </a>
        <button
          v-if="added"
          class="add-btn done"
          disabled
        >
          <Check class="ci" />已加入知识库
        </button>
        <button
          v-else
          class="add-btn"
          :disabled="!canAdd || adding"
          :title="canAdd ? '下载开放获取 PDF 并加入知识库' : '无开放获取 PDF，无法加入'"
          @click="emit('add', paper)"
        >
          <Plus class="ci" />{{ adding ? '加入中…' : '加入知识库' }}
        </button>
      </div>
      <p v-if="!canAdd" class="no-pdf-hint">该论文无开放获取 PDF，暂无法加入知识库深读。</p>
    </aside>
  </div>
</template>

<style scoped>
.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  z-index: 100;
  display: flex;
  justify-content: flex-end;
}

.drawer {
  width: 480px;
  max-width: 92vw;
  height: 100%;
  background: #fff;
  padding: 28px;
  overflow-y: auto;
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.1);
}

.close-btn {
  position: absolute;
  top: 20px;
  right: 20px;
  background: #f3f4f6;
  border: none;
  border-radius: 8px;
  padding: 6px;
  cursor: pointer;
}

.d-title {
  font-size: 1.2rem;
  font-weight: 700;
  color: #1f2937;
  line-height: 1.4;
  margin: 8px 40px 12px 0;
}

.d-meta {
  color: #6b7280;
  font-size: 0.88rem;
  margin-bottom: 8px;
}

.d-cited {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #7c3aed;
  font-weight: 600;
  font-size: 0.88rem;
  margin-bottom: 12px;
}

.d-topics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.topic-tag {
  background: #f5f3ff;
  color: #7c3aed;
  font-size: 0.78rem;
  padding: 3px 10px;
  border-radius: 12px;
}

.d-sub {
  font-size: 0.95rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
}

.d-abstract {
  color: #4b5563;
  font-size: 0.9rem;
  line-height: 1.7;
  margin-bottom: 24px;
  white-space: pre-wrap;
}

.d-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.link-btn,
.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 0.9rem;
  cursor: pointer;
  text-decoration: none;
  border: none;
}

.link-btn {
  background: #f3f4f6;
  color: #374151;
}

.link-btn:hover {
  background: #e5e7eb;
}

.add-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
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

.ci {
  width: 16px;
  height: 16px;
}

.no-pdf-hint {
  margin-top: 12px;
  font-size: 0.82rem;
  color: #9ca3af;
}
</style>
