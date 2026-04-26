import base64
import json
import mimetypes
from pathlib import Path
import requests
import sys
import time
from config import OPENROUTER_API_KEY

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_CANDIDATES = [
  "baidu/qianfan-ocr-fast:free",
  "nvidia/nemotron-nano-12b-v2-vl:free",
  "qwen/qwen2.5-vl-72b-instruct:free",
  "qwen/qwen2.5-vl-72b-instruct",
  "google/gemini-2.5-flash-image",
  "google/gemini-2.5-flash",
  "google/gemini-2.5-pro",
  "openai/gpt-4o-mini",
  "meta-llama/llama-3.2-11b-vision-instruct",
]
RETRY_DELAYS_SECONDS = [2, 4, 8]


def _resolve_image_path(image_path):
  """Resolve image path and try common extension alternatives when missing."""
  candidate = Path(image_path)

  if candidate.is_file():
    return candidate

  # Try relative to this file (backend folder) when called from elsewhere.
  backend_candidate = Path(__file__).resolve().parent / candidate
  if backend_candidate.is_file():
    return backend_candidate

  # Try common extension alternatives: .jpg/.jpeg/.png in the same folder.
  base = candidate.with_suffix("") if candidate.suffix else candidate
  for ext in (".jpg", ".jpeg", ".png"):
    ext_candidate = base.with_suffix(ext)
    if ext_candidate.is_file():
      return ext_candidate

    backend_ext_candidate = Path(__file__).resolve().parent / ext_candidate
    if backend_ext_candidate.is_file():
      return backend_ext_candidate

  return None


def _is_quota_exhausted(error):
  """Check if free-tier quota is fully used up (limit: 0). Not retryable."""
  error_msg = str(error)
  if "limit: 0," in error_msg or "limit: 0\n" in error_msg or error_msg.rstrip().endswith("limit: 0"):
    return True
  if "PerDay" in error_msg and "RESOURCE_EXHAUSTED" in error_msg:
    return True
  return False


def _is_transient_api_error(error):
  status_code = getattr(error, "status_code", None)
  if status_code is None and hasattr(error, "response") and error.response is not None:
    status_code = error.response.status_code
  if status_code is None:
    status_code = getattr(error, "code", None)

  # Handle temporary throttling and overloaded backend responses.
  return status_code in (408, 429, 500, 502, 503, 504)


def _fallback_prescription_json():
  """Fallback payload when model calls fail due to quota/availability."""
  return (
    '{"medicines": [], "diagnosis": "", '
    '"doctor_notes": "Prescription extraction failed. Please try again."}'
  )


def _strip_markdown_fences(text):
  """Remove markdown code fences (```json ... ```) from API response."""
  text = text.strip()
  if text.startswith("```"):
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
  return _extract_openrouter_text(response.json())


def _generate_with_resilience(prompt, image_bytes, mime_type):
  last_error = None

  for model_name in MODEL_CANDIDATES:
    for attempt, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
      try:
        response_text = _call_openrouter(model_name, prompt, image_bytes, mime_type)
        return _strip_markdown_fences(response_text)
      except requests.HTTPError as error:
        last_error = error
        status_code = getattr(error, "status_code", None)
        if status_code is None and hasattr(error, "response") and error.response is not None:
          status_code = error.response.status_code
        if status_code is None:
          status_code = getattr(error, "code", None)

        # Model is unavailable for this API version; try next candidate.
        if status_code == 404:
          break

        # Paid model or billing issue; continue with the next candidate.
        if status_code == 402:
          break

        # Daily quota fully exhausted — skip to next model immediately
        if status_code == 429 and _is_quota_exhausted(error):
          break

        if not _is_transient_api_error(error):
          raise

        if attempt < len(RETRY_DELAYS_SECONDS):
          time.sleep(delay)
          continue

        # Retries exhausted for this model, move to next model candidate.
        break
      except (requests.RequestException, ValueError) as error:
        last_error = error
        if attempt < len(RETRY_DELAYS_SECONDS):
          time.sleep(delay)
          continue
        break

  if last_error is not None:
    raise RuntimeError(
      "OpenRouter API is temporarily unavailable after retries and model fallbacks. "
      "Please try again in a minute."
    ) from last_error

  raise RuntimeError("Unable to generate prescription summary.")


def _refine_with_dose_verification(initial_json_text, image_bytes, mime_type):
  """Second pass focused only on correcting medicine dose/frequency from the image."""
  refine_prompt = f"""
You are validating medicine dose extraction from a prescription image.
Given the initial JSON below, re-check ONLY dose/frequency/timing/duration fields from the image.

Rules:
- Preserve drug names exactly unless clearly wrong.
- For dose: copy visible quantity exactly (examples: "2 tablets", "1/2 tablet", "5 ml").
- Never default to "1" when not visible. If uncertain, use empty string "".
- Return valid JSON only in this schema:
{{
  "medicines": [
    {{"name": "", "dose": "", "frequency": "", "timing": "", "duration": ""}}
  ],
  "diagnosis": "",
  "doctor_notes": ""
}}

Initial JSON:
{initial_json_text}
"""
  return _generate_with_resilience(refine_prompt, image_bytes, mime_type)


def _normalize_prescription_json(raw_json):
  """Normalize common medicine dose variants and remove risky defaults."""
  data = json.loads(raw_json)
  medicines = data.get("medicines")
  if isinstance(medicines, dict):
    medicines = [medicines]
  elif not isinstance(medicines, list):
    medicines = []

  normalized_medicines = []
  for med in medicines:
    if isinstance(med, str):
      normalized_medicines.append(
        {
          "name": med.strip(),
          "dose": "",
          "frequency": "",
          "timing": "",
          "duration": "",
        }
      )
    elif isinstance(med, dict):
      normalized_medicines.append(med)

  data["medicines"] = normalized_medicines

  for med in normalized_medicines:
    if not isinstance(med, dict):
      continue
    dose = str(med.get("dose", "")).strip()
    # Do not keep bare numeric defaults like "1" that often come from weak OCR guesses.
    if dose in {"1", "1.", "1 tab", "1 tabs"}:
      med["dose"] = ""
    elif dose.lower() in {"2", "2.", "2 tab", "2 tabs", "2 tablet"}:
      med["dose"] = "2 tablets"

  return json.dumps(data, ensure_ascii=False)

def read_prescription(image_path):
  resolved_path = _resolve_image_path(image_path)
  if resolved_path is None:
    raise FileNotFoundError(
      f"Prescription image not found: '{image_path}'. "
      "Try an existing file like 'test_prescription.jpeg'."
    )

  mime_type, _ = mimetypes.guess_type(str(resolved_path))
  if not mime_type:
    mime_type = "image/jpeg"

  image_bytes = resolved_path.read_bytes()
  first_pass = None

  prompt = """
    You are a helpful medical assistant for patients in India.
    Read this prescription image carefully.
    Extract and return JSON with exactly these fields:
    {
      "medicines": [
        {
          "name": "medicine name",
          "dose": "dose amount",
          "frequency": "how many times per day",
          "timing": "before food / after food / with food",
          "duration": "how many days"
        }
      ],
      "diagnosis": "what condition if mentioned",
      "doctor_notes": "any special instructions"
    }
    Important medicine extraction rules:
    - Extract every distinct medicine that is visible in the prescription.
    - Do not merge separate medicines into one object.
    - If multiple medicine lines are present, return one object per medicine.
    - Preserve the medicine name exactly as visible, even if capitalization or spacing differs.
    - Do not invent medicines that are not visible.
    If handwritten, do your best to read it.
    Critical dose extraction rules:
    - Preserve exact visible quantity in dose (for example: "2 tablets", "1 tablet", "1/2 tablet", "5 ml").
    - Do not guess dose as "1" by default.
    - If dose is not visible, set dose to "".
    - Prefer explicit tablet count from handwriting over assumptions.
    Return only valid JSON, nothing else. No explanation, no markdown.
    """

  try:
    first_pass = _generate_with_resilience(prompt, image_bytes, mime_type)
    verified_pass = _refine_with_dose_verification(first_pass, image_bytes, mime_type)
    return _normalize_prescription_json(verified_pass)
  except RuntimeError:
    if first_pass:
      try:
        return _normalize_prescription_json(first_pass)
      except Exception:
        pass
    raise RuntimeError(
      "Prescription extraction failed. The image could not be read reliably, so no hardcoded result was used."
    )
  except Exception:
    try:
      return _normalize_prescription_json(first_pass)
    except Exception:
      raise RuntimeError(
        "Prescription extraction failed. The image could not be read reliably, so no hardcoded result was used."
      )

# TEST — run this file directly to test
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prescription_reader.py yourprescription.jpg")
    else:
      try:
        result = read_prescription(sys.argv[1])
        print(result)
      except FileNotFoundError as error:
        print(error)
      except RuntimeError as error:
        print(error)
