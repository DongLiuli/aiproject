<template>
  <div class="modal-overlay" @click.self="cancel">
    <div class="modal">
      <h2>📦 发现游客数据</h2>
      <p class="desc">检测到您之前以游客身份使用过本系统，有数据可以合并：</p>
      <div class="stats">
        <div class="stat-item">
          <span class="stat-number">{{ papersCount }}</span>
          <span class="stat-label">篇论文</span>
        </div>
        <div class="stat-item">
          <span class="stat-number">{{ conversationsCount }}</span>
          <span class="stat-label">条对话</span>
        </div>
      </div>
      <p class="hint">合并后数据将永久归属于当前账号，是否合并？</p>
      <div class="actions">
        <button class="btn-cancel" @click="cancel">忽略</button>
        <button class="btn-confirm" @click="confirm">合并数据</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  papersCount: { type: Number, default: 0 },
  conversationsCount: { type: Number, default: 0 },
})
const emit = defineEmits(['confirm', 'cancel'])

function confirm() {
  emit('confirm')
}

function cancel() {
  emit('cancel')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal {
  background: white; border-radius: 16px; padding: 32px; max-width: 420px; width: 90%;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
}
h2 { margin: 0 0 8px 0; font-size: 1.5rem; color: #1a1a1a; }
.desc { color: #666; font-size: 0.95rem; line-height: 1.6; margin-bottom: 20px; }
.stats { display: flex; gap: 24px; justify-content: center; padding: 16px; background: #f5f7fa; border-radius: 12px; margin-bottom: 20px; }
.stat-item { text-align: center; }
.stat-number { display: block; font-size: 2rem; font-weight: 700; color: #667eea; }
.stat-label { font-size: 0.85rem; color: #888; }
.hint { font-size: 0.9rem; color: #888; text-align: center; margin-bottom: 24px; }
.actions { display: flex; gap: 12px; justify-content: center; }
.actions button { padding: 10px 24px; border-radius: 8px; font-size: 0.95rem; cursor: pointer; }
.btn-cancel { background: #f0f0f0; border: none; color: #666; }
.btn-cancel:hover { background: #e0e0e0; }
.btn-confirm { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; color: white; }
.btn-confirm:hover { opacity: 0.9; }
</style>
