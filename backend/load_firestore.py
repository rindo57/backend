import firebase_admin
from firebase_admin import credentials, firestore
import csv
import re
from config import FIREBASE_KEY_PATH

# Initialize Firebase
cred = credentials.Certificate(FIREBASE_KEY_PATH)
firebase_admin.initialize_app(cred)
db = firestore.client()

def load_nsq_data(csv_file):
    count = 0
    with open(csv_file, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_drug_name = str(row.get('drug_name', '')).strip()
            raw_batch_number = str(row.get('batch_number', '')).strip()
            raw_manufacturer = str(row.get('manufacturer', '')).strip()
            raw_reason = str(row.get('reason', '')).strip()

            # Repair rows where serial number was written into drug_name
            # and all meaningful fields shifted right by one column.
            if re.fullmatch(r"\d+\.?", raw_drug_name) and raw_batch_number:
                raw_drug_name, raw_batch_number, raw_manufacturer, raw_reason = (
                    raw_batch_number,
                    raw_manufacturer,
                    raw_reason,
                    "",
                )

            # Clean and upload each row
            doc_data = {
                'drug_name': raw_drug_name.upper(),
                'batch_number': raw_batch_number.upper(),
                'manufacturer': raw_manufacturer.upper(),
                'reason': raw_reason
            }
            if doc_data['batch_number']:  # only upload if batch number exists
                db.collection('nsq_medicines').add(doc_data)
                count += 1
                if count % 50 == 0:
                    print(f"Uploaded {count} records...")
    
    print(f"Done! Total {count} records uploaded to Firestore.")

load_nsq_data("cdsco_clean.csv")
