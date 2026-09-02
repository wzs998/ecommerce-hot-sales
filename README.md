# 电商每日热销产品汇总（免费方案）

一个零成本的「每日热销榜」网页：GitHub Actions 每天自动抓取公开榜单 →
生成 JSON → 静态页面读取渲染 → GitHub Pages 免费托管。无需服务器、无需数据库、无需付费 API。

## 项目结构

```
ecommerce-hot-sales/
├── index.html                  # 前端展示页（Tailwind CDN + 原生 JS）
├── scripts/
│   ├── fetch_hot.py            # 核心抓取脚本（真实源 + 失败自动回退模拟数据）
│   └── mock_data.py            # 模拟数据生成器（离线 Demo / 回退用）
├── data/
│   ├── latest.json             # 前端读取的最新数据（每次运行自动更新）
│   └── hot_YYYY-MM-DD.json     # 按日期存档
├── .github/workflows/
│   ├── daily-fetch.yml         # 每天北京时间 06:00 自动抓取
│   └── pages-deploy.yml        # push 到 main 时部署 GitHub Pages
├── requirements.txt
└── README.md
```

## 本地跑通 Demo（30 秒）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 生成数据（方式A：纯模拟数据，稳定可复现）
python3 scripts/mock_data.py

#    或方式B：抓真实源（什么值得买实测可用，其余平台失败自动回退模拟）
python3 scripts/fetch_hot.py

# 3. 打开页面（直接双击 index.html 或本地起个服务）
python3 -m http.server 8000
# 浏览器访问 http://localhost:8000
```

> 前端通过 `fetch('data/latest.json')` 读取数据，所以**不要用 file:// 直接打开**
> （浏览器会拦截本地 fetch），请用上面的 http.server 方式。

## 部署到 GitHub Pages（免费）

1. 把本目录推到一个新的 GitHub 仓库（分支名 `main`）。
2. 仓库 Settings → Pages → Source 选择 **GitHub Actions**。
3. 推送后 `pages-deploy.yml` 会自动把页面部署到
   `https://<你的用户名>.github.io/<仓库名>/`。
4. `daily-fetch.yml` 每天北京时间 06:00 自动抓取并提交最新 JSON，
   push 到 main 会再次触发部署，实现全自动更新。

手动触发抓取：Actions → 每日热销数据抓取 → Run workflow。

## 数据源说明与合规提醒

| 平台 | 状态 | 说明 |
|------|------|------|
| 什么值得买 | ✅ 可抓 | 公开榜单页，脚本内已写好解析器 |
| 京东 | ⚠️ 尽力而为 | 榜单为 JS 渲染，纯 requests 通常抓不到，自动回退模拟数据；可改 Playwright 无头浏览器 |
| 淘宝 / 拼多多 | 🚫 默认关闭 | 需登录态、风控严格，不在免费范围内 |

- 遵守 robots 协议，每天只抓 1 次，脚本带 UA、超时、重试与 1s 限速。
- **仅供个人学习 / 内部使用**；若用于商业用途，请自行评估采集合规风险。
- 平台页面结构随时可能改版，解析器需不定期维护（主要在 `scripts/fetch_hot.py` 的解析函数里）。

## 自定义

- 调整榜单规模：改 `fetch_hot.py` 里的 `MAX_PER_PLATFORM`。
- 增删平台：编辑 `SOURCES` 字典和对应解析函数，再往 `index.html` 的 `PLATFORMS` 加一行。
- 修改抓取时间：改 `daily-fetch.yml` 的 cron（UTC 时间，北京 = UTC+8）。
- 换图片源：真实商品图替换 `image` 字段即可（模拟图用 picsum.photos 占位）。
