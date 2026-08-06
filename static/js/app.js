/**
 * 主应用入口文件
 * 模块化重构 - 引入各功能模块
 */

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

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 初始化各个模块
    initNavigation();
    initHashListener();
    initCharts();
    loadAvatar();
    loadUsername();
    loadQWeather();
    initCitySelector();
    
    // 尝试初始化编辑器（如果在编辑页面）
    initEditor();
    
    // 尝试初始化聊天（如果在聊天页面）
    initChat();
    
    // 尝试初始化设置页面（如果在设置页面）
    initSettingsPage();
    
    // 绑定全局事件
    bindGlobalEvents();
});

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