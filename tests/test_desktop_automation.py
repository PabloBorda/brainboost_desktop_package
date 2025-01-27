# tests/test_desktop_automation.py

import pytest
import platform
import os
import random
from pathlib import Path
from PIL import Image
from brainboost_desktop_package.Desktop import Desktop
from brainboost_configuration_package.BBConfig import BBConfig
from datetime import datetime  # Ensure correct import

# Override configurations for testing purposes
BBConfig.override('snapshots_database_enabled', False)
BBConfig.override('snapshots_database_path', '')
BBConfig.override('write_screenshots_to_files', True)  # Added override
TEST_IMAGES_DIR = Path(__file__).parent / "test_images"
BBConfig.override('snapshot_images', str(TEST_IMAGES_DIR))  # Ensure snapshot_images points to the test directory

# Ensure the test_images directory exists
TEST_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

@pytest.fixture
def desktop_instance():
    """Fixture to create a singleton instance of the Desktop class."""
    return Desktop.get_desktop_singleton()

def test_get_open_windows(desktop_instance):
    """Test that get_open_windows returns a list of window titles."""
    current_system = platform.system()
    
    if current_system == "Linux":
        open_windows = desktop_instance.get_open_windows()
        assert isinstance(open_windows, list), "Expected a list of window titles"
        if open_windows:
            assert all(isinstance(window, dict) for window in open_windows), "All window entries should be dictionaries"
    else:
        pytest.skip("This test is currently implemented for Linux systems only.")

def test_get_focused_window(desktop_instance):
    """Test that get_focused_window returns a dictionary or None."""
    current_system = platform.system()
    
    if current_system == "Linux":
        focused_window = desktop_instance.get_focused_window()
        assert isinstance(focused_window, (dict, type(None))), "Expected focused window to be a dictionary or None"
    else:
        pytest.skip("This test is currently implemented for Linux systems only.")

def test_get_screen_coordinates(desktop_instance):
    """Test that get_screen_coordinates returns a list of dictionaries with screen coordinates."""
    screen_coordinates = desktop_instance.get_screen_coordinates()
    assert isinstance(screen_coordinates, list), "Expected a list of screen coordinate dictionaries"
    for screen in screen_coordinates:
        assert isinstance(screen, dict), "Each screen coordinate should be a dictionary"
        assert "left" in screen and isinstance(screen["left"], int), "Each screen should have a 'left' key with an integer value"
        assert "top" in screen and isinstance(screen["top"], int), "Each screen should have a 'top' key with an integer value"
        assert "width" in screen and isinstance(screen["width"], int), "Each screen should have a 'width' key with an integer value"
        assert "height" in screen and isinstance(screen["height"], int), "Each screen should have a 'height' key with an integer value"

def test_get_window_coordinates(desktop_instance):
    """Test that get_window_coordinates returns a list of dictionaries with window coordinates."""
    current_system = platform.system()
    
    if current_system == "Linux":
        window_coordinates = desktop_instance.get_window_coordinates()
        assert isinstance(window_coordinates, list), "Expected a list of window coordinate dictionaries"
        for window in window_coordinates:
            assert isinstance(window, dict), "Each window coordinate should be a dictionary"
            assert "title" in window and isinstance(window["title"], str), "Each window should have a 'title' key with a string value"
            assert "left" in window and isinstance(window["left"], int), "Each window should have a 'left' key with an integer value"
            assert "top" in window and isinstance(window["top"], int), "Each window should have a 'top' key with an integer value"
            assert "width" in window and isinstance(window["width"], int), "Each window should have a 'width' key with an integer value"
            assert "height" in window and isinstance(window["height"], int), "Each window should have a 'height' key with an integer value"
    
    elif current_system == "Windows":
        import pygetwindow as gw  # Only import if on Windows
        windows = gw.getAllTitles()
        assert isinstance(windows, list), "Expected a list of window titles"
        if windows:
            assert all(isinstance(title, str) for title in windows), "All window titles should be strings"
    
    elif current_system == "Darwin":
        from Quartz import CGWindowListCopyWindowInfo, kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        
        window_list = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
        assert isinstance(window_list, list), "Expected a list of window dictionaries"
        for window in window_list:
            assert isinstance(window, dict), "Each window should be a dictionary"
            assert "kCGWindowName" in window, "Each window should have a 'kCGWindowName' key"
            assert "kCGWindowBounds" in window, "Each window should have a 'kCGWindowBounds' key"
            
            # Check bounds for window coordinates
            bounds = window["kCGWindowBounds"]
            assert "X" in bounds and isinstance(bounds["X"], int), "Each window should have an 'X' key in bounds with an integer value"
            assert "Y" in bounds and isinstance(bounds["Y"], int), "Each window should have a 'Y' key in bounds with an integer value"
            assert "Width" in bounds and isinstance(bounds["Width"], int), "Each window should have a 'Width' key in bounds with an integer value"
            assert "Height" in bounds and isinstance(bounds["Height"], int), "Each window should have a 'Height' key in bounds with an integer value"
    
    else:
        pytest.skip("This test is only implemented for Linux, Windows, and macOS systems.")

def test_take_fullscreen_screenshot(desktop_instance):
    """
    Test that take_fullscreen_screenshot captures the entire desktop,
    saves the image to tests/test_images, and verifies the image is valid.
    """
    try:
        screenshot = desktop_instance.take_fullscreen_screenshot()
        assert screenshot is not None, "Screenshot should not be None"

        # Save the screenshot to the test_images directory
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        screenshot_path = TEST_IMAGES_DIR / f'fullscreen_screenshot_{timestamp}.png'
        Image.fromarray(screenshot).save(screenshot_path)
        assert screenshot_path.exists(), f"Screenshot file {screenshot_path} should exist"

        # Open the saved image and verify its properties
        with Image.open(screenshot_path) as img:
            assert img.width > 0 and img.height > 0, "Image dimensions should be greater than zero"
            assert img.mode in ["RGB", "BGR"], f"Image mode should be RGB or BGR, got {img.mode}"

    except Exception as e:
        pytest.fail(f"take_fullscreen_screenshot failed with exception: {e}")

def test_take_window_screenshot(desktop_instance):
    """
    Test that take_screenshot_from_window captures a specific window,
    saves the image to tests/test_images, and verifies the image is valid.
    """
    current_system = platform.system()
    try:
        open_windows = desktop_instance.get_open_windows()
        assert isinstance(open_windows, list) and len(open_windows) > 0, "There should be at least one open window"

        # Select a random window
        random_window = random.choice(open_windows)
        window_title = random_window.get("title") or random_window.get("kCGWindowName") or "Unknown"
        screenshot = desktop_instance.take_screenshot_from_window(window_title)
        assert screenshot is not None, f"Screenshot for window '{window_title}' should not be None"

        # Save the screenshot to the test_images directory
        sanitized_title = "".join(c if c.isalnum() else "_" for c in window_title)[:50]  # Sanitize filename
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        screenshot_path = TEST_IMAGES_DIR / f'window_screenshot_{sanitized_title}_{timestamp}.png'
        screenshot.save(screenshot_path)
        assert screenshot_path.exists(), f"Screenshot file {screenshot_path} should exist"

        # Open the saved image and verify its properties
        with Image.open(screenshot_path) as img:
            assert img.width > 0 and img.height > 0, "Image dimensions should be greater than zero"
            assert img.mode in ["RGB", "BGR"], f"Image mode should be RGB or BGR, got {img.mode}"

    except Exception as e:
        pytest.fail(f"take_screenshot_from_window failed with exception: {e}")

def test_snapshot_saves_image_correctly(desktop_instance):
    """
    Test that the take_snapshot method captures the desktop and saves the snapshot correctly.
    """
    try:
        snapshot = desktop_instance.take_snapshot()
        assert snapshot is not None, "Snapshot should not be None"

        # If write_screenshots_to_files is enabled, verify the file is saved
        if BBConfig.get('write_screenshots_to_files'):
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            snapshot_dir = Path(BBConfig.get('snapshot_images'))
            snapshot_path = snapshot_dir / f'snapshot_{timestamp}.png'
            assert snapshot_path.exists(), f"Snapshot file {snapshot_path} should exist"

    except Exception as e:
        pytest.fail(f"take_snapshot failed with exception: {e}")

def test_grayscale_image_capture(desktop_instance):
    """
    Test that a captured screenshot can be converted to grayscale correctly.
    """
    try:
        screenshot = desktop_instance.take_fullscreen_screenshot()
        assert screenshot is not None, "Screenshot should not be None"

        # Convert to grayscale
        grayscale_image = Image.fromarray(screenshot).convert('L')  # 'L' mode is for (8-bit pixels, black and white)
        
        # Save the grayscale image
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        grayscale_path = TEST_IMAGES_DIR / f'grayscale_screenshot_{timestamp}.png'
        grayscale_image.save(grayscale_path)
        assert grayscale_path.exists(), f"Grayscale screenshot file {grayscale_path} should exist"

        # Verify that the image is indeed grayscale
        with Image.open(grayscale_path) as img:
            assert img.mode == 'L', f"Image mode should be 'L' for grayscale, got {img.mode}"

    except Exception as e:
        pytest.fail(f"Grayscale image capture failed with exception: {e}")

def test_black_and_white_image_capture(desktop_instance):
    """
    Test that a captured screenshot can be converted to black and white correctly.
    """
    try:
        screenshot = desktop_instance.take_fullscreen_screenshot()
        assert screenshot is not None, "Screenshot should not be None"

        # Convert to black and white using a threshold
        img = Image.fromarray(screenshot).convert('L')
        threshold = 128
        bw_image = img.point(lambda x: 255 if x > threshold else 0, '1')  # '1' mode is for 1-bit pixels, black and white

        # Save the black and white image
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        bw_path = TEST_IMAGES_DIR / f'black_white_screenshot_{timestamp}.png'
        bw_image.save(bw_path)
        assert bw_path.exists(), f"Black and white screenshot file {bw_path} should exist"

        # Verify that the image is indeed black and white
        with Image.open(bw_path) as img:
            assert img.mode == '1', f"Image mode should be '1' for black and white, got {img.mode}"

    except Exception as e:
        pytest.fail(f"Black and white image capture failed with exception: {e}")
