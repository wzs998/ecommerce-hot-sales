#!/usr/bin/env python3
"""生成模拟新品监控快照序列（离线 Demo / 真实采集失败回退）。

思路（对应「快照差分」方案）：
  每 15 分钟生成一条快照，记录每个商品当时的 销量/排名/价格；
  多次快照之间出现的新商品、销量从 0 到 1（破0）、排名蹿升等，
  交给 analyze_new_products.py 做差分分析并打分。

本脚本生成 2026-09-02 14:00 ~ 16:00 共 9 条快照，
包含 60 款处于不同起量阶段的潜力新品（淘宝 28 / 拼多多 22 / 京东 10），
每款带 1688 同款搜索链接（供选品找工厂货源）。

用法：
    python3 scripts/mock_snapshots.py            # 生成默认演示序列
    python3 scripts/mock_snapshots.py --window-hours 2
"""
import argparse
import hashlib
import json
import random
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAP_DIR = DATA_DIR / "snapshots"
DAY = "2026-09-02"
BASE_TIME = datetime.strptime(f"{DAY} 14:00", "%Y-%m-%d %H:%M").replace(tzinfo=CST)
SNAP_INTERVAL_MIN = 15

# 1688 同款搜索链接模板
ALI1688_URL = "https://s.1688.com/selloffer/offer_search.htm?keywords={kw}"


# ---------------------------------------------------------------------------
# 60 款潜力新品
#   id       : 唯一标识（np-平台-序号）
#   platform : tb / pdd / jd
#   pattern  : hot(强起量) / medium(中速) / slow(慢速) / observing(观察期, 未破0)
#   appear   : 首次出现在快照序列的分钟偏移（相对 14:00）
#   keywords : 1688 同款搜索关键词
def _p(pid, platform, title, price, pattern, appear, kw):
    pl_label = {"tb": "淘宝", "pdd": "拼多多", "jd": "京东"}[platform]
    return {
        "id": pid, "platform": platform, "platform_label": pl_label,
        "title": title, "price": price,
        "image": f"data/img/{pid}.jpg",
        "pattern": pattern, "appear": appear, "keywords": kw,
    }


PRODUCTS = [
    # ---------------- 淘宝 28 款 ----------------
    _p("np-tb-1",  "tb", "无线蓝牙耳机 新升级降噪版", "¥79",   "hot",      15, "无线蓝牙耳机 降噪"),
    _p("np-tb-2",  "tb", "桌面迷你加湿器 静音款",     "¥49",   "medium",   30, "桌面加湿器 静音"),
    _p("np-tb-3",  "tb", "便携榨汁杯 USB充电",        "¥69",   "medium",   45, "便携榨汁杯"),
    _p("np-tb-4",  "tb", "宠物自动喂食器 定时定量",   "¥129",  "observing",60, "宠物自动喂食器"),
    _p("np-tb-5",  "tb", "智能体重秤 体脂测量",       "¥59",   "hot",      15, "智能体脂秤"),
    _p("np-tb-6",  "tb", "挂烫机 手持便携",           "¥89",   "hot",      30, "手持挂烫机"),
    _p("np-tb-7",  "tb", "蓝牙键盘 超薄静音",         "¥99",   "medium",   45, "超薄蓝牙键盘"),
    _p("np-tb-8",  "tb", "电动牙刷 声波款",           "¥129",  "hot",      60, "声波电动牙刷"),
    _p("np-tb-9",  "tb", "香薰加湿器 卧室助眠",       "¥79",   "medium",   75, "香薰加湿器"),
    _p("np-tb-10", "tb", "手机磁吸支架 车载",         "¥29.9", "hot",      90, "磁吸车载手机支架"),
    _p("np-tb-11", "tb", "除螨仪 家用床铺",           "¥199",  "medium",   105, "除螨仪 家用"),
    _p("np-tb-12", "tb", "真空保鲜盒 自动抽真空",     "¥89",   "slow",     30, "真空保鲜盒"),
    _p("np-tb-13", "tb", "电动打蛋器 烘焙家用",       "¥69",   "medium",   45, "电动打蛋器"),
    _p("np-tb-14", "tb", "硅胶保鲜盖 六件套",         "¥19.9", "slow",     60, "硅胶保鲜盖"),
    _p("np-tb-15", "tb", "儿童水杯 防摔吸管",         "¥39",   "hot",      75, "儿童水杯 防摔"),
    _p("np-tb-16", "tb", "化妆收纳盒 亚克力",         "¥49",   "medium",   90, "亚克力化妆收纳盒"),
    _p("np-tb-17", "tb", "折叠收纳箱 大容量",         "¥45.9", "slow",     105, "折叠收纳箱"),
    _p("np-tb-18", "tb", "眼部按摩仪 热敷",           "¥159",  "observing",45, "眼部按摩仪 热敷"),
    _p("np-tb-19", "tb", "电动修脚器 家用",           "¥59",   "medium",   60, "电动修脚器"),
    _p("np-tb-20", "tb", "便携热水壶 折叠硅胶",       "¥79",   "slow",     75, "折叠硅胶热水壶"),
    _p("np-tb-21", "tb", "指甲油 快干持久",           "¥19.9", "medium",   90, "快干指甲油"),
    _p("np-tb-22", "tb", "洗衣留香珠 香氛",           "¥29.9", "slow",     105, "洗衣留香珠"),
    _p("np-tb-23", "tb", "桌面收纳盒 文具",           "¥25.9", "slow",     30, "桌面文具收纳盒"),
    _p("np-tb-24", "tb", "空气炸锅纸 100张",          "¥15.9", "hot",      45, "空气炸锅纸"),
    _p("np-tb-25", "tb", "蓝牙音箱 户外防水",         "¥129",  "medium",   60, "户外蓝牙音箱"),
    _p("np-tb-26", "tb", "智能台灯 护眼调光",         "¥149",  "observing",75, "智能护眼台灯"),
    _p("np-tb-27", "tb", "电动拖把 无线",             "¥199",  "hot",      90, "无线电动拖把"),
    _p("np-tb-28", "tb", "暖手宝 充电式",             "¥49",   "medium",   105, "充电式暖手宝"),
    # ---------------- 拼多多 22 款 ----------------
    _p("np-pdd-1",  "pdd", "挂脖风扇 无叶设计",       "¥39",   "hot",      90, "挂脖风扇 无叶"),
    _p("np-pdd-2",  "pdd", "便携咖啡机 手压浓缩",     "¥199",  "observing",105, "便携咖啡机 手压"),
    _p("np-pdd-3",  "pdd", "车载手机支架 出风口",     "¥15.9", "hot",      15, "车载手机支架 出风口"),
    _p("np-pdd-4",  "pdd", "厨房计时器 磁吸",         "¥12.9", "medium",   30, "厨房计时器"),
    _p("np-pdd-5",  "pdd", "蒜蓉神器 手动切蒜",       "¥9.9",  "hot",      45, "手动切蒜器"),
    _p("np-pdd-6",  "pdd", "浴室置物架 免打孔",       "¥19.9", "medium",   60, "浴室置物架 免打孔"),
    _p("np-pdd-7",  "pdd", "磨刀神器 快速磨刀",       "¥13.9", "slow",     75, "快速磨刀器"),
    _p("np-pdd-8",  "pdd", "宠物除毛刷 双面",         "¥16.9", "medium",   90, "宠物除毛刷"),
    _p("np-pdd-9",  "pdd", "收纳箱 大号衣物",         "¥29.9", "slow",     105, "衣物收纳箱 大号"),
    _p("np-pdd-10", "pdd", "懒人抹布 一次性",         "¥14.9", "hot",      30, "一次性懒人抹布"),
    _p("np-pdd-11", "pdd", "手机防水袋 游泳",         "¥8.9",  "medium",   45, "手机防水袋"),
    _p("np-pdd-12", "pdd", "挂钩 免打孔强力",         "¥9.9",  "slow",     60, "免打孔强力挂钩"),
    _p("np-pdd-13", "pdd", "无线吸尘器 车载",         "¥79",   "observing",75, "车载无线吸尘器"),
    _p("np-pdd-14", "pdd", "冰袖 防晒 UPF50+",        "¥12.9", "hot",      90, "防晒冰袖"),
    _p("np-pdd-15", "pdd", "鞋架 简易多层",           "¥24.9", "slow",     105, "简易多层鞋架"),
    _p("np-pdd-16", "pdd", "电子秤 厨房精准",         "¥22.9", "medium",   45, "厨房电子秤 精准"),
    _p("np-pdd-17", "pdd", "折叠脸盆 旅行便携",       "¥13.9", "slow",     60, "折叠旅行脸盆"),
    _p("np-pdd-18", "pdd", "搓澡巾 加长双面",         "¥7.9",  "slow",     75, "双面搓澡巾"),
    _p("np-pdd-19", "pdd", "桌面风扇 迷你静音",       "¥19.9", "medium",   90, "桌面迷你风扇"),
    _p("np-pdd-20", "pdd", "收纳挂袋 衣柜门挂",       "¥15.9", "slow",     105, "衣柜收纳挂袋"),
    _p("np-pdd-21", "pdd", "钥匙收纳架 免打孔",       "¥9.9",  "slow",     30, "钥匙收纳架"),
    _p("np-pdd-22", "pdd", "分装瓶 旅行套装",         "¥12.9", "slow",     45, "旅行分装瓶"),
    # ---------------- 京东 10 款 ----------------
    _p("np-jd-1",  "jd", "智能门锁 指纹人脸",         "¥899",  "observing",15, "智能门锁 人脸识别"),
    _p("np-jd-2",  "jd", "机械键盘 客制化轴体",       "¥299",  "medium",   30, "客制化机械键盘"),
    _p("np-jd-3",  "jd", "显示器支架 升降",           "¥159",  "medium",   45, "显示器支架 升降"),
    _p("np-jd-4",  "jd", "桌面净化器 空气",           "¥399",  "observing",60, "桌面空气净化器"),
    _p("np-jd-5",  "jd", "便携投影仪 家用",           "¥999",  "hot",      75, "便携投影仪"),
    _p("np-jd-6",  "jd", "无线充电器 三合一",         "¥129",  "hot",      90, "三合一无线充电器"),
    _p("np-jd-7",  "jd", "降噪耳麦 头戴式",           "¥349",  "medium",   105, "头戴式降噪耳机"),
    _p("np-jd-8",  "jd", "智能音箱 带屏",             "¥449",  "observing",45, "带屏智能音箱"),
    _p("np-jd-9",  "jd", "摄像头 家用监控",           "¥199",  "hot",      60, "家用监控摄像头"),
    _p("np-jd-10", "jd", "人体工学椅 办公",           "¥699",  "medium",   75, "人体工学办公椅"),
]


# ---------------------------------------------------------------------------
# 确定性轨迹生成：同一商品每次生成结果一致（可复现）
def _seed(v: str) -> int:
    return int(hashlib.md5(v.encode()).hexdigest(), 16)


def gen_traj(pid: str, appear: int, pattern: str) -> dict:
    """生成 {分钟偏移: (销量, 排名)} 轨迹。"""
    rnd = random.Random(_seed(pid))
    offsets = list(range(appear, 121, SNAP_INTERVAL_MIN))
    end = offsets[-1]
    span = max(end - appear, SNAP_INTERVAL_MIN)

    if pattern == "hot":
        bz = appear + rnd.choice([15, 30])
        final_sales = rnd.randint(260, 420)
        final_rank = rnd.randint(5, 22)
        start_rank = final_rank + rnd.randint(35, 60)
    elif pattern == "medium":
        bz = appear + rnd.choice([30, 45])
        final_sales = rnd.randint(90, 210)
        final_rank = rnd.randint(14, 38)
        start_rank = final_rank + rnd.randint(15, 35)
    elif pattern == "slow":
        bz = appear + rnd.choice([45, 60, 75])
        final_sales = rnd.randint(20, 80)
        final_rank = rnd.randint(35, 80)
        start_rank = final_rank + rnd.randint(5, 18)
    else:  # observing：未破0，仅排名缓慢爬升
        bz = None
        final_sales = 0
        final_rank = rnd.randint(50, 220)
        start_rank = final_rank + rnd.randint(10, 35)

    traj = {}
    for off in offsets:
        frac = (off - appear) / span
        rank = int(start_rank - (start_rank - final_rank) * frac)
        if pattern == "observing" or off < bz:
            sales = 0
        else:
            progress = (off - bz) / max(end - bz, SNAP_INTERVAL_MIN)
            sales = min(final_sales, int(final_sales * progress * 0.85 + rnd.randint(1, 8)))
        traj[off] = (max(0, sales), max(1, rank))
    return traj


def build_snapshot(minute_offset: int) -> dict:
    """生成某分钟偏移对应的快照。"""
    ts = BASE_TIME + timedelta(minutes=minute_offset)
    items = []
    for p in PRODUCTS:
        if minute_offset < p["appear"]:
            continue
        sales, rank = gen_traj(p["id"], p["appear"], p["pattern"])[minute_offset]
        items.append({
            "id": p["id"],
            "platform": p["platform"],
            "platform_label": p["platform_label"],
            "title": p["title"],
            "price": p["price"],
            "image": p["image"],
            "sales": sales,
            "rank": rank,
            "ali1688_url": ALI1688_URL.format(kw=urllib.parse.quote(p["keywords"])),
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
    print(f"[mock_snapshots] 新品 {len(PRODUCTS)} 款，均带 1688 同款链接")
    return 0


if __name__ == "__main__":
    sys.exit(main())
