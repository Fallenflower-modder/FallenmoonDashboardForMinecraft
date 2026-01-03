// Global variables
let ws = null;
let connected = false;
let currentServer = null;
let selectedServer = null; // Track selected server across all pages
let memoryChart = null;
let cpuChart = null;
let isConnecting = false;
let serverInfoMap = {}; // Store server info for display names
// WebSocket default settings
let wsConfig = {
    ip: 'localhost',
    port: 9001
};

// DOM Elements
const elements = {
    // WebSocket status
    wsStatus: document.getElementById('ws-status'),
    wsConfigModal: document.getElementById('ws-config-modal'),
    wsIpInput: document.getElementById('ws-ip'),
    wsPortInput: document.getElementById('ws-port'),
    
    // Tab buttons
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabContents: document.querySelectorAll('.tab-content'),
    
    // Server Details Tab
    serverProcessSelect: document.getElementById('server-process-select'),
    refreshBtn: document.getElementById('refresh-btn'),
    connectBtn: document.getElementById('connect-btn'),
    consoleOutput: document.getElementById('console-output'),
    consoleInput: document.getElementById('console-input'),
    executeBtn: document.getElementById('execute-btn'),
    connectionStatus: document.getElementById('connection-status'),
    terminateBtn: document.getElementById('terminate-btn'),
    
    // Server Config Tab
    configServerSelect: document.getElementById('config-server-select'),
    searchServerBtn: document.getElementById('search-server-btn'),
    selectServerBtn: document.getElementById('select-server-btn'),
    startServerBtn: document.getElementById('start-server-btn'),
    configTabBtns: document.querySelectorAll('.config-tab-btn'),
    configTabContents: document.querySelectorAll('.config-tab-content'),
    propertiesList: document.getElementById('properties-list'),
    configList: document.getElementById('config-list'),
    startScriptContent: document.getElementById('start-script-content'),
    savePropertiesBtn: document.getElementById('save-properties-btn'),
    saveConfigBtn: document.getElementById('save-config-btn'),
    saveScriptBtn: document.getElementById('save-script-btn'),
    
    // Server Components Tab
    componentsServerSelect: document.getElementById('components-server-select'),
    componentsSearchBtn: document.getElementById('components-search-btn'),
    componentsSelectBtn: document.getElementById('components-select-btn'),
    componentTabBtns: document.querySelectorAll('.component-tab-btn'),
    componentTabContents: document.querySelectorAll('.component-tab-content'),
    
    // Panel Settings Tab
    outputRate: document.getElementById('output-rate'),
    backgroundSelect: document.getElementById('background-select'),
    searchBackgroundBtn: document.getElementById('search-background-btn'),
    backgroundPreview: document.getElementById('background-preview'),
    saveSettingsBtn: document.getElementById('save-settings-btn')
};

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    initializeCharts();
    initializeWebSocket();
    initializeEventListeners();
});

// Initialize charts
function initializeCharts() {
    // Memory Chart
    const memoryCtx = document.getElementById('memory-chart').getContext('2d');
    memoryChart = new Chart(memoryCtx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [0, 100],
                backgroundColor: ['#00aaff', '#2a3447'],
                borderWidth: 0,
                cutout: '80%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            },
            animation: {
                animateRotate: true,
                animateScale: true
            }
        }
    });
    
    // CPU Chart
    const cpuCtx = document.getElementById('cpu-chart').getContext('2d');
    cpuChart = new Chart(cpuCtx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [0, 100],
                backgroundColor: ['#00ffaa', '#2a3447'],
                borderWidth: 0,
                cutout: '80%'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            },
            animation: {
                animateRotate: true,
                animateScale: true
            }
        }
    });
}

// WebSocket connection variables
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let reconnectInterval = 1000; // Start with 1 second
let heartbeatTimeout = null;
const HEARTBEAT_INTERVAL = 35000; // 35 seconds, slightly longer than server's 30 seconds

// Initialize WebSocket connection
function initializeWebSocket() {
    // Prevent multiple connection attempts
    if (isConnecting || (ws && ws.readyState === WebSocket.OPEN)) {
        return;
    }
    
    isConnecting = true;
    
    try {
        const wsUrl = `ws://${wsConfig.ip}:${wsConfig.port}`;
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('WebSocket connected');
            elements.wsStatus.textContent = 'WebSocket: 在线';
            elements.wsStatus.className = 'ws-status online';
            // Reset reconnect attempts on successful connection
            reconnectAttempts = 0;
            reconnectInterval = 1000;
            isConnecting = false;
            // Start heartbeat checker
            startHeartbeatChecker();
        };
        
        ws.onmessage = (event) => {
            handleWebSocketMessage(event.data);
        };
        
        ws.onclose = (event) => {
            console.log(`WebSocket disconnected: ${event.code} - ${event.reason}`);
            elements.wsStatus.textContent = 'WebSocket: 离线';
            elements.wsStatus.className = 'ws-status offline';
            isConnecting = false;
            // Stop heartbeat checker
            stopHeartbeatChecker();
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    } catch (error) {
        console.error('Failed to initialize WebSocket:', error);
        isConnecting = false;
    }
}

// Show WebSocket configuration modal
function showWebSocketConfig() {
    // Fill with current configuration
    elements.wsIpInput.value = wsConfig.ip;
    elements.wsPortInput.value = wsConfig.port;
    
    // Show modal
    elements.wsConfigModal.style.display = 'block';
}

// Hide WebSocket configuration modal
function hideWebSocketConfig() {
    elements.wsConfigModal.style.display = 'none';
}

// Connect to WebSocket server with manual configuration
function connectToWebSocketServer() {
    // Get values from input fields
    const ip = elements.wsIpInput.value.trim();
    const port = parseInt(elements.wsPortInput.value.trim());
    
    // Validate input
    if (!ip || isNaN(port) || port < 1 || port > 65535) {
        showMessage('请输入有效的IP地址和端口号', 'error');
        return;
    }
    
    // Update configuration
    wsConfig.ip = ip;
    wsConfig.port = port;
    
    // Close existing connection if any
    if (ws) {
        ws.close();
    }
    
    // Hide modal
    hideWebSocketConfig();
    
    // Connect with new configuration
    showMessage('正在连接到WebSocket服务器...', 'info');
    initializeWebSocket();
}

// Reconnect with exponential backoff
function reconnect() {
    if (reconnectAttempts >= maxReconnectAttempts) {
        console.error('Max reconnection attempts reached. Stopping reconnection.');
        return;
    }
    
    reconnectAttempts++;
    // Exponential backoff with jitter
    const jitter = Math.random() * 500;
    const delay = reconnectInterval + jitter;
    
    console.log(`Attempting to reconnect in ${Math.round(delay / 1000)} seconds... (Attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
    
    setTimeout(() => {
        initializeWebSocket();
        // Double the reconnect interval for next time, but cap at 30 seconds
        reconnectInterval = Math.min(reconnectInterval * 2, 30000);
    }, delay);
}

// Start heartbeat checker
function startHeartbeatChecker() {
    stopHeartbeatChecker(); // Clear any existing timeout
    heartbeatTimeout = setTimeout(() => {
        console.warn('Heartbeat timeout - reconnecting...');
        ws.close(); // Force reconnection
    }, HEARTBEAT_INTERVAL);
}

// Stop heartbeat checker
function stopHeartbeatChecker() {
    if (heartbeatTimeout) {
        clearTimeout(heartbeatTimeout);
        heartbeatTimeout = null;
    }
}

// Handle WebSocket messages
function handleWebSocketMessage(message) {
    try {
        const data = JSON.parse(message);
        
        // Reset heartbeat timeout on any message from server
        startHeartbeatChecker();
        
        switch (data.type) {
            case 'heartbeat':
                // Handle server heartbeat, just reset timeout (already done above)
                break;
            case 'server_list':
                updateServerList(data.servers);
                break;
            case 'connect_success':
                handleConnectSuccess(data.server);
                break;
            case 'server_status':
                updateServerStatus(data.system_info, data.platform_type);
                break;
            case 'server_log':
                appendToConsole(data.log);
                break;
            case 'command_result':
                appendToConsole(data.result);
                break;
            case 'server_stopped':
                handleServerStopped(data.server_name);
                resetAdvancedData();
                break;
            case 'server_crashed':
                // Server has crashed unexpectedly
                showMessage(`服务器 ${data.server_name} 意外停止运行`, 'error');
                // Disconnect from server and update UI
                handleServerStopped(data.server_name);
                resetAdvancedData();
                break;
            case 'server_started':
                handleServerStarted(data.server_name);
                break;
            case 'server_search_result':
                updateConfigServerList(data.servers);
                break;
            case 'server_selected':
                handleServerSelected(data.server);
                break;
            case 'config_saved':
                showMessage(data.success ? '配置保存成功！' : '配置保存失败！', data.success ? 'success' : 'error');
                break;
            case 'components_data':
                showComponents(data.server_name, data.components);
                break;
            case 'schematic_deleted':
                if (data.success) {
                    showMessage(`蓝图 ${data.schematic_name} 删除成功！`, 'success');
                    // Refresh components list
                    selectComponentsServer();
                }
                break;
            case 'refresh_servers':
                // Refresh server list when notified by server
                refreshServers();
                showMessage('服务器列表已更新', 'info');
                break;
            case 'error':
                showMessage(data.message, 'error');
                break;
        }
    } catch (error) {
        console.error('Error parsing WebSocket message:', error);
    }
}

// Initialize event listeners
function initializeEventListeners() {
    // Tab switching
    elements.tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            switchTab(tab);
        });
    });
    
    // WebSocket status button click
    elements.wsStatus.addEventListener('click', showWebSocketConfig);
    
    // Close modal when clicking outside
    window.addEventListener('click', (event) => {
        if (event.target === elements.wsConfigModal) {
            hideWebSocketConfig();
        }
    });
    
    // Panel Settings Tab events
    if (elements.searchBackgroundBtn) {
        elements.searchBackgroundBtn.addEventListener('click', searchBackgrounds);
    }
    
    if (elements.backgroundSelect) {
        elements.backgroundSelect.addEventListener('change', updateBackgroundPreview);
    }
    
    if (elements.saveSettingsBtn) {
        elements.saveSettingsBtn.addEventListener('click', saveAndApplySettings);
    }
    
    // Server Details Tab Event Listeners
    elements.refreshBtn.addEventListener('click', refreshServers);
    elements.connectBtn.addEventListener('click', connectToServer);
    elements.executeBtn.addEventListener('click', executeCommand);
    elements.consoleInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            executeCommand();
        }
    });
    elements.terminateBtn.addEventListener('click', terminateConnection);
    
    // Server Config Tab Event Listeners
    elements.searchServerBtn.addEventListener('click', searchServers);
    elements.selectServerBtn.addEventListener('click', selectServer);
    elements.startServerBtn.addEventListener('click', startServer);
    
    // Sync server selection between config and components pages
    elements.configServerSelect.addEventListener('change', (e) => {
        elements.componentsServerSelect.value = e.target.value;
        selectedServer = e.target.value;
    });
    
    elements.componentsServerSelect.addEventListener('change', (e) => {
        elements.configServerSelect.value = e.target.value;
        selectedServer = e.target.value;
    });
    
    // Config tab switching
    elements.configTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const configTab = btn.dataset.configTab;
            switchConfigTab(configTab);
        });
    });
    
    // Save buttons
    elements.savePropertiesBtn.addEventListener('click', saveProperties);
    elements.saveConfigBtn.addEventListener('click', saveServerConfig);
    elements.saveScriptBtn.addEventListener('click', saveStartScript);
    
    // Server Components Tab Event Listeners
    elements.componentsSearchBtn.addEventListener('click', searchComponentsServers);
    elements.componentsSelectBtn.addEventListener('click', selectComponentsServer);
    
    // Component tab switching
    elements.componentTabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const componentTab = btn.dataset.componentTab;
            switchComponentTab(componentTab);
        });
    });
}

// Switch main tabs
function switchTab(tabName) {
    // Update active tab buttons
    elements.tabBtns.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Update active tab contents
    elements.tabContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === tabName) {
            content.classList.add('active');
        }
    });
    
    // Refresh data if switching to server details tab
    if (tabName === 'server-details' && connected) {
        refreshServerStatus();
    }
}

// Switch config tabs
function switchConfigTab(tabName) {
    // Update active config tab buttons
    elements.configTabBtns.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.configTab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Update active config tab contents
    elements.configTabContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === tabName) {
            content.classList.add('active');
        }
    });
}

// Switch component tabs
function switchComponentTab(tabName) {
    // Update active component tab buttons
    elements.componentTabBtns.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.componentTab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Update active component tab contents
    elements.componentTabContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === tabName) {
            content.classList.add('active');
        }
    });
}

// WebSocket message sending
function sendWebSocketMessage(action, data = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        const message = JSON.stringify({ action, ...data });
        ws.send(message);
        console.log('Sent message:', message);
    } else {
        console.error('WebSocket is not connected');
        showMessage('WebSocket连接已断开，请刷新页面重试', 'error');
    }
}

// Refresh servers list
function refreshServers() {
    sendWebSocketMessage('refresh_servers');
    showMessage('正在刷新服务器列表...', 'info');
}

// Update server list in dropdown
function updateServerList(servers) {
    elements.serverProcessSelect.innerHTML = '<option value="">选择服务器进程</option>';
    
    servers.forEach(server => {
        // Handle both old and new formats for backward compatibility
        const serverName = typeof server === 'string' ? server : server.name;
        const displayName = typeof server === 'string' 
            ? (serverInfoMap[serverName]?.server_name || serverName) 
            : server.display_name;
        
        const option = document.createElement('option');
        option.value = serverName;
        option.textContent = displayName;
        elements.serverProcessSelect.appendChild(option);
    });
    
    showMessage('服务器列表已刷新', 'success');
}

// Connect to server
async function connectToServer() {
    const serverName = elements.serverProcessSelect.value;
    
    if (!serverName) {
        showMessage('请选择一个服务器进程', 'error');
        return;
    }
    
    if (isConnecting) {
        return;
    }
    
    isConnecting = true;
    elements.connectBtn.disabled = true;
    elements.connectBtn.textContent = '连接中...';
    
    try {
        sendWebSocketMessage('connect_server', { server_name: serverName });
        // The actual connection will be handled by the WebSocket response
    } catch (error) {
        console.error('Error connecting to server:', error);
        showMessage('连接服务器失败', 'error');
        isConnecting = false;
        elements.connectBtn.disabled = false;
        elements.connectBtn.textContent = '连接';
    }
}

// Handle successful connection
function handleConnectSuccess(server) {
    connected = true;
    currentServer = server;
    
    // Update UI
    elements.connectBtn.disabled = true;
    elements.connectBtn.textContent = '已连接';
    elements.executeBtn.disabled = false;
    elements.terminateBtn.disabled = false;
    elements.connectionStatus.textContent = `${server.server_name} Minecraft ${server.game_version} ${server.platform_type} ${server.platform_version}`;
    elements.connectionStatus.classList.add('connected');
    
    // Clear console output
    clearConsole();
    
    showMessage(`成功连接到服务器：${server.server_name}`, 'success');
    isConnecting = false;
}

// Update server status
function updateServerStatus(systemInfo, platformType) {
    // Update charts
    updateChart(memoryChart, systemInfo.memory_usage);
    updateChart(cpuChart, systemInfo.cpu_usage);
    
    // Update status items
    document.getElementById('network-io').textContent = `${formatBytes(systemInfo.network_io.bytes_sent)}/s ↑ / ${formatBytes(systemInfo.network_io.bytes_recv)}/s ↓`;
    document.getElementById('cpu-info').textContent = `${systemInfo.cpu_frequency.toFixed(0)} MHz / ${systemInfo.cpu_usage.toFixed(1)}%`;
    
    // Update memory info with actual total memory and usage
    document.getElementById('memory-info').textContent = `${formatBytes(systemInfo.memory_total)} / ${systemInfo.memory_usage.toFixed(1)}%`;
    
    // Update TPS, MSPT, and players info
    const sparkInstalled = systemInfo.spark_installed;
    // Allow TPS/MSPT/players display for Paper servers even without Spark
    const canDisplayMetrics = connected && (sparkInstalled || platformType === 'Paper');
    
    if (canDisplayMetrics) {
        document.getElementById('tps').textContent = typeof systemInfo.tps === 'number' ? systemInfo.tps.toFixed(1) : systemInfo.tps;
        document.getElementById('mspt').textContent = typeof systemInfo.mspt === 'number' ? systemInfo.mspt.toFixed(1) : systemInfo.mspt;
        document.getElementById('players').textContent = `${systemInfo.players_online}/${systemInfo.players_max}`;
    } else {
        // Show spark installation message if connected but neither spark is installed nor it's a Paper server
        const sparkMessage = connected ? '安装Spark模组或插件以启用此监控' : '--';
        document.getElementById('tps').textContent = sparkMessage;
        document.getElementById('mspt').textContent = sparkMessage;
        document.getElementById('players').textContent = sparkMessage;
    }
}

// Update chart
function updateChart(chart, value) {
    chart.data.datasets[0].data = [value, 100 - value];
    chart.update();
    
    // Update chart center text (using a custom plugin would be better, but this works for now)
    const canvas = chart.canvas;
    const ctx = canvas.getContext('2d');
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    
    // Clear the center area
    ctx.clearRect(centerX - 50, centerY - 20, 100, 40);
    
    // Draw the percentage text
    ctx.font = 'bold 24px Arial';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(`${value.toFixed(1)}%`, centerX, centerY);
}

// Append to console
function appendToConsole(text) {
    const logLine = document.createElement('div');
    logLine.textContent = text;
    elements.consoleOutput.appendChild(logLine);
    elements.consoleOutput.scrollTop = elements.consoleOutput.scrollHeight;
}

// Clear console
function clearConsole() {
    elements.consoleOutput.innerHTML = '';
}

// Execute command
function executeCommand() {
    const command = elements.consoleInput.value.trim();
    if (!command) {
        return;
    }
    
    if (!connected) {
        showMessage('未连接到服务器', 'error');
        return;
    }
    
    sendWebSocketMessage('execute_command', { command });
    elements.consoleInput.value = '';
    appendToConsole(`> ${command}`);
}

// Terminate connection (only disconnect client from server, don't stop the server process)
function terminateConnection() {
    if (!connected) {
        return;
    }
    
    // Just disconnect client from server, don't send stop command
    const serverName = currentServer.server_name;
    handleServerStopped(serverName);
    resetAdvancedData();
    showMessage(`已断开与服务器 ${serverName} 的连接`, 'info');
}

// Handle server stopped
function handleServerStopped(serverName) {
    connected = false;
    currentServer = null;
    
    // Update UI
    elements.connectBtn.disabled = false;
    elements.connectBtn.textContent = '连接';
    elements.executeBtn.disabled = true;
    elements.terminateBtn.disabled = true;
    elements.connectionStatus.textContent = '未连接';
    elements.connectionStatus.classList.remove('connected');
    
    // Clear console output
    clearConsole();
    
    showMessage(`与服务器 ${serverName} 的连接已终止`, 'info');
}

// Search servers for config
function searchServers() {
    sendWebSocketMessage('search_servers');
    showMessage('正在搜索服务器...', 'info');
}

// Update config server list
function updateConfigServerList(servers) {
    // Store current selection to preserve it
    const currentValue = elements.configServerSelect.value;
    
    // Clear and update serverInfoMap
    serverInfoMap = {};
    
    // Update config page server list
    elements.configServerSelect.innerHTML = '<option value="">选择游戏服务端</option>';
    elements.componentsServerSelect.innerHTML = '<option value="">选择游戏服务端</option>';
    
    servers.forEach(server => {
        // Store server info in map for later use
        serverInfoMap[server.name] = server.info;
        
        const configOption = document.createElement('option');
        configOption.value = server.name;
        configOption.textContent = server.display_name;
        configOption.disabled = !server.valid;
        elements.configServerSelect.appendChild(configOption);
        
        // Add same option to components page
        const componentsOption = document.createElement('option');
        componentsOption.value = server.name;
        componentsOption.textContent = server.display_name;
        componentsOption.disabled = !server.valid;
        elements.componentsServerSelect.appendChild(componentsOption);
    });
    
    // Restore previous selection if it still exists
    if (currentValue) {
        elements.configServerSelect.value = currentValue;
        elements.componentsServerSelect.value = currentValue;
        selectedServer = currentValue;
    }
    
    showMessage('服务器搜索完成', 'success');
}

// Select server for config
function selectServer() {
    const serverName = elements.configServerSelect.value;
    
    if (!serverName) {
        showMessage('请选择一个服务器', 'error');
        return;
    }
    
    sendWebSocketMessage('select_server', { server_name: serverName });
    showMessage(`正在加载服务器 ${serverName} 的配置...`, 'info');
}

// Handle server selected for config
function handleServerSelected(server) {
    // Update UI
    elements.startServerBtn.disabled = false;
    
    // Fill in properties
    fillProperties(server.info);
    
    // Fill in config
    fillConfig(server.properties);
    
    // Fill in start script
    elements.startScriptContent.value = server.start_script;
    
    showMessage('服务器配置已加载', 'success');
}

// Fill properties
function fillProperties(info) {
    elements.propertiesList.innerHTML = '';
    
    Object.entries(info).forEach(([key, value]) => {
        // Filter out RCON-related properties from server properties page
        if (key === 'rcon_password' || key === 'rcon_port') {
            return; // Skip RCON password and port in server details page
        }
        
        const propertyItem = createPropertyItem(key, value);
        elements.propertiesList.appendChild(propertyItem);
    });
}

// Fill config
function fillConfig(properties) {
    elements.configList.innerHTML = '';
    
    Object.entries(properties).forEach(([key, value]) => {
        // Filter out RCON-related properties from server config page
        if (key === 'enable-rcon' || key === 'rcon.password' || key === 'rcon.port') {
            return; // Skip RCON-related properties in server config page
        }
        
        const configItem = createConfigItem(key, value);
        elements.configList.appendChild(configItem);
    });
}

// Create property item
function createPropertyItem(key, value) {
    const div = document.createElement('div');
    div.className = 'property-item';
    
    div.innerHTML = `
        <span class="property-label">${formatKey(key)}</span>
        <div class="property-value">
            <input type="text" value="${value}" data-key="${key}">
        </div>
    `;
    
    return div;
}

// Create config item
function createConfigItem(key, value) {
    const div = document.createElement('div');
    div.className = 'config-item';
    
    // Determine input type based on value
    let inputType = 'text';
    if (value === 'true' || value === 'false') {
        inputType = 'select';
    } else if (!isNaN(value) && value.includes('.')) {
        inputType = 'number';
    } else if (!isNaN(value)) {
        inputType = 'number';
    }
    
    let inputHTML = '';
    if (inputType === 'select') {
        inputHTML = `
            <select data-key="${key}">
                <option value="true" ${value === 'true' ? 'selected' : ''}>true</option>
                <option value="false" ${value === 'false' ? 'selected' : ''}>false</option>
            </select>
        `;
    } else {
        inputHTML = `<input type="${inputType}" value="${value}" data-key="${key}">`;
    }
    
    div.innerHTML = `
        <span class="config-label">${formatKey(key)}</span>
        <div class="config-value">
            ${inputHTML}
        </div>
    `;
    
    return div;
}

// Format key for display
function formatKey(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

// Panel Settings functions

// Search for background images
async function searchBackgrounds() {
    showMessage('正在搜索背景图片...', 'info');
    
    try {
        // Send API request to get real background images from server
        const response = await fetch('/api/backgrounds');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const backgrounds = await response.json();
        
        // Update background select options with real images
        updateBackgroundOptions(backgrounds);
        
        showMessage(`找到 ${backgrounds.length} 张背景图片`, 'success');
    } catch (error) {
        console.error('Error searching backgrounds:', error);
        showMessage('搜索背景图片失败，请重试', 'error');
    }
}

// Update background select options
function updateBackgroundOptions(backgrounds) {
    // Clear existing options except default
    const defaultOption = elements.backgroundSelect.querySelector('option[value="default"]');
    elements.backgroundSelect.innerHTML = '';
    elements.backgroundSelect.appendChild(defaultOption);
    
    // Add new background options
    backgrounds.forEach(background => {
        const option = document.createElement('option');
        option.value = background;
        option.textContent = background;
        elements.backgroundSelect.appendChild(option);
    });
}

// Update background preview
function updateBackgroundPreview() {
    const selectedBackground = elements.backgroundSelect.value;
    const preview = elements.backgroundPreview;
    
    // Clear existing preview
    preview.innerHTML = '';
    
    if (selectedBackground === 'default') {
        // Default background
        preview.innerHTML = '<div class="preview-placeholder">默认黑色背景</div>';
        preview.style.background = 'var(--bg-darker)';
    } else {
        // Custom background
        const img = document.createElement('img');
        // Use the actual path to the background image
        img.src = `/static/background/${encodeURIComponent(selectedBackground)}`;
        img.alt = selectedBackground;
        preview.appendChild(img);
    }
}

// Save and apply settings
function saveAndApplySettings() {
    const settings = {
        outputRate: parseInt(elements.outputRate.value) || 100,
        background: elements.backgroundSelect.value
    };
    
    showMessage('正在保存并应用设置...', 'info');
    
    // In a real implementation, this would send the settings to the server via WebSocket
    // and the server would save them and apply them
    
    // For now, just simulate saving and applying the settings
    console.log('Saving settings:', settings);
    
    // Apply background setting
    applyBackground(settings.background);
    
    // Show success message
    showMessage('设置保存并应用成功！', 'success');
}

// Apply background setting with fade transition
function applyBackground(background) {
    const body = document.body;
    
    if (background === 'default') {
        // Default background
        body.style.background = 'var(--bg-dark)';
        body.style.backgroundImage = '';
        body.style.backgroundSize = '';
        body.style.backgroundPosition = '';
        body.style.backgroundRepeat = '';
        body.style.backdropFilter = '';
    } else {
        // Custom background with blur effect
        body.style.background = '';
        body.style.backgroundImage = `url(/static/background/${encodeURIComponent(background)})`;
        body.style.backgroundSize = 'cover';
        body.style.backgroundPosition = 'center';
        body.style.backgroundRepeat = 'no-repeat';
        // The blur effect is handled by the CSS backdrop-filter on the dashboard container
    }
}

// Save properties
function saveProperties() {
    const serverName = elements.configServerSelect.value;
    if (!serverName) {
        showMessage('请先选择服务器', 'error');
        return;
    }
    
    const properties = {};
    elements.propertiesList.querySelectorAll('.property-item input').forEach(input => {
        const key = input.dataset.key;
        properties[key] = input.value;
    });
    
    sendWebSocketMessage('save_config', {
        server_name: serverName,
        config_type: 'version',
        config_data: properties
    });
}

// Save server config
function saveServerConfig() {
    const serverName = elements.configServerSelect.value;
    if (!serverName) {
        showMessage('请先选择服务器', 'error');
        return;
    }
    
    const config = {};
    elements.configList.querySelectorAll('.config-item input, .config-item select').forEach(input => {
        const key = input.dataset.key;
        config[key] = input.value;
    });
    
    sendWebSocketMessage('save_config', {
        server_name: serverName,
        config_type: 'properties',
        config_data: config
    });
}

// Save start script
function saveStartScript() {
    const serverName = elements.configServerSelect.value;
    if (!serverName) {
        showMessage('请先选择服务器', 'error');
        return;
    }
    
    const script = elements.startScriptContent.value;
    
    sendWebSocketMessage('save_config', {
        server_name: serverName,
        config_type: 'start_script',
        config_data: script
    });
}

// Start server
function startServer() {
    const serverName = elements.configServerSelect.value;
    if (!serverName) {
        showMessage('请选择一个服务器', 'error');
        return;
    }
    
    sendWebSocketMessage('start_server', { server_name: serverName });
    showMessage(`正在启动服务器：${serverName}`, 'info');
}

// Handle server started
function handleServerStarted(serverName) {
    showMessage(`服务器 ${serverName} 启动成功！`, 'success');
}

// Search servers for components
function searchComponentsServers() {
    // Same functionality as searchServers for config page
    searchServers();
}

// Select server for components
function selectComponentsServer() {
    const serverName = elements.componentsServerSelect.value;
    
    if (!serverName) {
        showMessage('请选择一个服务器', 'error');
        return;
    }
    
    sendWebSocketMessage('get_components', { server_name: serverName });
    showMessage(`正在获取服务器组件：${serverName}`, 'info');
}

// Show components data
function showComponents(serverName, components) {
    // Get available component types
    const availableComponents = Object.keys(components);
    
    // Update component tab buttons visibility
    elements.componentTabBtns.forEach(btn => {
        const componentType = btn.dataset.componentTab;
        if (availableComponents.includes(componentType)) {
            btn.style.display = 'inline-block';
        } else {
            btn.style.display = 'none';
        }
    });
    
    // Show first available tab if no tab is active
    const activeBtn = document.querySelector('.component-tab-btn.active');
    if (!activeBtn || !availableComponents.includes(activeBtn.dataset.componentTab)) {
        const firstAvailableBtn = document.querySelector('.component-tab-btn:not([style*="display: none"])');
        if (firstAvailableBtn) {
            switchComponentTab(firstAvailableBtn.dataset.componentTab);
        }
    }
    
    // Render components for each type
    for (const [componentType, files] of Object.entries(components)) {
        renderComponentList(componentType, files, serverName);
    }
    
    // Hide tabs for unavailable components
    elements.componentTabContents.forEach(content => {
        const componentType = content.id;
        if (!availableComponents.includes(componentType)) {
            content.innerHTML = '<div class="empty-state">此组件类型不可用</div>';
        }
    });
    
    showMessage(`成功加载服务器 ${serverName} 的组件`, 'success');
}

// Render component list
function renderComponentList(componentType, files, serverName) {
    const contentElement = document.getElementById(componentType);
    
    if (files.length === 0) {
        contentElement.innerHTML = '<div class="empty-state">这个目录空空如也</div>';
        return;
    }
    
    // Sort files by name
    files.sort((a, b) => a.name.localeCompare(b.name));
    
    // Create file list
    const fileList = document.createElement('div');
    fileList.className = 'file-list';
    
    files.forEach(file => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        
        // File info
        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info';
        fileInfo.innerHTML = `
            <div class="file-name">${file.name}</div>
            <div class="file-size">${formatBytes(file.size)}</div>
        `;
        
        fileItem.appendChild(fileInfo);
        
        // Add delete button for schematics
        if (componentType === 'schematics') {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'btn btn-danger btn-sm delete-btn';
            deleteBtn.textContent = '删除';
            deleteBtn.addEventListener('click', () => deleteSchematic(serverName, file.name));
            fileItem.appendChild(deleteBtn);
        }
        
        fileList.appendChild(fileItem);
    });
    
    contentElement.innerHTML = '';
    contentElement.appendChild(fileList);
}

// Delete schematic
function deleteSchematic(serverName, schematicName) {
    if (confirm(`确定要删除蓝图 ${schematicName} 吗？`)) {
        sendWebSocketMessage('delete_schematic', {
            server_name: serverName,
            schematic_name: schematicName
        });
    }
}

// Show message
function showMessage(message, type = 'info') {
    // Remove existing messages
    const existingMessages = document.querySelectorAll('.message');
    existingMessages.forEach(msg => msg.remove());
    
    // Create new message
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.textContent = message;
    
    // Insert at top of current tab content
    const activeTab = document.querySelector('.tab-content.active');
    activeTab.insertBefore(messageDiv, activeTab.firstChild);
    
    // Auto remove after 3 seconds
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.remove();
        }
    }, 3000);
}

// Format bytes
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Clear console
function clearConsole() {
    elements.consoleOutput.innerHTML = '';
}

// Refresh server status (for when switching to the server details tab)
function refreshServerStatus() {
    // This would trigger a status update from the server
    sendWebSocketMessage('refresh_status');
}

// Switch config tab
function switchConfigTab(tabName) {
    // Update active config tab buttons
    elements.configTabBtns.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.configTab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Update active config tab contents
    elements.configTabContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === tabName) {
            content.classList.add('active');
        }
    });
}

// Reset advanced data values to default
function resetAdvancedData() {
    // Reset UI elements
    document.getElementById('tps').textContent = '--';
    document.getElementById('mspt').textContent = '--';
    document.getElementById('players').textContent = '--/--';
}

// Switch component tab
function switchComponentTab(tabName) {
    // Update active component tab buttons
    elements.componentTabBtns.forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.componentTab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Update active component tab contents
    elements.componentTabContents.forEach(content => {
        content.classList.remove('active');
        if (content.id === tabName) {
            content.classList.add('active');
        }
    });
}
