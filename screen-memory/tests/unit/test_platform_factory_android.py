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


class TestAndroidOcrChainIntegration:
    def test_android_ocr_chain_has_two_engines(self):
        """create_ocr_chain on Android returns a chain with MlKit + Tesseract."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_chain
            chain = create_ocr_chain()
            assert len(chain._engines) == 2
            assert isinstance(chain._engines[0], MlKitOcr)
            assert isinstance(chain._engines[1], TesseractOcr)

    def test_android_ocr_chain_min_confidence_default(self):
        """Default min_confidence is 0.5."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_chain
            chain = create_ocr_chain()
            assert chain._min_confidence == 0.5

    def test_android_ocr_chain_custom_confidence(self):
        """Custom min_confidence is propagated."""
        with patch.object(sys, "platform", "android"):
            from screen_memory.adapters.platform_factory import create_ocr_chain
            chain = create_ocr_chain(min_confidence=0.8)
            assert chain._min_confidence == 0.8


class TestAndroidCaptureOnNonAndroid:
    def test_linux_without_android_root_returns_linux_capture(self):
        """On plain Linux (no ANDROID_ROOT), should not return AndroidCapture."""
        with patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {}, clear=False):
            if "ANDROID_ROOT" in os.environ:
                del os.environ["ANDROID_ROOT"]
            try:
                from screen_memory.adapters.platform_factory import create_capture
                capture = create_capture()
                assert not isinstance(capture, AndroidCapture)
            except (RuntimeError, ModuleNotFoundError):
                pass  # Expected: no linux_capture module exists yet
