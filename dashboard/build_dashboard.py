# -*- coding: utf-8 -*-
"""
=====================================================================
 澳门巴士运行观测仪表盘 —— 数据汇总脚本（教学版，组长运行）
=====================================================================

【这个脚本干什么】
  把小组 6 个人爬来的数据（每人一个 .db，或导出的 3 个 csv）合并、
  统计，最后交给 Streamlit 界面显示。

【阅读指南 —— 代码就 5 个部分，从上往下看】
  第 1 部分  read_db / read_csv_group / collect_data：读数据
  第 2 部分  按“线路+方向”把数据分组（一辆巴士属于某条线路的某一帧快照）
  第 3 部分  calc_route：计算一条线路的全部统计指标
  第 4 部分  calc_members / build_overview：成员统计和总览数据
  第 5 部分  build_data：把统计结果组装成界面要用的数据
  main()    在命令行里做一次数据检查，并提示怎么打开界面

【数据放哪里】
  · 组员交来的「提交_姓名.zip」解压到 submissions/ 文件夹；
  · 或直接把 .db 文件放进 submissions/（成员名取文件名）；
  · submissions 为空时，自动读取项目上一级目录的 macau_bus.db 做预览。

【界面使用 Streamlit】
  命令行检查数据：python build_dashboard.py
  打开可视化界面：streamlit run streamlit_app.py
=====================================================================
"""

import os
import csv
import glob
import sqlite3
import datetime

# ---- 一些固定设置 ----
HERE = os.path.dirname(os.path.abspath(__file__))          # 本脚本所在文件夹
PROJECT_DIR = os.path.dirname(HERE)                        # 上一级（项目根目录）
SUBMISSIONS_DIR = os.path.join(HERE, "submissions")        # 组员数据放这里
SNAP_SECONDS = 600        # 爬虫每 10 分钟（600 秒）抓一轮，用于估算采集完整度
NO_VALUE = -1             # 网页端约定：速度/位置缺失时用 -1 表示


# =====================================================================
# 第 1 部分：读取数据
# =====================================================================

def read_db(db_path, member):
    """从一个 macau_bus.db 读出三张表，返回 pages / stations / buses 三个列表。
    每条记录都用字典表示（带字段名），并补上成员姓名，方便后面合并。"""
    conn = sqlite3.connect(db_path)
    conn.text_factory = str
    cur = conn.cursor()

    # pages：每一轮抓取快照
    cur.execute("SELECT crawl_time, route_name, direction FROM pages")
    pages = []
    for time_str, route, direction in cur.fetchall():
        pages.append({"member": member, "time": time_str,
                      "route": str(route), "dir": int(direction or 0)})

    # stations：站点（同一个站点每轮快照都会重复存，这里先全读出来，
    # 后面第 2 部分会按序号去重）
    cur.execute("""
        SELECT p.route_name, p.direction, s.seq,
               s.station_code, s.station_name, s.lane_name
        FROM stations s JOIN pages p ON s.page_id = p.id
    """)
    stations = []
    for route, direction, seq, code, name, lane in cur.fetchall():
        stations.append({"member": member, "route": str(route),
                         "dir": int(direction or 0), "seq": int(seq),
                         "code": code or "", "name": name or "",
                         "lane": lane or ""})

    # buses：每一轮看到的车辆（和 pages 通过 page_id 关联，这里直接
    # 用 JOIN 把时间、线路一起取出来，合并时就不用管各人的 page_id 了）
    cur.execute("""
        SELECT p.crawl_time, p.route_name, p.direction,
               b.segment_seq, b.bus_plate, b.speed_kmh, b.position_pct
        FROM buses b JOIN pages p ON b.page_id = p.id
    """)
    buses = []
    for time_str, route, direction, seg, plate, speed, pos in cur.fetchall():
        buses.append({
            "member": member, "time": time_str,
            "route": str(route), "dir": int(direction or 0),
            "seg": NO_VALUE if seg is None else int(seg),
            "plate": plate or "",
            "speed": NO_VALUE if speed is None else round(float(speed), 1),
            "pos": NO_VALUE if pos is None else round(float(pos), 1),
        })

    conn.close()
    return pages, stations, buses


def read_csv_group(csv_files):
    """读取一组 csv（pages.csv / stations.csv / buses.csv），
    csv 是组员用「导出数据.py」生成的，格式和数据库读出来的一致。"""
    pages, stations, buses = [], [], []

    if "pages" in csv_files:
        with open(csv_files["pages"], encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                pages.append({"member": row["member_name"].strip(),
                              "time": row["crawl_time"],
                              "route": str(row["route_name"]),
                              "dir": int(row["direction"])})

    if "stations" in csv_files:
        with open(csv_files["stations"], encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                stations.append({"member": row["member_name"].strip(),
                                 "route": str(row["route_name"]),
                                 "dir": int(row["direction"]),
                                 "seq": int(row["seq"]),
                                 "code": row.get("station_code", ""),
                                 "name": row.get("station_name", ""),
                                 "lane": row.get("lane_name", "")})

    if "buses" in csv_files:
        with open(csv_files["buses"], encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                speed = row.get("speed_kmh", "")
                pos = row.get("position_pct", "")
                seg = row.get("segment_seq", "")
                buses.append({
                    "member": row["member_name"].strip(),
                    "time": row["crawl_time"],
                    "route": str(row["route_name"]),
                    "dir": int(row["direction"]),
                    "seg": int(seg) if seg not in ("", None) else NO_VALUE,
                    "plate": row.get("bus_plate", ""),
                    "speed": float(speed) if speed not in ("", None) else NO_VALUE,
                    "pos": float(pos) if pos not in ("", None) else NO_VALUE,
                })

    return pages, stations, buses


def find_csv_groups(folder):
    """在 folder 下（含子文件夹）找 pages/stations/buses.csv，
    按所在文件夹分成一组组返回：{文件夹: {pages:路径, buses:路径, ...}}"""
    groups = {}
    for path in glob.glob(os.path.join(folder, "**", "*.csv"), recursive=True):
        kind = os.path.basename(path).lower().replace(".csv", "")
        if kind in ("pages", "stations", "buses"):
            groups.setdefault(os.path.dirname(path), {})[kind] = path
    return groups


def collect_data():
    """扫描 submissions 文件夹，把所有 .db 和 .csv 的数据读进来合并。
    返回 pages / stations / buses 三个大列表，和一份读取说明（打印用）。"""
    pages_all, stations_all, buses_all = [], [], []
    notes = []

    # 1) 所有 .db 文件（成员名取文件名，去掉「提交_」前缀）
    for db_path in glob.glob(os.path.join(SUBMISSIONS_DIR, "**", "*.db"),
                             recursive=True):
        member = os.path.splitext(os.path.basename(db_path))[0]
        if member.startswith("提交_"):
            member = member[3:]
        p, s, b = read_db(db_path, member)
        pages_all += p
        stations_all += s
        buses_all += b
        notes.append(f"数据库 {member}：{len(p)} 轮快照")

    # 2) 所有 csv 小组
    if os.path.isdir(SUBMISSIONS_DIR):
        for folder, files in find_csv_groups(SUBMISSIONS_DIR).items():
            p, s, b = read_csv_group(files)
            if not p and not b:
                continue
            pages_all += p
            stations_all += s
            buses_all += b
            # 这个文件夹里出现过的成员姓名（去重、排序）
            names = []
            for r in p + b:
                if r["member"] not in names:
                    names.append(r["member"])
            names.sort()
            notes.append(f"CSV {os.path.basename(folder)}："
                         f"{','.join(names)}，{len(p)} 轮快照")

    # 3) submissions 为空时，回退读取项目根目录的数据库，方便先预览
    if not pages_all and not buses_all:
        fallback_db = os.path.join(PROJECT_DIR, "macau_bus.db")
        if os.path.isfile(fallback_db):
            p, s, b = read_db(fallback_db, "我的数据")
            pages_all, stations_all, buses_all = p, s, b
            notes.append(f"预览：submissions 为空，暂用项目根目录数据库"
                         f"（成员名「我的数据」，{len(p)} 轮快照）")

    return pages_all, stations_all, buses_all, notes


# =====================================================================
# 第 2 部分：小工具函数（时间、分组、平均）
# =====================================================================

def to_datetime(time_str):
    """'2026-10-15 09:00:03' 这种字符串转成 datetime，方便比大小。"""
    return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")


def day_of(dt):
    """日期标签，只取 月-日，例如 '10-15'。"""
    return dt.strftime("%m-%d")


def minute_of(dt):
    """分钟标签（爬虫约 10 分钟一轮，忽略秒），例如 '10-15 09:00'。"""
    return dt.strftime("%m-%d %H:%M")


def average(numbers):
    """求平均，列表为空时返回 None（图表上显示成「无数据」）。"""
    numbers = [x for x in numbers if x != NO_VALUE]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 1)


def route_key(route, direction):
    """线路和方向拼成唯一编号，例如 '3|0'、'26A|1'。"""
    return f"{route}|{direction}"


def dir_text(direction):
    """方向数字转中文：0 去程，1 回程。"""
    return "去程" if direction == 0 else "回程"


# =====================================================================
# 第 3 部分：计算一条线路的全部指标
# =====================================================================

def calc_route(key, pages_of_route, stations_of_route, buses_of_route):
    """
    输入一条线路（含方向）的全部原始记录，输出一个字典，里面是：
      基本信息、站点清单、按天的回放帧、热力图数据、对比指标。
    """
    route, direction = key.split("|")
    direction = int(direction)

    # ---- 3.1 站点清单：同一个站点在多轮快照里重复出现，按序号 seq 去重 ----
    # 不同成员可能交了同一条线路，挑站点记录最多的那位成员的数据为准
    member_count = {}
    for s in stations_of_route:
        member_count[s["member"]] = member_count.get(s["member"], 0) + 1
    best_member = max(member_count, key=member_count.get) \
        if member_count else None

    station_by_seq = {}     # seq -> 站点字典
    for s in stations_of_route:
        if best_member and s["member"] != best_member:
            continue
        station_by_seq[s["seq"]] = {"seq": s["seq"], "code": s["code"],
                                    "name": s["name"], "lane": s["lane"]}
    stations = [station_by_seq[i] for i in sorted(station_by_seq)]
    if not stations:
        # 极端情况下站点表为空，用车牌里出现过的最大段号兜底
        max_seg = max([b["seg"] for b in buses_of_route
                       if b["seg"] != NO_VALUE] + [-1])
        stations = [{"seq": i, "code": "", "name": f"区段{i}", "lane": ""}
                    for i in range(max_seg + 2)]
    station_count = len(stations)

    # ---- 3.2 时间轴：把所有快照时间按“分钟”去重，从小到大排 ----
    page_pairs = []
    for p in pages_of_route:
        page_pairs.append((to_datetime(p["time"]), p["member"]))
    page_pairs.sort()
    page_dt = page_pairs
    time_labels = []
    for dt, _ in page_dt:
        label = minute_of(dt)
        if label not in time_labels:
            time_labels.append(label)
    time_labels.sort()

    # ---- 3.3 按天组织回放帧 ----
    # 每一帧 = 某一分钟那一轮快照看到的全部车辆。
    # 先用字典按“分钟标签”去重（同一分钟最多一帧），最后再排好序。
    frames_dict = {}        # 日期 -> {分钟标签: [车,...]}
    for dt, _ in page_dt:
        d = day_of(dt)
        frames_dict.setdefault(d, {})
        frames_dict[d].setdefault(minute_of(dt), [])

    # 把每辆车放进它所属的那一帧（按分钟标签对号入座）
    plate_set = set()
    for b in buses_of_route:
        dt = to_datetime(b["time"])
        d = day_of(dt)
        mk = minute_of(dt)
        if d not in frames_dict or mk not in frames_dict[d]:
            continue
        frames_dict[d][mk].append({
            "plate": b["plate"], "speed": b["speed"],
            "seg": b["seg"], "pos": b["pos"],
        })
        plate_set.add(b["plate"])

    # 转成网页好用的结构：每天一个 {"times":[...], "frames":[[车,...],...]}
    frames_by_day = {}
    for d in sorted(frames_dict):
        mks = sorted(frames_dict[d])
        frames_by_day[d] = {"times": mks,
                            "frames": [frames_dict[d][mk] for mk in mks]}

    # ---- 3.4 逐格收集速度，用于热力图和小时统计 ----
    speed_by_hour = {}                 # 小时 -> [速度,...]
    active_by_hour = {}                # 小时 -> [每轮车辆数,...]
    speed_by_hour_seg = {}             # (小时, 段号) -> [速度,...]
    speed_by_day_hour = {}             # (日期, 小时) -> [速度,...]
    active_by_day_hour = {}            # (日期, 小时) -> [车辆数,...]
    first_plate_by_day_hour = {}       # (日期, 小时) -> 首站出现过的车牌集合

    for d, one_day in frames_by_day.items():
        for frame_i, mk in enumerate(one_day["times"]):
            hour = int(mk[6:8])
            cars = one_day["frames"][frame_i]
            speeds = [c["speed"] for c in cars if c["speed"] != NO_VALUE]

            speed_by_hour.setdefault(hour, []).extend(speeds)
            active_by_hour.setdefault(hour, []).append(len(cars))
            speed_by_day_hour.setdefault((d, hour), []).extend(speeds)
            active_by_day_hour.setdefault((d, hour), []).append(len(cars))

            for c in cars:
                if c["speed"] != NO_VALUE and 0 <= c["seg"] < station_count:
                    speed_by_hour_seg.setdefault((hour, c["seg"]), []) \
                        .append(c["speed"])
                # 首站（段号 0 或 1）出现的车牌，用来近似统计发车班次
                if c["seg"] in (0, 1):
                    first_plate_by_day_hour.setdefault((d, hour), set()) \
                        .add(c["plate"])

    # ---- 3.5 汇总成对比指标 ----
    all_speeds = [s for hour in speed_by_hour for s in speed_by_hour[hour]]
    frame_sizes = [len(fr) for one in frames_by_day.values()
                   for fr in one["frames"]]

    speed_hour = [None] * 24       # 每个小时的平均速度
    active_hour = [None] * 24      # 每个小时平均每轮在运车辆数
    trips_hour = [None] * 24       # 每个小时平均发车班次
    for hour in range(24):
        speed_hour[hour] = average(speed_by_hour.get(hour, []))
        if hour in active_by_hour:
            active_hour[hour] = round(
                sum(active_by_hour[hour]) / len(active_by_hour[hour]), 1)
        # 班次：先算每天该小时的不同车牌数，再对天数平均
        per_day = [len(v) for (d, h), v in first_plate_by_day_hour.items()
                   if h == hour]
        if per_day:
            trips_hour[hour] = round(sum(per_day) / len(per_day), 1)

    days = sorted(frames_by_day.keys())
    trips_total = sum(len(v) for v in first_plate_by_day_hour.values())

    # ---- 3.6 热力图数据（直接整理成 ECharts 能用的 [横坐标,纵坐标,值]）----
    hours_present = sorted(speed_by_hour.keys())
    seg_names = []
    for i in range(station_count - 1):
        a = stations[i]["name"] or stations[i]["code"] or f"第{i+1}站"
        b = stations[i + 1]["name"] or stations[i + 1]["code"]
        seg_names.append(f"{a} → {b}" if b else a)

    heat_speed = []
    for (hour, seg), vals in sorted(speed_by_hour_seg.items()):
        if seg >= len(seg_names):
            continue
        heat_speed.append([hours_present.index(hour), seg,
                           round(sum(vals) / len(vals), 1)])

    heat_day_speed, heat_day_active = [], []
    for di, d in enumerate(days):
        for hour in range(24):
            sv = speed_by_day_hour.get((d, hour))
            if sv:
                heat_day_speed.append([di, hour, round(sum(sv) / len(sv), 1)])
            av = active_by_day_hour.get((d, hour))
            if av:
                heat_day_active.append([di, hour,
                                        round(sum(av) / len(av), 1)])

    # 最拥堵区段：每个段的全部速度平均，样本不少于 10 次才排名，取最慢 8 个
    seg_speed_all = {}
    for (hour, seg), vals in speed_by_hour_seg.items():
        seg_speed_all.setdefault(seg, []).extend(vals)
    jam = []
    for seg, vals in seg_speed_all.items():
        if len(vals) >= 10 and seg < len(seg_names):
            jam.append({"seg": seg, "name": seg_names[seg],
                        "speed": round(sum(vals) / len(vals), 1),
                        "n": len(vals)})
    # 排序用：取一个拥堵区段的平均车速（不用 lambda，写成普通函数更好懂）
    def jam_speed(item):
        return item["speed"]
    jam.sort(key=jam_speed)
    jam = jam[:8]

    # 爬过这条线路的成员名单（去重后排序）
    member_names = []
    for p in pages_of_route:
        if p["member"] not in member_names:
            member_names.append(p["member"])
    member_names.sort()

    return {
        "name": route,
        "dir": direction,
        "dir_text": dir_text(direction),
        "members": member_names,
        "stations": stations,
        "days": days,
        "replay": {"days": days, "by_day": frames_by_day},
        "heat": {
            "hours": hours_present,
            "seg_names": seg_names,
            "speed_hour_seg": heat_speed,
            "days": days,
            "day_speed": heat_day_speed,
            "day_active": heat_day_active,
            "jam": jam,
        },
        "compare": {
            "avg_speed": average(all_speeds),
            "plates": len(plate_set),
            "avg_active": round(sum(frame_sizes) / len(frame_sizes), 1)
                         if frame_sizes else 0,
            "peak_active": max(frame_sizes) if frame_sizes else 0,
            "trips_per_day": round(trips_total / max(len(days), 1), 1),
            "speed_hour": speed_hour,
            "active_hour": active_hour,
            "trips_hour": trips_hour,
        },
        "rounds": len(time_labels),
    }


# =====================================================================
# 第 4 部分：成员统计和总览
# =====================================================================

def calc_members(pages, route_data):
    """统计每位成员：负责线路、轮次、车辆数、天数、采集完整度。"""
    # 每位成员每天每条线路的抓取时间（用于算采集完整度）
    times_of = {}
    rounds_of = {}
    days_of = {}
    routes_of = {}
    for p in pages:
        m = p["member"]
        key = route_key(p["route"], p["dir"])
        d = day_of(to_datetime(p["time"]))
        rounds_of[m] = rounds_of.get(m, 0) + 1
        days_of.setdefault(m, set()).add(d)
        routes_of.setdefault(m, set()).add(
            f"{p['route']}{dir_text(p['dir'])}")
        # times_of[(成员, 日期)][线路] = 这一天这条线路的全部抓取时间
        day_key = (m, d)
        if day_key not in times_of:
            times_of[day_key] = {}
        if key not in times_of[day_key]:
            times_of[day_key][key] = []
        times_of[day_key][key].append(to_datetime(p["time"]))

    # 车辆归属：线路不重叠，一条线路上的车牌算给爬它的成员
    plates_of = {}
    for key, rd in route_data.items():
        owners = rd["members"]
        # 该线路所有车牌
        plates = set()
        for one in rd["replay"]["by_day"].values():
            for frame in one["frames"]:
                for car in frame:
                    plates.add(car["plate"])
        for m in owners:
            plates_of.setdefault(m, set()).update(plates)

    # 采集完整度：实际轮次 ÷ 理论轮次（按当天首末抓取时间跨度，10 分钟一轮）
    cover_samples = {}
    for (m, d), by_route in times_of.items():
        for key, dts in by_route.items():
            dts.sort()
            if len(dts) < 2:
                cover_samples.setdefault(m, []).append(1.0)
                continue
            span_seconds = (dts[-1] - dts[0]).total_seconds()
            expect = span_seconds / SNAP_SECONDS + 1     # +1 算上首尾两轮
            cover_samples.setdefault(m, []).append(
                min(len(dts) / expect, 1.0))

    members = []
    for m in sorted(rounds_of.keys()):
        cov = cover_samples.get(m, [])
        members.append({
            "name": m,
            "routes": sorted(routes_of.get(m, [])),
            "rounds": rounds_of.get(m, 0),
            "plates": len(plates_of.get(m, set())),
            "days": sorted(days_of.get(m, set())),
            "coverage": round(sum(cov) / len(cov), 3) if cov else None,
        })
    return members


def build_overview(members, route_data, pages):
    """组装总览页需要的数据：顶部数字、成员卡片、每日轮次、线路表。"""
    all_days = set()
    day_rounds = {}
    for p in pages:
        d = day_of(to_datetime(p["time"]))
        all_days.add(d)
        day_rounds[d] = day_rounds.get(d, 0) + 1

    all_plates = set()
    for rd in route_data.values():
        for one in rd["replay"]["by_day"].values():
            for frame in one["frames"]:
                for car in frame:
                    all_plates.add(car["plate"])

    route_table, route_plates = [], []
    for key, rd in route_data.items():
        label = f"{rd['name']} {rd['dir_text']}"
        c = rd["compare"]
        route_table.append({
            "name": rd["name"], "dir_text": rd["dir_text"],
            "members": "、".join(rd["members"]),
            "stations": len(rd["stations"]),
            "days": len(rd["days"]), "rounds": rd["rounds"],
            "plates": c["plates"], "avg_speed": c["avg_speed"],
            "avg_active": c["avg_active"],
        })
        route_plates.append({"label": label, "value": c["plates"]})

    return {
        "kpi": {
            "members": len(members),
            "routes": len(route_data),
            "plates": len(all_plates),
            "rounds": len(pages),
            "days": len(all_days),
        },
        "members": members,
        "day_rounds": [[d, day_rounds[d]] for d in sorted(day_rounds)],
        "route_plates": route_plates,
        "route_table": route_table,
    }


# =====================================================================
# 第 5 部分：组装 Streamlit 界面要用的数据
# =====================================================================

def build_data():
    """读取、合并、统计所有数据，返回 Streamlit 界面直接使用的字典。"""
    pages, stations, buses, notes = collect_data()
    if not pages and not buses:
        return None, notes

    pages_by_key, stations_by_key, buses_by_key = {}, {}, {}
    for p in pages:
        pages_by_key.setdefault(route_key(p["route"], p["dir"]), []).append(p)
    for s in stations:
        stations_by_key.setdefault(route_key(s["route"], s["dir"]), []) \
            .append(s)
    for b in buses:
        buses_by_key.setdefault(route_key(b["route"], b["dir"]), []).append(b)

    def sort_key(k):
        name, d = k.split("|")
        num = ""
        for ch in name:
            if ch.isdigit():
                num += ch
            else:
                break
        return (int(num) if num else 999, name, int(d))

    route_data = {}
    for key in sorted(set(pages_by_key) | set(buses_by_key), key=sort_key):
        route_data[key] = calc_route(
            key,
            pages_by_key.get(key, []),
            stations_by_key.get(key, []),
            buses_by_key.get(key, []))

    members = calc_members(pages, route_data)
    overview = build_overview(members, route_data, pages)

    all_times = []
    for rd in route_data.values():
        for one in rd["replay"]["by_day"].values():
            all_times += one["times"]

    data = {
        "meta": {
            "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "date_min": min(all_times) if all_times else "",
            "date_max": max(all_times) if all_times else "",
            "notes": notes,
        },
        "overview": overview,
        "routes": route_data,
        "route_keys": sorted(route_data.keys(), key=sort_key),
    }
    return data, notes


# =====================================================================
# main：命令行检查数据
# =====================================================================

def main():
    print("正在扫描并统计数据 ...")
    data, notes = build_data()
    for note in notes:
        print("   " + note)
    if data is None:
        print("没有读到任何数据，请把组员的 .db 或解压后的 csv 放进 "
              + SUBMISSIONS_DIR)
        return

    kpi = data["overview"]["kpi"]
    print(f"完成！共 {kpi['members']} 位成员、{kpi['routes']} 条线路、"
          f"{kpi['rounds']} 轮快照、{kpi['plates']} 辆车。")
    print("打开界面请运行：streamlit run streamlit_app.py")


if __name__ == "__main__":
    main()
