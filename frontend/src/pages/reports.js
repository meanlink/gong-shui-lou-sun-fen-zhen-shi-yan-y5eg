import {jobs,reports,dispatches,station} from '../api/entities.js';
import {download} from '../api/client.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {DispatchStatus,DispatchStatusHint} from '../constants/enums.js';

const STATUS_ORDER=['pending','pending_verify','delivered','cancelled'];

function statusBadge(s){
 return '<span class="status dispatch-status status-'+s+'">'+esc(DispatchStatus[s]||s)+'</span>';
}

export async function reportPage(){
 const [list,deliveries,allJobs,dispatchList,inbox]=await Promise.all([
  reports.list(),reports.deliveries(),jobs.list(),dispatches.list(),
  station.inbox().catch(e=>({scenario:'unreachable',messages:[],error:e.message}))
 ]);
 workspace.reports=list;
 const approved=allJobs.filter(j=>j.approved&&j.status==='completed');
 const counts=Object.fromEntries(STATUS_ORDER.map(s=>[s,dispatchList.filter(d=>d.status===s).length]));
 const stationRows=(inbox.messages||[]);
 return heading('05 / DUTY STATION','值班站收件与回执核对','每份简报带固定编号与固定原文，收到值班站可核对回执才记送达；超时列待核实，恢复后查回执或补送原件，同编号异文拒收。',
  '<button class="button" id="refresh-reports">刷新收件端 ↻</button>')+
 '<div class="report-grid"><section class="panel"><div class="section-title"><h2>创建分发计划</h2></div>'+
 '<form id="report-form"><label>简报名称<input name="name" required minlength="2" value="日间巡检复核简报"></label>'+
 '<label>已批准分析<select name="job_id" required>'+approved.map(j=>'<option value="'+j.id+'">'+esc(j.name)+'</option>').join('')+'</select></label>'+
 '<label>值班站<input name="destination" value="城北巡检班值班站 · 本地收件端" required></label>'+
 '<div class="parameter-grid"><label>分发周期<select name="interval_seconds"><option value="86400">每日</option><option value="604800">每周</option><option value="60">每分钟（验收）</option></select></label>'+
 '<label>首次执行<select name="delay_seconds"><option value="0">立即</option><option value="60">1 分钟后</option><option value="3600">1 小时后</option></select></label></div>'+
 '<button type="submit" class="primary" '+(session.user.role!=='admin'||!approved.length?'disabled':'')+'>保存分发计划</button></form>'+
 '<p class="hint">到期由 worker 生成固定编号期号并向值班站投递原件；仅负责人可创建、暂停或演练断线。</p>'+
 '<div class="drill-console panel"><div class="section-title"><h2>值班站演练台</h2><span>'+(inbox.scenario==='unreachable'?'连接失败':esc(inbox.scenario||'online'))+'</span></div>'+
 '<p class="hint">模拟值班站断线或慢速：断线期间投递超时列待核实，恢复后自动查回执或补送原件，不重复收件。</p>'+
 '<div class="drill-buttons">'+
 '<button class="button small" data-scenario="online" '+(session.user.role!=='admin'?'disabled':'')+'>恢复在线</button>'+
 '<button class="button small" data-scenario="offline" '+(session.user.role!=='admin'?'disabled':'')+'>模拟断线</button>'+
 '<button class="button small" data-scenario="slow" '+(session.user.role!=='admin'?'disabled':'')+'>模拟慢速</button></div>'+
 (inbox.error?'<p class="warning">值班站暂不可达：'+esc(inbox.error)+'</p>':'')+
 '</div></section>'+

 '<section><div class="section-title"><h2>运行中的计划</h2><span>'+list.filter(r=>r.enabled).length+' 条已启用 · 暂停后不发起新投递</span></div><div class="schedule-list">'+
 list.map(r=>'<article><div><strong>'+esc(r.name)+'</strong><p>'+esc(r.destination)+'</p><small>'+(r.enabled?'下次到期 '+date(r.next_run)+' · 周期 '+r.interval_seconds+' 秒':'已暂停 · 在途待核实件继续查回执')+'</small></div><button class="button small" data-toggle="'+r.id+'" '+(session.user.role!=='admin'?'disabled':'')+'>'+(r.enabled?'暂停':'启用')+'</button></article>').join('')+
 '</div>'+

 '<div class="panel dispatch-board"><div class="section-title"><h2>投递追踪（以回执为准）</h2><span>待发 '+counts.pending+' · 待核实 '+counts.pending_verify+' · 送达 '+counts.delivered+' · 取消 '+counts.cancelled+'</span></div>'+
 '<div class="dispatch-filters">'+STATUS_ORDER.map((s,i)=>'<button class="text-button filter-link" data-filter="'+s+'" data-active="'+(i===0?'1':'0')+'">'+esc(DispatchStatus[s])+' '+counts[s]+'</button>').join('')+'<button class="text-button filter-link" data-filter="" data-active="0">全部</button></div>'+
 '<div class="table-wrap"><table><thead><tr><th>固定编号</th><th>状态</th><th>尝试</th><th>回执</th><th>创建 / 送达</th><th>最近问题</th><th>操作</th></tr></thead><tbody id="dispatch-tbody">'+
 dispatchList.map(d=>dispatchRow(d)).join('')+
 (!dispatchList.length?'<tr><td colspan="7" class="empty">计划到期后，固定编号投递会出现在此处。</td></tr>':'')+
 '</tbody></table></div></div>'+

 '<section class="panel inbox"><div class="section-title"><h2>值班站收件端（落盘原文）</h2><span>'+stationRows.length+' 封已收件</span></div>'+
 stationRows.map(m=>'<div class="delivery"><div><strong>'+esc(m.number)+'</strong><p>'+esc(m.station||'城北巡检班值班站')+' · 收件 '+date(m.received_at)+'</p><small>回执 '+esc(m.receipt.receipt_id)+' · SHA256 '+esc(m.checksum.slice(0,20))+'…</small></div><div><button class="text-button" data-inbox-content="'+esc(m.number)+'">查看原文</button></div></div>').join('')+
 (!stationRows.length?'<p class="empty">值班站尚未收到任何简报；可先模拟断线再恢复，观察待核实与补送过程。</p>':'')+
 '</section>'+

 '<section class="panel legacy-inbox"><div class="section-title"><h2>旧版内部归档（仅落盘凭证）</h2><span>'+deliveries.length+' 份 · 不代表值班站送达</span></div>'+
 '<p class="hint">下列文件只证明后端曾把快照写入本地卷，未取得值班站回执，不计入送达。</p>'+
 deliveries.map(d=>'<div class="delivery"><div><strong>'+esc(d.filename)+'</strong><p>'+esc(d.destination)+' · '+date(d.created_at)+'</p><small>SHA256 '+esc(d.checksum.slice(0,24))+'…</small></div><div><button class="text-button" data-download="'+d.id+'" data-format="csv">CSV ↓</button><button class="text-button" data-download="'+d.id+'" data-format="json">JSON ↓</button></div></div>').join('')+
 (!deliveries.length?'<p class="empty">暂无内部归档文件。</p>':'')+
 '</section></section></div>'+

 '<div id="content-modal" class="modal hidden"><div class="modal-card"><div class="section-title"><h2 id="modal-title">简报原文</h2><button class="text-button" id="modal-close">关闭</button></div><pre id="modal-body"></pre></div></div>';
}

function dispatchRow(d){
 const canCancel=session.user.role==='admin'&&d.status!=='delivered'&&d.status!=='cancelled';
 return '<tr data-status="'+esc(d.status)+'"><td><strong>'+esc(d.number)+'</strong></td><td>'+statusBadge(d.status)+
  '<small class="status-hint">'+esc(DispatchStatusHint[d.status]||'')+'</small></td><td>'+d.attempts+'</td>'+
  '<td>'+(d.receipt_id?esc(d.receipt_id):'—')+'</td>'+
  '<td><small>'+date(d.created_at)+(d.delivered_at?'<br>送达 '+date(d.delivered_at):'')+'</small></td>'+
  '<td><small>'+esc(d.last_error||'—')+'</small></td>'+
  '<td><button class="text-button" data-dispatch-content="'+d.id+'">原文</button>'+
  (canCancel?'<button class="text-button danger-link" data-cancel="'+d.id+'">取消</button>':'')+'</td></tr>';
}

export function bindReports(refresh){
 document.querySelector('#refresh-reports').onclick=refresh;
 submit(document.querySelector('#report-form'),async f=>{
  await reports.create({name:f.get('name'),job_id:Number(f.get('job_id')),destination:f.get('destination'),interval_seconds:Number(f.get('interval_seconds')),delay_seconds:Number(f.get('delay_seconds'))});
  notify('计划已保存，到期生成固定编号并投递值班站');await refresh();
 });
 document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{
  try{await reports.toggle(b.dataset.toggle);await refresh();}catch(e){notify(e.message,true);}
 });
 document.querySelectorAll('[data-scenario]').forEach(b=>b.onclick=async()=>{
  try{await station.scenario(b.dataset.scenario);notify('值班站演练场景已切换为 '+b.dataset.scenario);await refresh();}catch(e){notify(e.message,true);}
 });
 document.querySelectorAll('[data-cancel]').forEach(b=>b.onclick=async()=>{
  if(!confirm('确认取消该投递？取消后不补送，已送达记录不受影响。'))return;
  try{await dispatches.cancel(b.dataset.cancel);notify('投递已取消');await refresh();}catch(e){notify(e.message,true);}
 });
 document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{
  const f=b.dataset.filter;
  document.querySelectorAll('#dispatch-tbody tr').forEach(tr=>{tr.style.display=(!f||tr.dataset.status===f)?'':'none';});
  document.querySelectorAll('[data-filter]').forEach(x=>x.dataset.active=x===b?'1':'0');
 });
 document.querySelectorAll('[data-dispatch-content]').forEach(b=>b.onclick=async()=>{
  try{const d=await dispatches.get(b.dataset.dispatchContent);openModal('简报原文 · '+d.number,d.content);}catch(e){notify(e.message,true);}
 });
 document.querySelectorAll('[data-inbox-content]').forEach(b=>b.onclick=async()=>{
  try{
   const inbox=await station.inbox();
   const m=(inbox.messages||[]).find(x=>x.number===b.dataset.inboxContent);
   if(!m)throw new Error('值班站已无该编号记录');
   openModal('值班站落盘原文 · '+m.number,m.content);
  }catch(e){notify(e.message,true);}
 });
 document.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>download(b.dataset.download,b.dataset.format).catch(e=>notify(e.message,true)));
 const modal=document.querySelector('#content-modal');
 document.querySelector('#modal-close').onclick=()=>modal.classList.add('hidden');
 modal.onclick=e=>{if(e.target===modal)modal.classList.add('hidden');};
}

function openModal(title,text){
 document.querySelector('#modal-title').textContent=title;
 document.querySelector('#modal-body').textContent=text;
 document.querySelector('#content-modal').classList.remove('hidden');
}
