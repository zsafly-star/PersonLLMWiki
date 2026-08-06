/**
 * 聊天页面脚本（从 chat.html 提取）
 */

var sid = null;

if (!window._streamState) window._streamState = null;

if (window._chatEventController) {
    window._chatEventController.abort();
}
window._chatEventController = new AbortController();
var _ec = window._chatEventController;

window.addEventListener('beforeunload', function() {
    if (window._streamState && window._streamState.abortController) {
        window._streamState.abortController.abort();
    }
}, {signal: _ec.signal});

function abortStream() {
    if (window._streamState && window._streamState.abortController) {
        window._streamState.abortController.abort();
    }
    window._streamState = null;
}

// Re-bind UI event listeners (called on every SPA navigation to chat page)
function _bindChatUI() {
    var el;

    el = document.getElementById('chat-plus-dropdown');
    if (el) { el.removeEventListener('click', _onPlusDropdownClick); el.addEventListener('click', _onPlusDropdownClick); }

    el = document.getElementById('chat-mode-dropdown');
    if (el) { el.removeEventListener('click', _onModeDropdownClick); el.addEventListener('click', _onModeDropdownClick); }

    el = document.getElementById('chat-model-dropdown');
    if (el) { el.removeEventListener('click', _onModelDropdownClick); el.addEventListener('click', _onModelDropdownClick); }

    el = document.getElementById('chat-file-input');
    if (el) { el.removeEventListener('change', _onFileInputChange); el.addEventListener('change', _onFileInputChange); }

    el = document.getElementById('kb-browser');
    if (el) { el.removeEventListener('click', _onKbBrowserClick); el.addEventListener('click', _onKbBrowserClick); }

    el = document.getElementById('kb-browser-overlay');
    if (el) { el.removeEventListener('click', _onKbOverlayClick); el.addEventListener('click', _onKbOverlayClick); }

    // Panel resize (handle mousedown re-bound; document-level move/up bound once)
    el = document.getElementById('panel-resize-handle');
    if (el) { el.removeEventListener('mousedown', _onPanelResizeMouseDown); el.addEventListener('mousedown', _onPanelResizeMouseDown); }
    if (!_panelResizeState._docBound) {
        document.addEventListener('mousemove', _onPanelResizeMouseMove);
        document.addEventListener('mouseup', _onPanelResizeMouseUp);
        _panelResizeState._docBound = true;
    }
}

function initChat() {
    _bindChatUI();
    loadHistory();
    loadConfig();
    loadModels();

    // 从工作台搜索跳转过来，自动发起新会话
    var urlParams = new URLSearchParams(window.location.search);
    var autoQ = urlParams.get('q');
    if (autoQ) {
        window.history.replaceState({}, '', '/chat');
        createNewSession(function() {
            document.getElementById('chat-input').value = autoQ;
            sendMsg();
        });
        return;
    }

    var savedSid = localStorage.getItem('chat_sid');
    if (savedSid) {
        sid = parseInt(savedSid);
        showChat();
        if (window._streamState && window._streamState.active && window._streamState.sessionId === sid) {
            resumeStream();
        } else {
            loadMsgs(sid);
        }
    } else {
        // 无历史会话：显示欢迎页 + 输入框（新建对话模式）
        sid = null;
        hideChat();
    }
}

function resumeStream() {
    var st = window._streamState;
    st.active = false;  // 暂停 SSE 回调，防止 rebuild 期间操作已清除的 DOM
    clearMsgs();
    fetch('/api/chat/sessions/' + sid).then(function(r) { return r.json(); }).then(function(res) {
        // SSE 可能在 fetch 期间完成并清除了 _streamState
        if (window._streamState !== st) {
            // 流已完成，用常规方式加载消息
            loadMsgs(sid);
            return;
        }
        if (res.code === 200 && res.data && res.data.messages) {
            res.data.messages.forEach(function(m) {
                if (m.role === 'assistant' && !m.content) return;
                addBubble(m.role, m.content, m.created_at, m.id, null, m.exported_files, m.thinking_json);
            });
        }
        rebuildStreamUI(st);
        st.active = true;
    });
}

function rebuildStreamUI(st) {
    var oldStream = document.getElementById('stream-text');
    if (oldStream) oldStream.removeAttribute('id');

    var streamBubble = document.createElement('div');
    streamBubble.className = 'chat-bubble-row assistant';
    streamBubble.id = 'stream-bubble';
    streamBubble.innerHTML = '<div class="chat-bubble-wrap"><div class="chat-bubble" id="stream-text"></div></div>';
    document.getElementById('chat-messages-scroll').appendChild(streamBubble);

    var streamTextEl = document.getElementById('stream-text');

    // 重建思考过程容器
    if (st.thinking.stages.length > 0) {
        st.thinkingContainer = null;
        _initThinkingProcess(st);
        _renderProgressBar(st);
    }

    // 重建答案内容
    if (st.streamContent) {
        if (st.thinking.placeholderEl) st.thinking.placeholderEl.style.display = 'none';
        if (!st.thinking.answerEl) {
            st.thinking.answerEl = document.createElement('div');
            st.thinking.answerEl.id = 'stream-content';
            streamTextEl.appendChild(st.thinking.answerEl);
        }
        st.thinking.answerEl.innerHTML = md(st.streamContent);
    }

    var btn = document.getElementById('chat-send-btn');
    if (btn) btn.classList.add('streaming');
    scrollEnd();
}

// ===== 阶段节点式思考过程组件 =====
function _initThinkingProcess(st) {
    if (st.thinkingContainer) return;
    var el = document.getElementById('stream-text');
    if (!el) return;

    var container = document.createElement('div');
    container.className = 'thinking-process';
    container.id = 'thinking-process';

    container.innerHTML =
        '<div class="thinking-progress">' +
            '<div class="thinking-progress-track"></div>' +
            '<button class="thinking-skip-btn" onclick="_skipThinking(window._streamState)">跳过思考</button>' +
        '</div>' +
        '<div class="thinking-detail">' +
            '<div class="thinking-detail-header">' +
                '<span class="thinking-detail-title">当前阶段：—</span>' +
                '<div class="thinking-detail-actions">' +
                    '<button onclick="_copyStageDetail()">复制本段</button>' +
                    '<button onclick="this.closest(\'.thinking-detail\').classList.remove(\'active\');window._streamState&&(window._streamState.thinking.selectedStageId=null)">收起</button>' +
                '</div>' +
            '</div>' +
            '<div class="thinking-detail-content"></div>' +
        '</div>' +
        '<div class="thinking-answer-divider">最终答案</div>' +
        '<div class="thinking-answer-placeholder">思考完成后将展示最终答案</div>';

    el.appendChild(container);
    st.thinkingContainer = container;
    st.thinking.processEl = container;
    st.thinking.trackEl = container.querySelector('.thinking-progress-track');
    st.thinking.skipBtn = container.querySelector('.thinking-skip-btn');
    st.thinking.detailEl = container.querySelector('.thinking-detail');
    st.thinking.detailTitle = container.querySelector('.thinking-detail-title');
    st.thinking.detailContent = container.querySelector('.thinking-detail-content');
    st.thinking.placeholderEl = container.querySelector('.thinking-answer-placeholder');
    st.thinking.answerEl = null;
}

function _handleStageStart(st, data) {
    if (!st.active) return;
    _initThinkingProcess(st);

    // 查找或创建节点
    var existing = null;
    for (var i = 0; i < st.thinking.stages.length; i++) {
        if (st.thinking.stages[i].stage_id === data.stage_id) {
            existing = st.thinking.stages[i];
            break;
        }
    }

    if (!existing) {
        // 新阶段：添加 stage 数据
        var stage = {
            stage_id: data.stage_id,
            stage_name: data.stage_name || '',
            tool_name: data.tool_name || '',
            tool_arguments: data.tool_arguments || '',
            round: data.round || 0,
            status: 'processing',
            start_timestamp: data.start_timestamp || 0,
            content: '',
            nodeEl: null
        };
        st.thinking.stages.push(stage);

        // 标记之前的阶段为 completed
        for (var j = 0; j < st.thinking.stages.length - 1; j++) {
            if (st.thinking.stages[j].status === 'processing') {
                st.thinking.stages[j].status = 'completed';
            }
        }
    } else {
        existing.status = 'processing';
    }

    st.thinking.currentStageId = data.stage_id;
    _renderProgressBar(st);
}

function _handleStageEnd(st, data) {
    if (!st.active) return;
    for (var i = 0; i < st.thinking.stages.length; i++) {
        if (st.thinking.stages[i].stage_id === data.stage_id) {
            st.thinking.stages[i].status = data.status || 'completed';
            if (data.end_timestamp) st.thinking.stages[i].end_timestamp = data.end_timestamp;
            if (data.content) st.thinking.stages[i].content = data.content;
            break;
        }
    }
    _renderProgressBar(st);

    // 如果详情面板展开且选中该阶段，更新内容
    if (st.thinking.selectedStageId === data.stage_id) {
        _selectStageDetail(st, data.stage_id);
    }
}

function _finishThinking(st) {
    st.thinking.globalStatus = 'completed';
    // 标记所有进行中的阶段为已完成
    for (var i = 0; i < st.thinking.stages.length; i++) {
        if (st.thinking.stages[i].status === 'processing') {
            st.thinking.stages[i].status = 'completed';
        }
    }
    _renderProgressBar(st);
    // 隐藏跳过按钮
    if (st.thinking.skipBtn) st.thinking.skipBtn.style.display = 'none';
}

function _createStaticThinking(stages) {
    var container = document.createElement('div');
    container.className = 'thinking-history';

    var header = document.createElement('div');
    header.className = 'thinking-history-header';
    header.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a7 7 0 0 0-7 7c0 2.38 1.19 4.47 3 5.74V17a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-2.26c1.81-1.27 3-3.36 3-5.74a7 7 0 0 0-7-7z"/><line x1="9" y1="21" x2="15" y2="21"/></svg><span>思考过程</span><svg class="thinking-history-chevron" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>';

    var body = document.createElement('div');
    body.className = 'thinking-history-body';
    body.style.display = 'none';

    var track = document.createElement('div');
    track.className = 'thinking-track';
    var html = '';
    for (var i = 0; i < stages.length; i++) {
        var s = stages[i];
        var status = s.status || 'completed';
        var icon = status === 'completed' ? '\u2713' : (status === 'error' ? '!' : '');
        html += '<div class="thinking-node ' + status + '">';
        html += '<div class="thinking-node-icon">' + icon + '</div>';
        html += '<span class="thinking-node-name">' + _escHtml(s.stage_name || s.stage_id || '') + '</span>';
        html += '</div>';
        if (i < stages.length - 1) {
            html += '<div class="thinking-connector ' + (status === 'completed' ? 'completed' : '') + '"></div>';
        }
    }
    track.innerHTML = html;
    body.appendChild(track);
    container.appendChild(header);
    container.appendChild(body);

    header.onclick = function() {
        var isHidden = body.style.display === 'none';
        body.style.display = isHidden ? 'block' : 'none';
        header.classList.toggle('expanded', isHidden);
    };
    return container;
}

function _renderProgressBar(st) {
    var track = st.thinking.trackEl;
    if (!track) return;
    var stages = st.thinking.stages;
    var html = '';

    for (var i = 0; i < stages.length; i++) {
        var s = stages[i];
        var status = s.status;
        var iconContent = '';
        if (status === 'completed') {
            iconContent = '\u2713'; // ✓
        } else if (status === 'error') {
            iconContent = '!';
        } else if (status === 'processing') {
            iconContent = ''; // 空心
        }
        html += '<div class="thinking-node ' + status + '" data-stage-id="' + s.stage_id + '" onclick="var st=window._streamState;if(st&&st.thinking&&st.thinking.stages){_selectStageDetail(st,\'' + s.stage_id + '\')}" title="' + _escHtml(s.stage_name || s.stage_id) + (status === 'pending' ? ' (待执行)' : '') + '">';
        html += '<div class="thinking-node-icon">' + iconContent + '</div>';
        html += '<span class="thinking-node-name">' + _escHtml(s.stage_name || s.stage_id) + '</span>';
        html += '</div>';

        // 连接线（最后一个节点不加）
        if (i < stages.length - 1) {
            // completed 阶段后的连接线也用 completed 样式
            var connClass = (status === 'completed') ? 'completed' : (status === 'error' ? 'error' : '');
            html += '<div class="thinking-connector ' + connClass + '"></div>';
        }
    }

    track.innerHTML = html;

    // 更新节点 DOM 引用
    var nodes = track.querySelectorAll('.thinking-node');
    for (var j = 0; j < stages.length; j++) {
        if (j < nodes.length) stages[j].nodeEl = nodes[j];
    }

    // 自动滚动到当前进行中的节点
    for (var k = 0; k < stages.length; k++) {
        if (stages[k].status === 'processing' && stages[k].nodeEl) {
            _scrollCurrentNode(track, stages[k].nodeEl);
            break;
        }
    }
}

function _scrollCurrentNode(container, nodeEl) {
    if (!container || !nodeEl) return;
    var cLeft = container.scrollLeft;
    var cWidth = container.clientWidth;
    var nLeft = nodeEl.offsetLeft;
    var nWidth = nodeEl.offsetWidth;
    var target = nLeft - (cWidth / 2) + (nWidth / 2);
    container.scrollTo({left: Math.max(0, target), behavior: 'smooth'});
}

function _selectStageDetail(st, stageId) {
    if (!st || !st.thinking) return;
    if (st.thinking.selectedStageId === stageId) {
        // 再次点击同一节点 → 收起
        st.thinking.detailEl.classList.remove('active');
        st.thinking.selectedStageId = null;
        return;
    }

    // 查找阶段
    var stage = null;
    for (var i = 0; i < st.thinking.stages.length; i++) {
        if (st.thinking.stages[i].stage_id === stageId) {
            stage = st.thinking.stages[i];
            break;
        }
    }
    if (!stage || stage.status === 'pending') return;

    st.thinking.selectedStageId = stageId;
    st.thinking.detailTitle.textContent = '当前阶段：' + (stage.stage_name || stageId);

    // 构建详情内容
    var content = stage.content || '';
    if (!content.trim()) {
        content = '本阶段无详细记录';
    }
    // 如果有工具调用信息，显示出来
    if (stage.tool_name && stage.tool_arguments) {
        content += '\n\n---\n工具: ' + stage.tool_name;
        try {
            var args = typeof stage.tool_arguments === 'string' ? JSON.parse(stage.tool_arguments) : stage.tool_arguments;
            content += '\n参数: ' + JSON.stringify(args, null, 2);
        } catch(e) {}
    }
    content += '\n\n耗时: ' + (stage.start_timestamp ? new Date(stage.start_timestamp * 1000).toLocaleTimeString() : '—');
    if (stage.end_timestamp) {
        var dur = stage.end_timestamp - stage.start_timestamp;
        content += ' → ' + new Date(stage.end_timestamp * 1000).toLocaleTimeString() + ' (' + dur + 's)';
    }

    st.thinking.detailContent.textContent = content;
    st.thinking.detailEl.classList.add('active');
}

function _skipThinking(st) {
    if (!st || !st.thinking || st.thinking.globalStatus !== 'processing') return;
    _finishThinking(st);
    // 如果有已收到的内容，立即显示
    _updateStreamDisplay(st);
}

function _copyStageDetail() {
    var st = window._streamState;
    if (!st || !st.thinking || !st.thinking.detailContent) return;
    var text = st.thinking.detailContent.textContent;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).catch(function(){});
    }
}

function _escHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
// ===== END 阶段节点式思考过程组件 =====

// ===== 全局 SSE 流式显示函数（sendMsg 和 regenerateResponse 共用） =====
function _updateStreamDisplay(st) {
    if (!st.active) return;
    var el = document.getElementById('stream-text');
    if (!el) return;
    if (st.firstChunk && st.streamContent) {
        var typing = el.querySelector('.chat-typing');
        if (typing) typing.remove();
        st.firstChunk = false;
    }
    if (st.streamContent) {
        // 隐藏占位文字
        if (st.thinking.placeholderEl) st.thinking.placeholderEl.style.display = 'none';
        // 创建/更新答案内容区
        if (!st.thinking.answerEl) {
            st.thinking.answerEl = document.createElement('div');
            st.thinking.answerEl.id = 'stream-content';
            el.appendChild(st.thinking.answerEl);
        }
        st.thinking.answerEl.innerHTML = md(st.streamContent);
    }
    scrollEnd();
}

function _makeProcessChunk(st, reader, decoder, sid) {
    var buffer = '';
    return function processChunk(result) {
        if (result.done) {
            _finishThinking(st);
            _updateStreamDisplay(st);
            st.done = true;
            st.active = false;
            window._streamState = null;
            restoreSendBtn();
            scrollEnd();
            loadMsgs(sid);
            return;
        }

        buffer += decoder.decode(result.value, {stream: true});
        var lines = buffer.split('\n');
        buffer = lines.pop();

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (line.startsWith('data: ')) {
                try {
                    var data = JSON.parse(line.substring(6));
                    if (data.done) {
                        if (data.session_name) {
                            var nameEl = document.getElementById('chat-header-name');
                            if (nameEl) nameEl.textContent = data.session_name;
                        }
                        loadHistory();
                        _finishThinking(st);
                        _updateStreamDisplay(st);
                        st.done = true;
                        st.active = false;
                        window._streamState = null;
                        restoreSendBtn();
                        scrollEnd();
                        loadMsgs(sid);
                        return;
                    } else if (data.stage_start) {
                        _handleStageStart(st, data.stage_start);
                    } else if (data.stage_end) {
                        _handleStageEnd(st, data.stage_end);
                    } else if (data.thinking_done) {
                        _finishThinking(st);
                    } else if (data.chunk) {
                        st.streamContent += data.chunk;
                        _updateStreamDisplay(st);
                    } else if (data.heartbeat) {
                        // heartbeat - 忽略
                    }
                } catch (e) { console.error('[SSE chunk error]', e); }
            }
        }

        return reader.read().then(processChunk);
    };
}

function _streamCatch(err, sid) {
    window._streamState = null;
    restoreSendBtn();
    if (err && err.name === 'AbortError') {
        var sb = document.getElementById('stream-bubble');
        if (sb) {
            var textEl = document.getElementById('stream-text');
            var contentEl = document.getElementById('stream-content');
            var target = contentEl || textEl;
            if (target && target.textContent.trim()) {
                target.innerHTML += '<br><br><span style="color: var(--color-muted); font-size: 12px;">_[已停止生成]_</span>';
            }
            sb.removeAttribute('id');
        }
        scrollEnd();
        if (sid) loadMsgs(sid);
    } else {
        console.error('[SSE Error]', err);
    }
}

function createStreamState(sid, userMessage, ac) {
    return {
        active: true,
        sessionId: sid,
        userMessage: userMessage,
        abortController: ac,
        streamContent: '',
        thinkingContainer: null,
        thinking: {
            stages: [],
            currentStageId: null,
            globalStatus: 'processing',
            selectedStageId: null,
            processEl: null,
            trackEl: null,
            skipBtn: null,
            detailEl: null,
            detailTitle: null,
            detailContent: null,
            placeholderEl: null,
            answerEl: null
        },
        done: false,
        firstChunk: true
    };
}

function createStreamBubble(insertAfter) {
    // Remove old stream bubble if exists
    var oldStream = document.getElementById('stream-text');
    if (oldStream) oldStream.removeAttribute('id');

    var streamBubble = document.createElement('div');
    streamBubble.className = 'chat-bubble-row assistant';
    streamBubble.id = 'stream-bubble';
    streamBubble.innerHTML = '<div class="chat-bubble-wrap"><div class="chat-bubble md-body" id="stream-text"><div class="chat-typing">'
        + '<span></span><span></span><span></span></div></div></div>';

    if (insertAfter && insertAfter.parentNode) {
        insertAfter.parentNode.insertBefore(streamBubble, insertAfter.nextSibling);
    } else {
        document.getElementById('chat-messages-scroll').appendChild(streamBubble);
    }
    return streamBubble;
}

function _startStreamFetch(url, body, sid, ac, onError) {
    fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
        signal: ac.signal
    }).then(function(response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        var st = window._streamState;
        if (!st) return;
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var processChunk = _makeProcessChunk(st, reader, decoder, sid);
        return reader.read().then(processChunk);
    }).catch(function(err) {
        if (onError) { onError(err); } else { _streamCatch(err, sid); }
    });
}

function loadConfig() {
    fetch('/api/chat/active-config').then(function(r) { return r.json(); }).then(function(res) {
        var el = document.getElementById('chat-header-model');
        if (res.code === 200 && res.data) {
            el.textContent = res.data.name || (res.data.provider + '/' + res.data.model);
        } else {
            el.textContent = '未配置';
        }
    });
}

function loadHistory() {
    fetch('/api/chat/sessions')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.code === 200) {
                renderHistory(res.data);
            } else {
                renderHistory([]);
                console.warn('loadHistory failed:', res.message);
            }
        })
        .catch(function(e) {
            renderHistory([]);
            console.error('loadHistory error:', e);
        });
}

function renderHistory(list) {
    var el = document.getElementById('chat-history');
    if (!el) return;
    if (!list || list.length === 0) {
        el.innerHTML = '<div class="chat-history-empty"><svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:8px; opacity:0.4"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5M12 3v12"/></svg><span>暂无历史对话</span></div>';
        return;
    }
    var h = '';
    list.forEach(function(s) {
        var cls = s.id === sid ? ' active' : '';
        h += '<div class="chat-history-item' + cls + '" onclick="selectSession(' + s.id + ')">';
        h += '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="chat-history-item-icon"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
        h += '<span class="chat-history-item-text" onclick="handleTitleClick(event, ' + s.id + ')" ondblclick="startRenameSession(event, ' + s.id + ')" title="双击修改标题">' + esc(s.name) + '</span>';
        h += '<button class="chat-history-item-del" onclick="event.stopPropagation();delSession(' + s.id + ')" aria-label="删除"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>';
        h += '</div>';
    });
    el.innerHTML = h;
}

function esc(t) {
    var d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}

var _COPY_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
var _CHECK_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

function makeCopyBtn(content) {
    var btn = document.createElement('button');
    btn.className = 'chat-action-btn';
    btn.title = '复制';
    btn.innerHTML = _COPY_SVG;
    btn.onclick = function(e) {
        e.stopPropagation();
        navigator.clipboard.writeText(content).then(function() {
            btn.innerHTML = _CHECK_SVG;
            btn.style.color = 'var(--color-success, #22c55e)';
            setTimeout(function() { btn.innerHTML = _COPY_SVG; btn.style.color = ''; }, 1500);
        });
    };
    return btn;
}

function createNewSession(cb) {
    fetch('/api/chat/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
    }).then(function(r) { return r.json(); }).then(function(c) {
        if (c.code === 200) {
            sid = c.data.id;
            localStorage.setItem('chat_sid', sid);
            document.getElementById('chat-header-name').textContent = c.data.name || '新对话';
            loadHistory();
            showChat();
            clearMsgs();
            document.getElementById('chat-input').focus();
            if (cb) cb();
        } else {
            showToast(c.message || '创建失败');
        }
    });
}

function selectSession(id) {
    sid = id;
    localStorage.setItem('chat_sid', sid);
    loadHistory();
    showChat();
    resetRightPanel();
    // 切换会话时关闭预览面板
    var panel = document.getElementById('chat-right-panel');
    var handle = document.getElementById('panel-resize-handle');
    var btn = document.getElementById('panel-toggle-btn');
    if (panel && !panel.classList.contains('collapsed')) {
        panel.classList.add('collapsed');
        if (btn) btn.classList.remove('active');
        if (handle) handle.style.display = 'none';
    }
    if (window._streamState && window._streamState.sessionId === id && !window._streamState.done) {
        resumeStream();
    } else {
        loadMsgs(id);
    }
}

function delSession(id) {
    customConfirm('删除后无法恢复，是否继续？', '删除对话').then(function(ok) {
        if (!ok) return;
        _doDelSession(id);
    });
}

function _doDelSession(id) {
    if (window._streamState && window._streamState.sessionId === id) {
        abortStream();
    }
    fetch('/api/chat/sessions/' + id, { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.code === 200) {
                if (sid === id) { sid = null; localStorage.removeItem('chat_sid'); hideChat(); }
                loadHistory();
            }
        });
}

var _titleClickTimer = null;

function handleTitleClick(e, id) {
    // 双击编辑时阻止单击触发 selectSession
    e.stopPropagation();
    if (_titleClickTimer) {
        clearTimeout(_titleClickTimer);
        _titleClickTimer = null;
        return; // double-click in progress
    }
    _titleClickTimer = setTimeout(function() {
        _titleClickTimer = null;
        selectSession(id);
    }, 350);
}

function startRenameSession(e, id) {
    e.stopPropagation();
    if (_titleClickTimer) { clearTimeout(_titleClickTimer); _titleClickTimer = null; }
    var span = e.target;
    if (span.querySelector('input')) return; // already editing
    var origName = span.textContent;
    span.innerHTML = '<input class="rename-input" value="' + esc(origName) + '" maxlength="100" />';
    var inp = span.querySelector('input');
    inp.focus();
    inp.select();
    function finish() {
        var newName = inp.value.trim();
        if (!newName || newName === origName) {
            span.textContent = origName;
        } else {
            renameSession(id, newName, span);
        }
    }
    inp.addEventListener('blur', finish);
    inp.addEventListener('keydown', function(ev) {
        if (ev.key === 'Enter') { inp.blur(); }
        if (ev.key === 'Escape') { span.textContent = origName; }
    });
}

function renameSession(id, newName, span) {
    fetch('/api/chat/sessions/' + id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ name: newName })
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.code === 200) {
            span.textContent = newName;
            // 同步更新头部标题
            var hTitle = document.getElementById('chat-header-name');
            if (hTitle && sid === id) hTitle.textContent = newName;
        } else {
            span.textContent = span.getAttribute('data-orig') || '';
            showToast(res.message || '修改失败');
        }
    });
}

function showChat() {
    document.getElementById('chat-welcome').style.display = 'none';
    document.getElementById('chat-header').style.display = 'flex';
    document.getElementById('chat-messages').style.display = 'block';
    document.getElementById('chat-input-bar').style.display = 'block';
}

function hideChat() {
    document.getElementById('chat-welcome').style.display = 'flex';
    document.getElementById('chat-header').style.display = 'none';
    document.getElementById('chat-messages').style.display = 'none';
    document.getElementById('chat-input-bar').style.display = 'block';
}

function clearMsgs() {
    var el = document.getElementById('chat-messages-scroll');
    if (el) el.innerHTML = '';
}

function loadMsgs(id) {
    fetch('/api/chat/sessions/' + id).then(function(r) { return r.json(); }).then(function(res) {
        if (res.code === 200 && res.data) {
            clearMsgs();
            if (res.data.session) {
                document.getElementById('chat-header-name').textContent = res.data.session.name || '对话';
            }
            if (res.data.messages) {
                res.data.messages.forEach(function(m) {
                    if (m.role === 'assistant' && !m.content) {
                        return;
                    }
                    addBubble(m.role, m.content, m.created_at, m.id, null, m.exported_files, m.thinking_json);
                });
            }
            scrollEnd();
        }
    });
}

function addBubble(role, content, time, msgId, attachments, exportedFiles, thinkingJson) {
    var c = document.getElementById('chat-messages-scroll');
    if (!c) return;
    var row = document.createElement('div');
    row.className = 'chat-bubble-row ' + role;
    if (msgId) row.setAttribute('data-msg-id', msgId);

    var wrap = document.createElement('div');
    wrap.className = 'chat-bubble-wrap';

    var bub = document.createElement('div');
    bub.className = 'chat-bubble md-body';
    if (role === 'assistant') {
        bub.innerHTML = md(content || '');
    } else {
        // 附件胶囊：优先使用传入的 attachments 数据，否则从 content 中解析 [附件: xxx]
        var attachNames = [];
        var cleanContent = content || '';

        if (attachments && attachments.length > 0) {
            attachments.forEach(function(att) { attachNames.push({label: att.label, savedName: att.savedName || ''}); });
            // 如果有 attachments，content 不应包含 [附件: xxx]，但以防万一
            var m = cleanContent.match(/\n?\n?\[附件:\s*(.+?)\]$/);
            if (m) cleanContent = cleanContent.substring(0, m.index).replace(/\n+$/, '');
        } else {
            var attachMatch = cleanContent.match(/\n?\n?\[附件:\s*(.+?)\]$/);
            if (attachMatch) {
                cleanContent = cleanContent.substring(0, attachMatch.index).replace(/\n+$/, '');
                var raw = attachMatch[1];
                attachNames = raw.split(',').map(function(s) {
                    var parts = s.trim().split('#');
                    return { label: parts[0].trim(), savedName: parts[1] ? parts[1].trim() : '' };
                }).filter(function(x) { return x.label; });
            }
        }

        // 渲染附件胶囊
        if (attachNames.length > 0) {
            var attachRow = document.createElement('div');
            attachRow.className = 'chat-bubble-attachments';
            attachNames.forEach(function(att) {
                var pill = document.createElement('span');
                pill.className = 'chat-attach-pill';
                pill.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg><span></span>';
                if (pill.lastChild) pill.lastChild.textContent = att.label;
                if (att.savedName) {
                    pill.setAttribute('data-saved-name', att.savedName);
                    pill.style.cursor = 'pointer';
                    pill.title = '点击预览附件';
                    (function(sn, lb) {
                        pill.onclick = function() { previewAttachment(sn, lb); };
                    })(att.savedName, att.label);
                }
                attachRow.appendChild(pill);
            });
            wrap.appendChild(attachRow);
        }
        var p = document.createElement('p');
        p.style.margin = '0';
        p.textContent = cleanContent;
        bub.appendChild(p);
    }
    wrap.appendChild(bub);

    // 助手消息：如果有思考过程，渲染可折叠的历史思考面板
    if (role === 'assistant' && thinkingJson) {
        try {
            var _tj = JSON.parse(thinkingJson);
            if (_tj && _tj.stages && _tj.stages.length > 1) {
                var _thinkEl = _createStaticThinking(_tj.stages);
                wrap.insertBefore(_thinkEl, wrap.firstChild);
            }
        } catch(e) {}
    }

    // 助手消息：渲染导出文件胶囊
    if (role === 'assistant' && exportedFiles && exportedFiles.length > 0) {
        var exportRow = document.createElement('div');
        exportRow.className = 'chat-bubble-exports';
        exportedFiles.forEach(function(f) {
            var pill = document.createElement('span');
            pill.className = 'chat-export-pill';
            pill.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M12 18v-6"/><path d="M9 15l3 3 3-3"/></svg><span></span>';
            if (pill.lastChild) pill.lastChild.textContent = f.filename;
            pill.style.cursor = 'pointer';
            pill.title = '点击预览，可下载';
            (function(fn) {
                pill.onclick = function() { previewExportedFile(fn); };
            })(f.filename);
            exportRow.appendChild(pill);
        });
        wrap.appendChild(exportRow);
    }

    // 回答下方：时间 + 操作按钮（复制、重新生成）
    if (role === 'assistant') {
        var actionsBar = document.createElement('div');
        actionsBar.className = 'chat-bubble-actions';
        if (msgId) {
            actionsBar.appendChild(makeCopyBtn(content));

            // 重新生成按钮
            var regenBtn = document.createElement('button');
            regenBtn.className = 'chat-action-btn';
            regenBtn.title = '重新生成';
            regenBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/></svg>';
            regenBtn.onclick = function(e) {
                e.stopPropagation();
                regenerateFromAssistant(row);
            };
            actionsBar.appendChild(regenBtn);
        }
        if (time) {
            var t = document.createElement('span');
            t.className = 'chat-bubble-time';
            t.textContent = fmtTime(time);
            actionsBar.appendChild(t);
        }
        wrap.appendChild(actionsBar);
    } else {
        // 用户消息下方操作栏：复制、修改、三点菜单（含删除）
        var userActions = document.createElement('div');
        userActions.className = 'chat-bubble-actions';
        if (msgId) {
            userActions.appendChild(makeCopyBtn(content));

            // 修改按钮
            var editBtn = document.createElement('button');
            editBtn.className = 'chat-action-btn';
            editBtn.title = '修改并重新生成';
            editBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>';
            editBtn.onclick = function(e) { e.stopPropagation(); editUserBubble(bub, msgId, row, content); };
            userActions.appendChild(editBtn);

            // 三点菜单
            var moreBtn = document.createElement('button');
            moreBtn.className = 'chat-action-btn';
            moreBtn.title = '更多';
            moreBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>';
            moreBtn.onclick = function(e) { e.stopPropagation(); toggleMsgMenu(moreBtn, msgId, row); };
            userActions.appendChild(moreBtn);
        }
        if (time) {
            var t = document.createElement('span');
            t.className = 'chat-bubble-time';
            t.textContent = fmtTime(time);
            userActions.appendChild(t);
        }
        wrap.appendChild(userActions);
    }

    row.appendChild(wrap);

    c.appendChild(row);
    return row;
}

// ===== Right Panel Management =====

function toggleRightPanel() {
    var panel = document.getElementById('chat-right-panel');
    var btn = document.getElementById('panel-toggle-btn');
    var handle = document.getElementById('panel-resize-handle');
    if (panel.classList.contains('collapsed')) {
        panel.classList.remove('collapsed');
        if (btn) btn.classList.add('active');
        if (handle) handle.style.display = '';
    } else {
        panel.classList.add('collapsed');
        if (btn) btn.classList.remove('active');
        if (handle) handle.style.display = 'none';
    }
}

function resetRightPanel() {
    var contentEl = document.getElementById('panel-doc-content');
    var emptyEl = document.getElementById('panel-doc-empty');
    var titleEl = document.getElementById('panel-doc-title');
    if (contentEl) { contentEl.style.display = 'none'; contentEl.innerHTML = ''; }
    if (emptyEl) emptyEl.style.display = 'block';
    if (titleEl) titleEl.textContent = '文档预览';
}

// ===== Panel Resize (Drag) =====
var _panelResizeState = { isDragging: false, startX: 0, startWidth: 0 };

function _onPanelResizeMouseDown(e) {
    var panel = document.getElementById('chat-right-panel');
    if (!panel || panel.classList.contains('collapsed')) return;
    _panelResizeState.isDragging = true;
    _panelResizeState.startX = e.clientX;
    _panelResizeState.startWidth = panel.offsetWidth;
    var handle = document.getElementById('panel-resize-handle');
    if (handle) handle.classList.add('active');
    panel.style.transition = 'none';
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
}

function _onPanelResizeMouseMove(e) {
    if (!_panelResizeState.isDragging) return;
    var panel = document.getElementById('chat-right-panel');
    var chatMain = document.querySelector('.chat-main');
    if (!panel || !chatMain) return;
    var dx = _panelResizeState.startX - e.clientX;
    var newWidth = _panelResizeState.startWidth + dx;
    var maxWidth = chatMain.offsetWidth * 0.6;
    newWidth = Math.max(200, Math.min(newWidth, maxWidth));
    panel.style.width = newWidth + 'px';
    panel.style.minWidth = newWidth + 'px';
}

function _onPanelResizeMouseUp() {
    if (!_panelResizeState.isDragging) return;
    _panelResizeState.isDragging = false;
    var handle = document.getElementById('panel-resize-handle');
    var panel = document.getElementById('chat-right-panel');
    if (handle) handle.classList.remove('active');
    if (panel) panel.style.transition = '';
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
}

function _renderPreview(res, opts) {
    /** 共享预览渲染：展开面板 + 设置标题 + 按 type 渲染内容 + 控制下载按钮。 */
    if (res.code !== 200 || !res.data) {
        showToast(res.message || '预览失败');
        return;
    }
    var panel = document.getElementById('chat-right-panel');
    if (panel.classList.contains('collapsed')) {
        panel.classList.remove('collapsed');
        var h = document.getElementById('panel-resize-handle');
        if (h) h.style.display = '';
    }
    var contentEl = document.getElementById('panel-doc-content');
    var emptyEl = document.getElementById('panel-doc-empty');
    var titleEl = document.getElementById('panel-doc-title');
    var dlBtn = document.getElementById('panel-download-btn');
    titleEl.textContent = opts.title || res.data.title || '文档预览';
    var rawContent = res.data.content || '';
    if (res.data.type === 'html') {
        contentEl.innerHTML = rawContent;
    } else if (res.data.type === 'markdown') {
        // 走公共 Md 模块，与文章页/Wiki 渲染一致
        Md.renderInto(rawContent, contentEl, {
            onDone: function(el) {
                // 文档路径转可点击 pill（聊天专属逻辑）
                _decorateDocPills(el);
            }
        });
    } else {
        contentEl.innerHTML = '<p>' + rawContent.replace(/</g, '&lt;').replace(/\n/g, '<br>') + '</p>';
    }
    contentEl.style.display = 'block';
    emptyEl.style.display = 'none';
    if (dlBtn) {
        if (opts.downloadUrl) {
            dlBtn.style.display = '';
            dlBtn.onclick = function() { window.open(opts.downloadUrl, '_blank'); };
        } else {
            dlBtn.style.display = 'none';
        }
    }
    scrollEnd();
}

function previewDoc(path) {
    fetch('/api/chat/preview-doc?path=' + encodeURIComponent(path))
        .then(function(r) { return r.json(); })
        .then(function(res) { _renderPreview(res, {title: res.data && res.data.title}); })
        .catch(function() { showToast('预览失败'); });
}

function previewAttachment(savedName, filename) {
    showToast('正在加载附件...');
    fetch('/api/chat/preview-attachment?file=' + encodeURIComponent(savedName))
        .then(function(r) { return r.json(); })
        .then(function(res) { _renderPreview(res, {title: filename}); })
        .catch(function() { showToast('预览失败'); });
}

function previewExportedFile(filename) {
    showToast('正在加载文件...');
    fetch('/api/chat/file-exports/preview?file=' + encodeURIComponent(filename))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            _renderPreview(res, {
                title: filename,
                downloadUrl: '/api/chat/file-exports/download?file=' + encodeURIComponent(filename),
            });
        })
        .catch(function() { showToast('预览失败'); });
}

function deleteMsgPair(msgId, userRow) {
    // 识别问答对，画一个大框高亮
    var nextRow = userRow.nextElementSibling;
    var isPair = nextRow && nextRow.classList.contains('assistant');
    var rows = isPair ? [userRow, nextRow] : [userRow];
    rows.forEach(function(r) { r.classList.add('deleting'); });

    // 创建覆盖大框
    var container = document.getElementById('chat-messages-scroll') || userRow.parentNode;
    var cRect = container.getBoundingClientRect();
    var topRow = rows[0].getBoundingClientRect();
    var botRow = rows[rows.length - 1].getBoundingClientRect();
    var hlBox = document.createElement('div');
    hlBox.className = 'deleting-highlight-box';
    hlBox.id = 'deleting-highlight-box';
    hlBox.style.top = (topRow.top - cRect.top - 4) + 'px';
    hlBox.style.left = (Math.min(topRow.left, botRow.left) - cRect.left - 8) + 'px';
    hlBox.style.width = (Math.max(topRow.right, botRow.right) - Math.min(topRow.left, botRow.left) + 16) + 'px';
    hlBox.style.height = (botRow.bottom - topRow.top + 8) + 'px';
    // 确保容器是 relative
    if (getComputedStyle(container).position === 'static') container.style.position = 'relative';
    container.appendChild(hlBox);

    customConfirm('将同时删除提问和回答，是否继续？', '删除问答').then(function(ok) {
        hlBox.remove();
        rows.forEach(function(r) { r.classList.remove('deleting'); });
        if (!ok) return;
        fetch('/api/chat/messages/' + msgId, { method: 'DELETE' })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.code === 200) {
                    rows.forEach(function(r) { r.remove(); });
                } else {
                    showToast(res.message || '删除失败');
                }
            });
    });
}

function toggleMsgMenu(btn, msgId, row) {
    // 关闭已有的菜单
    var existing = document.getElementById('msg-context-menu');
    if (existing) { existing.remove(); return; }

    var menu = document.createElement('div');
    menu.id = 'msg-context-menu';
    menu.className = 'msg-context-menu';
    menu.innerHTML =
        '<div class="msg-menu-item" data-action="delete">'
        + '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>'
        + '<span>删除问答</span></div>';

    document.body.appendChild(menu);
    var rect = btn.getBoundingClientRect();
    menu.style.top = (rect.bottom + 4) + 'px';
    menu.style.left = rect.left + 'px';

    menu.querySelector('[data-action="delete"]').onclick = function() {
        menu.remove();
        if (closeHandler) document.removeEventListener('click', closeHandler);
        deleteMsgPair(msgId, row);
    };

    // 点击外部关闭
    var closeHandler = null;
    setTimeout(function() {
        closeHandler = function(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeHandler);
            }
        };
        document.addEventListener('click', closeHandler);
    }, 0);
}

function editUserBubble(bubbleEl, msgId, row, originalContent) {
    // 如果已经在编辑中，跳过
    if (bubbleEl.querySelector('.bubble-edit-area')) return;

    // 提取 [附件: label#savedName] 部分，编辑时剥离
    var attachSuffix = '';
    var cleanContent = originalContent;
    var attachMatch = originalContent.match(/\n?\n?\[附件:\s*(.+?)\]$/);
    if (attachMatch) {
        attachSuffix = originalContent.substring(attachMatch.index);
        cleanContent = originalContent.substring(0, attachMatch.index).replace(/\n+$/, '');
    }

    // 保存原始内容
    var originalHTML = bubbleEl.innerHTML;
    bubbleEl.innerHTML = '';

    var textarea = document.createElement('textarea');
    textarea.className = 'bubble-edit-area';
    textarea.value = cleanContent;
    bubbleEl.appendChild(textarea);
    textarea.focus();
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    textarea.addEventListener('input', function() {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    });

    var btnBar = document.createElement('div');
    btnBar.className = 'bubble-edit-btns';
    btnBar.innerHTML =
        '<button class="bubble-edit-cancel">取消</button>'
        + '<button class="bubble-edit-confirm">确认并发送</button>';
    bubbleEl.appendChild(btnBar);

    // 取消
    btnBar.querySelector('.bubble-edit-cancel').onclick = function(e) {
        e.stopPropagation();
        bubbleEl.innerHTML = originalHTML;
    };

    // 确认：更新消息内容，删除旧回复，重新生成
    btnBar.querySelector('.bubble-edit-confirm').onclick = function(e) {
        e.stopPropagation();
        var newContent = textarea.value.trim();
        if (attachSuffix) newContent = newContent + attachSuffix;
        if (!newContent || newContent === originalContent) {
            bubbleEl.innerHTML = originalHTML;
            return;
        }
        regenerateResponse(msgId, newContent, row, bubbleEl, originalHTML);
    };
}

function regenerateFromAssistant(assistantRow) {
    if (window._streamState && window._streamState.active) return;
    // 找到上一条用户消息
    var userRow = assistantRow.previousElementSibling;
    if (!userRow || !userRow.classList.contains('user')) return;

    var userMsgId = userRow.getAttribute('data-msg-id');
    var userBubble = userRow.querySelector('.chat-bubble');
    var userContent = userBubble.textContent || '';

    // 删除当前 assistant 回复
    assistantRow.remove();

    // 调用后端 regenerate（不需修改内容，直接重新生成）
    if (!sid || !userMsgId) return;

    // 创建 stream bubble
    createStreamBubble(userRow);
    scrollEnd();

    // 切换发送按钮为停止状态
    var btn = document.getElementById('chat-send-btn');
    btn.classList.add('streaming');
    btn.setAttribute('aria-label', '停止生成');
    btn.onclick = function() { stopGeneration(); };

    var ac = new AbortController();
    window._streamState = createStreamState(sid, userContent, ac);

    _startStreamFetch('/api/chat/sessions/' + sid + '/regenerate', {
        message_id: parseInt(userMsgId),
        content: userContent,
        mode: _chatMode
    }, sid, ac);
}

function regenerateResponse(msgId, newContent, userRow, bubbleEl, fallbackHTML) {
    if (window._streamState && window._streamState.active) return;
    // 更新用户消息内容（后端 + 前端）
    fetch('/api/chat/messages/' + msgId + '/edit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ content: newContent })
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.code !== 200) {
            showToast(res.message || '修改失败');
            bubbleEl.innerHTML = fallbackHTML;
            return;
        }

        // 恢复气泡为正常显示（非编辑态），剥离 [附件: ...] 避免与胶囊重复
        var displayText = newContent.replace(/\n?\n?\[附件:\s*.+?\]$/, '');
        var p = document.createElement('p');
        p.style.margin = '0';
        p.textContent = displayText || newContent;
        bubbleEl.innerHTML = '';
        bubbleEl.appendChild(p);

        // 删除旧的 assistant 回复
        var nextRow = userRow.nextElementSibling;
        if (nextRow && nextRow.classList.contains('assistant')) nextRow.remove();

        // 用新内容触发流式重新生成
        if (!sid || !userMsgId) return;

        // 创建 stream bubble
        createStreamBubble(userRow);

        var btn = document.getElementById('chat-send-btn');
        btn.classList.add('streaming');
        btn.setAttribute('aria-label', '停止生成');
        btn.onclick = function() { stopGeneration(); };

        var ac = new AbortController();
        window._streamState = createStreamState(sid, newContent, ac);

        scrollEnd();

        _startStreamFetch('/api/chat/sessions/' + sid + '/regenerate', {
            message_id: msgId,
            content: newContent,
            mode: _chatMode
        }, sid, ac);
    }).catch(function(err) {
        console.error('[Edit Error]', err);
        customAlert('修改失败: ' + (err && err.message ? err.message : '网络错误'), '修改失败');
        bubbleEl.innerHTML = fallbackHTML;
    });
}

function fmtTime(iso) {
    if (!iso) return '';
    try {
        var d = new Date(iso);
        var diff = Date.now() - d;
        if (diff < 60000) return '刚刚';
        if (diff < 3600000) return Math.floor(diff / 60000) + ' 分钟前';
        if (diff < 86400000) return Math.floor(diff / 3600000) + ' 小时前';
        return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
    } catch (e) { return ''; }
}

/**
 * 文档路径装饰：将容器内文本中的 .md/.txt 路径转换为可点击 pill。
 * 聊天专属逻辑，从原 md() 函数提取，在 Md.renderInto 完成后调用。
 */
function _decorateDocPills(container) {
    if (!container) return;
    var fileSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>';
    var pathRe = /(?<!["'\w\/])([\u4e00-\u9fa5\w][\u4e00-\u9fa5\w\/\s-]*?\.(?:md|txt|markdown))(?!["'\w\/])/g;

    // 遍历文本节点（跳过 a/code/pre 内的）
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
        acceptNode: function(node) {
            var p = node.parentNode;
            if (!p) return NodeFilter.FILTER_REJECT;
            var tag = p.nodeName.toLowerCase();
            if (tag === 'a' || tag === 'code' || tag === 'pre' || tag === 'script') {
                return NodeFilter.FILTER_REJECT;
            }
            return pathRe.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        }
    });

    var nodes = [];
    var n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function(node) {
        var text = node.nodeValue;
        pathRe.lastIndex = 0;
        if (!pathRe.test(text)) return;
        pathRe.lastIndex = 0;

        var frag = document.createDocumentFragment();
        var last = 0;
        var m;
        while ((m = pathRe.exec(text)) !== null) {
            if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
            var trimmed = m[0].trim();
            var label = trimmed.replace(/^.*[\/\\]/, '');
            var span = document.createElement('span');
            span.className = 'doc-file-pill';
            span.title = trimmed;
            span.setAttribute('onclick', "event.stopPropagation();previewDoc('" + trimmed.replace(/'/g, "\\'") + "')");
            span.innerHTML = fileSvg + '<span class="pill-label">' + label + '</span>';
            frag.appendChild(span);
            last = m.index + m[0].length;
        }
        if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
        node.parentNode.replaceChild(frag, node);
    });
}

function md(text) {
    if (!text) return '';
    var mdInline = function(t) {
        var _esc = function(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };
        var _inlineFmt = function(s) {
            return s.replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*([^*]+?)\*/g, '<em>$1</em>')
                .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img alt="$1" src="$2">')
                .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
        };
        var blocks = [];
        t = t.replace(/```(\w*)\n([\s\S]*?)```/g, function(m) {
            var code = m.replace(/^```\w*\n/, '').replace(/\n```$/, '');
            blocks.push('<pre><code>' + _esc(code) + '</code></pre>');
            return '\x01B' + (blocks.length - 1) + '\x01';
        });
        t = t.replace(/^###### (.+)$/gm, function(_, c) { blocks.push('<h6>' + _inlineFmt(_esc(c)) + '</h6>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/^##### (.+)$/gm, function(_, c) { blocks.push('<h5>' + _inlineFmt(_esc(c)) + '</h5>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/^#### (.+)$/gm, function(_, c) { blocks.push('<h4>' + _inlineFmt(_esc(c)) + '</h4>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/^### (.+)$/gm, function(_, c) { blocks.push('<h3>' + _inlineFmt(_esc(c)) + '</h3>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/^## (.+)$/gm, function(_, c) { blocks.push('<h2>' + _inlineFmt(_esc(c)) + '</h2>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/^# (.+)$/gm, function(_, c) { blocks.push('<h1>' + _inlineFmt(_esc(c)) + '</h1>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        // blockquote: 合并连续 > 行为单个引用块，内部递归处理代码块/列表/行内格式
        t = t.replace(/^((?:>.*(?:\r?\n|$))+)/gm, function(_, block) {
            var lines = block.replace(/\r/g, '').split('\n');
            var inner = lines.map(function(l) { return l.replace(/^>\s?/, ''); }).join('\n');
            // 内部代码块
            var codeBlocks = [];
            inner = inner.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
                codeBlocks.push(code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'));
                return '\x02C' + (codeBlocks.length - 1) + '\x02';
            });
            // 内部列表项
            inner = inner.replace(/^[-*] (.+)$/gm, '• $1');
            // HTML 转义
            inner = inner.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            // 行内格式
            inner = inner.replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
                .replace(/\*([^*]+?)\*/g, '<em>$1</em>')
                .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
            // 段落分割
            var paras = inner.split(/\n\n+/).filter(function(p) { return p.trim(); });
            var bqHtml = paras.map(function(p) {
                return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
            }).join('');
            // 恢复代码块
            bqHtml = bqHtml.replace(/\x02C(\d+)\x02/g, function(_, i) {
                return '</p><pre><code>' + codeBlocks[parseInt(i)] + '</code></pre><p>';
            });
            blocks.push('<blockquote>' + bqHtml + '</blockquote>');
            return '\x01B' + (blocks.length - 1) + '\x01';
        });
        t = t.replace(/^---+$/gm, function() { blocks.push('<hr>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        // 表格支持: | col1 | col2 |\n|---|---|\n| a | b |
        t = t.replace(/^\|(.+)\|\s*\n\|([-:\s|]+)\|\s*\n((?:\|.+\|\s*(?:\n|$))+)/gm, function(_, headerRow, sepRow, bodyRows) {
            var headers = headerRow.split('|').map(function(h){return h.trim();}).filter(function(h){return h!=='';});
            var seps = sepRow.split('|').map(function(s){return s.trim();}).filter(function(s){return s!=='';});
            var aligns = seps.map(function(s){
                if (s.startsWith(':') && s.endsWith(':')) return 'center';
                if (s.endsWith(':')) return 'right';
                return 'left';
            });
            var html = '<table><thead><tr>';
            headers.forEach(function(h, i) {
                html += '<th style="text-align:' + aligns[i] + '">' + _inlineFmt(_esc(h)) + '</th>';
            });
            html += '</tr></thead><tbody>';
            bodyRows.trim().split('\n').forEach(function(row) {
                var cells = row.split('|').map(function(c){return c.trim();});
                // 去掉首尾空元素（因为 | 开头和结尾）
                if (cells[0] === '') cells.shift();
                if (cells[cells.length-1] === '') cells.pop();
                html += '<tr>';
                cells.forEach(function(c, i) {
                    html += '<td style="text-align:' + (aligns[i]||'left') + '">' + _inlineFmt(_esc(c)) + '</td>';
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
            blocks.push(html);
            return '\x01B' + (blocks.length - 1) + '\x01';
        });
        t = t.replace(/^\d+\. (.+)$/gm, function(_, c) { blocks.push('<li>' + _inlineFmt(_esc(c)) + '</li>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/^[-*] (.+)$/gm, function(_, c) { blocks.push('<li>' + _inlineFmt(_esc(c)) + '</li>'); return '\x01B' + (blocks.length - 1) + '\x01'; });
        t = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        t = _inlineFmt(t);
        // blocks.map: 跳过已处理好的 <pre> 和 <blockquote>，只对标题/列表/表格做行内格式
        blocks = blocks.map(function(b) {
            if (b.startsWith('<pre>') || b.startsWith('<blockquote>')) return b;
            return _inlineFmt(b);
        });
        t = t.replace(/\n\n/g, '</p><p>');
        t = t.replace(/\n/g, '<br>');
        t = t.replace(/^/, '<p>').replace(/$/, '</p>');
        t = t.replace(/\x01B(\d+)\x01/g, function(_, i) { return '</p>' + blocks[parseInt(i)] + '<p>'; });
        return t.replace(/<p><\/p>/g, '');
    };
    var htmlBlocks = [];
    text = text.replace(/<details>[\s\S]*?<\/details>/gi, function(m) {
        var rendered = m.replace(/(<details>\s*<summary>[\s\S]*?<\/summary>\s*)([\s\S]*?)(\s*<\/details>)/i, function(_, header, body, footer) {
            return header + mdInline(body) + footer;
        });
        htmlBlocks.push(rendered);
        return '\x00HTML' + (htmlBlocks.length - 1) + '\x00';
    });
    // Pre-process: join file paths split by newlines (需求/\n武水... → 需求/武水...)
    text = text.replace(/([\u4e00-\u9fa5\/-])(?:\r?\n)+([\u4e00-\u9fa5])/g, '$1$2');
    text = mdInline(text);
    text = text.replace(/\x00HTML(\d+)\x00/g, function(_, i) { return '</p>' + htmlBlocks[parseInt(i)] + '<p>'; });
    // Make file paths clickable pills (e.g. 技术/Agent架构.md)
    var fileSvg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>';
    text = text.replace(/(?<!["'])([\u4e00-\u9fa5\w][\u4e00-\u9fa5\w\/\s-]*?\.(?:md|txt|markdown))(?!["'\w\/])/g, function(match) {
        var trimmed = match.trim();
        var label = trimmed.replace(/^.*[\/\\]/, '');
        return '<span class="doc-file-pill" onclick="event.stopPropagation();previewDoc(\'' + trimmed.replace(/'/g, "\\'") + '\')" title="' + trimmed.replace(/"/g, '&quot;') + '">' + fileSvg + '<span class="pill-label">' + label + '</span></span>';
    });
    return text.replace(/<p><\/p>/g, '');
}

function scrollEnd() {
    var el = document.getElementById('chat-messages');
    if (!el) return;
    el.scrollTop = el.scrollHeight;
}

function scrollToBubble(bubbleEl) {
    var container = document.getElementById('chat-messages');
    if (!bubbleEl || !container) return;
    var offset = bubbleEl.offsetTop - container.offsetTop;
    container.scrollTo({ top: offset - 20, behavior: 'smooth' });
}

var _uploadedFiles = [];
var _kbBrowserPath = ''; // 当前浏览的知识库子目录
var _chatMode = 'quick'; // 'quick' or 'expert'

function toggleAddMenu(e) {
    e.stopPropagation();
    var dd = document.getElementById('chat-plus-dropdown');
    dd.classList.toggle('open');
}

function closeAddMenu() {
    var dd = document.getElementById('chat-plus-dropdown');
    dd.classList.remove('open');
}

// Event delegation for dropdown items
function _onPlusDropdownClick(e) {
    var item = e.target.closest('[data-action]');
    if (!item) return;
    var action = item.getAttribute('data-action');
    if (action === 'add-file') {
        var type = item.getAttribute('data-type');
        closeAddMenu();
        if (type === 'local') {
            document.getElementById('chat-file-input').click();
        } else {
            openKbBrowser();
        }
        e.stopPropagation();
    }
}

// ===== Mode Selector =====
function toggleModeMenu(e) {
    e.stopPropagation();
    var dd = document.getElementById('chat-mode-dropdown');
    dd.classList.toggle('open');
}

function closeModeMenu() {
    var dd = document.getElementById('chat-mode-dropdown');
    dd.classList.remove('open');
}

function _onModeDropdownClick(e) {
    var item = e.target.closest('[data-action]');
    if (!item) return;
    if (item.getAttribute('data-action') === 'set-mode') {
        var mode = item.getAttribute('data-mode');
        setChatMode(mode);
        closeModeMenu();
        e.stopPropagation();
    }
}

function setChatMode(mode) {
    _chatMode = mode;
    var label = document.getElementById('chat-mode-label');
    var icon = document.getElementById('chat-mode-icon');
    if (mode === 'expert') {
        label.textContent = '专家';
        icon.innerHTML = '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c0 1 2 3 6 3s6-2 6-3v-5"/>';
    } else {
        label.textContent = '快速';
        icon.innerHTML = '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>';
    }
    // Update active state
    var items = document.querySelectorAll('#chat-mode-dropdown .dd-item');
    items.forEach(function(it) {
        if (it.getAttribute('data-mode') === mode) {
            it.classList.add('active');
        } else {
            it.classList.remove('active');
        }
    });
}

// ===== Model Selector =====
function toggleModelMenu(e) {
    e.stopPropagation();
    var dd = document.getElementById('chat-model-dropdown');
    dd.classList.toggle('open');
}

function loadModels() {
    fetch('/api/chat/model-configs').then(function(r) { return r.json(); }).then(function(res) {
        if (res.code !== 200 || !res.data) return;
        var dd = document.getElementById('chat-model-dropdown');
        var activeId = res.data.active_id;
        var label = document.getElementById('chat-model-label');
        // 清空旧项（保留 dd-head）
        var head = dd.querySelector('.dd-head');
        dd.innerHTML = '';
        dd.appendChild(head);

        res.data.models.forEach(function(m) {
            var item = document.createElement('div');
            item.className = 'dd-item' + (m.id === activeId ? ' active' : '');
            item.setAttribute('data-action', 'set-model');
            item.setAttribute('data-id', m.id);
            item.setAttribute('data-name', m.name || (m.provider + '/' + m.model));
            item.innerHTML = '<span>' + (m.name || m.model) + '</span>' +
                '<span class="dd-provider">' + m.provider + '</span>';
            dd.appendChild(item);
        });

        // 更新按钮标签
        var activeModel = res.data.models.find(function(m) { return m.id === activeId; });
        if (activeModel) {
            label.textContent = activeModel.name || activeModel.model;
        }
    });
}

function _onModelDropdownClick(e) {
    var item = e.target.closest('[data-action]');
    if (!item) return;
    if (item.getAttribute('data-action') === 'set-model') {
        var modelId = parseInt(item.getAttribute('data-id'));
        var modelName = item.getAttribute('data-name');
        // 乐观更新 UI
        document.querySelectorAll('#chat-model-dropdown .dd-item').forEach(function(it) {
            it.classList.toggle('active', parseInt(it.getAttribute('data-id')) === modelId);
        });
        document.getElementById('chat-model-label').textContent = modelName;
        document.getElementById('chat-model-dropdown').classList.remove('open');
        // 后端切换
        fetch('/api/chat/model-configs/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: modelId }),
        }).then(function(r) { return r.json(); }).then(function(res) {
            if (res.code === 200) {
                loadConfig(); // 同步刷新 header
            } else {
                showToast('切换失败: ' + (res.message || '未知错误'));
                loadModels(); // 恢复
            }
        }).catch(function() {
            showToast('切换失败: 网络错误');
            loadModels();
        });
        e.stopPropagation();
    }
}
// ===== End Mode Selector =====

// File input change handler — upload with progress cards
function _onFileInputChange() {
    var files = this.files;
    if (!files || files.length === 0) return;
    for (var i = 0; i < files.length; i++) {
        (function(file) {
            var id = 'uf_' + Date.now() + '_' + Math.random().toString(36).slice(2,6);
            var fileObj = {
                id: id, label: file.name, path: file.name, type: 'local',
                status: 'uploading', progress: 0, xhr: null, _file: file
            };
            _uploadedFiles.push(fileObj);
            renderUploadedFiles();
            _doUpload(fileObj, id);
        })(files[i]);
    }
    this.value = '';
}

function updateFileStatus(id, status, progress) {
    var found = _uploadedFiles.filter(function(f) { return f.id === id; })[0];
    if (!found) return;
    found.status = status;
    if (progress !== undefined) found.progress = progress;
    if (status === 'done' || status === 'error') found.xhr = null;
    // Only update that specific pill DOM to avoid full re-render
    var pill = document.querySelector('.chat-file-pill[data-id="' + id + '"]');
    if (pill) {
        renderPillDOM(pill, found, _uploadedFiles.indexOf(found));
    }
}

function updateFileDone(id, path, label, savedName) {
    var found = _uploadedFiles.filter(function(f) { return f.id === id; })[0];
    if (!found) return;
    found.path = path;
    found.label = label;
    found.savedName = savedName || '';
    found.status = 'done';
    found.progress = 100;
    found.xhr = null;
    var pill = document.querySelector('.chat-file-pill[data-id="' + id + '"]');
    if (pill) {
        renderPillDOM(pill, found, _uploadedFiles.indexOf(found));
    }
}

function renderPillDOM(el, f, i) {
    var tagLabel = f.type === 'kb' ? '知识库' : '本地';
    var iconSvg = f.type === 'kb'
        ? '<svg class="pill-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'
        : '<svg class="pill-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>';
    var statusHtml = '';
    if (f.status === 'uploading') {
        statusHtml = '<span class="pill-status"><span class="pill-spinner"></span></span>';
    } else if (f.status === 'done') {
        statusHtml = '<span class="pill-status">&#10003;</span>';
    } else if (f.status === 'error') {
        statusHtml = '<span class="pill-retry" onclick="event.stopPropagation(); retryUpload(\'' + f.id + '\')">重试</span>';
    }
    var progressHtml = f.status === 'uploading'
        ? '<div class="pill-progress-wrap"><div class="pill-progress-bar" style="width:' + f.progress + '%"></div></div>'
        : '';
    el.className = 'chat-file-pill' + (f.status === 'uploading' ? ' uploading' : '') + (f.status === 'done' ? ' done' : '') + (f.status === 'error' ? ' error' : '');
    el.title = esc(f.path);
    el.innerHTML = iconSvg
        + '<span class="pill-label">' + esc(f.label) + '</span>'
        + '<span class="pill-tag">' + tagLabel + '</span>'
        + statusHtml
        + (f.status !== 'uploading' ? '<span class="pill-remove" onclick="removeUploadedFile(' + i + ')" title="移除">&times;</span>' : '')
        + progressHtml;
}

function _doUpload(fileObj, fileId) {
    var xhr = new XMLHttpRequest();
    var formData = new FormData();
    formData.append('file', fileObj._file);
    xhr.open('POST', '/api/chat/upload', true);
    xhr.upload.onprogress = function(e) {
        if (e.lengthComputable) {
            updateFileStatus(fileId, 'uploading', Math.round(e.loaded / e.total * 100));
        }
    };
    xhr.onload = function() {
        if (xhr.status === 200) {
            try {
                var r = JSON.parse(xhr.responseText);
                if (r.code === 200 && r.data) {
                    updateFileDone(fileId, r.data.path, r.data.filename, r.data.saved_name);
                } else { updateFileStatus(fileId, 'error', 0); }
            } catch(e) { updateFileStatus(fileId, 'error', 0); }
        } else { updateFileStatus(fileId, 'error', 0); }
    };
    xhr.onerror = function() { updateFileStatus(fileId, 'error', 0); };
    fileObj.xhr = xhr;
    xhr.send(formData);
}

function retryUpload(id) {
    var found = _uploadedFiles.filter(function(f) { return f.id === id; })[0];
    if (!found || !found._file) return;
    found.status = 'uploading';
    found.progress = 0;
    renderUploadedFiles();
    _doUpload(found, id);
}

function removeUploadedFile(idx) {
    var f = _uploadedFiles[idx];
    if (f && f.xhr) { f.xhr.abort(); }
    _uploadedFiles.splice(idx, 1);
    renderUploadedFiles();
}

function renderUploadedFiles() {
    var pillsContainer = document.getElementById('chat-uploaded-files');
    if (_uploadedFiles.length === 0) {
        pillsContainer.classList.remove('has-files');
        pillsContainer.innerHTML = '';
        return;
    }
    pillsContainer.classList.add('has-files');
    pillsContainer.innerHTML = '';
    _uploadedFiles.forEach(function(f, i) {
        var pill = document.createElement('div');
        pill.setAttribute('data-id', f.id);
        renderPillDOM(pill, f, i);
        pillsContainer.appendChild(pill);
    });
}

// ===== KB File Browser =====
function openKbBrowser() {
    var overlay = document.getElementById('kb-browser-overlay');
    var browser = document.getElementById('kb-browser');
    overlay.classList.add('open');
    browser.classList.add('open');
    kbBrowseTo('');
}

function closeKbBrowser() {
    var overlay = document.getElementById('kb-browser-overlay');
    var browser = document.getElementById('kb-browser');
    overlay.classList.remove('open');
    browser.classList.remove('open');
}

function kbBrowseTo(path) {
    _kbBrowserPath = path;
    var breadcrumb = document.getElementById('kb-browser-breadcrumb');
    var backBtn = document.getElementById('kb-browser-back');
    var body = document.getElementById('kb-browser-body');

    breadcrumb.textContent = '知识库/' + (path || '');
    backBtn.disabled = !path;

    body.innerHTML = '<div class="kb-loading">加载中...</div>';

    fetch('/api/chat/kb-tree', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: path})
    }).then(function(r) { return r.json(); }).then(function(res) {
        if (res.code !== 200) {
            body.innerHTML = '<div class="kb-error">加载失败: ' + (res.message || '未知错误') + '</div>';
            return;
        }
        var data = res.data;
        var html = '';
        // Folders first
        data.folders.forEach(function(f) {
            html += '<div class="kb-browser-item folder" onclick="kbBrowseTo(\'' + escapeJs(path ? path + '/' + f : f) + '\')">'
                  + '<svg class="kb-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>'
                  + '<span class="kb-name">' + esc(f) + '</span>'
                  + '</div>';
        });
        // Files
        data.files.forEach(function(f) {
            var filePath = path ? path + '/' + f : f;
            html += '<div class="kb-browser-item file" onclick="selectKbFile(\'' + escapeJs(filePath) + '\', \'' + escapeJs(f) + '\')">'
                  + '<svg class="kb-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>'
                  + '<span class="kb-name">' + esc(f) + '</span>'
                  + '</div>';
        });
        if (data.folders.length === 0 && data.files.length === 0) {
            html = '<div class="kb-empty">此目录为空</div>';
        }
        body.innerHTML = html;
    }).catch(function(err) {
        body.innerHTML = '<div class="kb-error">网络错误: ' + err.message + '</div>';
    });
}

function kbBrowseUp() {
    if (!_kbBrowserPath) return;
    var parts = _kbBrowserPath.split('/');
    parts.pop();
    kbBrowseTo(parts.join('/'));
}

function selectKbFile(path, name) {
    // 知识库文件不用上传，直接添加为 done 状态的 pill
    _uploadedFiles.push({
        id: 'kb_' + Date.now() + '_' + Math.random().toString(36).slice(2,6),
        path: path,
        label: name,
        type: 'kb',
        status: 'done',
        progress: 100,
        xhr: null
    });
    renderUploadedFiles();
    closeKbBrowser();
}

function escapeJs(str) {
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"')
        .replace(/\n/g, '\\n').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Prevent clicks inside KB browser from bubbling to document (which would close it)
function _onKbBrowserClick(e) {
    e.stopPropagation();
}
function _onKbOverlayClick(e) {
    e.stopPropagation();
    closeKbBrowser();
}
// ===== End KB File Browser =====

// Close dropdown, KB browser, and mode menu on outside click
document.addEventListener('click', function(e) {
    var dd = document.getElementById('chat-plus-dropdown');
    var plusWrap = document.querySelector('.chat-plus-wrap');
    var kbBrowser = document.getElementById('kb-browser');
    var modeDd = document.getElementById('chat-mode-dropdown');
    var modeWrap = document.querySelector('.chat-mode-wrap');
    var modelDd = document.getElementById('chat-model-dropdown');
    var modelWrap = document.querySelector('.chat-model-wrap');
    if (dd && dd.classList.contains('open') && !plusWrap.contains(e.target)) {
        dd.classList.remove('open');
    }
    if (modeDd && modeDd.classList.contains('open') && !modeWrap.contains(e.target)) {
        modeDd.classList.remove('open');
    }
    if (modelDd && modelDd.classList.contains('open') && !modelWrap.contains(e.target)) {
        modelDd.classList.remove('open');
    }
    if (kbBrowser && kbBrowser.classList.contains('open')) {
        if (!kbBrowser.contains(e.target) && e.target.id !== 'kb-browser-overlay') {
            closeKbBrowser();
        }
    }
});

function restoreSendBtn() {
    var b = document.getElementById('chat-send-btn');
    if (b) {
        b.classList.remove('streaming');
        b.disabled = false;
        b.setAttribute('aria-label', '发送');
        b.onclick = sendMsg;
    }
}

function stopGeneration() {
    var st = window._streamState;
    if (st && st.abortController) {
        st.abortController.abort();
    }
}

function sendMsg() {
    if (window._streamState && window._streamState.active) return;
    if (!sid) {
        createNewSession(function() { sendMsg(); });
        return;
    }
    var ta = document.getElementById('chat-input');
    var text = ta.value.trim();
    if (!text && _uploadedFiles.length === 0) return;

    var displayText = text;
    var fileNames = _uploadedFiles.map(function(f) {
        return f.savedName ? f.label + '#' + f.savedName : f.label;
    });
    if (fileNames.length > 0) {
        displayText = text + (text ? '\n\n' : '') + '[附件: ' + fileNames.join(', ') + ']';
    }

    ta.value = '';
    autoH(ta);

    var btn = document.getElementById('chat-send-btn');
    btn.classList.add('streaming');
    btn.setAttribute('aria-label', '停止生成');
    btn.onclick = function() { stopGeneration(); };

    // 构建附件数据（含 savedName 用于预览），在清除 _uploadedFiles 前提取
    var sentFiles = _uploadedFiles.slice();
    var attachData = sentFiles.map(function(f) {
        return { label: f.label, savedName: f.savedName || '', path: f.path || '' };
    });

    var userBubble = addBubble('user', displayText, null, null, attachData);
    scrollToBubble(userBubble);

    // 清除已上传文件显示
    _uploadedFiles = [];
    renderUploadedFiles();

    var ac = new AbortController();

    window._streamState = createStreamState(sid, text, ac);

    var filePaths = sentFiles.map(function(f) { return f.path; });

    createStreamBubble();
    scrollEnd();

    _startStreamFetch('/api/chat/sessions/' + sid + '/stream', {
        content: text,
        display_text: displayText,
        use_wiki: false,
        attachments: filePaths,
        mode: _chatMode
    }, sid, ac, function(err) {
        if (err && err.name === 'AbortError') {
            _streamCatch(err, sid);
        } else {
            window._streamState = null;
            restoreSendBtn();
            var sb = document.getElementById('stream-bubble');
            if (sb) sb.remove();
            console.error('[SSE Error]', err);
            addBubble('assistant', '网络错误，请重试');
            scrollEnd();
        }
    });
}

function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMsg();
    }
}

function autoH(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}
