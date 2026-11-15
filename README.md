# 供水漏损分诊实验

决策树与模型选择的真实业务分析小型项目。完整模拟客户、痛点、上下游、算法公式与一天工作剧本见 [BUSINESS.md](BUSINESS.md)。

## 模块与业务流程
数据接入（JSON/CSV、字段验证、批次指纹）→ 参数化分析（异步 Python worker）→ 结果复核（指标、图形、明细、解释、批准）→ 定时派发（固定编号、固定原文、值班站收件端回执核对）；另有业务总览和审计轨迹。
贯穿全栈的实体：Dataset 数据批次、Job 分析任务、Report 分发计划、Dispatch 带回执投递；辅助 User、Audit、Delivery（旧版内部归档，仅落盘凭证，不代表值班站送达）。

## 值班站收件与回执核对
- 每期简报生成全局固定编号 `RPT{计划}-{期号}` 与固定原文（SHA256 校验），派发到独立部署的**值班站收件端**（`station` 服务，文件落盘 + 进程锁）。
- 只有收到值班站回执且编号、校验一致才记**送达**；连接超时/5xx 列**待核实**，按退避重试，恢复后先查回执、查无收件再补送同一原件。
- 收件端对同编号幂等（并发重试、断线恢复、两端重启均不重复收件，重放原回执），**同编号异文拒收**并保留先到原件。
- 负责人暂停计划后不再发起新投递；在途待发/待核实件继续查回执，暂停后查无收件到期**取消、不补送**；已送达记录保留。
- 页面分栏列出待发、待核实、送达、取消四类投递与收件原文；演练台可切换值班站 online/offline/slow 场景。旧 Delivery 归档单独展示，不冒充送达。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18208；后端文档 http://localhost:19208/docs；值班站收件端文档 http://localhost:19308/docs；数据库宿主端口 17708。
`SEED_DEMO=true` 自动幂等 seed；不覆盖用户修改。手动 seed 命令可重复执行。

## 演示账号与权限
|账号|密码|真实权限|
|---|---|---|
|admin@demo.local|Demo123!|接入、执行、批准、分发、暂停、读取与下载|
|analyst@demo.local|Demo123!|接入、执行、读取与下载；不能批准或安排分发|
|viewer@demo.local|Demo123!|只读与下载|

## 技术与本地开发
Python 3.12 / FastAPI / SQLAlchemy / NumPy / SciPy / scikit-learn；PostgreSQL 16；Redis 7；Nginx；原生 HTML CSS JavaScript ES modules（用户指定）。后端所有校验、持久化和算法在服务端。无前端打包步骤。
后端：安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET、ARTIFACT_DIR 后在 backend/ 执行 `python -m migrations.initial`、`python -m scripts.seed_demo`、`uvicorn src.main:app`，另开 `python -m src.worker`；本地演练收件端执行 `STATION_INBOX=./station-inbox uvicorn src.station.app:app --port 8010`，并令 STATION_URL 指向它。前端使用带 /api 反向代理的 Nginx，直接打开 index.html 不支持 API。
后端目录新增 src/station（值班站收件端 app 与文件存储）、src/services/dispatch.py（编号/退避/暂停）、src/services/station_client.py（HTTP 客户端）。

## 目录与工程约定
backend/src/{models,schemas,services,routes,controllers,middlewares,constants,config,utils}；backend/scripts/seed_demo.py；backend/migrations/initial.py。
frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。
Role 枚举：admin/analyst/viewer；JobStatus：queued/running/completed/failed。后端 backend/src/constants/enums.py，前端 frontend/src/constants/enums.js；路由权限在 middlewares/auth.py；页面按相同角色控制操作入口。

## 环境变量与 Docker
COMPOSE_PROJECT_NAME=water-triage；FRONTEND_PORT=18208；BACKEND_PORT=19208；STATION_PORT=19308；DB_PORT=17708；DB_PASSWORD、JWT_SECRET、STATION_DRILL_TOKEN 见 .env.example；SEED_DEMO 默认 true。共享命名产物卷供后端下载与 worker 写入，值班站收件端用独立持久卷 station-inbox，数据库/Redis 各持久卷。
六个服务均有健康检查。Redis 队列加 SQL 排队状态兜底；worker 按 next_run 生成固定编号期号并向值班站投递，以数据库条件更新与行锁保证并发/重启不重复。周期 60 秒至 30 天。分发结果为批准分析的固定快照；若需新数据重新计算并建立新计划。值班站为本地可演练收件端，不连接邮件或企业聊天。
错误响应、请求编号、Redis 每 IP 每分钟 240 次限流、JWT 和数据库操作审计。演示密钥与密码仅供本机模拟；生产部署前配置独立密钥与账号。

## 数据与验收
所有数据为固定随机种子生成的模拟业务数据，不能作为实际生产决策证据。项目独立算法、输入边界及业务局限详见 BUSINESS.md。测试与截图统一存放 ../../test-artifacts/gb-1009/，源码不含日志/截图/测试报告。
清理本项目演示数据：`docker compose down -v --remove-orphans`（会删除本项目命名卷）。

## License
MIT，见 LICENSE。
