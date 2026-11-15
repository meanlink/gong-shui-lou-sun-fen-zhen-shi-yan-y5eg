import os
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./local.db')
REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
JWT_SECRET = os.environ.get('JWT_SECRET', 'local-development-change-before-deploy')
ARTIFACT_DIR = os.getenv('ARTIFACT_DIR', '/artifacts')
# 可演练的值班站收件端
STATION_URL = os.getenv('STATION_URL', 'http://station:8010').rstrip('/')
STATION_TIMEOUT = float(os.getenv('STATION_TIMEOUT', '4.0'))
STATION_DRILL_TOKEN = os.getenv('STATION_DRILL_TOKEN', 'station-drill-token')
# 待核实件退避：首次 30 秒，之后倍增，上限 15 分钟
STATION_RETRY_BASE = float(os.getenv('STATION_RETRY_BASE', '30.0'))
STATION_RETRY_MAX = float(os.getenv('STATION_RETRY_MAX', '900.0'))
# 暂停后待核实件继续查询的最长时间（默认 24 小时），查无收件则取消
STATION_VERIFY_DEADLINE = float(os.getenv('STATION_VERIFY_DEADLINE', str(24 * 3600)))
