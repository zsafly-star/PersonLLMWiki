/**
 * 工具函数模块
 */

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// 格式化日期
function formatDate(timestamp) {
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString('zh-CN');
}

// 防抖工具函数
function debounce(fn, delay) {
    let timer;
    return function() {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, arguments), delay);
    };
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 全局变量定义
let imagePath = '';

// 获取图片路径
function getImagePath() {
    return imagePath || '/images';
}

// 设置图片路径
function setImagePath(path) {
    imagePath = path;
}

// 绑定全局事件
function bindGlobalEvents() {
    // 图片上传处理
    const fileUploadInput = document.getElementById('file-upload-input');
    if (fileUploadInput) {
        fileUploadInput.addEventListener('change', function(e) {
            handleImageUpload(e.target.files);
        });
    }
    
    // 主题切换事件监听
    document.addEventListener('themeChange', function(e) {
        applyTheme(e.detail.theme);
    });
}

// 更新时间显示
function updateTime() {
    const now = new Date();
    const hours = now.getHours().toString().padStart(2, '0');
    const minutes = now.getMinutes().toString().padStart(2, '0');
    const seconds = now.getSeconds().toString().padStart(2, '0');
    
    // 更新时间
    const timeEl = document.getElementById('current-time');
    if (timeEl) {
        timeEl.textContent = `${hours}:${minutes}:${seconds}`;
    }
    
    // 更新日期
    const options = { month: 'long', day: 'numeric' };
    const dateStr = now.toLocaleDateString('zh-CN', options);
    const dateEl = document.getElementById('current-date');
    if (dateEl) {
        dateEl.textContent = dateStr;
    }
    
    // 更新星期
    const weekdays = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六'];
    const weekdayEl = document.getElementById('current-weekday');
    if (weekdayEl) {
        weekdayEl.textContent = weekdays[now.getDay()];
    }
    
    // 更新问候语
    const greetingEl = document.getElementById('greeting');
    if (greetingEl) {
        let greeting = '早上好';
        if (hours >= 12 && hours < 18) {
            greeting = '下午好';
        } else if (hours >= 18 || hours < 6) {
            greeting = '晚上好';
        }
        greetingEl.textContent = greeting;
    }
}