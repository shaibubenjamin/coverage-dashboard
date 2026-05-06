"""
main.py — SARMAAN II Coverage Evaluation Dashboard
Sokoto State · Safety and Antimicrobial Resistance of Mass Administration
of Azithromycin in Children 1–59 Months
"""
from dotenv import load_dotenv
load_dotenv()

import os
import datetime
from io import BytesIO
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests as http_req
import pandas as pd
from sqlalchemy.orm import Session

from database import init_db, get_db, SessionLocal, User, Role, AuditLog
from auth import (
    hash_password, verify_password,
    create_access_token, get_current_user,
    generate_invite_token,
)

# ── Bootstrap ──────────────────────────────────────────────────────
app = FastAPI(title="SARMAAN II Coverage Dashboard — Sokoto State")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

init_db()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Helpers ────────────────────────────────────────────────────────
def _audit(db: Session, user_id: Optional[int], action: str, details: str = ""):
    db.add(AuditLog(user_id=user_id, action=action, details=details))
    db.commit()


def _user_payload(user: User) -> dict:
    return {
        "access_token":         create_access_token(
            user_id=user.id, email=user.email, name=user.name,
            role=user.role.name, permissions=user.permission_names,
            lgas=[], project_ids=[],
        ),
        "token_type":           "bearer",
        "role":                 user.role.name,
        "name":                 user.name,
        "email":                user.email,
        "must_change_password": user.must_change_password,
        "redirect":             "/coverage",
    }


# ══════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    email:    str
    password: str


@app.post("/api/login")
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=req.email.lower().strip()).first()
    if not user or not user.password_hash:
        raise HTTPException(401, "Invalid email or password")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "Account is disabled. Contact your administrator.")
    _audit(db, user.id, "login", f"role={user.role.name}")
    return _user_payload(user)


class SetPasswordRequest(BaseModel):
    token:    str
    password: str


@app.post("/api/auth/set-password")
def set_password(req: SetPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(invite_token=req.token).first()
    if not user:
        raise HTTPException(400, "Invalid or expired invite link")
    if len(req.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user.password_hash        = hash_password(req.password)
    user.must_change_password = False
    user.invite_token         = None
    db.commit()
    return _user_payload(user)


@app.get("/api/auth/me")
def me(current: dict = Depends(get_current_user)):
    return current


# ══════════════════════════════════════════════════════════════════
#  USER MANAGEMENT  (super_admin / admin only)
# ══════════════════════════════════════════════════════════════════

class UserCreate(BaseModel):
    name:  str
    email: str
    role:  str


class UserUpdate(BaseModel):
    name:      Optional[str]  = None
    role:      Optional[str]  = None
    is_active: Optional[bool] = None


@app.get("/api/users")
def list_users(current: dict = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if current.get("role") not in ("super_admin", "admin"):
        raise HTTPException(403, "Insufficient permissions")
    users = db.query(User).order_by(User.name).all()
    return [{"id": u.id, "name": u.name, "email": u.email,
             "role": u.role.name, "is_active": u.is_active}
            for u in users]


@app.post("/api/users")
def create_user(req: UserCreate, current: dict = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if current.get("role") != "super_admin":
        raise HTTPException(403, "Super admin only")
    role = db.query(Role).filter_by(name=req.role).first()
    if not role:
        raise HTTPException(400, f"Unknown role: {req.role}. Valid: super_admin, admin, validator, public")
    if db.query(User).filter_by(email=req.email.lower().strip()).first():
        raise HTTPException(409, "Email already registered")
    token = generate_invite_token()
    user  = User(
        name=req.name, email=req.email.lower().strip(),
        role_id=role.id, invite_token=token, must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _audit(db, int(current["sub"]), "create_user", f"created {user.email}")
    return {"id": user.id, "invite_token": token,
            "invite_link": f"/set-password?token={token}"}


@app.put("/api/users/{user_id}")
def update_user(user_id: int, req: UserUpdate,
                current: dict = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if current.get("role") != "super_admin":
        raise HTTPException(403, "Super admin only")
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if req.name      is not None: user.name      = req.name
    if req.is_active is not None: user.is_active = req.is_active
    if req.role      is not None:
        role = db.query(Role).filter_by(name=req.role).first()
        if role:
            user.role_id = role.id
    db.commit()
    return {"ok": True}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, current: dict = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if current.get("role") != "super_admin":
        raise HTTPException(403, "Super admin only")
    if int(current["sub"]) == user_id:
        raise HTTPException(400, "Cannot delete your own account")
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
#  COVERAGE DASHBOARD — SARMAAN II SOKOTO STATE
# ══════════════════════════════════════════════════════════════════

_COVERAGE_URL    = "https://kf.kobotoolbox.org/api/v2/assets/aC7agtm3my3Rfq4m4kYaF7/export-settings/esrUMZNBDYTJKNfARBovz2z/data.xlsx"
_COV_PLANNED_HH  = 1_700
_COV_PLANNED_RAS = 41

# Settlement Coverage reference (30 communities × 6 LGAs)
# Join: household["Q4. Community Name"] (holds numeric code) → "Community Code" in CSV
_SETTLEMENT_CSV = os.path.join(BASE_DIR, "PowerBI files", "Settlement Coverage.csv")


def _load_settlement_plan() -> pd.DataFrame:
    try:
        df = pd.read_csv(_SETTLEMENT_CSV)
        df.columns = df.columns.str.strip()
        df["Community Code"] = df["Community Code"].astype(str).str.strip()
        return df
    except Exception as exc:
        print(f"[settlement-plan] failed: {exc}")
        return pd.DataFrame(
            columns=["LGA", "Ward", "Community Name", "Community Code", "Planned"]
        )


_settlement_plan: pd.DataFrame = _load_settlement_plan()

_cov: dict = {
    "household":        None,   # sheet 0
    "all_children":     None,   # sheet 1
    "net_information":  None,   # sheet 2
    "children_1_59":    None,   # sheet 3
    "last_synced":      None,
    "syncing":          False,
    "error":            None,
}
_cov_status: dict = {}   # {row_idx: "Approved"|"Not Approached"|"Not Started"}


# ── Utilities ──────────────────────────────────────────────────────

def _col(df: pd.DataFrame, *keywords) -> Optional[str]:
    """First column whose name contains ALL keywords (case-insensitive)."""
    if df is None:
        return None
    kw = [k.lower() for k in keywords]
    for col in df.columns:
        if all(k in col.lower() for k in kw):
            return col
    return None


def _require_cov():
    if _cov["household"] is None:
        raise HTTPException(503, "Coverage data not loaded — click Sync Data first.")


def _consented() -> pd.DataFrame:
    """Household rows where the consent field = 'Yes'."""
    hh = _cov["household"]
    cc = _col(hh, "voluntary") or _col(hh, "agree to participate") or _col(hh, "participation")
    if cc:
        return hh[hh[cc].astype(str).str.strip() == "Yes"].copy()
    return hh.copy()


# ── Sync ───────────────────────────────────────────────────────────

def _do_sync():
    _cov["syncing"] = True
    _cov["error"]   = None
    try:
        resp = http_req.get(_COVERAGE_URL, timeout=180)
        resp.raise_for_status()
        xls = pd.ExcelFile(BytesIO(resp.content))
        _cov["household"]       = pd.read_excel(xls, sheet_name=0)
        _cov["all_children"]    = pd.read_excel(xls, sheet_name=1)
        _cov["net_information"] = pd.read_excel(xls, sheet_name=2)
        _cov["children_1_59"]  = pd.read_excel(xls, sheet_name=3)
        _cov["last_synced"]     = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        print(f"[sync] OK — {len(_cov['household'])} household rows")
    except Exception as exc:
        _cov["error"] = str(exc)
        print(f"[sync] FAILED: {exc}")
    finally:
        _cov["syncing"] = False


@app.post("/api/coverage/sync")
def cov_sync(background_tasks: BackgroundTasks,
             current: dict = Depends(get_current_user)):
    if _cov["syncing"]:
        return {"status": "already_running"}
    background_tasks.add_task(_do_sync)
    return {"status": "started"}


@app.get("/api/coverage/status")
def cov_status():
    return {
        "loaded":      _cov["household"] is not None,
        "syncing":     _cov["syncing"],
        "last_synced": _cov["last_synced"],
        "error":       _cov["error"],
        "rows": {
            "household":       len(_cov["household"])       if _cov["household"]       is not None else 0,
            "all_children":    len(_cov["all_children"])    if _cov["all_children"]    is not None else 0,
            "net_information": len(_cov["net_information"]) if _cov["net_information"] is not None else 0,
            "children_1_59":   len(_cov["children_1_59"])  if _cov["children_1_59"]   is not None else 0,
        },
    }


# ── Demographics ───────────────────────────────────────────────────

@app.get("/api/coverage/demographics")
def cov_demographics():
    _require_cov()
    con = _consented()
    total = len(con)

    def _pct(a, b): return round(a / b * 100, 1) if b else 0
    def _isum(df, col):
        if not col or col not in df.columns: return 0
        return int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())

    ch_col   = _col(con, "children currently live")
    elig_col = "total_eligible" if "total_eligible" in con.columns else _col(con, "total_eligible")
    total_ch   = _isum(con, ch_col)
    total_elig = _isum(con, elig_col)

    offered = not_offered = swallowed = vacc = 0
    c59 = _cov["children_1_59"]
    if c59 is not None:
        q90 = _col(c59, "azithromycin") or _col(c59, "Q90")
        q94 = _col(c59, "swallow")      or _col(c59, "Q94")
        vc  = _col(c59, "vaccination card")
        if q90:
            offered     = int((c59[q90].astype(str).str.strip() == "Yes").sum())
            not_offered = int((c59[q90].astype(str).str.strip() == "No").sum())
        if q94:
            swallowed   = int((c59[q94].astype(str).str.strip() == "Yes").sum())
        if vc:
            vacc        = int((c59[vc].astype(str).str.strip() == "Yes").sum())

    lga_c  = _col(con, "Local Government Area")
    wrd_c  = _col(con, "Q3") or _col(con, "Ward")
    com_c  = _col(con, "Community Name")

    plan   = _settlement_plan
    pl_lga = plan["LGA"].dropna().nunique()                         if "LGA"  in plan.columns else 0
    pl_wrd = plan[["LGA","Ward"]].dropna().drop_duplicates().shape[0] if "Ward" in plan.columns else 0
    pl_com = len(plan)

    return {
        "total_submissions":   total,
        "planned_total":       _COV_PLANNED_HH,
        "pct_of_planned":      _pct(total, _COV_PLANNED_HH),
        "total_children":      total_ch,
        "total_eligible":      total_elig,
        "pct_eligible":        _pct(total_elig, total_ch),
        "offered_azm":         offered,
        "pct_offered":         _pct(offered, total_elig),
        "not_offered_azm":     not_offered,
        "pct_not_offered":     _pct(not_offered, total_elig),
        "swallowed_azm":       swallowed,
        "didnt_swallow":       offered - swallowed,
        "pct_swallowed":       _pct(swallowed, offered),
        "hh_vaccine_card":     vacc,
        "pct_vaccine_card":    _pct(vacc, total),
        "lgas_reached":        con[lga_c].dropna().nunique() if lga_c else 0,
        "planned_lgas":        pl_lga,
        "wards_reached":       con[wrd_c].dropna().nunique() if wrd_c else 0,
        "planned_wards":       pl_wrd,
        "communities_reached": con[com_c].dropna().nunique() if com_c else 0,
        "planned_communities": pl_com,
    }


# ── Charts ─────────────────────────────────────────────────────────

@app.get("/api/coverage/charts/daily")
def cov_daily():
    _require_cov()
    df = _consented().copy()
    tc = "_submission_time"
    if tc not in df.columns:
        tc = next((c for c in df.columns if "submission_time" in c.lower()), None)
    if not tc:
        return {"labels": [], "values": []}
    df["_d"] = pd.to_datetime(df[tc], errors="coerce").dt.date
    out = (df.dropna(subset=["_d"]).groupby("_d").size()
             .reset_index(name="n").sort_values("_d"))
    return {"labels": [str(d) for d in out["_d"]], "values": out["n"].tolist()}


@app.get("/api/coverage/charts/lga-progress")
def cov_lga_progress():
    _require_cov()
    df    = _consented()
    lga_c = _col(df, "Local Government Area")
    if not lga_c:
        return {"rows": []}

    counts_map = {str(r[lga_c]): int(r["reached"])
                  for _, r in df.groupby(lga_c).size().reset_index(name="reached").iterrows()}

    plan_map: dict = {}
    for _, row in _settlement_plan.iterrows():
        lga = str(row.get("LGA", "")).strip()
        if lga:
            plan_map[lga] = plan_map.get(lga, 0) + int(float(row.get("Planned", 0) or 0))

    all_lgas = sorted(set(plan_map) | set(counts_map))
    rows = []
    for lga in all_lgas:
        reached = counts_map.get(lga, 0)
        planned = plan_map.get(lga, 0)
        rows.append({"lga": lga, "reached": reached, "planned": planned,
                     "pct": round(reached / planned * 100, 1) if planned else None})
    return {"rows": rows}


@app.get("/api/coverage/charts/ra-performance")
def cov_ra_performance():
    _require_cov()
    df   = _consented()
    ra_c = _col(df, "confirm user")
    lg_c = _col(df, "Local Government Area")
    if not ra_c:
        return {"rows": [], "total": 0}
    gcols = [c for c in [ra_c, lg_c] if c]
    grp   = df.groupby(gcols).size().reset_index(name="count")
    total = len(df)
    rows  = [{"ra": str(r.get(ra_c, "")), "lga": str(r.get(lg_c, "")) if lg_c else "",
               "submissions": int(r["count"]),
               "pct": round(int(r["count"]) / total * 100, 1) if total else 0}
             for _, r in grp.iterrows()]
    return {"rows": sorted(rows, key=lambda x: x["submissions"], reverse=True), "total": total}


@app.get("/api/coverage/charts/settlement-table")
def cov_settlement_table():
    """
    Join household Q4 (community code) → Settlement Coverage.csv Community Code.
    Returns all 30 planned communities with reached counts (0 if not yet visited).
    """
    _require_cov()
    df = _consented().copy()
    q4_c = _col(df, "Q4") or _col(df, "Community Name")
    if not q4_c:
        return {"rows": []}

    df["_code"] = df[q4_c].astype(str).str.strip()
    reached_map = {str(r["_code"]): int(r["reached"])
                   for _, r in df.groupby("_code").size().reset_index(name="reached").iterrows()}

    plan_map = {
        str(row["Community Code"]): {
            "lga":     row.get("LGA", ""),
            "ward":    row.get("Ward", ""),
            "name":    row.get("Community Name", ""),
            "planned": int(float(row.get("Planned", 0) or 0)),
        }
        for _, row in _settlement_plan.iterrows()
    }

    rows = []
    for code, meta in plan_map.items():
        reached = reached_map.get(code, 0)
        planned = meta["planned"]
        pct     = round(reached / planned * 100, 1) if planned else 0.0
        rows.append({"lga": meta["lga"], "ward": meta["ward"],
                     "settlement": meta["name"], "code": code,
                     "planned": planned, "reached": reached, "pct": pct})

    return {"rows": sorted(rows, key=lambda x: (x["lga"], x["ward"], x["settlement"]))}


@app.get("/api/coverage/charts/cdd-visitation")
def cov_cdd():
    _require_cov()
    hh   = _cov["household"]
    q86  = _col(hh, "visit your home") or _col(hh, "Q86")
    if not q86:
        return {"yes": 0, "no": 0}
    yes = int((hh[q86].astype(str).str.strip() == "Yes").sum())
    no  = int((hh[q86].astype(str).str.strip() == "No").sum())
    return {"yes": yes, "no": no}


# ── Quality Checks ─────────────────────────────────────────────────

@app.get("/api/coverage/quality")
def cov_quality():
    _require_cov()
    hh = _cov["household"]

    uid_c  = "unique_code" if "unique_code" in hh.columns else _col(hh, "unique_code")
    dup_hh = int((hh[uid_c].value_counts() > 1).sum()) if uid_c else 0

    lat_c = _col(hh, "latitude")
    lon_c = _col(hh, "longitude")
    stacked = 0
    if lat_c and lon_c:
        valid   = hh[[lat_c, lon_c]].dropna()
        stacked = int((valid.groupby([lat_c, lon_c]).size() > 1).sum())

    ra_c      = _col(hh, "confirm user")
    actual_ra = int(hh[ra_c].dropna().nunique()) if ra_c else 0

    prec_c   = _col(hh, "precision")
    mock_gps = int((pd.to_numeric(hh[prec_c], errors="coerce") < 2).sum()) if prec_c else 0

    return {
        "duplicate_hh":  dup_hh,
        "stacked_gps":   stacked,
        "planned_ras":   _COV_PLANNED_RAS,
        "actual_ras":    actual_ra,
        "mock_gps":      mock_gps,
        "total_records": len(hh),
    }


@app.get("/api/coverage/quality/table")
def cov_quality_table():
    _require_cov()
    hh = _cov["household"].copy()

    lga_c  = _col(hh, "Local Government Area")
    wrd_c  = _col(hh, "Q3") or _col(hh, "Ward")
    com_c  = _col(hh, "Community Name")
    ra_c   = _col(hh, "confirm user")
    uid_c  = "unique_code" if "unique_code" in hh.columns else None
    lat_c  = _col(hh, "latitude")
    lon_c  = _col(hh, "longitude")
    prec_c = _col(hh, "precision")

    hh["_dup"]   = hh[uid_c].duplicated(keep=False) if uid_c else False
    if lat_c and lon_c:
        cnt = hh.groupby([lat_c, lon_c])[lat_c].transform("count")
        hh["_stack"] = (cnt > 1) & hh[lat_c].notna()
    else:
        hh["_stack"] = False
    hh["_mock"] = (pd.to_numeric(hh[prec_c], errors="coerce") < 2) if prec_c else False

    gcols = [c for c in [lga_c, wrd_c, com_c, ra_c] if c]
    if not gcols:
        return {"rows": []}

    rows = []
    for key, grp in hh.groupby(gcols):
        if not isinstance(key, tuple):
            key = (key,)
        kd    = dict(zip(gcols, key))
        total = len(grp)
        dups  = int(grp["_dup"].sum())
        stk   = int(grp["_stack"].sum())
        mock  = int(grp["_mock"].sum())
        errs  = dups + stk + mock
        rows.append({
            "lga": kd.get(lga_c, ""), "ward": kd.get(wrd_c, ""),
            "settlement": kd.get(com_c, ""), "ra": kd.get(ra_c, ""),
            "total": total, "duplicates": dups, "stacked_gps": stk,
            "mock_gps": mock, "error_pct": round(errs / total * 100, 1) if total else 0,
        })
    return {"rows": sorted(rows, key=lambda x: x["error_pct"], reverse=True)}


# ── Completeness ───────────────────────────────────────────────────

@app.get("/api/coverage/completeness")
def cov_completeness():
    _require_cov()
    hh    = _cov["household"]
    total = len(hh)

    def _fp(col):
        if not col or col not in hh.columns or total == 0: return 0.0
        return round(hh[col].replace("", pd.NA).dropna().shape[0] / total * 100, 1)

    lga_c = _col(hh, "Local Government Area")
    by_lga = []
    if lga_c:
        lat_c = _col(hh, "latitude")
        for lga, grp in hh.groupby(lga_c):
            n      = len(grp)
            gps_ok = int(grp[lat_c].notna().sum()) if lat_c else 0
            by_lga.append({"lga": str(lga), "total": n, "gps_ok": gps_ok,
                            "gps_pct": round(gps_ok / n * 100, 1) if n else 0})

    return {
        "fields": {
            "LGA":         _fp(_col(hh, "Local Government Area")),
            "Ward":        _fp(_col(hh, "Q3") or _col(hh, "Ward")),
            "Community":   _fp(_col(hh, "Community Name")),
            "GPS":         _fp(_col(hh, "latitude")),
            "Head Name":   _fp(_col(hh, "Name of the Head")),
            "Head Gender": _fp(_col(hh, "Gender of the Head")),
        },
        "by_lga": sorted(by_lga, key=lambda x: x["lga"]),
    }


# ── Geospatial ─────────────────────────────────────────────────────

@app.get("/api/coverage/geospatial")
def cov_geospatial():
    _require_cov()
    hh    = _cov["household"]
    lat_c = _col(hh, "latitude")
    lon_c = _col(hh, "longitude")
    lga_c = _col(hh, "Local Government Area")
    if not (lat_c and lon_c):
        return {"points": [], "lgas": []}

    sub = hh[[lat_c, lon_c] + ([lga_c] if lga_c else [])].dropna(subset=[lat_c, lon_c])
    points = []
    for _, r in sub.iterrows():
        try:
            points.append({"lat": float(r[lat_c]), "lon": float(r[lon_c]),
                           "lga": str(r[lga_c]) if lga_c else ""})
        except (ValueError, TypeError):
            pass
    return {
        "points": points,
        "lgas":   sorted(hh[lga_c].dropna().unique().tolist()) if lga_c else [],
    }


# ── Validators ─────────────────────────────────────────────────────

class StatusUpdate(BaseModel):
    idx:    int
    status: str


@app.put("/api/coverage/validators/status")
def cov_set_status(req: StatusUpdate, current: dict = Depends(get_current_user)):
    allowed = {"Approved", "Not Approached", "Not Started"}
    if req.status not in allowed:
        raise HTTPException(400, f"Status must be one of {allowed}")
    _cov_status[req.idx] = req.status
    return {"ok": True}


@app.get("/api/coverage/validators")
def cov_validators(page: int = 1, per_page: int = 50, lga: str = ""):
    _require_cov()
    hh = _cov["household"]
    ac = _cov["all_children"]

    ra_c   = _col(hh, "confirm user")
    lga_c  = _col(hh, "Local Government Area")
    wrd_c  = _col(hh, "Q3") or _col(hh, "Ward")
    com_c  = _col(hh, "Community Name")
    q11_c  = _col(hh, "Name of the Head")
    q12_c  = _col(hh, "Gender of the Head")
    uuid_c = "submission__uuid" if "submission__uuid" in hh.columns else None

    col_map = {k: v for k, v in {
        "ra": ra_c, "lga": lga_c, "ward": wrd_c, "community": com_c,
        "head_name": q11_c, "head_gender": q12_c, "uuid": uuid_c,
    }.items() if v and v in hh.columns}

    df = hh[[v for v in col_map.values()]].copy()
    df.columns = list(col_map.keys())
    df = df.reset_index(drop=True)
    df["_idx"] = df.index

    if lga and "lga" in df.columns:
        df = df[df["lga"].astype(str).str.strip() == lga.strip()].copy()

    # Merge children names / sex from all_children sheet
    if ac is not None and "uuid" in df.columns:
        nm_c = _col(ac, "Child name and age")
        sx_c = _col(ac, "Sex of")
        ua_c = "submission__uuid" if "submission__uuid" in ac.columns else None
        if nm_c and ua_c:
            ac_sub = ac[[ua_c, nm_c] + ([sx_c] if sx_c else [])].copy()
            ac_sub.columns = ["uuid", "child_name"] + (["child_sex"] if sx_c else [])
            def _agg(sub_df):
                names = sub_df["child_name"].dropna().astype(str).tolist()
                if "child_sex" in sub_df.columns:
                    sexes = sub_df["child_sex"].dropna().astype(str).tolist()
                    return "; ".join(f"{n} ({s})" for n, s in zip(names, sexes))
                return "; ".join(names)
            ac_agg = ac_sub.groupby("uuid").apply(_agg).reset_index()
            ac_agg.columns = ["uuid", "children"]
            df = df.merge(ac_agg, on="uuid", how="left")

    df["status"] = df["_idx"].map(lambda i: _cov_status.get(i, "Not Started"))
    total   = len(df)
    page_df = df.iloc[(page - 1) * per_page: page * per_page].fillna("")
    records = page_df.drop(columns=[c for c in ["_idx", "uuid"] if c in page_df.columns]).to_dict(orient="records")

    all_lgas = sorted(hh[lga_c].dropna().unique().tolist()) if lga_c else []
    return {"total": total, "page": page, "per_page": per_page,
            "records": records, "lgas": all_lgas}


# ══════════════════════════════════════════════════════════════════
#  STATIC FILES & PAGE ROUTES
# ══════════════════════════════════════════════════════════════════

static_path = os.path.join(BASE_DIR, "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/")
def root():
    return FileResponse(os.path.join(static_path, "login.html"))


@app.get("/coverage")
def coverage_page():
    return FileResponse(os.path.join(static_path, "coverage.html"))


@app.get("/set-password")
def set_password_page():
    return FileResponse(os.path.join(static_path, "set-password.html"))
