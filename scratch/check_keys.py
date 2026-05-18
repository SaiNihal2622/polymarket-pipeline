from dotenv import load_dotenv
import os
load_dotenv()
keys = ['NVIDIA_API_KEY','GROQ_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','POLY_API_KEY','POLY_SECRET','POLY_PASSPHRASE']
for k in keys:
    v = os.getenv(k, '')
    status = "SET" if v else "EMPTY"
    print(f"{k}: {status} ({len(v)} chars)")