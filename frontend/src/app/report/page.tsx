'use client';
import {useState} from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import {Activity,ClipboardCheck,MessageCircle} from 'lucide-react';
import {VoicePanel} from '@/components/VoicePanel';
import {createJsonClient,errorMessage} from '@/lib/api';
const api=createJsonClient();
type Receipt={id:string;status:string;issue_type:string;location:string;reported_correction?:string};
type ResidentCall={status:string;intake:Record<string,string>;live_caption?:{text:string};transcript:{id:string;role:string;text:string}[];receipt?:Receipt;receipts?:Receipt[];error?:string};
const label=(value:string)=>value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());

export default function ReportPage(){
  const [session,setSession]=useState<{id:string;token:string}|null>(null);
  const {data:health}=useSWR<{voice_configured:boolean}>('/health',api,{refreshInterval:10000});
  const {data:call,error}=useSWR<ResidentCall>(session?['resident-call',session.id,session.token]:null,
    ([,id,token]:[string,string,string])=>api(`/public/calls/${id}`,{headers:{Authorization:`Bearer ${token}`}}),{refreshInterval:1000});
  return <><header className="topbar"><div className="brand"><span className="brand-icon"><Activity size={22}/></span><strong>EffiGov</strong><span className="brand-divider"/><span>Resident services</span></div><Link className="resident-entry" href="/">Staff workspace →</Link></header>
    <main className="resident-page"><div className="page-heading"><div className="eyebrow">PUBLIC DEMO · NO SIGN-IN NEEDED</div><h1>A service issue? Let’s talk.</h1><p className="muted">Report missed collection, a pothole, a streetlight issue, or check a request you’ve already made.</p></div>
      <div className="resident-workspace"><VoicePanel publicMode configured={health?.voice_configured??false} onCall={(id,token)=>{if(token)setSession({id,token})}}/>
        <section className="panel resident-conversation"><div className="eyebrow">YOUR CONVERSATION</div><h2>{call?.status==='ended'?'Call complete':'We’re here to listen.'}</h2>
          {!session?<><p className="muted">Start a call and tell Effi what happened. You can speak or type during the call.</p><ol className="resident-steps"><li>Describe the issue and where it is.</li><li>Give a name and contact number.</li><li>Confirm the details to get a case number.</li></ol><p className="demo-notice">This is a demonstration, not a live municipal service. Use fictional details. For an emergency, call 911 or your local emergency number.</p></>:<>
            {(call?.receipts??(call?.receipt?[call.receipt]:[])).map(receipt=><div key={receipt.id} className="resident-receipt"><ClipboardCheck size={22}/><div><div className="eyebrow">CONFIRMED CASE</div><strong>{receipt.id}</strong><p>{label(receipt.issue_type)} · {label(receipt.status)}<br/>{receipt.reported_correction?<>Reported correction: {receipt.reported_correction}<br/>Awaiting staff review · original field: {receipt.location}</>:receipt.location}</p></div></div>)}
            {!call?.receipt&&call?.intake&&Object.keys(call.intake).length>0&&<div className="intake-preview"><div className="eyebrow">DETAILS COLLECTED · NOT YET A SAVED CASE</div>{Object.entries(call.intake).map(([key,value])=><p key={key}><strong>{label(key)}:</strong> {key==='issue_type'?label(value):value}</p>)}</div>}
            {error&&<p className="error" role="alert">{errorMessage(error)}</p>}{call?.error&&<p className="error" role="alert">{call.error}</p>}
            {call?.live_caption&&<div className="live-caption" aria-live="polite"><div className="eyebrow">LIVE CAPTION · MAY CHANGE</div><p>{call.live_caption.text}</p></div>}
            <div className="transcript" aria-live="polite" aria-relevant="additions text">{call?.transcript?.length?call.transcript.map(turn=><article key={turn.id} className={turn.role}><div className="turn-meta">{turn.role==='user'?'You':'Effi'}</div><p>{turn.text}</p></article>):<div className="empty"><MessageCircle size={26}/><p>Your conversation will appear here.</p></div>}</div>
            <p className="muted resident-recording">Staff can review this call. Keep your case number for a follow-up call.</p>
          </>}
        </section></div></main><footer>EffiGov Engineering Take Home <span>Resident reporting · Staff review</span></footer></>;
}
