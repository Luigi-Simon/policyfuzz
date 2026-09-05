import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import App from '../App';
describe('interface preview', () => {
 it('requires policy confirmation before running and supports the complete journey', async () => {
  const user = userEvent.setup(); render(<App />);
  await user.click(screen.getByRole('button', {name: /Use sample policy/}));
  expect(screen.getByRole('button', {name: /Confirm contract/})).toBeDisabled();
  await user.click(screen.getByLabelText(/I confirm the extracted rules/));
  await user.click(screen.getByRole('button', {name: /Confirm contract/}));
  const reviewButton = await screen.findByRole('button', {name: /Review findings/}, {timeout: 4000});
  await user.click(screen.getByRole('button', {name:'Failed'}));
  expect(within(screen.getByRole('region', {name:'Scenario results'})).getAllByRole('row')).toHaveLength(4);
  await user.click(screen.getAllByRole('button', {name:'Inspect'})[0]);
  expect(screen.getByRole('dialog', {name:'Evidence inspector'})).toBeVisible();
  await user.click(screen.getByRole('button', {name:'Close evidence inspector'}));
  await user.click(reviewButton);
  for (let i=0; i<3; i++) {
   await user.click(screen.getByRole('button', {name: `Select finding ${i+1}`}));
   if(i>0) await user.selectOptions(screen.getByLabelText('Reviewer severity'), 'high');
   await user.click(screen.getByRole('button', {name: 'Accept finding'}));
  }
  await user.click(screen.getByRole('button', {name: /Prepare revision/}));
  await user.click(screen.getByRole('button', {name: /Confirm revision & retest/}));
  expect(await screen.findByText('Revision passed all safeguards for this test suite', {}, {timeout: 4000})).toBeVisible();
  await user.click(screen.getByRole('button', {name:'Failed safeguard state'}));
  expect(screen.getByText('Revision did not pass all safeguards')).toBeVisible();
  expect(screen.queryByText('Revision passed all safeguards for this test suite')).not.toBeInTheDocument();
 }, 15000);
 it('does not pretend to analyze arbitrary pasted text', async () => {
  const user=userEvent.setup(); render(<App />);
  await user.type(screen.getByLabelText('Policy text'), 'My custom policy');
  await user.click(screen.getByLabelText(/This policy is synthetic/));
  await user.click(screen.getByRole('button', {name: 'Analyze policy'}));
  expect(screen.getByRole('alert')).toHaveTextContent('Backend connection needed');
 });
 it('deletes the preview only after confirmation', async () => {
  const user=userEvent.setup(); render(<App />);
  await user.click(screen.getByRole('button', {name: /Use sample policy/}));
  await user.click(screen.getByRole('button', {name: 'Delete run'}));
  await user.click(screen.getByRole('button', {name: 'Confirm deletion'}));
  expect(screen.getByLabelText('Policy text')).toHaveValue('');
 });
});
