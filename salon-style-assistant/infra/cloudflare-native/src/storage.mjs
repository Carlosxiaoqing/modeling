import {fail} from './store.mjs';
import {read,mutate} from './store.mjs';
const encoder=new TextEncoder();
const hex=bytes=>[...new Uint8Array(bytes)].map(n=>n.toString(16).padStart(2,'0')).join('');
const escape=value=>encodeURIComponent(value).replace(/[!'()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase());
async function digest(value){return hex(await crypto.subtle.digest('SHA-256',encoder.encode(value)));}
async function hmac(key,value){const imported=await crypto.subtle.importKey('raw',typeof key==='string'?encoder.encode(key):key,{name:'HMAC',hash:'SHA-256'},false,['sign']);return crypto.subtle.sign('HMAC',imported,encoder.encode(value));}

export function storageReady(env){return env.STORAGE_PROVIDER==='local-r2'?!!env.PHOTOS:!!(env.OSS_BUCKET&&env.OSS_REGION&&env.OSS_ACCESS_KEY_ID&&env.OSS_ACCESS_KEY_SECRET);}
export function validateOSS(env){
 if(!storageReady(env))fail('STORAGE_NOT_CONFIGURED','请先配置阿里云 OSS 私有图片存储',503);
 if(!/^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(env.OSS_BUCKET)||!/^[a-z]{2}-[a-z0-9-]{2,40}$/.test(env.OSS_REGION))fail('STORAGE_NOT_CONFIGURED','OSS 桶名或地域配置无效',503);
}
export async function signedObjectRequest(env,method,key,contentType,now=new Date()){
 validateOSS(env);
 if(!['GET','PUT','DELETE'].includes(method)||!key||key.startsWith('/')||key.split('/').some(p=>!p||p==='.'||p==='..')||/[\x00-\x1f?#\\]/.test(key))fail('STORAGE_KEY_INVALID','图片存储路径无效');
 const objectKey='salon-style/'+key;
 const encoded=objectKey.split('/').map(escape).join('/');
 // Always derive the official HTTPS host; never send signed credentials to a supplied URL.
 const url=`https://${env.OSS_BUCKET}.oss-${env.OSS_REGION}.aliyuncs.com/${encoded}`;
 const time=now.toISOString().replace(/[-:]|\.\d{3}/g,''),date=time.slice(0,8);
 const headers=new Headers({'x-oss-date':time,'x-oss-content-sha256':'UNSIGNED-PAYLOAD'});
 if(contentType)headers.set('Content-Type',contentType);
 if(env.OSS_SECURITY_TOKEN)headers.set('x-oss-security-token',env.OSS_SECURITY_TOKEN);
 if(method==='PUT')headers.set('x-oss-object-acl','private');
 const canonicalHeaders=[...headers.entries()].filter(([k])=>k.startsWith('x-oss-')||['content-type','content-md5'].includes(k)).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>`${k}:${v}\n`).join('');
 const scope=`${date}/${env.OSS_REGION}/oss/aliyun_v4_request`;
 const canonical=[method,`/${env.OSS_BUCKET}/${encoded}`,'',canonicalHeaders,'','UNSIGNED-PAYLOAD'].join('\n');
 const toSign=['OSS4-HMAC-SHA256',time,scope,await digest(canonical)].join('\n');
 let signing=await hmac('aliyun_v4'+env.OSS_ACCESS_KEY_SECRET,date);
 for(const part of [env.OSS_REGION,'oss','aliyun_v4_request'])signing=await hmac(signing,part);
 headers.set('Authorization',`OSS4-HMAC-SHA256 Credential=${env.OSS_ACCESS_KEY_ID}/${scope}, Signature=${hex(await hmac(signing,toSign))}`);
 return {url,headers};
}

export function photoStore(env,fetcher=fetch){
 if(env.STORAGE_PROVIDER==='local-r2'){
  if(env.LOCAL_DEMO!=='true')fail('STORAGE_NOT_CONFIGURED','本地测试存储不能用于公开部署',503);
  return env.PHOTOS;
 }
 async function send(method,key,body,contentType){
  const {url,headers}=await signedObjectRequest(env,method,key,contentType);
  let response;
  try{response=await fetcher(url,{method,headers,body,redirect:'manual',signal:AbortSignal.timeout(45000)});}catch{fail('STORAGE_UNAVAILABLE','图片存储暂时不可用，请稍后重试',503);}
  if(response.status===404&&['GET','DELETE'].includes(method))return null;
  if(!response.ok)fail('STORAGE_UNAVAILABLE','图片存储访问失败，请检查 OSS 地域和 RAM 权限',503);
  return response;
 }
 return {
  async get(key){const response=await send('GET',key);if(!response)return null;return {body:response.body,arrayBuffer:()=>response.arrayBuffer()};},
  async put(key,bytes,options={}){await send('PUT',key,bytes,options.httpMetadata?.contentType||'application/octet-stream');},
  async delete(keys){for(const key of Array.isArray(keys)?keys:[keys])await send('DELETE',key);},
 };
}

export async function cleanupPhotos(env,id){
 const {value}=await read(env,id);const keys=value.pending_delete_keys||[];
 if(!keys.length)return true;
 try{await env.PHOTO_STORE.delete(keys);}catch{return false;}
 await mutate(env,id,null,c=>{c.pending_delete_keys=(c.pending_delete_keys||[]).filter(key=>!keys.includes(key));},{deleted:true});
 return true;
}
