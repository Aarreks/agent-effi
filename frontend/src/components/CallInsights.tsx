import type {CallRecord} from '@/lib/types';
const label=(value:string)=>value.replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());

export function CallInsights({call}:{call:CallRecord}) {
  const details=Object.entries(call.intake??{});
  const reviews=call.supervisor_reviews??[];
  const interventions=reviews.filter(r=>r.status!=='checked');
  return <>
    {details.length>0&&<section className="intake-preview" aria-live="polite">
      <div className="section-head"><h3>{call.intake_stage==='recorded'?'Confirmed intake':'Live intake'}</h3><span className="badge">{label(call.intake_stage??'collecting')}</span></div>
      {call.intake_stage!=='recorded'&&<p className="muted">Collected details appear here as the resident clarifies them. A case is created after confirmation.</p>}
      <dl className="analysis-fields">{details.map(([key,value])=><div key={key}><dt>{label(key)}</dt><dd>{key==='issue_type'?label(value):value}</dd></div>)}</dl>
    </section>}
    <section className="supervisor" aria-live="polite">
      <div className="section-head"><h3>Call supervisor</h3><span className={`badge ${interventions.length?'needs_attention':reviews.length?'complete':''}`}>{interventions.length?'Review findings':reviews.length?`${reviews.length} replies checked`:'Waiting for replies'}</span></div>
      <p className="muted">Checks the agent’s claims against saved case data and delivers a spoken correction when needed.</p>
      {interventions.map(review=><article key={review.event_id} className="supervisor-finding"><strong>{review.status==='corrected'?'Spoken correction delivered':'Check needs attention'}</strong><p>{review.reason}</p>{review.correction&&<blockquote>{review.correction}</blockquote>}</article>)}
      {reviews.length>0&&<details><summary>Review history</summary>{reviews.map(review=><article className="review-item" key={review.event_id}><small>{label(review.status)} · {new Date(review.at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</small><p>{review.utterance}</p></article>)}</details>}
      {!reviews.length&&call.status==='ended'&&<p className="muted">No completed supervisory reviews recorded for this call.</p>}
    </section>
  </>
}
