import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../App';
import { HttpTransport } from '../api/httpTransport';
import { makeAwaitingContractView, makeRunView } from './runViewFactory';

const reply = (body:unknown,status=200) => new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});
afterEach(()=>{vi.unstubAllGlobals();vi.restoreAllMocks();});

describe('public HTTP application',()=>{
 it('creates with public JSON, resynchronizes a rejected action, and deletes with validated 200 JSON',async()=>{
  const user=userEvent.setup();const contract={...makeAwaitingContractView(),run_id:'public-run',mode:'live' as const};
  const rejected={...makeRunView('contract_rejected'),run_id:'public-run',mode:'live' as const};
  const fetch=vi.fn().mockResolvedValueOnce(reply({schema_version:'1.0',run_id:'public-run'},202)).mockResolvedValueOnce(reply(contract))
   .mockResolvedValueOnce(reply({error:{schema_version:'1.0',code:'INVALID_STATE',message:'This contract review has already ended.',retryable:false,error_id:'public-review-409'}},409))
   .mockResolvedValueOnce(reply(rejected)).mockResolvedValueOnce(reply({schema_version:'1.0',run_id:'public-run',deleted:true}));
  vi.stubGlobal('fetch',fetch);render(<App transport={new HttpTransport()} />);
  expect(screen.getByText('Public API · no run loaded')).toBeVisible();
  await user.type(screen.getByLabelText('Policy title'),'Synthetic HTTP policy');
  await user.click(screen.getByLabelText('Bundled sample'));
  expect(screen.getByRole('combobox',{name:'Bundled policy sample'})).toHaveDisplayValue('Development reimbursement policy');
  await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));
  await user.click(screen.getByRole('button',{name:'Analyze policy'}));
  expect(await screen.findByText('Live run')).toBeVisible();
  expect(screen.queryByText(/authored display data/)).not.toBeInTheDocument();
  await user.click(screen.getByRole('button',{name:'Reject policy contract'}));
  expect(await screen.findByText('Contract rejected — run ended')).toBeVisible();
  expect(screen.getByRole('alert')).toHaveTextContent('This contract review has already ended.');
  expect(screen.getByRole('alert')).toHaveTextContent('public-review-409');
  await user.click(screen.getByRole('button',{name:'Delete run'}));
  await user.click(screen.getByRole('button',{name:'Confirm delete'}));
  await waitFor(()=>expect(screen.queryByText('Live run')).not.toBeInTheDocument());
  expect(fetch).toHaveBeenCalledTimes(5);
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({source_type:'bundled_sample',sample_id:'development-policy',text:null,title:'Synthetic HTTP policy',non_confidential_confirmed:true});
  expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({schema_version:'1.0',decision:'reject',baseline_policy_id:null,baseline_policy_sha256:null,invariants:[],required_dimensions:[]});
  expect(fetch.mock.calls.map(call=>[call[0],call[1].method])).toEqual([
   ['/api/v1/runs','POST'],['/api/v1/runs/public-run','GET'],['/api/v1/runs/public-run/confirm-contract','POST'],['/api/v1/runs/public-run','GET'],['/api/v1/runs/public-run','DELETE'],
  ]);
 });
 it('shows a safe error and keeps the input after an unstructured HTTP failure',async()=>{
  const user=userEvent.setup();vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('private stack trace and provider details',{status:500})));
  render(<App transport={new HttpTransport()} />);await user.type(screen.getByLabelText('Policy title'),'Synthetic failure');await user.type(screen.getByLabelText('Policy text'),'Non-confidential test');await user.click(screen.getByLabelText(/I confirm this policy is non-confidential/));await user.click(screen.getByRole('button',{name:'Analyze policy'}));
  expect(await screen.findByRole('alert')).not.toHaveTextContent(/private|stack trace|provider details/);expect(screen.getByLabelText('Policy text')).toHaveValue('Non-confidential test');
 });
});
