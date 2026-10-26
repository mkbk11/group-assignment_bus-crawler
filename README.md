# 澳门巴士数据采集与分析

**Group Assignment 1 · Crawler & Regular Expression**

本项目以澳门交通事务局的[「巴士报站」网站](https://bis.dsat.gov.mo:37812/macauweb/)为数据来源，使用 Selenium 获取动态渲染的页面，以正则表达式提取站点与车辆信息，通过 SQLite 保存采集记录，再汇总六位组员的导出数据进行分析与可视化。

## 版本更新

- **2026.10.26** - 更新 README，补充项目流程、小组分析结果、文件说明与运行步骤，核对当前脚本命令和默认配置；补齐 `requirements.txt` 中的分析、绘图及 notebook 依赖，并调整 Pandas、Matplotlib 的最低版本。
- **2026.10.21** - 新增 group_export 组员数据，新增 group_assignment-macau_bus_crawler_10.20.ipynb，删除 dashboard 等网页文件
- **2026.10.12** - 新增 group_export 文件夹（用于数据库数据导出），新增 dashboard 文件夹（用于可视化的数据展示）
- **2026.10.6** - 修复 `wait_until` 内部bug
- **2026.10.5** - 删除 `--minutes`，新增 `wait_until` - 等到指定时间才继续；如果那个时间已过，就自动等到明天同一时刻。
- **2026.10.5** - 新增 `--no-proxy-server` —— 直连网络（绕过系统代理），电脑其他程序不受影响。
- **2026.10.1** - 新增 `accept()` 和 `driver.get()` —— 弹窗还在就点掉，已消失就跳过。数据方向正常返回 `None`（跳过），整轮不再中断。

## 项目流程

```text
Selenium 获取动态页面
        ↓
gzip 压缩 HTML → SQLite 保存页面快照
        ↓
正则表达式提取站点、车牌、速度与路段位置
        ↓
CSV / ZIP 导出 → 小组数据关联、筛选与去重
        ↓
Jupyter Notebook 统计分析与可视化
```

每个页面快照对应一次对某条线路、某个方向的采集。站点与车辆记录通过 `page_id` 关联到原始快照，保留时间、线路和方向信息。

## 作业展示与数据概览

主要阅读入口为 [group_assignment-macau_bus_crawler_simple.ipynb](group_assignment-macau_bus_crawler_simple.ipynb)，包含采集过程、正则提取逻辑、小组数据合并及图表展示。

当前 notebook 汇总六份组员 ZIP 数据，分析 **2026 年 10 月 6 日至 12 日**的记录，已有输出如下：

| 指标 | 数值 |
|---|---:|
| 页面快照 | 2,497 |
| 车辆观测记录 | 15,921 |
| 线路数 | 8 |
| 不同车牌数 | 247 |
| 不同站点代码数 | 212 |

其中，15,921 表示车辆被观测到的记录数，同一辆车可在不同快照中重复出现；212 按 `station_code` 去重统计。

默认采集线路为 `25B`、`701X`、`3`、`26A`、`17`、`29`、`25BS`、`60`。图表包括：

- 每日页面快照数与车辆观测记录数。
- 15:00–19:00 各线路观测车辆数的热力图。
- 各线路观测车速分布。
- 按线路、方向统计的平均每快照车辆数。
- 各线路逐小时车辆观测记录数。
- 各线路最早与最晚车辆观测时间。

## 主要文件

| 文件或目录 | 用途 |
|---|---|
| [group_assignment-macau_bus_crawler_simple.ipynb](group_assignment-macau_bus_crawler_simple.ipynb) | 本次作业的主要展示 notebook |
| [macau_bus_crawler.py](macau_bus_crawler.py) | 主程序。定时、多轮采集 |
| [group_assignment-macau_bus_crawler.ipynb](group_assignment-macau_bus_crawler.ipynb) | 另一版采集与分析 notebook |
| [data_export.py](data_export.py) | 导出带组员姓名的数据，并生成提交 ZIP |
| [requirements.txt](requirements.txt) | 基础依赖清单 |

`macau_bus.db` 和 `assignment_demo.db` 为本地数据库，已列入 `.gitignore`；新克隆的项目不保证包含这些文件。小组数据分析直接读取已提交的 ZIP，不依赖本地数据库。

## 安装与运行环境

准备 Python 环境和 Google Chrome，在项目根目录安装依赖：

```bash
python -m pip install -r requirements.txt
```

`re`、`sqlite3`、`gzip`、`zipfile` 等属于 Python 标准库，无需单独安装。

采集阶段需要联网；Selenium 首次创建浏览器时可能需要下载匹配的驱动。读取已有 ZIP 并绘图无需访问巴士网站。


### 查看或复现已有数据分析

1. 确认六份组员 ZIP 位于 `group_export/group_export/`。
2. 运行 `Step1: environmental preparation` 中的导入单元格。
3. 从 `group dataset visualization` 开始，按顺序运行后续单元格。

分析默认使用以下配置，其中 `END` 为不包含的结束边界：

```python
DATA_DIR = Path("group_export/group_export")
START = pd.Timestamp("2026-10-06")
END = pd.Timestamp("2026-10-13")
```

合并时先在每份提交内部关联数据，再汇总去重，避免不同数据库中相同的 `page_id` 被直接混用。代码兼容按 `page_id` 关联，以及按时间、线路、方向关联的车辆数据格式。

### 演示一次页面采集

按顺序运行 notebook 的采集部分。默认使用 `assignment_demo.db`、显示浏览器，并对每条配置线路的方向 `0`、`1` 各尝试采集一次；没有数据的方向会跳过。再次运行采集单元格会追加页面快照。

当前精简 notebook 的 `Step4` **只定义 `parse_route_page()`，没有执行解析并写入 `stations`、`buses` 的调用**。如需完成采集、解析、入库的完整流程，使用下面的独立爬虫脚本。

## 使用完整爬虫

运行前，在 [macau_bus_crawler.py](macau_bus_crawler.py) 顶部调整时间配置，当前值为：

```python
START_TIME = "08:00"
END_TIME = "22:00"
DAYS = 4
```

时间判断使用运行电脑的本地时间。脚本在当天开始时间之前等待，到达结束时间后等待下一天；在采集时段内启动会直接开始。`DAYS` 用于按启动日期控制运行日期范围，并不保证每一天都采集完整时段。

```bash
python macau_bus_crawler.py
```

例如，指定两条线路、每轮结束后等待 10 分钟，并显示浏览器：

```bash
python macau_bus_crawler.py --routes 25B 3 --interval 600 --db macau_bus.db --show-browser
```

| 参数 | 当前默认值 | 说明 |
|---|---|---|
| `--routes` | `25B 701X 3 26A 17 29 25BS 60` | 要采集的线路，以空格分隔 |
| `--interval` | `600` | 每轮处理结束后的等待秒数；实际两轮开始时间还包含采集与解析耗时 |
| `--db` | `macau_bus.db` | SQLite 数据库路径 |
| `--show-browser` | 默认不启用 | 加上后显示浏览器，否则后台运行 |

每轮先保存页面，再解析尚未处理的页面并写入站点、车辆表。可使用 `Ctrl+C` 停止运行，已提交到数据库的记录会保留。

## 数据导出

### 小组提交 ZIP

在项目根目录运行：

```bash
python data_export.py macau_bus.db "Wang Hongjie"
```

将姓名替换为自己的姓名。脚本会在自身所在目录生成 `data_姓名/` 和 `提交_姓名.zip`，包含 `pages.csv`、`stations.csv`、`buses.csv`。页面表不导出压缩 HTML，站点表按线路与方向去重，车辆表附带采集时间、线路与方向。

分析新的提交时，将 ZIP 放入 `group_export/group_export/`，再调整 notebook 的日期范围。导出脚本中的 10 月 15–19 日检查提示是固定日期提示，不决定实际导出范围。


## 数据库结构

| 表 | 主要字段 | 说明 |
|---|---|---|
| `pages` | `id`, `crawl_time`, `route_name`, `direction`, `html`, `parsed` | 页面快照；`html` 为 gzip 压缩的 UTF-8 源码，`parsed` 标记解析状态 |
| `stations` | `id`, `page_id`, `seq`, `station_code`, `stopcode`, `station_name`, `lane_name` | 当前快照对应的站点顺序、代码、名称及车道 |
| `buses` | `id`, `page_id`, `segment_seq`, `segment_station_code`, `bus_plate`, `speed_kmh`, `position_pct` | 当前快照中的车牌、观测车速与路段位置 |

`stopcode` 作为字符串保存，可含字母或前导零。`position_pct` 表示页面中对应路段的相对位置，不是整条线路的完成百分比；未提取到的速度或百分比位置保存为空值。

## 数据解读与运行说明

- **观测范围**：逐小时车辆记录数同时受到采集次数与采集时间的影响，不能直接等同于发车频率。最早、最晚观测时间也不代表官方运营时间。
- **采集结果**：某方向无数据、页面加载失败或电脑休眠，都可能导致缺少快照。没有采集到页面与采集到页面但没有车辆，是两种不同情况。
- **页面结构**：**正则表达式针**对当前页面的标签与属性结构编写，网站结构变化后需要重新核对匹配结果。
- **网络连接**：独立脚本默认 `BYPASS_PROXY = True`，使爬虫浏览器绕过系统代理；全局或 TUN 模式的网络行为仍取决于代理软件配置。
- **持续采集**：运行期间保持电脑唤醒，并设置合理的采集间隔。

## 后续方向

本次展示聚焦 10 月 6–12 日的小组样本。后续可扩展其他日期与时段，完善数据质量检查，并探索实时展示、到站时间预测和线路运行分析。
