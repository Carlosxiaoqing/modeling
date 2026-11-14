const security = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Frame-Options': 'DENY',
  'Strict-Transport-Security': 'max-age=31536000',
  'Content-Security-Policy': "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'",
};
function protectedResponse(response, api = false) {
  const headers = new Headers(response.headers);
  for (const [k,v] of Object.entries(security)) headers.set(k,v);
  if (api) headers.set('Cache-Control', 'no-store');
  return new Response(response.body, { status: response.status, headers });
}
function failure(code, message, status=503) {
  return protectedResponse(Response.json({error:{code,message,retryable:false}}, {status}), true);
}
function originURL(value) {
  try {
    const u = new URL(value);
    if (u.protocol !== 'https:' || u.username || u.password || u.port && u.port !== '443' || u.pathname !== '/' || u.search || u.hash) return null;
    const host = u.hostname.toLowerCase();
    if (!host.includes('.') || /^[\d.]+$/.test(host) || host.includes(':') || ['.localhost','.local','.internal','.invalid'].some(s=>host.endsWith(s))) return null;
    return u;
  } catch { return null; }
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (!incoming.pathname.startsWith('/api/') && incoming.pathname !== '/api') {
      return protectedResponse(await env.ASSETS.fetch(request));
    }
    const origin = originURL(env.BACKEND_ORIGIN);
    if (!origin || !env.ORIGIN_ACCESS_TOKEN || env.ORIGIN_ACCESS_TOKEN.length < 32) {
      return failure('BACKEND_NOT_CONFIGURED', '测试服务尚未完成连接，请联系管理员。');
    }
    const target = new URL(origin);
    target.pathname = incoming.pathname;
    target.search = incoming.search;
    const headers = new Headers(request.headers);
    for (const key of ['host','forwarded','x-forwarded-host','x-forwarded-proto','x-forwarded-for','x-origin-token','cf-access-client-id','cf-access-client-secret']) headers.delete(key);
    headers.set('X-Origin-Token', env.ORIGIN_ACCESS_TOKEN);
    headers.set('X-Forwarded-Proto', 'https');
    headers.set('X-Forwarded-Host', incoming.host);
    // FastAPI accepts only the configured public origin; don't rewrite client Origin.
    try {
      const response = await fetch(target, {
        method: request.method, headers, redirect:'manual',
        body: ['GET','HEAD'].includes(request.method) ? undefined : request.body,
      });
      if (response.status >= 300 && response.status < 400) return failure('BACKEND_REDIRECT', '服务连接配置需要检查。', 502);
      return protectedResponse(response, true);
    } catch { return failure('BACKEND_UNAVAILABLE', '后台暂时不可用，请稍后再试。', 502); }
  },
};
