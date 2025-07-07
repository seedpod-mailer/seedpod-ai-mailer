# File: agents/prospector/prospector.py

import os
import time
import requests
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

# Apollo search filters tailored to Cyber Insurance and MSP segments
APOLLO_BASE = "https://api.apollo.io/v1/contacts/search"
BASE_FILTERS = {
    "q_organization_revenue": "5-500M",
    "q_country": "United States",
    "q_organization_industry": [
        "Financial Services",
        "Healthcare",
        "Manufacturing",
        "Wholesale Distribution",
        "Logistics",
        "Nonprofit",
        "Managed Service Providers",
        "Information Technology & Services"
    ],
    "q_funding_rounds": ["Series A","Series B","Series C","Series D"],
    "q_titles": [
        "CISO","Head of Risk","VP of IT","VP of Finance",
        "Risk Manager","Insurance Manager","MSP Owner","MSP Principal"
    ],
    "q_seniority": ["Manager","Director","VP","C-level"]
}

# Fetch settings from environment
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "100"))           # contacts per API page
MAX_LEADS_PER_RUN = int(os.getenv("MAX_LEADS_PER_RUN", "0"))  # 0 = unlimited

# Industries to be treated as tech E&O + Cyber
MSP_INDUSTRIES = {"Managed Service Providers", "Information Technology & Services"}


def fetch_contacts(api_key, filters, page):
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key
    }
    payload = filters.copy()
    payload.update({"page": page, "per_page": PAGE_SIZE})

    resp = requests.post(APOLLO_BASE, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data.get("contacts", []), data.get("meta", {}).get("next_page")


def main():
    print("Prospector starting…")
    api_key = os.getenv("APOLLO_API_KEY")
    if not api_key:
        raise RuntimeError("APOLLO_API_KEY not set")

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    # Connect to Postgres
    conn = psycopg.connect(db_url, row_factory=dict_row)
    cur = conn.cursor()

    # Ensure leads and state tables exist
    cur.execute("""
    CREATE SCHEMA IF NOT EXISTS prospector;
    CREATE TABLE IF NOT EXISTS prospector.leads (
        contact_id   TEXT PRIMARY KEY,
        name         TEXT,
        email        TEXT,
        company_name TEXT,
        industry     TEXT,
        revenue_band TEXT,
        segment      TEXT,
        created_at   TIMESTAMPTZ,
        ingested_at  TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS prospector.state (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    conn.commit()

    # Load last run timestamp
    cur.execute("SELECT value FROM prospector.state WHERE key = 'last_run';")
    row = cur.fetchone()
    last_run = row['value'] if row else None
    filters = BASE_FILTERS.copy()
    if last_run:
        filters['q_created_after'] = last_run
        print(f"Filtering Apollo for contacts created after {last_run}")

    total_new = 0
    page = 1
    # Fetch up to MAX_LEADS_PER_RUN (if set), in pages of PAGE_SIZE
    while True:
        # Stop if we've reached the max leads per run
        if MAX_LEADS_PER_RUN and total_new >= MAX_LEADS_PER_RUN:
            break

        contacts, next_page = fetch_contacts(api_key, filters, page)
        if not contacts:
            break

        for c in contacts:
            if MAX_LEADS_PER_RUN and total_new >= MAX_LEADS_PER_RUN:
                break

            cid = c.get('id')
            name = f"{c.get('first_name','')} {c.get('last_name','')}".strip()
            email = c.get('email')
            company = c.get('company_name')
            industry = c.get('industry', 'Unknown')
            revenue = c.get('organization_revenue_range', '5-500M')
            created = c.get('created_at') or (datetime.utcnow().isoformat() + 'Z')

            # Determine segment
            seg = 'tech_eo_cyber' if industry in MSP_INDUSTRIES else 'cyber_insurance'

            # Upsert new lead
            cur.execute(
                """
                INSERT INTO prospector.leads
                  (contact_id, name, email, company_name, industry, revenue_band, segment, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (contact_id) DO NOTHING
                """,
                (cid, name, email, company, industry, revenue, seg, created)
            )
            total_new += cur.rowcount

        conn.commit()
        print(f"Page {page}: fetched {len(contacts)}, new leads so far: {total_new}")

        # Stop pagination if no next page or reached max
        if not next_page or (MAX_LEADS_PER_RUN and total_new >= MAX_LEADS_PER_RUN):
            break

        page = next_page
        time.sleep(1)

    # Update last_run timestamp
    now_iso = datetime.utcnow().isoformat() + 'Z'
    cur.execute(
        "INSERT INTO prospector.state (key, value) VALUES ('last_run', %s)"
        " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (now_iso,)
    )
    conn.commit()

    print(f"Prospector completed: {total_new} new contacts ingested. last_run set to {now_iso}")


if __name__ == '__main__':
    main()

