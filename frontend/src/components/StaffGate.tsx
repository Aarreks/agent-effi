'use client';
import {useState} from 'react';
import useSWR,{useSWRConfig} from 'swr';
import {Activity} from 'lucide-react';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {createJsonClient,errorMessage} from '@/lib/api';
const api=createJsonClient();

export function StaffGate({children}:{children:React.ReactNode}) {
  const pathname=usePathname();
  return pathname==='/report'?<>{children}</>:<StaffAccess>{children}</StaffAccess>;
}

function StaffAccess({children}:{children:React.ReactNode}) {
  const {data,error,mutate}=useSWR<{authenticated:boolean}>('/auth/me',api,{refreshInterval:60000});
  const {mutate:clearCache}=useSWRConfig();
  const [password,setPassword]=useState('');
  const [failure,setFailure]=useState('');const [busy,setBusy]=useState(false);
  async function login(event:React.FormEvent){event.preventDefault();setBusy(true);setFailure('');try{await api('/auth/login',{method:'POST',body:JSON.stringify({password})});setPassword('');await mutate()}catch(e){setFailure(errorMessage(e))}finally{setBusy(false)}}
  async function logout(){await api('/auth/logout',{method:'POST'});await mutate({authenticated:false},false);await clearCache(k=>typeof k==='string'&&k!='/auth/me',undefined,{revalidate:false})}
  if(data?.authenticated)return <>{children}<button className="staff-logout" onClick={()=>void logout()}>Sign out</button></>;
  return <main className="signin"><section className="panel"><span className="brand-icon"><Activity size={24}/></span><div className="eyebrow">EFFIGOV VOICE DESK</div><h1>Staff sign-in</h1><p className="muted">Open your resident services workspace.</p>{!data&&!error?<p>Checking access…</p>:<form onSubmit={login}><label htmlFor="staff-password">Staff password</label><input id="staff-password" type="password" autoComplete="current-password" required value={password} onChange={e=>setPassword(e.target.value)}/><button className="primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form>}{(failure||error)&&<p className="error" role="alert">{failure||errorMessage(error)}</p>}<Link className="resident-entry" href="/report">Just reporting an issue? Talk to Effi →</Link></section></main>;
}
