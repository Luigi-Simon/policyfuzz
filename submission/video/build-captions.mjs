import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HEADING = /^##\s+(\d+):(\d{2})[\u2013-](\d+):(\d{2})\s+—\s+(.+)$/gm;
const DEPENDENCY = /^\*\*(?:Capture|Evidence) dependenc(?:y|ies):\*\*/i;

function toMilliseconds(minutes, seconds) {
  return (Number(minutes) * 60 + Number(seconds)) * 1000;
}

function cleanNarration(markdown) {
  const lines = [];
  for (const raw of markdown.split(/\r?\n/)) {
    const line = raw.trim();
    if (DEPENDENCY.test(line)) break;
    if (!line || line.startsWith("#") || line.startsWith("|")) continue;
    lines.push(line);
  }
  return lines
    .join(" ")
    .replace(/\*\*/g, "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

export function parseTimedSections(markdown) {
  const headings = [...markdown.matchAll(HEADING)];
  return headings.map((match, index) => {
    const bodyStart = match.index + match[0].length;
    const bodyEnd = headings[index + 1]?.index ?? markdown.length;
    const narration = cleanNarration(markdown.slice(bodyStart, bodyEnd));
    if (!narration) throw new Error(`Timed section has no narration: ${match[5]}`);
    const startMs = toMilliseconds(match[1], match[2]);
    const endMs = toMilliseconds(match[3], match[4]);
    if (endMs <= startMs) throw new Error(`Invalid time range: ${match[0]}`);
    return { title: match[5].trim(), startMs, endMs, narration };
  });
}

function formatTimestamp(milliseconds) {
  const hours = Math.floor(milliseconds / 3_600_000);
  const minutes = Math.floor((milliseconds % 3_600_000) / 60_000);
  const seconds = Math.floor((milliseconds % 60_000) / 1000);
  const millis = milliseconds % 1000;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")},${String(millis).padStart(3, "0")}`;
}

function sentenceCues(section) {
  const sentences = section.narration
    .split(/(?<=[.!?])\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
  return sentences.map((text, index) => {
    const startMs = Math.round(
      section.startMs + ((section.endMs - section.startMs) * index) / sentences.length,
    );
    const endMs = Math.round(
      section.startMs + ((section.endMs - section.startMs) * (index + 1)) / sentences.length,
    );
    return { startMs, endMs, text };
  });
}

export function buildDraftSrt(markdown) {
  const sections = parseTimedSections(markdown);
  const cues = sections.flatMap(sentenceCues);
  return `${cues
    .map(
      (cue, index) =>
        `${index + 1}\n${formatTimestamp(cue.startMs)} --> ${formatTimestamp(cue.endMs)}\n${cue.text}`,
    )
    .join("\n\n")}\n`;
}

async function main() {
  const directory = path.dirname(fileURLToPath(import.meta.url));
  const scriptPath = path.resolve(process.argv[2] ?? path.join(directory, "script.md"));
  const outputPath = path.resolve(
    process.argv[3] ?? path.join(directory, "PolicyFuzz-Demo-Draft.srt"),
  );
  const markdown = await fs.readFile(scriptPath, "utf8");
  await fs.writeFile(outputPath, buildDraftSrt(markdown), "utf8");
  console.log(JSON.stringify({ scriptPath, outputPath, status: "draft" }));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
