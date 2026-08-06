/**
 * 图表模块
 */

function initCharts() {
    // 初始化文档统计图表
    initDocStatsChart();
    
    // 初始化标签云
    initTagCloud();
    
    // 初始化活跃度图表
    initActivityChart();
}

function initDocStatsChart() {
    const chartCanvas = document.getElementById('doc-stats-chart');
    if (!chartCanvas) return;

    const ctx = chartCanvas.getContext('2d');
    
    // 模拟数据 - 实际应该从API获取
    const data = {
        labels: ['一月', '二月', '三月', '四月', '五月', '六月'],
        datasets: [{
            label: '文档数',
            data: [12, 19, 8, 15, 22, 30],
            borderColor: '#0D9488',
            backgroundColor: 'rgba(13, 148, 136, 0.1)',
            fill: true,
            tension: 0.4
        }]
    };

    const options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: false
            }
        },
        scales: {
            y: {
                beginAtZero: true,
                grid: {
                    color: 'rgba(0, 0, 0, 0.05)'
                }
            },
            x: {
                grid: {
                    display: false
                }
            }
        }
    };

    // 检查是否已存在图表实例
    if (chartCanvas.chartInstance) {
        chartCanvas.chartInstance.destroy();
    }

    // 创建简单的折线图（无外部依赖版本）
    drawSimpleLineChart(ctx, data, options, chartCanvas.width, chartCanvas.height);
}

function drawSimpleLineChart(ctx, data, options, width, height) {
    const padding = { top: 20, right: 20, bottom: 40, left: 50 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    ctx.clearRect(0, 0, width, height);

    const maxValue = Math.max(...data.datasets[0].data);
    const minValue = 0;
    const valueRange = maxValue - minValue;

    // 绘制网格线
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.05)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
        const y = padding.top + (chartHeight / 5) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(width - padding.right, y);
        ctx.stroke();
    }

    // 绘制坐标轴
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, height - padding.bottom);
    ctx.lineTo(width - padding.right, height - padding.bottom);
    ctx.stroke();

    // 绘制数据点和连线
    const points = [];
    data.labels.forEach((label, index) => {
        const x = padding.left + (chartWidth / (data.labels.length - 1)) * index;
        const value = data.datasets[0].data[index];
        const y = padding.top + chartHeight - ((value - minValue) / valueRange) * chartHeight;
        points.push({ x, y });

        // 绘制标签
        ctx.fillStyle = '#909399';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, height - 10);
    });

    // 绘制区域填充
    ctx.fillStyle = 'rgba(13, 148, 136, 0.1)';
    ctx.beginPath();
    ctx.moveTo(points[0].x, height - padding.bottom);
    points.forEach(point => ctx.lineTo(point.x, point.y));
    ctx.lineTo(points[points.length - 1].x, height - padding.bottom);
    ctx.closePath();
    ctx.fill();

    // 绘制折线
    ctx.strokeStyle = '#0D9488';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    points.forEach(point => ctx.lineTo(point.x, point.y));
    ctx.stroke();

    // 绘制数据点
    points.forEach(point => {
        ctx.fillStyle = '#0D9488';
        ctx.beginPath();
        ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.beginPath();
        ctx.arc(point.x, point.y, 2, 0, Math.PI * 2);
        ctx.fill();
    });
}

function initTagCloud() {
    const tagContainer = document.getElementById('tag-cloud');
    if (!tagContainer) return;

    fetch('/api/article/tags')
        .then(r => r.json())
        .then(result => {
            if (result.code === 200 && result.data) {
                renderTagCloud(result.data);
            }
        })
        .catch(() => {
            tagContainer.innerHTML = '<p class="empty-hint">暂无标签</p>';
        });
}

function renderTagCloud(tags) {
    const tagContainer = document.getElementById('tag-cloud');
    if (!tagContainer || !tags.length) {
        tagContainer.innerHTML = '<p class="empty-hint">暂无标签</p>';
        return;
    }

    const maxCount = Math.max(...tags.map(t => t.count));
    const minCount = Math.min(...tags.map(t => t.count));
    const countRange = maxCount - minCount || 1;

    const colors = ['#0D9488', '#3B82F6', '#8B5CF6', '#EC4899', '#F59E0B'];

    let html = '';
    tags.forEach(tag => {
        const weight = (tag.count - minCount) / countRange;
        const fontSize = 12 + weight * 10;
        const colorIndex = Math.floor(weight * colors.length) % colors.length;
        
        html += `<span class="tag-item" style="font-size: ${fontSize}px; color: ${colors[colorIndex]}" onclick="filterByTag('${tag.name}')">
            ${tag.name} (${tag.count})
        </span>`;
    });

    tagContainer.innerHTML = html;
}

function filterByTag(tagName) {
    // 触发标签筛选事件
    document.dispatchEvent(new CustomEvent('tagFilter', { detail: { tag: tagName } }));
}

function initActivityChart() {
    const container = document.getElementById('activity-container');
    if (!container) return;

    // 获取最近7天的数据
    const days = [];
    const today = new Date();
    for (let i = 6; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);
        days.push({
            date: date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
            count: Math.floor(Math.random() * 10) // 模拟数据
        });
    }

    let html = '<div class="activity-chart">';
    const maxCount = Math.max(...days.map(d => d.count));
    
    days.forEach(day => {
        const height = maxCount > 0 ? (day.count / maxCount) * 100 : 0;
        html += `
            <div class="activity-bar-wrapper">
                <div class="activity-bar" style="height: ${height}%"></div>
                <span class="activity-label">${day.date}</span>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
}