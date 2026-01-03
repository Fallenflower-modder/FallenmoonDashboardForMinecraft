import asyncio
from typing import Any, Callable, Dict, Set

class EventBus:
    """Lightweight async event bus for internal server communication"""
    
    def __init__(self):
        # Dictionary mapping event names to sets of async handlers
        self._handlers: Dict[str, Set[Callable]] = {}
        # Dictionary mapping event names to sets of sync handlers
        self._sync_handlers: Dict[str, Set[Callable]] = {}
    
    def subscribe(self, event: str, handler: Callable) -> None:
        """Subscribe to an event with an async handler"""
        if event not in self._handlers:
            self._handlers[event] = set()
        self._handlers[event].add(handler)
    
    def subscribe_sync(self, event: str, handler: Callable) -> None:
        """Subscribe to an event with a sync handler"""
        if event not in self._sync_handlers:
            self._sync_handlers[event] = set()
        self._sync_handlers[event].add(handler)
    
    def unsubscribe(self, event: str, handler: Callable) -> None:
        """Unsubscribe an async handler from an event"""
        if event in self._handlers:
            self._handlers[event].discard(handler)
            # Clean up empty event handlers
            if not self._handlers[event]:
                del self._handlers[event]
    
    def unsubscribe_sync(self, event: str, handler: Callable) -> None:
        """Unsubscribe a sync handler from an event"""
        if event in self._sync_handlers:
            self._sync_handlers[event].discard(handler)
            # Clean up empty event handlers
            if not self._sync_handlers[event]:
                del self._sync_handlers[event]
    
    async def publish(self, event: str, **kwargs) -> None:
        """Publish an event to all subscribed handlers"""
        # Handle async handlers
        if event in self._handlers:
            # Create tasks for all async handlers
            tasks = []
            for handler in self._handlers[event]:
                try:
                    tasks.append(handler(**kwargs))
                except Exception as e:
                    print(f"Error in async handler for event {event}: {e}")
            
            # Run all tasks concurrently
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle sync handlers
        if event in self._sync_handlers:
            for handler in self._sync_handlers[event]:
                try:
                    handler(**kwargs)
                except Exception as e:
                    print(f"Error in sync handler for event {event}: {e}")
    
    def publish_sync(self, event: str, **kwargs) -> None:
        """Publish an event synchronously to all handlers"""
        # Handle sync handlers first
        if event in self._sync_handlers:
            for handler in self._sync_handlers[event]:
                try:
                    handler(**kwargs)
                except Exception as e:
                    print(f"Error in sync handler for event {event}: {e}")
    
    def clear(self) -> None:
        """Clear all event handlers"""
        self._handlers.clear()
        self._sync_handlers.clear()

# Create a global event bus instance
event_bus = EventBus()
