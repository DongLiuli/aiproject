<script setup>
import { ref, computed } from 'vue'
import { BookOpen, ChevronDown, ChevronRight, Copy, FileText } from 'lucide-vue-next'

const props = defineProps({
  paper: {
    type: Object,
    default: () => ({}),
  },
})

const expandedSections = ref(new Set())

const paperSections = computed(() => {
  const items = []

  if (props.paper.sections && Array.isArray(props.paper.sections)) {
    props.paper.sections.forEach((section, index) => {
      if (section.title || section.content) {
        items.push({
          id: `section-${index}`,
          title: section.title || `章节 ${index + 1}`,
          content: section.content || '',
        })
      }
    })
  }

  if (props.paper.full_text && items.length === 0) {
    items.push({
      id: 'full-text',
      title: '全文',
      content: props.paper.full_text,
    })
  }

  return items
})

function toggleSection(id) {
  if (expandedSections.value.has(id)) {
    expandedSections.value.delete(id)
  } else {
    expandedSections.value.add(id)
  }
  expandedSections.value = new Set(expandedSections.value)
}

async function copyContent(content) {
  try {
    await navigator.clipboard.writeText(content)
  } catch (err) {
    console.error('Copy failed:', err)
  }
}
</script>

<template>
  <div class="content-container">
    <div class="content-header">
      <BookOpen class="content-icon" />
      <h3>论文内容</h3>
    </div>

    <div class="content-sections">
      <div v-if="paperSections.length === 0" class="empty-state">
        <FileText class="empty-icon" />
        <p>暂无论文内容</p>
      </div>

      <div v-for="section in paperSections" :key="section.id" class="section-item">
        <div class="section-header" @click="toggleSection(section.id)">
          <button class="expand-btn">
            <ChevronDown v-if="expandedSections.has(section.id)" class="expand-icon" />
            <ChevronRight v-else class="expand-icon" />
          </button>
          <h4 class="section-title">{{ section.title }}</h4>
          <button class="copy-btn" @click.stop="copyContent(section.content)" title="复制内容">
            <Copy class="copy-icon" />
          </button>
        </div>

        <div v-if="expandedSections.has(section.id)" class="section-content">
          <p>{{ section.content }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.content-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.content-icon {
  width: 20px;
  height: 20px;
  color: #667eea;
}

.content-header h3 {
  font-size: 1rem;
  font-weight: 600;
  color: #333;
}

.content-sections {
  padding: 8px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: #999;
}

.empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 16px;
}

.empty-state p {
  margin: 0;
  font-size: 0.9375rem;
}

.section-item {
  margin-bottom: 4px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.2s;
}

.section-header:hover {
  background: #fafafa;
}

.expand-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
}

.expand-icon {
  width: 16px;
  height: 16px;
  color: #999;
}

.section-title {
  flex: 1;
  font-size: 0.9375rem;
  font-weight: 500;
  color: #333;
  margin: 0;
}

.copy-btn {
  width: 28px;
  height: 28px;
  background: #f0f0f0;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.copy-btn:hover {
  background: #e0e0e0;
}

.copy-icon {
  width: 14px;
  height: 14px;
  color: #666;
}

.section-content {
  padding: 0 16px 16px 48px;
}

.section-content p {
  margin: 0;
  font-size: 0.9375rem;
  line-height: 1.8;
  color: #444;
}
</style>
