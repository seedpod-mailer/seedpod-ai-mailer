import os, time, requests, psycopg, redis

def main():
    print("Prospector booted")
    api_key = os.getenv("APOLLO_API_KEY")
    resp = requests.get(
        "https://api.apollo.io/v1/auth/health",
        headers={
            "Content-Type": "application/json",
            "X-Api-Key": api_key
        },
    )
    print(f"Apollo health: {resp.status_code} {resp.text}")
    print("Apollo ping:", requests.get("https://api.apollo.io/v1/misc/ping").json())
    print("Sleeping 30 s to prove liveness…"); time.sleep(30)

if __name__ == "__main__":
    main()
