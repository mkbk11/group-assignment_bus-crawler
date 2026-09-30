# -*- coding: utf-8 -*-
"""
把 SQLite 数据库里的爬取数据导出成 CSV 表格（方便用 Excel 打开查看）
================================================================
用法（终端里运行）：
    E:\Anaconda\python.exe export_to_csv.py
    E:\Anaconda\python.exe export_to_csv.py --db 其他数据库.db

导出 4 个文件（都会存到 export_data 文件夹里）：
    pages.csv      原始页面快照清单（每一轮爬取记录）
    stations.csv   所有站点明细
    buses.csv      所有车辆明细
    summary.csv    汇总表：每次爬取的站点数、车辆数（最方便看整体情况）
"""
import os
import sqlite3
import argparse
import pandas as pd

DB_PATH = "macau_bus.db"    # 爬虫生成的数据库；文件名不同就改这里
OUT_DIR = "export_data"     # CSV 输出文件夹（不存在会自动创建）


def export_table(con, table, columns="*"):
    """把一张表读出来存成 CSV。
    columns 可指定要导出的列（默认 * 表示全部列），
    例如 pages 表排除 html 二进制列，导出的表格才方便查看。"""
    df = pd.read_sql_query("SELECT %s FROM %s" % (columns, table), con)   # 读出指定列
    path = os.path.join(OUT_DIR, "%s.csv" % table)                        # 文件路径
    df.to_csv(path, index=False, encoding="utf-8-sig")                    # 存 CSV
    print("%s 已生成，共 %d 行" % (path, len(df)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="把爬取数据导出为 CSV")
    ap.add_argument("--db", default=DB_PATH, help="SQLite 数据库路径")
    args = ap.parse_args()
    DB_PATH = args.db

    os.makedirs(OUT_DIR, exist_ok=True)               # 没有 export_data 文件夹就自动创建
    con = sqlite3.connect(DB_PATH)                    # 打开数据库
    # pages 表排除 html 列（压缩的二进制源码，导出会变乱码且文件巨大）
    export_table(con, "pages", columns="id, crawl_time, route_name, direction, parsed")
    export_table(con, "stations")
    export_table(con, "buses")

    summary = pd.read_sql_query("""
        SELECT p.id,
               p.crawl_time,
               p.route_name,
               p.direction,
               COUNT(DISTINCT s.id) AS station_count,
               COUNT(b.id)          AS bus_count
        FROM pages p
        LEFT JOIN stations s ON s.page_id = p.id
        LEFT JOIN buses    b ON b.page_id = p.id
        GROUP BY p.id
    """, con)
    summary.to_csv(os.path.join(OUT_DIR, "summary.csv"), index=False,
                   encoding="utf-8-sig")
    print("%s 已生成，共 %d 行（每行 = 一次爬取快照）"
          % (os.path.join(OUT_DIR, "summary.csv"), len(summary)))
    con.close()
    print("完成！4 个 CSV 已生成到 %s 文件夹，用 Excel 打开即可查看。"
          % os.path.abspath(OUT_DIR))
