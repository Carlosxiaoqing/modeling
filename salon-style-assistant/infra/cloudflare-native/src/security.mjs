import {sha,uid,fail} from './store.mjs';
const encoder=new TextEncoder();
export async function password(value,salt=uid()){
 const key=await crypto.subtle.importKey('raw',encoder.encode(value),'PBKDF2',false,['deriveBits']);
 const bits=await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt:encoder.encode(salt),iterations:100000},key,256);
 return salt+':'+[...new Uint8Array(bits)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
export function equal(a,b){if(a.length!==b.length)return false;let x=0;for(let i=0;i<a.length;i++)x|=a.charCodeAt(i)^b.charCodeAt(i);return x===0;}
export function cookies(request){return Object.fromEntries((request.headers.get('Cookie')||'').split(';').map(s=>s.trim().split('=')));}
export function cookie(name,value,request,maxAge=28800){return `${name}=${value}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${new URL(request.url).protocol==='https:'?'; Secure':''}`;}
export async function auth(env,request){
 const raw=cookies(request).salon_session;if(!raw)fail('UNAUTHENTICATED','请先登录',401);
 const row=await env.DB.prepare('SELECT s.*,u.salon_id,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=? AND s.expires>?').bind(await sha(raw),Date.now()).first();
 if(!row)fail('UNAUTHENTICATED','请重新登录',401);
 if(!['GET','HEAD'].includes(request.method)&&!equal(request.headers.get('X-CSRF-Token')||'',row.csrf))fail('CSRF_INVALID','会话校验失败，请重新登录',403);
 return {...row,id:row.user_id,session_id:row.id};
}
export async function bootstrap(env){
 const exists=await env.DB.prepare('SELECT id FROM users LIMIT 1').first();if(exists)return true;
 const email=env.ADMIN_EMAIL,pw=env.ADMIN_PASSWORD;
 if(!email||!pw||pw.length<12)return false;
 if(env.LOCAL_DEMO!=='true'&&(email==='demo@salon.local'||pw==='SalonDemo2026!'))return false;
 await env.DB.prepare('INSERT OR IGNORE INTO users VALUES(?,?,?,?,?,?)').bind(uid(),'salon-primary',email,'门店管理员','admin',await password(pw)).run();return true;
}
export function hardened(response,api=true){
 const headers=new Headers(response.headers);
 for(const [k,v]of Object.entries({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Strict-Transport-Security':'max-age=31536000','Content-Security-Policy':"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"}))headers.set(k,v);
 if(api)headers.set('Cache-Control','no-store');
 return new Response(response.body,{status:response.status,headers});
}
