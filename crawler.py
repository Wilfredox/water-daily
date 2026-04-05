#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
水利日报爬虫 - 生产版
核心修复：
  - 中国政府网站经常屏蔽 GitHub Actions IP
  - 改用 RSS/Atom feed（更稳定、更易解析）
  - 所有源失败时写"暂无数据"占位，而非 exit 1 导致 Pages 空白
  - 归档逻辑健壮化
"""

import json, re, os, sys, time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup

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
    for pat in [
        r'(\d{4})年(\d{1,2})月(\d{1,2})日',
    ]:
        m = re.search(pat, s)
        if m:
            return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', s)
    if m:
        return f"{m.group(1)}年{int(m.group(2)):02d}月{int(m.group(3)):02d}日"
    m = re.match(r'(\d{1,2})[-/](\d{1,2})$', s)
    if m:
        y = beijing_now().year
        return f"{y}年{int(m.group(1)):02d}月{int(m.group(2)):02d}日"
    return None

# ── HTTP ──────────────────────────────────────────────────────────────────────
UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36',
]

import random
SESSION = requests.Session()

def get_headers():
    return {
        'User-Agent': random.choice(UA_LIST),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

def fetch(url, timeout=20, retries=2):
    for attempt in range(retries):
        try:
            r = SESSION.get(url, headers=get_headers(), timeout=timeout,
                            allow_redirects=True, verify=False)
            r.raise_for_status()
            if r.encoding in (None, 'ISO-8859-1', 'iso-8859-1'):
                r.encoding = r.apparent_encoding or 'utf-8'
            return r
        except Exception as e:
            print(f"    [attempt {attempt+1}] {url[:55]}… {e}")
            if attempt < retries - 1:
                time.sleep(2)
    return None

# 关闭 InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── RSS 解析（最可靠的方式） ──────────────────────────────────────────────────
def parse_rss(content, source_name, base_url=''):
    """解析 RSS/Atom XML，返回新闻列表"""
    items = []
    try:
        soup = BeautifulSoup(content, 'xml')
        # RSS 2.0
        entries = soup.find_all('item')
        is_atom = False
        if not entries:
            # Atom
            entries = soup.find_all('entry')
            is_atom = True

        for entry in entries[:20]:
            title_tag = entry.find('title')
            title = title_tag.get_text(strip=True) if title_tag else ''
            if not title or len(title) < 5:
                continue

            # URL
            link_tag = entry.find('link')
            if is_atom and link_tag:
                url = link_tag.get('href', '') or link_tag.get_text(strip=True)
            else:
                url = link_tag.get_text(strip=True) if link_tag else ''
            if not url:
                continue
            if url.startswith('/'):
                url = base_url.rstrip('/') + url

            # 日期
            for date_tag_name in ['pubDate', 'published', 'updated', 'dc:date']:
                date_tag = entry.find(date_tag_name)
                if date_tag:
                    date_str = date_tag.get_text(strip=True)
                    break
            else:
                date_str = ''

            # 摘要
            for desc_tag_name in ['description', 'summary', 'content']:
                desc_tag = entry.find(desc_tag_name)
                if desc_tag:
                    raw = BeautifulSoup(desc_tag.get_text(), 'html.parser').get_text(strip=True)
                    summary = re.sub(r'\s+', ' ', raw)[:300]
                    break
            else:
                summary = ''

            items.append({
                'title':    title,
                'url':      url,
                'pub_date': date_str,
                'content':  summary,
                'source':   source_name,
            })
    except Exception as e:
        print(f"    [RSS parse error] {e}")
    return items


def crawl_rss(rss_url, source_name, base_url=''):
    print(f"  ▷ [RSS] {source_name}  {rss_url[:55]}…")
    r = fetch(rss_url)
    if not r:
        print(f"    ✗ 失败")
        return []
    items = parse_rss(r.content, source_name, base_url)
    print(f"    ✓ {len(items)} 条")
    return items

# ── HTML 列表解析（备用） ─────────────────────────────────────────────────────
NOISE_TITLES = {'登录', '注册', '首页', '返回', '关于我们', '联系我们',
                '版权声明', '广告服务', '更多', '查看更多', '点击进入', '设为首页'}

def extract_content_from_html(html_text, max_chars=300):
    soup = BeautifulSoup(html_text, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
        tag.decompose()
    for sel in ['.TRS_Editor', '.article-content', '.art_content', '#content',
                '.content', '.news-content', 'article', '.main-text', '.text',
                '.detail-content', 'main']:
        el = soup.select_one(sel)
        if el:
            raw = el.get_text(separator=' ', strip=True)
            raw = re.sub(r'\s+', ' ', raw).strip()
            return raw[:max_chars]
    paras = [p.get_text(strip=True) for p in soup.find_all('p') if len(p.get_text(strip=True)) > 20]
    raw = re.sub(r'\s+', ' ', ' '.join(paras)).strip()
    return raw[:max_chars]


def extract_list_from_html(soup, base_url, source_name, max_items=15):
    items = []
    seen = set()
    parsed = urlparse(base_url)
    scheme_host = f"{parsed.scheme}://{parsed.netloc}"

    for li in soup.find_all('li'):
        a = li.find('a', href=True)
        if not a:
            continue
        title = a.get_text(strip=True)
        if len(title) < 7 or title in NOISE_TITLES:
            continue
        href = a['href'].strip()
        if not href or href.startswith('javascript') or href == '#':
            continue
        url = urljoin(scheme_host, href) if not href.startswith('http') else href
        date_str = ''
        for tag in li.find_all(['span', 'em', 'i', 'time', 'p', 'small']):
            t = tag.get_text(strip=True)
            if re.search(r'\d{4}[-/年]\d{1,2}', t) or re.search(r'\d{2}[-/]\d{2}', t):
                date_str = t
                break
        key = re.sub(r'\s+', '', title)[:20]
        if key not in seen:
            seen.add(key)
            items.append({'title': title, 'url': url, 'pub_date': date_str,
                          'content': '', 'source': source_name})
    return items[:max_items]


def crawl_html(list_url, source_name, base_url, max_items=15, fetch_content=False):
    print(f"  ▷ [HTML] {source_name}  {list_url[:55]}…")
    r = fetch(list_url)
    if not r:
        print(f"    ✗ 失败")
        return []
    soup = BeautifulSoup(r.text, 'html.parser')
    items = extract_list_from_html(soup, base_url, source_name, max_items)
    print(f"    ✓ {len(items)} 条（列表）")

    if fetch_content and items:
        print(f"    → 抓取正文…")
        for it in items[:12]:
            rc = fetch(it['url'], timeout=12)
            if rc:
                it['content'] = extract_content_from_html(rc.text)
            time.sleep(0.5)

    return items

# ── 新闻分类 ──────────────────────────────────────────────────────────────────
CATEGORY_RULES = [
    ('防汛抗旱',   ['防汛', '抗旱', '洪水', '汛情', '汛期', '台风', '暴雨',
                    '抢险', '旱情', '泄洪', '泄水', '应急响应', '备汛', '洪涝']),
    ('水利工程',   ['水库', '大坝', '堤防', '海塘', '渠道', '泵站', '闸',
                    '灌区', '工程建设', '竣工', '验收', '除险加固', '开工']),
    ('水资源管理', ['水资源', '节水', '供水', '取水许可', '地下水', '调水',
                    '引水', '水权', '用水总量', '水量分配']),
    ('水生态环境', ['水生态', '水环境', '河湖', '河长制', '湖长', '湿地',
                    '水质', '水污染', '生态修复', '水清岸绿', '水土保持']),
    ('政策法规',   ['发布', '印发', '出台', '条例', '规划', '办法', '意见',
                    '通知', '规范', '标准', '规定', '法规', '政策']),
    ('综合要闻',   []),
]

def classify(title, content=''):
    text = title + ' ' + content
    for category, kws in CATEGORY_RULES:
        if not kws:
            return category
        for kw in kws:
            if kw in text:
                return category
    return '综合要闻'

# ── 数据源配置 ────────────────────────────────────────────────────────────────
# 优先用 RSS（最稳定），备用 HTML 列表
# 水利部有官方 RSS，中国水利网也有
RSS_SOURCES = [
    # 水利部 RSS（多个频道）
    ('http://www.mwr.gov.cn/rss/mwr.xml',                      '水利部',      'http://www.mwr.gov.cn'),
    ('http://www.mwr.gov.cn/rss/gzdt.xml',                     '水利部',      'http://www.mwr.gov.cn'),
    # 中国水利网 RSS
    ('http://www.chinawater.com.cn/rss/chinawater.xml',         '中国水利网',  'http://www.chinawater.com.cn'),
    ('http://www.chinawater.com.cn/rss/yw.xml',                 '中国水利网',  'http://www.chinawater.com.cn'),
    # 新华网水利频道（有 RSS）
    ('http://www.xinhuanet.com/politics/rss/zhengce.xml',       '新华网',      'http://www.xinhuanet.com'),
]

HTML_SOURCES = [
    # 水利部工作动态
    ('http://www.mwr.gov.cn/sj/xxgk/gzdt/index.shtml',         '水利部',        'http://www.mwr.gov.cn',         15),
    # 中国水利网要闻
    ('http://www.chinawater.com.cn/newscenter/yw/index.htm',    '中国水利网',    'http://www.chinawater.com.cn',  12),
    # 浙江水利厅
    ('https://www.zjsw.gov.cn/col/col1229259781/index.html',    '浙江省水利厅',  'https://www.zjsw.gov.cn',       12),
    ('https://www.zjsw.gov.cn/col/col1229259784/index.html',    '浙江省水利厅',  'https://www.zjsw.gov.cn',       10),
]

# ── 主流程 ────────────────────────────────────────────────────────────────────
def run():
    now       = beijing_now()
    today_str = fmt_date(now)
    yest_str  = fmt_date(now - timedelta(days=1))
    upd_str   = now.strftime('%Y-%m-%d 00:00')

    print(f"\n{'='*55}")
    print(f"  水利日报爬虫  {today_str}")
    print(f"  期号：{today_str}  |  内容日期：{yest_str}")
    print(f"{'='*55}\n")

    all_raw = []

    # 1a. 先尝试 RSS（最可靠）
    print("── RSS 源 ──────────────────────────────────────")
    for rss_url, source_name, base_url in RSS_SOURCES:
        items = crawl_rss(rss_url, source_name, base_url)
        all_raw.extend(items)
        time.sleep(0.8)

    # 1b. 再尝试 HTML 列表
    print("\n── HTML 源 ─────────────────────────────────────")
    for list_url, source_name, base_url, max_items in HTML_SOURCES:
        items = crawl_html(list_url, source_name, base_url, max_items, fetch_content=True)
        all_raw.extend(items)
        time.sleep(1.0)

    print(f"\n原始条目：{len(all_raw)}")

    # 2. 去重
    seen, deduped = set(), []
    for it in all_raw:
        key = re.sub(r'\s+', '', it['title'])[:22]
        if key and key not in seen:
            seen.add(key)
            deduped.append(it)
    print(f"去重后：{len(deduped)}")

    # 3. 构建新闻数据（即使为空也继续，写占位）
    cat_map = {}
    nid = 1
    for it in deduped:
        cat = classify(it['title'], it.get('content', ''))
        cat_map.setdefault(cat, [])
        pd = parse_date_loose(it.get('pub_date', '')) or yest_str
        cat_map[cat].append({
            'id':        nid,
            'title':     it['title'],
            'source':    it['source'],
            'pub_date':  pd,
            'content':   it.get('content', '') or it['title'],
            'full_link': it['url'],
        })
        nid += 1

    total = sum(len(v) for v in cat_map.values())
    today_data = {
        'date':           today_str,
        'news_date':      yest_str,
        'update_time':    upd_str,
        'total_news':     total,
        'category_count': len(cat_map),
        'news':           cat_map,
    }

    # 4. 归档旧日报
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

    # 5. 写文件（无论是否抓到内容，都写文件，保证日期更新）
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)

    with open(news_path, 'w', encoding='utf-8') as f:
        json.dump(today_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完成")
    print(f"   今日日报：{today_str}（{total} 条，{len(cat_map)} 类）")
    print(f"   往期归档：{len(archive)} 期")

    # 无论是否抓到内容，都返回 True（保证 workflow 不因 exit 1 中断）
    if total == 0:
        print("  ⚠️  本次未抓取到新闻（网络问题），日期已更新，内容待下次更新")
    return True


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.exit(0 if run() else 1)
