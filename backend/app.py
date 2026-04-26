from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

from config import FIREBASE_KEY_PATH
from kannada_explainer import explain_in_kannada
from medicine_scanner import scan_medicine_label
from prescription_reader import read_prescription
from tts_kannada import text_to_kannada_speech
from verifier import verify_medicine

app = Flask(__name__)
CORS(app)


if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()


def _server_timestamp():
    return firestore.SERVER_TIMESTAMP


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _normalize_nhm_id(nhm_id):
    return str(nhm_id or "").strip().upper()


def _normalize_phone(phone):
    return re.sub(r"\D", "", str(phone or ""))


def _to_json_safe(value):
    if isinstance(value, dict):
        return {k: _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return value


def _save_audio_base64(audio_base64, prefix):
    audio_dir = Path(__file__).resolve().parent / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    audio_path = audio_dir / f"{prefix}_{timestamp}.mp3"
    audio_path.write_bytes(base64.b64decode(audio_base64))
    return str(audio_path)


def _save_temp_image(image_base64):
    image_bytes = base64.b64decode(image_base64)
    temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    try:
        temp_file.write(image_bytes)
        temp_file.flush()
        return temp_file.name
    finally:
        temp_file.close()


def _process_prescription_image(image_base64):
    temp_path = _save_temp_image(image_base64)
    try:
        prescription_json = read_prescription(temp_path)
        prescription = json.loads(prescription_json)
        kannada_text = explain_in_kannada(prescription_json)

        explanation_audio = None
        explanation_audio_error = None
        try:
            explanation_audio = text_to_kannada_speech(kannada_text)
        except Exception as audio_error:
            explanation_audio_error = str(audio_error)

        explanation_audio_path = None
        explanation_audio_save_error = None
        if explanation_audio:
            try:
                explanation_audio_path = _save_audio_base64(explanation_audio, "kannada_explanation")
            except Exception as save_error:
                explanation_audio_save_error = str(save_error)

        return {
            "prescription": prescription,
            "kannada_explanation": kannada_text,
            "kannada_explanation_audio": explanation_audio,
            "kannada_explanation_audio_path": explanation_audio_path,
            "kannada_explanation_audio_error": explanation_audio_error,
            "kannada_explanation_audio_save_error": explanation_audio_save_error,
        }
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _process_medicine_verification(image_base64):
    temp_path = _save_temp_image(image_base64)
    try:
        scan_json_string = scan_medicine_label(temp_path)
        scan_result = json.loads(scan_json_string)
        verdict = verify_medicine(scan_result)
        return {
            "scan_result": scan_result,
            "verdict": verdict,
        }
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _distance_km(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    earth_radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(earth_radius_km * c, 2)


def _rule_based_health_reply(question):
    text = str(question or "").strip().lower()
    if not text:
        return "Please ask your health query in English or Kannada."
    if "metformin" in text:
        return "Metformin is usually taken with or after food to reduce stomach discomfort. Follow the exact dose advised by your doctor."
    if "paracetamol" in text:
        return "Paracetamol is commonly taken for fever or pain. Keep dose intervals and avoid exceeding prescribed daily limits."
    if "side effect" in text or "reaction" in text:
        return "If you notice severe side effects like breathing trouble, swelling, or persistent vomiting, seek immediate medical care."
    if "pregnan" in text:
        return "During pregnancy, avoid self-medication. Please consult a qualified doctor or your ASHA worker before taking medicines."
    return "I can help with dose timing, side effects, and basic medicine guidance. For emergencies, contact your nearest health worker immediately."


def _sorted_firestore_docs(docs, limit=10):
    rows = []
    for doc in docs:
        data = doc.to_dict() or {}
        rows.append({"id": doc.id, **_to_json_safe(data)})

    rows.sort(key=lambda item: item.get("created_at") or item.get("timestamp") or "", reverse=True)
    return rows[:limit]


def _list_endpoints():
    endpoints = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = sorted([m for m in rule.methods if m not in {"HEAD", "OPTIONS"}])
        if not methods:
            continue
        if len(methods) > 1:
            endpoints[rule.endpoint] = f"{'/'.join(methods)} {rule.rule}"
        else:
            endpoints[rule.endpoint] = f"{methods[0]} {rule.rule}"
    return dict(sorted(endpoints.items()))


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "AushadhiSaathi backend",
        "status": "running",
        "time": _now_iso(),
        "endpoints": _list_endpoints(),
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "AushadhiSaathi backend is running!"})


@app.route("/read-prescription", methods=["POST"])
def read_prescription_api():
    try:
        data = request.get_json(silent=True) or {}
        image_base64 = data.get("image")
        if not image_base64:
            return jsonify({"success": False, "error": "Missing image field"}), 400

        result = _process_prescription_image(image_base64)
        return jsonify({"success": True, **result})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/verify-medicine", methods=["POST"])
def verify_medicine_api():
    try:
        data = request.get_json(silent=True) or {}
        image_base64 = data.get("image")
        if not image_base64:
            return jsonify({"success": False, "error": "Missing image field"}), 400

        result = _process_medicine_verification(image_base64)
        return jsonify({"success": True, **result})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/speak", methods=["POST"])
def speak():
    try:
        text = (request.get_json(silent=True) or {}).get("text")
        if not text:
            return jsonify({"success": False, "error": "Missing text"}), 400

        audio_base64 = text_to_kannada_speech(text)
        audio_path = None
        audio_save_error = None
        try:
            audio_path = _save_audio_base64(audio_base64, "tts_output")
        except Exception as save_error:
            audio_save_error = str(save_error)

        return jsonify({
            "success": True,
            "audio": audio_base64,
            "audio_path": audio_path,
            "audio_save_error": audio_save_error,
        })
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/report-medicine", methods=["POST"])
def report_medicine():
    try:
        data = request.get_json(silent=True) or {}
        db.collection("reports").add({
            "batch_number": str(data.get("batch_number", "")).strip(),
            "drug_name": str(data.get("drug_name", "")).strip(),
            "latitude": float(data.get("latitude") or 0),
            "longitude": float(data.get("longitude") or 0),
            "timestamp": _server_timestamp(),
        })
        return jsonify({"success": True, "message": "Report submitted"})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/get-reports", methods=["GET"])
def get_reports():
    try:
        docs = db.collection("reports").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(50).get()
        reports = [{"id": doc.id, **_to_json_safe(doc.to_dict())} for doc in docs]
        return jsonify({"success": True, "reports": reports})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/login", methods=["POST"])
def asha_login():
    try:
        data = request.get_json(silent=True) or {}
        full_name = str(data.get("full_name", "")).strip()
        nhm_id = _normalize_nhm_id(data.get("nhm_id"))
        phone = _normalize_phone(data.get("phone"))
        village = str(data.get("village", "")).strip()
        language = str(data.get("language", "EN")).strip().upper() or "EN"

        if not full_name or not nhm_id or len(phone) != 10:
            return jsonify({
                "success": False,
                "error": "full_name, nhm_id and a valid 10-digit phone are required",
            }), 400

        worker_ref = db.collection("asha_workers").document(nhm_id)
        existing = worker_ref.get()
        now = _server_timestamp()

        payload = {
            "full_name": full_name,
            "nhm_id": nhm_id,
            "phone": phone,
            "village": village,
            "language": language,
            "status": "active",
            "updated_at": now,
            "last_login_at": now,
        }
        if not existing.exists:
            payload["created_at"] = now

        worker_ref.set(payload, merge=True)

        db.collection("asha_sessions").add({
            "nhm_id": nhm_id,
            "phone": phone,
            "full_name": full_name,
            "login_at": now,
            "source": "web_html",
        })

        worker_doc = worker_ref.get().to_dict() or payload
        return jsonify({"success": True, "worker": _to_json_safe(worker_doc)})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/worker/<nhm_id>", methods=["GET"])
def get_asha_worker(nhm_id):
    try:
        worker_id = _normalize_nhm_id(nhm_id)
        doc = db.collection("asha_workers").document(worker_id).get()
        if not doc.exists:
            return jsonify({"success": False, "error": "Worker not found"}), 404
        return jsonify({"success": True, "worker": {"id": doc.id, **_to_json_safe(doc.to_dict())}})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/patients/upsert", methods=["POST"])
def upsert_patient():
    try:
        data = request.get_json(silent=True) or {}
        phone = _normalize_phone(data.get("phone"))
        nhm_id = _normalize_nhm_id(data.get("nhm_id"))
        if len(phone) != 10 or not nhm_id:
            return jsonify({"success": False, "error": "Valid phone and nhm_id are required"}), 400

        patient_ref = db.collection("patients").document(phone)
        patient_ref.set({
            "phone": phone,
            "name": str(data.get("name", "")).strip(),
            "gender": str(data.get("gender", "")).strip(),
            "age": data.get("age"),
            "area": str(data.get("area", "")).strip(),
            "notes": str(data.get("notes", "")).strip(),
            "last_updated_by": nhm_id,
            "last_updated_at": _server_timestamp(),
        }, merge=True)

        patient = patient_ref.get().to_dict() or {}
        return jsonify({"success": True, "patient": _to_json_safe(patient)})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/patients", methods=["GET"])
def get_patients():
    try:
        phone = _normalize_phone(request.args.get("phone"))
        limit = int(request.args.get("limit", 20))

        if phone:
            doc = db.collection("patients").document(phone).get()
            if not doc.exists:
                return jsonify({"success": True, "patients": []})
            return jsonify({"success": True, "patients": [{"id": doc.id, **_to_json_safe(doc.to_dict())}]})

        docs = db.collection("patients").order_by("last_updated_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
        patients = [{"id": doc.id, **_to_json_safe(doc.to_dict())} for doc in docs]
        return jsonify({"success": True, "patients": patients})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/dashboard", methods=["GET"])
def asha_dashboard():
    try:
        nhm_id = _normalize_nhm_id(request.args.get("nhm_id"))
        if not nhm_id:
            return jsonify({"success": False, "error": "nhm_id is required"}), 400

        worker_doc = db.collection("asha_workers").document(nhm_id).get()
        if not worker_doc.exists:
            return jsonify({"success": False, "error": "Worker not found"}), 404

        recent_scans_raw = db.collection("asha_prescription_scans").where("nhm_id", "==", nhm_id).limit(50).stream()
        recent_verifications_raw = db.collection("asha_medicine_verifications").where("nhm_id", "==", nhm_id).limit(50).stream()
        recent_messages_raw = db.collection("asha_messages").where("nhm_id", "==", nhm_id).limit(50).stream()

        dashboard = {
            "worker": {"id": worker_doc.id, **_to_json_safe(worker_doc.to_dict())},
            "recent_prescription_scans": _sorted_firestore_docs(recent_scans_raw, limit=5),
            "recent_medicine_verifications": _sorted_firestore_docs(recent_verifications_raw, limit=5),
            "recent_messages": _sorted_firestore_docs(recent_messages_raw, limit=5),
        }
        return jsonify({"success": True, "dashboard": dashboard})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/workflows/prescription-scan", methods=["POST"])
def asha_prescription_scan():
    try:
        data = request.get_json(silent=True) or {}
        nhm_id = _normalize_nhm_id(data.get("nhm_id"))
        patient_phone = _normalize_phone(data.get("patient_phone"))
        image_base64 = data.get("image")

        if not nhm_id or len(patient_phone) != 10 or not image_base64:
            return jsonify({"success": False, "error": "nhm_id, patient_phone and image are required"}), 400

        result = _process_prescription_image(image_base64)

        db.collection("asha_prescription_scans").add({
            "nhm_id": nhm_id,
            "patient_phone": patient_phone,
            "prescription": result["prescription"],
            "kannada_explanation": result["kannada_explanation"],
            "kannada_explanation_audio_path": result["kannada_explanation_audio_path"],
            "created_at": _server_timestamp(),
        })

        return jsonify({"success": True, **result})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/workflows/medicine-verify", methods=["POST"])
def asha_medicine_verify():
    try:
        data = request.get_json(silent=True) or {}
        nhm_id = _normalize_nhm_id(data.get("nhm_id"))
        patient_phone = _normalize_phone(data.get("patient_phone"))
        image_base64 = data.get("image")

        if not nhm_id or len(patient_phone) != 10 or not image_base64:
            return jsonify({"success": False, "error": "nhm_id, patient_phone and image are required"}), 400

        result = _process_medicine_verification(image_base64)
        db.collection("asha_medicine_verifications").add({
            "nhm_id": nhm_id,
            "patient_phone": patient_phone,
            "scan_result": result["scan_result"],
            "verdict": result["verdict"],
            "created_at": _server_timestamp(),
        })

        return jsonify({"success": True, **result})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/workflows/send-sms", methods=["POST"])
def asha_send_sms():
    try:
        data = request.get_json(silent=True) or {}
        nhm_id = _normalize_nhm_id(data.get("nhm_id"))
        patient_phone = _normalize_phone(data.get("patient_phone"))
        message = str(data.get("message", "")).strip()

        if not nhm_id or len(patient_phone) != 10 or not message:
            return jsonify({"success": False, "error": "nhm_id, patient_phone and message are required"}), 400

        db.collection("asha_messages").add({
            "nhm_id": nhm_id,
            "patient_phone": patient_phone,
            "message": message,
            "channel": "sms",
            "status": "queued",
            "created_at": _server_timestamp(),
        })

        return jsonify({"success": True, "status": "queued", "message": "Message queued and logged"})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/workflows/history", methods=["GET"])
def asha_workflow_history():
    try:
        nhm_id = _normalize_nhm_id(request.args.get("nhm_id"))
        patient_phone = _normalize_phone(request.args.get("patient_phone"))
        limit = int(request.args.get("limit", 10))

        if not nhm_id:
            return jsonify({"success": False, "error": "nhm_id is required"}), 400

        scans_query = db.collection("asha_prescription_scans").where("nhm_id", "==", nhm_id)
        verifications_query = db.collection("asha_medicine_verifications").where("nhm_id", "==", nhm_id)
        messages_query = db.collection("asha_messages").where("nhm_id", "==", nhm_id)

        if patient_phone:
            scans_query = scans_query.where("patient_phone", "==", patient_phone)
            verifications_query = verifications_query.where("patient_phone", "==", patient_phone)
            messages_query = messages_query.where("patient_phone", "==", patient_phone)

        scans_raw = scans_query.limit(100).stream()
        verifications_raw = verifications_query.limit(100).stream()
        messages_raw = messages_query.limit(100).stream()

        return jsonify({
            "success": True,
            "history": {
                "scans": _sorted_firestore_docs(scans_raw, limit=limit),
                "verifications": _sorted_firestore_docs(verifications_raw, limit=limit),
                "messages": _sorted_firestore_docs(messages_raw, limit=limit),
            },
        })
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/asha/workers/nearest", methods=["GET"])
def nearest_workers():
    try:
        area = str(request.args.get("area", "")).strip().lower()
        lat = request.args.get("lat")
        lng = request.args.get("lng")
        limit = int(request.args.get("limit", 10))

        lat = float(lat) if lat not in (None, "") else None
        lng = float(lng) if lng not in (None, "") else None

        docs = db.collection("asha_workers").where("status", "==", "active").limit(100).stream()
        workers = []
        for doc in docs:
            worker = doc.to_dict() or {}
            worker["id"] = doc.id
            village = str(worker.get("village", "")).lower()
            if area and area not in village:
                continue

            location = worker.get("location") or {}
            d_km = _distance_km(lat, lng, location.get("lat"), location.get("lng"))
            worker["distance_km"] = d_km
            workers.append(_to_json_safe(worker))

        workers.sort(key=lambda item: item.get("distance_km") if item.get("distance_km") is not None else 999999)
        return jsonify({"success": True, "workers": workers[:limit]})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/assistant/chat", methods=["POST"])
def assistant_chat():
    try:
        data = request.get_json(silent=True) or {}
        nhm_id = _normalize_nhm_id(data.get("nhm_id"))
        patient_phone = _normalize_phone(data.get("patient_phone"))
        question = str(data.get("message", "")).strip()
        language = str(data.get("language", "EN")).strip().upper() or "EN"

        if not question:
            return jsonify({"success": False, "error": "message is required"}), 400

        answer = _rule_based_health_reply(question)
        db.collection("asha_chat").add({
            "nhm_id": nhm_id,
            "patient_phone": patient_phone,
            "question": question,
            "answer": answer,
            "language": language,
            "created_at": _server_timestamp(),
        })

        return jsonify({"success": True, "answer": answer})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=80)
