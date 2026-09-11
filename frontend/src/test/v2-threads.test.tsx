import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import completed from '../../../contracts/v2/fixtures/completed-public-result.json';
import { validateResult, type PublicResult } from '../v2/api';
import { SandboxEvidence } from '../v2/SandboxEvidence';

afterEach(() => window.history.replaceState(null, '', '/v2'));

function branchedDiscussion() {
  const result = structuredClone(validateResult(completed));
  result.messages[2].reply_to_message_ids = ['message-002'];
  function append(id: string, content: string, parents: string[]) {
    const message: PublicResult['messages'][number] = {
      ...result.messages[0], message_id: id, content, sequence: result.messages.length + 1,
      reply_to_message_ids: parents, source_refs: [`source-${id}`],
    };
    result.messages.push(message);
    result.sources.push({ source_id: `source-${id}`, record_id: id, title: 'Synthetic source', excerpt: `Source text: ${content}` });
  }
  append('opening-two', 'A separate question about weekend service.', []);
  append('shared-reply', 'A reply connecting both discussions.', ['opening-two', 'message-002']);
  return validateResult(result);
}

describe('stakeholder threads', () => {
  it('groups nested replies under their opening, hides them initially and retains every message once', async () => {
    const result = branchedDiscussion();
    render(<SandboxEvidence result={result}/>);
    const list = screen.getByRole('list', { name: 'Stakeholder threads' });
    expect(list.children).toHaveLength(2);
    expect(screen.getByText(result.messages[0].content)).toBeVisible();
    expect(screen.getByText(result.messages[3].content)).toBeVisible();
    expect(screen.getByText(result.messages[1].content)).not.toBeVisible();
    expect(screen.getByText(result.messages[2].content)).not.toBeVisible();
    await userEvent.setup().click(screen.getByText('2 replies'));
    expect(screen.getByText(result.messages[1].content)).toBeVisible();
    expect(screen.getByText(result.messages[2].content)).toBeVisible();
    expect(screen.getByText(result.messages[4].content)).not.toBeVisible();
    expect(list.children[0]).toContainElement(screen.getByText(result.messages[2].content));
    expect(list.children[1]).toContainElement(screen.getByText(result.messages[4].content));
    for (const message of result.messages) {
      expect(document.querySelectorAll(`[id="v2-message-${message.message_id}"]`)).toHaveLength(1);
    }
    await userEvent.setup().click(screen.getByText('1 reply'));
    const sharedReply = document.getElementById('v2-message-shared-reply')!;
    expect(within(sharedReply).getAllByRole('link').map(link => link.getAttribute('href'))).toEqual([
      '#v2-message-opening-two', '#v2-message-message-002',
    ]);
  });

  it('opens a cited reply on initial navigation and again when the same citation is clicked', async () => {
    window.history.replaceState(null, '', '/v2#v2-message-message-003');
    const result = branchedDiscussion();
    render(<><a href="#v2-message-message-003">Judge citation</a><SandboxEvidence result={result}/></>);
    const reply = document.getElementById('v2-message-message-003')!;
    expect(screen.getByText(result.messages[2].content)).toBeVisible();
    expect(reply).toHaveFocus();
    const user = userEvent.setup();
    await user.click(screen.getByText('2 replies'));
    expect(screen.getByText(result.messages[2].content)).not.toBeVisible();
    await user.click(screen.getByRole('link', { name: 'Judge citation' }));
    expect(screen.getByText(result.messages[2].content)).toBeVisible();
    expect(reply).toHaveFocus();
  });

  it('opens only the target thread when the citation changes', () => {
    const result = branchedDiscussion();
    render(<SandboxEvidence result={result}/>);
    window.history.replaceState(null, '', '/v2#v2-message-shared-reply');
    fireEvent(window, new HashChangeEvent('hashchange'));
    expect(screen.getByText(result.messages[4].content)).toBeVisible();
    expect(screen.getByText(result.messages[1].content)).not.toBeVisible();
    expect(document.getElementById('v2-message-shared-reply')).toHaveFocus();
  });
});
