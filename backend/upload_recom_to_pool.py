# -*- coding: utf-8 -*-
"""把 data/recom/ 里的 PDF 批量走 admin 接口上传进推荐池。
每篇 POST /api/admin/pool/upload → 挂系统账户 + 设推荐位 + 后台解析打标。
用法：先启动后端(uvicorn ...:8000)，再 python upload_recom_to_pool.py"""
import os
import sys
import time
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://localhost:8000"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
RECOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "recom")


def login():
    r = requests.post(f"{BASE}/api/admin/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    r.raise_for_status()
    tok = r.json().get("token") or r.json().get("access_token")
    if not tok:
        raise RuntimeError(f"登录成功但没拿到 token: {r.json()}")
    return tok


def main():
    if not os.path.isdir(RECOM_DIR):
        print(f"目录不存在: {RECOM_DIR}"); return
    pdfs = sorted(f for f in os.listdir(RECOM_DIR) if f.lower().endswith(".pdf"))
    if not pdfs:
        print("recom/ 里没有 PDF，先下载。"); return

    print(f"找到 {len(pdfs)} 个 PDF，登录管理员…")
    try:
        token = login()
    except Exception as e:
        print(f"登录失败（后端没起？账号不对？）: {e}"); return
    headers = {"Authorization": f"Bearer {token}"}

    ok = fail = 0
    for i, name in enumerate(pdfs, 1):
        path = os.path.join(RECOM_DIR, name)
        try:
            with open(path, "rb") as f:
                r = requests.post(f"{BASE}/api/admin/pool/upload",
                                  headers=headers,
                                  files={"file": (name, f, "application/pdf")},
                                  timeout=60)
            if r.status_code == 200:
                ok += 1
                print(f"[{i}/{len(pdfs)}] OK 入池解析中: {name[:60]}")
            else:
                fail += 1
                msg = r.json().get("detail", {}).get("error", {}).get("message", r.text[:80])
                print(f"[{i}/{len(pdfs)}] 失败 {r.status_code}: {msg} | {name[:50]}")
        except Exception as e:
            fail += 1
            print(f"[{i}/{len(pdfs)}] 异常: {str(e)[:80]} | {name[:50]}")
        time.sleep(0.5)

    print(f"\n==== 完成：{ok} 篇已提交入池（后台解析中），{fail} 篇失败 ====")
    print("解析进度可在 admin 页「推荐管理」查看；解析完成后自动打标并出现在推荐位。")


if __name__ == "__main__":
    main()
