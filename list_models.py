from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai
import os

api_key = os.getenv('GOOGLE_API_KEY')
if api_key:
    genai.configure(api_key=api_key)
    models = genai.list_models()
    print("Available models for generateContent:")
    for m in models:
        if 'generateContent' in m.supported_generation_methods:
            print(f"  - {m.name}")
else:
    print("GOOGLE_API_KEY not set in environment")
