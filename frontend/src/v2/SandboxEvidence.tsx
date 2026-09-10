import { MessageSquareText, ShieldCheck, Users } from 'lucide-react';
import type { PublicResult } from './api';

export function SandboxEvidence({ result }: { result: PublicResult }) {
  const incompleteTranslation = result.messages.some(message => message.translation_status === 'unavailable');
  const status = result.status === 'completed' ? 'Completed'
    : result.status === 'partial' ? (incompleteTranslation ? 'Partial — translation incomplete' : 'Partial — incomplete evidence')
      : result.status === 'failed' ? 'Failed' : 'Cancelled';
  const translationLabel = { translated: 'Translated to English', original_english: 'Original English', unavailable: 'Translation unavailable' };
  return <section className="v2-evidence" aria-labelledby="v2-evidence-title">
    <div className="panel">
      <div className="row">
        <div><p className="eyebrow">FIXTURE RUN RESULT</p><h2 id="v2-evidence-title">Sandbox evidence</h2></div>
        <div className="badge-row"><span className="badge">Synthetic fixture</span><span className={`badge ${result.status === 'completed' ? 'success' : 'warning'}`}>{status}</span></div>
      </div>
      <p className="muted">Input: {result.policy_title}. The sample dialogue below is authored demonstration data.</p>
      <dl className="v2-counts">
        <div><dt>Requested stakeholders</dt><dd>{result.requested_stakeholder_count}</dd></div>
        <div><dt>Configured stakeholders</dt><dd>{result.configured_stakeholder_count}</dd></div>
        <div><dt>Observed stakeholders</dt><dd>{result.observed_stakeholder_count}</dd></div>
      </dl>
      <div className={`notice ${result.status === 'completed' ? 'neutral' : 'warning'}`}>
        <ShieldCheck size={20} aria-hidden="true"/><div><strong>Evidence limitations</strong>
          <ul>{result.limitations.map((note, index) => <li key={index}>{note}</li>)}</ul>
          {result.errors.length > 0 && <ul>{result.errors.map((note, index) => <li key={index}>{note}</li>)}</ul>}
        </div>
      </div>
    </div>
    <div className="v2-evidence-grid">
      <div className="panel"><h3><MessageSquareText size={20} aria-hidden="true"/>Stakeholder interactions</h3>
        <p className="muted">English display text with replies and source evidence.</p>
        {result.messages.length === 0 && <p>No stakeholder messages were returned.</p>}
        <ol className="v2-messages">{result.messages.map(message => {
          const persona = result.personas.find(item => item.persona_id === message.persona_id);
          return <li className="v2-message" id={`v2-message-${message.message_id}`} key={message.message_id}>
            <div className="row"><strong>{persona?.display_name ?? 'Unknown stakeholder'}</strong>
              <span className={`badge ${message.translation_status === 'unavailable' ? 'warning' : ''}`}>{translationLabel[message.translation_status]}</span></div>
            <p className="small muted">Message {message.sequence}{message.round_number !== null && ` · Round ${message.round_number}`}</p>
            <p className="v2-message-text">{message.content}</p>
            {message.reply_to_message_ids.length > 0 && <div className="v2-replies">{message.reply_to_message_ids.map(id => <a key={id} href={`#v2-message-${id}`}>Reply to {id}</a>)}</div>}
            <details><summary>Source evidence · {message.source_refs.length} record{message.source_refs.length === 1 ? '' : 's'}</summary>
              {message.source_refs.map(id => {
                const source = result.sources.find(item => item.source_id === id);
                return source ? <figure className="citation" key={id}><figcaption>{source.title} · {source.source_id}</figcaption><blockquote>{source.excerpt}</blockquote><small className="muted">Record: {source.record_id}</small></figure> : null;
              })}
              <small className="muted">Message: {message.message_id} · Persona: {message.persona_id}</small>
            </details>
          </li>;
        })}</ol>
      </div>
      <aside className="panel"><h3><Users size={20} aria-hidden="true"/>Fixture participants</h3>
        <p className="small muted">These personas are part of the authored sample. The live Sandbox will use your personality seed.</p>
        <ul className="v2-personas">{result.personas.map(persona => <li key={persona.persona_id}><strong>{persona.display_name}</strong><p>{persona.description}</p><code>{persona.persona_id}</code></li>)}</ul>
      </aside>
    </div>
    <details className="panel v2-trace"><summary>Run trace and request binding</summary>
      <dl>{Object.entries({ 'Run ID': result.run_id, 'Request ID': result.request_id, 'Policy version': result.policy_version, 'Schema version': result.schema_version, 'Exact policy SHA-256': result.policy_text_sha256, 'Request fingerprint': result.request_fingerprint }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><code>{value}</code></dd></div>)}</dl>
    </details>
  </section>;
}
