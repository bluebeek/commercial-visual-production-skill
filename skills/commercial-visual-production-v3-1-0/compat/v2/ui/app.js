let payload=null,current='R0',busy=false,drafts={};
const $=s=>document.querySelector(s);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels={PASS:'已签核',BLOCK:'有问题',PENDING:'待审核',READY:'可签核',SKIPPED:'不适用（未签核）',approved:'通过',rejected:'退回',unknown:'待证据',stale:'需复核',pending:'未检查',na:'不适用'};
function toast(msg,error=false){const d=$('#toast');d.textContent=msg;d.className='alert'+(error?' error':'');d.hidden=false;clearTimeout(window._toastTimer);window._toastTimer=setTimeout(()=>d.hidden=true,6000)}
function storageKey(){return 'visual-review-drafts:'+payload.state.project_id}
function saveDrafts(){try{localStorage.setItem(storageKey(),JSON.stringify(drafts))}catch(e){toast('无法保存本机草稿，请先复制未提交内容',true)}}
function remember(){document.querySelectorAll('input[id],textarea[id],select[id]').forEach(el=>{if(el.id!=='zoom')drafts[el.id]=el.value});if(payload)saveDrafts()}
function value(id,fallback=''){return document.getElementById(id)?.value?.trim()??String(drafts[id]??fallback).trim()}
function paths(id){return value(id).split(/\r?\n/).map(x=>x.trim()).filter(Boolean)}
function field(id,fallback=''){return esc(drafts[id]??fallback)}
async function req(action,data={}){
 if(busy)return;remember();busy=true;document.body.classList.add('spinner');
 try{
  const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,data,expected_seq:payload.state.seq})});
  const o=await r.json();if(!r.ok||!o.ok){if(r.status===409)await load();throw Error(o.error||'操作未完成')}
  if(data.check_id){for(const prefix of ['e-','f-','i-','p-'])delete drafts[prefix+data.check_id]}
  if(data.issue_id){for(const prefix of ['v-','r-','rf-'])delete drafts[prefix+data.issue_id]}
  saveDrafts();await load();toast('已保存。只有对应文件仍有效时，批准才会继续有效。');
 }catch(e){toast(e.message,true)}finally{busy=false;document.body.classList.remove('spinner')}
}
async function load(){
 const r=await fetch('/api/state');if(!r.ok)throw Error('无法读取项目；旧版项目请先执行 migrate');
 payload=await r.json();
 try{drafts=JSON.parse(localStorage.getItem(storageKey())||'{}')}catch(e){drafts={}}
 render();
}
function previewPaths(){return [...new Set([...(payload.previews[current]||[]).map(x=>'artifacts/'+x),...Object.keys(payload.state.active_revision?.files||{}),...Object.keys(payload.state.baseline?.files||{})])].filter(p=>/\.(png|jpg|jpeg|webp)$/i.test(p))}
function fileUrl(path){return '/api/file?path='+encodeURIComponent(path)}
function render(){
 const {state:s,definitions:d,stages,applicable_checks:active}=payload;
 $('#project').textContent=s.project_name;
 $('#project-sub').textContent=`V2.3.0 · ${s.task_mode} · ${s.modified_at.slice(0,19).replace('T',' ')} UTC · ${active.length} 项适用检查`;
 $('#nav').innerHTML=stages.map(m=>`<button class="stage-link ${current===m.id?'selected':''}" data-stage="${m.id}"><span>${m.id} · ${esc(m.name)}</span><span class="pill ${m.status}">${labels[m.status]}</span></button>`).join('');
 const approved=active.filter(c=>['approved','na'].includes(s.checks[c].status)).length;
 $('#summary').innerHTML=`<div class="metric"><b>${stages.filter(m=>m.status==='PASS').length}/${stages.filter(m=>m.status!=='SKIPPED').length}</b><span>适用模块已签核</span></div><div class="metric"><b>${approved}/${active.length}</b><span>已核验检查项</span></div><div class="metric"><b>${s.issues.filter(i=>i.status==='open').length}</b><span>待修复问题</span></div><div class="metric"><b>${esc(s.active_revision?.id||'未登记')}</b><span>当前成品版本${s.active_revision?.stale?'（已失效）':''}</span></div>`;
 const stage=d.modules.find(m=>m.id===current)||d.modules[0],info=stages.find(m=>m.id===stage.id);
 const cards=stage.checks.filter(c=>active.includes(c.id)).map((c,i)=>{
  const r=s.checks[c.id],issues=s.issues.filter(k=>k.check_id===c.id&&k.status==='open');
  return `<article class="check"><header><div><div class="index">${c.id}</div><h3>${esc(c.name)}</h3></div><span class="pill ${r.status}">${labels[r.status]}</span></header><p class="evidence-label">应核验证据：${esc(c.evidence)}</p>${r.auto?`<p class="evidence-label">程序 ${esc(r.auto.status)}：${esc(r.auto.message)}</p>`:''}<div class="check-form"><div><label for="e-${c.id}">验收说明</label><textarea id="e-${c.id}">${field('e-'+c.id,r.evidence)}</textarea><label for="f-${c.id}">真实证据文件（项目内相对路径，每行一个）</label><textarea id="f-${c.id}" placeholder="artifacts/final.png">${field('f-'+c.id,Object.keys(r.files||{}).join('\n'))}</textarea></div><div><label for="i-${c.id}">问题 / 不适用原因</label><textarea id="i-${c.id}">${field('i-'+c.id)}</textarea><label for="p-${c.id}">问题等级</label><select id="p-${c.id}">${['P0','P1','P2'].map(k=>`<option ${String(drafts['p-'+c.id]||'P1')===k?'selected':''}>${k}</option>`).join('')}</select></div></div><div class="check-buttons">${[['approve','核验通过'],['reject','提交问题并退回'],['unknown','证据不足'],...(c.allow_na?[['na','不适用']]:[]),['reopen','重新核验']].map(([action,label])=>`<button class="btn-outline btn-xs" data-action="${action}" data-check="${c.id}">${label}</button>`).join('')}<button class="btn-plain btn-xs" data-ticket="${c.id}">本项工单</button></div>${issues.map(k=>`<div class="issue"><strong>${esc(k.id)} · ${esc(k.severity)}</strong><p>${esc(k.text)}</p><div class="issue-form"><input id="v-${k.id}" placeholder="新修复版号" value="${field('v-'+k.id)}"><input id="r-${k.id}" placeholder="实际修复说明" value="${field('r-'+k.id)}"><button class="btn-outline btn-xs" data-resolve="${k.id}">解决并待复核</button></div><textarea id="rf-${k.id}" placeholder="修复证据文件，每行一个">${field('rf-'+k.id)}</textarea></div>`).join('')}</article>`;
 }).join('');
 const preview=previewPaths().map(path=>`<figure class="preview-item"><button class="btn-plain" data-image="${esc(path)}"><img src="${fileUrl(path)}" alt="${esc(path)}" loading="lazy"></button><figcaption>${esc(path)}</figcaption></figure>`).join('');
 const revision=`<details class="check"><summary>登记当前成品版本 / 局部修改基准</summary><p>换图前登记新版本；仅填写版本号不构成修复。</p><input id="revision-id" placeholder="版本号，如 v003" value="${field('revision-id')}"><textarea id="revision-files" placeholder="成品文件，每行一个">${field('revision-files')}</textarea><button class="btn-outline" data-register>登记成品版本</button>${s.task_mode==='local-edit'?`<p>导入基准：同时列出已批准图片及批准依据文件。</p><textarea id="baseline-files">${field('baseline-files')}</textarea><textarea id="baseline-note" placeholder="基准批准依据">${field('baseline-note')}</textarea><button class="btn-outline" data-baseline>记录基准批准依据</button>`:''}</details>`;
 $('#review').innerHTML=`${revision}<div class="review-head"><div><h2>${stage.id} · ${esc(stage.name)}</h2><p>${esc(stage.goal)}</p></div><span class="pill ${info.status}">${labels[info.status]}</span></div><div class="stage-panel"><div class="preview-area"><div class="actions"><b>图像对照</b><button class="btn-outline btn-xs" data-compare>放大 / 并排对照</button></div><div class="previews">${preview}</div></div>${cards||'<p>当前任务模式不适用此模块。跳过不等于已签核，也不会伪造前序批准。</p>'}${info.status!=='SKIPPED'?`<div class="stage-tools"><button class="btn-main" data-signoff="${stage.id}">确认本模块并签核</button><button class="btn-outline" data-revoke="${stage.id}">撤销签核</button><button class="btn-plain" data-ticket-stage="${stage.id}">导出本模块工单</button></div>`:''}</div>`;
 document.querySelectorAll('.preview-item img').forEach(im=>im.addEventListener('error',()=>im.closest('figure').hidden=true));
}
function download(url){const a=document.createElement('a');a.href=url;document.body.append(a);a.click();a.remove()}
function showCompare(first){
 remember();const paths=previewPaths();if(first&&!paths.includes(first))paths.unshift(first);
 if(!paths.length)return toast('请先登记实际图像，再打开对照',true);
 const dialog=$('#image-dialog');const options=paths.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');
 $('#left-select').innerHTML=options;$('#right-select').innerHTML=options;
 if(first)$('#left-select').value=first;if(paths.length>1)$('#right-select').selectedIndex=1;
 const update=()=>{$('#left-image').src=fileUrl($('#left-select').value);$('#right-image').src=fileUrl($('#right-select').value)};
 $('#left-select').onchange=update;$('#right-select').onchange=update;update();dialog.showModal();
}
document.addEventListener('input',e=>{if(e.target.id&&e.target.id!=='zoom'&&payload){drafts[e.target.id]=e.target.value;saveDrafts()}});
document.addEventListener('change',e=>{if(e.target.id&&e.target.id!=='zoom'&&payload){drafts[e.target.id]=e.target.value;saveDrafts()}});
document.addEventListener('click',e=>{
 const t=e.target.closest('button');if(!t)return;
 if(t.dataset.stage){remember();current=t.dataset.stage;render();return}
 if(t.dataset.ticket)return download('/api/ticket?check_id='+encodeURIComponent(t.dataset.ticket));
 if(t.dataset.ticketStage)return download('/api/ticket?stage='+encodeURIComponent(t.dataset.ticketStage));
 if(t.dataset.signoff)return req('signoff',{stage:t.dataset.signoff});
 if(t.dataset.revoke)return req('revoke_signoff',{stage:t.dataset.revoke});
 if(t.hasAttribute('data-register'))return req('revision',{revision:value('revision-id'),evidence_files:paths('revision-files')});
 if(t.hasAttribute('data-baseline'))return req('baseline',{evidence:value('baseline-note'),evidence_files:paths('baseline-files')});
 if(t.hasAttribute('data-compare'))return showCompare();
 if(t.dataset.image)return showCompare(t.dataset.image);
 if(t.dataset.resolve){const id=t.dataset.resolve;return req('resolve',{issue_id:id,fixed_revision:value('v-'+id),resolution:value('r-'+id),evidence_files:paths('rf-'+id)})}
 if(t.dataset.action){const id=t.dataset.check;return req(t.dataset.action,{check_id:id,evidence:value('e-'+id),evidence_files:paths('f-'+id),issue:value('i-'+id),severity:value('p-'+id)})}
});
$('#inspect').addEventListener('click',()=>req('inspect'));
$('#export').addEventListener('click',()=>download('/api/export'));
$('#close-images').addEventListener('click',()=>$('#image-dialog').close());
$('#zoom').addEventListener('input',e=>document.querySelectorAll('.compare-pane img').forEach(im=>im.style.width=e.target.value+'%'));
let syncing=false;for(const [a,b]of [['left-pane','right-pane'],['right-pane','left-pane']])document.getElementById(a).addEventListener('scroll',()=>{if(syncing)return;syncing=true;const x=document.getElementById(a),y=document.getElementById(b);y.scrollTop=x.scrollTop;y.scrollLeft=x.scrollLeft;requestAnimationFrame(()=>syncing=false)});
window.addEventListener('beforeunload',()=>{if(payload)remember()});
load().catch(e=>toast(e.message,true));
