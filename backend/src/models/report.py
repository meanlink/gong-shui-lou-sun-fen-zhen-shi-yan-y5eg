from sqlalchemy import String, Double, ForeignKey, Boolean, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    destination: Mapped[str] = mapped_column(String(120))
    interval_seconds: Mapped[int]
    next_run: Mapped[float] = mapped_column(Double)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
class Delivery(Base):
    """旧版内部归档：只证明文件落盘，不代表值班站收件。"""
    __tablename__ = 'deliveries'
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    created_at: Mapped[float] = mapped_column(Double)
    checksum: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(120))
class Dispatch(Base):
    """带固定编号与回执核对的值班站投递。"""
    __tablename__ = 'dispatches'
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    # 同计划内单调递增的期号，与 report_id 拼成全局固定编号
    sequence: Mapped[int]
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', index=True)
    content: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(String(500), default='')
    # 值班站回执
    receipt_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    delivered_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
    next_check: Mapped[float] = mapped_column(Double, default=0.0)
    updated_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('report_id', 'sequence', name='uq_dispatch_report_sequence'),
                      Index('ix_dispatch_status_check', 'status', 'next_check'))
