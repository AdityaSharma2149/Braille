"""
Menu-driven CLI matching Section 4.1 ("Ingestion Branching"):
    1 for Type Question, 2 for voice upload, 3 for image upload

Run:
    export GROQ_API_KEY=your_key_here   # only needed for translation/fallback paths
    python cli.py
"""
from __future__ import annotations

import sys

from pipeline import (
    ocr_accuracy,
    ocr_confidence,
    ocr_image,
    run_pipeline,
    transcribe_voice,
)

LANGUAGES = ["English", "Hindi", "Tamil", "Telugu", "Kannada", "Marathi", "Bengali", "Gujarati"]
WHISPER_LANG_CODE = {
    "English": "en", "Hindi": "hi", "Tamil": "ta", "Telugu": "te",
    "Kannada": "kn", "Marathi": "mr", "Bengali": "bn", "Gujarati": "gu",
}

ENGINE_LABELS = {
    "local-deterministic": "Local deterministic solver (verified, offline)",
    "local+llm-translation": "Local solver + AI translation (math verified, phrasing by AI)",
    "llm-fallback (unverified)": "AI solver (UNVERIFIED -- local engine could not parse this problem)",
    "local-offline": "Local solver only (translation unavailable offline)",
}


def choose_language(prompt: str) -> str:
    print(prompt)
    for i, lang in enumerate(LANGUAGES, 1):
        print(f"  {i}. {lang}")
    choice = input("Choose a number: ").strip()
    try:
        return LANGUAGES[int(choice) - 1]
    except (ValueError, IndexError):
        print("Invalid choice, defaulting to English.")
        return "English"


def get_question_text() -> str | None:
    choice = input("1 for Type Question, 2 for voice upload, 3 for image upload: ").strip()

    if choice == "1":
        return input("Type your math question: ").strip()

    if choice == "2":
        wav_path = input("Path to .wav voice note: ").strip()
        source_lang = choose_language("What language is the voice note in?")
        try:
            text = transcribe_voice(wav_path, language=WHISPER_LANG_CODE[source_lang])
        except Exception as exc:
            print(f"Could not transcribe audio (offline faster-whisper): {exc}")
            return None
        print(f"Transcribed: {text}")
        return text

    if choice == "3":
        image_path = input("Path to textbook image (.png/.jpg): ").strip()
        try:
            extracted = ocr_image(image_path)
        except Exception as exc:
            print(f"Could not read image: {exc}")
            return None
        if not ocr_confidence(extracted):
            print("No legible text was detected in this image. Try better lighting.")
            return None
        print(f"OCR extracted: {extracted.strip()}")
        reference = input(
            "(Optional) type the exact reference text to score OCR accuracy, or press Enter to skip: "
        ).strip()
        if reference:
            stats = ocr_accuracy(reference, extracted)
            print(f"OCR accuracy: {stats['accuracy_pct']}% "
                  f"({stats['characters_survived']}/{stats['reference_char_count']} chars survived)")
        return extracted.strip()

    print("Invalid option.")
    return None


def main() -> None:
    print("=== Cross-Lingual Spatial Math -> Braille + Audio Assistant ===")
    question = get_question_text()
    if not question:
        print("No question captured. Exiting.")
        sys.exit(1)

    target_language = choose_language("Translate the solution into which language?")

    print("\nDecoding spatial structure and solving...\n")
    result = run_pipeline(question, target_language=target_language, make_audio=True, audio_out="solution.mp3")

    print(f"Engine used: {ENGINE_LABELS.get(result.engine, result.engine)}")
    if result.notice:
        print(f"Notice: {result.notice}")
    print(f"\nSolution ({target_language}):\n{result.solution_text}\n")
    print(f"Braille preview:\n{result.braille_text}\n")
    print(f"Braille fidelity: {result.braille_fidelity['accuracy_pct']}% "
          f"({result.braille_fidelity['mapped_symbol_count']}/{result.braille_fidelity['input_symbol_count']} symbols)")
    print(f"Audio saved to: {result.audio_path}")


if __name__ == "__main__":
    main()
