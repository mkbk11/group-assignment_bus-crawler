# 巴士报站爬虫（Selenium + 正则提取 + SQLite）

课程作业项目：爬取澳门交通事务局「巴士报站」网站（https://bis.dsat.gov.mo:37812/macauweb/），
用 Selenium 抓取动态渲染的页面源码，用正则表达式提取站点与车辆信息，存入 SQLite 数据库，并支持导出 CSV 和可视化。

## 版本更新
- **2026.10.5** - 删除 `--minutes`，新增 `wait_until` - 等到指定时间才继续；如果那个时间已过，就自动等到明天同一时刻。
- **2026.10.5** - 新增 `--no-proxy-server` —— 直连网络（绕过系统代理），电脑其他程序不受影响。
- **2026.10.1** - 新增 `accept()` 和 `driver.get()` —— 弹窗还在就点掉，已消失就跳过。数据方向正常返回 `None`（跳过），整轮不再中断。

## 数据库结构（macau_bus.db）

| 表 | 字段 | 说明 |
|---|---|---|
| `pages` | id, crawl_time, route_name, direction, html, parsed | 每次爬取快照；html 为压缩源码；parsed 标记是否已提取 |
| `stations` | id, page_id, seq, station_code, stopcode, station_name, lane_name | 站点明细（站码如 M1/13） |
| `buses` | id, page_id, segment_seq, segment_station_code, bus_plate, speed_kmh, position_pct | 车辆明细（车牌、速度、路段位置百分比） |

## 使用方法

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 定时开始 / 定时关闭（自行设定）

脚本顶部配置区有 3 个参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `START_TIME` | `"09:00"` | 每天几点开始爬取（24 小时制，如 `"08:00"`） |
| `END_TIME` | `"21:00"` | 每天几点停止爬取（到点自动休息，第二天再开始） |
| `DAYS` | `7` | 连续爬取多少天 |


### 3. 正式爬取

```bash
E:\Anaconda\python.exe macau_bus_crawler_simple.py
```

可选参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--routes` | 26A 3 18 | 要爬的路线（2~3 条即可） |
| `--interval` | 600 | 爬取间隔（秒），默认 10 分钟一轮，不要太密 |
| `--db` | macau_bus.db | 数据库文件名 |
| `--show-browser` | 无 | 加上则弹出浏览器窗口（默认后台运行） |

### 4. 导出 CSV 查看数据

```bash
E:\Anaconda\python.exe export_to_csv.py
```

生成 4 个文件到 `export_data/`：pages / stations / buses / summary（汇总表）。



## 注意事项

- **网站证书**：该网站证书不受信任，脚本已加 `--ignore-certificate-errors`，不要删除
- **单向路线**：部分路线（如 25、33）是环线建模，只有方向 0 有数据；方向 1 会弹 `no data`，脚本自动跳过
- - **VPN / 代理**：电脑开着 VPN（系统代理模式）时网站可能访问不了。脚本顶部 `BYPASS_PROXY = True` 让爬虫直连网络、绕过代理，只影响爬虫自己的浏览器，电脑其他程序照常使用；若 VPN 是全局/TUN 模式则此参数无效，需在 VPN 客户端排除 Chrome 或爬取时临时关闭 VPN
- **晚间数据少**：澳门巴士一般运营到 23:30 左右，夜里车辆数为 0 属正常
- **电脑不要睡眠**：连续爬取期间请把电源设置改为"从不睡眠"，否则会空窗
- **网站限流**：若连续频繁测试，网站可能临时拒绝访问（页面能打开但无数据），属正常现象，停一会儿或第二天再跑即可
- **旧版数据库**：若之前用旧版本代码生成过数据库（表结构含 snapshot_id），脚本检测到会自动改名重建，不影响使用

