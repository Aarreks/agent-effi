'use client';
import {useEffect,useRef,useState} from 'react';
import {Mic,MicOff,Phone,PhoneOff,Send} from 'lucide-react';
import type {Room} from 'livekit-client';
import {createJsonClient,errorMessage} from '@/lib/api';
const api=createJsonClient();

export function VoicePanel({configured,onCall}:{configured:boolean;onCall:(id:string)=>void}) {
  const [phase,setPhase]=useState('idle'); const [error,setError]=useState('');
  const [muted,setMuted]=useState(false); const [text,setText]=useState('');
  const room=useRef<Room|null>(null); const call=useRef<string|null>(null);
  const audioRoot=useRef<HTMLDivElement>(null);
  const timeout=useRef<ReturnType<typeof setTimeout>|null>(null);
  const generation=useRef(0);
  useEffect(()=>()=>{if(timeout.current)clearTimeout(timeout.current);void room.current?.disconnect()},[]);

  async function end() {
    const operation=++generation.current;
    if(timeout.current)clearTimeout(timeout.current);
    const current=call.current; const connection=room.current;
    call.current=null;room.current=null;setPhase('idle');
    audioRoot.current?.replaceChildren();
    await connection?.disconnect();
    if(current)try{await api(`/calls/${current}/finish`,{method:'POST'})}catch(e){if(operation===generation.current)setError(errorMessage(e))}
  }

  async function start() {
    const operation=++generation.current;
    setError('');setPhase('connecting');setMuted(false);
    try {
      // Obtain microphone permission before creating a persisted call.
      const permission=await navigator.mediaDevices.getUserMedia({audio:true});
      permission.getTracks().forEach(track=>track.stop());
      if(operation!==generation.current)return;
      const info=await api<{call_id:string;url:string;token:string}>('/voice/session',{method:'POST'});
      if(operation!==generation.current){await api(`/calls/${info.call_id}/finish`,{method:'POST'});return}
      call.current=info.call_id;onCall(info.call_id);
      const {Room,RoomEvent,Track}=await import('livekit-client');
      if(operation!==generation.current)return;
      const connection=new Room();room.current=connection;
      const isCurrent=()=>operation===generation.current&&room.current===connection;
      connection.on(RoomEvent.TrackSubscribed,track=>{if(isCurrent()&&track.kind===Track.Kind.Audio){const element=track.attach();audioRoot.current?.appendChild(element);void element.play().catch(()=>{if(isCurrent())setError('Audio playback was blocked. Click Enable sound.')})}});
      connection.on(RoomEvent.TrackUnsubscribed,track=>track.detach().forEach(el=>el.remove()));
      connection.on(RoomEvent.ParticipantConnected,()=>{if(isCurrent()){setPhase('active');if(timeout.current)clearTimeout(timeout.current)}});
      connection.on(RoomEvent.Disconnected,()=>{if(isCurrent())void end()});
      await connection.connect(info.url,info.token);
      if(operation!==generation.current){await connection.disconnect();return}
      await connection.startAudio();
      if(operation!==generation.current){await connection.disconnect();return}
      await connection.localParticipant.setMicrophoneEnabled(true);
      if(operation!==generation.current){await connection.disconnect();return}
      if(connection.remoteParticipants.size){setPhase('active')}else{setPhase('waiting');timeout.current=setTimeout(()=>{setError('The voice worker did not join. Check that it is running and the model credentials are valid.');void end()},20000)}
    } catch(e) {if(operation===generation.current){setError(errorMessage(e));await end()}}
  }

  async function toggleMic(){try{await room.current?.localParticipant.setMicrophoneEnabled(muted);setMuted(!muted)}catch(e){setError(errorMessage(e))}}
  async function send(event:React.FormEvent){event.preventDefault();if(!text.trim()||!room.current)return;try{await room.current.localParticipant.sendText(text.trim(),{topic:'lk.chat'});setText('')}catch(e){setError(errorMessage(e))}}
  const connected=phase==='active'||phase==='waiting';
  return <section className="voice panel">
    <div className="eyebrow">RESIDENT LINE</div><h2>Talk to Effi</h2><p className="muted">Report a service issue or check an existing request.</p>
    <div className={`voice-orb ${connected?'on':''}`} aria-hidden="true"><Mic size={34}/></div>
    <div className="voice-state" role="status">{phase==='idle'?'Ready when you are':phase==='connecting'?'Connecting…':phase==='waiting'?'Waiting for the agent…':'Voice session connected'}</div>
    {!configured&&<p className="setup">Connect LiveKit Cloud or add an OpenAI API key to <code>submission/.env</code>, then restart.</p>}
    {phase==='idle'?<button className="primary wide" disabled={!configured} onClick={start}><Phone size={17}/> Start voice call</button>:<div className="call-controls"><button disabled={!connected} onClick={toggleMic}>{muted?<MicOff size={18}/>:<Mic size={18}/>} {muted?'Unmute':'Mute'}</button><button className="danger" onClick={()=>void end()}><PhoneOff size={18}/> End call</button></div>}
    {connected&&<><form onSubmit={send} className="text-turn"><label className="sr-only" htmlFor="message">Message the voice agent</label><input id="message" value={text} onChange={e=>setText(e.target.value)} placeholder="Or type to the same agent"/><button aria-label="Send message" disabled={!text.trim()}><Send size={17}/></button></form><button className="link" onClick={()=>void room.current?.startAudio()}>Enable sound</button></>}
    {error&&<p className="error" role="alert">{error}</p>}
    <div ref={audioRoot} className="audio-root"/>
    <div className="voice-foot">Staff workspace · calls simulate resident intake. Requests are recorded for staff review.</div>
  </section>
}
