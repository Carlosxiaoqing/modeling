import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {signedObjectRequest,photoStore,storageReady,cleanupPhotos} from './src/storage.mjs';
const env={OSS_BUCKET:'synthetic-bucket',OSS_REGION:'cn-beijing',OSS_ACCESS_KEY_ID:'syntheticAccessKey',OSS_ACCESS_KEY_SECRET:'syntheticSecret'};
const vectors=JSON.parse(readFileSync(new URL('./oss-signing-vectors.json',import.meta.url)));
for(const vector of vectors)test('OSS V4 matches official Python SDK: '+vector.method,async()=>{
 const config={...env,OSS_SECURITY_TOKEN:vector.securityToken};
 const request=await signedObjectRequest(config,vector.method,vector.key,vector.contentType,new Date('2026-11-11T08:00:00Z'));
 assert.equal(request.headers.get('Authorization'),vector.authorization);
 assert.ok(request.url.startsWith('https://synthetic-bucket.oss-cn-beijing.aliyuncs.com/salon-style/'));
 assert.equal(request.headers.get('x-oss-security-token'),vector.securityToken);
 if(vector.method==='PUT')assert.equal(request.headers.get('x-oss-object-acl'),'private');
});
test('private object lifecycle uses signed HTTPS and no redirects',async()=>{
 const calls=[];const memory=new Map();
 const store=photoStore(env,async(url,options)=>{calls.push({url,...options});if(options.method==='PUT'){memory.set(url,options.body);return new Response(null,{status:200});}if(options.method==='DELETE'){memory.delete(url);return new Response(null,{status:204});}return memory.has(url)?new Response(memory.get(url)):new Response(null,{status:404});});
 await store.put('salon-primary/c1/a',new Uint8Array([1,2,3]),{httpMetadata:{contentType:'image/jpeg'}});
 assert.deepEqual([...new Uint8Array(await(await store.get('salon-primary/c1/a')).arrayBuffer())],[1,2,3]);
 await store.delete(['salon-primary/c1/a']);assert.equal(await store.get('salon-primary/c1/a'),null);
 assert.ok(calls.every(c=>c.redirect==='manual'&&c.headers.has('Authorization')));
 assert.equal(calls[0].headers.get('Content-Type'),'image/jpeg');
});
test('unsafe configuration and traversal fail before network access',async()=>{
 for(const config of [{...env,OSS_BUCKET:'localhost/path'},{...env,OSS_REGION:'cn-beijing.evil.example'},{}])await assert.rejects(()=>signedObjectRequest(config,'GET','a'));
 for(const key of ['../secret','/absolute','a/../b','a?uploadId=evil','a#x'])await assert.rejects(()=>signedObjectRequest(env,'GET',key));
 assert.equal(storageReady({}),false);
});
test('OSS permission and redirect failures are explicit and never leak response bodies',async()=>{
 for(const status of [302,403,500]){
  const store=photoStore(env,async()=>new Response('private diagnostic data',{status}));
  await assert.rejects(()=>store.get('salon-primary/c1/a'),e=>e.code==='STORAGE_UNAVAILABLE'&&!e.message.includes('private diagnostic'));
 }
});
test('public deployment cannot use the local test binding',()=>{
 assert.throws(()=>photoStore({STORAGE_PROVIDER:'local-r2',PHOTOS:{}}),e=>e.code==='STORAGE_NOT_CONFIGURED');
});
test('failed physical deletion remains durable and can be retried after access is revoked',async()=>{
 let row={id:'consultation',salon_id:'salon',version:1,data:JSON.stringify({deleted:true,pending_delete_keys:['old-photo']})};
 const db={prepare(sql){return {bind(...args){return {async first(){return structuredClone(row);},async run(){assert.ok(sql.startsWith('UPDATE'));if(args[2]!==row.version)return {meta:{changes:0}};row={...row,data:args[0],version:row.version+1};return {meta:{changes:1}};}};}};}};
 const config={DB:db,PHOTO_STORE:{delete:async()=>{throw new Error('synthetic outage');}}};
 assert.equal(await cleanupPhotos(config,'consultation'),false);
 assert.deepEqual(JSON.parse(row.data).pending_delete_keys,['old-photo']);
 config.PHOTO_STORE.delete=async keys=>assert.deepEqual(keys,['old-photo']);
 assert.equal(await cleanupPhotos(config,'consultation'),true);
 assert.deepEqual(JSON.parse(row.data).pending_delete_keys,[]);
 assert.equal(JSON.parse(row.data).deleted,true);
});
