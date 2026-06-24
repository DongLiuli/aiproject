"""PDF 解析模块 - 改进版"""
import fitz  # PyMuPDF
import re
from typing import Dict, List, Any, Tuple
from .config import CHUNK_CONFIG


def parse_pdf(file_path: str) -> Dict[str, Any]:
    """
    解析 PDF 文件，提取文本内容和结构信息
    
    :param file_path: PDF 文件路径
    :return: 解析结果字典
    """
    # 1. 文件验证和异常处理
    validation_result = _validate_pdf_file(file_path)
    if not validation_result["success"]:
        return validation_result
    
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return {
            "success": False,
            "error": f"无法打开 PDF 文件: {str(e)}"
        }
    
    # 2. 检查是否是扫描件
    if _is_scanned_pdf(doc):
        doc.close()
        return {
            "success": False,
            "error": "检测到扫描件 PDF，无法提取文本内容。请使用 OCR 工具处理。"
        }
    
    full_text = ""
    sections = []
    figures_tables = []
    references_raw = ""
    
    # 3. 章节标题模式匹配（扩展版）
    section_patterns = [
        # 数字编号
        r'^\d+\.\s+[A-Z][^\n]{3,50}$',          # 1. Introduction (大写开头)
        r'^\d+\.\s+[A-Z\u4e00-\u9fa5][^\n]{3,50}$',  # 1. Introduction 或 1. 引言
        r'^\d+\.\d+\s+[A-Z\u4e00-\u9fa5][^\n]{3,40}$',  # 1.1 Background
        r'^\d+\.\d+\.\d+\s+[A-Z\u4e00-\u9fa5][^\n]{3,30}$',  # 1.1.1 Sub section
        
        # 罗马数字
        r'^[IVX]+\.\s+[A-Z][^\n]{3,50}$',        # I. Introduction
        r'^[IVX]+\.\s+[A-Z\u4e00-\u9fa5][^\n]{3,50}$',  # I. Introduction 或 I. 引言
        
        # 中文章节
        r'^[一二三四五六七八九十]+\s*[、.．]\s*[^\n]{3,50}$',  # 一、引言
        
        # 常见章节标题
        r'^Abstract\s*$',
        r'^Introduction\s*$',
        r'^Related Work\s*$',
        r'^Methodology\s*$',
        r'^Methods?\s*$',
        r'^Experiments?\s*$',
        r'^Results?\s*$',
        r'^Discussion\s*$',
        r'^Conclusion\s*$',
        r'^Conclusions?\s*$',
        r'^References?\s*$',
        r'^Acknowledgments?\s*$',
        r'^Appendix\s*[A-Z]?\s*$',
        
        # 中文章节
        r'^摘要\s*$',
        r'^引言\s*$',
        r'^相关工作\s*$',
        r'^方法\s*$',
        r'^实验\s*$',
        r'^结果\s*$',
        r'^讨论\s*$',
        r'^结论\s*$',
        r'^参考文献\s*$',
        r'^致谢\s*$',
        r'^附录\s*$',
    ]
    
    current_section = None
    current_section_content = ""
    current_section_page = 1
    
    # 4. 逐页处理（支持双栏排版）
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # 使用 blocks 提取文本块，支持双栏排版
        blocks = page.get_text("blocks")
        
        # 按位置排序（从上到下，从左到右）
        sorted_blocks = _sort_blocks(blocks)
        
        # 提取文本内容
        page_text = _extract_text_from_blocks(sorted_blocks)
        
        if not page_text.strip():
            continue
        
        # 5. 检测表格和图片
        figures_tables.extend(_detect_figures_tables(page, page_num, len(figures_tables)))
        
        # 6. 按段落分割
        paragraphs = page_text.split('\n\n')
        
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            
            # 过滤页眉页脚（短行且重复出现）
            if _is_header_footer(paragraph, page_num):
                continue
            
            # 7. 检测章节标题
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
    
    # 8. 保存最后一个章节
    if current_section:
        sections.append({
            "title": current_section,
            "content": current_section_content.strip(),
            "page_start": current_section_page,
            "page_end": len(doc)
        })
    
    # 9. 验证解析结果
    if not sections and not full_text.strip():
        doc.close()
        return {
            "success": False,
            "error": "PDF 文件似乎没有可提取的文本内容"
        }
    
    page_count = len(doc)
    doc.close()
    
    return {
        "success": True,
        "full_text": full_text.strip(),
        "sections": sections,
        "figures_tables": figures_tables,
        "references_raw": references_raw.strip(),
        "page_count": page_count
    }


def _validate_pdf_file(file_path: str) -> Dict[str, Any]:
    """
    验证 PDF 文件
    
    :param file_path: 文件路径
    :return: 验证结果
    """
    import os
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        return {
            "success": False,
            "error": f"文件不存在: {file_path}"
        }
    
    # 检查文件扩展名
    if not file_path.lower().endswith('.pdf'):
        return {
            "success": False,
            "error": "文件格式错误，必须是 PDF 文件"
        }
    
    # 检查文件大小
    file_size = os.path.getsize(file_path)
    if file_size == 0:
        return {
            "success": False,
            "error": "PDF 文件为空"
        }
    
    if file_size > 100 * 1024 * 1024:  # 100MB
        return {
            "success": False,
            "error": "PDF 文件过大（超过 100MB）"
        }
    
    return {"success": True}


def _is_scanned_pdf(doc: fitz.Document) -> bool:
    """
    检查是否是扫描件 PDF
    
    :param doc: PDF 文档对象
    :return: 是否是扫描件
    """
    try:
        # 检查前几页的文本内容
        for page_num in range(min(3, len(doc))):
            page = doc[page_num]
            text = page.get_text("text")
            
            # 如果文本很少，可能是扫描件
            if len(text.strip()) < 50:
                # 检查是否有图片
                images = page.get_images(full=True)
                if images:
                    return True
        
        return False
    except Exception:
        return False


def _sort_blocks(blocks: List[Tuple]) -> List[Tuple]:
    """
    对文本块进行排序，支持双栏排版
    
    :param blocks: 文本块列表
    :return: 排序后的文本块
    """
    # 提取块的位置信息
    block_info = []
    for block in blocks:
        x0, y0, x1, y1, content, block_type, block_no = block
        if block_type == 0:  # 文本块
            block_info.append({
                "block": block,
                "y0": y0,
                "x0": x0,
                "height": y1 - y0,
                "width": x1 - x0
            })
    
    # 按行分组（Y 坐标相近的块）
    lines = []
    current_line = []
    current_y = None
    
    for info in sorted(block_info, key=lambda x: x["y0"]):
        if current_y is None or abs(info["y0"] - current_y) < 10:  # 同一行
            current_line.append(info)
            current_y = info["y0"]
        else:
            if current_line:
                lines.append(current_line)
            current_line = [info]
            current_y = info["y0"]
    
    if current_line:
        lines.append(current_line)
    
    # 对每行按 X 坐标排序
    sorted_blocks = []
    for line in lines:
        # 检查是否是双栏（同一行有多个块且宽度相似）
        if len(line) > 1:
            # 按列排序
            sorted_line = sorted(line, key=lambda x: x["x0"])
            sorted_blocks.extend([info["block"] for info in sorted_line])
        else:
            sorted_blocks.append(line[0]["block"])
    
    return sorted_blocks


def _extract_text_from_blocks(blocks: List[Tuple]) -> str:
    """
    从文本块中提取文本
    
    :param blocks: 文本块列表
    :return: 提取的文本
    """
    text_parts = []
    
    for block in blocks:
        x0, y0, x1, y1, content, block_type, block_no = block
        if block_type == 0:  # 文本块
            text_parts.append(content)
    
    return "\n\n".join(text_parts)


def _detect_figures_tables(page: fitz.Page, page_num: int, start_index: int) -> List[Dict[str, Any]]:
    """
    检测页面中的图片和表格
    
    :param page: 页面对象
    :param page_num: 页码
    :param start_index: 起始索引
    :return: 图表列表
    """
    figures_tables = []
    
    # 检测图片
    images = page.get_images(full=True)
    for i, img in enumerate(images):
        figures_tables.append({
            "number": f"Fig.{start_index + len(figures_tables) + 1}",
            "title": f"图片 {start_index + len(figures_tables) + 1}",
            "page": page_num + 1,
            "type": "image"
        })
    
    # 检测表格
    tables = page.find_tables()
    for i, table in enumerate(tables):
        figures_tables.append({
            "number": f"Table.{start_index + len(figures_tables) + 1}",
            "title": f"表格 {start_index + len(figures_tables) + 1}",
            "page": page_num + 1,
            "type": "table"
        })
    
    return figures_tables


def _is_header_footer(text: str, page_num: int) -> bool:
    """
    判断是否是页眉或页脚
    
    :param text: 文本内容
    :param page_num: 页码
    :return: 是否是页眉页脚
    """
    # 短文本且包含页码
    if len(text) < 50 and str(page_num + 1) in text:
        return True
    
    # 常见页眉页脚模式
    header_footer_patterns = [
        r'^\d+$',  # 只有页码
        r'^Page\s+\d+$',  # Page 1
        r'^第\s*\d+\s*页$',  # 第1页
        r'^\d+\s*/\s*\d+$',  # 1/10
        r'^©\s*\d{4}',  # 版权信息
        r'^Draft\s+',  # 草稿
        r'^Confidential\s+',  # 机密
    ]
    
    for pattern in header_footer_patterns:
        if re.match(pattern, text.strip()):
            return True
    
    return False


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