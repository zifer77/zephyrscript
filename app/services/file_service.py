import os
import shutil
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.file import FileNode
from app.models.project import Project
from app.models.user import utcnow
from app.schemas.file import FileTreeNode
from app.utils.path_sanitizer import PathError, safe_join

IGNORED_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".cache"}

STARTER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{name}</title>
</head>
<body>
  <h1>Hello from ZephyrScript</h1>
  <p>Edit <code>index.html</code> dan lihat hasilnya di preview.</p>
</body>
</html>
"""


# ---------- project folder ----------
def project_dir(project_id: int) -> Path:
    path = settings.workspace_root / str(project_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def init_project_files(db: Session, project: Project) -> None:
    root = project_dir(project.id)
    index = root / "index.html"
    if not index.exists():
        index.write_text(STARTER_HTML.format(name=project.name), encoding="utf-8")
    sync_project(db, project)


def delete_project_dir(project_id: int) -> None:
    shutil.rmtree(settings.workspace_root / str(project_id), ignore_errors=True)


# ---------- helpers ----------
def _safe(project_id: int, rel: str) -> Path:
    try:
        return safe_join(project_dir(project_id), rel)
    except PathError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


def sync_project(db: Session, project: Project) -> None:
    """Samakan tabel `files` dengan isi disk (file bisa dibuat via terminal/npm/git)."""
    root = project_dir(project.id)
    found: dict[str, bool] = {}  # rel_path -> is_folder
    limit = settings.max_files_per_project

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not (base / d).is_symlink()]
        rel_base = base.relative_to(root).as_posix()
        prefix = "" if rel_base == "." else rel_base + "/"
        for d in dirnames:
            found[prefix + d] = True
        for f in filenames:
            if not (base / f).is_symlink():
                found[prefix + f] = False
        if len(found) >= limit:
            break

    existing = {r.path: r for r in db.query(FileNode).filter(FileNode.project_id == project.id)}
    changed = False
    for path, rec in existing.items():
        if path not in found or rec.is_folder != found[path]:
            db.delete(rec)
            changed = True
    if changed:
        db.flush()
    for path, is_folder in found.items():
        rec = existing.get(path)
        if rec is None or rec.is_folder != is_folder:
            db.add(FileNode(project_id=project.id, path=path, name=path.rsplit("/", 1)[-1], is_folder=is_folder))
            changed = True
    if changed:
        db.commit()


def build_tree(records: list[FileNode]) -> list[FileTreeNode]:
    nodes = {r.path: FileTreeNode(id=r.id, name=r.name, path=r.path, is_folder=r.is_folder, children=[]) for r in records}
    roots: list[FileTreeNode] = []
    for path in sorted(nodes):
        node = nodes[path]
        parent_path = path.rsplit("/", 1)[0] if "/" in path else None
        parent = nodes.get(parent_path) if parent_path else None
        (parent.children if parent else roots).append(node)

    def order(items: list[FileTreeNode]) -> None:
        items.sort(key=lambda n: (not n.is_folder, n.name.lower()))
        for n in items:
            order(n.children)

    order(roots)
    return roots


def get_tree(db: Session, project: Project) -> list[FileTreeNode]:
    sync_project(db, project)
    records = db.query(FileNode).filter(FileNode.project_id == project.id).all()
    return build_tree(records)


# ---------- CRUD ----------
def create_node(db: Session, project: Project, rel_path: str, is_folder: bool, content: str) -> FileNode:
    target = _safe(project.id, rel_path)
    if target.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "File atau folder sudah ada")
    if is_folder:
        target.mkdir(parents=True, exist_ok=False)
    else:
        _check_size(content)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    sync_project(db, project)
    root = project_dir(project.id).resolve()
    rel = target.relative_to(root).as_posix()
    node = db.query(FileNode).filter(FileNode.project_id == project.id, FileNode.path == rel).first()
    if node is None:  # mis. dibuat di dalam folder yang di-ignore (node_modules, dst.)
        node = FileNode(project_id=project.id, path=rel, name=target.name, is_folder=is_folder)
        db.add(node)
        db.commit()
        db.refresh(node)
    return node


def _check_size(content: str) -> None:
    if len(content.encode("utf-8")) > settings.max_file_size_kb * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"Ukuran file maksimal {settings.max_file_size_kb} KB")


def read_content(db: Session, node: FileNode) -> str:
    if node.is_folder:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ini adalah folder")
    path = _safe(node.project_id, node.path)
    if not path.is_file():
        db.delete(node)
        db.commit()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File tidak ditemukan di disk")
    if path.stat().st_size > settings.max_file_size_kb * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File terlalu besar untuk dibuka di editor")
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File biner tidak bisa dibuka sebagai teks")


def write_content(db: Session, node: FileNode, content: str) -> FileNode:
    if node.is_folder:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tidak bisa menulis ke folder")
    _check_size(content)
    path = _safe(node.project_id, node.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    db.add(node)
    node.updated_at = utcnow()
    db.commit()
    db.refresh(node)
    return node


def delete_node(db: Session, project: Project, node: FileNode) -> None:
    path = _safe(node.project_id, node.path)
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        path.unlink(missing_ok=True)
    sync_project(db, project)
    # pastikan record terhapus walau berada di folder yang di-ignore
    leftover = db.get(FileNode, node.id)
    if leftover is not None:
        db.delete(leftover)
        db.commit()
