import pytest
from core.database import Database
from core.queue_manager import QueueManager
from ui.add_download_dialog import AddDownloadDialog


@pytest.fixture
def mem_db(tmp_path):
    db_file = str(tmp_path / "test_queues.db")
    return Database(db_file)


@pytest.fixture
def queue_mgr(mem_db):
    return QueueManager(db=mem_db, max_concurrent=2)


def test_default_queue_exists(mem_db):
    queues = mem_db.get_all_queues()
    assert len(queues) >= 1
    default_q = next((q for q in queues if q["id"] == "default"), None)
    assert default_q is not None
    assert default_q["name"] == "Ana Kuyruk"
    assert default_q["is_default"] == 1


def test_add_update_delete_queue(mem_db):
    # Add new queue
    q_id = mem_db.add_queue(name="Film ve Dizi", max_concurrent=3, target_dir="D:\\Movies")
    assert q_id != "default"

    # Query queues
    queues = mem_db.get_all_queues()
    assert any(q["id"] == q_id and q["name"] == "Film ve Dizi" for q in queues)

    # Update queue
    mem_db.update_queue(q_id, name="Sinema Kulübü", max_concurrent=4)
    q_info = mem_db.get_queue(q_id)
    assert q_info["name"] == "Sinema Kulübü"
    assert q_info["max_concurrent"] == 4

    # Assign download to this queue
    did = mem_db.add_download(
        url="https://example.com/film.mkv",
        filename="film.mkv",
        save_path="D:\\Movies\\film.mkv",
        queue_id=q_id
    )
    dls = mem_db.get_all_downloads(queue_id=q_id)
    assert len(dls) == 1
    assert dls[0]["id"] == did

    # Cannot delete default queue
    assert mem_db.delete_queue("default") is False

    # Delete custom queue: tasks must be migrated to 'default'
    assert mem_db.delete_queue(q_id) is True
    rec = mem_db.get_download(did)
    assert rec["queue_id"] == "default"


def test_move_download_to_queue(mem_db):
    q_id = mem_db.add_queue(name="İş Dosyaları")
    did = mem_db.add_download(
        url="https://example.com/report.pdf",
        filename="report.pdf",
        save_path="C:\\report.pdf",
        queue_id="default"
    )

    mem_db.move_download_to_queue(did, q_id)
    rec = mem_db.get_download(did)
    assert rec["queue_id"] == q_id

    # Filter downloads by queue
    assert len(mem_db.get_all_downloads(queue_id=q_id)) == 1
    assert len(mem_db.get_all_downloads(queue_id="default")) == 0


def test_queue_manager_queue_controls(queue_mgr, mem_db, tmp_path):
    q_id = mem_db.add_queue(name="Özel Kuyruk")
    save_dir = str(tmp_path)

    did1 = queue_mgr.add_download(
        url="https://example.com/file1.zip",
        save_dir=save_dir,
        filename="file1.zip",
        start_now=False,
        queue_id=q_id
    )
    did2 = queue_mgr.add_download(
        url="https://example.com/file2.zip",
        save_dir=save_dir,
        filename="file2.zip",
        start_now=False,
        queue_id="default"
    )

    # Pause both
    mem_db.update_download(did1, status="Paused")
    mem_db.update_download(did2, status="Paused")

    # Start only q_id queue
    queue_mgr.start_queue(queue_id=q_id)
    assert mem_db.get_download(did1)["status"] in ("Queued", "Probing", "Downloading")
    assert mem_db.get_download(did2)["status"] == "Paused"


def test_add_download_dialog_queue_combo(qapp, mem_db):
    mem_db.add_queue("Yazılım Projeleri")
    dlg = AddDownloadDialog(db=mem_db)

    # Queue selector should have options
    assert dlg.combo_queue.count() >= 2
    assert dlg.combo_queue.findText("🗂️ Yazılım Projeleri") >= 0
