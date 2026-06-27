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
      saveLocalConfig()
    } catch (error) {
      console.error('Failed to fetch config from API:', error)
      loadLocalConfig()
    } finally {
      loading.value = false
    }
  }

  async function updateConfig(newConfig) {
    config.value = { ...config.value, ...newConfig }
    saveLocalConfig()

    try {
      await userAPI.updateConfig({
        api_key: config.value.llm_api_key,
        model: config.value.llm_model,
      })
      return { success: true, message: '配置保存成功' }
    } catch (error) {
      console.warn('API save failed, using local storage:', error)
      return { success: true, message: '配置已保存到本地', localOnly: true }
    }
  }

  async function testConfig() {
    try {
      const response = await userAPI.testConfig({
        api_key: config.value.llm_api_key,
        model: config.value.llm_model,
      })
      return response.ok
    } catch (error) {
      return false
    }
  }

  return {
    config,
    loading,
    fetchConfig,
    updateConfig,
    testConfig,
    loadLocalConfig,
  }
})
