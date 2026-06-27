"""知识库构建模块"""
import os
import logging
import time

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Any
from .config import MODEL_CONFIG, VECTOR_DIR, CHUNK_CONFIG, SEARCH_CONFIG
from .pdf_parser import chunk_text


class KnowledgeBase:
    """知识库管理类"""
    
    _instance = None
    _model = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KnowledgeBase, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def get_model(cls):
        """获取嵌入模型（单例）"""
        if cls._model is None:
            start_time = time.time()
            model_name = MODEL_CONFIG["embedding_model"]
            logging.info(f"[知识库] 开始加载嵌入模型: {model_name} (第一次加载较慢)")
            logging.info(f"[知识库] HF_ENDPOINT = {os.environ.get('HF_ENDPOINT', '未设置')}")
            
            local_model_path = os.environ.get("MODEL_LOCAL_PATH", "")
            if local_model_path and os.path.exists(local_model_path):
                logging.info(f"[知识库] 从本地路径加载模型: {local_model_path}")
                load_start = time.time()
                cls._model = SentenceTransformer(local_model_path)
                load_time = time.time() - load_start
                logging.info(f"[知识库] 本地模型加载完成，耗时 {load_time:.2f}s")
            else:
                try:
                    logging.info(f"[知识库] 开始在线加载模型...")
                    load_start = time.time()
                    cls._model = SentenceTransformer(model_name)
                    load_time = time.time() - load_start
                    logging.info(f"[知识库] 在线加载完成，耗时 {load_time:.2f}s")
                except Exception as e:
                    logging.warning(f"[知识库] 在线加载失败，尝试本地缓存: {str(e)}")
                    try:
                        load_start = time.time()
                        cls._model = SentenceTransformer(model_name, local_files_only=True)
                        load_time = time.time() - load_start
                        logging.info(f"[知识库] 本地缓存加载完成，耗时 {load_time:.2f}s")
                    except Exception as e2:
                        raise RuntimeError(
                            f"嵌入模型加载失败：\n"
                            f"  在线加载失败: {str(e)}\n"
                            f"  本地缓存加载失败: {str(e2)}\n"
                            f"建议：\n"
                            f"  1. 检查网络连接或设置 HF_ENDPOINT 环境变量\n"
                            f"  2. 或设置 MODEL_LOCAL_PATH 指向本地模型目录"
                        )
            
            total_time = time.time() - start_time
            logging.info(f"[知识库] 嵌入模型加载成功！总耗时 {total_time:.2f}s")
        return cls._model


def build_knowledge_base(paper_id: str, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    构建论文知识库

    :param paper_id: 论文 ID
    :param sections: 章节列表
    :return: 构建结果
    """
    try:
        start_time = time.time()
        logging.info(f"[知识库] 开始构建知识库 - {paper_id}")

        # 步骤 1: 获取模型
        step_start = time.time()
        model = KnowledgeBase.get_model()
        step_time = time.time() - step_start
        logging.info(f"[知识库] 步骤1/5: 获取模型完成，耗时 {step_time:.2f}s")

        # 步骤 2: 收集所有分块
        step_start = time.time()
        all_chunks = []
        for section in sections:
            chunks = chunk_text(
                section["content"],
                section["title"],
                section["page_start"]
            )
            all_chunks.extend(chunks)
        step_time = time.time() - step_start
        logging.info(f"[知识库] 步骤2/5: 共提取 {len(all_chunks)} 个分块，耗时 {step_time:.2f}s")

        if not all_chunks:
            logging.warning(f"[知识库] 未提取到有效分块 - {paper_id}")
            return {"success": False, "error": "无法从论文中提取有效内容"}

        # 步骤 3: 向量化
        step_start = time.time()
        contents = [chunk["content"] for chunk in all_chunks]
        logging.info(f"[知识库] 步骤3/5: 开始向量化 {len(contents)} 个分块...")
        embeddings = model.encode(contents)
        embeddings = np.array(embeddings).astype(np.float32)
        step_time = time.time() - step_start
        logging.info(f"[知识库] 步骤3/5: 向量化完成，维度 {embeddings.shape}，耗时 {step_time:.2f}s")

        # 步骤 4: 创建 FAISS 索引
        step_start = time.time()
        dimension = MODEL_CONFIG["embedding_dim"]
        index = faiss.IndexFlatL2(dimension)
        index.add(embeddings)
        step_time = time.time() - step_start
        logging.info(f"[知识库] 步骤4/5: FAISS 索引创建完成，耗时 {step_time:.2f}s")

        # 步骤 5: 保存索引文件
        step_start = time.time()
        os.makedirs(VECTOR_DIR, exist_ok=True)
        index_path = os.path.join(VECTOR_DIR, f"{paper_id}.index")
        faiss.write_index(index, index_path)
        step_time = time.time() - step_start
        logging.info(f"[知识库] 步骤5/5: 索引文件已保存 - {index_path}，耗时 {step_time:.2f}s")

        # 返回分块数据（供 A 写入数据库，不包含 faiss_index 和 embedding，因为模型没有这些字段）
        chunks_for_db = []
        for chunk in all_chunks:
            chunks_for_db.append({
                "paper_id": paper_id,
                "section_title": chunk["section_title"],
                "page_number": chunk["page_number"],
                "paragraph_index": chunk["paragraph_index"],
                "content": chunk["content"]
            })

        total_time = time.time() - start_time
        logging.info(f"[知识库] 知识库构建全部完成！总耗时 {total_time:.2f}s，共 {len(all_chunks)} 个分块")

        return {
            "success": True,
            "message": f"知识库构建完成，共 {len(all_chunks)} 个分块",
            "chunks": chunks_for_db,
            "chunk_count": len(all_chunks)
        }

    except Exception as e:
        total_time = time.time() - start_time if 'start_time' in locals() else 0
        logging.error(f"[知识库] 构建失败: {str(e)} - {paper_id}，已耗时 {total_time:.2f}s")
        return {"success": False, "error": f"构建知识库失败: {str(e)}"}


def delete_index(paper_id: str) -> Dict[str, Any]:
    """
    删除论文索引
    
    :param paper_id: 论文 ID
    :return: 删除结果
    """
    index_path = os.path.join(VECTOR_DIR, f"{paper_id}.index")
    
    if os.path.exists(index_path):
        os.remove(index_path)
        return {"success": True, "message": "索引已删除"}
    else:
        return {"success": False, "error": "索引文件不存在"}


def search_chunks(paper_id: str, query: str, k: int = 5, chunks_data: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    检索相关分块

    :param paper_id: 论文 ID
    :param query: 查询文本
    :param k: 返回条数
    :param chunks_data: 分块数据（必须，外部传入以解耦数据库依赖）
    :return: 检索结果列表
    """
    index_path = os.path.join(VECTOR_DIR, f"{paper_id}.index")

    if not os.path.exists(index_path):
        logging.warning(f"search_chunks: 索引文件不存在 - {paper_id}")
        return []

    if chunks_data is None:
        logging.error(f"search_chunks: chunks_data 为 None，请从外部传入分块数据 - {paper_id}")
        return []

    try:
        model = KnowledgeBase.get_model()

        # 加载索引
        index = faiss.read_index(index_path)

        # 向量化查询
        query_embedding = model.encode([query])

        # 搜索
        k = min(k, SEARCH_CONFIG["top_k"])
        distances, indices = index.search(np.array(query_embedding), k)

        # 准备chunks列表，确保顺序正确
        chunks = []
        for chunk in chunks_data:
            if hasattr(chunk, 'content'):
                chunks.append({
                    "content": chunk.content,
                    "section_title": chunk.section_title,
                    "page": chunk.page_number
                })
            elif isinstance(chunk, dict):
                chunks.append({
                    "content": chunk.get("content", ""),
                    "section_title": chunk.get("section_title", ""),
                    "page": chunk.get("page_number", 0)
                })

        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(chunks):
                chunk = chunks[idx]
                results.append({
                    "content": chunk["content"],
                    "section_title": chunk["section_title"],
                    "page": chunk["page"],
                    "score": float(1 - distances[0][i] / 2)
                })

        logging.info(f"search_chunks: 检索到 {len(results)} 条结果 - {paper_id}, query={query[:20]}")
        return results

    except Exception as e:
        logging.error(f"search_chunks error: {str(e)} - paper_id={paper_id}")
        return []