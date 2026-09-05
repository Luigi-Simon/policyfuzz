// UI-only illustrative content. This is NOT a RunView or an API contract.
// Replace through generated public types once Person 1 freezes OpenAPI.
export const policyText = `SYNTHETIC HACKATHON SAMPLE — NOT COMPANY POLICY

Section 4.1 — Meals and receipts
Meal claims are eligible with an individual claim cap of SGD 100.
Receipts are not required for claims below SGD 50.
Receipts are required for claims above SGD 50.

Section 4.2 — Travel and approval
Approval is normally not required. Hotel claims below SGD 250 require no approval regardless of destination. International hotel claims require manager approval.
Airfare booked fewer than 14 days ahead requires manager approval. Transport claims have a cap of SGD 200.

Section 4.3 — Incidentals
Employees may claim reasonable incidental expenses.`;
export const intents = ['Meal claims that take daily meal spending above SGD 100 must not remain eligible without escalation.', 'Claims at or above SGD 50 must require a receipt.', 'International hotel claims must resolve to manager approval without conflicting approval requirements.'];
export const rules = [
 { id:'R-01', title:'Meal eligibility & individual cap', condition:'expense_category = meal', effect:'eligibility = allow · claim_cap = SGD 100', quote:'Meal claims are eligible with an individual claim cap of SGD 100.', section:'4.1' },
 { id:'R-02', title:'Receipt exemption threshold', condition:'amount < SGD 50', effect:'receipt_requirement = not_required', quote:'Receipts are not required for claims below SGD 50.', section:'4.1' },
 { id:'R-03', title:'Mandatory receipt threshold', condition:'amount > SGD 50', effect:'receipt_requirement = required', quote:'Receipts are required for claims above SGD 50.', section:'4.1' },
 { id:'R-04', title:'Hotel approval exception', condition:'expense_category = hotel AND amount < SGD 250', effect:'approval_requirement = none', quote:'Hotel claims below SGD 250 require no approval regardless of destination.', section:'4.2' },
 { id:'R-05', title:'International hotel approval', condition:'expense_category = hotel AND destination = international', effect:'approval_requirement = manager', quote:'International hotel claims require manager approval.', section:'4.2' },
 { id:'R-06', title:'General approval', condition:'all supported claims', effect:'approval_requirement = none', quote:'Approval is normally not required.', section:'4.2' },
 { id:'R-07', title:'Short-notice airfare', condition:'expense_category = airfare AND booking_days_before < 14', effect:'approval_requirement = manager', quote:'Airfare booked fewer than 14 days ahead requires manager approval.', section:'4.2' },
 { id:'R-08', title:'Transport claim cap', condition:'expense_category = transport', effect:'claim_cap = SGD 200', quote:'Transport claims have a cap of SGD 200.', section:'4.2' },
];
export const findings = [
 { title:'Split meal claims exceed daily intent', type:'Intent breach', level:'Session-confirmed intent', scenario:'SCN-001', rule:'R-01', facts:'SGD 60 already claimed today + SGD 50 current meal claim = SGD 110 daily total.', expected:'Daily spending above SGD 100 must not remain eligible without escalation.', observed:'Eligibility resolves to allow; the SGD 50 current claim satisfies the individual SGD 100 cap.', quote:rules[0].quote, section:'4.1', before:'Meal → eligibility: allow; individual claim cap: SGD 100', after:'Meal → daily category cap: SGD 100; cap compliance checked against current + prior same-day spending.', draft:'Meal claims are subject to a cumulative daily limit of SGD 100. Claims exceeding this limit require escalation.', trace:['R-01 matches the meal category.','Current amount SGD 50 is within the SGD 100 individual cap.','Prior spending SGD 60 + current SGD 50 = SGD 110.','The owner-confirmed daily-intent assertion fails.'] },
 { title:'Receipt requirement missing at exactly SGD 50', type:'Structural gap', level:'Mechanically reproduced', scenario:'SCN-002', rule:'R-02 · R-03', facts:'Meal claim: exactly SGD 50. Receipt present. No prior meal spending.', expected:'The receipt requirement must be defined at the exact SGD 50 threshold.', observed:'Neither amount < SGD 50 nor amount > SGD 50 matches. Receipt requirement: GAP.', quote:rules[1].quote+' '+rules[2].quote, section:'4.1', before:'amount > SGD 50 → receipt required', after:'amount ≥ SGD 50 → receipt required', draft:'Receipts are required for claims of SGD 50 or more.', trace:['R-02: SGD 50 < SGD 50 → false.','R-03: SGD 50 > SGD 50 → false.','No applicable receipt effect survives.','Required receipt dimension resolves to GAP.'] },
 { title:'International hotel approval rules conflict', type:'Conflict', level:'Mechanically reproduced', scenario:'SCN-003', rule:'R-04 · R-05 · R-06', facts:'International hotel claim: SGD 220. No approval present.', expected:'International hotel claims must resolve to manager approval.', observed:'The hotel exception returns none, while the international rule returns manager. No override resolves the conflict.', quote:rules[3].quote+' '+rules[4].quote, section:'4.2', before:'International hotel → manager; no explicit overrides', after:'International hotel → manager; overrides general and hotel-exception approval effects', draft:'International hotel claims require manager approval, including claims below SGD 250.', trace:['R-04 matches hotel and SGD 220 < SGD 250 → none.','R-05 matches international hotel → manager.','R-06 general approval → none.','No explicit override. Surviving values conflict.'] },
];
export const scenarios = [
 ...findings.map((f,i)=>({id:f.scenario,category:i===1?'Boundary':'Adversarial',facts:f.facts,outcome:i===0?'Allowed':i===1?'Gap':'Conflict',assertion:'Failed',finding:i})),
 ...['Meal SGD 42, no receipt, no prior spending','Domestic hotel SGD 180, no approval','Transport SGD 120, receipt present','Airfare booked 21 days ahead, receipt present','Meal SGD 49.99, no prior spending','Meal SGD 50.01, receipt present','International hotel SGD 250, manager approval','Airfare booked 13 days ahead, manager approval','Transport SGD 200, receipt present','Meal SGD 30 + SGD 40 prior spending','Meal SGD 70, receipt present','Transport SGD 199.99, receipt present'].map((facts,i)=>({id:`SCN-${String(i+4).padStart(3,'0')}`,category:[4,5,6,7,8,11].includes(i)?'Boundary':'Normal',facts,outcome:'Resolved',assertion:'Passed',finding:null})),
];
export const stages=['Generate scenarios','Explore responses','Optional discussion','Evaluate actions','Calculate consequences','Freeze suite','Review findings'];
export const gates=['Same test suite','All targeted findings fixed','No new failures outside targets','No protected tests regressed','No new gaps, conflicts, inconclusive results, or errors','Unrelated rules unchanged','Held-back results did not worsen'];
