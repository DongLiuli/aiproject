"""PDF 解析测试脚本 - 改进版"""
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.pdf_parser import parse_pdf, chunk_text


def test_pdf_parser():
    """测试 PDF 解析功能"""
    # 使用绝对路径
    pdf_path = r"C:\Users\xml\aiproject\backend\data\uploads\0c8ce13f-5522-42a6-9dc4-fe7616872b78.pdf"
    
    print("🚀 PDF 解析测试 - 改进版")
    print("=" * 60)
    print(f"📄 测试文件: {pdf_path}")
    print(f"文件存在: {os.path.exists(pdf_path)}")
    print("=" * 60)
    
    if not os.path.exists(pdf_path):
        print("❌ 未找到测试 PDF 文件")
        return
    
    # 测试解析
    try:
        print("\n📖 开始解析 PDF...")
        result = parse_pdf(pdf_path)
        
        if result.get("success"):
            print("✅ PDF 解析成功")
            print(f"📄 页数: {result.get('page_count', 0)}")
            print(f"📑 章节数: {len(result.get('sections', []))}")
            print(f"📊 图表数: {len(result.get('figures_tables', []))}")
            print(f"📝 全文长度: {len(result.get('full_text', ''))} 字符")
            print(f"📚 参考文献长度: {len(result.get('references_raw', ''))} 字符")
            
            # 显示章节列表
            print("\n📋 章节列表:")
            sections = result.get("sections", [])
            if sections:
                for i, section in enumerate(sections):
                    content_preview = section['content'][:50] + "..." if len(section['content']) > 50 else section['content']
                    print(f"  {i+1}. {section['title']}")
                    print(f"     页码: {section['page_start']}-{section['page_end']}")
                    print(f"     内容: {content_preview}")
            else:
                print("  ⚠️  未检测到章节")
            
            # 显示全文预览
            full_text = result.get("full_text", "")
            if full_text:
                print(f"\n📝 全文预览 (前300字符):")
                print(full_text[:300] + "..." if len(full_text) > 300 else full_text)
            
            # 显示图表列表
            figures = result.get("figures_tables", [])
            if figures:
                print(f"\n📊 图表列表:")
                for fig in figures[:5]:
                    print(f"  - {fig['number']}: {fig['title']} (第{fig['page']}页, 类型: {fig.get('type', 'unknown')})")
                if len(figures) > 5:
                    print(f"  ... 还有 {len(figures) - 5} 个图表")
            
            # 测试文本分块
            print(f"\n🧩 测试文本分块功能:")
            if sections:
                test_section = sections[0]
                chunks = chunk_text(test_section['content'], test_section['title'], test_section['page_start'])
                print(f"  章节标题: {test_section['title']}")
                print(f"  原始长度: {len(test_section['content'])} 字符")
                print(f"  分块数量: {len(chunks)}")
                if chunks:
                    print(f"  第一个分块: {chunks[0]['content'][:100]}...")
            
            print("\n✅ 所有测试通过")
            
        else:
            print(f"❌ 解析失败: {result.get('error')}")
    
    except Exception as e:
        print(f"❌ 测试异常: {str(e)}")
        import traceback
        traceback.print_exc()


def test_error_handling():
    """测试异常处理"""
    print("\n🧪 测试异常处理")
    print("=" * 60)
    
    # 测试不存在的文件
    print("1. 测试不存在的文件...")
    result = parse_pdf("nonexistent.pdf")
    if not result["success"]:
        print(f"   ✅ 正确处理: {result['error']}")
    else:
        print("   ❌ 应该返回错误")
    
    # 测试非 PDF 文件
    print("2. 测试非 PDF 文件...")
    test_file = r"C:\Users\xml\aiproject\backend\ai\config.py"
    result = parse_pdf(test_file)
    if not result["success"]:
        print(f"   ✅ 正确处理: {result['error']}")
    else:
        print("   ❌ 应该返回错误")
    
    print("=" * 60)


if __name__ == "__main__":
    test_pdf_parser()
    test_error_handling()