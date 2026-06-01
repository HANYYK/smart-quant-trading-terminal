/**
 * 图表模块
 * 基于 ECharts 的 K 线图、均线图、MACD、KDJ 等技术指标图表
 */

const ChartModule = {
    echartsLoaded: false,

    /**
     * 加载 ECharts 库
     * @returns {Promise}
     */
    loadECharts: function() {
        if (this.echartsLoaded) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js';
            script.onload = () => {
                this.echartsLoaded = true;
                resolve();
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
    },

    /**
     * 获取默认的图表主题配色
     */
    getTheme: function() {
        return {
            upColor: '#00ff88',
            downColor: '#ff4444',
            flatColor: '#888888',
            bgColor: '#1a1a2e',
            textColor: '#e0e0e0',
            gridColor: '#2d2d44'
        };
    },

    /**
     * 创建基础折线图配置
     * @param {Object} options - 配置选项
     * @returns {Object} ECharts 配置
     */
    createLineChart: function(options = {}) {
        const theme = this.getTheme();
        return {
            backgroundColor: theme.bgColor,
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
                backgroundColor: 'rgba(30, 30, 50, 0.9)',
                borderColor: theme.gridColor,
                textStyle: { color: theme.textColor }
            },
            legend: { show: false },
            grid: { left: '10%', right: '5%', top: '10%', bottom: '15%' },
            xAxis: {
                type: 'category',
                data: options.xData || [],
                axisLine: { lineStyle: { color: theme.gridColor } },
                axisLabel: { color: theme.textColor, fontSize: 10 }
            },
            yAxis: {
                type: 'value',
                scale: true,
                splitLine: { lineStyle: { color: theme.gridColor, type: 'dashed' } },
                axisLabel: { color: theme.textColor }
            },
            series: options.series || []
        };
    },

    /**
     * 创建 K 线图配置
     * @param {Object} klineData - K线数据 [{date, open, high, low, close, volume}]
     * @param {Object} options - 额外配置
     * @returns {Object} ECharts 配置
     */
    createKlineChart: function(klineData, options = {}) {
        const theme = this.getTheme();
        const dates = klineData.map(d => d.date);
        const ohlc = klineData.map(d => [d.open, d.close, d.low, d.high]);
        const volumes = klineData.map(d => ({
            value: d.volume,
            itemStyle: { color: d.close >= d.open ? theme.upColor : theme.downColor }
        }));

        return {
            backgroundColor: theme.bgColor,
            animation: false,
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
                backgroundColor: 'rgba(30, 30, 50, 0.9)',
                borderColor: theme.gridColor,
                formatter: function(params) {
                    const data = params.find(p => p.seriesName === 'K线');
                    if (!data) return '';
                    const [o, c, l, h] = data.value;
                    const color = c >= o ? theme.upColor : theme.downColor;
                    return `<strong>${data.axisValue}</strong><br/>
                        开盘: <span style="color:${theme.textColor}">${o.toFixed(2)}</span><br/>
                        最高: <span style="color:${theme.upColor}">${h.toFixed(2)}</span><br/>
                        最低: <span style="color:${theme.downColor}">${l.toFixed(2)}</span><br/>
                        收盘: <span style="color:${color}">${c.toFixed(2)}</span>`;
                }
            },
            axisPointer: { link: [{ xAxisIndex: 'all' }] },
            grid: [
                { left: '10%', right: '5%', top: '5%', height: '60%' },
                { left: '10%', right: '5%', top: '70%', height: '20%' }
            ],
            xAxis: [
                {
                    type: 'category',
                    data: dates,
                    gridIndex: 0,
                    axisLine: { lineStyle: { color: theme.gridColor } },
                    axisLabel: { show: false }
                },
                {
                    type: 'category',
                    data: dates,
                    gridIndex: 1,
                    axisLine: { lineStyle: { color: theme.gridColor } },
                    axisLabel: { color: theme.textColor, fontSize: 10 }
                }
            ],
            yAxis: [
                {
                    scale: true,
                    gridIndex: 0,
                    splitLine: { lineStyle: { color: theme.gridColor, type: 'dashed' } },
                    axisLabel: { color: theme.textColor }
                },
                {
                    scale: true,
                    gridIndex: 1,
                    splitLine: { lineStyle: { color: theme.gridColor, type: 'dashed' } },
                    axisLabel: { color: theme.textColor }
                }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: ohlc,
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    itemStyle: {
                        color: theme.upColor,
                        color0: theme.downColor,
                        borderColor: theme.upColor,
                        borderColor0: theme.downColor
                    }
                },
                {
                    name: '成交量',
                    type: 'bar',
                    data: volumes,
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    barWidth: '60%'
                }
            ].concat(options.extraSeries || [])
        };
    },

    /**
     * 创建 MACD 图表配置
     * @param {Array} macdData - [{date, dif, dea, macd}]
     * @returns {Object} ECharts 配置
     */
    createMACDChart: function(macdData) {
        const theme = this.getTheme();
        const dates = macdData.map(d => d.date);
        const macdValues = macdData.map(d => d.macd);
        const difValues = macdData.map(d => d.dif);
        const deaValues = macdData.map(d => d.dea);

        return {
            backgroundColor: theme.bgColor,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(30, 30, 50, 0.9)',
                borderColor: theme.gridColor,
                textStyle: { color: theme.textColor }
            },
            legend: {
                data: ['DIF', 'DEA', 'MACD'],
                top: 5,
                textStyle: { color: theme.textColor }
            },
            grid: { left: '10%', right: '5%', top: '15%', bottom: '10%' },
            xAxis: {
                type: 'category',
                data: dates,
                axisLine: { lineStyle: { color: theme.gridColor } },
                axisLabel: { color: theme.textColor, fontSize: 10 }
            },
            yAxis: {
                scale: true,
                splitLine: { lineStyle: { color: theme.gridColor, type: 'dashed' } },
                axisLabel: { color: theme.textColor }
            },
            series: [
                {
                    name: 'DIF',
                    type: 'line',
                    data: difValues,
                    smooth: true,
                    lineStyle: { color: '#2196F3', width: 1 }
                },
                {
                    name: 'DEA',
                    type: 'line',
                    data: deaValues,
                    smooth: true,
                    lineStyle: { color: '#FF9800', width: 1 }
                },
                {
                    name: 'MACD',
                    type: 'bar',
                    data: macdValues.map(v => ({
                        value: v,
                        itemStyle: { color: v >= 0 ? theme.upColor : theme.downColor }
                    })),
                    barWidth: '50%'
                }
            ]
        };
    },

    /**
     * 创建 KDJ 图表配置
     * @param {Array} kdjData - [{date, k, d, j}]
     * @returns {Object} ECharts 配置
     */
    createKDJChart: function(kdjData) {
        const theme = this.getTheme();
        const dates = kdjData.map(d => d.date);

        return {
            backgroundColor: theme.bgColor,
            tooltip: {
                trigger: 'axis',
                backgroundColor: 'rgba(30, 30, 50, 0.9)',
                borderColor: theme.gridColor,
                textStyle: { color: theme.textColor }
            },
            legend: {
                data: ['K', 'D', 'J'],
                top: 5,
                textStyle: { color: theme.textColor }
            },
            grid: { left: '10%', right: '5%', top: '15%', bottom: '10%' },
            xAxis: {
                type: 'category',
                data: dates,
                axisLine: { lineStyle: { color: theme.gridColor } },
                axisLabel: { color: theme.textColor, fontSize: 10 }
            },
            yAxis: {
                type: 'value',
                min: 0,
                max: 100,
                splitLine: { lineStyle: { color: theme.gridColor, type: 'dashed' } },
                axisLabel: { color: theme.textColor }
            },
            series: [
                {
                    name: 'K',
                    type: 'line',
                    data: kdjData.map(d => d.k),
                    smooth: true,
                    lineStyle: { color: '#2196F3', width: 1 }
                },
                {
                    name: 'D',
                    type: 'line',
                    data: kdjData.map(d => d.d),
                    smooth: true,
                    lineStyle: { color: '#FF9800', width: 1 }
                },
                {
                    name: 'J',
                    type: 'line',
                    data: kdjData.map(d => d.j),
                    smooth: true,
                    lineStyle: { color: '#9C27B0', width: 1 }
                }
            ]
        };
    },

    /**
     * 渲染图表到容器
     * @param {string} containerId - 容器 ID
     * @param {Object} options - ECharts 配置
     * @returns {Object} ECharts 实例
     */
    render: function(containerId, options) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`Container ${containerId} not found`);
            return null;
        }
        const chart = echarts.init(container);
        chart.setOption(options);
        return chart;
    },

    /**
     * 响应式调整图表大小
     * @param {Object} chart - ECharts 实例
     */
    resize: function(chart) {
        if (chart) chart.resize();
    }
};
