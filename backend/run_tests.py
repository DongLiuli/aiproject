import requests
import time
import json
import os
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"
TEST_PDF = r"D:\study\3xun\test_paper.pdf"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

if len(sys.argv) > 1:
    API_KEY = sys.argv[1]

if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                API_KEY = line.strip().split("=", 1)[1]
                break

test_results = []

def log_test(module, test_name, status, message=""):
    result = {
        "module": module,
        "test_name": test_name,
        "status": status,
        "message": message,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    test_results.append(result)
    status_icon = "✓" if status == "通过" else "✗"
    print(f"{status_icon} [{module}] {test_name}: {status} - {message}")
    return result

def test_auth_anonymous():
    try:
        response = requests.post(f"{BASE_URL}/api/auth/anonymous")
        if response.status_code == 200:
            data = response.json()
            if "session_id" in data:
                return log_test("用户认证", "匿名访问", "通过", f"获取session_id: {data['session_id'][:20]}...")
            else:
                return log_test("用户认证", "匿名访问", "失败", "响应无session_id字段")
        else:
            return log_test("用户认证", "匿名访问", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("用户认证", "匿名访问", "失败", f"连接异常: {str(e)}")

def test_user_config(session_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload = {"api_key": API_KEY, "model": "deepseek-chat"}
        response = requests.put(f"{BASE_URL}/api/user/config", headers=headers, json=payload)
        if response.status_code == 200:
            return log_test("系统设置", "配置API Key", "通过", "配置保存成功")
        else:
            return log_test("系统设置", "配置API Key", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("系统设置", "配置API Key", "失败", f"连接异常: {str(e)}")

def test_config_test(session_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload = {"api_key": API_KEY, "model": "deepseek-chat"}
        response = requests.post(f"{BASE_URL}/api/user/config/test", headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                return log_test("系统设置", "测试配置", "通过", "API Key验证成功")
            else:
                return log_test("系统设置", "测试配置", "失败", f"验证失败: {data.get('error', '')}")
        else:
            return log_test("系统设置", "测试配置", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("系统设置", "测试配置", "失败", f"连接异常: {str(e)}")

def test_paper_upload(session_id):
    try:
        headers = {"X-Session-ID": session_id}
        with open(TEST_PDF, "rb") as f:
            files = {"file": ("test_paper.pdf", f, "application/pdf")}
            response = requests.post(f"{BASE_URL}/api/papers/upload", headers=headers, files=files)
        if response.status_code == 200:
            data = response.json()
            if "paper_id" in data:
                return log_test("论文上传", "上传PDF", "通过", f"获取paper_id: {data['paper_id']}")
            else:
                return log_test("论文上传", "上传PDF", "失败", "响应无paper_id字段")
        else:
            return log_test("论文上传", "上传PDF", "失败", f"HTTP状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        return log_test("论文上传", "上传PDF", "失败", f"连接异常: {str(e)}")

def test_paper_parse_status(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        for _ in range(60):
            response = requests.get(f"{BASE_URL}/api/papers/{paper_id}", headers=headers)
            if response.status_code == 200:
                data = response.json()
                status = data.get("parse_status", "")
                if status == "completed":
                    return log_test("论文解析", "解析状态轮询", "通过", "解析完成")
                elif status == "failed":
                    return log_test("论文解析", "解析状态轮询", "失败", f"解析失败: {data.get('parse_error', '')}")
            time.sleep(2)
        return log_test("论文解析", "解析状态轮询", "失败", "解析超时")
    except Exception as e:
        return log_test("论文解析", "解析状态轮询", "失败", f"连接异常: {str(e)}")

def test_paper_content(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        response = requests.get(f"{BASE_URL}/api/papers/{paper_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            has_title = "title" in data and data["title"]
            has_structured_info = "structured_info" in data and data["structured_info"]
            has_sections = "sections" in data and len(data["sections"]) > 0
            if has_title and has_structured_info and has_sections:
                return log_test("论文内容展示", "结构化信息显示", "通过", f"标题: {data['title'][:50]}...")
            else:
                return log_test("论文内容展示", "结构化信息显示", "失败", f"标题: {has_title}, 结构化信息: {has_structured_info}, 章节: {has_sections}")
        else:
            return log_test("论文内容展示", "结构化信息显示", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("论文内容展示", "结构化信息显示", "失败", f"连接异常: {str(e)}")

def test_paper_full_text(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        response = requests.get(f"{BASE_URL}/api/papers/{paper_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if "full_text" in data and data["full_text"] and len(data["full_text"]) > 0:
                return log_test("论文内容展示", "纯文本显示", "通过", f"文本长度: {len(data['full_text'])}字符")
            else:
                return log_test("论文内容展示", "纯文本显示", "失败", "full_text字段为空或不存在")
        else:
            return log_test("论文内容展示", "纯文本显示", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("论文内容展示", "纯文本显示", "失败", f"连接异常: {str(e)}")

def test_qa(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload = {"question": "这篇论文的创新点是什么？"}
        response = requests.post(f"{BASE_URL}/api/qa/{paper_id}", headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "answer" in data and len(data["answer"]) > 0:
                return log_test("智能问答", "提问", "通过", f"回答长度: {len(data['answer'])}字符")
            else:
                return log_test("智能问答", "提问", "失败", "回答为空")
        else:
            return log_test("智能问答", "提问", "失败", f"HTTP状态码: {response.status_code}, 响应: {response.text}")
    except Exception as e:
        return log_test("智能问答", "提问", "失败", f"连接异常: {str(e)}")

def test_qa_multi_round(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload1 = {"question": "这篇论文的研究方法是什么？"}
        response1 = requests.post(f"{BASE_URL}/api/qa/{paper_id}", headers=headers, json=payload1)
        if response1.status_code != 200:
            return log_test("智能问答", "多轮对话", "失败", f"第一轮问答失败: {response1.text[:100]}")
        
        data1 = response1.json()
        conversation_id = data1.get("conversation_id")
        
        payload2 = {"question": "这个方法的优缺点是什么？", "conversation_id": conversation_id}
        response2 = requests.post(f"{BASE_URL}/api/qa/{paper_id}", headers=headers, json=payload2)
        if response2.status_code == 200:
            data = response2.json()
            if "answer" in data and len(data["answer"]) > 0:
                return log_test("智能问答", "多轮对话", "通过", "多轮对话正常")
            else:
                return log_test("智能问答", "多轮对话", "失败", "第二轮回答为空")
        else:
            return log_test("智能问答", "多轮对话", "失败", f"HTTP状态码: {response2.status_code}, 响应: {response2.text[:100]}")
    except Exception as e:
        return log_test("智能问答", "多轮对话", "失败", f"连接异常: {str(e)}")

def test_report_quick(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload = {"report_type": "quick"}
        response = requests.post(f"{BASE_URL}/api/reports/{paper_id}", headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                return log_test("研读报告", "速读报告生成", "通过", f"报告长度: {len(data['content'])}字符")
            else:
                return log_test("研读报告", "速读报告生成", "失败", "报告内容为空")
        else:
            return log_test("研读报告", "速读报告生成", "失败", f"HTTP状态码: {response.status_code}, 响应: {response.text[:100]}")
    except Exception as e:
        return log_test("研读报告", "速读报告生成", "失败", f"连接异常: {str(e)}")

def test_report_method(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload = {"report_type": "method"}
        response = requests.post(f"{BASE_URL}/api/reports/{paper_id}", headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                return log_test("研读报告", "方法总结生成", "通过", f"报告长度: {len(data['content'])}字符")
            else:
                return log_test("研读报告", "方法总结生成", "失败", "报告内容为空")
        else:
            return log_test("研读报告", "方法总结生成", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("研读报告", "方法总结生成", "失败", f"连接异常: {str(e)}")

def test_report_experiment(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        payload = {"report_type": "experiment"}
        response = requests.post(f"{BASE_URL}/api/reports/{paper_id}", headers=headers, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "content" in data and len(data["content"]) > 0:
                return log_test("研读报告", "实验总结生成", "通过", f"报告长度: {len(data['content'])}字符")
            else:
                return log_test("研读报告", "实验总结生成", "失败", "报告内容为空")
        else:
            return log_test("研读报告", "实验总结生成", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("研读报告", "实验总结生成", "失败", f"连接异常: {str(e)}")

def test_paper_list(session_id):
    try:
        headers = {"X-Session-ID": session_id}
        response = requests.get(f"{BASE_URL}/api/papers", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                item_count = len(data["items"])
                return log_test("论文列表与搜索", "论文列表显示", "通过", f"论文数量: {item_count}")
            else:
                return log_test("论文列表与搜索", "论文列表显示", "失败", "响应无items字段")
        else:
            return log_test("论文列表与搜索", "论文列表显示", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("论文列表与搜索", "论文列表显示", "失败", f"连接异常: {str(e)}")

def test_paper_search(session_id):
    try:
        headers = {"X-Session-ID": session_id}
        response = requests.get(f"{BASE_URL}/api/papers?keyword=test", headers=headers)
        if response.status_code == 200:
            data = response.json()
            if "items" in data:
                return log_test("论文列表与搜索", "搜索论文", "通过", f"搜索结果数量: {len(data['items'])}")
            else:
                return log_test("论文列表与搜索", "搜索论文", "失败", "响应无items字段")
        else:
            return log_test("论文列表与搜索", "搜索论文", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("论文列表与搜索", "搜索论文", "失败", f"连接异常: {str(e)}")

def test_paper_delete(session_id, paper_id):
    try:
        headers = {"X-Session-ID": session_id}
        response = requests.delete(f"{BASE_URL}/api/papers/{paper_id}", headers=headers)
        if response.status_code == 200:
            return log_test("论文解析", "删除论文", "通过", "论文删除成功")
        else:
            return log_test("论文解析", "删除论文", "失败", f"HTTP状态码: {response.status_code}")
    except Exception as e:
        return log_test("论文解析", "删除论文", "失败", f"连接异常: {str(e)}")

def test_invalid_file_upload(session_id):
    try:
        headers = {"X-Session-ID": session_id}
        test_txt = r"D:\study\3xun\数据.txt"
        if os.path.exists(test_txt):
            with open(test_txt, "rb") as f:
                files = {"file": ("test.txt", f, "text/plain")}
                response = requests.post(f"{BASE_URL}/api/papers/upload", headers=headers, files=files)
            if response.status_code == 400:
                return log_test("异常场景测试", "文件格式错误", "通过", "正确拒绝非PDF文件")
            elif response.status_code == 200:
                return log_test("异常场景测试", "文件格式错误", "失败", "错误接受了非PDF文件")
            else:
                return log_test("异常场景测试", "文件格式错误", "失败", f"HTTP状态码: {response.status_code}")
        else:
            return log_test("异常场景测试", "文件格式错误", "跳过", "测试文件不存在")
    except Exception as e:
        return log_test("异常场景测试", "文件格式错误", "失败", f"连接异常: {str(e)}")

def generate_test_report():
    passed = sum(1 for r in test_results if r["status"] == "通过")
    failed = sum(1 for r in test_results if r["status"] == "失败")
    skipped = sum(1 for r in test_results if r["status"] == "跳过")
    
    report_content = []
    report_content.append("《科研文献智能解析与知识服务》")
    report_content.append("测试报告")
    report_content.append("")
    report_content.append(f"测试日期: {datetime.now().strftime('%Y年%m月%d日')}")
    report_content.append(f"测试环境: Windows 10, Python {sys.version.split()[0]}")
    report_content.append(f"测试地址: {BASE_URL}")
    report_content.append("")
    report_content.append("=" * 50)
    report_content.append("测试结果汇总")
    report_content.append("=" * 50)
    report_content.append(f"通过: {passed}")
    report_content.append(f"失败: {failed}")
    report_content.append(f"跳过: {skipped}")
    report_content.append(f"通过率: {passed / max(passed + failed, 1) * 100:.1f}%")
    report_content.append("")
    report_content.append("=" * 50)
    report_content.append("详细测试结果")
    report_content.append("=" * 50)
    
    modules = {}
    for result in test_results:
        module = result["module"]
        if module not in modules:
            modules[module] = []
        modules[module].append(result)
    
    for module, results in modules.items():
        report_content.append(f"\n【{module}】")
        for result in results:
            status_icon = "✓" if result["status"] == "通过" else "✗" if result["status"] == "失败" else "-"
            report_content.append(f"  {status_icon} {result['test_name']}: {result['status']}")
            if result["message"]:
                report_content.append(f"     {result['message']}")
    
    if failed > 0:
        report_content.append("\n" + "=" * 50)
        report_content.append("问题汇总")
        report_content.append("=" * 50)
        for result in test_results:
            if result["status"] == "失败":
                report_content.append(f"- [{result['module']}] {result['test_name']}: {result['message']}")
    
    report_content.append("\n" + "=" * 50)
    report_content.append("测试结论")
    report_content.append("=" * 50)
    if failed == 0:
        report_content.append("系统测试全部通过，功能正常。")
    else:
        report_content.append(f"系统存在 {failed} 个测试失败项，建议修复后重新测试。")
    
    report_text = "\n".join(report_content)
    
    with open("测试报告.txt", "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print("\n测试报告已保存到: 测试报告.txt")
    print(report_text)

def main():
    if not API_KEY:
        print("请先设置环境变量 DEEPSEEK_API_KEY")
        sys.exit(1)
    
    if not os.path.exists(TEST_PDF):
        print(f"测试PDF文件不存在: {TEST_PDF}")
        sys.exit(1)
    
    print("=" * 50)
    print("《科研文献智能解析与知识服务》系统测试")
    print("=" * 50)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试地址: {BASE_URL}")
    print("=" * 50)
    
    session_id = None
    paper_id = None
    
    auth_result = test_auth_anonymous()
    if auth_result["status"] == "通过":
        session_id = auth_result["message"].split(": ")[1].strip("...")
    
    if session_id:
        test_user_config(session_id)
        test_config_test(session_id)
        
        upload_result = test_paper_upload(session_id)
        if upload_result["status"] == "通过":
            paper_id = upload_result["message"].split(": ")[1]
            
            parse_result = test_paper_parse_status(session_id, paper_id)
            if parse_result["status"] == "通过":
                test_paper_content(session_id, paper_id)
                test_paper_full_text(session_id, paper_id)
                test_qa(session_id, paper_id)
                test_qa_multi_round(session_id, paper_id)
                test_report_quick(session_id, paper_id)
                test_report_method(session_id, paper_id)
                test_report_experiment(session_id, paper_id)
            
            test_paper_list(session_id)
            test_paper_search(session_id)
            test_invalid_file_upload(session_id)
            
            if paper_id:
                test_paper_delete(session_id, paper_id)
        else:
            print("论文上传失败，跳过后续测试")
    else:
        print("匿名认证失败，跳过后续测试")
    
    generate_test_report()

if __name__ == "__main__":
    main()