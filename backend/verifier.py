import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from config import FIREBASE_KEY_PATH

# Initialize Firebase (only if not already initialized)
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def check_expiry(expiry_string):
    """Returns True if medicine is expired"""
    try:
        if not expiry_string:
            return False
        parts = expiry_string.strip().split('/')
        month = int(parts[0])
        year = int(parts[1])
        expiry = datetime(year, month, 1)
        return datetime.now() > expiry
    except:
        return False

def verify_medicine(scan_result_dict):
    batch = scan_result_dict.get('batch_number', '').strip().upper()
    expiry = scan_result_dict.get('expiry_date', '')
    hologram = scan_result_dict.get('hologram_present', True)
    
    # Check 1 — Is batch in CDSCO fake/NSQ list?
    if batch:
        nsq_match = db.collection('nsq_medicines')\
            .where('batch_number', '==', batch).get()
        if len(list(nsq_match)) > 0:
            return {
                "status": "RED",
                "color": "🔴",
                "reason": "This batch is in CDSCO's fake/substandard drug list",
                "kannada": "ಈ ಔಷಧಿ ನಕಲಿ ಅಥವಾ ಕಳಪೆ ಗುಣಮಟ್ಟದ್ದು. ತಕ್ಷಣ ಬಳಸಬೇಡಿ."
            }
    
    # Check 2 — Is medicine expired?
    if check_expiry(expiry):
        return {
            "status": "RED",
            "color": "🔴",
            "reason": "Medicine is expired",
            "kannada": "ಈ ಔಷಧಿಯ ಅವಧಿ ಮುಗಿದಿದೆ. ಬಳಸಬೇಡಿ."
        }
    
    # Check 3 — Hologram missing?
    if not hologram:
        return {
            "status": "YELLOW",
            "color": "🟡",
            "reason": "Security hologram not found on packaging",
            "kannada": "ಔಷಧಿಯ ಮೇಲೆ ಭದ್ರತಾ ಚಿಹ್ನೆ ಕಾಣುತ್ತಿಲ್ಲ. ಜಾಗರೂಕರಾಗಿರಿ."
        }
    
    # All checks passed
    return {
        "status": "GREEN",
        "color": "🟢",
        "reason": "No issues found",
        "kannada": "ಈ ಔಷಧಿ ಸುರಕ್ಷಿತವಾಗಿದೆ. ನಿಸ್ಸಂಕೋಚವಾಗಿ ಬಳಸಬಹುದು."
    }
