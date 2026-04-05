/**
 * 水利日报 - 往期日报前端脚本
 *
 * URL 无参数  → 列表模式：读 archive-data.json，展示所有归档日期
 * URL ?date=X → 详情模式：在 archive-data.json 中找到该日期并展示全文
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
   列表模式
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
        .catch(function () {
            renderListEmpty();
        });
}

function renderList(data) {
    var container = document.getElementById('archive-container');
    var subtitle  = document.getElementById('archive-subtitle');

    if (!data || data.length === 0) {
        renderListEmpty();
        return;
    }

    if (subtitle) {
        subtitle.textContent = '共收录 ' + data.length + ' 期历史日报，点击日期查看完整内容';
    }

    // 按日期倒序
    var sorted = data.slice().sort(function (a, b) {
        return (b.date || '').localeCompare(a.date || '');
    });

    // 提取唯一月份（用于筛选器）
    var months = [];
    var monthSet = {};
    sorted.forEach(function (item) {
        var m = (item.date || '').match(/(\d{4})年(\d{1,2})月/);
        if (m) {
            var key = m[1] + '年' + pad2(m[2]) + '月';
            if (!monthSet[key]) {
                monthSet[key] = true;
                months.push(key);
            }
        }
    });
    months.sort(function (a, b) { return b.localeCompare(a); });

    var filterHtml = '';
    if (months.length > 1) {
        filterHtml = '<div class="month-filter">' +
            '<label for="month-select">筛选月份：</label>' +
            '<select id="month-select" class="date-filter-select">' +
            '<option value="all">全部月份</option>' +
            months.map(function (m) {
                return '<option value="' + esc(m) + '">' + esc(m) + '</option>';
            }).join('') +
            '</select></div>';
    }

    container.innerHTML = filterHtml + '<div id="date-list">' + buildDateItems(sorted) + '</div>';

    var sel = document.getElementById('month-select');
    if (sel) {
        sel.addEventListener('change', function () {
            var val = this.value;
            var filtered = val === 'all' ? sorted : sorted.filter(function (item) {
                var m = (item.date || '').match(/(\d{4})年(\d{1,2})月/);
                return m && (m[1] + '年' + pad2(m[2]) + '月') === val;
            });
            document.getElementById('date-list').innerHTML = buildDateItems(filtered);
        });
    }
}

function buildDateItems(items) {
    if (!items.length) {
        return '<div class="empty-state"><div class="empty-state-icon">📅</div>' +
               '<h3>该月份暂无记录</h3></div>';
    }
    return items.map(function (item) {
        return '<div class="date-item">' +
               '<div class="date-info">' +
               '<h3 class="date-title">' + esc(item.date) + '</h3>' +
               '<p class="date-meta">共 ' + (item.total_news || 0) + ' 条新闻，' +
               (item.category_count || 0) + ' 个分类</p>' +
               '</div>' +
               '<a href="archive.html?date=' + encodeURIComponent(item.date) +
               '" class="date-link">查看详情 →</a>' +
               '</div>';
    }).join('');
}

function renderListEmpty() {
    document.getElementById('archive-container').innerHTML =
        '<div class="empty-state">' +
        '<div class="empty-state-icon">📅</div>' +
        '<h3>暂无历史数据</h3>' +
        '<p>每日自动更新后，前一天的日报将自动归档至此</p>' +
        '</div>';
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
            if (item) {
                renderDetail(item);
            } else {
                renderDetailNotFound(date);
            }
        })
        .catch(function () {
            renderDetailNotFound(date);
        });
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
            var link = (item.full_link && item.full_link.indexOf('暂未公开') === -1)
                ? '<a href="' + esc(item.full_link) + '" target="_blank" rel="noopener" class="news-link">查看原文 →</a>'
                : '';
            var impactHtml = item.impact
                ? '<div class="news-impact"><strong>可能的影响：</strong>' + esc(item.impact) + '</div>'
                : '';
            html += '<article class="news-card">' +
                    '<h3>' + esc(item.title) + '</h3>' +
                    '<div class="news-meta">' +
                    '<span class="news-source">' + esc(item.source) + '</span>' +
                    '<span class="news-date">'   + esc(item.pub_date) + '</span>' +
                    '</div>' +
                    '<div class="news-content"><p>' + esc(item.content || item.title) + '</p></div>' +
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

function pad2(n) {
    return String(n).padStart(2, '0');
}

function esc(s) {
    if (!s) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
