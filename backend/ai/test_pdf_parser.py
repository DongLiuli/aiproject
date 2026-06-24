"""PDF 解析测试脚本"""
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.pdf_parser import parse_pdf


def test_pdf_parser():
    """测试 PDF 解析功能"""
    # 使用绝对路径
    pdf_path = r"C:\Users\xml\aiproject\backend\data\uploads\0c8ce13f-5522-42a6-9dc4-fe7616872b78.pdf"
    
    print(f"检查文件: {pdf_path}")
    print(f"文件存在: {os.path.exists(pdf_path)}")
    
    if not os.path.exists(pdf_path):
        print("❌ 未找到测试 PDF 文件")
        return
    
    print(f"📄 测试文件: {pdf_path}")
    print("=" * 50)
    
    # 测试解析
    try:
        result = parse_pdf(pdf_path)
        
        if result.get("success"):
            print("✅ PDF 解析成功")
            print(f"📄 页数: {result.get('page_count', 0)}")
            print(f"📑 章节数: {len(result.get('sections', []))}")
            print(f"📊 图表数: {len(result.get('figures_tables', []))}")
            
            # 显示前几个章节
            print("\n📋 章节列表:")
            sections = result.get("sections", [])
            for i, section in enumerate(sections[:5]):
                print(f"  {i+1}. {section['title']} (第{section['page_start']}-{section['page_end']}页)")
            
            # 显示部分全文
            full_text = result.get("full_text", "")
            if full_text:
                print("\n📝 全文预览 (前500字符):")
                print(full_text[:500] + "..." if len(full_text) > 500 else full_text)
            
            # 显示图表列表
            figures = result.get("figures_tables", [])
            if figures:
                print("\n📊 图表列表:")
                for fig in figures[:3]:
                    print(f"  - {fig['number']}: {fig['title']} (第{fig['page']}页)")
            
            print("\n✅ PyMuPDF 文本提取测试通过")
        
        else:
            print(f"❌ 解析失败: {result.get('error')}")
    
    except Exception as e:
        print(f"❌ 测试异常: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_pdf_parser()