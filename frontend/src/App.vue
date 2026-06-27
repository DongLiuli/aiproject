<script setup>
import { onMounted } from 'vue'
import Layout from '@/components/Layout.vue'
import UploadModal from '@/components/UploadModal.vue'
import SettingsModal from '@/components/SettingsModal.vue'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'

const authStore = useAuthStore()
const uiStore = useUIStore()
const userStore = useUserStore()

onMounted(async () => {
  userStore.loadLocalConfig()
  await authStore.initialize()
})
</script>

<template>
  <Layout>
    <router-view />
  </Layout>

  <UploadModal v-if="uiStore.showUploadModal" @close="uiStore.closeUploadModal" />

  <SettingsModal v-if="uiStore.showSettingsModal" @close="uiStore.closeSettingsModal" />
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans',
    'Helvetica Neue', sans-serif;
  background: #f5f7fa;
  color: #1a1a1a;
  line-height: 1.6;
}

#app {
  min-height: 100vh;
}

::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}
</style>
