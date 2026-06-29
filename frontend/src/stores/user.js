import { defineStore } from 'pinia'
import { ref } from 'vue'
import { userAPI } from '@/api'

const LOCAL_STORAGE_KEY = 'lit-ai-user-config'

export const useUserStore = defineStore('user', () => {
  const config = ref({
    llm_api_key: '',
    llm_model: 'deepseek-chat',
    llm_base_url: 'https://api.deepseek.com',
  })
  const loading = ref(false)
  // 后端真值：当前 session/用户在服务端是否已配置 API Key
  // （本地 llm_api_key 会随浏览器残留，不能作为「已配置」的判据，详见 #1）
  const apiKeyConfigured = ref(false)

  function loadLocalConfig() {
    try {
      const saved = localStorage.getItem(LOCAL_STORAGE_KEY)
      if (saved) {
        const parsed = JSON.parse(saved)
        config.value = { ...config.value, ...parsed }
      }
    } catch (error) {
      console.warn('Failed to load local config:', error)
    }
  }

  function saveLocalConfig() {
    try {
      localStorage.setItem(
        LOCAL_STORAGE_KEY,
        JSON.stringify({
          llm_api_key: config.value.llm_api_key,
          llm_model: config.value.llm_model,
          llm_base_url: config.value.llm_base_url,
        }),
      )
    } catch (error) {
      console.warn('Failed to save local config:', error)
    }
  }

  async function fetchConfig() {
    loading.value = true
    try {
      const response = await userAPI.getConfig()
      config.value = {
        ...config.value,
        llm_model: response.model || 'deepseek-chat',
      }
      apiKeyConfigured.value = !!response.api_key_configured
      saveLocalConfig()
    } catch (error) {
      console.error('Failed to fetch config from API:', error)
      apiKeyConfigured.value = false
      loadLocalConfig()
    } finally {
      loading.value = false
    }
  }

  async function updateConfig(newConfig) {
    config.value = { ...config.value, ...newConfig }
    saveLocalConfig()

    try {
      const response = await userAPI.updateConfig({
        api_key: config.value.llm_api_key,
        model: config.value.llm_model,
      })
      apiKeyConfigured.value = !!response.api_key_configured
      return { success: true, message: '配置保存成功' }
    } catch (error) {
      console.warn('API save failed, using local storage:', error)
      return { success: true, message: '配置已保存到本地', localOnly: true }
    }
  }

  async function testConfig(cfg) {
    try {
      const response = await userAPI.testConfig({
        api_key: cfg?.llm_api_key || config.value.llm_api_key,
        model: cfg?.llm_model || config.value.llm_model,
      })
      return response.ok
    } catch (error) {
      return false
    }
  }

  return {
    config,
    loading,
    apiKeyConfigured,
    fetchConfig,
    updateConfig,
    testConfig,
    loadLocalConfig,
  }
})
