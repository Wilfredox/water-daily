# 💧 水利日报

> 每日自动更新的水利行业资讯网站，数据来源于 Google News RSS，托管于 GitHub Pages。

[![每日更新](https://github.com/Wilfredox/water-daily/actions/workflows/daily-update.yml/badge.svg)](https://github.com/Wilfredox/water-daily/actions/workflows/daily-update.yml)
[![GitHub Pages](https://img.shields.io/badge/GitHub-Pages-brightgreen)](https://wilfredox.github.io/water-daily/)

---

## ✨ 项目简介

水利日报是一个全自动的水利行业新闻聚合网站，无需服务器、无需数据库，仅依赖 GitHub Actions + GitHub Pages 即可实现每日自动更新。爬虫每天北京时间 00:00 自动从 Google News RSS 抓取水利相关新闻，经分类、去重、影响分析后生成日报页面，并在校验通过后才覆盖线上数据。

### 核心特性

- 🤖 **全自动运行** — GitHub Actions 定时触发，零维护成本
- 📰 **多维度覆盖** — 覆盖防汛抗旱、水利工程、水资源管理、水生态环境、政策法规、综合要闻 6 大版块
- 🧠 **智能处理** — 语义去重、关键词分类、影响分析自动生成
- 📂 **自动归档** — 历史日报按年月树形归档，支持按日期回溯查看
- 📱 **响应式设计** — 适配桌面端与移动端
- ⚡ **纯静态部署** — 无后端依赖，GitHub Pages 即可托管

---

## 🌐 在线访问

👉 **[https://wilfredox.github.io/water-daily/](https://wilfredox.github.io/water-daily/)**

| 页面 | 说明 |
|------|------|
| `index.html` | 今日水利日报（页面内容由 `news-data.json` 动态渲染） |
| `archive.html` | 往期日报归档（年月树形浏览 + 日期详情） |

---

## ⚙️ 自动更新逻辑

每天 **北京时间 00:00** 由 GitHub Actions 自动执行以下流程：

1. **抓取新闻** — 通过多组关键词从 Google News RSS 获取水利相关资讯
2. **智能去重** — 先精确标题去重，再语义去重（Jaccard 相似度 ≥ 0.42 判定为重复）
3. **水利过滤** — 仅保留包含水利相关关键词的新闻，过滤无关内容
4. **自动分类** — 根据关键词匹配归入 6 大版块（每版块上限 6 条，不足 2 条时补充前天新闻）
5. **正文提取** — 尝试抓取原文正文（失败则留空，避免与标题重复）
6. **影响分析** — 从正文提取含正面关键词的语句，或按分类生成模板影响评述
7. **归档旧数据** — 将昨天的 `news-data.json` 归档到 `archive-data.json`
8. **校验提交** — 仅在 `news-data.json` / `archive-data.json` 校验通过后提交数据文件
9. **推送部署** — 提交数据文件，触发 GitHub Pages 重新部署（约 1 分钟生效）

> ⚠️ 若爬虫抓取失败或生成结果异常，工作流会停止并保留上一版可用站点。

---

## 📁 文件结构

```
water-daily/
├── index.html            # 今日日报页面（静态骨架）
├── archive.html          # 往期日报页面（静态骨架）
├── crawler.py            # Python 爬虫（Google News RSS 抓取 + 智能处理）
├── news-data.json        # 今日新闻数据（每天覆盖更新）
├── archive-data.json     # 往期归档数据（逐日累积）
├── 魄罗.jpg              # 网站 Logo 图片
├── requirements.txt      # Python 依赖清单
├── css/
│   └── style.css         # 全站样式（含分类配色、响应式、树形归档等）
├── js/
│   ├── app.js            # 今日日报前端逻辑（加载 + 渲染新闻卡片）
│   └── archive.js        # 往期日报前端逻辑（年月树形列表 + 日期详情）
└── .github/
    └── workflows/
        └── daily-update.yml  # GitHub Actions 定时任务配置
```

---

## 🛠️ 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | 原生 HTML / CSS / JavaScript（零框架依赖） |
| 爬虫 | Python 3 + `requests` + `beautifulsoup4` + `lxml` |
| 数据存储 | JSON 文件（无数据库） |
| 自动化 | GitHub Actions（cron 定时触发） |
| 部署 | GitHub Pages（纯静态托管） |

---

## 🚀 本地开发

### 前置条件

- Python 3.8+
- Git

### 启动步骤

```bash
# 1. 克隆仓库
git clone https://github.com/Wilfredox/water-daily.git
cd water-daily

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 手动运行爬虫（生成/更新 news-data.json）
python crawler.py

# 4. 本地预览（任选一种方式）
#    方式一：Python 内置 HTTP 服务器
python -m http.server 8080
#    方式二：VS Code Live Server 插件
#    方式三：npx serve
npx serve .
```

访问 `http://localhost:8080` 即可预览。

---

## ⚠️ Fork 后必读：配置 GitHub Actions

如果你 Fork 了本仓库，需要完成以下设置，否则 Actions 会报错：

### 第一步：Settings → Pages → 选 GitHub Actions

1. 进入你的仓库页面
2. 点击顶部 **Settings**（设置）
3. 左侧菜单找到 **Pages**
4. **Source（来源）** 下拉框选择 **`GitHub Actions`**
   - ❌ 不要选 "Deploy from a branch"
5. 点击 **Save**

### 第二步：Settings → Actions → 开放写权限

1. 还在 Settings 页面
2. 左侧菜单找到 **Actions** → **General**
3. 滚动到页面底部 **Workflow permissions**
4. 选择 **`Read and write permissions`**（读写权限）
5. 勾选下方的 **`Allow GitHub Actions to create and approve pull requests`**
6. 点击 **Save**

### 第三步：手动触发一次测试

1. 点击仓库顶部 **Actions** 标签
2. 左侧找到 **每日水利日报更新**
3. 点击右侧 **Run workflow** → **Run workflow**（绿色按钮）
4. 等待约 1 分钟，刷新看到绿色 ✅ 即成功

---

## 📰 新闻分类说明

| 版块 | 关键词示例 | 影响评述方向 |
|------|-----------|-------------|
| 🌊 防汛抗旱 | 防汛、抗旱、洪水、汛期、台风、暴雨 | 防灾减灾、生命财产安全 |
| 🏗️ 水利工程 | 水库、大坝、堤防、除险加固、竣工 | 水资源调配、防洪排涝 |
| 💧 水资源管理 | 节水、供水、地下水、南水北调、饮水安全 | 节水型社会、供水安全 |
| 🌿 水生态环境 | 河湖长制、水生态、水质、水土保持、湿地 | 水生态环境质量、河湖健康 |
| 📜 政策法规 | 印发、条例、规划、通知、水法、改革 | 依法治水、管理秩序 |
| 📋 综合要闻 | 水利部动态、地方水利新闻 | 行业发展推动 |

---

## 📄 License

本项目仅供水利专业学习参考使用，数据来源于公开新闻渠道。转载请注明出处。
