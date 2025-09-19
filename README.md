# Prize Wheel System for Raspberry Pi 5

[![GitHub repo stars](https://img.shields.io/github/stars/CastleLabs/prizewheel?style=social)](https://github.com/CastleLabs/prizewheel/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/CastleLabs/prizewheel?style=social)](https://github.com/CastleLabs/prizewheel/network/members)
[![GitHub issues](https://img.shields.io/github/issues/CastleLabs/prizewheel)](https://github.com/CastleLabs/prizewheel/issues)

A robust, production-ready Prize Wheel application designed to run as a dedicated kiosk on a **Raspberry Pi 5 with a CLI-only OS**. The system features a rich web-based administration panel, real-time hardware monitoring, and physical GPIO button integration.

This project is engineered to be an appliance. After setup, it automatically boots into a full-screen Chromium browser, displaying the prize wheel and ready for interaction, while the backend is managed by secure, auto-restarting `systemd` services.


## ✨ Features

### Software Features

* **Server-Side Winner Determination**: All prize-winning logic is handled securely on the server to prevent any client-side manipulation.
* **Real-time Web Interface**: Uses `Flask-SocketIO` for instant communication between the server and the display client.
* **Comprehensive Admin Dashboard**: A secure, web-based dashboard to:
    * Manage prizes (add, edit, delete), including names, descriptions, colors, and winning weights.
    * View recent spin history and statistics.
    * Monitor **real-time Raspberry Pi 5 system health** (CPU Usage, Temperature, Memory, Disk Space).
    * Upload custom sound files for each prize.
* **Production-Grade Stack**:
    * Runs on `Gunicorn` behind an `Nginx` reverse proxy for performance and security.
    * Managed by `systemd` services for reliability, auto-starting on boot and restarting on failure.
* **Kiosk Mode on CLI OS**: The setup script installs a minimal X11 server to launch a hardware-accelerated Chromium browser in kiosk mode, avoiding the overhead of a full desktop environment.
* **Database**: Uses `SQLite` with `Flask-SQLAlchemy` for easy setup and management.
* **Security**: Pre-configured with a UFW firewall, Fail2Ban for SSH protection, and secure file permissions.

### Hardware Features

* **Physical Spin Button**: Integrated with Raspberry Pi's GPIO pins. A physical button can be connected to trigger a spin.
* **Status LED**: A GPIO-connected LED indicates when the wheel is spinning.
* **Pi 5 Optimized**: The entire stack, from the Linux kernel parameters in `/boot/config.txt` to the Chromium launch flags, is optimized for the Raspberry Pi 5's hardware.
* **Enhanced Audio Support**: The system is configured to handle audio playback through HDMI or the 3.5mm jack for prize-specific sounds.

---

## 🏗️ System Architecture

```
+-------------------+      +------------------+      +------------------+
| Physical Hardware |      |     Clients      |      |      Admin       |
| (GPIO Button/LED) |<---->| (Chromium Kiosk) |      | (Web Browser)    |
+-------------------+      +--------+---------+      +--------+---------+
        ^                           |                        |
        | GPIO Events               | HTTP / WebSocket       | HTTP
        v                           v                        v
+----------------------------------+----------------------------------+
| Raspberry Pi 5 (CLI OS)                                             |
| +-----------------------------------------------------------------+ |
| | Nginx (Reverse Proxy, Port 80)                                  | |
| | Serves Static Files | Proxies to Gunicorn                       | |
| +---------------------+-------------------------------------------+ |
|                       |                                             |
|                       v                                             |
| +-----------------------------------------------------------------+ |
| | Gunicorn (WSGI Server)                                          | |
| | +-------------------------------------------------------------+ | |
| | | Flask Application (app.py)                                  | | |
| | | +------------------+   +------------------+   +-------------+ | | |
| | | |   API Routes     |<->|  Business Logic  |<->|  Database   | | | |
| | | | (Prize Mgmt, Spin) | | (Winner Calc)    | | (SQLite)    | | | |
| | | +------------------+   +------------------+   +-------------+ | | |
| | | |   SocketIO Events  |<---------------------->|   GPIO      | | | |
| | | | (Spin Start/End) |                      | (Handler)   | | | |
| | | +------------------+                      +-------------+ | | |
| | +-------------------------------------------------------------+ | |
| +-----------------------------------------------------------------+ |
+---------------------------------------------------------------------+
```

---

## 🛠️ Technology Stack

### Backend
* **Framework**: Flask
* **Real-time Communication**: Flask-SocketIO
* **WSGI Server**: Gunicorn
* **Web Server / Reverse Proxy**: Nginx
* **Database ORM**: Flask-SQLAlchemy
* **System Monitoring**: psutil
* **Hardware Interface**: RPi.GPIO

### Frontend
* **Rendering**: HTML5, CSS3
* **Wheel Animation**: HTML5 Canvas API
* **Interactivity**: JavaScript (ES6)
* **Real-time Client**: Socket.IO Client

### DevOps & System
* **OS**: Raspberry Pi OS (Bookworm, CLI-only recommended)
* **Process Management**: systemd
* **Firewall**: UFW
* **Intrusion Prevention**: Fail2Ban
* **Deployment**: Bash (`setup.sh`)

---

## 📋 Hardware Requirements

1. **Raspberry Pi 5**: Recommended for best performance.
2. **MicroSD Card**: 16GB or larger, high-speed recommended.
3. **Power Supply**: Official Raspberry Pi 5 27W USB-C Power Supply.
4. **Display**: Any HDMI-compatible monitor.
5. **(Optional) Hardware Button**:
    * 1 x Momentary Push Button.
    * Jumper Wires.
6. **(Optional) LED**:
    * 1 x Standard LED (e.g., 5mm red).
    * 1 x 330Ω Resistor.

### GPIO Connections

The default pin configuration is set in the `.env` file during setup.

* **Spin Button**: Connect between **GPIO 17** (Pin 11) and **Ground** (e.g., Pin 9).
* **Status LED**: Connect the anode (longer leg) to **GPIO 27** (Pin 13) and the cathode (shorter leg) through a **330Ω resistor** to **Ground** (e.g., Pin 14).

---

## 🚀 Setup and Installation

This project is designed for a **fresh installation of Raspberry Pi OS Lite (CLI-only)**. The setup script will install all necessary graphical, audio, and web server components.

**1. Clone the Repository:**
```bash
git clone https://github.com/CastleLabs/prizewheel.git
cd prizewheel
```

**2. Make the Setup Script Executable:**
```bash
chmod +x setup.sh
```

**3. Run the Setup Script:**

⚠️ **Warning**: The script will install packages, modify system configuration files, and set up services. It should NOT be run as root. It will ask for your password for sudo commands when needed.

```bash
./setup.sh
```

The script will perform the following actions:

* Update and upgrade system packages.
* Install a minimal X11 server, window manager, and Chromium browser.
* Install Nginx, Python 3, and all required libraries.
* Set up a Python virtual environment.
* Configure Nginx as a reverse proxy.
* Create and enable systemd services for the application and kiosk display.
* Configure the system for automatic login and kiosk launch on boot.
* Set up UFW firewall rules.
* Generate a secure `.env` configuration file.

**4. Reboot:**
After the script completes, it will prompt you to reboot.

```bash
sudo reboot
```

Upon rebooting, the Raspberry Pi will automatically start all services and launch the prize wheel display in full-screen mode.

---

## 📖 Usage

### Kiosk Display
The prize wheel will be displayed on the monitor connected to the Pi. It can be operated by:

* Clicking the "Spin Wheel" button on the screen.
* Pressing the physical hardware button if connected.

### Admin Panel
1. Find the Raspberry Pi's IP address by running `hostname -I` in the terminal.
2. From another computer on the same network, navigate to `http://<YOUR_PI_IP_ADDRESS>/admin`.
3. Log in with the default credentials:
   * **Username**: `admin`
   * **Password**: `admin123`

⚠️ **IMPORTANT**: Change the default password immediately after your first login for security!

---

## 🔌 API Endpoints

The application exposes a RESTful API for managing prizes and controlling the wheel. Admin authentication is required for all endpoints.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/prizes` | Get a list of all prizes. |
| POST | `/api/prizes` | Create a new prize. |
| PUT | `/api/prizes/<id>` | Update an existing prize. |
| DELETE | `/api/prizes/<id>` | Delete a prize. |
| POST | `/api/upload/sound` | Upload a sound file for a prize. |
| POST | `/api/wheel/spin` | Trigger a wheel spin via the API. |
| DELETE | `/api/stats` | Clear all spin history records. |
| GET | `/api/export/csv` | Export all spin history to a CSV file. |
| GET | `/api/health` | Get a detailed system health check (JSON). |

---


## 👨‍💻 Author

**Seth Morrow** - [CastleLabs](https://github.com/CastleLabs)
