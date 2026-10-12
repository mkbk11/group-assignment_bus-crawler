# -*- coding: utf-8 -*-
"""
澳门巴士运行观测仪表盘 —— Streamlit 版

运行方法：
  cd dashboard
  streamlit run streamlit_app.py
"""

import pandas as pd
import streamlit as st

import build_dashboard


st.set_page_config(page_title="澳门巴士运行观测仪表盘", layout="wide")


@st.cache_data
def load_data():
    return build_dashboard.build_data()


def route_label(key, route_data):
    rd = route_data[key]
    return f"{rd['name']} {rd['dir_text']}"


def show_kpis(kpi):
    cols = st.columns(5)
    cols[0].metric("成员数", kpi["members"])
    cols[1].metric("线路方向", kpi["routes"])
    cols[2].metric("观测车辆", kpi["plates"])
    cols[3].metric("快照轮次", kpi["rounds"])
    cols[4].metric("覆盖天数", kpi["days"])


def show_overview(data):
    overview = data["overview"]
    show_kpis(overview["kpi"])

    st.subheader("成员分工")
    members = pd.DataFrame(overview["members"])
    if not members.empty:
        members["routes"] = members["routes"].apply("、".join)
        members["days"] = members["days"].apply("、".join)
        members["coverage"] = members["coverage"].apply(
            lambda x: "" if pd.isna(x) else f"{x:.0%}")
        st.dataframe(members, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.subheader("每日快照轮次")
        day_rounds = pd.DataFrame(overview["day_rounds"],
                                  columns=["日期", "轮次"])
        st.bar_chart(day_rounds, x="日期", y="轮次")
    with right:
        st.subheader("各线路观测车辆数")
        route_plates = pd.DataFrame(overview["route_plates"])
        if not route_plates.empty:
            st.bar_chart(route_plates, x="label", y="value")

    st.subheader("线路数据总表")
    st.dataframe(pd.DataFrame(overview["route_table"]),
                 use_container_width=True, hide_index=True)


def show_replay(data):
    routes = data["routes"]
    keys = data["route_keys"]
    labels = {route_label(k, routes): k for k in keys}

    c1, c2, c3 = st.columns([2, 2, 3])
    label = c1.selectbox("线路", list(labels.keys()))
    rd = routes[labels[label]]
    day = c2.selectbox("日期", rd["days"])
    one_day = rd["replay"]["by_day"][day]

    if not one_day["times"]:
        st.info("这一天没有回放帧。")
        return

    index = c3.slider("快照时间", 0, len(one_day["times"]) - 1, 0)
    time_text = one_day["times"][index]
    cars = one_day["frames"][index]

    st.caption(f"当前快照：{time_text}，车辆 {len(cars)} 辆")

    stations = pd.DataFrame(rd["stations"])
    buses = pd.DataFrame(cars)
    chart_rows = []
    for _, row in stations.iterrows():
        chart_rows.append({"type": "站点", "x": row["seq"], "y": 0,
                           "name": row["name"] or row["code"]})
    if not buses.empty:
        for _, row in buses.iterrows():
            pos = 50 if row["pos"] == build_dashboard.NO_VALUE else row["pos"]
            x = row["seg"] + pos / 100
            chart_rows.append({"type": "车辆", "x": x, "y": 1,
                               "name": row["plate"]})

    st.scatter_chart(pd.DataFrame(chart_rows), x="x", y="y",
                     color="type", height=260)

    left, right = st.columns(2)
    left.subheader("当前车辆")
    left.dataframe(buses, use_container_width=True, hide_index=True)
    right.subheader("站点清单")
    right.dataframe(stations, use_container_width=True, hide_index=True)


def show_heat(data):
    routes = data["routes"]
    labels = {route_label(k, routes): k for k in data["route_keys"]}
    label = st.selectbox("线路", list(labels.keys()))
    rd = routes[labels[label]]
    heat = rd["heat"]

    st.subheader("时段 × 区段平均速度")
    rows = []
    for x, seg, speed in heat["speed_hour_seg"]:
        rows.append({
            "区段": heat["seg_names"][seg],
            "小时": heat["hours"][x],
            "平均速度": speed,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("暂无速度热力数据。")
    else:
        pivot = df.pivot_table(index="区段", columns="小时",
                               values="平均速度", aggfunc="mean")
        st.dataframe(pivot.style.background_gradient(cmap="RdYlGn"),
                     use_container_width=True)

    st.subheader("最拥堵区段 TOP")
    st.dataframe(pd.DataFrame(heat["jam"]),
                 use_container_width=True, hide_index=True)


def show_compare(data):
    routes = data["routes"]
    keys = data["route_keys"]
    labels = {route_label(k, routes): k for k in keys}
    chosen = st.multiselect("选择线路", list(labels.keys()),
                            default=list(labels.keys())[:min(3, len(labels))])
    chosen_keys = [labels[x] for x in chosen]
    if not chosen_keys:
        st.info("请至少选择一条线路。")
        return

    rows = []
    for key in chosen_keys:
        rd = routes[key]
        c = rd["compare"]
        rows.append({
            "线路": route_label(key, routes),
            "平均速度": c["avg_speed"],
            "观测车辆数": c["plates"],
            "平均在运/轮": c["avg_active"],
            "高峰在运": c["peak_active"],
            "日均首站班次": c["trips_per_day"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    metric = st.selectbox("小时曲线指标",
                          ["speed_hour", "active_hour", "trips_hour"],
                          format_func={
                              "speed_hour": "平均速度",
                              "active_hour": "平均在运车辆",
                              "trips_hour": "首站班次",
                          }.get)
    chart = pd.DataFrame({"小时": list(range(24))})
    for key in chosen_keys:
        chart[route_label(key, routes)] = routes[key]["compare"][metric]
    st.line_chart(chart, x="小时")


def main():
    st.title("澳门巴士运行观测仪表盘")
    data, notes = load_data()
    if data is None:
        st.error("没有读到任何数据。请把组员的 .db 或 csv 放进 dashboard/submissions。")
        return

    st.caption(
        f"生成时间：{data['meta']['generated']}；"
        f"数据范围：{data['meta']['date_min']} ~ {data['meta']['date_max']}")
    with st.expander("数据读取说明"):
        for note in notes:
            st.write(note)

    page = st.sidebar.radio("模块", ["小组总览", "车辆快照", "拥堵热力", "多线路对比"])
    if page == "小组总览":
        show_overview(data)
    elif page == "车辆快照":
        show_replay(data)
    elif page == "拥堵热力":
        show_heat(data)
    else:
        show_compare(data)


if __name__ == "__main__":
    main()
