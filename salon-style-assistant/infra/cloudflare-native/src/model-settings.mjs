import {fromBase64,base64} from './providers.mjs';
import {fail} from './store.mjs';
const encoder=new TextEncoder(),aad=encoder.encode('salon-model-config-v1');
async function key(env){if(!env.CONFIG_ENCRYPTION_KEY)fail('CONFIG_NOT_READY','管理员配置服务尚未就绪',503);const raw=fromBase64(env.CONFIG_ENCRYPTION_KEY);if(raw.length!==32)fail('CONFIG_NOT_READY','管理员配置服务尚未就绪',503);return crypto.subtle.importKey('raw',raw,'AES-GCM',false,['encrypt','decrypt']);}
export async function storeModels(env,values){
 const iv=crypto.getRandomValues(new Uint8Array(12));const encrypted=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad},await key(env),encoder.encode(JSON.stringify(values)));
 await env.DB.prepare('INSERT INTO secure_settings VALUES(?,?) ON CONFLICT(id) DO UPDATE SET encrypted=excluded.encrypted').bind('models',JSON.stringify({iv:base64(iv),data:base64(new Uint8Array(encrypted))})).run();
}
export async function modelEnv(env){
 const row=await env.DB.prepare('SELECT encrypted FROM secure_settings WHERE id=?').bind('models').first();if(!row)return env;
 try{const p=JSON.parse(row.encrypted),raw=await crypto.subtle.decrypt({name:'AES-GCM',iv:fromBase64(p.iv),additionalData:aad},await key(env),fromBase64(p.data));const values=JSON.parse(new TextDecoder().decode(raw));return {...env,...values};}catch{fail('CONFIG_NOT_READY','模型配置无法读取，请管理员重新保存',503);}
}
