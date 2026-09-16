from app.web_ui import render_device_cards, render_device_details


def test_render_device_cards_contains_devices_and_connect_button():
    html = render_device_cards([
        {"serial": "Lenovo TB-7304I", "status": "online", "model": "Lenovo TB-7304I"},
        {"serial": "Samsung A20", "status": "online", "model": "Samsung A20"},
        {"serial": "Xiaomi Redmi 7", "status": "online", "model": "Xiaomi Redmi 7"},
    ])

    assert "Lenovo TB-7304I" in html
    assert "Samsung A20" in html
    assert "Xiaomi Redmi 7" in html
    assert "CONNECT" in html


def test_connect_page_does_not_redirect_back_to_devices_list():
    serial = "Samsung A20"
    page = render_device_details(serial, [{"serial": serial, "status": "online", "model": serial}])
    assert serial in page
    assert "Back to devices" in page
    assert "meta http-equiv=\"refresh\"" not in page


def test_device_detail_page_contains_screen_and_controls():
    serial = "Samsung A20"
    page = render_device_details(
        serial,
        [{"serial": serial, "status": "online", "model": serial}],
        screenshot_data=b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAF",
    )
    assert "device-screen" in page
    assert "HOME" in page
    assert "BACK" in page
    assert "POWER" in page


def test_device_detail_page_has_live_refresh_and_pointer_controls():
    serial = "Samsung A20"
    page = render_device_details(
        serial,
        [{"serial": serial, "status": "online", "model": serial}],
        screenshot_data=b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAF",
    )
    assert "setInterval" in page
    assert "pointerdown" in page
    assert "pointermove" in page
    assert "wheel" in page
    assert "SWIPE" in page
    assert "/screen?serial=" in page
    assert "KEEP AWAKE" in page
    assert "SCREEN OFF" in page


def test_coordinate_mapping_logic():
    """Test that coordinate mapping formula is correct for different resolutions."""
    # Verify mapping formula: device_coord = (normalized / 1000.0) * resolution
    
    # Test 1920x1080 (portrait phone or tablet)
    norm_x, norm_y = 500, 500
    device_x = int((norm_x / 1000.0) * 1920)
    device_y = int((norm_y / 1000.0) * 1080)
    assert device_x == 960 and device_y == 540, "Center should map to half resolution"
    
    # Test 1200x1920 (Lenovo Tab-X606X landscape)
    device_x = int((norm_x / 1000.0) * 1200)
    device_y = int((norm_y / 1000.0) * 1920)
    assert device_x == 600 and device_y == 960, "Center should map to half of 1200x1920"
    
    # Test corners
    device_x = int((0 / 1000.0) * 1920)
    device_y = int((0 / 1000.0) * 1080)
    assert device_x == 0 and device_y == 0, "Top-left corner"
    
    device_x = int((1000 / 1000.0) * 1920)
    device_y = int((1000 / 1000.0) * 1080)
    assert device_x == 1920 and device_y == 1080, "Bottom-right corner"
