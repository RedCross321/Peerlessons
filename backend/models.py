import uuid
from datetime import datetime

from database import Base
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    username: Mapped[str | None] = mapped_column(
        String(50), unique=True, index=True, nullable=True
    )

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    hosted_rooms = relationship(
        "Room", back_populates="host", foreign_keys="Room.host_id"
    )
    participations = relationship("RoomParticipant", back_populates="user")

    refresh_tokens = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    host_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    current_editor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), default="waiting")

    current_code: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    language: Mapped[str] = mapped_column(String(50), default="html")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    host = relationship("User", back_populates="hosted_rooms", foreign_keys=[host_id])
    current_editor = relationship("User", foreign_keys=[current_editor_id])
    participants = relationship(
        "RoomParticipant", back_populates="room", cascade="all, delete-orphan"
    )
    snapshots = relationship(
        "CodeSnapshot", back_populates="room", cascade="all, delete-orphan"
    )
    edit_requests = relationship(
        "EditRequest", back_populates="room", cascade="all, delete-orphan"
    )


class RoomParticipant(Base):
    __tablename__ = "room_participants"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), default="viewer")
    hand_raised: Mapped[bool] = mapped_column(Boolean, default=False)

    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    room = relationship("Room", back_populates="participants")
    user = relationship("User", back_populates="participations")


class CodeSnapshot(Base):
    __tablename__ = "code_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    snapshot: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    room = relationship("Room", back_populates="snapshots")


class EditRequest(Base):
    __tablename__ = "edit_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    room = relationship("Room", back_populates="edit_requests")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    jti: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="refresh_tokens")
