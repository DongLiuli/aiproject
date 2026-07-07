# -*- coding: utf-8 -*-
"""从 arXiv 拉取各领域近3年相关论文，下载 PDF 到 data/recom/。
arXiv PDF (arxiv.org/pdf/{id}) 100% 可下、无 403。arXiv 无被引数据，
故按「相关度排序 + 限定 2023 起」近似「顶尖最新」。生成 manifest.json。可重复运行。"""
import os
import re
import sys
import json
import time
import requests
import xml.etree.ElementTree as ET

# Windows 控制台 GBK 印不出部分字符 → 强制 utf-8
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recom")
os.makedirs(OUT_DIR, exist_ok=True)

API = "http://export.arxiv.org/api/query"
PER_FIELD = 3
DATE_RANGE = "[202301010000 TO 202612312359]"   # 近3年
ATOM = "{http://www.w3.org/2005/Atom}"
UA = {"User-Agent": "literature-ai/1.0 (mailto:literature-ai@example.com)"}

# 领域 -> arXiv 检索表达式
FIELDS = {
    "大语言模型": 'cat:cs.CL AND abs:"large language model"',
    "计算机视觉": 'cat:cs.CV AND abs:"object detection"',
    "自然语言处理": 'cat:cs.CL AND abs:"transformer"',
    "强化学习": 'cat:cs.LG AND abs:"reinforcement learning"',
    "图神经网络": 'abs:"graph neural network"',
    "生成模型": 'abs:"diffusion model"',
    "多模态": 'cat:cs.CV AND abs:"multimodal"',
    "语音处理": 'abs:"speech recognition"',
    "推荐系统": 'cat:cs.IR AND abs:"recommendation"',
    "机器人": 'cat:cs.RO AND abs:"learning"',
}


def safe_name(s, n=60):
    s = re.sub(r"[^\w一-龥 \-]", "", s or "").strip().replace(" ", "_")
    return s[:n] or "paper"


def arxiv_search(query):
    params = {
        "search_query": f"({query}) AND submittedDate:{DATE_RANGE}",
        "sortBy": "relevance", "sortOrder": "descending",
        "start": 0, "max_results": 8,
    }
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.text
        except requests.RequestException as e:
            print(f"  搜索重试 {attempt+1}: {e}")
        time.sleep(3)
    return ""


def parse_entries(xml_text):
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for e in root.findall(f"{ATOM}entry"):
        abs_url = (e.findtext(f"{ATOM}id") or "").strip()
        title = re.sub(r"\s+", " ", (e.findtext(f"{ATOM}title") or "").strip())
        published = (e.findtext(f"{ATOM}published") or "")[:10]
        if not abs_url:
            continue
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1]
        pdf_url = abs_url.replace("/abs/", "/pdf/")
        out.append({"id": arxiv_id, "title": title, "published": published,
                    "abs_url": abs_url, "pdf_url": pdf_url})
    return out


def download_pdf(url, path):
    try:
        r = requests.get(url, headers=UA, timeout=60, stream=True, allow_redirects=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        buf = b""
        for chunk in r.iter_content(65536):
            buf += chunk
            if len(buf) > 50 * 1024 * 1024:
                break
        if not buf[:5].startswith(b"%PDF"):
            return False, "非 PDF"
        with open(path, "wb") as f:
            f.write(buf)
        return True, len(buf)
    except requests.RequestException as e:
        return False, str(e)[:80]


manifest = []
total_ok = 0
for field, query in FIELDS.items():
    print(f"\n=== {field} ===")
    entries = parse_entries(arxiv_search(query))
    got = 0
    for it in entries:
        if got >= PER_FIELD:
            break
        fname = f"{safe_name(field,8)}_{it['id'].replace('/', '_')}_{safe_name(it['title'],45)}.pdf"
        fpath = os.path.join(OUT_DIR, fname)
        if os.path.exists(fpath):
            print(f"  [skip] {it['title'][:55]}")
            got += 1
            continue
        ok, info = download_pdf(it["pdf_url"], fpath)
        if ok:
            got += 1
            total_ok += 1
            manifest.append({"field": field, "title": it["title"], "published": it["published"],
                             "arxiv_id": it["id"], "pdf_url": it["pdf_url"],
                             "abs_url": it["abs_url"], "file": fname})
            print(f"  [OK {info//1024}KB] {it['published']} | {it['title'][:55]}")
        else:
            print(f"  [FAIL {info}] {it['title'][:45]}")
        time.sleep(1.0)
    if got < PER_FIELD:
        print(f"  (only {got}/{PER_FIELD})")
    time.sleep(3)   # arXiv 礼貌间隔

with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)

print(f"\n==== done: {total_ok} new downloaded, manifest {len(manifest)} entries ====")
print(f"dir: {OUT_DIR}")
