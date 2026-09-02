# 电商每日热销产品汇总（免费方案）

一个零成本的「每日热销榜 + 潜力新品监控」网页：
GitHub Actions 自动抓取公开榜单 → 生成 JSON → 静态页面读取渲染 → GitHub Pages 免费托管。
无需服务器、无需数据库、无需付费 API。

- 🔥 **每日热销榜**：各平台热销商品卡片式榜单（排名 / 价格 / 排名变化）。
- 🚀 **潜力新品**：高频快照 + 差分分析，识别上架后短时间内起量异常的新品
  （近似"30 分钟破0 / 流量倾斜"）。当前内置 **60 款**潜力新品（淘宝 28 / 拼多多 22 / 京东 10），
  每款卡片带 **🏭 1688同款** 按钮，一键跳转 1688 按关键词搜索同款/工厂货源。

## 项目结构

```
ecommerce-hot-sales/
├── index.html                  # 前端展示页（Tailwind CDN + 原生 JS，热销榜 + 潜力新品两个视图）
├── scripts/
│   ├── fetch_hot.py            # 热销榜抓取脚本（真实源 + 失败自动回退模拟数据）
│   ├── mock_data.py            # 热销榜模拟数据生成器
│   ├── mock_snapshots.py       # 新品监控模拟快照生成器（离线 Demo / 回退用）
│   ├── fetch_new_products.py   # 新品快照采集（供 Actions 每 15 分钟调用）
│   └── analyze_new_products.py # 快照差分分析 → 潜力新品打分 → hot_new_products.json
├── data/
│   ├── latest.json             # 热销榜数据（前端读取，每次运行自动更新）
│   ├── hot_YYYY-MM-DD.json     # 热销榜按日期存档
│   ├── hot_new_products.json   # 潜力新品分析结果（前端"潜力新品"视图读取，含 1688 同款链接）
│   ├── snapshots/              # 新品监控快照序列（每 15 分钟一条）
│   └── img/                    # 自托管商品图（热销 30 张 + 新品 60 张，与商品一一对应）
├── .github/workflows/
│   ├── daily-fetch.yml         # 每天北京时间 06:00 抓热销榜
│   ├── new-products.yml        # 每 15 分钟采新品快照 + 差分分析
│   └── pages-deploy.yml        # push 到 main 时部署 GitHub Pages
├── requirements.txt
└── README.md
```

## 本地跑通 Demo

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2a. 热销榜数据（纯模拟，稳定可复现）
python3 scripts/mock_data.py
#     或抓真实源（什么值得买实测可用，其余失败自动回退模拟）
python3 scripts/fetch_hot.py

# 2b. 潜力新品数据（生成模拟快照 → 差分分析）
python3 scripts/mock_snapshots.py
python3 scripts/analyze_new_products.py

# 3. 打开页面（前端用 fetch 读数据，必须用 http 服务）
python3 -m http.server 8000
# 浏览器访问 http://localhost:8000 ，顶部切换「🚀 潜力新品」视图
```

> 不要用 file:// 双击打开 index.html（浏览器会拦截本地 fetch）。

## 潜力新品原理与局限

**原理（快照差分）**：每 15 分钟抓一次"新品"列表存快照，对比相邻快照：
- 新出现的商品 → 记录上架时刻（精度 = 轮询间隔）；
- 销量从 0 到 1 → 记录破0用时；排名变化 → 计算蹿升速度；
- 综合 破0速度 / 起量速度 / 排名蹿升 打分（0~99），输出 `hot_new_products.json`。

**局限（务必知悉）**：

| 指标 | 免费方案能做到的 |
|------|------------------|
| 30 分钟破0 | 近似为"30~60 分钟内出现销量"，受轮询间隔与平台销量展示延迟影响 |
| 流量倾斜 | 只能间接推断（排名蹿升、入榜速度），看不到平台真实曝光量 |
| 数据稳定性 | 各平台销量口径不一（付款人数 / 月销累积等），需逐平台适配 |

真实的流量倾斜 / 精确破0属于平台内部数据（生意参谋、京东商智等），免费渠道拿不到；
本方案用公开页面的"代理信号"逼近，适合先用模拟数据验证选品逻辑是否有效。

## 部署到 GitHub Pages（免费）

1. 把本目录推到 GitHub 仓库（分支名 `main`）；
2. 仓库 Settings → Pages → Source 选择 **GitHub Actions**；
3. 推送后 `pages-deploy.yml` 自动部署到
   `https://<你的用户名>.github.io/<仓库名>/`；
4. 自动化：
   - `daily-fetch.yml` 每天北京时间 06:00 抓热销榜；
   - `new-products.yml` 每 15 分钟采新品快照并差分分析（公开仓库 Actions 免费）。

手动触发：Actions → 对应工作流 → Run workflow。

## 数据源说明与合规提醒

| 平台 | 热销榜 | 新品监控 | 说明 |
|------|--------|----------|------|
| 什么值得买 | ✅ 可抓 | 分类页可尝试 | 公开榜单页 |
| 京东 | ⚠️ 尽力而为 | 需无头浏览器 | 榜单为 JS 渲染，抓不到自动回退模拟 |
| 淘宝 / 拼多多 | 🚫 默认关闭 | 需登录态 | 不在免费范围内 |

- 遵守 robots 协议，脚本带 UA、超时、重试与限速。
- **仅供个人学习 / 内部使用**；商业用途请自行评估采集合规风险。
- 平台页面结构随时可能改版，解析器需不定期维护（`fetch_hot.py` / `fetch_new_products.py`）。

## 自定义

- 榜单规模：改 `fetch_hot.py` 的 `MAX_PER_PLATFORM`。
- 新品打分权重：改 `analyze_new_products.py` 的 `BASE_SCORE / MAX_BROKE / MAX_GROWTH / MAX_RANK`。
- 快照频率：改 `new-products.yml` 的 cron（UTC 时间，北京 = UTC+8）。
- 增删平台：编辑脚本 `SOURCES` / `PRODUCTS`，再往 `index.html` 的 `PLATFORMS` 加一行。
