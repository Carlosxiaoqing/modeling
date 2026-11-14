import {api} from './api.mjs';
import {hardened} from './security.mjs';
import {processMessage,recover} from './jobs.mjs';
import {photoStore} from './storage.mjs';
import {browserAPI} from './browser-api.mjs';
export default {
 async fetch(request,env){
  try{
   const path=new URL(request.url).pathname;
   if(path.startsWith('/api/'))return hardened(await (env.WORKFLOW_MODE==='browser'?browserAPI(request,env):api(request,{...env,PHOTO_STORE:photoStore(env)})));
   return hardened(await env.ASSETS.fetch(request),false);
  }catch(error){return hardened(Response.json({error:{code:error.code||'INTERNAL_ERROR',message:error.code?error.message:'操作未完成，请联系管理员',retryable:false,request_id:crypto.randomUUID()}},{status:error.status||500}));}
 },
 async queue(batch,env){const runtime={...env,PHOTO_STORE:photoStore(env)};for(const message of batch.messages){await processMessage(runtime,message.body);message.ack();}},
 async scheduled(event,env,ctx){ctx.waitUntil(recover({...env,PHOTO_STORE:photoStore(env)}));},
};
