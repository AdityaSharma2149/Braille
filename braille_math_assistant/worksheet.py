"""
Batch/worksheet mode: solve every question in a text file (one per line) in
one pass, producing per-question Braille + audio plus an aggregate report of
how much of the worksheet the local deterministic engine solved without ever
touching the network or the LLM.

Run:
    python worksheet.py questions.txt --language Hindi
"""
from __future__ import annotations

import argparse

from pipeline import run_worksheet


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("questions_file", help="Text file with one math question per line")
    parser.add_argument("--language", default="English")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--audio-dir", default="worksheet_audio")
    args = parser.parse_args()

    with open(args.questions_file, encoding="utf-8") as f:
        questions = [line.strip() for line in f if line.strip()]

    if not questions:
        print("No questions found in file.")
        return

    report = run_worksheet(
        questions,
        target_language=args.language,
        make_audio=not args.no_audio,
        audio_dir=args.audio_dir,
    )

    for i, out in enumerate(report["outputs"], 1):
        print(f"[{i}] ({out.engine}) {out.input_text}")
        print(f"    -> {out.solution_text.splitlines()[-1] if out.solution_text else ''}")
        if out.audio_path:
            print(f"    audio: {out.audio_path}")

    print("\n--- Worksheet summary ---")
    print(f"Total questions: {report['total_questions']}")
    print(f"Engine breakdown: {report['engine_counts']}")
    print(f"Solved with zero LLM-math risk: {report['solved_without_llm_math_risk_pct']}%")


if __name__ == "__main__":
    main()
