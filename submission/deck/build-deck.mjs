import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const outPath = process.argv[2] || path.join(__dirname, "PolicyFuzz-Pitch-Draft.pptx");
const renderDir = process.argv[3] || path.join(__dirname, ".rendered-draft");

const W = 1280;
const H = 720;
const C = {
  bg: "#F2F5F5",
  paper: "#FFFFFF",
  navy: "#102A43",
  navy2: "#243B53",
  teal: "#0D9488",
  tealDark: "#0F766E",
  tealPale: "#DDF4F1",
  bluePale: "#E6EEF5",
  grey: "#627D8C",
  mid: "#9FB3C8",
  line: "#CBD7DE",
  amber: "#B7791F",
  amberPale: "#FFF3D6",
  red: "#B74D4D",
  redPale: "#FCE8E8",
};

function box(slide, x, y, w, h, fill = "none", line = "none", radius = 0, name = undefined) {
  return slide.shapes.add({
    geometry: radius ? "roundRect" : "rect",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: line === "none" ? 0 : 1.2 },
    borderRadius: radius || undefined,
  });
}

function txt(slide, text, x, y, w, h, opts = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name: opts.name,
    position: { left: x, top: y, width: w, height: h },
    fill: opts.fill || "none",
    line: { style: "solid", fill: opts.line || "none", width: opts.line && opts.line !== "none" ? 1 : 0 },
    borderRadius: opts.radius,
  });
  shape.text = text;
  shape.text.style = {
    fontFamily: "Aptos",
    fontSize: opts.size || 24,
    bold: opts.bold || false,
    color: opts.color || C.navy,
    alignment: opts.align || "left",
    italic: opts.italic || false,
  };
  shape.text.verticalAlignment = opts.valign || "top";
  return shape;
}

function line(slide, x, y, w, h = 0, color = C.line, width = 2, dash = "solid") {
  return slide.shapes.add({
    geometry: "line",
    position: { left: x, top: y, width: w, height: h },
    fill: "none",
    line: { style: dash, fill: color, width },
  });
}

function base(slide, n, kicker) {
  slide.background.fill = C.bg;
  box(slide, 0, 0, 16, H, C.teal, "none");
  txt(slide, kicker.toUpperCase(), 66, 38, 620, 28, { size: 15, bold: true, color: C.tealDark });
  txt(slide, `0${n}`, 1164, 38, 52, 26, { size: 15, bold: true, color: C.grey, align: "right" });
  line(slide, 66, 678, 1150, 0, C.line, 1);
  txt(slide, "POLICYFUZZ · REVIEWABLE DRAFT", 66, 686, 340, 18, { size: 11, bold: true, color: C.grey });
}

function title(slide, text, y = 78, size = 40, w = 1120) {
  return txt(slide, text, 66, y, w, 66, { size, bold: true, color: C.navy });
}

function label(slide, text, x, y, w, color = C.tealDark, fill = C.tealPale) {
  return txt(slide, text.toUpperCase(), x, y, w, 34, {
    size: 13, bold: true, color, fill, radius: 14, align: "center", valign: "middle",
  });
}

function notes(slide, lines, sources) {
  slide.speakerNotes.textFrame.setText([
    ...lines,
    "",
    "[Sources]",
    ...sources.map((s) => `- ${s}`),
    "[/Sources]",
  ]);
  slide.speakerNotes.setVisible(false);
}

function addBullet(slide, marker, heading, body, x, y, w) {
  txt(slide, marker.slice(-1), x, y, 48, 48, { size: 22, bold: true, color: C.paper, fill: C.teal, radius: 24, align: "center", valign: "middle" });
  txt(slide, heading, x + 70, y - 1, w - 70, 34, { size: 22, bold: true, color: C.navy });
  txt(slide, body, x + 70, y + 36, w - 70, 58, { size: 17, color: C.grey });
}

const deck = Presentation.create({ slideSize: { width: W, height: H } });

// 1 — hook
{
  const s = deck.slides.add();
  s.background.fill = C.navy;
  box(s, 0, 0, 16, H, C.teal, "none");
  line(s, 66, 100, 130, 0, C.teal, 5);
  txt(s, "POLICYFUZZ", 66, 54, 240, 30, { size: 16, bold: true, color: "#7DE2D7" });
  txt(s, "Policies have prose reviews,\nbut no unit tests", 66, 150, 920, 180, { size: 58, bold: true, color: C.paper });
  txt(s, "A prototype for turning session-confirmed travel & expense intent into traceable scenarios and deterministic checks.", 70, 374, 820, 112, { size: 26, color: "#D9E7EE" });
  label(s, "Synthetic prototype · validation pending", 70, 548, 410, "#D7F7F2", "#174A55");
  txt(s, "Narrow claim", 982, 520, 208, 24, { size: 14, bold: true, color: "#7DE2D7", align: "right" });
  txt(s, "Make ambiguity\nexecutable — then test it.", 874, 554, 316, 90, { size: 22, bold: true, color: C.paper, align: "right" });
  notes(s,
    ["Open with the gap between prose review and executable regression evidence.", "State that this is a prototype and that validation remains pending."],
    ["docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 24, slide 1", "docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §§17 and 19"]
  );
}

// 2 — target user hypothesis
{
  const s = deck.slides.add();
  base(s, 2, "User hypothesis");
  title(s, "One owner carries every edge case in their head");
  txt(s, "FINANCE / PEOPLE OPS", 70, 174, 355, 30, { size: 17, bold: true, color: C.tealDark });
  txt(s, "Policy owner", 70, 212, 355, 64, { size: 37, bold: true });
  txt(s, "Maintains rules, fields exceptions, and explains decisions across many combinations of amount, category, timing, destination, and prior spend.", 70, 292, 390, 150, { size: 21, color: C.grey });
  label(s, "Hypothesis — not user research", 70, 480, 318, C.amber, C.amberPale);
  line(s, 518, 170, 0, 416, C.line, 2);
  addBullet(s, "01", "Thresholds hide boundary gaps", "Manual review can miss equality cases and adjacent ranges.", 570, 178, 590);
  addBullet(s, "02", "Exceptions collide across clauses", "Priority and overrides may exist only in reviewers’ memory.", 570, 318, 590);
  addBullet(s, "03", "Change review lacks a fixed regression set", "A wording fix can shift a different outcome without a visible trace.", 570, 458, 590);
  notes(s,
    ["Frame the user and burden as a product hypothesis, not market validation.", "Use Finance and People Ops as the initial T&E owners identified in the approved scope."],
    ["docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 24, slide 2", "docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §§1, 12.3 and 17"]
  );
}

// 3 — journey
{
  const s = deck.slides.add();
  base(s, 3, "Product journey");
  title(s, "The journey ends in a retest, not a summary");
  const steps = [
    ["01", "UPLOAD", "Synthetic or non-confidential text"],
    ["02", "CONFIRM", "Cited rules and session intent"],
    ["03", "FUZZ", "Boundaries and combinations"],
    ["04", "REVISE", "Structured diff for review"],
    ["05", "RETEST", "The identical frozen suite"],
  ];
  const xs = [70, 300, 530, 760, 990];
  for (let i = 0; i < 4; i++) {
    slideArrow(s, xs[i] + 164, 305, 58);
  }
  steps.forEach((step, i) => {
    txt(s, step[0], xs[i], 224, 64, 34, { size: 15, bold: true, color: C.tealDark });
    line(s, xs[i], 270, 172, 0, i === 4 ? C.teal : C.line, i === 4 ? 5 : 2);
    txt(s, step[1], xs[i], 294, 174, 46, { size: 24, bold: true });
    txt(s, step[2], xs[i], 356, 176, 92, { size: 17, color: C.grey });
  });
  box(s, 70, 492, 1094, 106, C.paper, C.line, 12);
  txt(s, "Why it differs from summarization", 96, 510, 330, 62, { size: 20, bold: true, color: C.tealDark, valign: "middle" });
  txt(s, "Every finding should resolve to visible facts, a deterministic trace, and an exact source citation — then survive the same-suite comparison.", 440, 510, 690, 62, { size: 19, color: C.navy2 });
  label(s, "Live / cached mode stays visible", 820, 606, 344);
  notes(s,
    ["Walk left to right through the approved user journey.", "A mode label must distinguish live behavior from cached recorded artifacts."],
    ["docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 24, slides 3 and video plan", "docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §§9, 12.2 and 17"]
  );
}

function slideArrow(slide, x, y, w) {
  const a = slide.shapes.add({
    geometry: "rightArrow",
    position: { left: x, top: y, width: w, height: 22 },
    fill: C.line,
    line: { style: "solid", fill: "none", width: 0 },
  });
  return a;
}

// 4 — bounded agent loop
{
  const s = deck.slides.add();
  base(s, 4, "Bounded agent loop");
  title(s, "One targeted cycle closes coverage — or stops");
  line(s, 110, 320, 1000, 0, C.line, 4);
  const stages = [
    ["PLAN", "Required targets"],
    ["ACT", "Candidate scenarios"],
    ["OBSERVE", "Coverage gaps"],
    ["ADAPT", "One targeted batch"],
    ["RETEST", "Freeze + execute"],
  ];
  stages.forEach((st, i) => {
    const x = 84 + i * 232;
    txt(s, `${i + 1}`, x, 284, 64, 64, { size: 24, bold: true, color: C.paper, fill: i === 4 ? C.navy : C.teal, radius: 32, align: "center", valign: "middle" });
    txt(s, st[0], x - 38, 382, 140, 32, { size: 19, bold: true, color: i === 4 ? C.navy : C.tealDark, align: "center" });
    txt(s, st[1], x - 58, 428, 180, 58, { size: 16, color: C.grey, align: "center" });
  });
  box(s, 748, 526, 414, 78, C.amberPale, "none", 12);
  txt(s, "Bound", 772, 545, 74, 24, { size: 15, bold: true, color: C.amber });
  txt(s, "At most one targeted generation cycle before suite freeze.", 852, 538, 284, 44, { size: 17, bold: true, color: C.navy2 });
  notes(s,
    ["Explain that the agentic behavior is bounded by a single targeted cycle.", "If coverage remains insufficient, the workflow stops rather than expanding without limit."],
    ["docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Tasks 9 and 24", "docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §12.2 frozen-suite procedure"]
  );
}

// 5 — architecture diagram
{
  const s = deck.slides.add();
  base(s, 5, "Target architecture · integration pending");
  title(s, "Models propose; deterministic Python decides");
  // Connectors first so they remain behind nodes.
  slideArrow(s, 420, 312, 90);
  slideArrow(s, 770, 312, 90);
  line(s, 814, 188, 0, 396, C.teal, 3, "dashed");
  txt(s, "TRUST\nBOUNDARY", 762, 590, 104, 48, { size: 12, bold: true, color: C.tealDark, align: "center", valign: "middle" });
  box(s, 72, 210, 350, 338, C.paper, C.line, 16);
  txt(s, "LLM-backed stages", 98, 238, 298, 40, { size: 27, bold: true, color: C.navy });
  label(s, "Proposal only", 98, 294, 154);
  txt(s, "Interpret clauses\nSuggest invariants\nExplore scenario facts\nPropose a minimal revision", 100, 354, 286, 142, { size: 20, color: C.grey });
  box(s, 494, 248, 280, 260, C.tealPale, "none", 16);
  txt(s, "Public workflow", 520, 278, 228, 36, { size: 25, bold: true, color: C.tealDark, align: "center" });
  txt(s, "RunView\ncommands\nartifacts", 530, 350, 208, 110, { size: 22, bold: true, color: C.navy, align: "center", valign: "middle" });
  box(s, 848, 190, 344, 378, C.navy, "none", 16);
  txt(s, "Deterministic Python", 876, 222, 290, 42, { size: 27, bold: true, color: C.paper });
  label(s, "Authoritative", 876, 282, 166, "#D7F7F2", "#174A55");
  txt(s, "Validate schemas + citations\nResolve effects + traces\nFreeze + hash the suite\nCompute metrics\nGate patch acceptance", 878, 344, 282, 168, { size: 20, color: "#D9E7EE" });
  notes(s,
    ["Use the diagram to make the model/Python responsibility split explicit.", "This is the approved target modular-monolith architecture; final integration remains pending."],
    ["docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §§3, 7, 9 and 11", "docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 24, slide 5", "team/person-1-integration/HANDOFF.md — current integration limitations"]
  );
}

// 6 — planned cases
{
  const s = deck.slides.add();
  base(s, 6, "Planned development cases · synthetic");
  title(s, "Three planned cases make ambiguity executable");
  const rows = [
    ["01", "THRESHOLD GAP", "SGD 50.00 receipt claim", "below 50 ≠ above 50", "Equality has no matching rule"],
    ["02", "HOTEL CONFLICT", "International hotel · SGD 249.00", "no approval ↔ manager approval", "No override resolves the clash"],
    ["03", "DAILY CAP BREACH", "Meal SGD 60 + prior SGD 50", "eligible per claim → daily total 110", "Confirmed daily intent is breached"],
  ];
  rows.forEach((r, i) => {
    const y = 180 + i * 132;
    line(s, 70, y + 112, 1094, 0, C.line, 1);
    txt(s, r[0], 70, y + 4, 58, 36, { size: 17, bold: true, color: C.tealDark });
    txt(s, r[1], 138, y, 212, 34, { size: 19, bold: true });
    txt(s, r[2], 138, y + 48, 300, 34, { size: 17, color: C.grey });
    txt(s, r[3], 486, y + 6, 302, 42, { size: 20, bold: true, color: i === 0 ? C.red : C.tealDark });
    txt(s, r[4], 486, y + 54, 304, 38, { size: 16, color: C.grey });
    label(s, "Trace + citation pending", 858, y + 28, 262, C.amber, C.amberPale);
  });
  txt(s, "PLANNED", 70, 594, 106, 24, { size: 14, bold: true, color: C.amber });
  txt(s, "Final witnesses, authoritative traces, and exact policy citations will be captured only from the verified build.", 180, 586, 900, 46, { size: 17, color: C.navy2 });
  notes(s,
    ["Describe these as synthetic planned development cases, not observed findings.", "The amount facts instantiate the approved defect definitions; final witnesses, traces, and policy-span citations remain capture dependencies."],
    ["docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §12.1 development demonstration cases", "docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 21 fixture contract and Task 24, slide 6"]
  );
}

// 7 — pending evidence
{
  const s = deck.slides.add();
  base(s, 7, "Evidence plan");
  title(s, "Measured results wait for a frozen evidence chain");
  label(s, "Measured results: pending", 70, 158, 254, C.amber, C.amberPale);
  const columns = [
    ["DEVELOPMENT", "Known synthetic defects", "Exact finding match\nCitation integrity\nCoverage + replay\nSame-suite patch gates"],
    ["CORRECTED CONTROL", "Regression challenge", "No confirmed target defect\nProtected assertions\nNo new gaps or conflicts\nSame engine + suite"],
    ["BLIND", "Late-sealed candidate", "Human review pending\nScoring-ineligible\nFirst-run custody required\nNo headline claim"],
  ];
  columns.forEach((c, i) => {
    const x = 70 + i * 372;
    box(s, x, 224, 338, 302, i === 2 ? C.amberPale : C.paper, i === 2 ? "#E7C98A" : C.line, 14);
    txt(s, c[0], x + 22, 248, 294, 28, { size: 16, bold: true, color: i === 2 ? C.amber : C.tealDark });
    txt(s, c[1], x + 22, 292, 294, 58, { size: 24, bold: true });
    txt(s, c[2], x + 22, 374, 292, 124, { size: 17, color: C.grey });
  });
  txt(s, "Release chain", 70, 566, 120, 26, { size: 15, bold: true, color: C.grey });
  txt(s, "Gate B report  →  demo-core-v1  →  6-hour freeze  →  evidence capture  →  reviewer checks", 194, 560, 946, 34, { size: 18, bold: true, color: C.navy2 });
  txt(s, "Results will be reported with their frozen suite, engine, and source evidence.", 194, 606, 938, 34, { size: 16, color: C.tealDark });
  notes(s,
    ["Do not present placeholder values as measurements.", "Explain the evidence chain and disclose the blind candidate's late seal, delegated-agent authorship, pending human review, and scoring ineligibility."],
    ["docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Gate B and Task 24, steps 1–2", "docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §§12.2–12.4 and 18", "submission/evidence/benchmark-v2/README.md", "submission/evidence/benchmark-v2/provenance.json"]
  );
}

// 8 — impact hypothesis
{
  const s = deck.slides.add();
  base(s, 8, "Impact hypothesis");
  title(s, "The impact hypothesis is better review evidence");
  txt(s, "TODAY", 70, 184, 120, 26, { size: 15, bold: true, color: C.grey });
  txt(s, "Policy review relies on memory, spot checks, and examples that change between reviewers.", 70, 224, 450, 116, { size: 28, bold: true, color: C.navy });
  line(s, 580, 176, 0, 420, C.line, 2);
  txt(s, "HYPOTHESIS", 636, 184, 146, 26, { size: 15, bold: true, color: C.tealDark });
  addBullet(s, "01", "Broader review coverage", "Systematic boundaries and combinations expose what was exercised.", 636, 230, 510);
  addBullet(s, "02", "Traceable decisions", "Facts, rule paths, and citations make disagreements inspectable.", 636, 360, 510);
  addBullet(s, "03", "Regression evidence", "The same frozen suite tests a confirmed structured change.", 636, 490, 510);
  label(s, "No ROI or savings claim before measurement", 70, 528, 420, C.amber, C.amberPale);
  txt(s, "Future proof points", 70, 584, 146, 24, { size: 14, bold: true, color: C.grey });
  txt(s, "time to first actionable finding · total run time · confirmations · model calls · provider cost or N/A", 226, 578, 840, 40, { size: 16, color: C.navy2 });
  notes(s,
    ["Keep impact language explicitly hypothetical until tagged-build measurements exist.", "The approved business proxies are operational measurements, not ROI or user-validation claims."],
    ["docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §12.3 operational business proxies", "docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 24, slides 7–8"]
  );
}

// 9 — close
{
  const s = deck.slides.add();
  s.background.fill = C.navy;
  box(s, 0, 0, 16, H, C.teal, "none");
  txt(s, "09 · LIMITS, TEAM, REPOSITORY", 66, 42, 500, 28, { size: 15, bold: true, color: "#7DE2D7" });
  txt(s, "A narrow prototype\nwith a clear finish line", 66, 110, 740, 138, { size: 50, bold: true, color: C.paper });
  txt(s, "The intended proof", 70, 294, 210, 28, { size: 16, bold: true, color: "#7DE2D7" });
  txt(s, "A session-confirmed structured change fixes targeted failures and introduces no protected regressions in the disclosed frozen suite.", 70, 336, 690, 118, { size: 26, color: "#D9E7EE" });
  line(s, 810, 98, 0, 500, "#476779", 2);
  txt(s, "Limits", 858, 108, 260, 34, { size: 24, bold: true, color: C.paper });
  txt(s, "Prototype; validation pending\nSynthetic T&E scope\nNo legal-compliance claim\nNo automatic publication\nHuman confirmation remains required", 858, 164, 326, 150, { size: 18, color: "#D9E7EE" });
  txt(s, "Five-person ownership", 858, 350, 300, 34, { size: 24, bold: true, color: C.paper });
  txt(s, "P1 integration · P2 policy · P3 fuzzing\nP4 evaluation · P5 product", 858, 402, 332, 70, { size: 17, color: "#D9E7EE" });
  txt(s, "github.com/Luigi-Simon/policyfuzz", 858, 526, 330, 34, { size: 17, bold: true, color: "#7DE2D7" });
  label(s, "Validation pending", 70, 558, 196, "#D7F7F2", "#174A55");
  txt(s, "Next: capture verified results and footage after Gate B.", 286, 558, 486, 36, { size: 17, color: C.paper, valign: "middle" });
  notes(s,
    ["Close on the narrow intended proof, then state the present limitations plainly.", "Team roles are ownership areas only; no individual names are invented."],
    ["docs/superpowers/specs/2026-09-04-policyfuzz-design.md — §§11, 18 and 19", "docs/superpowers/plans/2026-09-04-policyfuzz-implementation.md — Task 24, slide 9", "AGENTS.md and team/person-5-product/AGENTS.md", "git remote origin — https://github.com/Luigi-Simon/policyfuzz"]
  );
}

await fs.mkdir(path.dirname(outPath), { recursive: true });
await fs.mkdir(renderDir, { recursive: true });

for (const [i, slide] of deck.slides.items.entries()) {
  const png = await deck.export({ slide, format: "png", scale: 1.5 });
  await fs.writeFile(path.join(renderDir, `slide-${i + 1}.png`), new Uint8Array(await png.arrayBuffer()));
  const layout = await slide.export({ format: "layout" });
  await fs.writeFile(path.join(renderDir, `slide-${i + 1}.layout.json`), await layout.text());
}

const montage = await deck.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(path.join(renderDir, "montage.webp"), new Uint8Array(await montage.arrayBuffer()));

const pptx = await PresentationFile.exportPptx(deck);
await pptx.save(outPath);
console.log(JSON.stringify({ outPath, renderDir, slideCount: deck.slides.items.length }, null, 2));
