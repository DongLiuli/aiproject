"""LLM 客户端测试脚本"""
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.llm_client import LLMClient


def test_llm_client():
    """测试 LLM 客户端"""
    print("🚀 LLM 客户端测试")
    print("=" * 50)
    
    # 获取 API Key（从环境变量或用户输入）
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    
    if not api_key:
        print("⚠️  未设置 DEEPSEEK_API_KEY 环境变量")
        print("请设置环境变量或直接输入 API Key")
        api_key = input("请输入 DeepSeek API Key: ").strip()
    
    if not api_key:
        print("❌ API Key 为空，测试终止")
        return
    
    # 创建客户端并测试
    client = LLMClient(api_key=api_key, provider="deepseek")
    
    print("\n📡 测试连接...")
    result = client.test_connection()
    
    if result["success"]:
        print("✅ API 连接成功")
        
        # 测试实际调用
        print("\n📝 测试 LLM 调用...")
        prompt = "请用一句话介绍什么是机器学习。"
        response = client.call(prompt)
        
        if response["success"]:
            print("✅ LLM 调用成功")
            print(f"📄 响应内容:\n{response['content']}")
            
            if "usage" in response:
                usage = response["usage"]
                print(f"\n📊 调用统计:")
                if "prompt_tokens" in usage:
                    print(f"  - 输入 tokens: {usage['prompt_tokens']}")
                if "completion_tokens" in usage:
                    print(f"  - 输出 tokens: {usage['completion_tokens']}")
        else:
            print(f"❌ LLM 调用失败: {response.get('error')}")
    
    else:
        print(f"❌ 连接测试失败: {result.get('error')}")


if __name__ == "__main__":
    test_llm_client()