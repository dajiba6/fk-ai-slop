"""Runs inside the ASR venv (funasr + torch), not the app venv.

Usage: asr_worker.py <audio> <out.json> <ffmpeg> <device> <batch>
Writes [{start, end, text}] with 30-second segments.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SEGMENT = 30


def main():
    audio, out, ffmpeg, device, batch = sys.argv[1:6]
    with tempfile.TemporaryDirectory(prefix="fk-asr-") as tmp:
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", audio, "-ar", "16000", "-ac", "1",
                        "-f", "segment", "-segment_time", str(SEGMENT), str(Path(tmp) / "seg%05d.wav")], check=True)
        segments = sorted(Path(tmp).glob("seg*.wav"))
        from funasr import AutoModel
        model = AutoModel(model="iic/SenseVoiceSmall", device=device, disable_update=True)
        cues = []
        size = int(batch)
        for start in range(0, len(segments), size):
            part = segments[start:start + size]
            results = model.generate(input=[str(p) for p in part], language="auto", use_itn=True,
                                     batch_size=len(part))
            for offset, result in enumerate(results):
                text = re.sub(r"<\|[^|]*\|>", "", result.get("text") or "").strip()
                if text:
                    index = start + offset
                    cues.append({"start": index * SEGMENT, "end": (index + 1) * SEGMENT, "text": text})
    Path(out).write_text(json.dumps(cues, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
