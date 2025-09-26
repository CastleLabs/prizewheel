# Prize Wheel Application

A Flask-based prize wheel application with real-time WebSocket communication, configurable timing, and hardware GPIO support for Raspberry Pi deployments.

## System Architecture

### Backend (Python/Flask)
- **Framework**: Flask with Flask-SocketIO for WebSocket support
- **Threading**: Thread-safe state management using threading.Lock
- **File Storage**: JSON-based data persistence with atomic writes
- **GPIO Support**: Optional Raspberry Pi GPIO integration for hardware buttons
- **Logging**: Comprehensive logging with file and console output

### Frontend (HTML/JavaScript)
- **Real-time Communication**: Socket.IO client for bidirectional communication
- **Canvas Rendering**: HTML5 Canvas for wheel graphics and animations
- **Audio Management**: Preloaded audio with error handling
- **State Management**: Client-side wheel state tracking to prevent race conditions

## Core Features

### Spin Management
- **Thread-safe spin state**: Prevents concurrent spins using atomic operations
- **Multiple input sources**: Web interface, REST API, hardware GPIO buttons
- **Configurable timing**: Spin duration, cooldown periods, and modal display timing
- **Audio integration**: System sounds and prize-specific audio files

### Prize Configuration
- **Dynamic prize management**: Add, edit, delete, enable/disable prizes
- **Weighted probability**: Configurable weights for prize selection
- **Visual customization**: Colors, descriptions, and custom audio per prize
- **Real-time updates**: Changes propagate immediately to connected clients

### Data Management
- **History tracking**: Complete spin history with timestamps and metadata
- **CSV export**: Export spin data for analysis
- **Backup system**: Automatic file backups before critical operations
- **Data validation**: Input validation and corruption recovery

## Installation

### Requirements
```
Python 3.7+
Flask
Flask-SocketIO
qrcode
RPi.GPIO (optional, for hardware support)
```

### Setup
```bash
git clone <repository-url>
cd prize-wheel
pip install -r requirements.txt
python app.py
```

### Hardware Requirements (Optional)
- Raspberry Pi with GPIO pins
- Hardware button connected to configurable GPIO pin (default: GPIO 17)
- Pull-up resistor configuration

## Configuration

### config.json Structure
```json
{
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
  "winner_flash_duration_ms": 4000
}
```

### prizes.json Structure
```json
[
  {
    "id": "unique-id",
    "name": "Prize Name",
    "description": "Prize description",
    "weight": 1.0,
    "color": "#FF6B6B",
    "is_winner": true,
    "enabled": true,
    "sound_path": "/static/sounds/custom.mp3"
  }
]
```

## API Endpoints

### Spin Control
- `POST /api/spin` - Trigger wheel spin
- `GET /api/spin/status` - Get current wheel status
- `GET /api/spin` - API documentation

### Prize Management
- `GET /api/prizes` - Retrieve all prizes
- `POST /api/prizes` - Create new prize
- `PUT /api/prizes/{id}` - Update existing prize
- `DELETE /api/prizes/{id}` - Delete prize

### Configuration
- `POST /api/config` - Update system configuration
- `GET /api/dashboard_data` - Comprehensive system state

### Data Operations
- `GET /api/export/csv` - Export spin history as CSV
- `DELETE /api/stats` - Clear spin history

### Utilities
- `GET /api/qr_code` - Generate QR code for mobile access
- `GET /api/sounds/list` - List available audio files
- `POST /api/upload/sound` - Upload audio file

## WebSocket Events

### Client to Server
- `trigger_spin_from_web` - Request spin from web interface
- `request_state_update` - Request current system state

### Server to Client
- `spin_started` - Spin animation initiated
- `spin_complete` - Spin finished with winner data
- `spin_rejected` - Spin request denied (wheel busy)
- `spin_error` - Error during spin process
- `state_update` - System state changes
- `connection_confirmed` - Client connection established

## State Management

### WheelState Class
```python
class WheelState:
    is_spinning: bool          # Spin animation active
    connected_clients: set     # Active WebSocket connections
    last_winner: str           # Most recent winner name
    total_spins_session: int   # Spins since server start
    performance_metrics: dict  # System performance data
```

### Thread Safety
- All state modifications use `threading.Lock`
- Atomic operations for spin start/stop
- Race condition prevention for concurrent requests

### Frontend State
```javascript
wheelSpinState = {
    isSpinning: false,     // Wheel animation running
    modalVisible: false,   // Winner modal displayed
    cooldownActive: false  // Post-spin cooldown period
}
```

## File Structure
```
/
├── app.py                 # Main Flask application
├── config.json          # System configuration
├── prizes.json          # Prize definitions
├── history.json          # Spin history
├── templates/
│   ├── display.html      # Main wheel interface
│   ├── dashboard.html    # Management interface
│   └── odds_calculator.html # Probability analysis
├── static/
│   ├── sounds/           # Audio files
│   └── images/           # Image assets
└── requirements.txt      # Python dependencies
```

## Audio System

### Supported Formats
- MP3, WAV, OGG, M4A, AAC
- Maximum file size: 16MB

### Audio Management
- Preloaded audio for reduced latency
- Volume control and error handling
- Prize-specific and system sound separation

## Security Considerations

### Input Validation
- File upload restrictions
- JSON data validation
- SQL injection prevention (N/A - no database)

### File Operations
- Atomic writes with temporary files
- Backup creation before modifications
- Error recovery mechanisms

## Deployment

### Development
```bash
python app.py
```
Access at: http://localhost:5000

### Production Considerations
- Use production WSGI server (Gunicorn, uWSGI)
- Configure reverse proxy (Nginx)
- Set appropriate file permissions
- Monitor log files and disk usage

### Raspberry Pi Deployment
1. Enable GPIO access for application user
2. Configure hardware button wiring
3. Set GPIO pin in config.json
4. Test hardware integration

## Troubleshooting

### Common Issues
- **GPIO not available**: Check RPi.GPIO installation and permissions
- **Audio not playing**: Verify file paths and browser audio permissions
- **Concurrent spin errors**: Check thread safety and state management logs
- **File corruption**: Review backup files and recovery procedures

### Logging
- Application logs: `prize_wheel.log`
- Log levels: DEBUG, INFO, WARNING, ERROR
- Real-time log monitoring for production deployments

### Debug Endpoints
- `/debug/prizes` - Prize data validation and file status
- `/api/performance` - System performance metrics
- `/api/spin/status` - Detailed wheel state information

## Performance Optimization

### Frontend
- Canvas rendering optimization
- Audio preloading
- Efficient animation loops
- Minimal DOM manipulation

### Backend
- Thread-safe operations
- Atomic file operations
- Connection pooling for WebSockets
- Memory-efficient data structures

## Browser Compatibility
- Modern browsers with Canvas and WebSocket support
- Mobile device compatibility
- Touch event handling
- Responsive design considerations
