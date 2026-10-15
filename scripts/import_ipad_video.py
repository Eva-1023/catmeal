"""Copy the selected long video over AFC, without modifying the iPad.

Run with the existing pymobiledevice3 environment used for USB imports.
The stream SHA256 is independently compared with the saved file before rename.
"""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.afc import AfcService

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / os.environ.get("CATMEAL_IMPORT_DIR", "outputs/ipad-import")


async def main():
    candidates = json.loads((AUDIT / "long_video_candidates.json").read_text())
    selected = candidates[0]
    source = "/" + selected["directory"].strip("/") + "/" + selected["filename"]
    filename = selected["original_filename"] or selected["filename"]
    assert Path(filename).name == filename
    destination = ROOT / "data/videos" / filename
    partial = destination.with_name(destination.name + ".partial")
    if destination.exists() or partial.exists():
        raise FileExistsError(f"Refusing to overwrite: {destination} or {partial}")
    serial = os.environ.get("CATMEAL_IPAD_UDID")
    if not serial:
        raise SystemExit("Set CATMEAL_IPAD_UDID to the paired iPad identifier before importing.")
    async with await create_using_usbmux(serial=serial, connection_type="USB", autopair=False) as device:
        assert device.all_values["ProductType"].startswith("iPad")
        async with AfcService(lockdown=device) as afc:
            before = await afc.stat(source)
            size = before["st_size"]
            assert size == selected["original_size"], (size, selected["original_size"])
            assert shutil.disk_usage(destination.parent).free > size + 1024**3
            record = dict(status="copying", selected=selected, source=source,
                          destination=str(destination), source_stat=before,
                          started_utc=datetime.now(timezone.utc).isoformat())
            def save():
                (AUDIT / "transfer.json").write_text(json.dumps(record, ensure_ascii=False, indent=2, default=str))
            save()
            digest = hashlib.sha256()
            handle = await afc.fopen(source, "r")
            copied, milestone = 0, 1024**3
            started = time.monotonic()
            try:
                with partial.open("xb") as out:
                    while copied < size:
                        chunk = await afc.fread(handle, min(4*1024**2, size-copied))
                        if not chunk:
                            raise IOError(f"Unexpected EOF at {copied}/{size}")
                        out.write(chunk)
                        digest.update(chunk)
                        copied += len(chunk)
                        if copied >= milestone:
                            print(f"Copied {copied}/{size} bytes ({copied/size:.0%}), {time.monotonic()-started:.1f}s", flush=True)
                            milestone += 1024**3
                    out.flush()
                    os.fsync(out.fileno())
            finally:
                await afc.fclose(handle)
            after = await afc.stat(source)
            assert after["st_size"] == before["st_size"] and after["st_mtime"] == before["st_mtime"], "Source changed during copy"
            local_digest = hashlib.sha256()
            with partial.open("rb") as saved:
                for chunk in iter(lambda: saved.read(8*1024**2), b""):
                    local_digest.update(chunk)
            assert partial.stat().st_size == size and local_digest.hexdigest() == digest.hexdigest()
            partial.rename(destination)
            record.update(status="copied_and_hash_verified", bytes=size,
                          source_stream_sha256=digest.hexdigest(), local_file_sha256=local_digest.hexdigest(),
                          finished_utc=datetime.now(timezone.utc).isoformat(), elapsed_seconds=round(time.monotonic()-started,3))
            save()
            print(json.dumps(record, ensure_ascii=False, indent=2, default=str), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
