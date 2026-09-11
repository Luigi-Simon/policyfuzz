import { MessageSquareText, ShieldCheck, Users } from 'lucide-react';
import { useEffect, useRef } from 'react';
import type { PublicResult } from './api';

type Message = PublicResult['messages'][number];
type Thread = { opening: Message; replies: Message[] };

function conversationThreads(messages: Message[]): Thread[] {
  const threads: Thread[] = [];
  const threadByMessage = new Map<string, Thread>();
  // Validated evidence is ordered with parents before replies. A reply to several
  // threads lives in its first parent's thread; all original reply links remain.
  for (const message of messages) {
    const parentThread = message.reply_to_message_ids.map(id => threadByMessage.get(id)).find(Boolean);
    if (parentThread) {
      parentThread.replies.push(message);
      threadByMessage.set(message.message_id, parentThread);
    } else {
      const thread = { opening: message, replies: [] };
      threads.push(thread);
      threadByMessage.set(message.message_id, thread);
    }
  }
  return threads;
}

export function SandboxEvidence({ result }: { result: PublicResult }) {
  const evidence = useRef<HTMLElement>(null);
  const threads = conversationThreads(result.messages);
  const personas = new Map(result.personas.map(persona => [persona.persona_id, persona]));
  const messages = new Map(result.messages.map(message => [message.message_id, message]));
  const sources = new Map(result.sources.map(source => [source.source_id, source]));

  useEffect(() => {
    const revealCitation = () => {
      let id: string;
      try { id = decodeURIComponent(window.location.hash.slice(1)); }
      catch { return; }
      if (!id.startsWith('v2-message-')) return;
      const target = document.getElementById(id);
      if (!target || !evidence.current?.contains(target)) return;
      for (let parent = target.parentElement; parent && parent !== evidence.current; parent = parent.parentElement) {
        if (parent instanceof HTMLDetailsElement) parent.open = true;
      }
      target.scrollIntoView?.({ block: 'center' });
      target.focus({ preventScroll: true });
    };
    const repeatCitation = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      // Clicking the same citation after collapsing its thread emits no hashchange.
      if (anchor?.href === window.location.href) revealCitation();
    };
    revealCitation();
    window.addEventListener('hashchange', revealCitation);
    document.addEventListener('click', repeatCitation);
    return () => {
      window.removeEventListener('hashchange', revealCitation);
      document.removeEventListener('click', repeatCitation);
    };
  }, [result]);

  const fixture = result.execution_mode === 'fixture';
  const incompleteTranslation = result.messages.some(message => message.translation_status === 'unavailable');
  const status = result.status === 'completed' ? 'Completed'
    : result.status === 'partial' ? (incompleteTranslation ? 'Partial — translation incomplete' : 'Partial — incomplete evidence')
      : result.status === 'failed' ? 'Failed' : 'Cancelled';
  const translationLabel = { translated: 'Translated to English', original_english: 'Original English', unavailable: 'Translation unavailable' };
  function renderMessage(message: Message) {
    return <article className="v2-message" id={`v2-message-${message.message_id}`} tabIndex={-1}>
      <div className="row"><strong>{personas.get(message.persona_id)?.display_name ?? 'Unknown stakeholder'}</strong>
        <span className={`badge ${message.translation_status === 'unavailable' ? 'warning' : ''}`}>{translationLabel[message.translation_status]}</span></div>
      <p className="small muted">Message {message.sequence}{message.round_number !== null && ` · Round ${message.round_number}`}</p>
      <p className="v2-message-text">{message.content}</p>
      {message.reply_to_message_ids.length > 0 && <div className="v2-replies">{message.reply_to_message_ids.map(id => {
        const parent = messages.get(id);
        return <a key={id} href={`#v2-message-${id}`}>Reply to {parent ? `${personas.get(parent.persona_id)?.display_name ?? 'Unknown stakeholder'} · Message ${parent.sequence}` : id}</a>;
      })}</div>}
      <details><summary>Source evidence · {message.source_refs.length} record{message.source_refs.length === 1 ? '' : 's'}</summary>
        {message.source_refs.map(id => {
          const source = sources.get(id);
          return source ? <figure className="citation" key={id}><figcaption>{source.title} · {source.source_id}</figcaption><blockquote>{source.excerpt}</blockquote><small className="muted">Record: {source.record_id}</small></figure> : null;
        })}
        <small className="muted">Message: {message.message_id} · Persona: {message.persona_id}</small>
      </details>
    </article>;
  }
  return <section className="v2-evidence" ref={evidence} aria-labelledby="v2-evidence-title">
    <div className="panel">
      <div className="row">
        <div><p className="eyebrow">{result.execution_mode.toUpperCase()} RUN RESULT</p><h2 id="v2-evidence-title">Sandbox evidence</h2></div>
        <div className="badge-row"><span className="badge">{fixture ? 'Synthetic fixture' : 'Live MiroFish'}</span><span className={`badge ${result.status === 'completed' ? 'success' : 'warning'}`}>{status}</span></div>
      </div>
      <p className="muted">Input: {result.policy_title}. {fixture ? 'The sample dialogue below is authored demonstration data.' : 'These conversations are simulated stakeholder observations, not an opinion survey.'}</p>
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
      <div className="panel"><h3><MessageSquareText size={20} aria-hidden="true"/>Stakeholder threads</h3>
        <p className="muted">Each opening message starts a conversation. Expand its replies to follow the discussion.</p>
        {result.messages.length === 0 && <p>No stakeholder messages were returned.</p>}
        <ol className="v2-messages" aria-label="Stakeholder threads">{threads.map(({ opening, replies }) => <li className="v2-thread" key={opening.message_id}>
          {renderMessage(opening)}
          {replies.length > 0 ? <details className="v2-thread-replies">
            <summary aria-label={`${replies.length} ${replies.length === 1 ? 'reply' : 'replies'} to ${personas.get(opening.persona_id)?.display_name ?? 'Unknown stakeholder'} · Message ${opening.sequence}`}>
              {replies.length} {replies.length === 1 ? 'reply' : 'replies'}
            </summary>
            <ol className="v2-messages" aria-label={`Replies to message ${opening.sequence}`}>{replies.map(reply => <li key={reply.message_id}>{renderMessage(reply)}</li>)}</ol>
          </details> : <p className="v2-thread-empty small muted">No replies</p>}
        </li>)}</ol>
      </div>
      <aside className="panel"><h3><Users size={20} aria-hidden="true"/>{fixture ? 'Fixture participants' : 'Simulated participants'}</h3>
        <p className="small muted">{!result.personas.length ? 'No participant profiles are available. Inspect Sandbox errors for setup or capture failures.' : fixture ? 'These personas are part of the authored sample. The live Sandbox will use your personality seed.' : 'These simulated personas were generated using your personality seed.'}</p>
        <ul className="v2-personas">{result.personas.map(persona => <li key={persona.persona_id}><strong>{persona.display_name}</strong><p>{persona.description}</p><code>{persona.persona_id}</code></li>)}</ul>
      </aside>
    </div>
    <details className="panel v2-trace"><summary>Run trace and request binding</summary>
      <dl>{Object.entries({ 'Run ID': result.run_id, 'Request ID': result.request_id, 'Policy version': result.policy_version, 'Schema version': result.schema_version, 'Exact policy SHA-256': result.policy_text_sha256, 'Request fingerprint': result.request_fingerprint }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd><code>{value}</code></dd></div>)}</dl>
    </details>
  </section>;
}
