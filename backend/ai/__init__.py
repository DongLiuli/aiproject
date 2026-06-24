"""AI 管道模块 - 科研文献智能解析"""
from .pdf_parser import parse_pdf
from .info_extractor import extract_structured_info
from .knowledge_base import build_knowledge_base, delete_index, search_chunks
from .qa_generator import generate_answer
from .report_generator import generate_report
from .llm_client import LLMClient

__all__ = [
    "parse_pdf",
    "extract_structured_info",
    "build_knowledge_base",
    "delete_index",
    "search_chunks",
    "generate_answer",
    "generate_report",
    "LLMClient"
]