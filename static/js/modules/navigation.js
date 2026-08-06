/**
 * 导航模块
 */

function initNavigation() {
    // 侧边栏导航点击事件
    const sidebarItems = document.querySelectorAll('.sidebar-item');
    sidebarItems.forEach(item => {
        item.addEventListener('click', function(e) {
            const targetView = this.dataset.view;
            if (targetView) {
                switchView(targetView);
            }
        });
    });

    // 移动端菜单切换
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    if (mobileMenuBtn && sidebar) {
        mobileMenuBtn.addEventListener('click', function() {
            sidebar.classList.toggle('mobile-open');
        });
    }

    // 点击外部关闭移动端菜单
    document.addEventListener('click', function(e) {
        if (!sidebar?.contains(e.target) && !mobileMenuBtn?.contains(e.target)) {
            sidebar?.classList.remove('mobile-open');
        }
    });
}

function switchView(viewName) {
    // 更新侧边栏激活状态
    const sidebarItems = document.querySelectorAll('.sidebar-item');
    sidebarItems.forEach(item => {
        item.classList.remove('active');
        if (item.dataset.view === viewName) {
            item.classList.add('active');
        }
    });

    // 更新视图显示
    const views = document.querySelectorAll('.main-view');
    views.forEach(view => {
        view.style.display = view.id === `${viewName}-view` ? 'block' : 'none';
    });

    // 触发视图切换事件
    document.dispatchEvent(new CustomEvent('viewChange', { detail: { view: viewName } }));

    // 更新URL hash
    window.history.pushState({ view: viewName }, '', `#${viewName}`);
}

// 监听URL hash变化
function initHashListener() {
    window.addEventListener('popstate', function(e) {
        if (e.state?.view) {
            switchView(e.state.view);
        }
    });

    // 初始化时根据hash切换视图
    const hash = window.location.hash.slice(1);
    if (hash && ['dashboard', 'note', 'chat', 'picture', 'settings'].includes(hash)) {
        switchView(hash);
    }
}

// 关闭所有菜单
function _closeAllMenus() {
    document.querySelectorAll('.sidebar-dropdown, .tree-item-dropdown').forEach(el => el.classList.remove('show'));
}

function _closeAllToolbarMenus() {
    document.querySelectorAll('.toolbar-dropdown').forEach(d => d.style.display = 'none');
}

function toggleSidebarMenu(event) {
    event.stopPropagation();
    const dd = document.getElementById('sidebar-dropdown');
    if (!dd) return;
    const isOpen = dd.classList.contains('show');
    _closeAllMenus();
    if (!isOpen) dd.classList.add('show');
}

function toggleToolbarMenu(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('toolbar-dropdown');
    if (!dropdown) return;
    const isOpen = dropdown.style.display === 'block';
    _closeAllToolbarMenus();
    if (!isOpen) dropdown.style.display = 'block';
}