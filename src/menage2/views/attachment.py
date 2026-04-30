import datetime
import io
import logging
import uuid
from pathlib import Path

from PIL import Image
from pyramid.httpexceptions import HTTPNotFound
from pyramid.renderers import render
from pyramid.view import view_config
from sqlalchemy import select

from menage2.models.todo import Todo, TodoAttachment
from menage2.principals import get_user_team_memberships, todo_matches_filter

log = logging.getLogger(__name__)

_FORMAT_TO_MIMETYPE = {
    "JPEG": ("image/jpeg", ".jpg"),
    "MPO": ("image/jpeg", ".jpg"),  # iPhone Live Photo / depth JPEG variant
    "PNG": ("image/png", ".png"),
    "GIF": ("image/gif", ".gif"),
    "WEBP": ("image/webp", ".webp"),
    "BMP": ("image/bmp", ".bmp"),
    "TIFF": ("image/tiff", ".tiff"),
}


def _get_attachments_dir(request):
    d = request.registry.settings.get("menage.attachments_dir", "").strip()
    if not d:
        raise ValueError("menage.attachments_dir not configured")
    path = Path(d)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_authorized_todo(request, todo_id):
    user = request.identity
    if user is None:
        raise HTTPNotFound()
    todo = request.dbsession.get(Todo, todo_id)
    if todo is None:
        raise HTTPNotFound()
    memberships = get_user_team_memberships(request.dbsession, user)
    if not todo_matches_filter(todo, user, memberships, "all"):
        raise HTTPNotFound()
    return todo


def _ext_for(att):
    suffix = Path(att.original_filename).suffix.lower()
    return suffix or ".bin"


def _render_todo_item(request, todo):
    return render(
        "menage2:templates/_todo_item.pt",
        {"todo": todo, "today": datetime.date.today()},
        request=request,
    )


@view_config(route_name="todo_attachment_upload", request_method="POST")
def upload_attachment(request):
    todo_id = int(request.matchdict["id"])
    todo = _get_authorized_todo(request, todo_id)
    attachments_dir = _get_attachments_dir(request)

    good_count = 0
    bad_reasons: list[str] = []

    log.warning(
        "attachment upload: POST keys=%r content_type=%r",
        list(request.POST.keys()),
        request.content_type,
    )

    for _key, value in request.POST.items():
        if not hasattr(value, "file"):
            continue
        value.file.seek(0)
        raw = value.file.read()
        original_filename = Path(value.filename or "upload").name

        if not raw:
            log.warning("attachment upload: empty file for %r", original_filename)
            bad_reasons.append(f"“{original_filename}” is empty")
            continue

        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
        except Exception as exc:
            log.warning(
                "attachment upload: Pillow rejected %r: %s", original_filename, exc
            )
            bad_reasons.append(f"“{original_filename}” is not a valid image")
            continue

        fmt = img.format
        if fmt not in _FORMAT_TO_MIMETYPE:
            log.warning(
                "attachment upload: unsupported format %r for %r",
                fmt,
                original_filename,
            )
            bad_reasons.append(f"“{original_filename}”: unsupported format {fmt}")
            continue

        good_count += 1
        mimetype, ext = _FORMAT_TO_MIMETYPE[fmt]
        uuid_str = str(uuid.uuid4())

        full_path = attachments_dir / (uuid_str + ext)
        thumb_path = attachments_dir / (uuid_str + "_thumb" + ext)

        img.save(full_path)

        thumb = img.copy()
        thumb.thumbnail((200, 200))
        thumb.save(thumb_path)

        att = TodoAttachment(
            todo_id=todo.id,
            uuid=uuid_str,
            original_filename=original_filename,
            mimetype=mimetype,
            created_at=datetime.datetime.now(datetime.timezone.utc),
        )
        request.dbsession.add(att)

    if good_count == 0 and bad_reasons:
        request.response.status_int = 400
        request.response.text = "Upload failed: " + "; ".join(bad_reasons)
        return request.response

    request.dbsession.flush()
    request.dbsession.expire(todo)

    html = _render_todo_item(request, todo)
    request.response.content_type = "text/html"
    request.response.text = html
    request.response.headers["HX-Reswap"] = "outerHTML"
    return request.response


@view_config(route_name="todo_attachment_thumbnail", request_method="GET")
def serve_thumbnail(request):
    todo_id = int(request.matchdict["todo_id"])
    uuid_str = request.matchdict["uuid"]
    todo = _get_authorized_todo(request, todo_id)

    att = request.dbsession.execute(
        select(TodoAttachment).where(
            TodoAttachment.todo_id == todo.id,
            TodoAttachment.uuid == uuid_str,
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPNotFound()

    attachments_dir = _get_attachments_dir(request)
    ext = _ext_for(att)
    thumb_path = attachments_dir / (uuid_str + "_thumb" + ext)
    if not thumb_path.exists():
        raise HTTPNotFound()

    request.response.content_type = att.mimetype
    request.response.body = thumb_path.read_bytes()
    request.response.headers["Cache-Control"] = "private, max-age=3600"
    return request.response


@view_config(route_name="todo_attachment_full", request_method="GET")
def serve_full(request):
    todo_id = int(request.matchdict["todo_id"])
    uuid_str = request.matchdict["uuid"]
    todo = _get_authorized_todo(request, todo_id)

    att = request.dbsession.execute(
        select(TodoAttachment).where(
            TodoAttachment.todo_id == todo.id,
            TodoAttachment.uuid == uuid_str,
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPNotFound()

    attachments_dir = _get_attachments_dir(request)
    ext = _ext_for(att)
    full_path = attachments_dir / (uuid_str + ext)
    if not full_path.exists():
        raise HTTPNotFound()

    request.response.content_type = att.mimetype
    request.response.body = full_path.read_bytes()
    request.response.headers["Cache-Control"] = "private, max-age=3600"
    request.response.headers["Content-Disposition"] = (
        f'inline; filename="{att.original_filename}"'
    )
    return request.response


@view_config(route_name="todo_attachment_delete", request_method="POST")
def delete_attachment(request):
    todo_id = int(request.matchdict["todo_id"])
    uuid_str = request.matchdict["uuid"]
    todo = _get_authorized_todo(request, todo_id)

    att = request.dbsession.execute(
        select(TodoAttachment).where(
            TodoAttachment.todo_id == todo.id,
            TodoAttachment.uuid == uuid_str,
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPNotFound()

    attachments_dir = _get_attachments_dir(request)
    ext = _ext_for(att)
    for suffix in ("", "_thumb"):
        path = attachments_dir / (uuid_str + suffix + ext)
        if path.exists():
            path.unlink()

    request.dbsession.delete(att)
    request.dbsession.flush()
    request.dbsession.expire(todo)

    html = _render_todo_item(request, todo)
    request.response.content_type = "text/html"
    request.response.text = html
    request.response.headers["HX-Reswap"] = "outerHTML"
    return request.response
