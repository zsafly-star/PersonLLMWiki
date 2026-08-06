/**
 * 设置模块 — 公共逻辑（主题加载、菜单切换）
 */

function initSettingsPage() {
    loadThemeSettings();
    bindSettingsEvents();
}

function loadThemeSettings() {
    const savedTheme = localStorage.getItem('blossom-theme') || 'green';

    const themeCards = document.querySelectorAll('.theme-card');
    themeCards.forEach(card => {
        card.classList.toggle('active', card.dataset.theme === savedTheme);
        card.setAttribute('aria-pressed', card.dataset.theme === savedTheme ? 'true' : 'false');
    });

    applyTheme(savedTheme);
}

function bindSettingsEvents() {
    // 设置菜单切换 (support both click and keyboard)
    const menuItems = document.querySelectorAll('.settings-menu-item');
    menuItems.forEach(item => {
        item.addEventListener('click', function() {
            const settingName = this.dataset.setting;
            switchSettingsTab(settingName);
        });
    });

    // 主题卡片切换
    const themeCards = document.querySelectorAll('.theme-card');
    themeCards.forEach(card => {
        card.addEventListener('click', function() {
            const theme = this.dataset.theme;
            applyTheme(theme);
            localStorage.setItem('blossom-theme', theme);

            themeCards.forEach(c => {
                c.classList.remove('active');
                c.setAttribute('aria-pressed', 'false');
            });
            this.classList.add('active');
            this.setAttribute('aria-pressed', 'true');
        });
    });
}

function applyTheme(theme) {
    const root = document.documentElement;
    root.classList.remove('theme-green', 'theme-pink', 'theme-dark-teal', 'theme-dark-pink', 'theme-blueprint');
    root.classList.add('theme-' + theme);
}

function switchSettingsTab(tabName) {
    // 更新菜单选中状态
    const menuItems = document.querySelectorAll('.settings-menu-item');
    menuItems.forEach(item => {
        const isActive = item.dataset.setting === tabName;
        item.classList.toggle('active', isActive);
        item.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    // 切换内容显示
    const sections = document.querySelectorAll('.setting-content-section');
    sections.forEach(section => {
        section.style.display = 'none';
    });

    const targetSection = document.getElementById('setting-' + tabName);
    if (targetSection) {
        targetSection.style.display = 'block';
    }
}
