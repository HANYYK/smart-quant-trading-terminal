/**
 * 前端工具函数模块
 * 提供格式化和通用功能，供所有模板复用
 */

const AppUtils = {
    /**
     * 获取 CSRF token
     */
    csrfToken: function() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.content;
        const input = document.querySelector('#csrf-form input');
        if (input) return input.value;
        return '';
    },

    /**
     * 格式化金额
     * @param {number} num - 金额
     * @param {number} decimals - 小数位数
     * @returns {string} 格式化后的金额字符串
     */
    formatMoney: function(num, decimals = 2) {
        if (!num && num !== 0) return '0.00';
        return parseFloat(num).toLocaleString('zh-CN', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    },

    /**
     * 格式化成交量
     * @param {number} vol - 成交量
     * @returns {string} 格式化后的成交量字符串
     */
    formatVolume: function(vol) {
        if (!vol && vol !== 0) return '0';
        vol = parseFloat(vol);
        if (vol >= 1e8) return (vol / 1e8).toFixed(2) + '亿';
        if (vol >= 1e4) return (vol / 1e4).toFixed(2) + '万';
        return vol.toFixed(0);
    },

    /**
     * 格式化涨跌幅
     * @param {number} val - 数值
     * @param {number} decimals - 小数位数
     * @returns {string} 带正负号和百分号的字符串
     */
    formatPercent: function(val, decimals = 2) {
        if (!val && val !== 0) return '0.00%';
        const prefix = parseFloat(val) >= 0 ? '+' : '';
        return prefix + parseFloat(val).toFixed(decimals) + '%';
    },

    /**
     * 格式化涨跌额
     * @param {number} val - 涨跌额
     * @param {number} decimals - 小数位数
     * @returns {string} 带正负号的字符串
     */
    formatChange: function(val, decimals = 2) {
        if (!val && val !== 0) return '0.00';
        const prefix = parseFloat(val) >= 0 ? '+' : '';
        return prefix + parseFloat(val).toFixed(decimals);
    },

    /**
     * 获取涨跌颜色类名
     * @param {number} val - 涨跌幅
     * @returns {string} 颜色类名
     */
    getChangeClass: function(val) {
        if (!val && val !== 0) return 'color-flat';
        return parseFloat(val) > 0 ? 'color-up' : parseFloat(val) < 0 ? 'color-down' : 'color-flat';
    },

    /**
     * 显示 Toast 通知
     * @param {string} message - 消息内容
     * @param {string} type - 类型: success, error, warning, info
     * @param {number} duration - 显示时长（毫秒）
     */
    showToast: function(message, type = 'info', duration = 3000) {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:10px;';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = `custom-toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => toast.classList.add('show'), 10);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    /**
     * 防抖函数
     * @param {Function} func - 要防抖的函数
     * @param {number} wait - 等待时间（毫秒）
     * @returns {Function} 防抖后的函数
     */
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * 节流函数
     * @param {Function} func - 要节流的函数
     * @param {number} limit - 时间限制（毫秒）
     * @returns {Function} 节流后的函数
     */
    throttle: function(func, limit) {
        let inThrottle;
        return function executedFunction(...args) {
            if (!inThrottle) {
                func(...args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    /**
     * Ajax GET 请求
     * @param {string} url - 请求地址
     * @param {Object} params - 查询参数
     * @returns {Promise} Promise 对象
     */
    ajaxGet: function(url, params = {}) {
        const query = new URLSearchParams(params).toString();
        const fullUrl = query ? `${url}?${query}` : url;
        return fetch(fullUrl, {
            headers: { 'Accept': 'application/json' }
        }).then(res => res.json());
    },

    /**
     * Ajax POST 请求（带 CSRF）
     * @param {string} url - 请求地址
     * @param {Object} data - 请求数据
     * @returns {Promise} Promise 对象
     */
    ajaxPost: function(url, data = {}) {
        const formData = new FormData();
        formData.append('csrf_token', this.csrfToken());
        for (const [key, value] of Object.entries(data)) {
            formData.append(key, value);
        }
        return fetch(url, {
            method: 'POST',
            body: formData
        }).then(res => res.json());
    }
};
