/**
 * 图片管理模块
 */

// SVG 图标库
var _picSvg = {
    loading: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="emoji-spin" aria-hidden="true"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>',
    folder: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    close: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
    closeSm: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>',
    chevronLeft: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>',
    chevronRight: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>',
    more: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>',
    moreSm: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>',
    edit: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>',
    trash: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>',
    warning: '<svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#D97706" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    image: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    upload: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
};

// 图片管理相关全局变量
var currentImages = [];
var allImagesCache = [];
var currentSelectedFolder = '';
var currentPreviewIndex = 0;
var pictureSelectMode = false;
var pictureSelectedPaths = new Set();
var treeOriginalOrder = null;
var currentViewMode = 'grid';

// 文件夹图标选项（32个可用图标，保留 emoji 系统但改用 icon 名称）
var pictureFolderIcons = [
    'Open file folder', 'File folder', 'Briefcase', 'Package',
    'Card file box', 'File cabinet', 'Books', 'Bookmark tabs',
    'Notebook', 'Open book', 'Closed book', 'Spiral notepad',
    'Card index', 'Card index dividers', 'Credit card', 'Identification card',
    'Envelope', 'Red envelope', 'Incoming envelope', 'Envelope with arrow',
    'Backpack', 'Handbag', 'Shopping bags', 'Clutch bag',
    'Money bag', 'Basket', 'Bucket', 'Bento box',
    'Beverage box', 'Takeout box', 'Toolbox', 'Wastebasket'
];

// 加载图片页面
function loadPicturePage() {
    initImagePath(function() {
        loadPictureTree();
        loadAllImages();
    });
}

function initImagePath(callback) {
    if (imagePath) {
        if (callback) callback();
        return;
    }
    fetch('/api/article/init-paths', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({})
    })
    .then(function(r) { return r.json(); })
    .then(function(result) {
        if (result.code === 200 && result.data && result.data.img_path) {
            imagePath = result.data.img_path;
        }
        if (callback) callback();
    })
    .catch(function() {
        if (callback) callback();
    });
}

// 加载图片目录树
function loadPictureTree() {
    var treeContainer = document.querySelector('.picture-tree-root');
    if (!treeContainer) return;

    fetch('/api/picture/tree')
        .then(function(response) { return response.json(); })
        .then(function(result) {
            if (result.code === 200 && result.data) {
                renderPictureTree(result.data, treeContainer);
                bindPictureTreeEvents();
            } else {
                treeContainer.innerHTML = '<li class="tree-empty">' +
                    _picSvg.folder +
                    '<span>' + (result && result.message ? result.message : '该路径下没有图片') + '</span>' +
                '</li>';
            }
        })
        .catch(function() {
            treeContainer.innerHTML = '<li class="tree-empty">' +
                _picSvg.folder +
                '<span>加载失败，请检查路径配置</span>' +
            '</li>';
        });
}

// 渲染图片目录树
function renderPictureTree(nodes, container) {
    if (!container) return;

    var html = '';
    nodes.forEach(function(node) {
        var imageCount = countImagesInFolder(node);
        var iconHtml = node.icon
            ? '<img class="tree-folder-emoji" src="/api/article/emoji/' + encodeURIComponent(node.icon) + '" alt="">'
            : _picSvg.folder;

        html += '<li>' +
            '<div class="picture-tree-item folder" data-path="' + node.path + '" data-type="folder" role="treeitem" tabindex="0" title="' + escapeHtml(node.name) + '">' +
                iconHtml +
                '<span class="tree-name">' + escapeHtml(node.name) + '</span>' +
                (imageCount > 0 ? '<span class="folder-count">' + imageCount + '</span>' : '') +
                '<span class="tree-item-menu" data-path="' + escapeHtml(node.path) + '" aria-label="更多操作" title="更多操作">' +
                    _picSvg.moreSm +
                '</span>' +
            '</div>' +
        '</li>';
    });

    container.innerHTML = html;
}

// 计算文件夹中的图片数量
function countImagesInFolder(node) {
    if (node.type === 'file') return 1;
    var count = 0;
    if (node.children) {
        node.children.forEach(function(child) { count += countImagesInFolder(child); });
    }
    return count;
}

// 绑定图片树事件
function bindPictureTreeEvents() {
    var treeItems = document.querySelectorAll('.picture-tree-item');
    treeItems.forEach(function(item) {
        item.addEventListener('click', function(event) {
            if (event.target.closest('.tree-item-menu')) {
                showPictureTreeMenu(event, this.dataset.path);
                return;
            }
            var path = this.dataset.path;
            document.querySelectorAll('.picture-tree-item').forEach(function(i) { i.classList.remove('active'); });
            this.classList.add('active');
            currentSelectedFolder = path;
            var btnUpload = document.getElementById('btn-upload');
            if (btnUpload) btnUpload.style.display = '';
            loadImagesByFolder(path);
        });

        item.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                this.click();
            }
        });
    });

    bindViewToggle();
}

// 显示图片树菜单
function showPictureTreeMenu(event, folderPath) {
    event.stopPropagation();
    _closeAllMenus();

    var menu = document.getElementById('tree-item-dd');
    if (menu) menu.remove();

    menu = document.createElement('div');
    menu.id = 'tree-item-dd';
    menu.className = 'tree-item-dropdown show';
    menu.setAttribute('role', 'menu');

    var editBtn = document.createElement('button');
    editBtn.setAttribute('role', 'menuitem');
    editBtn.innerHTML = _picSvg.edit + ' 编辑图标';
    editBtn.addEventListener('click', function() { showEditFolderModal(folderPath); });
    menu.appendChild(editBtn);

    var deleteBtn = document.createElement('button');
    deleteBtn.setAttribute('role', 'menuitem');
    deleteBtn.innerHTML = _picSvg.trash + ' 删除文件夹';
    deleteBtn.addEventListener('click', function() { confirmDeleteFolder(folderPath); });
    menu.appendChild(deleteBtn);

    document.body.appendChild(menu);

    var rect = menu.getBoundingClientRect();
    var left = event.clientX;
    var top = event.clientY;
    if (left + rect.width > window.innerWidth - 8) left = window.innerWidth - rect.width - 8;
    if (top + rect.height > window.innerHeight - 8) top = window.innerHeight - rect.height - 8;
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
}

// 绑定视图切换按钮
function bindViewToggle() {
    var viewBtns = document.querySelectorAll('.view-btn');
    viewBtns.forEach(function(btn) {
        btn.addEventListener('click', function() {
            var view = this.dataset.view;
            if (view === currentViewMode) return;
            currentViewMode = view;
            viewBtns.forEach(function(b) { b.classList.remove('active'); b.setAttribute('aria-checked', 'false'); });
            this.classList.add('active');
            this.setAttribute('aria-checked', 'true');
            renderImages(currentImages);
        });
    });
}

// 搜索过滤图片目录树（带防抖）
var _pictureSearchTimer = null;
function filterPictureTree() {
    clearTimeout(_pictureSearchTimer);
    _pictureSearchTimer = setTimeout(_doFilterPictureTree, 200);
}

function _doFilterPictureTree() {
    var input = document.getElementById('folder-search');
    var keyword = (input ? input.value : '').trim().toLowerCase();
    var treeRoot = document.querySelector('.picture-tree-root');

    if (!treeRoot) return;

    if (!keyword) {
        restoreTreeOrder(treeRoot);
        allTreeItemsShow(treeRoot);
        if (currentSelectedFolder) {
            loadImagesByFolder(currentSelectedFolder);
        } else {
            renderImages(allImagesCache);
        }
        return;
    }

    if (!treeOriginalOrder) {
        cacheTreeOrder(treeRoot);
    }

    var items = Array.from(treeRoot.children);
    var matched = [];
    var unmatched = [];

    items.forEach(function(li) {
        var name = (li.querySelector('.tree-name') || {}).textContent || '';
        if (name.toLowerCase().indexOf(keyword) >= 0) {
            matched.push(li);
        } else {
            unmatched.push(li);
        }
    });

    matched.forEach(function(li) { li.style.display = ''; treeRoot.prepend(li); });
    unmatched.forEach(function(li) { li.style.display = 'none'; });

    var filtered = allImagesCache.filter(function(img) { return img.name.toLowerCase().indexOf(keyword) >= 0; });
    currentImages = filtered;
    renderImages(filtered);
}

function cacheTreeOrder(treeRoot) {
    treeOriginalOrder = Array.from(treeRoot.children).slice();
}

function restoreTreeOrder(treeRoot) {
    if (!treeOriginalOrder) return;
    treeOriginalOrder.forEach(function(li) { treeRoot.appendChild(li); });
    treeOriginalOrder = null;
}

function allTreeItemsShow(treeRoot) {
    treeRoot.querySelectorAll('li').forEach(function(li) { li.style.display = ''; });
}

// ── Skeleton loading ──
function _showImageSkeleton() {
    var gridContainer = document.getElementById('image-grid');
    if (!gridContainer) return;
    var countEl = document.getElementById('image-count');
    if (countEl) countEl.textContent = '...';
    var skeletonHtml = '<div class="image-grid-skeleton">';
    for (var i = 0; i < 8; i++) {
        skeletonHtml += '<div class="image-skeleton-card"></div>';
    }
    skeletonHtml += '</div>';
    gridContainer.innerHTML = skeletonHtml;
}

// 加载所有图片
function loadAllImages() {
    _showImageSkeleton();
    fetch('/api/picture/images')
        .then(function(response) { return response.json(); })
        .then(function(result) {
            if (!result || result.code !== 200 || !result.data) { renderImages([]); return; }
            currentImages = result.data.map(function(img) {
                return {
                    name: img.name, path: img.path,
                    url: '/api/picture/image?img=' + encodeURIComponent(img.path),
                    size: img.size, modified: img.modified
                };
            });
            allImagesCache = currentImages.slice();
            renderImages(currentImages);
        })
        .catch(function() { renderImages([]); });
}

// 按文件夹加载图片
function loadImagesByFolder(folderPath) {
    _showImageSkeleton();
    fetch('/api/picture/images')
        .then(function(response) { return response.json(); })
        .then(function(result) {
            if (!result || result.code !== 200 || !result.data) { renderImages([]); return; }
            var filteredImages = result.data.filter(function(img) {
                if (!folderPath) return true;
                return img.full_path && img.full_path.indexOf(folderPath) === 0;
            });
            currentImages = filteredImages.map(function(img) {
                return {
                    name: img.name, path: img.path,
                    url: '/api/picture/image?img=' + encodeURIComponent(img.path),
                    size: img.size, modified: img.modified
                };
            });
            renderImages(currentImages);
        })
        .catch(function() { renderImages([]); });
}

// 渲染图片卡片
function renderImages(images) {
    var gridContainer = document.getElementById('image-grid');
    var countEl = document.getElementById('image-count');

    if (!gridContainer) return;

    if (!images || images.length === 0) {
        gridContainer.innerHTML = '<div class="empty-state">' +
            _picSvg.image +
            '<p>暂无图片</p>' +
            '<p class="empty-hint">该文件夹下没有图片文件</p>' +
        '</div>';
        if (countEl) countEl.textContent = '0';
        return;
    }

    if (countEl) countEl.textContent = String(images.length);

    if (currentViewMode === 'list') {
        var listHtml = '<div class="image-list">';
        listHtml += '<div class="image-list-header"><span class="list-col-name">名称</span><span class="list-col-size">大小</span><span class="list-col-date">修改时间</span></div>';
        images.forEach(function(img, index) {
            var size = formatFileSize(img.size);
            var date = formatDate(img.modified);
            var modeClass = pictureSelectMode ? ' select-mode' : '';
            var selClass = pictureSelectMode && pictureSelectedPaths.has(img.path) ? ' selected' : '';
            var clickHandler = pictureSelectMode
                ? 'onclick="toggleImageSelect(' + index + ', event)"'
                : 'onclick="showImagePreview(currentImages, ' + index + ')"';
            listHtml += '<div class="image-list-item' + modeClass + selClass + '" data-index="' + index + '" ' + clickHandler + ' tabindex="0" role="option" aria-selected="' + (!!selClass) + '">' +
                '<span class="list-col-name"><img src="' + img.url + '" alt="' + escapeHtml(img.name) + '" class="list-thumb" loading="lazy">' +
                '<span class="list-name">' + escapeHtml(img.name) + '</span></span>' +
                '<span class="list-col-size">' + size + '</span>' +
                '<span class="list-col-date">' + date + '</span>' +
            '</div>';
        });
        listHtml += '</div>';
        gridContainer.innerHTML = listHtml;
    } else {
        var gridHtml = '<div class="image-grid">';
        images.forEach(function(img, index) {
            var size = formatFileSize(img.size);
            var date = formatDate(img.modified);
            var modeClass = pictureSelectMode ? ' select-mode' : '';
            var selClass = pictureSelectMode && pictureSelectedPaths.has(img.path) ? ' selected' : '';
            var clickHandler = pictureSelectMode
                ? 'onclick="toggleImageSelect(' + index + ', event)"'
                : 'onclick="showImagePreview(currentImages, ' + index + ')"';
            gridHtml += '<div class="image-card' + modeClass + selClass + '" data-index="' + index + '" ' + clickHandler + ' tabindex="0" role="button" aria-label="' + escapeHtml(img.name) + '">' +
                '<div class="image-preview">' +
                    '<img src="' + img.url + '" alt="' + escapeHtml(img.name) + '" loading="lazy">' +
                    (pictureSelectMode ? '<span class="image-check" aria-hidden="true">' + _picSvg.check + '</span>' : '') +
                '</div>' +
                '<div class="image-info">' +
                    '<span class="image-name">' + escapeHtml(img.name) + '</span>' +
                    '<span class="image-meta">' + size + ' &middot; ' + date + '</span>' +
                '</div>' +
            '</div>';
        });
        gridHtml += '</div>';
        gridContainer.innerHTML = gridHtml;
    }
}

// 显示图片预览弹窗
function showImagePreview(images, index) {
    if (!images || images.length === 0) return;

    currentImages = images;
    currentPreviewIndex = index;

    var modal = document.getElementById('image-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'image-modal';
        modal.className = 'image-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', '图片预览');
        modal.innerHTML = '<div class="modal-overlay" onclick="closeImageModal()"></div>' +
            '<div class="modal-content">' +
                '<button class="modal-close" onclick="closeImageModal()" aria-label="关闭">' + _picSvg.close + '</button>' +
                '<button class="modal-nav modal-prev" onclick="prevImage()" aria-label="上一张">' + _picSvg.chevronLeft + '</button>' +
                '<button class="modal-nav modal-next" onclick="nextImage()" aria-label="下一张">' + _picSvg.chevronRight + '</button>' +
                '<div class="image-preview-container" id="preview-container">' +
                    '<img id="preview-image" src="" alt="">' +
                '</div>' +
                '<div class="modal-info">' +
                    '<span id="preview-name"></span>' +
                    '<span id="preview-index"></span>' +
                '</div>' +
            '</div>';
        document.body.appendChild(modal);

        // 键盘导航
        modal.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeImageModal();
            if (e.key === 'ArrowLeft') prevImage();
            if (e.key === 'ArrowRight') nextImage();
        });
    }

    updatePreviewContent();
    modal.classList.add('show');
}

// 更新预览内容
function updatePreviewContent() {
    var img = document.getElementById('preview-image');
    var nameEl = document.getElementById('preview-name');
    var indexEl = document.getElementById('preview-index');

    if (!img || !nameEl || !indexEl) return;

    var currentImg = currentImages[currentPreviewIndex];
    if (currentImg) {
        img.src = currentImg.url;
        img.alt = currentImg.name;
        nameEl.textContent = currentImg.name;
        indexEl.textContent = (currentPreviewIndex + 1) + ' / ' + currentImages.length;
    }
}

// 关闭图片预览弹窗
function closeImageModal() {
    var modal = document.getElementById('image-modal');
    if (modal) modal.classList.remove('show');
}

// 上一张图片
function prevImage() {
    if (currentPreviewIndex > 0) { currentPreviewIndex--; updatePreviewContent(); }
}

// 下一张图片
function nextImage() {
    if (currentPreviewIndex < currentImages.length - 1) { currentPreviewIndex++; updatePreviewContent(); }
}

// 切换到图片视图时加载
document.addEventListener('viewChange', function(event) {
    if (event.detail.view === 'picture') loadPicturePage();
});

// 点击外部关闭三点菜单
document.addEventListener('click', function(e) {
    var dd = document.getElementById('tree-item-dd');
    if (dd && !dd.contains(e.target) && !e.target.closest('.tree-item-menu')) {
        dd.remove();
    }
});

// 图片选择模式相关函数
function enterSelectMode() {
    _closeAllToolbarMenus();
    pictureSelectMode = true;
    pictureSelectedPaths.clear();
    var actions = document.getElementById('select-actions');
    var btnUpload = document.getElementById('btn-upload');
    var moreWrap = document.querySelector('.toolbar-more-wrap');
    if (actions) actions.style.display = 'flex';
    if (btnUpload) btnUpload.style.display = 'none';
    if (moreWrap) moreWrap.style.display = 'none';
    updateSelectedCount();
    renderImages(currentImages);
}

function toggleSelectMode() {
    pictureSelectMode = !pictureSelectMode;
    pictureSelectedPaths.clear();
    var actions = document.getElementById('select-actions');
    var btnUpload = document.getElementById('btn-upload');
    var moreWrap = document.querySelector('.toolbar-more-wrap');
    if (pictureSelectMode) {
        if (actions) actions.style.display = 'flex';
        if (btnUpload) btnUpload.style.display = 'none';
        if (moreWrap) moreWrap.style.display = 'none';
        updateSelectedCount();
    } else {
        if (actions) actions.style.display = 'none';
        if (btnUpload) btnUpload.style.display = '';
        if (moreWrap) moreWrap.style.display = '';
        document.getElementById('select-all-cb').checked = false;
    }
    renderImages(currentImages);
}

function cancelSelectMode() {
    pictureSelectMode = false;
    pictureSelectedPaths.clear();
    var actions = document.getElementById('select-actions');
    var btnUpload = document.getElementById('btn-upload');
    var moreWrap = document.querySelector('.toolbar-more-wrap');
    if (actions) actions.style.display = 'none';
    if (btnUpload) btnUpload.style.display = '';
    if (moreWrap) moreWrap.style.display = '';
    renderImages(currentImages);
}

function toggleImageSelect(index, event) {
    event.stopPropagation();
    var img = currentImages[index];
    if (!img) return;
    if (pictureSelectedPaths.has(img.path)) {
        pictureSelectedPaths.delete(img.path);
    } else {
        pictureSelectedPaths.add(img.path);
    }
    updateSelectedCount();
    renderImages(currentImages);
}

function toggleSelectAll(checked) {
    if (checked) {
        currentImages.forEach(function(img) { pictureSelectedPaths.add(img.path); });
    } else {
        pictureSelectedPaths.clear();
    }
    updateSelectedCount();
    renderImages(currentImages);
}

function updateSelectedCount() {
    var el = document.getElementById('selected-count');
    if (el) el.textContent = pictureSelectedPaths.size;
}

// 文件夹操作函数
function showTreeItemMenu(event, folderPath) {
    event.stopPropagation();
    _closeAllMenus();
    var menu = document.getElementById('tree-item-dd');
    if (menu) menu.remove();

    menu = document.createElement('div');
    menu.id = 'tree-item-dd';
    menu.className = 'tree-item-dropdown show';
    menu.setAttribute('role', 'menu');

    var editBtn = document.createElement('button');
    editBtn.setAttribute('role', 'menuitem');
    editBtn.innerHTML = _picSvg.edit + ' 编辑图标';
    editBtn.addEventListener('click', function() { showEditFolderModal(folderPath); });
    menu.appendChild(editBtn);

    var btn = document.createElement('button');
    btn.setAttribute('role', 'menuitem');
    btn.innerHTML = _picSvg.trash + ' 删除文件夹';
    btn.addEventListener('click', function() { confirmDeleteFolder(folderPath); });
    menu.appendChild(btn);
    menu.style.position = 'fixed';
    menu.style.zIndex = '200';
    document.body.appendChild(menu);

    var rect = menu.getBoundingClientRect();
    var left = event.clientX;
    var top = event.clientY;
    if (left + rect.width > window.innerWidth - 8) left = window.innerWidth - rect.width - 8;
    if (top + rect.height > window.innerHeight - 8) top = window.innerHeight - rect.height - 8;
    menu.style.left = left + 'px';
    menu.style.top = top + 'px';
}

// 图片弹窗相关
function showPicModal(html) {
    var overlay = document.getElementById('pic-modal-overlay');
    var content = document.getElementById('pic-modal-content');
    if (!overlay || !content) return;
    content.innerHTML = html;
    overlay.classList.add('show');
}

var editFolderIcon = 'Open file folder';
var editFolderPath = '';

function showEditFolderModal(folderPath) {
    _closeAllMenus();
    editFolderPath = folderPath;
    var overlay = document.getElementById('pic-modal-overlay');
    var content = document.getElementById('pic-modal-content');
    if (!overlay || !content) return;

    var folderName = folderPath.split(/[/\\]/).pop();
    var treeItem = document.querySelector('.picture-tree-item[data-path="' + folderPath.replace(/\\/g, '\\\\') + '"]');
    var emojiImg = treeItem ? treeItem.querySelector('.tree-folder-emoji') : null;
    editFolderIcon = emojiImg ? 'Open file folder' : '';
    if (emojiImg) {
        var src = emojiImg.src || '';
        var match = src.match(/emoji\/(.+)$/);
        if (match) editFolderIcon = decodeURIComponent(match[1]);
    }
    if (!editFolderIcon) editFolderIcon = 'Open file folder';

    var iconUrl = '/api/article/emoji/' + encodeURIComponent(editFolderIcon);

    content.innerHTML = '<div class="pic-modal-header"><h3>编辑文件夹</h3><button class="btn-close" id="ef-close" aria-label="关闭">' + _picSvg.closeSm + '</button></div>' +
        '<div class="pic-modal-body">' +
            '<div class="form-group">' +
                '<label>文件夹图标</label>' +
                '<div class="pic-folder-icon-row">' +
                    '<div class="icon-picker-hover" style="position:relative;">' +
                        '<div class="icon-preview" id="ef-icon-preview"><img src="' + iconUrl + '" alt="icon"></div>' +
                        '<div class="icon-dropdown" id="ef-icon-dropdown"><div class="icon-grid" id="ef-icon-grid"></div></div>' +
                    '</div>' +
                    '<input type="text" class="form-input" value="' + escapeHtml(folderName) + '" disabled style="flex:1;opacity:0.6;" />' +
                '</div>' +
                '<div class="form-hint" id="ef-hint" style="display:none;"></div>' +
            '</div>' +
        '</div>' +
        '<div class="pic-modal-footer">' +
            '<button class="toolbar-btn" id="ef-cancel">取消</button>' +
            '<button class="toolbar-btn toolbar-btn-primary" id="ef-submit">保存</button>' +
        '</div>';

    content.querySelector('#ef-close').addEventListener('click', closePicModal);
    content.querySelector('#ef-cancel').addEventListener('click', closePicModal);
    content.querySelector('#ef-submit').addEventListener('click', doUpdateFolderIcon);

    var efIconPreview = document.getElementById('ef-icon-preview');
    var efIconDropdown = document.getElementById('ef-icon-dropdown');
    if (efIconPreview && efIconDropdown) {
        efIconPreview.addEventListener('click', function(event) {
            event.stopPropagation();
            efIconDropdown.classList.toggle('show');
            if (efIconDropdown.classList.contains('show')) {
                var rect = efIconPreview.getBoundingClientRect();
                efIconDropdown.style.left = rect.left + 'px';
                efIconDropdown.style.top = (rect.bottom + 8) + 'px';
            }
        });
    }

    document.addEventListener('click', function closeEfIconDropdown() {
        if (efIconDropdown) efIconDropdown.classList.remove('show');
        document.removeEventListener('click', closeEfIconDropdown);
    });

    renderEditIconGrid();
    overlay.classList.add('show');
}

function renderEditIconGrid() {
    var grid = document.getElementById('ef-icon-grid');
    if (!grid) return;
    var html = '';
    pictureFolderIcons.forEach(function(icon) {
        var iconUrl = '/api/article/emoji/' + encodeURIComponent(icon);
        html += '<div class="icon-option' + (icon === editFolderIcon ? ' selected' : '') + '" data-icon="' + icon + '">' +
            '<img src="' + iconUrl + '" alt="' + icon + '" />' +
        '</div>';
    });
    grid.innerHTML = html;
    grid.querySelectorAll('.icon-option').forEach(function(el) {
        el.addEventListener('click', function() {
            editFolderIcon = this.dataset.icon;
            var preview = document.getElementById('ef-icon-preview');
            if (preview) preview.querySelector('img').src = '/api/article/emoji/' + encodeURIComponent(editFolderIcon);
            renderEditIconGrid();
        });
    });
}

function doUpdateFolderIcon() {
    var hint = document.getElementById('ef-hint');
    fetch('/api/picture/folder-icon', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: editFolderPath, icon: editFolderIcon})
    }).then(function(r) { return r.json(); }).then(function(result) {
        if (result.code === 200) { closePicModal(); loadPictureTree(); }
        else { if (hint) { hint.textContent = result.message || '更新失败'; hint.style.display = 'block'; } }
    });
}

function closePicModal() {
    var overlay = document.getElementById('pic-modal-overlay');
    if (overlay) overlay.classList.remove('show');
}

var selectedPicFolderIcon = 'Open file folder';

function showNewFolderModal() {
    _closeAllMenus();
    selectedPicFolderIcon = 'Open file folder';
    var overlay = document.getElementById('pic-modal-overlay');
    var content = document.getElementById('pic-modal-content');
    if (!overlay || !content) return;

    content.innerHTML = '<div class="pic-modal-header"><h3>新建文件夹</h3><button class="btn-close" id="nf-close" aria-label="关闭">' + _picSvg.closeSm + '</button></div>' +
        '<div class="pic-modal-body">' +
            '<div class="form-group">' +
                '<label>文件夹图标与名称</label>' +
                '<div class="pic-folder-icon-row">' +
                    '<div class="icon-picker-hover" style="position:relative;">' +
                        '<div class="icon-preview" id="pic-icon-preview"><img src="/api/article/emoji/Open%20file%20folder" alt="icon"></div>' +
                        '<div class="icon-dropdown" id="pic-icon-dropdown"><div class="icon-grid" id="pic-icon-grid"></div></div>' +
                    '</div>' +
                    '<input type="text" class="form-input" id="new-folder-name" placeholder="请输入文件夹名称" style="flex:1;" />' +
                '</div>' +
                '<div class="form-hint" id="nf-hint" style="display:none;"></div>' +
            '</div>' +
        '</div>' +
        '<div class="pic-modal-footer">' +
            '<button class="toolbar-btn" id="nf-cancel">取消</button>' +
            '<button class="toolbar-btn toolbar-btn-primary" id="nf-submit">创建</button>' +
        '</div>';

    content.querySelector('#nf-close').addEventListener('click', closePicModal);
    content.querySelector('#nf-cancel').addEventListener('click', closePicModal);
    content.querySelector('#nf-submit').addEventListener('click', doCreateFolder);

    var iconPreview = document.getElementById('pic-icon-preview');
    var iconDropdown = document.getElementById('pic-icon-dropdown');
    if (iconPreview && iconDropdown) {
        iconPreview.addEventListener('click', function(event) {
            event.stopPropagation();
            iconDropdown.classList.toggle('show');
            if (iconDropdown.classList.contains('show')) {
                var rect = iconPreview.getBoundingClientRect();
                iconDropdown.style.left = rect.left + 'px';
                iconDropdown.style.top = (rect.bottom + 8) + 'px';
            }
        });
    }

    document.addEventListener('click', function closeIconDropdown() {
        if (iconDropdown) iconDropdown.classList.remove('show');
        document.removeEventListener('click', closeIconDropdown);
    });

    renderPicIconGrid();
    overlay.classList.add('show');
}

function renderPicIconGrid() {
    var grid = document.getElementById('pic-icon-grid');
    if (!grid) return;
    var html = '';
    pictureFolderIcons.forEach(function(icon) {
        var iconUrl = '/api/article/emoji/' + encodeURIComponent(icon);
        html += '<div class="icon-option' + (icon === selectedPicFolderIcon ? ' selected' : '') + '" data-icon="' + icon + '">' +
            '<img src="' + iconUrl + '" alt="' + icon + '" />' +
        '</div>';
    });
    grid.innerHTML = html;
    grid.querySelectorAll('.icon-option').forEach(function(el) {
        el.addEventListener('click', function() {
            selectedPicFolderIcon = this.dataset.icon;
            var preview = document.getElementById('pic-icon-preview');
            if (preview) preview.querySelector('img').src = '/api/article/emoji/' + encodeURIComponent(selectedPicFolderIcon);
            renderPicIconGrid();
        });
    });
}

function doCreateFolder() {
    var nameEl = document.getElementById('new-folder-name');
    var name = (nameEl ? nameEl.value : '').trim();
    if (!name) {
        var hint = document.getElementById('nf-hint');
        if (hint) { hint.textContent = '请输入文件夹名称'; hint.style.display = 'block'; }
        return;
    }
    var hint = document.getElementById('nf-hint');
    if (hint) hint.style.display = 'none';
    fetch('/api/picture/folder', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({parent_path: imagePath || '', name: name, icon: selectedPicFolderIcon})
    }).then(function(r) { return r.json(); }).then(function(result) {
        if (result.code === 200) { closePicModal(); loadPictureTree(); }
        else { if (hint) { hint.textContent = result.message || '创建失败'; hint.style.display = 'block'; } }
    });
}

function confirmDeleteFolder(folderPath) {
    _closeAllMenus();
    var name = folderPath.split(/[/\\]/).pop();
    var overlay = document.getElementById('pic-modal-overlay');
    var content = document.getElementById('pic-modal-content');
    if (!overlay || !content) return;

    content.innerHTML = '<div class="pic-modal-header"><h3>确认删除</h3><button class="btn-close" id="modal-close-btn" aria-label="关闭">' + _picSvg.closeSm + '</button></div>' +
        '<div class="pic-modal-body" style="text-align:center;padding:24px;">' +
            _picSvg.warning +
            '<p style="margin-top:12px;">确定要删除文件夹 <strong>' + escapeHtml(name) + '</strong> 吗？</p>' +
            '<p style="color:var(--color-muted, #909399);font-size:13px;">该文件夹下的所有图片将被永久删除，此操作不可恢复。</p>' +
        '</div>' +
        '<div class="pic-modal-footer">' +
            '<button class="toolbar-btn" id="modal-cancel-btn">取消</button>' +
            '<button class="toolbar-btn toolbar-btn-danger" id="modal-confirm-btn">确认删除</button>' +
        '</div>';
    content.querySelector('#modal-close-btn').addEventListener('click', closePicModal);
    content.querySelector('#modal-cancel-btn').addEventListener('click', closePicModal);
    content.querySelector('#modal-confirm-btn').addEventListener('click', function() { doDeleteFolder(folderPath); });
    overlay.classList.add('show');
}

function doDeleteFolder(folderPath) {
    fetch('/api/picture/folder', {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: folderPath})
    }).then(function(r) { return r.json(); }).then(function(result) {
        if (result.code === 200) { closePicModal(); loadPictureTree(); }
        else { alert(result.message || '删除失败'); }
    });
}

// 图片上传相关
function triggerImageUpload() {
    var el = document.getElementById('file-upload-input');
    if (el) el.click();
}

function handleImageUpload(files) {
    if (!files || !files.length) return;
    var targetFolder = currentSelectedFolder || imagePath || '';
    var formData = new FormData();
    formData.append('target_folder', targetFolder);
    for (var i = 0; i < files.length; i++) { formData.append('files', files[i]); }

    fetch('/api/picture/upload', {method: 'POST', body: formData})
        .then(function(r) { return r.json(); }).then(function(result) {
            if (result.code === 200) {
                if (currentSelectedFolder) { loadImagesByFolder(currentSelectedFolder); }
                else { loadAllImages(); }
            } else {
                alert(result.message || '上传失败');
            }
            var el = document.getElementById('file-upload-input');
            if (el) el.value = '';
        });
}

// 确认删除选中图片
function confirmDeleteSelected() {
    if (pictureSelectedPaths.size === 0) return;
    var count = pictureSelectedPaths.size;
    showPicModal('<div class="pic-modal-header"><h3>确认删除</h3><button class="btn-close" onclick="closePicModal()" aria-label="关闭">' + _picSvg.closeSm + '</button></div>' +
        '<div class="pic-modal-body" style="text-align:center;padding:24px;">' +
            _picSvg.warning +
            '<p style="margin-top:12px;">确定要删除选中的 <strong>' + count + '</strong> 张图片吗？</p>' +
            '<p style="color:var(--color-muted, #909399);font-size:13px;">此操作不可恢复。</p>' +
        '</div>' +
        '<div class="pic-modal-footer">' +
            '<button class="toolbar-btn" onclick="closePicModal()">取消</button>' +
            '<button class="toolbar-btn toolbar-btn-danger" onclick="doDeleteSelected()">确认删除</button>' +
        '</div>');
}

function doDeleteSelected() {
    fetch('/api/picture/delete-images', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({paths: Array.from(pictureSelectedPaths)})
    }).then(function(r) { return r.json(); }).then(function(result) {
        if (result.code === 200) {
            closePicModal();
            cancelSelectMode();
            if (currentSelectedFolder) { loadImagesByFolder(currentSelectedFolder); }
            else { loadAllImages(); }
        } else {
            alert(result.message || '删除失败');
        }
    });
}
