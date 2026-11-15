import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const dispatches={list:(status)=>api('/dispatches'+(status?('?status='+status):'')),get:id=>api('/dispatches/'+id),cancel:id=>api('/dispatches/'+id+'/cancel',{method:'POST'})};
export const station={inbox:()=>api('/station/inbox'),scenario:scenario=>api('/station/scenario',{method:'POST',body:JSON.stringify({scenario})})};
