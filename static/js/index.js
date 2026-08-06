/**
 * JavaScript模块化入口文件
 * 按顺序引入所有模块
 */

// 工具函数模块
document.write('<script src="/static/js/modules/utils.js"></script>');

// 核心功能模块
document.write('<script src="/static/js/modules/navigation.js"></script>');
document.write('<script src="/static/js/modules/avatar.js"></script>');
document.write('<script src="/static/js/modules/weather.js"></script>');
document.write('<script src="/static/js/modules/charts.js"></script>');
document.write('<script src="/static/js/modules/dashboard.js"></script>');
document.write('<script src="/static/js/modules/article.js"></script>');
document.write('<script src="/static/js/modules/editor.js"></script>');
document.write('<script src="/static/js/modules/picture.js"></script>');
document.write('<script src="/static/js/modules/settings.js"></script>');
document.write('<script src="/static/js/modules/attachment.js"></script>');

// 页面初始化
document.addEventListener('DOMContentLoaded', function() {
    initNavigation();
    initHashListener();
    initCharts();
    loadAvatar();
    loadUsername();
    loadQWeather();
    initCitySelector();
    initEditor();
    initSettingsPage();
    bindGlobalEvents();
});
