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
 config.value = {
 ...config.value,
 llm_api_key: response.api_key || '',
 llm_model: response.model || 'deepseek-chat',
 };
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
 await userAPI.updateConfig({
 api_key: config.value.llm_api_key,
 model: config.value.llm_model,
 });
 }
 catch (error) {
 throw error;
 }
 }
 async function testConfig() {
 try {
 const response = await userAPI.testConfig();
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
