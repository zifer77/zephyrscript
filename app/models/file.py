from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import utcnow


class FileNode(Base):
    """Metadata file/folder. Isi file disimpan di disk (workspace/<project_id>/<path>)."""

    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("project_id", "path", name="uq_project_path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(1024))  # relatif, posix, mis. "src/app.js"
    name: Mapped[str] = mapped_column(String(255))
    is_folder: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project = relationship("Project", back_populates="files")
