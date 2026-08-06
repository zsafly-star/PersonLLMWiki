/**
 * 仪表盘模块
 * 包含首页卡片拖拽、调整大小、收藏等功能
 */

// 初始化拖拽功能
function initDragAndDrop() {
    const dashboard = document.getElementById('dashboard');
    if (!dashboard) return;
    
    const cards = dashboard.querySelectorAll('.bento-card');
    cards.forEach(card => {
        card.addEventListener('dragstart', handleDragStart);
        card.addEventListener('dragend', handleDragEnd);
        card.addEventListener('dragover', handleDragOver);
        card.addEventListener('drop', handleDrop);
    });
}

let draggedCard = null;

function handleDragStart(e) {
    draggedCard = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragEnd() {
    draggedCard = null;
    this.classList.remove('dragging');
    document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (draggedCard && this !== draggedCard) {
        this.classList.add('drag-over');
    }
}

function handleDrop(e) {
    e.preventDefault();
    this.classList.remove('drag-over');
    
    if (draggedCard && this !== draggedCard) {
        // 交换位置
        const container = document.getElementById('dashboard');
        const cards = Array.from(container.children);
        const oldIndex = cards.indexOf(draggedCard);
        const newIndex = cards.indexOf(this);
        
        if (oldIndex < newIndex) {
            container.insertBefore(draggedCard, this.nextSibling);
        } else {
            container.insertBefore(draggedCard, this);
        }
        
        // 保存布局
        saveLayout();
    }
}

// 初始化卡片大小调整
function initResizeCards() {
    const cards = document.querySelectorAll('.bento-card');
    cards.forEach(card => {
        // 添加双击切换大小功能
        card.addEventListener('dblclick', function() {
            const currentSize = this.dataset.size || '1x1';
            if (currentSize === '1x1') {
                this.dataset.size = '2x2';
                this.style.gridColumn = 'span 2';
                this.style.gridRow = 'span 2';
            } else {
                this.dataset.size = '1x1';
                this.style.gridColumn = 'span 1';
                this.style.gridRow = 'span 1';
            }
            saveLayout();
        });
    });
}

// 渲染收藏卡片
function renderFavoritesCard() {
    const favoritesRoot = document.getElementById('article-stars-root');
    if (!favoritesRoot) return;
    
    // 从localStorage获取收藏数据
    const favorites = JSON.parse(localStorage.getItem('blossom-favorites') || '[]');
    
    if (favorites.length === 0) {
        favoritesRoot.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #909399; font-size: 13px;">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 8px;"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                <p>暂无收藏文档</p>
            </div>
        `;
        return;
    }
    
    let html = '<div class="favorites-list">';
    favorites.forEach(fav => {
        html += `
            <div class="favorite-item" onclick="openFavorite('${escapeHtml(fav.path)}')">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>
                <span class="favorite-name">${escapeHtml(fav.title || fav.path.split('/').pop())}</span>
            </div>
        `;
    });
    html += '</div>';
    
    favoritesRoot.innerHTML = html;
}

// 打开收藏文档
function openFavorite(path) {
    // 导航到文章页面
    window.location.href = `/article?path=${encodeURIComponent(path)}`;
}

// 初始化设置（已在settings.js中实现，这里保持兼容）
function initSettings() {
    // 空实现，保持兼容性
}

// 加载保存的主题
function loadSavedTheme() {
    const savedTheme = localStorage.getItem('blossom-theme') || 'light';
    applyTheme(savedTheme);
}

// 加载保存的布局
function loadSavedLayout() {
    const savedLayout = localStorage.getItem('blossom-layout');
    if (!savedLayout) return;
    
    try {
        const layout = JSON.parse(savedLayout);
        const cards = document.querySelectorAll('.bento-card');
        cards.forEach(card => {
            const cardId = card.dataset.id;
            const cardLayout = layout[cardId];
            if (cardLayout) {
                card.style.gridColumn = `span ${cardLayout.colSpan || 1}`;
                card.style.gridRow = `span ${cardLayout.rowSpan || 1}`;
                card.dataset.size = cardLayout.size || '1x1';
            }
        });
    } catch (e) {
        console.error('Failed to load layout:', e);
    }
}

// 保存布局
function saveLayout() {
    const dashboard = document.getElementById('dashboard');
    if (!dashboard) return;
    
    const layout = {};
    const cards = dashboard.querySelectorAll('.bento-card');
    cards.forEach(card => {
        const cardId = card.dataset.id;
        const size = card.dataset.size || '1x1';
        const [colSpan, rowSpan] = size.split('x').map(Number);
        
        layout[cardId] = {
            size,
            colSpan,
            rowSpan
        };
    });
    
    localStorage.setItem('blossom-layout', JSON.stringify(layout));
}