import {uid,timestamp,sha,fail,read,mutate,locate,index,keyed,previous,remember,activeJobs,current,audit} from './store.mjs';
import {auth,password,equal,cookies,cookie,bootstrap} from './security.mjs';
import {ready,stripMetadata} from './providers.mjs';
import {zones,lengths,issues} from './rules.mjs';
import {dispatch} from './jobs.mjs';
import {storageReady,cleanupPhotos} from './storage.mjs';
const json=(body,status=200,headers={})=>Response.json(body,{status,headers});
const resource=(c,id,kind)=>{const r=c[kind].find(x=>x.id===id);if(!r)fail('NOT_FOUND','资源不存在',404);return r;};
const available=(c,r)=>!r.superseded&&r.profile_revision===c.revision;
export function profileValid(p){
 const choices={cut_tolerance:['仅修整','适度剪短','可明显改变'],fringe_preference:['保留','可改变','不要刘海','无偏好'],tie_back_need:['必须','偶尔','不需要'],daily_styling_time:['基本不打理','5 分钟内','5～15 分钟','更久'],perm_acceptance:['不接受','可讨论','接受'],waiting_horizon:['3 个月内','半年内','一年内','不限制'],curl_pattern:['直','微卷','明显卷','不确定'],strand_thickness:['细软','中等','粗硬','不确定'],density:['偏少','中等','偏多','不确定'],photo_hair_state:['干发','湿发','较多造型产品'],damage_observation:['无明显问题','有受损表现','需判断']};
 if(!Object.entries(choices).every(([k,v])=>v.includes(p[k])))return false;
 return Array.isArray(p.modes)&&p.modes.length>0&&p.modes.length<=2&&p.modes.every(m=>['current','grow_out'].includes(m))&&new Set(p.modes).size===p.modes.length&&p.lengths&&Object.keys(p.lengths).length===4&&zones.every(z=>Object.hasOwn(lengths,p.lengths[z]))&&Array.isArray(p.style_preferences)&&p.style_preferences.length<=3&&p.style_preferences.every(s=>['自然','利落','柔和','成熟','时尚','个性'].includes(s))&&Array.isArray(p.treatment_history)&&p.treatment_history.length>=1&&p.treatment_history.length<=3&&p.treatment_history.every(s=>['无','烫过','染过','漂过','不确定'].includes(s));
}
function photoReady(c){const v=c.assets.filter(a=>a.kind==='original').map(a=>a.view);if(!v.includes('front')||!v.some(v=>['left','right'].includes(v)))fail('PHOTO_QUALITY_BLOCKED','请上传正面和至少一张侧面');}
function canGenerate(env,c,revision){if(!c.consent)fail('CONSENT_REQUIRED','请确认照片使用授权');if(c.revision!==revision)fail('PROFILE_REVISION_CONFLICT','档案版本已更新',409);if(!c.profile)fail('PROFILE_INCOMPLETE','请先确认条件');photoReady(c);if(activeJobs(c).length)fail('JOB_ACTIVE','已有任务运行中',409);if(c.mode==='real'){if(!storageReady(env))fail('STORAGE_NOT_CONFIGURED','请先配置阿里云 OSS',503);if(!ready(env))fail('MODEL_NOT_CONFIGURED','模型密钥尚未配置',503);if(!c.analysis||c.analysis.blocking_issues.length)fail('PHOTO_QUALITY_BLOCKED','请先完成照片分析并解决严重问题');}}
async function presentation(env,request){const raw=cookies(request).salon_presentation;if(!raw)fail('PRESENTATION_EXPIRED','展示已结束，请交回发型师',401);const s=await env.DB.prepare('SELECT * FROM presentations WHERE id=? AND expires>?').bind(await sha(raw),Date.now()).first();if(!s)fail('PRESENTATION_EXPIRED','展示已结束',401);const c=(await read(env,s.consultation_id)).value;const d=c.deliveries.find(d=>d.id===s.delivery_id);if(c.deleted||!c.consent||!d||d.revoked)fail('NOT_FOUND','展示已撤销',404);return {c,d};}
async function imageResponse(env,asset){const o=await env.PHOTO_STORE.get(asset.key);if(!o)fail('ASSET_DELETED','图片已删除',404);return new Response(o.body,{headers:{'Content-Type':asset.mime||'image/jpeg','Cache-Control':'no-store'}});}
function detail(c){const out=current(c);out.assets=c.assets.map(({key,...asset})=>asset);out.candidates=c.candidates.map(r=>({...r,stale:!available(c,r)})).sort((a,b)=>a.mode.localeCompare(b.mode)||(b.score??-1)-(a.score??-1));for(const m of ['current','grow_out'])out.candidates.filter(r=>r.mode===m&&!r.stale).forEach((r,i)=>r.system_rank=i+1);return out;}

export async function api(request,env){
 const url=new URL(request.url),path=url.pathname.replace('/api/v1',''),method=request.method;
 if(method==='GET'&&path==='/health')return json({status:'ok',hosting:'cloudflare',storage:'aliyun-oss',storage_configured:storageReady(env),real_configured:ready(env)&&storageReady(env)});
 if(method==='GET'&&path==='/client-config')return json({demo_login_allowed:env.LOCAL_DEMO==='true'});
 if(method==='POST'&&path==='/auth/login'){
  const origin=request.headers.get('Origin');if(origin&&origin!==url.origin)fail('CSRF_INVALID','请从本站登录',403);
  const slot=Math.floor(Date.now()/60000),ip=request.headers.get('CF-Connecting-IP')||'local';
  const rate=await env.DB.prepare('INSERT INTO rate_limits VALUES(?,1) ON CONFLICT(id) DO UPDATE SET hits=hits+1 RETURNING hits').bind(await sha(ip)+':'+slot).first();if(rate.hits>10)fail('RATE_LIMITED','请求过多，请稍后重试',429);
  if(!await bootstrap(env))fail('ADMIN_NOT_CONFIGURED','请先在 Cloudflare 安全设置中配置管理员账号',503);
  const b=await request.json();if(typeof b.email!=='string'||typeof b.password!=='string'||b.password.length>200)fail('LOGIN_FAILED','账号或密码不正确',401);
  const u=await env.DB.prepare('SELECT * FROM users WHERE email=?').bind(b.email).first();
  if(!u||!equal(await password(b.password,u.password.split(':')[0]),u.password))fail('LOGIN_FAILED','账号或密码不正确',401);
  const token=uid()+uid(),csrf=uid()+uid();await env.DB.prepare('INSERT INTO sessions VALUES(?,?,?,?)').bind(await sha(token),u.id,csrf,Date.now()+28800000).run();return json({name:u.name,csrf},200,{'Set-Cookie':cookie('salon_session',token,request)});
 }
 if(path.startsWith('/presentation')){
  if(method==='POST'&&path==='/presentation/exit'){
   if(request.headers.get('X-Presentation-Action')!=='exit')fail('CSRF_INVALID','请求无效',403);const raw=cookies(request).salon_presentation;if(raw)await env.DB.prepare('DELETE FROM presentations WHERE id=?').bind(await sha(raw)).run();return json({ok:true},200,{'Set-Cookie':cookie('salon_presentation','',request,0)});
  }
  const {c,d}=await presentation(env,request);
  if(method==='GET'&&path==='/presentation')return json({customer_code:c.customer_code,delivery_id:d.id,type:d.type,demo:d.demo,candidates:d.snapshot});
  const match=path.match(/^\/presentation\/assets\/([a-f0-9]+)$/);
  if(method==='GET'&&match){if(!d.snapshot.some(r=>r.asset_id===match[1]))fail('NOT_FOUND','图片不存在',404);return imageResponse(env,resource(c,match[1],'assets'));}
  if(method==='POST'&&path==='/presentation/choice'){
   if(request.headers.get('X-Presentation-Action')!=='choose')fail('CSRF_INVALID','请求无效',403);const b=await request.json();if(!d.snapshot.some(r=>r.candidate_id===b.candidate_id))fail('NOT_FOUND','方案不存在',404);
   await mutate(env,c.id,c.salon_id,latest=>{const delivery=resource(latest,d.id,'deliveries');if(!latest.consent||delivery.revoked)fail('NOT_FOUND','展示已撤销',404);latest.feedback.push({type:'customer_selected',candidate_id:b.candidate_id,delivery_id:d.id,created_at:timestamp()});});return json({ok:true});
  }fail('NOT_FOUND','接口不存在',404);
 }
 const user=await auth(env,request);
 if(method==='GET'&&path==='/me')return json({id:user.id,name:user.name,role:user.role,csrf:user.csrf,mode:'demo',real_configured:ready(env)&&storageReady(env),image_model:env.IMAGE_MODEL,storage:env.STORAGE_PROVIDER==='local-r2'?'local-test':'aliyun-oss',storage_configured:storageReady(env),salon_name:'青禾 SALON',retention_days:30});
 if(method==='POST'&&path==='/auth/logout'){await env.DB.prepare('DELETE FROM sessions WHERE id=?').bind(user.session_id).run();return json({ok:true},200,{'Set-Cookie':cookie('salon_session','',request,0)});}
 if(method==='GET'&&path==='/consultations'){const rows=await env.DB.prepare('SELECT data FROM consultations WHERE salon_id=? ORDER BY rowid DESC').bind(user.salon_id).all();return json(rows.results.map(r=>JSON.parse(r.data)).filter(c=>!c.deleted).map(c=>{const v=current(c);delete v.candidates;delete v.assets;delete v.jobs;delete v.model_calls;delete v.deliveries;delete v.feedback;return v;}));}
 if(method==='POST'&&path==='/consultations'){
  const b=await request.json();if(typeof b.customer_code!=='string'||!b.customer_code.trim()||b.customer_code.length>40||!['demo','real'].includes(b.mode||'demo'))fail('SCHEMA_INVALID','顾客代号或生成方式无效');
  if(b.mode==='real'&&!ready(env))fail('MODEL_NOT_CONFIGURED','请先在 Cloudflare 配置两家模型密钥',503);
  const c={id:uid(),salon_id:user.salon_id,stylist_id:user.id,customer_code:b.customer_code,status:'collecting',mode:b.mode||'demo',consent:false,revision:1,profile:null,attempts_used:0,reserved_cny:0,budget_cny:null,assets:[],candidates:[],jobs:[],deliveries:[],feedback:[],model_calls:[],operations:{},created_at:timestamp()};
  await env.DB.prepare('INSERT INTO consultations VALUES(?,?,1,?)').bind(c.id,c.salon_id,JSON.stringify(c)).run();await audit(env,user,'consultation_created',c.id);return json(current(c),201);
 }
 let m=path.match(/^\/consultations\/([a-f0-9]+)(?:\/(.*))?$/);
 if(m){
  const id=m[1],action=m[2]||'',row=await read(env,id,user.salon_id),c=row.value;if(c.deleted)fail('ASSET_DELETED','咨询已删除',404);
  if(method==='GET'&&!action)return json(detail(c));
  if(method==='DELETE'&&!action){
   await mutate(env,id,user.salon_id,latest=>{const keys=[...new Set([...(latest.pending_delete_keys||[]),...latest.assets.map(a=>a.key)])];Object.assign(latest,{deleted:true,consent:false,status:'deleted',customer_code:'已删除',profile:null,analysis:null,assets:[],candidates:[],feedback:[],deliveries:[],operations:{},pending_delete_keys:keys,jobs:latest.jobs.map(j=>({id:j.id,status:'cancelled',cancel:true}))});});
   const cleaned=await cleanupPhotos(env,id);await audit(env,user,'consultation_deleted',id);return json({ok:true,cleanup_pending:!cleaned});
  }
  if(method==='POST'&&action==='consents'){const b=await request.json();if(typeof b.confirmed!=='boolean')fail('SCHEMA_INVALID','授权状态无效');await mutate(env,id,user.salon_id,latest=>{latest.consent=b.confirmed;latest.consent_record={confirmed:b.confirmed,text_version:'v1',operator:user.id,confirmed_at:timestamp()};if(!b.confirmed){latest.revision++;latest.deliveries.forEach(d=>d.revoked=true);}});return json({ok:true});}
  if(method==='POST'&&action==='photos'){
   if(!c.consent)fail('CONSENT_REQUIRED','请先确认照片使用授权');const form=await request.formData(),file=form.get('file'),view=form.get('view');if(!['front','left','right','back','top'].includes(view)||!file||typeof file.arrayBuffer!=='function')fail('PHOTO_FORMAT','照片或角度无效');if(file.size>15*1024*1024)fail('PHOTO_TOO_LARGE','照片不能超过 15 MB');
   const image=stripMetadata(new Uint8Array(await file.arrayBuffer()));if(image.width*image.height>40000000||Math.min(image.width,image.height)<160)fail('PHOTO_QUALITY_BLOCKED','照片过大或过小，请重新拍摄');
   const asset={id:uid(),kind:'original',view,mime:image.mime,width:image.width,height:image.height};asset.key=`${user.salon_id}/${id}/${asset.id}`;
   await env.PHOTO_STORE.put(asset.key,image.bytes,{httpMetadata:{contentType:image.mime}});
   try{await mutate(env,id,user.salon_id,latest=>{if(!latest.consent)fail('CONSENT_REQUIRED','照片授权已撤回');const removed=latest.assets.filter(a=>a.kind==='original'&&a.view===view).map(a=>a.key);latest.assets=latest.assets.filter(a=>!(a.kind==='original'&&a.view===view));latest.assets.push(asset);latest.pending_delete_keys=[...new Set([...(latest.pending_delete_keys||[]),...removed])];latest.revision++;latest.analysis=null;latest.status='collecting';});}catch(e){await env.PHOTO_STORE.delete(asset.key);throw e;}
   await index(env,asset.id,id,'asset');await cleanupPhotos(env,id);return json({id:asset.id,view},201);
  }
  if(method==='PUT'&&action==='profile'){
   const b=await request.json();if(!profileValid(b))fail('PROFILE_INCOMPLETE','请完整确认顾客条件');const profile=structuredClone(b);delete profile.expected_revision;
   const result=await mutate(env,id,user.salon_id,latest=>{if(latest.revision!==b.expected_revision)fail('PROFILE_REVISION_CONFLICT','条件已更新，请刷新',409);latest.revision++;latest.profile=profile;latest.confirmed_by=user.id;latest.confirmed_at=timestamp();latest.status='ready';return current(latest);});return json(result);
  }
  if(method==='POST'&&['analysis-jobs','generation-jobs'].includes(action)){
   const b=await request.json();const key=await keyed(request,action,action==='analysis-jobs'?{revision:c.revision}:b);const jid=uid();
   const result=await mutate(env,id,user.salon_id,latest=>{
    const prior=previous(latest,key);if(prior)return prior;
    if(!latest.consent)fail('CONSENT_REQUIRED','请先确认照片授权');photoReady(latest);if(activeJobs(latest).length)fail('JOB_ACTIVE','已有任务运行中',409);
    if(latest.mode==='real'&&!ready(env))fail('MODEL_NOT_CONFIGURED','模型密钥尚未配置',503);
    const analysis=action==='analysis-jobs';if(!analysis){canGenerate(env,latest,b.profile_revision);if(latest.attempts_used+latest.profile.modes.length*3>18)fail('BUDGET_EXCEEDED','本次咨询的 18 次图像尝试额度不足');latest.candidates.forEach(r=>{if(r.profile_revision===latest.revision)r.superseded=true;});latest.status='generating';}
    latest.jobs.push({id:jid,type:analysis?'analysis':'generate',phase:analysis?'analysis':'plan',profile_revision:latest.revision,modes:analysis?[]:latest.profile.modes,mode_index:0,plan_index:0,status:'queued',stage:analysis?'等待照片分析':'排队中',completed:0,target:analysis?1:latest.profile.modes.length*3,heartbeat:Date.now(),created_at:timestamp()});return remember(latest,key,{job_id:jid,status:'queued'});
   });await index(env,result.job_id,id,'job');await dispatch(env,{consultation_id:id,job_id:result.job_id});return json(result,202);
  }
  if(method==='POST'&&action==='deliveries'){
   const b=await request.json(),key=await keyed(request,'delivery',b),did=uid();const result=await mutate(env,id,user.salon_id,latest=>{
    const prior=previous(latest,key);if(prior)return prior;if(!latest.consent)fail('CONSENT_REQUIRED','授权已撤回');
    if(!Array.isArray(b.candidate_ids)||!b.candidate_ids.length||b.candidate_ids.length>9||new Set(b.candidate_ids).size!==b.candidate_ids.length)fail('DELIVERY_IMAGE_LIMIT','请选 1～9 张不同的交付图');
    if(typeof b.demo!=='boolean'||b.demo!==(latest.mode==='demo'))fail('DEMO_DELIVERY_FORBIDDEN','演示不能进入真实交付');
    if(!['preview','complete'].includes(b.delivery_type))fail('SCHEMA_INVALID','交付类型无效');
    const candidates=b.candidate_ids.map(id=>resource(latest,id,'candidates'));
    for(const r of candidates){if(!available(latest,r))fail('PROFILE_REVISION_CONFLICT','方案版本已过期',409);if(r.review!=='approved'||r.gate!=='pass'||r.issues.length||r.score==null||issues(latest.profile,r.plan,r.mode).length)fail('REVIEW_REQUIRED','只能交付已审核的合格方案');if(r.demo!==b.demo)fail('DEMO_DELIVERY_FORBIDDEN','演示不能进入真实交付');}
    if(b.delivery_type==='complete'){if(latest.profile.modes.some(m=>candidates.filter(r=>r.mode===m).length<3))fail('INSUFFICIENT_CANDIDATES','完整展示需要每种已选模式至少 3 款');if(candidates.some(r=>r.mode==='grow_out'&&r.growth.month_min==null))fail('PROFILE_INCOMPLETE','留发时间未知，只能发布条件性阶段预览');}
    const snapshot=candidates.map((r,i)=>({candidate_id:r.id,candidate_revision:r.candidate_revision,delivery_order:i+1,plan:r.plan,mode:r.mode,demo:r.demo,asset_id:r.asset_id,growth:r.growth,score:r.score}));latest.deliveries.push({id:did,type:b.delivery_type,demo:b.demo,snapshot,revoked:false,published_by:user.id,profile_revision:latest.revision,created_at:timestamp()});latest.status='delivered';return remember(latest,key,{delivery_id:did,demo:b.demo});
   });await index(env,result.delivery_id,id,'delivery');await audit(env,user,'delivery_published',id);return json(result,201);
  }
  if(method==='POST'&&action==='feedback'){
   const b=await request.json();if(!['可做','需调整','不可做'].includes(b.feasibility)||typeof b.executed!=='boolean'||!['未执行','基本一致','有偏差','明显偏差'].includes(b.actual_deviation))fail('SCHEMA_INVALID','反馈无效');await mutate(env,id,user.salon_id,latest=>{const candidate=resource(latest,b.candidate_id,'candidates');latest.feedback.push({...b,type:'stylist_actual_result',candidate_revision:candidate.candidate_revision,operator:user.id,created_at:timestamp()});});return json({ok:true});
  }
 }
 m=path.match(/^\/assets\/([a-f0-9]+)$/);if(method==='GET'&&m){const c=(await locate(env,m[1],'asset',user.salon_id)).value;if(!c.consent)fail('CONSENT_REQUIRED','授权已撤回',403);return imageResponse(env,resource(c,m[1],'assets'));}
 m=path.match(/^\/jobs\/([a-f0-9]+)(?:\/(cancel))?$/);
 if(m){const c=(await locate(env,m[1],'job',user.salon_id)).value;if(method==='GET'&&!m[2])return json(resource(c,m[1],'jobs'));if(method==='POST'&&m[2]==='cancel'){const result=await mutate(env,c.id,user.salon_id,latest=>{const j=resource(latest,m[1],'jobs');j.cancel=true;if(j.status==='queued')j.status='cancelled';latest.status='partial';return j;});return json(result);}}
 m=path.match(/^\/candidates\/([a-f0-9]+)\/(reviews|revision-jobs)$/);
 if(m&&method==='POST'){
  const c=(await locate(env,m[1],'candidate',user.salon_id)).value,b=await request.json();
  if(m[2]==='reviews'){const result=await mutate(env,c.id,user.salon_id,latest=>{const r=resource(latest,m[1],'candidates');if(!available(latest,r)||r.candidate_revision!==b.candidate_revision||b.profile_revision!==latest.revision)fail('PROFILE_REVISION_CONFLICT','方案已过期',409);if(!['approved','rejected'].includes(b.decision))fail('SCHEMA_INVALID','审核状态无效');if(b.decision==='approved'&&(!b.viewed||r.gate!=='pass'||r.issues.length||r.score==null||issues(latest.profile,r.plan,r.mode).length))fail('REVIEW_REQUIRED','请查看并解决限制后审核');if(b.decision==='rejected'&&(!Array.isArray(b.reason_codes)||!b.reason_codes.length))fail('REVIEW_REQUIRED','请选择原因');r.review=b.decision;r.reviewed_by=user.id;latest.feedback.push({type:'stylist_review',candidate_id:r.id,candidate_revision:r.candidate_revision,decision:b.decision,reason_codes:b.reason_codes||[],operator:user.id,created_at:timestamp()});return r;});return json(result);}
  const adjustments=['整体更自然','刘海露额','两侧更贴合','顶部降低蓬松','保留后区长度'];if(!adjustments.includes(b.adjustment))fail('SCHEMA_INVALID','调整项无效');const key=await keyed(request,'revision',b),jid=uid();
  const result=await mutate(env,c.id,user.salon_id,latest=>{const prior=previous(latest,key);if(prior)return prior;canGenerate(env,latest,b.profile_revision);const r=resource(latest,m[1],'candidates');if(!available(latest,r)||r.candidate_revision!==b.candidate_revision)fail('PROFILE_REVISION_CONFLICT','方案已过期',409);if(latest.attempts_used>=18)fail('BUDGET_EXCEEDED','图像次数不足');const p=structuredClone(r.plan);p.description+='；调整：'+b.adjustment;if(b.adjustment==='刘海露额')p.fringe='露额';r.superseded=true;latest.status='generating';latest.jobs.push({id:jid,type:'revision',phase:'generate',plans:[p],plan_index:0,mode_index:0,modes:[r.mode],profile_revision:latest.revision,candidate_revision:r.candidate_revision+1,previous_candidate_id:r.id,status:'queued',stage:'等待调整重做',completed:0,target:1,heartbeat:Date.now()});return remember(latest,key,{job_id:jid,status:'queued'});});await index(env,result.job_id,c.id,'job');await dispatch(env,{consultation_id:c.id,job_id:result.job_id});return json(result,202);
 }
 m=path.match(/^\/deliveries\/([a-f0-9]+)\/presentation-session$/);
 if(m&&method==='POST'){
  const c=(await locate(env,m[1],'delivery',user.salon_id)).value,d=resource(c,m[1],'deliveries');if(!c.consent||d.revoked)fail('NOT_FOUND','展示已撤销',404);const raw=uid()+uid();await env.DB.batch([env.DB.prepare('INSERT INTO presentations VALUES(?,?,?,?)').bind(await sha(raw),c.id,d.id,Date.now()+1800000),env.DB.prepare('DELETE FROM sessions WHERE id=?').bind(user.session_id)]);const headers=new Headers();headers.append('Set-Cookie',cookie('salon_session','',request,0));headers.append('Set-Cookie',cookie('salon_presentation',raw,request,1800));return json({ok:true},200,headers);
 }
 if(path==='/admin/users'&&method==='POST'){
  if(user.role!=='admin')fail('FORBIDDEN','需要管理员权限',403);const b=await request.json();if(typeof b.email!=='string'||!b.email.includes('@')||b.email.length>150||typeof b.name!=='string'||b.name.length>40||typeof b.password!=='string'||b.password.length<12||b.password.length>200||!['admin','stylist'].includes(b.role||'stylist'))fail('SCHEMA_INVALID','账号字段无效');const exists=await env.DB.prepare('SELECT id FROM users WHERE email=?').bind(b.email).first();if(exists)fail('ACCOUNT_EXISTS','账号已存在',409);const id=uid();await env.DB.prepare('INSERT INTO users VALUES(?,?,?,?,?,?)').bind(id,user.salon_id,b.email,b.name,b.role||'stylist',await password(b.password)).run();return json({id,name:b.name,role:b.role||'stylist'},201);
 }
 if(path==='/admin/metrics'&&method==='GET'){
  if(user.role!=='admin')fail('FORBIDDEN','需要管理员权限',403);const rows=await env.DB.prepare('SELECT data FROM consultations WHERE salon_id=?').bind(user.salon_id).all(),cs=rows.results.map(r=>JSON.parse(r.data));return json({consultations:cs.length,candidates:cs.reduce((n,c)=>n+c.candidates.length,0),failed_jobs:cs.reduce((n,c)=>n+c.jobs.filter(j=>['failed','provider_result_unknown'].includes(j.status)).length,0),actual_cost_cny:null,cost_status:'unreconciled'});
 }
 fail('NOT_FOUND','接口不存在',404);
}
