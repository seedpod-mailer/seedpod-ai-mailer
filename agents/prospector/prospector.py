import os, time, requests, psycopg, redis

def main():
    print("Prospector booted")
    print("Apollo ping:", requests.get("https://api.apollo.io/v1/misc/ping").json())
    print("Sleeping 30 s to prove liveness…"); time.sleep(30)

if __name__ == "__main__":
    main()
