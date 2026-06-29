import uuid
import json
from datetime import datetime

from sqlalchemy import Column, String, Integer, DateTime, Boolean, JSON, ForeignKey, create_engine, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT, LONGTEXT
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False,  # 生产环境关闭 SQL 日志
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def generate_uuid():
    return str(uuid.uuid4())


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(100), nullable=True, unique=True)
    password_hash = Column(String(255), nullable=True)
    is_anonymous = Column(Boolean, default=False)
    api_key_encrypted = Column(Text, nullable=True)
    model_preference = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关联
    papers = relationship("Paper", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")

    def to_dict(self):
        return {
            "user_id": self.id,
            "username": self.username,
            "is_anonymous": self.is_anonymous,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Admin(Base):
    __tablename__ = "admins"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "admin_id": self.id,
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Paper(Base):
    __tablename__ = "papers"

    paper_id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=True)
    authors = Column(JSON, nullable=True)       # list[str]
    file_name = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String(1000), nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    parse_status = Column(String(20), default="pending")  # pending / parsing / completed / failed
    parse_error = Column(Text, nullable=True)
    field = Column(String(200), nullable=True)       # 学科方向
    tags = Column(JSON, nullable=True)           # list[str]
    read_status = Column(String(20), default="unread")  # unread / skimmed / read / noted

    # 关联
    user = relationship("User", back_populates="papers")
    structured_info = relationship("PaperStructuredInfo", back_populates="paper", uselist=False)
    chunks = relationship("Chunk", back_populates="paper")
    conversations = relationship("Conversation", back_populates="paper")

    def to_dict(self):
        return {
            "paper_id": self.paper_id,
            "user_id": self.user_id,
            "title": self.title,
            "authors": self.authors or [],
            "file_name": self.file_name,
            "file_size": self.file_size,
            "upload_time": self.upload_time.isoformat() if self.upload_time else None,
            "parse_status": self.parse_status,
            "parse_error": self.parse_error,
            "field": self.field,
            "tags": self.tags or [],
            "read_status": self.read_status,
        }


class PaperStructuredInfo(Base):
    __tablename__ = "paper_structured_info"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    paper_id = Column(String(36), ForeignKey("papers.paper_id"), unique=True, nullable=False)
    research_background = Column(MEDIUMTEXT, nullable=True)
    research_questions = Column(MEDIUMTEXT, nullable=True)
    method_flow = Column(MEDIUMTEXT, nullable=True)
    model_algorithm = Column(String(500), nullable=True)
    dataset_info = Column(MEDIUMTEXT, nullable=True)
    evaluation_metrics = Column(JSON, nullable=True)
    experiment_results = Column(MEDIUMTEXT, nullable=True)
    innovations = Column(MEDIUMTEXT, nullable=True)
    limitations = Column(MEDIUMTEXT, nullable=True)
    future_work = Column(MEDIUMTEXT, nullable=True)
    figures_tables = Column(JSON, nullable=True)   # list[dict]
    references = Column(JSON, nullable=True)        # list[dict]
    full_text = Column(LONGTEXT, nullable=True)  # 提取的原文文本
    sections = Column(JSON, nullable=True)          # list[dict]
    extracted_at = Column(DateTime, default=datetime.utcnow)

    paper = relationship("Paper", back_populates="structured_info")

    def _try_json(self, value, default=None):
        """尝试 JSON 反序列化，失败则返回原值（兼容 Text 列存了字符串或已序列化的 JSON）"""
        if value is None:
            return default
        if isinstance(value, (list, dict)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value

    def to_dict(self):
        return {
            "research_background": self.research_background,
            "research_questions": self.research_questions,
            "method_flow": self.method_flow,
            "model_algorithm": self.model_algorithm,
            "dataset_info": self.dataset_info,
            "evaluation_metrics": self._try_json(self.evaluation_metrics, []),
            "experiment_results": self.experiment_results,
            "innovations": self._try_json(self.innovations, []),
            "limitations": self._try_json(self.limitations, []),
            "future_work": self.future_work,
            "figures_tables": self._try_json(self.figures_tables, []),
            "references": self._try_json(self.references, []),
            "sections": self._try_json(self.sections, []),
        }


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id = Column(String(36), primary_key=True, default=generate_uuid)
    paper_id = Column(String(36), ForeignKey("papers.paper_id"), nullable=False)
    section_title = Column(String(500), nullable=True)
    page_number = Column(Integer, nullable=True)
    paragraph_index = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)

    paper = relationship("Paper", back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id = Column(String(36), primary_key=True, default=generate_uuid)
    paper_id = Column(String(36), ForeignKey("papers.paper_id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    paper = relationship("Paper", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(36), ForeignKey("conversations.conversation_id"), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=True)  # list[dict] — 仅 assistant 消息有
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class Report(Base):
    __tablename__ = "reports"

    report_id = Column(String(36), primary_key=True, default=generate_uuid)
    paper_id = Column(String(36), ForeignKey("papers.paper_id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    report_type = Column(String(20), nullable=False)  # quick / method / experiment
    content = Column(Text, nullable=False)
    format = Column(String(20), default="markdown")
    generated_at = Column(DateTime, default=datetime.utcnow)
