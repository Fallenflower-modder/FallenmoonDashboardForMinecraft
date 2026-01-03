# Fallenmoon Dashboard 项目文档

## 1. 项目介绍

Fallenmoon Dashboard 是一个基于 B/S 架构的 Minecraft 服务器管理面板，提供实时监控、服务器管理、配置修改和组件管理等功能。该面板采用 Flask 框架开发，使用 WebSocket 进行实时通信，支持多服务器管理和监控。

## 2. 项目需求

### 2.1 核心功能需求

- **服务器监控**：实时监控服务器状态，包括 TPS、MSPT、玩家数量、CPU/内存使用情况等
- **服务器管理**：支持服务器启动、停止、重启等操作
- **实时日志**：实时查看服务器日志输出
- **指令执行**：通过面板执行 Minecraft 服务器指令
- **配置管理**：修改服务器配置文件
- **组件管理**：管理服务器的模组、插件、数据包等组件
- **崩溃分析**：（待开发）分析服务器崩溃日志

### 2.2 技术需求

- **实时通信**：使用 WebSocket 实现实时数据传输
- **多服务器支持**：支持同时管理多个 Minecraft 服务器
- **跨平台兼容**：支持 Windows 系统
- **安全性**：安全的 RCON 连接管理
- **可靠性**：稳定的服务器状态监控

## 3. 技术栈

### 3.1 后端技术

- **框架**：Flask
- **异步编程**：asyncio
- **WebSocket**：websockets
- **服务器管理**：subprocess、psutil
- **RCON 通信**：自定义 RCON 客户端
- **文件操作**：os、shutil

### 3.2 前端技术

- **HTML/CSS**：基础页面结构和样式
- **JavaScript**：客户端逻辑
- **图表库**：Chart.js

## 4. 项目结构

```
MinecraftDashboard/
├── server/                      # 后端代码
│   ├── __init__.py
│   ├── app.py                   # Flask 应用入口
│   ├── server_manager.py        # 服务器管理核心逻辑
│   ├── websocket_server.py      # WebSocket 服务器
│   ├── static/                  # 静态资源
│   │   ├── css/
│   │   │   └── style.css
│   │   └── js/
│   │       └── main.js
│   └── templates/               # HTML 模板
│       └── index.html
├── cached_minecraft_servers/     # 缓存的 Minecraft 服务器
├── start_full_serves.py          # 启动脚本
└── project_document/             # 项目文档
    └── Fallenmoon_Dashboard_Documentation.md
```

## 5. 关键实现和代码

### 5.1 WebSocket 通信

**文件**: `server/websocket_server.py`

实现了 WebSocket 服务器，用于实时传输服务器状态、日志和命令结果。

```python
async def start_websocket_server():
    server = await websockets.serve(handle_client, '0.0.0.0', 9001)
    asyncio.create_task(send_server_status())
    asyncio.create_task(send_server_logs())
    asyncio.create_task(check_server_processes())
    await server.wait_closed()
```

### 5.2 服务器状态监控

**文件**: `server/websocket_server.py`

通过 RCON 协议获取服务器状态数据，包括 TPS、MSPT 和玩家信息。

```python
async def send_server_status():
    global rotation_counter, persistent_rcon_client, persistent_rcon_server
    # ... 状态获取逻辑
    if rcon_available:
        # 轮流获取 TPS、MSPT 和玩家信息
        if rotation_counter == 0:  # Get TPS from tps command
            tps_result = persistent_rcon_client.send_command('tps')
            # ... 解析 TPS 数据
        elif rotation_counter == 1:  # Get MSPT from mspt command
            mspt_result = persistent_rcon_client.send_command('mspt')
            # ... 解析 MSPT 数据
        elif rotation_counter == 2:  # Get Players from list command
            list_result = persistent_rcon_client.send_command('list')
            # ... 解析玩家数据
```

### 5.3 日志缓存机制

**文件**: `server/websocket_server.py`

实现了日志缓存机制，避免面板服务端持续占用日志文件导致游戏服务端无法删除。

```python
# Log cache for each server
log_caches = {}

async def monitor_server_logs(server_path, server_name):
    # ... 日志监控逻辑
    if server_name not in log_caches:
        log_caches[server_name] = []
    # ... 日志缓存逻辑
```

### 5.4 服务器管理

**文件**: `server/server_manager.py`

负责服务器的扫描、验证和配置管理。

```python
class ServerManager:
    @staticmethod
    def scan_servers():
        # 扫描所有服务器目录
        pass
    
    @staticmethod
    def _check_server_validity(server_path):
        # 检查服务器有效性
        pass
    
    @staticmethod
    def _generate_rcon_password(length=16):
        # 生成 RCON 密码
        pass
```

### 5.5 客户端逻辑

**文件**: `server/static/js/main.js`

实现了客户端与服务器的通信和界面更新逻辑。

```javascript
function initializeWebSocket() {
    ws = new WebSocket('ws://localhost:9001');
    ws.onmessage = (event) => {
        handleWebSocketMessage(event.data);
    };
    // ... 其他 WebSocket 事件处理
}

function handleWebSocketMessage(message) {
    const data = JSON.parse(message);
    switch (data.type) {
        case 'server_status':
            updateServerStatus(data.system_info, data.platform_type);
            break;
        case 'server_log':
            appendToConsole(data.log);
            break;
        // ... 其他消息类型处理
    }
}
```

## 6. 技术遗留问题

### 6.1 架构问题

- **缺乏事件总线**：当前代码采用直接调用方式，模块间耦合度高，不利于扩展
- **WebSocket 设计**：WebSocket 处理逻辑较为复杂，缺乏清晰的消息路由机制
- **状态管理**：服务器状态管理分散在多个函数中，缺乏集中管理

### 6.2 性能问题

- **日志处理**：虽然实现了日志缓存，但仍存在优化空间
- **RCON 连接管理**：当前采用轮询方式获取数据，可能导致性能瓶颈

### 6.3 代码质量问题

- **代码重复**：部分功能存在代码重复，如 RCON 连接创建
- **错误处理**：部分错误处理不够完善
- **文档缺失**：部分代码缺乏注释和文档

## 7. 项目进度

### 7.1 已完成功能

- ✅ 服务器监控（TPS、MSPT、玩家数量等）
- ✅ 实时日志查看
- ✅ 指令执行
- ✅ 服务器启动/停止
- ✅ 配置管理
- ✅ 组件管理
- ✅ 日志缓存机制
- ✅ WebSocket 连接稳定性优化

### 7.2 待开发功能

- ⏳ 崩溃分析助手
- ⏳ 多服务器同时监控
- ⏳ 更完善的权限管理
- ⏳ 事件总线化重构

## 8. 后续开发计划

### 8.1 事件总线化重构

当前代码采用直接调用方式，模块间耦合度高，不利于扩展和维护。后续计划引入事件总线机制，实现：

1. **事件驱动架构**：
   - 定义清晰的事件类型（如服务器启动、停止、状态更新等）
   - 实现事件发布/订阅机制
   - 解耦模块间的直接依赖

2. **消息路由优化**：
   - 优化 WebSocket 消息处理，采用更清晰的路由机制
   - 实现消息类型的统一管理

3. **状态管理集中化**：
   - 实现集中的服务器状态管理
   - 提供统一的状态查询接口

4. **可扩展性提升**：
   - 设计插件式架构，支持功能扩展
   - 提供清晰的扩展接口

### 8.2 重构步骤

1. **设计事件模型**：定义核心事件类型和数据结构
2. **实现事件总线**：创建事件发布/订阅系统
3. **重构核心模块**：
   - WebSocket 服务器
   - 服务器状态监控
   - 服务器管理
4. **测试和验证**：确保重构后功能正常
5. **文档更新**：更新项目文档，记录重构后的架构

## 9. 关键 API 和类

### 9.1 WebSocket 消息类型

| 消息类型 | 说明 |
|---------|------|
| heartbeat | 心跳消息 |
| server_list | 服务器列表 |
| connect_success | 连接成功 |
| server_status | 服务器状态 |
| server_log | 服务器日志 |
| command_result | 命令执行结果 |
| server_stopped | 服务器停止 |
| server_started | 服务器启动 |
| server_search_result | 服务器搜索结果 |
| server_selected | 服务器选中 |
| config_saved | 配置保存 |
| components_data | 组件数据 |
| schematic_deleted | 蓝图删除 |
| refresh_servers | 刷新服务器列表 |
| error | 错误消息 |
| server_crashed | 服务器崩溃 |

### 9.2 核心类

- **RCONClient**：RCON 通信客户端，负责与 Minecraft 服务器进行 RCON 通信
- **ServerManager**：服务器管理类，负责服务器的扫描、验证和配置管理

## 10. 部署和运行

### 10.1 启动方式

```bash
python start_full_serves.py
```

### 10.2 访问地址

- **面板地址**：http://localhost:5000
- **WebSocket 地址**：ws://localhost:9001

## 11. 开发注意事项

### 11.1 代码风格

- 遵循 PEP 8 代码风格
- 为关键函数和类添加文档字符串
- 保持代码简洁和可读性

### 11.2 错误处理

- 添加适当的错误处理
- 记录详细的日志
- 提供友好的错误信息

### 11.3 性能考虑

- 避免阻塞操作
- 合理使用异步编程
- 优化数据库和文件操作

## 12. 总结

Fallenmoon Dashboard 是一个功能完整的 Minecraft 服务器管理面板，提供了服务器监控、管理、日志查看等核心功能。当前代码采用直接调用方式，模块间耦合度较高，后续计划进行事件总线化重构，提高系统的可扩展性和可维护性。

通过本次重构，将实现更清晰的架构设计、更高效的消息处理和更集中的状态管理，为后续功能扩展奠定基础。