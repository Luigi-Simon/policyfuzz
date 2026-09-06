import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import App from '../App';
import { MockTransport } from '../api/mockTransport';
import { makeCompletedView, makeRunView } from './runViewFactory';

describe('public application shell', () => {
 it('renders four workflow steps, one main heading, and authored fixture provenance before a run', () => {
  render(<App transport={new MockTransport()} />);
  expect(within(screen.getByRole('navigation',{name:'Run workflow'})).getAllByRole('listitem')).toHaveLength(4);
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
  expect(screen.getByRole('heading',{level:1,name:'PolicyFuzz'})).toBeVisible();
  expect(screen.getByText(/Cached synthetic fixture.*authored display data/)).toBeVisible();
  expect(screen.getByRole('link',{name:'Skip to main content'})).toHaveAttribute('href','#main-content');
 });
 it('disables unavailable earlier details when a completed run is loaded directly',async()=>{
  const transport=new MockTransport();vi.spyOn(transport,'getRun').mockResolvedValue(makeCompletedView());
  render(<App transport={transport} initialRunId="direct-complete" />);
  expect(await screen.findByText('Revision did not pass all safeguards')).toBeVisible();
  const nav=within(screen.getByRole('navigation',{name:'Run workflow'}));
  expect(nav.getByRole('button',{name:/Input & contract/})).toBeDisabled();
  expect(nav.getByRole('button',{name:/Run evidence/})).toBeDisabled();
  expect(nav.getByRole('button',{name:/Findings & revision/})).toBeDisabled();
  expect(screen.getByText(/Earlier detail is unavailable/)).toBeVisible();
  expect(screen.queryByText(/Safe to publish/)).not.toBeInTheDocument();
 });
 it('requires inline confirmation for deletion, retains the choice on failure, and clears only after success',async()=>{
  const user=userEvent.setup(),transport=new MockTransport();vi.spyOn(transport,'getRun').mockResolvedValue(makeCompletedView());
  const deleting=vi.spyOn(transport,'deleteRun').mockRejectedValueOnce(new Error('private failure')).mockResolvedValueOnce();
  render(<App transport={transport} initialRunId="direct-complete" />);await screen.findByText('Revision did not pass all safeguards');
  await user.click(screen.getByRole('button',{name:'Delete run'}));expect(deleting).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'Cancel deletion'})).toBeVisible();
  await user.click(screen.getByRole('button',{name:'Confirm delete'}));expect(await screen.findByRole('alert')).not.toHaveTextContent('private failure');
  expect(screen.getByRole('button',{name:'Confirm delete'})).toBeEnabled();expect(screen.getByText('Revision did not pass all safeguards')).toBeVisible();
  await user.click(screen.getByRole('button',{name:'Confirm delete'}));await waitFor(()=>expect(screen.queryByText('Revision did not pass all safeguards')).not.toBeInTheDocument());
 });
 it('only offers deletion when the server allows it',async()=>{
  const transport=new MockTransport();vi.spyOn(transport,'getRun').mockResolvedValue({...makeRunView('contract_rejected'),allowed_actions:[]});
  render(<App transport={transport} initialRunId="denied-delete" />);await screen.findByText('Contract rejected — run ended');
  expect(screen.queryByRole('button',{name:'Delete run'})).not.toBeInTheDocument();
 });
});

describe('complete synthetic public journey',()=>{
 it('rejects a contract through the real mock transport and reaches the terminal view',async()=>{
  const user=userEvent.setup();
  render(<App transport={new MockTransport()}/>);
  await user.type(screen.getByLabelText('Policy title'),'Synthetic rejection journey');
  await user.click(screen.getByLabelText('Bundled sample'));
  await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
  await user.click(screen.getByRole('button',{name:'Analyze policy'}));
  await screen.findByRole('heading',{name:'Confirm policy contract'});

  await user.click(screen.getByRole('button',{name:'Reject policy contract'}));

  expect(await screen.findByText('Contract rejected — run ended')).toBeVisible();
  expect(screen.getByRole('heading',{name:'contract rejected'})).toBeVisible();
 });

 it('supports all three confirmations and history navigation while preserving the rejected canonical result',async()=>{
  const user=userEvent.setup(),transport=new MockTransport();render(<App transport={transport}/>);
  await user.type(screen.getByLabelText('Policy title'),'Synthetic journey');await user.click(screen.getByLabelText('Bundled sample'));expect(screen.getByRole('combobox',{name:'Bundled policy sample'})).toHaveDisplayValue('Development reimbursement policy');await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));await user.click(screen.getByRole('button',{name:'Analyze policy'}));
  await screen.findByRole('heading',{name:'Confirm policy contract'});
  for (const checkbox of screen.getAllByRole('checkbox',{name:/Acknowledge rule|Confirm required dimension/})) await user.click(checkbox);
  const confirm=screen.getByRole('button',{name:'Confirm policy contract'});confirm.focus();await user.keyboard('{Enter}');
  await screen.findByText('Awaiting finding review');
  const nav=within(screen.getByRole('navigation',{name:'Run workflow'}));await user.click(nav.getByRole('button',{name:/Run evidence/}));
  expect(screen.getByRole('heading',{name:'Run evidence'})).toBeVisible();
  expect(screen.getAllByRole('button',{name:/View trace/}).length).toBeGreaterThan(0);
  await user.click(nav.getByRole('button',{name:/Findings & revision/}));
  await user.click(within(screen.getByRole('radiogroup',{name:'Decision for synthetic-finding-cap'})).getByLabelText('Accept'));
  await user.click(within(screen.getByRole('radiogroup',{name:'Decision for synthetic-finding-gap'})).getByLabelText('Reject'));
  await user.click(screen.getByRole('button',{name:'Submit finding decisions'}));
  expect(await screen.findByText('Unverified wording suggestion — not what was tested.')).toBeVisible();
  await user.click(screen.getByRole('button',{name:'Confirm revision'}));
  expect(await screen.findByText('Revision did not pass all safeguards')).toHaveAttribute('data-tone','danger');
  expect(screen.getByText(/Cached synthetic fixture.*authored display data/)).toBeVisible();
  await user.click(nav.getByRole('button',{name:/Input & contract/}));
  expect(screen.getByRole('heading',{name:'Confirm policy contract'})).toBeVisible();expect(screen.getByRole('button',{name:'Confirm policy contract'})).toBeDisabled();
  expect(screen.getAllByRole('main')).toHaveLength(1);
 });
});

it('allows an explicit refresh when the initial load failed before a run snapshot arrived',async()=>{
 const user=userEvent.setup(),transport=new MockTransport();vi.spyOn(transport,'getRun').mockRejectedValueOnce(new Error('connection closed')).mockResolvedValueOnce(makeCompletedView());
 render(<App transport={transport} initialRunId="initial-retry"/>);await screen.findByRole('alert');await user.click(screen.getByRole('button',{name:'Refresh run'}));expect(await screen.findByText('Revision did not pass all safeguards')).toBeVisible();
});
