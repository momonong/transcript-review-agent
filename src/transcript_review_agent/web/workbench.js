'use strict';
let state=null,selectedId=null,busy=false,playbackEnd=null,pollTimer=null,loadInFlight=false;
const $=id=>document.getElementById(id);
const labels={pending:'待人工確認',needs_human_review:'仍需人工查核',accepted:'人工採用候選',rejected:'人工保留原稿',reverted:'已復原原稿'};
const actionLabels={accept:'採用候選',reject:'保留原稿',revert:'復原為原稿'};
const reasonLabels={not_checked:'尚未執行工具查核',candidate_differs:'工具候選與匯入初稿不同',no_difference_detected:'工具未發現文字差異，不表示內容正確',observed_candidate_selected:'代理選擇已觀察到的工具證據',policy_failure:'代理動作未通過驗證，交人工續查',policy_handoff:'代理選擇交由人工續查',policy_incomplete:'代理回覆未完整結束，交人工續查',tool_failure:'工具執行失敗，交人工續查',tool_reported_unresolved:'工具證據未解，交人工續查',tool_budget_exhausted:'工具預算已用盡，交人工續查',llm_budget_exhausted:'代理預算已用盡，交人工續查',total_time_exhausted:'本次時間預算已用盡，交人工續查',segment_action_budget_exhausted:'本段動作預算已用盡，交人工續查',unresolved_at_context_limit:'已達上下文上限，仍需人工查核'};
const time=value=>`${Math.floor(value/60).toString().padStart(2,'0')}:${(value%60).toFixed(2).padStart(5,'0')}`;
function element(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function tokens(text){return text.match(/[\p{Script=Han}]|[\p{L}\p{N}]+(?:['’][\p{L}]+)?|\s+|[^\s]/gu)||[];}
function renderDiff(original,candidate){
  const left=$('original-text'),right=$('candidate-text');left.replaceChildren();right.replaceChildren();
  if(candidate===null){left.textContent=original;right.textContent='沒有可直接採用的候選。請回聽原音並人工處理。';return;}
  const a=tokens(original),b=tokens(candidate);
  if(a.length>500||b.length>500){left.textContent=original;right.textContent=candidate;return;}
  const grid=Array.from({length:a.length+1},()=>new Uint16Array(b.length+1));
  for(let i=a.length-1;i>=0;i--)for(let j=b.length-1;j>=0;j--)grid[i][j]=a[i]===b[j]?grid[i+1][j+1]+1:Math.max(grid[i+1][j],grid[i][j+1]);
  let i=0,j=0;
  while(i<a.length||j<b.length){
    if(i<a.length&&j<b.length&&a[i]===b[j]){left.append(document.createTextNode(a[i]));right.append(document.createTextNode(b[j]));i++;j++;}
    else if(j<b.length&&(i===a.length||grid[i][j+1]>=grid[i+1][j])){right.append(element('mark',b[j++]));}
    else{left.append(element('del',a[i++]));}
  }
}
function selected(){return state?.review.items.find(item=>item.segment_id===selectedId)||state?.review.items[0];}
function statusText(item){return labels[item.status]||item.status;}
function setError(id,message){$(id).hidden=!message;$(id).textContent=message||'';}
function updateControls(){const item=selected(),running=state?.job?.status==='running';for(const id of ['accept','reject','revert'])$(id).disabled=busy||running||!state||!state.source.available||(!item)||(id==='accept'&&item.candidate_text===null);$('refresh').disabled=busy;$('play-segment').disabled=!state?.source.available;$('play-context').disabled=!state?.source.available;$('run-review').hidden=!state?.job?.configured;$('run-review').disabled=busy||running||!state?.source.available||Boolean(state?.review.decisions.length);$('run-review').className=state?.review.policy?.kind==='not_run'?'primary':'';$('run-review').textContent=running?'查核進行中…':state?.review.policy?.kind==='not_run'?'執行查核':'重新執行查核';}
function renderQueue(){
  const queue=$('queue');queue.replaceChildren();
  const pending=state.review.items.filter(item=>item.status==='pending').length;
  const needsHuman=state.review.items.filter(item=>item.status==='needs_human_review').length;
  $('pending-count').textContent=`${needsHuman} 需續查 / ${pending} 待確認`;
  state.review.items.forEach((item,index)=>{const button=element('button',undefined,'queue-item'+(item.segment_id===selectedId?' selected':''));button.type='button';button.setAttribute('aria-pressed',String(item.segment_id===selectedId));const title=element('span',undefined,'queue-title');title.append(element('span',`段落 ${index+1}`),element('span',statusText(item)));button.append(title,element('span',item.original_text,'queue-preview'),element('span',`${time(item.start)}–${time(item.end)}`,'queue-time'));button.addEventListener('click',()=>{$('audio').pause();playbackEnd=null;$('audio').currentTime=item.start;selectedId=item.segment_id;render();if(window.innerWidth<=720){queue.classList.remove('expanded');queue.classList.add('collapsed');$('queue-toggle').setAttribute('aria-expanded','false');$('main').scrollIntoView({block:'start'});}});queue.append(button);});
}
function addEvidence(label,value){const row=element('div');row.append(element('dt',label),element('dd',value));$('evidence-summary').append(row);}
function renderEvidence(item){
  const evidence=item.evidence||[],last=evidence[evidence.length-1];$('evidence-summary').replaceChildren();
  addEvidence('候選來源',last?.provenance==='real_local_model_inference'?'已執行的本機模型推論':last?.provenance==='fictional_fixture_not_model_output'?'離線虛構 fixture（非模型輸出）':'無可用工具證據');
  if(last?.model)addEvidence('語音模型',state.review.demo?.model_display_name||state.review.demo?.model_id||(last.tool==='transformers_whisper_cuda'?'Whisper（本機 GPU）':last.model));
  if(state.review.demo?.device_display_name)addEvidence('執行裝置',state.review.demo.device_display_name);
  else if(last?.device)addEvidence('執行裝置',last.device);
  if(state.review.policy?.kind==='llm_agent')addEvidence('動作決策模型',state.review.policy.model_id||'本機 LLM');
  addEvidence('本段工具呼叫',`${evidence.length} 次`);addEvidence('工具查核說明',reasonLabels[item.reason]||item.reason);
  if(last?.target_termination)addEvidence('解碼狀態',last.target_termination.complete?'已正常結束；不代表內容正確':'未完整結束，需人工處理');
  $('policy-name').textContent=state.review.policy?.kind==='fixed_baseline'?'固定查核流程':state.review.policy?.kind==='llm_agent'?'本機 LLM 動作代理':state.review.policy?.kind==='not_run'?'尚未執行查核':'—';
  const trace=(state.review.trace||[]).filter(event=>event.segment_id===item.segment_id);
  $('evidence-json').textContent=JSON.stringify({evidence,trace},null,2);
}
function renderHistory(item){
  const history=(state.review.decisions||[]).filter(event=>event.segment_id===item.segment_id);$('decision-count').textContent=`${history.length} 筆`;$('decision-history').replaceChildren();
  if(!history.length){$('decision-history').append(element('li',item.candidate_text===null?'尚無人工決策。此段沒有可直接採用的候選，請回聽原音。':'尚無人工決策。候選仍待確認，匯出保留原稿。','empty'));return;}
  history.slice().reverse().forEach(event=>{const row=element('li');row.append(element('strong',`${event.reviewer}：${actionLabels[event.action]||event.action}`),element('span',new Date(event.at).toLocaleString('zh-TW'),'history-meta'));if(event.note)row.append(element('p',event.note));$('decision-history').append(row);});
}
function render(){
  if(!state)return;const item=selected();selectedId=item.segment_id;
  $('review-name').textContent=state.name;$('source-name').textContent=`${state.source.name} / ${state.source.seconds.toFixed(3)} 秒`;
  const demo=state.review.demo;const real=item.evidence.some(row=>row.provenance==='real_local_model_inference');const fixture=item.evidence.some(row=>row.provenance==='fictional_fixture_not_model_output');
  $('provenance').textContent=state.job.status==='running'?'正在執行本次模型查核。下方保留上一份資料，完成後才以新結果更新。':state.review.policy?.kind==='not_run'?'已載入初稿與原音，尚未執行工具查核。未確認的匯出會保留原稿。':demo?.kind==='synthetic_verified_gpu_snapshot'?'合成語音示範，初稿含手動植入錯誤。讀取既有真實 GPU 結果；模型輸出原樣保留，本次未重新推論。':fixture?'目前使用離線虛構 fixture 證據測試查核流程，並非語音模型推論結果。':real?'已載入本機模型查核結果；候選仍待人工確認。':'已載入本機查核檔案；請確認來源及工具證據。';
  $('job-status').hidden=!['running','completed','error'].includes(state.job.status);$('working-indicator').hidden=state.job.status!=='running';$('job-message').textContent=state.job.message;setError('job-error',state.job.error);
  $('segment-time').textContent=`本段 ${time(item.start)}–${time(item.end)}`;
  $('segment-status').textContent=statusText(item);$('segment-status').className='status'+(['accepted','rejected','reverted'].includes(item.status)?' confirmed':'');
  $('save-status').textContent=state.revision?`已另存 ${state.revision} 次修訂`:'尚無新修訂';
  renderDiff(item.original_text,item.candidate_text);renderQueue();renderEvidence(item);renderHistory(item);updateControls();
  setError('audio-error',state.source.available?'':'來源檔案已變更或不可讀。請重新開啟並驗證來源，暫停播放與決策。');
}
function schedulePoll(delay=1000){
  if(pollTimer!==null){clearTimeout(pollTimer);pollTimer=null;}
  if(state?.job?.status==='running')pollTimer=setTimeout(()=>{pollTimer=null;load({poll:true});},delay);
}
async function load(options={}){
  if(loadInFlight||busy){if(options.poll===true)schedulePoll();return;}
  if(pollTimer!==null){clearTimeout(pollTimer);pollTimer=null;}
  loadInFlight=true;busy=true;let failed=false;updateControls();
  try{
    const response=await fetch('/api/state',{cache:'no-store'});const data=await response.json();
    if(!response.ok)throw Error(data.error||'無法讀取查核狀態');
    if(state&&data.mutation_token===state.mutation_token&&data.revision<state.revision)return;
    state=data;
    if(!selectedId||!state.review.items.some(item=>item.segment_id===selectedId)){
      const preferred=state.review.demo?.default_segment_id;
      selectedId=state.review.items.some(item=>item.segment_id===preferred)?preferred:state.review.items[0].segment_id;
    }
    setError('decision-error','');render();
  }catch(error){
    failed=true;setError('decision-error',state?`更新暫時失敗，保留上次結果並重試：${error.message}`:`載入失敗：${error.message}`);
    if(!state)$('review-name').textContent='查核檔案尚未載入';
  }finally{loadInFlight=false;busy=false;updateControls();schedulePoll(failed?1500:1000);}
}
async function decision(action){
  if(busy||!state)return;busy=true;updateControls();setError('decision-error','');$('decision-message').textContent='正在另存新修訂…';
  try{const response=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':state.mutation_token},body:JSON.stringify({segment_id:selectedId,action,reviewer:$('reviewer').value,note:$('decision-note').value,revision:state.revision})});const data=await response.json();if(!response.ok)throw Error(data.error||'無法保存決策');state=data;$('decision-note').value='';$('decision-message').textContent='已保存新修訂，原稿未覆寫';render();}catch(error){setError('decision-error',error.message);$('decision-message').textContent='決策尚未保存';}finally{busy=false;updateControls();}}
async function startReview(){if(busy||!state)return;busy=true;updateControls();setError('decision-error','');try{const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':state.mutation_token},body:JSON.stringify({revision:state.revision})});const data=await response.json();if(!response.ok)throw Error(data.error||'無法開始查核');state=data;render();}catch(error){setError('decision-error',error.message);}finally{busy=false;updateControls();schedulePoll();}}
function play(context){const item=selected();if(!item)return;const audio=$('audio');playbackEnd=Math.min(state.source.seconds,item.end+context);audio.currentTime=Math.max(0,item.start-context);audio.play().catch(error=>setError('audio-error',`播放失敗：${error.message}`));}
$('audio').addEventListener('timeupdate',()=>{if(playbackEnd!==null&&$('audio').currentTime>=playbackEnd){$('audio').pause();playbackEnd=null;}});
$('audio').addEventListener('error',()=>{if(state)setError('audio-error','無法播放原音。請確認來源未變更且瀏覽器支援此格式。');});
$('play-segment').addEventListener('click',()=>play(0));$('play-context').addEventListener('click',()=>play(1.5));$('refresh').addEventListener('click',load);
$('run-review').addEventListener('click',startReview);
for(const action of ['accept','reject','revert'])$(action).addEventListener('click',()=>decision(action));
$('queue-toggle').addEventListener('click',()=>{if(window.innerWidth>720)return;const expanded=$('queue').classList.toggle('expanded');$('queue').classList.toggle('collapsed',!expanded);$('queue-toggle').setAttribute('aria-expanded',String(expanded));});
load();
