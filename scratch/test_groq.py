import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

print(f"Testing Groq key: {api_key[:10]}...")

try:
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "test",
            }
        ],
        model="llama-3.3-70b-versatile",
    )
    print("Groq Success!")
except Exception as e:
    print(f"Groq Failed: {e}")
