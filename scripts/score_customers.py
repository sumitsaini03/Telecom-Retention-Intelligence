"""Score a feature-only customer CSV with the trained XGBoost artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import MODEL_ARTIFACT
from src.inference import load_model_artifact, score_customers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="CSV with the model feature columns and optional customerID")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "inference_scores.csv")
    parser.add_argument("--model", type=Path, default=MODEL_ARTIFACT)
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"Input CSV not found: {args.input}")
    customers = pd.read_csv(args.input, dtype={"customerID": "string"})
    artifact = load_model_artifact(args.model)
    results = score_customers(customers, artifact)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output, index=False)
    print(f"Scored {len(results):,} rows with {artifact['model_identifier']}; output: {args.output}")


if __name__ == "__main__":
    main()
