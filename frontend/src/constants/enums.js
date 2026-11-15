export const Role={admin:'业务负责人',analyst:'分析员',viewer:'观察员'};
export const JobStatus={queued:'排队中',running:'计算中',completed:'已完成',failed:'执行失败'};
export const DispatchStatus={
 pending:'待发',
 pending_verify:'待核实',
 delivered:'送达',
 cancelled:'取消'
};
export const DispatchStatusHint={
 pending:'已生成固定编号与原文，等待首次投递',
 pending_verify:'超时或回执未核对，恢复后查回执或补送原件',
 delivered:'收到值班站可核对回执，校验一致',
 cancelled:'暂停后查无收件或人工取消，不补送'
};
