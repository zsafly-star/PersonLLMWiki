/**
 * 公共 Markdown 渲染模块
 * 统一调用后端 /api/article/preview 服务，保证全站渲染效果一致。
 *
 * 用法：
 *   1. 异步（推荐）：const html = await Md.render(text);
 *   2. 注入容器：    Md.renderInto(text, containerEl, { onLink });
 *   3. 同步降级：    Md.renderSync(text, fallbackRenderer);
 *
 * 内置 LRU 缓存，相同内容不重复请求。
 */
var Md = (function() {
    var API_URL = '/api/article/preview';
    var MAX_CACHE = 80;
    var cache = new Map(); // key: text -> value: html

    function key(text) { return text; }

    /**
     * 异步渲染 markdown，返回 HTML 字符串。
     * @param {string} text
     * @returns {Promise<string>}
     */
    function render(text) {
        text = text || '';
        if (!text) return Promise.resolve('');

        var k = key(text);
        if (cache.has(k)) {
            // 命中缓存，移到末尾（LRU）
            var v = cache.get(k);
            cache.delete(k); cache.set(k, v);
            return Promise.resolve(v);
        }

        return fetch(API_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: text })
        })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                var html = (res && res.code === 200 && res.data && res.data.content) ? res.data.content : '';
                // 写入缓存
                if (cache.size >= MAX_CACHE) {
                    // 删除最旧的
                    cache.delete(cache.keys().next().value);
                }
                cache.set(k, html);
                return html;
            });
    }

    /**
     * 渲染并注入到容器，注入完成后触发回调（可在此绑定链接）。
     * @param {string} text
     * @param {HTMLElement} container
     * @param {object} opts { loading: string, onDone: function(containerEl) }
     */
    function renderInto(text, container, opts) {
        if (!container) return;
        opts = opts || {};
        text = text || '';

        if (!text) { container.innerHTML = ''; return Promise.resolve(); }

        container.innerHTML = opts.loading || '<div class="md-loading">渲染中...</div>';
        return render(text).then(function(html) {
            container.innerHTML = html || '<p>（无内容）</p>';
            // 复用文章页 markdown 排版样式
            if (!container.classList.contains('article-body')) container.classList.add('article-body');
            if (typeof opts.onDone === 'function') opts.onDone(container);
        }).catch(function() {
            container.innerHTML = '<p>渲染失败</p>';
        });
    }

    /**
     * 同步降级渲染（仅当无法使用异步时）。需要传入一个本地 fallback 渲染器。
     * @param {string} text
     * @param {function} fallback function(text): html
     */
    function renderSync(text, fallback) {
        var k = key(text || '');
        if (cache.has(k)) return cache.get(k);
        if (typeof fallback === 'function') return fallback(text);
        return (text || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\n/g, '<br>');
    }

    /** 清空缓存 */
    function clearCache() { cache.clear(); }

    return {
        render: render,
        renderInto: renderInto,
        renderSync: renderSync,
        clearCache: clearCache
    };
})();
