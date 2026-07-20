from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(1), primary_key=True)  # 'A' | 'B'
    name: Mapped[str] = mapped_column(String(100))

    rest_url: Mapped[str | None] = mapped_column(String(255), default=None)
    bh_rest_token: Mapped[str | None] = mapped_column(String(255), default=None)
    token_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_category_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("company_id", "bh_category_id"),)


class BusinessSector(Base):
    __tablename__ = "business_sectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_business_sector_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("company_id", "bh_business_sector_id"),)


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(1), ForeignKey("companies.id"))
    bh_skill_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))

    __table_args__ = (UniqueConstraint("company_id", "bh_skill_id"),)
