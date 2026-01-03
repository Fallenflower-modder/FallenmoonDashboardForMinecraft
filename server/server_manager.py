import os
import json
import shutil
import random
import string

SERVERS_DIR = 'cached_minecraft_servers'

class ServerManager:
    @staticmethod
    def scan_servers():
        """Scan all servers in the cached_minecraft_servers directory"""
        servers = []
        
        if not os.path.exists(SERVERS_DIR):
            return servers
        
        for server_dir in os.listdir(SERVERS_DIR):
            server_path = os.path.join(SERVERS_DIR, server_dir)
            if os.path.isdir(server_path):
                server = ServerManager._process_server(server_path, server_dir)
                servers.append(server)
        
        return servers
    
    @staticmethod
    def _process_server(server_path, server_name):
        """Process a single server directory"""
        # First check if Fallenmoon/version.json exists, if not create it
        ServerManager._ensure_version_file(server_path, server_name)
        
        # Check server validity
        validity = ServerManager._check_server_validity(server_path)
        
        # If server is valid, generate and save RCON password only if it doesn't exist
        if validity['valid']:
            # Read version.json to check if RCON password already exists
            version_file = os.path.join(server_path, 'Fallenmoon', 'version.json')
            version_data = ServerManager._get_server_info(server_path)
            
            # Check if RCON password already exists
            if 'rcon_password' in version_data and version_data['rcon_password']:
                # RCON password already exists, use it
                rcon_password = version_data['rcon_password']
                rcon_port = version_data.get('rcon_port', 25575)
            else:
                # Generate random RCON password
                rcon_password = ServerManager._generate_rcon_password()
                rcon_port = 25575  # Default RCON port
            
            # Read and update server.properties
            properties_file = os.path.join(server_path, 'server.properties')
            properties = {}
            
            with open(properties_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        properties[key.strip()] = value.strip()
            
            # Enable RCON and set password
            properties['enable-rcon'] = 'true'
            properties['rcon.port'] = str(rcon_port)
            properties['rcon.password'] = rcon_password
            
            # Write updated properties back to file
            with open(properties_file, 'w') as f:
                for key, value in properties.items():
                    f.write(f'{key}={value}\n')
            
            # Update version.json if password doesn't exist or port changed
            if 'rcon_password' not in version_data or not version_data['rcon_password'] or version_data.get('rcon_port') != rcon_port:
                version_data['rcon_password'] = rcon_password
                version_data['rcon_port'] = rcon_port
                # Write updated version data back to file
                with open(version_file, 'w') as f:
                    json.dump(version_data, f, indent=4)
        
        return {
            'name': server_name,
            'path': server_path,
            'valid': validity['valid'],
            'reason': validity['reason'],
            'info': ServerManager._get_server_info(server_path)
        }
    
    @staticmethod
    def _ensure_version_file(server_path, server_name):
        """Ensure the version.json file exists"""
        fallenmoon_dir = os.path.join(server_path, 'Fallenmoon')
        version_file = os.path.join(fallenmoon_dir, 'version.json')
        
        if not os.path.exists(version_file):
            # Create Fallenmoon directory if it doesn't exist
            os.makedirs(fallenmoon_dir, exist_ok=True)
            
            # Determine server type
            if os.path.exists(os.path.join(server_path, r'libraries\com\mohistmc')):
                server_type = 'Mohist'
            elif os.path.exists(os.path.join(server_path, r'.arclight')):
                server_type = 'Arclight'
            elif os.path.exists(os.path.join(server_path, r'libraries\net\neoforged\neoforge')):
                server_type = 'Neoforge'
            elif os.path.exists(os.path.join(server_path, r'libraries\io\papermc\paper')):
                server_type = 'Paper'
            elif os.path.exists(os.path.join(server_path, r'libraries\net\minecraftforge\forge')):
                server_type = 'Forge'
            else:
                server_type = 'Unknown'

            
            # Create default version.json
            version_data = {
                'server_name': server_name,
                'game_version': 'Unknown',
                'platform_type': server_type,
                'platform_version': 'Unknown'
            }
            
            with open(version_file, 'w') as f:
                json.dump(version_data, f, indent=4)
    
    @staticmethod
    def _generate_rcon_password(length=16):
        """Generate a random RCON password using only safe characters"""
        # Use only letters and digits to avoid any escape characters
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    @staticmethod
    def _check_server_validity(server_path):
        """Check if a server is valid"""
        required_files = [
            'run.bat',
            'server.properties',
            'libraries'
        ]
        
        missing_files = []
        for file in required_files:
            if not os.path.exists(os.path.join(server_path, file)):
                missing_files.append(file)
        
        if missing_files:
            if len(missing_files) == 1:
                return {
                    'valid': False,
                    'reason': f'{missing_files[0]} 缺失'
                }
            else:
                return {
                    'valid': False,
                    'reason': f'缺失 {len(missing_files)} 个关键组件。'
                }
        
        # Check if server_start.bat exists, if not create it from run.bat
        run_bat = os.path.join(server_path, 'run.bat')
        server_start_bat = os.path.join(server_path, 'server_start.bat')
        
        if not os.path.exists(server_start_bat) and os.path.exists(run_bat):
            shutil.copy2(run_bat, server_start_bat)
        
        # Check eula.txt
        eula_file = os.path.join(server_path, 'eula.txt')
        if not os.path.exists(eula_file) or open(eula_file).read().strip() != 'eula = true':
            with open(eula_file, 'w') as f:
                f.write('eula = true')
        
        return {
            'valid': True,
            'reason': 'Valid'
        }
    
    @staticmethod
    def _get_server_info(server_path):
        """Get server information from version.json"""
        version_file = os.path.join(server_path, 'Fallenmoon', 'version.json')
        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                return json.load(f)
        return {
            'server_name': os.path.basename(server_path),
            'game_version': 'Unknown',
            'platform_type': 'Unknown',
            'platform_version': 'Unknown'
        }
    
    @staticmethod
    def get_server_details(server_name):
        """Get detailed information for a specific server"""
        server_path = os.path.join(SERVERS_DIR, server_name)
        if not os.path.exists(server_path):
            return None
        
        # Get version info
        info = ServerManager._get_server_info(server_path)
        
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
        
        # Add spark_installed to info
        info['spark_installed'] = spark_installed
        
        # Get server.properties
        properties = {}
        properties_file = os.path.join(server_path, 'server.properties')
        if os.path.exists(properties_file):
            with open(properties_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        properties[key.strip()] = value.strip()
        
        # Get server_start.bat content
        start_script = ''
        start_script_file = os.path.join(server_path, 'server_start.bat')
        if os.path.exists(start_script_file):
            with open(start_script_file, 'r') as f:
                start_script = f.read()
        
        return {
            'info': info,
            'properties': properties,
            'start_script': start_script
        }
    
    @staticmethod
    def save_server_config(server_name, config_type, data):
        """Save server configuration"""
        server_path = os.path.join(SERVERS_DIR, server_name)
        if not os.path.exists(server_path):
            return False
        
        try:
            if config_type == 'version':
                # Save version.json
                version_file = os.path.join(server_path, 'Fallenmoon', 'version.json')
                with open(version_file, 'w') as f:
                    json.dump(data, f, indent=4)
            elif config_type == 'properties':
                # Save server.properties
                properties_file = os.path.join(server_path, 'server.properties')
                with open(properties_file, 'w') as f:
                    for key, value in data.items():
                        f.write(f'{key}={value}\n')
            elif config_type == 'start_script':
                # Save server_start.bat
                start_script_file = os.path.join(server_path, 'server_start.bat')
                with open(start_script_file, 'w') as f:
                    f.write(data)
            return True
        except Exception as e:
            print(f'Error saving config: {e}')
            return False
