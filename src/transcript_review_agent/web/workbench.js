'use strict';
let state=null,selectedId=null,busy=false,playbackEnd=null,pollTimer=null,loadInFlight=false;
const $=id=>document.getElementById(id);
// Interface copy only. Imported text, hypotheses and raw evidence are never translated.
const strings={
  home:['Transcript Review Agent home','Transcript Review Agent 首頁'],
  scope:['Local review workbench','本機查核工作台'],localOnly:['Local connection only','僅本機連線'],
  language:['Language','語言'],languageLabel:['Interface language','介面語言'],
  queueHeading:['Review queue','待查核段落'],queueLabel:['Transcript segments','段落清單'],
  originalRetained:['The original stays intact','原稿始終保留'],
  originalNote:['Unflagged does not mean correct. A person must confirm a candidate before it appears in exported text.','未標記不代表正確。工具候選需經人工決定，才能成為匯出文字。'],
  title:['Transcript review','逐字稿查核'],pageTitle:['Transcript Review Agent','逐字稿查核｜Transcript Review Agent'],
  refresh:['Reload','重新載入'],loadingReview:['Loading review…','載入查核檔案…'],
  loadingState:['Reading local data and review status…','讀取本機資料與查核狀態…'],loading:['Loading…','載入中…'],
  sourceTitle:['Source audio','原音與段落位置'],audioUnsupported:['Your browser does not support audio playback.','此瀏覽器不支援音訊播放。'],
  playSegment:['Play segment','回聽這一段'],playContext:['Play with context','含前後文回聽'],
  compareTitle:['Original and candidate','原稿與候選'],importedDraft:['Imported draft','匯入初稿'],toolCandidate:['Tool candidate','工具候選'],verbatim:['Preserved verbatim','原樣保留'],
  diffKey:['Additions are highlighted; deletions are struck through. Script, repetitions, negation and numbers are never normalized.','新增以底色標示，刪除以刪線標示；繁簡、重複、否定及數字不自動改寫。'],
  decisionTitle:['Human decision','人工決策'],reviewer:['Reviewer','查核者'],defaultReviewer:['Local reviewer','本機查核者'],
  decisionNote:['Decision note','決策備註'],optional:['Optional','選填'],notePlaceholder:['Why accept the candidate or keep the original?','記錄採用或保留原稿的原因'],
  accept:['Accept candidate','採用候選'],reject:['Keep original','保留原稿'],revert:['Revert to original','復原為原稿'],
  evidenceTitle:['Review evidence','查核依據'],rawTrace:['Raw tool evidence and action trace','工具 evidence 與 action trace'],historyTitle:['Decision history','決策紀錄'],
  exportTitle:['Export with provenance','匯出可追溯資料'],
  exportNote:['Unconfirmed, retained or reverted segments export the original text. The audit includes all tool evidence and decisions.','未確認、保留或復原的段落，匯出仍使用原稿。audit 包含完整工具與決策紀錄。'],
  downloadTxt:['Transcript TXT','逐字稿 TXT'],downloadJson:['Transcript JSON','逐字稿 JSON'],downloadAudit:['Full audit','完整 audit'],
  noCandidate:['No directly acceptable candidate. Listen to the source and review this segment manually.','沒有可直接採用的候選。請回聽原音並人工處理。'],
  runReview:['Run review','執行查核'],rerunReview:['Run review again','重新執行查核'],runningReview:['Review running…','查核進行中…'],
  queueCounts:['{human} need review / {pending} pending','{human} 需續查 / {pending} 待確認'],segment:['Segment {n}','段落 {n}'],
  segmentTime:['Segment {start}–{end}','本段 {start}–{end}'],sourceDuration:['{name} / {seconds} s','{name} / {seconds} 秒'],
  candidateSource:['Candidate source','候選來源'],realInference:['Recorded local model inference','已執行的本機模型推論'],
  fictionalEvidence:['Fictional offline fixture (not model output)','離線虛構 fixture（非模型輸出）'],noEvidence:['No available tool evidence','無可用工具證據'],
  speechModel:['Speech model','語音模型'],localWhisper:['Whisper (local GPU)','Whisper（本機 GPU）'],device:['Execution device','執行裝置'],
  actionModel:['Action policy model','動作決策模型'],localLlm:['Local LLM','本機 LLM'],toolCalls:['Segment tool calls','本段工具呼叫'],calls:['{n} calls','{n} 次'],oneCall:['1 call','1 次'],
  reviewReason:['Review reason','工具查核說明'],decodeStatus:['Decoding status','解碼狀態'],
  decodeComplete:['Completed normally; correctness is unverified','已正常結束；不代表內容正確'],decodeIncomplete:['Incomplete; human review required','未完整結束，需人工處理'],
  fixedPolicy:['Fixed review process','固定查核流程'],agentPolicy:['Local LLM action agent','本機 LLM 動作代理'],notRunPolicy:['Review not yet run','尚未執行查核'],
  decisionCount:['{n} decisions','{n} 筆'],oneDecision:['1 decision','1 筆'],
  noDecisionCandidate:['No human decision yet. This candidate is unconfirmed; exports retain the original.','尚無人工決策。候選仍待確認，匯出保留原稿。'],
  noDecisionHandoff:['No human decision yet. No directly acceptable candidate; listen to the source.','尚無人工決策。此段沒有可直接採用的候選，請回聽原音。'],
  historyAction:['{reviewer}: {action}','{reviewer}：{action}'],
  runningNotice:['A model review is running. The previous result stays visible until new results are ready.','正在執行本次模型查核。下方保留上一份資料，完成後才以新結果更新。'],
  notRunNotice:['Draft and audio loaded; tool review has not run. Unconfirmed exports retain the original.','已載入初稿與原音，尚未執行工具查核。未確認的匯出會保留原稿。'],
  demoName:['Chinese synthetic demo: LLM tool review','中文合成示範：LLM 工具查核'],
  demoNotice:['Chinese synthetic speech with manually seeded draft errors. Recorded GPU results are shown verbatim; no inference runs when opened.','合成語音示範，初稿含手動植入錯誤。讀取既有真實 GPU 結果；模型輸出原樣保留，本次未重新推論。'],
  fixtureNotice:['This review uses fictional offline fixture evidence, not speech-model output.','目前使用離線虛構 fixture 證據測試查核流程，並非語音模型推論結果。'],
  realNotice:['Recorded local model results loaded; candidates still require human confirmation.','已載入本機模型查核結果；候選仍待人工確認。'],
  genericNotice:['Local review loaded. Check the source and tool evidence.','已載入本機查核檔案；請確認來源及工具證據。'],
  revisions:['{n} new revisions saved','已另存 {n} 次修訂'],oneRevision:['1 new revision saved','已另存 1 次修訂'],noRevisions:['No new revisions','尚無新修訂'],
  sourceUnavailable:['The source has changed or cannot be read. Reopen and verify it before playback or decisions.','來源檔案已變更或不可讀。請重新開啟並驗證來源，暫停播放與決策。'],
  readFailed:['Unable to read review status','無法讀取查核狀態'],saveFailed:['Unable to save the decision','無法保存決策'],startFailed:['Unable to start review','無法開始查核'],
  refreshFailed:['Refresh temporarily failed. Keeping the previous result and retrying: {detail}','更新暫時失敗，保留上次結果並重試：{detail}'],
  loadFailed:['Load failed: {detail}','載入失敗：{detail}'],notLoaded:['Review not loaded','查核檔案尚未載入'],
  saving:['Saving a new revision…','正在另存新修訂…'],saved:['New revision saved; original unchanged','已保存新修訂，原稿未覆寫'],notSaved:['Decision not saved','決策尚未保存'],
  playbackFailed:['Playback failed: {detail}','播放失敗：{detail}'],audioFailed:['Unable to play the source. Check that it has not changed and the browser supports this format.','無法播放原音。請確認來源未變更且瀏覽器支援此格式。'],
  'status.pending':['Awaiting confirmation','待人工確認'],'status.needs_human_review':['Needs human review','仍需人工查核'],
  'status.accepted':['Candidate accepted','人工採用候選'],'status.rejected':['Original retained','人工保留原稿'],'status.reverted':['Original restored','已復原原稿'],
  'reason.not_checked':['Tool review has not run','尚未執行工具查核'],
  'reason.candidate_differs':['Tool candidate differs from the imported draft','工具候選與匯入初稿不同'],
  'reason.no_difference_detected':['No text difference detected; correctness is unverified','工具未發現文字差異，不表示內容正確'],
  'reason.observed_candidate_selected':['Agent selected observed tool evidence','代理選擇已觀察到的工具證據'],
  'reason.policy_failure':['Agent action failed validation; handed to a person','代理動作未通過驗證，交人工續查'],
  'reason.policy_handoff':['Agent handed this segment to a person','代理選擇交由人工續查'],
  'reason.policy_incomplete':['Agent response did not finish; handed to a person','代理回覆未完整結束，交人工續查'],
  'reason.tool_failure':['Tool failed; handed to a person','工具執行失敗，交人工續查'],
  'reason.tool_reported_unresolved':['Tool evidence is unresolved; handed to a person','工具證據未解，交人工續查'],
  'reason.tool_budget_exhausted':['Tool budget exhausted; handed to a person','工具預算已用盡，交人工續查'],
  'reason.llm_budget_exhausted':['Agent budget exhausted; handed to a person','代理預算已用盡，交人工續查'],
  'reason.total_time_exhausted':['Time budget exhausted; handed to a person','本次時間預算已用盡，交人工續查'],
  'reason.segment_action_budget_exhausted':['Segment action budget exhausted; handed to a person','本段動作預算已用盡，交人工續查'],
  'reason.unresolved_at_context_limit':['Context limit reached; human review required','已達上下文上限，仍需人工查核']
};
// Keep the server contract. Match exact known copy; unexpected diagnostics remain verbatim.
const serverMessages={
  '顯示既有查核結果，未啟動新模型工作':'Showing an existing review; no new model job started',
  '模型已設定，尚未執行本次查核':'Models configured; this review has not run',
  '正在載入本機模型並執行查核；畫面保留上一份結果':'Loading local models and reviewing; the previous result stays visible',
  '本次查核流程結束，請人工檢視候選與未解項目':'Review process finished. Inspect candidates and unresolved segments',
  '本次查核失敗，上一份資料與決策保持不變':'Review failed; previous data and decisions are unchanged',
  '原始媒體內容已變更，請重新驗證後開啟':'Source content changed. Verify it before reopening',
  '原始媒體無法驗證，請重新開啟':'Unable to verify source media. Reopen the review',
  '原始媒體已變更，停止播放':'Source media changed; playback stopped',
  '原始媒體超過大小上限':'Source media exceeds the size limit',
  '原始媒體無法驗證，停止播放':'Unable to verify source media; playback stopped',
  '原始媒體內容已變更，停止播放以保護查核依據':'Source content changed; playback stopped to preserve review evidence',
  '原始媒體已變更，停止播放以保護查核依據':'Source media changed; playback stopped to preserve review evidence',
  '查核工作正在執行':'A review job is running',
  '尚未在本機 CLI 設定查核模型':'Configure review models through the local CLI first',
  '已有查核工作正在執行':'A review job is already running',
  '畫面已有較新修訂，請重新載入':'A newer revision exists. Reload the page',
  '此工作階段已有人工決策，請另開輸入以保留完整歷史':'This session has human decisions. Open a new input to preserve its history',
  '查核結果與本次輸入不一致':'Review result does not match this input',
  '查核期間修訂已變更':'The revision changed while review was running',
  '查核工作執行中，請等待結果再決定':'Wait for the running review before making a decision',
  '畫面已有較新修訂，請重新載入後再決定':'A newer revision exists. Reload before making a decision',
  '不允許的 Host':'Host is not allowed','不允許的 Origin':'Origin is not allowed','拒絕跨站請求':'Cross-site request rejected',
  '變更 token 無效，請重新載入':'Invalid mutation token. Reload the page','不支援的請求路徑':'Unsupported request path',
  '找不到此路由':'Route not found','找不到此變更路由':'Mutation route not found',
  '必須提供受限的 Content-Length':'A bounded Content-Length is required','變更內容超過大小上限':'Mutation body exceeds the size limit',
  '變更內容必須為 JSON':'Mutation body must be JSON','修訂寫入失敗；尚未變更目前決策':'Revision could not be written; current decisions are unchanged'
};
const languageKey='transcript-review-language';
function savedLanguage(){try{return window.localStorage.getItem(languageKey)==='zh-Hant'?'zh-Hant':'en';}catch{return 'en';}}
let language=savedLanguage();
const messages=new Map();
function t(key,values={}){return (strings[key]?.[language==='en'?0:1]||key).replace(/\{(\w+)\}/g,(_,name)=>String(values[name]??''));}
function codeLabel(prefix,code){return strings[`${prefix}.${code}`]?t(`${prefix}.${code}`):code;}
function serverText(message){return language==='en'?(serverMessages[message]||message):message;}
function number(value,decimals=0){return new Intl.NumberFormat(language==='en'?'en-US':'zh-TW',{minimumFractionDigits:decimals,maximumFractionDigits:decimals}).format(value);}
const time=value=>`${Math.floor(value/60).toString().padStart(2,'0')}:${number(value%60,2).padStart(5,'0')}`;
function showMessage(id,key=null,values={}){if(key)messages.set(id,{key,values});else messages.delete(id);renderMessage(id);}
function showError(id,raw){if(raw)messages.set(id,{raw});else messages.delete(id);renderMessage(id);}
function renderMessage(id){const message=messages.get(id);const text=message?.raw?serverText(message.raw):message?t(message.key,{...message.values,detail:serverText(message.values.detail)}):'';$(id).hidden=!text;$(id).textContent=text;}
function applyLanguage(){
  document.documentElement.lang=language;document.title=t('pageTitle');$('language').value=language;
  for(const node of document.querySelectorAll('[data-i18n]'))node.textContent=t(node.dataset.i18n);
  for(const attribute of ['placeholder','aria-label'])for(const node of document.querySelectorAll(`[data-i18n-${attribute}]`))node.setAttribute(attribute,t(node.getAttribute(`data-i18n-${attribute}`)));
  if(state)render();else{for(const [id,key] of [['review-name',messages.get('decision-error')?.key==='loadFailed'?'notLoaded':'loadingReview'],['provenance','loadingState'],['original-text','loading'],['candidate-text','loading'],['segment-status','loading'],['save-status','noRevisions']])$(id).textContent=t(key);$('decision-count').textContent=t('decisionCount',{n:number(0)});}
  for(const id of messages.keys())renderMessage(id);
}
function changeLanguage(next){if(!['en','zh-Hant'].includes(next))return;language=next;try{window.localStorage.setItem(languageKey,language);}catch{/* Optional preference: the workbench also works without storage. */}applyLanguage();}
function element(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function tokens(text){return text.match(/[\p{Script=Han}]|[\p{L}\p{N}]+(?:['’][\p{L}]+)?|\s+|[^\s]/gu)||[];}
function renderDiff(original,candidate){
  const left=$('original-text'),right=$('candidate-text');left.replaceChildren();right.replaceChildren();
  if(candidate===null){left.textContent=original;right.textContent=t('noCandidate');return;}
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
function statusText(item){return codeLabel('status',item.status);}
function updateControls(){const item=selected(),running=state?.job?.status==='running';for(const id of ['accept','reject','revert'])$(id).disabled=busy||running||!state||!state.source.available||!item||(id==='accept'&&item.candidate_text===null);$('refresh').disabled=busy;$('play-segment').disabled=!state?.source.available;$('play-context').disabled=!state?.source.available;$('run-review').hidden=!state?.job?.configured;$('run-review').disabled=busy||running||!state?.source.available||Boolean(state?.review.decisions.length);$('run-review').className=state?.review.policy?.kind==='not_run'?'primary':'';$('run-review').textContent=t(running?'runningReview':state?.review.policy?.kind==='not_run'?'runReview':'rerunReview');}
function renderQueue(){
  const queue=$('queue');queue.replaceChildren();
  const pending=state.review.items.filter(item=>item.status==='pending').length;
  const needsHuman=state.review.items.filter(item=>item.status==='needs_human_review').length;
  $('pending-count').textContent=t('queueCounts',{human:number(needsHuman),pending:number(pending)});
  state.review.items.forEach((item,index)=>{const button=element('button',undefined,'queue-item'+(item.segment_id===selectedId?' selected':''));button.type='button';button.setAttribute('aria-pressed',String(item.segment_id===selectedId));const title=element('span',undefined,'queue-title');title.append(element('span',t('segment',{n:number(index+1)})),element('span',statusText(item)));button.append(title,element('span',item.original_text,'queue-preview'),element('span',`${time(item.start)}–${time(item.end)}`,'queue-time'));button.addEventListener('click',()=>{$('audio').pause();playbackEnd=null;$('audio').currentTime=item.start;selectedId=item.segment_id;render();if(window.innerWidth<=720){queue.classList.remove('expanded');queue.classList.add('collapsed');$('queue-toggle').setAttribute('aria-expanded','false');$('main').scrollIntoView({block:'start'});}});queue.append(button);});
}
function addEvidence(label,value){const row=element('div');row.append(element('dt',label),element('dd',value));$('evidence-summary').append(row);}
function renderEvidence(item){
  const evidence=item.evidence||[],last=evidence[evidence.length-1];$('evidence-summary').replaceChildren();
  addEvidence(t('candidateSource'),t(last?.provenance==='real_local_model_inference'?'realInference':last?.provenance==='fictional_fixture_not_model_output'?'fictionalEvidence':'noEvidence'));
  if(last?.model)addEvidence(t('speechModel'),state.review.demo?.model_display_name||state.review.demo?.model_id||(last.tool==='transformers_whisper_cuda'?t('localWhisper'):last.model));
  if(state.review.demo?.device_display_name)addEvidence(t('device'),state.review.demo.device_display_name);
  else if(last?.device)addEvidence(t('device'),last.device);
  if(state.review.policy?.kind==='llm_agent')addEvidence(t('actionModel'),state.review.policy.model_id||t('localLlm'));
  addEvidence(t('toolCalls'),t(evidence.length===1?'oneCall':'calls',{n:number(evidence.length)}));addEvidence(t('reviewReason'),codeLabel('reason',item.reason));
  if(last?.target_termination)addEvidence(t('decodeStatus'),t(last.target_termination.complete?'decodeComplete':'decodeIncomplete'));
  $('policy-name').textContent=state.review.policy?.kind==='fixed_baseline'?t('fixedPolicy'):state.review.policy?.kind==='llm_agent'?t('agentPolicy'):state.review.policy?.kind==='not_run'?t('notRunPolicy'):'—';
  const trace=(state.review.trace||[]).filter(event=>event.segment_id===item.segment_id);
  $('evidence-json').textContent=JSON.stringify({evidence,trace},null,2);
}
function renderHistory(item){
  const history=(state.review.decisions||[]).filter(event=>event.segment_id===item.segment_id);$('decision-count').textContent=t(history.length===1?'oneDecision':'decisionCount',{n:number(history.length)});$('decision-history').replaceChildren();
  if(!history.length){$('decision-history').append(element('li',t(item.candidate_text===null?'noDecisionHandoff':'noDecisionCandidate'),'empty'));return;}
  history.slice().reverse().forEach(event=>{const row=element('li');row.append(element('strong',t('historyAction',{reviewer:event.reviewer,action:strings[event.action]?t(event.action):event.action})),element('span',new Date(event.at).toLocaleString(language==='en'?'en-US':'zh-TW'),'history-meta'));if(event.note)row.append(element('p',event.note));$('decision-history').append(row);});
}
function render(){
  if(!state)return;const item=selected();selectedId=item.segment_id;
  const demo=state.review.demo;const real=item.evidence.some(row=>row.provenance==='real_local_model_inference');const fixture=item.evidence.some(row=>row.provenance==='fictional_fixture_not_model_output');
  $('review-name').textContent=demo?.kind==='synthetic_verified_gpu_snapshot'?t('demoName'):state.name;$('source-name').textContent=t('sourceDuration',{name:state.source.name,seconds:number(state.source.seconds,3)});
  $('provenance').textContent=t(state.job.status==='running'?'runningNotice':state.review.policy?.kind==='not_run'?'notRunNotice':demo?.kind==='synthetic_verified_gpu_snapshot'?'demoNotice':fixture?'fixtureNotice':real?'realNotice':'genericNotice');
  $('job-status').hidden=!['running','completed','error'].includes(state.job.status);$('working-indicator').hidden=state.job.status!=='running';$('job-message').textContent=serverText(state.job.message);showError('job-error',state.job.error);
  $('segment-time').textContent=t('segmentTime',{start:time(item.start),end:time(item.end)});
  $('segment-status').textContent=statusText(item);$('segment-status').className='status'+(['accepted','rejected','reverted'].includes(item.status)?' confirmed':'');
  $('save-status').textContent=t(state.revision===1?'oneRevision':state.revision?'revisions':'noRevisions',{n:number(state.revision)});
  renderDiff(item.original_text,item.candidate_text);renderQueue();renderEvidence(item);renderHistory(item);updateControls();
  if(!state.source.available)showMessage('audio-error','sourceUnavailable');else if(messages.get('audio-error')?.key==='sourceUnavailable')showMessage('audio-error');
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
    if(!response.ok)throw Error(data.error||t('readFailed'));
    if(state&&data.mutation_token===state.mutation_token&&data.revision<state.revision)return;
    state=data;
    if(!selectedId||!state.review.items.some(item=>item.segment_id===selectedId)){
      const preferred=state.review.demo?.default_segment_id;
      selectedId=state.review.items.some(item=>item.segment_id===preferred)?preferred:state.review.items[0].segment_id;
    }
    showError('decision-error','');render();
  }catch(error){
    failed=true;showMessage('decision-error',state?'refreshFailed':'loadFailed',{detail:error.message});
    if(!state)$('review-name').textContent=t('notLoaded');
  }finally{loadInFlight=false;busy=false;updateControls();schedulePoll(failed?1500:1000);}
}
async function decision(action){
  if(busy||!state)return;busy=true;updateControls();showError('decision-error','');showMessage('decision-message','saving');
  try{const response=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':state.mutation_token},body:JSON.stringify({segment_id:selectedId,action,reviewer:$('reviewer').value,note:$('decision-note').value,revision:state.revision})});const data=await response.json();if(!response.ok)throw Error(data.error||t('saveFailed'));state=data;$('decision-note').value='';showMessage('decision-message','saved');render();}catch(error){showError('decision-error',error.message);showMessage('decision-message','notSaved');}finally{busy=false;updateControls();}
}
async function startReview(){if(busy||!state)return;busy=true;updateControls();showError('decision-error','');try{const response=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':state.mutation_token},body:JSON.stringify({revision:state.revision})});const data=await response.json();if(!response.ok)throw Error(data.error||t('startFailed'));state=data;render();}catch(error){showError('decision-error',error.message);}finally{busy=false;updateControls();schedulePoll();}}
function play(context){const item=selected();if(!item)return;const audio=$('audio');playbackEnd=Math.min(state.source.seconds,item.end+context);audio.currentTime=Math.max(0,item.start-context);audio.play().catch(error=>showMessage('audio-error','playbackFailed',{detail:error.message}));}
$('audio').addEventListener('timeupdate',()=>{if(playbackEnd!==null&&$('audio').currentTime>=playbackEnd){$('audio').pause();playbackEnd=null;}});
$('audio').addEventListener('error',()=>{if(state)showMessage('audio-error','audioFailed');});
$('play-segment').addEventListener('click',()=>play(0));$('play-context').addEventListener('click',()=>play(1.5));$('refresh').addEventListener('click',load);
$('run-review').addEventListener('click',startReview);
for(const action of ['accept','reject','revert'])$(action).addEventListener('click',()=>decision(action));
$('queue-toggle').addEventListener('click',()=>{if(window.innerWidth>720)return;const expanded=$('queue').classList.toggle('expanded');$('queue').classList.toggle('collapsed',!expanded);$('queue-toggle').setAttribute('aria-expanded',String(expanded));});
$('language').addEventListener('change',event=>changeLanguage(event.target.value));
applyLanguage();$('reviewer').value=t('defaultReviewer');load();
