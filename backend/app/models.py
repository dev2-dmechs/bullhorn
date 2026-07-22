from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(1), primary_key=True)  # 'A' | 'B'
    name: Mapped[str] = mapped_column(String(100))

    rest_url: Mapped[str | None] = mapped_column(String(255), default=None)
    bh_rest_token: Mapped[str | None] = mapped_column(String(255), default=None)
    token_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class BusinessSector(Base):
    __tablename__ = "business_sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_business_sector_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    date_added: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (UniqueConstraint("company_id", "bh_business_sector_id"),)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_category_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    occupation: Mapped[str | None] = mapped_column(String(50), default=None)
    description: Mapped[str | None] = mapped_column(String(255), default=None)
    type: Mapped[str | None] = mapped_column(String(20), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    skills: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), default=None)
    specialties: Mapped[list[int] | None] = mapped_column(ARRAY(Integer), default=None)
    date_added: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (UniqueConstraint("company_id", "bh_category_id"),)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_skill_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("company_id", "bh_skill_id"),)


class JobOrderSeen(Base):
    __tablename__ = "job_orders_seen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_job_order_id: Mapped[int] = mapped_column(Integer)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("company_id", "bh_job_order_id"),)


class JobOrder(Base):
    __tablename__ = "job_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_job_order_id: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("company_id", "bh_job_order_id"),)
