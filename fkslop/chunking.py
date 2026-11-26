import re

TARGET = 1200
LIMIT = 1500
_CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")
_WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")


def size(text):
    """Chinese characters and Latin words count the same, so both languages get comparable chunks."""
    return len(_CJK.findall(text)) + len(_WORD.findall(text))


def join_cues(texts):
    out = ""
    for text in texts:
        if out and (_CJK.match(out[-1]) or _CJK.match(text[:1])):
            out += text if out[-1] in "，。！？、；：,.!?" else "，" + text
        else:
            out += (" " if out else "") + text
    return out


def transcript_chunks(cues):
    chunks, current, current_size = [], [], 0
    for cue in cues:
        current.append(cue)
        current_size += size(cue["text"])
        if current_size >= TARGET:
            chunks.append(current)
            current = [current[-1]]
            current_size = size(current[0]["text"])
    if current and (not chunks or len(current) > 1):
        chunks.append(current)
    return [{"start": group[0]["start"], "end": group[-1]["end"], "section": None,
             "text": join_cues([c["text"] for c in group])} for group in chunks]


def markdown_chunks(body):
    sections, heading, lines = [], None, []
    for line in body.splitlines():
        match = re.match(r"^#{1,4}\s+(.*)", line)
        if match:
            if "".join(lines).strip():
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = match.group(1).strip(), []
        else:
            lines.append(line)
    if "".join(lines).strip():
        sections.append((heading, "\n".join(lines).strip()))

    chunks = []
    for heading, text in sections:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        buffer = []
        for paragraph in paragraphs:
            if buffer and size("\n\n".join(buffer + [paragraph])) > LIMIT:
                chunks.append({"section": heading, "text": "\n\n".join(buffer)})
                buffer = []
            buffer.append(paragraph)
        if buffer:
            merged = "\n\n".join(buffer)
            if chunks and chunks[-1]["section"] == heading and size(merged) < 200 \
                    and size(chunks[-1]["text"]) + size(merged) <= LIMIT:
                chunks[-1]["text"] += "\n\n" + merged
            else:
                chunks.append({"section": heading, "text": merged})
    return [{"start": None, "end": None, **c} for c in chunks]
