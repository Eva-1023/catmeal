import os
"""Read media metadata and decode beginning/middle/end after USB copy."""
import json
from pathlib import Path
import av

root = Path(__file__).resolve().parents[1]
audit = root / os.environ.get("CATMEAL_IMPORT_DIR", "outputs/ipad-import") / "transfer.json"
record = json.loads(audit.read_text())
assert record["status"] == "copied_and_hash_verified"
path = Path(record["destination"])
assert path.stat().st_size == record["bytes"]
with av.open(str(path)) as container:
    stream = container.streams.video[0]
    duration = float(stream.duration * stream.time_base) if stream.duration else container.duration / av.time_base
    metadata = dict(duration_seconds=duration, width=stream.width, height=stream.height,
                    codec=stream.codec_context.name, average_fps=float(stream.average_rate) if stream.average_rate else None,
                    audio_streams=len(container.streams.audio), container_metadata=container.metadata)
    assert duration > 3600
    assert abs(duration - record["selected"]["duration"]) < 2
checks = []
for target in (0, duration / 2, duration - 2):
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        container.seek(int(target / stream.time_base), stream=stream, backward=True)
        for frame in container.decode(video=0):
            if frame.time is not None and float(frame.time) >= target:
                checks.append(dict(target_seconds=target, decoded_seconds=float(frame.time), width=frame.width, height=frame.height))
                break
        else:
            raise ValueError(f"No decoded frame at {target}s")
record["media_validation"] = metadata
record["decode_spot_checks"] = checks
record["status"] = "verified"
audit.write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(json.dumps(dict(file=str(path), bytes=record["bytes"], sha256=record["local_file_sha256"], **metadata, decode_spot_checks=checks), ensure_ascii=False, indent=2))
