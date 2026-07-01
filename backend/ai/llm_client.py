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
        import logging
        logger = logging.getLogger(__name__)
        
        # 更新为正确的API端点
        url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        
        logger.info(f"[LLM] 调用Qwen API，URL: {url}")
        
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
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            logger.info(f"[LLM] 发送请求到Qwen...")
            response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
            
            logger.info(f"[LLM] Qwen响应状态码: {response.status_code}")
            
            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"[LLM] Qwen API错误: {response.status_code} - {error_detail}")
                return {"success": False, "error": f"API错误 {response.status_code}: {error_detail}"}
            
            result = response.json()
            logger.info(f"[LLM] Qwen响应格式正常")
            
            if result.get("choices") and len(result["choices"]) > 0:
                return {
                    "success": True,
                    "content": result["choices"][0]["message"]["content"],
                    "usage": result.get("usage", {})
                }
            else:
                logger.error(f"[LLM] Qwen返回格式异常: {result}")
                return {"success": False, "error": f"API返回格式异常: {result}"}
                
        except requests.exceptions.Timeout:
            logger.error("[LLM] Qwen请求超时")
            return {"success": False, "error": "Qwen API请求超时，请检查网络连接或稍后重试"}
        except requests.exceptions.ConnectionError:
            logger.error("[LLM] Qwen连接失败")
            return {"success": False, "error": "无法连接到Qwen API，请检查网络连接"}
        except Exception as e:
            logger.exception(f"[LLM] Qwen调用异常: {str(e)}")
            return {"success": False, "error": f"Qwen调用失败: {str(e)}"}
    
    def call_stream(self, prompt: str, system_prompt: str = ""):
        """
        流式调用 LLM API，逐块 yield 增量文本。

        yield 的事件为 dict：
          {"type": "delta", "content": "..."}  增量文本
          {"type": "error", "error": "..."}    出错（yield 后即结束）

        :param prompt: 用户提示
        :param system_prompt: 系统提示
        """
        if not self.api_key:
            yield {"type": "error", "error": "API Key 未配置"}
            return

        if self.provider == "deepseek":
            url = "https://api.deepseek.com/v1/chat/completions"
            model = "deepseek-chat"
        elif self.provider == "qwen":
            url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            model = "qwen-turbo"
        else:
            yield {"type": "error", "error": f"不支持的 provider: {self.provider}"}
            return

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
        }

        try:
            with requests.post(url, headers=headers, json=data,
                               timeout=self.timeout, stream=True) as response:
                if response.status_code != 200:
                    detail = response.text[:200] if response.text else ""
                    yield {"type": "error", "error": f"API错误 {response.status_code}: {detail}"}
                    return

                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = obj.get("choices")
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield {"type": "delta", "content": content}

        except requests.exceptions.Timeout:
            yield {"type": "error", "error": "请求超时"}
        except requests.exceptions.ConnectionError:
            yield {"type": "error", "error": "无法连接到 LLM 服务，请检查网络"}
        except requests.exceptions.RequestException as e:
            yield {"type": "error", "error": f"请求失败: {str(e)}"}
        except Exception as e:
            yield {"type": "error", "error": f"未知错误: {str(e)}"}

    def test_connection(self) -> Dict[str, Any]:
        """测试 API 连接"""
        test_prompt = "请简单回复 'OK' 表示连接正常"
        result = self.call(test_prompt)
        
        if result["success"] and "OK" in result["content"]:
            return {"success": True, "message": "API 连接正常"}
        else:
            return {"success": False, "error": result.get("error", "连接测试失败")}
