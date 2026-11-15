import time, json, logging
from pathlib import Path
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report, Dispatch
from src.services.business import analyze
from src.services import dispatch as dispatcher
from src.services import station_client
from src.services.audit import record
logging.basicConfig(level=logging.INFO)
def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j or j.status!='queued':return
        j.status='running'; db.commit()
        try:
            d=db.get(Dataset,j.dataset_id)
            result=analyze(d.records,j.params)
            json.dumps(result,allow_nan=False)
            j.result=result;j.status='completed';j.finished_at=time.time()
            record(db,'worker','job.completed',{'id':j.id})
        except Exception as e:
            logging.exception('Analysis failed')
            j.status='failed';j.error=str(e)[:990];j.finished_at=time.time()
            record(db,'worker','job.failed',{'id':j.id,'error':j.error})
        db.commit()

def _process_pending(db, d):
    """待发：首次投递原件，等待可核对回执。"""
    report=db.get(Report,d.report_id)
    if not report or not report.enabled:
        # 暂停后旧执行迟到：遵守暂停结果，不发起投递
        dispatcher.mark_pending_verify(db,d,'计划已暂停，不发起投递')
        return
    d.attempts+=1
    try:
        receipt=station_client.send(d.number,d.content,d.checksum,report.destination)
        if receipt.get('checksum')!=d.checksum or receipt.get('number')!=d.number:
            dispatcher.mark_pending_verify(db,d,'回执与简报编号/校验不一致')
            return
        dispatcher.mark_delivered(db,d,receipt)
        record(db,'worker','dispatch.delivered',{'id':d.id,'number':d.number,'receipt':d.receipt_id})
    except station_client.StationReject as e:
        logging.warning('Dispatch %s rejected: %s',d.number,e)
        dispatcher.mark_rejected(db,d,str(e))
        record(db,'worker','dispatch.rejected',{'id':d.id,'number':d.number,'error':d.last_error})
    except station_client.StationError as e:
        logging.warning('Dispatch %s pending verify: %s',d.number,e)
        dispatcher.mark_pending_verify(db,d,str(e))

def _process_pending_verify(db, d):
    """待核实：先查回执；查无且计划仍启用则补送同一原件；暂停后只查不补。"""
    now=time.time()
    report=db.get(Report,d.report_id)
    paused=not report or not report.enabled
    # 暂停后查无收件的取消期限：到期取消，不补送
    if paused and dispatcher.verify_deadline(d,now):
        d.status='cancelled';d.updated_at=now
        d.last_error=('暂停后查询期限内查无收件，取消不补送；'+(d.last_error or ''))[:500]
        record(db,'worker','dispatch.cancelled',{'id':d.id,'number':d.number,'reason':'verify-deadline'})
        return
    # 永久性异文拒收：只继续查回执，不再补送
    permanent=d.last_error.startswith('[异文拒收]')
    try:
        record_on_station=station_client.query_receipt(d.number)
    except station_client.StationError as e:
        dispatcher.mark_pending_verify(db,d,str(e))
        return
    if record_on_station:
        receipt=record_on_station.get('receipt') or {}
        if receipt.get('checksum')==d.checksum and receipt.get('number')==d.number:
            dispatcher.mark_delivered(db,d,receipt)
            record(db,'worker','dispatch.delivered',{'id':d.id,'number':d.number,'receipt':d.receipt_id,'recovered':True})
            return
        dispatcher.mark_rejected(db,d,'值班站记录与本编号原文不一致')
        return
    # 查无收件
    if paused or permanent:
        dispatcher.mark_pending_verify(db,d,'查无收件，保持待核实')
        return
    d.attempts+=1
    try:
        receipt=station_client.send(d.number,d.content,d.checksum,report.destination)
        if receipt.get('checksum')!=d.checksum or receipt.get('number')!=d.number:
            dispatcher.mark_pending_verify(db,d,'补送回执核对不一致')
            return
        dispatcher.mark_delivered(db,d,receipt)
        record(db,'worker','dispatch.delivered',{'id':d.id,'number':d.number,'receipt':d.receipt_id,'resent':True})
    except station_client.StationReject as e:
        dispatcher.mark_rejected(db,d,str(e))
    except station_client.StationError as e:
        dispatcher.mark_pending_verify(db,d,str(e))

def _issue_one_report(report_id, now):
    """原子认领到期计划并生成期号。

    先以条件 UPDATE 抢占 next_run：行级写锁在 SQLite/PostgreSQL 上都把并发
    worker 串行化，只有抢占成功者生成期号；其余 worker 复核 next_run 已推进即退出。
    (report_id, sequence) 唯一约束为最后兜底，冲突回滚不重复发起。
    """
    with Session() as db:
        r=db.get(Report,report_id)
        if not r or not r.enabled or r.next_run>now:
            return
        claimed=db.execute(
            update(Report)
            .where(Report.id==report_id,Report.enabled==True,Report.next_run<=now)
            .values(next_run=now+r.interval_seconds)
        ).rowcount
        db.flush()
        if not claimed:
            db.rollback();return
        try:
            d=dispatcher.create_dispatch(db,r)
            record(db,'worker','dispatch.created',{'id':d.id,'number':d.number,'report':r.id})
            db.commit()
        except IntegrityError:
            db.rollback()
        except Exception:
            logging.exception('issue dispatch failed for report %s',report_id)
            db.rollback()

def _run_dispatch_cycle():
    now=time.time()
    # 1) 到期计划先生成新一期（暂停的计划不再发起新投递）
    with Session() as db:
        due_ids=list(db.scalars(select(Report.id).where(Report.enabled==True,Report.next_run<=now)))
    for report_id in due_ids:
        _issue_one_report(report_id, now)
    # 2) 待发件首次投递（行锁认领，并发 worker 不会处理同一条）
    for _ in range(20):
        with Session() as db:
            d=dispatcher.claim_due(db,'pending')
            if not d:break
            try:_process_pending(db,d)
            except Exception:
                logging.exception('pending dispatch failed')
                dispatcher.mark_pending_verify(db,d,'worker 处理异常，转待核实')
            db.commit()
    # 3) 待核实件查回执/补送/到期取消
    for _ in range(20):
        with Session() as db:
            d=dispatcher.claim_due(db,'pending_verify')
            if not d:break
            try:_process_pending_verify(db,d)
            except Exception:
                logging.exception('verify dispatch failed')
                dispatcher.mark_pending_verify(db,d,'worker 处理异常，保持待核实')
            db.commit()

def tick():
    with Session() as db:
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').limit(3)))
    for job_id in queued:execute(job_id)
    _run_dispatch_cycle()

def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    with Session() as db:
        for j in db.scalars(select(Job).where(Job.status=='running')):
            j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
