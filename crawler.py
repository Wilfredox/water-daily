#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水利日报爬虫
数据源：Google News RSS
改进：
1. 扩充关键词覆盖更多水利细分领域（57 组关键词）
2. 每个版块上限 10 条；若某版块 <2 条则依次补充前天、更早新闻
3. 修复 content 重复问题：Google RSS description 格式为"标题+来源"，
   抓不到正文时改用空字符串（前端只显示 impact，不再重复标题）
4. 语义去重阈值优化至 0.55（减少误去重）
5. RSS 每查询取 20 条，标题最短 5 字
"""

import json, re, os, sys, time, random
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 时区 ──────────────────────────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))

def beijing_now():
    return datetime.now(CST)

def fmt_date(dt):
    return dt.strftime("%Y年%m月%d日")

def parse_date_loose(s):
    if not s:
        return None
    s = s.strip()
    # RFC 2822: Mon, 05 Apr 2026 16:30:00 GMT
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', s)
    if m:
        months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
                  'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        return f"{m.group(3)}年{months[m.group(2)]:02d}月{int(m.group(1)):02d}日"
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    m = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', s)
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    return None

# ── HTTP ──────────────────────────────────────────────────────────────────────
UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
]
SESSION = requests.Session()

def fetch(url, timeout=20, retries=3):
    headers = {
        'User-Agent': random.choice(UA_LIST),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
    }
    for attempt in range(retries):
        try:
            r = SESSION.get(url, headers=headers, timeout=timeout,
                            allow_redirects=True, verify=False)
            r.raise_for_status()
            if r.encoding in (None, 'ISO-8859-1', 'iso-8859-1'):
                r.encoding = r.apparent_encoding or 'utf-8'
            return r
        except Exception as e:
            print(f"  [attempt {attempt+1}/{retries}] {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None

# ── 正文提取 ──────────────────────────────────────────────────────────────────
CONTENT_SELECTORS = [
    '.TRS_Editor', '.article-content', '.art_content', '.articleContent',
    '#content', '.content', '.news-content', '.newsContent', '.detail-content',
    'article', '.main-text', '.article', '#article', '.text', 'main',
]

def fetch_article_content(url, max_chars=400):
    """抓取文章正文。失败返回空字符串（不用标题填充，避免重复）"""
    r = fetch(url, timeout=15, retries=2)
    if not r:
        return ''
    try:
        soup = BeautifulSoup(r.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'figure']):
            tag.decompose()
        el = None
        for sel in CONTENT_SELECTORS:
            el = soup.select_one(sel)
            if el:
                break
        if el:
            raw = el.get_text(separator=' ', strip=True)
        else:
            paras = [p.get_text(strip=True) for p in soup.find_all('p')
                     if len(p.get_text(strip=True)) > 25]
            raw = ' '.join(paras[:8])
        raw = re.sub(r'\s+', ' ', raw).strip()
        raw = re.sub(r'(责任编辑|编辑|来源|原标题|声明|版权)[：:].{0,30}', '', raw)
        raw = raw.strip()
        # 如果抓到的正文太短或疑似导航文字，放弃
        if len(raw) < 30:
            return ''
        return raw[:max_chars]
    except Exception:
        return ''

def clean_rss_description(desc_text, title):
    """
    Google RSS 的 description 通常格式为：
    "新闻标题来源网站" 或 "<a href=...>标题</a> <font>来源 · 时间</font>"
    提取后几乎就是标题重复，直接丢弃，返回空字符串。
    """
    if not desc_text:
        return ''
    # 去 HTML
    raw = BeautifulSoup(desc_text, 'html.parser').get_text(separator=' ', strip=True)
    raw = re.sub(r'\s+', ' ', raw).strip()
    # 如果去掉标题后剩余内容很少（<20字），视为无有效摘要
    cleaned = raw.replace(title, '').strip(' -·•·')
    if len(cleaned) < 20:
        return ''
    return cleaned[:280]

# ── Google News RSS ───────────────────────────────────────────────────────────
# 扩充关键词：覆盖防汛、水资源、工程建设、生态、政策、灌溉、农村水利等细分
GOOGLE_NEWS_QUERIES = [
    # ── 防汛抗旱 ──
    ('水利部 防汛', '防汛抗旱'),
    ('水利部 抗旱 旱情', '防汛抗旱'),
    ('防汛备汛 水库调度', '防汛抗旱'),
    ('洪涝 暴雨 水利', '防汛抗旱'),
    ('防汛 应急 抢险', '防汛抗旱'),
    ('台风 防汛 水利', '防汛抗旱'),
    ('山洪 泥石流 预警', '防汛抗旱'),
    ('泄洪 水库 汛期', '防汛抗旱'),
    ('暴雨 内涝 排水', '防汛抗旱'),
    ('水利 防灾 减灾', '防汛抗旱'),
    # ── 水利工程 ──
    ('水利工程 开工 竣工', '水利工程'),
    ('水库 大坝 除险加固', '水利工程'),
    ('堤防 海塘 水闸 建设', '水利工程'),
    ('灌区 泵站 水利设施', '水利工程'),
    ('水利 投资 建设 项目', '水利工程'),
    ('重大水利工程 开工', '水利工程'),
    ('水库 蓄水 建设', '水利工程'),
    ('水利 基建 工程', '水利工程'),
    ('大坝 安全 鉴定', '水利工程'),
    ('水利 施工 招标', '水利工程'),
    # ── 水资源管理 ──
    ('水资源 节水 供水', '水资源管理'),
    ('地下水 取水许可 水权', '水资源管理'),
    ('南水北调 调水 引水', '水资源管理'),
    ('农村饮水 饮水安全', '水资源管理'),
    ('节水 型社会 水利', '水资源管理'),
    ('供水 水厂 水利', '水资源管理'),
    ('水资源 管理 配置', '水资源管理'),
    ('跨流域 调水 工程', '水资源管理'),
    ('用水 总量 控制', '水资源管理'),
    ('城乡 供水 一体化', '水资源管理'),
    # ── 水生态环境 ──
    ('河湖长制 水生态', '水生态环境'),
    ('水环境 水质 水污染治理', '水生态环境'),
    ('湿地 水土保持 生态修复', '水生态环境'),
    ('河长制 湖长制 巡河', '水生态环境'),
    ('黑臭水体 治理 水利', '水生态环境'),
    ('生态流量 河湖 水利', '水生态环境'),
    ('水土流失 防治 水利', '水生态环境'),
    ('水质 改善 水环境', '水生态环境'),
    ('河湖 清四乱 整治', '水生态环境'),
    ('水污染 防治 水利', '水生态环境'),
    # ── 政策法规 ──
    ('水利部 印发 通知 政策', '政策法规'),
    ('水法 水利规划 水利改革', '政策法规'),
    ('水利 法规 条例', '政策法规'),
    ('水利 标准 规范 发布', '政策法规'),
    ('水利 改革 发展 意见', '政策法规'),
    ('水利 十四五 规划', '政策法规'),
    ('河长制 条例 办法', '政策法规'),
    # ── 综合要闻 ──
    ('水利部 新闻发布', '综合要闻'),
    ('浙江 水利 新闻', '综合要闻'),
    ('中国水利 行业动态', '综合要闻'),
    ('水利 新闻 最新', '综合要闻'),
    ('水利部 部署 工作', '综合要闻'),
    ('水利 高质量 发展', '综合要闻'),
    ('水利 数字化 智慧', '综合要闻'),
    ('水利 乡村振兴 助力', '综合要闻'),
    ('智慧水利 数字孪生', '综合要闻'),
    ('水电 清洁能源 水利', '综合要闻'),
    ('水利 科技 创新', '综合要闻'),
    ('河湖 管理 保护 水利', '综合要闻'),
    ('水利 监督 检查', '综合要闻'),
    ('水利 行政 执法', '综合要闻'),
]

def google_news_rss_url(query):
    return (f"https://news.google.com/rss/search"
            f"?q={quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")

def parse_google_rss(xml_content, hint_category):
    items = []
    try:
        soup = BeautifulSoup(xml_content, 'xml')
        for entry in soup.find_all('item')[:20]:
            title_tag = entry.find('title')
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # 拆出来源："新闻标题 - 来源网站"
            source_name = '综合媒体'
            if ' - ' in title:
                parts = title.rsplit(' - ', 1)
                title = parts[0].strip()
                source_name = parts[1].strip()
            if len(title) < 5:
                continue

            link_tag = entry.find('link')
            url = link_tag.get_text(strip=True) if link_tag else ''
            if not url:
                continue

            pub_tag = entry.find('pubDate')
            pub_date = pub_tag.get_text(strip=True) if pub_tag else ''
            date_str = parse_date_loose(pub_date)

            # description 通常只是标题重复，清洗后大概率为空
            desc_tag = entry.find('description')
            summary = clean_rss_description(
                desc_tag.get_text() if desc_tag else '', title)

            items.append({
                'title': title,
                'url': url,
                'pub_date': date_str,
                'content': summary,  # 可能为空字符串
                'source': source_name,
                '_hint': hint_category,
            })
    except Exception as e:
        print(f"  [RSS parse error] {e}")
    return items


def crawl_google_news():
    print("\n── Google News RSS ─────────────────────────────")
    all_items = []
    for query, category in GOOGLE_NEWS_QUERIES:
        print(f"  ▷ 「{query}」…", end=' ', flush=True)
        r = fetch(google_news_rss_url(query))
        if not r:
            print("✗")
            time.sleep(1)
            continue
        items = parse_google_rss(r.content, category)
        print(f"✓ {len(items)} 条")
        all_items.extend(items)
        time.sleep(1.2)
    return all_items

# ── 新闻分类 ──────────────────────────────────────────────────────────────────
WATER_KWS = [
    '水利', '防汛', '抗旱', '水资源', '水库', '河湖', '水生态', '灌溉',
    '堤防', '水环境', '节水', '水质', '水污染', '供水', '调水', '泄洪',
    '汛情', '旱情', '水权', '大坝', '入汛', '蓄水', '引水', '地下水',
    '水闸', '泵站', '灌区', '海塘', '湿地', '水土保持', '饮水安全',
    '南水北调', '河长制', '湖长', '水法', '水务',
]

CATEGORY_RULES = [
    ('防汛抗旱', [
        '防汛', '抗旱', '洪水', '汛情', '汛期', '台风', '暴雨',
        '抢险', '旱情', '泄洪', '应急响应', '备汛', '洪涝', '内涝', '入汛',
        '山洪', '泥石流', '超警', '洪峰',
    ]),
    ('水利工程', [
        '水库', '大坝', '堤防', '海塘', '渠道', '泵站', '水闸', '闸门',
        '灌区', '工程建设', '竣工', '验收', '除险加固', '开工', '蓄水',
        '水利设施', '水利项目', '水利投资',
    ]),
    ('水资源管理', [
        '水资源', '节水', '供水', '取水许可', '地下水', '调水',
        '引水', '水权', '用水总量', '水量分配', '缺水', '饮水安全',
        '农村饮水', '南水北调', '跨流域',
    ]),
    ('水生态环境', [
        '水生态', '水环境', '河湖', '河长制', '湖长', '湿地',
        '水质', '水污染', '生态修复', '水土保持', '水土流失', '生态流量',
    ]),
    ('政策法规', [
        '印发', '出台', '条例', '规划', '办法', '意见',
        '通知', '规范', '标准', '规定', '法规', '政策', '水法', '改革',
    ]),
    ('综合要闻', []),
]

def classify(title, content=''):
    text = title + ' ' + content
    if not any(kw in text for kw in WATER_KWS):
        return None
    for category, kws in CATEGORY_RULES:
        if not kws:
            return category
        for kw in kws:
            if kw in text:
                return category
    return '综合要闻'

# ── 日期过滤 ──────────────────────────────────────────────────────────────────
def date_in_range(date_str, allowed_dates):
    """date_str 在 allowed_dates 集合中，或为 None（日期缺失保留）"""
    if date_str is None:
        return True
    return date_str in allowed_dates

# ── 语义去重 ──────────────────────────────────────────────────────────────────
STOPWORDS = set(
    '的了是在和与及或也但而因为所以将会已经通过对于针对关于为了'
    '我们他们其水利部省市县区年月日'
)

def title_keywords(title):
    words = re.findall(r'[\u4e00-\u9fa5]{2,5}', title)
    return set(w for w in words if not any(sw in w for sw in STOPWORDS))

def semantic_dedup(items, threshold=0.55):
    kept, kept_kws = [], []
    for it in items:
        kws = title_keywords(it['title'])
        duplicate = False
        for existing_kws in kept_kws:
            if not existing_kws or not kws:
                continue
            inter = len(kws & existing_kws)
            union = len(kws | existing_kws)
            if union > 0 and inter / union >= threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(it)
            kept_kws.append(kws)
    return kept

# ── 生成「可能的影响」 ────────────────────────────────────────────────────────
IMPACT_TEMPLATES = {
    '防汛抗旱': '有助于提升防灾减灾能力，保障人民群众生命财产安全。',
    '水利工程': '将有效提升区域水资源调配与防洪排涝能力。',
    '水资源管理': '有利于推进节水型社会建设，保障供水安全。',
    '水生态环境': '有助于改善水生态环境质量，维护河湖生态健康。',
    '政策法规': '将进一步规范水利管理秩序，推动依法治水。',
    '综合要闻': '对水利行业发展具有积极推动作用。',
}

POSITIVE_KWS = ['将', '有助', '提升', '保障', '推动', '促进',
                '加强', '改善', '确保', '有效', '显著', '惠及']

def generate_impact(content, category):
    if content and len(content) > 60:
        sentences = re.split(r'[。！？；]', content)
        sentences = [s.strip() for s in sentences if 15 < len(s.strip()) < 80]
        for s in reversed(sentences):
            if any(kw in s for kw in POSITIVE_KWS):
                return s + ('。' if not s.endswith('。') else '')
    return IMPACT_TEMPLATES.get(category, IMPACT_TEMPLATES['综合要闻'])

# ── 主流程 ────────────────────────────────────────────────────────────────────
CAT_MAX = 10  # 每个版块最多条数
CAT_MIN = 2   # 低于此数则补充前天新闻

def run():
    now = beijing_now()
    today_str = fmt_date(now)
    yest_str = fmt_date(now - timedelta(days=1))
    before_str = fmt_date(now - timedelta(days=2))
    upd_str = now.strftime('%Y-%m-%d 00:00')

    print(f"\n{'='*55}")
    print(f"  水利日报爬虫 {today_str}")
    print(f"  目标日期：{yest_str}（不足时补充 {before_str}）")
    print(f"{'='*55}")

    # 步骤1：抓取所有关键词
    all_raw = crawl_google_news()
    print(f"\n原始条目：{len(all_raw)}")

    # 步骤2：精确标题去重
    seen_exact, deduped_exact = set(), []
    for it in all_raw:
        key = re.sub(r'\s+', '', it['title'])[:24]
        if key not in seen_exact:
            seen_exact.add(key)
            deduped_exact.append(it)
    print(f"标题去重：{len(deduped_exact)}")

    # 步骤3：语义去重
    deduped = semantic_dedup(deduped_exact)
    print(f"语义去重：{len(deduped)}（过滤 {len(deduped_exact)-len(deduped)} 条重复事件）")

    # 步骤4：水利过滤 + 分类
    classified = {}  # cat -> [items from yest, items from before, items from older]
    for it in deduped:
        cat = classify(it['title'], it.get('content', ''))
        if cat is None:
            continue
        it['_cat'] = cat
        classified.setdefault(cat, {'yest': [], 'before': [], 'older': []})
        pd = it.get('pub_date')
        if pd == yest_str or pd is None:
            classified[cat]['yest'].append(it)
        elif pd == before_str:
            classified[cat]['before'].append(it)
        else:
            # 更早日期的新闻也保留作为补充池
            classified[cat]['older'].append(it)

    # 步骤5：按版块决定最终新闻列表（优先昨天，不足时补前天→更早，上限10条）
    final_per_cat = {}
    for cat, buckets in classified.items():
        selected = buckets['yest'][:CAT_MAX]
        if len(selected) < CAT_MIN:
            need = CAT_MIN - len(selected)
            # 先补前天
            selected = selected + buckets['before'][:need]
            still_need = CAT_MIN - len(selected)
            # 再补更早
            if still_need > 0:
                selected = selected + buckets['older'][:still_need]
            if len(buckets['yest']) < CAT_MIN:
                yest_cnt = len(buckets['yest'])
                before_cnt = min(len(buckets['before']), max(0, need))
                older_cnt = min(len(buckets['older']), max(0, still_need))
                print(f"  [{cat}] 昨天仅 {yest_cnt} 条，补充前天 {before_cnt} 条、更早 {older_cnt} 条")
        final_per_cat[cat] = selected

    # 所有需要抓正文的条目
    all_to_fetch = [it for items in final_per_cat.values() for it in items]
    print(f"\n共 {len(all_to_fetch)} 条新闻，抓取正文…")

    # 步骤6：抓取正文 + 构建输出
    cat_map = {}
    nid = 1
    fetched_urls = {}  # url -> content，避免重复抓取同URL

    for cat, items in final_per_cat.items():
        if not items:
            continue
        cat_map[cat] = []
        for it in items:
            url = it['url']
            print(f"  [{nid:02d}] {it['title'][:32]}…", end=' ', flush=True)
            if url not in fetched_urls:
                fetched_urls[url] = fetch_article_content(url)
            full_content = fetched_urls[url]
            print(f"{'✓ ' + str(len(full_content)) + '字' if full_content else '✗'}")

            # content：优先正文，否则留空（不重复标题）
            content = full_content or ''

            pd = it.get('pub_date') or yest_str
            impact = generate_impact(full_content, cat)

            cat_map[cat].append({
                'id': nid,
                'title': it['title'],
                'source': it['source'],
                'pub_date': pd,
                'content': content,
                'impact': impact,
                'full_link': url,
            })
            nid += 1
            time.sleep(0.5)

    total = sum(len(v) for v in cat_map.values())
    print(f"\n最终：{total} 条，{len(cat_map)} 个分类")
    for cat, items in cat_map.items():
        print(f"  {cat}: {len(items)} 条")

    # 步骤7：构建今日数据
    today_data = {
        'date': today_str,
        'news_date': yest_str,
        'update_time': upd_str,
        'total_news': total,
        'category_count': len(cat_map),
        'news': cat_map,
    }

    # 步骤8：归档旧日报
    archive_path = 'archive-data.json'
    news_path = 'news-data.json'

    archive = []
    if os.path.exists(archive_path):
        try:
            with open(archive_path, encoding='utf-8') as f:
                raw = json.load(f)
            archive = raw if isinstance(raw, list) else []
        except Exception:
            archive = []

    if os.path.exists(news_path):
        try:
            with open(news_path, encoding='utf-8') as f:
                old = json.load(f)
            old_date = old.get('date', '')
            if old_date and old_date != today_str and old.get('total_news', 0) > 0:
                existing = {item.get('date') for item in archive}
                if old_date not in existing:
                    archive.insert(0, old)
                    print(f"✦ 归档 {old_date}（{old.get('total_news',0)} 条）")
        except Exception as e:
            print(f"  [WARN] 读旧日报失败: {e}")

    # 步骤9：写文件
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)

    if total == 0:
        print("⚠️ 未抓到新闻，日期已更新")
    else:
        print(f"✅ 完成：{today_str}（{total} 条）")
        print(f"  往期归档：{len(archive)} 期")
    return True


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(0 if run() else 1)