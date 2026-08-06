/**
 * 编辑器模块
 */

// 编辑器相关全局变量 - 使用检查模式避免重复声明
if (typeof isAutoSaveEnabled === 'undefined') {
    var isAutoSaveEnabled = true;
    var autoSaveTimer = null;
    var lastSavedContent = '';
}

// 初始化编辑器
function initEditor() {
    const textarea = document.getElementById('note-content');
    if (!textarea) return;

    // 绑定输入事件
    textarea.addEventListener('input', handleEditorInput);
    
    // 绑定快捷键
    textarea.addEventListener('keydown', handleEditorKeydown);
    
    // 初始化字数统计
    updateWordCount();
    
    // 加载自动保存设置
    isAutoSaveEnabled = localStorage.getItem('blossom-auto-save') !== 'false';
    
    // 保存初始内容
    lastSavedContent = textarea.value;
}

// 处理编辑器输入
function handleEditorInput() {
    updateWordCount();
    
    // 自动保存
    if (isAutoSaveEnabled) {
        if (autoSaveTimer) {
            clearTimeout(autoSaveTimer);
        }
        autoSaveTimer = setTimeout(autoSaveNote, 2000);
    }
}

// 处理编辑器快捷键
function handleEditorKeydown(e) {
    // Ctrl/Cmd + S 保存
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveNote();
    }
    
    // Ctrl/Cmd + B 加粗
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        wrapSelection('**', '**');
    }
    
    // Ctrl/Cmd + I 斜体
    if ((e.ctrlKey || e.metaKey) && e.key === 'i') {
        e.preventDefault();
        wrapSelection('*', '*');
    }
}

// 自动保存笔记
function autoSaveNote() {
    const textarea = document.getElementById('note-content');
    const noteId = document.getElementById('note-id')?.value;
    
    if (!textarea || !noteId) return;
    
    const content = textarea.value;
    if (content === lastSavedContent) return;
    
    fetch(`/api/article/${noteId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content })
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200) {
            lastSavedContent = content;
            updateSaveIndicator(true);
        }
    });
}

// 手动保存笔记
function saveNote() {
    const textarea = document.getElementById('note-content');
    const titleInput = document.getElementById('note-title');
    const noteId = document.getElementById('note-id')?.value;
    
    if (!textarea || !noteId) return;
    
    const data = {
        content: textarea.value
    };
    
    if (titleInput) {
        data.title = titleInput.value;
    }
    
    fetch(`/api/article/${noteId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200) {
            lastSavedContent = textarea.value;
            updateSaveIndicator(true);
            
            setTimeout(() => {
                updateSaveIndicator(false);
            }, 2000);
        } else {
            alert('保存失败');
        }
    })
    .catch(() => {
        alert('保存失败');
    });
}

// 更新保存指示器
function updateSaveIndicator(saved) {
    const indicator = document.getElementById('save-indicator');
    if (!indicator) return;
    
    if (saved) {
        indicator.textContent = '已保存';
        indicator.style.color = '#0D9488';
    } else {
        indicator.textContent = '未保存';
        indicator.style.color = '#F59E0B';
    }
}

// 更新字数统计
function updateWordCount() {
    const textarea = document.getElementById('note-content');
    const wordCountEl = document.getElementById('word-count');
    
    if (!textarea || !wordCountEl) return;
    
    const content = textarea.value;
    const wordCount = content.length;
    wordCountEl.textContent = `字数: ${wordCount}`;
}

// 包裹选区文本
function wrapSelection(prefix, suffix) {
    const textarea = document.getElementById('note-content');
    if (!textarea) return;
    
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end);
    
    const newText = prefix + selectedText + suffix;
    textarea.value = textarea.value.substring(0, start) + newText + textarea.value.substring(end);
    
    // 恢复选区
    textarea.selectionStart = start;
    textarea.selectionEnd = start + newText.length;
    textarea.focus();
    
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    handleEditorInput();
}

// 插入HTML到编辑器
function insertHTML(html) {
    const textarea = document.getElementById('editor-textarea') || document.getElementById('note-content');
    if (!textarea) return;
    
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    
    textarea.value = textarea.value.substring(0, start) + html + textarea.value.substring(end);
    
    // 移动光标到插入位置之后
    textarea.selectionStart = textarea.selectionEnd = start + html.length;
    textarea.focus();
    
    // 手动触发input事件，确保编辑器预览能更新
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    handleEditorInput();
}

// 插入图片到编辑器
function insertImage(url, alt = '') {
    const markdown = `![${alt || '图片'}](${url})`;
    insertHTML('\n' + markdown + '\n');
}

// 当前选中的图片文件夹路径
let currentPickerFolderPath = '';

// 显示图片选择器
function showImagePicker() {
    // 创建图片选择器弹窗
    const overlay = document.createElement('div');
    overlay.className = 'image-picker-overlay';
    overlay.id = 'image-picker-overlay';
    overlay.innerHTML = `
        <div class="image-picker-modal">
            <div class="image-picker-header">
                <h3>选择图片</h3>
                <button class="btn-close" onclick="closeImagePicker()">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
            </div>
            <div class="image-picker-body">
                <div class="image-picker-sidebar">
                    <div class="picker-sidebar-header">
                <button class="sidebar-item sidebar-all" data-path="" onclick="loadPickerImages('')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/></svg>
                    <span>全部图片</span>
                </button>
            </div>
                    <div class="picker-tree" id="picker-tree">
                        <div class="tree-loading">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="emoji-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                        </div>
                    </div>
                </div>
                <div class="image-picker-content">
                    <div class="picker-search-box">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
                        <input type="text" id="picker-search-input" placeholder="搜索图片..." oninput="filterPickerImages()" />
                    </div>
                    <div class="image-picker-grid" id="picker-image-grid">
                        <div class="image-picker-loading">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="emoji-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                            <span>加载中...</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="image-picker-footer">
                <button class="toolbar-btn" onclick="closeImagePicker()">取消</button>
                <button class="toolbar-btn toolbar-btn-primary" id="image-picker-confirm" disabled>插入选中</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    overlay.classList.add('show');

    // 点击遮罩关闭
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            closeImagePicker();
        }
    });

    // 加载目录树和图片列表
    loadPickerTree();
    loadPickerImages('');
}

// 加载目录树
function loadPickerTree() {
    const treeContainer = document.getElementById('picker-tree');
    fetch('/api/picture/tree')
        .then(response => response.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                treeContainer.innerHTML = renderPickerTree(result.data);
                bindPickerTreeEvents();
            } else {
                treeContainer.innerHTML = '<div class="tree-empty" style="padding: 12px; text-align: center; color: var(--color-muted);">暂无文件夹</div>';
            }
        })
        .catch(() => {
            treeContainer.innerHTML = '<div class="tree-empty" style="padding: 12px; text-align: center; color: var(--color-muted);">加载失败</div>';
        });
}

// 渲染目录树
function renderPickerTree(nodes) {
    if (!nodes || nodes.length === 0) return '';

    var html = '<ul class="picker-tree-list">';
    nodes.forEach(function(node) {
        if (node.type !== 'folder') return;

        var iconHtml = node.icon
            ? '<img class="tree-item-icon" src="/api/article/emoji/' + encodeURIComponent(node.icon) + '" alt="">'
            : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>';

        html += '<li class="picker-tree-item">' +
            '<div class="tree-item-row" data-path="' + escapeHtml(node.path) + '">' +
                iconHtml +
                '<span class="tree-item-name">' + escapeHtml(node.name) + '</span>' +
            '</div>';
        if (node.children && node.children.length > 0) {
            html += '<ul class="picker-tree-children">' + renderPickerTree(node.children) + '</ul>';
        }
        html += '</li>';
    });
    html += '</ul>';
    return html;
}

// 绑定目录树事件
function bindPickerTreeEvents() {
    const items = document.querySelectorAll('.tree-item-row');
    items.forEach(item => {
        item.addEventListener('click', function(e) {
            e.stopPropagation();
            const path = this.getAttribute('data-path');
            loadPickerImages(path);
            
            // 更新选中状态
            document.querySelectorAll('.sidebar-item, .tree-item-row').forEach(el => el.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

// 加载图片列表
function loadPickerImages(folderPath) {
    currentPickerFolderPath = folderPath;
    const grid = document.getElementById('picker-image-grid');
    const confirmBtn = document.getElementById('image-picker-confirm');
    
    // 更新侧边栏选中状态
    document.querySelectorAll('.sidebar-item, .tree-item-row').forEach(el => el.classList.remove('active'));
    if (folderPath) {
        document.querySelector(`.tree-item-row[data-path="${folderPath}"]`)?.classList.add('active');
    } else {
        document.querySelector('.sidebar-all')?.classList.add('active');
    }
    
    // 禁用确认按钮
    confirmBtn.disabled = true;
    
    // 构建URL：文件夹路径作为image_path参数传递
    let url = '/api/picture/images';
    if (folderPath) {
        url += `?image_path=${encodeURIComponent(folderPath)}`;
    }
    
    fetch(url)
        .then(response => response.json())
        .then(result => {
            if (!result || result.code !== 200 || !result.data) {
                grid.innerHTML = '\n                    <div class="image-picker-empty">\n                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>\n                        <span>暂无图片</span>\n                    </div>\n                ';
                return;
            }

            renderPickerImages(result.data);
        })
        .catch(() => {
            grid.innerHTML = '\n                <div class="image-picker-empty">\n                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>\n                    <span>加载失败</span>\n                </div>\n            ';
        });
}

// 渲染图片列表
function renderPickerImages(images) {
    const grid = document.getElementById('picker-image-grid');
    let html = '';
    images.forEach(img => {
        // 使用相对路径格式：只传递img参数，依赖后端默认路径配置
        // 这样项目移动时仍然能正确加载图片
        const relativePath = `/api/picture/image?img=${encodeURIComponent(img.path)}`;
        
        html += `
            <div class="image-picker-item" data-url="${relativePath}" data-name="${img.name}">
                <img src="${relativePath}" alt="${img.name}" />
            </div>
        `;
    });
    grid.innerHTML = html;
    bindPickerImageEvents();
}

// 绑定图片选择事件
function bindPickerImageEvents() {
    const items = document.querySelectorAll('.image-picker-item');
    const confirmBtn = document.getElementById('image-picker-confirm');
    let selectedUrl = null;

    items.forEach(item => {
        item.addEventListener('click', function() {
            items.forEach(i => i.classList.remove('selected'));
            this.classList.add('selected');
            selectedUrl = this.getAttribute('data-url');
            confirmBtn.disabled = false;
        });
    });

    confirmBtn.onclick = function() {
        if (selectedUrl) {
            const name = document.querySelector('.image-picker-item.selected')?.getAttribute('data-name') || '';
            insertImage(selectedUrl, name.replace(/\.[^/.]+$/, ''));
            closeImagePicker();
        }
    };
}

// 过滤图片
function filterPickerImages() {
    const searchInput = document.getElementById('picker-search-input');
    const keyword = searchInput.value.toLowerCase().trim();
    const items = document.querySelectorAll('.image-picker-item');
    
    items.forEach(item => {
        const name = item.getAttribute('data-name').toLowerCase();
        item.style.display = keyword === '' || name.includes(keyword) ? 'block' : 'none';
    });
}

// 关闭图片选择器
function closeImagePicker() {
    const overlay = document.getElementById('image-picker-overlay');
    if (overlay) {
        overlay.remove();
    }
    currentPickerFolderPath = '';
}

// 插入 Markdown 格式
function insertMarkdown(prefix, suffix) {
    const textarea = document.getElementById('editor-textarea') || document.getElementById('note-content');
    if (!textarea) return;
    
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end);
    
    const newText = textarea.value.substring(0, start) + prefix + selectedText + suffix + textarea.value.substring(end);
    textarea.value = newText;
    
    // 设置光标位置
    const newCursorPos = start + prefix.length + selectedText.length;
    textarea.setSelectionRange(newCursorPos, newCursorPos);
    textarea.focus();
    
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

// 插入链接
function insertLink() {
    const textarea = document.getElementById('editor-textarea') || document.getElementById('note-content');
    if (!textarea) return;
    
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end) || '链接文本';
    
    const url = prompt('请输入链接地址:', 'https://');
    if (!url) return;
    
    const markdown = `[${selectedText}](${url})`;
    const newText = textarea.value.substring(0, start) + markdown + textarea.value.substring(end);
    textarea.value = newText;
    
    textarea.focus();
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
}