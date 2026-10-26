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

    gemini_key = None
    for i in range(1, 5):
        gemini_key = os.getenv(f"GEMINI_API_KEY_{i}")
        if gemini_key:
            break
    if not gemini_key:
        gemini_key = os.getenv("GEMINI_API_KEY")

    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if not gemini_key and not openrouter_key:
        print("No GEMINI_API_KEY / GEMINI_API_KEY_1..4 or OPENROUTER_API_KEY found in environment.", file=sys.stderr)
        sys.exit(1)

    gemini_client = None
    if gemini_key:
        try:
            from google import genai
            gemini_client = genai.Client(api_key=gemini_key)
        except Exception as e:
            print(f"Warning: could not init Gemini client: {e}", file=sys.stderr)

    for model_name in models:
        print(f"\n=== {model_name} ===")
        # Route to OpenRouter if model has provider prefix or OpenRouter key is set
        if model_name.startswith("deepseek/") or model_name.startswith("openrouter/") or (openrouter_key and not gemini_client):
            if not openrouter_key:
                print("FAILED: OPENROUTER_API_KEY not set in environment.")
                continue
            try:
                import httpx
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/TurlaFSB/AeroHarness",
                    "X-Title": "AeroHarness",
                }
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Reply with exactly the word: OK"}],
                    "max_tokens": 10
                }
                with httpx.Client(timeout=30.0) as http_client:
                    resp = http_client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    print(f"SUCCESS (OpenRouter): model_used={model_name!r} response_text={text[:60]!r}")
            except Exception as e:
                print(f"FAILED (OpenRouter): {e!r}")
            continue

        # Route to Gemini client
        if not gemini_client:
            print("FAILED: No active Gemini client / API key.")
            continue
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents="Reply with exactly the word: OK",
            )
            text = (response.text or "").strip()
            print(f"SUCCESS (Gemini): model_used={model_name!r} response_text={text[:60]!r}")
        except Exception as e:
            print(f"FAILED (Gemini): {e!r}")


if __name__ == "__main__":
    main()
