#!/usr/bin/env python3
"""潜力新品差分分析：把快照序列变成「潜力新品榜」。

核心逻辑（对应快照差分方案）：
  1. 读取 data/snapshots/ 下按时间排序的快照；
  2. 追踪每个商品：首次出现时间（≈上架时刻）、销量从 0 到 1 的时刻（≈破0）、排名变化；
  3. 只对"监控窗口内新出现"的商品打分（常规在售商品不参与）；
  4. 综合 破0速度 / 起量速度 / 排名蹿升 三个信号输出潜力评分，写入 data/hot_new_products.json。

局限（与方案一致）：所有指标都是公开页面的"代理信号"——
  30 分钟破0 ≈ "30~60 分钟内出现销量"；流量倾斜只能由排名/入榜速度间接推断。

用法：
    python3 scripts/analyze_new_products.py
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SNAP_DIR = DATA_DIR / "snapshots"
OUT = DATA_DIR / "hot_new_products.json"

# 打分权重
BASE_SCORE = 30          # 基础分（进入监控即给）
MAX_BROKE = 25           # 破0速度最高分
MAX_GROWTH = 25          # 起量速度最高分
MAX_RANK = 20            # 排名蹿升最高分
MAX_AGE_HOURS = 3        # 只看最近 3 小时内出现的新品


def load_snapshots() -> list[dict]:
    """按时间排序加载全部快照。"""
    snaps = []
    for p in sorted(SNAP_DIR.glob("*.json")):
        try:
            snaps.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    snaps.sort(key=lambda s: s.get("scraped_at", ""))
    return snaps


def parse_ts(s: str) -> datetime:
    s = s.strip()
    # 统一成带时区格式
    if len(s) == 16:
        s += ":00"
    if "+" not in s and s.endswith("+0800"):
        pass
    # 处理 "2026-09-02T14:00:00+0800" 这类无冒号的时区
    if s.endswith("+0800") or s.endswith("+0000"):
        s = s[:-5] + s[-5:-2] + ":" + s[-2:]
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(CST).strftime("%Y-%m-%dT%H:%M:%S%z")


def main() -> int:
    snaps = load_snapshots()
    if len(snaps) < 2:
        print("[analyze] 快照不足（至少需 2 条），请先运行 mock_snapshots.py / fetch_new_products.py")
        return 1

    window_start = parse_ts(snaps[0]["scraped_at"])
    window_end = parse_ts(snaps[-1]["scraped_at"])
    first_ts = window_start

    # 按商品 id 聚合观测序列
    seen: dict[str, list[tuple[datetime, dict]]] = defaultdict(list)
    for snap in snaps:
        ts = parse_ts(snap["scraped_at"])
        for it in snap.get("items", []):
            seen[it["id"]].append((ts, it))

    candidates = []
    for pid, obs in seen.items():
        obs.sort(key=lambda x: x[0])
        first_seen = obs[0][0]
        # 只在窗口内新出现（晚于第一条快照）才算"新品"；常规在售商品排除
        if first_seen <= first_ts + timedelta(seconds=30):
            continue
        age = (window_end - first_seen).total_seconds() / 60
        if age > MAX_AGE_HOURS * 60:
            continue

        last_ts, last = obs[-1]
        first_item = obs[0][1]
        listed_minutes = int((last_ts - first_seen).total_seconds() // 60)

        # 破0：第一个销量 > 0 的观测
        broke_zero = False
        broke_zero_minutes = None
        for ts, it in obs:
            if it.get("sales", 0) > 0:
                broke_zero = True
                broke_zero_minutes = int((ts - first_seen).total_seconds() // 60)
                break

        last_sales = last.get("sales", 0)
        first_rank = first_item.get("rank")
        last_rank = last.get("rank")
        rank_change = (first_rank - last_rank) if (first_rank and last_rank) else 0

        sales_per_hour = last_sales / (max(listed_minutes, 1) / 60)

        candidates.append({
            "id": pid,
            "platform": last.get("platform", ""),
            "platform_label": last.get("platform_label", ""),
            "title": last.get("title", ""),
            "price": last.get("price", ""),
            "image": last.get("image", ""),
            "first_seen": fmt_ts(first_seen),
            "listed_minutes": listed_minutes,
            "broke_zero": broke_zero,
            "broke_zero_minutes": broke_zero_minutes,
            "sales": last_sales,
            "sales_per_hour": round(sales_per_hour, 1),
            "rank": last_rank,
            "rank_change": rank_change,
        })

    if not candidates:
        print("[analyze] 窗口内未发现新品")
        return 0

    # ---- 打分 ----
    max_growth = max(c["sales_per_hour"] for c in candidates) or 1
    max_rank = max(c["rank_change"] for c in candidates) or 1

    for c in candidates:
        # 破0速度分：30 分钟内破0得满分，越慢越少，未破0 观察期给 5 分
        if c["broke_zero"]:
            c["broke_zero_minutes"] = c["broke_zero_minutes"] or 0
            broke_score = MAX_BROKE * max(0.0, 1 - c["broke_zero_minutes"] / 120.0)
        else:
            broke_score = 5.0  # 未破0但排名在动，观察期
        # 起量速度分
        growth_score = MAX_GROWTH * (c["sales_per_hour"] / max_growth)
        # 排名蹿升分
        rank_score = MAX_RANK * (c["rank_change"] / max_rank)

        score = BASE_SCORE + broke_score + growth_score + rank_score
        c["potential_score"] = min(99, int(round(score)))

        # 标签
        tags = []
        if c["broke_zero"] and (c["broke_zero_minutes"] or 0) <= 30:
            tags.append("30分钟破0")
        elif c["broke_zero"]:
            tags.append("已破0")
        else:
            tags.append("观察期")
        if c["sales_per_hour"] >= max_growth * 0.5:
            tags.append("起量快")
        if c["rank_change"] >= 10:
            tags.append("排名飙升")
        c["tags"] = tags

    candidates.sort(key=lambda c: c["potential_score"], reverse=True)

    result = {
        "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %z"),
        "window_start": fmt_ts(window_start),
        "window_end": fmt_ts(window_end),
        "snapshots_count": len(snaps),
        "candidates_count": len(candidates),
        "items": candidates,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[analyze] 窗口 {fmt_ts(window_start)} ~ {fmt_ts(window_end)}，{len(snaps)} 条快照")
    print(f"[analyze] 候选新品 {len(candidates)} 款，已写入 {OUT}")
    for c in candidates[:6]:
        broke_txt = f"{c['broke_zero_minutes']}min" if c["broke_zero_minutes"] is not None else "—"
        print(f"  {c['potential_score']:>2}分 | {c['title'][:18]:<18} | 破0:{broke_txt} | "
              f"销量:{c['sales']:>4} | 排名:{c['rank']} ({c['rank_change']:+d}) | {','.join(c['tags'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
