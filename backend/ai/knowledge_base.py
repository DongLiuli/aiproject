"""知识库构建模块"""
import os
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
            cls._model = SentenceTransformer(MODEL_CONFIG["embedding_model"])
        return cls._model


def build_knowledge_base(paper_id: str, sections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    构建论文知识库
    
    :param paper_id: 论文 ID
    :param sections: 章节列表
    :return: 构建结果
    """
    try:
        model = KnowledgeBase.get_model()
        
        # 收集所有分块
        all_chunks = []
        for section in sections:
            chunks = chunk_text(
                section["content"],
                section["title"],
                section["page_start"]
            )
            all_chunks.extend(chunks)
        
        if not all_chunks:
            return {"success": False, "error": "无法从论文中提取有效内容"}
        
        # 向量化
        contents = [chunk["content"] for chunk in all_chunks]
        embeddings = model.encode(contents)
        
        # 创建 FAISS 索引
        dimension = MODEL_CONFIG["embedding_dim"]
        index = faiss.IndexFlatL2(dimension)
        index.add(np.array(embeddings))
        
        # 保存索引文件
        index_path = os.path.join(VECTOR_DIR, f"{paper_id}.index")
        faiss.write_index(index, index_path)
        
        # 返回分块数据（供 A 写入数据库）
        chunks_for_db = []
        for i, chunk in enumerate(all_chunks):
            chunks_for_db.append({
                "paper_id": paper_id,
                "section_title": chunk["section_title"],
                "page_number": chunk["page_number"],
                "paragraph_index": chunk["paragraph_index"],
                "content": chunk["content"],
                "embedding": embeddings[i].tolist()
            })
        
        return {
            "success": True,
            "message": f"知识库构建完成，共 {len(all_chunks)} 个分块",
            "chunks": chunks_for_db,
            "chunk_count": len(all_chunks)
        }
    
    except Exception as e:
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
    :param chunks_data: 分块数据（可选，外部传入以解耦数据库依赖）
    :return: 检索结果列表
    """
    index_path = os.path.join(VECTOR_DIR, f"{paper_id}.index")
    
    if not os.path.exists(index_path):
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
        
        # 获取分块数据（优先使用外部传入的数据）
        if chunks_data is not None:
            chunks = chunks_data
        else:
            try:
                from ..app.models import get_db, Chunk
                db = next(get_db())
                chunks = db.query(Chunk).filter(Chunk.paper_id == paper_id).order_by(Chunk.page_number, Chunk.paragraph_index).all()
            except ImportError:
                return []
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx >= 0 and idx < len(chunks):
                chunk = chunks[idx]
                if hasattr(chunk, 'content'):
                    results.append({
                        "content": chunk.content,
                        "section_title": chunk.section_title,
                        "page": chunk.page_number,
                        "score": float(1 - distances[0][i] / 2)
                    })
                else:
                    results.append({
                        "content": chunk.get("content", ""),
                        "section_title": chunk.get("section_title", ""),
                        "page": chunk.get("page_number", 0),
                        "score": float(1 - distances[0][i] / 2)
                    })
        
        return results
    
    except Exception as e:
        import logging
        logging.error(f"search_chunks error: {str(e)}")
        return []