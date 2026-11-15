"""值班站收件端（可演练）。

独立部署的本地 HTTP 服务，模拟城北巡检班值班站：
- POST /inbox/messages      投递简报，固定编号 + 原文，幂等收件，同编号异文拒收
- GET  /inbox/messages      列出已落盘简报与原文
- GET  /inbox/messages/{n}  查询单封与回执
- POST /drill/scenario      切换 online/offline/slow 演练场景（负责人）
- GET  /health              存活探针（不受 offline 场景影响）

offline 场景下收件接口返回 503，用于演练超时列待核实、恢复后查回执/补送原件。
"""
import os
import time
import logging
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from src.station import store

logging.basicConfig(level=logging.INFO)
app = FastAPI(title='值班站收件端', description='巡检简报本地可演练收件服务')
# 演练控制口令，默认本机演示值；compose 中由环境变量注入
DRILL_TOKEN = os.getenv('STATION_DRILL_TOKEN', 'station-drill-token')
SLOW_DELAY = float(os.getenv('STATION_SLOW_DELAY', '6.0'))


class MessageIn(BaseModel):
    number: str = Field(min_length=1, max_length=64)
    content: str
    checksum: str = Field(min_length=64, max_length=64)
    source: str = Field(default='water-triage-dispatcher', max_length=120)


class ScenarioIn(BaseModel):
    scenario: str


def _drill_guard(x_drill_token: str | None):
    if x_drill_token != DRILL_TOKEN:
        raise HTTPException(403, '演练控制需要负责人令牌')


@app.get('/health')
def health():
    return {'status': 'healthy', 'service': 'station-inbox', 'scenario': store.get_scenario()}


@app.post('/inbox/messages', status_code=201)
def receive(msg: MessageIn):
    scenario = store.get_scenario()
    if scenario == 'offline':
        # 模拟值班站断线：连接仍被接受但服务不可用，派发端按超时处理
        raise HTTPException(503, '值班站断线演练中，暂不收件')
    if scenario == 'slow':
        time.sleep(SLOW_DELAY)
    try:
        outcome, payload = store.receive(msg.number, msg.content, msg.checksum, msg.source)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if outcome == 'accepted':
        return {'outcome': 'accepted', 'receipt': payload}
    if outcome == 'duplicate':
        # 幂等：重放原回执，不产生第二封收件
        return {'outcome': 'duplicate', 'receipt': payload}
    if outcome == 'rejected':
        return JSONResponse(status_code=409, content={'detail': payload, 'outcome': 'rejected'})
    raise HTTPException(422, payload)


@app.get('/inbox/messages')
def messages():
    return {'scenario': store.get_scenario(), 'messages': store.list_messages()}


@app.get('/inbox/messages/{number}')
def one(number: str):
    record = store.lookup(number)
    if record is None:
        raise HTTPException(404, '值班站查无此编号简报')
    return record


@app.post('/drill/scenario')
def scenario(data: ScenarioIn, x_drill_token: str | None = Header(default=None)):
    _drill_guard(x_drill_token)
    try:
        name = store.set_scenario(data.scenario)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {'scenario': name}


@app.get('/drill/scenario')
def get_scenario(x_drill_token: str | None = Header(default=None)):
    _drill_guard(x_drill_token)
    return {'scenario': store.get_scenario()}
