"""LLM 客户端模块"""
import requests
import json
from typing import Dict, Any, Optional
from .config import LLM_CONFIG


class LLMClient:
    """LLM API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None, provider: str = "deepseek"):
        self.api_key = api_key or LLM_CONFIG["api_key"]
        self.provider = provider
        self.max_tokens = LLM_CONFIG["max_tokens"]
        self.temperature = LLM_CONFIG["temperature"]
        self.timeout = LLM_CONFIG["timeout"]
    
    def call(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """
        调用 LLM API
        
        :param prompt: 用户提示
        :param system_prompt: 系统提示
        :return: 响应结果
        """
        if not self.api_key:
            return {"success": False, "error": "API Key 未配置"}
        
        try:
            if self.provider == "deepseek":
                return self._call_deepseek(prompt, system_prompt)
            elif self.provider == "qwen":
                return self._call_qwen(prompt, system_prompt)
            else:
                return {"success": False, "error": f"不支持的 provider: {self.provider}"}
        
        except requests.exceptions.Timeout:
            return {"success": False, "error": "请求超时"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"请求失败: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"未知错误: {str(e)}"}
    
    def _call_deepseek(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """调用 DeepSeek API"""
        url = "https://api.deepseek.com/v1/chat/completions"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-chat",
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("choices"):
            return {
                "success": True,
                "content": result["choices"][0]["message"]["content"],
                "usage": result.get("usage", {})
            }
        else:
            return {"success": False, "error": "API 返回格式异常"}
    
    def _call_qwen(self, prompt: str, system_prompt: str = "") -> Dict[str, Any]:
        """调用 Qwen API"""
        url = "https://dashscope.aliyuncs.com/api/text/chat"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "qwen-turbo",
            "input": {
                "messages": messages
            },
            "parameters": {
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
        response.raise_for_status()
        
        result = response.json()
        
        if result.get("output") and result["output"].get("text"):
            return {
                "success": True,
                "content": result["output"]["text"],
                "usage": result.get("usage", {})
            }
        else:
            return {"success": False, "error": "API 返回格式异常"}
    
    def test_connection(self) -> Dict[str, Any]:
        """测试 API 连接"""
        test_prompt = "请简单回复 'OK' 表示连接正常"
        result = self.call(test_prompt)
        
        if result["success"] and "OK" in result["content"]:
            return {"success": True, "message": "API 连接正常"}
        else:
            return {"success": False, "error": result.get("error", "连接测试失败")}
