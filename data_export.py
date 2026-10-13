# -*- coding: utf-8 -*-
"""
澳门巴士爬虫数据 —— 小组汇总导出脚本 ()

code framework:
  step 1: find_db / ask_member: find database and ask name
  step 2: open database, Put the three tables pages / stations / buses, and export each into a csv file

running method - terminal (need to put .py and .db in the same folder):
1. `python data_export.py`
2. enter your name
3. zip and send

"""

import os
import sys
import csv
import sqlite3
import zipfile
import datetime

# ============ config ============
OUT_PARENT = os.path.dirname(os.path.abspath(__file__))  # output path
DB_CANDIDATES = ["macau_bus.db"]  # find database
CSV_ENCODING = "utf-8-sig"        # Excel 直接打开中文不乱码
# ==========================================


def log(msg=""):
    print(msg)


def find_db():
    # 方法 C / B：命令行参数或拖拽
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        return os.path.abspath(sys.argv[1])
    here = os.path.dirname(os.path.abspath(__file__))
    for name in DB_CANDIDATES:
        p = os.path.join(here, name)
        if os.path.isfile(p):
            return p
    # 同目录里只有一个 db 时也自动认
    dbs = []
    for f in os.listdir(here):
        if f.lower().endswith(".db"):
            dbs.append(f)
    if len(dbs) == 1:
        return os.path.join(here, dbs[0])
    return None


def ask_member(cli_name=None):
    if cli_name:
        name = cli_name.strip()
    else:
        name = ""
        while not name:
            name = input("请输入你的姓名（用于汇总时区分是谁的数据，必填）：").strip()
            if not name:
                print("姓名不能为空，请重新输入。")
    # 文件名里不允许出现的字符替换掉
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name


def check_schema(cur):
    """核对表结构，兼容旧版数据库。返回是否OK。"""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    table_rows = cur.fetchall()
    tables = []
    for row in table_rows:
        tables.append(row[0])
    missing = []
    for t in ("pages", "stations", "buses"):
        if t not in tables:
            missing.append(t)
    if missing:
        log("!! 数据库里缺少表：" + str(missing))
        log("   请确认你打开的是爬虫生成的 macau_bus.db，而不是别的文件。")
        return False
    return True


def export(db_path, member):
    conn = sqlite3.connect(db_path)
    conn.text_factory = str
    cur = conn.cursor()

    if not check_schema(cur):
        conn.close()
        return None

    out_dir = os.path.join(OUT_PARENT, f"data_{member}")
    os.makedirs(out_dir, exist_ok=True)

    # ---------- 1. pages：每轮抓取快照（扁平，带姓名）----------
    cur.execute("""
        SELECT id, crawl_time, route_name, direction, parsed
        FROM pages ORDER BY crawl_time
    """)
    pages_rows = cur.fetchall()
    pages_path = os.path.join(out_dir, "pages.csv")
    with open(pages_path, "w", newline="", encoding=CSV_ENCODING) as f:
        w = csv.writer(f)
        w.writerow(["member_name", "page_id", "crawl_time", "route_name",
                    "direction", "parsed"])
        for _id, t, route, dire, parsed in pages_rows:
            w.writerow([member, _id, t, route, dire, parsed])

    # ---------- 2. stations：站点清单（去重，带线路/方向/姓名）----------
    cur.execute("""
        SELECT DISTINCT p.route_name, p.direction, s.seq,
                        s.station_code, s.stopcode, s.station_name, s.lane_name
        FROM stations s JOIN pages p ON s.page_id = p.id
        ORDER BY p.route_name, p.direction, s.seq
    """)
    st_rows = cur.fetchall()
    st_path = os.path.join(out_dir, "stations.csv")
    with open(st_path, "w", newline="", encoding=CSV_ENCODING) as f:
        w = csv.writer(f)
        w.writerow(["member_name", "route_name", "direction", "seq",
                    "station_code", "stopcode", "station_name", "lane_name"])
        for row in st_rows:
            w.writerow([member] + list(row))

    # ---------- 3. buses：车辆明细（扁平，带时间/线路/方向/姓名）----------
    cur.execute("""
        SELECT p.crawl_time, p.route_name, p.direction,
               b.segment_seq, b.segment_station_code, b.bus_plate,
               b.speed_kmh, b.position_pct
        FROM buses b JOIN pages p ON b.page_id = p.id
        ORDER BY p.crawl_time
    """)
    bus_rows = cur.fetchall()
    bus_path = os.path.join(out_dir, "buses.csv")
    with open(bus_path, "w", newline="", encoding=CSV_ENCODING) as f:
        w = csv.writer(f)
        w.writerow(["member_name", "crawl_time", "route_name", "direction",
                    "segment_seq", "segment_station_code", "bus_plate",
                    "speed_kmh", "position_pct"])
        for row in bus_rows:
            w.writerow([member] + list(row))

    # ---------- 4. 自查信息 ----------
    log("\n================ 数据自查 ================")
    log(f"快照总轮次 pages : {len(pages_rows)}")
    log(f"站点记录(去重后) : {len(st_rows)}")
    log(f"车辆记录 buses   : {len(bus_rows)}")

    if pages_rows:
        tmin = pages_rows[0][1]
        tmax = pages_rows[-1][1]
        log(f"数据时间范围     : {tmin}  ~  {tmax}")

    log("\n各线路 / 方向 抓取轮次：")
    cur.execute("""
        SELECT route_name, direction, COUNT(*),
               substr(MIN(crawl_time),1,10), substr(MAX(crawl_time),1,10)
        FROM pages GROUP BY route_name, direction
        ORDER BY route_name, direction
    """)
    route_info = cur.fetchall()
    for route, dire, n, d0, d1 in route_info:
        log(f"   线路 {route:>4}  方向{dire} ：{n:>4} 轮   {d0} ~ {d1}")

    log("\n每天抓取轮次：")
    cur.execute("""
        SELECT substr(crawl_time,1,10) AS day, COUNT(*)
        FROM pages GROUP BY day ORDER BY day
    """)
    days_info = cur.fetchall()
    for day, n in days_info:
        log(f"   {day} : {n} 轮")

    cur.execute("SELECT COUNT(DISTINCT bus_plate) FROM buses")
    n_plate = cur.fetchone()[0]
    log(f"\n不同车牌数（观测车辆数）：{n_plate}")

    # 重点提醒：确认 15-19 号
    day_list = []
    for d, _ in days_info:
        day_list.append(d)
    hit = []                       # 实际抓到了哪几天目标日期
    for d in range(15, 20):
        target = "2026-10-%02d" % d
        if target in day_list:
            hit.append(target)
    log("\n------------------------------------------")
    if len(hit) == 5:
        log("已确认包含 10月15日~19日 全部 5 天数据。")
    elif hit:
        log(f"!! 只检测到这几天的数据：{hit}")
        log("   作业要求是 15~19 号，请确认你的爬虫是否跑满 5 天。")
    else:
        log("!! 没有检测到 10月15日~19日 的数据！")
        log("   请确认你导出的数据库是否正确（作业要求爬取 15~19 号）。")
    log("------------------------------------------")

    conn.close()

    # ---------- 5. 打包 zip，方便直接发 ----------
    zip_path = os.path.join(OUT_PARENT, f"提交_{member}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fn in ("pages.csv", "stations.csv", "buses.csv"):
            zf.write(os.path.join(out_dir, fn), arcname=f"提交_{member}/{fn}")

    size_kb = os.path.getsize(zip_path) / 1024
    log(f"\n导出完成！")
    log(f"文件夹：{out_dir}")
    log(f"压缩包：{zip_path}  （{size_kb:.0f} KB）")
    log("请把这个压缩包（或整个文件夹）发给组长。")
    return out_dir


def main():
    log("=" * 46)
    log("   澳门巴士爬虫数据 —— 小组汇总导出工具")
    log("=" * 46)
    db_path = find_db()
    if not db_path:
        log("\n没有找到 macau_bus.db！")
        log("请把本脚本和 macau_bus.db 放在同一个文件夹后重试，")
        log("或者直接把 macau_bus.db 文件拖到本脚本图标上运行。")
        input("\n按回车键退出...")
        return
    log(f"找到数据库：{db_path}")
    try:
        member = ask_member(sys.argv[2] if len(sys.argv) > 2 else None)
        result = export(db_path, member)
        if result is None:
            input("\n按回车键退出...")
            return
    except sqlite3.DatabaseError as e:
        log(f"\n!! 数据库打不开或已损坏：{e}")
    except Exception as e:
        log(f"\n!! 运行出错：{type(e).__name__}: {e}")
    input("\n按回车键退出...")


if __name__ == "__main__":
    main()
