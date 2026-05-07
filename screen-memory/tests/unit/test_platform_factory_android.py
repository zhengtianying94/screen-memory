# tests/unit/test_platform_factory_android.py
"""Tests for platform_factory Android detection and wiring."""

import os
import sys
from unittest.mock import patch

import pytest

from screen_memory.adapters.android_capture import AndroidCapture
from screen_memory.adapters.mlkit_ocr import MlKitOcr
from screen_memory.adapters.tesseract_ocr import TesseractOcr


class TestAndroidDetection:
    def test_create_capture_returns_android_on_android_platform(self):
        """When sys.platform is 'android', create_capture returns AndroidCapture."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_capture
            capture = create_capture()
            assert isinstance(capture, AndroidCapture)

    def test_create_capture_returns_android_with_env_var(self):
        """When ANDROID_ROOT env var is set, create_capture returns AndroidCapture."""
        with patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            from screen_memory.adapters.platform_factory import create_capture
            capture = create_capture()
            assert isinstance(capture, AndroidCapture)


class TestAndroidOcrChain:
    def test_android_platform_has_mlkit_first(self):
        """Android OCR chain puts MlKitOcr as the first engine."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_engines
            engines = create_ocr_engines()
            assert len(engines) >= 1
            assert isinstance(engines[0], MlKitOcr)

    def test_android_chain_order_mlkit_then_tesseract(self):
        """Android OCR chain is: MlKitOcr -> TesseractOcr."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_engines
            engines = create_ocr_engines()
            assert isinstance(engines[0], MlKitOcr)
            assert isinstance(engines[1], TesseractOcr)
            assert len(engines) == 2
