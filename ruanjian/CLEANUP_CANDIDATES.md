# 后续可清理内容标注

这份清单只做标注，不代表已经删除。部署或提交代码前可以按需清理，清理前建议先备份数据库。

## 可以直接删除的生成物

- `__pycache__/`
- `routes/__pycache__/`
- `routes/auth/__pycache__/`
- `utils/__pycache__/`
- `tests/__pycache__/`
- `.pytest_cache/`

原因：Python/pytest 自动生成的缓存文件，删除后会自动重建。

## 可以轮转或删除的运行日志

- `logs/app.log`
- `logs/error.log`
- `venv/Scripts/logs/`

原因：运行日志不应随项目提交。服务器部署后建议由日志系统或定时任务轮转。

## 需要确认后再删除的本地数据

- `instance/quant_trading.db`
- `instance/trading.db`
- `../instance/quant_trading.db`
- `cache/stock_cache.json`

原因：这些是本地数据库和行情缓存。若只是测试数据，可以删除；若包含演示账号、交易记录或你要保留的数据，先备份。

## 可以重建的环境目录

- `venv/`

原因：当前虚拟环境绑定了旧的本机 Python 路径，迁移后运行 `venv\Scripts\python.exe` 会失败。建议后续删除后用当前机器重新创建：

```powershell
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 明显的旧缓存残留

- `routes/__pycache__/auth.cpython-311.pyc`
- `routes/__pycache__/strategy.cpython-311.pyc`
- `tests/__pycache__/test_all_features.cpython-311-pytest-9.0.3.pyc`

原因：对应源码文件当前不存在，属于历史文件编译缓存。

## 暂时保留

- `migrate_add_columns.py`
- `migrate_account_schema.py`
- `init_db.py`
- `OPTIMIZATION.md`
- `DEPLOY.md`

原因：这些脚本/文档仍可能用于初始化、迁移、部署说明或复盘，不建议在上线前随手删除。
