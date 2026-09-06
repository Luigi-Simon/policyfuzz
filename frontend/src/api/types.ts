import type { components as GeneratedComponents } from './generated';

/** The generated OpenAPI component registry. */
export type components = GeneratedComponents;

export type RunView = GeneratedComponents['schemas']['RunView'];
export type PublicError = GeneratedComponents['schemas']['PublicError'];
export type CreateRunRequest = GeneratedComponents['schemas']['CreateRunRequest'];
export type CreateRunResponse = GeneratedComponents['schemas']['CreateRunResponse'];
export type ConfirmContractRequest = GeneratedComponents['schemas']['ConfirmContractRequest'];
export type SelectFindingsRequest = GeneratedComponents['schemas']['SelectFindingsRequest'];
export type ConfirmRevisionRequest = GeneratedComponents['schemas']['ConfirmRevisionRequest'];
export type DeleteRunResponse = GeneratedComponents['schemas']['DeleteRunResponse'];
export type PendingConfirmation = NonNullable<RunView['pending_confirmation']>;
export type RuleSummary = GeneratedComponents['schemas']['RuleSummary'];
export type InvariantSummary = GeneratedComponents['schemas']['InvariantSummary'];
export type FindingDecision = GeneratedComponents['schemas']['FindingDecision'];
export type FindingSummary = GeneratedComponents['schemas']['FindingSummary'];
export type RevisionConfirmation = GeneratedComponents['schemas']['RevisionConfirmation'];
export type VisibleTraceSummary = GeneratedComponents['schemas']['VisibleTraceSummary'];
export type SourceSpan = GeneratedComponents['schemas']['SourceSpan'];
export type Effect = GeneratedComponents['schemas']['Effect'];
