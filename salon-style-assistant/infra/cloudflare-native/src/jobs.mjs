import {mutate,index,uid,timestamp,live,read} from './store.mjs';
import {filtered,demoPlans,dimensions,score,growth} from './rules.mjs';
import * as providers from './providers.mjs';
import {cleanupPhotos} from './storage.mjs';

function finish(c,j){const sufficient=c.profile.modes.every(m=>c.candidates.filter(r=>!r.superseded&&r.profile_revision===c.revision&&r.mode===m&&r.gate==='pass'&&r.score!=null).length>=3);j.status=sufficient?'succeeded':'partial';j.stage=sufficient?'等待审核':'结果不足';c.status=sufficient?'review_ready':'partial';j.updated_at=timestamp();}
export async function dispatch(env,body){await env.JOBS.send(body);}
export async function processMessage(env,body){
 const {consultation_id:id,job_id}=body;
 let claim,asset=null;
 try{
  claim=await mutate(env,id,null,c=>{
   const j=c.jobs.find(j=>j.id===job_id);if(!j||!['queued','running'].includes(j.status))return null;
   if(!live(c,j)){j.status='cancelled';j.stage='条件更新、授权撤回或任务取消';return null;}
   if(j.status==='running')return null; // Duplicate delivery cannot repeat an external side effect.
   if(j.phase==='generate'){if(c.attempts_used>=18){j.status='partial';j.stage='图像次数上限';c.status='partial';return null;}c.attempts_used++;}
   j.status='running';j.claim=uid();j.heartbeat=Date.now();j.stage={analysis:'分析照片',plan:'规划方案',generate:'生成图像',evaluate:'检查与评分'}[j.phase];
   return {c:structuredClone(c),j:structuredClone(j)};
  });
  if(!claim)return;
  const {c,j}=claim;const mode=j.modes[j.mode_index||0];let result,meta=null,candidate=null;
  if(j.phase==='analysis'){
   ({result,meta}=c.mode==='real'?await providers.analyze(env,c):{result:{observations:['演示模式不分析照片内容，请发型师检查照片质量。'],unknown_fields:['发长','密度','发质'],photo_issues:[],blocking_issues:[],demo:true}});
  }else if(j.phase==='plan'){
   const response=c.mode==='real'?await providers.plan(env,c,mode):{plans:mode==='grow_out'?demoPlans().reverse():demoPlans()};
   result=filtered(response.plans,c.profile,mode);meta=response.meta;
  }else if(j.phase==='generate'){
   if(c.mode==='real'){
    const response=await providers.generate(env,c,j.plans[j.plan_index]);meta=response.meta;
    asset={id:uid(),kind:'generated',view:'front',mime:response.info.mime,width:response.info.width,height:response.info.height};asset.key=`${c.salon_id}/${c.id}/${asset.id}`;
    await env.PHOTO_STORE.put(asset.key,response.bytes,{httpMetadata:{contentType:asset.mime}});
    await index(env,asset.id,id,'asset');
   }
  }else if(j.phase==='evaluate'){
   const plan=j.plans[j.plan_index];
   ({result,meta}=c.mode==='real'?await providers.evaluate(env,c,plan,j.current_asset):{result:{gate_status:'pass',issues:[],dimensions:Object.fromEntries(dimensions.map((d,i)=>[d,i<3?4:3]))}});
   candidate={id:uid(),plan,mode,demo:c.mode!=='real',profile_revision:j.profile_revision,candidate_revision:j.candidate_revision||1,previous_candidate_id:j.previous_candidate_id||null,asset_id:j.current_asset?.id||null,dimensions:result.dimensions,score:score(result.dimensions,mode),issues:result.issues,gate:result.gate_status,review:'pending',growth:mode==='grow_out'?growth(c.profile,plan.minimum_lengths):null,created_at:timestamp()};
   await index(env,candidate.id,id,'candidate');
  }
  const shouldContinue=await mutate(env,id,null,c=>{
   const current=c.jobs.find(x=>x.id===j.id);
   if(!current||current.claim!==j.claim)return false;
   if(meta)c.model_calls.push({...meta,job_id:j.id,phase:j.phase,created_at:timestamp()});
   if(!live(c,current)){current.status='cancelled';return false;}
   if(j.phase==='analysis'){c.analysis=result;current.status='succeeded';current.stage='分析完成，待人工确认';current.completed=1;return false;}
   if(j.phase==='plan'){
    current.plans=result;current.plan_index=0;current.phase='generate';
    if(!result.length){current.mode_index++;if(current.mode_index>=current.modes.length){finish(c,current);return false;}current.phase='plan';}
   }else if(j.phase==='generate'){
    if(asset)c.assets.push(asset);current.current_asset=asset;current.phase='evaluate';
   }else if(j.phase==='evaluate'){
    c.candidates.push(candidate);current.completed++;current.current_asset=null;current.plan_index++;
    if(current.plan_index<current.plans.length)current.phase='generate';
    else {current.mode_index++;if(current.mode_index>=current.modes.length){finish(c,current);return false;}current.phase='plan';}
   }
   current.status='queued';current.heartbeat=Date.now();return true;
  },{deleted:true});
  if(asset){const after=await read(env,id);if(!after.value.assets.some(a=>a.id===asset.id))await env.PHOTO_STORE.delete(asset.key);}
  if(shouldContinue)await dispatch(env,body);
 }catch(error){
  try{await mutate(env,id,null,c=>{if(asset&&!c.assets.some(a=>a.id===asset.id))c.pending_delete_keys=[...new Set([...(c.pending_delete_keys||[]),asset.key])];const j=c.jobs.find(j=>j.id===job_id);if(j&&['running','queued'].includes(j.status)){j.status=error.code==='PROVIDER_RESULT_UNKNOWN'?'provider_result_unknown':'failed';j.error=error.code||'WORKER_ERROR';j.stage='任务需处理';if(c.revision===j.profile_revision&&!c.deleted)c.status='failed';}},{deleted:true});await cleanupPhotos(env,id);}catch{/* Never log request bodies, keys or photos. */}
 }
}
export async function recover(env){
 const rows=await env.DB.prepare('SELECT id,data FROM consultations').all();
 for(const row of rows.results){const c=JSON.parse(row.data);
  if(c.pending_delete_keys?.length)await cleanupPhotos(env,c.id);
  if(c.deleted)continue;
  for(const j of c.jobs){
   if(j.status==='queued')await dispatch(env,{consultation_id:c.id,job_id:j.id});
   if(j.status==='running'&&Date.now()-j.heartbeat>15*60*1000)await mutate(env,c.id,null,latest=>{const job=latest.jobs.find(x=>x.id===j.id);if(job.status==='running'&&Date.now()-job.heartbeat>15*60*1000){job.status='provider_result_unknown';job.error='PROVIDER_RESULT_UNKNOWN';job.stage='任务中断，需核对费用';latest.status='failed';}});
  }
 }
 await env.DB.batch([env.DB.prepare('DELETE FROM sessions WHERE expires<?').bind(Date.now()),env.DB.prepare('DELETE FROM presentations WHERE expires<?').bind(Date.now()),env.DB.prepare("DELETE FROM rate_limits WHERE CAST(substr(id,instr(id,':')+1) AS INTEGER)<?").bind(Math.floor(Date.now()/60000)-60)]);
}
