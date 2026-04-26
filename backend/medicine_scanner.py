import base64
import mimetypes
from pathlib import Path
import requests
import sys
import time
from config import OPENROUTER_API_KEY

VERBOSE = False  # Set to True for debug output

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_CANDIDATES = [
    "google/gemini-2.5-flash-image",
    "google/gemini-2.5-flash",
    "openai/gpt-4o-mini",
    "qwen/qwen2.5-vl-72b-instruct",
    "meta-llama/llama-3.2-11b-vision-instruct",
]
RETRY_DELAYS_SECONDS = [3, 6, 12, 20]


def _log(msg):
    if VERBOSE:
        print(f"[DEBUG] {msg}", file=sys.stderr)


def _resolve_image_path(image_path):
    candidate = Path(image_path)

    if candidate.is_file():
        return candidate

    backend_candidate = Path(__file__).resolve().parent / candidate
    if backend_candidate.is_file():
        return backend_candidate

    base = candidate.with_suffix("") if candidate.suffix else candidate
    for ext in (".jpg", ".jpeg", ".png"):
        ext_candidate = base.with_suffix(ext)
        if ext_candidate.is_file():
            return ext_candidate

        backend_ext_candidate = Path(__file__).resolve().parent / ext_candidate
        if backend_ext_candidate.is_file():
            return backend_ext_candidate

    return None


def _get_status_code(error):
    """Extract HTTP status code from a requests or API-style error."""
    status_code = getattr(error, "status_code", None)
    if status_code is None and hasattr(error, "response") and error.response is not None:
        status_code = error.response.status_code
    if status_code is None:
        status_code = getattr(error, "code", None)
    return status_code


def _is_quota_exhausted(error):
    """Check if the error indicates that the daily/free-tier quota is fully used up (limit: 0).
    Per-minute rate limits with remaining daily quota ARE retryable, so we don't flag those."""
    error_msg = str(error)
    # 'limit: 0' means the free tier quota is literally zero — retrying is pointless
    if "limit: 0," in error_msg or "limit: 0\n" in error_msg or error_msg.rstrip().endswith("limit: 0"):
        return True
    # Also check for PerDay quota violations specifically
    if "PerDay" in error_msg and "RESOURCE_EXHAUSTED" in error_msg:
        return True
    return False


def _is_transient_api_error(error):
    return _get_status_code(error) in (408, 429, 500, 502, 503, 504)


def _strip_markdown_fences(text):
    """Remove markdown code fences (```json ... ```) from API response."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (e.g. ```json or ```)
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _extract_openrouter_text(response_json):
    choices = response_json.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join([part for part in parts if part])

    return str(content)


def _call_openrouter(model_name, prompt, image_bytes, mime_type):
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model_name,
        "temperature": 0,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}",
                        },
                    },
                ],
            }
        ],
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ShankarKarajanagi18/AushadhiSaathi",
        "X-Title": "AushadhiSaathi",
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    response_json = response.json()
    return _extract_openrouter_text(response_json)


def _generate_with_resilience(prompt, image_bytes, mime_type):
    last_error = None
    error_details = []

    for model_name in MODEL_CANDIDATES:
        _log(f"Trying model: {model_name}")
        for attempt, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
            try:
                response_text = _call_openrouter(model_name, prompt, image_bytes, mime_type)
                return _strip_markdown_fences(response_text)

            except requests.HTTPError as error:
                last_error = error
                status_code = _get_status_code(error)
                detail = f"Model={model_name}, attempt={attempt}, status={status_code}, error={error}"
                error_details.append(detail)
                _log(detail)

                # Model not found — skip to next model
                if status_code == 404:
                    _log(f"Model {model_name} not found (404), skipping.")
                    break

                # Daily quota fully exhausted — no point retrying this model
                if status_code == 429 and _is_quota_exhausted(error):
                    _log(f"Daily quota exhausted for {model_name}, skipping to next model.")
                    break

                # Non-retryable error — fail immediately with details
                if not _is_transient_api_error(error):
                    raise RuntimeError(
                        f"OpenRouter request failed (status {status_code}): {error}"
                    ) from error

                # Retryable error — wait and retry
                if attempt < len(RETRY_DELAYS_SECONDS):
                    _log(f"Retrying in {delay}s...")
                    time.sleep(delay)
                    continue

                # Exhausted retries for this model, try next
                _log(f"Exhausted retries for {model_name}")
                break

            except (requests.RequestException, ValueError) as error:
                # Catch unexpected errors (network issues, timeouts, etc.)
                last_error = error
                detail = f"Model={model_name}, attempt={attempt}, unexpected_error={type(error).__name__}: {error}"
                error_details.append(detail)
                _log(detail)

                if attempt < len(RETRY_DELAYS_SECONDS):
                    _log(f"Retrying in {delay}s after unexpected error...")
                    time.sleep(delay)
                    continue
                break

    # Build a detailed error message
    details_str = "\n  ".join(error_details) if error_details else "No error details captured."
    error_msg = (
        f"OpenRouter API failed after trying all models and retries.\n"
        f"Error details:\n  {details_str}\n"
        f"Possible fixes:\n"
        f"  1. Check if your OpenRouter API key is valid (config.py)\n"
        f"  2. Check your OpenRouter credits/limits at https://openrouter.ai/settings/credits\n"
        f"  3. Check model availability at https://openrouter.ai/models\n"
        f"  4. Wait a minute and try again (rate limiting)\n"
        f"  5. Try generating a new API key at https://openrouter.ai/keys"
    )

    if last_error is not None:
        raise RuntimeError(error_msg) from last_error
    raise RuntimeError("Unable to scan medicine label — no models were attempted.")


def scan_medicine_label(image_path):
    resolved_path = _resolve_image_path(image_path)
    if resolved_path is None:
        raise FileNotFoundError(
            f"Medicine image not found: '{image_path}'. "
            "Try a valid file like 'med10.jpeg'."
        )

    mime_type, _ = mimetypes.guess_type(str(resolved_path))
    if not mime_type:
        mime_type = "image/jpeg"

    image_bytes = resolved_path.read_bytes()
    
    prompt = """
    Look at this medicine packaging, strip, or box image carefully.
    Find and extract the following information.
    
    Return ONLY this JSON, nothing else, no markdown:
    {
      "drug_name": "name of the medicine",
      "batch_number": "batch or lot number — usually starts with letters like BN, Batch No, B.No",
      "expiry_date": "expiry date in MM/YYYY format",
      "manufacturer": "name of manufacturing company",
      "hologram_present": true or false
    }
    
    For batch_number: look for text near words like "Batch", "B.No", "Lot", "Mfg Batch".
    For expiry_date: look for "Exp", "Use before", "Expiry".
    For hologram: look for any shiny sticker or security mark on the packaging.
    If you cannot find a field, use empty string "".
    Return only valid JSON.
    """
    
    return _generate_with_resilience(prompt, image_bytes, mime_type)

# TEST
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python medicine_scanner.py med1.jpg")
    else:
        # Enable verbose mode when running directly
        VERBOSE = True
        try:
            result = scan_medicine_label(sys.argv[1])
            print(result)
        except FileNotFoundError as error:
            print(f"ERROR: {error}")
        except RuntimeError as error:
            print(f"ERROR: {error}")
        except Exception as error:
            print(f"Unexpected scanner error ({type(error).__name__}): {error}")
