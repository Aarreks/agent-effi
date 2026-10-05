'use client';
import {useEffect,useRef,useState} from 'react';
import useSWR,{useSWRConfig} from 'swr';
import {ArrowUpRight,Check,ClipboardList,Headphones,Search,Activity,Phone,MapPin,User,Clock} from 'lucide-react';
import {VoicePanel} from '@/components/VoicePanel';
import {CallInsights} from '@/components/CallInsights';
import Link from 'next/link';
import {createJsonClient,errorMessage} from '@/lib/api';
import type {CaseRecord,CaseStatus,CallRecord} from '@/lib/types';
const api=createJsonClient();
const statuses:CaseStatus[]=['new','in_progress','resolved'];
const label=(value:string)=>value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
const time=(value:string)=>new Date(value).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});

function Badge({value}:{value:string}){return <span className={`badge ${value}`}>{label(value)}</span>}

function CaseDetail({id,onCall}:{id:string;onCall:(id:string)=>void}) {
  const {data,error,mutate}=useSWR<CaseRecord>(`/cases/${id}`,api,{refreshInterval:3000});
  const {data:calls=[]}=useSWR<CallRecord[]>('/calls',api);
  const {mutate:allMutate}=useSWRConfig();
  const [note,setNote]=useState('');const [status,setStatus]=useState<CaseStatus>('new');
  const [location,setLocation]=useState('');const [locationEdited,setLocationEdited]=useState(false);const [reviewAddress,setReviewAddress]=useState(false);
  const [saving,setSaving]=useState(false);const [saveError,setSaveError]=useState('');const [saved,setSaved]=useState(false);
  useEffect(()=>{if(data)setStatus(data.status)},[data?.status,id]);
  useEffect(()=>{if(data&&!locationEdited)setLocation(data.location||'')},[data?.location,locationEdited]);
  useEffect(()=>{setNote('');setSaveError('');setSaved(false)},[id]);
  async function save(event:React.FormEvent){event.preventDefault();if(!data)return;setSaving(true);setSaveError('');setSaved(false);try{await api(`/cases/${id}`,{method:'PATCH',body:JSON.stringify({revision:data.revision,status,...(note.trim()?{note:note.trim()}:{}),...(location.trim()!==(data.location||'')||reviewAddress?{location:location.trim()}:{})})});setNote('');setLocationEdited(false);setReviewAddress(false);setSaved(true);await mutate();await allMutate(k=>typeof k==='string'&&(k.startsWith('/cases')||k.startsWith('/calls')))}catch(e){setSaveError(errorMessage(e));void mutate()}finally{setSaving(false)}}
  if(error)return <div role="alert" className="error">{errorMessage(error)}</div>;
  if(!data)return <div className="empty">Loading case…</div>;
  return <section className="panel case-detail">
    <div className="section-head"><div><div className="eyebrow">CASE DETAIL · REVISION {data.revision}</div><h2>{data.id}</h2></div><Badge value={data.status}/></div>
    <h3 className="issue-title">{label(data.issue_type)}</h3><p className="description">{data.description}</p>
    <dl className="resident"><div><dt><User size={15}/>Resident</dt><dd>{data.name}</dd></div><div><dt><Phone size={15}/>Contact</dt><dd>{data.phone}</dd></div><div><dt><MapPin size={15}/>Location</dt><dd>{data.location||'Not provided'}</dd></div></dl>
    <form onSubmit={save} className="triage"><div className="section-head"><h3>Staff triage</h3>{saved&&<span className="saved"><Check size={14}/>Saved</span>}</div><label htmlFor="status">Status</label><select id="status" value={status} onChange={e=>{setStatus(e.target.value as CaseStatus);setSaved(false)}}>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select><label htmlFor="location">Official address or location</label><input id="location" value={location} maxLength={300} onChange={e=>{setLocation(e.target.value);setLocationEdited(true);setSaved(false)}}/><p className="muted">Saving an address replaces the official location and closes earlier address corrections. The original notes stay in the history.</p><label className="address-review"><input type="checkbox" checked={reviewAddress} onChange={e=>{setReviewAddress(e.target.checked);setSaved(false)}}/> Keep this address and mark earlier corrections reviewed</label><label htmlFor="note">Add a note</label><textarea id="note" value={note} onChange={e=>{setNote(e.target.value);setSaved(false)}} placeholder="Next step, context, or resolution details…" rows={3}/><button className="primary" disabled={saving||(!note.trim()&&status===data.status&&location.trim()===(data.location||'')&&!reviewAddress)}>{saving?'Saving…':'Save changes'}</button>{saveError&&<p role="alert" className="error">{saveError}</p>}</form>
    <h3>Notes <span className="count">{data.notes.length}</span></h3><div className="notes">{data.notes.length?data.notes.map((n,i)=><article key={i}><p>{n.text}</p><small>{label(n.actor)} · {time(n.at)}</small></article>):<p className="muted">No notes yet.</p>}</div>
    <h3>Related calls</h3><div className="related">{calls.filter(c=>c.case_id===id).map(c=><button key={c.id} onClick={()=>onCall(c.id)}><Headphones size={15}/>{time(c.started_at)} · {label(c.status)} <ArrowUpRight size={15}/></button>)}</div>
    <details className="audit"><summary>Change history · {data.audit?.length??0} events</summary>{data.audit?.map((a,i)=><article key={i}><small>{time(a.at)} · {label(a.actor)} · revision {a.revision}</small>{Object.entries(a.fields).map(([field,value])=><p key={field}><strong>{label(field)}</strong> {field==='notes'?'Note added':`${value.before==null?'—':String(value.before)} → ${String(value.after)}`}</p>)}</article>)}</details>
  </section>
}

function CallDetail({id,onCase}:{id:string;onCase:(id:string)=>void}){
  const {data,error,mutate}=useSWR<CallRecord>(`/calls/${id}`,api,{refreshInterval:3000});
  const panel=useRef<HTMLElement>(null);
  const loaded=Boolean(data);
  useEffect(()=>{if(loaded)panel.current?.scrollIntoView({block:'start',behavior:'smooth'})},[id,loaded]);
  const [retryError,setRetryError]=useState('');
  async function retry(){setRetryError('');try{await api(`/calls/${id}/analyze`,{method:'POST'});void mutate()}catch(e){setRetryError(errorMessage(e))}}
  if(error)return <p className="error" role="alert">{errorMessage(error)}</p>;
  if(!data)return <div className="empty">Loading call…</div>;
  return <section ref={panel} className="panel call-detail"><div className="section-head"><div><div className="eyebrow">CALL · {time(data.started_at)} {data.mode==='test'?'· API TEST':''}</div><h2>Conversation</h2></div><Badge value={data.status}/></div>
    {data.error&&<p className="error" role="alert">{data.error}</p>}
    {data.case_id?<button className="case-link" onClick={()=>onCase(data.case_id!)}><ClipboardList size={16}/> {data.case_id}<ArrowUpRight size={15}/></button>:<p className="muted">No case linked yet.</p>}
    <h3>Live transcript <span className="count">{data.transcript?.length??0} turns</span></h3>
    {data.live_caption&&<div className="live-caption" aria-live="polite"><div className="eyebrow">LIVE CAPTION · MAY CHANGE</div><p>{data.live_caption.text}</p></div>}
    <div className="transcript" aria-live="polite" aria-relevant="additions text">{data.transcript?.length?data.transcript.map(t=><article className={t.role} key={t.id}><div className="turn-meta">{t.role==='user'?'Resident':'Effi'} <time>{time(t.at)}</time></div><p>{t.text}</p></article>):<div className="empty"><Headphones size={25}/><p>The transcript will appear here as the conversation progresses.</p></div>}</div>
    <CallInsights call={data}/>
    <div className="analysis"><div className="section-head"><h3>Call analysis</h3><Badge value={data.analysis_status}/></div>{data.analysis?<><p>{data.analysis.summary}</p><dl className="analysis-fields">{[['Caller',data.analysis.caller_name],['Phone',data.analysis.phone],['Issue',data.analysis.issue_type],['Location',data.analysis.location],['Outcome',data.analysis.outcome]].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v||'Not stated'}</dd></div>)}</dl>{data.analysis.follow_up.length>0&&<><h4>Staff follow-up</h4><ul>{data.analysis.follow_up.map((f,i)=><li key={i}>{f}</li>)}</ul></>}</>:<p className="muted">{data.analysis_error||'Structured analysis runs after the call ends.'}</p>}{data.status==='ended'&&data.analysis_status!=='complete'&&<button onClick={retry}>Retry analysis</button>}{retryError&&<p className="error" role="alert">{retryError}</p>}</div>
  </section>
}

export default function Home(){
  const [search,setSearch]=useState('');const [filter,setFilter]=useState('');const [tab,setTab]=useState<'cases'|'calls'>('cases');
  const [caseId,setCaseId]=useState<string|null>(null);const [callId,setCallId]=useState<string|null>(null);
  const [live,setLive]=useState(false);const {mutate}=useSWRConfig();
  const {data:health}=useSWR<{ok:boolean;voice_configured:boolean}>('/health',api,{refreshInterval:10000});
  const {data:cases=[],error:caseError,isLoading}=useSWR<CaseRecord[]>(`/cases?search=${encodeURIComponent(search)}&status=${filter}`,api,{refreshInterval:3000});
  const {data:calls=[],error:callError}=useSWR<CallRecord[]>('/calls',api,{refreshInterval:3000});
  useEffect(()=>{let socket:WebSocket;let timer:ReturnType<typeof setTimeout>;let stopped=false;const connect=()=>{socket=new WebSocket(process.env.NEXT_PUBLIC_WS_URL??`ws://${window.location.hostname}:8060/events`);socket.onopen=()=>setLive(true);socket.onmessage=e=>{const event=JSON.parse(e.data);if(event.type!=='heartbeat')void mutate(k=>typeof k==='string'&&(k.startsWith('/cases')||k.startsWith('/calls')))};socket.onerror=()=>socket.close();socket.onclose=()=>{setLive(false);if(!stopped)timer=setTimeout(connect,2000)}};connect();return()=>{stopped=true;clearTimeout(timer);socket?.close()}},[mutate]);
  function openCase(id:string){setCaseId(id);setCallId(null);setTab('cases')}
  function openCall(id:string){setCallId(id);setCaseId(null);setTab('calls')}
  const active=calls.filter(c=>c.status==='active'||c.status==='connecting').length;
  return <><header className="topbar"><div className="brand"><span className="brand-icon"><Activity size={22}/></span><strong>EffiGov</strong><span className="brand-divider"/><span>Voice Desk</span></div><div className="top-right"><Link className="resident-entry" href="/report">Resident demo ↗</Link><span className={`connection ${live?'live':''}`}><i/>{live?'Live updates':'Polling updates'}</span><span className="demo-tag">LOCAL DEMO</span></div></header>
    <main><div className="page-heading"><div className="eyebrow">RESIDENT SERVICES</div><h1>Every call, a clear next step.</h1><p className="muted">Voice intake and staff triage in one place.</p></div><div className="workspace"><aside><VoicePanel configured={health?.voice_configured??false} onCall={openCall}/><section className="panel overview"><div className="eyebrow">TODAY’S WORKSPACE</div><div><span>Cases in view</span><strong>{cases.length}</strong></div><div><span>Active calls</span><strong>{active}</strong></div><div><span>Call records</span><strong>{calls.length}</strong></div></section></aside>
      <div className="queue-area">{callId&&<CallDetail key={callId} id={callId} onCase={openCase}/>}<section className="panel queue"><div className="tabs"><button className={tab==='cases'?'selected':''} onClick={()=>setTab('cases')}><ClipboardList size={17}/>Cases<span>{cases.length}</span></button><button className={tab==='calls'?'selected':''} onClick={()=>{setTab('calls');if(!callId&&calls.length)openCall(calls[0].id)}}><Headphones size={17}/>Calls<span>{calls.length}</span></button></div>
        {tab==='cases'?<><div className="filters"><div className="search"><Search size={17}/><label className="sr-only" htmlFor="search">Search cases</label><input id="search" placeholder="Search name, case, phone, or issue" value={search} onChange={e=>setSearch(e.target.value)}/></div><label className="sr-only" htmlFor="filter">Filter status</label><select id="filter" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">All statuses</option>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select></div>{caseError?<p className="error" role="alert">{errorMessage(caseError)}</p>:isLoading?<div className="empty">Loading cases…</div>:cases.length?<div className="table-wrap"><table><thead><tr><th>Case / resident</th><th>Issue</th><th>Status</th><th>Updated</th></tr></thead><tbody>{cases.map(c=><tr className={caseId===c.id?'chosen':''} key={c.id}><td><button className="case-row" onClick={()=>openCase(c.id)}><strong>{c.id}</strong><span>{c.name}</span></button></td><td><strong className="issue-type">{label(c.issue_type)}</strong><span className="truncate">{c.description}</span></td><td><Badge value={c.status}/></td><td><span className="timestamp">{time(c.updated_at)}</span></td></tr>)}</tbody></table></div>:<div className="empty"><ClipboardList size={28}/><h3>{search||filter?'No matching cases':'The queue is clear'}</h3><p>{search||filter?'Try another search or status.':'Start a voice call to record the first service request.'}</p></div>}</>:<>{callError&&<p className="error" role="alert">{errorMessage(callError)}</p>}<div className="call-list">{calls.length?calls.map(c=><button className={callId===c.id?'chosen':''} key={c.id} onClick={()=>openCall(c.id)}><span className="call-icon"><Headphones size={18}/></span><span><strong>{c.case_id||'Intake in progress'}</strong><small>{time(c.started_at)}{c.mode==='test'?' · API test':''}</small></span><Badge value={c.status}/></button>):<div className="empty"><Headphones size={28}/><h3>No calls yet</h3><p>A call appears here as soon as the session starts.</p></div>}</div></>}
      </section>{caseId?<CaseDetail key={caseId} id={caseId} onCall={openCall}/>:!callId?<div className="detail-placeholder"><Clock size={20}/><span>Open a case or call to see its details and history.</span></div>:null}</div>
    </div></main><footer>EffiGov Engineering Take Home <span>Voice → Case → Staff review</span></footer></>
}
