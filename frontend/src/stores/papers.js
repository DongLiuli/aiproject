import { defineStore } from 'pinia';
import { ref } from 'vue';
import { papersAPI, qaAPI, reportsAPI } from '@/api';
export const usePapersStore = defineStore('papers', () => {
 const papers = ref([]);
 const currentPaper = ref(null);
 const loading = ref(false);
 const uploading = ref(false);
 async function fetchPapers() {
 loading.value = true;
 try {
 const response = await papersAPI.list();
 papers.value = response.data || response;
 }
 catch (error) {
 console.error('Failed to fetch papers:', error);
 }
 finally {
 loading.value = false;
 }
 }
 async function uploadPaper(file) {
 uploading.value = true;
 try {
 const formData = new FormData();
 formData.append('file', file);
 const response = await papersAPI.upload(formData);
 await fetchPapers();
 return response;
 }
 catch (error) {
 throw error;
 }
 finally {
 uploading.value = false;
 }
 }
 async function getPaper(paperId) {
 loading.value = true;
 try {
 const response = await papersAPI.get(paperId);
 currentPaper.value = response.data || response;
 return currentPaper.value;
 }
 catch (error) {
 throw error;
 }
 finally {
 loading.value = false;
 }
 }
 async function updatePaper(paperId, data) {
 try {
 const response = await papersAPI.update(paperId, data);
 const index = papers.value.findIndex(p => p.id === paperId);
 if (index !== -1) {
 papers.value[index] = { ...papers.value[index], ...response };
 }
 if (currentPaper.value?.id === paperId) {
 currentPaper.value = { ...currentPaper.value, ...response };
 }
 return response;
 }
 catch (error) {
 throw error;
 }
 }
 async function deletePaper(paperId) {
 try {
 await papersAPI.delete(paperId);
 papers.value = papers.value.filter(p => p.id !== paperId);
 if (currentPaper.value?.id === paperId) {
 currentPaper.value = null;
 }
 }
 catch (error) {
 throw error;
 }
 }
 async function reparsePaper(paperId) {
 try {
 await papersAPI.reparse(paperId);
 await fetchPapers();
 }
 catch (error) {
 throw error;
 }
 }
 return {
 papers,
 currentPaper,
 loading,
 uploading,
 fetchPapers,
 uploadPaper,
 getPaper,
 updatePaper,
 deletePaper,
 reparsePaper,
 };
});
export const useQAStore = defineStore('qa', () => {
 const conversations = ref({});
 const currentQuestion = ref('');
 const answering = ref(false);
 async function askQuestion(paperId, question, conversationId = null) {
 answering.value = true;
 try {
 const response = await qaAPI.ask(paperId, question, conversationId);
 if (!conversations.value[paperId]) {
 conversations.value[paperId] = [];
 }
 conversations.value[paperId].push({
 question,
 answer: response.answer,
 sources: response.sources || [],
 timestamp: new Date().toISOString(),
 });
 return response;
 }
 catch (error) {
 throw error;
 }
 finally {
 answering.value = false;
 }
 }
 async function getConversationHistory(paperId) {
 try {
 const response = await qaAPI.getHistory(paperId);
 conversations.value[paperId] = response.data || response;
 return conversations.value[paperId];
 }
 catch (error) {
 throw error;
 }
 }
 function clearConversation(paperId) {
 conversations.value[paperId] = [];
 }
 return {
 conversations,
 currentQuestion,
 answering,
 askQuestion,
 getConversationHistory,
 clearConversation,
 };
});
export const useReportsStore = defineStore('reports', () => {
 const reports = ref({});
 const generating = ref(false);
 async function generateReport(paperId, reportType) {
 generating.value = true;
 try {
 const response = await reportsAPI.generate(paperId, reportType);
 if (!reports.value[paperId]) {
 reports.value[paperId] = {};
 }
 reports.value[paperId][reportType] = response.content;
 return response.content;
 }
 catch (error) {
 throw error;
 }
 finally {
 generating.value = false;
 }
 }
 function getReport(paperId, reportType) {
 return reports.value[paperId]?.[reportType];
 }
 return {
 reports,
 generating,
 generateReport,
 getReport,
 };
});
