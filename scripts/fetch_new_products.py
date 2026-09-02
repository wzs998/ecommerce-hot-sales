#!/usr/bin/env python3
"""新品快照采集脚本（供 GitHub Actions 每 15 分钟调用）。

设计：
  - 每次运行生成一条带时间戳的快照，写入 data/snapshots/
  - 先尝试真实数据源（公开"新品"频道）；多数平台需登录/风控，抓不到时
    自动回退到模拟数据（基于 mock_snapshots 的轨迹，按当前时间滚动），
    保证流程不断、Demo 可复现。
  - 差分分析与打分由 analyze_new_products.py 完成。

用法：
    python3 scripts/fetch_new_products.py          # 尝试真实源，失败回退模拟
    python3 scripts/fetch_new_products.py --mock   # 强制模拟
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from mock_snapshots import BASE_TIME, PRODUCTS, build_snapshot  # noqa: E402

CST = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAP_DIR = DATA_DIR / "snapshots"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 公开"新品"入口（真实采集需按平台适配；多数需登录态，默认不可用）
LIVE_SOURCES = {
    "tb":   {"url": "",            "note": "淘宝新品频道需登录态，默认关闭"},
    "jd":   {"url": "",            "note": "京东新品首发为 JS 渲染，需无头浏览器"},
    "smzdm":{"url": "https://www.smzdm.com/fenlei/", "note": "值得买分类页可尝试"},
}


def mock_snapshot_for_now() -> dict:
    """基于当前时间生成一条模拟快照（滚动模拟新品发布过程）。"""
    now = datetime.now(CST)
    minutes = int((now - BASE_TIME).total_seconds() // 60)
    offset = max(0, min(120, minutes))  # 落在演示窗口内
    snap = build_snapshot(offset)
    snap["scraped_at"] = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    snap["source"] = "mock"
    return snap


def try_live() -> dict | None:
    """尽力尝试真实源；这里以什么值得买为例，抓不到返回 None。"""
    url = LIVE_SOURCES["smzdm"]["url"]
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=12)
        if resp.status_code != 200:
            return None
        # 真实新品解析逻辑需按页面结构适配；此处留作扩展点
        return None
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="新品快照采集（15 分钟粒度）")
    parser.add_argument("--mock", action="store_true", help="强制使用模拟数据")
    args = parser.parse_args()

    snap = None
    if not args.mock:
        snap = try_live()
        if snap is None:
            print("[fetch_new] 真实源不可用，回退模拟数据")
    if snap is None:
        snap = mock_snapshot_for_now()

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.strptime(snap["scraped_at"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=CST)
    path = SNAP_DIR / f"{ts.strftime('%Y-%m-%dT%H%M')}.json"
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_new] 快照已写入 {path}（{len(snap['items'])} 条，source={snap['source']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
