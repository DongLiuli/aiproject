"""PDF 解析模块 - 改进版"""
import fitz  # PyMuPDF
import re
import logging
import threading
import unicodedata
from typing import Dict, List, Any, Tuple
from .config import CHUNK_CONFIG

logger = logging.getLogger(__name__)

# PyMuPDF 的 find_tables 依赖模块级全局 TEXTPAGE（pymupdf/table.py），非线程安全。
# FastAPI 把解析后台任务丢进线程池并发执行，两个 find_tables 并发会互相踩坏 TEXTPAGE
# → "not a textpage of this page"。用模块级锁串行化这一个调用即可根治。
_FIND_TABLES_LOCK = threading.Lock()

# 扫描件判定阈值（折进主循环统计，零额外遍历）
SCAN_TEXT_MIN = 50            # 页文字少于此视为"低文字页"
FULL_PAGE_IMAGE_RATIO = 0.8  # 单图 bbox 面积 / 页面积 ≥ 此视为"整页图"
SCAN_PAGE_FRACTION = 0.6     # 扫描页占全篇比例 ≥ 此才判整篇扫描件
# 章节标题防御上限（正常标题很短，超长必是解析噪声）
MAX_SECTION_TITLE_LEN = 200


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
    
    # 2. 扫描件判定改为折进主循环统计（见下方 scanned_pages），此处不再预检
    full_text = ""
    sections = []
    figures_tables = []
    references_raw = ""
    scanned_pages = 0  # 累积"整页图+无文字"的页数，循环后按占比判定扫描件
    
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
        # #6 Unicode 归一化：连字 ﬁ/ﬂ→fi/fl、全角→半角，净化下游 BM25/向量/LLM 输入
        page_text = unicodedata.normalize("NFKC", page_text)

        # 扫描件信号：复用已取的 page_text 与页面图片，主循环内累积（无额外遍历）
        if _page_is_scan(page, page_text):
            scanned_pages += 1

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
                m = re.match(pattern, paragraph, re.MULTILINE)
                if m:
                    # 保存上一个章节
                    if current_section:
                        sections.append({
                            "title": current_section,
                            "content": current_section_content.strip(),
                            "page_start": current_section_page,
                            "page_end": page_num + 1
                        })

                    # #2 只取匹配到的标题行；PyMuPDF 有时把"标题+正文"返回成一个 block，
                    # 之前 current_section = paragraph 会把整段正文当标题 → section_title 溢出。
                    current_section = m.group(0).strip()[:MAX_SECTION_TITLE_LEN]
                    remainder = paragraph[m.end():].strip()  # 标题行之后的正文并入内容
                    current_section_content = (remainder + "\n") if remainder else ""
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
    
    page_count = len(doc)

    # 9. 扫描件判定：多数页面都是"整页图 + 无文字"才判扫描件（单页大图不误杀）
    if page_count and scanned_pages / page_count >= SCAN_PAGE_FRACTION:
        doc.close()
        return {
            "success": False,
            "error": "检测到扫描件 PDF，无法提取文本内容。请使用 OCR 工具处理。"
        }

    # 10. 验证解析结果
    if not sections and not full_text.strip():
        doc.close()
        return {
            "success": False,
            "error": "PDF 文件似乎没有可提取的文本内容"
        }

    doc.close()
    
    # 拆分参考文献
    references = _split_references(references_raw)
    
    return {
        "success": True,
        "full_text": full_text.strip(),
        "sections": sections,
        "figures_tables": figures_tables,
        "references_raw": references_raw.strip(),
        "references": references,
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


def _page_is_scan(page: fitz.Page, page_text: str) -> bool:
    """
    判断单页是否为"扫描页"：文字极少，且被一张接近整页的图覆盖。

    区别于"正常论文里的插图"——正常图只占页面一部分；扫描页是整页一张图。
    有足够文字则直接早退（不查图，省成本）。由 parse_pdf 主循环逐页调用累积，
    再按 SCAN_PAGE_FRACTION 占比判定整篇是否扫描件（单页大图不会误杀）。

    :param page: 页面对象
    :param page_text: 该页已提取（并归一化）的文本
    :return: 该页是否为扫描页
    """
    if len(page_text.strip()) >= SCAN_TEXT_MIN:
        return False
    try:
        area = abs(page.rect.width * page.rect.height)
        if area <= 0:
            return False
        for info in page.get_image_info():
            b = info.get("bbox")
            if not b:
                continue
            if abs((b[2] - b[0]) * (b[3] - b[1])) / area >= FULL_PAGE_IMAGE_RATIO:
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
        if content.strip():  # 只要有文本内容就处理
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
        if content.strip():  # 只要有文本内容就提取
            text_parts.append(content)
    
    return "\n\n".join(text_parts)


def _detect_figures_tables(page: fitz.Page, page_num: int, start_index: int) -> List[Dict[str, Any]]:
    """
    检测页面中的图片和表格，并提取真实的图题/表题文本
    
    :param page: 页面对象
    :param page_num: 页码
    :param start_index: 起始索引
    :return: 图表列表
    """
    figures_tables = []
    
    # 获取页面文本用于提取图题/表题
    page_text = page.get_text("text")
    
    # 图题匹配模式（支持多种格式）
    figure_patterns = [
        r'(Figure\s+\d+[:：]\s*.+?)(?=\n\n|\nFigure|\nTable|\Z)',
        r'(Fig\.\s*\d+[:：]\s*.+?)(?=\n\n|\nFigure|\nTable|\Z)',
        r'(图\s*\d+[:：]\s*.+?)(?=\n\n|\n图|\n表|\Z)'
    ]
    
    # 表题匹配模式
    table_patterns = [
        r'(Table\s+\d+[:：]\s*.+?)(?=\n\n|\nFigure|\nTable|\Z)',
        r'(表\s*\d+[:：]\s*.+?)(?=\n\n|\n图|\n表|\Z)'
    ]
    
    # 检测图片并提取图题
    images = page.get_images(full=True)
    detected_figures = []
    
    for pattern in figure_patterns:
        matches = re.finditer(pattern, page_text, re.DOTALL)
        for match in matches:
            full_match = match.group(1).strip()
            # 提取编号（如 Figure 1, Fig. 2, 图 3）
            num_match = re.match(r'(Figure\s+\d+|Fig\.\s*\d+|图\s*\d+)', full_match, re.IGNORECASE)
            if num_match:
                detected_figures.append({
                    "number": num_match.group(1).strip(),
                    "title": full_match[len(num_match.group(1)):].replace(':', '').replace('：', '').strip()
                })
    
    for i, img in enumerate(images):
        if i < len(detected_figures):
            figures_tables.append({
                "number": detected_figures[i]["number"],
                "title": detected_figures[i]["title"],
                "page": page_num + 1,
                "type": "image"
            })
        else:
            figures_tables.append({
                "number": f"Fig.{start_index + len(figures_tables) + 1}",
                "title": f"图片 {start_index + len(figures_tables) + 1}",
                "page": page_num + 1,
                "type": "image"
            })
    
    # 检测表格并提取表题
    # 加锁串行化（find_tables 非线程安全，见文件顶部 _FIND_TABLES_LOCK 说明）；
    # 表格检测非核心，任何失败都降级为"无表格"而不中断整篇解析
    tables = []
    try:
        with _FIND_TABLES_LOCK:
            tables = list(page.find_tables())
    except Exception as e:
        logger.warning(f"find_tables 失败，跳过本页表格检测 (page {page_num + 1}): {e}")
        tables = []
    detected_tables = []
    
    for pattern in table_patterns:
        matches = re.finditer(pattern, page_text, re.DOTALL)
        for match in matches:
            full_match = match.group(1).strip()
            num_match = re.match(r'(Table\s+\d+|表\s*\d+)', full_match, re.IGNORECASE)
            if num_match:
                detected_tables.append({
                    "number": num_match.group(1).strip(),
                    "title": full_match[len(num_match.group(1)):].replace(':', '').replace('：', '').strip()
                })
    
    for i, table in enumerate(tables):
        if i < len(detected_tables):
            figures_tables.append({
                "number": detected_tables[i]["number"],
                "title": detected_tables[i]["title"],
                "page": page_num + 1,
                "type": "table"
            })
        else:
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
    text = text.strip()
    page_str = str(page_num + 1)
    
    # 只有页码数字的情况（如 "1", "2", " 3 "）
    if text == page_str or re.match(r'^\s*\d+\s*$', text):
        return True
    
    # 常见页眉页脚模式
    header_footer_patterns = [
        r'^Page\s+\d+$',  # Page 1
        r'^第\s*\d+\s*页$',  # 第1页
        r'^\d+\s*/\s*\d+$',  # 1/10
        r'^©\s*\d{4}',  # 版权信息
        r'^Draft\s+',  # 草稿
        r'^Confidential\s+',  # 机密
    ]
    
    for pattern in header_footer_patterns:
        if re.match(pattern, text):
            return True
    
    return False


def _split_references(references_raw: str) -> List[Dict[str, Any]]:
    """
    将参考文献原始文本逐条拆分为结构化列表
    
    :param references_raw: 参考文献原始文本
    :return: 参考文献条目列表
    """
    references = []
    
    if not references_raw.strip():
        return references
    
    # 参考文献编号模式（支持多种格式）
    # 格式1: [1] Author. Title. Journal, Year.
    # 格式2: 1. Author. Title. Journal, Year.
    # 格式3: [1] Author, Title, Journal, Year.
    reference_patterns = [
        r'(\[\d+\])\s*(.+?)(?=\[\d+\]|\Z)',
        r'(\d+\.)\s*(.+?)(?=\d+\.|\Z)'
    ]
    
    for pattern in reference_patterns:
        matches = re.finditer(pattern, references_raw, re.DOTALL)
        for match in matches:
            number = match.group(1).strip()
            content = match.group(2).strip()
            if content:
                references.append({
                    "number": number,
                    "content": content
                })
    
    # 如果没有匹配到任何模式，按换行尝试拆分
    if not references:
        lines = references_raw.split('\n')
        current_ref = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 检测是否是新条目（以数字或 [数字] 开头）
            if re.match(r'^\[\d+\]|\d+\.', line):
                if current_ref:
                    references.append({
                        "number": "",
                        "content": current_ref.strip()
                    })
                current_ref = line
            else:
                current_ref += " " + line
        if current_ref:
            references.append({
                "number": "",
                "content": current_ref.strip()
            })
    
    return references


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

        # 单段超长（PDF 偶尔把整节正文/图注堆成一个无空行的大 block，split('\n\n') 拆不开）：
        # chunk_size 只在段落之间判断、从不在段落内部切，这种大段会整块穿过去 → 生成超大 chunk
        # → 撑爆 MySQL TEXT(64KB)，且嵌入模型(512 token)会截断。这里先冲刷当前块，再按 chunk_size
        # 带重叠硬切，尾巴留给后文继续合并。
        if len(paragraph) > chunk_size:
            if current_chunk and len(current_chunk.strip()) >= min_chunk_size:
                chunks.append({
                    "content": current_chunk.strip(),
                    "section_title": section_title,
                    "page_number": page_number,
                    "paragraph_index": paragraph_index
                })
                paragraph_index += 1
            current_chunk = ""
            step = max(1, chunk_size - chunk_overlap)
            start = 0
            while len(paragraph) - start > chunk_size:
                piece = paragraph[start:start + chunk_size].strip()
                if len(piece) >= min_chunk_size:
                    chunks.append({
                        "content": piece,
                        "section_title": section_title,
                        "page_number": page_number,
                        "paragraph_index": paragraph_index
                    })
                    paragraph_index += 1
                start += step
            current_chunk = paragraph[start:] + "\n\n"  # 尾巴（≤ chunk_size）留给后文合并
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