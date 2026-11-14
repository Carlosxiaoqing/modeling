export const uid=()=>crypto.randomUUID().replaceAll('-','');
export const timestamp=()=>new Date().toISOString();
export const fail=(code,message,status=422)=>{throw Object.assign(new Error(message),{code,status});};
export async function sha(value){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export async function audit(env,user,action,resource){await env.DB.prepare('INSERT INTO audit VALUES(?,?,?,?,?,?)').bind(uid(),user.salon_id,user.id,action,resource,timestamp()).run();}
export async function read(env,id,salon){
 const row=await env.DB.prepare('SELECT * FROM consultations WHERE id=?').bind(id).first();
 if(!row||salon&&row.salon_id!==salon)fail('NOT_FOUND','咨询不存在',404);
 return {...row,value:JSON.parse(row.data)};
}
export async function mutate(env,id,salon,fn,{deleted=false}={}){
 for(let retry=0;retry<5;retry++){
  const row=await read(env,id,salon);
  if(row.value.deleted&&!deleted)fail('ASSET_DELETED','咨询已删除',404);
  const result=fn(row.value);
  const update=await env.DB.prepare('UPDATE consultations SET data=?,version=version+1 WHERE id=? AND version=?').bind(JSON.stringify(row.value),id,row.version).run();
  if(update.meta.changes===1)return result;
 }
 fail('PROFILE_REVISION_CONFLICT','咨询已被更新，请刷新后重试',409);
}
export async function locate(env,id,kind,salon){
 const entry=await env.DB.prepare('SELECT * FROM resources WHERE id=? AND kind=?').bind(id,kind).first();
 if(!entry)fail('NOT_FOUND','资源不存在',404);
 const row=await read(env,entry.consultation_id,salon);
 if(row.value.deleted)fail('ASSET_DELETED','咨询已删除',404);
 return row;
}
export async function index(env,id,parent,kind){await env.DB.prepare('INSERT OR IGNORE INTO resources VALUES(?,?,?)').bind(id,parent,kind).run();}
export async function keyed(request,operation,body){
 const key=request.headers.get('Idempotency-Key');
 if(!key||key.length>120)fail('IDEMPOTENCY_REQUIRED','缺少有效操作编号');
 const canonical=v=>Array.isArray(v)?v.map(canonical):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])])):v;
 return {id:await sha(operation+':'+key),fingerprint:await sha(JSON.stringify(canonical(body)))};
}
export function previous(c,key){const saved=c.operations[key.id];if(saved&&saved.fingerprint!==key.fingerprint)fail('IDEMPOTENCY_CONFLICT','同一操作编号的内容不同',409);return saved?.result;}
export function remember(c,key,result){c.operations[key.id]={fingerprint:key.fingerprint,result};return result;}
export const activeJobs=c=>c.jobs.filter(j=>['queued','running'].includes(j.status));
export function live(c,j){return !c.deleted&&c.consent&&!j.cancel&&c.revision===j.profile_revision;}
export function current(c){const result=structuredClone(c);delete result.operations;delete result.pending_delete_keys;return result;}
