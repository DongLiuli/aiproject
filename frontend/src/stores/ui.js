import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUIStore = defineStore('ui', () => {
  const showUploadModal = ref(false)
  const showSettingsModal = ref(false)

  function openUploadModal() {
    showUploadModal.value = true
  }

  function closeUploadModal() {
    showUploadModal.value = false
  }

  function openSettingsModal() {
    showSettingsModal.value = true
  }

  function closeSettingsModal() {
    showSettingsModal.value = false
  }

  return {
    showUploadModal,
    showSettingsModal,
    openUploadModal,
    closeUploadModal,
    openSettingsModal,
    closeSettingsModal,
  }
})
