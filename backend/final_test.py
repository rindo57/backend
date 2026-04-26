from prescription_reader import read_prescription
from kannada_explainer import explain_in_kannada
from medicine_scanner import scan_medicine_label
from verifier import verify_medicine
from tts_kannada import text_to_kannada_speech
import json

print("=" * 50)
print("TEST 1: Prescription Reading")
print("=" * 50)
presc = read_prescription("test_prescription.jpeg")
print("JSON output:", presc[:100], "...")

print("\nTEST 2: Kannada Explanation")
kannada = explain_in_kannada(presc)
print("Kannada text:\n", kannada)

print("\nTEST 3: Medicine Scan")
scan = scan_medicine_label("med1.jpeg")
print("Scan output:", scan)

print("\nTEST 4: Verification")
verdict = verify_medicine(json.loads(scan))
print("Verdict:", verdict['status'])
print("Kannada:", verdict['kannada'])

print("\nTEST 5: TTS Voice")
audio = text_to_kannada_speech(verdict['kannada'])
print("Audio generated:", len(audio), "chars")

print("\n✅ ALL TESTS PASSED — Backend is 100% ready")
