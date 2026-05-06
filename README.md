# SARMAAN II Coverage Dashboard — Sokoto State

**Safety and Antimicrobial Resistance of Mass Administration of Azithromycin in Children 1–59 Months**

A FastAPI dashboard for evaluating household coverage of the SARMAAN II MDA campaign across 6 LGAs and 30 communities in Sokoto State.

## Sections

| Tab | Contents |
|-----|----------|
| **Demographics** | KPI cards, daily submission chart, LGA progress, RA table, settlement coverage, CDD visitation pie |
| **Completeness** | Field fill rates, GPS completeness by LGA |
| **Quality Checks** | Duplicate HH, stacked GPS, mock GPS, per-RA error table |
| **Geospatial** | Leaflet map of all GPS submissions |
| **Validators** | Record-level review with Approved / Not Approached / Not Started status |

## Quick Start

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Open **http://127.0.0.1:8080** and log in with:

- **Email:** `admin@sarmaan.org`
- **Password:** `Sarmaan@2024!`

Click **Sync Data** to pull from KoboToolbox.

## Data Sources

| Sheet | Internal name | Description |
|-------|--------------|-------------|
| Sheet 1 | `household` | Main household consent + demographics |
| Sheet 2 | `all_children` | Child names & sex (merged via `submission__uuid`) |
| Sheet 3 | `net_information` | Net repeat data |
| Sheet 4 | `children_1_59` | Eligible children — AZM offer, swallow, vaccine card |

Settlement planned estimates: `PowerBI files/Settlement Coverage.csv` (join key: `Q4. Community Name` → `Community Code`).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | SQLite local | PostgreSQL URL for production |
| `SUPER_ADMIN_EMAIL` | `admin@sarmaan.org` | Super admin email |
| `SUPER_ADMIN_PASSWORD` | `Sarmaan@2024!` | Super admin password |

## Docker

```bash
docker compose up --build
```
