"""
手动添加 is_recommended 和 recommend_order 列到 papers 表
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'literature.db')

print(f"连接数据库: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 检查列是否已存在
cursor.execute("PRAGMA table_info(papers)")
columns = [col[1] for col in cursor.fetchall()]
print(f"当前 papers 表的列: {columns}")

try:
    if 'is_recommended' not in columns:
        print("添加 is_recommended 列...")
        cursor.execute("ALTER TABLE papers ADD COLUMN is_recommended BOOLEAN DEFAULT 0")
        print("✓ is_recommended 列添加成功")
    
    if 'recommend_order' not in columns:
        print("添加 recommend_order 列...")
        cursor.execute("ALTER TABLE papers ADD COLUMN recommend_order INTEGER")
        print("✓ recommend_order 列添加成功")
    
    conn.commit()
    print("\n✓ 数据库更新成功！")
    
    # 再次检查确认
    cursor.execute("PRAGMA table_info(papers)")
    new_columns = [col[1] for col in cursor.fetchall()]
    print(f"更新后的列: {new_columns}")
    
except Exception as e:
    print(f"\n✗ 错误: {e}")
    conn.rollback()
finally:
    conn.close()
