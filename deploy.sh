#!/bin/bash
# 科研文献智能解析与知识服务系统 - Linux一键部署脚本
# 使用方法: bash deploy.sh [your_domain] [your_username]

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 打印日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 参数处理
DOMAIN=${1:-localhost}
USERNAME=${2:-$USER}

echo "============================================"
echo "  科研文献智能解析与知识服务系统"
echo "  Linux一键部署脚本"
echo "============================================"
echo "  域名/IP: $DOMAIN"
echo "  用户名: $USERNAME"
echo "============================================"

# 检查是否为root用户
if [ "$(id -u)" != "0" ]; then
    log_warn "建议使用root用户运行此脚本"
    read -p "是否继续以当前用户运行? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_error "部署已取消"
        exit 1
    fi
fi

# ============================================
# Step 1: 更新系统
# ============================================
log_info "Step 1/10: 更新系统..."
if command -v yum &> /dev/null; then
    yum update -y
elif command -v apt &> /dev/null; then
    apt update && apt upgrade -y
else
    log_warn "未知的包管理器，跳过系统更新"
fi
log_success "系统更新完成"

# ============================================
# Step 2: 安装基础依赖
# ============================================
log_info "Step 2/10: 安装基础依赖..."
if command -v yum &> /dev/null; then
    yum install -y wget curl git gcc gcc-c++ make openssl-devel bzip2-devel libffi-devel zlib-devel
elif command -v apt &> /dev/null; then
    apt install -y wget curl git gcc g++ make openssl libssl-dev libbz2-dev libffi-dev zlib1g-dev
else
    log_error "无法安装基础依赖"
    exit 1
fi
log_success "基础依赖安装完成"

# ============================================
# Step 3: 安装Python 3.10
# ============================================
log_info "Step 3/10: 安装Python 3.10..."
if command -v python3.10 &> /dev/null; then
    log_warn "Python 3.10已安装，跳过"
else
    if command -v yum &> /dev/null; then
        # CentOS 7
        if [ -f /etc/centos-release ] && grep -q "CentOS Linux release 7" /etc/centos-release; then
            yum install -y https://repo.ius.io/ius-release-el7.rpm || true
            yum install -y python310 python310-devel python310-pip || true
        else
            yum install -y python310 python310-devel python310-pip
        fi
    elif command -v apt &> /dev/null; then
        apt install -y python3.10 python3.10-dev python3.10-venv
        curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
    else
        log_error "无法安装Python 3.10"
        exit 1
    fi
fi

if ! command -v python3.10 &> /dev/null; then
    log_error "Python 3.10安装失败"
    exit 1
fi
log_success "Python 3.10安装完成"
python3.10 --version

# ============================================
# Step 4: 安装Node.js 18（使用阿里云镜像）
# ============================================
log_info "Step 4/10: 安装Node.js 18..."
if command -v node &> /dev/null && node --version | grep -q "v18"; then
    log_warn "Node.js 18已安装，跳过"
else
    if command -v yum &> /dev/null; then
        curl -sL https://mirrors.aliyun.com/nodesource/setup_18.x | bash -
        yum install -y nodejs
    elif command -v apt &> /dev/null; then
        curl -sL https://mirrors.aliyun.com/nodesource/setup_18.x | bash -
        apt install -y nodejs
    else
        log_error "无法安装Node.js"
        exit 1
    fi
fi

if ! command -v node &> /dev/null; then
    log_error "Node.js安装失败"
    exit 1
fi
log_success "Node.js安装完成"
node --version

# ============================================
# Step 5: 安装MySQL
# ============================================
log_info "Step 5/11: 安装MySQL..."
if command -v mysql &> /dev/null; then
    log_warn "MySQL已安装，跳过"
else
    if command -v yum &> /dev/null; then
        yum install -y mysql-community-server
        systemctl start mysqld
        systemctl enable mysqld
    elif command -v apt &> /dev/null; then
        apt install -y mysql-server
        systemctl start mysql
        systemctl enable mysql
    else
        log_error "无法安装MySQL"
        exit 1
    fi
fi

# 创建数据库和用户
log_info "创建数据库..."
mysql -u root -e "CREATE DATABASE IF NOT EXISTS literature_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "CREATE USER IF NOT EXISTS 'lit_user'@'localhost' IDENTIFIED BY 'lit_password';"
mysql -u root -e "GRANT ALL PRIVILEGES ON literature_db.* TO 'lit_user'@'localhost';"
mysql -u root -e "FLUSH PRIVILEGES;"
log_success "MySQL安装完成"
mysql --version

# ============================================
# Step 6: 安装Nginx
# ============================================
log_info "Step 6/11: 安装Nginx..."
if command -v nginx &> /dev/null; then
    log_warn "Nginx已安装，跳过"
else
    if command -v yum &> /dev/null; then
        yum install -y nginx
    elif command -v apt &> /dev/null; then
        apt install -y nginx
    else
        log_error "无法安装Nginx"
        exit 1
    fi
fi
log_success "Nginx安装完成"
nginx -v

# ============================================
# Step 7: 克隆项目代码
# ============================================
log_info "Step 7/11: 克隆项目代码..."
mkdir -p /opt/aiproject
chown -R $USERNAME:$USERNAME /opt/aiproject

cd /opt/aiproject
if [ -d .git ]; then
    log_warn "项目已存在，拉取最新代码..."
    git pull origin main
else
    git clone https://gitee.com/DongLiuli/aiproject.git .
fi
log_success "项目代码克隆完成"

# ============================================
# Step 8: 安装后端依赖
# ============================================
log_info "Step 8/11: 安装后端依赖..."
cd /opt/aiproject/backend
pip3.10 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
log_success "后端依赖安装完成"

# ============================================
# Step 9: 创建数据库配置文件
# ============================================
log_info "Step 9/11: 创建数据库配置文件..."
cat > /opt/aiproject/backend/db_config.json <<EOF
{
    "DATABASE_URL": "mysql+pymysql://lit_user:lit_password@localhost:3306/literature_db?charset=utf8mb4"
}
EOF
log_success "数据库配置文件创建完成"

# ============================================
# Step 10: 安装前端依赖并打包（使用国内镜像）
# ============================================
log_info "Step 10/11: 安装前端依赖并打包..."
cd /opt/aiproject/frontend
npm config set registry https://registry.npmmirror.com/
npm install
npm run build
log_success "前端构建完成"

# ============================================
# Step 11: 创建数据目录
# ============================================
log_info "Step 11/11: 创建数据目录..."
cd /opt/aiproject/backend
mkdir -p data/uploads data/faiss_index data/report_cache
chown -R $USERNAME:$USERNAME data
log_success "数据目录创建完成"

# ============================================
# Step 12: 配置Nginx
# ============================================
log_info "Step 12/12: 配置Nginx..."

# 创建Nginx配置文件
cat > /etc/nginx/conf.d/paper-system.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        root /opt/aiproject/frontend/dist;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 60s;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /download/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location ~ /\\.(env|git|svn|md)\$ {
        deny all;
    }

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml+rss text/javascript image/svg+xml;
}
EOF

# 测试Nginx配置
if ! nginx -t; then
    log_error "Nginx配置错误"
    exit 1
fi

# 重启Nginx
systemctl restart nginx
systemctl enable nginx
log_success "Nginx配置完成"

# ============================================
# Step 13: 配置Systemd服务
# ============================================
log_info "Step 13/13: 配置Systemd服务..."

# 创建Systemd服务文件
cat > /etc/systemd/system/paper-system.service <<EOF
[Unit]
Description=Paper System Backend Service
After=network.target nginx.service

[Service]
User=$USERNAME
Group=$USERNAME
WorkingDirectory=/opt/aiproject/backend
Environment="HF_ENDPOINT=https://hf-mirror.com"
Environment="DEEPSEEK_API_KEY="
Environment="MODEL_LOCAL_PATH="
ExecStart=/usr/bin/python3.10 -m uvicorn app.main:app --host 127.0.0.1 --port 8080
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

# 重新加载systemd配置
systemctl daemon-reload

# 启动服务
systemctl start paper-system
systemctl enable paper-system
log_success "Systemd服务配置完成"

# ============================================
# Step 14: 配置防火墙
# ============================================
log_info "Step 14/14: 配置防火墙..."
if command -v firewall-cmd &> /dev/null; then
    firewall-cmd --add-port=80/tcp --permanent || true
    firewall-cmd --reload || true
    log_success "防火墙配置完成"
elif command -v ufw &> /dev/null; then
    ufw allow 80/tcp || true
    log_success "防火墙配置完成"
else
    log_warn "未检测到防火墙工具，跳过"
fi

# ============================================
# 等待服务启动并验证
# ============================================
log_info "等待后端服务启动..."
sleep 10

# 检查服务状态
if systemctl is-active --quiet paper-system; then
    log_success "后端服务启动成功"
else
    log_warn "后端服务启动可能需要更长时间（首次启动需要下载模型）"
    log_info "查看日志: journalctl -u paper-system -f"
fi

# ============================================
# 部署完成
# ============================================
echo ""
echo "============================================"
echo "  部署完成!"
echo "============================================"
echo ""
echo "  服务信息:"
echo "  ├── 前端页面: http://$DOMAIN"
echo "  ├── 后端API:  http://$DOMAIN/api"
echo "  └── API文档:  http://$DOMAIN/docs"
echo ""
echo "  管理命令:"
echo "  ├── 查看后端状态: sudo systemctl status paper-system"
echo "  ├── 查看后端日志: sudo journalctl -u paper-system -f"
echo "  ├── 重启后端服务: sudo systemctl restart paper-system"
echo "  └── 重启Nginx: sudo nginx -s reload"
echo ""
echo "  首次使用:"
echo "  1. 打开浏览器访问 http://$DOMAIN"
echo "  2. 进入系统设置页面"
echo "  3. 配置DeepSeek API Key"
echo "  4. 开始上传论文"
echo ""
echo "  注意:"
echo "  - 首次启动需要下载BGE模型（约1.3GB）"
echo "  - 建议服务器内存16GB以上"
echo "  - 如需HTTPS，请配置SSL证书"
echo "============================================"