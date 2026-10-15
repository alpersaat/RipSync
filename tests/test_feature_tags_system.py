import pytest
from core.database import Database

def test_database_tags_system():
    db = Database(":memory:")

    # Add downloads with tags
    id1 = db.add_download(
        url="https://example.com/doc1.pdf",
        filename="doc1.pdf",
        save_path="C:\\Downloads\\doc1.pdf",
        tags="İş, Acil"
    )

    id2 = db.add_download(
        url="https://example.com/course.mp4",
        filename="course.mp4",
        save_path="C:\\Downloads\\course.mp4",
        tags="Ders, Video"
    )

    id3 = db.add_download(
        url="https://example.com/project.zip",
        filename="project.zip",
        save_path="C:\\Downloads\\project.zip",
        tags="İş, Proje"
    )

    # Verify tags stored
    rec1 = db.get_download(id1)
    assert rec1["tags"] == "İş, Acil"

    # Verify get_all_tags returns unique sorted tags
    all_tags = db.get_all_tags()
    assert all_tags == ["Acil", "Ders", "Proje", "Video", "İş"]

    # Filter downloads by tag
    is_dls = db.get_all_downloads(tag="İş")
    assert len(is_dls) == 2
    is_ids = [d["id"] for d in is_dls]
    assert id1 in is_ids and id3 in is_ids

    ders_dls = db.get_all_downloads(tag="Ders")
    assert len(ders_dls) == 1
    assert ders_dls[0]["id"] == id2

    # Update tag
    db.update_download(id1, tags="Arşiv")
    rec1_up = db.get_download(id1)
    assert rec1_up["tags"] == "Arşiv"

    all_tags_up = db.get_all_tags()
    assert "Arşiv" in all_tags_up
    assert "Acil" not in all_tags_up

