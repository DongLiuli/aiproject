import { defineStore } from 'pinia';
import { ref } from 'vue';
import { userAPI } from '@/api';
export const useUserStore = defineStore('user', () => {
 const config = ref({
 llm_api_key: '',
 llm_model: 'deepseek-chat',
 llm_base_url: 'https://api.deepseek.com',
 });
 const loading = ref(false);
 async function fetchConfig() {
 loading.value = true;
 try {
 const response = await userAPI.getConfig();
 config.value = { ...config.value, ...response };
 }
 catch (error) {
 console.error('Failed to fetch config:', error);
 }
 finally {
 loading.value = false;
 }
 }
 async function updateConfig(newConfig) {
 try {
 config.value = { ...config.value, ...newConfig };
 await userAPI.updateConfig(config.value);
 }
 catch (error) {
 throw error;
 }
 }
 async function testConfig() {
 try {
 const response = await userAPI.testConfig(config.value);
 return response.ok;
 }
 catch (error) {
 return false;
 }
 }
 return {
 config,
 loading,
 fetchConfig,
 updateConfig,
 testConfig,
 };
});
