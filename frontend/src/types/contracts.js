/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,report_id:number,sequence:number,number:string,status:'pending'|'pending_verify'|'delivered'|'cancelled',checksum:string,attempts:number,last_error:string,receipt_id:?string,delivered_at:?number,created_at:number,next_check:number,updated_at:number,content?:string}} Dispatch */
export {};
