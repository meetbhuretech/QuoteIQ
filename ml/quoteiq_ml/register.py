"""Record a candidate manifest. This does not activate a model."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def register_candidate() -> dict:
    metadata_path = ROOT / "artifacts" / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    manifest = {
        "stage": "candidate",
        "version": metadata["version"],
        "data_origin": metadata["data_origin"],
        "production_ready": False,
        "action": "An organization admin must import this candidate and explicitly promote it. This step does not deploy the model.",
    }
    path = ROOT / "artifacts" / "registry_candidate.json"
    path.write_text(json.dumps(manifest, indent=2))
    return manifest


if __name__ == "__main__":
    print(json.dumps(register_candidate(), indent=2))
