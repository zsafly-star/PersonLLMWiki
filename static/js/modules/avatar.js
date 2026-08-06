/**
 * 头像模块
 */

// 头像选项
const avatarOptions = [
    'fa-user-circle', 'fa-user', 'fa-user-alt', 'fa-user-check',
    'fa-smile', 'fa-smile-beam', 'fa-grin', 'fa-grin-beam',
    'fa-heart', 'fa-star', 'fa-sun', 'fa-moon',
    'fa-cloud', 'fa-brain', 'fa-cat', 'fa-dog',
    'fa-paw', 'fa-coffee', 'fa-music', 'fa-book',
    'fa-laptop', 'fa-phone', 'fa-camera', 'fa-gift',
    'fa-flower2', 'fa-leaf', 'fa-tree', 'fa-mountain',
    'fa-anchor', 'fa-ship', 'fa-plane', 'fa-car'
];

function loadAvatar() {
    const savedAvatar = localStorage.getItem('blossom-avatar') || 'user';
    const avatarIcon = document.getElementById('avatar-icon');
    if (avatarIcon) {
        avatarIcon.className = `fas ${savedAvatar || 'fa-user-circle'} avatar-icon`;
    }

    const sidebarAvatar = document.getElementById('sidebar-avatar');
    if (sidebarAvatar && typeof window.AVATAR_SVGS !== 'undefined') {
        var key = savedAvatar;
        if (key.indexOf('fa-') === 0) { key = key.substring(3); }
        sidebarAvatar.innerHTML = window.AVATAR_SVGS[key] || window.AVATAR_SVGS['user'];
    }

    // 从服务端加载（覆盖 localStorage，确保桌面模式重启后数据不丢失）
    fetch('/api/settings/profile').then(function(r) { return r.json(); }).then(function(d) {
        if (d && d.data) {
            var p = d.data;
            if (p.avatar) {
                localStorage.setItem('blossom-avatar', p.avatar);
                if (avatarIcon) {
                    avatarIcon.className = 'fas ' + p.avatar + ' avatar-icon';
                }
                if (sidebarAvatar && typeof window.AVATAR_SVGS !== 'undefined') {
                    var k = p.avatar;
                    if (k.indexOf('fa-') === 0) { k = k.substring(3); }
                    sidebarAvatar.innerHTML = window.AVATAR_SVGS[k] || window.AVATAR_SVGS['user'];
                }
            }
            if (p.username) {
                localStorage.setItem('blossom-username', p.username);
                var usernameEl = document.getElementById('user-name');
                if (usernameEl) { usernameEl.textContent = p.username; }
            }
        }
    }).catch(function() {});
}

function loadUsername() {
    const savedUsername = localStorage.getItem('blossom-username');
    const usernameEl = document.getElementById('user-name');
    if (usernameEl) {
        usernameEl.textContent = savedUsername || '用户';
    }
}

function changeAvatar() {
    const modal = document.getElementById('modal-avatar');
    if (!modal) {
        createAvatarModal();
    } else {
        modal.classList.add('show');
    }
}

function createAvatarModal() {
    const modal = document.createElement('div');
    modal.id = 'modal-avatar';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content avatar-modal">
            <div class="modal-header">
                <h3>选择头像图标</h3>
                <button class="btn-close" onclick="closeAvatarModal()" title="关闭">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
                </button>
            </div>
            <div class="modal-body avatar-grid">
                ${avatarOptions.map(icon => `
                    <div class="avatar-option" onclick="selectAvatar('${icon}')">
                        <i class="fas ${icon}"></i>
                    </div>
                `).join('')}
            </div>
            <div class="modal-footer">
                <button class="btn btn-primary" onclick="closeAvatarModal()">确定</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    modal.classList.add('show');
}

function selectAvatar(iconName) {
    const avatarIcon = document.getElementById('avatar-icon');
    if (avatarIcon) {
        avatarIcon.className = `fas ${iconName} avatar-icon`;
    }
    localStorage.setItem('blossom-avatar', iconName);
    fetch('/api/settings/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ avatar: iconName })
    }).catch(function() {});
    closeAvatarModal();
}

function closeAvatarModal() {
    const modal = document.getElementById('modal-avatar');
    if (modal) {
        modal.classList.remove('show');
    }
}