"""Shared-workspace transport never rebases a stale draft or loses scope."""

import shutil
import subprocess
from pathlib import Path

import pytest
from test_case_review_frontend import run_case_review

SCRIPT = Path(__file__).parents[1] / "src/omphalos/ui/team.js"
HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const nodes = new Map();
class Node {
  constructor(id='') { this.id=id; this.dataset={}; this.listeners={}; this.children=[]; }
  addEventListener(type,fn) { this.listeners[type]=fn; }
  setAttribute() {}
  querySelector(selector) { return get(this.id+selector); }
  append(node) { nodes.set('#'+node.id,node); this.children.push(node); }
  prepend(node) { this.append(node); }
  before(node) { nodes.set('#'+node.id,node); }
  showModal() { this.open=true; }
  close() { this.open=false; }
}
function get(selector) { if (!nodes.has(selector)) nodes.set(selector,new Node(selector)); return nodes.get(selector); }
const document=new Node('document');
document.body=get('body');
document.createElement=()=>new Node();
document.querySelector=(selector)=>['#team-account','#team-update'].includes(selector) ? nodes.get(selector)||null : get(selector);
const storage = new Map([['omphalos-team-matter','matter-one']]);
const window={addEventListener(){},sessionStorage:{getItem:(k)=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:(k)=>storage.delete(k)}};
const calls=[];
let releasePoll;
let engine=()=>reply({ok:true},7);
function reply(result,revision,status=200) {return {ok:status<400,status,json:async()=>result,headers:{get:()=>revision===null ? null:String(revision)}};}
const fetch=async(url,options)=>{
 calls.push({url,options});
 if (url==='/team/api/session') return reply({authenticated:true,user:{id:'u1',display_name:'Analyst',is_admin:false},csrf:'csrf-token'},null);
 if (url==='/team/api/matters') return reply({matters:[{id:'matter-one',title:'First matter',revision:7,role:'analyst'}]},null);
 if (url.includes('/events?')) return new Promise((resolve)=>{releasePoll=resolve;});
 return engine(url,options);
};
const context=vm.createContext({window,document,fetch,location:{reload(){}},setTimeout,FormData:class {}});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const team=window.omphalosTeam;
async function scenario() {
 await team.init();
 await team.request('state');
 __SCENARIO__
}
scenario().catch((e)=>{console.error(e);process.exitCode=1;});
"""


def run_team(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for frontend state regression tests")
    result = subprocess.run(
        [node, "-e", HARNESS.replace("__SCENARIO__", scenario), str(SCRIPT)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_team_posts_scope_and_precondition_without_local_token():
    run_team(r"""
 engine=(url,options)=>{
   assert.equal(url,'/team/api/matters/matter-one/engine/runs/run-one/review');
   assert.equal(options.headers['If-Match'],'"7"');
   assert.equal(options.headers['X-Omphalos-CSRF'],'csrf-token');
   assert.equal(options.headers['X-Omphalos-Token'],undefined);
   assert.equal(options.credentials,'same-origin');
   return reply({review_id:'review-one'},8);
 };
 await team.request('runs/run-one/review',{summary:'Retain this assessment.'});
 assert.equal(team.state.revision,8);
 assert.equal(team.state.stale,false);
""")


def test_refresh_cannot_rebase_earlier_unsaved_draft():
    run_team(r"""
 engine=()=>reply({changed:true},8);
 await team.request('state');
 assert.equal(team.state.revision,7);
 assert.equal(team.state.stale,true);
 const before=calls.length;
 await assert.rejects(team.request('runs/run-one/review',{summary:'Earlier draft'}),/Reload the shared version/);
 assert.equal(calls.length,before,'Do not submit old drafts with a newer revision.');
 assert.ok(nodes.has('#team-update'));
""")


@pytest.mark.parametrize("status", [409, 401])
def test_failed_save_preserves_revision_and_freezes_mutations(status):
    run_team(r"""
 engine=()=>reply({error:'Shared state changed'},8,STATUS);
 await assert.rejects(team.request('cases',{question:'Original draft'}),/Shared state changed/);
 assert.equal(team.state.revision,7);
 assert.equal(team.state.stale,true);
 const before=calls.length;
 await assert.rejects(team.request('cases',{question:'Original draft'}),/Reload the shared version/);
 assert.equal(calls.length,before);
""".replace("STATUS", str(status)))


def test_missing_revision_cannot_be_accepted_as_fresh_state():
    run_team(r"""
 engine=()=>reply({ok:true},null);
 await assert.rejects(team.request('state'),/omitted the workspace revision/);
 assert.equal(team.state.revision,7);
 assert.equal(team.state.stale,true);
""")


def test_app_routes_through_team_and_keeps_authenticated_name():
    run_case_review(r"""
 const requests=[];
 window.omphalosTeam={state:{user:{display_name:'Authenticated Analyst'}},request:async(path,body)=>{requests.push({path,body});return {ok:true};}};
 await run('api("cases", {question:"Retain the scoped case"})');
 assert.equal(requests[0].path,'cases');
 assert.match(run('caseReviewView()'),/value="Authenticated Analyst" readonly/);
 run("model.run.latest_export={sha256:'a'.repeat(64)};model.run.latest_review={review_id:'r1',review:{schema_version:'2.2',run_id:'runA',reviewer:'Analyst',decision:'keep_open',summary:'Retain case',scope_finding_ids:['context-A','volume-B'],acknowledge_limitations:true}};model.run.review_validation={ok:true};");
 assert.match(run('independentReviewActions(model.run)'),/Team review/);
""")


def test_transformed_name_candidate_discloses_original_and_comparison_forms():
    run_case_review(r"""
 const markup=run(`candidateFacts({investigation_id:'screening_candidates',metrics:{entity_name_compared:'НПО Астра',source_name_compared:'NPO Astra',name_transformation:'Russian ALA-LC romanization',entity_comparison_form:'astra',source_comparison_form:'astra'}})`);
 assert.match(markup,/НПО Астра/);
 assert.match(markup,/NPO Astra/);
 assert.match(markup,/Russian ALA-LC romanization/);
 assert.match(markup,/Entity comparison form/);
""")


def test_late_package_review_does_not_replace_a_different_package():
    run_team(r"""
 let releaseA;
 engine=(url)=>{
   const id=url.endsWith('run_id=A') ? 'A':'B';
   const result={package:{run_id:id,package_sha256:id.repeat(64)},submission:null,decisions:[],can_submit:true,can_review:false};
   if (id==='A') return new Promise((resolve)=>{releaseA=()=>resolve(reply(result,7));});
   return reply(result,7);
 };
 const earlier=team.review({run_id:'A',package_sha256:'A'.repeat(64)});
 await team.review({run_id:'B',package_sha256:'B'.repeat(64)});
 const visible=nodes.get('#team-dialog').innerHTML;
 assert.ok(visible.includes('B'.repeat(64)));
 releaseA(); await earlier;
 assert.equal(nodes.get('#team-dialog').innerHTML,visible);
""")


def test_review_rejects_a_package_changed_since_the_opened_run():
    run_team(r"""
 engine=()=>reply({package:{run_id:'A',package_sha256:'b'.repeat(64)},submission:null,decisions:[],can_submit:true,can_review:false},7);
 await assert.rejects(team.review({run_id:'A',package_sha256:'a'.repeat(64)}),/package changed/);
 assert.equal(team.state.stale,true);
 assert.equal(nodes.has('#team-dialog'),false);
""")


def test_reviewer_reads_assessment_without_an_edit_form():
    run_case_review(r"""
 window.omphalosTeam={state:{matter:{role:'reviewer'},user:{display_name:'Independent Reviewer'}}};
 const markup=run('caseReviewView()');
 assert.match(markup,/Recorded assessment/);
 assert.ok(!markup.includes('<form'));
 assert.ok(!run('flowWorkActions()').includes('data-flow="restart"'));
""")


def test_selecting_current_workspace_preserves_revision_and_generation():
    run_team(r"""
 const generation=team.state.generation;
 const button={dataset:{team:'select',id:'matter-one'},disabled:false};
 document.listeners.click({target:{closest:()=>button},preventDefault(){}});
 await new Promise((resolve)=>setTimeout(resolve,0));
 assert.equal(team.state.generation,generation);
 assert.equal(team.state.revision,7);
 assert.equal(team.state.stale,false);
 engine=(url,options)=>{
   assert.equal(options.headers['If-Match'],'"7"');
   return reply({review_id:'saved-after-picker'},9);
 };
 await team.request('runs/run-one/review',{summary:'Draft retained while choosing the same workspace.'});
 assert.equal(team.state.revision,9);
""")


@pytest.mark.parametrize("change", ["selection", "dialog"])
def test_late_access_list_cannot_be_shown_under_another_workspace(change):
    run_team(r"""
 let release;
 get('#team-member-matter').value='matter-A';
 get('#team-members').innerHTML='Keep the currently displayed access list.';
 engine=(url)=>{
   assert.equal(url,'/team/api/admin/matters/matter-A/members');
   return new Promise((resolve)=>{release=()=>resolve(reply({members:[{display_name:'Member of A only',role:'analyst'}]},11));});
 };
 const membersButton={dataset:{team:'members'},disabled:false};
 document.listeners.click({target:{closest:()=>membersButton},preventDefault(){}});
 if (CHANGE==='selection') get('#team-member-matter').value='matter-B';
 else {
   const passwordButton={dataset:{team:'password'},disabled:false};
   document.listeners.click({target:{closest:()=>passwordButton},preventDefault(){}});
 }
 release();
 await new Promise((resolve)=>setTimeout(resolve,0));
 assert.equal(get('#team-members').innerHTML,'Keep the currently displayed access list.');
""".replace("CHANGE", repr(change)))


def test_review_note_is_retained_across_close_and_isolated_by_exact_package():
    run_team(r"""
 engine=(url)=>{
   const id=url.endsWith('run_id=A') ? 'A':'B';
   return reply({package:{run_id:id,package_sha256:id.repeat(64)},submission:null,decisions:[],can_submit:false,can_review:true},7);
 };
 await team.review({run_id:'A',package_sha256:'A'.repeat(64)});
 const form=get('#team-decision');
 form.querySelector('[name="note"]').value='Retain the exact invoice question <without changing its text>.';
 form.querySelector('[name="decision"]').value='approve';
 const button={dataset:{team:'close'},disabled:false};
 document.listeners.click({target:{closest:()=>button},preventDefault(){}});
 const saved=team.drafts();
 assert.equal(saved.length,1);
 assert.equal(saved[0].matter_id,'matter-one');
 assert.equal(saved[0].run_id,'A');
 assert.equal(saved[0].package_sha256,'A'.repeat(64));
 assert.equal(saved[0].base_revision,7);
 assert.equal(saved[0].decision,'approve');
 await team.review({run_id:'A',package_sha256:'A'.repeat(64)});
 assert.ok(nodes.get('#team-dialog').innerHTML.includes('invoice question &lt;without changing its text&gt;.'));
 assert.match(nodes.get('#team-dialog').innerHTML,/value="approve" selected/);
 await team.review({run_id:'B',package_sha256:'B'.repeat(64)});
 assert.ok(!nodes.get('#team-dialog').innerHTML.includes('invoice question'));
 // The generic DOM adapter does not parse new textarea markup; mirror the new empty field.
 form.querySelector('[name="note"]').value='';
 assert.equal(team.drafts().length,1);
 assert.equal(team.drafts()[0].run_id,'A');
""")


def test_stale_workspace_keeps_the_review_note_and_original_base_revision():
    run_team(r"""
 engine=()=>reply({package:{run_id:'A',package_sha256:'a'.repeat(64)},submission:null,decisions:[],can_submit:false,can_review:true},7);
 await team.review({run_id:'A',package_sha256:'a'.repeat(64)});
 get('#team-decision').querySelector('[name="note"]').value='Ask the analyst to obtain and cite the missing registration record.';
 engine=()=>reply({changed:true},9);
 await team.request('state');
 assert.equal(team.state.stale,true);
 const saved=team.drafts()[0];
 assert.equal(saved.base_revision,7);
 assert.equal(saved.package_sha256,'a'.repeat(64));
 assert.match(saved.note,/missing registration record/);
 const before=calls.length;
 await assert.rejects(team.request('runs/A/review',{}),/Reload the shared version/);
 assert.equal(calls.length,before);
""")


def test_draft_download_includes_unsaved_team_review_and_package_binding():
    run_case_review(r"""
 window.omphalosTeam={
   state:{matter:{id:'matter-one'},revision:7},
   drafts:()=>[{matter_id:'matter-one',run_id:'runA',package_sha256:'a'.repeat(64),base_revision:7,decision:'request_changes',note:'Retain the registration evidence question.'}],
 };
 run('globalThis.savedDraftCopy=null; downloadReviewJson=(value)=>{globalThis.savedDraftCopy=value;};');
 window.emit('omphalos-team-save-draft',{});
 const saved=JSON.parse(run('JSON.stringify(savedDraftCopy)'));
 assert.equal(saved.kind,'omphalos-unsaved-draft');
 assert.equal(saved.team_reviews.length,1);
 assert.equal(saved.team_reviews[0].package_sha256,'a'.repeat(64));
 assert.equal(saved.team_reviews[0].base_revision,7);
 assert.equal(saved.team_reviews[0].note,'Retain the registration evidence question.');
""")


def test_late_older_notification_does_not_flag_our_completed_save():
    run_team(r"""
 engine=()=>reply({saved:true},9);
 await team.request('cases',{question:'Saved in this session'});
 releasePoll(reply({revision:8,events:[]},8));
 await new Promise((resolve)=>setImmediate(resolve));
 assert.equal(team.state.revision,9);
 assert.equal(team.state.stale,false);
 team.state.generation+=1;
""")
