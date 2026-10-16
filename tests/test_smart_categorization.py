import os
import tempfile
from core.database import (
    CATEGORY_MAP,
    CATEGORY_FOLDER_NAMES,
    detect_category,
    get_category_folder,
    get_categorized_save_dir,
    Database
)
import core.categories as direct_categories
from core.queue_manager import QueueManager

def test_smart_categorization():
    print("=== Testing Auto Smart Categorization Rules ===")
    assert direct_categories.detect_category("test.mp4") == "Video"
    assert direct_categories.get_category_folder("Video") == get_category_folder("Video")

    # Test cases requested by the user:
    # .mp4, .mkv, .avi ➔ İndirilenler / Videolar
    # .mp3, .wav, .flac ➔ İndirilenler / Müzik
    # .zip, .rar, .7z ➔ İndirilenler / Arşivler
    # .exe, .msi, .iso ➔ İndirilenler / Programlar
    # .pdf, .docx ➔ İndirilenler / Belgeler

    test_extensions = [
        # Video
        ("movie.mp4", "Video", "Videolar"),
        ("clip.mkv", "Video", "Videolar"),
        ("video.avi", "Video", "Videolar"),
        # Music
        ("song.mp3", "Music", "Müzik"),
        ("audio.wav", "Music", "Müzik"),
        ("lossless.flac", "Music", "Müzik"),
        # Compressed / Archives
        ("archive.zip", "Compressed", "Arşivler"),
        ("pack.rar", "Compressed", "Arşivler"),
        ("backup.7z", "Compressed", "Arşivler"),
        # Programs
        ("setup.exe", "Programs", "Programlar"),
        ("installer.msi", "Programs", "Programlar"),
        ("os_image.iso", "Programs", "Programlar"),
        # Documents
        ("document.pdf", "Documents", "Belgeler"),
        ("report.docx", "Documents", "Belgeler"),
        # Others
        ("unknown.xyz", "Others", "")
    ]

    base_dir = os.path.join(tempfile.gettempdir(), "TestDownloads")
    os.makedirs(base_dir, exist_ok=True)

    for filename, expected_cat, expected_subfolder in test_extensions:
        cat = detect_category(filename)
        assert cat == expected_cat, f"Category mismatch for {filename}: got {cat}, expected {expected_cat}"

        target_dir = get_categorized_save_dir(filename, base_dir=base_dir)
        if expected_subfolder:
            expected_target_dir = os.path.join(base_dir, expected_subfolder)
        else:
            expected_target_dir = base_dir

        assert os.path.abspath(target_dir) == os.path.abspath(expected_target_dir), (
            f"Directory mismatch for {filename}: got {target_dir}, expected {expected_target_dir}"
        )
        assert os.path.exists(target_dir), f"Directory was not created: {target_dir}"
        print(f"[OK] {filename:<16} -> {cat:<12} -> {os.path.basename(target_dir) or 'Root'}")

    print("\n=== Testing QueueManager Auto Categorization Routing ===")
    import uuid
    test_db_path = os.path.join(tempfile.gettempdir(), f"test_cat_{uuid.uuid4().hex[:8]}.db")

    db = Database(test_db_path)
    db.set_setting("auto_categorize", True)
    db.set_setting("default_dir", base_dir)

    qm = QueueManager(db, max_concurrent=2)

    # Add downloads without explicit subfolder
    dl_video_id = qm.add_download(
        url="http://example.com/test.mp4",
        save_dir=base_dir,
        filename="test.mp4",
        start_now=False
    )
    rec_video = db.get_download(dl_video_id)
    assert rec_video["category"] == "Video"
    assert os.path.abspath(os.path.dirname(rec_video["save_path"])) == os.path.abspath(os.path.join(base_dir, "Videolar"))
    print("[OK] QueueManager routed test.mp4 to Videolar")

    dl_prog_id = qm.add_download(
        url="http://example.com/installer.iso",
        save_dir=base_dir,
        filename="installer.iso",
        start_now=False
    )
    rec_prog = db.get_download(dl_prog_id)
    assert rec_prog["category"] == "Programs"
    assert os.path.abspath(os.path.dirname(rec_prog["save_path"])) == os.path.abspath(os.path.join(base_dir, "Programlar"))
    print("[OK] QueueManager routed installer.iso to Programlar")

    dl_doc_id = qm.add_download(
        url="http://example.com/sheet.docx",
        save_dir=base_dir,
        filename="sheet.docx",
        start_now=False
    )
    rec_doc = db.get_download(dl_doc_id)
    assert rec_doc["category"] == "Documents"
    assert os.path.abspath(os.path.dirname(rec_doc["save_path"])) == os.path.abspath(os.path.join(base_dir, "Belgeler"))
    print("[OK] QueueManager routed sheet.docx to Belgeler")

    dl_zip_id = qm.add_download(
        url="http://example.com/files.7z",
        save_dir=base_dir,
        filename="files.7z",
        start_now=False
    )
    rec_zip = db.get_download(dl_zip_id)
    assert rec_zip["category"] == "Compressed"
    assert os.path.abspath(os.path.dirname(rec_zip["save_path"])) == os.path.abspath(os.path.join(base_dir, "Arşivler"))
    print("[OK] QueueManager routed files.7z to Arşivler")

    dl_audio_id = qm.add_download(
        url="http://example.com/track.flac",
        save_dir=base_dir,
        filename="track.flac",
        start_now=False
    )
    rec_audio = db.get_download(dl_audio_id)
    assert rec_audio["category"] == "Music"
    assert os.path.abspath(os.path.dirname(rec_audio["save_path"])) == os.path.abspath(os.path.join(base_dir, "Müzik"))
    print("[OK] QueueManager routed track.flac to Müzik")

    print("\n>>> ALL CATEGORIZATION TESTS PASSED! <<<")

if __name__ == "__main__":
    test_smart_categorization()
