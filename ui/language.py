"""Basit dil katmanı: teknik terimleri Basit modda sade ifadelerle değiştirir.

Hiçbir çekirdek metni etkilemez; yalnızca etiket metni seçerken Basit mod
hesaba katılır. Gelişmiş modda teknik ifadeler aynen korunur.
"""
from ui import styles as _styles


def is_simple_language() -> bool:
    db = getattr(_styles, "_APP_DB", None)
    if db is None:
        return False
    try:
        return getattr(db, "get_ui_mode", lambda: "advanced")() == "simple"
    except Exception:
        return False


def label_pair(simple: str, advanced: str) -> str:
    """Basit/Gelişmiş moda göre uygun metni döndürür."""
    return simple if is_simple_language() else advanced


# Sık karşılaşılan terim çiftleri (advanced, simple)
TERMS = {
    "connections": label_pair("aynı anda inen parça", "parça / bağlantı sayısı"),
    "range_support": label_pair("kaldığı yerden devam", "Range desteği"),
    "concurrent": label_pair("aynı anda inen dosya", "eşzamanlı indirme"),
    "segments": label_pair("parça", "segment"),
    "proxy": label_pair("ara sunucu", "proxy"),
    "webhook": label_pair("bildirim web adresi", "webhook"),
    "user_agent": label_pair("tarayıcı kimliği", "user-agent"),
}
