"""
web url: 
https://bis.dsat.gov.mo:37812/macauweb/

Design:
  1. Selenium - crawl pages, save gzipped source code into pages table
  2. regular expression - extract stations and buses, save into stations and buses tables

Usage(in terminal): 
    python macau_bus_crawler.py
    python macau_bus_crawler.py --routes 26A 3 18 --interval 1200
    python macau_bus_crawler.py --minutes 5

Param: 
    --routes        route (default 26A 3 18)
    --interval      interval seconds (default 600)
    --db            database path (default macau_bus.db)
    --show-browser  show browser window (default False - headless)
"""
import os, re, sqlite3, time, gzip, argparse
from datetime import datetime, date, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import UnexpectedAlertPresentException

BASE_URL = "https://bis.dsat.gov.mo:37812/macauweb/"

# ------------------------------------------------------------
# Chrome connect DIRECTLY (bypass proxy), other apps are NOT affected.
# If VPN is global / TUN mode, this option has no effect - need to turn off VPN while crawling
BYPASS_PROXY = True

# ---------- Timing Crawler Config ----------
START_TIME = "09:00"      # start crawling at this time every day (24h, e.g. "09:00")
END_TIME   = "21:00"      # stop crawling at this time every day (auto rest, next day again)
DAYS       = 7            # how many days to crawl continuously
# -------------------------------------------

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------- create tables ----------------------
def create_tables(con):
    """
    create 3 tables: pages, stations, buses
    1. pages: id, crawl_time, route_name, direction, html, parsed
    2. stations: id, page_id, seq, station_code, stopcode, station_name, lane_name
    3. buses: id, page_id, segment_seq, segment_station_code, bus_plate, speed_kmh, position_pct
    
    if tables already exist, do nothing
    """
    con.executescript('''
        CREATE TABLE IF NOT EXISTS pages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_time TEXT NOT NULL,
            route_name TEXT NOT NULL,
            direction  INTEGER NOT NULL,
            html       BLOB,
            parsed     INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS stations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id       INTEGER NOT NULL,
            seq           INTEGER,
            station_code  TEXT,
            stopcode      TEXT,
            station_name  TEXT,
            lane_name     TEXT
        );
        CREATE TABLE IF NOT EXISTS buses (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id              INTEGER NOT NULL,
            segment_seq          INTEGER,
            segment_station_code TEXT,
            bus_plate            TEXT,
            speed_kmh            REAL,
            position_pct         REAL
        );
    ''')

# init database: open database. create tables if not exist, check compatibility
def init_db(path):
    con = sqlite3.connect(path)
    create_tables(con)
    # compatibility checking
    cols = [c[1] for c in con.execute("PRAGMA table_info(stations)")]
    if cols and "page_id" not in cols:
        con.close()
        os.replace(path, path + ".old")
        print("The new library is being rebuilt... %s" % (path + ".old"))
        con = sqlite3.connect(path)
        create_tables(con)
    return con


# ---------------------- crawl web pages ----------------------
# create a browser. Selenium will automatically download the matching chromediver
def make_driver(headless=True):
    opts = Options()
    opts.add_argument("--ignore-certificate-errors")   # ignore SSL certificate errors -- this web must add
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,2000")
    opts.add_argument("--lang=zh-cn")
    opts.add_argument("--no-first-run")
    if BYPASS_PROXY:
        # connect directly, bypass system proxy (VPN)
        opts.add_argument("--no-proxy-server")
    d = webdriver.Chrome(options=opts)
    d.set_page_load_timeout(60)
    return d

# construct a url for direction of a route
def route_url(route, direction):
    return (BASE_URL + "routeLine.html?routeName=%s&direction=%d&language=zh-tw"
            "&ver=3.8.6&routeType=0&fromDzzp=false" % (route, direction))

#  open page.
def get_page_source(driver, route, direction):
    try:
        driver.get(route_url(route, direction))
    except UnexpectedAlertPresentException:
        # "no data" alert popped up right after page loading -> skip
        try:
            driver.switch_to.alert.accept()
        except Exception:
            pass
        return None
    deadline = time.time() + 25
    while time.time() < deadline:
        try:
            n = len(driver.find_elements(By.CSS_SELECTOR, "#bus_stations .macau-route-station"))
            if n > 0:
                time.sleep(4)
                return driver.page_source
        except UnexpectedAlertPresentException:
            # no data: the site pops up a "no data" alert.
            # ChromeDriver may have auto-dismissed the alert already,
            # so accept() may fail -> just ignore it.
            try:
                driver.switch_to.alert.accept()
            except Exception:
                pass
            return None     # no data in that direction -> return None
        time.sleep(1)
    return None

# gzip -> save in pages table
def save_page(con, route, direction, html):
    gz = gzip.compress(html.encode("utf-8"))
    con.execute("INSERT INTO pages(crawl_time, route_name, direction, html, parsed) "
                "VALUES(?,?,?,?,0)", (now_str(), route, direction, gz))
    con.commit()


# ---------------------- regular expression extraction ----------------------
#  extract stations and buses
def parse_route_page(html):
    stations, buses = [], []
    # 1. match the start tag of each station
    tag_re = re.compile(
        r'<div id="_(\d+)"'
        r' data-code="([^"]+)"'
        r' data-stopcode="([^"]+)"'
        r' class="macau-route-station[^"]*">')
    tags = list(tag_re.finditer(html))
    # 2. processing each station
    for i, tag in enumerate(tags):
        seq, code, stop = int(tag.group(1)), tag.group(2), tag.group(3)
        end = tags[i + 1].start() if i + 1 < len(tags) else len(html)
        block = html[tag.end():end]
        # 3. extract station and lane name
        m = re.search(r'station-title="([^"]*)" station-lane-name="([^"]*)"', block)
        stations.append({'seq': seq, 'code': code, 'stopcode': stop,
                         'name': m.group(1).lstrip('-') if m else '',
                         'lane': m.group(2) if m else ''})
        # 4. runing buses (a busLocDom = a bus)
        for bt in re.finditer(r'<div class="busLocDom"', block):
            s = bt.start()
            e = block.find('<div class="busLocDom"', s + 1)
            e = e if e != -1 else len(block)
            bb = block[s:e]
            plate = re.search(r'<p class="busPlateL"[^>]*>([^<]+)</p>', bb)
            if not plate:
                continue
            top = re.search(r'style="top: ([0-9.]+)%', bb)
            spd = re.search(r'<div class="readyStart">\s*([0-9.]+)\s*km/h', bb)
            buses.append({'page_seq': seq, 'station_code': code,
                          'plate': plate.group(1).strip(),
                          'speed': float(spd.group(1)) if spd else None,
                          'position': float(top.group(1)) if top else None})
    return stations, buses

# parse pages: extract stations and buses from pages table, write into stations and buses tables
def parse_pages(con):
    rows = con.execute("SELECT id, html FROM pages WHERE parsed = 0").fetchall()
    for page_id, gz in rows:
        html = gzip.decompress(gz).decode("utf-8")
        stations, buses = parse_route_page(html)
        con.executemany(
            "INSERT INTO stations(page_id, seq, station_code, stopcode, station_name, lane_name) "
            "VALUES(?,?,?,?,?,?)",
            [(page_id, s['seq'], s['code'], s['stopcode'], s['name'], s['lane']) for s in stations])
        con.executemany(
            "INSERT INTO buses(page_id, segment_seq, segment_station_code, bus_plate, speed_kmh, position_pct) "
            "VALUES(?,?,?,?,?,?)",
            [(page_id, b['page_seq'], b['station_code'], b['plate'], b['speed'], b['position'])
             for b in buses])
        con.execute("UPDATE pages SET parsed = 1 WHERE id = ?", (page_id,))
        con.commit()
    return len(rows)


# ---------------------- main ----------------------
# a round - each route & two direction - save in pages table
def crawl_once(driver, con, routes):
    """"""
    for route in routes:
        for direction in (0, 1):
            html = get_page_source(driver, route, direction)
            if html is None:
                print("  %s direction %d has no data, Skip! " % (route, direction))
                continue
            save_page(con, route, direction, html)
            print("  [%s] %s direction %d has been saved (%d)" % (now_str(), route, direction, len(html)))


# continous crawling
def wait_until(hhmm):
    """Wait until hh:mm today; if that time has passed, wait until tomorrow."""
    while True:
        now = datetime.now()
        target = now.replace(hour=int(hhmm[:2]), minute=int(hhmm[3:]),
                             second=0, microsecond=0)
        if target <= now:                       # today's time already passed -> tomorrow
            target += timedelta(days=1)
        print("== Waiting until %s to start crawling ==" % target.strftime("%Y-%m-%d %H:%M"))
        time.sleep((target - now).total_seconds())


def run_schedule(routes, interval, db_path, headless=True):
    """Scheduled crawling: start at START_TIME, stop at END_TIME, for DAYS days."""
    con = init_db(db_path)
    driver = make_driver(headless)
    round_no = 0
    print("== Crawler Startup @ %s ==" % now_str())
    print("== route: %s | interval: %ds | database: %s ==" % (routes, interval, os.path.abspath(db_path)))
    print("== every day %s start, %s stop, for %d days ==" % (START_TIME, END_TIME, DAYS))
    today = date.today()
    try:
        while date.today() < today + timedelta(days=DAYS):
            hhmm = datetime.now().strftime("%H:%M")
            if hhmm < START_TIME:
                wait_until(START_TIME)          # not yet start time -> wait
            elif hhmm >= END_TIME:
                wait_until(START_TIME)          # already past stop time -> wait until tomorrow
            print("\n== %s start crawling today ==" % now_str())
            while True:                         # crawl inside today's time window
                if datetime.now().strftime("%H:%M") >= END_TIME:
                    print("== reached stop time %s, stop today, continue tomorrow ==" % END_TIME)
                    break
                round_no += 1
                print("\n== round %d @ %s ==" % (round_no, now_str()))
                try:
                    crawl_once(driver, con, routes)          # step1 - crawler
                    n = parse_pages(con)                     # step2 - regular extracting
                    print("this round extracted %d pages, with a total of %d pages, %d stations, and %d buses" % (
                        n,
                        con.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
                        con.execute("SELECT COUNT(*) FROM stations").fetchone()[0],
                        con.execute("SELECT COUNT(*) FROM buses").fetchone()[0]))
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print("Error in this round", e)
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = make_driver(headless)           # rebuild browser
                time.sleep(interval)                         # wait for next round
    except KeyboardInterrupt:
        print("\n== Manually stop (Ctrl+C), and all data has been saved ==")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        con.close()
        print("== ENDING. Database: %s ==" % os.path.abspath(db_path))

# Param
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Macau bus (DSAT) crawler")
    ap.add_argument("--routes", nargs="+", default=["3", "26A", "17"])
    ap.add_argument("--interval", type=int, default=600)
    ap.add_argument("--db", default="macau_bus.db")
    ap.add_argument("--show-browser", dest="headless", action="store_false", default=True)
    args = ap.parse_args()
    run_schedule(args.routes, args.interval, args.db, args.headless)
