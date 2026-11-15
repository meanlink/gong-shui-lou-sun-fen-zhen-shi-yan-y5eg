import os
import time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from src.config.database import get_db
from src.config.settings import ARTIFACT_DIR
from src.models import Report, Delivery, Dispatch
from src.schemas.report import ReportInput, ScenarioInput
from src.middlewares.auth import current_user, admin_only
from src.services import reports, dispatch as dispatcher, station_client
from src.services.audit import record
from src.utils.serialization import report_dict, delivery_dict, dispatch_dict
router=APIRouter()

@router.get('/reports')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [report_dict(r) for r in db.scalars(select(Report).order_by(Report.id.desc()))]

@router.post('/reports',status_code=201)
def create(data:ReportInput,db=Depends(get_db),u=Depends(admin_only)):
    r=reports.create(db,data); record(db,u.email,'report.schedule',{'id':r.id,'destination':r.destination}); db.commit()
    return report_dict(r)

@router.post('/reports/{id}/toggle')
def toggle(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=db.get(Report,id)
    if not r:raise HTTPException(404,'分发计划不存在')
    if r.enabled:
        # 暂停：不再发起新投递；在途待发件转待核实继续查回执
        dispatcher.pause_report(db,r)
        record(db,u.email,'report.pause',{'id':id})
    else:
        r.enabled=True
        # 恢复后待核实件由 worker 自动查回执/补送；新期号按既定期到期时间发起
        record(db,u.email,'report.resume',{'id':id})
    db.commit()
    return report_dict(r)

# ---- 值班站投递（固定编号 + 回执核对） ----

@router.get('/dispatches')
def dispatches(status:str|None=None,db=Depends(get_db),u=Depends(current_user)):
    stmt=select(Dispatch).order_by(Dispatch.id.desc()).limit(200)
    if status:
        if status not in ('pending','pending_verify','delivered','cancelled'):
            raise HTTPException(422,'未知投递状态')
        stmt=select(Dispatch).where(Dispatch.status==status).order_by(Dispatch.id.desc()).limit(200)
    return [dispatch_dict(d) for d in db.scalars(stmt)]

@router.get('/dispatches/{id}')
def dispatch_detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dispatch,id)
    if not d:raise HTTPException(404,'投递记录不存在')
    return dispatch_dict(d,include_content=True)

@router.post('/dispatches/{id}/cancel')
def cancel_dispatch(id:int,db=Depends(get_db),u=Depends(admin_only)):
    d=db.get(Dispatch,id)
    if not d:raise HTTPException(404,'投递记录不存在')
    if d.status in ('delivered','cancelled'):
        raise HTTPException(409,'已送达或已取消的投递不能取消')
    d.status='cancelled';d.updated_at=time.time()
    record(db,u.email,'dispatch.cancel',{'id':d.id,'number':d.number})
    db.commit()
    return dispatch_dict(d)

# ---- 值班站收件端（可演练） ----

@router.get('/station/inbox')
def station_inbox(db=Depends(get_db),u=Depends(current_user)):
    try:
        return station_client.fetch_inbox()
    except station_client.StationError as e:
        raise HTTPException(503,f'值班站暂不可达：{e}')

@router.post('/station/scenario')
def station_scenario(data:ScenarioInput,db=Depends(get_db),u=Depends(admin_only)):
    try:
        result=station_client.set_scenario(data.scenario)
    except station_client.StationError as e:
        raise HTTPException(503,f'值班站暂不可达：{e}')
    except ValueError as e:
        raise HTTPException(422,str(e))
    record(db,u.email,'station.scenario',{'scenario':data.scenario})
    db.commit()
    return result

# ---- 旧版内部归档：只证明文件落盘，不代表值班站收件 ----

@router.get('/deliveries')
def deliveries(db=Depends(get_db),u=Depends(current_user)):
    return [delivery_dict(d) for d in db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(100))]
@router.get('/deliveries/{id}/download')
def download(id:int,format:str='csv',db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Delivery,id)
    if not d:raise HTTPException(404,'归档不存在')
    if format not in ('csv','json'):raise HTTPException(422,'支持 CSV 或 JSON')
    filename=d.filename+('.json' if format=='json' else '')
    p=os.path.join(ARTIFACT_DIR,filename)
    if not os.path.exists(p):raise HTTPException(404,'归档文件不存在，请重新安排分发')
    return FileResponse(p,filename=filename,media_type='application/json' if format=='json' else 'text/csv; charset=utf-8')
