import datetime
import uuid
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "User"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="User_pkey"),
        Index("User_email_key", "email", unique=True),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    createdAt: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(precision=3), server_default=text("CURRENT_TIMESTAMP")
    )
    updatedAt: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=3))
    name: Mapped[Optional[str]] = mapped_column(Text)
    role = Column(String, default="user")
    email: Mapped[Optional[str]] = mapped_column(Text)
    emailVerified: Mapped[Optional[datetime.datetime]] = mapped_column(
        TIMESTAMP(precision=3)
    )
    image: Mapped[Optional[str]] = mapped_column(Text)

    Account: Mapped[List["Account"]] = relationship("Account", back_populates="User_")
    Authenticator: Mapped[List["Authenticator"]] = relationship(
        "Authenticator", back_populates="User_"
    )
    Bookmark: Mapped[List["Bookmark"]] = relationship(
        "Bookmark", back_populates="User_"
    )
    Notification: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="User_"
    )
    ReadPost: Mapped[List["ReadPost"]] = relationship(
        "ReadPost", back_populates="User_"
    )


class VerificationToken(Base):
    __tablename__ = "VerificationToken"
    __table_args__ = (
        PrimaryKeyConstraint("identifier", "token", name="VerificationToken_pkey"),
    )

    identifier: Mapped[str] = mapped_column(Text, primary_key=True)
    token: Mapped[str] = mapped_column(Text, primary_key=True)
    expires: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=3))


class PrismaMigrations(Base):
    __tablename__ = "_prisma_migrations"
    __table_args__ = (PrimaryKeyConstraint("id", name="_prisma_migrations_pkey"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64))
    migration_name: Mapped[str] = mapped_column(String(255))
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), server_default=text("now()")
    )
    applied_steps_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    finished_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    logs: Mapped[Optional[str]] = mapped_column(Text)
    rolled_back_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class Authors(Base):
    __tablename__ = "authors"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="authors_pkey"),
        Index("author_name", "name", unique=True),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)

    resources: Mapped[List["Resources"]] = relationship(
        "Resources", secondary="_authorsToresources", back_populates="authors"
    )


class Paths(Base):
    __tablename__ = "paths"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="paths_pkey"),
        Index("path_name", "name", unique=True),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)

    topics: Mapped[List["Topics"]] = relationship("Topics", back_populates="path")


class Resources(Base):
    __tablename__ = "resources"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="resources_pkey"),
        Index("url", "url", unique=True),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    accepted: Mapped[Optional[bool]] = mapped_column(Boolean)
    date: Mapped[Optional[datetime.datetime]] = mapped_column(TIMESTAMP(precision=3))
    time: Mapped[Optional[int]] = mapped_column(Integer)

    authors: Mapped[List["Authors"]] = relationship(
        "Authors", secondary="_authorsToresources", back_populates="resources"
    )
    tags: Mapped[List["Tags"]] = relationship(
        "Tags", secondary="_resourcesTotags", back_populates="resources"
    )
    Bookmark: Mapped[List["Bookmark"]] = relationship(
        "Bookmark", back_populates="resources"
    )
    ReadPost: Mapped[List["ReadPost"]] = relationship(
        "ReadPost", back_populates="resources"
    )


class Tags(Base):
    __tablename__ = "tags"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="tags_pkey"),
        Index("tag_name", "name", unique=True),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)

    resources: Mapped[List["Resources"]] = relationship(
        "Resources", secondary="_resourcesTotags", back_populates="tags"
    )
    topics: Mapped[List["Topics"]] = relationship("Topics", back_populates="tag")
    sections: Mapped[List["Sections"]] = relationship("Sections", back_populates="tag")


class Account(Base):
    __tablename__ = "Account"
    __table_args__ = (
        ForeignKeyConstraint(
            ["userId"],
            ["User.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="Account_userId_fkey",
        ),
        PrimaryKeyConstraint("provider", "providerAccountId", name="Account_pkey"),
    )

    userId: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    providerAccountId: Mapped[str] = mapped_column(Text, primary_key=True)
    createdAt: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(precision=3), server_default=text("CURRENT_TIMESTAMP")
    )
    updatedAt: Mapped[datetime.datetime] = mapped_column(TIMESTAMP(precision=3))
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)
    access_token: Mapped[Optional[str]] = mapped_column(Text)
    expires_at: Mapped[Optional[int]] = mapped_column(Integer)
    token_type: Mapped[Optional[str]] = mapped_column(Text)
    scope: Mapped[Optional[str]] = mapped_column(Text)
    id_token: Mapped[Optional[str]] = mapped_column(Text)
    session_state: Mapped[Optional[str]] = mapped_column(Text)

    User_: Mapped["User"] = relationship("User", back_populates="Account")


class Authenticator(Base):
    __tablename__ = "Authenticator"
    __table_args__ = (
        ForeignKeyConstraint(
            ["userId"],
            ["User.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="Authenticator_userId_fkey",
        ),
        PrimaryKeyConstraint("userId", "credentialID", name="Authenticator_pkey"),
        Index("Authenticator_credentialID_key", "credentialID", unique=True),
    )

    credentialID: Mapped[str] = mapped_column(Text, primary_key=True)
    userId: Mapped[str] = mapped_column(Text, primary_key=True)
    providerAccountId: Mapped[str] = mapped_column(Text)
    credentialPublicKey: Mapped[str] = mapped_column(Text)
    counter: Mapped[int] = mapped_column(Integer)
    credentialDeviceType: Mapped[str] = mapped_column(Text)
    credentialBackedUp: Mapped[bool] = mapped_column(Boolean)
    transports: Mapped[Optional[str]] = mapped_column(Text)

    User_: Mapped["User"] = relationship("User", back_populates="Authenticator")


class Bookmark(Base):
    __tablename__ = "Bookmark"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resourceId"],
            ["resources.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="Bookmark_resourceId_fkey",
        ),
        ForeignKeyConstraint(
            ["userId"],
            ["User.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="Bookmark_userId_fkey",
        ),
        PrimaryKeyConstraint("id", name="Bookmark_pkey"),
        Index("Bookmark_userId_resourceId_key", "userId", "resourceId", unique=True),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    userId: Mapped[str] = mapped_column(Text)
    resourceId = Column(UUID(as_uuid=False))
    createdAt: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(precision=3), server_default=text("CURRENT_TIMESTAMP")
    )

    resources: Mapped["Resources"] = relationship(
        "Resources", back_populates="Bookmark"
    )
    User_: Mapped["User"] = relationship("User", back_populates="Bookmark")


class Notification(Base):
    __tablename__ = "Notification"
    __table_args__ = (
        ForeignKeyConstraint(
            ["userId"],
            ["User.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="Notification_userId_fkey",
        ),
        PrimaryKeyConstraint("id", name="Notification_pkey"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    userId: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    createdAt: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(precision=3), server_default=text("CURRENT_TIMESTAMP")
    )

    User_: Mapped["User"] = relationship("User", back_populates="Notification")


class ReadPost(Base):
    __tablename__ = "ReadPost"
    __table_args__ = (
        ForeignKeyConstraint(
            ["resourceId"],
            ["resources.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="ReadPost_resourceId_fkey",
        ),
        ForeignKeyConstraint(
            ["userId"],
            ["User.id"],
            ondelete="CASCADE",
            onupdate="CASCADE",
            name="ReadPost_userId_fkey",
        ),
        PrimaryKeyConstraint("id", name="ReadPost_pkey"),
        Index("ReadPost_userId_resourceId_key", "userId", "resourceId", unique=True),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    userId: Mapped[str] = mapped_column(Text)
    resourceId = Column(UUID(as_uuid=False))
    readAt: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(precision=3), server_default=text("CURRENT_TIMESTAMP")
    )

    resources: Mapped["Resources"] = relationship(
        "Resources", back_populates="ReadPost"
    )
    User_: Mapped["User"] = relationship("User", back_populates="ReadPost")


t_Session = Table(
    "Session",
    Base.metadata,
    Column("sessionToken", Text, nullable=False),
    Column("userId", Text, nullable=False),
    Column("expires", TIMESTAMP(precision=3), nullable=False),
    Column(
        "createdAt",
        TIMESTAMP(precision=3),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("updatedAt", TIMESTAMP(precision=3), nullable=False),
    ForeignKeyConstraint(
        ["userId"],
        ["User.id"],
        ondelete="CASCADE",
        onupdate="CASCADE",
        name="Session_userId_fkey",
    ),
    Index("Session_sessionToken_key", "sessionToken", unique=True),
)


t__authorsToresources = Table(
    "_authorsToresources",
    Base.metadata,
    Column("A", UUID(as_uuid=False), primary_key=True, nullable=False),
    Column("B", UUID(as_uuid=False), primary_key=True, nullable=False),
    ForeignKeyConstraint(
        ["A"],
        ["authors.id"],
        ondelete="CASCADE",
        onupdate="CASCADE",
        name="_authorsToresources_A_fkey",
    ),
    ForeignKeyConstraint(
        ["B"],
        ["resources.id"],
        ondelete="CASCADE",
        onupdate="CASCADE",
        name="_authorsToresources_B_fkey",
    ),
    PrimaryKeyConstraint("A", "B", name="_authorsToresources_AB_pkey"),
    Index("_authorsToresources_B_index", "B"),
)


t__resourcesTotags = Table(
    "_resourcesTotags",
    Base.metadata,
    Column("A", UUID(as_uuid=False), primary_key=True, nullable=False),
    Column("B", UUID(as_uuid=False), primary_key=True, nullable=False),
    ForeignKeyConstraint(
        ["A"],
        ["resources.id"],
        ondelete="CASCADE",
        onupdate="CASCADE",
        name="_resourcesTotags_A_fkey",
    ),
    ForeignKeyConstraint(
        ["B"],
        ["tags.id"],
        ondelete="CASCADE",
        onupdate="CASCADE",
        name="_resourcesTotags_B_fkey",
    ),
    PrimaryKeyConstraint("A", "B", name="_resourcesTotags_AB_pkey"),
    Index("_resourcesTotags_B_index", "B"),
)


class Topics(Base):
    __tablename__ = "topics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["path_id"],
            ["paths.id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
            name="topics_path_id_fkey",
        ),
        ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
            name="topics_tag_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="topics_pkey"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    tag_id = Column(UUID(as_uuid=False))
    path_id = Column(UUID(as_uuid=False))

    path: Mapped["Paths"] = relationship("Paths", back_populates="topics")
    tag: Mapped["Tags"] = relationship("Tags", back_populates="topics")
    sections: Mapped[List["Sections"]] = relationship(
        "Sections", back_populates="topic"
    )


class Sections(Base):
    __tablename__ = "sections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
            name="sections_tag_id_fkey",
        ),
        ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
            name="sections_topic_id_fkey",
        ),
        PrimaryKeyConstraint("id", name="sections_pkey"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=uuid.uuid4)
    tag_id = Column(UUID(as_uuid=False))
    priority: Mapped[int] = mapped_column(Integer)
    topic_id = Column(UUID(as_uuid=False))

    tag: Mapped["Tags"] = relationship("Tags", back_populates="sections")
    topic: Mapped["Topics"] = relationship("Topics", back_populates="sections")
