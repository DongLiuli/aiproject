"""PDF 解析模块"""
import fitz  # PyMuPDF
import re
from typing import Dict, List, Any
from .config import CHUNK_CONFIG


def parse_pdf(file_path: str) -> Dict[str, Any]:
    """
    解析 PDF 文件，提取文本内容和结构信息
    
    :param file_path: PDF 文件路径
    :return: 解析结果字典
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return {
            "success": False,
            "error": f"无法打开 PDF 文件: {str(e)}"
        }
    
    full_text = ""
    sections = []
    figures_tables = []
    references_raw = ""
    
    # 章节标题模式匹配
    section_patterns = [
        r'^\d+\.\s+.+',           # 1. Introduction
        r'^\d+\.\d+\s+.+',        # 1.1 Background
        r'^\d+\.\d+\.\d+\s+.+',   # 1.1.1 Sub section
        r'^[IVX]+\.\s+.+',        # I. Introduction (罗马数字)
        r'^[一二三四五六七八九十]+\s*[、.．]\s*.+',  # 中文章节
        r'^Abstract\s*$',
        r'^Introduction\s*$',
        r'^Conclusion\s*$',
        r'^References\s*$',
        r'^Acknowledgments?\s*$',
        r'^Appendix\s*$',
        r'^摘要\s*$',
        r'^引言\s*$',
        r'^结论\s*$',
        r'^参考文献\s*$',
        r'^附录\s*$',
    ]
    
    current_section = None
    current_section_content = ""
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_text = page.get_text("text")
        
        if not page_text.strip():
            continue
        
        # 检测表格和图片
        for img in page.get_images(full=True):
            figures_tables.append({
                "number": f"Fig.{len(figures_tables) + 1}",
                "title": f"图片 {len(figures_tables) + 1}",
                "page": page_num + 1
            })
        
        for table in page.find_tables():
            figures_tables.append({
                "number": f"Table.{len(figures_tables) + 1}",
                "title": f"表格 {len(figures_tables) + 1}",
                "page": page_num + 1
            })
        
        # 按段落分割
        paragraphs = page_text.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # 检测章节标题
            is_section = False
            for pattern in section_patterns:
                if re.match(pattern, paragraph, re.MULTILINE):
                    # 保存上一个章节
                    if current_section:
                        sections.append({
                            "title": current_section,
                            "content": current_section_content.strip(),
                            "page_start": current_section_page,
                            "page_end": page_num + 1
                        })
                    
                    current_section = paragraph
                    current_section_content = ""
                    current_section_page = page_num + 1
                    is_section = True
                    break
            
            if not is_section:
                # 检查是否是参考文献部分
                if current_section and current_section.lower() == "references":
                    references_raw += paragraph + "\n"
                elif current_section:
                    current_section_content += paragraph + "\n"
            
            # 添加到全文
            full_text += paragraph + "\n\n"
    
    # 保存最后一个章节
    if current_section:
        sections.append({
            "title": current_section,
            "content": current_section_content.strip(),
            "page_start": current_section_page,
            "page_end": len(doc)
        })
    
    doc.close()
    
    return {
        "success": True,
        "full_text": full_text.strip(),
        "sections": sections,
        "figures_tables": figures_tables,
        "references_raw": references_raw.strip(),
        "page_count": len(doc)
    }


def chunk_text(text: str, section_title: str = "", page_number: int = 0) -> List[Dict[str, Any]]:
    """
    将文本分块
    
    :param text: 原始文本
    :param section_title: 章节标题
    :param page_number: 页码
    :return: 分块列表
    """
    chunks = []
    chunk_size = CHUNK_CONFIG["chunk_size"]
    chunk_overlap = CHUNK_CONFIG["chunk_overlap"]
    min_chunk_size = CHUNK_CONFIG["min_chunk_size"]
    
    paragraphs = text.split('\n\n')
    current_chunk = ""
    paragraph_index = 0
    
    for i, paragraph in enumerate(paragraphs):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        
        # 如果当前块加上新段落超过阈值，保存当前块
        if len(current_chunk) + len(paragraph) > chunk_size and current_chunk:
            if len(current_chunk) >= min_chunk_size:
                chunks.append({
                    "content": current_chunk.strip(),
                    "section_title": section_title,
                    "page_number": page_number,
                    "paragraph_index": paragraph_index
                })
                paragraph_index += 1
            
            # 保留重叠部分
            overlap_text = current_chunk[-chunk_overlap:] if len(current_chunk) > chunk_overlap else current_chunk
            current_chunk = overlap_text + "\n\n" + paragraph
        else:
            current_chunk += paragraph + "\n\n"
    
    # 保存最后一个块
    if current_chunk and len(current_chunk) >= min_chunk_size:
        chunks.append({
            "content": current_chunk.strip(),
            "section_title": section_title,
            "page_number": page_number,
            "paragraph_index": paragraph_index
        })
    
    return chunks