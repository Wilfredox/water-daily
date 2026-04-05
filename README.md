# 水利日报

每日自动更新的水利行业资讯网站，托管于 GitHub Pages。

---

## ⚠️ 上传后必须完成的设置（否则 Actions 会报错）

### 第一步：Settings → Pages → 选 GitHub Actions

1. 进入你的仓库页面
2. 点击顶部 **Settings**（设置）
3. 左侧菜单找到 **Pages**
4. **Source（来源）** 下拉框选择 **`GitHub Actions`**
   - ❌ 不要选 "Deploy from a branch"
5. 点击 Save

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

## 自动更新逻辑

每天 **北京时间 00:00** 自动执行：

1. 爬取水利部、中国水利网、浙江省水利厅等官方网站的最新新闻（RSS 优先）
2. 将昨天的 `news-data.json` 归档到 `archive-data.json`
3. 生成新的 `news-data.json`（期号 = 今天，内容 = 昨天新闻）
4. 推送数据到仓库，触发 Pages 重新部署
5. 网站自动更新（约 1 分钟内生效）

> 若爬虫抓取失败（如官方网站临时维护），仍会更新日期，不影响 Pages 部署。

---

## 文件结构

```
├── index.html                          # 今日日报
├── archive.html                        # 往期日报
├── crawler.py                          # 爬虫（RSS + HTML 双路）
├── news-data.json                      # 今日数据（每天覆盖）
├── archive-data.json                   # 往期归档（累积）
├── css/style.css                       # 样式（不改动）
├── js/app.js                           # 今日日报前端逻辑
├── js/archive.js                       # 往期日报前端逻辑
├── requirements.txt                    # Python 依赖
└── .github/workflows/daily-update.yml # GitHub Actions 定时任务
```
