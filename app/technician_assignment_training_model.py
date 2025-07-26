import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import joblib

# Load the data
df = pd.read_csv("job_assignment_data.csv")

# Encode job_category
label_encoder = LabelEncoder()
df["job_category_encoded"] = label_encoder.fit_transform(df["job_category"])

# Features and target
X = df[["job_category_encoded", "skill_match", "active_jobs"]]
y = df["assigned"]

# Split for training/testing (optional)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train Random Forest model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Save the model and label encoder
joblib.dump((model, label_encoder), "assign_model.pkl")

# Optional: print accuracy
accuracy = model.score(X_test, y_test)
print(f" Model trained with accuracy: {accuracy:.2f}")
print(" Model saved as assign_model.pkl")
