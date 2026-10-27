"""Sanitasi path untuk mencegah directory traversal."""
from pathlib import Path, PurePosixPath

MAX_DEPTH = 20
MAX_SEGMENT = 255


class PathError(ValueError):
    pass


def normalize_rel_path(raw: str) -> str:
    """Validasi & normalisasi path relatif ke bentuk posix ('a/b/c.txt')."""
    if not isinstance(raw, str) or not raw.strip():
        raise PathError("Path tidak boleh kosong")
    if "\x00" in raw:
        raise PathError("Path mengandung karakter terlarang")
    if "\\" in raw:
        raise PathError("Gunakan '/' sebagai pemisah path")
    pure = PurePosixPath(raw.strip())
    if pure.is_absolute():
        raise PathError("Path absolut tidak diizinkan")
    parts = [p for p in pure.parts if p not in ("", ".")]
    if not parts:
        raise PathError("Path tidak valid")
    if ".." in parts:
        raise PathError("Path tidak boleh mengandung '..'")
    if len(parts) > MAX_DEPTH or any(len(p) > MAX_SEGMENT for p in parts):
        raise PathError("Path terlalu dalam atau terlalu panjang")
    return "/".join(parts)


def safe_join(base: Path, rel: str) -> Path:
    """Gabungkan base + rel, pastikan hasil resolve() tetap di dalam base (symlink-safe)."""
    rel = normalize_rel_path(rel)
    base_resolved = base.resolve()
    target = (base_resolved / rel).resolve()
    if target == base_resolved or base_resolved not in target.parents:
        raise PathError("Path keluar dari folder project")
    return target
