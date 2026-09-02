#!/usr/bin/env python3
"""生成模拟新品监控快照序列（离线 Demo / 真实采集失败回退）。

思路（对应「快照差分」方案）：
  每 15 分钟生成一条快照，记录每个商品当时的 销量/排名/价格；
  多次快照之间出现的新商品、销量从 0 到 1（破0）、排名蹿升等，
  交给 analyze_new_products.py 做差分分析并打分。

本脚本生成 2026-09-02 14:00 ~ 16:00 共 9 条快照，
包含 6 款处于不同起量阶段的新品 + 4 款常规在售商品（用于差分对照）。

用法：
    python3 scripts/mock_snapshots.py            # 生成默认演示序列
    python3 scripts/mock_snapshots.py --window-hours 2
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAP_DIR = DATA_DIR / "snapshots"
DAY = "2026-09-02"
BASE_TIME = datetime.strptime(f"{DAY} 14:00", "%Y-%m-%d %H:%M").replace(tzinfo=CST)
SNAP_INTERVAL_MIN = 15

# ---------------------------------------------------------------------------
# 商品轨迹定义
#   appear : 首次出现在快照序列中的分钟偏移（相对 14:00）
#   traj   : { 分钟偏移: (销量, 排名) }
# 说明：真实场景下"销量"来自平台展示的付款人数/销量口径（各平台需适配），
#       这里用模拟值演示差分逻辑。
PRODUCTS = [
    # ---- 潜力新品（不同起量阶段）----
    {
        "id": "np-tb-1", "platform": "tb", "platform_label": "淘宝",
        "title": "无线蓝牙耳机 新升级降噪版", "price": "¥79",
        "image": "data/img/np-tb-1.jpg", "appear": 15,
        "traj": {15: (0, 42), 30: (0, 38), 45: (3, 30), 60: (12, 22),
                 75: (35, 18), 90: (80, 14), 105: (150, 11), 120: (320, 8)},
    },
    {
        "id": "np-tb-2", "platform": "tb", "platform_label": "淘宝",
        "title": "桌面迷你加湿器 静音款", "price": "¥49",
        "image": "data/img/np-tb-2.jpg", "appear": 30,
        "traj": {30: (0, 60), 45: (0, 55), 60: (1, 48), 75: (8, 40),
                 90: (22, 32), 105: (60, 25), 120: (180, 20)},
    },
    {
        "id": "np-tb-3", "platform": "tb", "platform_label": "淘宝",
        "title": "便携榨汁杯 USB充电", "price": "¥69",
        "image": "data/img/np-tb-3.jpg", "appear": 45,
        "traj": {45: (0, 30), 60: (0, 28), 75: (2, 24), 90: (10, 21),
                 105: (30, 17), 120: (95, 15)},
    },
    {
        "id": "np-tb-4", "platform": "tb", "platform_label": "淘宝",
        "title": "宠物自动喂食器 定时定量", "price": "¥129",
        "image": "data/img/np-tb-4.jpg", "appear": 60,
        "traj": {60: (0, 80), 75: (0, 75), 90: (0, 68), 105: (0, 60), 120: (0, 55)},
    },
    {
        "id": "np-pdd-1", "platform": "pdd", "platform_label": "拼多多",
        "title": "挂脖风扇 无叶设计", "price": "¥39",
        "image": "data/img/np-pdd-1.jpg", "appear": 90,
        "traj": {90: (0, 120), 105: (1, 95), 120: (45, 50)},
    },
    {
        "id": "np-pdd-2", "platform": "pdd", "platform_label": "拼多多",
        "title": "便携咖啡机 手压浓缩", "price": "¥199",
        "image": "data/img/np-pdd-2.jpg", "appear": 105,
        "traj": {105: (0, 200), 120: (0, 190)},
    },
    # ---- 常规在售商品（差分对照，不应被识别为新品）----
    {
        "id": "ex-tb-1", "platform": "tb", "platform_label": "淘宝",
        "title": "优衣库 U系列 圆领纯棉T恤", "price": "¥79",
        "image": "data/img/tb-1.jpg", "appear": 0,
        "traj": {o: (5000, 2) for o in range(0, 121, 15)},
    },
    {
        "id": "ex-tb-2", "platform": "tb", "platform_label": "淘宝",
        "title": "三只松鼠 每日坚果 30包", "price": "¥89",
        "image": "data/img/tb-3.jpg", "appear": 0,
        "traj": {o: (3200, 4) for o in range(0, 121, 15)},
    },
    {
        "id": "ex-tb-3", "platform": "tb", "platform_label": "淘宝",
        "title": "欧莱雅 玻尿酸精华 安瓶", "price": "¥259",
        "image": "data/img/tb-5.jpg", "appear": 0,
        "traj": {o: (2800, 7) for o in range(0, 121, 15)},
    },
    {
        "id": "ex-tb-4", "platform": "tb", "platform_label": "淘宝",
        "title": "蕉下 冰丝防晒衣 UPF50+", "price": "¥199",
        "image": "data/img/tb-4.jpg", "appear": 0,
        "traj": {o: (2600, 9) for o in range(0, 121, 15)},
    },
]


def build_snapshot(minute_offset: int) -> dict:
    """生成某分钟偏移对应的快照。"""
    ts = BASE_TIME + timedelta(minutes=minute_offset)
    items = []
    for p in PRODUCTS:
        if minute_offset < p["appear"]:
            continue
        sales, rank = p["traj"][minute_offset]
        items.append({
            "id": p["id"],
            "platform": p["platform"],
            "platform_label": p["platform_label"],
            "title": p["title"],
            "price": p["price"],
            "image": p["image"],
            "sales": sales,
            "rank": rank,
        })
    return {
        "scraped_at": ts.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": "mock",
        "items": items,
    }


def snapshot_filename(ts: datetime) -> str:
    return f"{ts.strftime('%Y-%m-%dT%H%M')}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成模拟新品监控快照序列")
    parser.add_argument("--window-hours", type=float, default=2.0, help="监控时长（小时）")
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    total_min = int(args.window_hours * 60)
    out_dir = Path(args.out_dir) if args.out_dir else SNAP_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    offsets = list(range(0, total_min + 1, SNAP_INTERVAL_MIN))
    for off in offsets:
        snap = build_snapshot(off)
        path = out_dir / snapshot_filename(BASE_TIME + timedelta(minutes=off))
        path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[mock_snapshots] 已生成 {len(offsets)} 条快照 -> {out_dir}/")
    print(f"[mock_snapshots] 窗口 {offsets[0]}~{offsets[-1]} 分钟，新品 {sum(1 for p in PRODUCTS if p['id'].startswith('np-'))} 款")
    return 0


if __name__ == "__main__":
    sys.exit(main())
