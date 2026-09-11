"""Descriptive discussion diagnostics; never discard source evidence or score it."""

from collections import Counter, defaultdict


def discussion_quality(parsed):
    notes, groups = [], defaultdict(list)
    replies = [(record, parent) for record, parent in parsed if parent]
    for record, _ in replies:
        normalized = " ".join(record.content.split()).casefold()
        if len(normalized) >= 20:
            groups[normalized].append(record)
    duplicated = [
        records for records in groups.values() if len({r.author for r in records}) > 1
    ]
    if duplicated:
        count = sum(len(records) for records in duplicated)
        notes.append(
            f"discussion_quality: duplicate wording across participants in {count} reply records ({len(duplicated)} repeated text groups). Distinct native records are retained; repetition is not independent corroboration."
        )
    openings = {
        record.identifier
        for record, parent in parsed
        if record.kind == "post" and parent is None
    }
    parents = {record.identifier: parent for record, parent in parsed}
    roots = Counter()
    for _, parent in replies:
        seen = set()
        while parent in parents and parents[parent] and parent not in seen:
            seen.add(parent)
            parent = parents[parent]
        if parent in openings:
            roots[parent] += 1
    top = sum(count for _, count in roots.most_common(2))
    if len(openings) >= 5 and len(replies) >= 6 and top / len(replies) >= 0.75:
        notes.append(
            f"discussion_quality: concentrated replies; {top} of {len(replies)} replies target the two most-discussed opening threads, with replies reaching {len(roots)} of {len(openings)} openings. Participation counts alone do not establish breadth of discussion."
        )
    return notes
