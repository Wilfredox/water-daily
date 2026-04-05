/**
 * 水利日报 - 今日日报前端脚本
 *
 * 流程：
 *   1. 加载 news-data.json
 *   2. 用 data.date 更新页面标题和 <title>
 *   3. 按分类渲染新闻卡片
 */

document.addEventListener('DOMContentLoaded', function () {
    fetch('news-data.json?t=' + Date.now())   // 加时间戳防 CDN 缓存
        .then(function (r) {
            if (!r.ok) throw new Error('数据文件不存在');
            return r.json();
        })
        .then(function (data) {
            renderReport(data);
        })
        .catch(function (err) {
            console.error(err);
            renderEmpty('数据加载失败，请稍后刷新重试');
        });
});

/* ── 渲染今日日报 ──────────────────────────────────── */
function renderReport(data) {
    var titleEl  = document.getElementById('report-title');
    var timeEl   = document.getElementById('update-time');

    var dateStr  = data.date || '日期获取中';
    var timeStr  = data.update_time || (data.date ? data.date + ' 00:00' : '');

    if (titleEl) titleEl.textContent = '今日水利日报 — ' + dateStr;
    if (timeEl)  timeEl.textContent  = timeStr;
    document.title = '水利日报 — ' + dateStr;

    var container = document.getElementById('news-container');
    var news = data.news;

    if (!news || Object.keys(news).length === 0) {
        renderEmpty('今日暂无新闻数据，爬虫将于每天 00:00 自动更新');
        return;
    }

    var html = '';
    for (var category in news) {
        if (!Object.prototype.hasOwnProperty.call(news, category)) continue;
        var list = news[category];
        if (!list || list.length === 0) continue;

        html += '<div class="category-section category-' + esc(category) + '">';
        html += '<h4 class="category-title">' + esc(category) +
                '<span class="category-count">（' + list.length + ' 条）</span></h4>';
        html += '<div class="news-grid">';

        list.forEach(function (item) {
            var link = (item.full_link && item.full_link.indexOf('暂未公开') === -1)
                ? '<a href="' + esc(item.full_link) + '" target="_blank" rel="noopener" class="news-link">查看原文 →</a>'
                : '';
            html += '<article class="news-card">' +
                    '<h3>' + esc(item.title) + '</h3>' +
                    '<div class="news-meta">' +
                    '  <span class="news-source">' + esc(item.source) + '</span>' +
                    '  <span class="news-date">'   + esc(item.pub_date) + '</span>' +
                    '</div>' +
                    '<div class="news-content"><p>' + esc(item.content || item.title) + '</p></div>' +
                    link +
                    '</article>';
        });

        html += '</div></div>';
    }

    container.innerHTML = html;
}

/* ── 空状态 ───────────────────────────────────────── */
function renderEmpty(msg) {
    document.getElementById('news-container').innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">📰</div>' +
        '<h3>暂无新闻数据</h3>' +
        '<p>' + (msg || '') + '</p>' +
        '</div>';
}

/* ── HTML 转义 ────────────────────────────────────── */
function esc(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
