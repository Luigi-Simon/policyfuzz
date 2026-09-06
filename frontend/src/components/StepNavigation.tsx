export type WorkflowStep = 'input' | 'evidence' | 'findings' | 'comparison';

const steps: ReadonlyArray<{ id: WorkflowStep; label: string }> = [
  { id: 'input', label: 'Input & contract' },
  { id: 'evidence', label: 'Run evidence' },
  { id: 'findings', label: 'Findings & revision' },
  { id: 'comparison', label: 'Comparison' },
];

export function StepNavigation({
  active,
  available = {},
  onNavigate,
}: {
  active: WorkflowStep;
  available?: Partial<Record<WorkflowStep, boolean>>;
  onNavigate?: (step: WorkflowStep) => void;
}) {
  return (
    <nav aria-label="Run workflow">
      <ol className="workflow-steps">
        {steps.map((step, index) => {
          const enabled = step.id === active || available[step.id] === true;
          return (
            <li key={step.id} aria-current={step.id === active ? 'step' : undefined}>
              <button type="button" disabled={!enabled} onClick={() => onNavigate?.(step.id)}>
                <span aria-hidden="true">{index + 1}</span> {step.label}
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
