# Event types for the internal event bus

# WebSocket events
CLIENT_CONNECTED = "client.connected"
CLIENT_DISCONNECTED = "client.disconnected"

# Server events
SERVER_STARTED = "server.started"
SERVER_STOPPED = "server.stopped"
SERVER_CRASHED = "server.crashed"
SERVER_CONNECTED = "server.connected"
SERVER_STARTUP_COMPLETED = "server.startup.completed"

# Command events
COMMAND_EXECUTED = "command.executed"

# Status events
STATUS_UPDATED = "status.updated"
LOG_LINE_RECEIVED = "log.line.received"

# Refresh events
REFRESH_SERVERS = "refresh.servers"
