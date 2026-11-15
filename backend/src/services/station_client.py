"""值班站收件端 HTTP 客户端：发送原件、查询回执，区分超时/拒收/异文。"""
import json
import urllib.error
import urllib.request
from src.config.settings import STATION_URL, STATION_TIMEOUT, STATION_DRILL_TOKEN


class StationError(Exception):
    """连接失败/超时/5xx：可恢复，派发件列待核实。"""


class StationReject(Exception):
    """409 同编号异文等永久性拒收：不再补送原件。"""


class StationNotFound(Exception):
    """404 查无此编号：不是故障，按“查无收件”处理。"""


def _request(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(
        STATION_URL + path, data=data, method=method,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=STATION_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode('utf-8'))
        except Exception:
            body = {'detail': '值班站响应无法解析'}
        if e.code == 409:
            raise StationReject(body.get('detail', '同编号异文拒收'))
        if e.code == 404:
            raise StationNotFound(body.get('detail', '值班站查无此编号简报'))
        if e.code in (503, 502, 504, 408):
            raise StationError(f'值班站暂不可用({e.code})')
        raise StationError(f'值班站返回 {e.code}: {body.get("detail", "")}')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise StationError(f'连接值班站失败: {e}')


def send(number: str, content: str, checksum: str, source: str):
    """发送原件。成功返回回执 dict；重复收件同样返回原回执。"""
    status, body = _request('POST', '/inbox/messages',
                            {'number': number, 'content': content,
                             'checksum': checksum, 'source': source})
    if status not in (200, 201) or 'receipt' not in body:
        raise StationError('值班站未给出可核对回执')
    return body['receipt']


def query_receipt(number: str):
    """查回执。查无返回 None；服务不可用抛 StationError。"""
    try:
        _, body = _request('GET', f'/inbox/messages/{number}')
    except StationNotFound:
        return None
    return body


def fetch_inbox():
    """读取值班站已落盘简报与原文（含回执）。"""
    _, body = _request('GET', '/inbox/messages')
    return body


def set_scenario(name: str):
    """切换演练场景 online/offline/slow，需要负责人令牌。"""
    if name not in ('online', 'offline', 'slow'):
        raise ValueError('演练场景仅支持 online/offline/slow')
    req = urllib.request.Request(
        STATION_URL + '/drill/scenario',
        data=json.dumps({'scenario': name}, ensure_ascii=False).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json', 'X-Drill-Token': STATION_DRILL_TOKEN},
    )
    try:
        with urllib.request.urlopen(req, timeout=STATION_TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode('utf-8'))
        except Exception:
            body = {'detail': '值班站响应无法解析'}
        if e.code in (503, 502, 504, 408):
            raise StationError(f'值班站暂不可用({e.code})')
        raise StationError(f'值班站返回 {e.code}: {body.get("detail", "")}')
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise StationError(f'连接值班站失败: {e}')
