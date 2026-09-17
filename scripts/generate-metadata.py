import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
for vehicle, profile in [("ArduCopter", "copter"), ("ArduPlane", "plane"), ("Rover", "rover")]:
    folder = root / "runtime/metadata" / profile
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "generation.log").open("w") as log:
        subprocess.run(
            [
                sys.executable,
                str(root / "ardupilot/Tools/autotest/param_metadata/param_parse.py"),
                "--vehicle",
                vehicle,
                "--format",
                "json",
            ],
            cwd=folder,
            stdout=log,
            stderr=log,
            check=True,
        )
    print("Generated pinned metadata:", profile)
