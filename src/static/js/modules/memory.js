/* ═══════════════════════════════════════════════════════════════════
   记忆管理页 — 列表 / 过滤 / 撤回 / 转正
   依赖全局：customConfirm / customAlert / showToast（base.html）
   ═══════════════════════════════════════════════════════════════════ */

var _mmKind = '';
var _mmShowRevoked = false;

var MM_KIND_LABELS = { preference: '偏好', fact: '事实', decision: '决策', other: '其他' };
var MM_KIND_TAGS = {
    preference: 'am-tag-builtin',
    fact: 'am-tag-local',
    decision: 'am-tag-custom',
    other: 'am-tag-remote',
};
var MM_STATUS_LABELS = { auto: '自动', promoted: '已转正', revoked: '已撤回' };
var MM_STATUS_CLASS = { auto: 'mm-status-auto', promoted: 'mm-status-promoted', revoked: 'mm-status-revoked' };

function mmEsc(str) {
    var d = document.createElement('div');
    d.textContent = (str == null ? '' : String(str));
    return d.innerHTML;
}

function initMemoryPage() {
    var tabs = document.querySelectorAll('.mm-tab');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].addEventListener('click', function() {
            _mmKind = this.getAttribute('data-kind') || '';
            var all = document.querySelectorAll('.mm-tab');
            for (var j = 0; j < all.length; j++) all[j].classList.remove('mm-tab--on');
            this.classList.add('mm-tab--on');
            loadMemoryList();
        });
    }

    var toggle = document.getElementById('mm-show-revoked');
    if (toggle) {
        toggle.addEventListener('change', function() {
            _mmShowRevoked = this.checked;
            loadMemoryList();
        });
    }

    loadMemoryList();
}

function loadMemoryList() {
    var grid = document.getElementById('mm-grid');
    if (!grid) return;

    var qs = _mmKind ? '?kind=' + encodeURIComponent(_mmKind) : '';

    fetch('/api/memory/list' + qs)
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.code !== 200) {
                grid.innerHTML = '<div class="mm-empty"><p>加载失败</p></div>';
                return;
            }
            var items = (res.data && res.data.items) || [];
            if (!_mmShowRevoked) {
                items = items.filter(function(m) { return m.status !== 'revoked'; });
            }
            renderMemoryList(items);
        })
        .catch(function() {
            grid.innerHTML = '<div class="mm-empty"><p>加载失败</p></div>';
        });
}

function renderMemoryList(items) {
    var grid = document.getElementById('mm-grid');
    if (!grid) return;

    if (!items || items.length === 0) {
        grid.innerHTML =
            '<div class="mm-empty">' +
            '<svg class="mm-empty-icon" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a9 9 0 1 0 9 9"/><path d="M12 7v5l3 2"/></svg>' +
            '<p>还没有记忆</p>' +
            '<p class="mm-empty-hint">去对话中自动沉淀，或用对话里的「记住本对话」</p>' +
            '</div>';
        return;
    }

    grid.innerHTML = items.map(function(m) {
        var slug = m.slug || '';
        var kind = m.kind || 'other';
        var status = m.status || 'auto';
        var body = m.body || '';
        var summary = m.summary || '';
        var sourceChat = m.source_chat_id;
        var kindLabel = MM_KIND_LABELS[kind] || kind;
        var kindTag = MM_KIND_TAGS[kind] || 'am-tag-remote';
        var statusLabel = MM_STATUS_LABELS[status] || status;
        var statusClass = MM_STATUS_CLASS[status] || 'mm-status-auto';

        var title = summary || body.slice(0, 40);
        var preview = body || summary;

        var sourceHtml = '';
        if (sourceChat != null && sourceChat !== '') {
            sourceHtml = '<span class="mm-source">来源对话 ' +
                '<a href="/chat" data-nav>#' + mmEsc(String(sourceChat)) + '</a></span>';
        }

        var promoted = status === 'promoted';
        var revoked = status === 'revoked';

        var actions =
            '<button class="am-btn-ghost am-btn-xs" onclick="mmPromote(\'' + mmJsAttr(slug) + '\')"' + (promoted ? ' disabled' : '') + '>转正为知识</button>' +
            (revoked
                ? ''
                : '<button class="am-btn-ghost am-btn-xs am-btn-danger" onclick="mmForget(\'' + mmJsAttr(slug) + '\')">撤回</button>');

        return '<div class="am-mcp-card mm-card" data-slug="' + mmEsc(slug) + '">' +
            '<div class="mm-card-head" onclick="mmToggle(\'' + mmJsAttr(slug) + '\')">' +
                '<div class="am-mcp-info">' +
                    '<div class="mm-title">' + mmEsc(title) + '</div>' +
                    '<div class="mm-preview">' + mmEsc(preview) + '</div>' +
                    '<div class="mm-meta">' +
                        '<span class="am-tag ' + kindTag + '">' + mmEsc(kindLabel) + '</span>' +
                        '<span class="mm-status ' + statusClass + '"><span class="mm-status-dot"></span>' + mmEsc(statusLabel) + '</span>' +
                        sourceHtml +
                    '</div>' +
                '</div>' +
                '<svg class="am-mcp-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>' +
            '</div>' +
            '<div class="mm-body-full" id="mm-body-' + mmEsc(slug) + '" style="display:none">' +
                '<pre class="mm-body-text">' + mmEsc(body || '') + '</pre>' +
            '</div>' +
            '<div class="mm-actions">' + actions + '</div>' +
        '</div>';
    }).join('');
}

function mmToggle(slug) {
    var el = document.getElementById('mm-body-' + slug);
    if (!el) return;
    var card = el.closest('.mm-card');
    var chevron = card ? card.querySelector('.am-mcp-chevron') : null;
    if (el.style.display === 'none') {
        el.style.display = '';
        if (card) card.classList.add('am-mcp-expanded');
        if (chevron) chevron.style.transform = 'rotate(180deg)';
    } else {
        el.style.display = 'none';
        if (card) card.classList.remove('am-mcp-expanded');
        if (chevron) chevron.style.transform = '';
    }
}

function mmForget(slug) {
    customConfirm('撤回后该记忆将从检索中移除（物理文件保留，可在「显示已撤回」中查看）。是否继续？', '撤回记忆')
        .then(function(ok) {
            if (!ok) return;
            fetch('/api/memory/forget', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ slug: slug }),
            })
                .then(function(r) { return r.json(); })
                .then(function(res) {
                    if (res.code === 200) {
                        showToast('已撤回');
                        loadMemoryList();
                    } else {
                        customAlert(res.message || '撤回失败');
                    }
                })
                .catch(function() { customAlert('撤回失败'); });
        });
}

function mmPromote(slug) {
    fetch('/api/memory/promote', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug: slug }),
    })
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.code === 200) {
                showToast('已转正，编译产出待审批');
                setTimeout(function() {
                    window.location.href = '/wiki';
                }, 900);
            } else {
                customAlert(res.message || '转正失败');
            }
        })
        .catch(function() { customAlert('转正失败'); });
}

function mmJsAttr(str) {
    return (str == null ? '' : String(str)).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
