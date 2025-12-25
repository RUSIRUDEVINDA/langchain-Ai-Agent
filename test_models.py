import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

candidates = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-pro",
    "gemini-pro",
]

print("START_TESTING")
for model_name in candidates:
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Hi")
        print(f"MODEL_FOUND: {model_name}")
        break
    except Exception as e:
        # Just print the error code/brief
        err = str(e).split('\n')[0]
        print(f"FAILED {model_name}: {err}")
