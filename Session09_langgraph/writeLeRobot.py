"""
LeRobot Dataset Reader (No Hardware)

This sample shows how to:
1) Load a public LeRobot-compatible dataset from Hugging Face
2) Inspect top-level schema/features
3) Read one sample safely and summarize key robotics fields

Install dependencies (example):
    pip install lerobot datasets

Run:
    python Session09_langgraph/writeLeRobot.py

Expected output (high-level):
    - Dependency check status
    - Dataset split and sample count
    - Top-level feature keys
    - A concise summary of one sample (action/state/images/timestamp if present)
"""

from __future__ import annotations

import sys
from typing import Any


# Editable constants
DATASET_REPO_ID = "lerobot/pusht"
DATASET_SPLIT = "train"
SAMPLE_INDEX = 0


def _safe_shape(value: Any) -> str:
    """Return a compact shape string when available."""
    shape = getattr(value, "shape", None)
    if shape is None:
        return "n/a"
    try:
        return str(tuple(shape))
    except Exception:
        return str(shape)


def _safe_dtype(value: Any) -> str:
    """Return a compact dtype string when available."""
    dtype = getattr(value, "dtype", None)
    if dtype is None:
        return "n/a"
    return str(dtype)


def describe_value(name: str, value: Any) -> None:
    """Print concise metadata for a value."""
    value_type = type(value).__name__
    shape = _safe_shape(value)
    dtype = _safe_dtype(value)

    if isinstance(value, dict):
        nested_keys = list(value.keys())
        print(f"- {name}: dict(keys={nested_keys})")
        return

    if isinstance(value, (list, tuple)):
        size = len(value)
        if size > 0:
            first_type = type(value[0]).__name__
            print(f"- {name}: {value_type}(len={size}, first_item_type={first_type})")
        else:
            print(f"- {name}: {value_type}(len=0)")
        return

    print(f"- {name}: type={value_type}, shape={shape}, dtype={dtype}")


def _find_keys_containing(sample: dict[str, Any], keyword: str) -> list[str]:
    keyword = keyword.lower()
    return [k for k in sample.keys() if keyword in k.lower()]


def _print_nested_image_hints(sample: dict[str, Any]) -> None:
    """Check common nested image locations without deep recursion."""
    obs = sample.get("observation")
    if isinstance(obs, dict):
        image_keys = [k for k in obs.keys() if "image" in k.lower() or "rgb" in k.lower()]
        if image_keys:
            print("\nNested observation image-like keys:")
            for k in image_keys:
                describe_value(f"observation.{k}", obs[k])

        obs_images = obs.get("images")
        if isinstance(obs_images, dict):
            print("\nObservation camera image entries:")
            for cam_name, cam_value in obs_images.items():
                describe_value(f"observation.images.{cam_name}", cam_value)


def print_sample_summary(sample: dict[str, Any]) -> None:
    """Print a robust summary of common robotics sample fields."""
    if not isinstance(sample, dict):
        print(f"Unexpected sample type: {type(sample).__name__}")
        return

    print("\nSample top-level keys:")
    print(list(sample.keys()))

    print("\nCommon robotics fields:")
    for field in ("action", "state", "observation", "timestamp"):
        if field in sample:
            describe_value(field, sample[field])
        else:
            print(f"- {field}: not present")

    image_like_keys = _find_keys_containing(sample, "image")
    if image_like_keys:
        print("\nTop-level image-like keys:")
        for key in image_like_keys:
            describe_value(key, sample[key])
    else:
        print("\nTop-level image-like keys: none found")

    # Optional metadata keys seen in many robotics datasets.
    optional_meta = ("episode_index", "frame_index", "index", "task", "language_instruction")
    found_meta = [k for k in optional_meta if k in sample]
    if found_meta:
        print("\nOptional metadata:")
        for key in found_meta:
            describe_value(key, sample[key])
    else:
        print("\nOptional metadata: none found")

    _print_nested_image_hints(sample)


def main() -> None:
    print("LeRobot dataset reader (no hardware)")
    print(f"Dataset repo: {DATASET_REPO_ID}")
    print(f"Split: {DATASET_SPLIT}")
    print(f"Requested sample index: {SAMPLE_INDEX}")

    try:
        import datasets
    except ImportError:
        print("\nMissing dependency: datasets")
        print("Install with: pip install datasets")
        sys.exit(1)

    try:
        import lerobot
        lerobot_version = getattr(lerobot, "__version__", "unknown")
        print(f"LeRobot package detected (version: {lerobot_version})")
    except ImportError:
        print("\nMissing dependency: lerobot")
        print("Install with: pip install lerobot")
        sys.exit(1)

    try:
        dataset = datasets.load_dataset(DATASET_REPO_ID, split=DATASET_SPLIT)
    except Exception as exc:
        print("\nFailed to load dataset.")
        print(f"Repo/split: {DATASET_REPO_ID} / {DATASET_SPLIT}")
        print(f"Error: {exc}")
        print("Check internet access, repo id, and split name.")
        sys.exit(1)

    total = len(dataset)
    print(f"\nLoaded split '{DATASET_SPLIT}' with {total} samples.")
    if total == 0:
        print("Dataset split is empty. Nothing to inspect.")
        return

    print("\nTop-level feature keys:")
    if getattr(dataset, "features", None) is not None:
        feature_keys = list(dataset.features.keys())
        print(feature_keys)
    else:
        print("No feature metadata available.")

    safe_index = max(0, min(SAMPLE_INDEX, total - 1))
    if safe_index != SAMPLE_INDEX:
        print(f"\nAdjusted sample index from {SAMPLE_INDEX} to {safe_index} (valid range: 0..{total - 1})")

    sample = dataset[safe_index]
    print_sample_summary(sample)


if __name__ == "__main__":
    main()
