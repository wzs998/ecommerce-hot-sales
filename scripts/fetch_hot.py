#!/usr/bin/env python3
"""电商每日热销榜抓取脚本（免费方案核心）。

架构：多平台公开榜单页采集 -> 统一 JSON -> 前端渲染，全免费、无需服务器/数据库。

数据源（按优先级）：
  1. 什么值得买 top 榜  https://www.smzdm.com/top/   —— 可直接抓取，实测可用
  2. 京东排行榜        https://www.jd.com/rankingList —— 页面为 JS 渲染，需无头浏览器，
                                                      当前为"尽力而为"解析，抓不到时自动回退模拟数据
  3. 淘宝 / 拼多多热销榜 —— 需登录态 / 风控严格，默认关闭，预留占位

策略：
  - 每平台独立抓取，单个平台失败不影响其他平台；
  - 失败的平台自动用模拟数据补位（mock），保证每天都有数据可展示；
  - 遵守 robots 协议，每天只跑 1 次，个人学习用途；
  - 自动读取前一日数据，对比计算排名变化(↑↓)。

用法：
  python3 scripts/fetch_hot.py                 # 默认：抓真实源，失败回退模拟
  python3 scripts/fetch_hot.py --mock          # 强制全用模拟数据（离线 Demo）
  python3 scripts/fetch_hot.py --sources smzdm # 只抓指定平台
  python3 scripts/fetch_hot.py --date 2026-09-02
"""
import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 保证能 import 同目录的 mock_data

import requests
from bs4 import BeautifulSoup

CST = timezone(timedelta(hours=8))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 平台定义: key -> (名称, 榜单 URL, 是否默认启用, 说明)
SOURCES = {
    "smzdm": ("什么值得买", "https://www.smzdm.com/top/", True, "公开榜单页，可稳定抓取"),
    "jd":    ("京东",       "https://www.jd.com/rankingList", True, "JS 渲染，尽力而为，抓不到自动回退"),
    "tb":    ("淘宝",       "", False, "需登录态/风控严格，默认关闭"),
    "pdd":   ("拼多多",     "", False, "需登录态/风控严格，默认关闭"),
}

MAX_PER_PLATFORM = 15   # 每平台最多保留条数
REQUEST_TIMEOUT = 15    # 秒
RETRIES = 2


# ---------------------------------------------------------------- HTTP
def http_get(url: str) -> str | None:
    """带 UA、重试、超时的 GET，失败返回 None。"""
    last_err = None
    for i in range(RETRIES + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
            last_err = f"HTTP {resp.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(1.5 * (i + 1))
    print(f"    [warn] 抓取失败 {url}: {last_err}")
    return None


def normalize_price(raw: str) -> str:
    """'50元' -> '¥50'；'¥199' -> '¥199'；空 -> '—'。"""
    raw = (raw or "").strip()
    if not raw:
        return "—"
    if raw.endswith("元"):
        raw = raw[:-1]
    if raw.startswith("¥"):
        return raw
    return f"¥{raw}"


# ---------------------------------------------------------------- 解析器
def parse_smzdm(html: str) -> list[dict]:
    """解析什么值得买 top 榜（结构已实测：feed-hot-card）。

    该页有多个榜单分区（data-tab），每个分区内又是多列网格布局
    （data-position 按列交错，如 1,7,2,8...）。因此：
      1) 只取第一个分区（默认激活的榜单）的卡片；
      2) 以 data-position 为准，按名次排序后返回。
    """
    soup = BeautifulSoup(html, "lxml")
    first_tab = None
    grouped: list[dict] = []
    for card in soup.select("div.feed-hot-card"):
        tab = card.get("data-tab")
        if not tab:
            continue
        if first_tab is None:
            first_tab = tab
        if tab != first_tab:
            break  # 已进入下一个榜单分区，停止
        a = card.find("a", href=True)
        title_el = card.select_one(".feed-hot-title")
        img_el = card.select_one(".feed-hot-pic img")
        price_el = card.select_one(".z-highlight")
        if not (a and title_el):
            continue
        pos = card.get("data-position") or ""
        grouped.append({
            "rank": int(pos) if pos.isdigit() else len(grouped) + 1,
            "title": title_el.get_text(strip=True),
            "price": normalize_price(price_el.get_text(strip=True) if price_el else ""),
            "url": a["href"],
            "image": img_el.get("src", "") if img_el else "",
        })
    grouped.sort(key=lambda x: x["rank"])
    return grouped[:MAX_PER_PLATFORM]


def parse_jd(html: str) -> list[dict]:
    """京东排行榜解析（尽力而为模板）。

    注意：该页面为 JS 动态渲染，纯 requests 通常拿不到商品节点，
    抓不到时上层会自动回退模拟数据。若要真实抓取京东，可改用
    Playwright / Selenium 无头浏览器（免费、开源），或接入官方开放平台 API（需资质）。
    """
    soup = BeautifulSoup(html or "", "lxml")
    items = []
    # 常见的排行榜商品卡片类名，随页面改版可能失效，需按需维护
    for node in soup.select(".rank-goods, .gl-item, .shop_list .li, li[data-sku]")[:MAX_PER_PLATFORM]:
        a = node.find("a", href=True)
        img = node.select_one("img")
        price_el = node.select_one(".p-price, .price")
        title_el = node.select_one(".p-name, .title, .name")
        if not (a and title_el):
            continue
        items.append({
            "rank": len(items) + 1,
            "title": title_el.get_text(strip=True),
            "price": normalize_price(price_el.get_text(strip=True) if price_el else ""),
            "url": a["href"] if a["href"].startswith("http") else "https://www.jd.com" + a["href"],
            "image": img.get("src", "") if img else "",
        })
    return items


def parse_taobao(html: str) -> list[dict]:
    """淘宝热销榜占位：默认关闭，返回空列表（需登录态，不在免费范围内）。"""
    return []


def parse_pdd(html: str) -> list[dict]:
    """拼多多热销榜占位：默认关闭，返回空列表（需登录态，风控严格）。"""
    return []


PARSERS = {
    "smzdm": parse_smzdm,
    "jd": parse_jd,
    "tb": parse_taobao,
    "pdd": parse_pdd,
}


# ---------------------------------------------------------------- 模拟回退
def mock_for(platform: str, label: str, day: str) -> tuple[list[dict], str]:
    """单平台回退：从 mock_data 生成该平台的模拟数据。"""
    from mock_data import build_mock_dataset
    ds = build_mock_dataset(day)
    items = [it for it in ds["items"] if it["platform"] == platform]
    return items, "mock"


# ---------------------------------------------------------------- 排名变化
def normalize_title(s: str) -> str:
    """标题归一化，用于跨日匹配。"""
    return re.sub(r"\s+", "", s or "")


def compute_trend(prev_items: list[dict], curr_items: list[dict]) -> None:
    """就地给 curr_items 计算 trend/change（对比昨日排名）。"""
    prev_map = {normalize_title(it["title"]): it["rank"] for it in prev_items}
    for it in curr_items:
        prev_rank = prev_map.get(normalize_title(it["title"]))
        if prev_rank is None:
            it["trend"], it["change"] = "new", 0
        elif prev_rank > it["rank"]:
            it["trend"], it["change"] = "up", prev_rank - it["rank"]
        elif prev_rank < it["rank"]:
            it["trend"], it["change"] = "down", it["rank"] - prev_rank
        else:
            it["trend"], it["change"] = "same", 0


def load_prev_items(day: str) -> list[dict]:
    """读取昨日榜单，用于排名变化计算。"""
    prev_day = (datetime.strptime(day, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    p = DATA_DIR / f"hot_{prev_day}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("items", [])
        except Exception:  # noqa: BLE001
            return []
    return []


# ---------------------------------------------------------------- 主流程
def fetch_platform(key: str, label: str, day: str) -> tuple[list[dict], str]:
    """抓取单个平台，返回 (items, status)，status ∈ {live, mock}。"""
    _, url, enabled, _note = SOURCES[key]
    if not enabled or not url:
        print(f"  [{key}] 未启用，使用模拟数据")
        return mock_for(key, label, day)

    html = http_get(url)
    if html:
        try:
            items = PARSERS[key](html)
            items = items[:MAX_PER_PLATFORM]
            if items:
                for it in items:
                    it["platform"] = key
                    it["platform_label"] = label
                print(f"  [{key}] 抓取成功，{len(items)} 条")
                return items, "live"
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] [{key}] 解析失败: {e}")

    print(f"  [{key}] 抓取失败，回退模拟数据")
    return mock_for(key, label, day)


def main() -> int:
    parser = argparse.ArgumentParser(description="电商每日热销榜抓取")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--mock", action="store_true", help="强制使用模拟数据")
    parser.add_argument("--sources", default=None, help="逗号分隔的平台 key，如 smzdm,jd")
    args = parser.parse_args()

    day = args.date
    enabled = [s.strip() for s in (args.sources or "").split(",") if s.strip()] \
        if args.sources else [k for k, v in SOURCES.items() if v[2]]

    print(f"[fetch] 日期={day} 平台={','.join(enabled)} mock_only={args.mock}")

    all_items, sources_status = [], {}
    for key in enabled:
        if args.mock:
            label = SOURCES[key][0]
            items, status = mock_for(key, label, day)
        else:
            items, status = fetch_platform(key, SOURCES[key][0], day)
        all_items.extend(items)
        sources_status[key] = status
        time.sleep(1)  # 控制频率，遵守 robots 协议

    # 排名变化（对比昨日存档）
    prev_items = load_prev_items(day) if not args.mock else []
    compute_trend(prev_items, all_items)

    dataset = {
        "date": day,
        "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %z"),
        "total": len(all_items),
        "sources": sources_status,
        "items": all_items,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    latest = DATA_DIR / "latest.json"
    dated = DATA_DIR / f"hot_{day}.json"
    text = json.dumps(dataset, ensure_ascii=False, indent=2)
    latest.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")

    live_n = sum(1 for v in sources_status.values() if v == "live")
    print(f"[fetch] 完成：{dataset['total']} 条，live={live_n} 平台，mock={len(sources_status)-live_n} 平台")
    print(f"[fetch] 已写入 {latest} / {dated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
