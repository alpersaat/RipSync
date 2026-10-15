import os
import subprocess
import threading
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple
import httpx

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

def run_post_download_command(command_template: str, context: Dict[str, str]):
    """Executes a custom CLI command asynchronously in the background."""
    if not command_template or not command_template.strip():
        return

    cmd = substitute_variables(command_template, context)
    def _runner():
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(cmd, shell=True, creationflags=creationflags)
        except Exception as e:
            print(f"[PostDownload] Command failed to execute ({cmd}): {e}")

    threading.Thread(target=_runner, daemon=True).start()

def send_webhook_notification(webhook_url: str, context: Dict[str, str], timeout: float = 10.0) -> Tuple[bool, str]:
    """
    Sends an HTTP POST webhook notification (compatible with Discord, Slack, and generic webhooks).
    Returns (success, message).
    """
    if not webhook_url or not webhook_url.strip():
        return False, "Boş Webhook adresi."

    clean_url = webhook_url.strip()
    filename = context.get("{filename}", "Dosya")
    filesize = context.get("{filesize}", "Bilinmiyor")
    category = context.get("{category}", "Others")
    filepath = context.get("{filepath}", "")
    url = context.get("{url}", "")

    # Payload compatible with Discord embeds & generic JSON webhooks
    payload = {
        "content": f"⚡ **RipSync:** İndirme tamamlandı! `{filename}` ({filesize})",
        "embeds": [
            {
                "title": "✅ İndirme Başarıyla Tamamlandı",
                "color": 0x3d59a1,
                "fields": [
                    {"name": "📁 Dosya Adı", "value": filename, "inline": True},
                    {"name": "📂 Kategori", "value": category, "inline": True},
                    {"name": "💾 Boyut", "value": filesize, "inline": True},
                    {"name": "📍 Kayıt Konumu", "value": filepath or "--", "inline": False},
                    {"name": "🔗 Bağlantı", "value": url[:200] if url else "--", "inline": False}
                ],
                "footer": {"text": "RipSync Modern Download Manager"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ],
        "event": "download_completed",
        "filename": filename,
        "filepath": filepath,
        "filesize": filesize,
        "category": category,
        "url": url
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(clean_url, json=payload)
            if 200 <= resp.status_code < 300:
                return True, f"HTTP {resp.status_code} Başarılı"
            return False, f"Sunucu yanıt kodu: HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)

def send_webhook_notification_async(webhook_url: str, context: Dict[str, str]):
    """Sends webhook in background thread without blocking the caller."""
    def _runner():
        send_webhook_notification(webhook_url, context)
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
        send_webhook_notification_async(settings["webhook_url"], context)
