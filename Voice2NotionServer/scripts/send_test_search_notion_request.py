import os
import requests
import dotenv

dotenv.load_dotenv()

API_URL = os.getenv("SERVER_URL", "http://localhost:8000/search-notion")
API_KEY = os.getenv("API_KEY", "test-key")

def main():
    prompt = "What tasks do I have labeled with priority Today?" 
    resp = requests.post(
        API_URL,
        json={"query": prompt},
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=10,
    )
    print("Status:", resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)

if __name__ == "__main__":
    main()
