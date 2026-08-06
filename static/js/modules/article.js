/**
 * 文档管理模块
 */

// 当前笔记分类ID
let currentCategoryId = '';

// 文件夹图标选项（32个适合做文件夹的图标）
const folderIcons = [
    'Open file folder_3d', 'File folder_3d', 'Briefcase_3d', 'Package_3d',
    'Bento box_3d', 'Beverage box_3d', 'Card file box_3d', 'Takeout box_3d',
    'Toolbox_3d', 'File cabinet_3d', 'Clipboard_3d', 'Books_3d',
    'Open book_3d', 'Closed book_3d', 'Blue book_3d', 'Green book_3d',
    'Orange book_3d', 'Notebook_3d', 'Notebook with decorative cover_3d', 'Bookmark tabs_3d',
    'bookmark_3d', 'Inbox tray_3d', 'Outbox tray_3d', 'Open mailbox with raised flag_3d',
    'Open mailbox with lowered flag_3d', 'Closed mailbox with raised flag_3d', 'Closed mailbox with lowered flag_3d', 'Postbox_3d',
    'Check box with check_3d', 'Ballot box with ballot_3d', 'Card index_3d', 'Scroll_3d'
];

// 当前选中的文件夹图标
let selectedFolderIcon = 'Open file folder_3d';

// SVG 图标库（替代 emoji PNG）
// 所有图标使用 Lucide 风格的描边 SVG，viewBox 0 0 24 24
const FOLDER_SVG_ICONS = {
    'Open file folder_3d': '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/><path d="M2 10 4.5 14a2 2 0 0 0 1.7 1H20"/>',
    'File folder_3d': '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    'Briefcase_3d': '<path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/><rect width="20" height="14" x="2" y="6" rx="2"/>',
    'Package_3d': '<path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    'Bento box_3d': '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    'Beverage box_3d': '<path d="M15.5 3H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h14a2 2 0 0 0 2-2V8.5L15.5 3Z"/><path d="M15 3v6h6"/>',
    'Card file box_3d': '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
    'Takeout box_3d': '<path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/>',
    'Toolbox_3d': '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    'File cabinet_3d': '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    'Clipboard_3d': '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
    'Books_3d': '<path d="m16 6 4 14"/><path d="M12 6v14"/><path d="M8 8v12"/><path d="M4 4v16"/>',
    'Open book_3d': '<path d="M12 7v14"/><path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z"/>',
    'Closed book_3d': '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/>',
    'Blue book_3d': '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a1 1 0 0 1 0-5H20"/>',
    'Green book_3d': '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a1 1 0 0 1 0-5H20"/>',
    'Orange book_3d': '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a1 1 0 0 1 0-5H20"/>',
    'Notebook_3d': '<path d="M2 6h4"/><path d="M2 10h4"/><path d="M2 14h4"/><path d="M2 18h4"/><rect width="16" height="20" x="4" y="2" rx="2"/>',
    'Notebook with decorative cover_3d': '<path d="M2 6h4"/><path d="M2 10h4"/><path d="M2 14h4"/><path d="M2 18h4"/><rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9.5 8h5"/><path d="M9.5 12H16"/><path d="M9.5 16H14"/>',
    'Bookmark tabs_3d': '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/><path d="M9 3h8a2 2 0 0 1 2 2v16l-2-1"/>',
    'bookmark_3d': '<path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>',
    'Inbox tray_3d': '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    'Outbox tray_3d': '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    'Open mailbox with raised flag_3d': '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/><path d="M18 2v6"/>',
    'Open mailbox with lowered flag_3d': '<path d="M21.2 8.4c.5-.4.8-.9.8-1.5a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 4 7c0 .6.3 1.1.8 1.5L12 14l7.2-5.6Z"/><path d="m22 8-10 7L2 8"/>',
    'Closed mailbox with raised flag_3d': '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/><path d="M18 2v6"/>',
    'Closed mailbox with lowered flag_3d': '<path d="M21.2 8.4c.5-.4.8-.9.8-1.5a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 4 7c0 .6.3 1.1.8 1.5L12 14l7.2-5.6Z"/><path d="m22 8-10 7L2 8"/>',
    'Postbox_3d': '<path d="M22 17a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9.5a2 2 0 0 1 1.4-1.9L8 6"/><path d="M2 9.5 8 6"/><path d="M8 6V4a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v14"/><path d="M18 22V4a2 2 0 0 0-2-2H8"/>',
    'Check box with check_3d': '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
    'Ballot box with ballot_3d': '<path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z"/>',
    'Card index_3d': '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
    'Scroll_3d': '<path d="M19 17V5a2 2 0 0 0-2-2H4"/><path d="M8 21h12a2 2 0 0 0 2-2v-1a1 1 0 0 0-1-1H11a1 1 0 0 0-1 1v1a2 2 0 1 1-4 0V5a2 2 0 1 0-4 0v2a1 1 0 0 0 1 1h3"/>'
};

// 默认文件图标（文档）
const FILE_SVG_PATHS = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>';

// 构造 SVG 图标
function makeSvgIcon(paths, opts) {
    opts = opts || {};
    const size = opts.size || 18;
    const sw = opts.strokeWidth || 2;
    const cls = opts['class'] || '';
    return '<svg xmlns="http://www.w3.org/2000/svg" width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + sw + '" stroke-linecap="round" stroke-linejoin="round"' + (cls ? ' class="' + cls + '"' : '') + '>' + paths + '</svg>';
}

// 获取文件夹图标 SVG
function getFolderIconSvg(iconName, size, cls) {
    size = size || 18;
    const paths = FOLDER_SVG_ICONS[iconName] || FOLDER_SVG_ICONS['File folder_3d'];
    return makeSvgIcon(paths, { size: size, 'class': cls || 'tree-svg-icon' });
}

// 获取文件图标 SVG
function getFileIconSvg(size, cls) {
    return makeSvgIcon(FILE_SVG_PATHS, { size: size || 18, 'class': cls || 'tree-svg-icon' });
}

// 根据类型获取树节点图标
function getTreeNodeIcon(node, size) {
    const isFolder = node.type === 'folder' || (node.children && node.children.length > 0);
    if (isFolder) {
        return getFolderIconSvg(node.icon || 'File folder_3d', size || 18, 'tree-svg-icon');
    }
    return getFileIconSvg(size || 18, 'tree-svg-icon');
}

// 当前编辑的文件夹路径
let currentEditingFolderPath = null;

// 文章根路径（从后端获取）
let articleRootPath = '/resource/article';

// 加载笔记列表
function loadNotes(categoryId = '') {
    currentCategoryId = categoryId;
    const url = categoryId ? `/api/article/list?category=${categoryId}` : '/api/article/list';
    
    fetch(url)
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                renderNotes(result.data);
            } else {
                renderNotes([]);
            }
        })
        .catch(() => {
            renderNotes([]);
        });
}

// 渲染笔记列表
function renderNotes(notes) {
    const container = document.getElementById('note-list');
    if (!container) return;

    if (!notes || notes.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="14" y2="17"/></svg>
                <p>暂无笔记</p>
                <p class="empty-hint">点击右上角按钮创建第一篇笔记</p>
            </div>
        `;
        return;
    }

    let html = '';
    notes.forEach(note => {
        const date = formatDate(note.modified);
        const preview = note.content ? note.content.substring(0, 100) + '...' : '';
        
        html += `
            <div class="note-card" data-id="${note.id}" onclick="openNote('${note.id}')">
                <h3 class="note-title">${escapeHtml(note.title) || '无标题'}</h3>
                <p class="note-preview">${escapeHtml(preview)}</p>
                <div class="note-meta">
                    <span class="note-date">${date}</span>
                    ${note.tags && note.tags.length > 0 ? `
                        <div class="note-tags">
                            ${note.tags.map(tag => `<span class="tag">${tag}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

// 打开笔记
function openNote(noteId) {
    window.location.href = `/note/${noteId}`;
}

// 创建新笔记
function createNote() {
    fetch('/api/article/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            title: '',
            content: '',
            category_id: currentCategoryId || null
        })
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200 && result.data) {
            window.location.href = `/note/${result.data.id}`;
        } else {
            alert('创建失败');
        }
    })
    .catch(() => {
        alert('创建失败');
    });
}

// 加载分类树
function loadCategoryTree() {
    fetch('/api/category/tree')
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                renderCategoryTree(result.data);
            }
        })
        .catch(() => {
            // 忽略错误
        });
}

// 渲染分类树
function renderCategoryTree(categories) {
    const container = document.getElementById('category-tree');
    if (!container) return;

    const html = renderCategoryNode(categories);
    container.innerHTML = html;

    // 绑定点击事件
    container.querySelectorAll('.category-item').forEach(item => {
        item.addEventListener('click', function() {
            const categoryId = this.dataset.id;
            loadNotes(categoryId);
            
            // 更新选中状态
            container.querySelectorAll('.category-item').forEach(i => i.classList.remove('active'));
            this.classList.add('active');
        });
    });
}

function renderCategoryNode(categories) {
    if (!categories || categories.length === 0) return '';

    let html = '<ul>';
    categories.forEach(cat => {
        html += `
            <li>
                <div class="category-item" data-id="${cat.id}">
                    <span>${escapeHtml(cat.name)}</span>
                    ${cat.count > 0 ? `<span class="category-count">${cat.count}</span>` : ''}
                </div>
                ${cat.children && cat.children.length > 0 ? renderCategoryNode(cat.children) : ''}
            </li>
        `;
    });
    html += '</ul>';
    return html;
}

// 删除笔记
function deleteNote(noteId) {
    if (!confirm('确定要删除这篇笔记吗？')) return;

    fetch(`/api/article/${noteId}`, {
        method: 'DELETE'
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200) {
            loadNotes(currentCategoryId);
        } else {
            alert('删除失败');
        }
    })
    .catch(() => {
        alert('删除失败');
    });
}

// ============ 文档树相关函数 ============

// 加载文档树
function loadDocTree() {
    const treeLoading = document.getElementById('tree-loading');
    const treeEmpty = document.getElementById('tree-empty');
    const treeList = document.getElementById('tree-list');
    
    if (treeLoading) treeLoading.style.display = 'flex';
    if (treeEmpty) treeEmpty.style.display = 'none';
    if (treeList) treeList.style.display = 'none';
    
    fetch('/api/article/tree')
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                renderDocTree(result.data);
            } else {
                showEmptyTree();
            }
        })
        .catch(() => {
            showEmptyTree();
        })
        .finally(() => {
            if (treeLoading) treeLoading.style.display = 'none';
        });
}

// 渲染文档树
function renderDocTree(nodes) {
    const treeList = document.getElementById('tree-list');
    const treeEmpty = document.getElementById('tree-empty');
    
    if (!nodes || nodes.length === 0) {
        showEmptyTree();
        return;
    }
    
    if (treeEmpty) treeEmpty.style.display = 'none';
    if (treeList) {
        treeList.innerHTML = renderDocTreeNode(nodes);
        treeList.style.display = 'block';
    }
    
    // 绑定点击事件
    bindDocTreeEvents();
}

function renderDocTreeNode(nodes) {
    if (!nodes || nodes.length === 0) return '';
    
    let html = '';
    nodes.forEach(node => {
        const isFolder = node.type === 'folder' || node.children && node.children.length > 0;
        const hasChildren = node.children && node.children.length > 0;
        // 转义路径中的反斜杠和单引号，用于 JavaScript 字符串
        const escapedPath = escapeHtml(node.path).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        // 使用 SVG 图标
        const nodeIcon = getTreeNodeIcon(node, 18);
        
        html += `
            <li class="tree-item" data-path="${escapeHtml(node.path)}" data-name="${escapeHtml(isFolder ? node.name : node.name.replace(/\.md$/, ''))}" data-type="${isFolder ? 'folder' : 'file'}" draggable="true">
                <div class="tree-item-content">
                    <span class="tree-expand" ${hasChildren ? '' : 'style="visibility:hidden"'} onclick="toggleTreeExpand(this)">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
                    </span>
                    ${nodeIcon}
                    <span class="tree-item-name" onclick="loadArticle('${escapedPath}')">${escapeHtml(node.name)}</span>
                    <span class="tree-item-menu" onclick="toggleTreeItemMenu(this)">
                        <button class="tree-item-menu-btn">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>
                        </button>
                        <div class="tree-item-dropdown">
                            ${isFolder ? `<button onclick="createDocument('${escapedPath}')">新建文档</button>` : ''}
                            <button onclick="${isFolder ? `openFolderEditModal('${escapedPath}')` : `editArticle('${escapedPath}')`}">编辑</button>
                            <button class="tree-dropdown-danger" onclick="deleteDocument('${escapedPath}')">删除</button>
                        </div>
                    </span>
                </div>
                ${hasChildren ? `<ul class="tree-children">${renderDocTreeNode(node.children)}</ul>` : ''}
            </li>
        `;
    });
    
    return html;
}

// 显示空树
function showEmptyTree() {
    const treeEmpty = document.getElementById('tree-empty');
    const treeList = document.getElementById('tree-list');
    
    if (treeEmpty) treeEmpty.style.display = 'flex';
    if (treeList) treeList.style.display = 'none';
}

// 切换树节点展开/折叠
function toggleTreeExpand(el) {
    const li = el.closest('.tree-item');
    if (!li) return;
    
    const children = li.querySelector('.tree-children');
    if (!children) return;
    
    const isExpanded = children.style.display !== 'none';
    children.style.display = isExpanded ? 'none' : 'block';
    
    // 旋转图标
    el.style.transform = isExpanded ? 'rotate(0deg)' : 'rotate(90deg)';
}

// 切换目录项下拉菜单
function toggleTreeItemMenu(el) {
    // 阻止事件冒泡
    event.stopPropagation();
    
    // 关闭其他打开的下拉菜单
    document.querySelectorAll('.tree-item-dropdown').forEach(dropdown => {
        dropdown.classList.remove('show');
    });
    
    // 切换当前菜单
    const dropdown = el.querySelector('.tree-item-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

// 在文件夹中创建新文档
function createDocument(folderPath) {
    // 关闭下拉菜单
    document.querySelectorAll('.tree-item-dropdown').forEach(dropdown => {
        dropdown.classList.remove('show');
    });
    
    fetch('/api/article/document', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath })
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200) {
            loadDocTree();
            if (result.data && result.data.path) {
                loadArticle(result.data.path);
                setTimeout(function() {
                    editArticle(result.data.path);
                }, 300);
            }
        } else {
            alert('创建文档失败');
        }
    })
    .catch(() => {
        alert('创建文档失败');
    });
}

// 重命名文档/文件夹
function renameDocument(filePath) {
    // 关闭下拉菜单
    document.querySelectorAll('.tree-item-dropdown').forEach(dropdown => {
        dropdown.classList.remove('show');
    });
    
    const currentName = filePath.split(/[\\/]/).pop();
    const newName = prompt('请输入新名称', currentName);
    
    if (!newName || newName.trim() === '') return;
    
    fetch('/api/article/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            old_path: filePath, 
            new_name: newName.trim() 
        })
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200) {
            loadDocTree();
        } else {
            alert('重命名失败');
        }
    })
    .catch(() => {
        alert('重命名失败');
    });
}

// 删除文档/文件夹
function deleteDocument(filePath) {
    if (!confirm('确定要删除吗？')) return;

    // 关闭下拉菜单
    document.querySelectorAll('.tree-item-dropdown').forEach(dropdown => {
        dropdown.classList.remove('show');
    });
    closeAllToolbarDropdowns();

    fetch(`/api/article/document?path=${encodeURIComponent(filePath)}`, {
        method: 'DELETE'
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200) {
            loadDocTree();
            // 如果删除的是当前打开的文章，清空内容
            const contentEl = document.getElementById('article-content');
            if (contentEl) {
                contentEl.innerHTML = '<div class="content-empty-hint">请选择一篇文章</div>';
            }
            const articleContent = contentEl ? contentEl.parentElement : null;
            const toolbarEl = articleContent ? articleContent.querySelector('.article-toolbar') : null;
            if (toolbarEl) { toolbarEl.style.display = 'none'; }
        } else {
            alert('删除失败');
        }
    })
    .catch(() => {
        alert('删除失败');
    });
}

// 绑定文档树事件
function bindDocTreeEvents() {
    var treeList = document.getElementById('tree-list');
    if (!treeList) return;

    if (treeList._dragBound) return;
    treeList._dragBound = true;

    var dragSrcEl = null;
    var dropTarget = null;
    var dropAction = '';

    treeList.addEventListener('dragstart', function(e) {
        var item = e.target.closest('.tree-item');
        if (!item) return;
        dragSrcEl = item;
        dropTarget = null;
        dropAction = '';
        item.classList.add('tree-dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.getAttribute('data-path'));
    });

    treeList.addEventListener('dragend', function(e) {
        var item = e.target.closest('.tree-item');
        if (item) item.classList.remove('tree-dragging');
        treeList.querySelectorAll('.tree-drag-over, .tree-drag-before, .tree-drag-after, .tree-drag-inside').forEach(function(el) {
            el.classList.remove('tree-drag-over', 'tree-drag-before', 'tree-drag-after', 'tree-drag-inside');
        });
        dragSrcEl = null;
        dropTarget = null;
        dropAction = '';
    });

    treeList.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        var targetItem = e.target.closest('.tree-item');
        if (!targetItem || targetItem === dragSrcEl) {
            dropTarget = null;
            dropAction = '';
            return;
        }
        if (dragSrcEl && dragSrcEl.contains(targetItem)) {
            return;
        }
        treeList.querySelectorAll('.tree-drag-over, .tree-drag-before, .tree-drag-after, .tree-drag-inside').forEach(function(el) {
            if (el !== targetItem) el.classList.remove('tree-drag-over', 'tree-drag-before', 'tree-drag-after', 'tree-drag-inside');
        });
        targetItem.classList.add('tree-drag-over');
        var rect = targetItem.querySelector('.tree-item-content').getBoundingClientRect();
        var y = e.clientY - rect.top;
        var h = rect.height;
        var edgeSize = Math.min(h * 0.3, 12);
        targetItem.classList.remove('tree-drag-before', 'tree-drag-after', 'tree-drag-inside');
        if (y < edgeSize) {
            targetItem.classList.add('tree-drag-before');
            dropAction = 'before';
        } else if (y > h - edgeSize) {
            targetItem.classList.add('tree-drag-after');
            dropAction = 'after';
        } else {
            var targetType = targetItem.getAttribute('data-type');
            if (targetType === 'folder') {
                targetItem.classList.add('tree-drag-inside');
                dropAction = 'inside';
            } else {
                if (e.clientY < rect.top + h / 2) {
                    targetItem.classList.add('tree-drag-before');
                    dropAction = 'before';
                } else {
                    targetItem.classList.add('tree-drag-after');
                    dropAction = 'after';
                }
            }
        }
        dropTarget = targetItem;
    });

    treeList.addEventListener('dragleave', function(e) {
        var targetItem = e.target.closest('.tree-item');
        if (targetItem && !targetItem.contains(e.relatedTarget)) {
            targetItem.classList.remove('tree-drag-over', 'tree-drag-before', 'tree-drag-after', 'tree-drag-inside');
        }
    });

    function saveNewSortOrder(parentEl) {
        var folderPath = parentEl.closest('.tree-item');
        var folderPathStr = folderPath ? folderPath.getAttribute('data-path') : '';
        var items = parentEl.querySelectorAll(':scope > .tree-item');
        var newOrder = [];
        items.forEach(function(item) {
            var name = item.getAttribute('data-name') || item.getAttribute('data-path').split(/[\\/]/).pop().replace(/\.md$/, '');
            newOrder.push(name);
        });
        fetch('/api/article/sort-order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ folder_path: folderPathStr, sort_order: newOrder })
        })
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.code === 200) {
                loadDocTree();
            }
        });
    }

    treeList.addEventListener('drop', function(e) {
        e.preventDefault();
        e.stopPropagation();
        treeList.querySelectorAll('.tree-drag-over, .tree-drag-before, .tree-drag-after, .tree-drag-inside').forEach(function(el) {
            el.classList.remove('tree-drag-over', 'tree-drag-before', 'tree-drag-after', 'tree-drag-inside');
        });

        if (!dropTarget || !dragSrcEl || dropTarget === dragSrcEl) return;

        var srcPath = dragSrcEl.getAttribute('data-path');
        var targetType = dropTarget.getAttribute('data-type');

        if (dropAction === 'inside' && targetType === 'folder') {
            var srcName = dragSrcEl.querySelector('.tree-item-name');
            var targetName = dropTarget.querySelector('.tree-item-name');
            var msg = '确定移动 "' + (srcName ? srcName.textContent : '') + '" 到 "' + (targetName ? targetName.textContent : '') + '"？';
            if (!confirm(msg)) return;

            fetch('/api/article/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ src_path: srcPath, target_folder: dropTarget.getAttribute('data-path') })
            })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.code === 200) {
                    loadDocTree();
                } else {
                    alert(res.message || '移动失败');
                }
            })
            .catch(function() { alert('移动失败'); });
        } else if (dropAction === 'before' || dropAction === 'after') {
            var srcParent = dragSrcEl.parentElement;
            var targetParent = dropTarget.parentElement;

            if (srcParent === targetParent) {
                if (dropAction === 'before') {
                    targetParent.insertBefore(dragSrcEl, dropTarget);
                } else {
                    targetParent.insertBefore(dragSrcEl, dropTarget.nextSibling);
                }
                saveNewSortOrder(targetParent);
            } else {
                var srcName = dragSrcEl.querySelector('.tree-item-name');
                var targetParentItem = targetParent.closest('.tree-item');
                var targetParentName = targetParentItem ? targetParentItem.querySelector('.tree-item-name') : null;
                var msg = '确定移动 "' + (srcName ? srcName.textContent : '') + '" 到 "' + (targetParentName ? targetParentName.textContent : '根目录') + '"？';
                if (!confirm(msg)) return;

                var targetFolderPath = targetParentItem ? targetParentItem.getAttribute('data-path') : '';
                fetch('/api/article/move', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ src_path: srcPath, target_folder: targetFolderPath })
                })
                .then(function(r) { return r.json(); })
                .then(function(res) {
                    if (res.code === 200) {
                        loadDocTree();
                    } else {
                        alert(res.message || '移动失败');
                    }
                })
                .catch(function() { alert('移动失败'); });
            }
        }

        dragSrcEl = null;
        dropTarget = null;
        dropAction = '';
    });

    document.addEventListener('click', function(e) {
        const dropdown = document.getElementById('sidebar-dropdown');
        if (dropdown && !dropdown.contains(e.target)) {
            dropdown.classList.remove('show');
        }
        
        // 点击外部关闭目录项的下拉菜单
        const treeItemMenus = document.querySelectorAll('.tree-item-menu');
        treeItemMenus.forEach(menu => {
            if (!menu.contains(e.target)) {
                const dropdown = menu.querySelector('.tree-item-dropdown');
                if (dropdown) {
                    dropdown.classList.remove('show');
                }
            }
        });
    });
}

// 过滤文档树
function filterDocTree() {
    const input = document.getElementById('tree-search');
    const keyword = (input?.value || '').trim().toLowerCase();
    const treeItems = document.querySelectorAll('.tree-item');
    
    treeItems.forEach(item => {
        const nameEl = item.querySelector('.tree-item-name');
        const name = nameEl?.textContent?.toLowerCase() || '';
        
        if (!keyword || name.includes(keyword)) {
            item.style.display = '';
            // 显示所有祖先节点
            let parent = item.parentElement;
            while (parent) {
                if (parent.classList.contains('tree-item')) {
                    parent.style.display = '';
                }
                parent = parent.parentElement;
            }
        } else {
            item.style.display = 'none';
        }
    });
}

// 刷新文档树
function refreshDocTree() {
    loadDocTree();
}

// 加载文章内容
function loadArticle(filePath) {
    const contentEl = document.getElementById('article-content');
    if (!contentEl) return;
    
    contentEl.innerHTML = '<div class="content-empty-hint">加载中...</div>';
    
    fetch(`/api/article/content?path=${encodeURIComponent(filePath)}`)
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                renderArticle(result.data);
            } else {
                contentEl.innerHTML = '<div class="content-empty-hint">加载失败</div>';
            }
        })
        .catch(() => {
            contentEl.innerHTML = '<div class="content-empty-hint">加载失败</div>';
        });
}

// 绑定 wiki 链接（[[标题]]）点击事件，在侧边抽屉中打开概念（不离开当前文章页）
function bindWikiLinks() {
    const links = document.querySelectorAll('.article-body .wiki-link, .markdown-body .wiki-link');
    links.forEach(function(link) {
        if (link.dataset.bound) return;
        link.dataset.bound = '1';
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const target = (this.getAttribute('data-target') || '').trim();
            if (!target) return;
            const slug = target.toLowerCase().replace(/ /g, '_').replace(/\//g, '_');
            openWikiDrawer(slug);
        });
    });
}

// 打开 wiki 概念抽屉
function openWikiDrawer(slug) {
    const overlay = document.getElementById('wiki-drawer-overlay');
    const body = document.getElementById('wiki-drawer-body');
    if (!overlay || !body) return;

    // 显示抽屉 + loading
    body.innerHTML = '<div class="wiki-drawer-loading"><svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="emoji-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 加载中...</div>';
    overlay.classList.add('show');
    document.getElementById('wiki-drawer-panel').scrollTop = 0;

    fetch('/api/wiki/pages/' + encodeURIComponent(slug))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (res.code !== 200 || !res.data) {
                body.innerHTML = '<div class="wiki-drawer-error"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg><p>未找到该概念</p></div>';
                return;
            }
            renderWikiDrawerContent(res.data);
        })
        .catch(function() {
            body.innerHTML = '<div class="wiki-drawer-error"><p>加载失败</p></div>';
        });
}

// 渲染抽屉内容（body 走公共 Md 模块，与全站渲染一致）
function renderWikiDrawerContent(d) {
    const body = document.getElementById('wiki-drawer-body');

    const tags = '<span class="wiki-drawer-tag">' + escapeHtml(d.kind || 'concept') + '</span>' +
        (d.source === 'common' ? '<span class="wiki-drawer-tag wiki-drawer-tag--meta">公共库</span>' : '<span class="wiki-drawer-tag wiki-drawer-tag--meta">本地</span>') +
        (d.confidence ? '<span class="wiki-drawer-tag wiki-drawer-tag--meta">置信度 ' + (d.confidence * 100).toFixed(0) + '%</span>' : '');

    const summary = d.summary ? '<div class="wiki-drawer-summary">' + escapeHtml(d.summary) + '</div>' : '';
    const sources = (d.sources && d.sources.length) ? '<div class="wiki-drawer-sources"><strong>来源</strong> ' + escapeHtml(d.sources.join(', ')) + '</div>' : '';

    body.innerHTML =
        '<h1 class="wiki-drawer-title">' + escapeHtml(d.title || '') + '</h1>' +
        '<div class="wiki-drawer-tags">' + tags + '</div>' +
        summary +
        '<div class="wiki-drawer-content" id="wiki-drawer-content"></div>' +
        sources;

    const contentEl = document.getElementById('wiki-drawer-content');
    Md.renderInto(d.body || '', contentEl, {
        onDone: function() { bindWikiLinks(); }
    });
}

// 关闭 wiki 概念抽屉
function closeWikiDrawer() {
    const overlay = document.getElementById('wiki-drawer-overlay');
    if (overlay) overlay.classList.remove('show');
}

// 渲染文章内容
function renderArticle(data) {
    const contentEl = document.getElementById('article-content');
    if (!contentEl || !data) return;
    
    const articleContent = contentEl.parentElement;
    
    const isFolder = data.path && !data.path.endsWith('.md');
    const escapedPath = escapeHtml(data.path).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
    
    const tocEl = document.getElementById('article-toc');
    if (tocEl) {
        tocEl.style.display = isFolder ? 'none' : '';
    }
    
    const folderHeaderIcon = getFolderIconSvg(data.icon, 32, 'md-folder-icon-svg');
    const toolbarDropdownId = 'tdd-' + Math.random().toString(36).substring(2, 10);
    
    const favorites = JSON.parse(localStorage.getItem('blossom-favorites') || '[]');
    const isFavorited = favorites.some(f => f.path === data.path);
    const favClass = isFavorited ? 'article-toolbar-btn active' : 'article-toolbar-btn';
    const favFill = isFavorited ? 'currentColor' : 'none';
    const favSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="${favFill}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="fav-star"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`;
    
    let toolbarEl = articleContent.querySelector('.article-toolbar');
    if (!toolbarEl) {
        toolbarEl = document.createElement('div');
        toolbarEl.className = 'article-toolbar';
        articleContent.insertBefore(toolbarEl, contentEl);
    }
    
    toolbarEl.setAttribute('data-article-path', data.path);
    toolbarEl.innerHTML = `
        <div class="article-toolbar-left">
            <button class="${favClass}" id="article-fav-btn" data-path="${escapeHtml(data.path)}" data-title="${escapeHtml(data.title || '无标题')}" title="${isFavorited ? '取消收藏' : '收藏'}" aria-label="${isFavorited ? '取消收藏' : '收藏'}" aria-pressed="${isFavorited}">
                ${favSvg}
            </button>
        </div>
        <div class="article-toolbar-right">
            <button class="article-toolbar-btn" id="article-fullscreen-btn" title="全屏 (Esc 退出)">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" id="fullscreen-icon-enter"><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" id="fullscreen-icon-exit" style="display:none;"><path d="M3 8V5a2 2 0 0 1 2-2h3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M21 16v3a2 2 0 0 1-2 2h-3"/></svg>
            </button>
            <div class="article-toolbar-menu-wrapper">
                <button class="article-toolbar-btn" id="article-toolbar-more">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>
                </button>
                <div class="article-toolbar-dropdown" id="${toolbarDropdownId}">
                    <button class="toolbar-dropdown-item" data-action="edit" data-path="${escapeHtml(data.path)}" data-is-folder="${isFolder}">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                        <span>编辑</span>
                    </button>
                    <button class="toolbar-dropdown-item toolbar-dropdown-danger" data-action="delete" data-path="${escapeHtml(data.path)}">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                        <span>删除</span>
                    </button>
                </div>
            </div>
        </div>
    `;
    toolbarEl.style.display = isFolder ? 'none' : 'flex';
    
    contentEl.innerHTML = `
        <div class="content-body-inner">
            ${isFolder ? `
            <div class="folder-header-row">
                ${folderHeaderIcon}
                <div class="article-title">${escapeHtml(data.title || '无标题')}</div>
                <div class="article-toolbar-menu-wrapper article-title-menu">
                    <button class="article-toolbar-btn" id="article-title-more">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>
                    </button>
                    <div class="article-toolbar-dropdown" id="article-title-dropdown">
                        <button class="toolbar-dropdown-item" onclick="openFolderEditModal('${escapedPath}')">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                            <span>编辑</span>
                        </button>
                        <button class="toolbar-dropdown-item toolbar-dropdown-danger" onclick="deleteDocument('${escapedPath}')">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                            <span>删除</span>
                        </button>
                    </div>
                </div>
            </div>
            ` : ''}
            <div class="article-body">${data.content || '<p>暂无内容</p>'}</div>
            ${isFolder && data.children && data.children.length > 0 ? `
            <div class="folder-articles" id="folder-articles">
                ${data.children.map(function(child) {
                    var childEscaped = escapeHtml(child.path).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                    return '<div class="folder-article-item" draggable="true" data-path="' + escapeHtml(child.path) + '" data-name="' + escapeHtml(child.name) + '">' +
                        '<span class="folder-article-drag-handle" aria-hidden="true"><svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="15" cy="18" r="1"/></svg></span>' +
                        '<a class="folder-article-link" onclick="loadArticle(\'' + childEscaped + '\')">' + escapeHtml(child.name) + '</a>' +
                    '</div>';
                }).join('')}
            </div>
            ` : ''}
        </div>
    `;
    
    // 绑定 wiki 链接点击跳转
    bindWikiLinks();
    
    // 收藏按钮事件
    const favBtn = document.getElementById('article-fav-btn');
    if (favBtn) {
        favBtn.addEventListener('click', function() {
            toggleArticleFavorite(this.getAttribute('data-path'), this.getAttribute('data-title'), this);
        });
    }
    
    // 全屏按钮事件
    const fullscreenBtn = document.getElementById('article-fullscreen-btn');
    if (fullscreenBtn) {
        fullscreenBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleArticleFullscreen();
        });
    }
    
    // 三点按钮事件
    const moreBtn = document.getElementById('article-toolbar-more');
    const toolbarDropdown = document.getElementById(toolbarDropdownId);
    if (moreBtn && toolbarDropdown) {
        moreBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            const isOpen = toolbarDropdown.classList.contains('show');
            closeAllToolbarDropdowns();
            if (!isOpen) {
                toolbarDropdown.classList.add('show');
            }
        });
    }
    
    // 标题行三点按钮事件
    const titleMoreBtn = document.getElementById('article-title-more');
    const titleDropdown = document.getElementById('article-title-dropdown');
    if (titleMoreBtn && titleDropdown) {
        titleMoreBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            const isOpen = titleDropdown.classList.contains('show');
            closeAllToolbarDropdowns();
            if (!isOpen) {
                titleDropdown.classList.add('show');
            }
        });
    }
    
    // 下拉菜单项事件
    const dropdownItems = toolbarEl.querySelectorAll('.toolbar-dropdown-item');
    dropdownItems.forEach(item => {
        item.addEventListener('click', function(e) {
            e.stopPropagation();
            const action = this.getAttribute('data-action');
            const path = this.getAttribute('data-path');
            if (action === 'delete') {
                deleteDocument(path);
                return;
            }
            closeAllToolbarDropdowns();
            if (action === 'edit') {
                const isFld = this.getAttribute('data-is-folder') === 'true';
                if (isFld) {
                    openFolderEditModal(path);
                } else {
                    editArticle(path);
                }
            }
        });
    });
    
    // 文件夹内文章拖拽排序
    var folderArticles = document.getElementById('folder-articles');
    if (folderArticles && !folderArticles._sortBound) {
        folderArticles._sortBound = true;
        var sortDragEl = null;

        folderArticles.addEventListener('dragstart', function(e) {
            var item = e.target.closest('.folder-article-item');
            if (!item) return;
            sortDragEl = item;
            item.classList.add('folder-article-dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        folderArticles.addEventListener('dragend', function(e) {
            var item = e.target.closest('.folder-article-item');
            if (item) item.classList.remove('folder-article-dragging');
            folderArticles.querySelectorAll('.folder-article-drag-over').forEach(function(el) {
                el.classList.remove('folder-article-drag-over');
            });
            sortDragEl = null;
        });

        folderArticles.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            var targetItem = e.target.closest('.folder-article-item');
            folderArticles.querySelectorAll('.folder-article-drag-over').forEach(function(el) {
                if (el !== targetItem) el.classList.remove('folder-article-drag-over');
            });
            if (targetItem && targetItem !== sortDragEl) {
                var rect = targetItem.getBoundingClientRect();
                var midY = rect.top + rect.height / 2;
                if (e.clientY < midY) {
                    targetItem.parentNode.insertBefore(sortDragEl, targetItem);
                } else {
                    targetItem.parentNode.insertBefore(sortDragEl, targetItem.nextSibling);
                }
                targetItem.classList.add('folder-article-drag-over');
            }
        });

        folderArticles.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            folderArticles.querySelectorAll('.folder-article-drag-over').forEach(function(el) {
                el.classList.remove('folder-article-drag-over');
            });
            var items = folderArticles.querySelectorAll('.folder-article-item');
            var newOrder = [];
            items.forEach(function(item) {
                newOrder.push(item.getAttribute('data-name'));
            });
            fetch('/api/article/sort-order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: data.path, sort_order: newOrder })
            })
            .then(function(r) { return r.json(); })
            .then(function(res) {
                if (res.code === 200) {
                    loadDocTree();
                }
            });
        });
    }

    // 文档内链接点击事件（文件夹页面）
    const articleBody = contentEl.querySelector('.article-body');
    if (articleBody) {
        articleBody.addEventListener('click', function(e) {
            const link = e.target.closest('a');
            if (link && link.getAttribute('href')) {
                e.preventDefault();
                const href = link.getAttribute('href');
                // 如果是 markdown 文档链接
                if (href.endsWith('.md')) {
                    // 当前是文件夹页面，data.path 就是文件夹路径，直接拼接文件名
                    const targetPath = data.path + '\\' + href;
                    loadArticle(targetPath);
                }
            }
        });
    }
    
    document.querySelectorAll('.tree-item').forEach(item => {
        item.classList.remove('active');
    });
    const activeItem = document.querySelector('.tree-item[data-path="' + CSS.escape(data.path) + '"]');
    if (activeItem) {
        activeItem.classList.add('active');
        var parent = activeItem.parentElement;
        while (parent) {
            if (parent.classList && parent.classList.contains('tree-children')) {
                parent.style.display = 'block';
                var prevExpand = parent.previousElementSibling;
                if (prevExpand) {
                    var expandBtn = prevExpand.querySelector('.tree-expand');
                    if (expandBtn) expandBtn.style.transform = 'rotate(90deg)';
                }
            }
            parent = parent.parentElement;
        }
        setTimeout(function() {
            var treeContainer = document.querySelector('.sidebar-tree');
            if (treeContainer) {
                var itemRect = activeItem.getBoundingClientRect();
                var containerRect = treeContainer.getBoundingClientRect();
                if (itemRect.top < containerRect.top || itemRect.bottom > containerRect.bottom) {
                    activeItem.scrollIntoView({ block: 'center', behavior: 'smooth' });
                }
            }
        }, 100);
    }
    
    if (!isFolder) {
        generateToc();
    }
}

// 格式化日期
function formatDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// 生成目录
function generateToc() {
    const tocList = document.getElementById('toc-list');
    if (!tocList) return;
    
    const headers = document.querySelectorAll('.article-body h1, .article-body h2, .article-body h3');
    if (headers.length === 0) {
        tocList.innerHTML = '';
        return;
    }
    
    let html = '';
    headers.forEach((header, index) => {
        const level = parseInt(header.tagName.charAt(1));
        const id = `toc-${index}`;
        header.id = id;
        
        const indent = (level - 1) * 12;
        html += `
            <a href="#${id}" class="toc-item" style="padding-left: ${indent}px;">
                ${escapeHtml(header.textContent)}
            </a>
        `;
    });
    
    tocList.innerHTML = html;
}

// 切换文件夹设置菜单
function toggleFolderSettingsMenu(folderPath, button) {
    // 关闭其他菜单
    closeAllFolderSettingsMenus();
    
    // 获取当前菜单ID
    const menuId = `folder-settings-dropdown-${folderPath.replace(/[\\/:*?"<>|]/g, '_')}`;
    const menu = document.getElementById(menuId);
    
    if (menu) {
        menu.classList.toggle('show');
    }
}

// 关闭所有文件夹设置菜单
function closeAllFolderSettingsMenus() {
    document.querySelectorAll('.md-settings-dropdown').forEach(el => el.classList.remove('show'));
}

function closeAllToolbarDropdowns() {
    document.querySelectorAll('.article-toolbar-dropdown').forEach(el => el.classList.remove('show'));
}

// 文章全屏切换
function toggleArticleFullscreen() {
    const articleContent = document.querySelector('.article-content');
    if (!articleContent) return;
    
    const isFullscreen = articleContent.classList.toggle('article-fullscreen');
    
    // 切换图标
    const iconEnter = document.getElementById('fullscreen-icon-enter');
    const iconExit = document.getElementById('fullscreen-icon-exit');
    if (iconEnter && iconExit) {
        iconEnter.style.display = isFullscreen ? 'none' : '';
        iconExit.style.display = isFullscreen ? '' : 'none';
    }
}

// ESC 退出全屏 / 关闭 wiki 抽屉
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const wikiOverlay = document.getElementById('wiki-drawer-overlay');
        if (wikiOverlay && wikiOverlay.classList.contains('show')) {
            closeWikiDrawer();
            return;
        }
        const articleContent = document.querySelector('.article-content.article-fullscreen');
        if (articleContent) {
            articleContent.classList.remove('article-fullscreen');
            const iconEnter = document.getElementById('fullscreen-icon-enter');
            const iconExit = document.getElementById('fullscreen-icon-exit');
            if (iconEnter && iconExit) {
                iconEnter.style.display = '';
                iconExit.style.display = 'none';
            }
        }
    }
});

function toggleArticleFavorite(path, title, btn) {
    const favorites = JSON.parse(localStorage.getItem('blossom-favorites') || '[]');
    const index = favorites.findIndex(f => f.path === path);
    const star = btn.querySelector('.fav-star');
    
    if (index >= 0) {
        favorites.splice(index, 1);
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
        btn.setAttribute('title', '收藏');
        btn.setAttribute('aria-label', '收藏');
        if (star) star.setAttribute('fill', 'none');
    } else {
        favorites.push({ path: path, title: title });
        btn.classList.add('active');
        btn.setAttribute('aria-pressed', 'true');
        btn.setAttribute('title', '取消收藏');
        btn.setAttribute('aria-label', '取消收藏');
        if (star) star.setAttribute('fill', 'currentColor');
    }
    
    localStorage.setItem('blossom-favorites', JSON.stringify(favorites));
    
    if (typeof renderFavoritesCard === 'function') {
        renderFavoritesCard();
    }
}

function editArticle(filePath) {
    const contentEl = document.getElementById('article-content');
    const articleContent = document.querySelector('.article-content');
    if (!contentEl || !articleContent) return;

    const isFolder = filePath && !filePath.endsWith('.md');
    if (isFolder) {
        openFolderEditModal(filePath);
        return;
    }

    fetch(`/api/article/content?path=${encodeURIComponent(filePath)}`)
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                const rawContent = result.data.raw || '';
                
                // 更新工具栏为编辑模式
                let toolbarEl = articleContent.querySelector('.article-toolbar');
                if (!toolbarEl) {
                    toolbarEl = document.createElement('div');
                    toolbarEl.className = 'article-toolbar';
                    articleContent.insertBefore(toolbarEl, contentEl);
                }
                toolbarEl.setAttribute('data-article-path', filePath);
                toolbarEl.innerHTML = `
                    <div class="article-toolbar-left">
                        <span class="editor-title">编辑: ${escapeHtml(result.data.title || '无标题')}</span>
                    </div>
                    <div class="article-toolbar-right">
                        <button class="editor-btn editor-btn-save" id="editor-save-btn">保存</button>
                        <button class="editor-btn editor-btn-cancel" id="editor-cancel-btn">取消</button>
                    </div>
                `;
                toolbarEl.style.display = 'flex';

                // 内容区域只保留编辑工具栏和编辑器
                contentEl.innerHTML = `
                    <div class="article-edit-toolbar">
                        <button class="tool-btn" title="粗体 (Ctrl+B)" onclick="insertMarkdown('**', '**')}" aria-label="粗体">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 4h8a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/><path d="M6 12h9a4 4 0 0 1 4 4 4 4 0 0 1-4 4H6z"/></svg>
                        </button>
                        <button class="tool-btn" title="斜体 (Ctrl+I)" onclick="insertMarkdown('*', '*')" aria-label="斜体">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/></svg>
                        </button>
                        <button class="tool-btn" title="删除线" onclick="insertMarkdown('~~', '~~')" aria-label="删除线">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="12" x2="20" y2="12"/><path d="M16 6c-1.5-1.5-3.5-2-5-2-3 0-5 2-5 4 0 1.5 1 2.5 3 3"/><path d="M8 18c1.5 1.5 3.5 2 5 2 3 0 5-2 5-4 0-1.5-1-2.5-3-3"/></svg>
                        </button>
                        <span class="tool-sep"></span>
                        <button class="tool-btn" title="标题" onclick="insertMarkdown('# ', '')" aria-label="标题">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 12h12"/><path d="M6 20V4"/><path d="M18 20V4"/></svg>
                        </button>
                        <button class="tool-btn" title="无序列表" onclick="insertMarkdown('- ', '')" aria-label="无序列表">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                        </button>
                        <button class="tool-btn" title="引用" onclick="insertMarkdown('> ', '')" aria-label="引用">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3c0 1 0 1 1 1z"/></svg>
                        </button>
                        <button class="tool-btn" title="代码" onclick="insertMarkdown('\`', '\`')" aria-label="代码">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                        </button>
                        <span class="tool-sep"></span>
                        <button class="tool-btn" title="链接" onclick="insertLink()" aria-label="链接">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
                        </button>
                        <button class="tool-btn" title="图片" onclick="showImagePicker()" aria-label="图片">
                            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
                        </button>
                        <span class="tool-sep"></span>
                        <button class="tool-btn editor-btn-attach" id="editor-attach-btn" title="上传附件" aria-label="上传附件"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg></button>
                    </div>
                    <div class="editor-split">
                        <div class="editor-split-left">
                            <textarea class="article-editor-textarea" id="editor-textarea">${escapeHtml(rawContent)}</textarea>
                        </div>
                        <div class="editor-split-right">
                            <div class="editor-preview" id="editor-preview"></div>
                        </div>
                    </div>
                `;
                const textarea = document.getElementById('editor-textarea');
                const previewEl = document.getElementById('editor-preview');
                if (textarea) textarea.focus();

                let previewTimer = null;
                function updatePreview() {
                    clearTimeout(previewTimer);
                    previewTimer = setTimeout(() => {
                        fetch('/api/article/preview', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ content: textarea.value })
                        })
                        .then(r => r.json())
                        .then(res => {
                            if (res.code === 200 && previewEl) {
                                previewEl.innerHTML = res.data.content;
                            }
                        })
                        .catch(() => {});
                    }, 500);
                }
                updatePreview();
                textarea.addEventListener('input', updatePreview);

                document.getElementById('editor-save-btn').addEventListener('click', function() {
                    var newContent = textarea.value;
                    var firstLine = newContent.split('\n')[0];
                    var newTitle = firstLine.replace(/^#+\s*/, '').trim();
                    var oldTitle = filePath.split(/[\\/]/).pop().replace(/\.md$/, '');
                    var savePath = filePath;

                    fetch('/api/article/content', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path: savePath, content: newContent })
                    })
                    .then(r => r.json())
                    .then(res => {
                        if (res.code === 200) {
                            if (newTitle && newTitle !== oldTitle) {
                                fetch('/api/article/rename', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ file_path: savePath, new_name: newTitle + '.md' })
                                })
                                .then(r2 => r2.json())
                                .then(res2 => {
                                    if (res2.code === 200 && res2.data && res2.data.path) {
                                        loadDocTree();
                                        loadArticle(res2.data.path);
                                    } else {
                                        alert(res2.message || '重命名失败');
                                    }
                                })
                                .catch(() => {
                                    alert('重命名失败');
                                });
                            } else {
                                loadArticle(savePath);
                            }
                        } else {
                            alert(res.message || '保存失败');
                        }
                    })
                    .catch(() => alert('保存失败'));
                });

                document.getElementById('editor-cancel-btn').addEventListener('click', function() {
                    loadArticle(filePath);
                });

                document.getElementById('editor-attach-btn').addEventListener('click', function() {
                    showAttachmentModal();
                });
            }
        })
        .catch(() => alert('加载失败'));
}

// 打开文件夹编辑弹窗
function openFolderEditModal(folderPath) {
    const modal = document.getElementById('modal-folder-settings');
    if (!modal) return;
    
    // 保存当前编辑的文件夹路径
    currentEditingFolderPath = folderPath;
    
    // 获取文件夹名称（从.zsnote.json读取真实名称）
    fetch(`/api/article/folder-meta?path=${encodeURIComponent(folderPath)}`)
        .then(r => r.json())
        .then(result => {
            const folderName = result.code === 200 && result.data && result.data.name 
                ? result.data.name 
                : (folderPath.split('/').pop() || folderPath.split('\\').pop());
            
            const folderNameEl = document.getElementById('folder-name');
            if (folderNameEl) folderNameEl.value = folderName;
            
            const folderDescEl = document.getElementById('folder-description');
            if (folderDescEl) folderDescEl.value = result.code === 200 && result.data && result.data.description ? result.data.description : '';
            
            selectedFolderIcon = result.code === 200 && result.data && result.data.icon ? result.data.icon : 'Open file folder_3d';
            
            renderFolderIconGrid();
            const iconPreview = document.getElementById('icon-preview');
            if (iconPreview) {
                iconPreview.innerHTML = getFolderIconSvg(selectedFolderIcon, 32, 'modal-icon-preview-svg');
            }
            
            modal.classList.add('show');
        });
}

// 显示文件夹设置弹窗
function showFolderSettings(folderPath) {
    const modal = document.getElementById('modal-folder-settings');
    if (!modal) return;
    
    // 保存当前编辑的文件夹路径
    currentEditingFolderPath = folderPath;
    
    // 获取文件夹名称
    const folderName = folderPath.split('/').pop() || folderPath.split('\\').pop();
    
    const folderNameEl = document.getElementById('folder-name');
    if (folderNameEl) folderNameEl.value = folderName;
    const folderDescEl = document.getElementById('folder-description');
    if (folderDescEl) folderDescEl.value = '';
    
    // 读取.zsnote.json获取图标
    fetch(`/api/article/folder-meta?path=${encodeURIComponent(folderPath)}`)
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                selectedFolderIcon = result.data.icon || 'Open file folder_3d';
                if (folderDescEl) folderDescEl.value = result.data.description || '';
            } else {
                selectedFolderIcon = 'Open file folder_3d';
            }
            
            renderFolderIconGrid();
            const iconPreview = document.getElementById('icon-preview');
            if (iconPreview) {
                iconPreview.innerHTML = getFolderIconSvg(selectedFolderIcon, 32, 'modal-icon-preview-svg');
            }
        });
    
    modal.classList.add('show');
}

// 显示新建知识库弹窗
function showNewKnowledgeBaseModal() {
    const modal = document.getElementById('modal-folder-settings');
    if (!modal) return;
    
    // 清除编辑路径
    currentEditingFolderPath = null;
    
    const folderNameEl = document.getElementById('folder-name');
    if (folderNameEl) folderNameEl.value = '';
    const folderDescEl = document.getElementById('folder-description');
    if (folderDescEl) folderDescEl.value = '';
    
    // 初始化图标选择器
    selectedFolderIcon = 'Open file folder_3d';
    renderFolderIconGrid();
    const iconPreview = document.getElementById('icon-preview');
    if (iconPreview) {
        iconPreview.innerHTML = getFolderIconSvg(selectedFolderIcon, 32, 'modal-icon-preview-svg');
    }
    
    modal.classList.add('show');
}

// 渲染文件夹图标选择网格
function renderFolderIconGrid() {
    const grid = document.getElementById('icon-grid');
    if (!grid) return;
    
    let html = '';
    folderIcons.forEach(icon => {
        const iconSvg = getFolderIconSvg(icon, 22, 'icon-option-svg');
        html += `<div class="icon-option${icon === selectedFolderIcon ? ' selected' : ''}" data-icon="${icon}">${iconSvg}</div>`;
    });
    grid.innerHTML = html;
    
    // 绑定图标点击事件
    grid.querySelectorAll('.icon-option').forEach(el => {
        el.addEventListener('click', function() {
            selectedFolderIcon = this.dataset.icon;
            const preview = document.getElementById('icon-preview');
            if (preview) {
                preview.innerHTML = getFolderIconSvg(selectedFolderIcon, 32, 'modal-icon-preview-svg');
            }
            renderFolderIconGrid();
        });
    });
}

// 关闭文件夹设置弹窗
function closeFolderSettings() {
    const modal = document.getElementById('modal-folder-settings');
    if (modal) modal.classList.remove('show');
}

// 获取文章根路径
function loadArticleRootPath() {
    fetch('/api/article/init-paths', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
    .then(r => r.json())
    .then(result => {
        if (result.code === 200 && result.data && result.data.article_path) {
            // 提取文章文件夹的相对路径
            const fullPath = result.data.article_path;
            articleRootPath = '/resource/article';
            // 尝试从完整路径中提取相对路径
            if (fullPath.includes('resource' + '/')) {
                const idx = fullPath.indexOf('resource' + '/');
                articleRootPath = '/' + fullPath.substring(idx).replace(/\\/g, '/');
            }
        }
    });
}

// 保存文件夹设置
function saveFolderSettings() {
    const name = document.getElementById('folder-name')?.value?.trim();
    const desc = document.getElementById('folder-description')?.value?.trim();
    
    if (!name) {
        alert('请输入文件夹名称');
        return;
    }
    
    // 判断是新建还是编辑
    if (currentEditingFolderPath) {
        // 编辑模式：更新文件夹元信息
        fetch('/api/article/folder-meta', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentEditingFolderPath, name, description: desc, icon: selectedFolderIcon })
        })
        .then(r => r.json())
        .then(result => {
            if (result.code === 200) {
                closeFolderSettings();
                loadDocTree();
                const toolbarEl = document.querySelector('.article-toolbar');
                const currentPath = toolbarEl?.getAttribute('data-article-path');
                if (currentPath && currentPath === currentEditingFolderPath) {
                    loadArticle(currentEditingFolderPath);
                }
            } else {
                alert(result.message || '更新失败');
            }
        });
    } else {
        // 新建模式：创建文件夹
        fetch('/api/article/folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ parent_path: articleRootPath, name, description: desc, icon: selectedFolderIcon })
        })
        .then(r => r.json())
        .then(result => {
            if (result.code === 200) {
                closeFolderSettings();
                loadDocTree();
            } else {
                alert(result.message || '创建失败');
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    loadArticleRootPath();
    loadDocTree();
});

// 点击外部关闭文件夹设置菜单
document.addEventListener('click', function(e) {
    const settingsWrapper = e.target.closest('.md-folder-settings-wrapper');
    if (!settingsWrapper) {
        closeAllFolderSettingsMenus();
    }
    const toolbarWrapper = e.target.closest('.article-toolbar-menu-wrapper');
    if (!toolbarWrapper) {
        closeAllToolbarDropdowns();
    }
});