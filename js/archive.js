/**
 * 水利日报 - 往期日报前端脚本
 *
 * 列表模式：年月树形展开，点击月份展开该月所有日期
 * 详情模式：URL ?date=XXXX 时展示完整日报
 */

document.addEventListener('DOMContentLoaded', function () {
    var date = getUrlDate();
    if (date) {
        loadDetail(date);
    } else {
        loadList();
    }
});

/* ══════════════════════════════════════════════════
   列表模式 — 年月树形
══════════════════════════════════════════════════ */
function loadList() {
    fetch('archive-data.json?t=' + Date.now())
        .then(function (r) {
            if (!r.ok) throw new Error('归档文件不存在');
            return r.json();
        })
        .then(function (data) {
            renderList(Array.isArray(data) ? data : []);
        })
        .catch(renderListEmpty);
}

function renderList(data) {
    var container = document.getElementById('archive-container');
    var subtitle  = document.getElementById('archive-subtitle');

    if (!data || data.length === 0) {
        renderListEmpty();
        return;
    }

    if (subtitle) {
        subtitle.textContent = '共收录 ' + data.length + ' 期历史日报，选择月份查看';
    }

    // 按日期倒序
    var sorted = data.slice().sort(function (a, b) {
        return (b.date || '').localeCompare(a.date || '');
    });

    // 构建 年 -> 月 -> [item] 的树结构
    // key: "2026年" -> "04月" -> [items]
    var tree = {};   // { year: { month: [items] } }
    var yearOrder = [], monthOrder = {};

    sorted.forEach(function (item) {
        var m = (item.date || '').match(/(\d{4})年(\d{1,2})月(\d{1,2})日/);
        if (!m) return;
        var year  = m[1] + '年';
        var month = pad2(m[2]) + '月';
        if (!tree[year]) {
            tree[year] = {};
            yearOrder.push(year);
            monthOrder[year] = [];
        }
        if (!tree[year][month]) {
            tree[year][month] = [];
            monthOrder[year].push(month);
        }
        tree[year][month].push(item);
    });

    // 渲染树形结构
    var html = '<div class="archive-tree">';

    yearOrder.forEach(function (year) {
        html += '<div class="tree-year">';
        html += '<div class="tree-year-label">📅 ' + esc(year) + '</div>';
        html += '<div class="tree-months">';

        monthOrder[year].forEach(function (month) {
            var monthKey = year + month;   // 唯一 ID，用于展开/收起
            var items    = tree[year][month];
            var isFirst  = (yearOrder[0] === year && monthOrder[year][0] === month);

            html += '<div class="tree-month" data-key="' + esc(monthKey) + '">';
            html += '<div class="tree-month-label" onclick="toggleMonth(\'' + esc(monthKey) + '\')">' +
                    '<span class="tree-arrow" id="arrow-' + esc(monthKey) + '">' +
                    (isFirst ? '▾' : '▸') + '</span>' +
                    '<span class="tree-month-name">' + esc(month) + '</span>' +
                    '<span class="tree-month-count">（' + items.length + ' 期）</span>' +
                    '</div>';

            // 日期列表，默认只展开最新月份
            html += '<div class="tree-days" id="days-' + esc(monthKey) + '" ' +
                    'style="display:' + (isFirst ? 'block' : 'none') + ';">';

            items.forEach(function (item) {
                html += '<div class="tree-day-item">' +
                        '<div class="day-info">' +
                        '<span class="day-label">' + esc(item.date) + '</span>' +
                        '<span class="day-meta">' + (item.total_news || 0) + ' 条</span>' +
                        '</div>' +
                        '<a href="archive.html?date=' + encodeURIComponent(item.date) +
                        '" class="date-link">查看 →</a>' +
                        '</div>';
            });

            html += '</div>';   // tree-days
            html += '</div>';   // tree-month
        });

        html += '</div>';   // tree-months
        html += '</div>';   // tree-year
    });

    html += '</div>';   // archive-tree
    container.innerHTML = html;
}

function toggleMonth(key) {
    var days  = document.getElementById('days-' + key);
    var arrow = document.getElementById('arrow-' + key);
    if (!days) return;
    if (days.style.display === 'none') {
        days.style.display = 'block';
        if (arrow) arrow.textContent = '▾';
    } else {
        days.style.display = 'none';
        if (arrow) arrow.textContent = '▸';
    }
}

function renderListEmpty() {
    var container = document.getElementById('archive-container');
    if (container) {
        container.innerHTML =
            '<div class="empty-state">' +
            '<div class="empty-state-icon">📅</div>' +
            '<h3>暂无历史数据</h3>' +
            '<p>每日自动更新后，前一天的日报将自动归档至此</p>' +
            '</div>';
    }
}

/* ══════════════════════════════════════════════════
   详情模式
══════════════════════════════════════════════════ */
function loadDetail(date) {
    fetch('archive-data.json?t=' + Date.now())
        .then(function (r) {
            if (!r.ok) throw new Error('归档文件不存在');
            return r.json();
        })
        .then(function (data) {
            var arr  = Array.isArray(data) ? data : [];
            var item = null;
            for (var i = 0; i < arr.length; i++) {
                if (arr[i].date === date) { item = arr[i]; break; }
            }
            item ? renderDetail(item) : renderDetailNotFound(date);
        })
        .catch(function () { renderDetailNotFound(date); });
}

function renderDetail(data) {
    document.title = data.date + ' — 往期水利日报';
    var subtitle = document.getElementById('archive-subtitle');
    if (subtitle) {
        subtitle.textContent = data.date + ' · 共 ' +
            (data.total_news || 0) + ' 条新闻，' +
            (data.category_count || 0) + ' 个分类';
    }

    var container = document.getElementById('archive-container');
    var news = data.news;

    if (!news || Object.keys(news).length === 0) {
        container.innerHTML =
            '<div class="empty-state">' +
            '<div class="empty-state-icon">📰</div>' +
            '<h3>该期日报暂无新闻数据</h3>' +
            '<p><a href="archive.html" style="color:#2c5282">← 返回往期列表</a></p>' +
            '</div>';
        return;
    }

    var html = '<div class="archive-detail">' +
        '<div class="detail-header">' +
        '<a href="archive.html" class="back-button">← 返回往期列表</a>' +
        '<h1 class="detail-title">' + esc(data.date) + ' 水利日报</h1>' +
        '<p class="detail-subtitle">共 ' + (data.total_news || 0) +
        ' 条新闻 · ' + (data.category_count || 0) + ' 个分类</p>' +
        '</div>' +
        '<div style="padding:30px 40px;">';

    for (var category in news) {
        if (!Object.prototype.hasOwnProperty.call(news, category)) continue;
        var list = news[category];
        if (!list || list.length === 0) continue;

        html += '<div class="category-section category-' + esc(category) + '" style="margin-bottom:40px;">' +
                '<h4 class="category-title">' + esc(category) +
                '<span class="category-count">（' + list.length + ' 条）</span></h4>' +
                '<div class="news-grid">';

        list.forEach(function (item) {
            // 同样的内容去重逻辑
            var contentText = (item.content || '').trim();
            var titleText   = (item.title   || '').trim();
            var contentHtml = '';
            if (contentText && contentText.length > 20) {
                var overlap = longestCommonSubstr(titleText, contentText);
                if (overlap / titleText.length < 0.7) {
                    contentHtml = '<div class="news-content"><p>' + esc(contentText) + '</p></div>';
                }
            }

            var impactHtml = item.impact
                ? '<div class="news-impact"><strong>可能的影响：</strong>' + esc(item.impact) + '</div>'
                : '';
            var link = (item.full_link && item.full_link.indexOf('暂未公开') === -1)
                ? '<a href="' + esc(item.full_link) + '" target="_blank" rel="noopener" class="news-link">查看原文 →</a>'
                : '';

            html += '<article class="news-card">' +
                    '<h3>' + esc(item.title) + '</h3>' +
                    '<div class="news-meta">' +
                    '<span class="news-source">' + esc(item.source) + '</span>' +
                    '<span class="news-date">'   + esc(item.pub_date) + '</span>' +
                    '</div>' +
                    contentHtml +
                    impactHtml +
                    link +
                    '</article>';
        });
        html += '</div></div>';
    }

    html += '</div></div>';
    container.innerHTML = html;
}

function renderDetailNotFound(date) {
    document.getElementById('archive-container').innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">🔍</div>' +
        '<h3>未找到 ' + esc(date) + ' 的日报</h3>' +
        '<p><a href="archive.html" style="color:#2c5282">← 返回往期列表</a></p>' +
        '</div>';
}

/* ── 工具函数 ─────────────────────────────────────── */
function getUrlDate() {
    var p = new URLSearchParams(window.location.search);
    var d = p.get('date');
    return d ? decodeURIComponent(d) : null;
}

function pad2(n) { return String(n).padStart(2, '0'); }

function longestCommonSubstr(a, b) {
    if (!a || !b) return 0;
    var maxLen = 0;
    for (var i = 0; i < a.length; i++) {
        for (var j = 0; j < b.length; j++) {
            var len = 0;
            while (i+len < a.length && j+len < b.length && a[i+len] === b[j+len]) len++;
            if (len > maxLen) maxLen = len;
        }
    }
    return maxLen;
}

function esc(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
