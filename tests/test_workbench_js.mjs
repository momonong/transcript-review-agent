// Browser-independent regressions against the real workbench source and HTML copy hooks.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor(){this.children=[];this.text='';this.hidden=false;this.disabled=false;this.value='';this.className='';this.attributes={};this.dataset={};this.events=new Map();this.currentTime=0;this.paused=true;this.classList={add(){},remove(){},toggle(){return true;}};}
  get textContent(){return this.text+this.children.map(node=>node.textContent).join('');}
  set textContent(value){this.text=String(value);this.children=[];}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.text='';this.children=nodes;}
  setAttribute(key,value){this.attributes[key]=String(value);}
  getAttribute(key){return this.attributes[key];}
  addEventListener(type,callback){this.events.set(type,callback);}
  dispatch(type){return this.events.get(type)?.({target:this});}
  pause(){this.paused=true;}
  play(){this.paused=false;return Promise.resolve();}
  scrollIntoView(){}
}
const source=fs.readFileSync(new URL('../src/transcript_review_agent/web/workbench.js',import.meta.url),'utf8');
const html=fs.readFileSync(new URL('../src/transcript_review_agent/web/index.html',import.meta.url),'utf8');
const snapshot=status=>({name:'review remains visible',mutation_token:'token',revision:status==='completed'?1:0,source:{name:'source.wav',seconds:30,available:true},job:{status,configured:true,message:'正在載入本機模型並執行查核；畫面保留上一份結果',error:null},review:{policy:{kind:'fixed_baseline'},items:[{segment_id:'s1',start:0,end:10,original_text:'我拿了十五份。明天需要再準備。',candidate_text:'我、我沒有拿十五份。明天不需要再準備。',status:'pending',reason:'candidate_differs',evidence:[{provenance:'real_local_model_inference',raw:'原樣 evidence 15 / 50',target_termination:{complete:true}}]},{segment_id:'s2',start:10,end:20,original_text:'先確認時間。最後再寄出通知。',candidate_text:null,status:'needs_human_review',reason:'policy_failure',evidence:[]}],trace:[{segment_id:'s1',raw:'未正規化的 trace 中文'}],decisions:[]}});
function harness(responses,{saved=null,storageThrows=false}={}){
  const elements=new Map(),copyNodes=[];let fetches=0,nextTimer=0;const timers=new Map(),stored=new Map(saved?[['transcript-review-language',saved]]:[]);
  const document={documentElement:{lang:'en'},title:'',getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();},createTextNode(text){const node=new Element();node.textContent=text;return node;},querySelectorAll(selector){return copyNodes.filter(node=>node.attributes[selector.slice(1,-1)]!==undefined);}};
  for(const match of html.matchAll(/<[^>]+\bdata-i18n(?:-placeholder|-aria-label)?="[^"]+"[^>]*>/g)){
    const id=match[0].match(/\bid="([^"]+)"/)?.[1];const node=id?document.getElementById(id):new Element();
    for(const attribute of match[0].matchAll(/(data-i18n(?:-placeholder|-aria-label)?)="([^"]+)"/g)){node.setAttribute(attribute[1],attribute[2]);if(attribute[1]==='data-i18n')node.dataset.i18n=attribute[2];}copyNodes.push(node);
  }
  const storage={getItem(key){if(storageThrows)throw Error('storage blocked');return stored.get(key)??null;},setItem(key,value){if(storageThrows)throw Error('storage blocked');stored.set(key,value);}};
  const context=vm.createContext({document,window:{innerWidth:1440,localStorage:storage},console,
    fetch:async()=>{let result=responses[fetches++];if(typeof result==='function')result=await result();if(result instanceof Error)throw result;return result?.response||{ok:true,json:async()=>result};},
    setTimeout:callback=>{const id=++nextTimer;timers.set(id,callback);return id;},clearTimeout:id=>timers.delete(id)});
  vm.runInContext(source,context);
  return{context,elements,document,copyNodes,timers,stored,get fetches(){return fetches;},run:script=>vm.runInContext(script,context),language(value){const node=elements.get('language');node.value=value;node.dispatch('change');}};
}
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
const tick=async app=>{assert.equal(app.timers.size,1,'one controlled poll is scheduled');const [id,callback]=app.timers.entries().next().value;app.timers.delete(id);callback();await settle();};

const poll=harness([snapshot('running'),new Error('temporary network failure'),snapshot('completed')]);
await settle();assert.equal(poll.timers.size,1);
await tick(poll);
assert.equal(poll.timers.size,1,'a failed GET must schedule one recovery poll');
assert.equal(poll.elements.get('review-name').textContent,'review remains visible');
assert.equal(poll.elements.get('decision-error').hidden,false);
poll.language('zh-Hant');
assert.match(poll.elements.get('decision-error').textContent,/更新暫時失敗/);
assert.match(poll.elements.get('decision-error').textContent,/temporary network failure/,'unexpected diagnostics remain intact');
assert.equal(poll.elements.get('run-review').textContent,'查核進行中…');
assert.equal(poll.elements.get('accept').disabled,true,'switching cannot enable decisions during a running job');
assert.equal(poll.timers.size,1,'language switch does not duplicate polling');
await tick(poll);
assert.equal(poll.fetches,3);assert.equal(poll.timers.size,0,'completed jobs stop polling');
assert.equal(poll.elements.get('accept').disabled,false);
console.log('PASS: transient polling failure recovers, keeps prior data, and never duplicates timers');

const initial=snapshot('completed');initial.revision=0;
const app=harness([initial]);await settle();
const get=id=>app.elements.get(id);
assert.equal(app.document.documentElement.lang,'en');
for(const node of app.copyNodes)for(const attribute of ['data-i18n','data-i18n-placeholder','data-i18n-aria-label']){const key=node.getAttribute(attribute);if(key)assert.notEqual(app.run(`t(${JSON.stringify(key)})`),key,`English copy exists for ${key}`);}
assert.equal(app.copyNodes.find(node=>node.dataset.i18n==='title').textContent,'Transcript review');
assert.equal(get('accept').textContent,'Accept candidate');
assert.equal(get('decision-note').getAttribute('placeholder'),'Why accept the candidate or keep the original?');
assert.equal(get('language').getAttribute('aria-label'),'Interface language');
assert.equal(get('pending-count').textContent,'1 need review / 1 pending');
assert.equal(get('segment-status').textContent,'Awaiting confirmation');
assert.match(get('job-message').textContent,/Loading local models/,'known server copy is localized');
assert.match(get('evidence-summary').textContent,/Candidate source/);
assert.match(get('evidence-summary').textContent,/Tool candidate differs/);
assert.match(get('evidence-summary').textContent,/1 call(?!s)/);
const rawBefore=get('evidence-json').textContent;
assert.equal(get('original-text').textContent,initial.review.items[0].original_text);
assert.equal(get('candidate-text').textContent,initial.review.items[0].candidate_text);
get('reviewer').value='陳 reviewer';get('decision-note').value='保留 not / 15 與 50';
get('play-segment').dispatch('click');get('audio').currentTime=4.25;
const playbackEnd=app.run('playbackEnd');
app.language('zh-Hant');
assert.equal(app.document.documentElement.lang,'zh-Hant');assert.equal(get('accept').textContent,'採用候選');
for(const node of app.copyNodes)for(const attribute of ['data-i18n','data-i18n-placeholder','data-i18n-aria-label']){const key=node.getAttribute(attribute);if(key)assert.notEqual(app.run(`t(${JSON.stringify(key)})`),key,`Chinese copy exists for ${key}`);}
assert.equal(get('decision-note').getAttribute('placeholder'),'記錄採用或保留原稿的原因');
assert.equal(get('language').getAttribute('aria-label'),'介面語言');
assert.equal(get('pending-count').textContent,'1 需續查 / 1 待確認');
assert.equal(get('segment-status').textContent,'待人工確認');
assert.equal(get('reviewer').value,'陳 reviewer');assert.equal(get('decision-note').value,'保留 not / 15 與 50');
assert.equal(get('audio').currentTime,4.25);assert.equal(get('audio').paused,false);assert.equal(app.run('playbackEnd'),playbackEnd);
assert.equal(app.run('selectedId'),'s1');assert.equal(app.run('state.review.items[0].status'),'pending');
assert.equal(get('original-text').textContent,initial.review.items[0].original_text);assert.equal(get('candidate-text').textContent,initial.review.items[0].candidate_text);assert.equal(get('evidence-json').textContent,rawBefore);
assert.equal(app.stored.get('transcript-review-language'),'zh-Hant');
get('queue').children[1].dispatch('click');assert.equal(app.run('selectedId'),'s2');
assert.equal(get('segment-status').textContent,'仍需人工查核');assert.match(get('candidate-text').textContent,/沒有可直接採用/);
app.language('en');assert.equal(app.run('selectedId'),'s2');assert.match(get('candidate-text').textContent,/No directly acceptable candidate/);assert.equal(get('accept').disabled,true);
assert.equal(get('reviewer').value,'陳 reviewer');assert.equal(get('decision-note').value,'保留 not / 15 與 50');
assert.equal(app.run('serverText("Unexpected runtime 診斷")'),'Unexpected runtime 診斷');
console.log('PASS: English default, Chinese switch, dynamic copy, exact transcripts, inputs, selection and playback preservation');

app.run("state.review.decisions=[{segment_id:'s2',action:'reject',reviewer:'陳 reviewer',note:'原始 note 中文',at:'2026-10-29T03:04:05Z'}];render()");
assert.equal(get('decision-count').textContent,'1 decision');assert.match(get('decision-history').textContent,/陳 reviewer: Keep original/);
const englishDate=get('decision-history').children[0].children[1].textContent;
app.language('zh-Hant');assert.equal(get('decision-count').textContent,'1 筆');assert.match(get('decision-history').textContent,/陳 reviewer：保留原稿/);assert.match(get('decision-history').textContent,/原始 note 中文/);
assert.notEqual(get('decision-history').children[0].children[1].textContent,englishDate,'history date follows interface locale');
app.run("showMessage('decision-message','saving')");app.language('en');assert.equal(get('decision-message').textContent,'Saving a new revision…');
app.run("showError('decision-error','畫面已有較新修訂，請重新載入後再決定')");assert.match(get('decision-error').textContent,/A newer revision exists/);
app.language('zh-Hant');assert.equal(get('decision-error').textContent,'畫面已有較新修訂，請重新載入後再決定');
console.log('PASS: decision history, locale dates, pending save copy and known errors switch without rewriting reviewer notes');

for(const storageThrows of [false,true]){
  const restored=harness([snapshot('completed')],{saved:'zh-Hant',storageThrows});await settle();
  assert.equal(restored.document.documentElement.lang,storageThrows?'en':'zh-Hant');
  restored.language('zh-Hant');assert.equal(restored.elements.get('accept').textContent,'採用候選');
  restored.language('en');assert.equal(restored.elements.get('accept').textContent,'Accept candidate');
}
const invalid=harness([snapshot('completed')],{saved:'unknown-language'});await settle();assert.equal(invalid.document.documentElement.lang,'en');
const failed=harness([new Error('initial connection failure')]);await settle();
failed.language('zh-Hant');assert.equal(failed.elements.get('review-name').textContent,'查核檔案尚未載入');assert.match(failed.elements.get('decision-error').textContent,/載入失敗：initial connection failure/);
failed.language('en');assert.equal(failed.elements.get('review-name').textContent,'Review not loaded');assert.match(failed.elements.get('decision-error').textContent,/Load failed: initial connection failure/);
console.log('PASS: explicit preference restores, invalid preference defaults to English, unavailable storage never blocks review');
