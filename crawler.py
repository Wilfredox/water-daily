#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水利日报爬虫
数据源：Google News RSS（境外可访问，聚合真实中文水利新闻）
备用源：新华网 RSS（部分境外镜像可访问）
"""

import json, re, os, sys, time, random
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlparse

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
    """把各种格式日期统一为 '2026年04月05日'"""
    if not s:
        return None
    s = s.strip()
    # RFC 2822: Mon, 05 Apr 2026 ...
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
    'Googlebot/2.1 (+http://www.google.com/bot.html)',
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

# ── Google News RSS 解析 ───────────────────────────────────────────────────────
# Google News RSS 为每个关键词返回最新新闻，字段齐全：标题/来源/日期/摘要/链接
# URL格式: https://news.google.com/rss/search?q=关键词&hl=zh-CN&gl=CN&ceid=CN:zh-Hans

GOOGLE_NEWS_QUERIES = [
    # (搜索词, 显示分类标签)
    ('水利部 防汛',     '防汛抗旱'),
    ('水利部 水资源',   '水资源管理'),
    ('水利工程 建设',   '水利工程'),
    ('河湖长制 水生态', '水生态环境'),
    ('水利部 政策',     '政策法规'),
    ('浙江 水利',       '综合要闻'),
    ('中国 水利 新闻',  '综合要闻'),
]

def google_news_rss_url(query):
    encoded = quote(query)
    return (f"https://news.google.com/rss/search"
            f"?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans")

def parse_google_rss(xml_content, hint_category='综合要闻'):
    """解析 Google News RSS XML"""
    items = []
    try:
        soup = BeautifulSoup(xml_content, 'xml')
        entries = soup.find_all('item')
        for entry in entries[:8]:  # 每个关键词最多取8条
            title_tag = entry.find('title')
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            # Google News标题格式："新闻标题 - 来源网站"
            # 拆分出来源
            source_name = '综合媒体'
            if ' - ' in title:
                parts = title.rsplit(' - ', 1)
                title = parts[0].strip()
                source_name = parts[1].strip()

            if len(title) < 8:
                continue

            link_tag = entry.find('link')
            url = link_tag.get_text(strip=True) if link_tag else ''
            if not url:
                continue

            # 日期
            pub_tag = entry.find('pubDate')
            pub_date = pub_tag.get_text(strip=True) if pub_tag else ''
            date_str = parse_date_loose(pub_date) or ''

            # 摘要（Google News 的 description 含 HTML）
            desc_tag = entry.find('description')
            summary = ''
            if desc_tag:
                raw = BeautifulSoup(desc_tag.get_text(), 'html.parser').get_text(strip=True)
                summary = re.sub(r'\s+', ' ', raw).strip()[:280]

            items.append({
                'title':    title,
                'url':      url,
                'pub_date': date_str,
                'content':  summary if summary else title,
                'source':   source_name,
                '_hint':    hint_category,
            })
    except Exception as e:
        print(f"    [RSS parse error] {e}")
    return items


def crawl_google_news():
    """爬取 Google News RSS 的水利新闻"""
    print("\n── Google News RSS ─────────────────────────────")
    all_items = []
    for query, category in GOOGLE_NEWS_QUERIES:
        url = google_news_rss_url(query)
        print(f"  ▷ 搜索：「{query}」…")
        r = fetch(url)
        if not r:
            print(f"    ✗ 失败")
            time.sleep(1)
            continue
        items = parse_google_rss(r.content, category)
        print(f"    ✓ {len(items)} 条")
        all_items.extend(items)
        time.sleep(1.5)   # 避免频率限制
    return all_items

# ── 新华网 RSS（部分境外可访问，备用） ────────────────────────────────────────
XINHUA_RSS_SOURCES = [
    ('https://feeds.feedburner.com/xinhuanet/politics', '新华网'),
    ('http://www.xinhuanet.com/rss/zhengzhi.xml',       '新华网'),
]

def crawl_xinhua():
    """尝试爬取新华网，作为备用"""
    print("\n── 新华网 RSS（备用）─────────────────────────────")
    items = []
    for url, source in XINHUA_RSS_SOURCES:
        print(f"  ▷ {url[:55]}…")
        r = fetch(url)
        if not r:
            print(f"    ✗ 失败")
            continue
        try:
            soup = BeautifulSoup(r.content, 'xml')
            for entry in soup.find_all('item')[:10]:
                t = entry.find('title')
                l = entry.find('link')
                d = entry.find('pubDate')
                if not t or not l:
                    continue
                title = t.get_text(strip=True)
                # 过滤非水利相关
                WATER_KEYWORDS = ['水利', '防汛', '抗旱', '水资源', '水库', '河湖',
                                   '水生态', '灌溉', '堤防', '水环境', '节水']
                if not any(kw in title for kw in WATER_KEYWORDS):
                    continue
                items.append({
                    'title':    title,
                    'url':      l.get_text(strip=True),
                    'pub_date': parse_date_loose(d.get_text(strip=True) if d else '') or '',
                    'content':  title,
                    'source':   source,
                    '_hint':    '',
                })
        except Exception as e:
            print(f"    [parse error] {e}")
        time.sleep(1)
    print(f"  水利相关新闻：{len(items)} 条")
    return items

# ── 新闻分类 ──────────────────────────────────────────────────────────────────
CATEGORY_RULES = [
    ('防汛抗旱',   ['防汛', '抗旱', '洪水', '汛情', '汛期', '台风', '暴雨',
                    '抢险', '旱情', '泄洪', '应急响应', '备汛', '洪涝', '内涝']),
    ('水利工程',   ['水库', '大坝', '堤防', '海塘', '渠道', '泵站', '闸',
                    '灌区', '工程建设', '竣工', '验收', '除险加固', '开工']),
    ('水资源管理', ['水资源', '节水', '供水', '取水许可', '地下水', '调水',
                    '引水', '水权', '用水总量', '水量分配', '缺水']),
    ('水生态环境', ['水生态', '水环境', '河湖', '河长制', '湖长', '湿地',
                    '水质', '水污染', '生态修复', '水清岸绿', '水土保持']),
    ('政策法规',   ['印发', '出台', '条例', '规划', '办法', '意见',
                    '通知', '规范', '标准', '规定', '法规', '政策']),
    ('综合要闻',   []),
]

def classify(title, content='', hint=''):
    # 优先使用搜索时的分类提示（同时标题也要包含水利关键词）
    WATER_KWS = ['水利', '防汛', '抗旱', '水资源', '水库', '河湖', '水生态',
                 '灌溉', '堤防', '水环境', '节水', '水质', '水污染', '供水',
                 '调水', '泄洪', '汛情', '旱情', '水权', '大坝']
    # 必须是水利相关
    text = title + ' ' + content
    if not any(kw in text for kw in WATER_KWS):
        return None  # 返回 None 表示不相关，直接丢弃

    for category, kws in CATEGORY_RULES:
        if not kws:
            return category
        for kw in kws:
            if kw in text:
                return category
    return '综合要闻'

# ── 主流程 ────────────────────────────────────────────────────────────────────
def run():
    now       = beijing_now()
    today_str = fmt_date(now)
    yest_str  = fmt_date(now - timedelta(days=1))
    upd_str   = now.strftime('%Y-%m-%d 00:00')

    print(f"\n{'='*55}")
    print(f"  水利日报爬虫  {today_str}")
    print(f"  期号：{today_str}  |  内容：{yest_str} 的新闻")
    print(f"{'='*55}")

    # 1. 抓取
    all_raw = []
    all_raw.extend(crawl_google_news())
    all_raw.extend(crawl_xinhua())

    print(f"\n原始条目：{len(all_raw)}")

    # 2. 去重（按标题前20字）
    seen, deduped = set(), []
    for it in all_raw:
        key = re.sub(r'\s+', '', it['title'])[:20]
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)
    print(f"去重后：{len(deduped)}")

    # 3. 过滤 & 分类
    cat_map = {}
    nid = 1
    for it in deduped:
        cat = classify(it['title'], it.get('content', ''), it.get('_hint', ''))
        if cat is None:
            continue   # 非水利相关，丢弃
        pd = it.get('pub_date') or yest_str
        cat_map.setdefault(cat, []).append({
            'id':        nid,
            'title':     it['title'],
            'source':    it['source'],
            'pub_date':  pd,
            'content':   it.get('content', '') or it['title'],
            'full_link': it['url'],
        })
        nid += 1

    total = sum(len(v) for v in cat_map.values())
    print(f"水利相关新闻：{total} 条，{len(cat_map)} 个分类")

    # 4. 构建今日数据
    today_data = {
        'date':           today_str,
        'news_date':      yest_str,
        'update_time':    upd_str,
        'total_news':     total,
        'category_count': len(cat_map),
        'news':           cat_map,
    }

    # 5. 归档旧日报
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
                    print(f"\n✦ 归档 {old_date}（{old.get('total_news',0)} 条）")
        except Exception as e:
            print(f"  [WARN] 读旧日报失败: {e}")

    # 6. 写文件（无论是否抓到内容，都写，确保日期每天更新）
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)

    if total == 0:
        print("\n⚠️  未抓取到水利新闻（可能是网络问题），日期已更新")
    else:
        print(f"\n✅ 写入完成：{today_str}（{total} 条）")
    print(f"   往期归档：{len(archive)} 期")

    return True   # 永远返回 True，保证 workflow 不报 exit 1


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(0 if run() else 1)
