import json
import re


def _fallback_kannada_explanation(prescription_json_string):
  """Return a detailed Kannada explanation when AI is unavailable."""
  try:
    data = json.loads(prescription_json_string)
  except Exception:
    return (
      "ಕ್ಷಮಿಸಿ, ಈಗ ವಿವರಣೆ ತಯಾರಿಸಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ವೈದ್ಯರು ಹೇಳಿದಂತೆ ಮಾತ್ರೆಗಳನ್ನು ತೆಗೆದುಕೊಳ್ಳಿ. "
      "ಯಾವುದೇ ಅಸಹಜ ಲಕ್ಷಣಗಳು ಕಂಡುಬಂದರೆ ತಕ್ಷಣ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ."
    )

  medicines = data.get("medicines", []) or []
  diagnosis = (data.get("diagnosis") or "").strip()
  notes = (data.get("doctor_notes") or "").strip()

  lines = []
  if diagnosis:
    lines.append(f"ನಿಮ್ಮ ಆರೋಗ್ಯ ಸಮಸ್ಯೆ: {diagnosis}.")
  else:
    lines.append("ವೈದ್ಯರು ಕೊಟ್ಟ ಔಷಧಿಗಳನ್ನು ಸಮಯಕ್ಕೆ ಸರಿಯಾಗಿ ತೆಗೆದುಕೊಳ್ಳಿ. ಸ್ವಂತವಾಗಿ ಮಾತ್ರೆಯ ಪ್ರಮಾಣವನ್ನು ಬದಲಾಯಿಸಬೇಡಿ.")

  if medicines:
    for med in medicines[:5]:
      name = (med.get("name") or "ಔಷಧಿ").strip()
      dose = (med.get("dose") or "").strip()
      timing = (med.get("timing") or "").strip()
      frequency = (med.get("frequency") or "").strip()
      duration = (med.get("duration") or "").strip()
      parts = [part for part in [name, dose, timing, frequency, duration] if part]
      lines.append("; ".join(parts) + ".")
      lines.append("ಔಷಧಿ ತೆಗೆದುಕೊಂಡ ನಂತರ ಬೇಸರ, ಅಲರ್ಜಿ, ಉಸಿರಾಟ ತೊಂದರೆ ಕಂಡರೆ ತಕ್ಷಣ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ.")

  if notes:
    lines.append(f"ವೈದ್ಯರ ಸೂಚನೆ: {notes}")

  lines.append("ಔಷಧಿ ಸಮಯ ಮಿಸ್ ಆದರೆ ಮುಂದಿನ ಡೋಸ್ ಅನ್ನು ಡಬಲ್ ಮಾಡಬೇಡಿ.")
  lines.append("2–3 ದಿನದಲ್ಲಿ ಸುಧಾರಣೆ ಕಾಣದಿದ್ದರೆ, ಅಥವಾ ಜ್ವರ/ವಾಂತಿ/ಅಲರ್ಜಿ ಹೆಚ್ಚಾದರೆ ತಕ್ಷಣ ವೈದ್ಯರನ್ನು ಭೇಟಿ ಮಾಡಿ.")
  return "\n".join(lines)


def _clean_value(value, default="ವೈದ್ಯರನ್ನು ಕೇಳಿ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ"):
  text = str(value or "").strip()
  return text if text else default


def _translate_medical_text_to_kannada(text):
  raw = str(text or "").strip()
  if not raw:
    return ""

  converted = raw

  replacements = [
    (r"\busg\s*abdomen\b", "ಹೊಟ್ಟೆಯ ಅಲ್ಟ್ರಾಸೌಂಡ್ ಪರೀಕ್ಷೆ"),
    (r"\busg\b", "ಅಲ್ಟ್ರಾಸೌಂಡ್ ಪರೀಕ್ಷೆ"),
    (r"\bdm\b", "ಮಧುಮೇಹ"),
    (r"\bhtn\b", "ರಕ್ತದೊತ್ತಡ"),
    (r"\bno\s+vomiting\b", "ವಾಂತಿ ಇಲ್ಲ"),
    (r"\bno\s+pain\s+abdomen\b", "ಹೊಟ್ಟೆ ನೋವು ಇಲ್ಲ"),
    (r"\bno\s+altered\s+bowel\s+movements\b", "ಮಲವಿಸರ್ಜನೆಯಲ್ಲಿ ಬದಲಾವಣೆ ಇಲ್ಲ"),
    (r"\bno\s+pain\b", "ನೋವು ಇಲ್ಲ"),
    (r"\bpain\s+abdomen\b", "ಹೊಟ್ಟೆ ನೋವು"),
    (r"\baltered\s+bowel\s+movements\b", "ಮಲವಿಸರ್ಜನೆಯಲ್ಲಿ ಬದಲಾವಣೆ"),
    (r"\bbowel\s+movements\b", "ಮಲವಿಸರ್ಜನೆ"),
    (r"\bvomiting\b", "ವಾಂತಿ"),
    (r"\bscan\s+report\b", "ಸ್ಕ್ಯಾನ್ ವರದಿ"),
    (r"\bscan\b", "ಸ್ಕ್ಯಾನ್"),
    (r"\babdomen\b", "ಹೊಟ್ಟೆ"),
  ]

  for pattern, replacement in replacements:
    converted = re.sub(pattern, replacement, converted, flags=re.IGNORECASE)

  converted = re.sub(r"\bx\s*(\d+)\s*days\b", r"ಕಳೆದ \1 ದಿನಗಳಿಂದ", converted, flags=re.IGNORECASE)
  converted = re.sub(r"\b(\d+)\s*days\b", r"\1 ದಿನ", converted, flags=re.IGNORECASE)
  converted = re.sub(r"\b(\d+)\s*weeks\b", r"\1 ವಾರ", converted, flags=re.IGNORECASE)
  converted = re.sub(r"\b(\d+)\s*week\b", r"\1 ವಾರ", converted, flags=re.IGNORECASE)

  # Clean up punctuation and repeated spaces after replacements.
  converted = re.sub(r"\s+", " ", converted).strip(" ,;")
  return converted


def _normalize_duration_text(duration):
  text = str(duration or "").strip().lower()
  if not text:
    return "ವೈದ್ಯರು ಸೂಚಿಸಿದ ಅವಧಿವರೆಗೆ"

  text = text.replace("days", "ದಿನ").replace("day", "ದಿನ")
  text = text.replace("weeks", "ವಾರ").replace("week", "ವಾರ")
  text = text.replace("months", "ತಿಂಗಳು").replace("month", "ತಿಂಗಳು")
  return text


def _normalize_time_text(timing):
  text = str(timing or "").strip().lower()
  if not text:
    return "ವೈದ್ಯರು ಸೂಚಿಸಿದ ಸಮಯಕ್ಕೆ"
  if (("morning" in text or "am" in text) and ("night" in text or "pm" in text)):
    return "ಬೆಳಿಗ್ಗೆ ಮತ್ತು ರಾತ್ರಿ"
  if "before" in text or "ಮೊದಲು" in text:
    return "ಊಟ ಮಾಡುವುದಕ್ಕೆ ಮುಂಚೆ"
  if "after" in text or "ನಂತರ" in text:
    return "ಊಟವಾದ ನಂತರ"
  if "with food" in text or "ಆಗೇ" in text or "ಒಟ್ಟಿಗೆ" in text:
    return "ಊಟದ ಜೊತೆಗೆ"
  if "morning" in text or "am" in text:
    return "ಬೆಳಿಗ್ಗೆ"
  if "night" in text or "pm" in text:
    return "ರಾತ್ರಿ"
  if "afternoon" in text:
    return "ಮಧ್ಯಾಹ್ನ"
  if "evening" in text:
    return "ಸಂಜೆ"
  return text


def _spoken_medicine_name(name):
  text = str(name or "ಔಷಧಿ").strip()
  return text


def _normalize_frequency_text(frequency):
  text = str(frequency or "").strip().lower()
  if not text:
    return "ದಿನಕ್ಕೆ ವೈದ್ಯರು ಸೂಚಿಸಿದಷ್ಟು ಬಾರಿ"
  if text in {"1", "1.0"}:
    return "ದಿನಕ್ಕೆ ಒಂದು ಬಾರಿ"
  if text in {"2", "2.0"}:
    return "ದಿನಕ್ಕೆ ಎರಡು ಬಾರಿ"
  if text in {"3", "3.0"}:
    return "ದಿನಕ್ಕೆ ಮೂರು ಬಾರಿ"
  if "once" in text or ("1" in text and "day" in text):
    return "ದಿನಕ್ಕೆ ಒಂದು ಬಾರಿ"
  if "twice" in text or ("2" in text and "day" in text):
    return "ದಿನಕ್ಕೆ ಎರಡು ಬಾರಿ"
  if "thrice" in text or ("3" in text and "day" in text):
    return "ದಿನಕ್ಕೆ ಮೂರು ಬಾರಿ"
  return text


def _normalize_dose_text(dose):
  text = str(dose or "").strip().lower()
  if not text:
    return "ವೈದ್ಯರು ಬರೆದ ಪ್ರಮಾಣದಲ್ಲಿ"

  text = text.replace("tablets", "ಮಾತ್ರೆಗಳು").replace("tablet", "ಮಾತ್ರೆ")
  text = text.replace("tab", "ಮಾತ್ರೆ").replace("capsule", "ಕ್ಯಾಪ್ಸುಲ್")
  text = text.replace("capsules", "ಕ್ಯಾಪ್ಸುಲ್")
  return text


def _infer_purpose_from_name(name):
  """Best-effort non-blocking purpose inference from common medicine names."""
  text = str(name or "").strip().lower()
  if not text:
    return ""

  if "vag" in text or "vaginal" in text or "pessary" in text:
    return "ಯೋನಿಯ ಭಾಗದ ಸೊಂಕು, ಉರಿ ಅಥವಾ ಅಸ್ವಸ್ಥತೆ ಕಡಿಮೆ ಮಾಡಲು"
  if "letogut" in text or "gut" in text or "lacto" in text:
    return "ಜೀರ್ಣಕ್ರಿಯೆ ಮತ್ತು ಹೊಟ್ಟೆಯ ಆರೋಗ್ಯ ಸುಧಾರಿಸಲು"
  if "dory" in text or "doxy" in text:
    return "ಸೊಂಕನ್ನು ನಿಯಂತ್ರಿಸಲು ವೈದ್ಯರು ನೀಡಿರುವ ಔಷಧಿ"
  if "fas" in text or "folic" in text or "iron" in text:
    return "ರಕ್ತಹೀನತೆ ತಡೆಯಲು ಮತ್ತು ದೇಹಕ್ಕೆ ಅಗತ್ಯ ಪೋಷಕಾಂಶ ನೀಡಲು"
  if "talmenax" in text or "telma" in text or "telmis" in text:
    return "ರಕ್ತದೊತ್ತಡವನ್ನು ನಿಯಂತ್ರಣದಲ್ಲಿ ಇಡಲು"
  if "saluf" in text or "glim" in text or "glic" in text or "met" in text:
    return "ರಕ್ತದಲ್ಲಿನ ಸಕ್ಕರೆ ಮಟ್ಟವನ್ನು ನಿಯಂತ್ರಿಸಲು"

  if "sporolac" in text or "sporlac" in text:
    return "ಹೊಟ್ಟೆಯ ಜೀರ್ಣಕ್ರಿಯೆ ಸುಧಾರಿಸಲು ಮತ್ತು ಹೊಟ್ಟೆಯ ತೊಂದರೆ ಕಡಿಮೆ ಮಾಡಲು"
  if "sompraz" in text or "esomepraz" in text or "omepraz" in text or "pantop" in text:
    return "ಹೊಟ್ಟೆಯಲ್ಲಿನ ಗ್ಯಾಸ್, ಉರಿ ಮತ್ತು ಆಸಿಡಿಟಿ ಕಡಿಮೆ ಮಾಡಲು"
  if "crocin" in text or "dolo" in text or "paracetamol" in text:
    return "ಜ್ವರ ಮತ್ತು ದೇಹದ ನೋವು ಕಡಿಮೆ ಮಾಡಲು"
  if "cetiriz" in text or "levocet" in text:
    return "ಅಲರ್ಜಿ, ತುರಿಕೆ ಮತ್ತು ಶೀತದ ಲಕ್ಷಣಗಳು ಕಡಿಮೆ ಮಾಡಲು"
  if "amox" in text or "azith" in text or "cef" in text:
    return "ಸೊಂಕಿಗಾಗಿ ವೈದ್ಯರು ನೀಡಿರುವ ಪ್ರತಿಜೈವಿಕ ಔಷಧಿ"

  return ""


def _infer_purpose_from_context(diagnosis, notes):
  context = f"{str(diagnosis or '').lower()} {str(notes or '').lower()}"
  if not context.strip():
    return "ಈ ಆರೋಗ್ಯ ಸಮಸ್ಯೆಯನ್ನು ನಿಯಂತ್ರಣದಲ್ಲಿ ಇಡಲು"

  if "dm" in context or "diabet" in context or "sugar" in context:
    return "ರಕ್ತದಲ್ಲಿನ ಸಕ್ಕರೆ ಮಟ್ಟವನ್ನು ನಿಯಂತ್ರಿಸಲು"
  if "htn" in context or "bp" in context or "hypert" in context:
    return "ರಕ್ತದೊತ್ತಡವನ್ನು ನಿಯಂತ್ರಣದಲ್ಲಿ ಇಡಲು"
  if "acid" in context or "gas" in context or "burn" in context or "reflux" in context:
    return "ಹೊಟ್ಟೆಯ ಉರಿ ಮತ್ತು ಆಸಿಡಿಟಿ ಕಡಿಮೆ ಮಾಡಲು"
  if "vomit" in context or "nausea" in context:
    return "ವಾಂತಿ ಮತ್ತು ಒದ್ದೆತನ ಕಡಿಮೆ ಮಾಡಲು"
  if "pain" in context:
    return "ನೋವು ಕಡಿಮೆ ಮಾಡಲು"
  if "infection" in context or "sank" in context or "fever" in context:
    return "ಸೊಂಕು ಮತ್ತು ಸಂಬಂಧಿತ ಲಕ್ಷಣಗಳನ್ನು ನಿಯಂತ್ರಿಸಲು"

  return "ಈ ಆರೋಗ್ಯ ಸಮಸ್ಯೆಯನ್ನು ನಿಯಂತ್ರಣದಲ್ಲಿ ಇಡಲು"


def _extract_purpose_text(medicine, diagnosis, notes):
  purpose = (
    medicine.get("purpose")
    or medicine.get("use")
    or medicine.get("indication")
    or medicine.get("reason")
    or ""
  )
  purpose = str(purpose).strip()
  if purpose:
    return _translate_medical_text_to_kannada(purpose)

  inferred = _infer_purpose_from_name(medicine.get("name"))
  if inferred:
    return inferred

  return _infer_purpose_from_context(diagnosis, notes)


def _build_spoken_kannada_explanation(prescription_json_string):
  data = json.loads(prescription_json_string)
  medicines = data.get("medicines", []) or []
  diagnosis = (data.get("diagnosis") or "").strip()
  notes = (data.get("doctor_notes") or "").strip()
  diagnosis_ka = _translate_medical_text_to_kannada(diagnosis)
  notes_ka = _translate_medical_text_to_kannada(notes)

  lines = [
    "ನಮಸ್ಕಾರ, ವೈದ್ಯರು ನಿಮಗೆ ಕೆಲವು ಮಾತ್ರೆಗಳನ್ನು ನೀಡಿದ್ದಾರೆ. ಅವುಗಳನ್ನು ಹೇಗೆ ತೆಗೆದುಕೊಳ್ಳಬೇಕು ಎಂದು ಈಗ ಹೇಳುತ್ತೇನೆ.",
  ]

  if diagnosis:
    lines.append(f"ನಿಮಗೆ {diagnosis_ka} ಸಮಸ್ಯೆಗೆ ಈ ಔಷಧಿಗಳನ್ನು ನೀಡಿದ್ದಾರೆ.")
  else:
    lines.append("ನಿಮಗೆ ಯಾವ ಸಮಸ್ಯೆಗೆ ಈ ಮಾತ್ರೆಗಳನ್ನು ನೀಡಿದ್ದಾರೆ ಎಂಬುದು ಇಲ್ಲಿ ಬರೆದಿಲ್ಲ. ಆದರೂ ವೈದ್ಯರು ಹೇಳಿದಂತೆ ಮಾತ್ರೆಗಳನ್ನು ಸರಿಯಾಗಿ ತೆಗೆದುಕೊಳ್ಳಬೇಕು.")

  if medicines:
    for index, med in enumerate(medicines[:6], start=1):
      name = _spoken_medicine_name(med.get("name"))
      purpose = _extract_purpose_text(med, diagnosis, notes)
      prefix = "ಮೊದಲ ಮಾತ್ರೆ" if index == 1 else "ಎರಡನೇ ಮಾತ್ರೆ" if index == 2 else f"{index}ನೇ ಮಾತ್ರೆ"
      lines.append(f"{prefix} '{name}'. ಇದು {purpose}.")

    for index, med in enumerate(medicines[:6], start=1):
      name = _spoken_medicine_name(med.get("name"))
      dose = _normalize_dose_text(med.get("dose"))
      frequency = _normalize_frequency_text(med.get("frequency"))
      timing = _normalize_time_text(med.get("timing"))
      duration = _normalize_duration_text(_clean_value(med.get("duration"), ""))
      lines.append(f"'{name}' ಮಾತ್ರೆ: {dose}, {frequency}, {timing} ತೆಗೆದುಕೊಳ್ಳಬೇಕು. ಇದನ್ನು {duration} ಮುಂದುವರಿಸಿ.")

      medicine_note = (med.get("note") or med.get("instructions") or "").strip()
      if medicine_note:
        lines.append(f"ಈ ಮಾತ್ರೆಗೆ ವಿಶೇಷ ಸೂಚನೆ: {medicine_note}")

  else:
    lines.append("ಈ ವೈದ್ಯರ ಚೀಟಿಯಲ್ಲಿ ಮಾತ್ರೆಗಳ ವಿವರ ಕಾಣುತ್ತಿಲ್ಲ. ದಯವಿಟ್ಟು ವೈದ್ಯರನ್ನು ಮತ್ತೆ ಕೇಳಿ ಖಚಿತಪಡಿಸಿಕೊಳ್ಳಿ.")

  if notes:
    lines.append(f"ವೈದ್ಯರ ಹೆಚ್ಚುವರಿ ಸೂಚನೆ: {notes_ka}")

  lines.append("ಔಷಧಿ ಸಮಯ ಮಿಸ್ ಆದರೆ ಮುಂದಿನ ಬಾರಿ ಎರಡು ಮಾತ್ರೆಗಳನ್ನು ಒಟ್ಟಿಗೆ ತೆಗೆದುಕೊಳ್ಳಬೇಡಿ.")
  lines.append("ಅಲರ್ಜಿ, ಹೆಚ್ಚು ವಾಂತಿ, ತಲೆಸುತ್ತು ಅಥವಾ ಉಸಿರಾಟದ ತೊಂದರೆ ಬಂದರೆ ತಕ್ಷಣ ಮಾತ್ರೆ ನಿಲ್ಲಿಸಿ ವೈದ್ಯರನ್ನು ಸಂಪರ್ಕಿಸಿ.")
  lines.append("ಈಗಾಗಲೇ ಬೇರೆ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳುತ್ತಿದ್ದರೆ, ಅದನ್ನು ವೈದ್ಯರಿಗೆ ತಿಳಿಸಿ ನಂತರ ಮಾತ್ರ ಮುಂದುವರಿಸಿ.")

  lines.append("ಕೊನೆ ಮಾತು: ಎಲ್ಲಾ ಮಾತ್ರೆಗಳನ್ನು ತಪ್ಪದೆ, ವೈದ್ಯರು ಹೇಳಿದ ಸಮಯಕ್ಕೆ ತೆಗೆದುಕೊಳ್ಳಿ.")
  lines.append("ಯಾವುದೇ ತೊಂದರೆ ಕಂಡರೆ ದಯವಿಟ್ಟು ತಕ್ಷಣ ವೈದ್ಯರನ್ನು ಭೇಟಿ ಮಾಡಿ.")
  return "\n".join(lines)


def explain_in_kannada(prescription_json_string):
    # Build the answer locally so it stays natural, consistent, and easy to understand.
    try:
      return _build_spoken_kannada_explanation(prescription_json_string)
    except Exception:
      return _fallback_kannada_explanation(prescription_json_string)


# TEST
if __name__ == "__main__":
    # Paste a sample JSON here to test
    sample = '''
    {
      "medicines": [
        {
          "name": "Crocin 500mg",
          "dose": "1 tablet",
          "frequency": "3 times a day",
          "timing": "after food",
          "duration": "5 days"
        }
      ],
      "diagnosis": "Fever",
      "doctor_notes": "Rest well"
    }
    '''
    result = explain_in_kannada(sample)
    print(result)
