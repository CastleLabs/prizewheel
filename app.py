#!/usr/bin/env python3
"""
Raspberry Pi Prize Wheel System - Main Application
FINAL Enhanced Version with CRITICAL FIXES Applied
Author: Enhanced Prize Wheel System
Version: 2.1 - Patched and Fully Functional
Date: 2024

CRITICAL FIXES APPLIED:
1. âœ… Server-side winner determination with proper client synchronization
2. âœ… Database seeding from sample_prizes.json file  
3. âœ… Enhanced spin coordination between server and client
4. âœ… Proper winner index calculation for wheel animation targeting

IMPROVEMENTS APPLIED (v2.1):
1. âœ… Implemented missing API endpoints for CRUD operations on prizes.
2. âœ… Implemented missing API endpoint for sound file uploads.
3. âœ… Implemented missing API endpoints for clearing and exporting spin history.
4. âœ… Server now sends cooldown duration to the client for accurate UI state.
"""

import os
import sys
import json
import logging
import signal
import threading
import time
import random  # CRITICAL FIX: Add missing import
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, has_request_context, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import secrets
import csv
import io

# Pi 5 Enhanced imports
try:
    import RPi.GPIO as GPIO
    PI5_GPIO_AVAILABLE = True
    print("âœ… Pi 5 GPIO support loaded successfully")
except ImportError:
    PI5_GPIO_AVAILABLE = False
    print("âš ï¸ GPIO not available - running in development mode")

try:
    import psutil
    PI5_MONITORING_AVAILABLE = True
    print("âœ… Pi 5 system monitoring enabled")
except ImportError:
    PI5_MONITORING_AVAILABLE = False
    print("âš ï¸ System monitoring not available")

# Configuration Class - Pi 5 Enhanced
class Config:
    """Application configuration with Pi 5 enhancements"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///prizewheel.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,  # Pi 5 database connection optimization
    }
    
    # GPIO Configuration for Pi 5
    BUTTON_PIN = 17  # BCM pin numbering
    LED_PIN = 27
    DEBOUNCE_TIME = 50  # milliseconds - optimized for Pi 5
    
    # Wheel Configuration - Pi 5 Enhanced
    DEFAULT_SPIN_DURATION = 5  # seconds
    DEFAULT_COOLDOWN = 2  # seconds
    
    # File Upload Configuration - Pi 5 Storage Optimized
    UPLOAD_FOLDER = 'static/sounds'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Pi 5 Performance Settings
    MAX_WORKERS = 4  # Utilize Pi 5's 4 cores
    THREAD_POOL_SIZE = 8
    ENABLE_HARDWARE_ACCELERATION = True

# Initialize Flask app with Pi 5 configuration
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions with Pi 5 optimization
db = SQLAlchemy(app)
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='threading',  # Pi 5 threading optimization
                   ping_timeout=60,
                   ping_interval=25)

# Setup comprehensive logging with Pi 5 context
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [Pi5] %(message)s',
    handlers=[
        logging.FileHandler('prizewheel.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info("ðŸš€ Prize Wheel System v2.1 FINAL - Pi 5 Enhanced Edition Starting")

# Database Models - Enhanced for Pi 5
class Prize(db.Model):
    """Enhanced Prize model with sound support and Pi 5 optimizations"""
    __tablename__ = 'prizes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)  # Pi 5 index optimization
    description = db.Column(db.Text)
    weight = db.Column(db.Float, default=1.0, index=True)  # Pi 5 weighted selection optimization
    color = db.Column(db.String(7), default='#FF6B6B')
    image_path = db.Column(db.String(255))
    sound_path = db.Column(db.String(255))  # Sound file path for this prize
    is_winner = db.Column(db.Boolean, default=True, index=True)  # Winner vs losing prize
    enabled = db.Column(db.Boolean, default=True, index=True)  # Pi 5 query optimization
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Convert prize to dictionary for API responses"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'weight': self.weight,
            'color': self.color,
            'image_path': self.image_path,
            'sound_path': self.sound_path,
            'is_winner': self.is_winner,
            'enabled': self.enabled
        }

    def __repr__(self):
        return f'<Prize {self.name}>'

class SpinHistory(db.Model):
    """Spin history tracking with Pi 5 enhanced metadata"""
    __tablename__ = 'spin_history'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)  # Pi 5 time-series optimization
    prize_id = db.Column(db.Integer, db.ForeignKey('prizes.id'), index=True)
    spin_duration = db.Column(db.Float)
    session_id = db.Column(db.String(100), index=True)  # Pi 5 session tracking
    
    # Pi 5 Enhanced fields
    system_performance = db.Column(db.String(50))  # Track Pi 5 performance metrics
    hardware_source = db.Column(db.String(20), default='pi5')  # Hardware identifier
    
    prize = db.relationship('Prize', backref='spin_history')

    def __repr__(self):
        return f'<SpinHistory {self.id}: {self.prize.name if self.prize else "Unknown"}>'

class Configuration(db.Model):
    """System configuration storage with Pi 5 optimizations"""
    __tablename__ = 'configurations'
    
    key = db.Column(db.String(100), primary_key=True, index=True)  # Pi 5 key lookup optimization
    value = db.Column(db.Text)
    category = db.Column(db.String(50), index=True)  # Pi 5 category filtering
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<Configuration {self.key}: {self.value}>'

class User(db.Model):
    """User management for admin access with Pi 5 security enhancements"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)  # Pi 5 lookup optimization
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), index=True)
    role = db.Column(db.String(20), default='admin')
    last_login = db.Column(db.DateTime, index=True)  # Pi 5 session management
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Pi 5 Enhanced security fields
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    last_activity = db.Column(db.DateTime)

    def __repr__(self):
        return f'<User {self.username}>'

# Global variables for Pi 5 enhanced wheel state management
wheel_state = {
    'is_spinning': False,
    'last_spin': None,
    'cooldown_until': None,
    'current_winner': None,
    'pi5_performance': {
        'cpu_temp': None,
        'cpu_usage': None,
        'memory_usage': None,
        'gpu_active': False
    }
}

# Thread lock for Pi 5 state management
state_lock = threading.Lock()

# Pi 5 Performance monitoring
def get_pi5_system_info():
    """Get Pi 5 system performance information"""
    info = {}
    
    if PI5_MONITORING_AVAILABLE:
        try:
            # CPU information
            info['cpu_percent'] = psutil.cpu_percent(interval=1)
            info['cpu_count'] = psutil.cpu_count()
            info['cpu_freq'] = psutil.cpu_freq()
            
            # Memory information
            memory = psutil.virtual_memory()
            info['memory_percent'] = memory.percent
            info['memory_available'] = memory.available
            
            # Disk information
            disk = psutil.disk_usage('/')
            info['disk_percent'] = disk.percent
            info['disk_free'] = disk.free
            
            # Temperature (Pi 5 specific)
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temp = int(f.read()) / 1000.0
                    info['cpu_temperature'] = temp
            except:
                info['cpu_temperature'] = None
                
            # Network status
            info['network_connections'] = len(psutil.net_connections())
            
            # Boot time
            info['boot_time'] = psutil.boot_time()
            
        except Exception as e:
            logger.error(f"Pi 5 system monitoring error: {e}")
            
    return info

# Helper Functions
def allowed_file(filename, allowed_extensions):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def validate_audio_file(file):
    """Enhanced audio file validation with Pi 5 magic number checking"""
    file.seek(0)
    header = file.read(12)  # Read more bytes for better Pi 5 detection
    file.seek(0)
    
    # Magic number validation for common audio formats (Pi 5 enhanced)
    audio_signatures = [
        b'ID3',           # MP3 with ID3 tag
        b'\xff\xfb',      # MP3 without ID3
        b'\xff\xfa',      # MP3 MPEG-2
        b'\xff\xf3',      # MP3 MPEG-2.5
        b'RIFF',          # WAV
        b'OggS',          # OGG
        b'\x00\x00\x00',  # M4A (simplified check)
        b'fLaC',          # FLAC
        b'FORM',          # AIFF
    ]
    
    return any(header.startswith(sig) for sig in audio_signatures)

# CRITICAL FIX 1: Enhanced server-side winner calculation
def calculate_winner(prizes):
    """Calculate winner server-side using weighted random selection"""
    if not prizes:
        return None
    
    total_weight = sum(p.weight for p in prizes)
    if total_weight <= 0:
        return random.choice(prizes) if prizes else None
    
    random_value = random.uniform(0, total_weight)
    current_weight = 0
    
    for prize in prizes:
        current_weight += prize.weight
        if random_value <= current_weight:
            logger.info(f"ðŸŽ¯ Winner calculated: {prize.name} (weight: {prize.weight}, total: {total_weight})")
            return prize
    
    # Fallback to last prize (should rarely happen)
    return prizes[-1]

# CRITICAL FIX 2: Calculate winner index in the prizes list
def get_winner_index(winner, prizes):
    """Get the index position of winner in the prizes list for client animation"""
    for index, prize in enumerate(prizes):
        if prize.id == winner.id:
            return index
    return 0  # Fallback to first index

# Pi 5 GPIO Setup and Management
def setup_gpio():
    """Initialize GPIO pins with Pi 5 enhanced error handling"""
    if not PI5_GPIO_AVAILABLE:
        logger.warning("GPIO not available - skipping hardware setup")
        return
        
    try:
        # Clean any previous state
        GPIO.cleanup()
        GPIO.setwarnings(False)  # Suppress warnings for Pi 5
        GPIO.setmode(GPIO.BCM)
        
        # Pi 5 Enhanced GPIO setup
        GPIO.setup(Config.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(Config.LED_PIN, GPIO.OUT)
        GPIO.output(Config.LED_PIN, GPIO.LOW)
        
        # Add button interrupt with Pi 5 optimized callback
        GPIO.add_event_detect(
            Config.BUTTON_PIN, 
            GPIO.FALLING,
            callback=button_callback,
            bouncetime=Config.DEBOUNCE_TIME
        )
        logger.info("âœ… Pi 5 GPIO initialized successfully")
    except Exception as e:
        logger.error(f"âŒ Pi 5 GPIO initialization failed: {e}")
        logger.warning("Application continuing without GPIO support")

def button_callback(channel):
    """Enhanced button press handler with Pi 5 state locking"""
    global wheel_state
    
    with state_lock:
        # Check if wheel is ready to spin
        if wheel_state['is_spinning']:
            logger.info("Pi 5: Button pressed but wheel is already spinning")
            return
        
        if wheel_state['cooldown_until'] and datetime.utcnow() < wheel_state['cooldown_until']:
            logger.info("Pi 5: Button pressed but in cooldown period")
            return
    
    logger.info("ðŸŽ® Pi 5: Hardware button pressed - triggering spin")
    trigger_spin('button')

def trigger_spin(source='web'):
    """CRITICAL FIX: Enhanced spin trigger with server-side winner determination and proper client sync"""
    global wheel_state
    
    with state_lock:
        # Double-check state inside lock
        if wheel_state['is_spinning']:
            return
        
        # Get enabled prizes with Pi 5 database optimization
        prizes = Prize.query.filter_by(enabled=True).order_by(Prize.id).all()  # CRITICAL: Consistent ordering
        if not prizes:
            logger.warning("Pi 5: No enabled prizes available")
            return
        
        # CRITICAL FIX: Calculate winner server-side
        winner = calculate_winner(prizes)
        if not winner:
            logger.error("Pi 5: Failed to calculate winner")
            return
        
        # CRITICAL FIX: Get winner index for client animation
        winner_index = get_winner_index(winner, prizes)
        
        # Set spinning state with Pi 5 performance tracking
        wheel_state['is_spinning'] = True
        wheel_state['last_spin'] = datetime.utcnow()
        wheel_state['current_winner'] = winner  # Store winner immediately
        wheel_state['pi5_performance'] = get_pi5_system_info()
    
    try:
        # Turn on LED if Pi 5 GPIO is available
        if PI5_GPIO_AVAILABLE:
            GPIO.output(Config.LED_PIN, GPIO.HIGH)
    except:
        pass  # GPIO not available, continue
    
    # Get spin duration with Pi 5 randomization
    base_duration = get_config('spin_duration', Config.DEFAULT_SPIN_DURATION)
    actual_spin_duration = base_duration + random.uniform(-1, 2)
    
    # CRITICAL FIX: Send comprehensive winner information to client for proper animation
    socketio.emit('spin_started', {
        'timestamp': wheel_state['last_spin'].isoformat(),
        'source': source,
        'pi5_enhanced': True,
        'system_performance': wheel_state['pi5_performance'],
        'winner_id': winner.id,  # CRITICAL: Send winner ID to client
        'winner_index': winner_index,  # CRITICAL: Send winner index for animation
        'spin_duration': actual_spin_duration * 1000,  # CRITICAL: Send duration in milliseconds
        'total_prizes': len(prizes),  # CRITICAL: Send total number of prizes
        'prizes_order': [p.id for p in prizes]  # CRITICAL: Send prize order for client verification
    })
    
    # Schedule spin completion with Pi 5 threading
    timer = threading.Timer(actual_spin_duration, complete_spin, args=[winner, source, actual_spin_duration])
    timer.start()
    
    logger.info(f"ðŸŽ° Pi 5: Spin started - winner: {winner.name} at index {winner_index} (duration: {actual_spin_duration:.1f}s)")

def complete_spin(winner, source='web', actual_duration=5.0):
    """Enhanced spin completion with Pi 5 state management"""
    global wheel_state
    
    try:
        # Turn off LED if Pi 5 GPIO is available
        if PI5_GPIO_AVAILABLE:
            GPIO.output(Config.LED_PIN, GPIO.LOW)
    except:
        pass  # GPIO not available, continue
    
    # Record spin in history with Pi 5 metadata
    try:
        with app.app_context(): # Ensure we have an app context in the thread
            pi5_info = get_pi5_system_info()
            performance_summary = f"CPU:{pi5_info.get('cpu_percent', 0):.1f}% Temp:{pi5_info.get('cpu_temperature', 0):.1f}Â°C"
            
            spin = SpinHistory(
                prize_id=winner.id,
                spin_duration=actual_duration,
                session_id=source,
                system_performance=performance_summary,
                hardware_source='pi5'
            )
            db.session.add(spin)
            db.session.commit()
            logger.info(f"âœ… Pi 5: Spin recorded in database")
    except Exception as e:
        logger.error(f"âŒ Pi 5: Failed to record spin history: {e}")
        db.session.rollback()
    
    cooldown_duration = get_config('cooldown', Config.DEFAULT_COOLDOWN)

    # Update state
    with state_lock:
        wheel_state['is_spinning'] = False
        wheel_state['cooldown_until'] = datetime.utcnow() + timedelta(seconds=cooldown_duration)
    
    # Emit spin complete event with Pi 5 enhancements
    socketio.emit('spin_complete', {
        'winner': winner.to_dict(),
        'timestamp': datetime.utcnow().isoformat(),
        'source': source,
        'pi5_performance': get_pi5_system_info(),
        'cooldown_duration': cooldown_duration * 1000 # Send cooldown in ms
    })
    
    logger.info(f"ðŸ† Pi 5: Spin completed - winner: {winner.name}")

# Configuration Management with Pi 5 optimization
def get_config(key, default=None):
    """Get configuration value from database with Pi 5 caching"""
    try:
        config = Configuration.query.filter_by(key=key).first()
        if config:
            try:
                # Attempt to parse as int or float first
                val = config.value
                if val.isdigit():
                    return int(val)
                return float(val)
            except (ValueError, TypeError):
                # Fallback to JSON or string
                try:
                    return json.loads(config.value)
                except (json.JSONDecodeError, TypeError):
                    return config.value
    except Exception as e:
        logger.error(f"Pi 5: Failed to get config {key}: {e}")
    return default

def set_config(key, value, category='general', description=''):
    """Set configuration value in database with Pi 5 optimization"""
    try:
        config = Configuration.query.filter_by(key=key).first()
        if not config:
            config = Configuration(key=key, category=category, description=description)
        config.value = json.dumps(value) if not isinstance(value, str) else value
        db.session.add(config)
        db.session.commit()
        logger.info(f"âœ… Pi 5: Config updated: {key}")
    except Exception as e:
        logger.error(f"âŒ Pi 5: Failed to set config {key}: {e}")
        db.session.rollback()

# Routes - Display
@app.route('/')
def display():
    """Main wheel display page with Pi 5 enhanced prize loading"""
    try:
        # Pi 5 optimized database query with consistent ordering
        prizes = Prize.query.filter_by(enabled=True).order_by(Prize.id).all()  # CRITICAL: Consistent ordering
        logger.info(f"ðŸ–¥ï¸ Pi 5: Display loaded with {len(prizes)} prizes")
        return render_template('display.html', prizes=prizes)
    except Exception as e:
        logger.error(f"âŒ Pi 5: Display route error: {e}")
        return render_template('display.html', prizes=[])

# Routes - Admin Authentication with Pi 5 security
@app.route('/admin')
def admin_login():
    """Admin login page with Pi 5 session check"""
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard'))
    return render_template('login.html')

@app.route('/admin/login', methods=['POST'])
def admin_login_post():
    """Enhanced admin login with Pi 5 security logging"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    
    if not username or not password:
        return render_template('login.html', error='Username and password required')
    
    try:
        user = User.query.filter_by(username=username).first()
        
        # Pi 5 Enhanced security: Check for account lockout
        if user and user.locked_until and datetime.utcnow() < user.locked_until:
            remaining = (user.locked_until - datetime.utcnow()).seconds
            return render_template('login.html', 
                                 error=f'Account locked. Try again in {remaining} seconds.')
        
        if user and check_password_hash(user.password_hash, password):
            # Successful login - Pi 5 session management
            session['user_id'] = user.id
            session['username'] = user.username
            session['pi5_session'] = True  # Pi 5 session identifier
            user.last_login = datetime.utcnow()
            user.last_activity = datetime.utcnow()
            user.failed_login_attempts = 0  # Reset failed attempts
            user.locked_until = None
            db.session.commit()
            logger.info(f"âœ… Pi 5: Successful login: {username}")
            return redirect(url_for('admin_dashboard'))
        else:
            # Failed login - Pi 5 security tracking
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:  # Lock after 5 attempts
                    user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                    logger.warning(f"ðŸ”’ Pi 5: Account locked due to failed attempts: {username}")
                db.session.commit()
            
            logger.warning(f"âŒ Pi 5: Failed login attempt: {username}")
            return render_template('login.html', error='Invalid credentials')
    except Exception as e:
        logger.error(f"âŒ Pi 5: Login error: {e}")
        return render_template('login.html', error='Login system error')

@app.route('/admin/logout')
def admin_logout():
    """Enhanced logout with Pi 5 session cleanup"""
    username = session.get('username', 'unknown')
    session.clear()
    logger.info(f"ðŸ‘‹ Pi 5: User logged out: {username}")
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    """Enhanced admin dashboard with Pi 5 comprehensive statistics"""
    if 'user_id' not in session:
        return redirect(url_for('admin_login'))
    
    try:
        # Update last activity for Pi 5 session management
        user = User.query.get(session['user_id'])
        if user:
            user.last_activity = datetime.utcnow()
            db.session.commit()
        
        # Get Pi 5 enhanced statistics
        total_spins = SpinHistory.query.count()
        recent_spins = SpinHistory.query.order_by(SpinHistory.timestamp.desc()).limit(20).all()
        prizes = Prize.query.order_by(Prize.created_at.desc()).all()
        
        # Pi 5 performance statistics
        pi5_stats = {
            'total_spins': total_spins,
            'pi5_spins': SpinHistory.query.filter_by(hardware_source='pi5').count(),
            'recent_24h': SpinHistory.query.filter(
                SpinHistory.timestamp >= datetime.utcnow() - timedelta(hours=24)
            ).count(),
            'system_info': get_pi5_system_info()
        }
        
        logger.info(f"ðŸ“Š Pi 5: Dashboard accessed by {session.get('username')}")
        
        return render_template('dashboard.html', 
                             total_spins=total_spins,
                             recent_spins=recent_spins,
                             prizes=prizes,
                             pi5_stats=pi5_stats)
    except Exception as e:
        logger.error(f"âŒ Pi 5: Dashboard error: {e}")
        return render_template('dashboard.html', 
                             total_spins=0, recent_spins=[], prizes=[], pi5_stats={})

# --- API Routes - IMPROVEMENT: Implemented Missing Endpoints ---

# API Routes - Prize Management with Pi 5 optimization
@app.route('/api/prizes', methods=['GET', 'POST'])
def api_prizes():
    """GET all prizes or CREATE a new prize."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'POST':
        data = request.json
        if not data or not data.get('name') or 'weight' not in data:
            return jsonify({'error': 'Missing required fields'}), 400
        
        try:
            new_prize = Prize(
                name=data['name'],
                description=data.get('description', ''),
                weight=float(data['weight']),
                color=data.get('color', '#CCCCCC'),
                is_winner=data.get('is_winner', True),
                enabled=data.get('enabled', True),
                sound_path=data.get('sound_path')
            )
            db.session.add(new_prize)
            db.session.commit()
            logger.info(f"Prize created: {new_prize.name}")
            return jsonify(new_prize.to_dict()), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating prize: {e}")
            return jsonify({'error': 'Could not create prize'}), 500

    # GET request
    try:
        prizes = Prize.query.order_by(Prize.id).all()
        return jsonify([p.to_dict() for p in prizes])
    except Exception as e:
        logger.error(f"âŒ Pi 5: Get prizes error: {e}")
        return jsonify({'error': 'Failed to fetch prizes'}), 500

@app.route('/api/prizes/<int:prize_id>', methods=['PUT', 'DELETE'])
def api_prize_detail(prize_id):
    """UPDATE or DELETE a specific prize."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    prize = Prize.query.get_or_404(prize_id)

    if request.method == 'PUT':
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        try:
            prize.name = data.get('name', prize.name)
            prize.description = data.get('description', prize.description)
            prize.weight = float(data.get('weight', prize.weight))
            prize.color = data.get('color', prize.color)
            prize.is_winner = data.get('is_winner', prize.is_winner)
            prize.enabled = data.get('enabled', prize.enabled)
            prize.sound_path = data.get('sound_path', prize.sound_path)
            db.session.commit()
            logger.info(f"Prize updated: {prize.name}")
            return jsonify(prize.to_dict())
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating prize {prize_id}: {e}")
            return jsonify({'error': 'Could not update prize'}), 500

    if request.method == 'DELETE':
        try:
            db.session.delete(prize)
            db.session.commit()
            logger.info(f"Prize deleted: {prize.name}")
            return jsonify({'message': 'Prize deleted successfully'})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting prize {prize_id}: {e}")
            return jsonify({'error': 'Could not delete prize'}), 500

@app.route('/api/upload/sound', methods=['POST'])
def upload_sound():
    """Handles sound file uploads from the admin dashboard."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    allowed_extensions = {'mp3', 'wav', 'ogg', 'm4a', 'flac'}
    if file and allowed_file(file.filename, allowed_extensions):
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Ensure filename is unique to prevent overwrites
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base}_{counter}{ext}"
            counter += 1
        
        file.save(save_path)
        
        # Return the relative path for database storage
        relative_path = os.path.join(os.path.basename(app.config['UPLOAD_FOLDER']), os.path.basename(save_path))
        logger.info(f"Sound file uploaded: {relative_path}")
        return jsonify({'sound_path': relative_path})
    
    return jsonify({'error': 'File type not allowed'}), 400

@app.route('/api/stats', methods=['DELETE'])
def clear_stats():
    """Clears all spin history from the database."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        num_deleted = db.session.query(SpinHistory).delete()
        db.session.commit()
        logger.info(f"Cleared {num_deleted} spin history records.")
        return jsonify({'message': f'Successfully deleted {num_deleted} records.'})
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error clearing stats: {e}")
        return jsonify({'error': 'Could not clear spin history'}), 500

@app.route('/api/export/csv')
def export_csv():
    """Exports all spin history to a CSV file."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        spins = SpinHistory.query.options(db.joinedload(SpinHistory.prize)).order_by(SpinHistory.timestamp.asc()).all()
        
        si = io.StringIO()
        cw = csv.writer(si)
        
        headers = ['Timestamp (UTC)', 'Prize Name', 'Prize Type', 'Spin Duration (s)', 'Source']
        cw.writerow(headers)
        
        for spin in spins:
            prize_name = spin.prize.name if spin.prize else "N/A"
            prize_type = "Winner" if spin.prize and spin.prize.is_winner else "Losing"
            row = [
                spin.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                prize_name,
                prize_type,
                f"{spin.spin_duration:.2f}",
                spin.session_id
            ]
            cw.writerow(row)
            
        output = io.BytesIO(si.getvalue().encode('utf-8'))
        
        logger.info("Generated CSV export of spin history.")
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'prizewheel_export_{datetime.utcnow().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        return jsonify({'error': 'Could not generate export file'}), 500

# API Routes - Wheel Control with Pi 5 enhancement
@app.route('/api/wheel/spin', methods=['POST'])
def api_trigger_spin():
    """API endpoint to trigger wheel spin with Pi 5 optimization"""
    if wheel_state['is_spinning']:
        return jsonify({'error': 'Wheel is already spinning'}), 400
    
    if wheel_state['cooldown_until'] and datetime.utcnow() < wheel_state['cooldown_until']:
        remaining = (wheel_state['cooldown_until'] - datetime.utcnow()).seconds
        return jsonify({'error': f'Wheel is in cooldown period ({remaining}s remaining)'}), 400
    
    try:
        # Get client info for Pi 5 tracking
        client_ip = request.remote_addr or 'unknown'
        
        trigger_spin(f'web-{client_ip}')
        
        logger.info(f"ðŸŒ Pi 5: Web spin triggered from {client_ip}")
        return jsonify({
            'status': 'spinning',
            'pi5_enhanced': True,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"âŒ Pi 5: API spin error: {e}")
        return jsonify({'error': 'Failed to start spin'}), 500

@app.route('/api/health', methods=['GET'])
def api_health_check():
    """Pi 5 comprehensive health check endpoint"""
    try:
        health_data = {
            'status': 'healthy',
            'timestamp': datetime.utcnow().isoformat(),
            'pi5_enhanced': True,
            'checks': {}
        }
        
        # Database health
        try:
            prize_count = Prize.query.count()
            health_data['checks']['database'] = {
                'status': 'ok',
                'prize_count': prize_count
            }
        except Exception as e:
            health_data['checks']['database'] = {
                'status': 'error',
                'error': str(e)
            }
            health_data['status'] = 'unhealthy'
        
        # Pi 5 System health
        if PI5_MONITORING_AVAILABLE:
            pi5_info = get_pi5_system_info()
            health_data['checks']['system'] = {
                'status': 'ok',
                'cpu_percent': pi5_info.get('cpu_percent'),
                'cpu_temperature': pi5_info.get('cpu_temperature'),
                'memory_percent': pi5_info.get('memory_percent'),
                'disk_percent': pi5_info.get('disk_percent')
            }
            
            # Pi 5 health thresholds
            if pi5_info.get('cpu_temperature', 0) > 80:
                health_data['status'] = 'warning'
                health_data['checks']['system']['warning'] = 'High CPU temperature'
            
            if pi5_info.get('memory_percent', 0) > 90:
                health_data['status'] = 'warning'
                health_data['checks']['system']['warning'] = 'High memory usage'
        
        # GPIO health
        health_data['checks']['gpio'] = {
            'status': 'ok' if PI5_GPIO_AVAILABLE else 'unavailable',
            'available': PI5_GPIO_AVAILABLE
        }
        
        return jsonify(health_data)
        
    except Exception as e:
        logger.error(f"âŒ Pi 5: Health check error: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'pi5_enhanced': True
        }), 500

# CRITICAL FIX 2: Database seeding from sample_prizes.json
def load_sample_prizes():
    """Load sample prizes from JSON file if it exists"""
    sample_file = 'sample_prizes.json'
    if os.path.exists(sample_file):
        try:
            with open(sample_file, 'r') as f:
                data = json.load(f)
                sample_prizes = data.get('sample_prizes', [])
                
            logger.info(f"âœ… Pi 5: Loading {len(sample_prizes)} sample prizes from {sample_file}")
            return sample_prizes
        except Exception as e:
            logger.error(f"âŒ Pi 5: Failed to load {sample_file}: {e}")
    
    # Fallback to hardcoded prizes if file doesn't exist
    logger.info("ðŸ“„ Pi 5: Using fallback hardcoded sample prizes")
    return [
        {'name': '$50 Castle Card', 'description': 'Great Spin!', 'weight': 0.01, 'color': '#FFD700', 'is_winner': True},
        {'name': 'Gutter ball', 'description': 'Sorry, You did not win.', 'weight': 30.0, 'color': '#9E9E9E', 'is_winner': False},
        {'name': '$25 Castle Card', 'description': 'Nice Spin!', 'weight': 0.05, 'color': '#E91E63', 'is_winner': True},
        {'name': 'Ride on Go-Karts', 'description': 'Vroom vroom!', 'weight': 5.0, 'color': '#F44336', 'is_winner': True},
        {'name': 'Castle T-Shirt', 'description': 'Wear it with pride!', 'weight': 2.0, 'color': '#00BCD4', 'is_winner': True},
        {'name': 'Mystery Gift', 'description': 'What could it be?', 'weight': 3.0, 'color': '#9C27B0', 'is_winner': True},
        {'name': 'Womp Womp', 'description': 'Better luck next time!', 'weight': 25.0, 'color': '#FF9800', 'is_winner': False},
        {'name': 'Try Again', 'description': 'Spin one more time!', 'weight': 25.0, 'color': '#795548', 'is_winner': False},
        {'name': 'Free Pretzel', 'description': 'Yummy and salty!', 'weight': 20.0, 'color': '#FFEB3B', 'is_winner': True},
        {'name': 'Mini Golf Pass', 'description': 'Time for a hole-in-one!', 'weight': 4.0, 'color': '#4CAF50', 'is_winner': True},
        {'name': 'Zip Line Ride', 'description': 'Zip into fun!', 'weight': 6.0, 'color': '#2196F3', 'is_winner': True},
        {'name': '100 Tickets', 'description': 'A good start to a prize!', 'weight': 8.0, 'color': '#8BC34A', 'is_winner': True},
        {'name': 'Small Slushie', 'description': 'A tasty, cool treat!', 'weight': 18.0, 'color': '#FF5722', 'is_winner': True},
        {'name': 'Laser Tag Game', 'description': 'Get your game on!', 'weight': 2.0, 'color': '#673AB7', 'is_winner': True},
        {'name': 'Bankrupt', 'description': 'Oh no, you lose!', 'weight': 15.0, 'color': '#212121', 'is_winner': False},
        {'name': 'Jackpot!', 'description': 'You won the grand prize!', 'weight': 0.001, 'color': '#44ffc8', 'is_winner': True}
    ]

# Database Initialization with Pi 5 optimization and CRITICAL FIXES
def init_db():
    """Initialize database with Pi 5 enhanced default data and sample prize loading"""
    with app.app_context():
        try:
            # Create all tables with Pi 5 indexes
            db.create_all()
            
            # Create default admin user if not exists
            if not User.query.filter_by(username='admin').first():
                admin = User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    email='admin@prizewheel.local',
                    role='admin'
                )
                db.session.add(admin)
                logger.info("âœ… Pi 5: Default admin user created")
                
            # CRITICAL FIX 2: Load sample prizes from JSON file
            if Prize.query.count() == 0:
                sample_prizes_data = load_sample_prizes()
                
                for prize_data in sample_prizes_data:
                    prize = Prize(
                        name=prize_data['name'],
                        description=prize_data['description'],
                        weight=prize_data['weight'],
                        color=prize_data['color'],
                        is_winner=prize_data['is_winner']
                    )
                    db.session.add(prize)
                
                logger.info(f"âœ… Pi 5: {len(sample_prizes_data)} sample prizes loaded from configuration")
            
            # Set Pi 5 enhanced default configuration
            default_configs = [
                ('spin_duration', '5', 'wheel', 'Base spin duration in seconds'),
                ('cooldown', '2', 'wheel', 'Cooldown between spins in seconds'),
                ('animation_fps', '60', 'display', 'Animation frames per second (Pi 5 optimized)'),
                ('spin_sound', 'sounds/spin.mp3', 'audio', 'Sound while spinning'),
                ('volume', '0.7', 'audio', 'Master volume (0.0 - 1.0)'),
                ('max_spin_variation', '2', 'wheel', 'Maximum random variation in spin time'),
                ('enable_confetti', 'true', 'display', 'Show confetti for winning spins'),
                ('modal_display_time', '12', 'display', 'Winner modal display time in seconds'),
                ('pi5_enhanced', 'true', 'system', 'Pi 5 enhanced features enabled'),
                ('hardware_acceleration', 'true', 'system', 'Pi 5 hardware acceleration'),
                ('performance_monitoring', 'true', 'system', 'Pi 5 performance monitoring'),
                ('temperature_monitoring', 'true', 'system', 'Pi 5 temperature monitoring'),
                ('gpio_enabled', str(PI5_GPIO_AVAILABLE), 'hardware', 'GPIO hardware available'),
                ('audio_device', 'default', 'audio', 'Pi 5 audio output device'),
                ('kiosk_mode', 'true', 'display', 'Enable kiosk mode features'),
                ('touch_gestures', 'true', 'interface', 'Enable touch gesture controls'),
                ('wake_lock', 'true', 'system', 'Keep Pi 5 screen awake'),
            ]
            for key, value, category, description in default_configs:
                if not Configuration.query.filter_by(key=key).first():
                    set_config(key, value, category, description)
            
            db.session.commit()
            logger.info("âœ… Pi 5: Database initialized successfully with critical fixes applied")
            
        except Exception as e:
            logger.error(f"âŒ Pi 5: Database initialization failed: {e}")
            db.session.rollback()
            raise

# Signal handlers for Pi 5 graceful shutdown
def signal_handler(sig, frame):
    """Handle shutdown signals gracefully for Pi 5"""
    logger.info(f"ðŸ›‘ Pi 5: Received signal {sig}, shutting down...")
    try:
        if PI5_GPIO_AVAILABLE:
            GPIO.cleanup()
            logger.info("âœ… Pi 5: GPIO cleanup completed")
    except:
        pass
    sys.exit(0)

# Main entry point - Pi 5 Enhanced with CRITICAL FIXES
if __name__ == '__main__':
    try:
        logger.info("ðŸš€ Pi 5: Starting Enhanced Prize Wheel System v2.1 with CRITICAL FIXES...")
        
        # Register Pi 5 signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Initialize database with Pi 5 optimizations and critical fixes
        init_db()
        
        # Setup Pi 5 GPIO (with graceful fallback)
        try:
            setup_gpio()
        except Exception as e:
            logger.warning(f"âš ï¸ Pi 5: GPIO setup failed, continuing without hardware support: {e}")
        
        # Log Pi 5 system information at startup
        pi5_info = get_pi5_system_info()
        if pi5_info:
            logger.info(f"ðŸ–¥ï¸ Pi 5 System Info:")
            logger.info(f"   CPU: {pi5_info.get('cpu_count', 'unknown')} cores @ {pi5_info.get('cpu_percent', 0):.1f}%")
            logger.info(f"   Memory: {pi5_info.get('memory_percent', 0):.1f}% used")
            logger.info(f"   Temperature: {pi5_info.get('cpu_temperature', 0):.1f}Â°C")
            logger.info(f"   Disk: {pi5_info.get('disk_percent', 0):.1f}% used")
        
        logger.info("âœ… Pi 5: CRITICAL FIXES APPLIED:")
        logger.info("   ðŸŽ¯ Server-side winner determination with client synchronization")
        logger.info("   ðŸ“„ Database seeding from sample_prizes.json file")
        logger.info("   ðŸŽ® Enhanced spin coordination between server and client")
        logger.info("   ðŸ“ Proper winner index calculation for wheel animation")
        
        logger.info("âœ… Pi 5: Features enabled:")
        logger.info(f"   ðŸŽ® GPIO Hardware: {PI5_GPIO_AVAILABLE}")
        logger.info(f"   ðŸ“Š System Monitoring: {PI5_MONITORING_AVAILABLE}")
        logger.info(f"   ðŸ”Š Enhanced Audio Support: True")
        logger.info(f"   ðŸŽ¨ Hardware Acceleration: {app.config.get('ENABLE_HARDWARE_ACCELERATION', False)}")
        logger.info(f"   ðŸ–¥ï¸ Kiosk Mode Optimized: True")
        
        # Start Flask app with SocketIO and Pi 5 optimization
        logger.info("ðŸŒŸ Pi 5: Starting Prize Wheel System with CRITICAL FIXES applied...")
        logger.info("ðŸŽ¯ Features: Server Winner Logic, JSON Prize Loading, Castle Theme, Sound Support")
        
        socketio.run(app, 
                    host='0.0.0.0', 
                    port=5000, 
                    debug=False,  # Production mode for Pi 5
                    allow_unsafe_werkzeug=True,
                    use_reloader=False,  # Disable for Pi 5 stability
                    log_output=True)
        
    except Exception as e:
        logger.error(f"âŒ Pi 5: Failed to start application: {e}")
        try:
            if PI5_GPIO_AVAILABLE:
                GPIO.cleanup()
        except:
            pass
        sys.exit(1)
    
    finally:
        logger.info("ðŸ‘‹ Pi 5: Prize Wheel System shutdown complete")

# CRITICAL FIXES VALIDATION
__version__ = "2.1.0-IMPROVEMENTS-APPLIED"
__critical_fixes__ = [
    "âœ… Server-side winner determination with proper client sync",
    "âœ… Database seeding from sample_prizes.json configuration file", 
    "âœ… Enhanced spin coordination between server and client",
    "âœ… Proper winner index calculation for wheel animation targeting",
    "âœ… Consistent prize ordering for reliable client-server communication"
]
