# API 约定文档

> 全体共用。三人开发时所有接口必须严格遵循此文档。
> 丢给 LLM 分析时请全文粘贴。

---

## 通用规范

| 项目 | 约定 |
|------|------|
| 接口前缀 | 全部以 `/api/` 开头 |
| 字段命名 | `snake_case`（paper_id、conversation_id、user_id） |
| 分页 | 请求 `?page=1&size=20`，返回 `{"items": [...], "total": 0, "page": 1, "size": 20}` |
| 错误返回 | `{"error": {"code": "PAPER_NOT_FOUND", "message": "描述"}}` |
| 身份传递 | 匿名：`X-Session-ID: sess_xxx` / 登录：`Authorization: Bearer xxx` |
| 后端地址 | `http://localhost:8000` |

---

## 全部接口

### 用户与认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/anonymous` | 建立匿名 Session |
| POST | `/api/auth/register` | 用户注册 |
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/merge-anonymous` | 合并匿名数据到登录账户 |
| GET | `/api/user/me` | 获取当前用户信息与统计 |
| GET | `/api/user/config` | 获取 API Key 配置 |
| PUT | `/api/user/config` | 更新 API Key 与模型选择 |
| POST | `/api/user/config/test` | 测试 API Key 连接 |

### 论文管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/papers` | 论文列表（分页+搜索+筛选） |
| POST | `/api/papers/upload` | 上传 PDF（触发异步解析） |
| GET | `/api/papers/{paper_id}` | 论文详情（含结构化信息+原文） |
| PUT | `/api/papers/{paper_id}` | 更新论文（标签、阅读状态） |
| DELETE | `/api/papers/{paper_id}` | 删除论文及关联数据 |
| POST | `/api/papers/{paper_id}/reparse` | 重新触发解析 |

### 问答

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/qa/{paper_id}` | 论文问答（单轮/多轮） |
| GET | `/api/qa/{paper_id}/history` | 获取对话历史 |

### 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/reports/{paper_id}` | 生成研读报告 |

---

## 接口详细定义

### POST /api/auth/anonymous

```
请求头：无
请求体：无

返回 200：
{
  "session_id": "sess_a1b2c3d4",
  "has_existing_data": false
}
```

### POST /api/auth/register

```
请求头：X-Session-ID（当前匿名 Session）
请求体：
{
  "username": "zhang",
  "password": "123456"
}

返回 201：
{
  "user_id": "user_zhang",
  "username": "zhang",
  "token": "eyJhbGciOi...",
  "merged_items": {"papers": 3, "conversations": 5}
}

异常：
409 — 用户名已存在
400 — 密码不足6位
```

### POST /api/auth/login

```
请求头：X-Session-ID（当前匿名 Session）
请求体：
{
  "username": "zhang",
  "password": "123456"
}

返回 200：
{
  "user_id": "user_zhang",
  "username": "zhang",
  "token": "eyJhbGciOi...",
  "has_anonymous_data": true,
  "anonymous_data_summary": {"papers": 3, "conversations": 5}
}

异常：
401 — 用户名或密码错误
```

### POST /api/auth/merge-anonymous

```
请求头：Authorization: Bearer xxx
请求体：
{
  "anonymous_session_id": "sess_a1b2c3d4"
}

返回 200：
{
  "merged": true,
  "papers_migrated": 3,
  "conversations_migrated": 5
}
```

### GET /api/user/me

```
请求头：Authorization: Bearer xxx（或 X-Session-ID）

返回 200：
{
  "user_id": "user_zhang",
  "username": "zhang",
  "is_anonymous": false,
  "config": {"api_key_configured": true, "model": "deepseek-v3"},
  "stats": {"paper_count": 12, "total_questions": 45}
}
```

### GET /api/user/config

```
请求头：Authorization: Bearer xxx（或 X-Session-ID）

返回 200：
{
  "api_key": "sk-xxx***c8d",      // 脱敏显示
  "api_key_configured": true,
  "model": "deepseek-v3"
}
```

### PUT /api/user/config

```
请求体：
{
  "api_key": "sk-abc123def456",
  "model": "qwen-3"
}

返回 200：
{
  "api_key": "sk-abc***456",
  "model": "qwen-3"
}
```

### POST /api/user/config/test

```
请求头：Authorization: Bearer xxx

返回 200：
{ "ok": true }

返回 200（失败）：
{ "ok": false, "error": "Key 无效或余额不足" }
```

### GET /api/papers

```
请求头：Authorization: Bearer xxx（或 X-Session-ID）
参数：?keyword=Transformer&tag=NLP&status=completed&page=1&size=20

返回 200：
{
  "items": [
    {
      "paper_id": "p_abc123",
      "title": "Attention Is All You Need",
      "authors": ["Vaswani, Ashish"],
      "file_name": "attention.pdf",
      "file_size": 2048000,
      "upload_time": "2026-06-23T10:30:00",
      "parse_status": "completed",
      "field": "NLP",
      "tags": ["Transformer"],
      "read_status": "unread"
    }
  ],
  "total": 12,
  "page": 1,
  "size": 20
}
```

### POST /api/papers/upload

```
请求头：Authorization: Bearer xxx（或 X-Session-ID）
请求体：multipart/form-data
       ├── file: attention.pdf
       ├── field: "NLP"（可选）
       └── tags: "Transformer,Attention"（可选）

返回 201：
{
  "paper_id": "p_abc123",
  "title": "attention.pdf",
  "file_size": 2048000,
  "upload_time": "2026-06-23T10:30:00",
  "parse_status": "pending",
  "field": "NLP",
  "tags": ["Transformer", "Attention"]
}

异常：
400 — 非 PDF 格式
413 — 文件大小超过 50MB
422 — PDF 损坏或无法读取
```

### GET /api/papers/{paper_id}

```
请求头：Authorization: Bearer xxx

返回 200：
{
  "paper_id": "p_abc123",
  "title": "Attention Is All You Need",
  "authors": ["Vaswani, Ashish"],
  "parse_status": "completed",
  "field": "NLP",
  "tags": ["Transformer"],
  "read_status": "unread",
  "structured_info": {
    "research_background": "...",
    "research_questions": "...",
    "method_flow": "...",
    "innovations": "...",
    "limitations": "...",
    "figures_tables": [
      {"number": "Table 1", "title": "BLEU scores", "page": 5}
    ]
  },
  "full_text": "第1页内容...\n===第2页===\n...",
  "sections": [
    {"title": "1. Introduction", "content": "...", "page_start": 1, "page_end": 3}
  ]
}

异常：
404 — 论文不存在
403 — 无权访问
```

### PUT /api/papers/{paper_id}

```
请求体：
{
  "tags": ["NLP", "要精读"],
  "read_status": "read"
}

返回 200：
{ ... 更新后的完整论文对象 ... }
```

### DELETE /api/papers/{paper_id}

```
请求头：Authorization: Bearer xxx

返回 200：
{ "deleted": true }
```

### POST /api/papers/{paper_id}/reparse

```
请求头：Authorization: Bearer xxx

返回 200：
{
  "paper_id": "p_abc123",
  "parse_status": "parsing"
}

异常：
400 — 论文正在解析中
```

### POST /api/qa/{paper_id}

```
请求头：Authorization: Bearer xxx
请求体：
{
  "question": "这篇论文的核心创新点是什么？",
  "conversation_id": null          // 第一轮传 null，后续传上次返回的 ID
}

返回 200：
{
  "answer": "核心创新点在于提出了 Transformer 架构...",
  "sources": [
    {
      "page": 2,
      "section": "1. Introduction",
      "snippet": "论文原文摘录..."
    }
  ],
  "conversation_id": "conv_001"
}

异常：
400 — 论文尚未完成解析
502 — LLM API 调用失败
```

### GET /api/qa/{paper_id}/history

```
请求头：Authorization: Bearer xxx

返回 200：
{
  "conversations": [
    {
      "conversation_id": "conv_001",
      "created_at": "2026-06-23T10:30:00",
      "messages": [
        {"role": "user", "content": "核心创新点是什么？", "created_at": "..."},
        {"role": "assistant", "content": "核心创新点在于...", "sources": [...], "created_at": "..."}
      ]
    }
  ]
}
```

### POST /api/reports/{paper_id}

```
请求头：Authorization: Bearer xxx
请求体：
{
  "report_type": "quick"          // "quick" | "method" | "experiment"
}

返回 200：
{
  "report_id": "rpt_001",
  "report_type": "quick",
  "content": "# 速读报告\n\n## 论文基本信息\n...",
  "format": "markdown",
  "generated_at": "2026-06-23T11:00:00"
}

异常：
400 — 论文尚未完成解析
```
