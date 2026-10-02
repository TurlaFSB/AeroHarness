#!/usr/bin/env python3
"""
Standalone, zero-dependency-on-the-rest-of-the-pipeline diagnostic for Work Plan item 2's
"all 4 keys failed on their very first call" finding (Oct 2 2026). Does NOT import
anything from src/ or this directory's other modules -- the point is to confirm, with a
single real API call, whether a given model name actually works, before trusting any
guessed replacement string in config/settings.py (which this sandbox cannot verify itself
-- it cannot reach generativelanguage.googleapis.com -- see FAILURE_TAXONOMY.md).

Usage:
    export GEMINI_API_KEY_1="..."   # just one key is enough for this
    python3 diagnose_model.py gemini-1.5-pro gemini-2.0-flash gemini-3.1-pro-preview gemini-3.8-flash

Prints, per model name tried: OK (with the first ~60 chars of the response) or the exact
exception repr. Report the raw output of this script verbatim -- do not summarize "it
worked" or "it failed" in your own words; paste what it actually printed.
"""
import os
import sys


def main() -> None:
    models = sys.argv[1:]
    if not models:
        print("Usage: python3 diagnose_model.py <model_name> [<model_name> ...]", file=sys.stderr)
        sys.exit(1)

    api_key = None
    for i in range(1, 5):
        api_key = os.getenv(f"GEMINI_API_KEY_{i}")
        if api_key:
            break
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("No GEMINI_API_KEY_1..4 or GEMINI_API_KEY found in environment.", file=sys.stderr)
        sys.exit(1)

    from google import genai
    client = genai.Client(api_key=api_key)

    for model_name in models:
        print(f"\n=== {model_name} ===")
        try:
            response = client.models.generate_content(
                model=model_name,
                contents="Reply with exactly the word: OK",
            )
            text = (response.text or "").strip()
            print(f"SUCCESS: model_used={model_name!r} response_text={text[:60]!r}")
        except Exception as e:
            print(f"FAILED: {e!r}")


if __name__ == "__main__":
    main()
