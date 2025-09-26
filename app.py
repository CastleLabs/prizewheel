import json
import os
import random
import threading
import uuid
import logging
import csv
import io
import time
import qrcode
from datetime import datetime
from flask import Flask, jsonify, render_template, request, send_file, Response
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
import base64
from io import BytesIO

# Enhanced logging for events with better formatting
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
    handlers=[
        logging.FileHandler('prize_wheel.log'),
        logging.StreamHandler()
    ]
)

# GPIO with comprehensive error handling
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
    logging.info("🎯 RPi.GPIO library loaded successfully - Hardware mode enabled!")
except (ImportError, RuntimeError) as e:
    logging.warning(f"⚠️ GPIO not available ({e}) - Simulation mode enabled")
    GPIO_AVAILABLE = False

# App Configuration with expanded file type support
UPLOAD_FOLDER = 'static/sounds'
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'aac'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Enhanced Flask & SocketIO configuration
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config.update(
    SECRET_KEY='prize-wheel-castle-kingdom-2024!',
    UPLOAD_FOLDER=UPLOAD_FOLDER,
    MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max file size
)

# Ensure required directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('static/images', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60, ping_interval=25)

# Enhanced thread-safe state management with backup capabilities
class WheelState:
    """
    Enhanced wheel state management class to prevent concurrent spins
    and track all busy states that should block new spin requests
    """
    def __init__(self):
        self.is_spinning = False
        self.connected_clients = set()
        self.last_winner = None
        self.total_spins_session = 0
        self._lock = threading.Lock()
        self.performance_metrics = {
            'start_time': time.time(),
            'total_connections': 0,
            'peak_concurrent': 0
        }
        
        # Enhanced state tracking for debugging
        self.spin_start_time = None
        self.last_spin_source = None

    def start_spin(self):
        """
        Attempt to start a spin - returns True if successful, False if already spinning
        Thread-safe implementation prevents race conditions
        """
        with self._lock:
            if self.is_spinning:
                logging.debug(f"🔒 Spin blocked - already spinning (started by {self.last_spin_source})")
                return False
            
            self.is_spinning = True
            self.total_spins_session += 1
            self.spin_start_time = time.time()
            
            logging.info(f"🎲 Spin #{self.total_spins_session} STARTED")
            return True

    def end_spin(self):
        """Mark spin as complete and log timing"""
        with self._lock:
            if self.is_spinning:
                duration = time.time() - self.spin_start_time if self.spin_start_time else 0
                logging.info(f"✅ Spin #{self.total_spins_session} COMPLETED (duration: {duration:.1f}s)")
                
            self.is_spinning = False
            self.spin_start_time = None

    def add_client(self, client_id):
        """Add connected client and update metrics"""
        with self._lock:
            self.connected_clients.add(client_id)
            self.performance_metrics['total_connections'] += 1
            self.performance_metrics['peak_concurrent'] = max(
                len(self.connected_clients), 
                self.performance_metrics['peak_concurrent']
            )

    def remove_client(self, client_id):
        """Remove disconnected client"""
        with self._lock:
            self.connected_clients.discard(client_id)

    def get_status(self):
        """Get current wheel status for debugging"""
        with self._lock:
            return {
                'is_spinning': self.is_spinning,
                'connected_clients': len(self.connected_clients),
                'total_spins': self.total_spins_session,
                'last_winner': self.last_winner,
                'spin_duration': time.time() - self.spin_start_time if self.spin_start_time else 0
            }

wheel_state = WheelState()
file_lock = threading.Lock()

# Enhanced file operations with backup and recovery
def create_backup(filename):
    """Create a timestamped backup of a JSON file"""
    if os.path.exists(filename):
        backup_path = f"{filename}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
        try:
            import shutil
            shutil.copy2(filename, backup_path)
            logging.info(f"💾 Backup created: {backup_path}")
            return backup_path
        except Exception as e:
            logging.error(f"💥 Backup creation failed: {e}")
    return None

def load_json_file(filename, default_data):
    """Load JSON file with corruption recovery and backup creation"""
    with file_lock:
        if not os.path.exists(filename):
            save_json_file(filename, default_data)
            return default_data
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Validate data structure for critical files
                if filename == 'prizes.json' and not isinstance(data, list):
                    raise json.JSONDecodeError("Invalid prizes format", filename, 0)
                return data
        except json.JSONDecodeError as e:
            logging.error(f"🚨 CORRUPTION: '{filename}' corrupted. Auto-recovering...")
            backup_path = create_backup(filename)
            if backup_path:
                logging.info(f"🔒 Corrupted file backed up as: {backup_path}")
            save_json_file(filename, default_data)
            logging.info(f"✅ Recovery complete. File reset to defaults.")
            return default_data
        except IOError as e:
            logging.error(f"💥 IO ERROR reading '{filename}': {e}")
            return default_data

def save_json_file(filename, data):
    """Save JSON file atomically with validation"""
    with file_lock:
        try:
            # Validate JSON serialization before writing
            json.dumps(data, indent=2, ensure_ascii=False)
            
            # Create backup before overwriting critical files
            if filename in ['prizes.json'] and os.path.exists(filename):
                create_backup(filename)
            
            # Atomic write with temp file
            temp_filename = f"{filename}.tmp"
            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(temp_filename, filename)
            logging.debug(f"💾 File saved successfully: {filename}")
            return True
        except (IOError, TypeError, ValueError) as e:
            logging.error(f"💥 Save error for '{filename}': {e}")
            # Clean up temp file if it exists
            temp_filename = f"{filename}.tmp"
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except:
                    pass
            return False

# Helper functions for file validation
def allowed_file(filename, allowed_extensions):
    """Check if file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def validate_prize_data(data):
    """Validate prize data structure"""
    required_fields = ['name', 'weight']
    for field in required_fields:
        if field not in data:
            return False, f"Missing required field: {field}"
    
    if not isinstance(data['weight'], (int, float)) or data['weight'] <= 0:
        return False, "Weight must be a positive number"
    
    if not isinstance(data['name'], str) or not data['name'].strip():
        return False, "Name must be a non-empty string"
    
    return True, None

# Enhanced dashboard state with error handling
def get_dashboard_state():
    """Comprehensive dashboard state with performance metrics and error handling"""
    try:
        prizes = load_json_file('prizes.json', [])
        history = load_json_file('history.json', [])
        
        total_spins = len(history)
        winner_spins = 0
        if prizes:
            winner_ids = {p['id'] for p in prizes if p.get('is_winner')}
            winner_spins = sum(1 for spin in history if spin.get('prize_id') in winner_ids)
        
        win_rate = (winner_spins / total_spins * 100) if total_spins > 0 else 0
        uptime_hours = (time.time() - wheel_state.performance_metrics['start_time']) / 3600
        
        return {
            'stats': {
                'total_spins': total_spins,
                'session_spins': wheel_state.total_spins_session,
                'win_rate': f"{win_rate:.1f}",
                'active_prizes': sum(1 for p in prizes if p.get('enabled', True)),
                'last_spin': history[0]['timestamp'] if history else 'Never',
                'connected_clients': len(wheel_state.connected_clients),
                'peak_concurrent': wheel_state.performance_metrics['peak_concurrent'],
                'uptime_hours': f"{uptime_hours:.1f}",
                'last_winner': wheel_state.last_winner
            },
            'history': history[:30],
            'performance': wheel_state.performance_metrics
        }
    except Exception as e:
        logging.error(f"💥 Dashboard state error: {e}")
        # Return safe default state
        return {
            'stats': {
                'total_spins': 0, 'session_spins': 0, 'win_rate': '0.0', 
                'active_prizes': 0, 'last_spin': 'Never', 'connected_clients': 0,
                'peak_concurrent': 0, 'uptime_hours': '0.0', 'last_winner': None
            },
            'history': [],
            'performance': wheel_state.performance_metrics
        }

# Enhanced spin logic with comprehensive error handling and configurable timing
def trigger_spin_flow(source='unknown', user_data=None):
    """
    Enhanced spin trigger with comprehensive state checking to prevent concurrent spins
    This is the main function that handles all spin requests from any source
    """
    # Enhanced spin state checking - this is the critical gatekeeper
    if not wheel_state.start_spin():
        logging.warning(f"🔄 Spin from '{source}' BLOCKED: wheel is busy (spinning: {wheel_state.is_spinning})")
        # Send detailed rejection message to frontend
        socketio.emit('spin_rejected', {
            'reason': 'wheel_busy',
            'message': 'Wheel is currently spinning or in cooldown. Please wait.',
            'source': source,
            'current_state': wheel_state.get_status(),
            'timestamp': datetime.now().isoformat()
        })
        return False

    # Store source for debugging
    wheel_state.last_spin_source = source
    logging.info(f"🎲 Spin ACCEPTED from: {source} {f'({user_data})' if user_data else ''}")
    
    try:
        prizes = load_json_file('prizes.json', [])
        config = load_json_file('config.json', {
            'spin_duration_seconds': 8,
            'cooldown_seconds': 5,
            'volume': 75,
            'modal_delay_ms': 3000,
            'modal_auto_close_ms': 10000,
            'winner_flash_duration_ms': 4000
        })
        
        enabled_prizes = [p for p in prizes if p.get('enabled', True)]
        if not enabled_prizes:
            logging.error("⌘ Spin ABORTED: No enabled prizes found.")
            socketio.emit('spin_error', {
                'message': 'Cannot spin: No prizes are enabled!',
                'error_type': 'no_prizes'
            })
            wheel_state.end_spin()
            return False

        winner = calculate_winner(enabled_prizes)
        if not winner:
            logging.error("⌘ Spin ABORTED: Could not determine a winner.")
            socketio.emit('spin_error', {
                'message': 'Cannot spin: Winner calculation failed.',
                'error_type': 'calculation_failed'
            })
            wheel_state.end_spin()
            return False

        # Enhanced history tracking with error handling
        history = load_json_file('history.json', [])
        spin_record = {
            "timestamp": datetime.now().isoformat(),
            "prize_id": winner.get('id'),
            "prize_name": winner.get('name', 'Unknown Prize'),
            "is_winner": winner.get('is_winner', False),
            "source": source,
            "session_spin": wheel_state.total_spins_session
        }
        
        if user_data:
            spin_record["user_data"] = user_data
        
        history.insert(0, spin_record)
        save_json_file('history.json', history[:100])

        wheel_state.last_winner = winner.get('name')
        
        spin_duration_s = config.get('spin_duration_seconds', 8)
        spin_duration_ms = spin_duration_s * 1000
        cooldown_s = config.get('cooldown_seconds', 5)
        
        logging.info(f"🏆 Winner: '{winner.get('name')}' | Duration: {spin_duration_s}s | Cooldown: {cooldown_s}s")

        # Enhanced spin data with timing info
        spin_data = {
            'winner_id': winner.get('id'),
            'spin_duration': spin_duration_ms,
            'prizes': enabled_prizes,
            'spin_number': wheel_state.total_spins_session,
            'source': source,
            'cooldown_duration': cooldown_s * 1000,
            'modal_delay': config.get('modal_delay_ms', 3000),
            'modal_auto_close': config.get('modal_auto_close_ms', 10000)
        }
        
        logging.info(f"📡 Emitting spin_started: winner_id={winner.get('id')}")
        socketio.emit('spin_started', spin_data)

        # Use SocketIO background task for spin completion
        def complete_spin():
            logging.info(f"⏰ SocketIO background task executing spin completion...")
            
            wheel_state.end_spin()
            
            complete_data = {
                'winner': winner,
                'cooldown_duration': cooldown_s * 1000,
                'modal_delay': config.get('modal_delay_ms', 3000),
                'modal_auto_close': config.get('modal_auto_close_ms', 10000),
                'spin_stats': {
                    'total_spins': len(history),
                    'session_spins': wheel_state.total_spins_session
                }
            }
            
            logging.info(f"📡 Emitting spin_complete: winner={winner.get('name')}")
            socketio.emit('spin_complete', complete_data)
            
            # Real-time dashboard updates
            dashboard_state = get_dashboard_state()
            logging.info(f"📡 Emitting state_update")
            socketio.emit('state_update', dashboard_state)
            
            logging.info(f"✅ Spin #{wheel_state.total_spins_session} COMPLETE - server ready")
        
        # Start the background task with SocketIO's built-in scheduler
        logging.info(f"⏰ Starting SocketIO background task for {spin_duration_s}s")
        socketio.start_background_task(lambda: (time.sleep(spin_duration_s), complete_spin()))
        return True
        
    except Exception as e:
        logging.error(f"💥 Spin flow error: {e}")
        import traceback
        logging.error(f"🔍 Full traceback: {traceback.format_exc()}")
        socketio.emit('spin_error', {
            'message': f'Spin failed: {str(e)}',
            'error_type': 'server_error'
        })
        wheel_state.end_spin()
        return False

def calculate_winner(prizes):
    """Enhanced winner calculation with comprehensive logging and error handling"""
    try:
        if not prizes:
            logging.warning("⚠️ No prizes provided to calculate_winner")
            return None
            
        valid_prizes = [p for p in prizes if isinstance(p.get('weight', 0), (int, float)) and p.get('weight', 0) > 0]
        if not valid_prizes:
            logging.warning("⚠️ No prizes with valid weights, using random selection")
            return random.choice(prizes) if prizes else None
            
        total_weight = sum(p['weight'] for p in valid_prizes)
        if total_weight <= 0:
            logging.warning("⚠️ Total weight is zero or negative")
            return random.choice(valid_prizes)
            
        rand_val = random.uniform(0, total_weight)
        cumulative_weight = 0
        
        for i, prize in enumerate(valid_prizes):
            cumulative_weight += prize['weight']
            if rand_val <= cumulative_weight:
                logging.debug(f"Winner calculation: {rand_val:.3f}/{total_weight:.3f} -> Prize {i+1}")
                return prize
                
        # Fallback to last prize
        logging.debug("Winner calculation fallback to last prize")
        return valid_prizes[-1]
        
    except Exception as e:
        logging.error(f"💥 Winner calculation error: {e}")
        return prizes[0] if prizes else None

# Enhanced GPIO with comprehensive error handling
button_last_press = 0
BUTTON_DEBOUNCE_TIME = 1.0

def gpio_button_callback(channel):
    """
    Enhanced GPIO button callback with state checking
    This ensures hardware button respects the same spin state as web interface
    """
    global button_last_press
    try:
        current_time = time.time()
        if current_time - button_last_press < BUTTON_DEBOUNCE_TIME:
            logging.debug(f"🔘 GPIO {channel} debounced (too soon)")
            return
            
        button_last_press = current_time
        
        # Check wheel state before triggering - this prevents hardware double-spins
        if wheel_state.is_spinning:
            logging.warning(f"🔘 GPIO {channel} BLOCKED: wheel is spinning")
            return
            
        logging.info(f"🔘 GPIO {channel} pressed - triggering spin")
        success = trigger_spin_flow(source='hardware_button', user_data=f'GPIO_{channel}')
        
        if not success:
            logging.warning(f"🔘 GPIO {channel} spin was rejected by server")
            
    except Exception as e:
        logging.error(f"💥 GPIO callback error: {e}")

def setup_gpio():
    """Enhanced GPIO setup with comprehensive error handling"""
    global GPIO_AVAILABLE
    
    config = load_json_file('config.json', {'button_pin': 17})
    button_pin = config.get('button_pin', 17)
    
    if not GPIO_AVAILABLE:
        logging.info("🔧 GPIO simulation mode - button functionality available via web")
        return
    
    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(button_pin, GPIO.FALLING, 
                             callback=gpio_button_callback, bouncetime=300)
        logging.info(f"🎯 GPIO pin {button_pin} configured successfully!")
        
        # Test GPIO pin accessibility
        initial_state = GPIO.input(button_pin)
        logging.debug(f"🔍 GPIO pin {button_pin} initial state: {initial_state}")
        
    except Exception as e:
        logging.error(f"💥 Failed to set up GPIO on pin {button_pin}: {e}")
        GPIO_AVAILABLE = False

# ==============================================================================
# ROUTE HANDLERS
# ==============================================================================

@app.route('/')
def display_page():
    """Enhanced display page with configurable timing"""
    try:
        prizes = load_json_file('prizes.json', [])
        config = load_json_file('config.json', {
            'volume': 75,
            'system_sounds': {
                'spin': '/static/sounds/spin.mp3',
                'winner': '/static/sounds/victory.mp3',
                'loser': '/static/sounds/try-again.mp3'
            },
            'modal_delay_ms': 3000,
            'modal_auto_close_ms': 10000,
            'winner_flash_duration_ms': 4000
        })
        
        # Filter enabled prizes and ensure they have all required fields
        enabled_prizes = []
        for prize in prizes:
            if prize.get('enabled', True):  # Default to enabled if not specified
                # Ensure required fields exist
                cleaned_prize = {
                    'id': prize.get('id', str(uuid.uuid4())),
                    'name': prize.get('name', 'Unknown Prize'),
                    'description': prize.get('description', ''),
                    'weight': prize.get('weight', 1),
                    'color': prize.get('color', '#4CAF50'),
                    'is_winner': prize.get('is_winner', False),
                    'enabled': True,
                    'sound_path': prize.get('sound_path', '')
                }
                enabled_prizes.append(cleaned_prize)
        
        # Log for debugging
        logging.info(f"🎯 Display page serving {len(enabled_prizes)} enabled prizes")
        logging.info(f"⏱️ Timing config: modal_delay={config.get('modal_delay_ms')}ms, auto_close={config.get('modal_auto_close_ms')}ms")
        
        for i, prize in enumerate(enabled_prizes):
            logging.info(f"  Prize {i+1}: {prize['name']} (ID: {prize['id']})")
        
        return render_template('display.html', 
                             prizes=enabled_prizes, 
                             volume=config.get('volume', 80), 
                             system_sounds=config.get('system_sounds', {}),
                             config=config,  # Pass full config object for timing settings
                             total_prizes=len(enabled_prizes),
                             session_spins=wheel_state.total_spins_session)
    except Exception as e:
        logging.error(f"💥 Display page error: {e}")
        # Return a minimal working page with fallback data
        fallback_config = {
            'volume': 75,
            'system_sounds': {
                'spin': '/static/sounds/spin.mp3',
                'winner': '/static/sounds/victory.mp3',
                'loser': '/static/sounds/try-again.mp3'
            },
            'modal_delay_ms': 3000,
            'modal_auto_close_ms': 10000,
            'winner_flash_duration_ms': 4000
        }
        fallback_prizes = [
            {
                'id': '1',
                'name': '$50 Castle Card',
                'description': 'Great Spin! Major cash prize!',
                'weight': 0.5,
                'color': '#FFD700',
                'is_winner': True,
                'enabled': True,
                'sound_path': ''
            },
            {
                'id': '2',
                'name': 'Gutter ball',
                'description': 'Sorry, You did not win this time.',
                'weight': 30,
                'color': '#9E9E9E',
                'is_winner': False,
                'enabled': True,
                'sound_path': ''
            }
        ]
        return render_template('display.html', 
                             prizes=fallback_prizes, 
                             volume=75, 
                             system_sounds=fallback_config['system_sounds'],
                             config=fallback_config,
                             total_prizes=len(fallback_prizes),
                             session_spins=0)

@app.route('/dashboard')
def dashboard_page():
    """Dashboard page with error handling"""
    try:
        state = get_dashboard_state()
        return render_template('dashboard.html', 
                             current_date=datetime.now().strftime('%B %d, %Y'),
                             performance=state['performance'])
    except Exception as e:
        logging.error(f"💥 Dashboard page error: {e}")
        return f"Error loading dashboard: {e}", 500

@app.route('/odds')
def odds_calculator():
    """Odds calculator page for analyzing prize probabilities"""
    try:
        prizes = load_json_file('prizes.json', [])
        logging.info(f"🎯 Odds calculator loaded {len(prizes)} prizes")
        
        # Debug logging
        for i, prize in enumerate(prizes):
            logging.info(f"  Prize {i+1}: {prize.get('name', 'Unknown')} - Weight: {prize.get('weight', 0)} - Enabled: {prize.get('enabled', True)}")
        
        return render_template('odds_calculator.html', 
                             prizes=prizes,
                             prizes_json=json.dumps(prizes))  # Add JSON version for debugging
    except Exception as e:
        logging.error(f"💥 Odds calculator page error: {e}")
        import traceback
        logging.error(f"🔍 Full traceback: {traceback.format_exc()}")
        return f"Error loading odds calculator: {e}", 500

# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.route('/api/dashboard_data')
def get_dashboard_data():
    """Get comprehensive dashboard data"""
    try:
        prizes = load_json_file('prizes.json', [])
        config = load_json_file('config.json', {
            'spin_duration_seconds': 8,
            'cooldown_seconds': 5,
            'volume': 75,
            'modal_delay_ms': 3000,
            'modal_auto_close_ms': 10000,
            'winner_flash_duration_ms': 4000
        })
        state = get_dashboard_state()
        return jsonify({
            'prizes': prizes,
            'config': config,
            'recent_spins': state['history'],
            'stats': state['stats'],
            'performance': state['performance'],
            'system_info': {
                'gpio_available': GPIO_AVAILABLE,
                'connected_clients': len(wheel_state.connected_clients),
                'wheel_status': wheel_state.get_status()
            }
        })
    except Exception as e:
        logging.error(f"💥 Dashboard data error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizes', methods=['GET'])
def get_prizes():
    """Get all prizes"""
    try:
        prizes = load_json_file('prizes.json', [])
        return jsonify({'prizes': prizes})
    except Exception as e:
        logging.error(f"💥 Get prizes error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/odds/prizes')
def get_odds_prizes():
    """Get prizes specifically for odds calculator with enhanced error handling"""
    try:
        prizes = load_json_file('prizes.json', [])
        logging.info(f"🎯 API: Serving {len(prizes)} prizes to odds calculator")
        
        # Ensure all prizes have required fields for odds calculator
        cleaned_prizes = []
        for prize in prizes:
            cleaned_prize = {
                'id': prize.get('id', str(uuid.uuid4())),
                'name': prize.get('name', 'Unknown Prize'),
                'description': prize.get('description', ''),
                'weight': float(prize.get('weight', 1.0)),
                'color': prize.get('color', '#4CAF50'),
                'is_winner': bool(prize.get('is_winner', False)),
                'enabled': bool(prize.get('enabled', True)),
                'sound_path': prize.get('sound_path', '')
            }
            cleaned_prizes.append(cleaned_prize)
        
        return jsonify({
            'success': True,
            'prizes': cleaned_prizes,
            'count': len(cleaned_prizes),
            'enabled_count': len([p for p in cleaned_prizes if p['enabled']])
        })
        
    except Exception as e:
        logging.error(f"💥 Odds prizes API error: {e}")
        import traceback
        logging.error(f"🔍 Full traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e),
            'prizes': []
        }), 500

@app.route('/api/odds/simulate', methods=['POST'])
def simulate_spins():
    """Simulate multiple spins to test probability distribution"""
    try:
        data = request.json
        num_simulations = min(data.get('simulations', 1000), 10000)  # Cap at 10k
        
        prizes = load_json_file('prizes.json', [])
        enabled_prizes = [p for p in prizes if p.get('enabled', True)]
        
        if not enabled_prizes:
            return jsonify({'error': 'No enabled prizes found'}), 400
        
        # Run simulations
        results = {}
        for _ in range(num_simulations):
            winner = calculate_winner(enabled_prizes)
            if winner:
                prize_id = winner.get('id')
                results[prize_id] = results.get(prize_id, 0) + 1
        
        # Calculate percentages
        simulation_results = []
        total_weight = sum(float(p.get('weight', 0)) for p in enabled_prizes)
        
        for prize in enabled_prizes:
            count = results.get(prize['id'], 0)
            percentage = (count / num_simulations) * 100
            expected_percentage = (float(prize.get('weight', 0)) / total_weight) * 100 if total_weight > 0 else 0
            
            simulation_results.append({
                'id': prize['id'],
                'name': prize['name'],
                'expected_percentage': expected_percentage,
                'actual_percentage': percentage,
                'count': count,
                'is_winner': prize.get('is_winner', False)
            })
        
        return jsonify({
            'simulations': num_simulations,
            'results': simulation_results,
            'total_winners': sum(r['count'] for r in simulation_results if r['is_winner']),
            'win_rate': (sum(r['count'] for r in simulation_results if r['is_winner']) / num_simulations) * 100
        })
        
    except Exception as e:
        logging.error(f"💥 Simulation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/odds/analysis')
def get_odds_analysis():
    """Get detailed odds analysis"""
    try:
        prizes = load_json_file('prizes.json', [])
        enabled_prizes = [p for p in prizes if p.get('enabled', True)]
        
        if not enabled_prizes:
            return jsonify({'error': 'No enabled prizes found'}), 400
        
        total_weight = sum(float(p.get('weight', 0)) for p in enabled_prizes)
        
        analysis = {
            'total_prizes': len(prizes),
            'enabled_prizes': len(enabled_prizes),
            'disabled_prizes': len(prizes) - len(enabled_prizes),
            'total_weight': total_weight,
            'prizes': []
        }
        
        winner_weight = 0
        loser_weight = 0
        
        for prize in enabled_prizes:
            weight = float(prize.get('weight', 0))
            probability = (weight / total_weight) * 100 if total_weight > 0 else 0
            
            prize_analysis = {
                'id': prize['id'],
                'name': prize['name'],
                'weight': weight,
                'probability': probability,
                'is_winner': prize.get('is_winner', False),
                'color': prize.get('color', '#4CAF50'),
                'enabled': prize.get('enabled', True)
            }
            
            analysis['prizes'].append(prize_analysis)
            
            if prize.get('is_winner', False):
                winner_weight += weight
            else:
                loser_weight += weight
        
        # Overall statistics
        analysis['win_probability'] = (winner_weight / total_weight) * 100 if total_weight > 0 else 0
        analysis['lose_probability'] = (loser_weight / total_weight) * 100 if total_weight > 0 else 0
        analysis['expected_spins_to_win'] = (100 / analysis['win_probability']) if analysis['win_probability'] > 0 else float('inf')
        
        # Sort by probability
        analysis['prizes'].sort(key=lambda x: x['probability'], reverse=True)
        analysis['most_likely'] = analysis['prizes'][0] if analysis['prizes'] else None
        analysis['least_likely'] = analysis['prizes'][-1] if analysis['prizes'] else None
        
        return jsonify(analysis)
        
    except Exception as e:
        logging.error(f"💥 Odds analysis error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizes', methods=['POST'])
def add_prize():
    """Add a new prize"""
    try:
        data = request.json
        is_valid, error_msg = validate_prize_data(data)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
        
        prizes = load_json_file('prizes.json', [])
        
        # Generate unique ID
        new_id = str(uuid.uuid4())
        while any(p.get('id') == new_id for p in prizes):
            new_id = str(uuid.uuid4())
        
        new_prize = {
            'id': new_id,
            'name': data['name'].strip(),
            'description': data.get('description', '').strip(),
            'weight': float(data['weight']),
            'color': data.get('color', '#FF6B6B'),
            'sound_path': data.get('sound_path', ''),
            'is_winner': data.get('is_winner', True),
            'enabled': data.get('enabled', True)
        }
        
        prizes.append(new_prize)
        success = save_json_file('prizes.json', prizes)
        
        if success:
            logging.info(f"🎁 Prize added: {new_prize['name']}")
            return jsonify({'message': 'Prize added successfully', 'prize': new_prize})
        else:
            return jsonify({'error': 'Failed to save prize'}), 500
            
    except Exception as e:
        logging.error(f"💥 Add prize error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizes/<prize_id>', methods=['PUT'])
def update_prize(prize_id):
    """Update an existing prize"""
    try:
        data = request.json
        prizes = load_json_file('prizes.json', [])
        
        prize_index = next((i for i, p in enumerate(prizes) if p.get('id') == prize_id), None)
        if prize_index is None:
            return jsonify({'error': 'Prize not found'}), 404
        
        # If updating core data, validate it
        if any(key in data for key in ['name', 'weight']):
            is_valid, error_msg = validate_prize_data({**prizes[prize_index], **data})
            if not is_valid:
                return jsonify({'error': error_msg}), 400
        
        # Update prize
        prizes[prize_index].update({
            key: value for key, value in data.items() 
            if key in ['name', 'description', 'weight', 'color', 'sound_path', 'is_winner', 'enabled']
        })
        
        # Ensure weight is float and strip strings
        if 'weight' in data:
            prizes[prize_index]['weight'] = float(data['weight'])
        if 'name' in data:
            prizes[prize_index]['name'] = data['name'].strip()
        if 'description' in data:
            prizes[prize_index]['description'] = data['description'].strip()
        
        success = save_json_file('prizes.json', prizes)
        
        if success:
            logging.info(f"🎁 Prize updated: {prizes[prize_index]['name']}")
            return jsonify({'message': 'Prize updated successfully', 'prize': prizes[prize_index]})
        else:
            return jsonify({'error': 'Failed to save prize'}), 500
            
    except Exception as e:
        logging.error(f"💥 Update prize error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/prizes/<prize_id>', methods=['DELETE'])
def delete_prize(prize_id):
    """Delete a prize"""
    try:
        prizes = load_json_file('prizes.json', [])
        
        prize_index = next((i for i, p in enumerate(prizes) if p.get('id') == prize_id), None)
        if prize_index is None:
            return jsonify({'error': 'Prize not found'}), 404
        
        deleted_prize = prizes.pop(prize_index)
        success = save_json_file('prizes.json', prizes)
        
        if success:
            logging.info(f"🗑️ Prize deleted: {deleted_prize['name']}")
            return jsonify({'message': 'Prize deleted successfully'})
        else:
            return jsonify({'error': 'Failed to save prizes'}), 500
            
    except Exception as e:
        logging.error(f"💥 Delete prize error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    """Save configuration settings including timing"""
    try:
        data = request.json
        config = load_json_file('config.json', {})
        
        # Update only allowed config keys
        allowed_keys = [
            'volume', 
            'spin_duration_seconds', 
            'cooldown_seconds', 
            'system_sounds', 
            'button_pin',
            'modal_delay_ms',
            'modal_auto_close_ms', 
            'winner_flash_duration_ms'
        ]
        
        for key in allowed_keys:
            if key in data:
                config[key] = data[key]
        
        # Validate volume range
        if 'volume' in config:
            config['volume'] = max(0, min(100, int(config['volume'])))
        
        # Validate timing ranges with helpful limits
        if 'modal_delay_ms' in config:
            config['modal_delay_ms'] = max(500, min(10000, int(config['modal_delay_ms'])))
        
        if 'modal_auto_close_ms' in config:
            config['modal_auto_close_ms'] = max(2000, min(30000, int(config['modal_auto_close_ms'])))
            
        if 'winner_flash_duration_ms' in config:
            config['winner_flash_duration_ms'] = max(1000, min(10000, int(config['winner_flash_duration_ms'])))
        
        success = save_json_file('config.json', config)
        
        if success:
            timing_info = {
                'modal_delay': config.get('modal_delay_ms', 'not set'),
                'auto_close': config.get('modal_auto_close_ms', 'not set'),
                'flash_duration': config.get('winner_flash_duration_ms', 'not set')
            }
            logging.info(f"⚙️ Configuration updated with timing: {timing_info}")
            return jsonify({'message': 'Configuration saved successfully', 'config': config})
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
            
    except Exception as e:
        logging.error(f"💥 Save config error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sounds/list')
def list_sounds():
    """List available sound files"""
    try:
        sounds = []
        sound_dir = app.config['UPLOAD_FOLDER']
        
        if os.path.exists(sound_dir):
            for filename in os.listdir(sound_dir):
                if allowed_file(filename, ALLOWED_EXTENSIONS):
                    sounds.append(f"/static/sounds/{filename}")
        
        # Add system sounds
        config = load_json_file('config.json', {})
        system_sounds = config.get('system_sounds', {})
        for sound_path in system_sounds.values():
            if sound_path and sound_path not in sounds:
                sounds.append(sound_path)
        
        logging.debug(f"🎵 Listed {len(sounds)} available sounds")
        return jsonify({'sounds': sounds})
        
    except Exception as e:
        logging.error(f"💥 List sounds error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload/sound', methods=['POST'])
def upload_sound():
    """Upload a sound file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename, ALLOWED_EXTENSIONS):
            return jsonify({'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        
        filename = secure_filename(file.filename)
        # Ensure unique filename
        base_name, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
            filename = f"{base_name}_{counter}{ext}"
            counter += 1
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        sound_url = f"/static/sounds/{filename}"
        logging.info(f"🎵 Sound uploaded: {filename}")
        
        return jsonify({
            'message': 'Sound uploaded successfully',
            'filename': filename,
            'url': sound_url
        })
        
    except Exception as e:
        logging.error(f"💥 Upload sound error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/csv')
def export_csv():
    """Export spin history as CSV"""
    try:
        history = load_json_file('history.json', [])
        
        if not history:
            return jsonify({'error': 'No history data to export'}), 404
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Timestamp', 'Prize Name', 'Prize ID', 'Is Winner', 'Source', 'Session Spin'])
        
        # Write data
        for record in history:
            writer.writerow([
                record.get('timestamp', ''),
                record.get('prize_name', ''),
                record.get('prize_id', ''),
                'Yes' if record.get('is_winner') else 'No',
                record.get('source', ''),
                record.get('session_spin', '')
            ])
        
        # Create response
        output.seek(0)
        response = Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=prize_wheel_history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
        
        logging.info(f"📊 CSV export generated with {len(history)} records")
        return response
        
    except Exception as e:
        logging.error(f"💥 Export CSV error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['DELETE'])
def clear_stats():
    """Clear spin history"""
    try:
        # Create backup before clearing
        history = load_json_file('history.json', [])
        if history:
            backup_path = create_backup('history.json')
            logging.info(f"🔒 History backed up to: {backup_path}")
        
        # Clear history
        success = save_json_file('history.json', [])
        
        if success:
            logging.info("🗑️ Spin history cleared")
            return jsonify({'message': 'History cleared successfully'})
        else:
            return jsonify({'error': 'Failed to clear history'}), 500
            
    except Exception as e:
        logging.error(f"💥 Clear stats error: {e}")
        return jsonify({'error': str(e)}), 500

# QR Code generation for easy mobile access
@app.route('/api/qr_code')
def generate_qr_code():
    """Generate QR code for easy mobile access"""
    try:
        # Get the actual server IP/URL
        host = request.host
        if host.startswith('127.0.0.1') or host.startswith('localhost'):
            # Try to get actual network IP for events
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                s.close()
                host = f"{local_ip}:5000"
            except:
                pass
        
        url = f"http://{host}/"
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64 for easy embedding
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'qr_code': f"data:image/png;base64,{img_str}",
            'url': url
        })
    except Exception as e:
        logging.error(f"💥 QR Code generation failed: {e}")
        return jsonify({'error': 'Failed to generate QR code'}), 500

# Performance monitoring endpoint
@app.route('/api/performance')
def get_performance_metrics():
    """Get performance metrics"""
    try:
        return jsonify(wheel_state.performance_metrics)
    except Exception as e:
        logging.error(f"💥 Performance metrics error: {e}")
        return jsonify({'error': str(e)}), 500

# Enhanced Remote Spin API Endpoints with state checking
@app.route('/api/spin', methods=['POST'])
def trigger_spin_api():
    """
    Enhanced API spin trigger with comprehensive state checking
    This endpoint respects the same spin state as all other spin sources
    """
    try:
        # Check wheel state immediately - this is the first line of defense
        if wheel_state.is_spinning:
            logging.warning(f"📡 API spin BLOCKED: wheel is spinning")
            return jsonify({
                'success': False,
                'error': 'wheel_busy',
                'message': 'Wheel is currently spinning. Please wait for it to complete.',
                'is_spinning': True,
                'wheel_status': wheel_state.get_status(),
                'timestamp': datetime.now().isoformat()
            }), 409
        
        # Get optional user data from request
        data = request.get_json() if request.is_json else {}
        user_info = data.get('user_info', 'api_client')
        source_info = data.get('source', 'rest_api')
        
        logging.info(f"📡 API spin request from: {user_info} via {source_info}")
        
        # Attempt to trigger the spin using the same flow as other sources
        success = trigger_spin_flow(source=f'api_{source_info}', user_data=user_info)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Spin triggered successfully',
                'spin_number': wheel_state.total_spins_session,
                'wheel_status': wheel_state.get_status(),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'spin_rejected',
                'message': 'Spin was rejected by the server (wheel may be busy)',
                'is_spinning': wheel_state.is_spinning,
                'wheel_status': wheel_state.get_status(),
                'timestamp': datetime.now().isoformat()
            }), 409
        
    except Exception as e:
        logging.error(f"💥 API spin trigger error: {e}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/spin/status')
def get_spin_status():
    """Get current wheel status with detailed state information"""
    try:
        return jsonify({
            'is_spinning': wheel_state.is_spinning,
            'connected_clients': len(wheel_state.connected_clients),
            'total_spins_session': wheel_state.total_spins_session,
            'last_winner': wheel_state.last_winner,
            'last_spin_source': wheel_state.last_spin_source,
            'detailed_status': wheel_state.get_status(),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logging.error(f"💥 Spin status error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/spin', methods=['GET'])
def get_spin_info():
    """Get information about spin API endpoints"""
    return jsonify({
        'endpoints': {
            'trigger_spin': {
                'method': 'POST',
                'url': '/api/spin',
                'description': 'Trigger a wheel spin',
                'optional_body': {
                    'user_info': 'string - identifier for the user/system triggering the spin',
                    'source': 'string - source system identifier'
                },
                'response_codes': {
                    '200': 'Spin triggered successfully',
                    '409': 'Wheel is busy (spinning or in cooldown)',
                    '500': 'Server error'
                }
            },
            'spin_status': {
                'method': 'GET', 
                'url': '/api/spin/status',
                'description': 'Get current wheel status with detailed information'
            }
        },
        'examples': {
            'basic_spin': 'POST /api/spin',
            'spin_with_info': 'POST /api/spin with body: {"user_info": "kiosk_1", "source": "lobby_terminal"}'
        },
        'timing_info': {
            'description': 'Modal timing is now configurable via /api/config',
            'settings': [
                'modal_delay_ms - Time before winner modal appears',
                'modal_auto_close_ms - How long modal stays open', 
                'winner_flash_duration_ms - Winner segment flash duration'
            ]
        },
        'state_management': {
            'description': 'The API now includes comprehensive state checking to prevent double-spins',
            'features': [
                'Thread-safe spin state management',
                'Automatic rejection of concurrent spin requests',
                'Detailed error messages for blocked requests',
                'Real-time status monitoring'
            ]
        }
    })

# ==============================================================================
# DEBUG ROUTES - Remove after testing
# ==============================================================================

@app.route('/debug/prizes')
def debug_prizes():
    """Debug route to check prizes.json loading"""
    try:
        import os
        import json
        
        debug_info = {
            'timestamp': datetime.now().isoformat(),
            'working_directory': os.getcwd(),
            'files_in_directory': [f for f in os.listdir('.') if f.endswith('.json')],
            'wheel_status': wheel_state.get_status()
        }
        
        # Check if prizes.json exists
        prizes_file = 'prizes.json'
        if os.path.exists(prizes_file):
            debug_info['prizes_file_exists'] = True
            debug_info['prizes_file_size'] = os.path.getsize(prizes_file)
            
            # Try to read raw file
            try:
                with open(prizes_file, 'r', encoding='utf-8') as f:
                    raw_content = f.read()
                debug_info['raw_file_length'] = len(raw_content)
                debug_info['raw_file_preview'] = raw_content[:500] + ('...' if len(raw_content) > 500 else '')
                
                # Try to parse JSON
                try:
                    parsed_data = json.loads(raw_content)
                    debug_info['json_parse_success'] = True
                    debug_info['prizes_count'] = len(parsed_data) if isinstance(parsed_data, list) else 'not_a_list'
                    debug_info['first_prize'] = parsed_data[0] if parsed_data and isinstance(parsed_data, list) else None
                except json.JSONDecodeError as e:
                    debug_info['json_parse_error'] = str(e)
                    
            except Exception as e:
                debug_info['file_read_error'] = str(e)
        else:
            debug_info['prizes_file_exists'] = False
        
        # Test load_json_file function
        try:
            prizes_via_function = load_json_file('prizes.json', [])
            debug_info['load_json_file_success'] = True
            debug_info['load_json_file_count'] = len(prizes_via_function)
            debug_info['load_json_file_data'] = prizes_via_function[:3]  # First 3 prizes
        except Exception as e:
            debug_info['load_json_file_error'] = str(e)
            
        # Format as HTML for easy reading
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Prizes Debug Info</title>
            <style>
                body {{ font-family: monospace; margin: 20px; background: #1a1a1a; color: #fff; }}
                pre {{ background: #333; padding: 15px; border-radius: 5px; overflow-x: auto; }}
                .success {{ color: #4CAF50; }}
                .error {{ color: #f44336; }}
                .warning {{ color: #ff9800; }}
            </style>
        </head>
        <body>
            <h1>🔍 Prizes.json Debug Information</h1>
            <pre>{json.dumps(debug_info, indent=2, default=str)}</pre>
            
            <h2>Quick Actions</h2>
            <p><a href="/odds" style="color: #4CAF50;">🎯 Go to Odds Calculator</a></p>
            <p><a href="/dashboard" style="color: #4CAF50;">📊 Go to Dashboard</a></p>
            <p><a href="/api/prizes" style="color: #4CAF50;">🔗 Test Prizes API</a></p>
            <p><a href="/api/odds/prizes" style="color: #4CAF50;">🎲 Test Odds Prizes API</a></p>
            <p><a href="/api/spin/status" style="color: #4CAF50;">⚙️ Test Spin Status API</a></p>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        logging.error(f"💥 Debug route error: {e}")
        return f"Debug route error: {e}", 500

# ==============================================================================
# SOCKET.IO EVENT HANDLERS
# ==============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection with comprehensive logging"""
    try:
        wheel_state.add_client(request.sid)
        logging.info(f"🔌 Client connected: {request.sid} (Total: {len(wheel_state.connected_clients)})")
        
        # Send current state to new client
        socketio.emit('state_update', get_dashboard_state(), room=request.sid)
        socketio.emit('connection_confirmed', {
            'client_id': request.sid,
            'server_time': datetime.now().isoformat(),
            'total_clients': len(wheel_state.connected_clients),
            'wheel_status': wheel_state.get_status()
        }, room=request.sid)
        
    except Exception as e:
        logging.error(f"💥 Connect handler error: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    try:
        wheel_state.remove_client(request.sid)
        logging.info(f"🔌 Client disconnected: {request.sid} (Remaining: {len(wheel_state.connected_clients)})")
    except Exception as e:
        logging.error(f"💥 Disconnect handler error: {e}")

@socketio.on('trigger_spin_from_web')
def handle_web_spin_request(data=None):
    """
    Enhanced web-triggered spin requests with state checking
    This uses the same trigger_spin_flow as all other sources
    """
    try:
        user_info = data.get('user_info', 'anonymous') if data else 'web_client'
        
        # Log the request
        logging.info(f"🌐 Web spin request from client {request.sid}: {user_info}")
        
        # Use the same trigger function as all other sources
        success = trigger_spin_flow(source='web_interface', user_data=user_info)
        
        if not success:
            logging.warning(f"🌐 Web spin from {request.sid} was rejected")
            
    except Exception as e:
        logging.error(f"💥 Web spin request error: {e}")
        socketio.emit('spin_error', {'message': f'Spin request failed: {str(e)}'})

@socketio.on('request_state_update')
def handle_state_request():
    """Handle state update requests"""
    try:
        socketio.emit('state_update', get_dashboard_state(), room=request.sid)
    except Exception as e:
        logging.error(f"💥 State request error: {e}")

# ==============================================================================
# ERROR HANDLERS
# ==============================================================================

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    logging.error(f"💥 Internal server error: {error}")
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle not found errors"""
    return jsonify({'error': 'Not found', 'message': 'Endpoint not found'}), 404

@app.errorhandler(413)
def file_too_large(error):
    """Handle file too large errors"""
    return jsonify({'error': 'File too large', 'message': 'File exceeds 16MB limit'}), 413

@app.errorhandler(400)
def bad_request(error):
    """Handle bad request errors"""
    return jsonify({'error': 'Bad request', 'message': str(error)}), 400

# ==============================================================================
# STARTUP AND INITIALIZATION
# ==============================================================================

def initialize_default_files():
    """Initialize default configuration files if they don't exist"""
    try:
        # Enhanced default configuration with timing settings
        default_config = {
            "spin_duration_seconds": 8,
            "cooldown_seconds": 3,
            "volume": 75,
            "button_pin": 17,
            "system_sounds": {
                "spin": "/static/sounds/spin.mp3",
                "winner": "/static/sounds/victory.mp3",
                "loser": "/static/sounds/try-again.mp3"
            },
            "modal_delay_ms": 3000,
            "modal_auto_close_ms": 10000,
            "winner_flash_duration_ms": 4000,
            "display_settings": {
                "enable_confetti": True,
                "show_instructions": False,
                "show_stats": True,
                "animation_speed": "normal"
            },
            "event_settings": {
                "max_concurrent_users": 50,
                "session_timeout_minutes": 30,
                "auto_backup_interval_minutes": 15
            },
            "audio_settings": {
                "enable_sound_effects": True,
                "master_volume": 75,
                "fade_in_duration": 0.5,
                "fade_out_duration": 0.3
            },
            "error_handling": {
                "max_retry_attempts": 3,
                "retry_delay_seconds": 2,
                "fallback_mode_enabled": True,
                "log_level": "INFO"
            }
        }
        
        # Default prizes (if none exist)
        default_prizes = [
            {
                "name": "$50 Castle Card",
                "description": "Great Spin! Major cash prize!",
                "weight": 0.5,
                "color": "#FFD700",
                "is_winner": True,
                "sound_path": "/static/sounds/victory.mp3",
                "enabled": True,
                "id": "1"
            },
            {
                "name": "Try Again",
                "description": "Better luck next time!",
                "weight": 10,
                "color": "#9E9E9E",
                "is_winner": False,
                "sound_path": "/static/sounds/try-again.mp3",
                "enabled": True,
                "id": "2"
            }
        ]
        
        # Initialize files
        config = load_json_file('config.json', default_config)
        prizes = load_json_file('prizes.json', default_prizes)
        history = load_json_file('history.json', [])
        
        logging.info(f"🔒 Configuration initialized: {len(prizes)} prizes, {len(history)} history records")
        logging.info(f"⏱️ Timing defaults: modal_delay={config.get('modal_delay_ms', 'not set')}ms")
        
    except Exception as e:
        logging.error(f"💥 File initialization error: {e}")

if __name__ == '__main__':
    # Initialize the application
    try:
        initialize_default_files()
        setup_gpio()
        
        logging.info("🎪 PRIZE WHEEL - CASTLE KINGDOM EDITION 🎪")
        logging.info("=" * 60)
        logging.info(f"🌍 Main Display: http://0.0.0.0:5000/")
        logging.info(f"📊 Dashboard:    http://0.0.0.0:5000/dashboard")
        logging.info(f"🎯 Odds Calculator: http://0.0.0.0:5000/odds")
        logging.info(f"⚙️ GPIO Mode:    {'ENABLED' if GPIO_AVAILABLE else 'SIMULATION'}")
        logging.info(f"📱 QR Code API:  http://0.0.0.0:5000/api/qr_code")
        logging.info(f"🎵 Sound Upload: http://0.0.0.0:5000/api/upload/sound")
        logging.info(f"🎲 Remote Spin:  http://0.0.0.0:5000/api/spin")
        logging.info(f"📡 Spin Status:  http://0.0.0.0:5000/api/spin/status")
        logging.info(f"🔍 Debug Info:   http://0.0.0.0:5000/debug/prizes")
        logging.info(f"⏱️ Configurable: Modal timing via dashboard settings")
        logging.info(f"🛡️ State Management: Enhanced thread-safe spin protection")
        logging.info("=" * 60)
        logging.info("🚀 Starting server for event deployment...")
        
        # Start the server
        socketio.run(app, host='0.0.0.0', port=5000, 
                    debug=False, allow_unsafe_werkzeug=True)
                    
    except KeyboardInterrupt:
        logging.info("🛑 Server shutdown requested")
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
                logging.info("🧹 GPIO cleanup completed")
            except:
                pass
        logging.info("✅ Clean shutdown complete")
        
    except Exception as e:
        logging.error(f"💥 Server startup failed: {e}")
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except:
                pass
