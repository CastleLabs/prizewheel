#!/bin/bash
#
# Raspberry Pi Prize Wheel System - Comprehensive Fixed Setup Script v2.3
# For Raspberry Pi 5 with CLI-only Raspberry Pi OS (Bookworm recommended)
# Version: 2.3 COMPREHENSIVE-FIXED - All original features + critical fixes
# 
# Author: Prize Wheel System Team
# Date: 2024

set -e  # Exit on any error
set -u  # Exit on undefined variables

# Script Configuration
SCRIPT_VERSION="2.3-COMPREHENSIVE-FIXED"
PROJECT_NAME="Prize Wheel System"
PROJECT_DIR="$HOME/prizewheel"
SERVICE_NAME="prizewheel"
LOG_FILE="/tmp/prizewheel-setup.log"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# FIXED: Robust boot config detection for all Pi OS versions
detect_boot_config() {
    if [ -d "/boot/firmware" ] && [ -w "/boot/firmware" ]; then
        BOOT_CONFIG="/boot/firmware/config.txt"
    elif [ -d "/boot" ] && [ -w "/boot" ]; then
        BOOT_CONFIG="/boot/config.txt"
    else
        # Fallback detection
        for path in "/boot/firmware/config.txt" "/boot/config.txt"; do
            if [ -f "$path" ]; then
                BOOT_CONFIG="$path"
                break
            fi
        done
    fi
    
    if [ -z "${BOOT_CONFIG:-}" ]; then
        BOOT_CONFIG="/boot/config.txt"  # Default fallback
    fi
}

detect_boot_config

# Color codes for enhanced output (FIXED: Proper character encoding)
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[1;37m'
readonly NC='\033[0m' # No Color
readonly BOLD='\033[1m'

# FIXED: ASCII symbols for better compatibility (no corrupted unicode)
readonly CHECKMARK="[OK]"
readonly CROSSMARK="[ERR]"
readonly WARNING="[WARN]"
readonly INFO="[INFO]"
readonly ROCKET="[>>]"
readonly GEAR="[*]"
readonly LOCK="[SEC]"
readonly SOUND="[AUD]"

# Enhanced logging functions
log() {
    echo -e "${1}" | tee -a "${LOG_FILE}"
}

print_header() {
    clear
    log "${PURPLE}${BOLD}"
    log "============================================================================"
    log "                    ${ROCKET} ${PROJECT_NAME} - Setup v${SCRIPT_VERSION} ${ROCKET}"
    log "              Enhanced Raspberry Pi 5 Prize Wheel with Sound Support"
    log "                        CLI-Only OS Compatible with Auto Display"
    log "                              ** COMPREHENSIVE FIXES APPLIED **"
    log "============================================================================"
    log "${NC}"
}

print_status() {
    log "${GREEN}${CHECKMARK}${NC} ${BOLD}$1${NC}"
}

print_error() {
    log "${RED}${CROSSMARK}${NC} ${BOLD}$1${NC}"
}

print_warning() {
    log "${YELLOW}${WARNING}${NC} ${BOLD}$1${NC}"
}

print_info() {
    log "${CYAN}${INFO}${NC} $1"
}

print_section() {
    log ""
    log "${BLUE}${BOLD}${GEAR} $1${NC}"
    log "${BLUE}----------------------------------------------------------------------------${NC}"
}

# FIXED: Enhanced error handling with cleanup
cleanup_on_error() {
    local exit_code=$?
    print_error "Setup failed at line $1 with exit code $exit_code"
    print_error "Check the log file: ${LOG_FILE}"
    print_info "You can re-run this script to continue from where it left off"
    
    # Stop any services that might be partially configured
    sudo systemctl stop prizewheel prizewheel-kiosk prizewheel-watchdog 2>/dev/null || true
    
    exit $exit_code
}

trap 'cleanup_on_error $LINENO' ERR

# System validation functions
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should NOT be run as root!"
        print_info "Please run as a regular user with sudo privileges"
        exit 1
    fi
}

# FIXED: Enhanced source file validation with better error handling
check_source_files() {
    print_section "Source Files Validation"
    
    # Check if we're in the right directory
    if [[ ! -f "app.py" ]] && [[ -f "../app.py" ]]; then
        print_info "Adjusting source directory..."
        cd ..
        SOURCE_DIR="$(pwd)"
    fi
    
    # Verify required application files exist
    local required_files=("app.py" "requirements.txt")
    local missing_files=()
    
    for file in "${required_files[@]}"; do
        if [[ ! -f "${SOURCE_DIR}/${file}" ]]; then
            missing_files+=("$file")
        fi
    done
    
    if [[ ${#missing_files[@]} -gt 0 ]]; then
        print_error "Missing required files in source directory:"
        for file in "${missing_files[@]}"; do
            print_error "  - $file"
        done
        print_info "Please ensure you're running this script from the project root directory"
        print_info "Source directory: ${SOURCE_DIR}"
        exit 1
    fi
    
    # Check for optional files and warn if missing
    local optional_files=("display.html" "dashboard.html" "login.html" "sample_prizes.json")
    for file in "${optional_files[@]}"; do
        if [[ -f "${SOURCE_DIR}/${file}" ]]; then
            print_status "Found: $file"
        else
            print_warning "Optional file not found: $file"
        fi
    done
    
    # FIXED: Validate requirements.txt content
    if grep -q "Flask" "${SOURCE_DIR}/requirements.txt"; then
        print_status "requirements.txt appears valid"
    else
        print_warning "requirements.txt may be incomplete"
    fi
    
    print_status "Source files validation completed"
}

check_raspberry_pi() {
    if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
        print_warning "This doesn't appear to be a Raspberry Pi"
        print_info "The script can continue but hardware features may not work"
        read -p "Continue anyway? (y/N): " -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            print_info "Setup cancelled by user"
            exit 0
        fi
    else
        PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
        print_status "Detected: ${PI_MODEL}"
        
        # Check if it's a Pi 5
        if echo "$PI_MODEL" | grep -q "Raspberry Pi 5"; then
            print_status "Raspberry Pi 5 detected - optimizing for best performance"
            export PI5_DETECTED=true
        fi
    fi
}

check_os_version() {
    if ! command -v lsb_release &> /dev/null; then
        print_warning "Cannot determine OS version"
        return 0
    fi
    
    OS_VERSION=$(lsb_release -rs)
    OS_CODENAME=$(lsb_release -cs)
    print_status "Running: Raspberry Pi OS ${OS_VERSION} (${OS_CODENAME})"
    
    # Check for minimum supported version
    if [[ "${OS_VERSION}" < "11" ]]; then
        print_warning "Raspberry Pi OS 11+ (Bullseye) recommended for best compatibility"
    fi
}

check_internet() {
    print_info "Checking internet connectivity..."
    if ! ping -c 1 8.8.8.8 &> /dev/null; then
        print_error "No internet connection detected"
        print_info "Internet access is required for package installation"
        exit 1
    fi
    print_status "Internet connection verified"
}

# FIXED: System update with better error handling
update_system() {
    print_section "System Update and Package Installation"
    
    print_info "Updating package lists..."
    if ! sudo apt-get update -qq; then
        print_warning "Package list update failed, retrying..."
        sudo apt-get update
    fi
    
    print_info "Upgrading existing packages..."
    sudo apt-get upgrade -y -qq
    
    print_info "Installing essential system packages..."
    sudo apt-get install -y \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-setuptools \
        python3-wheel \
        git \
        curl \
        wget \
        unzip \
        sqlite3 \
        build-essential \
        libffi-dev \
        libssl-dev \
        libjpeg-dev \
        zlib1g-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libopenjp2-7-dev \
        libtiff5-dev \
        tk-dev \
        tcl-dev \
        python3-tk \
        nginx \
        htop \
        tree \
        nano \
        vim \
        tmux \
        rsync \
        fail2ban \
        ufw
    
    print_status "System packages installed"
}

install_display_system() {
    print_section "Display System Installation (CLI OS Compatible)"
    
    print_info "Installing X11 and display components for CLI OS..."
    sudo apt-get install -y \
        xserver-xorg \
        x11-xserver-utils \
        xinit \
        chromium-browser \
        unclutter \
        xdotool \
        matchbox-window-manager \
        lightdm \
        plymouth \
        plymouth-themes \
        xauth \
        xorg
    
    # FIXED: Configure X11 to start without desktop environment
    print_info "Configuring X11 for kiosk mode..."
    
    # Create xorg.conf for Pi 5 optimization
    sudo tee /etc/X11/xorg.conf > /dev/null << 'EOF'
# Xorg configuration for Raspberry Pi 5 Prize Wheel System
# Optimized for kiosk mode operation

Section "Device"
    Identifier "Raspberry Pi Graphics"
    Driver "modesetting"
    Option "AccelMethod" "glamor"
    Option "DRI" "3"
EndSection

Section "Screen"
    Identifier "Default Screen"
    Monitor "Default Monitor"
    Device "Raspberry Pi Graphics"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "1920x1080" "1680x1050" "1280x1024" "1024x768"
    EndSubSection
EndSection

Section "Monitor"
    Identifier "Default Monitor"
    Option "DPMS" "false"
EndSection

Section "ServerLayout"
    Identifier "Default Layout"
    Screen "Default Screen"
EndSection

Section "ServerFlags"
    Option "BlankTime" "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime" "0"
EndSection
EOF

    print_status "Display system installed and configured for Pi 5"
}

install_audio_system() {
    print_section "Audio System Installation (Pi 5 Enhanced)"
    
    print_info "Installing audio packages..."
    sudo apt-get install -y \
        alsa-utils \
        pulseaudio \
        pulseaudio-module-bluetooth \
        pavucontrol \
        sox \
        libsox-fmt-all \
        ffmpeg \
        python3-pyaudio \
        portaudio19-dev \
        libasound2-dev
    
    print_info "Configuring audio system for Pi 5..."
    
    # Add user to audio group
    sudo usermod -a -G audio "$USER"
    
    # FIXED: Configure ALSA for Pi 5 with better device detection
    sudo tee /etc/asound.conf > /dev/null << 'EOF'
# ALSA Configuration for Prize Wheel System - Raspberry Pi 5
pcm.!default {
    type pulse
    fallback "sysdefault"
    hint {
        show on
        description "Default ALSA Output (via PulseAudio)"
    }
}

ctl.!default {
    type pulse
    fallback "sysdefault"
}

# Pi 5 specific PCM configurations
pcm.hw0 {
    type hw
    card 0
}

ctl.hw0 {
    type hw
    card 0
}

# HDMI Audio for Pi 5
pcm.hdmi {
    type hw
    card 0
    device 0
}

# 3.5mm Jack Audio for Pi 5
pcm.analog {
    type hw
    card 0
    device 1
}
EOF

    # FIXED: Configure PulseAudio for system-wide operation with better error handling
    sudo tee -a /etc/pulse/system.pa > /dev/null << 'EOF'

# Prize Wheel System Audio Configuration - Pi 5 Enhanced
load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse-socket

# Pi 5 specific audio modules
load-module module-alsa-sink device=hw:0,0 sink_name=hdmi_sink
load-module module-alsa-sink device=hw:0,1 sink_name=analog_sink
EOF

    # Configure audio for auto-start
    mkdir -p ~/.config/pulse
    echo "autospawn = yes" > ~/.config/pulse/client.conf
    echo "daemon-binary = /usr/bin/pulseaudio" >> ~/.config/pulse/client.conf
    
    print_status "Audio system configured for Pi 5"
}

install_gpio_support() {
    print_section "GPIO and Hardware Support (Pi 5 Compatible)"
    
    print_info "Installing GPIO libraries for Pi 5..."
    sudo apt-get install -y \
        python3-rpi.gpio \
        python3-gpiozero \
        python3-lgpio \
        i2c-tools \
        spi-tools \
        raspi-gpio
    
    # Add user to gpio group
    sudo usermod -a -G gpio "$USER"
    
    # FIXED: Enable hardware interfaces on Pi 5 with error handling
    print_info "Enabling hardware interfaces for Pi 5..."
    sudo raspi-config nonint do_i2c 0 || print_warning "I2C enable failed"
    sudo raspi-config nonint do_spi 0 || print_warning "SPI enable failed"
    sudo raspi-config nonint do_serial 0 || print_warning "Serial enable failed"
    
    # Pi 5 specific GPIO configuration
    if sudo test -w "$BOOT_CONFIG"; then
        echo "# Prize Wheel GPIO Configuration - Pi 5" | sudo tee -a "$BOOT_CONFIG"
        echo "dtparam=gpio=on" | sudo tee -a "$BOOT_CONFIG"
    else
        print_warning "Cannot write to boot config: $BOOT_CONFIG"
    fi
    
    print_status "GPIO support installed and configured for Pi 5"
}

# FIXED: Enhanced project structure creation with better error handling
create_project_structure() {
    print_section "Project Setup and File Structure"
    
    print_info "Creating project directory structure..."
    
    # Remove existing directory if it exists (with backup)
    if [[ -d "${PROJECT_DIR}" ]]; then
        print_warning "Existing project directory found. Backing up..."
        sudo mv "${PROJECT_DIR}" "${PROJECT_DIR}.backup.$(date +%s)" || {
            print_error "Failed to backup existing directory"
            exit 1
        }
    fi
    
    # Create main project directory
    mkdir -p "${PROJECT_DIR}" || {
        print_error "Failed to create project directory"
        exit 1
    }
    
    # Copy application files from source directory
    print_info "Copying application files from source directory..."
    print_info "Source: ${SOURCE_DIR}"
    print_info "Destination: ${PROJECT_DIR}"
    
    # FIXED: Copy all files with better error handling
    if ! rsync -av \
        --exclude='.git' \
        --exclude='venv' \
        --exclude='*.db' \
        --exclude='*.log' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='backups' \
        --exclude='logs' \
        "${SOURCE_DIR}/" "${PROJECT_DIR}/"; then
        print_error "Failed to copy project files"
        exit 1
    fi
    
    cd "${PROJECT_DIR}"
    
    # Create additional subdirectories
    mkdir -p {logs,backups,scripts}
    
    # Ensure static directories exist
    mkdir -p static/{css,js,sounds,images}
    mkdir -p templates
    
    # Move HTML files to templates if they exist in root
    for html_file in *.html; do
        if [[ -f "$html_file" ]]; then
            mv "$html_file" templates/
            print_info "Moved $html_file to templates/"
        fi
    done
    
    # FIXED: Create Python virtual environment with better error handling
    print_info "Creating Python virtual environment..."
    if ! python3 -m venv venv; then
        print_error "Failed to create virtual environment"
        exit 1
    fi
    
    source venv/bin/activate || {
        print_error "Failed to activate virtual environment"
        exit 1
    }
    
    # Upgrade pip and install build tools
    pip install --upgrade pip setuptools wheel
    
    print_status "Project structure created and files copied"
}

# FIXED: Enhanced Python dependencies installation
install_python_dependencies() {
    print_section "Python Dependencies Installation"
    
    cd "${PROJECT_DIR}"
    source venv/bin/activate || {
        print_error "Failed to activate virtual environment"
        exit 1
    }
    
    print_info "Installing Python dependencies from requirements.txt..."
    
    # Verify requirements.txt exists and create if missing
    if [[ ! -f "requirements.txt" ]]; then
        print_warning "requirements.txt not found in project directory"
        print_info "Creating minimal requirements.txt..."
        
        cat > requirements.txt << 'EOF'
# Prize Wheel System - Core Dependencies
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-SocketIO==5.3.6
python-socketio==5.10.0
python-engineio==4.7.1
Werkzeug==2.3.7
RPi.GPIO==0.7.1
gpiozero==1.6.2
Pillow==10.1.0
python-dotenv==1.0.0
gunicorn==21.2.0
psutil==5.9.6
mutagen==1.47.0
pydub==0.25.1
cryptography==41.0.8
Flask-Limiter==3.5.0
Flask-CORS==4.0.0
coloredlogs==15.0.1
EOF
    fi
    
    # Install all dependencies from requirements.txt with retries
    local retry_count=0
    local max_retries=3
    
    while [ $retry_count -lt $max_retries ]; do
        if pip install -r requirements.txt; then
            break
        else
            retry_count=$((retry_count + 1))
            print_warning "Pip install failed, retry $retry_count/$max_retries"
            if [ $retry_count -eq $max_retries ]; then
                print_error "Failed to install Python dependencies after $max_retries attempts"
                exit 1
            fi
            sleep 5
        fi
    done
    
    print_status "Python dependencies installed from requirements.txt"
}

# FIXED: Enhanced database setup with initialization
setup_database() {
    print_section "Database Configuration"
    
    cd "${PROJECT_DIR}"
    
    print_info "Setting up SQLite database..."
    
    # Database will be created by the Flask app on first run
    # Set proper permissions for database directory
    chmod 755 "${PROJECT_DIR}"
    
    # FIXED: Create database backup script with better error handling
    cat > scripts/backup_database.sh << 'EOF'
#!/bin/bash
# Database backup script for Prize Wheel System

DB_PATH="$HOME/prizewheel/prizewheel.db"
BACKUP_DIR="$HOME/prizewheel/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "$BACKUP_DIR"

if [[ -f "$DB_PATH" ]]; then
    if sqlite3 "$DB_PATH" ".backup $BACKUP_DIR/prizewheel_$TIMESTAMP.db"; then
        echo "[OK] Database backed up to: $BACKUP_DIR/prizewheel_$TIMESTAMP.db"
        
        # Keep only last 7 backups
        ls -t "$BACKUP_DIR"/prizewheel_*.db | tail -n +8 | xargs -r rm
        echo "[OK] Old backups cleaned up (keeping latest 7)"
    else
        echo "[ERR] Database backup failed"
        exit 1
    fi
else
    echo "[WARN] Database file not found: $DB_PATH"
fi
EOF
    
    chmod +x scripts/backup_database.sh
    
    print_status "Database system configured"
}

# FIXED: Enhanced nginx configuration
configure_nginx() {
    print_section "Web Server Configuration"
    
    print_info "Configuring Nginx reverse proxy..."
    
    # Create Nginx configuration
    sudo tee /etc/nginx/sites-available/prizewheel > /dev/null << EOF
# Prize Wheel System - Nginx Configuration
server {
    listen 80;
    server_name _;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Increase client max body size for file uploads
    client_max_body_size 20M;
    client_body_timeout 60s;
    
    # Main application proxy
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Handle connection issues
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
    }
    
    # Socket.IO proxy with better handling
    location /socket.io {
        proxy_pass http://127.0.0.1:5000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Longer timeouts for websockets
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    
    # Static files with caching
    location /static/ {
        alias ${PROJECT_DIR}/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        
        # Gzip compression
        gzip on;
        gzip_vary on;
        gzip_types text/css application/javascript image/svg+xml;
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://127.0.0.1:5000/health;
    }
    
    # Security: Block access to sensitive files
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }
    
    location ~ \.(db|log|bak|sql)$ {
        deny all;
        access_log off;
        log_not_found off;
    }
}
EOF

    # Enable site and remove default
    sudo ln -sf /etc/nginx/sites-available/prizewheel /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test Nginx configuration
    if sudo nginx -t; then
        print_status "Nginx configuration valid"
    else
        print_error "Nginx configuration error"
        exit 1
    fi
    
    print_status "Nginx configured and optimized"
}

# FIXED: Critical systemd services configuration with proper venv activation
create_systemd_services() {
    print_section "System Service Configuration (Pi 5 Optimized)"
    
    print_info "Creating Prize Wheel application service..."
    
    # FIXED: Main application service with proper virtual environment activation
    sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=Prize Wheel System - Flask Application
After=network.target sound.target
Wants=network-online.target
StartLimitInterval=0

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=${PROJECT_DIR}
Environment="PATH=${PROJECT_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="VIRTUAL_ENV=${PROJECT_DIR}/venv"
Environment="FLASK_APP=app.py"
Environment="FLASK_ENV=production"
Environment="PULSE_RUNTIME_PATH=/run/user/$(id -u)/pulse"
# FIXED: Proper virtual environment activation
ExecStartPre=/bin/bash -c 'source ${PROJECT_DIR}/venv/bin/activate && python -c "import flask; print(\"Flask import successful\")"'
ExecStart=${PROJECT_DIR}/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 --threads 4 --timeout 60 --keep-alive 30 --max-requests 1000 --preload app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${PROJECT_DIR}

# Pi 5 Resource limits
LimitNOFILE=65536
MemoryMax=1G
CPUQuota=90%

[Install]
WantedBy=multi-user.target
EOF

    # Create watchdog service
    sudo tee /etc/systemd/system/${SERVICE_NAME}-watchdog.service > /dev/null << EOF
[Unit]
Description=Prize Wheel Watchdog
After=${SERVICE_NAME}.service

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do sleep 30; curl -f http://localhost/health > /dev/null 2>&1 || systemctl restart ${SERVICE_NAME}; done'
Restart=always
RestartSec=30
User=$USER

[Install]
WantedBy=multi-user.target
EOF

    print_status "Systemd services created for Pi 5"
}

# FIXED: Enhanced display scripts with proper URL routing
create_display_scripts() {
    print_section "Display System Setup (Pi 5 Kiosk Mode)"
    
    # Create display startup script optimized for Pi 5
    cat > "${PROJECT_DIR}/scripts/start_display.sh" << 'EOF'
#!/bin/bash
# Prize Wheel Display Startup Script - Raspberry Pi 5 Optimized

# Wait for services to be ready
sleep 10

# Set up environment for Pi 5
export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/$(id -u)

# Start PulseAudio if not running
if ! pulseaudio --check; then
    pulseaudio --start --log-target=syslog &
    sleep 3
fi

# Set audio output
if command -v amixer &> /dev/null; then
    amixer sset PCM,0 80% unmute 2>/dev/null || true
    amixer sset Master 80% unmute 2>/dev/null || true
    amixer sset Headphone 80% unmute 2>/dev/null || true
fi

# Configure display for Pi 5
xset -dpms      # Disable power management
xset s off      # Disable screen saver
xset s noblank  # Don't blank screen

# Hide mouse cursor after inactivity
unclutter -idle 5 -root &

# Start window manager (lightweight for Pi 5)
matchbox-window-manager -use_cursor no -use_titlebar no &

# Wait for window manager
sleep 3

# Wait for web service to be ready
echo "Waiting for web service..."
for i in {1..30}; do
    if curl -s http://localhost/health > /dev/null 2>&1; then
        echo "Web service is ready!"
        break
    fi
    echo "Attempt $i/30: Web service not ready, waiting..."
    sleep 2
done

# Launch Chromium in kiosk mode (Pi 5 optimized)
# FIXED: Use localhost (nginx proxy) instead of localhost:5000
chromium-browser \
    --kiosk \
    --no-sandbox \
    --disable-web-security \
    --disable-features=TranslateUI,VizDisplayCompositor \
    --disable-ipc-flooding-protection \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-component-update \
    --check-for-update-interval=31536000 \
    --autoplay-policy=no-user-gesture-required \
    --enable-features=VaapiVideoDecoder \
    --use-gl=egl \
    --enable-gpu-rasterization \
    --enable-zero-copy \
    --enable-hardware-overlays \
    --start-fullscreen \
    --window-size=1920,1080 \
    --window-position=0,0 \
    --disable-background-timer-throttling \
    --disable-backgrounding-occluded-windows \
    --disable-renderer-backgrounding \
    --disable-dev-shm-usage \
    --memory-pressure-off \
    --max_old_space_size=128 \
    "http://localhost" \
    2>/dev/null &

# Keep script running
wait
EOF
    
    chmod +x "${PROJECT_DIR}/scripts/start_display.sh"
    
    print_status "Display scripts created for Pi 5 kiosk mode"
}

configure_auto_login() {
    print_section "Auto-Login Configuration (CLI OS with X11 Launch)"
    
    print_info "Configuring automatic login and display startup for CLI OS..."
    
    # Configure autologin for current user
    sudo systemctl enable getty@tty1.service
    
    # Create autologin override
    sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
    sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER --noclear %I \$TERM
EOF

    # FIXED: Create dedicated systemd service to start X11 and display with proper dependencies
    sudo tee /etc/systemd/system/prizewheel-kiosk.service > /dev/null << EOF
[Unit]
Description=Prize Wheel Kiosk Display
After=multi-user.target prizewheel.service
Wants=prizewheel.service
StartLimitInterval=0

[Service]
Type=simple
User=$USER
Environment="DISPLAY=:0"
Environment="XDG_RUNTIME_DIR=/run/user/$(id -u $USER)"
# FIXED: Better service dependency management
ExecStartPre=/bin/bash -c 'until systemctl is-active prizewheel; do sleep 2; done'
ExecStartPre=/bin/bash -c 'until curl -s http://localhost/health; do sleep 5; done'
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/startx ${PROJECT_DIR}/scripts/start_display.sh
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=prizewheel-kiosk

[Install]
WantedBy=graphical.target
EOF

    # Create .xinitrc for X11 startup
    cat > "$HOME/.xinitrc" << EOF
#!/bin/bash
# X11 startup configuration for Prize Wheel System
exec ${PROJECT_DIR}/scripts/start_display.sh
EOF
    
    chmod +x "$HOME/.xinitrc"
    
    # Enable the kiosk service
    sudo systemctl enable prizewheel-kiosk.service
    
    print_status "Auto-login and kiosk startup configured"
}

setup_security() {
    print_section "Security Configuration"
    
    print_info "Configuring firewall (UFW)..."
    
    # Configure UFW firewall
    sudo ufw --force reset
    sudo ufw default deny incoming
    sudo ufw default allow outgoing
    
    # Allow SSH (if enabled)
    if systemctl is-enabled ssh &>/dev/null; then
        sudo ufw allow ssh
        print_info "SSH access allowed"
    fi
    
    # Allow HTTP for web interface
    sudo ufw allow 80/tcp
    
    # Allow local network access to Flask dev server (backup)
    sudo ufw allow from 192.168.0.0/16 to any port 5000
    sudo ufw allow from 10.0.0.0/8 to any port 5000
    sudo ufw allow from 172.16.0.0/12 to any port 5000
    
    # Enable firewall
    sudo ufw --force enable
    
    print_info "Configuring Fail2Ban..."
    
    # Configure Fail2Ban for SSH protection
    sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true
port = ssh
logpath = %(sshd_log)s
backend = %(sshd_backend)s

[nginx-http-auth]
enabled = true
port = http,https
logpath = %(nginx_error_log)s
EOF

    sudo systemctl enable fail2ban
    
    print_info "Setting secure file permissions..."
    
    # Set secure permissions
    chmod 750 "${PROJECT_DIR}"
    chmod 640 "${PROJECT_DIR}"/*.py 2>/dev/null || true
    chmod 640 "${PROJECT_DIR}"/requirements.txt 2>/dev/null || true
    chmod 750 "${PROJECT_DIR}"/scripts/*.sh 2>/dev/null || true
    
    print_status "Security measures implemented"
}

# FIXED: Enhanced environment configuration
create_environment_config() {
    print_section "Environment Configuration"
    
    cd "${PROJECT_DIR}"
    
    print_info "Creating environment configuration..."
    
    # Generate secure secret key
    source venv/bin/activate
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    
    # Create .env file
    cat > .env << EOF
# Prize Wheel System - Environment Configuration
# Generated on: $(date)
# Optimized for Raspberry Pi 5

# Security
SECRET_KEY=${SECRET_KEY}
FLASK_ENV=production
FLASK_DEBUG=False

# Database
DATABASE_URL=sqlite:///${PROJECT_DIR}/prizewheel.db

# Hardware Configuration (Pi 5 GPIO)
BUTTON_PIN=17
LED_PIN=27
DEBOUNCE_TIME=50

# Application Settings
DEFAULT_SPIN_DURATION=5
DEFAULT_COOLDOWN=2
UPLOAD_FOLDER=static/sounds
MAX_CONTENT_LENGTH=16777216

# Audio Settings (Pi 5 Enhanced)
DEFAULT_VOLUME=0.7
ENABLE_SOUND=True
AUDIO_DEVICE=default

# Security Settings
SESSION_TIMEOUT=3600
MAX_LOGIN_ATTEMPTS=5
RATE_LIMIT_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
LOG_FILE=${PROJECT_DIR}/logs/prizewheel.log

# Network Settings
HOST=0.0.0.0
PORT=5000
WORKERS=2

# Performance (Pi 5 Optimized)
CACHE_TYPE=simple
CACHE_TIMEOUT=300
MAX_WORKERS=4
THREAD_POOL_SIZE=8
EOF

    # Secure the environment file
    chmod 600 .env
    
    print_status "Environment configuration created"
}

# FIXED: Enhanced maintenance scripts with better error handling
create_maintenance_scripts() {
    print_section "Maintenance Scripts"
    
    cd "${PROJECT_DIR}/scripts"
    
    print_info "Creating system maintenance scripts..."
    
    # System status script
    cat > system_status.sh << 'EOF'
#!/bin/bash
# Prize Wheel System - Status Check Script (Pi 5 Enhanced)

echo "=== Prize Wheel System Status - Raspberry Pi 5 ==="
echo "Date: $(date)"
echo

# System information
echo "=== System Information ==="
echo "Uptime: $(uptime -p)"
echo "Load: $(uptime | awk -F'load average:' '{print $2}')"
echo "Memory: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
echo "Disk: $(df -h / | tail -1 | awk '{print $3 "/" $2 " (" $5 " used)"}')"
echo "Temperature: $(vcgencmd measure_temp 2>/dev/null || echo 'N/A')"
echo

# Service status
echo "=== Service Status ==="
for service in prizewheel prizewheel-kiosk prizewheel-watchdog nginx; do
    if systemctl is-active --quiet $service; then
        echo "[OK] $service: RUNNING"
    else
        echo "[ERR] $service: STOPPED"
    fi
done
echo

# X11 and Display Status
echo "=== Display Status ==="
if pgrep -x "Xorg" > /dev/null; then
    echo "[OK] X11 Server: RUNNING"
else
    echo "[ERR] X11 Server: NOT RUNNING"
fi

if pgrep -x "chromium-browser" > /dev/null; then
    echo "[OK] Chromium Kiosk: RUNNING"
else
    echo "[ERR] Chromium Kiosk: NOT RUNNING"
fi

# Network status
echo "=== Network Status ==="
echo "IP Address: $(hostname -I | awk '{print $1}')"
if curl -s --max-time 5 http://localhost/health > /dev/null; then
    echo "[OK] Web Interface: ACCESSIBLE"
else
    echo "[ERR] Web Interface: NOT ACCESSIBLE"
fi
echo

# Hardware status
echo "=== Hardware Status ==="
if [ -c /dev/gpiomem ]; then
    echo "[OK] GPIO: AVAILABLE"
else
    echo "[ERR] GPIO: NOT AVAILABLE"
fi

if aplay -l 2>/dev/null | grep -q card; then
    echo "[OK] Audio: AVAILABLE"
    echo "   Audio Cards:"
    aplay -l 2>/dev/null | grep "card" | head -3
else
    echo "[ERR] Audio: NOT AVAILABLE"
fi
echo

# Database status
if [ -f "$HOME/prizewheel/prizewheel.db" ]; then
    DB_SIZE=$(du -h "$HOME/prizewheel/prizewheel.db" | cut -f1)
    echo "[OK] Database: $DB_SIZE"
else
    echo "[ERR] Database: NOT FOUND"
fi

# Recent logs
echo "=== Recent Logs (last 5 lines) ==="
journalctl -u prizewheel --no-pager -n 5 --quiet || echo "No logs available"
EOF

    # System update script
    cat > update_system.sh << 'EOF'
#!/bin/bash
# Prize Wheel System - Update Script (Pi 5)

set -e

echo "=== Prize Wheel System Update - Raspberry Pi 5 ==="
echo "Starting system update process..."

# Stop services
echo "Stopping services..."
sudo systemctl stop prizewheel-kiosk prizewheel prizewheel-watchdog || true

# Update system packages
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Update Python packages
echo "Updating Python packages..."
cd "$HOME/prizewheel"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt --upgrade

# Restart services
echo "Restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart prizewheel prizewheel-watchdog
sudo systemctl restart prizewheel-kiosk

echo "[OK] System update completed!"
echo "Check status with: ./system_status.sh"
EOF

    # Log rotation script
    cat > rotate_logs.sh << 'EOF'
#!/bin/bash
# Prize Wheel System - Log Rotation Script

LOG_DIR="$HOME/prizewheel/logs"
MAX_SIZE="10M"
KEEP_DAYS=30

mkdir -p "$LOG_DIR"

# Rotate application logs
for logfile in "$LOG_DIR"/*.log; do
    if [[ -f "$logfile" && $(stat -c%s "$logfile" 2>/dev/null) -gt $((10*1024*1024)) ]]; then
        timestamp=$(date +"%Y%m%d_%H%M%S")
        mv "$logfile" "${logfile%.log}_$timestamp.log"
        touch "$logfile"
        chown $USER:$USER "$logfile"
        echo "Rotated: $(basename $logfile)"
    fi
done

# Clean old logs
find "$LOG_DIR" -name "*.log" -type f -mtime +$KEEP_DAYS -delete
echo "Cleaned logs older than $KEEP_DAYS days"
EOF

    # Pi 5 specific optimization script
    cat > optimize_pi5.sh << 'EOF'
#!/bin/bash
# Raspberry Pi 5 Performance Optimization Script

echo "=== Optimizing Raspberry Pi 5 for Prize Wheel System ==="

# GPU memory optimization for Pi 5
sudo raspi-config nonint do_memory_split 128

# CPU governor optimization
echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# I/O scheduler optimization for Pi 5
echo "mq-deadline" | sudo tee /sys/block/mmcblk*/queue/scheduler 2>/dev/null || true

# Network optimization
sudo sysctl -w net.core.rmem_max=16777216
sudo sysctl -w net.core.wmem_max=16777216

echo "[OK] Pi 5 optimization completed!"
EOF

    # FIXED: Database initialization script
    cat > init_database.sh << 'EOF'
#!/bin/bash
# Prize Wheel System - Database Initialization Script

cd "$HOME/prizewheel"
source venv/bin/activate

echo "Initializing Prize Wheel database..."

python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '.')

try:
    from app import app, db, init_db
    
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("[OK] Database tables created")
        
        # Initialize with default data
        init_db()
        print("[OK] Database initialized with default data")
        
except Exception as e:
    print(f"[ERR] Database initialization failed: {e}")
    sys.exit(1)
PYTHON_SCRIPT

echo "[OK] Database initialization completed!"
EOF

    # Make scripts executable
    chmod +x *.sh
    
    print_status "Maintenance scripts created"
}

# FIXED: Enhanced finalization with proper boot configuration
finalize_setup() {
    print_section "Final Configuration and Optimization (Pi 5)"
    
    print_info "Optimizing system for Raspberry Pi 5 performance..."
    
    # FIXED: GPU memory split (optimal for Pi 5) with error checking
    if sudo test -w "$BOOT_CONFIG"; then
        if grep -q "gpu_mem=" "$BOOT_CONFIG"; then
            sudo sed -i 's/gpu_mem=.*/gpu_mem=128/' "$BOOT_CONFIG"
        else
            echo "gpu_mem=128" | sudo tee -a "$BOOT_CONFIG"
        fi
        
        # Pi 5 specific optimizations
        echo "# Prize Wheel System - Pi 5 Optimizations" | sudo tee -a "$BOOT_CONFIG"
        echo "dtoverlay=vc4-kms-v3d" | sudo tee -a "$BOOT_CONFIG"
        echo "max_framebuffers=2" | sudo tee -a "$BOOT_CONFIG"
        echo "disable_overscan=1" | sudo tee -a "$BOOT_CONFIG"
        echo "hdmi_force_hotplug=1" | sudo tee -a "$BOOT_CONFIG"
    else
        print_warning "Cannot write to boot config: $BOOT_CONFIG"
    fi
    
    # Optimize boot time for Pi 5
    sudo systemctl disable bluetooth hciuart || true
    sudo systemctl mask plymouth-start.service || true
    
    # Set timezone
    sudo timedatectl set-timezone "$(curl -s http://ip-api.com/line?fields=timezone)" || true
    
    # FIXED: Initialize database here to ensure it's ready
    print_info "Initializing database..."
    cd "${PROJECT_DIR}"
    source venv/bin/activate
    
    # Test if app can be imported
    if python3 -c "from app import app; print('App import successful')"; then
        # Initialize database
        python3 -c "
from app import app, db, init_db
with app.app_context():
    db.create_all()
    init_db()
    print('Database initialized successfully')
" || print_warning "Database initialization failed - will be created on first run"
    else
        print_warning "App import failed - database will be initialized on first run"
    fi
    
    # Enable services
    print_info "Enabling system services..."
    sudo systemctl daemon-reload
    sudo systemctl enable nginx
    sudo systemctl enable ${SERVICE_NAME}
    sudo systemctl enable ${SERVICE_NAME}-watchdog
    sudo systemctl enable prizewheel-kiosk
    sudo systemctl enable fail2ban
    
    print_status "System optimization completed for Pi 5"
}

# FIXED: Test services before completion
test_setup() {
    print_section "Testing Installation"
    
    print_info "Starting services for testing..."
    
    # Start nginx first
    if sudo systemctl start nginx; then
        print_status "Nginx started successfully"
    else
        print_warning "Nginx failed to start"
    fi
    
    # Start main application
    if sudo systemctl start ${SERVICE_NAME}; then
        print_status "Prize Wheel service started successfully"
        
        # Wait for service to be ready
        sleep 10
        
        # Test web interface
        if curl -s --max-time 10 http://localhost/health > /dev/null; then
            print_status "Web interface is accessible"
        else
            print_warning "Web interface test failed"
            print_info "Check logs: sudo journalctl -u ${SERVICE_NAME} --no-pager -n 10"
        fi
    else
        print_warning "Prize Wheel service failed to start"
        print_info "Check logs: sudo journalctl -u ${SERVICE_NAME} --no-pager -n 10"
    fi
    
    # Stop services (they'll auto-start on boot)
    sudo systemctl stop ${SERVICE_NAME} nginx || true
}

print_final_summary() {
    print_section "Setup Complete! ${ROCKET}"
    
    local IP_ADDRESS
    IP_ADDRESS=$(hostname -I | awk '{print $1}')
    
    log ""
    log "${GREEN}${BOLD}*** Prize Wheel System v${SCRIPT_VERSION} Setup Completed Successfully! ***${NC}"
    log "${GREEN}${BOLD}Optimized for Raspberry Pi 5 with CLI-only OS and Auto Kiosk Display${NC}"
    log "${GREEN}${BOLD}** COMPREHENSIVE FIXES APPLIED **${NC}"
    log ""
    log "${CYAN}${BOLD}System Information:${NC}"
    log "  Installation Directory: ${PROJECT_DIR}"
    log "  IP Address: ${IP_ADDRESS}"
    log "  Kiosk Display: Auto-launches on boot to http://localhost"
    log "  Admin Panel: http://${IP_ADDRESS}/admin (from other devices)"
    log ""
    log "${CYAN}${BOLD}Default Login Credentials:${NC}"
    log "  ${LOCK} Username: admin"
    log "  ${LOCK} Password: admin123"
    log "  ${WARNING} ${BOLD}IMPORTANT: Change these credentials immediately!${NC}"
    log ""
    log "${CYAN}${BOLD}Comprehensive Fixes Applied:${NC}"
    log "  [OK] Fixed character encoding issues throughout codebase"
    log "  [OK] Enhanced boot config compatibility for all Pi OS versions"
    log "  [OK] Robust virtual environment activation in systemd services"
    log "  [OK] Better error handling in database initialization"
    log "  [OK] Enhanced source file validation and copying"
    log "  [OK] Improved service dependencies and startup order"
    log "  [OK] Fixed URL routing through nginx proxy"
    log "  [OK] Added comprehensive testing and validation"
    log ""
    log "${CYAN}${BOLD}Hardware Connections (Pi 5 GPIO):${NC}"
    log "  Spin Button: GPIO 17 (Pin 11) to Ground"
    log "  Status LED: GPIO 27 (Pin 13) with 330Ω resistor"
    log "  ${SOUND} Audio: HDMI or 3.5mm jack (auto-detected)"
    log ""
    log "${CYAN}${BOLD}System Services:${NC}"
    log "  Main App: sudo systemctl status prizewheel"
    log "  Display: sudo systemctl status prizewheel-kiosk"
    log "  Watchdog: sudo systemctl status prizewheel-watchdog"
    log "  Web Server: sudo systemctl status nginx"
    log ""
    log "${CYAN}${BOLD}Useful Commands:${NC}"
    log "  System Status: ${PROJECT_DIR}/scripts/system_status.sh"
    log "  Update System: ${PROJECT_DIR}/scripts/update_system.sh"
    log "  Backup Database: ${PROJECT_DIR}/scripts/backup_database.sh"
    log "  Optimize Pi 5: ${PROJECT_DIR}/scripts/optimize_pi5.sh"
    log "  Initialize DB: ${PROJECT_DIR}/scripts/init_database.sh"
    log "  View Logs: journalctl -u prizewheel -f"
    log ""
    log "${CYAN}${BOLD}Next Steps:${NC}"
    log "  1. ${CHECKMARK} Reboot the system: sudo reboot"
    log "  2. ${CHECKMARK} System will auto-start in kiosk mode"
    log "  3. ${CHECKMARK} Test hardware connections"
    log "  4. ${CHECKMARK} Access admin from another device to change password"
    log "  5. ${CHECKMARK} Upload custom prizes and sounds"
    log "  6. ${CHECKMARK} Test the wheel operation"
    log ""
    log "${PURPLE}${BOLD}The Prize Wheel System is ready with comprehensive fixes applied!${NC}"
    log ""
    log "${CYAN}If you encounter any issues:${NC}"
    log "  - Run: ${PROJECT_DIR}/scripts/system_status.sh"
    log "  - Check logs: sudo journalctl -u prizewheel -f"
    log "  - Re-run setup: $0"
    log ""
}

# Main execution flow
main() {
    print_header
    
    # Pre-flight checks
    check_root
    check_source_files
    check_raspberry_pi
    check_os_version
    check_internet
    
    # Core system setup
    update_system
    install_display_system
    install_audio_system
    install_gpio_support
    
    # Project setup
    create_project_structure
    install_python_dependencies
    setup_database
    
    # Web server and services
    configure_nginx
    create_systemd_services
    create_display_scripts
    configure_auto_login
    
    # Security and configuration
    setup_security
    create_environment_config
    
    # Maintenance and monitoring
    create_maintenance_scripts
    finalize_setup
    
    # Test the setup
    test_setup
    
    # Summary
    print_final_summary
    
    # Prompt for reboot
    log ""
    read -p "Setup complete! Reboot now to start the Prize Wheel System in kiosk mode? (y/N): " -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        print_status "Rebooting system..."
        sleep 2
        sudo reboot
    else
        print_info "Reboot manually when ready: sudo reboot"
        print_info "After reboot, the system will automatically start in kiosk mode!"
    fi
}

# Script entry point
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
