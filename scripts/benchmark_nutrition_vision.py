"""Benchmark Gemini vision accuracy for meal macro estimation.

Usage:
    python scripts/benchmark_nutrition_vision.py --model gemini-2.5-flash
    python scripts/benchmark_nutrition_vision.py --model gemini-2.5-pro

Requires a benchmark dataset at data/nutrition_benchmark/ with:
    - photos/001.jpg, 002.jpg, ...
    - ground_truth.json with expected macros per photo

Ground truth format:
    [
        {"file": "001.jpg", "calories": 500, "protein_g": 35, "carbs_g": 60, "fat_g": 15},
        ...
    ]
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from google.genai import types
from google import genai

ANALYSIS_PROMPT = """Analyze this meal photo and estimate:
- Total calories
- Protein (grams)
- Carbs (grams)
- Fat (grams)

Return ONLY a JSON object: {"calories": N, "protein_g": N, "carbs_g": N, "fat_g": N}"""


def run_benchmark(model_name: str, data_dir: str):
    """Run benchmark against ground truth dataset."""
    client = genai.Client(vertexai=True)
    gt_path = Path(data_dir) / "ground_truth.json"

    if not gt_path.exists():
        print(f"Ground truth not found at {gt_path}")
        print("Create data/nutrition_benchmark/ground_truth.json with format:")
        print(
            '[{"file": "001.jpg", "calories": 500, "protein_g": 35, '
            '"carbs_g": 60, "fat_g": 15}, ...]'
        )
        return

    with open(gt_path) as f:
        ground_truth = json.load(f)

    results = []
    for entry in ground_truth:
        photo_path = Path(data_dir) / "photos" / entry["file"]
        if not photo_path.exists():
            print(f"  SKIP {entry['file']} -- file not found")
            continue

        image_bytes = photo_path.read_bytes()
        content = types.Content(
            role="user",
            parts=[
                types.Part.from_image(
                    image=types.Image.from_bytes(
                        data=image_bytes, mime_type="image/jpeg"
                    )
                ),
                types.Part.from_text(text=ANALYSIS_PROMPT),
            ],
        )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=content,
            )
            text = response.text.strip()
            # Parse JSON from response (handle markdown code blocks)
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()
            predicted = json.loads(text)
        except Exception as e:
            print(f"  ERROR {entry['file']}: {e}")
            continue

        # Compute error percentages
        errors = {}
        for key in ["calories", "protein_g", "carbs_g", "fat_g"]:
            actual = entry[key]
            pred = predicted.get(key, 0)
            pct_err = abs(pred - actual) / actual * 100 if actual > 0 else 0
            errors[key] = round(pct_err, 1)

        results.append(
            {
                "file": entry["file"],
                "actual": entry,
                "predicted": predicted,
                "error_pct": errors,
            }
        )
        print(
            f"  {entry['file']}: "
            f"cal_err={errors['calories']}% "
            f"prot_err={errors['protein_g']}%"
        )

    # Summary statistics
    if results:
        avg_cal_err = sum(r["error_pct"]["calories"] for r in results) / len(results)
        avg_prot_err = sum(r["error_pct"]["protein_g"] for r in results) / len(results)
        avg_carb_err = sum(r["error_pct"]["carbs_g"] for r in results) / len(results)
        avg_fat_err = sum(r["error_pct"]["fat_g"] for r in results) / len(results)

        print(f"\n=== BENCHMARK RESULTS: {model_name} ===")
        print(f"Samples: {len(results)}")
        print(f"Avg calorie error: {avg_cal_err:.1f}%")
        print(f"Avg protein error: {avg_prot_err:.1f}%")
        print(f"Avg carbs error:   {avg_carb_err:.1f}%")
        print(f"Avg fat error:     {avg_fat_err:.1f}%")

        # Save results
        out_path = Path(data_dir) / f"results_{model_name.replace('/', '_')}.json"
        with open(out_path, "w") as f:
            json.dump(
                {
                    "model": model_name,
                    "results": results,
                    "summary": {
                        "avg_calorie_error_pct": round(avg_cal_err, 1),
                        "avg_protein_error_pct": round(avg_prot_err, 1),
                        "avg_carbs_error_pct": round(avg_carb_err, 1),
                        "avg_fat_error_pct": round(avg_fat_err, 1),
                    },
                },
                f,
                indent=2,
            )
        print(f"Results saved to {out_path}")
    else:
        print("\nNo results -- check that photos exist and ground_truth.json is valid.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Benchmark Gemini vision accuracy for meal macro estimation"
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Gemini model to benchmark (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/nutrition_benchmark",
        help="Benchmark dataset directory (default: data/nutrition_benchmark)",
    )
    args = parser.parse_args()
    run_benchmark(args.model, args.data_dir)
