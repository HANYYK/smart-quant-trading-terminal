/**
 * 表格模块
 * 基于 DataTables 的统一配置和数据表格功能扩展
 */

const TableModule = {
    /**
     * 默认配置
     */
    defaultConfig: {
        language: {
            lengthMenu: '每页 _MENU_ 条',
            zeroRecords: '没有找到匹配的记录',
            info: '第 _START_ 到 _END_ 条，共 _TOTAL_ 条',
            infoEmpty: '无记录',
            infoFiltered: '(从 _MAX_ 条记录中过滤)',
            search: '搜索:',
            paginate: {
                first: '首页',
                last: '末页',
                next: '下一页',
                previous: '上一页'
            }
        },
        pageLength: 20,
        lengthMenu: [[10, 20, 50, 100], [10, 20, 50, 100]],
        order: [],
        dom: '<"row"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>' +
             '<"row"<"col-sm-12"tr>>' +
             '<"row"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        responsive: true,
        autoWidth: false,
        processing: true,
        serverSide: false
    },

    /**
     * 创建表格实例
     * @param {string} tableId - 表格 ID
     * @param {Object} options - 配置选项
     * @returns {Object} DataTables 实例
     */
    create: function(tableId, options = {}) {
        const table = document.getElementById(tableId);
        if (!table) {
            console.error(`Table ${tableId} not found`);
            return null;
        }

        const config = { ...this.defaultConfig, ...options };
        return $(`#${tableId}`).DataTable(config);
    },

    /**
     * 创建股票行情表格
     * @param {string} tableId - 表格 ID
     * @param {Function} onRowClick - 行点击回调
     * @returns {Object} DataTables 实例
     */
    createStockTable: function(tableId, onRowClick) {
        const theme = {
            upColor: '#00ff88',
            downColor: '#ff4444',
            flatColor: '#888888'
        };

        return this.create(tableId, {
            columns: [
                { title: '代码', data: 'code', width: '100px' },
                { title: '名称', data: 'name', width: '120px' },
                { title: '最新价', data: 'price', width: '100px', render: d => d ? d.toFixed(2) : '-' },
                {
                    title: '涨跌幅',
                    data: 'change_pct',
                    width: '100px',
                    render: d => {
                        if (!d && d !== 0) return '-';
                        const cls = d > 0 ? 'color-up' : d < 0 ? 'color-down' : 'color-flat';
                        const prefix = d > 0 ? '+' : '';
                        return `<span class="${cls}">${prefix}${d.toFixed(2)}%</span>`;
                    }
                },
                {
                    title: '涨跌额',
                    data: 'change',
                    width: '100px',
                    render: d => {
                        if (!d && d !== 0) return '-';
                        const cls = d > 0 ? 'color-up' : d < 0 ? 'color-down' : 'color-flat';
                        const prefix = d > 0 ? '+' : '';
                        return `<span class="${cls}">${prefix}${d.toFixed(2)}</span>`;
                    }
                },
                { title: '成交量', data: 'volume', width: '120px', render: d => d ? AppUtils.formatVolume(d) : '-' },
                { title: '成交额', data: 'amount', width: '120px', render: d => d ? AppUtils.formatVolume(d) + '元' : '-' },
                { title: '换手率', data: 'turnover', width: '80px', render: d => d ? d.toFixed(2) + '%' : '-' },
                { title: '市盈率', data: 'pe', width: '80px', render: d => d ? d.toFixed(2) : '-' },
                { title: '市净率', data: 'pb', width: '80px', render: d => d ? d.toFixed(2) : '-' }
            ],
            createdRow: function(row, data) {
                if (onRowClick) {
                    $(row).css('cursor', 'pointer').on('click', () => onRowClick(data));
                }
            }
        });
    },

    /**
     * 创建基金排行表格
     * @param {string} tableId - 表格 ID
     * @param {Function} onRowClick - 行点击回调
     * @returns {Object} DataTables 实例
     */
    createFundTable: function(tableId, onRowClick) {
        return this.create(tableId, {
            columns: [
                { title: '基金代码', data: 'code', width: '100px' },
                { title: '基金名称', data: 'name', width: '200px' },
                { title: '单位净值', data: 'nav', width: '100px', render: d => d ? d.toFixed(4) : '-' },
                { title: '累计净值', data: 'acc_nav', width: '100px', render: d => d ? d.toFixed(4) : '-' },
                {
                    title: '日涨幅',
                    data: 'daily_return',
                    width: '100px',
                    render: d => {
                        if (!d && d !== 0) return '-';
                        const cls = d > 0 ? 'color-up' : d < 0 ? 'color-down' : 'color-flat';
                        const prefix = d > 0 ? '+' : '';
                        return `<span class="${cls}">${prefix}${d.toFixed(2)}%</span>`;
                    }
                },
                { title: '近1月', data: 'm1_return', width: '80px', render: d => d ? d.toFixed(2) + '%' : '-' },
                { title: '近3月', data: 'm3_return', width: '80px', render: d => d ? d.toFixed(2) + '%' : '-' },
                { title: '近6月', data: 'm6_return', width: '80px', render: d => d ? d.toFixed(2) + '%' : '-' },
                { title: '近1年', data: 'y1_return', width: '80px', render: d => d ? d.toFixed(2) + '%' : '-' },
                { title: '今年来', data: 'ytd_return', width: '80px', render: d => d ? d.toFixed(2) + '%' : '-' }
            ],
            createdRow: function(row, data) {
                if (onRowClick) {
                    $(row).css('cursor', 'pointer').on('click', () => onRowClick(data));
                }
            }
        });
    },

    /**
     * 创建交易记录表格
     * @param {string} tableId - 表格 ID
     * @returns {Object} DataTables 实例
     */
    createTradeTable: function(tableId) {
        return this.create(tableId, {
            columns: [
                { title: '时间', data: 'created_at', width: '160px' },
                { title: '代码', data: 'code', width: '100px' },
                { title: '名称', data: 'name', width: '120px' },
                {
                    title: '方向',
                    data: 'action',
                    width: '80px',
                    render: d => {
                        const cls = d === 'buy' ? 'color-up' : 'color-down';
                        const text = d === 'buy' ? '买入' : '卖出';
                        return `<span class="${cls}">${text}</span>`;
                    }
                },
                { title: '数量', data: 'quantity', width: '100px', render: d => d ? d.toLocaleString() : '-' },
                { title: '价格', data: 'price', width: '100px', render: d => d ? d.toFixed(2) : '-' },
                { title: '金额', data: 'total_amount', width: '120px', render: d => d ? AppUtils.formatMoney(d) : '-' },
                { title: '手续费', data: 'commission', width: '100px', render: d => d ? AppUtils.formatMoney(d) : '-' }
            ],
            order: [[0, 'desc']]
        });
    },

    /**
     * 重新加载表格数据
     * @param {Object} table - DataTables 实例
     * @param {Array} data - 新数据
     */
    reloadData: function(table, data) {
        if (table) {
            table.clear();
            table.rows.add(data);
            table.draw();
        }
    },

    /**
     * 获取选中行数据
     * @param {Object} table - DataTables 实例
     * @returns {Array} 选中的行数据
     */
    getSelectedRows: function(table) {
        if (!table) return [];
        return table.rows('.selected').data().toArray();
    }
};
