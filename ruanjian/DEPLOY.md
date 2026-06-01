# 服务器部署指南

适用于 Ubuntu 22.04+、Python 3.11、Gunicorn、Nginx。

## 1. 准备环境

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev build-essential nginx redis-server
sudo mkdir -p /var/www/quant_trading
sudo chown -R $USER:$USER /var/www/quant_trading
```

把 `ruanjian/` 目录内的项目文件上传到 `/var/www/quant_trading`。

## 2. 安装依赖

```bash
cd /var/www/quant_trading
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 3. 配置环境变量

```bash
cat > /var/www/quant_trading/.env << 'EOF'
FLASK_ENV=production
SECRET_KEY=<replace-with-a-real-secret>
DATABASE_URL=sqlite:////var/www/quant_trading/instance/quant_trading.db
RATELIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
LOG_LEVEL=INFO
LOG_FILE=/var/log/quant_trading/app.log
EOF
```

生成密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 4. 创建运行目录

```bash
sudo mkdir -p /var/log/quant_trading /var/run/quant_trading /var/www/quant_trading/instance
sudo chown -R www-data:www-data /var/log/quant_trading /var/run/quant_trading /var/www/quant_trading/instance
```

## 5. Gunicorn 配置

```bash
cat > /var/www/quant_trading/gunicorn_config.py << 'EOF'
bind = "127.0.0.1:5000"
workers = 3
worker_class = "sync"
timeout = 120
keepalive = 5
errorlog = "/var/log/quant_trading/error.log"
accesslog = "/var/log/quant_trading/access.log"
loglevel = "info"
EOF
```

本项目的 `create_app()` 会根据 `.env` 中的 `FLASK_ENV=production` 选择生产配置，也可以显式写成 `app:create_app('production')`。

## 6. Systemd 服务

```bash
sudo tee /etc/systemd/system/quant_trading.service > /dev/null << 'EOF'
[Unit]
Description=Quant Trading Terminal
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/quant_trading
Environment=PATH=/var/www/quant_trading/venv/bin
ExecStart=/var/www/quant_trading/venv/bin/gunicorn -c /var/www/quant_trading/gunicorn_config.py "app:create_app('production')"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable quant_trading
sudo systemctl start quant_trading
sudo systemctl status quant_trading
```

## 7. Nginx 反向代理

```bash
sudo tee /etc/nginx/sites-available/quant_trading > /dev/null << 'EOF'
server {
    listen 80;
    server_name your_domain_or_ip;

    client_max_body_size 16M;

    location /static/ {
        alias /var/www/quant_trading/static/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/quant_trading /etc/nginx/sites-enabled/quant_trading
sudo nginx -t
sudo systemctl restart nginx
```

## 8. HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your_domain.com
sudo certbot renew --dry-run
```

## 9. 部署前检查

```bash
source /var/www/quant_trading/venv/bin/activate
cd /var/www/quant_trading
python -m compileall -q app.py models.py extensions.py routes utils tests
pytest -q
```

## 10. 常用运维命令

```bash
sudo journalctl -u quant_trading -f
sudo systemctl restart quant_trading
sudo systemctl status quant_trading
curl http://127.0.0.1:5000/health
curl http://127.0.0.1:5000/ready
```

## 11. 不要上传到服务器代码目录的内容

上传代码前可参考 `CLEANUP_CANDIDATES.md`。`venv/`、`__pycache__/`、`.pytest_cache/`、`logs/`、本地测试数据库和缓存文件不需要跟随代码提交。
