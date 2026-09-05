import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import App from '../App';
import { BehavioralComparison, defaultContext } from '../behavior';
describe('revised behavioral workflow',()=>{
 it('withholds like-for-like results when comparison inputs differ',async()=>{
  const user=userEvent.setup();render(<BehavioralComparison context={defaultContext} accepted={[0]}/>);
  expect(screen.getByRole('region',{name:'Fixed action comparison'})).toBeVisible();
  await user.selectOptions(screen.getByLabelText('Comparison basis preview'),'changed');
  expect(screen.getByRole('status')).toHaveTextContent('Like-for-like comparison unavailable');
  expect(screen.queryByRole('region',{name:'Fixed action comparison'})).not.toBeInTheDocument();
 });
 it('collects setup context and defaults interaction simulation off',async()=>{
  const user=userEvent.setup();render(<App/>);
  expect(screen.getByRole('checkbox',{name:/Explore interactions/})).not.toBeChecked();
  await user.click(screen.getByRole('button',{name:'Add affected group'}));
  expect(screen.getByLabelText('Group name 4')).toHaveValue('');
  await user.click(screen.getByRole('button',{name:'Add goal'}));
  expect(screen.getByLabelText('Goal 4')).toHaveValue('');
 });
 it('shows simulation summaries and separates hypotheses from consequences',async()=>{
  const user=userEvent.setup();render(<App/>);
  await user.click(screen.getByRole('checkbox',{name:/Explore interactions/}));
  await user.click(screen.getByRole('button',{name:/Use sample policy/}));
  await user.click(screen.getByLabelText(/I confirm the extracted rules/));
  await user.click(screen.getByRole('button',{name:/Confirm contract/}));
  await screen.findByRole('button',{name:/Review findings/},{timeout:4000});
  expect(screen.getByText('Employee — simulated')).toBeVisible();
  expect(screen.getByText('People might respond this way')).toBeVisible();
  expect(screen.getByText('Given that action, the calculated consequence is…')).toBeVisible();
  await user.selectOptions(screen.getByLabelText('Simulation preview state'),'failed');
  expect(screen.getByText(/Direct action evaluation remains available/)).toBeVisible();
 });
});
