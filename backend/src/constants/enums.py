from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
class DispatchStatus(str, Enum):
    # 待发：已生成固定编号与原文，尚未完成任何一次投递
    pending = 'pending'
    # 待核实：超时/断线/回执未能核对，恢复后查回执或补送原件
    pending_verify = 'pending_verify'
    # 送达：收到值班站可核对回执且校验一致
    delivered = 'delivered'
    # 取消：暂停后查无收件，或负责人人工取消
    cancelled = 'cancelled'
