import random
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# Init Firestore
cred = credentials.Certificate("uni-fsm-7b5e1-firebase-adminsdk-fbsvc-4bfb6e8a36.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Configuration
job_categories = ["Bathroom", "Electrical", "Furniture", "Kitchen Appliances", "Windows"]
num_jobs = 500
technicians = []

# Fetch technicians from Firestore
docs = db.collection('users').where('role', '==', 'Technician').stream()
for doc in docs:
    data = doc.to_dict()
    technicians.append({
        "technician_id": doc.id,
        "username": data["username"],
        "skills": data.get("skills", []),
        "active_jobs": data.get("active_jobs", 0)
    })

# Generate synthetic jobs data and
rows = []
for i in range(num_jobs):
    job_id = f"job_{i+1}"
    category = random.choice(job_categories)

    for tech in technicians:
        skill_match = 1 if category in tech["skills"] else 0
        active_jobs = tech["active_jobs"]
        assigned = 1 if skill_match and active_jobs < 3 else 0

        rows.append({
            "job_id": job_id,
            "job_category": category,
            "technician_id": tech["technician_id"],
            "technician_name": tech["username"],
            "skill_match": skill_match,
            "active_jobs": active_jobs,
            "assigned": assigned
        })

# Save to CSV
df = pd.DataFrame(rows)
df.to_csv("job_assignment_data.csv", index=False)
