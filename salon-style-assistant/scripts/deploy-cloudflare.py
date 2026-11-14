"""Provision the native Cloudflare deployment. Provider credentials are never copied; bootstrap login is saved privately.

Run with backend/.venv/bin/python scripts/deploy-cloudflare.py from project root.
Browser-only images: no R2, OSS, COS, image bucket, queue or service purchase.
"""
import json
import os
import secrets
import subprocess
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
RUNTIME.mkdir(exist_ok=True)
TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
if not TOKEN: raise SystemExit('Missing Cloudflare authorization; configure CLOUDFLARE_API_TOKEN securely.')
client = httpx.Client(base_url='https://api.cloudflare.com/client/v4', headers={'Authorization':'Bearer '+TOKEN}, timeout=60)

def call(method,path,body=None):
    response = client.request(method,path,json=body)
    data = response.json()
    if not response.is_success or data.get('success') is False:
        errors = data.get('errors') or []
        codes = [e.get('code') for e in errors]
        raise SystemExit(f'Cloudflare {method} operation failed: HTTP {response.status_code}, codes={codes}. No automatic plan purchase or token changes.')
    return data.get('result')

accounts = call('GET','/accounts')
saved = RUNTIME / 'cloudflare-account.json'
account = json.loads(saved.read_text()).get('account_id') if saved.exists() else None
if account not in [a['id'] for a in accounts]:
    if len(accounts)!=1: raise SystemExit('Authorization exposes multiple accounts; select a target account before deployment.')
    account = accounts[0]['id']
prefix = f'/accounts/{account}'
# Browser-session workflow: no photo bucket, queue or persistent image service.
plan_path = RUNTIME / 'cloudflare-native-deployment.json'
if plan_path.exists():
    plan = json.loads(plan_path.read_text())
    if plan['account_id']!=account: raise SystemExit('Deployment account mismatch; refusing to replace another account deployment.')
else:
    plan = {'account_id':account,'name':'qinghe-salon-'+secrets.token_hex(3)}
    plan_path.write_text(json.dumps(plan,indent=2))
name=plan['name']
databases = call('GET',prefix+'/d1/database')
db = next((d for d in databases if d['name']==name),None)
if not db: db=call('POST',prefix+'/d1/database',{'name':name})
config = json.loads((ROOT/'infra/cloudflare-native/wrangler.jsonc').read_text())
config.update({'account_id':account,'name':name,'main':str(ROOT/'infra/cloudflare-native/src/index.mjs')})
config['assets']['directory']=str(ROOT/'apps/web/dist')
config['d1_databases'][0].update(database_name=name,database_id=db['uuid'],migrations_dir=str(ROOT/'infra/cloudflare-native/migrations'))
config.pop('r2_buckets',None)
config.pop('queues',None)
config.pop('triggers',None)
config['vars']['WORKFLOW_MODE']='browser'
config['vars']['ADMIN_EMAIL']='owner@salon.local'
config_file=RUNTIME/'wrangler.native.json'
config_file.write_text(json.dumps(config,indent=2))
env={**os.environ,'WRANGLER_SEND_METRICS':'false','XDG_CONFIG_HOME':str(RUNTIME/'cloudflare-config')}
cwd=ROOT/'infra/cloudflare-native'
wrangler=str(cwd/'node_modules/.bin/wrangler')
for migration in sorted((ROOT/'infra/cloudflare-native/migrations').glob('*.sql')):
    # Official D1 query API avoids presigned bulk-import object hosts.
    result=call('POST',prefix+f"/d1/database/{db['uuid']}/query",{'sql':migration.read_text()})
    if any(item.get('success') is False for item in result): raise SystemExit('D1 migration did not succeed.')
    print('D1 migration applied:',migration.name,flush=True)
subprocess.run([wrangler,'deploy','--config',str(config_file)],cwd=cwd,env=env,check=True)
# Generate only a fresh app credential; never upload the platform's model-key placeholders.
remote_secrets = call('GET',prefix+f'/workers/scripts/{name}/secrets')
if not any(s['name']=='CONFIG_ENCRYPTION_KEY' for s in remote_secrets):
    import base64
    call('PUT',prefix+f'/workers/scripts/{name}/secrets',{'name':'CONFIG_ENCRYPTION_KEY','type':'secret_text','text':base64.b64encode(secrets.token_bytes(32)).decode()})
if not any(s['name']=='ADMIN_PASSWORD' for s in remote_secrets):
    pw=secrets.token_urlsafe(24)
    access_path=RUNTIME/'cloudflare-login.txt'
    access_path.write_text('Account: owner@salon.local\nPassword: '+pw+'\nOpen Model Settings in the protected website and enter your Qwen and Ark API keys before real use. Images are kept only in browser memory; download before leaving.\n')
    access_path.chmod(0o600)
    call('PUT',prefix+f'/workers/scripts/{name}/secrets',{'name':'ADMIN_PASSWORD','type':'secret_text','text':pw})
subdomain=call('GET',prefix+'/workers/subdomain')['subdomain']
plan.update(database_id=db['uuid'],url=f'https://{name}.{subdomain}.workers.dev',model_secrets_pending=True,storage='none',workflow_mode='browser')
plan_path.write_text(json.dumps(plan,indent=2))
print('Worker deployed. URL metadata and private login instructions saved under .runtime; public verification still required.')
