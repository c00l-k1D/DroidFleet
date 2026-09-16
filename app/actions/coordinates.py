"""Coordinate mapping utilities for converting screen coordinates to device pixels."""

from app.adb.client import AdbClient

# Cache for device resolutions to avoid repeated queries
_resolution_cache = {}


def get_device_resolution(client: AdbClient, serial: str) -> tuple[int, int]:
    """Get device resolution from cache or query it."""
    if serial in _resolution_cache:
        return _resolution_cache[serial]
    resolution = client.get_device_resolution(serial)
    _resolution_cache[serial] = resolution
    return resolution


def clear_resolution_cache():
    """Clear cached device resolutions (call after device reconnect)."""
    _resolution_cache.clear()


def normalize_to_device(norm_x: int, norm_y: int, client: AdbClient, serial: str) -> tuple[int, int]:
    """
    Convert normalized coordinates (0-1000 range) to device pixel coordinates.
    
    Args:
        norm_x: X coordinate in 0-1000 range
        norm_y: Y coordinate in 0-1000 range
        client: AdbClient instance
        serial: Device serial number
    
    Returns:
        (device_x, device_y) in actual device pixel coordinates
    """
    width, height = get_device_resolution(client, serial)
    device_x = int((norm_x / 1000.0) * width)
    device_y = int((norm_y / 1000.0) * height)
    return (device_x, device_y)
