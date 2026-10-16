import os
import subprocess
import threading
import json
import re
import shlex
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List
import httpx

SHELL_UNSAFE_CHARS = re.compile(r'[;&|`$()<>\r\n\x00^"\']')
SHELL_UNSAFE_CHARS_URL = re.compile(r'[;|`$()<>\r\n\x00^"\']')

def sanitize_shell_variable(val: str, allow_ampersand: bool = False) -> str:
    """Removes dangerous shell metacharacters from template variables."""
    if not val:
        return ""
    pattern = SHELL_UNSAFE_CHARS_URL if allow_ampersand else SHELL_UNSAFE_CHARS
    return pattern.sub('', str(val)).strip()

def parse_command_template(command_template: str) -> List[str]:
    """
    Safely splits a command template into argument tokens without shell execution.
    Preserves Windows backslashes in paths and strips enclosing quotation marks.
    """
    if not command_template or not command_template.strip():
        return []

    is_windows = (os.name == 'nt')
    try:
        tokens = shlex.split(command_template, posix=not is_windows)
    except Exception:
        tokens = command_template.strip().split()

    cleaned = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        if is_windows:
            if (tok.startswith('"') and tok.endswith('"')) or (tok.startswith("'") and tok.endswith("'")):
                if len(tok) >= 2:
                    tok = tok[1:-1]
        cleaned.append(tok)
    return cleaned

def build_command_args(command_template: str, context: Dict[str, str]) -> List[str]:
    """
    Builds a secure argument list for subprocess.run(shell=False).
    Sanitizes context values and substitutes them into parsed tokens.
    """
    tokens = parse_command_template(command_template)
    if not tokens:
        return []

    safe_context = {}
    for key, val in context.items():
        is_url = ("{url}" in key.lower())
        safe_context[key] = sanitize_shell_variable(str(val), allow_ampersand=is_url)

    result_args = []
    for tok in tokens:
        arg = tok
        for k, v in safe_context.items():
            arg = arg.replace(k, v)
        result_args.append(arg)
    return result_args

def format_size_simple(bytes_val: int) -> str:
    """Format bytes into human-readable string without UI dependencies."""
    if bytes_val <= 0:
        return "Bilinmiyor"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0 or unit == 'TB':
            if unit in ('B', 'KB'):
                return f"{int(bytes_val)} {unit}"
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"

def build_template_context(rec: Dict[str, Any]) -> Dict[str, str]:
    """Builds template variable dictionary from a download record."""
    save_path = os.path.abspath(rec.get("save_path", "") or "")
    filename = rec.get("filename", "") or (os.path.basename(save_path) if save_path else "download")
    url = rec.get("url", "") or ""
    category = rec.get("category", "") or "Others"
    tot = rec.get("total_size", -1)
    done = rec.get("downloaded_size", 0)
    eff_size = tot if tot > 0 else done
    size_str = format_size_simple(eff_size)

    return {
        "{filepath}": save_path,
        "{filename}": filename,
        "{url}": url,
        "{category}": category,
        "{filesize}": size_str,
        "{bytes}": str(eff_size),
        "{status}": rec.get("status", "Completed")
    }

def substitute_variables(template: str, context: Dict[str, str]) -> str:
    """Substitutes placeholders like {filepath} with their actual values."""
    res = template
    for key, val in context.items():
        res = res.replace(key, str(val))
    return res

def run_post_download_command(command_template: str, context: Dict[str, str], timeout: float = 60.0):
    """
    Executes a custom CLI command asynchronously in the background.
    Uses subprocess.run with shell=False and argument list to prevent command injection.
    """
    if not command_template or not command_template.strip():
        return

    cmd_args = build_command_args(command_template, context)
    if not cmd_args:
        return

    def _runner():
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.run(
                cmd_args,
                shell=False,
                creationflags=creationflags,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except Exception as e:
            print(f"[PostDownload] Command failed to execute ({cmd_args}): {e}")

    threading.Thread(target=_runner, daemon=True).start()

def send_webhook_notification(webhook_url: str, context: Dict[str, str], timeout: float = 10.0, include_filepath: bool = False) -> Tuple[bool, str]:
    """
    Sends an HTTP POST webhook notification (compatible with Discord, Slack, and generic webhooks).
    Returns (success, message).
    If include_filepath is False, local disk paths are withheld to protect user privacy.
    """
    if not webhook_url or not webhook_url.strip():
        return False, "Boş Webhook adresi."

    clean_url = webhook_url.strip()
    filename = context.get("{filename}", "Dosya")
    filesize = context.get("{filesize}", "Bilinmiyor")
    category = context.get("{category}", "Others")
    filepath = context.get("{filepath}", "") if include_filepath else ""
    url = context.get("{url}", "")

    # Embed fields (omitting local filepath if include_filepath is False)
    fields = [
        {"name": "📁 Dosya Adı", "value": filename, "inline": True},
        {"name": "📂 Kategori", "value": category, "inline": True},
        {"name": "💾 Boyut", "value": filesize, "inline": True},
    ]
    if include_filepath and filepath:
        fields.append({"name": "📍 Kayıt Konumu", "value": filepath, "inline": False})
    fields.append({"name": "🔗 Bağlantı", "value": url[:200] if url else "--", "inline": False})

    # Payload compatible with Discord embeds & generic JSON webhooks
    payload = {
        "content": f"⚡ **RipSync:** İndirme tamamlandı! `{filename}` ({filesize})",
        "embeds": [
            {
                "title": "✅ İndirme Başarıyla Tamamlandı",
                "color": 0x3d59a1,
                "fields": fields,
                "footer": {"text": "RipSync Modern Download Manager"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ],
        "event": "download_completed",
        "filename": filename,
        "filesize": filesize,
        "category": category,
        "url": url
    }
    if include_filepath and filepath:
        payload["filepath"] = filepath

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(clean_url, json=payload)
            if 200 <= resp.status_code < 300:
                return True, f"HTTP {resp.status_code} Başarılı"
            return False, f"Sunucu yanıt kodu: HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)

def send_webhook_notification_async(webhook_url: str, context: Dict[str, str], include_filepath: bool = False):
    """Sends webhook in background thread without blocking the caller."""
    def _runner():
        send_webhook_notification(webhook_url, context, include_filepath=include_filepath)
    threading.Thread(target=_runner, daemon=True).start()

def execute_post_download(rec: Dict[str, Any], settings: Dict[str, Any]):
    """
    Main entry point invoked when a download successfully completes.
    Executes configured command and/or triggers webhook.
    """
    context = build_template_context(rec)

    # 1. Custom Command
    if settings.get("command_enabled") and settings.get("command"):
        run_post_download_command(settings["command"], context)

    # 2. Webhook
    if settings.get("webhook_enabled") and settings.get("webhook_url"):
        include_filepath = bool(settings.get("webhook_include_filepath", False))
        send_webhook_notification_async(settings["webhook_url"], context, include_filepath=include_filepath)
