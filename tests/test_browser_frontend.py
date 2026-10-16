"""Offline browser-transport regressions using the actual UI and worker scripts.

The fake DOM and Python bridge exercise request, storage, and download boundaries;
they do not stand in for the real WASM pipeline or browser layout checks.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from test_frontend_guards import run_scenario

UI = Path(__file__).parents[1] / "src/omphalos/ui"

WORKER_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const messages = [], syncCalls = [], syncErrors = [], dispatchCalls = [], fetches = [], packageCalls = [];
let envelope = {status:200,body_json:{ok:true}};
let restoreEnvelope = {status:200,body_json:{restored:true,datasets:1,runs:1}};
let destroyed = 0, restoredBytes = null;
const source = Uint8Array.from([80,75,1,2]);
const manifest = {pyodide:{index_url:'runtime/pyodide/'},wheels:[],engine:{path:'runtime/omphalos.zip',bytes:source.length,sha256:crypto.createHash('sha256').update(source).digest('hex')}};
function binary() {
  const bytes = Uint8Array.from([80,75,7,9]);
  return {toJs:()=>bytes,destroy(){destroyed += 1;bytes.fill(0);}};
}
const bridgeMock = {
  dispatch_json(...args){dispatchCalls.push(args);return JSON.stringify(envelope);},
  export_bytes:binary, backup_bytes:binary,
  restore_bytes(bytes){restoredBytes=bytes;return {toJs(options){assert.equal(typeof options.dict_converter,'function');return restoreEnvelope;},destroy(){destroyed+=1;}};},
};
const engineMock = {
  FS:{syncfs(populate,callback){syncCalls.push(populate);callback(syncErrors.shift()||null);},mkdirTree(){},mount(){},filesystems:{IDBFS:{}}},
  loadedPackages:{},async loadPackage(names,options){packageCalls.push({names,options});for(const name of names)this.loadedPackages[name]='local';},unpackArchive(){},runPython(){},globals:{get:()=>bridgeMock},
};
let xhrResult = {status:200,headers:'Last-Modified: Fri, 16 Oct 2026 12:15:05 GMT\r\nContent-Type: application/json\r\n',bytes:Uint8Array.from([123,125])};
let xhrRequest;
class XHR {
  constructor(){xhrRequest=this;this.headers={};}
  open(method,url,async){Object.assign(this,{method,url,async});}
  setRequestHeader(name,value){this.headers[name]=value;}
  send(){this.status=xhrResult.status;this.responseURL=xhrResult.url||this.url;this.response=xhrResult.bytes.buffer;}
  getAllResponseHeaders(){return xhrResult.headers;}
}
const self = {location:{origin:'https://petervartanian.xyz'},postMessage(message){messages.push(message);},addEventListener(){}};
const context = vm.createContext({self,URL,Uint8Array,ArrayBuffer,Date,console,crypto:crypto.webcrypto,XMLHttpRequest:XHR,
  async fetch(url){fetches.push(String(url));return {ok:true,json:async()=>manifest,arrayBuffer:async()=>source.buffer};},
  engineMock,bridgeMock,
});
const runtimeModule = new vm.SyntheticModule(['loadPyodide'],function(){this.setExport('loadPyodide',async()=>engineMock);},{context});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context,{importModuleDynamically:async()=>{
  if(runtimeModule.status==='unlinked')await runtimeModule.link(()=>{});
  if(runtimeModule.status==='linked')await runtimeModule.evaluate();
  return runtimeModule;
}});
const run = (code)=>vm.runInContext(code,context);
run('engine=engineMock;bridge=bridgeMock;dispatch=bridgeMock.dispatch_json;exportBytes=bridgeMock.export_bytes;');
const handle=(message)=>{context.message=message;return run('handle(message)');};
const result=(id)=>messages.findLast(message=>message.id===id);
async function scenario(){
__SCENARIO__
}
scenario().catch(error=>{console.error(error);process.exitCode=1;});
"""

MAIN_HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const events = [], workers = [], downloads = [], blobs = [], timers = [];
class Element {
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.attributes={};this.children=[];this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';this.focused=false;}
  setAttribute(name,value){this.attributes[name]=String(value);}
  getAttribute(name){return this.attributes[name]??null;}
  removeAttribute(name){delete this.attributes[name];}
  addEventListener(type,listener){(this.listeners[type] ||= []).push(listener);}
  async emit(type,event={}){event.target ||= this;for(const listener of this.listeners[type]||[])await listener(event);}
  append(...elements){for(const element of elements){element.parentNode=this;this.children.push(element);}}
  prepend(element){element.parentNode=this;this.children.unshift(element);}
  insertBefore(element,before){element.parentNode=this;this.children.splice(this.children.indexOf(before),0,element);}
  remove(){if(this.parentNode)this.parentNode.children=this.parentNode.children.filter(item=>item!==this);}
  closest(selector){if(selector==='a[href]')return this.tagName==='A'&&this.href?this:null;const match=selector.match(/^\[([^\]]+)\]$/);return match&&Object.hasOwn(this.attributes,match[1])?this:null;}
  querySelector(selector){return this.children.find(item=>item.closest(selector))||this.children.map(item=>item.querySelector(selector)).find(Boolean)||null;}
  focus(){this.focused=true;}
  showModal(){this.open=true;}
  close(){this.open=false;void this.emit('close');}
  click(){if(this.tagName==='A')downloads.push({href:this.href,name:this.download});return this.emit('click');}
  set innerHTML(value){this.html=value;for(const name of ['data-browser-backup','data-restore-cancel','data-restore-confirm']){if(value.includes(name)){const element=new Element('button');element.setAttribute(name,'');this.append(element);}}}
  get innerHTML(){return this.html||'';}
}
const document = new Element('document');
document.currentScript={src:'https://petervartanian.xyz/omphalos/browser.js'};
document.body=new Element('body');
const main=new Element('main');main.id='main';document.body.append(main);
document.createElement=(tag)=>new Element(tag);
document.getElementById=(id)=>{const visit=(element)=>element.id===id?element:element.children.map(visit).find(Boolean);return visit(document.body)||null;};
document.querySelector=()=>null;
const window=new Element('window');window.indexedDB={};window.dispatchEvent=(event)=>events.push(event);
const lockCalls=[];
let lockAvailable=true;
const navigator={locks:{request(name,options,callback){lockCalls.push({name,options});return Promise.resolve(callback(lockAvailable?{}:null));}}};
class Worker {
  constructor(url,options){this.url=String(url);this.options=options;this.sent=[];this.listeners={};workers.push(this);}
  addEventListener(type,handler){this.listeners[type]=handler;}
  postMessage(value){this.sent.push(value);}
  emit(value){this.listeners.message({data:value});}
}
class BrowserURL extends URL {
  static createObjectURL(blob){blobs.push(blob);return 'blob:'+blobs.length;}
  static revokeObjectURL(){}
}
class CustomEvent {constructor(type,options){this.type=type;this.detail=options.detail;}}
const context=vm.createContext({document,window,navigator,Worker,URL:BrowserURL,Blob,Uint8Array,CustomEvent,console,setTimeout:(callback,ms)=>timers.push({callback,ms})});
function boot(){vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const event=(target)=>({target,prevented:false,preventDefault(){this.prevented=true;}});
async function scenario(){
__SCENARIO__
}
scenario().catch(error=>{console.error(error);process.exitCode=1;});
"""


def run_script(harness: str, filename: str, scenario: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for browser transport regression tests")
    result = subprocess.run(
        [
            node,
            "--experimental-vm-modules",
            "-e",
            harness.replace("__SCENARIO__", scenario),
            str(UI / filename),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def worker(scenario: str) -> None:
    run_script(WORKER_HARNESS, "browser-worker.js", scenario)


def main(scenario: str) -> None:
    run_script(MAIN_HARNESS, "browser.js", scenario)


def test_ui_uses_browser_bridge_without_fetch_and_preserves_http_errors() -> None:
    run_scenario(r"""
let calls=[];
fetchImplementation=()=>{throw new Error('Browser mode must not call the HTTP API.');};
window.omphalosBrowser={request:async(...args)=>{calls.push(args);return {ok:true};}};
assert.equal((await run("api('state')")).ok,true);
assert.equal(calls[0][0],'state');
assert.equal(calls[0][1],undefined);
await run("api('reviews',{decision:'keep_open'})");
assert.equal(calls[1][1].decision,'keep_open');
window.omphalosBrowser.request=async()=>{const error=new Error('Decision required');error.status=422;throw error;};
await assert.rejects(run("api('reviews',{})"),error=>error.status===422&&error.message==='Decision required');
""")


def test_native_transport_and_storage_copy_stay_separate() -> None:
    run_scenario(r"""
const calls=[];
fetchImplementation=async(...args)=>{calls.push(args);return jsonResponse({ok:true});};
await run("api('reviews',{decision:'keep_open'})");
assert.equal(calls[0][0],'/api/reviews');
assert.equal(calls[0][1].method,'POST');
assert.equal(calls[0][1].headers['X-Omphalos-Token'],'synthetic-session-token');
assert.match(run('storageExplanation()'),/local workspace/);
run("model.state.storage={mode:'browser'}");
assert.match(run('storageExplanation()'),/Clearing website data or browser storage eviction/);
assert.doesNotMatch(run('storageExplanation()'),/server|forever/);
""")


def test_get_omits_python_body_argument_and_never_flushes() -> None:
    worker(r"""
await handle({id:1,type:'request',path:'/api/state',body:null});
await handle({id:2,type:'request',path:'/api/runs/runA'});
assert.deepEqual(dispatchCalls,[['/api/state'],['/api/runs/runA']]);
assert.deepEqual(syncCalls,[]);
assert.equal(result(1).result.status,200);
""")


def test_failed_storage_preserves_completed_response_and_can_recover() -> None:
    worker(r"""
envelope={status:201,body_json:{download_url:'/api/exports/real-package.zip'}};
syncErrors.push(new Error('quota'));
await handle({id:1,type:'request',path:'/api/exports',body:'{"run_id":"runA"}'});
assert.equal(result(1).result.body_json.download_url,'/api/exports/real-package.zip');
assert.equal(result(1).error,undefined);
assert.equal(messages.findLast(message=>message.type==='storage').saved,false);
envelope={status:200,body_json:{storage:{description:'Retained workspace'}}};
await handle({id:2,type:'request',path:'/api/state',body:null});
assert.match(result(2).result.body_json.storage.description,/not been saved/);
assert.deepEqual(syncCalls,[false]);
await handle({id:3,type:'request',path:'/api/reviews',body:'{}'});
assert.equal(messages.findLast(message=>message.type==='storage').saved,true);
assert.deepEqual(syncCalls,[false,false]);
""")


def test_failed_mutation_response_is_also_flushed() -> None:
    worker(r"""
envelope={status:422,body_json:{error:'Choose a decision'}};
await handle({id:1,type:'request',path:'/api/reviews',body:'{}'});
assert.deepEqual(syncCalls,[false]);
assert.equal(result(1).result.status,422);
""")


def test_startup_flush_failure_allows_work_but_populate_failure_stops() -> None:
    worker(r"""
syncErrors.push(null,new Error('storage full'));
await handle({type:'initialize',appBase:'https://petervartanian.xyz/omphalos/'});
assert.deepEqual(syncCalls,[true,false]);
assert.equal(messages.findLast(message=>message.type==='storage').saved,false);
assert.equal(messages.at(-1).type,'ready');
messages.length=0;syncCalls.length=0;
syncErrors.push(new Error('cannot read retained files'));
await handle({type:'initialize',appBase:'https://petervartanian.xyz/omphalos/'});
assert.deepEqual(syncCalls,[true]);
assert.equal(messages.at(-1).type,'startup-error');
assert.match(messages.at(-1).error,/cannot read retained files/);
assert.equal(messages.some(message=>message.type==='ready'),false);
""")


def test_binary_downloads_survive_proxy_release_without_writing_storage() -> None:
    worker(r"""
await handle({id:1,type:'download',path:'/api/exports/retained-evidence.zip'});
await handle({id:2,type:'backup'});
assert.equal(result(1).result.name,'retained-evidence.zip');
assert.deepEqual([...result(1).result.bytes],[80,75,7,9]);
assert.match(result(2).result.name,/^omphalos-workspace-\d{4}-\d{2}-\d{2}\.zip$/);
assert.deepEqual([...result(2).result.bytes],[80,75,7,9]);
assert.equal(destroyed,2);
assert.deepEqual(syncCalls,[]);
""")


def test_runtime_loads_verified_package_names_and_fails_if_a_package_is_missing() -> (
    None
):
    worker(r"""
manifest.wheels=[{name:'pydantic',path:'runtime/wheels/pydantic.whl',sha256:'fixture',bytes:1}];
await handle({type:'initialize',appBase:'https://petervartanian.xyz/omphalos/'});
assert.deepEqual([...packageCalls[0].names],['pydantic']);
assert.equal(packageCalls[0].options.checkIntegrity,true);
assert.equal(fetches.some(url=>url.includes('/wheels/')),false);
assert.equal(messages.at(-1).type,'ready');
engineMock.loadedPackages={};engineMock.loadPackage=async()=>[];messages.length=0;
await handle({type:'initialize',appBase:'https://petervartanian.xyz/omphalos/'});
assert.equal(messages.at(-1).type,'startup-error');
assert.match(messages.at(-1).error,/could not be verified/);
""")


def test_restore_flushes_final_state_and_keeps_response_when_flush_fails() -> None:
    worker(r"""
const bytes=Uint8Array.from([80,75,1,2]);
syncErrors.push(new Error('quota'));
await handle({id:1,type:'restore',bytes});
assert.equal(restoredBytes,bytes);
assert.equal(result(1).result.body_json.restored,true);
assert.equal(messages.findLast(message=>message.type==='storage').saved,false);
restoreEnvelope={status:400,body_json:{error:'Invalid backup'}};
await handle({id:2,type:'restore',bytes});
assert.equal(result(2).result.status,400);
assert.deepEqual(syncCalls,[false,false]);
assert.equal(destroyed,2);
""")


def test_source_transport_preserves_canonical_url_and_visible_provenance() -> None:
    worker(r"""
const canonical='https://www.wikidata.org/w/api.php?action=query&format=json';
const response=self.omphalosFetch(canonical,1024,'wikidata');
assert.equal(xhrRequest.url,canonical+'&origin=*');
assert.equal(xhrRequest.async,false);
assert.equal(xhrRequest.timeout,90000);
assert.equal(response.url,canonical);
assert.equal(response.headers['last-modified'],'Fri, 16 Oct 2026 12:15:05 GMT');
assert.deepEqual([...response.body],[123,125]);
""")


def test_source_transport_rejects_unexpected_hosts_redirects_and_oversize() -> None:
    worker(r"""
assert.throws(()=>self.omphalosFetch('https://sanctionslist.ofac.treas.gov/Home/SdnList',100,'ofac'),/Import its file/);
assert.throws(()=>self.omphalosFetch('http://data.trade.gov/x',100,'csl'),/Import its file/);
xhrResult.url='https://unrelated.example/response';
assert.throws(()=>self.omphalosFetch('https://data.trade.gov/source.json',100,'csl'),/unexpected address/);
delete xhrResult.url;
assert.throws(()=>self.omphalosFetch('https://data.trade.gov/source.json',1,'csl'),/download limit/);
""")


def test_main_transport_keeps_paths_and_errors_and_requires_single_writer_lock() -> (
    None
):
    main(r"""
boot();
assert.equal(workers.length,1);
assert.equal(lockCalls[0].name,'omphalos-workspace-v2');
assert.equal(lockCalls[0].options.ifAvailable,true);
const worker=workers[0];
assert.equal(worker.url,'https://petervartanian.xyz/omphalos/browser-worker.js');
assert.equal(worker.options.type,'module');
worker.emit({type:'ready'});
const request=window.omphalosBrowser.request('state');await tick();
assert.equal(worker.sent.at(-1).path,'/api/state');
assert.equal(worker.sent.at(-1).body,null);
worker.emit({id:worker.sent.at(-1).id,result:{status:200,body_json:{ok:true}}});
assert.equal((await request).ok,true);
const failed=window.omphalosBrowser.request('reviews',{decision:''});
const rejection=assert.rejects(failed,error=>error.status===422&&error.message==='Decision required');
await tick();
assert.equal(worker.sent.at(-1).body,'{"decision":""}');
worker.emit({id:worker.sent.at(-1).id,result:{status:422,body_json:{error:'Decision required'}}});
await rejection;
""")


@pytest.mark.parametrize(
    "setup", ["lockAvailable=false", "window.indexedDB=null", "navigator.locks=null"]
)
def test_unsupported_or_already_open_browser_does_not_start_writer(setup: str) -> None:
    main(setup + r""";
boot();
await assert.rejects(window.omphalosBrowser.request('state'),/another tab|cannot safely save/);
assert.equal(workers.length,0);
""")


def test_storage_warning_survives_notices_and_protects_unload_until_saved() -> None:
    main(r"""
boot();const worker=workers[0];worker.emit({type:'ready'});
worker.emit({type:'storage',saved:false});
const warning=document.getElementById('browser-storage-warning');
assert.equal(warning.hidden,false);
assert.equal(warning.getAttribute('role'),'alert');
assert.match(warning.children[0].textContent,/only in this tab/);
assert.ok(warning.querySelector('[data-browser-backup]'));
main.innerHTML='<p>Ordinary successful operation</p>';
assert.equal(document.getElementById('browser-storage-warning'),warning);
const before=event(window);await window.emit('beforeunload',before);
assert.equal(before.prevented,true);
worker.emit({type:'storage',saved:true});
assert.equal(warning.hidden,true);
const after=event(window);await window.emit('beforeunload',after);
assert.equal(after.prevented,false);
""")


def test_export_and_backup_download_exact_bytes_and_leave_external_links_alone() -> (
    None
):
    main(r"""
boot();const worker=workers[0];worker.emit({type:'ready'});
const link=new Element('a');link.href='https://petervartanian.xyz/api/exports/evidence.zip';
const click=event(link), pending=document.emit('click',click);await tick();
assert.equal(click.prevented,true);
assert.equal(worker.sent.at(-1).type,'download');
assert.equal(link.getAttribute('aria-busy'),'true');
worker.emit({id:worker.sent.at(-1).id,result:{name:'evidence.zip',bytes:Uint8Array.from([80,75,3,4])}});
await pending;
assert.equal(downloads.at(-1).name,'evidence.zip');
assert.deepEqual([...new Uint8Array(await blobs[0].arrayBuffer())],[80,75,3,4]);
assert.equal(blobs[0].type,'application/zip');
assert.equal(link.getAttribute('aria-busy'),null);
const external=new Element('a');external.href='https://other.example/api/exports/evidence.zip';
const externalClick=event(external);await document.emit('click',externalClick);
assert.equal(externalClick.prevented,false);
const backup=new Element('button');backup.setAttribute('data-browser-backup','');
const pendingBackup=document.emit('click',event(backup));await tick();
assert.equal(worker.sent.at(-1).type,'backup');assert.equal(backup.disabled,true);
worker.emit({id:worker.sent.at(-1).id,result:{name:'workspace.zip',bytes:Uint8Array.from([80,75])}});
await pendingBackup;assert.equal(backup.disabled,false);assert.equal(downloads.at(-1).name,'workspace.zip');
""")


def test_restore_requires_confirmation_and_offers_existing_backup_first() -> None:
    main(r"""
boot();const worker=workers[0];worker.emit({type:'ready'});
let reads=0;
const input=new Element('input');input.setAttribute('data-browser-restore','');
input.files=[{size:4,arrayBuffer:async()=>{reads+=1;return Uint8Array.from([80,75,1,2]).buffer;}}];
input.value='archive.zip';
const cancelled=document.emit('change',event(input));await tick();
let dialog=document.body.children.find(element=>element.tagName==='DIALOG');
assert.ok(dialog.open);assert.ok(dialog.querySelector('[data-browser-backup]'));
assert.equal(dialog.querySelector('[data-restore-cancel]').focused,true);
assert.equal(reads,0);
await dialog.querySelector('[data-restore-cancel]').click();await cancelled;
assert.equal(reads,0);assert.equal(worker.sent.length,1);assert.equal(input.disabled,false);
const pending=document.emit('change',event(input));await tick();
dialog=document.body.children.find(element=>element.tagName==='DIALOG');
await dialog.querySelector('[data-restore-confirm]').click();await tick();
assert.equal(reads,1);assert.equal(worker.sent.at(-1).type,'restore');
assert.deepEqual([...worker.sent.at(-1).bytes],[80,75,1,2]);
const progress=document.body.children.find(element=>element.tagName==='DIALOG');
assert.equal(progress.open,true);assert.match(progress.innerHTML,/Restoring workspace…/);
assert.equal(progress.getAttribute('aria-busy'),'true');
const cancel=event(progress);await progress.emit('cancel',cancel);assert.equal(cancel.prevented,true);
await assert.rejects(window.omphalosBrowser.request('state'),/restore to finish/);
assert.equal(worker.sent.at(-1).type,'restore','No stale app request may queue behind restoration.');
const before=event(window);await window.emit('beforeunload',before);assert.equal(before.prevented,true);
worker.emit({id:worker.sent.at(-1).id,result:{status:200,body_json:{restored:true,datasets:1,runs:2}}});
await pending;
assert.equal(progress.open,false);assert.equal(document.body.children.includes(progress),false);
assert.equal(events.at(-1).type,'omphalos-browser-restored');assert.equal(events.at(-1).detail.runs,2);
assert.equal(input.value,'');assert.equal(input.disabled,false);
const refreshed=window.omphalosBrowser.request('state');await tick();
worker.emit({id:worker.sent.at(-1).id,result:{status:200,body_json:{datasets:[]}}});
assert.equal((await refreshed).datasets.length,0);
""")


def test_restore_does_not_begin_during_another_operation_or_a_pending_backup() -> None:
    main(r"""
boot();const worker=workers[0];worker.emit({type:'ready'});
const input=new Element('input');input.setAttribute('data-browser-restore','');
let reads=0;input.files=[{size:4,arrayBuffer:async()=>{reads+=1;return new ArrayBuffer(4);}}];
const appRequest=window.omphalosBrowser.request('reviews',{decision:'keep_open'});await tick();
await document.emit('change',event(input));
assert.equal(reads,0);assert.equal(document.body.children.some(element=>element.tagName==='DIALOG'),false);
assert.match(events.at(-1).detail,/current operation to finish/);
worker.emit({id:worker.sent.at(-1).id,result:{status:200,body_json:{saved:true}}});await appRequest;
const restore=document.emit('change',event(input));await tick();
const dialog=document.body.children.find(element=>element.tagName==='DIALOG');
const backup=document.emit('click',event(dialog.querySelector('[data-browser-backup]')));await tick();
assert.equal(worker.sent.at(-1).type,'backup');
await dialog.querySelector('[data-restore-confirm]').click();await restore;
assert.equal(reads,0);assert.match(events.at(-1).detail,/current operation to finish/);
worker.emit({id:worker.sent.at(-1).id,result:{name:'workspace.zip',bytes:Uint8Array.from([80,75])}});await backup;
assert.equal(worker.sent.some(message=>message.type==='restore'),false);
assert.equal(input.disabled,false);
""")


def test_failed_restore_closes_progress_reports_error_and_unlocks_existing_workspace() -> (
    None
):
    main(r"""
boot();const worker=workers[0];worker.emit({type:'ready'});
const input=new Element('input');input.setAttribute('data-browser-restore','');
input.files=[{size:4,arrayBuffer:async()=>Uint8Array.from([80,75,1,2]).buffer}];
const restore=document.emit('change',event(input));await tick();
const confirmation=document.body.children.find(element=>element.tagName==='DIALOG');
await confirmation.querySelector('[data-restore-confirm]').click();await tick();
const progress=document.body.children.find(element=>element.tagName==='DIALOG');
worker.emit({id:worker.sent.at(-1).id,result:{status:400,body_json:{error:'Backup validation failed. Existing files were retained.'}}});
await restore;
assert.equal(progress.open,false);assert.equal(document.body.children.includes(progress),false);
assert.equal(events.at(-1).type,'omphalos-browser-error');assert.match(events.at(-1).detail,/Existing files were retained/);
const error=document.body.querySelector('[data-browser-restore-error]');
assert.equal(error.getAttribute('role'),'alert');assert.equal(error.hidden,false);
assert.match(error.textContent,/Existing files were retained/);
assert.equal(events.some(event=>event.type==='omphalos-browser-restored'),false);
const request=window.omphalosBrowser.request('state');await tick();
worker.emit({id:worker.sent.at(-1).id,result:{status:200,body_json:{datasets:[{dataset_id:'existing'}]}}});
assert.equal((await request).datasets[0].dataset_id,'existing');
assert.equal(input.disabled,false);
const nextAttempt=document.emit('change',event(input));await tick();
assert.equal(error.hidden,true);assert.equal(error.textContent,'');
const nextConfirmation=document.body.children.find(element=>element.tagName==='DIALOG');
await nextConfirmation.querySelector('[data-restore-cancel]').click();await nextAttempt;
""")


def test_oversized_restore_is_rejected_before_reading_or_opening_confirmation() -> None:
    main(r"""
boot();workers[0].emit({type:'ready'});
const input=new Element('input');input.setAttribute('data-browser-restore','');
input.files=[{size:512*1024*1024+1,arrayBuffer(){throw new Error('Must not allocate this file.');}}];
await document.emit('change',event(input));
assert.equal(events.at(-1).type,'omphalos-browser-error');
assert.match(events.at(-1).detail,/512 MiB/);
assert.equal(document.body.children.some(element=>element.tagName==='DIALOG'),false);
assert.equal(workers[0].sent.length,1);
""")
