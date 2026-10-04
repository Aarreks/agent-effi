"""Create local demo credentials only when absent. Never print credential values."""
import os
from pathlib import Path
import secrets
from dotenv import dotenv_values,set_key

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'.env'
if not path.exists():path.write_text((ROOT/'.env.example').read_text(),encoding='utf-8')
values=dotenv_values(path)
for key,size in (('STAFF_PASSWORD',18),('SESSION_SECRET',32),('VOICE_WORKER_TOKEN',32)):
    if not values.get(key):
        value=secrets.token_urlsafe(size)
        set_key(str(path),key,value)
        values[key]=value
login=ROOT/'data'/'staff-login.txt'
login.parent.mkdir(parents=True,exist_ok=True)
login.write_text('EffiGov Voice Desk staff sign-in\n\nPassword: '+values['STAFF_PASSWORD']+'\n\nUse this password on the localhost sign-in page. Keep this file out of shared source code.\n',encoding='utf-8')
if os.name!='nt':
    path.chmod(0o600);login.chmod(0o600)
print('Staff and voice-worker credentials configured locally. Staff sign-in details: data/staff-login.txt')
