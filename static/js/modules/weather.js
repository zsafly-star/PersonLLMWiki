/**
 * 天气模块
 */

function loadQWeather() {
    fetch('/api/weather/daily')
        .then(function(r) { return r.json(); })
        .then(function(result) {
            if (result.code === 200 && result.data) {
                renderQWeather(result.data);
            } else {
                clearWeatherUI();
            }
        })
        .catch(function() {
            clearWeatherUI();
        });
}

function renderQWeather(data) {
    var cityEl = document.getElementById('current-city');
    var conditionEl = document.getElementById('weather-condition');
    if (cityEl) cityEl.textContent = data.city || '';
    if (conditionEl && data.forecast && data.forecast.length > 0) {
        conditionEl.textContent = data.forecast[0].text_day || '';
    }

    var cards = document.querySelectorAll('.forecast-card');
    var forecast = data.forecast || [];
    cards.forEach(function(card, index) {
        if (index >= forecast.length) return;
        var day = forecast[index];

        var iconEl = card.querySelector('.forecast-icon');
        if (iconEl) {
            iconEl.src = day.icon_path || '/static/icons/weather/weather_晴.svg';
            iconEl.style.display = 'block';
        }

        var highEl = card.querySelector('.temp-high');
        var lowEl = card.querySelector('.temp-low');
        var descEl = card.querySelector('.forecast-desc');
        var dayLabelEl = card.querySelector('.forecast-day');

        if (highEl) highEl.textContent = day.temp_max || '--';
        if (lowEl) lowEl.textContent = day.temp_min || '--';
        if (descEl) descEl.textContent = day.text_day || '';
        if (dayLabelEl) dayLabelEl.textContent = day.day_label || '';
    });
}

function clearWeatherUI() {
    var forecastContainer = document.getElementById('weather-forecast');
    if (!forecastContainer) return;

    var cards = forecastContainer.querySelectorAll('.forecast-card');
    cards.forEach(function(card) {
        var iconEl = card.querySelector('.forecast-icon');
        var highEl = card.querySelector('.temp-high');
        var lowEl = card.querySelector('.temp-low');
        var descEl = card.querySelector('.forecast-desc');
        if (iconEl) {
            iconEl.src = '';
            iconEl.style.display = 'none';
        }
        if (highEl) highEl.textContent = '--';
        if (lowEl) lowEl.textContent = '--';
        if (descEl) descEl.textContent = '';
    });

    var tempValue = document.querySelector('#main-temp-value');
    var conditionEl = document.querySelector('.forecast-city-bar .weather-condition');
    if (tempValue) tempValue.textContent = '--';
    if (conditionEl) conditionEl.textContent = '';
}

function initCitySelector() {
    var refreshBtn = document.getElementById('weather-refresh');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            var svg = refreshBtn.querySelector('svg');
            if (svg) {
                svg.style.animation = 'emoji-spin 0.6s linear';
                setTimeout(function() { svg.style.animation = ''; }, 600);
            }
            loadQWeather();
        });
    }
}

function selectCityFromSettings(city) {
    const cityInput = document.getElementById('city-input');
    if (cityInput) {
        cityInput.value = city;
    }
    
    const currentCityValue = document.getElementById('current-city-value');
    if (currentCityValue) {
        currentCityValue.textContent = city;
    }
    
    const cityEl = document.getElementById('current-city');
    if (cityEl) {
        cityEl.textContent = city;
    }
    localStorage.setItem('blossom-city', city);
    loadQWeather();
    
    const cityOptions = document.getElementById('city-options');
    if (cityOptions) {
        cityOptions.classList.remove('show');
    }
}