"""ORM models for SnapFit."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import String, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Tool(Base):
    """A power tool with key body dimensions for STL generation."""

    __tablename__ = "tools"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    brand: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Key dimensions in millimetres
    body_width_mm: Mapped[float] = mapped_column(Float, nullable=False)
    body_depth_mm: Mapped[float] = mapped_column(Float, nullable=False)
    body_height_mm: Mapped[float] = mapped_column(Float, nullable=False)
    handle_diameter_mm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        """Serialise to plain dict for JSON responses."""
        return {
            "id": self.id,
            "brand": self.brand,
            "model_name": self.model_name,
            "tool_type": self.tool_type,
            "body_width_mm": self.body_width_mm,
            "body_depth_mm": self.body_depth_mm,
            "body_height_mm": self.body_height_mm,
            "handle_diameter_mm": self.handle_diameter_mm,
            "weight_kg": self.weight_kg,
        }


class ToolSubmission(Base):
    """User-submitted tool requests (stub — no processing yet)."""

    __tablename__ = "tool_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    brand: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
