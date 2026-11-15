"""值班站派发：固定编号、固定原文、回执核对、待核实补送、暂停语义。"""
import io
import csv
import time
import hashlib
from sqlalchemy import select, update
from fastapi import HTTPException
from src.config.settings import (
    STATION_RETRY_BASE, STATION_RETRY_MAX, STATION_VERIFY_DEADLINE,
)
from src.models import Job, Report, Dispatch


def render_content(job: Job) -> str:
    """根据批准快照渲染固定原文（CSV 文本）。同一期号永远补送同一份字节。"""
    out = io.StringIO()
    out.write('﻿')
    table = job.result.get('table', {})
    cols = table.get('columns', [])
    writer = csv.writer(out)

    def safe(v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
        text = str(v)
        return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text

    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows', []):
        writer.writerow([safe(row.get(c['key'], '')) for c in cols])
    return out.getvalue()


def checksum_of(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def next_sequence(db, report_id: int) -> int:
    current = db.scalar(
        select(Dispatch.sequence).where(Dispatch.report_id == report_id)
        .order_by(Dispatch.sequence.desc()).limit(1)
    )
    return (current or 0) + 1


def create_dispatch(db, report: Report) -> Dispatch:
    """到期生成新一期：固定编号 + 固定原文，状态待发。"""
    job = db.get(Job, report.job_id)
    if not job or not job.approved:
        raise HTTPException(409, '简报关联的分析未获批准，无法派发')
    sequence = next_sequence(db, report.id)
    now = time.time()
    content = render_content(job)
    d = Dispatch(
        report_id=report.id, sequence=sequence,
        number=f'RPT{report.id:04d}-{sequence:06d}',
        status='pending', content=content, checksum=checksum_of(content),
        attempts=0, last_error='', created_at=now, next_check=now, updated_at=now,
    )
    db.add(d)
    db.flush()
    return d


def backoff(attempts: int) -> float:
    return min(STATION_RETRY_BASE * (2 ** max(0, attempts - 1)), STATION_RETRY_MAX)


def claim_due(db, status: str, now: float | None = None) -> Dispatch | None:
    """认领一条到期记录并加行锁，避免多 worker/重启并发下重复处理。

    PostgreSQL 下 SKIP LOCKED 保证被其他 worker 持有的记录直接跳过；
    SQLite 不支持该子句时由写锁串行化，同样不会重复处理。
    """
    now = time.time() if now is None else now
    stmt = select(Dispatch).where(
        Dispatch.status == status, Dispatch.next_check <= now
    ).order_by(Dispatch.id).limit(1)
    try:
        d = db.scalars(stmt.with_for_update(skip_locked=True)).first()
    except Exception:
        d = db.scalars(stmt).first()
    if d is None:
        return None
    d.updated_at = now
    return d


def mark_delivered(db, d: Dispatch, receipt: dict):
    d.status = 'delivered'
    d.receipt_id = str(receipt.get('receipt_id', ''))[:80]
    d.delivered_at = float(receipt.get('received_at', time.time()))
    d.last_error = ''
    d.updated_at = time.time()


def mark_pending_verify(db, d: Dispatch, error: str):
    d.status = 'pending_verify'
    d.last_error = error[:500]
    d.next_check = time.time() + backoff(d.attempts)
    d.updated_at = time.time()


def mark_rejected(db, d: Dispatch, error: str):
    """同编号异文等永久性拒收：不再自动补送，转待核实等待人工裁决。"""
    d.status = 'pending_verify'
    d.last_error = ('[异文拒收] ' + error)[:500]
    d.next_check = time.time() + STATION_RETRY_MAX
    d.updated_at = time.time()


def pause_report(db, report: Report):
    """负责人暂停：不再发起新投递；在途待发件转待核实继续查回执。"""
    now = time.time()
    report.enabled = False
    db.execute(
        update(Dispatch).where(
            Dispatch.report_id == report.id, Dispatch.status == 'pending'
        ).values(status='pending_verify', updated_at=now,
                 last_error='计划已暂停，转待核实查回执', next_check=now)
    )


def verify_deadline(d: Dispatch, now: float) -> bool:
    return now - d.created_at > STATION_VERIFY_DEADLINE
