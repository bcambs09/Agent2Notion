import os
import requests

API_URL = os.getenv("SERVER_URL", "http://localhost:8000/add-to-notion")
API_KEY = os.getenv("API_KEY", "test-key")

def main():
    prompt = "Hello from test" 
    resp = requests.post(
        API_URL,
        json={"prompt": prompt},
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
