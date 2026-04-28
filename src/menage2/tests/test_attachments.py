import datetime
import io
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from menage2.models.todo import Todo, TodoAttachment, TodoStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg_bytes(width=2, height=2):
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_todo(dbsession, admin_user, text="Test todo"):
    todo = Todo(
        text=text,
        tags=set(),
        assignees=set(),
        status=TodoStatus.todo,
        owner_id=admin_user.id,
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(todo)
    dbsession.flush()
    return todo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def attachments_dir(tmp_path, app):
    d = tmp_path / "attachments"
    d.mkdir()
    old = app.registry.settings.get("menage.attachments_dir")
    app.registry.settings["menage.attachments_dir"] = str(d)
    yield d
    if old is not None:
        app.registry.settings["menage.attachments_dir"] = old
    else:
        app.registry.settings.pop("menage.attachments_dir", None)


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


def test_upload_jpeg_creates_db_row_and_two_disk_files(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()

    res = authenticated_testapp.post(
        f"/todos/{todo.id}/attachments",
        upload_files=[("files[]", "photo.jpg", jpeg)],
        status=200,
    )

    att = dbsession.execute(
        select(TodoAttachment).where(TodoAttachment.todo_id == todo.id)
    ).scalar_one()
    assert att.original_filename == "photo.jpg"
    assert att.mimetype == "image/jpeg"

    files = list(attachments_dir.iterdir())
    assert len(files) == 2
    assert any(f.name.endswith("_thumb.jpg") for f in files)

    assert b"todo-attachment-icon" in res.body or b"bi-camera" in res.body


def test_upload_multiple_files_creates_multiple_rows(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()

    authenticated_testapp.post(
        f"/todos/{todo.id}/attachments",
        upload_files=[
            ("files[]", "a.jpg", jpeg),
            ("files[]", "b.jpg", jpeg),
        ],
        status=200,
    )

    atts = (
        dbsession.execute(
            select(TodoAttachment).where(TodoAttachment.todo_id == todo.id)
        )
        .scalars()
        .all()
    )
    assert len(atts) == 2
    assert len(list(attachments_dir.iterdir())) == 4  # 2 full + 2 thumb


def test_upload_invalid_file_rejected(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)

    authenticated_testapp.post(
        f"/todos/{todo.id}/attachments",
        upload_files=[("files[]", "document.txt", b"this is not an image")],
        status=400,
    )

    count = dbsession.execute(
        select(TodoAttachment).where(TodoAttachment.todo_id == todo.id)
    ).all()
    assert len(count) == 0
    assert list(attachments_dir.iterdir()) == []


def test_upload_validates_with_pillow_ignores_content_type(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    """Pillow opens the bytes; browser Content-Type is irrelevant."""
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()

    authenticated_testapp.post(
        f"/todos/{todo.id}/attachments",
        upload_files=[("files[]", "sneaky.jpg", jpeg)],
        status=200,
    )

    att = dbsession.execute(
        select(TodoAttachment).where(TodoAttachment.todo_id == todo.id)
    ).scalar_one()
    assert att.mimetype == "image/jpeg"


# ---------------------------------------------------------------------------
# Serve tests
# ---------------------------------------------------------------------------


def test_thumbnail_endpoint_requires_auth(
    testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    att = TodoAttachment(
        todo_id=todo.id,
        uuid="test-uuid-thumbnail",
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    res = testapp.get(
        f"/todos/{todo.id}/attachment/test-uuid-thumbnail/thumbnail",
        expect_errors=True,
    )
    assert res.status_int in (302, 303, 404)


def test_thumbnail_returns_image_bytes(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()
    uuid_str = "test-uuid-serve-thumb"
    (attachments_dir / (uuid_str + "_thumb.jpg")).write_bytes(jpeg)

    att = TodoAttachment(
        todo_id=todo.id,
        uuid=uuid_str,
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    res = authenticated_testapp.get(
        f"/todos/{todo.id}/attachment/{uuid_str}/thumbnail",
        status=200,
    )
    assert "image/jpeg" in res.headers.get("Content-Type", "")
    assert res.body == jpeg


def test_full_image_endpoint_returns_bytes_and_disposition(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()
    uuid_str = "test-uuid-serve-full"
    (attachments_dir / (uuid_str + ".jpg")).write_bytes(jpeg)

    att = TodoAttachment(
        todo_id=todo.id,
        uuid=uuid_str,
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    res = authenticated_testapp.get(
        f"/todos/{todo.id}/attachment/{uuid_str}/full",
        status=200,
    )
    assert "image/jpeg" in res.headers.get("Content-Type", "")
    assert res.body == jpeg
    assert "Content-Disposition" in res.headers
    assert "photo.jpg" in res.headers["Content-Disposition"]


def test_thumbnail_wrong_todo_id_returns_404(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo_a = _make_todo(dbsession, admin_user, text="Todo A")
    todo_b = _make_todo(dbsession, admin_user, text="Todo B")
    jpeg = _make_jpeg_bytes()
    uuid_str = "test-uuid-wrong-todo"
    (attachments_dir / (uuid_str + "_thumb.jpg")).write_bytes(jpeg)

    att = TodoAttachment(
        todo_id=todo_a.id,
        uuid=uuid_str,
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    authenticated_testapp.get(
        f"/todos/{todo_b.id}/attachment/{uuid_str}/thumbnail",
        status=404,
    )


def test_other_user_cannot_access_attachment(
    testapp, regular_user, dbsession, admin_user, attachments_dir
):
    """User B cannot access an attachment on user A's private todo."""
    todo = _make_todo(dbsession, admin_user, text="Admin private todo")
    jpeg = _make_jpeg_bytes()
    uuid_str = "test-uuid-cross-user"
    (attachments_dir / (uuid_str + "_thumb.jpg")).write_bytes(jpeg)

    att = TodoAttachment(
        todo_id=todo.id,
        uuid=uuid_str,
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    testapp.post(
        "/login", {"username": "user", "password": "user-password"}, status=303
    )

    res = testapp.get(
        f"/todos/{todo.id}/attachment/{uuid_str}/thumbnail",
        expect_errors=True,
    )
    assert res.status_int == 404


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------


def test_delete_removes_disk_files_and_db_row(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()
    uuid_str = "test-uuid-delete"
    full_path = attachments_dir / (uuid_str + ".jpg")
    thumb_path = attachments_dir / (uuid_str + "_thumb.jpg")
    full_path.write_bytes(jpeg)
    thumb_path.write_bytes(jpeg)

    att = TodoAttachment(
        todo_id=todo.id,
        uuid=uuid_str,
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    authenticated_testapp.post(
        f"/todos/{todo.id}/attachment/{uuid_str}/delete",
        status=200,
    )

    result = dbsession.execute(
        select(TodoAttachment).where(TodoAttachment.uuid == uuid_str)
    ).scalar_one_or_none()
    assert result is None
    assert not full_path.exists()
    assert not thumb_path.exists()


# ---------------------------------------------------------------------------
# Edit-todo removal
# ---------------------------------------------------------------------------


def test_edit_todo_removes_attachment_via_remove_attachments_param(
    authenticated_testapp, dbsession, admin_user, attachments_dir
):
    todo = _make_todo(dbsession, admin_user)
    jpeg = _make_jpeg_bytes()
    uuid_str = "test-uuid-edit-remove"
    full_path = attachments_dir / (uuid_str + ".jpg")
    thumb_path = attachments_dir / (uuid_str + "_thumb.jpg")
    full_path.write_bytes(jpeg)
    thumb_path.write_bytes(jpeg)

    att = TodoAttachment(
        todo_id=todo.id,
        uuid=uuid_str,
        original_filename="photo.jpg",
        mimetype="image/jpeg",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    dbsession.add(att)
    dbsession.flush()

    authenticated_testapp.post(
        f"/todos/{todo.id}/edit",
        {
            "text": "Updated text",
            "next": "/todos",
            "remove_attachments": uuid_str,
        },
        status=303,
    )

    result = dbsession.execute(
        select(TodoAttachment).where(TodoAttachment.uuid == uuid_str)
    ).scalar_one_or_none()
    assert result is None
    assert not full_path.exists()
    assert not thumb_path.exists()
