"""
检查和修复数据库
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'literature.db')

print("连接数据库...")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查列是否已存在
cursor.execute("PRAGMA table_info(papers)")
columns = [col[1] for col in cursor.fetchall()]
print(f"当前 papers 表的列: {columns}")

if 'is_recommended' in columns and 'recommend_order' in columns:
    print("\nOK: 所有列都已存在！")
    conn.close()
    exit(0)

try:
    if 'is_recommended' not in columns:
        print("添加 is_recommended 列...")
        cursor.execute("ALTER TABLE papers ADD COLUMN is_recommended BOOLEAN DEFAULT 0")
        print("OK: is_recommended 列添加成功")
    
    if 'recommend_order' not in columns:
        print("添加 recommend_order 列...")
        cursor.execute("ALTER TABLE papers ADD COLUMN recommend_order INTEGER")
        print("OK: recommend_order 列添加成功")
    
    conn.commit()
    print("\n数据库更新成功！")
    
except Exception as e:
    print(f"错误: {e}")
    conn.rollback()
finally:
    conn.close()
