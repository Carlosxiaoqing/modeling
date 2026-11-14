import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './src/index.mjs';

test('serves real frontend assets with security headers', async()=>{
  const response = await worker.fetch(new Request('https://salon.example.com/'), {ASSETS:{fetch:async()=>new Response('<html>studio</html>')}});
  assert.equal(response.status,200);
  assert.match(await response.text(),/studio/);
  assert.equal(response.headers.get('X-Frame-Options'),'DENY');
});
test('missing backend is explicit failure, never mock success', async()=>{
  const response=await worker.fetch(new Request('https://salon.example.com/api/v1/consultations'),{});
  assert.equal(response.status,503);
  assert.equal((await response.json()).error.code,'BACKEND_NOT_CONFIGURED');
});
test('rejects unsafe backend destinations', async()=>{
  for(const url of ['http://example.com','https://127.0.0.1','https://private.local','https://foo.invalid','https://name:secret@example.com','https://example.com/other']) {
    const response=await worker.fetch(new Request('https://salon.example.com/api/v1/health'),{BACKEND_ORIGIN:url,ORIGIN_ACCESS_TOKEN:'x'.repeat(32)});
    assert.equal(response.status,503,url);
  }
});
test('forwards multipart/CSRF/cookie and replaces forged origin credentials', async()=>{
  const previous=globalThis.fetch;
  try {
    let seen;
    globalThis.fetch=async(url, options)=>{ seen={url:String(url),...options};return new Response('{"ok":true}',{headers:{'Set-Cookie':'salon_session=test; HttpOnly; Secure'}}); };
    const request=new Request('https://salon.example.com/api/v1/consultations?q=1',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':'csrf','Cookie':'salon_session=user','X-Origin-Token':'forged','X-Forwarded-Host':'evil.example'},body:'{}'});
    const response=await worker.fetch(request,{BACKEND_ORIGIN:'https://backend.example.com',ORIGIN_ACCESS_TOKEN:'x'.repeat(32)});
    assert.equal(seen.url,'https://backend.example.com/api/v1/consultations?q=1');
    assert.equal(seen.headers.get('X-Origin-Token'),'x'.repeat(32));
    assert.equal(seen.headers.get('X-Forwarded-Host'),'salon.example.com');
    assert.equal(seen.headers.get('X-CSRF-Token'),'csrf');
    assert.equal(seen.headers.get('Cookie'),'salon_session=user');
    assert.equal(seen.redirect,'manual');
    assert.equal(response.headers.get('Cache-Control'),'no-store');
    assert.match(response.headers.get('Set-Cookie'),/Secure/);
  } finally { globalThis.fetch=previous; }
});
test('never follows origin redirects with origin credentials',async()=>{
  const previous=globalThis.fetch;
  try {
    globalThis.fetch=async()=>new Response(null,{status:302,headers:{Location:'https://elsewhere.example/'}});
    const response=await worker.fetch(new Request('https://salon.example.com/api/v1/health'),{BACKEND_ORIGIN:'https://backend.example.com',ORIGIN_ACCESS_TOKEN:'x'.repeat(32)});
    assert.equal(response.status,502);
  } finally { globalThis.fetch=previous; }
});
