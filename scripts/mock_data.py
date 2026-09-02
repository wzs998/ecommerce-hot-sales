#!/usr/bin/env python3
"""生成模拟热销榜数据（离线 Demo / 真实源抓取失败时的自动回退）。

用法：
    python3 scripts/mock_data.py                     # 默认今天，写 data/latest.json + data/hot_<日期>.json
    python3 scripts/mock_data.py --date 2026-09-02   # 指定日期
    python3 scripts/mock_data.py --out /tmp/a.json   # 只写单个文件

说明：模拟数据仅用于跑通"抓取 -> JSON -> 前端渲染"整条链路，
真实使用时请以 scripts/fetch_hot.py 抓取的线上数据为准。
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
# 商品图：存放在仓库 data/img/ 下的本地图片（自托管，与商品一一对应，不依赖外部图床）
IMG_BASE = "data/img/{key}-{i}.jpg"

# 平台: (key, 展示名)
PLATFORMS = [
    ("jd", "京东"),
    ("tb", "淘宝"),
    ("pdd", "拼多多"),
    ("smzdm", "什么值得买"),
]

# 每个平台的模拟商品（title / price / url / trend / change）
# trend: up=排名上升 down=下降 same=持平 new=新品
MOCK_ITEMS = {
    "jd": [
        ("Apple iPhone 16 Pro 256GB 原色钛金属 5G手机", "¥7999", "https://www.jd.com/", "new", 0),
        ("小米 智能门锁 Pro 指纹锁 C级锁芯 全自动", "¥1299", "https://www.jd.com/", "up", 2),
        ("美的 变频空调 大1.5匹 新一级能效 智能语音", "¥2199", "https://www.jd.com/", "up", 1),
        ("华为 FreeBuds Pro 4 无线蓝牙耳机 降噪", "¥899", "https://www.jd.com/", "down", 1),
        ("联想拯救者 Y9000P 电竞游戏本 16英寸", "¥9299", "https://www.jd.com/", "same", 0),
        ("格力 电风扇 落地扇 家用静音遥控", "¥199", "https://www.jd.com/", "up", 3),
        ("蒙牛特仑苏 纯牛奶 250ml×16盒 整箱", "¥59.9", "https://www.jd.com/", "up", 5),
        ("罗技 MX Master 3S 无线蓝牙鼠标 静音", "¥649", "https://www.jd.com/", "down", 2),
        ("苏泊尔 电饭煲 4L 球釜 智能预约", "¥349", "https://www.jd.com/", "up", 1),
        ("海信 55英寸 4K超高清 智能网络电视", "¥1899", "https://www.jd.com/", "new", 0),
    ],
    "tb": [
        ("优衣库 U系列 圆领纯棉T恤 男女同款", "¥79", "https://www.taobao.com/", "up", 2),
        ("花西子 空气蜜粉 定妆散粉 控油持妆", "¥149", "https://www.taobao.com/", "same", 0),
        ("三只松鼠 每日坚果 30包 混合装", "¥89", "https://www.taobao.com/", "up", 4),
        ("蕉下 冰丝防晒衣 UPF50+ 轻薄透气", "¥199", "https://www.taobao.com/", "down", 1),
        ("欧莱雅 玻尿酸充盈 安瓶精华 保湿", "¥259", "https://www.taobao.com/", "up", 3),
        ("小米 氮化镓充电器 67W 快充", "¥99", "https://www.taobao.com/", "new", 0),
        ("六神 花露水 195ml×2瓶 驱蚊清凉", "¥29.9", "https://www.taobao.com/", "up", 6),
        ("鸿星尔克 轻便透气运动跑鞋 男款", "¥159", "https://www.taobao.com/", "down", 3),
    ],
    "pdd": [
        ("无线蓝牙耳机 高音质降噪 运动款", "¥29.9", "https://www.pinduoduo.com/", "up", 5),
        ("家用厨房置物架 多层落地收纳架", "¥45.9", "https://www.pinduoduo.com/", "new", 0),
        ("手机支架 桌面可调节 懒人神器", "¥9.9", "https://www.pinduoduo.com/", "up", 2),
        ("车载吸尘器 大吸力 无线便携", "¥79", "https://www.pinduoduo.com/", "up", 1),
        ("夏季冰丝凉席 空调被 三件套", "¥59", "https://www.pinduoduo.com/", "down", 1),
        ("洗衣凝珠 留香珠 持久留香 60颗", "¥19.9", "https://www.pinduoduo.com/", "up", 3),
    ],
    "smzdm": [
        ("京东PLUS 年卡会员 送免运费券", "¥148", "https://www.smzdm.com/top/", "up", 2),
        ("天猫超市 牛奶卡 88VIP 充值", "¥99", "https://www.smzdm.com/top/", "down", 1),
        ("星巴克 中杯拿铁 电子兑换券", "¥25", "https://www.smzdm.com/top/", "same", 0),
        ("Kindle 电子书 0.99元 特价专场", "¥0.99", "https://www.smzdm.com/top/", "new", 0),
        ("瑞幸 9.9元咖啡券 全国通用 囤货", "¥9.9", "https://www.smzdm.com/top/", "up", 4),
        ("小米手环9 NFC版 到手价", "¥229", "https://www.smzdm.com/top/", "up", 1),
    ],
}


def build_mock_dataset(day: str) -> dict:
    """生成一份完整的模拟榜单数据集（统一 JSON 结构）。"""
    items = []
    for key, label in PLATFORMS:
        for i, (title, price, url, trend, change) in enumerate(MOCK_ITEMS[key], start=1):
            items.append({
                "platform": key,
                "platform_label": label,
                "rank": i,
                "title": title,
                "price": price,
                "url": url,
                "image": IMG_BASE.format(key=key, i=i),
                "trend": trend,
                "change": change,
            })
    return {
        "date": day,
        "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S %z"),
        "total": len(items),
        "sources": {key: "mock" for key, _ in PLATFORMS},
        "items": items,
    }


def get_today() -> str:
    return date.today().strftime("%Y-%m-%d")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成模拟热销榜数据")
    parser.add_argument("--date", default=get_today(), help="榜单日期 YYYY-MM-DD")
    parser.add_argument("--out", default=None, help="只输出到单个文件")
    args = parser.parse_args()

    data = build_mock_dataset(args.date)
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[mock] 已写入 {out}（{data['total']} 条）")
        return 0

    latest = data_dir / "latest.json"
    dated = data_dir / f"hot_{args.date}.json"
    latest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[mock] 已写入 {latest} 和 {dated}（{data['total']} 条，来源全部为 mock）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
