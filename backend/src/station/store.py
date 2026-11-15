"""值班站收件端持久化：文件落盘、原子写入、进程锁、幂等收件。

收件箱目录结构（STATION_INBOX，默认 /station-inbox）：
  messages/<编号>.json   每封简报一个文件，先写临时文件再 rename，落盘即持久
  scenario.json          演练场景（online/offline/slow）
  .lock                  全量串行锁，保证并发重试不重复收件
"""
import os
import json
import time
import fcntl
import hashlib
from contextlib import contextmanager

INBOX_DIR = os.getenv('STATION_INBOX', '/station-inbox')
MESSAGE_DIR = os.path.join(INBOX_DIR, 'messages')
SCENARIO_FILE = os.path.join(INBOX_DIR, 'scenario.json')
LOCK_FILE = os.path.join(INBOX_DIR, '.lock')
VALID_SCENARIOS = ('online', 'offline', 'slow')


def ensure_dirs():
    os.makedirs(MESSAGE_DIR, exist_ok=True)
    if not os.path.exists(SCENARIO_FILE):
        _atomic_write(SCENARIO_FILE, {'scenario': 'online', 'updated_at': time.time()})


def _atomic_write(path, payload):
    tmp = f'{path}.tmp-{os.getpid()}-{time.time_ns()}'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@contextmanager
def locked():
    """串行化所有写操作：并发重试、两端重启后同时投递都不重复收件。"""
    ensure_dirs()
    with open(LOCK_FILE, 'w') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def get_scenario():
    ensure_dirs()
    try:
        with open(SCENARIO_FILE, encoding='utf-8') as f:
            data = json.load(f)
        return data.get('scenario', 'online')
    except (FileNotFoundError, json.JSONDecodeError):
        return 'online'


def set_scenario(name):
    if name not in VALID_SCENARIOS:
        raise ValueError(f'未知演练场景: {name}')
    ensure_dirs()
    _atomic_write(SCENARIO_FILE, {'scenario': name, 'updated_at': time.time()})
    return name


def _message_path(number):
    # 编号仅允许文件名安全字符，杜绝路径穿越
    safe = ''.join(c for c in str(number) if c.isalnum() or c in ('-', '_', '.'))
    if not safe or safe != str(number):
        raise ValueError('非法简报编号')
    return os.path.join(MESSAGE_DIR, safe + '.json')


def receive(number, content, checksum, source):
    """幂等收件。返回 (结果, 消息或回执)。

    accepted  首次收件，落盘并给回执
    duplicate 编号已存在且原文一致 → 不重复收件，重放原回执
    rejected  同编号异文 → 拒收，保留先到原件
    """
    if not number or not isinstance(content, str):
        return 'invalid', '编号与原文必填'
    actual = hashlib.sha256(content.encode('utf-8')).hexdigest()
    if checksum != actual:
        return 'rejected', '校验值与原文不一致，拒收'
    path = _message_path(number)
    with locked():
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                existing = json.load(f)
            if existing.get('checksum') == checksum and existing.get('content') == content:
                return 'duplicate', existing['receipt']
            return 'rejected', '同编号异文，拒收并保留先到原件'
        receipt = {
            'receipt_id': f'RCPT-{number}-{actual[:12]}',
            'number': number,
            'checksum': checksum,
            'received_at': time.time(),
            'station': '城北巡检班值班站',
        }
        record = {
            'number': number, 'content': content, 'checksum': checksum,
            'source': source, 'received_at': receipt['received_at'],
            'receipt': receipt,
        }
        _atomic_write(path, record)
        return 'accepted', receipt


def lookup(number):
    """查回执：只读取，不改变收件状态。"""
    try:
        path = _message_path(number)
    except ValueError:
        return None
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def list_messages():
    ensure_dirs()
    items = []
    for name in sorted(os.listdir(MESSAGE_DIR)):
        if not name.endswith('.json'):
            continue
        with open(os.path.join(MESSAGE_DIR, name), encoding='utf-8') as f:
            items.append(json.load(f))
    items.sort(key=lambda m: m.get('received_at', 0), reverse=True)
    return items
