"""
Comprehensive tests for Clipboard Privacy & Sensitive Data Protection
Tests Luhn algorithm, password patterns, tokens, private keys, memory hygiene,
and consent dialog functionality.
"""

import sys
import pytest
from PyQt6.QtWidgets import QApplication

from core.database import Database
from core.privacy import (
    is_luhn_valid,
    contains_credit_card,
    is_valid_tc_kimlik,
    contains_identity_number,
    is_complex_password,
    contains_sensitive_url_data,
    is_sensitive_text
)
from ui.clipboard_monitor import ClipboardMonitor
from ui.clipboard_consent_dialog import ClipboardConsentDialog


@pytest.fixture
def mem_db(tmp_path):
    return Database(str(tmp_path / "privacy_test.db"))


def test_luhn_and_credit_card_detection():
    # Valid credit card numbers (test numbers with valid Luhn checksums)
    # Visa test number
    valid_visa = "4532 0150 1234 5671"
    assert is_luhn_valid(valid_visa) is True
    assert contains_credit_card(valid_visa) is True
    assert is_sensitive_text(valid_visa) is True

    # Mastercard test number
    valid_mc = "5425-2334-3010-9903"
    assert is_luhn_valid(valid_mc) is True
    assert contains_credit_card(valid_mc) is True
    assert is_sensitive_text(valid_mc) is True

    # Invalid Luhn number (should not trigger false positive)
    invalid_cc = "4532 0150 1234 5674"
    assert is_luhn_valid(invalid_cc) is False
    assert contains_credit_card(invalid_cc) is False

    # Regular random numbers or phone numbers
    phone = "0532 123 45 67"
    assert contains_credit_card(phone) is False


def test_identity_number_detection():
    # Valid TC Kimlik algorithm test (generated test ID complying with algorithm: 10000000146)
    valid_tc = "10000000146"
    assert is_valid_tc_kimlik(valid_tc) is True
    assert contains_identity_number(valid_tc) is True
    assert is_sensitive_text(valid_tc) is True

    # Invalid TC Kimlik
    invalid_tc = "10000000145"
    assert is_valid_tc_kimlik(invalid_tc) is False

    # US SSN format
    ssn = "123-45-6789"
    assert contains_identity_number(ssn) is True
    assert is_sensitive_text(ssn) is True


def test_private_keys_detection():
    rsa_key = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Yv...fakekeycontent...
-----END RSA PRIVATE KEY-----
"""
    assert is_sensitive_text(rsa_key) is True

    ssh_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNza..."
    assert is_sensitive_text(ssh_key) is True

    pgp_key = "-----BEGIN PGP PRIVATE KEY BLOCK-----\nVersion: GnuPG..."
    assert is_sensitive_text(pgp_key) is True


def test_api_keys_and_tokens_detection():
    # JWT token (three base64 segments)
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    assert is_sensitive_text(jwt) is True

    # Bearer Token
    bearer = "Bearer ya29.a0AfH6SMDI_sample_token_content_1234567"
    assert is_sensitive_text(bearer) is True

    # GitHub token
    gh_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    assert is_sensitive_text(gh_token) is True

    # AWS Access Key ID
    aws_key = "AKIAIOSFODNN7EXAMPLE"
    assert is_sensitive_text(aws_key) is True

    # Google API Key
    google_key = "AIzaSyD-sample_google_api_key_123456"
    assert is_sensitive_text(google_key) is True

    # OpenAI API Key
    openai_key = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
    assert is_sensitive_text(openai_key) is True


def test_password_patterns():
    # Labeled passwords
    labeled_1 = "Password: SuperSecretPass123!"
    assert is_sensitive_text(labeled_1) is True

    labeled_2 = "kullanici: admin\nparola: C0mpl3xP@ss!"
    assert is_sensitive_text(labeled_2) is True

    labeled_3 = "api_key = abcdef1234567890"
    assert is_sensitive_text(labeled_3) is True

    # High entropy password without label
    raw_pwd = "X9#mQ2!zL8$vP1@w"
    assert is_complex_password(raw_pwd) is True
    assert is_sensitive_text(raw_pwd) is True


def test_url_with_sensitive_data():
    # URL with embedded credentials
    url_with_auth = "https://admin:my_secret_password@downloads.example.com/archive.zip"
    assert contains_sensitive_url_data(url_with_auth) is True
    assert is_sensitive_text(url_with_auth) is True
    assert ClipboardMonitor.analyze_url(url_with_auth) is None

    # URL with password query param
    url_with_pwd = "https://example.com/download.php?file=test.zip&password=Secret123"
    assert contains_sensitive_url_data(url_with_pwd) is True
    assert is_sensitive_text(url_with_pwd) is True
    assert ClipboardMonitor.analyze_url(url_with_pwd) is None

    # Clean, legitimate URLs must NOT be flagged as sensitive
    clean_media = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert is_sensitive_text(clean_media) is False
    assert ClipboardMonitor.analyze_url(clean_media) is not None

    clean_file = "https://cdn.example.com/releases/v1.0.0/setup.exe"
    assert is_sensitive_text(clean_file) is False
    assert ClipboardMonitor.analyze_url(clean_file) is not None


def test_clipboard_monitor_memory_hygiene_and_defaults():
    # 1. Defaults: Privacy by default (enabled=False)
    monitor = ClipboardMonitor()
    assert monitor.enabled is False

    # 2. Memory hygiene: Non-URL text is not stored in last_text
    # Simulate non-url text change
    monitor.enabled = True
    monitor.last_text = "https://previous.url/file.zip"
    
    # Pretend clipboard has a copied password
    class FakeClipboard:
        def __init__(self, val):
            self._text = val
        def text(self):
            return self._text

    monitor.clipboard = FakeClipboard("MySecretP@ssw0rd123!")
    monitor._on_clipboard_change()

    # Crucial assertion: plain password MUST NOT be stored in last_text
    assert monitor.last_text == ""

    # Pretend clipboard has a valid downloadable URL
    monitor.clipboard = FakeClipboard("https://sample.com/data.zip")
    detected = []
    monitor.link_detected.connect(lambda u, i: detected.append(u))
    monitor._on_clipboard_change()

    assert monitor.last_text == "https://sample.com/data.zip"
    assert len(detected) == 1

    # Pretend clipboard has a sensitive URL (with password query)
    monitor.clipboard = FakeClipboard("https://sample.com/data.zip?password=SuperSecret")
    monitor._on_clipboard_change()
    assert monitor.last_text == ""
    assert len(detected) == 1  # No new emission!


def test_clipboard_consent_dialog():
    app = QApplication.instance() or QApplication(sys.argv)
    dlg = ClipboardConsentDialog()
    assert dlg.windowTitle() == "Pano İzleme ve Gizlilik - RipSync"
    assert dlg.btn_enable is not None
    assert dlg.btn_disable is not None
    dlg.close()
