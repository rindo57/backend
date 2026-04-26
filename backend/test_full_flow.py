from prescription_reader import read_prescription
from kannada_explainer import explain_in_kannada

# Full prescription flow test
image_path = "test_prescription.jpg"

print("Reading prescription...")
prescription_json = read_prescription(image_path)
print("Prescription JSON:")
print(prescription_json)

print("\nGenerating Kannada explanation...")
kannada_text = explain_in_kannada(prescription_json)
print("Kannada Explanation:")
print(kannada_text)
