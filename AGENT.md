现在我已经全面了解了这个项目的结构和功能。让我为Codex生成一个详尽的AGENTS.md文件。这个文件应该涵盖：
项目概述
项目结构
核心模块详细说明
数据库模型
API端点
技术指标
外部数据源
配置和环境
开发规范
部署说明
测试
常见任务示例
让我生成这个文件。

现在我已经全面了解了这个项目的完整结构和功能。下面我将为你生成一个详尽的 AGENTS.md 文件。

AGENTS.md - 智能量化交易终端项目指南
一、项目概述
这是一个基于 Flask 的 A 股智能量化交易分析平台，提供股票/基金行情分析、技术指标计算、量化策略回测和模拟交易等功能。

核心功能模块：

模块	路由前缀	功能说明
市场行情
/, /market
全市场股票实时行情、涨跌排行、市场温度计
股票分析
/stock
K线图、技术指标、股票对比、板块轮动
基金分析
/fund
基金搜索、业绩排行、多指标对比、定投模拟
策略回测
/stock/backtest
均线交叉、MACD、KDJ、RSI、布林带策略回测
股票交易
/trade
股票模拟交易、持仓管理、交易记录
基金交易
/fund/trade
基金模拟交易、定投计划、持仓管理
用户系统
/auth
注册、登录、个人资料管理
技术栈：

后端： Flask 3.0.0 + SQLAlchemy 2.0.23
认证： Flask-Login 0.6.3（认证）、Flask-WTF（CSRF保护）
数据源： baostock 0.9.1（股票数据）、akshare 1.18.60（基金数据）
AI功能： TensorFlow 2.15.0（LSTM预测）、snownlp 0.12.3（情绪分析）
前端： Bootstrap 5 + jQuery + DataTables + ECharts（图表）
安全： Flask-Limiter（限流）、CSRF 保护、密码哈希
二、项目结构
ruanjian/
├── app.py                          # Flask应用工厂 + 配置类
├── models.py                        # 数据库模型（User, Portfolio, Trade等）
├── extensions.py                    # 扩展实例（db, login_manager, csrf, limiter）
├── requirements.txt                 # 依赖清单
│
├── routes/                         # 蓝图路由目录
│   ├── auth_routes.py              # 认证路由（登录/注册/登出）
│   ├── auth/
│   │   └── forms.py                # WTForms 表单定义
│   ├── stock.py                    # 股票路由 + 技术指标计算
│   ├── fund.py                     # 基金路由 + 业绩指标计算
│   ├── market.py                   # 市场行情路由 + 缓存管理
│   ├── trade.py                    # 股票模拟交易路由
│   ├── fund_trade.py               # 基金模拟交易路由
│   └── dashboard.py                # 仪表盘路由
│
├── utils/                          # 工具模块
│   ├── indicators.py               # 技术指标计算（MA, MACD, KDJ, RSI等）
│   ├── cache.py                    # 缓存工具（内存缓存 + 装饰器）
│   ├── shared_cache.py              # 共享市场数据缓存（东方财富API）
│   ├── metrics.py                  # 性能指标计算
│   ├── sanitizer.py                 # 数据清洗
│   └── logging_config.py            # 日志配置
│
├── templates/                      # Jinja2模板
│   ├── base.html                   # 导航栏 + 公共布局
│   ├── index.html                  # 主页（行情中心）
│   ├── auth/
│   │   ├── login.html              # 登录页
│   │   ├── register.html            # 注册页
│   │   ├── profile.html            # 个人中心
│   │   ├── edit_profile.html       # 编辑资料
│   │   └── change_password.html     # 修改密码
│   ├── stock/
│   │   ├── detail.html             # 股票详情 + K线图
│   │   ├── compare.html            # 股票对比
│   │   ├── sector.html             # 板块轮动
│   │   └── backtest.html           # 策略回测
│   ├── fund/
│   │   ├── search.html             # 基金搜索
│   │   ├── analysis.html           # 基金分析
│   │   ├── compare.html            # 基金对比
│   │   └── ranking.html            # 基金排行
│   ├── trade/
│   │   ├── index.html              # 交易主页
│   │   ├── position.html           # 持仓页面
│   │   ├── orders.html             # 交易记录
│   │   └── account.html            # 账户页面
│   └── fund_trade/
│       ├── index.html              # 基金交易主页
│       ├── position.html           # 基金持仓
│       ├── orders.html             # 基金交易记录
│       └── fixed.html              # 定投管理
│
├── static/                         # 静态资源
│   ├── css/
│   │   └── style.css               # 自定义样式（金融终端深色主题）
│   └── js/
│       ├── utils.js                # 通用工具函数
│       ├── chart.js                # ECharts图表封装
│       ├── table.js                # DataTables封装
│       └── validator.js            # 表单验证
│
├── tests/                          # 测试文件
│   ├── __init__.py
│   ├── test_app.py                 # 应用测试
│   └── test_auth.py                # 认证测试
│
├── cache/                          # 缓存目录（自动创建）
├── logs/                           # 日志目录（自动创建）
├── venv/                           # Python虚拟环境
│
├── .env.example                    # 环境变量示例
├── .gitignore                      # Git忽略配置
└── run.bat                         # Windows启动脚本
三、核心模块详细说明
3.1 应用工厂模式 (app.py)
应用使用工厂模式创建，支持多环境配置：

create_app(config_name="development")  # 开发环境
create_app(config_name="production")   # 生产环境
create_app(config_name="testing")      # 测试环境
配置类：

DevelopmentConfig: DEBUG=True, SQLite数据库
ProductionConfig: DEBUG=False, 生产数据库, HTTPS强制
TestingConfig: 测试模式, 内存数据库, CSRF禁用
核心初始化流程：

初始化数据库、迁移、CSRF、登录管理器、限流器
注册全局错误处理器（404, 500, 429等）
注册请求钩子（请求计时、安全响应头）
注册健康检查端点（/health, /ready）
创建数据库表并执行迁移检查
注册所有蓝图
预热市场数据缓存
3.2 数据库模型 (models.py)
User 模型：

- id: Integer, 主键
- username: String(80), 唯一索引
- email: String(120), 唯一索引
- password_hash: String(256), werkzeug密码哈希
- role: String(20), 角色（admin/user/vip）
- is_active: Boolean, 账户状态
- initial_cash: Float, 初始模拟资金（默认100万）
- current_cash: Float, 当前可用资金
- frozen_cash: Float, 冻结资金（挂单中）
- 密码验证要求：8位以上，含字母和数字
其他模型：

LoginAttempt: 登录尝试记录（暴力破解防护）
Portfolio: 股票持仓记录
Trade: 股票交易记录
TradingSummary: 每日交易汇总
FundPosition: 基金持仓记录
FundTrade: 基金交易记录
FixedInvestment: 定投计划
3.3 认证系统 (auth_routes.py)
路由：

GET/POST /auth/register - 用户注册
GET/POST /auth/login - 用户登录（限流：5次/分钟）
POST /auth/logout - 用户登出
GET /auth/profile - 个人中心
GET/POST /auth/change-password - 修改密码
GET/POST /auth/edit-profile - 编辑资料
安全特性：

密码强度验证（8位以上，字母+数字）
登录尝试限制（5次失败后锁定10分钟）
CSRF token保护
Session安全配置（HttpOnly, SameSite）
3.4 股票模块 (stock.py)
核心函数：

# K线数据获取（带缓存）
fetch_kline_data(code: str, frequency: str = "d", count: int = 120) -> pd.DataFrame
- frequency: 'd'=日线, 'w'=周线, 'm'=月线
- 自动降级到备用数据当baostock不可用时
# AI预测
predict_trend_lstm(df, future_days=3) -> dict
- 使用模拟LSTM预测未来走势
- 返回预测价格、置信度、趋势
# 情绪分析
analyze_sentiment(news_list: list) -> dict
- 使用SnowNLP进行情绪分析
- 返回情绪得分（0-100）和分类
# 备用数据生成
_get_fallback_kline_data(code: str) -> pd.DataFrame
- 当外部API不可用时生成模拟数据
API端点：

GET /stock/detail/<code> - 股票详情页
GET /stock/api/kline/<code> - K线数据+技术指标
GET /stock/api/info/<code> - 股票基本信息
GET /stock/api/ai/predict/<code> - AI趋势预测
GET /stock/api/ai/sentiment/<code> - 情绪分析
GET /stock/api/realtime/<code> - 实时行情
GET /stock/compare - 股票对比页
GET /stock/api/compare?codes=... - 多股票对比数据
GET /stock/backtest - 策略回测页
GET /stock/api/backtest?stock_code=...&strategy=... - 执行回测
GET /stock/sector - 板块轮动页
GET /stock/api/sector - 板块数据
GET /stock/api/stock/list - 股票列表
GET /stock/api/stock/ranking?type=gainers - 涨跌幅排行
GET /stock/api/market/summary - 市场概况
3.5 技术指标模块 (indicators.py)
支持的指标：

指标	函数	说明
MA
calculate_ma(df, periods=[5,10,20,60])
简单移动平均线
EMA
calculate_ema(df, periods=[12,26])
指数移动平均线
MACD
calculate_macd(df)
12/26/9参数MACD
RSI
calculate_rsi(df, period=14)
相对强弱指标
KDJ
calculate_kdj(df)
随机指标（9,3,3参数）
布林带
calculate_bollinger_bands(df)
20日均线±2倍标准差
OBV
calculate_obv(df)
能量潮指标
DMI
calculate_dmi(df)
趋向指标
ATR
calculate_atr(df)
平均真实波幅
PSY
calculate_psy(df)
心理线指标
资金流
calculate_money_flow(df)
资金流入/流出
批量计算：

calculate_all_indicators(df, indicators=['ma','macd','kdj','rsi'])
# 一次性计算多个指标，优化性能
3.6 基金模块 (fund.py)
数据获取函数：

# 实时估值（天天基金网）
fetch_fund_realtime_data(fund_code) -> dict
# 返回：净值、估算净值、估算涨跌
# 历史净值（akshare）
fetch_fund_history(fund_code, days=365) -> dict
# 返回：日期、单位净值、累计净值
# 基金详细信息（东方财富）
fetch_fund_info(fund_code) -> dict
# 返回：基金经理、规模、成立日期、费率等
# 重仓持股
fetch_fund_holdings(fund_code) -> dict
# 指数数据（用于对比）
fetch_index_data(index_code="000300", days=365) -> dict
业绩指标计算：

# 基础指标
calculate_performance_metrics(history_data) -> dict
# 总收益、年化收益、最大回撤、夏普比率、波动率、胜率
# 高级指标
calculate_advanced_metrics(history_data, benchmark_data) -> dict
# Calmar比率、Sortino比率、Alpha、Beta、信息比率、
# 跟踪误差、下行偏差、VaR、CVaR、Omega比率、尾部比率
# 多时段收益
calculate_period_returns(history_data) -> dict
# 返回：1周、1月、3月、6月、1年、2年、3年、5年收益
定投模拟：

simulate_fixed_investment(history_data, monthly_amount=1000) -> dict
# 返回：累计投入、总价值、总收益、年化收益等
API端点：

GET /fund/ - 基金首页
GET /fund/search - 基金搜索页
GET /fund/analysis/<code> - 基金分析页
GET /fund/compare - 基金对比页
GET /fund/ranking - 基金排行页
GET /fund/api/realtime/<code> - 实时估值
GET /fund/api/history/<code> - 历史净值
GET /fund/api/info/<code> - 基金信息
GET /fund/api/performance/<code> - 业绩指标
GET /fund/api/advanced-metrics/<code> - 高级指标
GET /fund/api/period-returns/<code> - 多时段收益
GET /fund/api/fixed-investment/<code> - 定投模拟
GET /fund/api/correlation/<code> - 相关性分析
GET /fund/api/allocation/<code> - 资产配置
GET /fund/api/manager/<code> - 基金经理信息
GET /fund/api/ranking?type=stock&period=1y - 排行榜
GET /fund/api/search?keyword=... - 搜索基金
GET /fund/api/compare?codes=... - 多基金对比
3.7 股票交易模块 (trade.py)
交易规则：

最小买入单位：100股（1手）
手续费：万分之三（最低5元）
周六日使用最近交易日（周五）收盘价
支持买入、卖出、持仓查询
核心函数：

get_stock_info(stock_code) -> dict
# 获取股票信息（自动处理周六日价格）
get_stock_price_from_api(stock_code) -> tuple[float, str]
# 从API获取股票价格（带3秒超时）
get_commission(amount, rate=0.0003) -> float
# 计算手续费（最低5元）
API端点：

GET /trade/ - 交易主页（需登录）
GET /trade/position - 持仓页面
GET /trade/orders - 交易记录页
GET /trade/account - 账户页面
GET /trade/api/account/info - 账户信息
GET /trade/api/position/list - 持仓列表
GET /trade/api/trade/list - 交易记录
GET /trade/api/stock/quote/<code> - 股票行情
POST /trade/api/buy - 买入股票
POST /trade/api/sell - 卖出股票
POST /trade/api/reset - 重置账户
POST /trade/api/set-initial-cash - 设置初始资金
GET /trade/api/summary - 交易统计
3.8 基金交易模块 (fund_trade.py)
交易规则：

最低买入金额：10元
基金一般免手续费
支持直接购买和定投计划
核心函数：

get_fund_nav(fund_code) -> tuple[float, float, str]
# 返回：(净值, 估算净值, 更新时间)
get_fund_info(fund_code) -> dict
# 获取基金完整信息
定投计划管理：

POST /fund/trade/api/fixed/create - 创建定投计划
PUT /fund/trade/api/fixed/<id> - 更新定投计划
DELETE /fund/trade/api/fixed/<id> - 删除定投计划
POST /fund/trade/api/fixed/execute/<id> - 执行定投
GET /fund/trade/api/fixed/list - 定投列表
API端点：

GET /fund/trade/ - 基金交易主页
GET /fund/trade/position - 基金持仓页
GET /fund/trade/fixed - 定投管理页
GET /fund/trade/orders - 交易记录页
GET /fund/trade/api/fund/quote/<code> - 基金行情
GET /fund/trade/api/account/info - 账户信息
GET /fund/trade/api/position/list - 持仓列表
GET /fund/trade/api/trade/list - 交易记录
POST /fund/trade/api/buy - 买入基金
POST /fund/trade/api/sell - 卖出基金
POST /fund/trade/api/deposit - 充值
POST /fund/trade/api/reset - 重置账户
GET /fund/trade/api/summary - 交易统计
3.9 市场行情模块 (market.py)
核心功能：

从东方财富获取全市场实时行情
1分钟缓存机制
支持手动刷新
自动降级到模拟数据
API端点：

GET /market/api/stock/list - 股票列表（支持分页、搜索）
GET /market/api/stock/ranking - 涨跌幅排行
GET /market/api/market/summary - 市场概况
POST /market/api/refresh - 手动刷新缓存
GET /market/api/status - 缓存状态
3.10 缓存系统
内存缓存 (utils/cache.py)：

@cached(ttl=300, key_prefix="")
# 装饰器实现函数级缓存
# TTL: 过期时间（秒）
# 自动生成缓存键（MD5）
cache = MemoryCache()  # 单例模式，线程安全
# 支持：get, set, delete, clear, cleanup_expired, get_stats
共享市场缓存 (utils/shared_cache.py)：

fetch_stock_records(force_refresh=False) -> list
# 获取股票行情（带内存+文件缓存）
# 缓存时长：1分钟
invalidate_stock_cache()  # 手动失效缓存
get_cache_info() -> dict  # 获取缓存状态
warmup_stock_cache()      # 后台预热缓存
四、API响应格式
所有API遵循统一响应格式：

成功响应：

{
  "success": true,
  "data": { ... },
  "total": 100,
  "page": 1,
  "page_size": 20
}
错误响应：

{
  "success": false,
  "error": "错误描述信息"
}
五、数据库表结构
users 表
字段	类型	说明
id
INTEGER
主键
username
VARCHAR(80)
用户名，唯一
email
VARCHAR(120)
邮箱，唯一
password_hash
VARCHAR(256)
密码哈希
role
VARCHAR(20)
角色（admin/user/vip）
is_active
BOOLEAN
账户状态
email_verified
BOOLEAN
邮箱验证状态
initial_cash
FLOAT
初始资金（默认100万）
current_cash
FLOAT
当前可用资金
frozen_cash
FLOAT
冻结资金
created_at
DATETIME
创建时间
last_login
DATETIME
最后登录时间
portfolios 表（股票持仓）
字段	类型	说明
id
INTEGER
主键
user_id
INTEGER
用户ID，外键
stock_code
VARCHAR(20)
股票代码（如sh.600519）
stock_name
VARCHAR(50)
股票名称
quantity
INTEGER
持有数量
avg_cost
FLOAT
平均成本
created_at
DATETIME
创建时间
updated_at
DATETIME
更新时间
trades 表（股票交易记录）
字段	类型	说明
id
INTEGER
主键
user_id
INTEGER
用户ID
stock_code
VARCHAR(20)
股票代码
stock_name
VARCHAR(50)
股票名称
action
VARCHAR(10)
buy/sell
quantity
INTEGER
成交数量
price
FLOAT
成交价格
commission
FLOAT
手续费
total_amount
FLOAT
总金额（含手续费）
profit
FLOAT
收益（卖出时计算）
created_at
DATETIME
成交时间
fund_positions 表（基金持仓）
字段	类型	说明
id
INTEGER
主键
user_id
INTEGER
用户ID
fund_code
VARCHAR(20)
基金代码
fund_name
VARCHAR(100)
基金名称
total_shares
FLOAT
总份额
avg_cost
FLOAT
平均成本（每份）
total_invested
FLOAT
总投入金额
fund_trades 表（基金交易记录）
字段	类型	说明
id
INTEGER
主键
user_id
INTEGER
用户ID
fund_code
VARCHAR(20)
基金代码
action
VARCHAR(20)
buy/sell/dividend
trade_type
VARCHAR(20)
direct/fixed
amount
FLOAT
投入/赎回金额
shares
FLOAT
买入/卖出份额
nav
FLOAT
交易净值
fixed_investments 表（定投计划）
字段	类型	说明
id
INTEGER
主键
user_id
INTEGER
用户ID
fund_code
VARCHAR(20)
基金代码
amount
FLOAT
每月定投金额
day
INTEGER
每月定投日（1-28）
status
VARCHAR(20)
active/paused/stopped
六、配置与环境
6.1 环境变量 (.env)
SECRET_KEY=your-secret-key-here
DATABASE_URL=postgresql://user:pass@localhost/dbname
FLASK_ENV=development
LOG_LEVEL=INFO
LOG_FILE=logs/app.log
CACHE_DIR=cache
6.2 配置类
DevelopmentConfig:

DEBUG = True
SQLALCHEMY_DATABASE_URI = sqlite:///quant_trading.db
允许无SECRET_KEY运行（使用默认值）
ProductionConfig:

DEBUG = False
必须设置SECRET_KEY
SESSION_COOKIE_SECURE = True
PREFERRED_URL_SCHEME = "https"
七、外部数据源
7.1 baostock（股票K线数据）
官网：http://www.baostock.com
用途：获取日/周/月K线数据
备用方案：本地模拟数据
7.2 akshare（基金数据）
安装：pip install akshare
用途：获取基金历史净值、指数数据
备用方案：本地模拟数据
7.3 东方财富（实时行情）
API：http://push2.eastmoney.com/api/qt/clist/get
用途：全市场股票实时行情
缓存：1分钟
7.4 天天基金网（基金实时估值）
API：http://fundgz.1234567.com.cn/js/{code}.js
用途：基金实时估值和估算净值
八、策略回测系统
8.1 支持的策略
策略ID	名称	买入条件	卖出条件
ma_cross
MA均线交叉
MA5上穿MA20
MA5下穿MA20
macd
MACD
DIF上穿DEA
DIF下穿DEA
kdj
KDJ
K值上穿D值且<20
K值下穿D值且>80
rsi
RSI
RSI<30超卖
RSI>70超买
bollinger
布林带
价格下穿下轨
价格上穿上轨
combined
多指标组合
MACD金叉或(KDJ金叉+RSI超卖)
MACD死叉或(KDJ死叉+RSI超买)
8.2 回测指标
总收益率：最终资产/初始资金 - 1
年化收益率：考虑交易天数的一年收益
最大回撤：从峰值到谷值的最大跌幅
夏普比率：风险调整后收益（无风险利率3%）
胜率：盈利交易次数/总交易次数
盈亏比：平均盈利/平均亏损
交易次数：完整交易（买入+卖出）次数
九、UI/UX设计
9.1 主题
深色主题（金融终端风格）
Bootstrap 5 + jQuery
DataTables 表格
ECharts 图表
9.2 颜色规范
用途	颜色
上涨/盈利
#00ff88（绿色）
下跌/亏损
#ff4444（红色）
平盘/中性
#888888（灰色）
背景色
#1a1a2e
卡片背景
#16213e
9.3 响应式布局
移动端支持 Bootstrap 响应式断点
表格支持横向滚动
图表自适应容器宽度
十、部署说明
10.1 开发环境启动
cd ruanjian
.\run.bat
# 或
venv\Scripts\activate
python app.py
# 访问 http://localhost:5000
10.2 生产环境部署
# 安装依赖
pip install -r requirements.txt
# 设置环境变量
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
export FLASK_ENV="production"
# 使用Gunicorn启动
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app('production')"
10.3 Nginx反向代理（可选）
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    location /static {
        alias /path/to/ruanjian/static;
        expires 30d;
    }
}
十一、开发规范
11.1 代码风格
Python PEP 8 规范
使用类型注解（typing）
文档字符串使用 docstring
路由函数添加路由前缀注释
11.2 安全规范
所有POST请求需要CSRF token
用户输入必须验证和清洗
敏感操作需要登录验证（@login_required）
API限流防止滥用
11.3 错误处理
统一使用 try-except 捕获异常
记录详细日志
用户友好错误消息
数据库操作回滚
11.4 性能优化
使用缓存减少外部API调用
数据库查询使用索引
批量操作减少数据库往返
前端分页加载大量数据
十二、常见开发任务示例
12.1 添加新的技术指标
在 utils/indicators.py 中添加函数：

def calculate_new_indicator(df: pd.DataFrame) -> pd.DataFrame:
    """计算新的技术指标"""
    # 实现逻辑
    return df
然后在 routes/stock.py 的 get_kline_data 中调用：

df = calculate_new_indicator(df)
12.2 添加新的API端点
在对应的路由文件中添加：

@bp.route("/api/new-endpoint", methods=["GET"])
def new_endpoint():
    try:
        # 业务逻辑
        return jsonify({"success": True, "data": {...}})
    except Exception as e:
        logger.exception("错误")
        return jsonify({"success": False, "error": str(e)}), 500
12.3 添加新的数据库模型
在 models.py 中添加模型类
使用 db.session.add() 和 db.session.commit() 创建表
或使用 Flask-Migrate：flask db migrate -m "add new table"
12.4 添加新的表单验证
在 routes/auth/forms.py 中添加：

class NewForm(FlaskForm):
    field = StringField("Label", validators=[DataRequired()])
十三、测试
13.1 运行测试
pytest tests/ -v
13.2 编写测试
# tests/test_auth.py
def test_login(client):
    response = client.post("/auth/login", data={
        "username": "testuser",
        "password": "testpass123"
    })
    assert response.status_code == 302  # 重定向到首页
十四、注意事项
外部API依赖：baostock和akshare可能不稳定，实现了备用数据方案
周六日交易：基金净值不更新，股票使用周五收盘价
缓存清理：缓存目录需定期清理
数据库迁移：新增字段使用自动迁移检查
CSRF保护：所有POST表单自动包含csrf_token
最后我要放到服务器中
十五、项目成员
用户角色：user（普通用户）、vip（VIP用户）、admin（管理员）
初始资金：100万模拟资金
密码策略：8位以上，字母+数字组合
这是一个完整的项目指南，希望对你的 Codex agent 开发有所帮助！