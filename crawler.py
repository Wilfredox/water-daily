#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水利日报爬虫
数据源：Google News RSS（境外可访问，聚合真实中文水利新闻）

修复：
  1. 按发布日期过滤 — 只保留「昨天」的新闻
  2. 语义去重 — 抽取标题关键词，跨媒体合并同一事件
  3. 爬取原文正文 — 用于生成「可能的影响」字段（替换重复内容）
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
    """把各种格式日期统一为 '2026年04月05日'，失败返回 None"""
    if not s:
        return None
    s = s.strip()
    # RFC 2822: Mon, 05 Apr 2026 16:30:00 GMT
    m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', s)
    if m:
        months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,
                  'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        return f"{m.group(3)}年{months[m.group(2)]:02d}月{int(m.group(1)):02d}日"
    # ISO: 2026-04-05
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    # 中文：2026年4月5日
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
            print(f"    [attempt {attempt+1}/{retries}] {e}")
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
    """抓取文章正文，返回摘要文字"""
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
        # 去掉明显的噪声句子
        raw = re.sub(r'(责任编辑|编辑|来源|原标题|声明|版权)[：:].{0,30}', '', raw)
        return raw.strip()[:max_chars]
    except Exception:
        return ''

# ── Google News RSS ───────────────────────────────────────────────────────────
GOOGLE_NEWS_QUERIES = [
    ('水利部 防汛',        '防汛抗旱'),
    ('水利部 抗旱',        '防汛抗旱'),
    ('水利部 水资源', '水资源管理'),
    ('水利工程 水库', '水利工程'),
    ('河湖长制 水生态', '水生态环境'),
    ('水利部 政策 通知', '政策法规'),
    ('浙江 水利', '综合要闻'),
    ('水利部 新闻', '综合要闻'),
]

def google_news_rss_url(query):
    return (f"https://news.google.com/rss/search"
            f"?q={quote(query)}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")

def parse_google_rss(xml_content, hint_category):
    items = []
    try:
        soup = BeautifulSoup(xml_content, 'xml')
        for entry in soup.find_all('item')[:10]:
            title_tag = entry.find('title')
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # 拆出来源："新闻标题 - 来源网站"
            source_name = '综合媒体'
            if ' - ' in title:
                parts = title.rsplit(' - ', 1)
                title     = parts[0].strip()
                source_name = parts[1].strip()
            if len(title) < 8:
                continue

            link_tag = entry.find('link')
            url = link_tag.get_text(strip=True) if link_tag else ''
            if not url:
                continue

            pub_tag  = entry.find('pubDate')
            pub_date = pub_tag.get_text(strip=True) if pub_tag else ''
            date_str = parse_date_loose(pub_date)

            # description 含 HTML，剥离后当摘要
            desc_tag = entry.find('description')
            summary  = ''
            if desc_tag:
                raw = BeautifulSoup(desc_tag.get_text(), 'html.parser').get_text(strip=True)
                summary = re.sub(r'\s+', ' ', raw).strip()[:300]

            items.append({
                'title':    title,
                'url':      url,
                'pub_date': date_str,     # 已转为标准格式或 None
                'content':  summary,
                'source':   source_name,
                '_hint':    hint_category,
            })
    except Exception as e:
        print(f"    [RSS parse error] {e}")
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
        time.sleep(1.5)
    return all_items

# ── 新闻分类 ──────────────────────────────────────────────────────────────────
WATER_KWS = ['水利', '防汛', '抗旱', '水资源', '水库', '河湖', '水生态',
             '灌溉', '堤防', '水环境', '节水', '水质', '水污染', '供水',
             '调水', '泄洪', '汛情', '旱情', '水权', '大坝', '入汛', '蓄水']

CATEGORY_RULES = [
    ('防汛抗旱',   ['防汛', '抗旱', '洪水', '汛情', '汛期', '台风', '暴雨',
                    '抢险', '旱情', '泄洪', '应急响应', '备汛', '洪涝', '内涝', '入汛']),
    ('水利工程',   ['水库', '大坝', '堤防', '海塘', '渠道', '泵站', '闸',
                    '灌区', '工程建设', '竣工', '验收', '除险加固', '开工', '蓄水']),
    ('水资源管理', ['水资源', '节水', '供水', '取水许可', '地下水', '调水',
                    '引水', '水权', '用水总量', '水量分配', '缺水']),
    ('水生态环境', ['水生态', '水环境', '河湖', '河长制', '湖长', '湿地',
                    '水质', '水污染', '生态修复', '水土保持']),
    ('政策法规', ['印发', '出台', '条例', '规划', '办法', '意见',
                  '通知', '规范', '标准', '规定', '法规', '政策']),
    ('综合要闻',   []),
]

def classify(title, content=''):
    text = title + ' ' + content
    if not any(kw in text for kw in WATER_KWS):
        return None  # 非水利相关
    for category, kws in CATEGORY_RULES:
        if not kws:
            return category
        for kw in kws:
            if kw in text:
                return category
    return '综合要闻'

# ── 日期过滤 ──────────────────────────────────────────────────────────────────
def is_yesterday(date_str, yest_str):
    """
    判断一条新闻是否属于「昨天」。
    - date_str 为 None（日期缺失）→ 保留（宁可多要，不漏掉）
    - 匹配昨天 → True
    - 其他日期 → False
    """
    if date_str is None:
        return True   # 日期缺失时保留，不误杀
    return date_str == yest_str

# ── 语义去重 ──────────────────────────────────────────────────────────────────
# 思路：从标题中提取「核心实词」（去掉停用词），
#       如果两条新闻的核心词重叠度 > 阈值，视为同一事件，只保留第一条。

STOPWORDS = set('的了是在和与及或也但而因为所以将会已经通过对于针对关于为了'
                '我们他们其水利部省市县区年月日')

def title_keywords(title):
    """提取标题中长度≥2的实词"""
    # 简单按字切分，取2~4字的连续汉字片段
    words = re.findall(r'[\u4e00-\u9fa5]{2,4}', title)
    return set(w for w in words if not any(sw in w for sw in STOPWORDS))

def semantic_dedup(items):
    """跨媒体语义去重：同一事件只保留第一条（通常是最权威来源）"""
    kept = []
    kept_kws = []
    THRESHOLD = 0.45   # Jaccard 相似度阈值

    for it in items:
        kws = title_keywords(it['title'])
        if not kws:
            kept.append(it)
            kept_kws.append(kws)
            continue
        duplicate = False
        for existing_kws in kept_kws:
            if not existing_kws:
                continue
            intersection = len(kws & existing_kws)
            union        = len(kws | existing_kws)
            if union > 0 and intersection / union >= THRESHOLD:
                duplicate = True
                break
        if not duplicate:
            kept.append(it)
            kept_kws.append(kws)

    return kept

# ── 生成「可能的影响」 ────────────────────────────────────────────────────────
IMPACT_TEMPLATES = {
    '防汛抗旱':   '有助于提升防灾减灾能力，保障人民群众生命财产安全。',
    '水利工程':   '将有效提升区域水资源调配与防洪排涝能力。',
    '水资源管理': '有利于推进节水型社会建设，保障供水安全。',
    '水生态环境': '有助于改善水生态环境质量，维护河湖生态健康。',
    '政策法规':   '将进一步规范水利管理秩序，推动依法治水。',
    '综合要闻':   '对水利行业发展具有积极推动作用。',
}

def generate_impact(title, content, category):
    """
    根据正文内容生成「可能的影响」。
    优先从正文末段提取结论性句子；如果提取不到，用模板。
    """
    if content and len(content) > 60:
        # 取最后1~2句话（常含结论）
        sentences = re.split(r'[。！？；]', content)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]
        if sentences:
            last = sentences[-1]
            # 如果末句包含正向词，就用它
            POSITIVE_KWS = ['将', '有助', '提升', '保障', '推动', '促进',
                            '加强', '改善', '确保', '有效', '显著']
            if any(kw in last for kw in POSITIVE_KWS) and len(last) < 80:
                return last + '。' if not last.endswith('。') else last

    return IMPACT_TEMPLATES.get(category, IMPACT_TEMPLATES['综合要闻'])

# ── 主流程 ────────────────────────────────────────────────────────────────────
def run():
    now       = beijing_now()
    today_str = fmt_date(now)
    yest_str  = fmt_date(now - timedelta(days=1))
    upd_str   = now.strftime('%Y-%m-%d 00:00')

    print(f"\n{'='*55}")
    print(f"  水利日报爬虫  {today_str}")
    print(f"  只收录：{yest_str} 发布的新闻")
    print(f"{'='*55}")

    # ── 步骤1：抓取 ──────────────────────────────────────────────────────────
    all_raw = crawl_google_news()
    print(f"\n原始条目：{len(all_raw)}")

    # ── 步骤2：日期过滤（只保留昨天） ────────────────────────────────────────
    dated = [it for it in all_raw if is_yesterday(it.get('pub_date'), yest_str)]
    print(f"日期过滤后（{yest_str}）：{len(dated)} 条")

    # 如果过滤后太少（<5条），放宽到近2天（新闻发布时区差异）
    if len(dated) < 5:
        day_before = fmt_date(now - timedelta(days=2))
        dated = [it for it in all_raw
                 if it.get('pub_date') in (yest_str, day_before, None)]
        print(f"  → 放宽到近2天后：{len(dated)} 条")

    # ── 步骤3：水利关键词过滤 + 分类 ─────────────────────────────────────────
    water_items = []
    for it in dated:
        cat = classify(it['title'], it.get('content', ''))
        if cat is not None:
            it['_cat'] = cat
            water_items.append(it)
    print(f"水利相关：{len(water_items)} 条")

    # ── 步骤4：标题去重（精确） ───────────────────────────────────────────────
    seen_exact, exact_deduped = set(), []
    for it in water_items:
        key = re.sub(r'\s+', '', it['title'])[:22]
        if key not in seen_exact:
            seen_exact.add(key)
            exact_deduped.append(it)
    print(f"标题去重后：{len(exact_deduped)} 条")

    # ── 步骤5：语义去重（跨媒体同一事件） ───────────────────────────────────
    deduped = semantic_dedup(exact_deduped)
    print(f"语义去重后：{len(deduped)} 条（过滤了 {len(exact_deduped)-len(deduped)} 条重复事件）")

    # ── 步骤6：抓取正文 + 生成影响 ───────────────────────────────────────────
    print(f"\n抓取文章正文（最多 {min(len(deduped), 25)} 篇）…")
    cat_map = {}
    nid = 1
    for i, it in enumerate(deduped[:25]):
        print(f"  [{i+1:02d}] {it['title'][:32]}…", end=' ', flush=True)
        full_content = fetch_article_content(it['url'])
        print(f"{'✓ ' + str(len(full_content)) + '字' if full_content else '✗ 用摘要'}")

        # content：优先用抓到的正文，否则用 RSS 摘要，否则用标题
        content = full_content or it.get('content', '') or it['title']

        cat = it['_cat']
        impact = generate_impact(it['title'], full_content or it.get('content',''), cat)

        pd = it.get('pub_date') or yest_str
        cat_map.setdefault(cat, []).append({
            'id':        nid,
            'title':     it['title'],
            'source':    it['source'],
            'pub_date':  pd,
            'content':   content,
            'impact':    impact,        # ← 新增字段
            'full_link': it['url'],
        })
        nid += 1
        time.sleep(0.6)

    total = sum(len(v) for v in cat_map.values())
    print(f"\n最终：{total} 条，{len(cat_map)} 个分类")

    # ── 步骤7：构建今日数据 ───────────────────────────────────────────────────
    today_data = {
        'date':           today_str,
        'news_date':      yest_str,
        'update_time':    upd_str,
        'total_news':     total,
        'category_count': len(cat_map),
        'news':           cat_map,
    }

    # ── 步骤8：归档旧日报 ─────────────────────────────────────────────────────
    archive_path = 'archive-data.json'
    news_path    = 'news-data.json'

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

    # ── 步骤9：写文件 ─────────────────────────────────────────────────────────
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)

    if total == 0:
        print("⚠️  未抓到昨天的水利新闻，日期已更新")
    else:
        print(f"✅ 完成：{today_str}（{total} 条）")
    print(f"   往期归档：{len(archive)} 期")
    return True


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(0 if run() else 1)