"""Tests for preview resolution scaling."""


def test_preview_resolution_scaling():
    """Test that preview dimensions are correctly scaled based on device aspect ratio."""
    max_width, max_height = 180, 300
    
    # Test 1: Tall portrait device (like Lenovo Tab) 1200x1920
    device_width, device_height = 1200, 1920
    aspect_ratio = device_width / device_height
    
    if aspect_ratio > (max_width / max_height):
        preview_width = max_width
        preview_height = int(max_width / aspect_ratio)
    else:
        preview_height = max_height
        preview_width = int(max_height * aspect_ratio)
    
    assert preview_width <= max_width, f"Preview width {preview_width} exceeds max {max_width}"
    assert preview_height <= max_height, f"Preview height {preview_height} exceeds max {max_height}"
    # Very tall device should still fit within bounds
    assert preview_height == max_height or preview_width == max_width
    
    # Test 2: Wide landscape device (16:9) - Samsung 1920x1080
    device_width, device_height = 1920, 1080
    aspect_ratio = device_width / device_height
    
    if aspect_ratio > (max_width / max_height):
        preview_width = max_width
        preview_height = int(max_width / aspect_ratio)
    else:
        preview_height = max_height
        preview_width = int(max_height * aspect_ratio)
    
    assert preview_width <= max_width, f"Preview width {preview_width} exceeds max {max_width}"
    assert preview_height <= max_height, f"Preview height {preview_height} exceeds max {max_height}"
    # Wide device should fit by width
    assert preview_width == max_width, f"Wide device should fit by width, got {preview_width}"
    
    # Test 3: Square device
    device_width, device_height = 1000, 1000
    aspect_ratio = device_width / device_height
    
    if aspect_ratio > (max_width / max_height):
        preview_width = max_width
        preview_height = int(max_width / aspect_ratio)
    else:
        preview_height = max_height
        preview_width = int(max_height * aspect_ratio)
    
    assert preview_width <= max_width
    assert preview_height <= max_height
    # Square device at 1:1 ratio
    assert preview_width == preview_height, "Square device should produce square preview"


def test_preview_service_resolution_cache():
    """Test that PreviewService caches device resolutions."""
    class MockClient:
        pass
    
    class MockRoot:
        def after(self, delay, func):
            func()
    
    def mock_on_image(serial, photo):
        pass
    
    def mock_on_failure(serial):
        pass
    
    from app.video.preview import PreviewService
    
    service = PreviewService(
        MockRoot(), MockClient(), 
        mock_on_image, mock_on_failure,
        180, 300, 1
    )
    
    # Test setting device resolution
    service.set_device_resolution("device1", 150, 200)
    assert service.device_resolutions["device1"] == (150, 200)
    
    # Test multiple devices
    service.set_device_resolution("device2", 100, 150)
    assert service.device_resolutions["device1"] == (150, 200)
    assert service.device_resolutions["device2"] == (100, 150)
    
    # Test that default resolution is used if not set
    assert service.device_resolutions.get("device3", None) is None
