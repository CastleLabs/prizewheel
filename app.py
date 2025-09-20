#!/bin/bash
#
# Raspberry Pi Prize Wheel System - FIXED Setup Script v2.3
# Addresses virtual environment, database, and service issues
#

set -e  # Exit on any error

# Script Configuration
SCRIPT_VERSION="2.3-FIXED"
PROJECT_NAME="Prize Wheel System"
PROJECT_DIR="$HOME/prizewheel"
SERVICE_NAME="prizewheel"
LOG_FILE="/tmp/prizewheel-setup.log"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes
readonly GREEN='\033[0;32m'
readonly RED='\033[0;31m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

log() {
    echo -e "${1}" | tee -a "${LOG_FILE}"
}

print_status() {
    log "${GREEN}✅${NC} ${1}"
}

print_error() {
    log "${RED}❌${NC} ${1}"
}

print_warning() {
    log "${YELLOW}⚠️${NC} ${1}"
}

print_info() {
    log "${BLUE}ℹ️${NC} ${1}"
}

# FIXED: Comprehensive cleanup function
cleanup_previous_installation() {
    print_info "Cleaning up any previous installation..."
    
    # Stop services
    sudo systemctl stop prizewheel 2>/dev/null || true
    sudo systemctl stop prizewheel-kiosk 2>/dev/null || true
    sudo systemctl stop prizewheel-watchdog 2>/dev/null || true
    sudo systemctl disable prizewheel 2>/dev/null || true
    sudo systemctl disable prizewheel-kiosk 2>/dev/null || true
    sudo systemctl disable prizewheel-watchdog 2>/dev/null || true
    
    # Remove service files
    sudo rm -f /etc/systemd/system/prizewheel*.service
    sudo systemctl daemon-reload
    
    # Backup existing project if it exists
    if [[ -d "${PROJECT_DIR}" ]]; then
        print_warning "Backing up existing installation..."
        sudo mv "${PROJECT_DIR}" "${PROJECT_DIR}.backup.$(date +%s)" 2>/dev/null || true
    fi
    
    print_status "Cleanup completed"
}

# FIXED: System update and package installation
update_system() {
    print_info "Updating system packages..."
    sudo apt-get update -qq
    sudo apt-get upgrade -y -qq
    
    print_info "Installing essential packages..."
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-setuptools \
        python3-wheel \
        git \
        curl \
        wget \
        sqlite3 \
        build-essential \
        libffi-dev \
        libssl-dev \
        nginx \
        htop \
        nano \
        rsync \
        ufw \
        python3-rpi.gpio \
        python3-gpiozero \
        alsa-utils \
        pulseaudio
    
    print_status "System packages installed"
}

# FIXED: Create project structure with proper permissions
create_project_structure() {
    print_info "Creating project directory structure..."
    
    cleanup_previous_installation
    
    # Create main project directory
    mkdir -p "${PROJECT_DIR}"
    cd "${PROJECT_DIR}"
    
    # Copy files from source
    print_info "Copying application files..."
    cp "${SOURCE_DIR}"/*.py . 2>/dev/null || true
    cp "${SOURCE_DIR}"/*.txt . 2>/dev/null || true
    cp "${SOURCE_DIR}"/*.json . 2>/dev/null || true
    cp "${SOURCE_DIR}"/*.html . 2>/dev/null || true
    
    # Create directory structure
    mkdir -p {logs,backups,scripts,static/{css,js,sounds,images},templates}
    
    # Move HTML files to templates directory if they exist
    mv *.html templates/ 2>/dev/null || true
    
    # Set proper ownership and permissions
    chown -R $USER:$USER "${PROJECT_DIR}"
    chmod 755 "${PROJECT_DIR}"
    
    print_status "Project structure created"
}

# FIXED: Python virtual environment setup
setup_python_environment() {
    print_info "Setting up Python virtual environment..."
    
    cd "${PROJECT_DIR}"
    
    # Remove any existing venv
    rm -rf venv
    
    # Create new virtual environment
    python3 -m venv venv
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip setuptools wheel
    
    # Install dependencies
    print_info "Installing Python dependencies..."
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
    else
        # Install minimal required packages
        pip install \
            Flask==2.3.3 \
            Flask-SQLAlchemy==3.0.5 \
            Flask-SocketIO==5.3.6 \
            python-socketio==5.10.0 \
            Werkzeug==2.3.7 \
            RPi.GPIO==0.7.1 \
            python-dotenv==1.0.0 \
            gunicorn==21.2.0 \
            psutil==5.9.6
    fi
    
    print_status "Python environment setup completed"
}

# FIXED: Database initialization with proper error handling
setup_database() {
    print_info "Setting up database..."
    
    cd "${PROJECT_DIR}"
    source venv/bin/activate
    
    # Create .env file first
    cat > .env << EOF
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
FLASK_ENV=production
FLASK_DEBUG=False
DATABASE_URL=sqlite:///${PROJECT_DIR}/prizewheel.db
EOF
    
    # Initialize database using Python
    python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '.')

from app import app, db, init_db
import os

if __name__ == "__main__":
    try:
        with app.app_context():
            print("Creating database tables...")
            db.create_all()
            print("Database tables created successfully")
            
            # Call the init_db function to set up default data
            print("Initializing default data...")
            init_db()
            print("Database initialization completed")
            
    except Exception as e:
        print(f"Database setup error: {e}")
        sys.exit(1)
PYTHON_SCRIPT
    
    # Set proper permissions on database
    chmod 664 prizewheel.db 2>/dev/null || true
    
    print_status "Database setup completed"
}

# FIXED: Nginx configuration
configure_nginx() {
    print_info "Configuring Nginx..."
    
    # Create Nginx configuration
    sudo tee /etc/nginx/sites-available/prizewheel > /dev/null << EOF
server {
    listen 80;
    server_name _;
    
    client_max_body_size 20M;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    location /static/ {
        alias ${PROJECT_DIR}/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    
    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }
}
EOF

    # Enable site
    sudo ln -sf /etc/nginx/sites-available/prizewheel /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test configuration
    if sudo nginx -t; then
        print_status "Nginx configured successfully"
    else
        print_error "Nginx configuration failed"
        exit 1
    fi
}

# FIXED: Systemd service with proper virtual environment activation
create_systemd_service() {
    print_info "Creating systemd service..."
    
    # Create the main service file with FIXED virtual environment handling
    sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Prize Wheel System Flask Application
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${PROJECT_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="VIRTUAL_ENV=${PROJECT_DIR}/venv"
Environment="FLASK_APP=app.py"
Environment="FLASK_ENV=production"
ExecStartPre=/bin/bash -c 'cd ${PROJECT_DIR} && source venv/bin/activate && python -c "import app; print(\"App import successful\")"'
ExecStart=${PROJECT_DIR}/venv/bin/python -m gunicorn --bind 127.0.0.1:5000 --workers 2 --timeout 60 app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

    # Create a startup script for better service management
    cat > "${PROJECT_DIR}/start_app.sh" << 'EOF'
#!/bin/bash
cd "${PROJECT_DIR}"
source venv/bin/activate
exec python -m gunicorn --bind 127.0.0.1:5000 --workers 2 --timeout 60 app:app
EOF

    chmod +x "${PROJECT_DIR}/start_app.sh"
    
    print_status "Systemd service created"
}

# FIXED: Service startup and testing
start_services() {
    print_info "Starting services..."
    
    # Reload systemd
    sudo systemctl daemon-reload
    
    # Enable and start nginx
    sudo systemctl enable nginx
    sudo systemctl restart nginx
    
    # Enable and start the main service
    sudo systemctl enable ${SERVICE_NAME}
    sudo systemctl start ${SERVICE_NAME}
    
    # Wait for service to start
    sleep 5
    
    # Check service status
    if sudo systemctl is-active --quiet ${SERVICE_NAME}; then
        print_status "Prize Wheel service started successfully"
    else
        print_error "Prize Wheel service failed to start"
        print_info "Checking service logs..."
        sudo journalctl -u ${SERVICE_NAME} --no-pager -n 20
        return 1
    fi
    
    # Test web interface
    if curl -f http://localhost/health > /dev/null 2>&1; then
        print_status "Web interface is accessible"
    else
        print_warning "Web interface test failed - checking logs..."
        sudo journalctl -u ${SERVICE_NAME} --no-pager -n 10
    fi
}

# Test admin login
test_admin_login() {
    print_info "Testing admin login functionality..."
    
    cd "${PROJECT_DIR}"
    source venv/bin/activate
    
    # Test database and admin user
    python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '.')

try:
    from app import app, db, User
    from werkzeug.security import check_password_hash
    
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        if admin_user:
            print("✅ Admin user found in database")
            if check_password_hash(admin_user.password_hash, 'admin123'):
                print("✅ Admin password verification successful")
            else:
                print("❌ Admin password verification failed")
        else:
            print("❌ Admin user not found in database")
            
except Exception as e:
    print(f"❌ Database test failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT
}

# Main setup function
main() {
    print_info "Starting Prize Wheel System setup v${SCRIPT_VERSION}..."
    
    # Check if running as root
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should NOT be run as root!"
        exit 1
    fi
    
    # Main setup steps
    update_system
    create_project_structure
    setup_python_environment
    setup_database
    configure_nginx
    create_systemd_service
    start_services
    test_admin_login
    
    # Final summary
    local IP_ADDRESS=$(hostname -I | awk '{print $1}')
    
    print_info ""
    print_status "🎉 Prize Wheel System setup completed successfully!"
    print_info ""
    print_info "🌐 Access URLs:"
    print_info "   Main Wheel: http://${IP_ADDRESS}/"
    print_info "   Admin Panel: http://${IP_ADDRESS}/admin"
    print_info ""
    print_info "🔐 Default Login:"
    print_info "   Username: admin"
    print_info "   Password: admin123"
    print_info ""
    print_info "📊 Service Management:"
    print_info "   Status: sudo systemctl status prizewheel"
    print_info "   Logs: sudo journalctl -u prizewheel -f"
    print_info "   Restart: sudo systemctl restart prizewheel"
    print_info ""
    print_info "🔧 Troubleshooting:"
    print_info "   Database check: cd ${PROJECT_DIR} && source venv/bin/activate && python -c 'from app import *; print(\"OK\")'"
    print_info "   Log file: ${LOG_FILE}"
    print_info ""
    
    read -p "Setup complete! Would you like to open the admin panel now? (y/N): " -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        print_info "Opening admin panel..."
        if command -v firefox &> /dev/null; then
            firefox "http://localhost/admin" &
        elif command -v chromium-browser &> /dev/null; then
            chromium-browser "http://localhost/admin" &
        else
            print_info "Please open http://localhost/admin in your web browser"
        fi
    fi
}

# Run main function
main "$@"
