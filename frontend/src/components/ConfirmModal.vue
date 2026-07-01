<template>
  <div class="modal-overlay" @click.self="onCancel">
    <div class="modal">
      <h2>{{ title }}</h2>
      <p class="message">{{ message }}</p>
      <div class="actions">
        <button v-if="cancelText" class="btn-cancel" @click="onCancel">{{ cancelText }}</button>
        <button class="btn-confirm" :class="{ danger }" @click="onConfirm">{{ confirmText }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '提示' },
  message: { type: String, default: '' },
  confirmText: { type: String, default: '确定' },
  // cancelText 为空时隐藏取消按钮（提示模式，仅一个确定）
  cancelText: { type: String, default: '取消' },
  danger: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'cancel'])
function onConfirm() {
  emit('confirm')
}
function onCancel() {
  emit('cancel')
}
</script>

<style scoped>
.modal-overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; z-index: 1100;
}
.modal {
  background: white; border-radius: 16px; padding: 28px 32px; max-width: 400px; width: 90%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}
h2 { margin: 0 0 12px 0; font-size: 1.25rem; color: #1a1a1a; }
.message { color: #666; font-size: 0.95rem; line-height: 1.6; margin-bottom: 24px; }
.actions { display: flex; gap: 12px; justify-content: flex-end; }
.actions button { padding: 10px 24px; border-radius: 8px; font-size: 0.95rem; cursor: pointer; border: none; }
.btn-cancel { background: #f0f0f0; color: #666; }
.btn-cancel:hover { background: #e0e0e0; }
.btn-confirm { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
.btn-confirm:hover { opacity: 0.9; }
.btn-confirm.danger { background: #dc2626; }
.btn-confirm.danger:hover { background: #b91c1c; }
</style>
