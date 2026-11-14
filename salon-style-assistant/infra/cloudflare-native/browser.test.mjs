import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {assertNoPhotoPayload,allowedPreviewURL,validatePhotos} from './src/browser-api.mjs';
import {storeModels,modelEnv} from './src/model-settings.mjs';
test('durable metadata rejects inline images and temporary image URLs',()=>{
 assertNoPhotoPayload({attempts:6,hash:'a'.repeat(64),approved:true});
 for(const value of [{photo:'data:image/jpeg;base64,AA=='},{nested:[{url:'https://private.example/photo'}]},{huge:'a'.repeat(13000)}])assert.throws(()=>assertNoPhotoPayload(value));
});
test('vendor preview proxy permits official HTTPS only',()=>{
 assert.ok(allowedPreviewURL('https://ark-image.tos-cn-beijing.volces.com/private.png?signature=synthetic'));
 for(const url of ['http://images.byteimg.com/a','https://127.0.0.1/a','https://evil.example/','https://volces.com.evil.example/a','https://user:secret@images.byteimg.com/a','https://images.byteimg.com:8080/a'])assert.equal(allowedPreviewURL(url),false,url);
});
test('photo fingerprint is independent of input ordering and requires real image headers',async()=>{
 const bytes=readFileSync('../../tests/fixtures/synthetic-reference.png'),data_url='data:image/png;base64,'+bytes.toString('base64');
 const a=await validatePhotos([{view:'front',data_url},{view:'left',data_url}]),b=await validatePhotos([{view:'left',data_url},{view:'front',data_url}]);assert.equal(a.fingerprint,b.fingerprint);
 await assert.rejects(()=>validatePhotos([{view:'front',data_url},{view:'front',data_url}]));
 await assert.rejects(()=>validatePhotos([{view:'front',data_url:'data:image/png;base64,AAAA'},{view:'left',data_url}]));
});
test('administrator model keys are encrypted, not persisted as plaintext',async()=>{
 let stored=null;const env={CONFIG_ENCRYPTION_KEY:btoa('0'.repeat(32)),DB:{prepare(sql){return {bind(...args){return {async run(){stored=args[1];},async first(){return stored?{encrypted:stored}:null;}};}};}}};
 const values={ARK_API_KEY:'synthetic-ark-private-value',DASHSCOPE_API_KEY:'synthetic-qwen-private-value'};
 await storeModels(env,values);assert.ok(stored&&!stored.includes(values.ARK_API_KEY)&&!stored.includes(values.DASHSCOPE_API_KEY));
 const loaded=await modelEnv(env);assert.equal(loaded.ARK_API_KEY,values.ARK_API_KEY);
});
