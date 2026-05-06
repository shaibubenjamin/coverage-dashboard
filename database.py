"""
database.py — SARMAAN II Coverage Dashboard
Auth models only: Role, Permission, User, AuditLog.
SQLite for local dev; set DATABASE_URL env var for PostgreSQL in production.
"""
import os
import datetime
import tempfile
from typing import List

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean,
    DateTime, Text, ForeignKey, Table,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker


# ── Database connection ────────────────────────────────────────────
def _default_sqlite_url() -> str:
    if os.path.exists("/data"):
        return "sqlite:////data/coverage_dashboard.db"
    base = os.path.dirname(os.path.abspath(__file__))
    path = base if os.access(base, os.W_OK) else tempfile.gettempdir()
    return f"sqlite:///{os.path.join(path, 'coverage_dashboard.db')}"


def _build_postgres_url() -> str | None:
    from urllib.parse import quote_plus
    host = os.environ.get("POSTGRES_HOST")
    if not host:
        return None
    user = os.environ.get("POSTGRES_USER", "coverage_app")
    pwd  = os.environ.get("POSTGRES_PASSWORD", "")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db   = os.environ.get("POSTGRES_DB",   "coverage_dashboard")
    return f"postgresql://{quote_plus(user)}:{quote_plus(pwd)}@{host}:{port}/{db}"


DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or _build_postgres_url()
    or _default_sqlite_url()
)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine       = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


# ── Association table ─────────────────────────────────────────────
role_permissions = Table(
    "role_permissions", Base.metadata,
    Column("role_id",       Integer, ForeignKey("roles.id"),       primary_key=True),
    Column("permission_id", Integer, ForeignKey("permissions.id"), primary_key=True),
)


# ── Models ────────────────────────────────────────────────────────

class Permission(Base):
    __tablename__ = "permissions"
    id   = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")


class Role(Base):
    __tablename__ = "roles"
    id   = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users       = relationship("User", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id                   = Column(Integer, primary_key=True)
    name                 = Column(String(128), nullable=False)
    email                = Column(String(256), unique=True, nullable=False)
    password_hash        = Column(String(256), nullable=True)
    role_id              = Column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active            = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=True)
    invite_token         = Column(String(128), nullable=True, unique=True)
    invite_expires       = Column(DateTime, nullable=True)
    created_at           = Column(DateTime, default=datetime.datetime.utcnow)

    role       = relationship("Role", back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user",
                              foreign_keys="AuditLog.user_id")

    @property
    def permission_names(self) -> List[str]:
        return [p.name for p in self.role.permissions]


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True)
    action     = Column(String(64), nullable=False)
    details    = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="audit_logs",
                        foreign_keys=[user_id])


# ── DB helpers ────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Seed data ─────────────────────────────────────────────────────

ROLES = {
    "super_admin": ["view_dashboard", "manage_users", "configure_project",
                    "approve_validation", "view_audit_log"],
    "admin":       ["view_dashboard", "manage_users", "approve_validation"],
    "validator":   ["view_dashboard", "approve_validation"],
    "public":      ["view_dashboard"],
}

SUPER_ADMIN_EMAIL    = os.environ.get("SUPER_ADMIN_EMAIL",    "admin@sarmaan.org")
SUPER_ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "Sarmaan@2024!")
SUPER_ADMIN_NAME     = "Super Admin"


def init_db():
    Base.metadata.create_all(bind=engine)

    from auth import hash_password

    with SessionLocal() as s:
        # Permissions
        all_perms = sorted({p for perms in ROLES.values() for p in perms})
        perm_objs = {}
        for name in all_perms:
            obj = s.query(Permission).filter_by(name=name).first()
            if not obj:
                obj = Permission(name=name)
                s.add(obj)
            perm_objs[name] = obj
        s.flush()

        # Roles
        role_objs = {}
        for rname, pnames in ROLES.items():
            obj = s.query(Role).filter_by(name=rname).first()
            if not obj:
                obj = Role(name=rname)
                s.add(obj)
            obj.permissions = [perm_objs[p] for p in pnames]
            role_objs[rname] = obj
        s.flush()

        # Super admin user
        if not s.query(User).filter_by(email=SUPER_ADMIN_EMAIL).first():
            s.add(User(
                name=SUPER_ADMIN_NAME,
                email=SUPER_ADMIN_EMAIL,
                password_hash=hash_password(SUPER_ADMIN_PASSWORD),
                role_id=role_objs["super_admin"].id,
                must_change_password=False,
            ))

        s.commit()
