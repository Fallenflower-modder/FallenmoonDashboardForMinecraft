import asyncio
import websockets
import json
import psutil
import os
import subprocess
import time
import traceback
import wmi
import socket
import platform
from datetime import datetime
from .server_manager import ServerManager
from .event_bus import event_bus
from .event_types import *

# Try to import win32pdh and pythoncom for Windows performance counters
try:
    import win32pdh
    import pythoncom
    win32pdh_available = True
except ImportError as e:
    print(f"Failed to import win32pdh or pythoncom: {e}")
    win32pdh_available = False

# Global variables
connected_clients = set()
server_processes = {}
server_info = {}
current_client = None

# Persistent RCON connection for status monitoring
persistent_rcon_client = None
persistent_rcon_server = None

# Data rotation counter for轮流获取数据
# 0: TPS (via tps command), 1: MSPT (via mspt command), 2: Players (via list command)
rotation_counter = 0

# Server startup completion flag
# Dictionary to track if each server has completed startup
server_startup_completed = {}

# Log cache for each server
# Stores log lines from server start until client connects or startup completes
log_caches = {}

# Previous advanced data values
# Stores the last successfully retrieved values for TPS, MSPT, and players
previous_advanced_data = {
    'tps': '--',
    'mspt': '--',
    'players_online': '--',
    'players_max': '--'
}

# Log rate limiting settings
# Maximum number of log lines to send per second
LOG_RATE_LIMIT = 100
# Dictionary to track log rate for each client
# Key: client websocket, Value: tuple (last_reset_time, line_count)
log_rate_counters = {}
# Dictionary to track if we've already sent a warning for this second
warning_sent = {}

# RCON protocol constants
RCON_TYPE_AUTH = 3
RCON_TYPE_AUTH_RESPONSE = 2
RCON_TYPE_COMMAND = 2
RCON_TYPE_RESPONSE_VALUE = 0

class RCONClient:
    """RCON client for Minecraft servers"""
    
    def __init__(self, host='localhost', port=25575, password=''):
        self.host = host
        self.port = int(port)  # Ensure port is integer
        self.password = password
        self.socket = None
    
    def connect(self):
        """Connect to the RCON server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.host, self.port))
            return True
        except Exception as e:
            print(f"Failed to connect to RCON: {e}")
            return False
    
    def authenticate(self):
        """Authenticate with the RCON server"""
        if not self.socket:
            if not self.connect():
                return False
        
        try:
            # Send auth request
            auth_packet = self._build_packet(1, RCON_TYPE_AUTH, self.password)
            self.socket.send(auth_packet)
            
            # Receive response
            response = self._receive_packet()
            if response['request_id'] == -1:
                return False  # Authentication failed
            return True
        except Exception as e:
            print(f"RCON authentication failed: {e}")
            return False
    
    def send_command(self, command):
        """Send a command to the RCON server"""
        if not self.socket:
            if not self.connect():
                return None
        
        try:
            # Send command packet
            command_packet = self._build_packet(2, RCON_TYPE_COMMAND, command)
            self.socket.send(command_packet)
            
            # Receive response
            response = self._receive_packet()
            return response['payload']
        except Exception as e:
            print(f"Failed to send RCON command: {e}")
            return None
    
    def close(self):
        """Close the RCON connection"""
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                print(f"Error closing RCON socket: {e}")
            self.socket = None
    
    def _build_packet(self, request_id, packet_type, payload):
        """Build an RCON packet"""
        # Packet structure: Length (4 bytes) + Request ID (4 bytes) + Type (4 bytes) + Payload + 2 null bytes
        payload_bytes = payload.encode('utf-8')
        packet_size = 4 + 4 + len(payload_bytes) + 2  # Request ID + Type + Payload + 2 null bytes
        
        packet = bytearray()
        packet.extend(packet_size.to_bytes(4, byteorder='little'))
        packet.extend(request_id.to_bytes(4, byteorder='little'))
        packet.extend(packet_type.to_bytes(4, byteorder='little'))
        packet.extend(payload_bytes)
        packet.extend(b'\x00\x00')  # Two null bytes at the end
        
        return packet
    
    def _receive_packet(self):
        """Receive an RCON packet"""
        # Read length
        length_bytes = self.socket.recv(4)
        if not length_bytes:
            raise ConnectionError("Connection closed by server")
        
        length = int.from_bytes(length_bytes, byteorder='little')
        
        # Read the rest of the packet
        packet = self.socket.recv(length)
        if len(packet) < length:
            raise ConnectionError("Incomplete packet received")
        
        # Parse packet
        request_id = int.from_bytes(packet[:4], byteorder='little')
        packet_type = int.from_bytes(packet[4:8], byteorder='little')
        payload = packet[8:-2].decode('utf-8', errors='replace')
        
        return {
            'request_id': request_id,
            'type': packet_type,
            'payload': payload
        }

async def send_message_with_log(websocket, data):
    """Send message to client and log it"""
    try:
        # Convert data to JSON string
        message = json.dumps(data) if isinstance(data, dict) else data
        
        # Send message to client
        await websocket.send(message)
        
        # Log the message
        print(f"[Packet Sent] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Type: {data.get('type', 'unknown')}")
        print(f"[Packet Content] {message[:500]}{'...' if len(message) > 500 else ''}")
    except Exception as e:
        # Check if it's a normal close (1000, 1001) to avoid spamming logs
        error_str = str(e)
        if "1000" not in error_str and "1001" not in error_str:
            print(f"Error sending message: {e}")

async def handle_client(*args):
    global current_client
    
    # Get websocket object (works with both 1 and 2 argument signatures)
    websocket = args[0]
    
    # Check if there's already a connected client
    if current_client is not None:
        await websocket.close(code=1008, reason="Another client is already connected")
        return
    
    # Set this client as the current client
    current_client = websocket
    
    # Start heartbeat task for this client
    heartbeat_task = asyncio.create_task(send_heartbeat(websocket))
    
    try:
        # Publish client connected event
        await event_bus.publish(CLIENT_CONNECTED, websocket=websocket)
        
        async for message in websocket:
            await process_message(websocket, message)
    except websockets.exceptions.ConnectionClosedError:
        # Expected close, do nothing
        pass
    except Exception as e:
        print(f"Error handling client: {e}")
    finally:
        # Publish client disconnected event
        await event_bus.publish(CLIENT_DISCONNECTED, websocket=websocket)
        
        # Clean up when client disconnects
        heartbeat_task.cancel()
        current_client = None
        # Reset advanced data values
        global previous_advanced_data
        previous_advanced_data = {
            'tps': '--',
            'mspt': '--',
            'players_online': '--',
            'players_max': '--'
        }
        # Remove all server processes tracked for this client
        server_processes.clear()

async def process_message(websocket, message):
    """Process incoming messages from clients"""
    try:
        data = json.loads(message)
        action = data.get('action')
        
        # Publish message events instead of direct function calls
        if action == 'refresh_servers':
            await event_bus.publish(REFRESH_SERVERS, websocket=websocket)
        elif action == 'connect_server':
            await event_bus.publish(SERVER_CONNECTED, websocket=websocket, data=data)
        elif action == 'execute_command':
            await event_bus.publish(COMMAND_EXECUTED, websocket=websocket, data=data)
        elif action == 'stop_server':
            await event_bus.publish(SERVER_STOPPED, websocket=websocket, data=data)
        elif action == 'start_server':
            await event_bus.publish(SERVER_STARTED, websocket=websocket, data=data)
        elif action == 'search_servers':
            await event_bus.publish('search.servers', websocket=websocket)
        elif action == 'select_server':
            await event_bus.publish('server.selected', websocket=websocket, data=data)
        elif action == 'save_config':
            await event_bus.publish('config.save', websocket=websocket, data=data)
        elif action == 'get_components':
            await event_bus.publish('components.get', websocket=websocket, data=data)
        elif action == 'delete_schematic':
            await event_bus.publish('schematic.delete', websocket=websocket, data=data)
            
    except json.JSONDecodeError:
        await send_message_with_log(websocket, {'error': 'Invalid JSON format'})

async def on_refresh_servers(**kwargs):
    """Handle refresh_servers event"""
    websocket = kwargs.get('websocket', current_client)
    if not websocket:
        return
    
    # Format server list with display names from version.json
    formatted_servers = []
    for server_name in server_processes.keys():
        # Get server info from server_info map
        server_info_data = server_info.get(server_name, {})
        display_name = server_info_data.get('server_name', server_name)
        
        formatted_servers.append({
            'name': server_name,
            'display_name': display_name
        })
    
    await send_message_with_log(websocket, {
        'type': 'server_list',
        'servers': formatted_servers
    })

# Alias for backward compatibility
refresh_servers = on_refresh_servers

async def on_server_connected(**kwargs):
    """Handle server.connected event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    if server_name in server_processes:
        try:
            # Get server path
            server_path = os.path.join('cached_minecraft_servers', server_name)
            
            # Read server info from Fallenmoon/version.json
            version_file = os.path.join(server_path, 'Fallenmoon', 'version.json')
            server_info_data = {}
            
            if os.path.exists(version_file):
                with open(version_file, 'r', encoding='utf-8') as f:
                    server_info_data = json.load(f)
            
            # Check if spark is installed
            spark_installed = False
            # Check mods directory
            mods_dir = os.path.join(server_path, 'mods')
            if os.path.exists(mods_dir):
                for file in os.listdir(mods_dir):
                    if file.startswith('spark-') and file.endswith('.jar'):
                        spark_installed = True
                        break
            
            # Check plugins directory if not found in mods
            if not spark_installed:
                plugins_dir = os.path.join(server_path, 'plugins')
                if os.path.exists(plugins_dir):
                    for file in os.listdir(plugins_dir):
                        if file.startswith('spark-') and file.endswith('.jar'):
                            spark_installed = True
                            break
            
            # Reset advanced data values when connecting to a new server
            global previous_advanced_data
            previous_advanced_data = {
                'tps': '--',
                'mspt': '--',
                'players_online': '--',
                'players_max': '--'
            }
            
            # Store server info with spark status
            server_info[server_name] = {
                **server_info_data,
                'spark_installed': spark_installed
            }
            
            # Check if server has already completed startup by scanning existing logs
            try:
                logs_dir = os.path.join(server_path, 'logs')
                latest_log = os.path.join(logs_dir, 'latest.log')
                if os.path.exists(latest_log):
                    with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            if "Done (" in line and "s)! For help, type " in line and "help" in line or "Server Started!" in line:
                                # Server has completed startup, set the flag
                                server_startup_completed[server_name] = True
                                print(f"Server {server_name} has already completed startup, detected from connect_server")
                                break
            except Exception as e:
                print(f"Error checking server startup status: {e}")
            
            # Send confirmation
            await send_message_with_log(websocket, {
                'type': 'connect_success',
                'server': server_info[server_name]
            })
            
            # Start log streaming for this server
            asyncio.create_task(stream_server_logs(websocket, server_path))
            
        except Exception as e:
            await send_message_with_log(websocket, {
                'type': 'error',
                'message': f'Failed to connect to server: {str(e)}'
            })

# Alias for backward compatibility
connect_server = on_server_connected

async def on_command_executed(**kwargs):
    """Handle command.executed event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    command = data.get('command')
    
    if not server_processes:
        await send_message_with_log(websocket, {
            'type': 'command_result',
            'result': 'No server is running'
        })
        return
    
    # Get first connected server (assuming only one server is connected at a time)
    server_name = list(server_processes.keys())[0]
    server_info_data = server_info.get(server_name, {})
    
    # Get RCON credentials from server_info
    rcon_port = server_info_data.get('rcon_port', 25575)
    rcon_password = server_info_data.get('rcon_password', '')
    
    if not rcon_password:
        await send_message_with_log(websocket, {
            'type': 'command_result',
            'result': 'RCON password not found'
        })
        return
    
    # Use a new temporary RCON connection for executing user commands
    # This ensures user commands don't interfere with the persistent status monitoring connection
    rcon_client = RCONClient(host='localhost', port=rcon_port, password=rcon_password)
    result = None
    
    try:
        if rcon_client.connect() and rcon_client.authenticate():
            result = rcon_client.send_command(command)
            if result is None:
                result = 'Failed to execute command'
        else:
            result = 'Failed to connect to RCON server'
    except Exception as e:
        result = f'Error executing command: {str(e)}'
    finally:
        rcon_client.close()
    
    # Check if command is 'stop'
    if command.strip().lower() == 'stop':
        # Command is 'stop', perform additional cleanup
        print(f"User executed stop command on server {server_name}, performing cleanup")
        
        # Close persistent RCON connection for status monitoring
        global persistent_rcon_client, persistent_rcon_server
        if persistent_rcon_client:
            persistent_rcon_client.close()
            persistent_rcon_client = None
            persistent_rcon_server = None
        
        # Reset server startup status
        if server_name in server_startup_completed:
            server_startup_completed[server_name] = False
        
        # Reset previous advanced data values
        global previous_advanced_data
        previous_advanced_data = {
            'tps': '--',
            'mspt': '--',
            'players_online': '--',
            'players_max': '--'
        }
        
        # Notify client to update status
        await send_message_with_log(websocket, {
            'type': 'server_stopped',
            'server_name': server_name
        })
        
        # Publish server stopped event
        await event_bus.publish(SERVER_STOPPED, websocket=websocket, data={'server_name': server_name})
    
    await send_message_with_log(websocket, {
        'type': 'command_result',
        'result': result
    })

# Alias for backward compatibility
execute_command = on_command_executed

async def on_server_stopped(**kwargs):
    """Handle server.stopped event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    if server_name in server_processes:
        try:
            # Get server info
            server_info_data = server_info.get(server_name, {})
            rcon_port = server_info_data.get('rcon_port', 25575)
            rcon_password = server_info_data.get('rcon_password', '')
            
            # Get the process object
            process_info = server_processes[server_name]
            process = process_info.get('process')
            
            # First try to stop server via RCON
            if rcon_password and process:
                rcon_client = RCONClient(host='localhost', port=rcon_port, password=rcon_password)
                try:
                    if rcon_client.connect() and rcon_client.authenticate():
                        rcon_client.send_command('stop')
                        print(f"Sent stop command to server {server_name} via RCON")
                except Exception as e:
                    print(f"Failed to send stop command via RCON: {e}")
                finally:
                    rcon_client.close()
            
            # Wait for 30 seconds before checking if process is still running
            if process:
                print(f"Waiting for server {server_name} to stop...")
                await asyncio.sleep(30)
                
                # Check if process is still running
                try:
                    process_status = process.poll()
                    if process_status is None:
                        # Process is still running, force terminate
                        print(f"Server {server_name} is still running, forcing termination...")
                        process.kill()
                        # Wait for process to terminate
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            print(f"Failed to kill server {server_name} after 5 seconds")
                    else:
                        print(f"Server {server_name} stopped successfully")
                except Exception as e:
                    print(f"Error checking process status: {e}")
        except Exception as e:
            print(f"Error stopping server {server_name}: {e}")
        finally:
            # Remove from process list
            del server_processes[server_name]
            if server_name in server_info:
                del server_info[server_name]
            await send_message_with_log(websocket, {
                'type': 'server_stopped',
                'server_name': server_name
            })

# Alias for backward compatibility
stop_server = on_server_stopped

async def on_server_started(**kwargs):
    """Handle server.started event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    
    try:
        # Get server path
        server_path = os.path.join('cached_minecraft_servers', server_name)
        
        # Check if server directory exists
        if not os.path.exists(server_path):
            await send_message_with_log(websocket, {
                'type': 'error',
                'message': f'Server directory not found: {server_path}'
            })
            return
        
        # Start the server with a visible console window
        # Use CREATE_NEW_CONSOLE flag to show the console window
        process = subprocess.Popen(
            ['cmd.exe', '/c', 'server_start.bat'],
            cwd=server_path,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        # Read server info from Fallenmoon/version.json
        version_file = os.path.join(server_path, 'Fallenmoon', 'version.json')
        server_info_data = {}
        
        if os.path.exists(version_file):
            with open(version_file, 'r', encoding='utf-8') as f:
                server_info_data = json.load(f)
        
        # Check if spark is installed
        spark_installed = False
        # Check mods directory
        mods_dir = os.path.join(server_path, 'mods')
        if os.path.exists(mods_dir):
            for file in os.listdir(mods_dir):
                if file.startswith('spark-') and file.endswith('.jar'):
                    spark_installed = True
                    break
        
        # Check plugins directory if not found in mods
        if not spark_installed:
            plugins_dir = os.path.join(server_path, 'plugins')
            if os.path.exists(plugins_dir):
                for file in os.listdir(plugins_dir):
                    if file.startswith('spark-') and file.endswith('.jar'):
                        spark_installed = True
                        break
        
        # Store server info with spark status
        server_info[server_name] = {
            **server_info_data,
            'spark_installed': spark_installed
        }
        
        # Add server to the process list
        server_processes[server_name] = {
            'name': server_name,
            'pid': process.pid,  # Save the actual PID
            'process': process,  # Save the process object
            'status': 'running'
        }
        
        # Start log monitoring for this server immediately after starting
        asyncio.create_task(monitor_server_logs(server_path, server_name))
        
        # Send confirmation
        await send_message_with_log(websocket, {
            'type': 'server_started',
            'server_name': server_name
        })
        
        # Send updated server list
        await on_refresh_servers(websocket=websocket)
        
    except Exception as e:
        await send_message_with_log(websocket, {
            'type': 'error',
            'message': f'Failed to start server: {str(e)}'
        })

# Alias for backward compatibility
start_server = on_server_started

async def on_search_servers(**kwargs):
    """Handle search.servers event"""
    websocket = kwargs.get('websocket', current_client)
    if not websocket:
        return
    
    servers = ServerManager.scan_servers()
    
    # Format servers for client
    formatted_servers = []
    for server in servers:
        # Get the actual display name from version.json
        server_info = server['info']
        display_name = server_info.get('server_name', server['name'])
        
        if not server['valid']:
            display_name = f"{display_name} - {server['reason']}"
        
        formatted_servers.append({
            'name': server['name'],
            'display_name': display_name,
            'valid': server['valid'],
            'reason': server['reason'],
            'info': server_info  # Include full server info
        })
    
    await send_message_with_log(websocket, {
        'type': 'server_search_result',
        'servers': formatted_servers
    })

# Alias for backward compatibility
search_servers = on_search_servers

async def on_server_selected(**kwargs):
    """Handle server.selected event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    server_details = ServerManager.get_server_details(server_name)
    
    if server_details:
        await send_message_with_log(websocket, {
            'type': 'server_selected',
            'server': server_details
        })
    else:
        await send_message_with_log(websocket, {
            'type': 'error',
            'message': f'Server {server_name} not found'
        })

# Alias for backward compatibility
select_server = on_server_selected

async def on_config_save(**kwargs):
    """Handle config.save event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    config_type = data.get('config_type')
    config_data = data.get('config_data')
    
    success = ServerManager.save_server_config(server_name, config_type, config_data)
    
    await send_message_with_log(websocket, {
        'type': 'config_saved',
        'success': success
    })

# Alias for backward compatibility
save_config = on_config_save

async def on_components_get(**kwargs):
    """Handle components.get event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    if not server_name:
        await send_message_with_log(websocket, {
            'type': 'error',
            'message': 'Server name is required'
        })
        return
    
    try:
        # Get server path
        server_path = os.path.join('cached_minecraft_servers', server_name)
        if not os.path.exists(server_path):
            await send_message_with_log(websocket, {
                'type': 'error',
                'message': f'Server directory not found: {server_path}'
            })
            return
        
        # Define component directories mapping
        component_dirs = {
            'mods': os.path.join(server_path, 'mods'),
            'plugins': os.path.join(server_path, 'plugins'),
            'datapacks': os.path.join(server_path, 'world', 'datapacks'),
            'resourcepacks': os.path.join(server_path, 'resourcepacks'),
            'schematics': os.path.join(server_path, 'schematics')
        }
        
        # Get files for each component type
        components = {}
        for component_type, component_path in component_dirs.items():
            if os.path.exists(component_path):
                # Get list of files in the directory
                files = []
                for file_name in os.listdir(component_path):
                    file_path = os.path.join(component_path, file_name)
                    if os.path.isfile(file_path):
                        # Get file stats
                        file_stats = os.stat(file_path)
                        files.append({
                            'name': file_name,
                            'size': file_stats.st_size,
                            'mtime': file_stats.st_mtime
                        })
                components[component_type] = files
        
        await send_message_with_log(websocket, {
            'type': 'components_data',
            'server_name': server_name,
            'components': components
        })
    except Exception as e:
            await send_message_with_log(websocket, {
                'type': 'error',
                'message': f'Failed to get server components: {str(e)}'
            })

# Alias for backward compatibility
get_server_components = on_components_get

async def on_schematic_delete(**kwargs):
    """Handle schematic.delete event"""
    websocket = kwargs.get('websocket', current_client)
    data = kwargs.get('data')
    if not websocket or not data:
        return
    
    server_name = data.get('server_name')
    schematic_name = data.get('schematic_name')
    
    if not server_name or not schematic_name:
        await send_message_with_log(websocket, {
            'type': 'error',
            'message': 'Server name and schematic name are required'
        })
        return
    
    try:
        # Get server path
        server_path = os.path.join('cached_minecraft_servers', server_name)
        schematic_path = os.path.join(server_path, 'schematics', schematic_name)
        
        if os.path.exists(schematic_path):
            os.remove(schematic_path)
            await send_message_with_log(websocket, {
                'type': 'schematic_deleted',
                'success': True,
                'schematic_name': schematic_name
            })
        else:
            await send_message_with_log(websocket, {
                'type': 'error',
                'message': f'Schematic file not found: {schematic_path}'
            })
    except Exception as e:
        await send_message_with_log(websocket, {
            'type': 'error',
            'message': f'Failed to delete schematic: {str(e)}'
        })

# Alias for backward compatibility
delete_schematic = on_schematic_delete

async def send_heartbeat(websocket):
    """Send periodic heartbeat to client to keep connection alive"""
    while True:
        try:
            await send_message_with_log(websocket, {'type': 'heartbeat'})
            await asyncio.sleep(30)  # Send heartbeat every 30 seconds
        except websockets.exceptions.ConnectionClosedError:
            break
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
            break

async def _ensure_persistent_rcon():
    """Ensure persistent RCON connection is established and valid"""
    global persistent_rcon_client, persistent_rcon_server
    
    # Check if any server is connected
    if not server_processes:
        # No server connected, close any existing persistent connection
        if persistent_rcon_client:
            persistent_rcon_client.close()
            persistent_rcon_client = None
            persistent_rcon_server = None
        return False
    
    # Get first connected server (assuming only one server is connected at a time)
    server_name = list(server_processes.keys())[0]
    
    # Check if server has completed startup
    if server_name not in server_startup_completed or not server_startup_completed[server_name]:
        # Server hasn't completed startup yet, don't establish RCON connection
        print(f"Server {server_name} hasn't completed startup yet, skipping RCON connection")
        return False
    
    # Check if we already have a valid persistent connection for this server
    if persistent_rcon_client and persistent_rcon_server == server_name:
        # Try to send a simple command to check if connection is still valid
        # Minecraft RCON doesn't support 'ping' command, use 'list' instead
        try:
            # Send a simple command that should always work
            persistent_rcon_client.send_command('list')
            return True
        except Exception as e:
            print(f"Persistent RCON connection is invalid: {e}")
            persistent_rcon_client.close()
            persistent_rcon_client = None
            persistent_rcon_server = None
    
    # Get server info
    server_info_data = server_info.get(server_name, {})
    rcon_port = server_info_data.get('rcon_port', 25575)
    rcon_password = server_info_data.get('rcon_password', '')
    spark_installed = server_info_data.get('spark_installed', False)
    
    if not rcon_password:
        return False
    
    # Create new persistent RCON client
    try:
        client = RCONClient(host='localhost', port=rcon_port, password=rcon_password)
        if client.connect() and client.authenticate():
            persistent_rcon_client = client
            persistent_rcon_server = server_name
            print(f"Persistent RCON connection established for server {server_name}")
            return True
        else:
            client.close()
            return False
    except Exception as e:
        print(f"Failed to establish persistent RCON connection: {e}")
        return False

async def send_server_status():
    """Send server status updates to the connected client"""
    global rotation_counter, persistent_rcon_client, persistent_rcon_server
    
    # Store previous network IO counters to calculate rate
    previous_network_io = psutil.net_io_counters()
    
    while True:
        try:
            if current_client is not None:
                # Get current network IO counters
                current_network_io = psutil.net_io_counters()
                
                # Calculate network IO rate (bytes per second)
                network_rate = {
                    'bytes_sent': current_network_io.bytes_sent - previous_network_io.bytes_sent,
                    'bytes_recv': current_network_io.bytes_recv - previous_network_io.bytes_recv
                }
                
                # Update previous network IO counters
                previous_network_io = current_network_io
                
                # Get memory information
                memory = psutil.virtual_memory()
                
                # Get CPU frequency based on platform
                cpu_frequency = 0
                current_platform = platform.system()
                
                if current_platform in ['Linux', 'Darwin']:  # Linux or macOS
                    # Use original logic for Linux/macOS
                    cpu_freq = psutil.cpu_freq()
                    cpu_frequency = cpu_freq.current if cpu_freq else 0
                elif current_platform == 'Windows':  # Windows
                    # Try to use WMI with the correct class and property based on WMI Explorer findings
                    wmi_success = False
                    try:                        
                        import wmi
                        import pythoncom
                        
                        # Initialize COM library for this thread
                        pythoncom.CoInitialize()
                        
                        # Create WMI instance
                        c = wmi.WMI()
                        
                        # Use the specified SELECT statement to query ActualFrequency
                        query = "SELECT ActualFrequency, Name FROM Win32_PerfFormattedData_Counters_ProcessorInformation WHERE Name='_Total'"
                        result = c.query(query)
                        
                        total_freq = None
                        fallback_freq = None
                        
                        # Check if any results were returned
                        if result:
                            # Get the first result (should be _Total instance)
                            item = result[0]
                            try:
                                # Check if ActualFrequency attribute exists
                                if hasattr(item, 'ActualFrequency'):
                                    # ActualFrequency is already in MHz, no conversion needed
                                    actual_freq = float(item.ActualFrequency)
                                    # Store _Total instance frequency
                                    total_freq = actual_freq
                                    instance_name = str(item.Name) if hasattr(item, 'Name') else "_Total"
                                    print(f"Found _Total instance frequency: {total_freq} MHz")
                            except (ValueError, TypeError, AttributeError) as e:
                                print(f"Error processing result: {e}")
                        
                        # If _Total query failed, try without WHERE clause
                        if total_freq is None:
                            print("_Total instance query failed, trying without WHERE clause")
                            query_all = "SELECT ActualFrequency, Name FROM Win32_PerfFormattedData_Counters_ProcessorInformation"
                            result_all = c.query(query_all)
                            
                            for i, item in enumerate(result_all):
                                try:
                                    if hasattr(item, 'ActualFrequency') and hasattr(item, 'Name'):
                                        instance_name = str(item.Name)
                                        actual_freq = float(item.ActualFrequency)
                                        
                                        if instance_name == '_Total':
                                            total_freq = actual_freq
                                            print(f"Found _Total instance frequency: {total_freq} MHz (index: {i})")
                                            break
                                        elif fallback_freq is None:
                                            fallback_freq = actual_freq
                                            print(f"Found fallback frequency: {fallback_freq} MHz (instance: {instance_name}, index: {i})")
                                except (ValueError, TypeError, AttributeError) as e:
                                    print(f"Error processing result {i}: {e}")
                                    continue
                        
                        # Use _Total instance frequency if available, otherwise use fallback
                        if total_freq is not None:
                            cpu_frequency = total_freq
                            print(f"Windows CPU frequency via WMI ActualFrequency: {cpu_frequency} MHz (instance: _Total)")
                            wmi_success = True
                        elif fallback_freq is not None:
                            cpu_frequency = fallback_freq
                            print(f"No _Total instance found, using fallback frequency: {cpu_frequency} MHz")
                            wmi_success = True
                        else:
                            # No valid frequency found in query results
                            print(f"No valid frequency found in query results. Result count: {len(result_all) if 'result_all' in locals() else 0}")
                    except Exception as e:
                        print(f"Error getting CPU frequency with WMI: {e}")
                        traceback.print_exc()
                    finally:
                        # Uninitialize COM library for this thread
                        try:
                            pythoncom.CoUninitialize()
                        except:
                            pass
                    
                    # If WMI failed, fallback to psutil
                    if not wmi_success:
                        try:
                            cpu_freq = psutil.cpu_freq()
                            if cpu_freq:
                                cpu_frequency = cpu_freq.current
                                print(f"Fallback to psutil CPU frequency: {cpu_frequency} MHz")
                            else:
                                cpu_frequency = 0.0
                                print(f"psutil.cpu_freq() returned None, using default: {cpu_frequency} MHz")
                        except Exception as e:
                            print(f"Error getting CPU frequency with psutil: {e}")
                            cpu_frequency = 0.0
                            print(f"Fallback to default CPU frequency: {cpu_frequency} MHz")
                
                # Get system information
                system_info = {
                    'cpu_usage': psutil.cpu_percent(interval=0.1),
                    'memory_usage': memory.percent,
                    'memory_total': memory.total,
                    'memory_used': memory.used,
                    'network_io': network_rate,
                    'cpu_frequency': cpu_frequency,
                    'tps': previous_advanced_data['tps'],
                    'mspt': previous_advanced_data['mspt'],
                    'players_online': previous_advanced_data['players_online'],
                    'players_max': previous_advanced_data['players_max'],
                    'spark_installed': False
                }
                
                # Initialize server_info_data with default value
                server_info_data = {}
                
                # Check if any server is connected
                if server_processes:
                    # Get first connected server (assuming only one server is connected at a time)
                    server_name = list(server_processes.keys())[0]
                    server_info_data = server_info.get(server_name, {})
                    spark_installed = server_info_data.get('spark_installed', False)
                    system_info['spark_installed'] = spark_installed
                    
                    # Ensure persistent RCON connection is established
                    rcon_available = await _ensure_persistent_rcon()
                    
                    # If RCON is available, get server data in rotation
                    if rcon_available:
                        try:
                            # Get server info again to ensure we have latest spark_installed status
                            server_info_data = server_info.get(server_name, {})
                            spark_installed = server_info_data.get('spark_installed', False)
                            
                            # Get server info for platform and version checks
                            server_info_data = server_info.get(server_name, {})
                            platform_type = server_info_data.get('platform_type', 'Unknown')
                            game_version = server_info_data.get('game_version', '1.0.0')
                            spark_installed = server_info_data.get('spark_installed', False)
                            
                            # Check if we should use tick query command
                            # Conditions: Forge platform OR no spark installed, and game version >= 1.20.1
                            use_tick_query = False
                            try:
                                # Parse game version to compare
                                version_parts = list(map(int, game_version.split('.')))
                                if (platform_type == 'Forge' or not spark_installed) and len(version_parts) >= 3:
                                    if (version_parts[0] > 1) or \
                                       (version_parts[0] == 1 and version_parts[1] > 20) or \
                                       (version_parts[0] == 1 and version_parts[1] == 20 and version_parts[2] >= 1):
                                        use_tick_query = True
                            except Exception as e:
                                print(f"Error parsing game version: {e}")
                            
                            # 根据rotation_counter轮流获取数据
                            if rotation_counter == 0:  # Get TPS and MSPT using appropriate method
                                if use_tick_query:
                                    # Use tick query command for Forge 1.20.1+ without spark
                                    tick_result = persistent_rcon_client.send_command('tick query')
                                    if tick_result:
                                        print(f"Tick query output: {tick_result}")
                                        tick_lines = tick_result.split('\n')
                                        
                                        # Helper function to remove Minecraft formatting codes
                                        def remove_minecraft_formatting(text):
                                            import re
                                            # Remove all formatting codes (§ followed by any character)
                                            return re.sub(r'§[0-9a-fklmnor]', '', text, flags=re.IGNORECASE)
                                        
                                        for line in tick_lines:
                                            line = line.strip()
                                            if not line:
                                                continue
                                            
                                            # Remove Minecraft formatting codes
                                            clean_line = remove_minecraft_formatting(line)
                                            
                                            # Parse tick query output
                                            # Format: The game is running normallyTarget tick rate: {A} per second. Average time per tick: {B}ms (Target: 50.0ms)Percentiles: P50: {C}ms P95: {D}ms P99: {E}ms, sample: 100
                                            import re
                                            match = re.search(r'Average time per tick: ([\d.]+)ms', clean_line)
                                            if match:
                                                # Get MSPT from {B}
                                                mspt_value = match.group(1)
                                                system_info['mspt'] = mspt_value
                                                previous_advanced_data['mspt'] = mspt_value
                                                print(f"Extracted MSPT from tick query: {mspt_value}")
                                                
                                                # Calculate TPS from MSPT
                                                try:
                                                    mspt = float(mspt_value)
                                                    if mspt <= 50.0:
                                                        tps_value = "20.0"
                                                    else:
                                                        tps = 1000.0 / mspt
                                                        tps_value = f"{min(tps, 20.0):.1f}"
                                                    system_info['tps'] = tps_value
                                                    previous_advanced_data['tps'] = tps_value
                                                    print(f"Calculated TPS from MSPT: {tps_value}")
                                                except ValueError:
                                                    print(f"Error calculating TPS from MSPT: {mspt_value}")
                                                break
                                else:
                                    # Use traditional tps command for spark installed servers
                                    tps_result = persistent_rcon_client.send_command('tps')
                                    if tps_result:
                                        print(f"TPS command output: {tps_result}")
                                        tps_lines = tps_result.split('\n')
                                        
                                        # Helper function to remove Minecraft formatting codes
                                        def remove_minecraft_formatting(text):
                                            import re
                                            # Remove all formatting codes (§ followed by any character)
                                            return re.sub(r'§[0-9a-fklmnor]', '', text, flags=re.IGNORECASE)
                                        
                                        for line in tps_lines:
                                            line = line.strip()
                                            if not line:
                                                continue
                                            
                                            # Remove Minecraft formatting codes
                                            clean_line = remove_minecraft_formatting(line)
                                            
                                            # Parse TPS from line with [⚡] and multiple comma-separated values
                                            if "[⚡]" in clean_line and len(clean_line.split(',')) >= 5:
                                                # Extract TPS from {10分钟前TPS} position (first value)
                                                tps_values = [val.strip() for val in clean_line.split(',')]
                                                if tps_values:
                                                    tps_value = tps_values[0]
                                                    # Clean up any remaining special characters
                                                    tps_value = tps_value.replace('[⚡]', '').strip()
                                                    if tps_value:
                                                        system_info['tps'] = tps_value
                                                        previous_advanced_data['tps'] = tps_value
                                                        print(f"Extracted TPS: {tps_value}")
                                            
                                            # Parse TPS from "TPS from last 1m, 5m, 15m:" line
                                            elif "TPS from last" in clean_line:
                                                # Extract TPS from the first value
                                                tps_part = clean_line.split(':')[-1].strip()
                                                if tps_part:
                                                    tps_values = [val.strip() for val in tps_part.split(',')]
                                                    if tps_values:
                                                        tps_value = tps_values[0]
                                                        system_info['tps'] = tps_value
                                                        previous_advanced_data['tps'] = tps_value
                                                        print(f"Extracted TPS from 'TPS from last' line: {tps_value}")
                            elif rotation_counter == 1:  # Get MSPT from mspt command (only if spark is installed)
                                if not use_tick_query:
                                    mspt_result = persistent_rcon_client.send_command('mspt')
                                    if mspt_result:
                                        print(f"MSPT command output: {mspt_result}")
                                        mspt_lines = mspt_result.split('\n')
                                        
                                        # Helper function to remove Minecraft formatting codes
                                        def remove_minecraft_formatting(text):
                                            import re
                                            # Remove all formatting codes (§ followed by any character)
                                            return re.sub(r'§[0-9a-fklmnor]', '', text, flags=re.IGNORECASE)
                                        
                                        for line in mspt_lines:
                                            line = line.strip()
                                            if not line:
                                                continue
                                            
                                            # Remove Minecraft formatting codes
                                            clean_line = remove_minecraft_formatting(line)
                                            
                                            # Parse MSPT from line with ◴
                                            if "◴" in clean_line:
                                                # Extract MSPT from {G} position (first value before /)
                                                # Format: ◴ 1.23/4.56/7.89, 1.23/4.56/7.89, 1.23/4.56/7.89
                                                mspt_part = clean_line.split('◴')[1].strip() if '◴' in clean_line else clean_line
                                                mspt_values = mspt_part.split(',')[0].strip() if ',' in mspt_part else mspt_part
                                                if '/' in mspt_values:
                                                    mspt_value = mspt_values.split('/')[0].strip()
                                                    if mspt_value:
                                                        system_info['mspt'] = mspt_value
                                                        previous_advanced_data['mspt'] = mspt_value
                                                        print(f"Extracted MSPT: {mspt_value}")
                            elif rotation_counter == 2:  # Get Players from list command
                                list_result = persistent_rcon_client.send_command('list')
                                if list_result:
                                    print(f"List command output: {list_result}")
                                    # Parse list output - Example: "There are 2 of a max of 20 players online: player1, player2"
                                    # or "There are 0 of a max of 20 players online"
                                    import re
                                    player_pattern = r"There are (\d+) of a max of (\d+) players online"
                                    match = re.search(player_pattern, list_result)
                                    if match:
                                        system_info['players_online'] = match.group(1)
                                        system_info['players_max'] = match.group(2)
                                        previous_advanced_data['players_online'] = match.group(1)
                                        previous_advanced_data['players_max'] = match.group(2)
                                    else:
                                        # Alternative format: "Online players: 2/20"
                                        online_pattern = r"Online players: (\d+)/(\d+)"
                                        match = re.search(online_pattern, list_result)
                                        if match:
                                            system_info['players_online'] = match.group(1)
                                            system_info['players_max'] = match.group(2)
                                            previous_advanced_data['players_online'] = match.group(1)
                                            previous_advanced_data['players_max'] = match.group(2)
                        except Exception as e:
                            print(f"Error getting server data via persistent RCON: {e}")
                            # Close invalid connection, but check if it exists first
                            if persistent_rcon_client:
                                persistent_rcon_client.close()
                                persistent_rcon_client = None
                                persistent_rcon_server = None
                            # Try to re-establish connection for next iteration
                            print("Attempting to re-establish RCON connection for next iteration...")
                            await _ensure_persistent_rcon()
                
                # Send status update to client
                await send_message_with_log(current_client, {
                    'type': 'server_status',
                    'system_info': system_info,
                    'platform_type': server_info_data.get('platform_type', 'Unknown')
                })
                
                # Increment rotation counter, reset to 0 after 2 to cycle through all three commands
                rotation_counter = (rotation_counter + 1) % 3
            
            await asyncio.sleep(1)  # Update every 1 second
        except Exception as e:
            print(f"Error in send_server_status: {e}")
            # Log the full traceback for debugging
            import traceback
            traceback.print_exc()
            # Continue the loop even if there's an error
            await asyncio.sleep(1)

async def send_server_logs():
    """Send server logs to the connected client"""
    # This function is kept for compatibility but log streaming is now handled by stream_server_logs
    # which is called per client connection
    await asyncio.sleep(3600)  # Sleep for an hour, effectively doing nothing

async def monitor_server_logs(server_path, server_name):
    """Monitor server logs independently to detect startup completion and cache logs"""
    try:
        # Find the latest log file
        logs_dir = os.path.join(server_path, 'logs')
        if not os.path.exists(logs_dir):
            print(f"Log directory not found for server {server_name}: {logs_dir}")
            return
        
        # Get the latest log file (typically latest.log)
        latest_log = os.path.join(logs_dir, 'latest.log')
        if not os.path.exists(latest_log):
            print(f"Latest log file not found for server {server_name}: {latest_log}")
            return
        
        # Initialize log cache for this server
        if server_name not in log_caches:
            log_caches[server_name] = []
        
        # Track the last position in the log file
        last_position = 0
        startup_completed = False
        
        # First, check if server has already completed startup by scanning existing logs
        try:
            with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                # Read the entire file to find startup completion line
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                
                # Move to beginning to search for startup line and cache logs
                f.seek(0)
                for line in f:
                    # Cache the log line
                    log_caches[server_name].append(line.rstrip())
                    
                    # Check if this line indicates server startup completion
                    if "Done (" in line and "s)! For help, type " in line and "help" in line or "Server Started!" in line:
                        # Found startup completion line, server has already completed startup
                        server_startup_completed[server_name] = True
                        print(f"Server {server_name} has already completed startup, detected from logs")
                        startup_completed = True
                        break
                
                # Update last position to end of file
                last_position = file_size
        except Exception as e:
            print(f"Error initializing log cache for server {server_name}: {e}")
        
        if not startup_completed:
            # If startup not completed, continue monitoring for new log lines
            while True:
                try:
                    with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                        # Move to last read position
                        f.seek(last_position)
                        
                        # Read new log lines
                        new_lines = f.readlines()
                        if new_lines:
                            for line in new_lines:
                                # Cache the log line
                                log_caches[server_name].append(line.rstrip())
                                
                                # Check if this line indicates server startup completion
                                if "Done (" in line and "s)! For help, type " in line and "help" in line:
                                    # Server has completed startup, set the flag
                                    server_startup_completed[server_name] = True
                                    print(f"Server {server_name} has completed startup")
                                    startup_completed = True
                                    break
                        
                        # Update last position to end of file
                        last_position = f.tell()
                except Exception as e:
                    print(f"Error reading logs for server {server_name}: {e}")
                
                if startup_completed:
                    break
                
                await asyncio.sleep(0.5)  # Wait for new logs
    except Exception as e:
        print(f"Error monitoring server logs for {server_name}: {e}")

async def _check_log_rate_limit(websocket):
    """Check if log rate limit has been exceeded for this client"""
    current_time = time.time()
    
    # Initialize counter if not exists
    if websocket not in log_rate_counters:
        log_rate_counters[websocket] = (current_time, 0)
    
    last_reset_time, line_count = log_rate_counters[websocket]
    
    # Reset counter if we're in a new second
    if current_time - last_reset_time > 1.0:
        log_rate_counters[websocket] = (current_time, 0)
        if websocket in warning_sent:
            del warning_sent[websocket]
        return True
    
    # Check if we've reached the limit
    if line_count >= LOG_RATE_LIMIT:
        # Check if we've already sent a warning this second
        if websocket not in warning_sent:
            # Send warning message
            await send_message_with_log(websocket, {
                'type': 'server_log',
                'log': '[!] 日志输出速率限制已触发，部分日志被丢弃。'
            })
            warning_sent[websocket] = True
        return False
    
    # Increment line count
    log_rate_counters[websocket] = (last_reset_time, line_count + 1)
    return True

async def stream_server_logs(websocket, server_path):
    """Stream server logs to the client using cached logs and periodic file reads"""
    try:
        # Get server name from server_path
        server_name = os.path.basename(server_path)
        
        # Find the latest log file
        logs_dir = os.path.join(server_path, 'logs')
        if not os.path.exists(logs_dir):
            await send_message_with_log(websocket, {
                'type': 'server_log',
                'log': f'Log directory not found: {logs_dir}'
            })
            return
        
        # Get the latest log file (typically latest.log)
        latest_log = os.path.join(logs_dir, 'latest.log')
        if not os.path.exists(latest_log):
            await send_message_with_log(websocket, {
                'type': 'server_log',
                'log': f'Latest log file not found: {latest_log}'
            })
            return
        
        # Send cached logs first (with rate limiting)
        if server_name in log_caches and log_caches[server_name]:
            print(f"Sending {len(log_caches[server_name])} cached log lines to client for server {server_name}")
            for log_line in log_caches[server_name]:
                # Check rate limit before sending
                if await _check_log_rate_limit(websocket):
                    await send_message_with_log(websocket, {
                        'type': 'server_log',
                        'log': log_line
                    })
            # Clear the cache after sending
            log_caches[server_name] = []
        
        # Track the last position in the log file
        last_position = 0
        
        # Get initial file size to know where to start reading new logs
        try:
            with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(0, os.SEEK_END)
                last_position = f.tell()
        except Exception as e:
            print(f"Error getting initial log position: {e}")
        
        # Continue streaming new log lines using periodic file reads
        while True:
            try:
                with open(latest_log, 'r', encoding='utf-8', errors='ignore') as f:
                    # Move to last read position
                    f.seek(last_position)
                    
                    # Read new log lines
                    new_lines = f.readlines()
                    if new_lines:
                        for line in new_lines:
                            # Check rate limit before sending
                            if await _check_log_rate_limit(websocket):
                                await send_message_with_log(websocket, {
                                    'type': 'server_log',
                                    'log': line.rstrip()
                                })
                    
                    # Update last position to end of file
                    last_position = f.tell()
            except Exception as e:
                print(f"Error reading logs for streaming: {e}")
            
            await asyncio.sleep(0.5)  # Wait for new logs
            
    except Exception as e:
        await send_message_with_log(websocket, {
            'type': 'error',
            'message': f'Log streaming error: {str(e)}'
        })

async def check_server_processes():
    """Check if server processes are still running every 5 seconds"""
    while True:
        await asyncio.sleep(5)
        
        # Create a copy of the keys to avoid modification during iteration
        servers_to_remove = []
        
        for server_name, process_info in server_processes.items():
            process = process_info.get('process')
            if process:
                # Check if process is still running
                process_status = process.poll()
                if process_status is not None:
                    # Process has stopped, add to removal list
                    servers_to_remove.append(server_name)
        
        # Remove stopped servers
        for server_name in servers_to_remove:
            print(f"Server {server_name} has stopped unexpectedly")
            
            # Remove from process list
            del server_processes[server_name]
            if server_name in server_info:
                del server_info[server_name]
            
            # Clear server log cache
            if server_name in log_caches:
                del log_caches[server_name]
            
            # Remove from startup completed list
            if server_name in server_startup_completed:
                del server_startup_completed[server_name]
            
            # Notify all connected clients that server has stopped unexpectedly
            if current_client:
                await send_message_with_log(current_client, {
                    'type': 'server_crashed',
                    'server_name': server_name
                })
            
            # Also send refresh_servers to update server list
            if current_client:
                await send_message_with_log(current_client, {
                    'type': 'refresh_servers'
                })

# Event subscription setup

def setup_event_handlers():
    """Set up all event handlers"""
    # WebSocket events - use sync subscription for lambda functions
    event_bus.subscribe_sync(CLIENT_CONNECTED, lambda **kwargs: print("Client connected"))
    event_bus.subscribe_sync(CLIENT_DISCONNECTED, lambda **kwargs: print("Client disconnected"))
    
    # Server events
    event_bus.subscribe(SERVER_STARTED, on_server_started)
    event_bus.subscribe(SERVER_STOPPED, on_server_stopped)
    event_bus.subscribe(SERVER_CONNECTED, on_server_connected)
    
    # Command events
    event_bus.subscribe(COMMAND_EXECUTED, on_command_executed)
    
    # Refresh events
    event_bus.subscribe(REFRESH_SERVERS, on_refresh_servers)
    
    # Custom events
    event_bus.subscribe('search.servers', on_search_servers)
    event_bus.subscribe('server.selected', on_server_selected)
    event_bus.subscribe('config.save', on_config_save)
    event_bus.subscribe('components.get', on_components_get)
    event_bus.subscribe('schematic.delete', on_schematic_delete)

async def start_websocket_server():
    """Start the WebSocket server"""
    # Set up event handlers
    setup_event_handlers()
    
    server = await websockets.serve(handle_client, '0.0.0.0', 9001)
    
    # Start background tasks
    asyncio.create_task(send_server_status())
    asyncio.create_task(send_server_logs())
    asyncio.create_task(check_server_processes())
    
    await server.wait_closed()

if __name__ == '__main__':
    asyncio.run(start_websocket_server())
