import { spawnSync } from 'node:child_process';
// This script never starts an interactive OAuth flow or invents credentials.
if (!process.env.CLOUDFLARE_API_TOKEN) {
  console.error('Missing CLOUDFLARE_API_TOKEN. Configure it securely for api.cloudflare.com.');
  process.exit(2);
}
// This is the external-origin gateway variant. The user selected native Cloudflare
// hosting, whose backend/storage adaptation must be completed before publishing.
if (!process.env.BACKEND_ORIGIN) {
  console.error('Gateway backend is not configured. Do not publish a frontend-only shell. For native Cloudflare hosting, complete the D1/R2/queue backend adaptation first.');
  process.exit(2);
}
const result = spawnSync('wrangler', ['deploy'], {stdio:'inherit', env:{...process.env,WRANGLER_SEND_METRICS:'false'}});
process.exit(result.status ?? 1);
