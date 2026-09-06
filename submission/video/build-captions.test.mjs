import assert from "node:assert/strict";
import test from "node:test";

import { buildDraftSrt, parseTimedSections } from "./build-captions.mjs";

const script = `# Demo

## 0:00–0:20 — Hook

First sentence. Second sentence keeps the narration exact.

**Capture dependency:** frozen frame.

## 0:20–0:45 — Evidence

Ten scenarios expose three findings. All seven gates pass.
`;

test("parses timed narration while excluding dependency notes", () => {
  const sections = parseTimedSections(script);
  assert.equal(sections.length, 2);
  assert.deepEqual(
    sections.map(({ startMs, endMs }) => [startMs, endMs]),
    [
      [0, 20_000],
      [20_000, 45_000],
    ],
  );
  assert.match(sections[0].narration, /First sentence/);
  assert.doesNotMatch(sections[0].narration, /Capture dependency/);
});

test("builds ordered SRT cues that exactly cover narration sentences", () => {
  const srt = buildDraftSrt(script);
  assert.match(srt, /00:00:00,000 --> 00:00:10,000/);
  assert.match(srt, /00:00:20,000 --> 00:00:32,500/);
  assert.match(srt, /Ten scenarios expose three findings\./);
  assert.match(srt, /All seven gates pass\./);
  assert.doesNotMatch(srt, /dependency/);
});
