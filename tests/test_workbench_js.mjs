// Browser-independent regression for the real workbench polling code.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor(){this.textContent='';this.children=[];this.hidden=false;this.disabled=false;this.value='reviewer';this.className='';this.classList={add(){},remove(){},toggle(){return true;}};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(){}
  addEventListener(){}
  pause(){}
  play(){return Promise.resolve();}
  scrollIntoView(){}
}
const elements=new Map();
const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},createElement(){return new Element();},createTextNode(text){const node=new Element();node.textContent=text;return node;}};
const snapshot=status=>({name:'review remains visible',mutation_token:'token',revision:status==='completed'?1:0,source:{name:'source.wav',seconds:1,available:true},job:{status,configured:true,message:'checking',error:null},review:{policy:{kind:'fixed_baseline'},items:[{segment_id:'s1',start:0,end:1,original_text:'draft',candidate_text:'candidate',status:'pending',reason:'candidate_differs',evidence:[]}],trace:[],decisions:[]}});
const responses=[snapshot('running'),new Error('temporary network failure'),snapshot('completed')];
let fetches=0,nextTimer=0;
const timers=new Map();
const context=vm.createContext({document,window:{innerWidth:1440},console,
  fetch:async()=>{const result=responses[fetches++];if(result instanceof Error)throw result;return{ok:true,json:async()=>result};},
  setTimeout:callback=>{const id=++nextTimer;timers.set(id,callback);return id;},
  clearTimeout:id=>timers.delete(id)});
vm.runInContext(fs.readFileSync(new URL('../src/transcript_review_agent/web/workbench.js',import.meta.url),'utf8'),context);
const settle=async()=>{for(let i=0;i<5;i++)await new Promise(resolve=>setImmediate(resolve));};
const tick=async()=>{assert.equal(timers.size,1,'one controlled poll is scheduled');const [id,callback]=timers.entries().next().value;timers.delete(id);callback();await settle();};
await settle();assert.equal(timers.size,1);
await tick();
assert.equal(timers.size,1,'a failed GET must schedule one recovery poll');
assert.equal(elements.get('review-name').textContent,'review remains visible');
assert.equal(elements.get('decision-error').hidden,false);
await tick();
assert.equal(fetches,3);
assert.equal(timers.size,0,'completed jobs stop polling');
assert.equal(elements.get('accept').disabled,false);
console.log('PASS: transient polling failure recovers, keeps prior data, and never duplicates timers');
