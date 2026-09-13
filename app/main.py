from __future__ import annotations

import os
import re
import json
import shlex
import sqlite3
import smtplib
import ssl
import subprocess
import time
import threading
import hashlib
import base64
import secrets
import hmac
import tempfile
import contextvars
import uuid
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from io import BytesIO
from email.message import EmailMessage
from html import escape, unescape
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote

import requests
from app import profile_documents
import qrcode
import struct
import paramiko
from bs4 import BeautifulSoup
try:
    from pypdf import PdfReader
except Exception:  # PDF parsing is optional; provider falls back to release-note link only.
    PdfReader = None
from fastapi import FastAPI, Form, Request, UploadFile, File, HTTPException
from starlette.concurrency import run_in_threadpool
from app.ssh_transport import ssh_client as _ssh_client
from app.database_access import DatabaseGate
from app.http_fetch import get as _document_get
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, StreamingResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError


try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import Paragraph, Table, TableStyle
except Exception:  # Report generation is unavailable until dependencies are installed.
    colors = None
    A4 = None

from app.providers.github import fetch_latest_stable as fetch_github_latest_stable
from app.providers.github import repository_from_url as github_repository_from_url
from app.providers.registry import infer_provider
from app.device_profiles import DEFAULT_CATALOG_URL as DEVICE_PROFILES_CATALOG_URL, ensure_profile as ensure_device_profile, installed_profiles as load_installed_device_profiles, load_catalog as load_device_profiles_catalog, match_profile as match_device_profile, profile_version_map as device_profile_version_map, prune_profiles as prune_device_profiles, sync_catalog as sync_device_profiles_catalog

APP_VERSION = "0.18.8"
APP_DATE = "12-09-2026"
DATABASE_SCHEMA_VERSION = "0.18.8"
INSTALLER_VERSION = "0.18.8"

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
DATA_DIR = Path(os.environ.get("OUTLAWS_DATA_DIR") or (BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
KEY_DIR = DATA_DIR / "keys"
SECRETS_DIR = DATA_DIR / "secrets"
UPDATE_STAGING_DIR = DATA_DIR / "update-staging"
RECONNECT_DIR = DATA_DIR / "reconnect-actions"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_INSPECTION_CACHE_FILE = DATA_DIR / "backup-inspection-cache.json"
SETUP_STATE_DIR = DATA_DIR / "setup-state"
AVATAR_DIR = DATA_DIR / "avatars"
GITHUB_TOKEN_FILE = SECRETS_DIR / "github-token"
SMTP_PASSWORD_FILE = SECRETS_DIR / "smtp-password"
APPLICATION_UPDATE_REPOSITORY = "OutlawNL/outlaws-inventory"
DB_PATH = DATA_DIR / "outlaws-inventory.db"
DEVICE_PROFILES_DIR = DATA_DIR / "device-profiles"
DEVICE_PROFILES_CACHE_FILE = DEVICE_PROFILES_DIR / "catalog.json"
DEVICE_PROFILES_INSTALLED_DIR = DEVICE_PROFILES_DIR / "profiles"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
KEY_DIR.mkdir(parents=True, exist_ok=True)
SECRETS_DIR.mkdir(parents=True, exist_ok=True)
UPDATE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
RECONNECT_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
SETUP_STATE_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
DEVICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
try:
    KEY_DIR.chmod(0o700)
    SECRETS_DIR.chmod(0o700)
    UPDATE_STAGING_DIR.chmod(0o700)
    RECONNECT_DIR.chmod(0o700)
    AVATAR_DIR.chmod(0o700)
    DEVICE_PROFILES_DIR.chmod(0o700)
except Exception:
    pass

PROCESS_START_ID = uuid.uuid4().hex

# In-process state for long-running browser actions. The state is keyed by
# authenticated user so a page reload can reconnect to an operation that is
# still running instead of losing its progress indication.
_OPERATION_STATE_LOCK = threading.Lock()
_OPERATION_STATES: dict[tuple[int, str], dict[str, object]] = {}

def _operation_state(name: str, user_id: int | None = None) -> dict[str, object]:
    owner = int(user_id if user_id is not None else require_current_user_id())
    with _OPERATION_STATE_LOCK:
        state = dict(_OPERATION_STATES.get((owner, name), {}))
    return {
        "running": bool(state.get("running", False)),
        "started_at": str(state.get("started_at", "") or ""),
        "finished_at": str(state.get("finished_at", "") or ""),
        "error": str(state.get("error", "") or ""),
    }

def _start_user_operation(name: str, user_id: int, action) -> bool:
    key = (int(user_id), name)
    with _OPERATION_STATE_LOCK:
        current = _OPERATION_STATES.get(key) or {}
        if current.get("running"):
            return False
        _OPERATION_STATES[key] = {
            "running": True,
            "started_at": now(),
            "finished_at": "",
            "error": "",
        }

    def worker() -> None:
        token = _CURRENT_USER_ID.set(int(user_id))
        error = ""
        try:
            action()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:1000]
            print(f"Background operation {name} failed: {error}", flush=True)
        finally:
            _CURRENT_USER_ID.reset(token)
            with _OPERATION_STATE_LOCK:
                _OPERATION_STATES[key] = {
                    "running": False,
                    "started_at": str((_OPERATION_STATES.get(key) or {}).get("started_at", "")),
                    "finished_at": now(),
                    "error": error,
                }

    threading.Thread(target=worker, name=f"oi-{name}-{user_id}", daemon=True).start()
    return True

def normalize_runtime_data_permissions() -> None:
    """Apply safe runtime modes after install/restore without depending on archive metadata."""
    directory_modes = {
        DATA_DIR: 0o750,
        UPLOAD_DIR: 0o750,
        BACKUP_DIR: 0o700,
        KEY_DIR: 0o700,
        SECRETS_DIR: 0o700,
        UPDATE_STAGING_DIR: 0o700,
        RECONNECT_DIR: 0o700,
        SETUP_STATE_DIR: 0o700,
        AVATAR_DIR: 0o700,
    }
    for directory, mode in directory_modes.items():
        try:
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(mode)
        except OSError:
            pass
    try:
        for path in KEY_DIR.iterdir():
            if path.is_file():
                path.chmod(0o644 if path.suffix == ".pub" else 0o600)
    except OSError:
        pass
    for path in (GITHUB_TOKEN_FILE, SMTP_PASSWORD_FILE):
        try:
            if path.is_file():
                path.chmod(0o600)
        except OSError:
            pass
    try:
        if DB_PATH.is_file():
            DB_PATH.chmod(0o600)
    except OSError:
        pass
    for private_dir in (UPLOAD_DIR, AVATAR_DIR, BACKUP_DIR):
        try:
            for path in private_dir.iterdir():
                if path.is_file():
                    path.chmod(0o600)
        except OSError:
            pass

app = FastAPI(title="Outlaw's Inventory", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

_CURRENT_USER_ID: contextvars.ContextVar[int | None] = contextvars.ContextVar("outlaws_current_user_id", default=None)

def current_user_id() -> int | None:
    value = _CURRENT_USER_ID.get()
    if value is not None:
        return int(value)
    try:
        with db() as con:
            row = con.execute("SELECT id FROM users WHERE is_active=1 ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, id LIMIT 1").fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None

def require_current_user_id() -> int:
    value = current_user_id()
    if value is None:
        raise RuntimeError("No authenticated user is available.")
    return value

DEFAULT_CATEGORIES = ["3D Printer", "Audio", "Camera", "Computer", "Drone", "Lens", "Network", "Other", "Printer", "Server", "Smart Home", "Vehicle"]
CATEGORIES = DEFAULT_CATEGORIES
LIFECYCLES = ["Supported", "Legacy", "Discontinued", "End of Support", "Unknown"]
FIRMWARE_SOURCES = ["Official website", "GitHub", "Vendor support", "Community source", "Manual", "Unknown"]
FIRMWARE_PROVIDERS = ["Auto", "GitHub", "GL.iNet", "Garmin", "Brother", "Fujifilm", "DJI", "Onkyo", "Generic website", "Vendor-managed", "Manual"]
CHECK_METHODS = ["Official website", "Community source", "Vendor application", "Manual", "Not configured"]
CONFIDENCES = ["Official", "API", "Community", "Manual", "Unknown"]
STATUS_LABELS = {"ok": "OK", "attention": "Update", "deferred": "Deferred", "unknown": "Unknown"}


def status_label(status: str | None) -> str:
    return STATUS_LABELS.get(status or "unknown", "Unknown")


def display_date(value: str | None) -> str:
    """Display dates as DD-MM-YYYY when possible; keep free text as-is."""
    if not value:
        return ""
    v = value.strip()
    # Stored ISO format
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(v, fmt).strftime("%d-%m-%Y")
        except ValueError:
            pass
    # Already Dutch format
    try:
        return datetime.strptime(v, "%d-%m-%Y").strftime("%d-%m-%Y")
    except ValueError:
        pass
    # US-style source dates such as 07-26-2025 -> 26-07-2025
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})", v)
    if m:
        a, b, y = map(int, m.groups())
        if a <= 12 and b > 12:
            return f"{b:02d}-{a:02d}-{y}"
    return v


def format_euro(value: str | None) -> str:
    """Normalize purchase prices to Dutch-style euro display, e.g. € 100,00."""
    if not value:
        return ""
    v = str(value).strip()
    if not v:
        return ""
    v = v.replace("€", "").strip()
    v = re.sub(r"\s+", "", v)
    # Keep already Dutch decimals; convert simple dot decimals to comma.
    if re.fullmatch(r"\d+(?:\.\d{1,2})?", v):
        if "." in v:
            euros, cents = v.split(".", 1)
            cents = (cents + "00")[:2]
        else:
            euros, cents = v, "00"
        return f"€ {int(euros):,}".replace(",", ".") + f",{cents}"
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*,\d{1,2}", v) or re.fullmatch(r"\d+,\d{1,2}", v):
        euros, cents = v.rsplit(",", 1)
        cents = (cents + "00")[:2]
        return f"€ {euros},{cents}"
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})*", v):
        return f"€ {v},00"
    # Unknown/free-form value: keep it, but prefix euro if it looks like a price.
    return f"€ {v}" if not value.strip().startswith("€") else value.strip()

def display_name(device) -> str:
    if not device:
        return ""
    try:
        return (device["display_name"] or device["name"] or "").strip()
    except Exception:
        return (device.get("display_name") or device.get("name") or "").strip()


def tag_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [t.strip() for t in value.split(",") if t.strip()]


CATEGORY_ICONS = {
    "3D Printer": "box-3d", "Audio": "headphones", "Camera": "camera", "Computer": "monitor",
    "Drone": "drone", "Lens": "aperture", "Network": "network", "Other": "package",
    "Printer": "printer", "Server": "server", "Smart Home": "home", "Vehicle": "car",
}


def category_icon(value: str | None) -> str:
    """Return the visual icon key for a category; custom categories use a neutral fallback."""
    return CATEGORY_ICONS.get((value or "").strip(), "package")


def next_check_at(last_checked: str | None, interval_minutes: int | None) -> str:
    if not last_checked:
        return "Due now"
    try:
        dt = datetime.strptime(last_checked, "%Y-%m-%d %H:%M")
        from datetime import timedelta
        return (dt + timedelta(minutes=max(1, int(interval_minutes or 10)))).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "Due soon"


def offline_for(last_online: str | None, last_checked: str | None = None) -> str:
    """Human readable offline duration based on the last successful check."""
    source = (last_online or "").strip()
    if not source:
        return "Offline"
    try:
        dt = datetime.strptime(source, "%Y-%m-%d %H:%M")
    except ValueError:
        return "Offline"
    seconds = max(0, int((datetime.now() - dt).total_seconds()))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    if days:
        return f"Offline for {days}d {hours}h"
    if hours:
        return f"Offline for {hours}h {minutes}m"
    return f"Offline for {max(1, minutes)}m"


def current_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def effective_latest_value(automatic: str | None, override: str | None) -> str:
    return _effective_latest_version(automatic or "", override or "")


templates.env.filters["status_label"] = status_label
templates.env.filters["display_date"] = display_date
templates.env.filters["format_euro"] = format_euro
templates.env.filters["tag_list"] = tag_list
templates.env.filters["category_icon"] = category_icon
templates.env.filters["next_check_at"] = next_check_at
templates.env.filters["offline_for"] = offline_for
templates.env.filters["effective_latest"] = effective_latest_value
templates.env.globals["current_timestamp"] = current_timestamp
templates.env.globals["app_version"] = APP_VERSION
templates.env.globals["app_date"] = APP_DATE


def safe_report_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "device").strip()).strip("-.")
    return cleaned.lower() or "device"


def _pdf_text(value) -> str:
    return str(value or "").strip()


def _report_rows(device, fields: list[tuple[str, str]], transforms: dict[str, object] | None = None) -> list[list[str]]:
    transforms = transforms or {}
    rows = []
    for label, key in fields:
        value = device[key] if key in device.keys() else ""
        if key in transforms:
            value = transforms[key](value)
        value = _pdf_text(value)
        if value:
            rows.append([label, value])
    return rows


def build_device_report_pdf(device, attachments) -> bytes:
    if colors is None or A4 is None:
        raise RuntimeError("ReportLab is not installed")

    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    page_width, page_height = A4
    c = canvas.Canvas(buffer, pagesize=A4, pageCompression=1)
    report_title = " ".join(part for part in [_pdf_text(device["vendor"]), _pdf_text(device["model"])] if part) or display_name(device)
    c.setTitle(f"Device Report - {report_title}")
    c.setAuthor("Outlaw's Inventory")
    c.setSubject("Device inventory report")

    margin_x = 15 * mm
    content_width = page_width - (2 * margin_x)
    navy = colors.HexColor("#17365D")
    text = colors.HexColor("#172033")
    muted = colors.HexColor("#64748B")
    border = colors.HexColor("#D8E1EC")
    table_head = colors.HexColor("#EEF3F8")
    divider = colors.HexColor("#E4EAF1")

    label_style = ParagraphStyle("report-label", fontName="Helvetica", fontSize=7.2, leading=9, textColor=navy)
    value_style = ParagraphStyle("report-value", fontName="Helvetica", fontSize=8.2, leading=10.2, textColor=text)
    note_style = ParagraphStyle("report-note", fontName="Helvetica", fontSize=8.1, leading=10.6, textColor=text)
    section_style = ParagraphStyle("report-section", fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=navy)

    def esc(value: object) -> str:
        return _pdf_text(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")

    def draw_section_icon(kind, x, y):
        """Draw small dependency-free vector icons for PDF section headings."""
        c.saveState()
        c.setStrokeColor(navy)
        c.setFillColor(colors.white)
        c.setLineWidth(0.9)
        size = 5.2 * mm
        left = x
        bottom = y - size + 0.6 * mm
        if kind == "device":
            c.roundRect(left, bottom, size, size * 0.72, 0.7 * mm, fill=0, stroke=1)
            c.circle(left + size * 0.78, bottom + size * 0.36, 0.45 * mm, fill=0, stroke=1)
            c.line(left + size * 0.18, bottom - 0.8 * mm, left + size * 0.82, bottom - 0.8 * mm)
        elif kind == "purchase":
            c.line(left + 0.4 * mm, bottom + size * 0.76, left + 1.5 * mm, bottom + size * 0.76)
            c.line(left + 1.5 * mm, bottom + size * 0.76, left + 2.2 * mm, bottom + size * 0.18)
            c.line(left + 2.2 * mm, bottom + size * 0.18, left + size * 0.86, bottom + size * 0.18)
            c.line(left + 2.3 * mm, bottom + size * 0.62, left + size * 0.92, bottom + size * 0.62)
            c.circle(left + 2.8 * mm, bottom - 0.4 * mm, 0.55 * mm, fill=0, stroke=1)
            c.circle(left + size * 0.78, bottom - 0.4 * mm, 0.55 * mm, fill=0, stroke=1)
        elif kind == "firmware":
            c.rect(left + 1.0 * mm, bottom + 1.0 * mm, size - 2.0 * mm, size - 2.0 * mm, fill=0, stroke=1)
            c.rect(left + 2.0 * mm, bottom + 2.0 * mm, size - 4.0 * mm, size - 4.0 * mm, fill=0, stroke=1)
            for i in range(4):
                off = (1.2 + i * 1.0) * mm
                c.line(left + off, bottom + size, left + off, bottom + size + 0.8 * mm)
                c.line(left + off, bottom, left + off, bottom - 0.8 * mm)
                c.line(left, bottom + off, left - 0.8 * mm, bottom + off)
                c.line(left + size, bottom + off, left + size + 0.8 * mm, bottom + off)
        elif kind == "notes":
            c.roundRect(left + 0.6 * mm, bottom + 0.4 * mm, size - 1.2 * mm, size - 0.8 * mm, 0.6 * mm, fill=0, stroke=1)
            c.line(left + 1.5 * mm, bottom + size * 0.70, left + size - 1.5 * mm, bottom + size * 0.70)
            c.line(left + 1.5 * mm, bottom + size * 0.48, left + size - 1.5 * mm, bottom + size * 0.48)
            c.line(left + 1.5 * mm, bottom + size * 0.26, left + size * 0.66, bottom + size * 0.26)
        elif kind == "attachments":
            p = c.beginPath()
            p.moveTo(left + size * 0.72, bottom + size * 0.82)
            p.curveTo(left + size * 0.98, bottom + size * 0.58, left + size * 0.86, bottom + size * 0.28, left + size * 0.64, bottom + size * 0.12)
            p.lineTo(left + size * 0.38, bottom - 0.06 * size)
            p.curveTo(left + size * 0.16, bottom - 0.20 * size, left - 0.04 * size, bottom + size * 0.06, left + size * 0.12, bottom + size * 0.25)
            p.lineTo(left + size * 0.58, bottom + size * 0.68)
            p.curveTo(left + size * 0.72, bottom + size * 0.82, left + size * 0.82, bottom + size * 0.64, left + size * 0.68, bottom + size * 0.51)
            p.lineTo(left + size * 0.30, bottom + size * 0.15)
            c.drawPath(p, fill=0, stroke=1)
        c.restoreState()

    def rounded_card(x, y_top, width, height, title_text):
        c.setFillColor(colors.white)
        c.setStrokeColor(border)
        c.setLineWidth(0.75)
        c.roundRect(x, y_top - height, width, height, 3 * mm, fill=1, stroke=1)
        icon_kind = {
            "Device details": "device",
            "Purchase & warranty": "purchase",
            "Firmware": "firmware",
            "Notes": "notes",
        }.get(title_text, "attachments" if title_text.startswith("Attachments") else "")
        title_x = x + 5 * mm
        if icon_kind:
            draw_section_icon(icon_kind, title_x, y_top - 5.2 * mm)
            title_x += 8.2 * mm
        section_para = Paragraph(esc(title_text), section_style)
        section_para.wrapOn(c, width - (title_x - x) - 5 * mm, 8 * mm)
        section_para.drawOn(c, title_x, y_top - 11 * mm)

    def measure_rows(rows, width):
        if not rows:
            return 0
        value_width = width - 34 * mm
        total = 0
        for label, value in rows:
            lp = Paragraph(esc(label), label_style)
            vp = Paragraph(esc(value), value_style)
            _, lh = lp.wrap(31 * mm, 100 * mm)
            _, vh = vp.wrap(value_width, 100 * mm)
            total += max(lh, vh) + 3.1 * mm
        return total

    def draw_rows(x, y_top, width, rows, separators=True):
        y = y_top
        value_x = x + 34 * mm
        value_width = width - 34 * mm
        for index, (label, value) in enumerate(rows):
            lp = Paragraph(esc(label), label_style)
            vp = Paragraph(esc(value), value_style)
            _, lh = lp.wrap(31 * mm, 100 * mm)
            _, vh = vp.wrap(value_width, 100 * mm)
            h = max(lh, vh)
            lp.drawOn(c, x, y - lh)
            vp.drawOn(c, value_x, y - vh)
            y -= h + 2.1 * mm
            if separators and index < len(rows) - 1:
                c.setStrokeColor(divider)
                c.setLineWidth(0.35)
                c.line(x, y, x + width, y)
                y -= 1 * mm

    # Header
    header_top = page_height - 14 * mm
    c.setFillColor(navy)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(margin_x, header_top, "Outlaw's Inventory")
    c.setFont("Helvetica", 12.5)
    c.setFillColor(muted)
    c.drawString(margin_x, header_top - 7.5 * mm, "Device Report")
    c.setFont("Helvetica", 7.4)
    c.drawRightString(page_width - margin_x, header_top, "Print date")
    c.setFillColor(navy)
    c.setFont("Helvetica", 8.3)
    c.drawRightString(page_width - margin_x, header_top - 4.5 * mm, datetime.now().strftime('%d-%m-%Y %H:%M'))
    c.setFillColor(muted)
    c.setFont("Helvetica", 7.4)
    c.drawRightString(page_width - margin_x, header_top - 10.5 * mm, "Report version")
    c.setFillColor(navy)
    c.setFont("Helvetica", 8.3)
    c.drawRightString(page_width - margin_x, header_top - 15 * mm, APP_VERSION)
    c.setStrokeColor(navy)
    c.setLineWidth(1.15)
    c.line(margin_x, header_top - 17.5 * mm, page_width - margin_x, header_top - 17.5 * mm)

    title_y = header_top - 28 * mm
    c.setFillColor(navy)
    title_size = 15.5
    while stringWidth(report_title, "Helvetica-Bold", title_size) > content_width and title_size > 10:
        title_size -= 0.5
    c.setFont("Helvetica-Bold", title_size)
    c.drawString(margin_x, title_y, report_title)

    identity = _report_rows(device, [
        ("Name", "display_name"), ("Category", "category"), ("Serial number", "serial_number"), ("Condition", "condition"),
    ])
    if not any(row[0] == "Name" for row in identity):
        identity.insert(0, ["Name", display_name(device)])
    ownership = _report_rows(device, [
        ("Purchase date", "purchase_date"), ("Purchased from", "purchased_from"), ("Purchase price", "purchase_price"),
        ("Warranty until", "warranty_until"), ("Extended warranty", "extended_warranty"),
    ], {"purchase_date": display_date, "purchase_price": format_euro, "warranty_until": display_date,
        "extended_warranty": lambda v: "Yes" if v else ""})
    firmware = _report_rows(device, [
        ("Installed firmware", "current_firmware"), ("Latest known firmware", "latest_firmware_override"),
        ("Last checked", "last_checked"), ("Source", "firmware_source"),
    ])
    if not any(row[0] == "Latest known firmware" for row in firmware):
        latest = _effective_latest_version(_pdf_text(device["latest_firmware"]), "")
        if latest:
            insert_at = next((i + 1 for i, row in enumerate(firmware) if row[0] == "Installed firmware"), len(firmware))
            firmware.insert(insert_at, ["Latest known firmware", latest])

    gap = 5 * mm
    col_width = (content_width - gap) / 2
    cards_top = title_y - 9 * mm
    identity_h = max(43 * mm, 19 * mm + measure_rows(identity, col_width - 10 * mm))
    ownership_h = max(43 * mm, 19 * mm + measure_rows(ownership, col_width - 10 * mm))
    row1_h = max(identity_h, ownership_h)
    if identity:
        rounded_card(margin_x, cards_top, col_width, row1_h, "Device details")
        draw_rows(margin_x + 5 * mm, cards_top - 17 * mm, col_width - 10 * mm, identity)
    if ownership:
        rounded_card(margin_x + col_width + gap, cards_top, col_width, row1_h, "Purchase & warranty")
        draw_rows(margin_x + col_width + gap + 5 * mm, cards_top - 17 * mm, col_width - 10 * mm, ownership)

    y = cards_top - row1_h - gap
    if firmware:
        firmware_h = max(39 * mm, 19 * mm + measure_rows(firmware, col_width - 10 * mm))
        rounded_card(margin_x, y, col_width, firmware_h, "Firmware")
        draw_rows(margin_x + 5 * mm, y - 17 * mm, col_width - 10 * mm, firmware)
        y -= firmware_h + gap

    notes = _pdf_text(device["notes"] if "notes" in device.keys() else "") or "No notes."
    note_para = Paragraph(esc(notes), note_style)
    _, note_text_h = note_para.wrap(content_width - 10 * mm, 40 * mm)
    note_h = max(25 * mm, min(48 * mm, 18 * mm + note_text_h))
    rounded_card(margin_x, y, content_width, note_h, "Notes")
    note_para.wrapOn(c, content_width - 10 * mm, note_h - 18 * mm)
    note_para.drawOn(c, margin_x + 5 * mm, y - 16 * mm - note_para.height)
    y -= note_h + gap

    attachment_rows = []
    for item in attachments[:8]:
        attachment_rows.append([
            _pdf_text(item["description"]) or "Attachment",
            _pdf_text(item["original_name"]),
            display_date(_pdf_text(item["created_at"])[:10]) if "created_at" in item.keys() else "",
        ])
    if len(attachments) > 8:
        attachment_rows.append([f"{len(attachments) - 8} additional file(s)", "", ""])
    if attachment_rows and y > 36 * mm:
        available_h = y - 23 * mm
        row_h = 6 * mm
        max_rows = max(1, min(len(attachment_rows), int((available_h - 19 * mm) / row_h)))
        rows = attachment_rows[:max_rows]
        card_h = 18 * mm + (len(rows) + 1) * row_h
        rounded_card(margin_x, y, content_width, card_h, f"Attachments ({len(attachments)})")
        data = [[Paragraph("Description", label_style), Paragraph("Filename", label_style), Paragraph("Uploaded", label_style)]]
        data += [[Paragraph(esc(a), value_style), Paragraph(esc(b), value_style), Paragraph(esc(d), value_style)] for a, b, d in rows]
        table = Table(data, colWidths=[50 * mm, content_width - 89 * mm, 29 * mm], rowHeights=row_h)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), table_head),
            ("BOX", (0, 0), (-1, -1), 0.45, border),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        table.wrapOn(c, content_width - 10 * mm, card_h - 18 * mm)
        table.drawOn(c, margin_x + 5 * mm, y - card_h + 5 * mm)

    c.setStrokeColor(navy)
    c.setLineWidth(0.8)
    c.line(margin_x, 13 * mm, page_width - margin_x, 13 * mm)
    c.setFont("Helvetica", 7)
    c.setFillColor(muted)
    c.drawString(margin_x, 8.5 * mm, f"Outlaw's Inventory {APP_VERSION}")
    c.drawRightString(page_width - margin_x, 8.5 * mm, "Page 1 of 1")
    c.save()
    return buffer.getvalue()


_database_gate = DatabaseGate()


class _DatabaseConnection(sqlite3.Connection):
    _gate_held = False

    def close(self):
        try:
            super().close()
        finally:
            if self._gate_held:
                self._gate_held = False
                _database_gate.release()

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def db() -> sqlite3.Connection:
    # Short transactions normally hold this lock; restore holds it across its
    # complete database transition. Connections never survive a with-block.
    _database_gate.acquire()
    con = None
    try:
        con = sqlite3.connect(DB_PATH, timeout=30, factory=_DatabaseConnection)
        con._gate_held = True
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.row_factory = sqlite3.Row
        return con
    except BaseException:
        if con is not None:
            con.close()
        else:
            _database_gate.release()
        raise


def _repair_multi_user_ownership(con: sqlite3.Connection) -> dict[str, int]:
    """Repair and validate ownership across all user-scoped records.

    Device children follow the device owner. SSH profiles are reassigned (or
    cloned when shared by multiple owners) so managed-host and update links
    always resolve inside the same tenant. Safe to run at every startup.
    """
    stats = {"usernames": 0, "health": 0, "updates": 0, "profiles": 0, "profile_clones": 0, "categories": 0}

    # Canonical account names are always lowercase; display_name keeps casing.
    for row in con.execute("SELECT id,username FROM users ORDER BY id").fetchall():
        canonical = (row["username"] or "").strip().lower()
        if canonical and canonical != row["username"]:
            con.execute("UPDATE users SET username=?, updated_at=? WHERE id=?", (canonical, now(), row["id"]))
            stats["usernames"] += 1

    first_user = con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    fallback_owner = int(first_user[0]) if first_user else None

    # Child checks inherit their linked device owner.
    stats["health"] += con.execute(
        """UPDATE health_checks
           SET owner_user_id=(SELECT owner_user_id FROM devices WHERE devices.id=health_checks.device_id)
           WHERE device_id IS NOT NULL AND COALESCE(owner_user_id,-1)<>COALESCE((SELECT owner_user_id FROM devices WHERE devices.id=health_checks.device_id),-1)"""
    ).rowcount
    stats["updates"] += con.execute(
        """UPDATE update_checks
           SET owner_user_id=(SELECT owner_user_id FROM devices WHERE devices.id=update_checks.device_id)
           WHERE device_id IS NOT NULL AND COALESCE(owner_user_id,-1)<>COALESCE((SELECT owner_user_id FROM devices WHERE devices.id=update_checks.device_id),-1)"""
    ).rowcount
    if fallback_owner is not None:
        stats["health"] += con.execute("UPDATE health_checks SET owner_user_id=? WHERE owner_user_id IS NULL", (fallback_owner,)).rowcount

    # Determine every owner that references each SSH profile.
    profiles = con.execute("SELECT * FROM ssh_profiles ORDER BY id").fetchall()
    for profile in profiles:
        refs = con.execute(
            """SELECT DISTINCT owner_id FROM (
                   SELECT owner_user_id AS owner_id FROM devices WHERE managed_ssh_profile_id=? AND owner_user_id IS NOT NULL
                   UNION
                   SELECT d.owner_user_id AS owner_id
                   FROM update_checks u JOIN devices d ON d.id=u.device_id
                   WHERE u.ssh_profile_id=? AND d.owner_user_id IS NOT NULL
               ) WHERE owner_id IS NOT NULL ORDER BY owner_id""",
            (profile["id"], profile["id"]),
        ).fetchall()
        owners = [int(r[0]) for r in refs]
        if not owners:
            if profile["owner_user_id"] is None and fallback_owner is not None:
                con.execute("UPDATE ssh_profiles SET owner_user_id=? WHERE id=?", (fallback_owner, profile["id"]))
                stats["profiles"] += 1
            continue
        primary = owners[0]
        if int(profile["owner_user_id"] or 0) != primary:
            con.execute("UPDATE ssh_profiles SET owner_user_id=? WHERE id=?", (primary, profile["id"]))
            stats["profiles"] += 1
        # A profile cannot safely span tenants. Clone it for every extra owner.
        for owner in owners[1:]:
            base_name = str(profile["name"])
            candidate = f"{base_name} ({owner})"
            suffix = 2
            while con.execute("SELECT 1 FROM ssh_profiles WHERE name=?", (candidate,)).fetchone():
                candidate = f"{base_name} ({owner}-{suffix})"; suffix += 1
            cur = con.execute(
                """INSERT INTO ssh_profiles(owner_user_id,name,username,port,private_key_path,known_host_fingerprint,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (owner,candidate,profile["username"],profile["port"],profile["private_key_path"],profile["known_host_fingerprint"],now(),now()),
            )
            clone_id = int(cur.lastrowid)
            con.execute("UPDATE devices SET managed_ssh_profile_id=? WHERE managed_ssh_profile_id=? AND owner_user_id=?", (clone_id, profile["id"], owner))
            con.execute("""UPDATE update_checks SET ssh_profile_id=?, owner_user_id=?
                           WHERE ssh_profile_id=? AND device_id IN (SELECT id FROM devices WHERE owner_user_id=?)""",
                        (clone_id, owner, profile["id"], owner))
            stats["profile_clones"] += 1

    # Update checks without a linked device follow their profile owner.
    stats["updates"] += con.execute(
        """UPDATE update_checks
           SET owner_user_id=(SELECT owner_user_id FROM ssh_profiles WHERE ssh_profiles.id=update_checks.ssh_profile_id)
           WHERE device_id IS NULL AND COALESCE(owner_user_id,-1)<>COALESCE((SELECT owner_user_id FROM ssh_profiles WHERE ssh_profiles.id=update_checks.ssh_profile_id),-1)"""
    ).rowcount

    # Ensure each device category exists for its owner.
    for row in con.execute("SELECT DISTINCT owner_user_id,category FROM devices WHERE owner_user_id IS NOT NULL AND TRIM(COALESCE(category,''))<>''").fetchall():
        before = con.total_changes
        con.execute("""INSERT OR IGNORE INTO categories(owner_user_id,name,show_ownership,show_firmware,show_network,show_health,show_updates,show_system_checks)
                       VALUES (?,?,1,1,0,0,0,0)""", (row["owner_user_id"], row["category"]))
        if con.total_changes > before: stats["categories"] += 1

    # Hard integrity checks: no cross-owner device/profile/check links may remain.
    mismatches = int(con.execute("""SELECT COUNT(*) FROM update_checks u
        LEFT JOIN devices d ON d.id=u.device_id
        LEFT JOIN ssh_profiles s ON s.id=u.ssh_profile_id
        WHERE u.owner_user_id IS NULL OR s.id IS NULL
           OR (d.id IS NOT NULL AND u.owner_user_id<>d.owner_user_id)
           OR u.owner_user_id<>s.owner_user_id""").fetchone()[0])
    managed_mismatches = int(con.execute("""SELECT COUNT(*) FROM devices d JOIN ssh_profiles s ON s.id=d.managed_ssh_profile_id
        WHERE d.owner_user_id<>s.owner_user_id""").fetchone()[0])
    health_mismatches = int(con.execute("""SELECT COUNT(*) FROM health_checks h JOIN devices d ON d.id=h.device_id
        WHERE h.owner_user_id<>d.owner_user_id""").fetchone()[0])
    if mismatches or managed_mismatches or health_mismatches:
        raise RuntimeError(f"Ownership integrity audit failed: updates={mismatches}, managed_profiles={managed_mismatches}, health={health_mismatches}")

    con.execute("INSERT INTO settings(key,value) VALUES('ownership_audit_v0831',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps({**stats,"checked_at":now()}, sort_keys=True),))
    return stats

def _data_integrity_report(con: sqlite3.Connection) -> dict[str, object]:
    checks: dict[str, int] = {}
    checks["sqlite_integrity_errors"] = 0 if con.execute("PRAGMA integrity_check").fetchone()[0] == "ok" else 1
    checks["foreign_key_violations"] = len(con.execute("PRAGMA foreign_key_check").fetchall())
    checks["orphan_devices"] = int(con.execute("SELECT COUNT(*) FROM devices d LEFT JOIN users u ON u.id=d.owner_user_id WHERE u.id IS NULL").fetchone()[0])
    checks["orphan_categories"] = int(con.execute("SELECT COUNT(*) FROM categories c LEFT JOIN users u ON u.id=c.owner_user_id WHERE u.id IS NULL").fetchone()[0])
    checks["orphan_ssh_profiles"] = int(con.execute("SELECT COUNT(*) FROM ssh_profiles s LEFT JOIN users u ON u.id=s.owner_user_id WHERE u.id IS NULL").fetchone()[0])
    checks["orphan_attachments"] = int(con.execute("SELECT COUNT(*) FROM attachments a LEFT JOIN devices d ON d.id=a.device_id WHERE d.id IS NULL").fetchone()[0])
    checks["orphan_auth_sessions"] = int(con.execute("SELECT COUNT(*) FROM auth_sessions s LEFT JOIN users u ON u.id=s.user_id WHERE u.id IS NULL").fetchone()[0])
    checks["device_category_mismatches"] = int(con.execute("SELECT COUNT(*) FROM devices d LEFT JOIN categories c ON c.owner_user_id=d.owner_user_id AND lower(trim(c.name))=lower(trim(d.category)) WHERE d.owner_user_id IS NOT NULL AND trim(coalesce(d.category,''))<>'' AND c.id IS NULL").fetchone()[0])
    checks["orphan_attachments"] = int(con.execute("SELECT COUNT(*) FROM attachments a LEFT JOIN devices d ON d.id=a.device_id WHERE d.id IS NULL").fetchone()[0])
    checks["health_owner_mismatches"] = int(con.execute("SELECT COUNT(*) FROM health_checks h LEFT JOIN devices d ON d.id=h.device_id WHERE h.owner_user_id IS NULL OR (d.id IS NOT NULL AND h.owner_user_id<>d.owner_user_id)").fetchone()[0])
    checks["update_owner_mismatches"] = int(con.execute("SELECT COUNT(*) FROM update_checks u LEFT JOIN devices d ON d.id=u.device_id LEFT JOIN ssh_profiles s ON s.id=u.ssh_profile_id WHERE u.owner_user_id IS NULL OR s.id IS NULL OR u.owner_user_id<>s.owner_user_id OR (d.id IS NOT NULL AND u.owner_user_id<>d.owner_user_id)").fetchone()[0])
    checks["managed_profile_mismatches"] = int(con.execute("SELECT COUNT(*) FROM devices d LEFT JOIN ssh_profiles s ON s.id=d.managed_ssh_profile_id WHERE d.managed_ssh_profile_id IS NOT NULL AND (s.id IS NULL OR d.owner_user_id<>s.owner_user_id)").fetchone()[0])
    checks["duplicate_usernames_casefolded"] = int(con.execute("SELECT COUNT(*) FROM (SELECT lower(username) n,COUNT(*) c FROM users GROUP BY lower(username) HAVING c>1)").fetchone()[0])
    checks["duplicate_profile_names_per_owner"] = int(con.execute("SELECT COUNT(*) FROM (SELECT owner_user_id,lower(name),COUNT(*) c FROM ssh_profiles GROUP BY owner_user_id,lower(name) HAVING c>1)").fetchone()[0])
    total = sum(checks.values())
    return {"ok": total == 0, "issues": total, "checks": checks, "checked_at": now()}

def _repair_and_audit_integrity(con: sqlite3.Connection) -> dict[str, object]:
    if not con.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        report = {"ok": True, "issues": 0, "checks": {}, "checked_at": now(), "status": "pending_admin_setup"}
        con.execute("INSERT INTO settings(key,value) VALUES('data_integrity_report',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(report,sort_keys=True),))
        return report
    _repair_multi_user_ownership(con)
    # Normalize usernames while preserving free-form display names.
    for row in con.execute("SELECT id,username FROM users").fetchall():
        normalized = str(row["username"] or "").strip().lower()
        if normalized and normalized != row["username"]:
            conflict = con.execute("SELECT 1 FROM users WHERE lower(username)=? AND id<>?", (normalized,row["id"])).fetchone()
            if not conflict:
                con.execute("UPDATE users SET username=? WHERE id=?", (normalized,row["id"]))
    report = _data_integrity_report(con)
    con.execute("INSERT INTO settings(key,value) VALUES('data_integrity_report',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(report,sort_keys=True),))
    if not report["ok"]:
        raise RuntimeError(f"Data integrity audit failed with {report['issues']} issue(s)")
    return report

def init_db() -> None:
    with db() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                category TEXT DEFAULT 'Other',
                vendor TEXT DEFAULT '',
                model TEXT DEFAULT '',
                serial_number TEXT DEFAULT '',
                hostname TEXT DEFAULT '',
                ipv4_address TEXT DEFAULT '',
                ipv6_address TEXT DEFAULT '',
                mac_address TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                lifecycle TEXT DEFAULT 'Supported',
                purchase_date TEXT DEFAULT '',
                purchased_from TEXT DEFAULT '',
                purchase_price TEXT DEFAULT '',
                condition TEXT DEFAULT '',
                warranty_status TEXT DEFAULT '',
                warranty_until TEXT DEFAULT '',
                extended_warranty INTEGER DEFAULT 0,
                current_firmware TEXT DEFAULT '',
                latest_firmware TEXT DEFAULT '',
                firmware_url TEXT DEFAULT '',
                firmware_lookup TEXT DEFAULT '',
                firmware_provider TEXT DEFAULT 'Auto',
                firmware_identifier TEXT DEFAULT '',
                latest_firmware_override TEXT DEFAULT '',
                firmware_source TEXT DEFAULT 'Unknown',
                check_method TEXT DEFAULT 'Not configured',
                release_date TEXT DEFAULT '',
                release_summary TEXT DEFAULT '',
                release_notes_url TEXT DEFAULT '',
                confidence TEXT DEFAULT 'Unknown',
                auto_check INTEGER DEFAULT 1,
                status TEXT DEFAULT 'unknown',
                last_checked TEXT DEFAULT '',
                last_firmware_update TEXT DEFAULT '',
                deferred_version TEXT DEFAULT '',
                deferred_reason TEXT DEFAULT '',
                deferred_until TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                managed_host INTEGER DEFAULT 0,
                managed_ssh_profile_id INTEGER,
                managed_system_type TEXT DEFAULT 'debian',
                integration_status TEXT DEFAULT 'not_configured',
                system_uptime_seconds INTEGER DEFAULT 0,
                last_boot TEXT DEFAULT '',
                uptime_last_checked TEXT DEFAULT '',
                integration_checked_at TEXT DEFAULT '',
                integration_message TEXT DEFAULT '',
                integration_details TEXT DEFAULT '{}',
                virtual_device INTEGER DEFAULT 0,
                detected_platform TEXT DEFAULT '',
                owner_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS health_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                owner_user_id INTEGER,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                check_type TEXT DEFAULT 'ping',
                url TEXT DEFAULT '',
                interval_minutes INTEGER DEFAULT 10,
                enabled INTEGER DEFAULT 1,
                status TEXT DEFAULT 'unknown',
                response_ms INTEGER DEFAULT 0,
                last_checked TEXT DEFAULT '',
                last_online TEXT DEFAULT '',
                last_error TEXT DEFAULT '',
                maintenance INTEGER DEFAULT 0,
                disk_usage_percent INTEGER DEFAULT 0,
                disk_usage_details TEXT DEFAULT '',
                group_key TEXT DEFAULT '',
                disk_warning_percent INTEGER,
                disk_critical_percent INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE SET NULL
            )
            """
        )
        con.execute("""
            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT 'info',
                summary TEXT DEFAULT '',
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_activity_history_device ON activity_history(owner_user_id, device_id, id DESC)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                is_active INTEGER NOT NULL DEFAULT 1,
                mfa_enabled INTEGER NOT NULL DEFAULT 0,
                totp_secret TEXT DEFAULT '',
                recovery_codes_hash TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                avatar_filename TEXT DEFAULT '',
                avatar_updated_at TEXT DEFAULT '',
                must_change_password INTEGER NOT NULL DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                remember_me INTEGER NOT NULL DEFAULT 0,
                user_agent TEXT DEFAULT '',
                remote_address TEXT DEFAULT '',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_token_hash ON auth_sessions(token_hash)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS trusted_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                user_agent TEXT DEFAULT '',
                remote_address TEXT DEFAULT '',
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_trusted_devices_token_hash ON trusted_devices(token_hash)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_trusted_devices_user_id ON trusted_devices(user_id)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS mfa_login_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                next_url TEXT NOT NULL DEFAULT '/',
                remember_me INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                user_agent TEXT DEFAULT '',
                remote_address TEXT DEFAULT '',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mfa_login_challenges_token_hash ON mfa_login_challenges(token_hash)")
        con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_devices_owner_user_id ON devices(owner_user_id)")
        con.execute("""
            CREATE TABLE IF NOT EXISTS notification_state (
                user_id INTEGER NOT NULL,
                event_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, event_key),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_notification_state_user_active ON notification_state(user_id, active)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduler_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'running',
                details TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_scheduler_runs_job_started ON scheduler_runs(job_name, started_at DESC)")
        con.execute("""CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER,
            name TEXT NOT NULL COLLATE NOCASE,
            show_ownership INTEGER NOT NULL DEFAULT 1,
            show_firmware INTEGER NOT NULL DEFAULT 1,
            show_network INTEGER NOT NULL DEFAULT 0,
            show_health INTEGER NOT NULL DEFAULT 0,
            show_updates INTEGER NOT NULL DEFAULT 0,
            show_system_checks INTEGER NOT NULL DEFAULT 0,
            UNIQUE(owner_user_id, name)
        )""")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ssh_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_user_id INTEGER,
                name TEXT NOT NULL COLLATE NOCASE,
                username TEXT NOT NULL DEFAULT 'outlaw',
                port INTEGER NOT NULL DEFAULT 22,
                private_key_path TEXT NOT NULL DEFAULT '',
                known_host_fingerprint TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(owner_user_id, name)
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_ssh_profiles_owner_user_id ON ssh_profiles(owner_user_id)")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS update_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER,
                owner_user_id INTEGER,
                ssh_profile_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                system_type TEXT NOT NULL DEFAULT 'debian',
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                package_count INTEGER NOT NULL DEFAULT 0,
                packages_json TEXT NOT NULL DEFAULT '[]',
                last_checked TEXT DEFAULT '',
                last_error TEXT DEFAULT '',
                minecraft_jar_path TEXT DEFAULT 'server.jar',
                last_upgrade TEXT DEFAULT '',
                upgrade_status TEXT DEFAULT '',
                upgrade_output TEXT DEFAULT '',
                reboot_required INTEGER DEFAULT 0,
                reboot_reason TEXT DEFAULT '',
                last_reboot TEXT DEFAULT '',
                reboot_status TEXT DEFAULT '',
                reboot_output TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE SET NULL,
                FOREIGN KEY(ssh_profile_id) REFERENCES ssh_profiles(id) ON DELETE RESTRICT
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS application_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                owner_user_id INTEGER NOT NULL,
                ssh_profile_id INTEGER NOT NULL,
                application_type TEXT NOT NULL DEFAULT 'pihole',
                enabled INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'unknown',
                details_json TEXT NOT NULL DEFAULT '{}',
                last_checked TEXT DEFAULT '',
                last_error TEXT DEFAULT '',
                last_update TEXT DEFAULT '',
                update_status TEXT DEFAULT '',
                update_output TEXT DEFAULT '',
                minecraft_jar_path TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(ssh_profile_id) REFERENCES ssh_profiles(id) ON DELETE RESTRICT,
                UNIQUE(device_id, application_type)
            )
            """
        )
        # Seed defaults only for a new installation. Afterwards categories are
        # fully user-managed, so a renamed built-in category is not recreated.
        if con.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            section_defaults = {
                "Camera": (1,1,0,0,0), "Lens": (1,0,0,0,0), "Drone": (1,1,0,0,0),
                "3D Printer": (1,1,1,1,1), "Printer": (1,1,1,1,0),
                "Server": (0,0,1,1,1), "Computer": (1,1,1,1,1), "Network": (0,1,1,1,1),
                "Smart Home": (1,1,1,1,0), "Vehicle": (1,0,0,0,0), "Audio": (1,1,0,0,0),
                "Other": (1,1,0,0,0),
            }
            for cat in DEFAULT_CATEGORIES:
                flags = section_defaults.get(cat, (1,1,0,0,0))
                system_checks = 1 if flags[3] or flags[4] else 0
                con.execute("INSERT INTO categories(owner_user_id,name,show_ownership,show_firmware,show_network,show_health,show_updates,show_system_checks) VALUES (NULL,?,?,?,?,?,?,?)", (cat, *flags, system_checks))
        first_user = con.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
        if first_user:
            owner = int(first_user[0])
            con.execute("UPDATE devices SET owner_user_id=? WHERE owner_user_id IS NULL", (owner,))
            con.execute("UPDATE categories SET owner_user_id=? WHERE owner_user_id IS NULL", (owner,))
            con.execute("UPDATE ssh_profiles SET owner_user_id=? WHERE owner_user_id IS NULL", (owner,))

        # v0.16.3: seed the generic history once from meaningful action state
        # already present in the v0.15.x database. Periodic checks are excluded.
        con.execute("""
            INSERT INTO activity_history(device_id,owner_user_id,event_type,title,result,summary,details,created_at)
            SELECT u.device_id,u.owner_user_id,'system_upgrade','System Upgrade',
                   CASE WHEN u.upgrade_status='success' THEN 'success' ELSE 'failed' END,
                   'Historical system upgrade.',COALESCE(u.upgrade_output,''),u.last_upgrade
            FROM update_checks u
            WHERE u.device_id IS NOT NULL AND COALESCE(u.last_upgrade,'')<>''
              AND NOT EXISTS (SELECT 1 FROM activity_history h WHERE h.device_id=u.device_id AND h.owner_user_id=u.owner_user_id AND h.event_type='system_upgrade' AND h.created_at=u.last_upgrade)
        """)
        con.execute("""
            INSERT INTO activity_history(device_id,owner_user_id,event_type,title,result,summary,details,created_at)
            SELECT u.device_id,u.owner_user_id,'reboot','Reboot',
                   CASE WHEN u.reboot_status='success' THEN 'success' ELSE 'failed' END,
                   'Historical reboot.',COALESCE(u.reboot_output,''),u.last_reboot
            FROM update_checks u
            WHERE u.device_id IS NOT NULL AND COALESCE(u.last_reboot,'')<>''
              AND NOT EXISTS (SELECT 1 FROM activity_history h WHERE h.device_id=u.device_id AND h.owner_user_id=u.owner_user_id AND h.event_type='reboot' AND h.created_at=u.last_reboot)
        """)
        con.execute("""
            INSERT INTO activity_history(device_id,owner_user_id,event_type,title,result,summary,details,created_at)
            SELECT a.device_id,a.owner_user_id,a.application_type || '_update',
                   CASE WHEN lower(a.application_type)='minecraft' THEN 'Minecraft Update' ELSE 'Pi-hole Update' END,
                   CASE WHEN a.update_status='success' THEN 'success' ELSE 'failed' END,
                   'Historical application update.',COALESCE(a.update_output,''),a.last_update
            FROM application_checks a
            WHERE COALESCE(a.last_update,'')<>''
              AND lower(a.application_type) IN ('minecraft','pihole')
              AND NOT EXISTS (SELECT 1 FROM activity_history h WHERE h.device_id=a.device_id AND h.owner_user_id=a.owner_user_id AND h.event_type=a.application_type || '_update' AND h.created_at=a.last_update)
        """)
        con.execute("""
            INSERT INTO activity_history(device_id,owner_user_id,event_type,title,result,summary,details,created_at)
            SELECT d.id,d.owner_user_id,'firmware_update','Firmware Update','success',
                   CASE WHEN COALESCE(d.current_firmware,'')<>'' THEN 'Marked updated to ' || d.current_firmware || '.' ELSE 'Firmware update marked completed.' END,
                   '',d.last_firmware_update
            FROM devices d
            WHERE d.owner_user_id IS NOT NULL AND COALESCE(d.last_firmware_update,'')<>''
              AND NOT EXISTS (SELECT 1 FROM activity_history h WHERE h.device_id=d.id AND h.owner_user_id=d.owner_user_id AND h.event_type='firmware_update' AND h.created_at=d.last_firmware_update)
        """)

        # Tenant-performance indexes and ownership guard rails.
        for statement in (
            "CREATE INDEX IF NOT EXISTS idx_categories_owner_name ON categories(owner_user_id, name)",
            "CREATE INDEX IF NOT EXISTS idx_ssh_profiles_owner_name ON ssh_profiles(owner_user_id, name)",
            "CREATE INDEX IF NOT EXISTS idx_attachments_device_id ON attachments(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_health_checks_owner_user_id ON health_checks(owner_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_health_checks_device_id ON health_checks(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_update_checks_owner_user_id ON update_checks(owner_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_update_checks_device_id ON update_checks(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_update_checks_ssh_profile_id ON update_checks(ssh_profile_id)",
            "CREATE INDEX IF NOT EXISTS idx_application_checks_owner_user_id ON application_checks(owner_user_id)",
            "CREATE INDEX IF NOT EXISTS idx_application_checks_device_id ON application_checks(device_id)",
            "CREATE INDEX IF NOT EXISTS idx_application_checks_ssh_profile_id ON application_checks(ssh_profile_id)",
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)",
        ):
            con.execute(statement)
        con.executescript("""
        CREATE TRIGGER IF NOT EXISTS trg_devices_owner_required_insert
        BEFORE INSERT ON devices WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_user_id))
        BEGIN SELECT RAISE(ABORT,'invalid device owner'); END;
        CREATE TRIGGER IF NOT EXISTS trg_devices_owner_required_update
        BEFORE UPDATE OF owner_user_id ON devices WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_user_id))
        BEGIN SELECT RAISE(ABORT,'invalid device owner'); END;
        CREATE TRIGGER IF NOT EXISTS trg_categories_owner_required_insert
        BEFORE INSERT ON categories WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_user_id))
        BEGIN SELECT RAISE(ABORT,'invalid category owner'); END;
        CREATE TRIGGER IF NOT EXISTS trg_ssh_owner_required_insert
        BEFORE INSERT ON ssh_profiles WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NOT EXISTS(SELECT 1 FROM users WHERE id=NEW.owner_user_id))
        BEGIN SELECT RAISE(ABORT,'invalid SSH profile owner'); END;
        CREATE TRIGGER IF NOT EXISTS trg_health_owner_match_insert
        BEFORE INSERT ON health_checks WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR (NEW.device_id IS NOT NULL AND NEW.owner_user_id<>(SELECT owner_user_id FROM devices WHERE id=NEW.device_id)))
        BEGIN SELECT RAISE(ABORT,'health ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_health_owner_match_update
        BEFORE UPDATE OF owner_user_id,device_id ON health_checks WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR (NEW.device_id IS NOT NULL AND NEW.owner_user_id<>(SELECT owner_user_id FROM devices WHERE id=NEW.device_id)))
        BEGIN SELECT RAISE(ABORT,'health ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_update_owner_match_insert
        BEFORE INSERT ON update_checks WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NEW.owner_user_id<>(SELECT owner_user_id FROM ssh_profiles WHERE id=NEW.ssh_profile_id) OR (NEW.device_id IS NOT NULL AND NEW.owner_user_id<>(SELECT owner_user_id FROM devices WHERE id=NEW.device_id)))
        BEGIN SELECT RAISE(ABORT,'update ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_update_owner_match_update
        BEFORE UPDATE OF owner_user_id,device_id,ssh_profile_id ON update_checks WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NEW.owner_user_id<>(SELECT owner_user_id FROM ssh_profiles WHERE id=NEW.ssh_profile_id) OR (NEW.device_id IS NOT NULL AND NEW.owner_user_id<>(SELECT owner_user_id FROM devices WHERE id=NEW.device_id)))
        BEGIN SELECT RAISE(ABORT,'update ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_application_check_owner_match_insert
        BEFORE INSERT ON application_checks WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NEW.owner_user_id<>(SELECT owner_user_id FROM ssh_profiles WHERE id=NEW.ssh_profile_id) OR NEW.owner_user_id<>(SELECT owner_user_id FROM devices WHERE id=NEW.device_id))
        BEGIN SELECT RAISE(ABORT,'application check ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_application_check_owner_match_update
        BEFORE UPDATE OF owner_user_id,device_id,ssh_profile_id ON application_checks WHEN EXISTS(SELECT 1 FROM users) AND (NEW.owner_user_id IS NULL OR NEW.owner_user_id<>(SELECT owner_user_id FROM ssh_profiles WHERE id=NEW.ssh_profile_id) OR NEW.owner_user_id<>(SELECT owner_user_id FROM devices WHERE id=NEW.device_id))
        BEGIN SELECT RAISE(ABORT,'application check ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_managed_profile_owner_insert
        BEFORE INSERT ON devices WHEN EXISTS(SELECT 1 FROM users) AND NEW.managed_ssh_profile_id IS NOT NULL AND NEW.owner_user_id<>(SELECT owner_user_id FROM ssh_profiles WHERE id=NEW.managed_ssh_profile_id)
        BEGIN SELECT RAISE(ABORT,'managed SSH profile ownership mismatch'); END;
        CREATE TRIGGER IF NOT EXISTS trg_managed_profile_owner_update
        BEFORE UPDATE OF managed_ssh_profile_id,owner_user_id ON devices WHEN EXISTS(SELECT 1 FROM users) AND NEW.managed_ssh_profile_id IS NOT NULL AND NEW.owner_user_id<>(SELECT owner_user_id FROM ssh_profiles WHERE id=NEW.managed_ssh_profile_id)
        BEGIN SELECT RAISE(ABORT,'managed SSH profile ownership mismatch'); END;
        """)

        defaults = {
            "daily_check_time": "03:00",
            "daily_checks_last_successful_run": "",
            "health_last_successful_run": "",
            "dashboard_refresh_minutes": "5",
            "default_health_check_interval_minutes": "10",
            "disk_usage_warning_percent": "85",
            "disk_usage_critical_percent": "95",
            "firmware_checks_enabled": "true",
            "system_update_checks_enabled": "true",
            "system_update_check_interval_hours": "24",
            "system_update_last_auto_check": "",
            "maintenance_check_interval_hours": "24",
            "maintenance_last_auto_check": "",
            "language": "en",
                "application_update_repository": APPLICATION_UPDATE_REPOSITORY,
            "application_update_channel": "production",
            "application_update_last_checked": "",
            "application_update_latest_version": "",
            "application_update_latest_tag": "",
            "application_update_release_name": "",
            "application_update_release_notes": "",
            "application_update_release_prerelease": "0",
            "application_update_zip_asset_id": "",
            "application_update_checksum_asset_id": "",
            "device_profiles_last_checked": "",
            "device_profiles_last_updated": "",
            "device_profiles_last_attempt": "",
            "device_profiles_catalog_version": "0",
            "device_profiles_installed_count": "0",
            "device_profiles_last_update_count": "0",
            "device_profiles_last_error": "",
            "notifications_enabled": "false",
            "notification_health_enabled": "true",
            "notification_firmware_enabled": "true",
            "notification_updates_enabled": "true",
            "notification_application_enabled": "true",
            "smtp_host": "",
            "smtp_port": "587",
            "smtp_encryption": "starttls",
            "smtp_username": "",
            "smtp_sender_name": "Outlaw's Inventory",
            "smtp_sender_address": "",
            "smtp_recipient_address": "",
            "application_base_url": "",
            "automatic_backup_schedule": "disabled",
            "automatic_backup_retention": "10",
            "automatic_backup_time": "02:00",
            "automatic_backup_last_run": "",
            "authentication_session_timeout_minutes": "30",
            "authentication_remember_me_enabled": "1",
        }
        for key, value in defaults.items():
            con.execute("INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, value))
        con.execute("UPDATE settings SET value=? WHERE key='application_update_repository' AND (value IS NULL OR trim(value)='')", (APPLICATION_UPDATE_REPOSITORY,))
        # v0.8.69 establishes the supported pre-release database baseline.
        con.execute("""CREATE TABLE IF NOT EXISTS schema_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        con.execute(
            "INSERT INTO schema_metadata(key,value,updated_at) VALUES('baseline_version',?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (DATABASE_SCHEMA_VERSION, now()),
        )
        _repair_and_audit_integrity(con)


_health_scheduler_stop = threading.Event()
_health_scheduler_thread: threading.Thread | None = None
_health_scheduler_lock = threading.Lock()
_update_scheduler_lock = threading.Lock()
_backup_lock = threading.Lock()
_backup_inspection_cache_lock = threading.Lock()
_notification_dispatch_lock = threading.Lock()


@app.on_event("startup")
def startup() -> None:
    global _health_scheduler_thread
    init_db()
    normalize_runtime_data_permissions()
    _health_scheduler_stop.clear()
    threading.Thread(target=_warm_backup_inspection_cache, name="backup-inspection-cache", daemon=True).start()
    # Scheduled checks wait for the next configured clock boundary.
    # This prevents a restart from shifting all future run times.
    if not _health_scheduler_thread or not _health_scheduler_thread.is_alive():
        _health_scheduler_thread = threading.Thread(
            target=health_scheduler_loop,
            name="health-check-scheduler",
            daemon=True,
        )
        _health_scheduler_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    _health_scheduler_stop.set()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def get_settings() -> dict[str, str]:
    with db() as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
SESSION_COOKIE = "outlaws_session"
MFA_CHALLENGE_COOKIE = "outlaws_mfa_challenge"
TRUSTED_DEVICE_COOKIE = "outlaws_trusted_device"
MFA_ISSUER = "Outlaw's Inventory"
_login_attempts: dict[str, list[float]] = {}


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _users_exist() -> bool:
    with db() as con:
        return bool(con.execute("SELECT 1 FROM users LIMIT 1").fetchone())


def _request_is_https(request: Request) -> bool:
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def _set_session_cookie(response: Response, request: Request, token: str, max_age: int | None = None) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=_request_is_https(request),
        samesite="strict",
        path="/",
    )


def _delete_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=_request_is_https(request), httponly=True, samesite="strict")


def _session_user(request: Request) -> sqlite3.Row | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    token_hash = _hash_session_token(token)
    current = datetime.now()
    with db() as con:
        row = con.execute("""
            SELECT u.*, s.id AS session_id, s.csrf_token, s.expires_at, s.last_seen_at
            FROM auth_sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND u.is_active=1
        """, (token_hash,)).fetchone()
        if not row:
            return None
        try:
            if datetime.fromisoformat(row["expires_at"]) <= current:
                con.execute("DELETE FROM auth_sessions WHERE id=?", (row["session_id"],))
                return None
        except Exception:
            con.execute("DELETE FROM auth_sessions WHERE id=?", (row["session_id"],))
            return None
        try:
            last_seen = datetime.fromisoformat(row["last_seen_at"])
        except Exception:
            last_seen = current - timedelta(minutes=10)
        if (current - last_seen).total_seconds() >= 60:
            settings = get_settings()
            timeout = max(5, min(1440, int(settings.get("authentication_session_timeout_minutes", "30") or 30)))
            remember = con.execute("SELECT remember_me FROM auth_sessions WHERE id=?", (row["session_id"],)).fetchone()[0]
            expires = current + (timedelta(days=30) if remember else timedelta(minutes=timeout))
            con.execute("UPDATE auth_sessions SET last_seen_at=?, expires_at=? WHERE id=?", (current.isoformat(), expires.isoformat(), row["session_id"]))
        return row


def _create_session(request: Request, user_id: int, remember_me: bool) -> tuple[str, int | None]:
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    created = datetime.now()
    settings = get_settings()
    timeout = max(5, min(1440, int(settings.get("authentication_session_timeout_minutes", "30") or 30)))
    expires = created + (timedelta(days=30) if remember_me else timedelta(minutes=timeout))
    with db() as con:
        con.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (created.isoformat(),))
        con.execute("""INSERT INTO auth_sessions(user_id,token_hash,csrf_token,created_at,last_seen_at,expires_at,remember_me,user_agent,remote_address)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (user_id,_hash_session_token(raw_token),csrf_token,created.isoformat(),created.isoformat(),expires.isoformat(),1 if remember_me else 0,
                     (request.headers.get("user-agent") or "")[:500], request.client.host if request.client else ""))
    return raw_token, (30*24*3600 if remember_me else None)


def _safe_next_url(value: str | None) -> str:
    value = (value or "").strip()
    return value if value.startswith("/") and not value.startswith("//") and "\\" not in value and not any(ord(c) < 32 for c in value) else "/"


def _auth_settings() -> dict[str, object]:
    settings = get_settings()
    try:
        timeout = int(settings.get("authentication_session_timeout_minutes", "30"))
    except Exception:
        timeout = 30
    return {"session_timeout_minutes": str(timeout if timeout in {15,30,60,240,480,1440} else 30),
            "remember_me_enabled": settings.get("authentication_remember_me_enabled", "1") == "1",
            "require_mfa_admins": settings.get("authentication_require_mfa_admins", "0") == "1"}



def _set_trusted_device_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(TRUSTED_DEVICE_COOKIE, token, max_age=30*24*3600, httponly=True, secure=_request_is_https(request), samesite="strict", path="/")


def _delete_trusted_device_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(TRUSTED_DEVICE_COOKIE, path="/", secure=_request_is_https(request), httponly=True, samesite="strict")


def _create_trusted_device(request: Request, user_id: int) -> str:
    raw = secrets.token_urlsafe(48)
    created = datetime.now()
    expires = created + timedelta(days=30)
    with db() as con:
        con.execute("DELETE FROM trusted_devices WHERE expires_at<=?", (created.isoformat(),))
        con.execute("""INSERT INTO trusted_devices(user_id,token_hash,created_at,last_used_at,expires_at,user_agent,remote_address)
                       VALUES(?,?,?,?,?,?,?)""", (user_id,_hash_session_token(raw),created.isoformat(),created.isoformat(),expires.isoformat(),
                       (request.headers.get("user-agent") or "")[:500],request.client.host if request.client else ""))
    return raw


def _trusted_device_for_user(request: Request, user_id: int) -> sqlite3.Row | None:
    raw = request.cookies.get(TRUSTED_DEVICE_COOKIE, "")
    if not raw:
        return None
    current = datetime.now()
    with db() as con:
        row = con.execute("SELECT * FROM trusted_devices WHERE token_hash=? AND user_id=?", (_hash_session_token(raw), user_id)).fetchone()
        if not row:
            return None
        try:
            if datetime.fromisoformat(row["expires_at"]) <= current:
                con.execute("DELETE FROM trusted_devices WHERE id=?", (row["id"],))
                return None
        except Exception:
            con.execute("DELETE FROM trusted_devices WHERE id=?", (row["id"],))
            return None
        con.execute("UPDATE trusted_devices SET last_used_at=? WHERE id=?", (current.isoformat(), row["id"]))
        return row


def _client_label(user_agent: str) -> str:
    ua = user_agent or ""
    browser = "Safari" if "Safari/" in ua and "Chrome/" not in ua and "Chromium/" not in ua else "Edge" if "Edg/" in ua else "Chrome" if "Chrome/" in ua else "Firefox" if "Firefox/" in ua else "Browser"
    platform = "iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Mac" if "Macintosh" in ua else "Windows" if "Windows" in ua else "Android" if "Android" in ua else "Linux" if "Linux" in ua else "Device"
    return f"{platform} · {browser}"


def _account_security_data(user_id: int, current_session_id: int) -> tuple[list[dict], list[dict]]:
    current = datetime.now().isoformat()
    with db() as con:
        con.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (current,))
        con.execute("DELETE FROM trusted_devices WHERE expires_at<=?", (current,))
        sessions = con.execute("SELECT * FROM auth_sessions WHERE user_id=? ORDER BY last_seen_at DESC", (user_id,)).fetchall()
        devices = con.execute("SELECT * FROM trusted_devices WHERE user_id=? ORDER BY last_used_at DESC", (user_id,)).fetchall()
    return ([{**dict(r),"label":_client_label(r["user_agent"]),"is_current":int(r["id"])==int(current_session_id)} for r in sessions],
            [{**dict(r),"label":_client_label(r["user_agent"])} for r in devices])


def _set_mfa_challenge_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(MFA_CHALLENGE_COOKIE, token, max_age=600, httponly=True, secure=_request_is_https(request), samesite="strict", path="/")


def _delete_mfa_challenge_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(MFA_CHALLENGE_COOKIE, path="/", secure=_request_is_https(request), httponly=True, samesite="strict")


def _create_mfa_challenge(request: Request, user_id: int, next_url: str, remember_me: bool) -> str:
    raw = secrets.token_urlsafe(48)
    created = datetime.now()
    expires = created + timedelta(minutes=10)
    with db() as con:
        con.execute("DELETE FROM mfa_login_challenges WHERE expires_at<=?", (created.isoformat(),))
        con.execute("""INSERT INTO mfa_login_challenges(user_id,token_hash,next_url,remember_me,created_at,expires_at,user_agent,remote_address)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (user_id,_hash_session_token(raw),_safe_next_url(next_url),1 if remember_me else 0,created.isoformat(),expires.isoformat(),
                     (request.headers.get("user-agent") or "")[:500],request.client.host if request.client else ""))
    return raw


def _get_mfa_challenge(request: Request) -> sqlite3.Row | None:
    raw = request.cookies.get(MFA_CHALLENGE_COOKIE, "")
    if not raw:
        return None
    with db() as con:
        row = con.execute("""SELECT c.*,u.username,u.display_name,u.mfa_enabled,u.totp_secret,u.recovery_codes_hash,u.is_active
                             FROM mfa_login_challenges c JOIN users u ON u.id=c.user_id WHERE c.token_hash=?""",
                          (_hash_session_token(raw),)).fetchone()
        if not row or not int(row["is_active"] or 0):
            return None
        try:
            if datetime.fromisoformat(row["expires_at"]) <= datetime.now():
                con.execute("DELETE FROM mfa_login_challenges WHERE id=?", (row["id"],))
                return None
        except Exception:
            return None
        return row


def _recovery_code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().replace(" ", "").encode("utf-8")).hexdigest()


def _generate_recovery_codes() -> list[str]:
    return [f"{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}" for _ in range(10)]


def _recovery_hashes(codes: list[str]) -> str:
    return json.dumps([_recovery_code_hash(code) for code in codes])


def _verify_totp_or_recovery(user: sqlite3.Row, value: str, consume_recovery: bool = True) -> bool:
    value = (value or "").strip()
    user_id = int(user["user_id"] if "user_id" in user.keys() else user["id"])
    # Read current security state, not a potentially stale login-challenge row.
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        account = con.execute("SELECT totp_secret,recovery_codes_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not account:
            return False
        secret = str(account["totp_secret"] or "")
        if secret and _totp_verify(secret, value.replace(" ", ""), valid_window=1):
            return True
        supplied = _recovery_code_hash(value)
        try:
            hashes = list(json.loads(account["recovery_codes_hash"] or "[]"))
        except (TypeError, ValueError):
            return False
        if supplied not in hashes:
            return False
        if consume_recovery:
            hashes.remove(supplied)
            con.execute("UPDATE users SET recovery_codes_hash=?,updated_at=? WHERE id=?", (json.dumps(hashes),now(),user_id))
        return True


def _totp_random_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_code(secret: str, at_time: int | None = None, interval: int = 30) -> str:
    current = int(time.time() if at_time is None else at_time) // interval
    padded = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", current), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1000000:06d}"


def _totp_verify(secret: str, code: str, valid_window: int = 1) -> bool:
    normalized = re.sub(r"\s+", "", code or "")
    if not re.fullmatch(r"\d{6}", normalized):
        return False
    now_epoch = int(time.time())
    return any(hmac.compare_digest(_totp_code(secret, now_epoch + offset * 30), normalized) for offset in range(-valid_window, valid_window + 1))


def _totp_qr_data_uri(username: str, secret: str) -> str:
    label = quote(f"{MFA_ISSUER}:{username}", safe="")
    issuer = quote(MFA_ISSUER, safe="")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    image = qrcode.make(uri)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    path = request.url.path
    public = path.startswith("/static/") or path.startswith("/system/reconnect/") or path.startswith("/setup") or path in {"/login", "/login/mfa", "/system/ready", "/settings/application-update/status"}
    if not _users_exist():
        if not public:
            return RedirectResponse("/setup", status_code=303)
        request.state.user = None
    else:
        user = _session_user(request)
        request.state.user = user
        if user and int(user["must_change_password"] or 0) and path not in {"/profile", "/profile/change-password", "/logout"} and not path.startswith("/static/"):
            return RedirectResponse("/profile?profile_message=Change+the+temporary+password+to+continue.&profile_ok=0#security", status_code=303)
        mfa_required = bool(user and user["role"] == "admin" and _auth_settings()["require_mfa_admins"] and not int(user["mfa_enabled"] or 0))
        if mfa_required and path not in {"/profile", "/profile/mfa/setup", "/profile/mfa/enable", "/logout", "/profile/avatar"} and not path.startswith("/static/"):
            return RedirectResponse("/profile?profile_message=MFA+is+required+for+administrator+accounts.&profile_ok=0&mfa_required=1", status_code=303)
        if not public and not user:
            if request.method == "GET":
                return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and path not in {"/login", "/login/mfa"} and not path.startswith("/setup"):
        site = (request.headers.get("sec-fetch-site") or "").lower()
        if site in {"cross-site", "none"}:
            return HTMLResponse("Cross-site request rejected.", status_code=403)
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        expected = str(request.base_url).rstrip("/")
        if origin and origin.rstrip("/") != expected:
            return HTMLResponse("Invalid request origin.", status_code=403)
        if not origin and referer and not referer.startswith(expected + "/"):
            return HTMLResponse("Invalid request origin.", status_code=403)
        if request.headers.get("content-type", "").startswith("application/json"):
            expected_token = request.state.user["csrf_token"] if getattr(request.state, "user", None) else None
            supplied = request.headers.get("x-csrf-token", "")
            if not expected_token or not hmac.compare_digest(str(expected_token), supplied):
                return JSONResponse({"detail": "Invalid CSRF token"}, status_code=403)
    token_ctx = _CURRENT_USER_ID.set(int(user["id"]) if getattr(request.state, "user", None) else None)
    try:
        response = await call_next(request)
    finally:
        _CURRENT_USER_ID.reset(token_ctx)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


def page_context(request: Request, page: str, **extra):
    user = getattr(request.state, "user", None)
    ctx = {"request": request, "page": page, "settings": get_settings(), "app_version": APP_VERSION, "app_date": APP_DATE,
           "database_schema_version": DATABASE_SCHEMA_VERSION, "installer_version": INSTALLER_VERSION,
           "current_user": user, "current_user_initials": _profile_initials(user) if user else "", "csrf_token": user["csrf_token"] if user else ""}
    ctx.update(extra)
    return ctx


def fetch_category_configs() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT * FROM categories WHERE owner_user_id=? ORDER BY name COLLATE NOCASE", (require_current_user_id(),)).fetchall()


def fetch_categories() -> list[str]:
    values = [r["name"] for r in fetch_category_configs()]
    return values or sorted(DEFAULT_CATEGORIES, key=str.lower)


def category_config(name: str | None) -> dict[str, bool]:
    with db() as con:
        row = con.execute("SELECT * FROM categories WHERE owner_user_id=? AND name=?", (require_current_user_id(), (name or "Other"))).fetchone()
    if not row:
        return {"show_ownership": True, "show_firmware": True, "show_network": False, "show_system_checks": False}
    system_checks = bool(row["show_system_checks"] if "show_system_checks" in row.keys() else (row["show_health"] or row["show_updates"]))
    return {
        "show_ownership": bool(row["show_ownership"]),
        "show_firmware": bool(row["show_firmware"]),
        "show_network": bool(row["show_network"]),
        "show_system_checks": system_checks,
    }


def available_key_files() -> list[str]:
    """Return usable private-key files from the application data directory."""
    files: list[str] = []
    try:
        KEY_DIR.mkdir(parents=True, exist_ok=True)
        for path in KEY_DIR.iterdir():
            if path.is_file() and not path.name.endswith((".pub", ".txt")):
                files.append(path.name)
    except OSError:
        return []
    return sorted(files, key=str.lower)


def fetch_devices() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT * FROM devices WHERE owner_user_id=? ORDER BY display_name COLLATE NOCASE, name COLLATE NOCASE", (require_current_user_id(),)).fetchall()


def fetch_device(device_id: int) -> Optional[sqlite3.Row]:
    return fetch_device_for_owner(device_id, require_current_user_id())


def add_activity_event(device_id: int, owner_user_id: int, event_type: str, title: str, result: str = "info", summary: str = "", details: str = "") -> None:
    """Store one meaningful user/action event for a device. Periodic checks do not belong here."""
    if not device_id or not owner_user_id:
        return
    with db() as con:
        con.execute(
            "INSERT INTO activity_history(device_id,owner_user_id,event_type,title,result,summary,details,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (int(device_id), int(owner_user_id), str(event_type), str(title), str(result), str(summary or "")[:1000], str(details or "")[-12000:], now()),
        )


def fetch_activity_history(device_id: int, limit: int = 50) -> list[sqlite3.Row]:
    with db() as con:
        return con.execute(
            "SELECT * FROM activity_history WHERE device_id=? AND owner_user_id=? ORDER BY id DESC LIMIT ?",
            (int(device_id), require_current_user_id(), max(1, min(200, int(limit)))),
        ).fetchall()



def group_activity_history(events) -> list[dict]:
    """Present activity history as stable, compact categories."""
    buckets = [
        ("system", "System Upgrades", {"system_upgrade"}),
        ("reboot", "Reboots", {"reboot"}),
        ("minecraft", "Minecraft", {"minecraft_update"}),
        ("pihole", "Pi-hole", {"pihole_update"}),
        ("maintenance", "Maintenance", {"maintenance"}),
    ]
    grouped = []
    consumed = set()
    for key, title, types in buckets:
        items = [event for event in events if str(event["event_type"] or "") in types]
        if items:
            grouped.append({"key": key, "title": title, "events": items})
            consumed.update(types)
    other = [event for event in events if str(event["event_type"] or "") not in consumed]
    if other:
        grouped.append({"key": "other", "title": "Other", "events": other})
    return grouped

def fetch_device_for_owner(device_id: int, owner_user_id: int) -> Optional[sqlite3.Row]:
    """Fetch a device without depending on a browser-session context.

    Background jobs run outside an authenticated request, so they must use the
    owner stored on the scheduled check instead of require_current_user_id().
    """
    with db() as con:
        return con.execute(
            "SELECT * FROM devices WHERE id = ? AND owner_user_id=?",
            (device_id, owner_user_id),
        ).fetchone()


def fetch_attachments(device_id: int) -> list[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT * FROM attachments WHERE device_id = ? ORDER BY created_at DESC", (device_id,)).fetchall()


def device_network_target(device_id: int | None) -> str:
    if not device_id:
        return ""
    device = fetch_device(int(device_id))
    if not device:
        return ""
    return (device["ipv4_address"] or device["hostname"] or device["ipv6_address"] or "").strip()


def resolved_target(device_id: int | None, fallback: str = "") -> str:
    return device_network_target(device_id) or (fallback or "").strip()


def fetch_health_checks_for_scheduler() -> list[sqlite3.Row]:
    """Fetch all health checks for the background scheduler, independent of a web session."""
    with db() as con:
        return con.execute(
            """
            SELECT h.*, d.display_name AS device_display_name, d.name AS device_name, d.category AS device_category,
                   d.hostname AS device_hostname, d.ipv4_address AS device_ipv4, d.ipv6_address AS device_ipv6,
                   d.managed_host AS device_managed_host, d.integration_status AS device_integration_status,
                   d.integration_checked_at AS device_integration_checked_at, d.integration_details AS device_integration_details
            FROM health_checks h
            LEFT JOIN devices d ON d.id = h.device_id AND d.owner_user_id = h.owner_user_id
            ORDER BY h.device_id,
                     CASE LOWER(COALESCE(h.check_type,'ping'))
                       WHEN 'ping' THEN 0
                       WHEN 'http' THEN 1
                       WHEN 'disk' THEN 2
                       ELSE 3
                     END,
                     h.id
            """
        ).fetchall()


def fetch_health_checks() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute(
            """
            SELECT h.*, d.display_name AS device_display_name, d.name AS device_name, d.category AS device_category,
                   d.hostname AS device_hostname, d.ipv4_address AS device_ipv4, d.ipv6_address AS device_ipv6,
                   d.managed_host AS device_managed_host, d.integration_status AS device_integration_status,
                   d.integration_checked_at AS device_integration_checked_at, d.integration_details AS device_integration_details
            FROM health_checks h
            LEFT JOIN devices d ON d.id = h.device_id
            WHERE h.owner_user_id=? AND d.owner_user_id=?
            ORDER BY h.device_id,
                     CASE LOWER(COALESCE(h.check_type,'ping'))
                       WHEN 'ping' THEN 0
                       WHEN 'http' THEN 1
                       WHEN 'disk' THEN 2
                       ELSE 3
                     END,
                     h.id
            """, (require_current_user_id(), require_current_user_id())
        ).fetchall()


def fetch_health_check(check_id: int) -> Optional[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT h.* FROM health_checks h JOIN devices d ON d.id=h.device_id WHERE h.id=? AND h.owner_user_id=? AND d.owner_user_id=?", (check_id, require_current_user_id(), require_current_user_id())).fetchone()


def fetch_device_health_check(device_id: int) -> Optional[sqlite3.Row]:
    with db() as con:
        return con.execute(
            "SELECT h.* FROM health_checks h JOIN devices d ON d.id=h.device_id WHERE h.device_id=? AND h.owner_user_id=? AND d.owner_user_id=? ORDER BY h.enabled DESC, h.name COLLATE NOCASE LIMIT 1",
            (device_id, require_current_user_id(), require_current_user_id()),
        ).fetchone()


def fetch_unlinked_health_checks() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute(
            "SELECT * FROM health_checks WHERE device_id IS NULL AND owner_user_id=? ORDER BY name COLLATE NOCASE",
            (require_current_user_id(),),
        ).fetchall()


def category_usage() -> dict[str, int]:
    """Return authoritative per-category item counts.

    Matching is case-insensitive and ignores accidental surrounding whitespace so
    renamed/imported categories cannot produce misleading totals.
    """
    with db() as con:
        rows = con.execute(
            """
            SELECT c.name AS category_name, COUNT(d.id) AS count
            FROM categories c
            LEFT JOIN devices d
              ON d.owner_user_id=c.owner_user_id AND LOWER(TRIM(COALESCE(d.category, ''))) = LOWER(TRIM(c.name))
            WHERE c.owner_user_id=?
            GROUP BY c.name
            ORDER BY c.name COLLATE NOCASE
            """, (require_current_user_id(),)
        ).fetchall()
    return {r["category_name"]: int(r["count"] or 0) for r in rows}


def health_group_key(row) -> str:
    return str(row["group_key"] or (f"device:{row['device_id']}" if row["device_id"] else f"host:{row['name']}:{row['host']}"))


def fetch_health_group(check_id: int) -> list[sqlite3.Row]:
    check = fetch_health_check(check_id)
    if not check:
        return []
    key = health_group_key(check)
    with db() as con:
        rows = con.execute("SELECT * FROM health_checks WHERE owner_user_id=? ORDER BY check_type", (require_current_user_id(),)).fetchall()
    return [row for row in rows if health_group_key(row) == key]


def grouped_health_checks() -> list[dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    order: list[str] = []
    rank = {"critical": 5, "offline": 4, "warning": 3, "unknown": 2, "maintenance": 1, "online": 0, "disabled": -1}
    for row in fetch_health_checks():
        item = dict(row)
        key = health_group_key(row)
        if key not in groups:
            groups[key] = {"id": row["id"], "key": key, "name": row["name"], "device_id": row["device_id"],
                "device_display_name": row["device_display_name"], "device_name": row["device_name"],
                "device_ipv4": row["device_ipv4"], "device_hostname": row["device_hostname"], "device_ipv6": row["device_ipv6"],
                "device_managed_host": row["device_managed_host"], "device_integration_status": row["device_integration_status"],
                "device_integration_checked_at": row["device_integration_checked_at"],
                "device_integration_details": row["device_integration_details"],
                "checks": [], "overall_status": "disabled", "last_checked": "", "maintenance": bool(row["maintenance"])}
            order.append(key)
        g=groups[key]
        if not g.get("integration_details"):
            try:
                g["integration_details"] = json.loads(str(g.get("device_integration_details") or "{}"))
            except (TypeError, json.JSONDecodeError):
                g["integration_details"] = {}
        status = "maintenance" if row["maintenance"] else ((row["status"] or "unknown").lower() if row["enabled"] else "disabled")
        item["effective_status"] = status
        g["checks"].append(item)
        if status != "disabled" and rank.get(status, 2) > rank.get(str(g["overall_status"]), 0): g["overall_status"] = status
        if str(row["last_checked"] or "") > str(g["last_checked"] or ""): g["last_checked"] = row["last_checked"]
    return [groups[k] for k in order]


def health_summary() -> dict[str, int]:
    """Return one effective status per host, identical to the System Checks page."""
    counts = {"online": 0, "warning": 0, "critical": 0, "offline": 0, "unknown": 0, "maintenance": 0, "disabled": 0, "managed_attention": 0}
    for group in grouped_health_checks():
        status = str(group.get("overall_status") or "unknown")
        if status not in counts:
            status = "unknown"
        counts[status] += 1
        if group.get("device_managed_host") and str(group.get("device_integration_status") or "") in ("warning", "failed"):
            counts["managed_attention"] += 1
    counts["total"] = sum(counts[k] for k in ("online", "warning", "critical", "offline", "unknown", "maintenance", "disabled"))
    return counts


def _tcp_probe_host(host: str) -> tuple[bool, int]:
    """Fallback reachability check when ICMP ping is unavailable or blocked.

    Some LXC/container setups cannot use raw ICMP even though the target is alive.
    For a lightweight availability check, a successful TCP connect to a common
    management/service port is enough to mark the device reachable.
    """
    import socket
    ports = [80, 443, 22, 53, 445, 139, 8000, 8080, 8123, 5000, 5001]
    for port in ports:
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=0.6):
                return True, max(1, int((time.perf_counter() - started) * 1000))
        except Exception:
            continue
    return False, 0


def _ping_host(host: str) -> tuple[str, int, str]:
    started = time.perf_counter()
    last_output = ""
    last_error = ""
    for _attempt in range(2):
        try:
            result = subprocess.run(["ping", "-c", "1", "-W", "2", host], capture_output=True, text=True, timeout=4)
            elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            last_output = output
            m = re.search(r"time[=<]([0-9.]+)\s*ms", output)
            if result.returncode == 0 or m:
                ms = int(float(m.group(1))) if m else elapsed_ms
                return "online", ms, ""
        except Exception as exc:
            last_error = str(exc)

    # ICMP can be blocked or unavailable in containers. Keep the existing
    # conservative TCP fallback before declaring the device offline.
    tcp_ok, tcp_ms = _tcp_probe_host(host)
    if tcp_ok:
        return "online", tcp_ms, ""

    err_lines = [ln.strip() for ln in last_output.splitlines() if ln.strip()]
    err = err_lines[-1] if err_lines else (last_error or "Ping failed")
    return "offline", 0, err[:220]


def _http_check(url: str) -> tuple[str, int, str]:
    started = time.perf_counter()
    try:
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        r = requests.get(url, timeout=5, allow_redirects=True, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
        ms = int((time.perf_counter() - started) * 1000)
        if 200 <= r.status_code < 500:
            return "online", ms, ""
        return "offline", ms, f"HTTP {r.status_code}"
    except Exception as exc:
        return "offline", int((time.perf_counter() - started) * 1000), str(exc)[:220]


def _format_uptime(seconds: int | None) -> str:
    total = max(0, int(seconds or 0))
    days, rem = divmod(total, 86400)
    hours = rem // 3600
    if days and hours:
        return f"{days} day{'s' if days != 1 else ''}, {hours} hour{'s' if hours != 1 else ''}"
    if days:
        return f"{days} day{'s' if days != 1 else ''}"
    return f"{hours} hour{'s' if hours != 1 else ''}"


def _read_and_store_uptime(client: paramiko.SSHClient, device_id: int) -> tuple[int, str]:
    try:
        _, stdout, stderr = client.exec_command("cat /proc/uptime | cut -d' ' -f1; uptime -s", timeout=10)
        lines = stdout.read().decode("utf-8", "replace").strip().splitlines()
        error = stderr.read().decode("utf-8", "replace").strip()
        if stdout.channel.recv_exit_status() != 0 or not lines:
            return 0, ""
        seconds = max(0, int(float(lines[0].strip())))
        boot = lines[1].strip()[:16] if len(lines) > 1 else ""
        with db() as con:
            con.execute("UPDATE devices SET system_uptime_seconds=?, last_boot=?, uptime_last_checked=?, updated_at=? WHERE id=?", (seconds, boot, now(), now(), device_id))
        return seconds, boot
    except Exception:
        return 0, ""


def _disk_status_from_percent(percent: int, warning: int, critical: int) -> str:
    warning = max(1, min(99, int(warning)))
    critical = max(warning + 1, min(100, int(critical)))
    if int(percent) >= critical:
        return "critical"
    if int(percent) >= warning:
        return "warning"
    return "online"


def _disk_usage_check(check: sqlite3.Row) -> tuple[str, int, str, str]:
    """Check root filesystem usage through the device's managed SSH profile."""
    if not check["device_id"]:
        return "unknown", 0, "Disk Usage requires a linked managed host.", ""
    device = fetch_device_for_owner(int(check["device_id"]), int(check["owner_user_id"]))
    if not device or not device["managed_host"] or not device["managed_ssh_profile_id"]:
        return "unknown", 0, "Disk Usage requires configured managed host integration.", ""
    profile = fetch_ssh_profile_for_owner(int(device["managed_ssh_profile_id"]), int(check["owner_user_id"]))
    if not profile:
        return "unknown", 0, "Managed host SSH profile not found.", ""
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        target = (device["ipv4_address"] or device["hostname"] or device["ipv6_address"] or check["host"] or "").strip()
        if not target:
            return "unknown", 0, "No network address is configured for this managed host.", ""
        client.connect(hostname=target, port=int(profile["port"] or 22), username=profile["username"], pkey=pkey,
                       timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False)
        _read_and_store_uptime(client, int(device["id"]))
        _, stdout, stderr = client.exec_command("df -P -B1 / | tail -1", timeout=15)
        output = stdout.read().decode("utf-8", "replace").strip()
        error = stderr.read().decode("utf-8", "replace").strip()
        if stdout.channel.recv_exit_status() != 0 or not output:
            return "unknown", 0, (error or "Unable to read disk usage.")[:220], ""
        fields = output.split()
        if len(fields) < 6 or not fields[4].endswith("%"):
            return "unknown", 0, "Unexpected disk usage response.", ""
        percent = int(fields[4].rstrip("%"))
        total, used, available, mountpoint = int(fields[1]), int(fields[2]), int(fields[3]), fields[5]
        details = json.dumps({"total_bytes": total, "used_bytes": used, "available_bytes": available, "mountpoint": mountpoint})
        settings = get_settings()
        try:
            warning = max(1, min(99, int(check["disk_warning_percent"] if "disk_warning_percent" in check.keys() and check["disk_warning_percent"] is not None else settings.get("disk_usage_warning_percent", "85"))))
            critical = max(warning + 1, min(100, int(check["disk_critical_percent"] if "disk_critical_percent" in check.keys() and check["disk_critical_percent"] is not None else settings.get("disk_usage_critical_percent", "95"))))
        except (TypeError, ValueError):
            warning, critical = 85, 95
        status = _disk_status_from_percent(percent, warning, critical)
        return status, percent, "", details
    except Exception as exc:
        return "unknown", 0, str(exc)[:220], ""
    finally:
        client.close()


def run_health_check(check: sqlite3.Row) -> dict[str, object]:
    if check["maintenance"]:
        return {"status": "maintenance", "response_ms": 0, "error": "Maintenance mode"}
    if not check["enabled"]:
        return {"status": "unknown", "response_ms": 0, "error": "Health check disabled"}
    check_type = (check["check_type"] or "ping").lower()
    if check_type == "disk":
        if check["device_id"] and _device_online_status(int(check["device_id"]), int(check["owner_user_id"] or 0)) == "offline":
            return {"status": "unknown", "response_ms": 0, "error": "", "disk_usage_percent": int(check["disk_usage_percent"] or 0), "disk_usage_details": str(check["disk_usage_details"] or "")}
        status, percent, error, details = _disk_usage_check(check)
        return {"status": status, "response_ms": 0, "error": error, "disk_usage_percent": percent, "disk_usage_details": details}
    target = check["url"] if check_type == "http" else check["host"]
    if not target:
        error = "No HTTP(S) URL configured" if check_type == "http" else "No host configured"
        return {"status": "unknown", "response_ms": 0, "error": error, "disk_usage_percent": 0, "disk_usage_details": ""}
    if check_type == "http":
        status, response_ms, error = _http_check(target)
    else:
        status, response_ms, error = _ping_host(target)
    status = (status or "unknown").lower()
    if status not in ("online", "offline", "unknown"):
        status = "unknown"
    return {"status": status, "response_ms": response_ms if status == "online" else 0, "error": error if status != "online" else "", "disk_usage_percent": 0, "disk_usage_details": ""}



def _health_last_checked(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def health_check_is_due(check: sqlite3.Row, at: datetime | None = None) -> bool:
    if not check["enabled"] or check["maintenance"]:
        return False
    current = (at or datetime.now()).replace(second=0, microsecond=0)
    interval = max(1, int(check["interval_minutes"] or 10))
    # Preserve fixed boundaries, including intervals longer than one hour.
    minutes = current.toordinal() * 1440 + current.hour * 60 + current.minute
    boundary = current - timedelta(minutes=minutes % interval)
    last = _health_last_checked(check["last_checked"])
    return last is None or last < boundary


def execute_health_check(check: sqlite3.Row) -> None:
    # Re-read current maintenance state so a scheduler row fetched just before an
    # application update cannot race into a false offline/critical result.
    with db() as con:
        current = con.execute("SELECT maintenance FROM health_checks WHERE id=?", (check["id"],)).fetchone()
    if check["maintenance"] or (current and int(current["maintenance"] or 0)):
        with db() as con:
            con.execute("UPDATE health_checks SET status='maintenance', response_ms=0, last_error='', updated_at=? WHERE id=?", (now(), check["id"]))
        return
    try:
        result = run_health_check(check)
    except Exception as exc:
        # One failing host must never abort the complete scheduler run. Store a
        # persistent Unknown result for this check and continue with the rest.
        result = {
            "status": "unknown",
            "response_ms": 0,
            "error": str(exc)[:220],
            "disk_usage_percent": 0,
            "disk_usage_details": "",
        }
    status = str(result["status"]).lower()
    t = now()
    last_online = t if status == "online" else (check["last_online"] or "")
    with db() as con:
        con.execute(
            """UPDATE health_checks
               SET status=?, response_ms=?, last_checked=?, last_online=?,
                   last_error=?, disk_usage_percent=?, disk_usage_details=?, updated_at=? WHERE id=?""",
            (status, int(result["response_ms"]), t, last_online, result["error"], int(result.get("disk_usage_percent", 0)), str(result.get("disk_usage_details", "")), t, check["id"]),
        )
    # System Check results are authoritative and must remain persistent. Managed-host
    # integration validation is a separate diagnostic workflow; running it after
    # every individual Ping/Disk/HTTP check caused unnecessary SSH work and could
    # race with page reads while a grouped Check all operation was still active.
    # Do not mix or overwrite these two state machines here.


def run_due_health_checks(force: bool = False) -> int:
    # Prevent Check all and the background loop from checking the same target
    # simultaneously.
    if not _health_scheduler_lock.acquire(blocking=False):
        return 0
    try:
        at = datetime.now()
        ran = 0
        due_device_ids = set()
        for check in fetch_health_checks_for_scheduler():
            if check["enabled"] and not check["maintenance"] and (force or health_check_is_due(check, at)):
                execute_health_check(check)
                if check["device_id"]:
                    due_device_ids.add(int(check["device_id"]))
                ran += 1
        # Application runtime/availability health belongs to the 10-minute health
        # cycle, while external/latest-version lookups remain daily.
        if due_device_ids:
            with db() as con:
                minecraft_checks = con.execute(
                    "SELECT * FROM application_checks WHERE enabled=1 AND application_type='minecraft'"
                ).fetchall()
                pihole_checks = con.execute(
                    "SELECT * FROM application_checks WHERE enabled=1 AND application_type='pihole'"
                ).fetchall()
            for minecraft_check in minecraft_checks:
                if int(minecraft_check["device_id"] or 0) in due_device_ids:
                    execute_minecraft_runtime_check(minecraft_check)
            for pihole_check in pihole_checks:
                if int(pihole_check["device_id"] or 0) in due_device_ids:
                    execute_pihole_dns_health_check(pihole_check)
        if ran:
            with db() as con:
                con.execute("INSERT INTO settings(key,value) VALUES ('health_last_successful_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now(),))
        return ran
    finally:
        _health_scheduler_lock.release()


def _record_scheduler_start(job_name: str) -> int:
    with db() as con:
        cursor = con.execute(
            "INSERT INTO scheduler_runs(job_name,started_at,status) VALUES (?,?, 'running')",
            (job_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        run_id = int(cursor.lastrowid)
        # Keep bounded operational history without requiring manual cleanup.
        con.execute(
            "DELETE FROM scheduler_runs WHERE id IN (SELECT id FROM scheduler_runs ORDER BY id DESC LIMIT -1 OFFSET 500)"
        )
    return run_id


def _record_scheduler_finish(run_id: int, status: str, details: str = "", error: str = "") -> None:
    with db() as con:
        con.execute(
            "UPDATE scheduler_runs SET finished_at=?, status=?, details=?, error=? WHERE id=?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), status, details[:500], error[:1000], run_id),
        )


def _run_scheduler_job(job_name: str, callback) -> None:
    run_id = _record_scheduler_start(job_name)
    try:
        result = callback()
        detail = "" if result is None else str(result)
        # The loop polls every 15 seconds, but operational history should only
        # contain work that actually ran or failed.
        idle_results = {"", "0", "not due", "already completed", "already completed today", "already running", "disabled"}
        if detail.strip().lower() in idle_results:
            with db() as con:
                con.execute("DELETE FROM scheduler_runs WHERE id=?", (run_id,))
            return
        _record_scheduler_finish(run_id, "success", detail)
    except Exception as exc:
        _record_scheduler_finish(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
        print(f"Scheduler job {job_name} failed: {exc}", flush=True)


def _active_user_ids() -> list[int]:
    with db() as con:
        return [int(row[0]) for row in con.execute("SELECT id FROM users WHERE is_active=1 ORDER BY id").fetchall()]


def dispatch_notifications_for_all_users() -> int:
    total = 0
    for user_id in _active_user_ids():
        token = _CURRENT_USER_ID.set(user_id)
        try:
            total += dispatch_notifications()
        finally:
            _CURRENT_USER_ID.reset(token)
    return total


def health_scheduler_loop() -> None:
    # One process-level scheduler, independent of browser sessions. Each job is
    # isolated so a notification, update or backup failure cannot block the
    # remaining background work.
    while not _health_scheduler_stop.wait(15):
        _run_scheduler_job("health", run_due_health_checks)
        _run_scheduler_job("daily_checks", run_due_maintenance_checks)
        _run_scheduler_job("notifications", dispatch_notifications_for_all_users)
        _run_scheduler_job("automatic_backup", run_due_automatic_backup)

def _setting_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}



def notification_settings() -> dict[str, object]:
    settings = get_settings()
    return {
        "enabled": _setting_bool(settings.get("notifications_enabled")),
        "health_enabled": _setting_bool(settings.get("notification_health_enabled"), True),
        "firmware_enabled": _setting_bool(settings.get("notification_firmware_enabled"), True),
        "updates_enabled": _setting_bool(settings.get("notification_updates_enabled"), True),
        "application_enabled": _setting_bool(settings.get("notification_application_enabled"), True),
        "smtp_host": settings.get("smtp_host", ""), "smtp_port": settings.get("smtp_port", "587"),
        "smtp_encryption": settings.get("smtp_encryption", "starttls"), "smtp_username": settings.get("smtp_username", ""),
        "smtp_sender_name": settings.get("smtp_sender_name", "Outlaw's Inventory"),
        "smtp_sender_address": settings.get("smtp_sender_address", ""), "smtp_recipient_address": settings.get("smtp_recipient_address", ""),
        "application_base_url": settings.get("application_base_url", ""), "password_configured": SMTP_PASSWORD_FILE.exists(),
    }


def _smtp_password() -> str:
    try: return SMTP_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    except OSError: return ""


def _notification_email_html(
    title: str,
    intro: str,
    items: list[tuple[str, str]],
    button_label: str = "",
    button_url: str = "",
    accent: str = "#f59e0b",
    footer_text: str = "",
) -> str:
    item_rows = "".join(
        '<tr><td style="padding:12px 0;border-bottom:1px solid #27334d;">'
        f'<div style="font-size:15px;font-weight:600;color:#f8fafc;">{escape(label)}</div>'
        f'<div style="margin-top:4px;font-size:14px;line-height:1.5;color:#aab6cc;">{escape(detail)}</div>'
        '</td></tr>'
        for label, detail in items
    )
    button = ""
    if button_label and button_url:
        button = (
            '<tr><td style="padding-top:22px;">'
            f'<a href="{escape(button_url, quote=True)}" style="display:inline-block;background:{accent};color:#111827;text-decoration:none;font-size:14px;font-weight:700;padding:11px 18px;border-radius:8px;">{escape(button_label)}</a>'
            '</td></tr>'
        )
    footer = escape(footer_text) if footer_text else "Outlaw's Inventory"
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#0b1220;color:#e5e7eb;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif;">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#0b1220;padding:24px 12px;"><tr><td align="center">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:620px;background:#111a2c;border:1px solid #27334d;border-radius:14px;overflow:hidden;">'
        f'<tr><td style="height:5px;background:{accent};font-size:0;line-height:0;">&nbsp;</td></tr>'
        '<tr><td style="padding:28px 30px 10px;">'
        '<div style="font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:#7f8da8;">Outlaw&#39;s Inventory</div>'
        f'<h1 style="margin:10px 0 8px;font-size:24px;line-height:1.25;color:#f8fafc;">{escape(title)}</h1>'
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#aab6cc;">{escape(intro)}</p>'
        '</td></tr>'
        f'<tr><td style="padding:8px 30px 28px;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">{item_rows}{button}</table></td></tr>'
        f'<tr><td style="padding:18px 30px;background:#0e1728;border-top:1px solid #27334d;font-size:12px;color:#71809d;">{footer}</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def send_notification_email(subject: str, body: str, html_body: str = "") -> tuple[bool, str]:
    cfg = notification_settings()
    host = str(cfg["smtp_host"]).strip(); recipient = str(cfg["smtp_recipient_address"]).strip()
    sender = str(cfg["smtp_sender_address"]).strip() or str(cfg["smtp_username"]).strip()
    if not host or not recipient or not sender: return False, "SMTP host, sender and recipient are required."
    try: port = int(str(cfg["smtp_port"]) or "587")
    except ValueError: return False, "Invalid SMTP port."
    msg = EmailMessage(); msg["Subject"] = subject; msg["From"] = f'{cfg["smtp_sender_name"]} <{sender}>' if cfg["smtp_sender_name"] else sender; msg["To"] = recipient; msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    try:
        mode = str(cfg["smtp_encryption"]).lower(); context = ssl.create_default_context()
        client = smtplib.SMTP_SSL(host, port, timeout=15, context=context) if mode == "ssl" else smtplib.SMTP(host, port, timeout=15)
        with client:
            if mode == "starttls": client.starttls(context=context)
            username = str(cfg["smtp_username"]).strip(); password = _smtp_password()
            if username: client.login(username, password)
            client.send_message(msg)
        return True, "Test email sent successfully."
    except Exception as exc: return False, f"Unable to send email: {exc}"



def _application_notification_owner_user_id() -> int | None:
    """Return the single account responsible for instance-wide application alerts."""
    with db() as con:
        row = con.execute(
            "SELECT id FROM users WHERE is_active=1 ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END, id LIMIT 1"
        ).fetchone()
    return int(row[0]) if row else None

def collect_notification_events() -> dict[str, tuple[str, str, str]]:
    cfg = notification_settings(); events = {}
    if cfg["health_enabled"]:
        for r in fetch_health_checks():
            if r["enabled"] and not r["maintenance"] and r["status"] not in ("online", "unknown"):
                key=f'health:{r["id"]}'; text=f'{r["name"]}: {r["status"]}'
                events[key]=(text, text, "/system-checks")
    if cfg["firmware_enabled"]:
        for d in fetch_devices():
            if d["status"] == "attention":
                text=f'{display_name(d)}: firmware {d["current_firmware"] or "unknown"} → {effective_latest_value(d["latest_firmware"], d["latest_firmware_override"])}'
                events[f'firmware:{d["id"]}']=(text, text, "/firmware")
    if cfg["updates_enabled"]:
        for r in fetch_update_checks():
            if (
                r["enabled"]
                and not _device_system_checks_maintenance(r["device_id"], r["owner_user_id"])
                and (r["status"] in ("available", "failed") or r["reboot_required"])
            ):
                detail = f'{r["package_count"]} update(s) available' if r["status"] == "available" else (r["last_error"] or r["status"])
                if r["reboot_required"]: detail += "; reboot required"
                text=f'{r["name"]}: {detail}'; events[f'updates:{r["id"]}']=(text, text, "/system-checks")
    if cfg["updates_enabled"]:
        for r in fetch_application_checks():
            if (
                r["enabled"]
                and not _device_system_checks_maintenance(r["device_id"], r["owner_user_id"])
                and (r["status"] in ("available", "failed") or (r["status"] == "unknown" and str(r["last_error"] or "").strip()))
            ):
                app_name = {"pihole": "Pi-hole", "minecraft": "Minecraft"}.get(str(r["application_type"]).lower(), str(r["application_type"]))
                system_name = str(r["display_name"] or r["device_name"] or "Server")
                detail = f"{app_name} update available" if r["status"] == "available" else (r["last_error"] or f"{app_name} check failed")
                text = f"{system_name}: {detail}"
                events[f'appupdates:{r["id"]}'] = (text, text, f'/system-checks/{r["device_id"]}')
    # Application releases are instance-wide, not owned inventory data. Send
    # them once through one deterministic account instead of once per user.
    if cfg["application_enabled"] and require_current_user_id() == _application_notification_owner_user_id():
        info = application_update_info()
        if info.get("update_available"):
            version = str(info.get("latest_version") or "").strip().lstrip("v")
            text = f"Outlaw's Inventory v{version} is available"
            events["application:update"] = (version, text, "/settings?update_open=1#application-version")
    return events


def dispatch_notifications() -> int:
    cfg = notification_settings()
    if not cfg["enabled"]:
        return 0
    user_id = require_current_user_id()

    # Notification dispatch can be triggered by the background scheduler and by
    # completed checks at nearly the same time. Serialize the claim operation so
    # the same event cannot be mailed twice before its state is recorded.
    with _notification_dispatch_lock:
        events = collect_notification_events()
        claimed: list[tuple[str, str, str, str]] = []
        stamp = now()
        with db() as con:
            existing = {
                r["event_key"]: r
                for r in con.execute(
                    "SELECT * FROM notification_state WHERE user_id=?", (user_id,)
                ).fetchall()
            }
            for key, (fingerprint, text, path) in events.items():
                row = existing.get(key)
                if not row or not row["active"] or row["fingerprint"] != fingerprint:
                    claimed.append((key, fingerprint, text, path))
                con.execute(
                    """INSERT INTO notification_state(user_id,event_key,fingerprint,active,updated_at)
                       VALUES (?,?,?,1,?)
                       ON CONFLICT(user_id,event_key) DO UPDATE SET
                           fingerprint=excluded.fingerprint,active=1,updated_at=excluded.updated_at""",
                    (user_id, key, fingerprint, stamp),
                )
            missing_keys = set(existing) - set(events)
            if missing_keys:
                con.executemany(
                    "UPDATE notification_state SET active=0, updated_at=? WHERE user_id=? AND event_key=?",
                    [(stamp, user_id, key) for key in missing_keys],
                )

        if not claimed:
            return 0

        base = str(cfg["application_base_url"]).rstrip("/")
        sent = 0
        failed_keys: list[tuple[str, str]] = []

        application_events = [item for item in claimed if item[0] == "application:update"]
        general_events = [item for item in claimed if item[0] != "application:update"]

        for key, fingerprint, _text, _path in application_events:
            version = fingerprint.strip().lstrip("v")
            target = "/settings?update_open=1#application-version"
            body = "A new version of Outlaw's Inventory is available.\n\n"
            body += f"Version: v{version}\n"
            if base:
                body += f"\n{base}{target}\n"
            url = f"{base}{target}" if base else ""
            html_body = _notification_email_html(
                "Application update available",
                "A new version of Outlaw's Inventory is ready to install.",
                [("Available version", f"v{version}")],
                "Open Application Version" if url else "",
                url,
                "#f59e0b",
                f"Checked: {stamp}",
            )
            ok, _ = send_notification_email(
                f"Outlaw's Inventory: Update available (v{version})", body, html_body
            )
            if ok:
                sent += 1
            else:
                failed_keys.append((key, fingerprint))

        if general_events:
            event_count = len(general_events)
            plural = "s" if event_count != 1 else ""
            verb = "require" if event_count != 1 else "requires"
            lines = [f"Outlaw's Inventory found {event_count} item{plural} that {verb} attention:", ""]
            for _key, _fingerprint, text, path in general_events:
                lines.append(f"- {text}" + (f"\n  {base}{path}" if base else ""))
            lines += ["", f"Checked: {stamp}"]
            html_items = []
            for key, _fingerprint, text, _path in general_events:
                category = "System Checks" if key.startswith(("health:", "updates:", "appupdates:")) else "Firmware"
                html_items.append((category, text))
            target_url = base if base else ""
            has_critical = any("critical" in text.lower() or "failed" in text.lower() for _key, _fingerprint, text, _path in general_events)
            html_body = _notification_email_html(
                f"{event_count} item{plural} {verb} attention",
                "Outlaw's Inventory detected an item that needs review." if event_count == 1 else "Outlaw's Inventory detected new items that need review.",
                html_items,
                "Open Dashboard" if target_url else "",
                target_url,
                "#ef4444" if has_critical else "#f59e0b",
                f"Checked: {stamp}",
            )
            ok, _ = send_notification_email(
                f"Outlaw's Inventory: {event_count} item{plural} {verb} attention",
                "\n".join(lines), html_body,
            )
            if ok:
                sent += len(general_events)
            else:
                failed_keys.extend((key, fingerprint) for key, fingerprint, _text, _path in general_events)

        # A failed SMTP delivery must remain eligible for a later retry. Only
        # release the exact fingerprints claimed by this dispatch attempt.
        if failed_keys:
            with db() as con:
                con.executemany(
                    """UPDATE notification_state SET active=0, updated_at=?
                       WHERE user_id=? AND event_key=? AND fingerprint=?""",
                    [(now(), user_id, key, fingerprint) for key, fingerprint in failed_keys],
                )
        return sent


def _parse_setting_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None

def _daily_check_time(settings: dict[str, str] | None = None) -> tuple[int, int]:
    raw = (settings or get_settings()).get("daily_check_time", "03:00")
    try:
        hour, minute = [int(part) for part in raw.split(":", 1)]
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except (ValueError, TypeError):
        return 3, 0

def _next_daily_run(at: datetime | None = None, settings: dict[str, str] | None = None) -> datetime:
    current = at or datetime.now()
    hour, minute = _daily_check_time(settings)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return candidate if candidate > current else candidate + timedelta(days=1)

def automatic_maintenance_schedule() -> dict[str, str]:
    settings = get_settings()
    last = _parse_setting_datetime(settings.get("daily_checks_last_successful_run") or settings.get("maintenance_last_auto_check"))
    next_run = _next_daily_run(settings=settings)
    interval = max(1, min(60, int(settings.get("default_health_check_interval_minutes", "10") or 10)))
    current = datetime.now().replace(second=0, microsecond=0)
    minutes_to_boundary = interval - (current.minute % interval)
    if minutes_to_boundary == 0:
        minutes_to_boundary = interval
    health_next = current + timedelta(minutes=minutes_to_boundary)
    return {
        "enabled": "true",
        "interval_hours": "24",
        "daily_time": settings.get("daily_check_time", "03:00"),
        "last_check": last.strftime("%Y-%m-%d %H:%M") if last else "Never",
        "next_check": next_run.strftime("%Y-%m-%d %H:%M"),
        "health_last_check": settings.get("health_last_successful_run") or "Never",
        "health_next_check": health_next.strftime("%Y-%m-%d %H:%M"),
    }


def device_profiles_catalog() -> dict[str, object]:
    return load_device_profiles_catalog(DEVICE_PROFILES_CACHE_FILE)


def _required_device_profile_entries(catalog: dict[str, object]) -> list[dict[str, object]]:
    required: dict[str, dict[str, object]] = {}
    with db() as con:
        rows = con.execute("SELECT vendor, model FROM devices WHERE COALESCE(vendor,'')<>'' AND COALESCE(model,'')<>''").fetchall()
    for row in rows:
        entry = match_device_profile(catalog, str(row["vendor"] or ""), str(row["model"] or ""))
        if entry and entry.get("id"):
            required[str(entry["id"])] = entry
    return list(required.values())


def _installed_device_profile_rows() -> list[dict[str, object]]:
    installed = []
    for profile in load_installed_device_profiles(DEVICE_PROFILES_INSTALLED_DIR):
        identity = profile.get("device") or {}
        installed.append({
            "id": str(profile.get("id") or ""),
            "vendor": str(identity.get("vendor") or ""),
            "model": str(identity.get("model") or ""),
            "origin": str(profile.get("origin") or "community").title(),
            "profile_version": int(profile.get("profile_version", 0) or 0),
            "status": str(profile.get("status") or ""),
        })
    installed.sort(key=lambda item: (str(item["vendor"]).lower(), str(item["model"]).lower()))
    return installed


def device_profiles_status() -> dict[str, object]:
    settings = get_settings()
    catalog = device_profiles_catalog()
    installed = _installed_device_profile_rows()
    return {
        "catalog_version": int(catalog.get("catalog_version", 0) or 0) if isinstance(catalog, dict) else 0,
        "available_profiles": len(catalog.get("profiles", [])) if isinstance(catalog, dict) else 0,
        "installed_profiles": len(installed),
        "profiles": installed,
        "last_checked": settings.get("device_profiles_last_checked", "") or "Never",
        "last_updated": settings.get("device_profiles_last_updated", "") or "Never",
        "profiles_updated": int(settings.get("device_profiles_last_update_count", "0") or 0),
        "last_error": settings.get("device_profiles_last_error", ""),
        "repository": "OutlawNL/outlaws-inventory-device-profiles",
        "catalog_url": DEVICE_PROFILES_CATALOG_URL,
    }


def sync_device_profiles() -> dict[str, object]:
    before = device_profiles_catalog()
    before_catalog_version = int(before.get("catalog_version", 0) or 0)
    stamp = now()
    with db() as con:
        con.execute("INSERT INTO settings(key,value) VALUES('device_profiles_last_attempt',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (stamp,))
    try:
        catalog = sync_device_profiles_catalog(
            DEVICE_PROFILES_CACHE_FILE,
            url=DEVICE_PROFILES_CATALOG_URL,
            user_agent=f"OutlawsInventory/{APP_VERSION}",
        )
        installed_updates = 0
        required_entries = _required_device_profile_entries(catalog)
        required_ids = {str(entry.get("id") or "") for entry in required_entries if entry.get("id")}
        profile_errors: list[str] = []
        for entry in required_entries:
            try:
                _profile, changed = ensure_device_profile(
                    DEVICE_PROFILES_INSTALLED_DIR,
                    entry,
                    user_agent=f"OutlawsInventory/{APP_VERSION}",
                )
                if changed:
                    installed_updates += 1
            except Exception as exc:
                profile_errors.append(f"{entry.get('id')}: {exc}")
        removed = prune_device_profiles(DEVICE_PROFILES_INSTALLED_DIR, required_ids)
        installed = _installed_device_profile_rows()
        catalog_changed = before_catalog_version != int(catalog.get("catalog_version", 0) or 0)
        changed_anything = catalog_changed or installed_updates > 0 or removed > 0
        error_text = "; ".join(profile_errors)[:500]
        with db() as con:
            values = {
                "device_profiles_last_checked": stamp,
                "device_profiles_catalog_version": str(catalog.get("catalog_version", 0) or 0),
                "device_profiles_installed_count": str(len(installed)),
                "device_profiles_last_update_count": str(installed_updates),
                "device_profiles_last_error": error_text,
            }
            if changed_anything:
                values["device_profiles_last_updated"] = stamp
            for key, value in values.items():
                con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        return {
            "ok": not profile_errors,
            "updated": installed_updates,
            "removed": removed,
            "catalog": catalog,
            "installed": len(installed),
            "error": error_text,
        }
    except Exception as exc:
        with db() as con:
            con.execute("INSERT INTO settings(key,value) VALUES('device_profiles_last_error',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(exc)[:500],))
        return {"ok": False, "updated": 0, "error": str(exc)}


def _device_profile_match(vendor: str, model: str, *, sync_if_empty: bool = False) -> dict[str, object] | None:
    catalog = device_profiles_catalog()
    if sync_if_empty and not catalog.get("profiles"):
        last_attempt = _parse_setting_datetime(get_settings().get("device_profiles_last_attempt", ""))
        retry_allowed = not last_attempt or (datetime.now() - last_attempt) >= timedelta(minutes=5)
        if retry_allowed:
            result = sync_device_profiles()
            if result.get("catalog"):
                catalog = result.get("catalog") or catalog
    entry = match_device_profile(catalog, vendor, model)
    if not entry:
        return None
    try:
        profile, _changed = ensure_device_profile(
            DEVICE_PROFILES_INSTALLED_DIR,
            entry,
            user_agent=f"OutlawsInventory/{APP_VERSION}",
        )
        return profile
    except Exception as exc:
        raise RuntimeError("Matched Device Profile is temporarily unavailable.") from exc

def _available_device_profile(vendor, model, **kwargs):
    try:
        return _device_profile_match(vendor, model, **kwargs)
    except RuntimeError:
        return None


def _profile_for_device(device: sqlite3.Row, *, sync_if_empty: bool = False) -> dict[str, object] | None:
    return _device_profile_match(str(device["vendor"] or ""), str(device["model"] or ""), sync_if_empty=sync_if_empty)


def _resolved_firmware_provider(device: sqlite3.Row) -> str:
    configured = ((device["firmware_provider"] if "firmware_provider" in device.keys() else "") or "Auto").strip()
    if configured and configured.lower() != "auto":
        return configured
    return infer_provider(device["vendor"] or "", device["model"] or "", device["firmware_url"] or "")


def _firmware_monitoring_supported(device: sqlite3.Row) -> bool:
    """Return False only for providers that cannot produce reliable results."""
    return _resolved_firmware_provider(device).strip().lower() != "brother"


def execute_all_firmware_checks() -> int:
    devices = [
        d for d in fetch_devices()
        if category_config(d["category"]).get("show_firmware", True)
        and _firmware_monitoring_supported(d)
        and (d["auto_check"] or d["lifecycle"] in ("Discontinued", "End of Support"))
    ]
    for device in devices:
        try:
            info = check_device(device)
        except Exception as exc:
            info = {"status": "unknown", "latest": "", "release_date": "", "summary": f"Firmware check failed: {exc}", "notes_url": device["firmware_url"] or "", "confidence": "Unknown"}
        with db() as con:
            con.execute(
                """UPDATE devices SET status=?, latest_firmware=?, release_date=?, release_summary=?, release_notes_url=?, confidence=?, firmware_source=?, check_method=?, last_checked=?, updated_at=? WHERE id=?""",
                (info["status"], info.get("automatic_latest", info["latest"]), info["release_date"], info["summary"], info["notes_url"], info["confidence"], info.get("source", device["firmware_source"] or "Unknown"), info.get("method", device["check_method"] or "Not configured"), now(), now(), device["id"]),
            )
    return len(devices)


def run_due_maintenance_checks(force: bool = False) -> str:
    settings = get_settings()
    current = datetime.now().replace(second=0, microsecond=0)
    hour, minute = _daily_check_time(settings)
    last = _parse_setting_datetime(settings.get("daily_checks_last_successful_run") or settings.get("maintenance_last_auto_check"))
    if not force:
        if (current.hour, current.minute) < (hour, minute):
            return "not due"
        if last and last.date() == current.date():
            return "already completed today"
    if not _update_scheduler_lock.acquire(blocking=False):
        return "already running"
    try:
        errors: list[str] = []
        # Device Profiles are refreshed before any external update/firmware work,
        # so the daily checks use the newest validated catalog available.
        profile_sync = sync_device_profiles()
        # A catalog outage must never make the daily maintenance run fail. Cached
        # profiles remain usable and the sync error is visible under Settings.
        user_ids = _active_user_ids()
        # Security and operating-system state first. A failure for one account
        # must not prevent the other accounts or later stages from running.
        for user_id in user_ids:
            token = _CURRENT_USER_ID.set(user_id)
            try:
                execute_all_update_checks()
            except Exception as exc:
                errors.append(f"system user {user_id}: {exc}")
            finally:
                _CURRENT_USER_ID.reset(token)
        for user_id in user_ids:
            token = _CURRENT_USER_ID.set(user_id)
            try:
                execute_all_application_checks()
            except Exception as exc:
                errors.append(f"application checks user {user_id}: {exc}")
            finally:
                _CURRENT_USER_ID.reset(token)
        try:
            check_application_release()
        except Exception as exc:
            errors.append(f"application: {exc}")
        for user_id in user_ids:
            token = _CURRENT_USER_ID.set(user_id)
            try:
                execute_all_firmware_checks()
            except Exception as exc:
                errors.append(f"firmware user {user_id}: {exc}")
            finally:
                _CURRENT_USER_ID.reset(token)
        stamp = now()
        with db() as con:
            con.execute("INSERT INTO settings(key,value) VALUES ('daily_checks_last_attempt_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (stamp,))
            con.execute("INSERT INTO settings(key,value) VALUES ('daily_checks_last_error',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("; ".join(errors)[:1000],))
            if not errors:
                for key in ("daily_checks_last_successful_run", "maintenance_last_auto_check", "system_update_last_auto_check"):
                    con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, stamp))
        if errors:
            raise RuntimeError("; ".join(errors))
        return f"completed for {len(user_ids)} active user(s)"
    finally:
        _update_scheduler_lock.release()

def _version_key(version: str) -> tuple:
    parts = []
    for part in re.split(r"[._-]", version.strip().lower().lstrip("v")):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    # Treat semantically equal versions such as 2.2 and 2.2.0 as equal.
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _firmware_status(current: str | None, latest: str | None) -> str:
    current = (current or "").strip()
    latest = (latest or "").strip()
    if not latest or not current:
        return "unknown"
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    # Safety rule: a provider result older than the installed firmware is not reliable enough.
    # Do not report OK or Update from stale DJI PDFs or stale support pages.
    if latest_key < current_key:
        return "unknown"
    return "attention" if latest_key > current_key else "ok"


def _profile_versions_are_comparable(current: str, latest: str, firmware: dict) -> bool:
    """Apply an optional Device Profile format rule before ordering versions.

    A shared Release Notes document can contain unrelated products whose version
    schemes look numeric but cannot safely be compared. Profiles may declare
    the installed-version format they expect; a mismatch is Unknown, never an
    inferred update.
    """
    comparison = (firmware.get("version_comparison") or {}) if isinstance(firmware, dict) else {}
    current_pattern = str(comparison.get("current_version_pattern") or "").strip()
    if not current_pattern or not current or not latest:
        return True
    try:
        return bool(re.fullmatch(current_pattern, current))
    except re.error:
        return False


def _clean_summary(text: str) -> str:
    soup = BeautifulSoup(text or "", "html.parser")
    plain = soup.get_text(" ", strip=True)
    plain = re.sub(r"\s+", " ", plain)
    return plain[:260]


def _bullets_from_text(text: str, max_items: int = 3) -> str:
    if not text:
        return ""
    # split on sentence boundaries and semicolons; keep short practical bullets
    pieces = re.split(r"(?<=[.!?])\s+|;\s+|\n+", _clean_summary(text))
    bullets = []
    for p in pieces:
        p = p.strip(" -•\t")
        if len(p) < 4:
            continue
        bullets.append(p[:180])
        if len(bullets) >= max_items:
            break
    return "\n".join(bullets)



def _norm_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _target_keys(device: sqlite3.Row | None) -> list[str]:
    if not device:
        return []
    keys = []
    for field in ("firmware_identifier", "firmware_lookup", "model", "display_name", "name"):
        try:
            val = (device[field] or "").strip()
        except Exception:
            val = ""
        if val:
            n = _norm_key(val)
            if len(n) >= 4 and n not in keys:
                keys.append(n)
    return keys


def _row_matches_device(text: str, device: sqlite3.Row | None) -> bool:
    if not device:
        return False
    row_norm = _norm_key(text)
    for key in _target_keys(device):
        if key and key in row_norm:
            return True
    return False


def _extract_date_as_iso(text: str) -> str:
    m = re.search(r"\b(20[0-9]{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20[0-9]{2})\b", text)
    if m:
        a, b, y = m.groups()
        ai, bi = int(a), int(b)
        # Source pages can be DD-MM-YYYY or MM-DD-YYYY. If the second value is >12,
        # treat it as US-style month-day-year.
        if ai <= 12 and bi > 12:
            mo, d = ai, bi
        else:
            d, mo = ai, bi
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return ""


# v0.2.3 Firmware Catalog
# This is deliberately conservative: known products get known official results,
# unknown or ambiguous products stay Unknown instead of guessed.
FIRMWARE_CATALOG = [
    {
        "vendor": "GL.iNet",
        "models": ["GL-MT3000", "MT3000", "Beryl AX", "GL.iNet Beryl AX"],
        "latest": "4.8.1",
        "release_date": "2025-08-19",
        "summary": "Stable firmware release from the official GL.iNet download center.",
        "notes_url": "https://dl.gl-inet.com/release/router/release/mt3000/4.8.1",
        "source": "Official GL.iNet download center",
        "method": "GL.iNet provider",
        "confidence": "Official",
    },
    {
        "vendor": "Garmin",
        "models": ["GPSMAP 67", "Garmin GPSMAP 67"],
        "latest": "9.46",
        "release_date": "2026-06-25",
        "summary": "Firmware release from the official Garmin GPSMAP 67 Series release notes.",
        "notes_url": "https://support.garmin.com/en-US/?faq=kwZJwxVAEw4RfyoRvRWW5A",
        "source": "Official Garmin support",
        "method": "Garmin provider",
        "confidence": "Official",
    },
    {
        "vendor": "Fujifilm",
        "models": ["XF150-600mmF5.6-8 R LM OIS WR", "XF 150-600", "XF150-600", "Fujifilm XF 150-600"],
        "latest": "",
        "release_date": "",
        "summary": "No model-specific firmware release is currently published for this lens. Use Latest version override for the known baseline; automatic checks remain enabled.",
        "notes_url": "https://www.fujifilm-x.com/global/support/download/firmware/lenses/",
        "source": "Official Fujifilm website",
        "method": "Fujifilm provider",
        "confidence": "Unknown",
    },
    {
        "vendor": "Fujifilm",
        "models": ["instax mini Evo", "INSTAX mini Evo", "Mini Evo", "Fujifilm Instax mini Evo"],
        "latest": "1.09",
        "release_date": "",
        "summary": "Enhanced Bluetooth pairing for improved security; future smartphone app update planned to enable direct firmware downloads in-app.",
        "notes_url": "https://instax.com/mini_evo/en/support/firmware/",
        "source": "Official instax website",
        "method": "Firmware Catalog",
        "confidence": "Official",
    },
    {
        "vendor": "Canon",
        "models": ["PIXMA PRO-200", "Canon PIXMA PRO-200", "PRO-200", "Pixma Pro 200"],
        "latest": "2.010",
        "release_date": "2026-06-25",
        "summary": "Firmware Ver. 2.010 from the official Canon Europe PIXMA PRO-200 firmware page.",
        "notes_url": "https://www.canon-europe.com/support/consumer/products/printers/pixma/pro-series/pixma-pro-200.html?type=firmware",
        "source": "Official Canon Europe website",
        "method": "Firmware Catalog",
        "confidence": "Official",
    },
    {
        "vendor": "Brother",
        "models": ["DCP-L3510CDW", "Brother DCP-L3510CDW"],
        "latest": "",
        "release_date": "",
        "summary": "Brother exposes a Firmware Update Tool on the official support page. Tool versions such as ZD/1.60 are not printer firmware versions, so the printer firmware stays Unknown until a direct Brother firmware endpoint is mapped.",
        "notes_url": "https://support.brother.com/g/b/downloadlist.aspx?c=as_ot&lang=en&prod=dcpl3510cdw_eu_as&os=10088",
        "source": "Official Brother support page",
        "method": "Brother Firmware Update Tool",
        "confidence": "Official",
    },
    {
        "vendor": "UGREEN",
        "models": ["DXP2800", "UGREEN DXP2800", "UGREEN NASync DXP2800"],
        "latest": "",
        "release_date": "",
        "summary": "UGREEN NAS firmware is not exposed reliably enough by the public download page yet. Keep as Unknown until a direct system firmware endpoint is mapped.",
        "notes_url": "https://nas.ugreen.com/pages/downloads",
        "source": "Official UGREEN NAS download page",
        "method": "Firmware Catalog",
        "confidence": "Unknown",
    },
    {
        "vendor": "Ricoh",
        "models": ["GR III", "GRIII", "Ricoh GR III"],
        "latest": "2.10",
        "release_date": "2025-03-27",
        "summary": "Firmware information retrieved from the official Ricoh GR III firmware page.",
        "notes_url": "https://www.ricoh-imaging.co.jp/english/support/digital/gr3.html",
        "source": "Official Ricoh website",
        "method": "Firmware Catalog",
        "confidence": "Official",
    },
    {
        "vendor": "Arturia",
        "models": ["MiniFuse 2", "Arturia MiniFuse 2"],
        "latest": "1.5.0.212",
        "release_date": "2024-10-08",
        "summary": "Hardware firmware entry matched from the Arturia product/support information, excluding bundled software versions.",
        "notes_url": "https://www.arturia.com/support/downloads&manuals",
        "source": "Official Arturia website",
        "method": "Firmware Catalog",
        "confidence": "Official",
    },
    {
        "vendor": "Arturia",
        "models": ["MiniLab MkII", "MiniLab MK II", "MiniLab Mk2", "MiniLab MK2", "Arturia MiniLab MK II"],
        "latest": "1.1.2.1689",
        "release_date": "2021-12-30",
        "summary": "Hardware firmware entry matched from the Arturia product/support information, excluding Analog Lab and bundled software versions.",
        "notes_url": "https://www.arturia.com/support/downloads&manuals",
        "source": "Official Arturia website",
        "method": "Firmware Catalog",
        "confidence": "Official",
    },
]


def _catalog_match(device: sqlite3.Row | None) -> dict[str, str] | None:
    if not device:
        return None
    vendor_key = _norm_key((device["vendor"] or ""))
    candidate_values = []
    for field in ("firmware_lookup", "model", "display_name", "name"):
        try:
            val = (device[field] or "").strip()
        except Exception:
            val = ""
        if val:
            candidate_values.append(_norm_key(val))
    if not candidate_values:
        return None
    for item in FIRMWARE_CATALOG:
        item_vendor = _norm_key(item["vendor"])
        if vendor_key and item_vendor and vendor_key != item_vendor and item_vendor not in vendor_key and vendor_key not in item_vendor:
            continue
        model_keys = [_norm_key(m) for m in item["models"]]
        for ck in candidate_values:
            for mk in model_keys:
                if not ck or not mk:
                    continue
                # Exact normalized match is preferred; containment supports short UI names
                # such as "XF 16-80" against the official Fujifilm model name.
                if ck == mk or ck in mk or mk in ck:
                    return item
    return None


def _catalog_result(device: sqlite3.Row) -> dict[str, str] | None:
    item = _catalog_match(device)
    if not item:
        return None
    latest = item.get("latest", "")
    current = (device["current_firmware"] or "").strip()
    status = _firmware_status(current, latest)
    return {
        "status": status,
        "latest": latest,
        "release_date": item.get("release_date", ""),
        "summary": item.get("summary", ""),
        "notes_url": item.get("notes_url", ""),
        "confidence": item.get("confidence", "Official"),
        "source": item.get("source", "Official website"),
        "method": item.get("method", "Firmware Catalog"),
    }



# v0.2.9: conservative DJI knowledge base.
# DJI does not offer a stable public latest-firmware API for all consumer products.
# These entries are used before the generic DJI PDF parser, so known devices do not
# regress to stale release-note PDFs or unrelated app/software versions.
DJI_STATIC_CATALOG = [
    {
        "models": ["O4 Air Unit Pro", "DJI O4 Air Unit Pro"],
        "latest": "01.00.06.00",
        "release_date": "2026-03-25",
        "summary": "Latest known O4 Air Unit Pro firmware from official DJI release notes. Fixed minor bugs.",
        "notes_url": "https://dl.djicdn.com/downloads/DJI_O4_Air_Unit_Series/RN/20260325/DJI_O4_Air_Unit_Series_Release_Notes_en.pdf",
        "source": "Official DJI release notes",
        "method": "DJI Knowledge Base",
        "confidence": "Official",
    },
    {
        "models": ["O4 Air Unit", "O4 Air Unit Lite", "DJI O4 Air Unit", "DJI O4 Air Unit Lite"],
        "latest": "01.00.06.00",
        "release_date": "2026-03-25",
        "summary": "Latest known O4 Air Unit firmware from official DJI release notes. Fixed minor bugs.",
        "notes_url": "https://dl.djicdn.com/downloads/DJI_O4_Air_Unit_Series/RN/20260325/DJI_O4_Air_Unit_Series_Release_Notes_en.pdf",
        "source": "Official DJI release notes",
        "method": "DJI Knowledge Base",
        "confidence": "Official",
    },
    {
        "models": ["DJI Goggles N3", "Goggles N3"],
        "latest": "01.00.0500",
        "release_date": "2025-07-29",
        "summary": "Added lock screen settings. Fixed known issues.",
        "notes_url": "https://dl.djicdn.com/downloads/DJI_Goggles_N3/20251030/DJI_Goggles_N3_Release_Notes_EN.pdf",
        "source": "Official DJI release notes",
        "method": "DJI Knowledge Base",
        "confidence": "Official",
    },
    {
        "models": ["DJI Mic Mini", "Mic Mini"],
        "latest": "01.01.00.56",
        "release_date": "2025-07-23",
        "summary": "Optimized stability. Fixed known issues.",
        "notes_url": "https://dl.djicdn.com/downloads/DJI_Mic_Mini/20260421/DJI_Mic_Mini_Release_Notes_EN_20260421.pdf",
        "source": "Official DJI release notes",
        "method": "DJI Knowledge Base",
        "confidence": "Official",
    },

    {
        "models": ["DJI Osmo Action 4", "Osmo Action 4"],
        "latest": "01.04.07.10",
        "release_date": "2024-11-26",
        "summary": "Latest known Osmo Action 4 firmware from DJI release notes/download information.",
        "notes_url": "https://www.dji.com/osmo-action-4/downloads",
        "source": "Official DJI Download Center",
        "method": "DJI Knowledge Base",
        "confidence": "Official",
    },
    {
        "models": ["DJI Osmo 360", "Osmo 360"],
        "latest": "01.03.07.70",
        "release_date": "",
        "summary": "Baseline Osmo 360 firmware. DJI sources can lag behind installed firmware; the app will not report older public release notes as latest.",
        "notes_url": "https://www.dji.com/360/downloads",
        "source": "DJI Download Center / installed baseline",
        "method": "DJI Knowledge Base",
        "confidence": "Manual",
    },
]

def _dji_static_match(device: sqlite3.Row | None) -> dict[str, str] | None:
    if not device:
        return None
    vendor = _norm_key(device["vendor"] or "")
    if vendor and "dji" not in vendor:
        return None
    candidates = []
    for field in ("firmware_lookup", "model", "display_name", "name"):
        try:
            val = (device[field] or "").strip()
        except Exception:
            val = ""
        if val:
            candidates.append(_norm_key(val))
    for item in DJI_STATIC_CATALOG:
        model_keys = [_norm_key(m) for m in item["models"]]
        for ck in candidates:
            for mk in model_keys:
                if ck == mk or ck in mk or mk in ck:
                    return item
    return None

def _dji_static_result(device: sqlite3.Row) -> dict[str, str] | None:
    item = _dji_static_match(device)
    if not item:
        return None
    latest = item.get("latest", "")
    current = (device["current_firmware"] or "").strip()
    # Never use installed/current firmware as Latest. If the stored DJI knowledge
    # base is older than the installed firmware, the source is stale: show Unknown.
    if current and latest and _version_key(latest) < _version_key(current):
        latest = ""
    return {
        "status": _firmware_status(current, latest),
        "latest": latest,
        "release_date": item.get("release_date", ""),
        "summary": item.get("summary", ""),
        "notes_url": item.get("notes_url", ""),
        "confidence": item.get("confidence", "Unknown"),
        "source": item.get("source", "DJI"),
        "method": item.get("method", "DJI Knowledge Base"),
    }


DJI_DOWNLOAD_CATALOG = [
    {
        "models": ["Osmo 360", "DJI Osmo 360"],
        "downloads_url": "https://www.dji.com/360/downloads",
        "label": "Osmo 360 - Release Notes",
    },
    {
        "models": ["Mini 4 Pro", "DJI Mini 4 Pro", "mini 4 Pro"],
        "downloads_url": "https://www.dji.com/mini-4-pro/downloads",
        "label": "DJI Mini 4 Pro - Release Notes",
    },
    {
        "models": ["Osmo Action 4", "DJI Osmo Action 4"],
        "downloads_url": "https://www.dji.com/osmo-action-4/downloads",
        "label": "Osmo Action 4 - Release Notes",
    },
    {
        "models": ["O4 Air Unit", "O4 Air Unit Pro", "DJI O4 Air Unit", "DJI O4 Air Unit Pro", "O4 Air Unit Lite", "DJI O4 Air Unit Lite"],
        "downloads_url": "https://www.dji.com/global/o4-air-unit/downloads",
        "label": "DJI O4 Air Unit Series - Release Notes",
    },
]


def _dji_catalog_match(device: sqlite3.Row | None) -> dict[str, str] | None:
    if not device:
        return None
    vendor = _norm_key(device["vendor"] or "")
    if vendor and "dji" not in vendor:
        return None
    candidate_values = []
    for field in ("firmware_lookup", "model", "display_name", "name"):
        val = (device[field] or "").strip()
        if val:
            candidate_values.append(_norm_key(val))
    for item in DJI_DOWNLOAD_CATALOG:
        model_keys = [_norm_key(m) for m in item["models"]]
        for ck in candidate_values:
            for mk in model_keys:
                if ck == mk or ck in mk or mk in ck:
                    return item
    return None


def _latest_release_notes_from_download_page(downloads_url: str, label: str = "Release Notes") -> tuple[str, str]:
    """Return (pdf_url, release_date_iso) for the matching DJI Release Notes entry.

    DJI download pages frequently embed document URLs in escaped JSON rather than
    plain anchor tags. Normalize those encodings first, then prefer a Release Notes
    PDF near the requested product label.
    """
    try:
        resp = requests.get(downloads_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception:
        return "", ""

    raw_html = resp.text or ""
    normalized = unescape(raw_html)
    # Common JSON/script encodings used by DJI pages.
    normalized = normalized.replace("\\/", "/")
    normalized = re.sub(r"\\u002[fF]", "/", normalized)
    normalized = re.sub(r"\\u003[aA]", ":", normalized)
    normalized = re.sub(r"\\u002[dD]", "-", normalized)
    try:
        normalized = unquote(normalized)
    except Exception:
        pass

    label_patterns = [label, "Release Notes", "Versionshinweise", "Note di rilascio"]
    # Search near the requested product label first. This avoids accidentally
    # selecting DJI Assistant release notes from the same download page.
    windows: list[str] = []
    lower = normalized.lower()
    for pattern in label_patterns:
        needle = pattern.lower()
        pos = 0
        while needle and (idx := lower.find(needle, pos)) >= 0:
            windows.append(normalized[max(0, idx - 5000): idx + 9000])
            pos = idx + len(needle)

    def pdf_candidates(text: str) -> list[str]:
        values = re.findall(r"https?://[^\"'<>\s]+?\.pdf(?:\?[^\"'<>\s]*)?", text, flags=re.I)
        cleaned: list[str] = []
        for value in values:
            value = value.rstrip("),];}")
            if value not in cleaned:
                cleaned.append(value)
        return cleaned

    requested_tokens = [token for token in re.findall(r"[a-z0-9]+", label.lower()) if token not in {"dji", "release", "notes", "note"}]

    def score(url: str) -> tuple[int, int]:
        low = url.lower()
        points = 0
        if "release" in low and "note" in low:
            points += 40
        if "assistant" in low and "assistant" not in label.lower():
            points -= 80
        points += sum(12 for token in requested_tokens if token in re.sub(r"[^a-z0-9]+", "", low))
        # Newer DJI documents normally carry YYYYMMDD in the path.
        dates = [int(value) for value in re.findall(r"20\d{6}", low)]
        return points, max(dates or [0])

    candidates: list[str] = []
    for window in windows:
        candidates.extend(pdf_candidates(window))
    candidates.extend(pdf_candidates(normalized))
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        # Fall back to ordinary links in case the page is server-rendered.
        soup = BeautifulSoup(normalized, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href") or "")
            if ".pdf" not in href.lower():
                continue
            absolute = href if href.startswith("http") else requests.compat.urljoin(downloads_url, href)
            candidates.append(absolute)

    release_candidates = [url for url in candidates if "release" in url.lower() and "note" in url.lower()]
    ranked = sorted(release_candidates or candidates, key=score, reverse=True)
    pdf_url = ranked[0] if ranked else ""

    soup = BeautifulSoup(normalized, "html.parser")
    text = soup.get_text("\n", strip=True)
    release_date = ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if any(pattern.lower() in line.lower() for pattern in label_patterns):
            release_date = _extract_date_as_iso(" ".join(lines[index:index + 6]))
            if release_date:
                break
    return pdf_url, release_date


def _text_from_pdf_url(pdf_url: str) -> str:
    if not pdf_url or PdfReader is None:
        return ""
    try:
        resp = requests.get(pdf_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        reader = PdfReader(BytesIO(resp.content))
        chunks = []
        for page in reader.pages[:3]:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(chunks)
    except Exception:
        return ""


def _extract_dji_firmware_version(pdf_text: str, device: sqlite3.Row) -> str:
    if not pdf_text:
        return ""
    model_text = " ".join([(device["model"] or ""), (device["display_name"] or ""), (device["name"] or "")]).lower()
    lines = [ln.strip() for ln in pdf_text.splitlines() if ln.strip()]
    preferred = []
    if "o4" in model_text and "air" in model_text:
        preferred = [ln for ln in lines if "o4" in ln.lower() and "firmware" in ln.lower()]
    elif "mini 4" in model_text:
        preferred = [ln for ln in lines if ("aircraft firmware" in ln.lower() or "mini 4" in ln.lower())]
    elif "osmo action 4" in model_text or "action 4" in model_text:
        preferred = [ln for ln in lines if "firmware" in ln.lower() and ("action" in ln.lower() or "camera" in ln.lower())]
    elif "osmo 360" in model_text or "360" in model_text:
        preferred = [ln for ln in lines if "firmware" in ln.lower() and ("360" in ln.lower() or "camera" in ln.lower())]
    search_text = "\n".join(preferred) if preferred else pdf_text
    patterns = [
        r"Firmware[^\n:：]*[:：]?\s*v?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{2})",
        r"Firmware[^\n:：]*[:：]?\s*v?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
        r"\bv\s*([0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{2})\b",
        r"\bv\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})\b",
    ]
    candidates = []
    for pat in patterns:
        candidates.extend(re.findall(pat, search_text, flags=re.I))
    candidates = [c.strip().lstrip("v") for c in candidates]
    if not candidates:
        return ""
    return sorted(set(candidates), key=_version_key)[-1]


def _extract_dji_profile_firmware_version(pdf_text: str, firmware_labels: list[str]) -> str:
    if not pdf_text:
        return ""
    lines = [line.strip() for line in pdf_text.splitlines() if line.strip()]
    candidates: list[str] = []
    labels = [label.lower() for label in firmware_labels if label]
    for index, line in enumerate(lines):
        if labels and not any(label in line.lower() for label in labels):
            continue
        window = " ".join(lines[index:index + 3])
        for pattern in (
            r"(?:Firmware[^:：\n]*)?[:：]?\s*[Vv]?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
            r"(?:Firmware[^:：\n]*)?[:：]?\s*[Vv]?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{2}\.[0-9]{2})",
        ):
            candidates.extend(re.findall(pattern, window, flags=re.I))
    if not candidates:
        return ""
    return sorted(set(value.lstrip("vV") for value in candidates), key=_version_key)[-1]


def _profile_normalize_html(raw_html: str) -> str:
    normalized = unescape(raw_html or "")
    normalized = normalized.replace("\\/", "/")
    normalized = re.sub(r"\\u002[fF]", "/", normalized)
    normalized = re.sub(r"\\u003[aA]", ":", normalized)
    normalized = re.sub(r"\\u002[dD]", "-", normalized)
    try:
        normalized = unquote(normalized)
    except Exception:
        pass
    return normalized


def _profile_pdf_candidates(text: str, base_url: str) -> list[str]:
    values = re.findall(r"https?://[^\"'<>\s]+?\.pdf(?:\?[^\"'<>\s]*)?", text, flags=re.I)
    soup = BeautifulSoup(text, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if ".pdf" not in href.lower():
            continue
        values.append(href if href.startswith("http") else requests.compat.urljoin(base_url, href))
    cleaned: list[str] = []
    for value in values:
        value = value.rstrip("),];}")
        if value not in cleaned:
            cleaned.append(value)
    return cleaned


def _discover_profile_document(source_url: str, discovery: dict) -> tuple[str, str]:
    """Discover a document using only declarative Device Profile rules.

    The core knows how to normalize an HTML page and rank document links. The
    profile supplies the product/document title and URL hints. No device name is
    hard-coded here.
    """
    try:
        response = _document_get(requests, source_url, timeout=20, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
        response.raise_for_status()
    except Exception:
        return "", ""
    try:
        document_url = profile_documents.discover(response.text or "", response.url or source_url, discovery)
        return document_url, ""
    except Exception:
        return "", ""


def _extract_profile_labeled_value(text: str, rule: dict) -> str:
    labels = [str(value).strip() for value in (rule.get("labels") or []) if str(value).strip()]
    pattern = str(rule.get("pattern") or "").strip()
    group = int(rule.get("group", 1) or 1)
    max_lines = max(1, min(int(rule.get("max_lines", 12) or 12), 30))
    if not text or not labels or not pattern:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        low = line.lower()
        for label in labels:
            pos = low.find(label.lower())
            if pos < 0:
                continue
            tail = line[pos + len(label):].strip()
            scopes = [tail] if tail else []
            # PDF table extraction can emit all labels first and all values later.
            # The profile controls how far the generic parser may look ahead.
            for offset in range(1, max_lines + 1):
                if index + offset < len(lines):
                    scopes.append(lines[index + offset])
            scopes.append(" ".join(lines[index:index + max_lines + 1]))
            for scope in scopes:
                match = re.search(pattern, scope, flags=re.I)
                if match:
                    try:
                        return match.group(group).strip().lstrip("vV")
                    except IndexError:
                        return match.group(0).strip().lstrip("vV")
    return ""


def _extract_profile_labeled_date(text: str, rule: dict) -> str:
    labels = [str(value).strip() for value in (rule.get("labels") or []) if str(value).strip()]
    formats = [str(value).strip() for value in (rule.get("formats") or []) if str(value).strip()]
    max_lines = max(1, min(int(rule.get("max_lines", 12) or 12), 30))
    if not text or not labels:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    date_re = re.compile(r"\b(20\d{2}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{1,2}[.\-/]\d{1,2}[.\-/]20\d{2})\b")
    for index, line in enumerate(lines):
        low = line.lower()
        for label in labels:
            pos = low.find(label.lower())
            if pos < 0:
                continue
            tail = line[pos + len(label):].strip()
            scopes = [tail] if tail else []
            for offset in range(1, max_lines + 1):
                if index + offset < len(lines):
                    scopes.append(lines[index + offset])
            # Use the first date after the declared label that matches a declared format.
            for scope in scopes:
                for match in date_re.finditer(scope):
                    candidate = match.group(1)
                    for fmt in formats:
                        try:
                            return datetime.strptime(candidate, fmt).date().isoformat()
                        except (ValueError, TypeError):
                            continue
            # Backward-compatible fallback, still constrained to the declared look-ahead window.
            nearby = " ".join(scopes)
            fallback = _extract_date_as_iso(nearby)
            if fallback:
                return fallback
    return ""

def _extract_profile_section(text: str, rule: dict) -> str:
    start_labels = [str(v).strip() for v in (rule.get("start_labels") or []) if str(v).strip()]
    end_labels = [str(v).strip() for v in (rule.get("end_labels") or []) if str(v).strip()]
    max_items = max(1, min(int(rule.get("max_items", 3) or 3), 10))
    if not text or not start_labels:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    start = None
    for index, line in enumerate(lines):
        normalized = line.lower().replace("’", "'")
        if any(label.lower().replace("’", "'") in normalized for label in start_labels):
            start = index + 1
            break
    if start is None:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        normalized = lines[index].lower().replace("’", "'")
        if any(normalized == label.lower().replace("’", "'") or normalized.startswith(label.lower().replace("’", "'")) for label in end_labels):
            end = index
            break
    body = lines[start:end]
    items: list[str] = []
    current = ""
    bullet_re = re.compile(r"^[•●▪◦*\-–—]\s*(.+)$")
    numbered_re = re.compile(r"^\d+[.)]\s+(.+)$")
    for line in body:
        bullet = bullet_re.match(line) or numbered_re.match(line)
        if bullet:
            if current:
                items.append(current.strip())
            current = bullet.group(1).strip()
        elif current:
            current += " " + line
        elif line:
            # Some PDF extractors strip bullet glyphs entirely. Treat a standalone
            # sentence/paragraph as an item rather than falling back to document-wide text.
            items.append(line.strip())
    if current:
        items.append(current.strip())
    cleaned: list[str] = []
    for item in items:
        item = re.sub(r"\s+", " ", item).strip()
        if item and item not in cleaned:
            cleaned.append(item)
        if len(cleaned) >= max_items:
            break
    return "\n".join(cleaned)


def _release_notes_pdf_profile_result(device: sqlite3.Row, profile: dict) -> dict[str, str]:
    firmware = profile.get("firmware") or {}
    source = firmware.get("source") or {}
    discovery = firmware.get("discovery") or {}
    extraction = firmware.get("extraction") or {}
    source_url = str(source.get("url") or "").strip()
    pdf_url, _ = _discover_profile_document(source_url, discovery)
    pdf_text = ""
    if pdf_url:
        try:
            response = _document_get(requests, pdf_url, timeout=30, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
            response.raise_for_status()
            pdf_text = response.content
        except Exception:
            pass
    try:
        extracted = profile_documents.extract_pdf(pdf_text, firmware)
    except Exception:
        extracted = {"latest": "", "release_date": "", "summary": "", "error": "Device Profile extraction rules could not be applied."}
    latest = extracted["latest"]
    release_date = extracted["release_date"]
    summary = extracted["summary"]
    current = (device["current_firmware"] or "").strip().lstrip("vV")
    latest = (latest or "").strip().lstrip("vV")
    comparison_safe = _profile_versions_are_comparable(current, latest, firmware)
    if comparison_safe and current and latest and _version_key(latest) < _version_key(current):
        latest = ""
        release_date = ""
    error = extracted["error"]
    if not pdf_url:
        error = "Device Profile matched, but its Release Notes document could not be discovered from the configured source."
        summary = ""
    elif not pdf_text:
        error = "Release Notes PDF was found, but its text could not be read."
        summary = ""
    elif not latest and not error:
        error = "Release Notes PDF was read, but the profile's firmware-version rule did not produce a valid value."
        summary = ""
    profile_name = str((profile.get("device") or {}).get("model") or profile.get("id") or "device")
    origin = str(profile.get("origin") or "").strip().title()
    return {
        "status": _firmware_status(current, latest) if comparison_safe else "unknown",
        "latest": latest,
        "release_date": release_date,
        "summary": summary,
        "notes_url": pdf_url or source_url,
        "confidence": origin if latest else "Unknown",
        "source": "Device Profile source",
        "method": f"Device Profile · {profile_name}",
        "error": error,
        "_comparison_safe": comparison_safe,
    }


def _html_profile_result(device: sqlite3.Row, profile: dict) -> dict[str, str]:
    firmware = profile.get("firmware") or {}
    source = firmware.get("source") or {}
    discovery = firmware.get("discovery") or {}
    extraction = firmware.get("extraction") or {}
    source_url = str(source.get("url") or "").strip()
    pdf_url = source_url
    pdf_text = ''
    try:
        response = _document_get(requests, source_url, timeout=30, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
        response.raise_for_status()
        pdf_text = response.text
        extracted = profile_documents.extract_html(pdf_text, firmware)
    except Exception:
        extracted = {"latest": "", "release_date": "", "summary": "", "error": "Firmware page could not be read using the Device Profile."}
    latest = extracted["latest"]
    release_date = extracted["release_date"]
    summary = extracted["summary"]
    current = (device["current_firmware"] or "").strip().lstrip("vV")
    latest = (latest or "").strip().lstrip("vV")
    if current and latest and _version_key(latest) < _version_key(current):
        latest = ""
        release_date = ""
    error = extracted["error"]
    if not pdf_url:
        error = "Device Profile matched, but its Release Notes document could not be discovered from the configured source."
        summary = ""
    elif not pdf_text:
        error = "Firmware page was found, but its text could not be read."
        summary = ""
    elif not latest and not error:
        error = "Firmware page was read, but the profile's firmware-version rule did not produce a valid value."
        summary = ""
    profile_name = str((profile.get("device") or {}).get("model") or profile.get("id") or "device")
    origin = str(profile.get("origin") or "").strip().title()
    return {
        "status": _firmware_status(current, latest),
        "latest": latest,
        "release_date": release_date,
        "summary": summary,
        "notes_url": pdf_url or source_url,
        "confidence": origin if latest else "Unknown",
        "source": "Device Profile source",
        "method": f"Device Profile · {profile_name}",
        "error": error,
    }


def _device_profile_result(device: sqlite3.Row) -> dict[str, str] | None:
    try:
        profile = _profile_for_device(device, sync_if_empty=True)
    except Exception:
        return {"status": "unknown", "latest": "", "release_date": "", "summary": "Matched Device Profile is temporarily unavailable.", "notes_url": device["firmware_url"] or "", "confidence": "Unknown", "source": "Device Profile source", "method": "Device Profile", "error": "Matched Device Profile is temporarily unavailable."}
    if not profile:
        return None
    firmware = profile.get("firmware") or {}
    strategy = str(firmware.get("strategy") or "").strip()
    if strategy == "html_release":
        return _html_profile_result(device, profile)
    if strategy == "release_notes_pdf":
        return _release_notes_pdf_profile_result(device, profile)
    # Backward compatibility with the first experimental v0.18.0/0.18.1 catalog.
    # New profiles must use declarative `release_notes_pdf` rules instead.
    if strategy != "dji_release_notes_pdf":
        return None
    source = firmware.get("source") or {}
    downloads_url = str(source.get("url") or "").strip()
    release_notes = firmware.get("release_notes") or {}
    labels = [str(value) for value in (release_notes.get("labels") or ["Release Notes"]) if value]
    firmware_labels = [str(value) for value in (release_notes.get("firmware_labels") or []) if value]
    pdf_url, page_release_date = _latest_release_notes_from_download_page(downloads_url, labels[0] if labels else "Release Notes")
    pdf_text = _text_from_pdf_url(pdf_url)
    latest = _extract_dji_profile_firmware_version(pdf_text, firmware_labels)
    if not latest:
        latest = _extract_dji_firmware_version(pdf_text, device)
    release_date = _extract_date_as_iso(pdf_text[:3000]) or page_release_date
    current = (device["current_firmware"] or "").strip().lstrip("vV")
    latest = (latest or "").strip().lstrip("vV")
    if current and latest and _version_key(latest) < _version_key(current):
        latest = ""
        release_date = ""
    if not pdf_url:
        summary = "Device Profile matched, but no Release Notes PDF could be discovered on the configured download page."
    elif not pdf_text:
        summary = "Release Notes PDF was found, but its text could not be read."
    else:
        summary = _bullets_from_text(pdf_text, 3) or "Release Notes PDF was read, but no firmware version could be extracted reliably."
    profile_name = str((profile.get("device") or {}).get("model") or profile.get("id") or "device")
    return {
        "status": _firmware_status(current, latest),
        "latest": latest,
        "release_date": release_date,
        "summary": summary,
        "notes_url": pdf_url or downloads_url,
        "confidence": "Official" if latest else "Unknown",
        "source": "Device Profile source",
        "method": f"Device Profile · {profile_name}",
    }

def _dji_result(device: sqlite3.Row) -> dict[str, str] | None:
    item = _dji_catalog_match(device)
    if not item:
        return None
    pdf_url, release_date = _latest_release_notes_from_download_page(item["downloads_url"], item.get("label", "Release Notes"))
    pdf_text = _text_from_pdf_url(pdf_url)
    latest = _extract_dji_firmware_version(pdf_text, device)
    current = (device["current_firmware"] or "").strip()
    if current and latest and _version_key(latest) < _version_key(current):
        # Stale DJI release-note result: do not present an older version as Latest.
        latest = ""
    summary = _bullets_from_text(pdf_text, 3) if pdf_text else "Official DJI release notes found, but no firmware version could be extracted reliably."
    return {
        "status": _firmware_status(device["current_firmware"], latest),
        "latest": latest,
        "release_date": release_date,
        "summary": summary,
        "notes_url": pdf_url or item["downloads_url"],
        "confidence": "Official" if latest else "Unknown",
        "source": "Official DJI Download Center" if pdf_url else "Official DJI Download Center",
        "method": "DJI Download Center",
    }




# v0.2.12: Creality Cloud is the preferred source for Creality printers.
# Do not use the older creality.com product download pages when a Creality Cloud
# firmware page is known; those pages can lag behind the printer/OTA firmware.
CREALITY_STATIC_CATALOG = [
    {
        "models": ["K1 Max", "Creality K1 Max"],
        "variant": "Monochrome",
        "mainboard": "CR4CU220812S11",
        "latest": "1.3.5.22",
        "release_date": "2026-07-10",
        "summary": "Latest known official Creality Cloud firmware for K1 Max Monochrome with mainboard CR4CU220812S11.",
        "notes_url": "https://www.crealitycloud.com/downloads/firmware/flagship-series/k1-max",
        "source": "Official Creality Cloud firmware page",
        "method": "Creality Cloud Knowledge Base",
        "confidence": "Official",
    },
    {
        "models": ["K1 Max CFS", "K1 Max Multicolor", "Creality K1 Max CFS", "Creality K1 Max Multicolor"],
        "variant": "Multicolor/CFS",
        "mainboard": "",
        "latest": "2.3.5.34",
        "release_date": "2025-12-30",
        "summary": "Latest known official Creality Cloud firmware for K1 Max CFS/Multicolor configurations.",
        "notes_url": "https://www.crealitycloud.com/downloads/firmware/flagship-series/k1-max",
        "source": "Official Creality Cloud firmware page",
        "method": "Creality Cloud Knowledge Base",
        "confidence": "Official",
    },
    {
        "models": ["Ender 3 V3 KE", "Ender-3 V3 KE", "Creality Ender 3 V3 KE", "Creality Ender-3 V3 KE"],
        "variant": "",
        "mainboard": "HWCR4NS200320C13",
        "latest": "1.1.0.17",
        "release_date": "2025-08-27",
        "summary": "Latest known official Creality Cloud firmware for Ender-3 V3 KE.",
        "notes_url": "https://www.crealitycloud.com/downloads/firmware/ender-series/ender-3-v3-ke",
        "source": "Official Creality Cloud firmware page",
        "method": "Creality Cloud Knowledge Base",
        "confidence": "Official",
    },
]


def _device_search_blob(device: sqlite3.Row | None) -> str:
    if not device:
        return ""
    parts = []
    for field in ("firmware_lookup", "model", "display_name", "name", "notes"):
        try:
            parts.append(str(device[field] or ""))
        except Exception:
            pass
    return " ".join(parts)


def _creality_static_match(device: sqlite3.Row | None) -> dict[str, str] | None:
    if not device:
        return None
    vendor = _norm_key(device["vendor"] or "")
    if vendor and "creality" not in vendor:
        return None
    blob = _device_search_blob(device)
    blob_norm = _norm_key(blob)

    # K1 Max has separate Monochrome and CFS/Multicolor firmware tracks.
    if "k1max" in blob_norm:
        if any(word in blob_norm for word in ("cfs", "multicolor", "multicolour", "multi", "kleur")):
            return next((i for i in CREALITY_STATIC_CATALOG if i.get("variant") == "Multicolor/CFS"), None)
        return next((i for i in CREALITY_STATIC_CATALOG if "K1 Max" in i.get("models", []) and i.get("variant") == "Monochrome"), None)

    for item in CREALITY_STATIC_CATALOG:
        model_keys = [_norm_key(m) for m in item["models"]]
        for mk in model_keys:
            if mk and (mk in blob_norm or blob_norm in mk):
                return item
    return None


def _creality_ota_candidates(html: str, item: dict[str, str]) -> list[tuple[str, str]]:
    """Return (version, filename/context) candidates from Creality OTA image filenames only.

    Important rule: do not scan arbitrary page text for version-like numbers.
    Creality pages contain many unrelated numbers (viewer/app/package versions).
    The firmware version must come from a firmware/OTA image filename such as:
    - Ender-3_V3_KE_F005_ota_img_V1.1.0.17.img
    - ...K1_Max...ota_img_V1.3.5.19.img
    """
    if not html:
        return []
    # Decode common escaped slashes from JSON blobs in the page source.
    haystack = html.replace("\\/", "/")
    # Capture compact chunks containing an OTA IMG filename or URL.
    chunks = re.findall(r"[^\s\"'<>]{0,160}ota[^\s\"'<>]{0,160}\.img", haystack, flags=re.I)
    chunks += re.findall(r"[^\s\"'<>]{0,160}V[0-9]+(?:[._][0-9]+){2,5}[^\s\"'<>]{0,160}\.img", haystack, flags=re.I)

    variant = (item.get("variant") or "").lower()
    model_names = " ".join(item.get("models", []))
    model_norm = _norm_key(model_names)
    mainboard = _norm_key(item.get("mainboard", ""))

    candidates: list[tuple[str, str]] = []
    for chunk in chunks:
        c_norm = _norm_key(chunk)
        # Model-specific filters. These are intentionally strict to avoid wrong tracks.
        if "ender3v3ke" in model_norm:
            if not all(k in c_norm for k in ("ender3", "v3", "ke")):
                continue
        elif "k1max" in model_norm:
            if not ("k1" in c_norm and "max" in c_norm):
                continue
            if "monochrome" in variant:
                # CFS/Multicolor is a separate 2.x firmware track.
                if any(x in c_norm for x in ("cfs", "multicolor", "multicolour")):
                    continue
            elif "multicolor" in variant or "cfs" in variant:
                # Prefer explicit CFS/multicolor chunks when possible, but do not require it
                # because Creality filenames are not always consistently named.
                pass

        if mainboard and mainboard not in c_norm:
            # Some filenames omit the board id, so only require this when it appears to be a
            # mixed page with multiple board identifiers.
            board_like = re.findall(r"cr4cu[0-9a-z]+|hwcr[0-9a-z]+", c_norm)
            if board_like:
                continue

        for m in re.finditer(r"[Vv]([0-9]+(?:[._][0-9]+){2,5})", chunk):
            version = m.group(1).replace("_", ".")
            if "monochrome" in variant and version.startswith("2."):
                continue
            candidates.append((version, chunk))
    # Deduplicate
    seen = set()
    out = []
    for v, c in candidates:
        if v not in seen:
            seen.add(v)
            out.append((v, c))
    return out


def _creality_cloud_live_version(item: dict[str, str]) -> tuple[str, str]:
    """Best-effort live check against the official Creality Cloud page.

    v0.2.13 rule: only accept firmware versions parsed from OTA .img filenames.
    If no matching OTA image is visible in the page source, fall back to the known
    catalog value instead of guessing from unrelated page text.
    """
    url = item.get("notes_url", "")
    if not url:
        return item.get("latest", ""), item.get("release_date", "")
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
        resp.raise_for_status()
    except Exception:
        return item.get("latest", ""), item.get("release_date", "")

    candidates = _creality_ota_candidates(resp.text, item)
    if not candidates:
        return item.get("latest", ""), item.get("release_date", "")

    latest, context = sorted(candidates, key=lambda vc: _version_key(vc[0]))[-1]
    # Date near the filename if available; otherwise keep the catalog date.
    idx = resp.text.find(context)
    window = resp.text[max(0, idx - 500): idx + 500] if idx >= 0 else context
    release_date = _extract_date_as_iso(window) or item.get("release_date", "")
    return latest, release_date


def _creality_static_result(device: sqlite3.Row) -> dict[str, str] | None:
    item = _creality_static_match(device)
    if not item:
        return None
    latest, release_date = _creality_cloud_live_version(item)
    current = (device["current_firmware"] or "").strip().lstrip("vV")
    latest = (latest or "").strip().lstrip("vV")
    # Safety rule: never present an older public page as Latest.
    if current and latest and _version_key(latest) < _version_key(current):
        latest = ""
        release_date = ""
    return {
        "status": _firmware_status(current, latest),
        "latest": latest,
        "release_date": release_date if latest else "",
        "summary": item.get("summary", ""),
        "notes_url": item.get("notes_url", ""),
        "confidence": item.get("confidence", "Unknown") if latest else "Unknown",
        "source": item.get("source", "Creality"),
        "method": item.get("method", "Creality Cloud Knowledge Base"),
    }



def _glinet_model_slug(device: sqlite3.Row | None) -> str:
    """Return the official GL.iNet download slug for supported models."""
    if not device:
        return ""
    text = " ".join(
        str(device[field] or "")
        for field in ("firmware_identifier", "firmware_lookup", "model", "display_name", "name")
        if field in device.keys()
    ).lower()
    if any(token in text for token in ("gl-mt3000", "mt3000", "beryl ax")):
        return "mt3000"
    return ""


def _parse_glinet_listing(html: str) -> tuple[str, str, str]:
    """Extract newest stable version, date and link from an official GL.iNet listing.

    The download center is a JavaScript application. Depending on the response,
    releases may appear as rendered table rows or as embedded JSON. Version and
    date are therefore paired by proximity and never selected independently.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str, str]] = []

    # First preference: an actual rendered table row/card.
    for node in soup.find_all(["tr", "li", "article", "section", "div"]):
        text = node.get_text(" ", strip=True)
        versions = re.findall(r"(?<!\d)(\d+\.\d+(?:\.\d+){1,3})(?!\d)", text)
        if not versions:
            continue
        date = _extract_date_as_iso(text)
        link = node.find("a", href=True)
        href = str(link.get("href") or "") if link else ""
        for version in versions:
            if len(version.split(".")) >= 3:
                candidates.append((version, date, href))

    # Fallback for the Vue/JSON payload returned by dl.gl-inet.com.
    raw = BeautifulSoup(html, "html.parser").get_text(" ", strip=True) + " " + html
    for match in re.finditer(r"(?<!\d)(\d+\.\d+(?:\.\d+){1,3})(?!\d)", raw):
        version = match.group(1)
        if len(version.split(".")) < 3:
            continue
        window = raw[max(0, match.start()-900):match.end()+900]
        date = _extract_date_as_iso(window)
        href_match = re.search(r"https?://[^\s\"'<>]+", window)
        candidates.append((version, date, href_match.group(0) if href_match else ""))

    if not candidates:
        return "", "", ""
    version, date, href = sorted(candidates, key=lambda item: (_version_key(item[0]), bool(item[1]), bool(item[2])))[-1]
    return version, date, href


def _glinet_result(device: sqlite3.Row) -> dict[str, str] | None:
    vendor_text = " ".join(str(device[field] or "") for field in ("vendor", "display_name", "name") if field in device.keys()).lower()
    slug = _glinet_model_slug(device)
    if "gl.i" not in vendor_text and "gl-inet" not in vendor_text and not slug:
        return None
    if not slug:
        return None
    url = (device["firmware_url"] or "").strip() or f"https://dl.gl-inet.com/router/{slug}/stable"
    try:
        response = requests.get(url, timeout=15, allow_redirects=True, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
        response.raise_for_status()
        latest, release_date, href = _parse_glinet_listing(response.text)
    except Exception:
        return None
    if not latest:
        return None
    notes_url = requests.compat.urljoin(response.url or url, href) if href else (response.url or url)
    return {
        "status": _firmware_status(device["current_firmware"], latest),
        "latest": latest,
        "release_date": release_date,
        "summary": "Stable firmware release from the official GL.iNet download center.",
        "notes_url": notes_url,
        "confidence": "Official",
        "source": "Official GL.iNet download center",
        "method": "GL.iNet provider",
    }

def _onkyo_model(device: sqlite3.Row) -> str:
    text = " ".join(str(device[field] or "") for field in ("firmware_identifier", "model", "display_name", "name") if field in device.keys())
    match = re.search(r"\b((?:HT-R|TX-NR)\d{3,4})\b", text, re.I)
    return match.group(1).upper() if match else ""


def _onkyo_result(device: sqlite3.Row) -> dict[str, str] | None:
    model = _onkyo_model(device)
    vendor = " ".join(str(device[field] or "") for field in ("vendor", "display_name", "name") if field in device.keys()).lower()
    if "onkyo" not in vendor and not model:
        return None
    if not model:
        return None
    slug = model.lower()
    urls = [
        (device["firmware_url"] or "").strip(),
        f"https://onkyo.com/{slug}",
        f"https://onkyo.com/receivers/{slug}",
    ]
    for url in [u for i,u in enumerate(urls) if u and u not in urls[:i]]:
        try:
            response = requests.get(url, timeout=18, allow_redirects=True, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
            response.raise_for_status()
        except Exception:
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        if model.lower() not in text.lower() and model.lower() not in (response.url or url).lower():
            continue
        firmware_nodes = []
        for node in soup.find_all(["a", "li", "p", "div"]):
            node_text = node.get_text(" ", strip=True)
            if "firmware" in node_text.lower() and ("update" in node_text.lower() or "latest" in node_text.lower()):
                firmware_nodes.append(node)
        context = " ".join(n.get_text(" ", strip=True) for n in firmware_nodes)
        latest = _extract_version(context) if context else ""
        release_date = _extract_date_as_iso(context) if context else ""
        notes_url = response.url or url
        for node in firmware_nodes:
            link = node if getattr(node, "name", "") == "a" else node.find("a", href=True)
            if link and link.get("href"):
                notes_url = requests.compat.urljoin(response.url or url, str(link.get("href")))
                break
        # Older Onkyo pages may expose only an official firmware download link,
        # not a machine-readable version. Keep that as managed/Unknown.
        return {
            "status": _firmware_status(device["current_firmware"], latest) if latest else "unknown",
            "latest": latest,
            "release_date": release_date,
            "summary": f"Official Onkyo firmware source for {model}." if latest else f"Official Onkyo firmware page found for {model}, but no reliable version could be extracted.",
            "notes_url": notes_url,
            "confidence": "Official",
            "source": "Official Onkyo product support",
            "method": "Onkyo provider",
        }
    return None


def _provider_name(device: sqlite3.Row | None) -> str:
    vendor = ((device["vendor"] if device else "") or "").strip().lower()
    name = (display_name(device) if device else "").strip().lower()
    url = ((device["firmware_url"] if device else "") or "").strip().lower()
    if "fujifilm" in vendor or "fujifilm" in name or "fujifilm-x.com" in url:
        return "fujifilm"
    if "ricoh" in vendor or "ricoh" in name:
        return "ricoh"
    if "arturia" in vendor or "arturia" in name:
        return "arturia"
    if "dji" in vendor or name.startswith("dji"):
        return "dji"
    if "onkyo" in vendor or "onkyo" in name:
        return "onkyo"
    return "generic"


def _candidate_blocks(soup: BeautifulSoup, device: sqlite3.Row | None) -> list[str]:
    """Return chunks that likely describe exactly this model."""
    blocks: list[str] = []
    # Tables first: firmware vendor pages often keep version/date/description in one row.
    for row in soup.find_all("tr"):
        row_text = row.get_text(" | ", strip=True)
        if _row_matches_device(row_text, device):
            blocks.append(row_text)
    # Then list/card/paragraph style pages.
    for selector in ["li", "article", "section", "div", "p"]:
        for node in soup.find_all(selector):
            txt = node.get_text(" | ", strip=True)
            if 20 <= len(txt) <= 1500 and _row_matches_device(txt, device):
                if txt not in blocks:
                    blocks.append(txt)
    return blocks[:8]


def _extract_version(text: str) -> str:
    patterns = [
        r"(?:Ver\.?|Version|Firmware(?: Version)?|Firmware update)\s*[:：]?\s*v?\s*([0-9]+(?:[._][0-9]+){1,5})",
        r"\bv\s*([0-9]+(?:[._][0-9]+){1,5})\b",
    ]
    candidates: list[str] = []
    for pat in patterns:
        candidates += re.findall(pat, text, flags=re.I)
    # Drop obvious software-major versions on hardware device pages when possible.
    candidates = [c.replace("_", ".") for c in candidates]
    return sorted(set(candidates), key=_version_key)[-1] if candidates else ""


def _summarize_block(block: str, device: sqlite3.Row | None, version: str) -> str:
    summary = block
    for term in [
        (device["firmware_lookup"] if device and "firmware_lookup" in device.keys() else ""),
        (device["model"] if device else ""),
        display_name(device) if device else "",
        (device["vendor"] if device else ""),
        version,
    ]:
        if term:
            summary = re.sub(re.escape(term), "", summary, flags=re.I)
    summary = re.sub(r"(?:Ver\.?|Version|Firmware(?: Version)?|Firmware update)\s*[:：]?\s*v?\s*[0-9]+(?:[._][0-9]+){1,5}", "", summary, flags=re.I)
    summary = re.sub(r"20[0-9]{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20[0-9]{2}", "", summary)
    summary = summary.replace("|", ". ")
    return _bullets_from_text(summary)



def _github_release_result(device: sqlite3.Row, source_url: str) -> dict[str, str] | None:
    """Retrieve and normalize the newest stable release through the GitHub provider."""
    result = fetch_github_latest_stable(source_url, APP_VERSION)
    if result is None:
        return None
    latest = result.get("latest", "")
    summary = _bullets_from_text(result.get("summary", ""), 3)
    if latest and not summary:
        summary = f"Stable GitHub release {result.get('tag') or latest}."
    return {
        "status": _firmware_status(device["current_firmware"], latest) if latest else "unknown",
        "latest": latest,
        "release_date": result.get("release_date", ""),
        "summary": summary or result.get("summary", ""),
        "notes_url": result.get("notes_url", source_url),
        "confidence": result.get("confidence", "API"),
        "source": result.get("source", "GitHub Releases API"),
        "method": result.get("method", "Official website"),
    }


def parse_firmware_info(html: str, device: sqlite3.Row | None = None, source_url: str = "") -> dict[str, str]:
    """Provider-based firmware parser.

    v0.2.2 rule: vendor-specific providers beat broad generic parsing. If the
    provider cannot connect a version to the exact model/lookup key, it returns
    Unknown instead of guessing.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    provider = _provider_name(device)
    result = {"latest_version": "", "release_date": "", "summary": "", "notes_url": source_url or "", "confidence": "Unknown"}

    # Manual: use data already filled in by the user; no parsing.
    check_method = ((device["check_method"] if device and "check_method" in device.keys() else "") or "").lower()
    fw_source = ((device["firmware_source"] if device and "firmware_source" in device.keys() else "") or "").lower()
    if check_method == "manual" or fw_source == "manual":
        result["latest_version"] = (device["latest_firmware"] if device else "") or ""
        result["release_date"] = (device["release_date"] if device else "") or ""
        result["summary"] = (device["release_summary"] if device else "") or ""
        result["notes_url"] = (device["release_notes_url"] if device else "") or source_url or ""
        result["confidence"] = "Manual"
        return result

    # DJI: no public stable latest index yet. Official one-off PDFs are useful as
    # release-note links, but not as automatic latest sources.
    if provider == "dji":
        result["confidence"] = "Manual" if source_url else "Unknown"
        return result

    blocks = _candidate_blocks(soup, device)

    if provider in {"fujifilm", "ricoh"}:
        # Exact pages can be parsed from full text. Overview pages must match the
        # exact model or firmware_lookup row/block.
        is_overview = len(soup.find_all("tr")) > 1 or any(word in source_url.lower() for word in ["/lenses/", "/cameras/"])
        exact_page = False
        lookup_key = _norm_key((device["firmware_lookup"] if device and "firmware_lookup" in device.keys() else "") or (device["model"] if device else "") or "")
        url_key = _norm_key(source_url)
        if lookup_key and lookup_key in url_key:
            exact_page = True
        if not blocks and not exact_page:
            result["confidence"] = "Official"
            return result
        search_text = "\n".join(blocks) if blocks else text
        version = _extract_version(search_text)
        if not version:
            result["confidence"] = "Official"
            return result
        result["latest_version"] = version
        result["release_date"] = _extract_date_as_iso(search_text)
        result["summary"] = _summarize_block(blocks[0] if blocks else search_text[:1200], device, version)
        result["confidence"] = "Official"
        return result

    if provider == "arturia":
        current = ((device["current_firmware"] if device else "") or "").strip()
        blocks_text = "\n".join(blocks)
        firmware_context = blocks_text if blocks_text and "firmware" in blocks_text.lower() else ""
        # If the exact current firmware appears near the product/firmware context,
        # mark OK. Do not parse unrelated Analog Lab / software versions.
        if current and (current in firmware_context or current in text):
            result["latest_version"] = current
            result["summary"] = "No newer hardware firmware found on the source page."
            result["confidence"] = "Official"
            return result
        if firmware_context:
            version = _extract_version(firmware_context)
            if version:
                result["latest_version"] = version
                result["release_date"] = _extract_date_as_iso(firmware_context)
                result["summary"] = _summarize_block(firmware_context, device, version)
            result["confidence"] = "Official"
        return result

    # Generic provider is intentionally conservative. It only parses when a block
    # matching the exact device/model is found.
    if not blocks:
        return result
    search_text = "\n".join(blocks)
    version = _extract_version(search_text)
    if version:
        result["latest_version"] = version
        result["release_date"] = _extract_date_as_iso(search_text)
        result["summary"] = _summarize_block(blocks[0], device, version)
        result["confidence"] = "Community" if source_url else "Unknown"
    return result


def _check_device_provider(device: sqlite3.Row) -> dict[str, str]:
    # Providers marked unsupported are excluded from monitoring and never scraped.
    if not _firmware_monitoring_supported(device):
        return {"status": "unknown", "latest": "", "release_date": "", "summary": "Automatic firmware monitoring is not supported for this provider.", "notes_url": device["firmware_url"] or "", "confidence": "Unsupported", "source": "Brother update utility", "method": "Unsupported provider"}
    # Support status is separate from firmware status.
    # Discontinued devices can still be firmware-OK when they run the last known version.
    if device["lifecycle"] in ("Discontinued", "End of Support"):
        latest = device["latest_firmware"] or ""
        return {"status": _firmware_status(device["current_firmware"], latest), "latest": latest, "release_date": device["release_date"] or "", "summary": device["release_summary"] or "", "notes_url": device["release_notes_url"] or device["firmware_url"] or "", "confidence": device["confidence"] or "Unknown", "source": device["firmware_source"] or "Unknown", "method": device["check_method"] or "Not configured"}
    profile_result = _device_profile_result(device)
    if profile_result:
        return profile_result
    onkyo = _onkyo_result(device)
    if onkyo:
        return onkyo
    glinet = _glinet_result(device)
    if glinet:
        return glinet
    catalog = _catalog_result(device)
    if catalog:
        return catalog
    dji = _dji_result(device)
    if dji and dji.get("latest"):
        return dji
    dji_static = _dji_static_result(device)
    if dji_static:
        return dji_static
    if dji:
        return dji
    creality = _creality_static_result(device)
    if creality:
        return creality
    if not device["firmware_url"]:
        return {"status": "unknown", "latest": "", "release_date": "", "summary": "No firmware catalog/provider match and no reliable firmware URL configured.", "notes_url": "", "confidence": "Unknown", "source": "Unknown", "method": "Not configured"}
    try:
        github = _github_release_result(device, device["firmware_url"])
        if github is not None:
            return github
        r = requests.get(device["firmware_url"], timeout=12, headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"})
        r.raise_for_status()
        info = parse_firmware_info(r.text, device, device["firmware_url"])
        latest = info["latest_version"]
        if not latest:
            return {"status": "unknown", "latest": "", "release_date": info.get("release_date", ""), "summary": info.get("summary", "") or "No reliable firmware version could be extracted from the configured source.", "notes_url": info.get("notes_url", ""), "confidence": info.get("confidence", "Unknown"), "source": device["firmware_source"] or "Unknown", "method": device["check_method"] or "Not configured"}
        current = (device["current_firmware"] or "").strip()
        status = _firmware_status(current, latest)
        return {"status": status, "latest": latest, "release_date": info.get("release_date", ""), "summary": info.get("summary", ""), "notes_url": info.get("notes_url", ""), "confidence": info.get("confidence", "Unknown"), "source": device["firmware_source"] or "Unknown", "method": device["check_method"] or "Not configured"}
    except Exception as exc:
        return {"status": "unknown", "latest": device["latest_firmware"] or "", "release_date": device["release_date"] or "", "summary": f"Firmware check failed: {exc}", "notes_url": device["release_notes_url"] or device["firmware_url"] or "", "confidence": device["confidence"] or "Unknown", "source": device["firmware_source"] or "Unknown", "method": device["check_method"] or "Not configured"}



def _effective_latest_version(automatic: str, override: str) -> str:
    automatic = (automatic or "").strip()
    override = (override or "").strip()
    if not automatic:
        return override
    if not override:
        return automatic
    return automatic if _version_key(automatic) >= _version_key(override) else override


def check_device(device: sqlite3.Row) -> dict[str, str]:
    """Run the configured provider and apply a safe manual latest-version floor.

    The override never disables automatic checking: a newer provider result wins.
    Existing firmware data and source metadata remain untouched.
    """
    result = _check_device_provider(device)
    comparison_safe = result.pop("_comparison_safe", True)
    override = device["latest_firmware_override"] if "latest_firmware_override" in device.keys() else ""
    automatic = result.get("latest", "")
    effective = _effective_latest_version(automatic, override)
    result["automatic_latest"] = automatic
    result["latest"] = effective
    result["status"] = _firmware_status(device["current_firmware"], effective) if comparison_safe else "unknown"
    if override and effective == override and (not automatic or _version_key(override) > _version_key(automatic)):
        result["source"] = result.get("source") or "Manual"
        result["method"] = "Automatic check + manual latest override"
        if not result.get("summary"):
            result["summary"] = "Latest known version is supplied manually; automatic checks remain enabled."
    return result



def fetch_ssh_profiles() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT * FROM ssh_profiles WHERE owner_user_id=? ORDER BY name COLLATE NOCASE", (require_current_user_id(),)).fetchall()


def fetch_ssh_profile(profile_id: int) -> Optional[sqlite3.Row]:
    """Fetch an SSH profile for the currently signed-in user."""
    with db() as con:
        return con.execute("SELECT * FROM ssh_profiles WHERE id=? AND owner_user_id=?", (profile_id, require_current_user_id())).fetchone()


def fetch_ssh_profile_for_owner(profile_id: int, owner_user_id: int) -> Optional[sqlite3.Row]:
    """Fetch a profile for an explicitly known owner.

    Remote checks can run in scheduler/background contexts where no browser
    session is available.  They must therefore use the persisted owner on the
    update check rather than ``require_current_user_id()``.
    """
    with db() as con:
        return con.execute(
            "SELECT * FROM ssh_profiles WHERE id=? AND owner_user_id=?",
            (profile_id, owner_user_id),
        ).fetchone()


def _profile_for_update_check(check: sqlite3.Row) -> Optional[sqlite3.Row]:
    owner_user_id = int(check["owner_user_id"] or 0)
    if not owner_user_id:
        return None
    return fetch_ssh_profile_for_owner(int(check["ssh_profile_id"]), owner_user_id)


def fetch_update_checks() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute(
            """SELECT u.*, d.display_name, d.name AS device_name, d.hostname AS device_hostname, d.ipv4_address AS device_ipv4, d.ipv6_address AS device_ipv6, s.name AS profile_name
               FROM update_checks u
               LEFT JOIN devices d ON d.id=u.device_id
               JOIN ssh_profiles s ON s.id=u.ssh_profile_id AND s.owner_user_id=d.owner_user_id
               WHERE d.owner_user_id=? AND u.owner_user_id=?
               ORDER BY u.name COLLATE NOCASE""", (require_current_user_id(), require_current_user_id())
        ).fetchall()


def fetch_update_check(check_id: int) -> Optional[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT u.* FROM update_checks u JOIN devices d ON d.id=u.device_id WHERE u.id=? AND d.owner_user_id=? AND u.owner_user_id=?", (check_id, require_current_user_id(), require_current_user_id())).fetchone()


def fetch_device_update_check(device_id: int) -> Optional[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT * FROM update_checks WHERE device_id=? AND owner_user_id=? ORDER BY enabled DESC, name COLLATE NOCASE LIMIT 1", (device_id, require_current_user_id())).fetchone()


def update_summary() -> dict[str, int]:
    out = {"ok": 0, "available": 0, "failed": 0, "unknown": 0, "disabled": 0}
    for row in fetch_update_checks():
        if not row["enabled"]:
            out["disabled"] += 1
        elif row["status"] in out:
            out[row["status"]] += 1
        else:
            out["unknown"] += 1
    return out


def fetch_application_checks() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute(
            """SELECT a.*, d.display_name, d.name AS device_name, d.hostname AS device_hostname,
                      d.ipv4_address AS device_ipv4, s.name AS profile_name
               FROM application_checks a
               JOIN devices d ON d.id=a.device_id AND d.owner_user_id=a.owner_user_id
               JOIN ssh_profiles s ON s.id=a.ssh_profile_id AND s.owner_user_id=a.owner_user_id
               WHERE a.owner_user_id=?
               ORDER BY COALESCE(d.display_name,d.name) COLLATE NOCASE, a.application_type""",
            (require_current_user_id(),),
        ).fetchall()


def fetch_device_application_check(device_id: int, application_type: str = "pihole") -> Optional[sqlite3.Row]:
    with db() as con:
        return con.execute(
            "SELECT * FROM application_checks WHERE device_id=? AND owner_user_id=? AND application_type=? LIMIT 1",
            (device_id, require_current_user_id(), application_type),
        ).fetchone()


def _application_profile(check: sqlite3.Row) -> Optional[sqlite3.Row]:
    owner_user_id = int(check["owner_user_id"] or 0)
    if not owner_user_id:
        return None
    return fetch_ssh_profile_for_owner(int(check["ssh_profile_id"]), owner_user_id)


def _application_target(check: sqlite3.Row) -> str:
    with db() as con:
        device = con.execute(
            "SELECT hostname,ipv4_address,ipv6_address FROM devices WHERE id=? AND owner_user_id=?",
            (int(check["device_id"]), int(check["owner_user_id"])),
        ).fetchone()
    if not device:
        return ""
    return str(device["ipv4_address"] or device["hostname"] or device["ipv6_address"] or "").strip()


def _parse_pihole_check_output(output: str) -> dict[str, object]:
    clean = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output or "")
    component_labels = (
        ("core", "Pi-hole Core"),
        ("web", "Web Interface"),
        ("ftl", "FTL"),
    )
    components: list[dict[str, str]] = []
    any_available = False
    everything_ok = "everything is up to date" in clean.lower()
    for key, label in component_labels:
        match = re.search(rf"(?:\[[^\]]*\]\s*)?{re.escape(label)}:\s*([^\r\n]+)", clean, re.I)
        detail = match.group(1).strip() if match else ""
        lowered = detail.lower()
        if "up to date" in lowered:
            state = "ok"
        elif any(marker in lowered for marker in ("update available", "update is available", "out of date", "update required", "new version")):
            state = "available"
            any_available = True
        elif detail:
            state = "available" if "available" in lowered and "not available" not in lowered else "unknown"
            any_available = any_available or state == "available"
        elif everything_ok:
            state = "ok"
            detail = "up to date"
        else:
            state = "unknown"
        components.append({"key": key, "name": label, "status": state, "detail": detail or "Unknown"})
    if any_available or "update available" in clean.lower() or "updates are available" in clean.lower():
        status = "available"
    elif everything_ok or all(item["status"] == "ok" for item in components):
        status = "ok"
    else:
        status = "unknown"
    return {"status": status, "components": components, "output": clean.strip()[-12000:]}


def _minecraft_version_from_jar(client: paramiko.SSHClient, configured_path: str = "") -> dict[str, str]:
    # Prefer an explicit path, then inspect running Java processes. If Minecraft
    # is stopped or crash-looping, inspect systemd unit definitions and readable
    # launcher scripts so version detection still works from the configured JAR.
    probe = r'''import glob,json,os,re,shlex,subprocess,sys,zipfile
configured=sys.argv[1] if len(sys.argv)>1 else ''
candidates=[configured] if configured else []

def add_jar(value, workdir=''):
 value=(value or '').strip().strip('"\'')
 if not value: return
 if not os.path.isabs(value) and workdir:
  value=os.path.join(workdir,value)
 candidates.append(value)

def jars_from_command(command, workdir=''):
 try: argv=shlex.split(command)
 except Exception: return
 if '-jar' in argv:
  i=argv.index('-jar')
  if i+1<len(argv): add_jar(argv[i+1],workdir)

def inspect_script(path, inherited_workdir=''):
 try:
  text=open(path,encoding='utf-8',errors='replace').read()
 except Exception: return
 workdir=inherited_workdir
 for raw in text.splitlines():
  line=raw.strip()
  if not line or line.startswith('#'): continue
  m=re.match(r'^cd\s+(?:--\s+)?(.+?)(?:\s*(?:&&|;)|$)',line)
  if m:
   try:
    parts=shlex.split(m.group(1)); workdir=parts[0] if parts else workdir
   except Exception: pass
  jars_from_command(line,workdir)

# 1. Running Java processes: most precise when the server is healthy.
try:
 out=subprocess.check_output(['ps','-eo','pid=,args='],text=True,stderr=subprocess.DEVNULL)
 for line in out.splitlines():
  line=line.strip()
  if not line or 'java' not in line or '-jar' not in line: continue
  parts=line.split(None,1)
  if len(parts)!=2: continue
  pid,args=parts
  try: argv=shlex.split(args)
  except Exception: continue
  if '-jar' not in argv: continue
  i=argv.index('-jar')
  if i+1>=len(argv): continue
  jar=argv[i+1]
  workdir=''
  try: workdir=os.readlink('/proc/'+pid+'/cwd')
  except Exception: pass
  add_jar(jar,workdir)
except Exception: pass

# 2. systemd services: works even when the server is stopped or crash-looping.
try:
 units=subprocess.check_output(['systemctl','list-unit-files','--type=service','--no-legend','--no-pager'],text=True,stderr=subprocess.DEVNULL)
 for row in units.splitlines():
  fields=row.split()
  if not fields: continue
  unit=fields[0]
  if 'minecraft' not in unit.lower(): continue
  try:
   cat=subprocess.check_output(['systemctl','cat',unit,'--no-pager'],text=True,stderr=subprocess.DEVNULL)
  except Exception: continue
  workdir=''
  execstarts=[]
  for raw in cat.splitlines():
   line=raw.strip()
   if line.startswith('WorkingDirectory='):
    workdir=line.split('=',1)[1].strip()
   elif line.startswith('ExecStart='):
    execstarts.append(line.split('=',1)[1].strip())
  for command in execstarts:
   jars_from_command(command,workdir)
   try:
    argv=shlex.split(command)
   except Exception: argv=[]
   if argv:
    script=argv[0]
    if not os.path.isabs(script) and workdir: script=os.path.join(workdir,script)
    if os.path.isfile(script): inspect_script(script,workdir)
except Exception: pass

# 3. Common locations as a final fallback.
for pattern in ('/home/*/minecraft/server.jar','/opt/minecraft/server.jar','/srv/minecraft/server.jar'):
 candidates.extend(glob.glob(pattern))
candidates.append('server.jar')

seen=set()
for path in candidates:
 if not path: continue
 path=os.path.abspath(os.path.expanduser(path))
 if path in seen or not os.path.isfile(path): continue
 seen.add(path)
 try:
  with zipfile.ZipFile(path) as z: data=json.loads(z.read('version.json'))
  version=str(data.get('id') or data.get('name') or '').strip()
  if version:
   print(json.dumps({'version':version,'path':path})); raise SystemExit(0)
 except Exception: continue
raise SystemExit(2)'''
    command = f"python3 -c {shlex.quote(probe)} {shlex.quote((configured_path or '').strip())}"
    _, stdout, stderr = client.exec_command(command, timeout=30)
    out = stdout.read().decode('utf-8', 'replace').strip()
    err = stderr.read().decode('utf-8', 'replace').strip()
    code = stdout.channel.recv_exit_status()
    if code != 0 or not out:
        return {'version':'','path':'','error':err or 'Could not find/read the Minecraft server JAR.'}
    try:
        data=json.loads(out.splitlines()[-1])
        return {'version':str(data.get('version') or ''),'path':str(data.get('path') or ''),'error':''}
    except Exception:
        return {'version':'','path':'','error':'Could not parse Minecraft server version.'}


def _minecraft_runtime_status(client: paramiko.SSHClient) -> dict[str, object]:
    """Return Minecraft runtime state independently from the installed JAR version."""
    probe = r'''import json,subprocess

def run(args):
 try:
  return subprocess.check_output(args,text=True,stderr=subprocess.DEVNULL).strip()
 except Exception:
  return ''

units=[]
listing=run(['systemctl','list-units','--type=service','--all','--plain','--no-legend','--no-pager'])
for row in listing.splitlines():
 fields=row.split()
 if not fields: continue
 unit=fields[1] if fields[0]=='●' and len(fields)>1 else fields[0].lstrip('●')
 if not unit or 'minecraft' not in unit.lower(): continue
 props={}
 raw=run(['systemctl','show',unit,'--no-pager','--property=ActiveState,SubState,NRestarts,MainPID,Result'])
 for line in raw.splitlines():
  if '=' in line:
   k,v=line.split('=',1); props[k]=v
 active=(props.get('ActiveState') or '').lower()
 sub=(props.get('SubState') or '').lower()
 result=(props.get('Result') or '').lower()
 try: restarts=int(props.get('NRestarts') or 0)
 except Exception: restarts=0
 try: pid=int(props.get('MainPID') or 0)
 except Exception: pid=0
 age=None
 if pid>0:
  try: age=int(run(['ps','-o','etimes=','-p',str(pid)]) or 0)
  except Exception: age=None
 state='unknown'
 detail=' / '.join(x for x in (active,sub) if x) or 'unknown'
 if active=='failed' or sub in ('failed','auto-restart'):
  state='failed'
 elif active=='activating' and sub!='running':
  state='failed'
 elif active=='active' and sub=='running':
  state='failed' if restarts>=3 and age is not None and age<60 else 'running'
 elif active in ('inactive','deactivating') or sub in ('dead','exited'):
  state='stopped'
 if state=='failed' and restarts>=3 and age is not None and age<60:
  detail=f'crash loop ({restarts} restarts; current process {age}s old)'
 elif result and result not in ('success','') and state!='running':
  detail=f'{detail}; result {result}'
 units.append({'unit':unit,'state':state,'detail':detail,'restarts':restarts,'process_age_seconds':age,'pid':pid})

for wanted in ('running','failed','stopped','unknown'):
 for item in units:
  if item['state']==wanted:
   print(json.dumps(item)); raise SystemExit(0)

ps=run(['ps','-eo','args='])
for line in ps.splitlines():
 low=line.lower()
 if 'java' in low and '-jar' in low and ('minecraft' in low or 'server.jar' in low):
  print(json.dumps({'unit':'','state':'running','detail':'running Java server process','restarts':0,'process_age_seconds':None,'pid':0})); raise SystemExit(0)
print(json.dumps({'unit':'','state':'unknown','detail':'No Minecraft service or running Java server process was found.','restarts':0,'process_age_seconds':None,'pid':0}))'''
    command = f"python3 -c {shlex.quote(probe)}"
    _, stdout, stderr = client.exec_command(command, timeout=20)
    out = stdout.read().decode('utf-8', 'replace').strip()
    err = stderr.read().decode('utf-8', 'replace').strip()
    code = stdout.channel.recv_exit_status()
    if code != 0 or not out:
        return {'state':'unknown','unit':'','detail':err or 'Could not determine Minecraft service status.','restarts':0}
    try:
        data=json.loads(out.splitlines()[-1])
        return {
            'state': str(data.get('state') or 'unknown'),
            'unit': str(data.get('unit') or ''),
            'detail': str(data.get('detail') or ''),
            'restarts': int(data.get('restarts') or 0),
            'process_age_seconds': data.get('process_age_seconds'),
            'pid': int(data.get('pid') or 0),
        }
    except Exception:
        return {'state':'unknown','unit':'','detail':'Could not parse Minecraft service status.','restarts':0}


def _minecraft_port_status(client: paramiko.SSHClient, jar_path: str) -> dict[str, object]:
    # Read server.properties next to the JAR and verify its configured TCP port.
    probe = r'''import json,os,socket,sys
jar=os.path.abspath(os.path.expanduser(sys.argv[1] if len(sys.argv)>1 else ''))
props=os.path.join(os.path.dirname(jar),'server.properties') if jar else ''
port=25565
bind=''
if props and os.path.isfile(props):
 try:
  for raw in open(props,encoding='utf-8',errors='replace'):
   line=raw.strip()
   if not line or line.startswith('#') or '=' not in line: continue
   key,value=line.split('=',1)
   if key.strip()=='server-port':
    try: port=int(value.strip())
    except Exception: pass
   elif key.strip()=='server-ip': bind=value.strip()
 except Exception: pass
if port<1 or port>65535:
 print(json.dumps({'port':port,'listening':False,'bind':bind,'properties_path':props,'error':'Invalid server-port in server.properties.'})); raise SystemExit(0)
host=bind or '127.0.0.1'
listening=False
error=''
try:
 with socket.create_connection((host,port),timeout=2): listening=True
except Exception as exc:
 error=str(exc)
print(json.dumps({'port':port,'listening':listening,'bind':bind,'properties_path':props,'error':error}))'''
    command = f"python3 -c {shlex.quote(probe)} {shlex.quote((jar_path or '').strip())}"
    _, stdout, stderr = client.exec_command(command, timeout=10)
    out = stdout.read().decode('utf-8', 'replace').strip()
    err = stderr.read().decode('utf-8', 'replace').strip()
    code = stdout.channel.recv_exit_status()
    if code != 0 or not out:
        return {'port': 0, 'listening': False, 'bind': '', 'properties_path': '', 'error': err or 'Could not determine Minecraft server port.'}
    try:
        data = json.loads(out.splitlines()[-1])
        return {
            'port': int(data.get('port') or 0),
            'listening': bool(data.get('listening')),
            'bind': str(data.get('bind') or ''),
            'properties_path': str(data.get('properties_path') or ''),
            'error': str(data.get('error') or ''),
        }
    except Exception:
        return {'port': 0, 'listening': False, 'bind': '', 'properties_path': '', 'error': 'Could not parse Minecraft port status.'}


def _pihole_dns_status(client: paramiko.SSHClient) -> dict[str, object]:
    """Perform a real DNS query against Pi-hole on localhost without external tools."""
    probe = r'''import json,random,socket,struct,time
name='example.com'
server=('127.0.0.1',53)

def packet(txid):
 labels=b''.join(bytes([len(part)])+part.encode('ascii') for part in name.split('.'))+b'\x00'
 return struct.pack('!HHHHHH',txid,0x0100,1,0,0,0)+labels+struct.pack('!HH',1,1)

last='No DNS response received.'
for attempt in range(2):
 txid=random.randint(0,65535)
 sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
 sock.settimeout(2.0)
 try:
  sock.sendto(packet(txid),server)
  data,_=sock.recvfrom(4096)
  if len(data)<12:
   last='DNS response was too short.'; continue
  rid,flags,qd,an,ns,ar=struct.unpack('!HHHHHH',data[:12])
  if rid!=txid:
   last='DNS transaction ID mismatch.'; continue
  if not (flags & 0x8000):
   last='Received packet was not a DNS response.'; continue
  rcode=flags & 0x000f
  if rcode!=0:
   last='DNS query returned response code %d.' % rcode; continue
  if an<1:
   last='DNS responded but returned no answer records.'; continue
  print(json.dumps({'ok':True,'query':name,'answers':an,'detail':'Responding'})); raise SystemExit(0)
 except socket.timeout:
  last='DNS query timed out.'
 except Exception as exc:
  last=str(exc) or exc.__class__.__name__
 finally:
  sock.close()
 time.sleep(0.2)
print(json.dumps({'ok':False,'query':name,'answers':0,'detail':last})); raise SystemExit(1)'''
    command = f"python3 -c {shlex.quote(probe)}"
    _, stdout, stderr = client.exec_command(command, timeout=8)
    out = stdout.read().decode('utf-8', 'replace').strip()
    err = stderr.read().decode('utf-8', 'replace').strip()
    code = stdout.channel.recv_exit_status()
    try:
        data = json.loads(out.splitlines()[-1]) if out else {}
    except Exception:
        data = {}
    ok = bool(data.get('ok')) and code == 0
    detail = str(data.get('detail') or err or ('Responding' if ok else 'DNS check failed.'))
    return {
        'ok': ok,
        'query': str(data.get('query') or 'example.com'),
        'answers': int(data.get('answers') or 0),
        'detail': detail,
    }


def run_remote_application_check(check: sqlite3.Row) -> dict[str, object]:
    application_type = str(check['application_type'] or '').lower()
    if application_type not in ('pihole', 'minecraft'):
        return {'status':'failed','details':{},'error':f'Unsupported application check: {application_type}'}
    profile = _application_profile(check)
    if not profile:
        return {'status':'failed','details':{},'error':'SSH profile not found'}
    client = _ssh_client(profile)
    try:
        pkey=_load_private_key(profile['private_key_path']); hostname=_application_target(check)
        if not hostname:
            return {'status':'failed','details':{},'error':'The managed device has no reachable hostname or IP address.'}
        client.connect(hostname=hostname,port=int(profile['port'] or 22),username=profile['username'],pkey=pkey,timeout=8,auth_timeout=8,banner_timeout=8,look_for_keys=False,allow_agent=False)
        if application_type == 'minecraft':
            runtime=_minecraft_runtime_status(client)
            found=_minecraft_version_from_jar(client, str(check['minecraft_jar_path'] or ''))
            port_status=_minecraft_port_status(client, str(found.get('path') or '')) if found.get('path') else {'port':0,'listening':False,'bind':'','properties_path':'','error':''}
            details={
                'current': str(found.get('version') or ''),
                'latest': '',
                'jar_path': str(found.get('path') or ''),
                'runtime_status': str(runtime.get('state') or 'unknown'),
                'service_unit': str(runtime.get('unit') or ''),
                'runtime_detail': str(runtime.get('detail') or ''),
                'restart_count': int(runtime.get('restarts') or 0),
                'server_port': int(port_status.get('port') or 0),
                'port_listening': bool(port_status.get('listening')),
                'server_bind': str(port_status.get('bind') or ''),
                'properties_path': str(port_status.get('properties_path') or ''),
            }
            # Runtime health is authoritative. A release-metadata outage must never
            # mask a stopped service or a closed Minecraft port, nor turn a healthy
            # game server Critical merely because Mojang cannot be reached.
            runtime_state=str(runtime.get('state') or 'unknown')
            if runtime_state in ('failed','stopped'):
                label='failed' if runtime_state=='failed' else 'stopped'
                unit=f" ({runtime.get('unit')})" if runtime.get('unit') else ''
                extra=f": {runtime.get('detail')}" if runtime.get('detail') else ''
                return {'status':'failed','details':details,'error':f'Minecraft service is {label}{unit}{extra}'}
            if runtime_state != 'running':
                return {'status':'unknown','details':details,'error':runtime.get('detail') or 'Minecraft runtime status could not be determined.'}
            if found.get('path') and not port_status.get('listening'):
                port=int(port_status.get('port') or 0)
                detail=f'configured port {port}' if port else 'configured server port'
                return {'status':'failed','details':details,'error':f'Minecraft service is running but {detail} is not listening.'}
            if not found.get('version'):
                # The service can be healthy even when its JAR/version cannot be
                # inspected. Keep the diagnostic visible, but do not call the
                # running server Critical.
                return {'status':'attention','details':details,'error':found.get('error') or 'Could not read Minecraft server version.'}
            current=found['version']
            try: latest=_latest_minecraft_release()
            except Exception as exc:
                return {'status':'attention','details':details,'error':f'Could not retrieve latest Minecraft release: {exc}'}
            if not latest:
                return {'status':'attention','details':details,'error':'Could not retrieve latest Minecraft release.'}
            details['latest']=latest
            return {'status':'ok' if current==latest else 'available','details':details,'error':''}
        # Pi-hole's update checker uses Git internally. Keep the remote command
        # strictly non-interactive so an unexpected GitHub credential prompt can
        # never hold a scheduled worker open. The channel timeout is a final guard.
        _,stdout,stderr=client.exec_command("sudo -n /usr/local/bin/pihole -up --check-only </dev/null", timeout=90)
        out=stdout.read().decode('utf-8','replace'); err=stderr.read().decode('utf-8','replace').strip(); code=stdout.channel.recv_exit_status()
        combined=(out+('\n'+err if err else '')).strip()
        parsed=_parse_pihole_check_output(out)
        parsed['output']=combined[-12000:]
        dns=_pihole_dns_status(client)
        dns_component={
            'key':'dns',
            'name':'DNS',
            'status':'ok' if dns.get('ok') else 'failed',
            'detail':'Responding' if dns.get('ok') else 'Not responding',
        }
        parsed['components']=[dns_component]+list(parsed.get('components') or [])
        parsed['dns']={
            'responding':bool(dns.get('ok')),
            'query':str(dns.get('query') or 'example.com'),
            'answers':int(dns.get('answers') or 0),
            'detail':str(dns.get('detail') or ''),
        }
        if not dns.get('ok'):
            return {'status':'failed','details':parsed,'error':f"Pi-hole DNS is not responding: {dns.get('detail') or 'DNS query failed.'}"}

        lowered=combined.lower()
        permission_problem = code != 0 and any(marker in lowered for marker in ('sudoers', 'not allowed', 'a password is required', 'permission denied'))
        if permission_problem:
            error='Pi-hole check permission is missing for the managed SSH account. Reconfigure System Checks on this host once to add the fixed Pi-hole check/update permissions.'
            parsed['update_check']={'status':'failed','detail':'Permission missing'}
            return {'status':'failed','details':parsed,'error':error}

        github_problem = any(marker in lowered for marker in (
            "username for 'https://github.com",
            'could not read username for',
            'authentication failed for',
            'repository not found',
            "unable to access 'https://github.com",
            'the requested url returned error: 401',
            'the requested url returned error: 403',
        ))
        if code != 0 or parsed['status']=='unknown':
            if github_problem:
                detail='Unable to query GitHub'
                error='Pi-hole update check could not query GitHub. DNS is responding normally.'
            elif code != 0:
                detail=f'Check failed (exit code {code})'
                error='Pi-hole update check could not complete. DNS is responding normally.'
            else:
                detail='No recognized version result'
                error='Pi-hole update check could not determine Core, Web Interface and FTL versions. DNS is responding normally.'
            parsed['update_check']={'status':'unknown','detail':detail}
            parsed['components'].insert(1, {'key':'update_check','name':'Update Check','status':'unknown','detail':detail})
            return {'status':'unknown','details':parsed,'error':error}

        parsed['update_check']={'status':'ok','detail':'Completed'}
        return {'status':parsed['status'],'details':parsed,'error':''}
    except Exception as exc:
        return {'status':'failed','details':{},'error':str(exc)}
    finally:
        client.close()


def execute_pihole_dns_health_check(check: sqlite3.Row) -> None:
    """Refresh Pi-hole DNS health without doing the daily version/update check.

    The fast health cycle merges the DNS result into the last known Pi-hole
    application details so Core/Web/FTL version state remains daily while DNS
    availability is refreshed with the normal System Checks cadence.
    """
    if _device_system_checks_maintenance(check["device_id"], check["owner_user_id"]):
        return
    profile = _application_profile(check)
    if not profile:
        return
    client = _ssh_client(profile)
    try:
        pkey=_load_private_key(profile['private_key_path']); hostname=_application_target(check)
        if not hostname:
            return
        client.connect(hostname=hostname,port=int(profile['port'] or 22),username=profile['username'],pkey=pkey,timeout=8,auth_timeout=8,banner_timeout=8,look_for_keys=False,allow_agent=False)
        dns=_pihole_dns_status(client)
        try:
            previous=json.loads(str(check['details_json'] or '{}'))
        except Exception:
            previous={}
        components=[dict(c) for c in list(previous.get('components') or []) if str(c.get('key') or '').lower() != 'dns']
        components.insert(0,{
            'key':'dns',
            'name':'DNS',
            'status':'ok' if dns.get('ok') else 'failed',
            'detail':'Responding' if dns.get('ok') else 'Not responding',
        })
        previous['components']=components
        previous['dns']={
            'responding':bool(dns.get('ok')),
            'query':str(dns.get('query') or 'example.com'),
            'answers':int(dns.get('answers') or 0),
            'detail':str(dns.get('detail') or ''),
        }
        if not dns.get('ok'):
            status='failed'
            error=f"Pi-hole DNS is not responding: {dns.get('detail') or 'DNS query failed.'}"
        else:
            # Preserve the daily version/update result while refreshing DNS. An
            # update-check failure is still Unknown even though DNS is healthy,
            # and its diagnostic message must remain visible until a full check
            # succeeds.
            version_components=[c for c in components if str(c.get('key') or '').lower() not in ('dns','update_check')]
            update_state=str((previous.get('update_check') or {}).get('status') or '').lower()
            if update_state == 'unknown':
                status='unknown'
                error=str(check['last_error'] or '')
            elif any(str(c.get('status') or '').lower() == 'available' for c in version_components):
                status='available'
                error=''
            elif version_components and all(str(c.get('status') or '').lower() == 'ok' for c in version_components):
                status='ok'
                error=''
            else:
                prior=str(check['status'] or 'unknown').lower()
                status=prior if prior in ('ok','available') else 'unknown'
                error=str(check['last_error'] or '') if status == 'unknown' else ''
        with db() as con:
            con.execute("UPDATE application_checks SET status=?, details_json=?, last_checked=?, last_error=?, updated_at=? WHERE id=?",
                        (status,json.dumps(previous),now(),error,now(),check['id']))
    except Exception as exc:
        with db() as con:
            con.execute("UPDATE application_checks SET status='failed', last_checked=?, last_error=?, updated_at=? WHERE id=?",
                        (now(),f'Pi-hole DNS health refresh failed: {exc}',now(),check['id']))
    finally:
        client.close()


def execute_minecraft_runtime_check(check: sqlite3.Row) -> None:
    """Refresh Minecraft service/port health without doing the daily Mojang release lookup."""
    if _device_system_checks_maintenance(check["device_id"], check["owner_user_id"]):
        return
    profile = _application_profile(check)
    if not profile:
        return
    client = _ssh_client(profile)
    try:
        pkey=_load_private_key(profile['private_key_path']); hostname=_application_target(check)
        if not hostname: return
        client.connect(hostname=hostname,port=int(profile['port'] or 22),username=profile['username'],pkey=pkey,timeout=8,auth_timeout=8,banner_timeout=8,look_for_keys=False,allow_agent=False)
        runtime=_minecraft_runtime_status(client)
        found=_minecraft_version_from_jar(client, str(check['minecraft_jar_path'] or ''))
        port_status=_minecraft_port_status(client, str(found.get('path') or '')) if found.get('path') else {'port':0,'listening':False,'bind':'','properties_path':'','error':''}
        try: previous=json.loads(str(check['details_json'] or '{}'))
        except Exception: previous={}
        previous_error=str(check['last_error'] or '')
        release_check_attention=(
            str(check['status'] or '').lower()=='attention'
            and (
                previous_error.startswith('Could not retrieve latest Minecraft release')
                or previous_error.startswith('Could not read Minecraft server version')
                or previous_error.startswith('Could not find/read the Minecraft server JAR')
            )
        )
        latest=str(previous.get('latest') or '')
        current=str(found.get('version') or previous.get('current') or '')
        details={
            'current': current, 'latest': latest, 'jar_path': str(found.get('path') or previous.get('jar_path') or ''),
            'runtime_status': str(runtime.get('state') or 'unknown'), 'service_unit': str(runtime.get('unit') or ''),
            'runtime_detail': str(runtime.get('detail') or ''), 'restart_count': int(runtime.get('restarts') or 0),
            'server_port': int(port_status.get('port') or 0), 'port_listening': bool(port_status.get('listening')),
            'server_bind': str(port_status.get('bind') or ''), 'properties_path': str(port_status.get('properties_path') or ''),
        }
        state=details['runtime_status']; error=''
        if state in ('failed','stopped'):
            status='failed'; error=f"Minecraft service is {state}" + (f" ({details['service_unit']})" if details['service_unit'] else '')
        elif state!='running':
            status='unknown'; error=details['runtime_detail'] or 'Minecraft runtime status could not be determined.'
        elif not details['port_listening']:
            status='failed'; error=f"Minecraft service is running but configured port {details['server_port'] or 'unknown'} is not listening."
        elif release_check_attention:
            # The frequent runtime refresh verifies service/port health only. Do
            # not erase a release-check warning until the scheduled/manual
            # version lookup actually succeeds again.
            status='attention'; error=previous_error
        else:
            status='available' if latest and current and current!=latest else 'ok'
        with db() as con:
            con.execute("UPDATE application_checks SET status=?, details_json=?, last_checked=?, last_error=?, updated_at=? WHERE id=?", (status,json.dumps(details),now(),error,now(),check['id']))
    except Exception as exc:
        with db() as con:
            con.execute("UPDATE application_checks SET status='unknown', last_checked=?, last_error=?, updated_at=? WHERE id=?", (now(),f'Minecraft runtime refresh failed: {exc}',now(),check['id']))
    finally:
        client.close()


def execute_application_check(check: sqlite3.Row) -> None:
    if _device_system_checks_maintenance(check["device_id"], check["owner_user_id"]):
        return
    result = run_remote_application_check(check)
    with db() as con:
        con.execute(
            "UPDATE application_checks SET status=?, details_json=?, last_checked=?, last_error=?, updated_at=? WHERE id=?",
            (result["status"], json.dumps(result.get("details") or {}), now(), result.get("error", ""), now(), check["id"]),
        )


def execute_all_application_checks() -> dict[str, int]:
    checks = [check for check in fetch_application_checks() if check["enabled"] and not _device_system_checks_maintenance(check["device_id"], check["owner_user_id"])]
    counts = {"checked": 0, "failed": 0}
    for check in checks:
        counts["checked"] += 1
        try:
            execute_application_check(check)
            refreshed = fetch_device_application_check(int(check["device_id"]), str(check["application_type"]))
            if refreshed and refreshed["status"] == "failed":
                counts["failed"] += 1
        except Exception as exc:
            counts["failed"] += 1
            with db() as con:
                con.execute("UPDATE application_checks SET status='failed', last_checked=?, last_error=?, updated_at=? WHERE id=?",
                            (now(), f"Unexpected application-check error: {exc}", now(), check["id"]))
    return counts


def run_remote_pihole_update(check: sqlite3.Row) -> dict[str, str]:
    profile = _application_profile(check)
    if not profile:
        return {"status": "failed", "output": "SSH profile not found"}
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        hostname = _application_target(check)
        if not hostname:
            return {"status": "failed", "output": "The managed device has no reachable hostname or IP address."}
        client.connect(hostname=hostname, port=int(profile["port"] or 22), username=profile["username"],
                       pkey=pkey, timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False)
        _, stdout, stderr = client.exec_command("sudo -n /usr/local/bin/pihole -up", timeout=1800)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        combined = (out + ("\n" + err if err else "")).strip()
        if code != 0:
            if "password" in combined.lower() or "not allowed" in combined.lower() or "sudoers" in combined.lower():
                combined = "Pi-hole update permission is missing for the managed SSH account. Reconfigure System Checks on this host once to add the fixed Pi-hole check/update permissions."
            return {"status": "failed", "output": combined[-12000:] or f"Pi-hole update failed with exit code {code}"}
        return {"status": "success", "output": combined[-12000:] or "Pi-hole update completed without output."}
    except Exception as exc:
        return {"status": "failed", "output": str(exc)}
    finally:
        client.close()


def execute_pihole_update(check: sqlite3.Row) -> None:
    maintenance_snapshot = _begin_temporary_application_update_maintenance(check)
    try:
        result = run_remote_pihole_update(check)
        with db() as con:
            con.execute("UPDATE application_checks SET last_update=?, update_status=?, update_output=?, updated_at=? WHERE id=?",
                        (now(), result["status"], result.get("output", ""), now(), check["id"]))
        add_activity_event(int(check["device_id"]), int(check["owner_user_id"]), "pihole_update", "Pi-hole Update", str(result["status"]), "Pi-hole update completed." if result["status"] == "success" else "Pi-hole update failed.", str(result.get("output", "")))
    finally:
        _end_temporary_application_update_maintenance(check, maintenance_snapshot)
    refreshed = fetch_device_application_check(int(check["device_id"]), "pihole")
    if refreshed:
        execute_application_check(refreshed)


def run_remote_minecraft_update(check: sqlite3.Row) -> dict[str, str]:
    profile = _application_profile(check)
    if not profile:
        return {"status": "failed", "output": "SSH profile not found"}
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        hostname = _application_target(check)
        if not hostname:
            return {"status": "failed", "output": "The managed device has no reachable hostname or IP address."}
        client.connect(hostname=hostname, port=int(profile["port"] or 22), username=profile["username"],
                       pkey=pkey, timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False)
        runtime = _minecraft_runtime_status(client)
        found = _minecraft_version_from_jar(client, str(check['minecraft_jar_path'] or ''))
        unit = str(runtime.get('unit') or '')
        jar_path = str(found.get('path') or '')
        if not unit:
            return {"status": "failed", "output": "Could not determine the Minecraft systemd service. No update was performed."}
        if not jar_path:
            return {"status": "failed", "output": found.get('error') or "Could not determine the Minecraft server JAR. No update was performed."}
        command = f"sudo -n /usr/local/sbin/outlaws-minecraft-update {shlex.quote(unit)} {shlex.quote(jar_path)}"
        _, stdout, stderr = client.exec_command(command, timeout=1800)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        combined = (out + ("\n" + err if err else "")).strip()
        if code != 0:
            lowered = combined.lower()
            if "password" in lowered or "not allowed" in lowered or "sudoers" in lowered or "not found" in lowered:
                combined = "Minecraft update permission is not configured. Reconfigure System Checks on this host once with Minecraft enabled."
            return {"status": "failed", "output": combined[-12000:] or f"Minecraft update failed with exit code {code}"}
        return {"status": "success", "output": combined[-12000:] or "Minecraft update completed without output."}
    except Exception as exc:
        return {"status": "failed", "output": str(exc)}
    finally:
        client.close()


def execute_minecraft_update(check: sqlite3.Row) -> None:
    maintenance_snapshot = _begin_temporary_application_update_maintenance(check)
    try:
        result = run_remote_minecraft_update(check)
        with db() as con:
            con.execute("UPDATE application_checks SET last_update=?, update_status=?, update_output=?, updated_at=? WHERE id=?",
                        (now(), result["status"], result.get("output", ""), now(), check["id"]))
        try:
            before = json.loads(check["details_json"] or "{}")
        except Exception:
            before = {}
        current_version = str(before.get("current") or "").strip()
        latest_version = str(before.get("latest") or "").strip()
        summary = f"{current_version} → {latest_version}" if current_version and latest_version and current_version != latest_version else ("Minecraft update completed." if result["status"] == "success" else "Minecraft update failed.")
        add_activity_event(int(check["device_id"]), int(check["owner_user_id"]), "minecraft_update", "Minecraft Update", str(result["status"]), summary, str(result.get("output", "")))
    finally:
        _end_temporary_application_update_maintenance(check, maintenance_snapshot)
    refreshed = fetch_device_application_check(int(check["device_id"]), "minecraft")
    if refreshed:
        execute_application_check(refreshed)


def parse_apt_upgradable(output: str) -> list[dict[str, str]]:
    packages: list[dict[str, str]] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("listing") or "/" not in line or "upgradable from:" not in line:
            continue
        # Example: pkg/repo 1.2 amd64 [upgradable from: 1.1]
        m = re.match(r"([^/\s]+)/\S+\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]", line, re.I)
        if m:
            packages.append({"name": m.group(1), "new": m.group(2), "current": m.group(3)})
    return packages


def _load_private_key(path: str):
    expanded = str(Path(path).expanduser())
    errors = []
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return cls.from_private_key_file(expanded)
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("Unable to load SSH private key: " + "; ".join(errors[-2:]))


def _latest_minecraft_release() -> str:
    response = requests.get(
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
        timeout=15,
        headers={"User-Agent": f"OutlawsInventory/{APP_VERSION}"},
    )
    response.raise_for_status()
    return str(response.json().get("latest", {}).get("release", "")).strip()


def run_remote_update_check(check: sqlite3.Row) -> dict[str, object]:
    profile = _profile_for_update_check(check)
    if not profile:
        return {"status": "failed", "packages": [], "error": "SSH profile not found"}
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        client.connect(
            hostname=check["host"], port=int(profile["port"] or 22), username=profile["username"],
            pkey=pkey, timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False,
        )
        system_type = (check["system_type"] or "debian").lower()

        if system_type == "minecraft":
            jar_path = (check["minecraft_jar_path"] or "server.jar").strip()
            quoted = shlex.quote(jar_path)
            script = "import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); d=json.loads(z.read('version.json')); print(d.get('id') or d.get('name') or '')"
            command = f"python3 -c {shlex.quote(script)} {quoted}"
            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            exit_code = stdout.channel.recv_exit_status()
            current = stdout.read().decode("utf-8", "replace").strip()
            err = stderr.read().decode("utf-8", "replace").strip()
            if exit_code != 0 or not current:
                return {"status": "failed", "packages": [], "error": err or f"Could not read Minecraft version from {jar_path}"}
            latest = _latest_minecraft_release()
            if not latest:
                return {"status": "failed", "packages": [], "error": "Could not retrieve latest Minecraft release"}
            packages = [] if current == latest else [{"name": "Minecraft server", "current": current, "new": latest}]
            return {"status": "available" if packages else "ok", "packages": packages, "error": ""}

        # Refresh package metadata first. Without this step an old APT cache can
        # incorrectly report that the machine is up to date. The non-interactive
        # sudo call fails clearly when the remote account is not authorised.
        apt_update = "sudo -n /usr/bin/apt-get update"
        apt_list = "/usr/bin/apt list --upgradable 2>/dev/null"
        reboot_probe = "printf '\n__REBOOT__\n'; virt=$(/usr/bin/systemd-detect-virt 2>/dev/null || true); is_container=no; /usr/bin/systemd-detect-virt --container >/dev/null 2>&1 && is_container=yes; running=vmlinuz-$(/usr/bin/uname -r); newest=$(/usr/bin/basename $(/usr/bin/readlink -f /vmlinuz) 2>/dev/null || true); valid_newest=no; case \"$newest\" in vmlinuz-[0-9]*) valid_newest=yes ;; esac; if [ -f /run/reboot-required ]; then echo yes; cat /run/reboot-required.pkgs 2>/dev/null || true; elif [ \"$is_container\" = no ] && [ \"$valid_newest\" = yes ] && [ \"$running\" != \"$newest\" ]; then echo yes; echo kernel:$running-$newest; else echo no; fi"
        if system_type == "pihole":
            command = f"{apt_update} || exit $?; {apt_list} || exit $?; {reboot_probe}; printf '\n__PIHOLE__\n'; pihole -v 2>/dev/null || true"
        else:
            command = f"{apt_update} || exit $?; {apt_list} || exit $?; {reboot_probe}"

        stdin, stdout, stderr = client.exec_command(command, timeout=180)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            error = err or f"Remote command failed with exit code {exit_code}"
            if "password is required" in error.lower() or "a password is required" in error.lower():
                error = "APT metadata could not be refreshed: passwordless sudo is not configured for apt-get. Allow exactly /usr/bin/apt-get update and /usr/bin/apt-get upgrade -y for this SSH user."
            return {"status": "failed", "packages": [], "error": error, "reboot_required": False, "reboot_reason": ""}
        apt_output = out.split("__REBOOT__", 1)[0]
        reboot_output = out.split("__REBOOT__", 1)[1].split("__PIHOLE__", 1)[0].strip() if "__REBOOT__" in out else "no"
        reboot_lines = [line.strip() for line in reboot_output.splitlines() if line.strip()]
        reboot_required = bool(reboot_lines and reboot_lines[0] == "yes")
        reboot_reason = ", ".join(reboot_lines[1:]) if reboot_required else ""
        packages = parse_apt_upgradable(apt_output)
        return {"status": "available" if packages else "ok", "packages": packages, "error": "", "reboot_required": reboot_required, "reboot_reason": reboot_reason}
    except Exception as exc:
        return {"status": "failed", "packages": [], "error": str(exc), "reboot_required": False, "reboot_reason": ""}
    finally:
        client.close()

def run_remote_apt_upgrade(check: sqlite3.Row) -> dict[str, object]:
    profile = _profile_for_update_check(check)
    if not profile:
        return {"status": "failed", "output": "SSH profile not found"}
    if (check["system_type"] or "debian").lower() not in {"debian", "proxmox", "pihole"}:
        return {"status": "failed", "output": "This update type does not support APT upgrade."}
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        client.connect(
            hostname=check["host"], port=int(profile["port"] or 22), username=profile["username"],
            pkey=pkey, timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False,
        )

        def run(command: str, timeout: int = 1800) -> tuple[int, str]:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            return code, (out + ("\n" + err if err else "")).strip()

        output_parts: list[str] = []
        code, normal_output = run("sudo -n /usr/bin/apt-get upgrade -y")
        output_parts.append("Normal package upgrade:\n" + (normal_output or "APT upgrade completed without output."))
        if code != 0:
            combined = "\n\n".join(output_parts)
            if "password is required" in combined.lower() or "a password is required" in combined.lower():
                combined = "Upgrade could not start: passwordless sudo permission is missing for /usr/bin/apt-get upgrade -y."
            return {"status": "failed", "output": combined[-12000:]}

        # Re-check after the normal upgrade. Debian may keep kernel meta-packages
        # back during a regular upgrade, so install the exact supported package
        # in a separate, explicitly authorised phase.
        _, remaining_output = run("/usr/bin/apt list --upgradable 2>/dev/null", timeout=60)
        remaining = parse_apt_upgradable(remaining_output)
        remaining_names = {(item.get("name") or "") for item in remaining if isinstance(item, dict)}
        if "linux-image-amd64" in remaining_names:
            code, kernel_output = run("sudo -n /usr/local/sbin/outlaws-kernel-upgrade")
            output_parts.append("Kernel package upgrade:\n" + (kernel_output or "Kernel package upgrade completed without output."))
            if code != 0:
                combined = "\n\n".join(output_parts)
                if "password is required" in combined.lower() or "a password is required" in combined.lower():
                    combined += "\n\nThe dedicated kernel-upgrade wrapper permission is missing. Reconfigure the host integration once."
                return {"status": "failed", "output": combined[-12000:]}

            _, verify_output = run("/usr/bin/apt list --upgradable 2>/dev/null", timeout=60)
            verify_packages = parse_apt_upgradable(verify_output)
            if any((item.get("name") or "") == "linux-image-amd64" for item in verify_packages if isinstance(item, dict)):
                output_parts.append("Verification failed: linux-image-amd64 is still reported as upgradable.")
                return {"status": "failed", "output": "\n\n".join(output_parts)[-12000:]}

        return {"status": "success", "output": "\n\n".join(output_parts)[-12000:]}
    except Exception as exc:
        return {"status": "failed", "output": str(exc)}
    finally:
        client.close()


def run_remote_reboot(check: sqlite3.Row) -> dict[str, object]:
    profile = _profile_for_update_check(check)
    if not profile:
        return {"status": "failed", "output": "SSH profile not found"}
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        client.connect(hostname=check["host"], port=int(profile["port"] or 22), username=profile["username"], pkey=pkey,
                       timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False)
        _, stdout, stderr = client.exec_command("sudo -n /usr/sbin/reboot", timeout=15)
        try:
            exit_code = stdout.channel.recv_exit_status()
        except Exception:
            exit_code = 0
        err = stderr.read().decode("utf-8", "replace").strip()
        if exit_code != 0:
            return {"status": "failed", "output": err or f"Reboot command failed with exit code {exit_code}"}
        return {"status": "success", "output": "Reboot command accepted."}
    except Exception as exc:
        text = str(exc)
        if "closed" in text.lower() or "reset" in text.lower():
            return {"status": "success", "output": "Connection closed while rebooting, as expected."}
        return {"status": "failed", "output": text}
    finally:
        client.close()


def execute_remote_reboot(check: sqlite3.Row) -> dict[str, object]:
    old_boot = ""
    if check["device_id"]:
        device_before = fetch_device(int(check["device_id"]))
        old_boot = str(device_before["last_boot"] or "") if device_before else ""
    result = run_remote_reboot(check)
    with db() as con:
        con.execute("UPDATE update_checks SET last_reboot=?, reboot_status=?, reboot_output=?, updated_at=? WHERE id=?",
                    (now(), result["status"], result.get("output", ""), now(), check["id"]))
    if result["status"] != "success":
        return result
    import time
    time.sleep(8)
    for _ in range(36):
        time.sleep(5)
        refreshed = fetch_update_check(check["id"])
        if not refreshed:
            break
        probe = run_remote_update_check(refreshed)
        if probe.get("status") != "failed":
            execute_update_check(refreshed)
            if check["device_id"]:
                # Refresh SSH-backed checks so uptime/boot time are authoritative after reboot.
                for health in fetch_health_checks():
                    if int(health["device_id"] or 0) == int(check["device_id"]) and str(health["check_type"] or "") == "disk":
                        execute_health_check(health)
                        break
                device_after = fetch_device(int(check["device_id"]))
                new_boot = str(device_after["last_boot"] or "") if device_after else ""
                if old_boot and new_boot and old_boot == new_boot:
                    with db() as con:
                        con.execute("UPDATE update_checks SET reboot_status='failed', reboot_output=?, updated_at=? WHERE id=?", ("The host came back online, but its boot time did not change. Reboot could not be confirmed.", now(), check["id"]))
                    with db() as con:
                        con.execute("UPDATE update_checks SET reboot_status='failed', reboot_output=?, updated_at=? WHERE id=?", ("The host came back online, but its boot time did not change. Reboot could not be confirmed.", now(), check["id"]))
                    return {"status": "failed", "output": "The host came back online, but its boot time did not change. Reboot could not be confirmed."}
                if new_boot:
                    output = f"Host rebooted and came back online. Last boot: {new_boot}."
                    with db() as con:
                        con.execute("UPDATE update_checks SET reboot_status='success', reboot_output=?, updated_at=? WHERE id=?", (output, now(), check["id"]))
                    return {"status": "success", "output": output}
            return {"status": "success", "output": "Host rebooted and came back online."}
    return {"status": "success", "output": "Reboot was started, but the host did not return before the wait period ended."}


def execute_apt_upgrade(check: sqlite3.Row) -> None:
    if check["device_id"]:
        target = resolved_target(check["device_id"], check["host"])
        if target and target != (check["host"] or ""):
            with db() as con:
                con.execute("UPDATE update_checks SET host=?, updated_at=? WHERE id=?", (target, now(), check["id"]))
            check = fetch_update_check(check["id"])
    result = run_remote_apt_upgrade(check)
    with db() as con:
        con.execute(
            "UPDATE update_checks SET last_upgrade=?, upgrade_status=?, upgrade_output=?, updated_at=? WHERE id=?",
            (now(), result["status"], result.get("output", ""), now(), check["id"]),
        )
    if check["device_id"]:
        package_count = 0
        try:
            package_count = len(json.loads(check["packages_json"] or "[]"))
        except Exception:
            package_count = int(check["package_count"] or 0)
        summary = f"{package_count} package{'s' if package_count != 1 else ''} processed." if package_count else "APT upgrade executed."
        add_activity_event(int(check["device_id"]), int(check["owner_user_id"]), "system_upgrade", "System Upgrade", str(result["status"]), summary, str(result.get("output", "")))
    if result["status"] == "success":
        refreshed = fetch_update_check(check["id"])
        if refreshed:
            execute_update_check(refreshed)


_application_update_maintenance_lock = threading.Lock()
_application_update_maintenance_devices: set[tuple[int, int]] = set()


def _begin_temporary_application_update_maintenance(check: sqlite3.Row) -> list[dict[str, object]]:
    """Temporarily place one managed device in maintenance during an OI-driven application update.

    Existing user-selected maintenance state is preserved. Health rows changed by this
    operation are restored exactly afterwards, while the in-process guard prevents
    concurrent system/application schedulers from treating the planned outage as a fault.
    """
    device_id = int(check["device_id"] or 0)
    owner_user_id = int(check["owner_user_id"] or 0)
    if not device_id or not owner_user_id:
        return []
    key = (device_id, owner_user_id)
    with _application_update_maintenance_lock:
        _application_update_maintenance_devices.add(key)
    snapshot: list[dict[str, object]] = []
    try:
        t = now()
        with db() as con:
            rows = con.execute(
                "SELECT id,maintenance,status,response_ms,last_error FROM health_checks WHERE device_id=? AND owner_user_id=?",
                key,
            ).fetchall()
            for row in rows:
                if int(row["maintenance"] or 0):
                    continue
                snapshot.append({
                    "id": int(row["id"]),
                    "status": str(row["status"] or "unknown"),
                    "response_ms": int(row["response_ms"] or 0),
                    "last_error": str(row["last_error"] or ""),
                })
                con.execute(
                    "UPDATE health_checks SET maintenance=1,status='maintenance',response_ms=0,last_error='',updated_at=? WHERE id=?",
                    (t, row["id"]),
                )
        return snapshot
    except Exception:
        with _application_update_maintenance_lock:
            _application_update_maintenance_devices.discard(key)
        raise


def _end_temporary_application_update_maintenance(check: sqlite3.Row, snapshot: list[dict[str, object]]) -> None:
    device_id = int(check["device_id"] or 0)
    owner_user_id = int(check["owner_user_id"] or 0)
    key = (device_id, owner_user_id)
    try:
        if snapshot:
            t = now()
            with db() as con:
                for row in snapshot:
                    con.execute(
                        "UPDATE health_checks SET maintenance=0,status=?,response_ms=?,last_error=?,updated_at=? WHERE id=?",
                        (row["status"], row["response_ms"], row["last_error"], t, row["id"]),
                    )
    finally:
        if device_id and owner_user_id:
            with _application_update_maintenance_lock:
                _application_update_maintenance_devices.discard(key)


def _device_system_checks_maintenance(device_id: int | None, owner_user_id: int | None) -> bool:
    if not device_id or not owner_user_id:
        return False
    key = (int(device_id), int(owner_user_id))
    with _application_update_maintenance_lock:
        if key in _application_update_maintenance_devices:
            return True
    with db() as con:
        row = con.execute(
            "SELECT 1 FROM health_checks WHERE device_id=? AND owner_user_id=? AND maintenance=1 LIMIT 1",
            (int(device_id), int(owner_user_id)),
        ).fetchone()
    return bool(row)


def _device_online_status(device_id: int | None, owner_user_id: int | None) -> str:
    if not device_id or not owner_user_id:
        return "unknown"
    with db() as con:
        row = con.execute(
            """SELECT status FROM health_checks
               WHERE device_id=? AND owner_user_id=? AND enabled=1 AND check_type='ping'
               ORDER BY id LIMIT 1""",
            (int(device_id), int(owner_user_id)),
        ).fetchone()
    return str(row["status"] or "unknown").lower() if row else "unknown"


def _ensure_current_online_status(device_id: int | None, owner_user_id: int | None) -> str:
    """Refresh Online Status once per current minute before SSH-dependent work."""
    if not device_id or not owner_user_id:
        return "unknown"
    with db() as con:
        ping = con.execute(
            """SELECT * FROM health_checks
               WHERE device_id=? AND owner_user_id=? AND enabled=1 AND check_type='ping'
               ORDER BY id LIMIT 1""",
            (int(device_id), int(owner_user_id)),
        ).fetchone()
    if not ping:
        return "unknown"
    if ping["maintenance"]:
        return "maintenance"
    if str(ping["last_checked"] or "") != now():
        execute_health_check(ping)
    return _device_online_status(device_id, owner_user_id)


def execute_update_check(check: sqlite3.Row) -> None:
    owner_user_id = int(check["owner_user_id"] or 0)
    device_id = int(check["device_id"] or 0)
    if _device_system_checks_maintenance(device_id, owner_user_id):
        return
    if device_id and _ensure_current_online_status(device_id, owner_user_id) == "offline":
        return

    if check["device_id"]:
        device = fetch_device_for_owner(int(check["device_id"]), owner_user_id)
        target = (
            (device["ipv4_address"] or device["hostname"] or device["ipv6_address"] or "").strip()
            if device else (check["host"] or "").strip()
        )
        if target and target != (check["host"] or ""):
            with db() as con:
                con.execute("UPDATE update_checks SET host=?, updated_at=? WHERE id=?", (target, now(), check["id"]))
            with db() as con:
                check = con.execute("SELECT * FROM update_checks WHERE id=?", (check["id"],)).fetchone()
    result = run_remote_update_check(check)
    packages = result.get("packages", [])
    with db() as con:
        con.execute(
            """UPDATE update_checks SET status=?, package_count=?, packages_json=?, last_checked=?, last_error=?, reboot_required=?, reboot_reason=?, updated_at=? WHERE id=?""",
            (result["status"], len(packages), json.dumps(packages), now(), result.get("error", ""), 1 if result.get("reboot_required") else 0, result.get("reboot_reason", ""), now(), check["id"]),
        )


def fetch_users() -> list[sqlite3.Row]:
    with db() as con:
        return con.execute("SELECT id,username,display_name,role,is_active,mfa_enabled,must_change_password,created_at,last_login_at FROM users ORDER BY username COLLATE NOCASE").fetchall()

def _is_admin(request: Request) -> bool:
    user = getattr(request.state, "user", None)
    return bool(user and user["role"] == "admin")

def _seed_categories_for_user(con: sqlite3.Connection, user_id: int) -> None:
    defaults = {
        "Camera": (1,1,0,0,0), "Lens": (1,0,0,0,0), "Drone": (1,1,0,0,0),
        "3D Printer": (1,1,1,1,1), "Printer": (1,1,1,1,0), "Server": (0,0,1,1,1),
        "Computer": (1,1,1,1,1), "Network": (0,1,1,1,1), "Smart Home": (1,1,1,1,0),
        "Vehicle": (1,0,0,0,0), "Audio": (1,1,0,0,0), "Other": (1,1,0,0,0),
    }
    for cat in DEFAULT_CATEGORIES:
        flags = defaults.get(cat,(1,1,0,0,0))
        system_checks = 1 if flags[3] or flags[4] else 0
        con.execute("INSERT OR IGNORE INTO categories(owner_user_id,name,show_ownership,show_firmware,show_network,show_health,show_updates,show_system_checks) VALUES (?,?,?,?,?,?,?,?)", (user_id,cat,*flags,system_checks))

def _setup_system_checks() -> list[dict]:
    checks = []
    def add(label: str, ok: bool, detail: str, attention: bool = False):
        status = "ok" if ok else ("attention" if attention else "error")
        checks.append({"label": label, "ok": bool(ok), "detail": detail, "status": status})
    try:
        os_release = Path("/etc/os-release").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        os_release = ""
    debian = "ID=debian" in os_release or "ID_LIKE=debian" in os_release
    add("Operating system", debian, "Debian-compatible system detected" if debian else "Debian-compatible system not detected")
    add("Application data directory", DATA_DIR.exists() and os.access(DATA_DIR, os.W_OK), str(DATA_DIR))
    free = shutil.disk_usage(DATA_DIR).free if DATA_DIR.exists() else 0
    add("Free disk space", free >= 1024 * 1024 * 1024, f"{free / (1024**3):.1f} GB available")
    add("Database", DB_PATH.exists(), "Ready" if DB_PATH.exists() else "Will be created automatically")
    return checks


def _setup_restore_statistics() -> dict:
    stats = {"devices": 0, "categories": 0, "users": 0, "ssh_profiles": 0}
    try:
        with db() as con:
            stats["devices"] = int(con.execute("SELECT COUNT(*) FROM devices").fetchone()[0])
            stats["categories"] = int(con.execute("SELECT COUNT(*) FROM categories").fetchone()[0])
            stats["users"] = int(con.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            try:
                stats["ssh_profiles"] = int(con.execute("SELECT COUNT(*) FROM ssh_profiles").fetchone()[0])
            except sqlite3.OperationalError:
                stats["ssh_profiles"] = 0
    except Exception:
        pass
    return stats


def _write_setup_restore_result() -> str:
    token = secrets.token_urlsafe(24)
    payload = {"created_at": now(), "phase": "restored", "statistics": _setup_restore_statistics()}
    path = SETUP_STATE_DIR / f"restore-{token}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def _read_setup_restore_result(token: str) -> Optional[dict]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token or ""):
        return None
    path = SETUP_STATE_DIR / f"restore-{token}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _update_setup_restore_result(token: str, payload: dict) -> bool:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token or ""):
        return False
    path = SETUP_STATE_DIR / f"restore-{token}.json"
    if not path.is_file():
        return False
    try:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        path.chmod(0o600)
        return True
    except Exception:
        return False


def _consume_setup_restore_result(token: str) -> Optional[dict]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token or ""):
        return None
    path = SETUP_STATE_DIR / f"restore-{token}.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        payload = None
    path.unlink(missing_ok=True)
    return payload


@app.get("/setup", response_class=HTMLResponse)
def setup_wizard(request: Request):
    if _users_exist():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request,
        "app_version": APP_VERSION,
        "step": "welcome",
        "checks": _setup_system_checks(),
        "error": "",
    })


@app.get("/setup/new", response_class=HTMLResponse)
def setup_new_page(request: Request):
    if _users_exist():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request,
        "app_version": APP_VERSION,
        "step": "new",
        "checks": _setup_system_checks(),
        "error": "",
    })


@app.post("/setup/new")
def setup_new(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(""),
    password: str = Form(...),
    password_confirm: str = Form(...),
    configure_mfa: Optional[str] = Form(None),
):
    if _users_exist():
        return RedirectResponse("/login", status_code=303)
    username = username.strip().lower()
    display_name = display_name.strip()
    error = ""
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", username):
        error = "Username must be 3–64 characters and use letters, numbers, dots, dashes or underscores."
    elif password != password_confirm:
        error = "Passwords do not match."
    elif len(password) < 12:
        error = "Password must contain at least 12 characters."
    if error:
        return templates.TemplateResponse("setup_wizard.html", {
            "request": request, "app_version": APP_VERSION, "step": "new", "checks": _setup_system_checks(),
            "error": error, "username": username,
            "display_name": display_name,
        }, status_code=400)
    secret = _totp_random_secret() if configure_mfa else ""
    with db() as con:
        cur = con.execute(
            "INSERT INTO users(username,display_name,password_hash,role,is_active,totp_secret,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (username, display_name, PASSWORD_HASHER.hash(password), "admin", 1, secret, now(), now()),
        )
        user_id = cur.lastrowid
        con.execute("UPDATE devices SET owner_user_id=? WHERE owner_user_id IS NULL", (user_id,))
        con.execute("UPDATE categories SET owner_user_id=? WHERE owner_user_id IS NULL", (user_id,))
        try:
            con.execute("UPDATE ssh_profiles SET owner_user_id=? WHERE owner_user_id IS NULL", (user_id,))
        except sqlite3.OperationalError:
            pass
        for key, value in (("instance_name", "Outlaw's Inventory"), ("first_run_complete", "false"), ("first_run_step", "categories")):
            con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    token, max_age = _create_session(request, user_id, False)
    response = RedirectResponse("/setup/mfa" if secret else "/setup/complete", status_code=303)
    _set_session_cookie(response, request, token, max_age)
    return response


@app.get("/setup/mfa", response_class=HTMLResponse)
def setup_mfa_page(request: Request):
    user = _session_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    secret = str(user["totp_secret"] or "")
    if not secret or int(user["mfa_enabled"] or 0):
        return RedirectResponse("/setup/complete", status_code=303)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request, "app_version": APP_VERSION, "step": "mfa", "error": "",
        "mfa_secret": secret, "mfa_qr_data_uri": _totp_qr_data_uri(user["username"], secret),
    })


@app.post("/setup/mfa")
def setup_mfa_enable(request: Request, verification_code: str = Form(...)):
    user = _session_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    secret = str(user["totp_secret"] or "")
    if not _totp_verify(secret, verification_code):
        return templates.TemplateResponse("setup_wizard.html", {
            "request": request, "app_version": APP_VERSION, "step": "mfa",
            "error": "The verification code is incorrect.", "mfa_secret": secret,
            "mfa_qr_data_uri": _totp_qr_data_uri(user["username"], secret),
        }, status_code=400)
    codes = _generate_recovery_codes()
    with db() as con:
        con.execute("UPDATE users SET mfa_enabled=1,recovery_codes_hash=?,updated_at=? WHERE id=?", (_recovery_hashes(codes), now(), user["id"]))
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request, "app_version": APP_VERSION, "step": "recovery", "error": "", "recovery_codes": codes,
    })


@app.get("/setup/restore", response_class=HTMLResponse)
def setup_restore_page(request: Request):
    if _users_exist():
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request, "app_version": APP_VERSION, "step": "restore", "checks": _setup_system_checks(), "error": "",
    })


@app.post("/setup/restore")
async def setup_restore_backup(request: Request, file: UploadFile = File(...)):
    if _users_exist():
        return RedirectResponse("/login", status_code=303)
    raw = await file.read(BACKUP_MAX_BYTES + 1)
    if len(raw) > BACKUP_MAX_BYTES:
        error = "The backup exceeds the 1 GB limit."
    else:
        temporary = BACKUP_DIR / f"setup-{uuid.uuid4().hex}.oi-backup.tmp"
        try:
            temporary.write_bytes(raw)
            validate_full_backup(temporary)
            restore_full_backup(temporary)
            completion_token = _write_setup_restore_result()
            return RedirectResponse(f"/setup/restore-complete?token={completion_token}", status_code=303)
        except Exception as exc:
            error = f"Restore failed: {exc}"
        finally:
            temporary.unlink(missing_ok=True)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request, "app_version": APP_VERSION, "step": "restore", "checks": _setup_system_checks(), "error": error,
    }, status_code=400)


@app.get("/setup/restore-complete", response_class=HTMLResponse)
def setup_restore_complete(request: Request, token: str = ""):
    result = _read_setup_restore_result(token)
    if not result:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request,
        "app_version": APP_VERSION,
        "step": "restore_complete",
        "error": "",
        "restore_token": token,
        "restore_phase": result.get("phase", "restored"),
        "restore_statistics": result.get("statistics", {}),
        "status_refresh": result.get("status_refresh", {}),
    })


@app.post("/setup/restore-refresh")
def setup_restore_refresh(token: str = Form(...)):
    result = _read_setup_restore_result(token)
    if not result:
        return JSONResponse({"ok": False, "detail": "Restore session not found."}, status_code=404)
    if result.get("phase") == "checked":
        return JSONResponse({"ok": True, "status_refresh": result.get("status_refresh", {})})
    if result.get("phase") != "restored":
        return JSONResponse({"ok": False, "detail": "Restore is not ready for status refresh."}, status_code=409)

    # The backup has already been fully validated and restored at this point.
    # Current status is a separate recovery phase and can never turn a successful
    # backup restore into a restore failure.
    refresh_statistics = run_all_system_checks(notify=False, session_scoped=False)
    result["phase"] = "checked"
    result["status_refresh"] = refresh_statistics
    result["checked_at"] = now()
    if not _update_setup_restore_result(token, result):
        return JSONResponse({"ok": False, "detail": "Could not save refresh result."}, status_code=500)
    return JSONResponse({"ok": True, "status_refresh": refresh_statistics})


@app.get("/setup/restore-finish")
def setup_restore_finish(token: str = ""):
    result = _consume_setup_restore_result(token)
    if not result:
        return RedirectResponse("/login", status_code=303)
    return RedirectResponse("/login?next=/", status_code=303)


@app.get("/setup/complete", response_class=HTMLResponse)
def setup_complete(request: Request):
    user = _session_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("setup_wizard.html", {
        "request": request, "app_version": APP_VERSION, "step": "complete", "error": "",
    })


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if not _users_exist():
        return RedirectResponse("/setup", status_code=303)
    if getattr(request.state, "user", None):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "app_version": APP_VERSION, "error": "", "next": _safe_next_url(next), "remember_enabled": _auth_settings()["remember_me_enabled"]})


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/"), remember_me: Optional[str] = Form(None)):
    key = request.client.host if request.client else "unknown"
    cutoff = time.time() - 900
    attempts = [t for t in _login_attempts.get(key, []) if t > cutoff]
    if len(attempts) >= 10:
        return templates.TemplateResponse("login.html", {"request": request, "app_version": APP_VERSION, "error": "Too many failed attempts. Try again later.", "next": _safe_next_url(next), "remember_enabled": _auth_settings()["remember_me_enabled"]}, status_code=429)
    with db() as con:
        user = con.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE AND is_active=1", (username.strip().lower(),)).fetchone()
    valid = False
    if user:
        try:
            valid = PASSWORD_HASHER.verify(user["password_hash"], password)
        except (VerifyMismatchError, InvalidHashError):
            valid = False
    if not valid:
        attempts.append(time.time()); _login_attempts[key] = attempts
        time.sleep(0.35)
        return templates.TemplateResponse("login.html", {"request": request, "app_version": APP_VERSION, "error": "Invalid username or password.", "next": _safe_next_url(next), "remember_enabled": _auth_settings()["remember_me_enabled"]}, status_code=401)
    _login_attempts.pop(key, None)
    if PASSWORD_HASHER.check_needs_rehash(user["password_hash"]):
        with db() as con: con.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?", (PASSWORD_HASHER.hash(password), now(), user["id"]))
    use_remember = bool(remember_me) and bool(_auth_settings()["remember_me_enabled"])
    if int(user["mfa_enabled"] or 0) and not _trusted_device_for_user(request, int(user["id"])):
        challenge = _create_mfa_challenge(request, int(user["id"]), next, use_remember)
        response = RedirectResponse("/login/mfa", status_code=303)
        _set_mfa_challenge_cookie(response, request, challenge)
        return response
    token, max_age = _create_session(request, user["id"], use_remember)
    with db() as con: con.execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), user["id"]))
    response = RedirectResponse(_safe_next_url(next), status_code=303)
    _set_session_cookie(response, request, token, max_age)
    return response



@app.get("/login/mfa", response_class=HTMLResponse)
def login_mfa_page(request: Request):
    challenge = _get_mfa_challenge(request)
    if not challenge:
        response = RedirectResponse("/login", status_code=303)
        _delete_mfa_challenge_cookie(response, request)
        return response
    return templates.TemplateResponse("login_mfa.html", {"request":request,"app_version":APP_VERSION,"error":"","username":challenge["display_name"] or challenge["username"]})


@app.post("/login/mfa")
def login_mfa(request: Request, verification_code: str = Form(...)):
    challenge = _get_mfa_challenge(request)
    if not challenge:
        response = RedirectResponse("/login", status_code=303)
        _delete_mfa_challenge_cookie(response, request)
        return response
    if not _verify_totp_or_recovery(challenge, verification_code, consume_recovery=True):
        with db() as con:
            con.execute("UPDATE mfa_login_challenges SET attempt_count=attempt_count+1 WHERE id=?", (challenge["id"],))
            attempts = con.execute("SELECT attempt_count FROM mfa_login_challenges WHERE id=?", (challenge["id"],)).fetchone()[0]
            if attempts >= 10:
                con.execute("DELETE FROM mfa_login_challenges WHERE id=?", (challenge["id"],))
        if attempts >= 10:
            response = RedirectResponse("/login", status_code=303)
            _delete_mfa_challenge_cookie(response, request)
            return response
        time.sleep(0.25)
        return templates.TemplateResponse("login_mfa.html", {"request":request,"app_version":APP_VERSION,"error":"Invalid verification or recovery code.","username":challenge["display_name"] or challenge["username"]}, status_code=401)
    token, max_age = _create_session(request, int(challenge["user_id"]), bool(challenge["remember_me"]))
    trusted_token = _create_trusted_device(request, int(challenge["user_id"])) if bool(challenge["remember_me"]) else ""
    with db() as con:
        con.execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), challenge["user_id"]))
        con.execute("DELETE FROM mfa_login_challenges WHERE id=?", (challenge["id"],))
    response = RedirectResponse(_safe_next_url(challenge["next_url"]), status_code=303)
    _set_session_cookie(response, request, token, max_age)
    if trusted_token:
        _set_trusted_device_cookie(response, request, trusted_token)
    _delete_mfa_challenge_cookie(response, request)
    return response


@app.post("/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        with db() as con: con.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_hash_session_token(token),))
    response = RedirectResponse("/login", status_code=303)
    _delete_session_cookie(response, request)
    return response


@app.post("/settings/users/create")
def create_user(request: Request, username: str = Form(...), display_name: str = Form(""), temporary_password: str = Form(...), role: str = Form("user")):
    if not _is_admin(request):
        return HTMLResponse("Administrator access required.", status_code=403)
    username = username.strip().lower()
    display_name = display_name.strip() or username
    role = role if role in {"admin","user"} else "user"
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", username):
        return RedirectResponse("/settings?auth_message=Username+must+be+3-64+characters+and+use+letters,+numbers,+dot,+dash+or+underscore.&auth_ok=0&auth_open=1", status_code=303)
    if len(temporary_password) < 12:
        return RedirectResponse("/settings?auth_message=Temporary+password+must+contain+at+least+12+characters.&auth_ok=0&auth_open=1", status_code=303)
    try:
        with db() as con:
            t=now()
            cur=con.execute("INSERT INTO users(username,display_name,password_hash,role,is_active,must_change_password,created_at,updated_at) VALUES(?,?,?,?,1,1,?,?)", (username,display_name,PASSWORD_HASHER.hash(temporary_password),role,t,t))
            _seed_categories_for_user(con, int(cur.lastrowid))
    except sqlite3.IntegrityError:
        return RedirectResponse("/settings?auth_message=Username+already+exists.&auth_ok=0&auth_open=1", status_code=303)
    return RedirectResponse("/settings?auth_message=User+created.+A+password+change+is+required+at+first+login.&auth_ok=1&auth_open=1", status_code=303)

@app.post("/settings/users/{user_id}/role")
def change_user_role(request: Request, user_id: int, role: str = Form(...)):
    if not _is_admin(request):
        return HTMLResponse("Administrator access required.", status_code=403)
    role = role if role in {"admin", "user"} else "user"
    with db() as con:
        row = con.execute("SELECT id,role,is_active FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            return RedirectResponse("/settings?auth_message=User+not+found.&auth_ok=0&auth_open=1", status_code=303)
        if row["role"] == "admin" and role != "admin" and con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0] <= 1:
            return RedirectResponse("/settings?auth_message=The+last+active+administrator+cannot+be+changed.&auth_ok=0&auth_open=1", status_code=303)
        # Intentionally update only the role and audit timestamp. Ownership and user data remain untouched.
        con.execute("UPDATE users SET role=?,updated_at=? WHERE id=?", (role, now(), user_id))
        if role != "admin":
            con.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
    return RedirectResponse("/settings?auth_message=User+role+updated.&auth_ok=1&auth_open=1", status_code=303)


@app.post("/settings/users/{user_id}/toggle")
def toggle_user(request: Request, user_id: int):
    if not _is_admin(request) or user_id == int(request.state.user["id"]):
        return RedirectResponse("/settings?auth_message=This+user+cannot+be+disabled.&auth_ok=0&auth_open=1", status_code=303)
    with db() as con:
        row=con.execute("SELECT is_active,role FROM users WHERE id=?",(user_id,)).fetchone()
        if not row: return RedirectResponse("/settings?auth_message=User+not+found.&auth_ok=0&auth_open=1",status_code=303)
        new=0 if row["is_active"] else 1
        if row["role"]=="admin" and not new and con.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0] <= 1:
            return RedirectResponse("/settings?auth_message=The+last+active+administrator+cannot+be+disabled.&auth_ok=0&auth_open=1",status_code=303)
        con.execute("UPDATE users SET is_active=?,updated_at=? WHERE id=?",(new,now(),user_id))
        if not new: con.execute("DELETE FROM auth_sessions WHERE user_id=?",(user_id,))
    return RedirectResponse("/settings?auth_message=User+status+updated.&auth_ok=1&auth_open=1",status_code=303)

@app.post("/settings/users/{user_id}/reset-password")
def reset_user_password(request: Request, user_id: int, temporary_password: str = Form(...)):
    if not _is_admin(request): return HTMLResponse("Administrator access required.",status_code=403)
    if len(temporary_password)<12: return RedirectResponse("/settings?auth_message=Temporary+password+must+contain+at+least+12+characters.&auth_ok=0&auth_open=1",status_code=303)
    with db() as con:
        con.execute("UPDATE users SET password_hash=?,must_change_password=1,updated_at=? WHERE id=?",(PASSWORD_HASHER.hash(temporary_password),now(),user_id))
        con.execute("DELETE FROM mfa_login_challenges WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM auth_sessions WHERE user_id=?",(user_id,))
    return RedirectResponse("/settings?auth_message=Password+reset.+The+user+must+change+it+at+next+login.&auth_ok=1&auth_open=1",status_code=303)

@app.post("/settings/users/{user_id}/delete")
def delete_user(request: Request, user_id: int):
    with _database_gate.access():
        if not _is_admin(request) or user_id == int(request.state.user["id"]):
            return RedirectResponse("/settings?auth_message=This+user+cannot+be+deleted.&auth_ok=0&auth_open=1",status_code=303)
        with db() as con:
            row=con.execute("SELECT role FROM users WHERE id=?",(user_id,)).fetchone()
            if not row: return RedirectResponse("/settings?auth_message=User+not+found.&auth_ok=0&auth_open=1",status_code=303)
            if con.execute("SELECT COUNT(*) FROM devices WHERE owner_user_id=?",(user_id,)).fetchone()[0]:
                return RedirectResponse("/settings?auth_message=User+still+owns+devices.+Disable+the+account+instead.&auth_ok=0&auth_open=1",status_code=303)
            if row["role"]=="admin" and con.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] <= 1:
                return RedirectResponse("/settings?auth_message=The+last+administrator+cannot+be+deleted.&auth_ok=0&auth_open=1",status_code=303)
            con.execute("DELETE FROM categories WHERE owner_user_id=?",(user_id,))
            con.execute("DELETE FROM users WHERE id=?",(user_id,))
        _avatar_path(user_id).unlink(missing_ok=True)
        return RedirectResponse("/settings?auth_message=User+deleted.&auth_ok=1&auth_open=1",status_code=303)


@app.post("/settings/users/{user_id}/reset-mfa")
def reset_user_mfa(request: Request, user_id: int):
    if not _is_admin(request):
        return HTMLResponse("Administrator access required.", status_code=403)
    if int(request.state.user["id"]) == int(user_id):
        return RedirectResponse("/settings?auth_message=Use+Account+settings+to+manage+MFA.&auth_ok=0&auth_open=1", status_code=303)
    with db() as con:
        user = con.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            return RedirectResponse("/settings?auth_message=User+not+found.&auth_ok=0&auth_open=1", status_code=303)
        con.execute("UPDATE users SET mfa_enabled=0,totp_secret='',recovery_codes_hash='',updated_at=? WHERE id=?", (now(),user_id))
        con.execute("DELETE FROM mfa_login_challenges WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user_id,))
        con.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
    return RedirectResponse("/settings?auth_message=MFA+reset.+The+user+must+sign+in+again.&auth_ok=1&auth_open=1", status_code=303)


@app.post("/settings/users/transfer-inventory")
def transfer_user_inventory(request: Request, source_user_id: int = Form(...), target_user_id: int = Form(...)):
    if not _is_admin(request):
        return HTMLResponse("Administrator access required.", status_code=403)
    if source_user_id == target_user_id:
        return RedirectResponse("/settings?auth_message=Source+and+destination+must+be+different.&auth_ok=0&auth_open=1", status_code=303)
    try:
        with db() as con:
            source = con.execute("SELECT id,username FROM users WHERE id=?", (source_user_id,)).fetchone()
            target = con.execute("SELECT id,username FROM users WHERE id=?", (target_user_id,)).fetchone()
            if not source or not target:
                raise ValueError("User not found.")
            target_device_count = con.execute("SELECT COUNT(*) FROM devices WHERE owner_user_id=?", (target_user_id,)).fetchone()[0]
            target_profile_count = con.execute("SELECT COUNT(*) FROM ssh_profiles WHERE owner_user_id=?", (target_user_id,)).fetchone()[0]
            if target_device_count or target_profile_count:
                raise ValueError("Destination user must have an empty inventory and no SSH profiles.")
            # Target default categories can safely be replaced with the source category configuration.
            con.execute("DELETE FROM categories WHERE owner_user_id=?", (target_user_id,))
            con.execute("UPDATE categories SET owner_user_id=? WHERE owner_user_id=?", (target_user_id, source_user_id))
            con.execute("UPDATE ssh_profiles SET owner_user_id=? WHERE owner_user_id=?", (target_user_id, source_user_id))
            con.execute("UPDATE devices SET owner_user_id=?, updated_at=? WHERE owner_user_id=?", (target_user_id, now(), source_user_id))
            con.execute("UPDATE health_checks SET owner_user_id=? WHERE owner_user_id=?", (target_user_id, source_user_id))
            con.execute("UPDATE update_checks SET owner_user_id=? WHERE owner_user_id=?", (target_user_id, source_user_id))
            _repair_multi_user_ownership(con)
            # Keep the source account usable with a clean default category set.
            _seed_categories_for_user(con, source_user_id)
            moved = con.execute("SELECT COUNT(*) FROM devices WHERE owner_user_id=?", (target_user_id,)).fetchone()[0]
        message = f"Inventory transferred to {target['username']} ({moved} devices)."
        return RedirectResponse(f"/settings?auth_message={quote(message)}&auth_ok=1&auth_open=1", status_code=303)
    except (ValueError, sqlite3.IntegrityError) as exc:
        return RedirectResponse(f"/settings?auth_message={quote(str(exc))}&auth_ok=0&auth_open=1", status_code=303)


@app.post("/settings/authentication")
def save_authentication_settings(request: Request, session_timeout_minutes: str = Form("30"), remember_me_enabled: Optional[str] = Form(None), require_mfa_admins: Optional[str] = Form(None)):
    if not _is_admin(request):
        return HTMLResponse("Administrator access required.", status_code=403)
    if session_timeout_minutes not in {"15","30","60","240","480","1440"}:
        return RedirectResponse("/settings?auth_message=Invalid+session+timeout.&auth_ok=0&auth_open=1", status_code=303)
    with db() as con:
        con.execute("INSERT INTO settings(key,value) VALUES ('authentication_session_timeout_minutes',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (session_timeout_minutes,))
        con.execute("INSERT INTO settings(key,value) VALUES ('authentication_remember_me_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("1" if remember_me_enabled else "0",))
        if _is_admin(request):
            con.execute("INSERT INTO settings(key,value) VALUES ('authentication_require_mfa_admins',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("1" if require_mfa_admins else "0",))
    return RedirectResponse("/settings?auth_message=Authentication+settings+saved.&auth_ok=1&auth_open=1", status_code=303)


@app.post("/settings/authentication/change-password")
def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), new_password_confirm: str = Form(...)):
    user = getattr(request.state, "user", None)
    error = ""
    try:
        if not user or not PASSWORD_HASHER.verify(user["password_hash"], current_password): error = "Current password is incorrect."
    except Exception: error = "Current password is incorrect."
    if not error and len(new_password) < 12: error = "New password must contain at least 12 characters."
    if not error and new_password != new_password_confirm: error = "New passwords do not match."
    if error:
        return RedirectResponse(f"/settings?auth_message={quote(error)}&auth_ok=0&auth_open=1", status_code=303)
    with db() as con:
        con.execute("UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?", (PASSWORD_HASHER.hash(new_password), now(), user["id"]))
        con.execute("DELETE FROM mfa_login_challenges WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM auth_sessions WHERE user_id=? AND id<>?", (user["id"], user["session_id"]))
    return RedirectResponse("/settings?auth_message=Password+changed.+Other+sessions+were+signed+out.&auth_ok=1&auth_open=1", status_code=303)


@app.post("/profile/change-password")
def profile_change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), new_password_confirm: str = Form(...)):
    user = getattr(request.state, "user", None)
    error = ""
    try:
        if not user or not PASSWORD_HASHER.verify(user["password_hash"], current_password):
            error = "Current password is incorrect."
    except Exception:
        error = "Current password is incorrect."
    if not error and len(new_password) < 12:
        error = "New password must contain at least 12 characters."
    if not error and new_password != new_password_confirm:
        error = "New passwords do not match."
    if error:
        return RedirectResponse(f"/settings?account_open=1&account_message={quote(error)}&account_ok=0#security", status_code=303)
    with db() as con:
        con.execute("UPDATE users SET password_hash=?, must_change_password=0, updated_at=? WHERE id=?", (PASSWORD_HASHER.hash(new_password), now(), user["id"]))
        con.execute("DELETE FROM mfa_login_challenges WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM auth_sessions WHERE user_id=? AND id<>?", (user["id"], user["session_id"]))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user["id"],))
    return RedirectResponse("/settings?account_open=1&account_message=Password+changed.+Other+sessions+were+signed+out.&account_ok=1#security", status_code=303)


PROFILE_AVATAR_MAX_BYTES = 5 * 1024 * 1024
PROFILE_AVATAR_SIZE = 256
PROFILE_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _profile_initials(user: sqlite3.Row | dict) -> str:
    label = str(user["display_name"] or user["username"] or "U").strip()
    words = [part for part in re.split(r"\s+", label) if part]
    if not words:
        return "U"
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()


def _avatar_path(user_id: int) -> Path:
    return AVATAR_DIR / f"{int(user_id)}.webp"


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    user = request.state.user
    mfa_setup = request.query_params.get("mfa_setup", "")
    return templates.TemplateResponse("profile.html", page_context(
        request, "settings",
        profile_message=request.query_params.get("profile_message", ""),
        profile_ok=request.query_params.get("profile_ok", ""),
        mfa_required=request.query_params.get("mfa_required", ""),
        mfa_setup=mfa_setup,
        mfa_secret=str(user["totp_secret"] or ""),
        mfa_qr_data_uri=_totp_qr_data_uri(user["username"], str(user["totp_secret"] or "")) if mfa_setup == "1" and str(user["totp_secret"] or "") else "",
        profile_initials=_profile_initials(user),
    ))


@app.post("/profile")
def save_profile(request: Request, display_name: str = Form(...)):
    user = request.state.user
    cleaned = " ".join(display_name.strip().split())
    if not cleaned or len(cleaned) > 100:
        return RedirectResponse("/settings?account_open=1&account_message=Display+name+must+contain+1-100+characters.&account_ok=0", status_code=303)
    with db() as con:
        con.execute("UPDATE users SET display_name=?, updated_at=? WHERE id=?", (cleaned, now(), user["id"]))
    return RedirectResponse("/settings?account_open=1&account_message=Profile+saved.&account_ok=1", status_code=303)



@app.get("/profile/mfa/setup", response_class=HTMLResponse)
def profile_mfa_setup_page(request: Request):
    user = request.state.user
    if int(user["mfa_enabled"] or 0):
        return RedirectResponse("/settings?account_open=1&account_message=MFA+is+already+enabled.&account_ok=0", status_code=303)
    secret = _totp_random_secret()
    with db() as con:
        con.execute("UPDATE users SET totp_secret=?,updated_at=? WHERE id=?", (secret,now(),user["id"]))
    return RedirectResponse("/settings?account_open=1&mfa_setup=1#security", status_code=303)


@app.post("/profile/mfa/enable", response_class=HTMLResponse)
def profile_mfa_enable(request: Request, current_password: str = Form(...), verification_code: str = Form(...)):
    user = request.state.user
    try:
        password_ok = PASSWORD_HASHER.verify(user["password_hash"], current_password)
    except Exception:
        password_ok = False
    secret = str(user["totp_secret"] or "")
    code_ok = bool(secret and _totp_verify(secret, verification_code.replace(" ",""), valid_window=1))
    if not password_ok or not code_ok:
        return RedirectResponse("/settings?account_open=1&account_message=Current+password+or+verification+code+is+incorrect.&account_ok=0&mfa_setup=1#security", status_code=303)
    codes = _generate_recovery_codes()
    with db() as con:
        con.execute("UPDATE users SET mfa_enabled=1,recovery_codes_hash=?,updated_at=? WHERE id=?", (_recovery_hashes(codes),now(),user["id"]))
        con.execute("DELETE FROM mfa_login_challenges WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM auth_sessions WHERE user_id=? AND id<>?", (user["id"],user["session_id"]))
    return templates.TemplateResponse("mfa_recovery_codes.html", page_context(request,"profile",recovery_codes=codes))


@app.post("/profile/mfa/disable")
def profile_mfa_disable(request: Request, current_password: str = Form(...), verification_code: str = Form(...)):
    user = request.state.user
    try:
        password_ok = PASSWORD_HASHER.verify(user["password_hash"], current_password)
    except Exception:
        password_ok = False
    if not password_ok or not _verify_totp_or_recovery(user, verification_code, consume_recovery=True):
        return RedirectResponse("/settings?account_open=1&account_message=Current+password+or+verification+code+is+incorrect.&account_ok=0", status_code=303)
    with db() as con:
        con.execute("UPDATE users SET mfa_enabled=0,totp_secret='',recovery_codes_hash='',updated_at=? WHERE id=?", (now(),user["id"]))
        con.execute("DELETE FROM mfa_login_challenges WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (user["id"],))
        con.execute("DELETE FROM auth_sessions WHERE user_id=? AND id<>?", (user["id"],user["session_id"]))
    return RedirectResponse("/settings?account_open=1&account_message=MFA+disabled.+Other+sessions+were+signed+out.&account_ok=1", status_code=303)


@app.post("/profile/mfa/recovery-codes", response_class=HTMLResponse)
def profile_mfa_recovery_codes(request: Request, current_password: str = Form(...), verification_code: str = Form(...)):
    user = request.state.user
    try:
        password_ok = PASSWORD_HASHER.verify(user["password_hash"], current_password)
    except Exception:
        password_ok = False
    if not password_ok or not _verify_totp_or_recovery(user, verification_code, consume_recovery=False):
        return RedirectResponse("/settings?account_open=1&account_message=Current+password+or+verification+code+is+incorrect.&account_ok=0", status_code=303)
    codes = _generate_recovery_codes()
    with db() as con:
        con.execute("UPDATE users SET recovery_codes_hash=?,updated_at=? WHERE id=?", (_recovery_hashes(codes),now(),user["id"]))
    return templates.TemplateResponse("mfa_recovery_codes.html", page_context(request,"profile",recovery_codes=codes))


@app.get("/profile/avatar")
def current_profile_avatar(request: Request):
    user = request.state.user
    path = _avatar_path(int(user["id"]))
    if not path.is_file() or not str(user["avatar_filename"] or ""):
        return Response(status_code=404)
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=3600"})


@app.post("/profile/avatar")
async def upload_profile_avatar(request: Request, avatar: UploadFile = File(...)):
    user = request.state.user
    content_type = (avatar.content_type or "").lower()
    if content_type not in PROFILE_AVATAR_TYPES:
        return RedirectResponse("/settings?account_open=1&account_message=Use+a+JPG,+PNG+or+WEBP+image.&account_ok=0", status_code=303)
    content = await avatar.read(PROFILE_AVATAR_MAX_BYTES + 1)
    if not content or len(content) > PROFILE_AVATAR_MAX_BYTES:
        return RedirectResponse("/settings?account_open=1&account_message=Avatar+must+be+smaller+than+5+MB.&account_ok=0", status_code=303)
    with _database_gate.access():
        destination = _avatar_path(int(user["id"]))
        temporary = destination.with_suffix(".tmp")
        try:
            with Image.open(BytesIO(content)) as image:
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                image = ImageOps.fit(image, (PROFILE_AVATAR_SIZE, PROFILE_AVATAR_SIZE), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                image.save(temporary, format="WEBP", quality=86, method=6)
            temporary.replace(destination)
            destination.chmod(0o600)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            temporary.unlink(missing_ok=True)
            return RedirectResponse("/settings?account_open=1&account_message=The+uploaded+file+is+not+a+valid+image.&account_ok=0", status_code=303)
        with db() as con:
            con.execute("UPDATE users SET avatar_filename=?, avatar_updated_at=?, updated_at=? WHERE id=?", (destination.name, now(), now(), user["id"]))
        return RedirectResponse("/settings?account_open=1&account_message=Avatar+updated.&account_ok=1", status_code=303)


@app.post("/profile/avatar/delete")
def delete_profile_avatar(request: Request):
    with _database_gate.access():
        user = request.state.user
        _avatar_path(int(user["id"])).unlink(missing_ok=True)
        with db() as con:
            con.execute("UPDATE users SET avatar_filename='', avatar_updated_at='', updated_at=? WHERE id=?", (now(), user["id"]))
        return RedirectResponse("/settings?account_open=1&account_message=Avatar+removed.&account_ok=1", status_code=303)



def _replace_owner_categories(request: Request, selected: list[str]) -> None:
    owner_id = int(request.state.user["id"])
    clean = []
    seen = set()
    for value in selected:
        name = str(value or "").strip()
        if name and name.lower() not in seen:
            clean.append(name)
            seen.add(name.lower())
    with db() as con:
        existing = con.execute(
            "SELECT id,name FROM categories WHERE owner_user_id=? ORDER BY id",
            (owner_id,),
        ).fetchall()
        existing_map = {str(row["name"]).strip().lower(): row for row in existing}
        keep = set()
        for name in clean:
            key = name.lower()
            if key in existing_map:
                keep.add(int(existing_map[key]["id"]))
            else:
                cur = con.execute(
                    "INSERT INTO categories(owner_user_id,name,created_at,updated_at) VALUES(?,?,?,?)",
                    (owner_id, name, now(), now()),
                )
                keep.add(int(cur.lastrowid))
        for row in existing:
            category_id = int(row["id"])
            if category_id in keep:
                continue
            used = con.execute(
                "SELECT COUNT(*) FROM devices WHERE owner_user_id=? AND category=?",
                (owner_id, row["name"]),
            ).fetchone()[0]
            if int(used or 0) == 0:
                con.execute("DELETE FROM categories WHERE id=?", (category_id,))



def _normalize_system_checks_for_device(device: sqlite3.Row) -> None:
    """Normalize stored check records into the current System Checks model."""
    device_id = int(device["id"])
    owner_id = int(device["owner_user_id"])
    target = resolved_target(device_id, "")
    label = device["display_name"] or device["name"]
    t = now()
    with db() as con:
        rows = con.execute(
            "SELECT * FROM health_checks WHERE device_id=? AND owner_user_id=? ORDER BY id",
            (device_id, owner_id),
        ).fetchall()
        by_type: dict[str, sqlite3.Row] = {}
        duplicates: list[int] = []
        for row in rows:
            check_type = str(row["check_type"] or "ping").lower()
            if check_type not in {"ping", "disk", "http"}:
                check_type = "ping"
            if check_type in by_type:
                duplicates.append(int(row["id"]))
            else:
                by_type[check_type] = row
        for duplicate_id in duplicates:
            con.execute("DELETE FROM health_checks WHERE id=?", (duplicate_id,))

        # Normalization may repair metadata on existing health checks, but it must
        # never change the user's enabled/disabled selection. In particular,
        # Online and Disk used to be force-enabled (or recreated after deletion)
        # whenever a device/detail page was opened. Initial managed-host setup is
        # responsible for creating the default checks; normal page reads only
        # normalize rows that still exist.
        for check_type, suffix in (("ping", "Ping"), ("disk", "Disk usage")):
            row = by_type.get(check_type)
            if row:
                con.execute(
                    """UPDATE health_checks
                       SET name=?,host=?,group_key=?,updated_at=?
                       WHERE id=?""",
                    (f"{label} — {suffix}", target, f"device:{device_id}", t, row["id"]),
                )

        con.execute(
            """UPDATE update_checks
               SET name=?,host=?,updated_at=?
               WHERE device_id=? AND owner_user_id=?""",
            (label, target, t, device_id, owner_id),
        )


def _normalize_all_system_checks() -> None:
    for device in fetch_devices():
        if str(device["category"] or "").strip().lower() == "server" or device["managed_host"]:
            _normalize_system_checks_for_device(device)


def _is_system_check_transport_error(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    markers = (
        "unable to connect to port",
        "connection refused",
        "connection timed out",
        "timed out",
        "no route to host",
        "network is unreachable",
        "connection reset",
        "connection closed",
    )
    return any(marker in text for marker in markers)


def _system_check_configuration_issue(item: dict) -> dict[str, str] | None:
    """Return a user-facing managed-host configuration issue, without exposing raw SSH errors."""
    candidates = []
    for row in (item.get("disk_check"), item.get("updates")):
        if row:
            candidates.append(str(row.get("last_error") or ""))
    message = " ".join(candidates).strip().lower()
    auth_markers = (
        "authentication failed",
        "permission denied",
        "no authentication methods",
        "private key",
        "ssh profile not found",
        "configured managed host integration",
        "managed host ssh profile",
    )
    if any(marker in message for marker in auth_markers):
        return {
            "kind": "ssh",
            "title": "System Checks configuration needs attention",
            "message": "SSH access to this host could not be authenticated. Reconfigure System Checks to restore managed checks.",
        }
    return None


def _system_check_status(item: dict) -> str:
    if any(bool((row or {}).get("maintenance")) for row in item.get("health_checks", {}).values()):
        return "maintenance"

    ping = item.get("ping_check")
    disk = item.get("disk_check")
    http = item.get("http_check")
    updates = item.get("updates")
    applications = item.get("applications") or []

    ping_status = str((ping or {}).get("status") or "unknown").lower()
    disk_status = str((disk or {}).get("status") or "unknown").lower()
    http_status = str((http or {}).get("status") or "unknown").lower()
    update_count = int((updates or {}).get("package_count") or 0)

    if ping and ping_status in {"offline", "critical", "failed"}:
        return "critical"
    if disk and disk_status in {"critical", "failed"}:
        return "critical"
    if http and http_status in {"offline", "critical", "failed"}:
        return "critical"
    if updates and bool(updates.get("reboot_required")):
        return "reboot"
    if disk and disk_status in {"warning", "attention"}:
        return "attention"
    if updates and str(updates.get("status") or "").lower() == "failed":
        return "critical"
    if any(str(app.get("status") or "").lower() == "failed" for app in applications):
        return "critical"
    if update_count > 0 or any(str(app.get("status") or "").lower() in {"available", "attention"} for app in applications):
        return "attention"
    if any(str(app.get("status") or "").lower() == "unknown" for app in applications):
        return "unknown"

    # Disabled checks are omitted from the item before aggregate status is
    # calculated. A host is healthy when every remaining active check is
    # healthy; Ping is not a mandatory prerequisite for an OK state.
    active_checks = bool(ping or disk or http or updates or applications)
    if not active_checks:
        return "unknown"

    if ping and ping_status not in {"online", "ok"}:
        return "unknown"
    if disk and disk_status not in {"online", "ok"}:
        return "unknown"
    if http and http_status not in {"online", "ok"}:
        return "unknown"
    if updates and str(updates.get("status") or "ok").lower() in {"unknown", "pending"}:
        return "unknown"
    if any(str(app.get("status") or "").lower() not in {"ok", "up_to_date", "uptodate"} for app in applications):
        return "unknown"
    return "ok"


def _system_check_rows() -> list[dict]:
    health_by_device: dict[int, dict[str, dict]] = {}
    for row in fetch_health_checks():
        # Disabled health checks are configuration records, not current overview
        # checks. Keep them available for re-enabling on the detail page, but do
        # not render or include them in the current System Checks status.
        if not row["enabled"]:
            continue
        device_id = int(row["device_id"] or 0)
        if not device_id:
            continue
        check_type = str(row["check_type"] or "ping").lower()
        current = health_by_device.setdefault(device_id, {}).get(check_type)
        if current is None or int(row["id"]) < int(current["id"]):
            health_by_device[device_id][check_type] = dict(row)

    applications_by_device: dict[int, list[dict]] = {}
    for row in fetch_application_checks():
        device_id = int(row["device_id"] or 0)
        if not device_id or not row["enabled"]:
            continue
        app = dict(row)
        try:
            app["details"] = json.loads(row["details_json"] or "{}")
        except Exception:
            app["details"] = {}
        app["display_name"] = {"pihole": "Pi-hole", "minecraft": "Minecraft"}.get(str(row["application_type"]).lower(), str(row["application_type"]))
        applications_by_device.setdefault(device_id, []).append(app)

    updates_by_device: dict[int, dict] = {}
    for row in fetch_update_checks():
        device_id = int(row["device_id"] or 0)
        if not device_id:
            continue
        item = dict(row)
        try:
            item["packages"] = json.loads(row["packages_json"] or "[]")
        except Exception:
            item["packages"] = []
        updates_by_device[device_id] = item

    result = []
    for device in fetch_devices():
        if str(device["category"] or "").strip().lower() != "server" and not device["managed_host"]:
            continue
        item = dict(device)
        checks = health_by_device.get(int(device["id"]), {})
        item["health_checks"] = checks
        item["ping_check"] = checks.get("ping")
        item["disk_check"] = checks.get("disk")
        item["http_check"] = checks.get("http")
        item["update_check"] = updates_by_device.get(int(device["id"]))
        item["updates"] = item["update_check"] if item["update_check"] and bool(item["update_check"].get("enabled")) else None
        item["applications"] = applications_by_device.get(int(device["id"]), [])
        item["pihole"] = next((app for app in item["applications"] if str(app.get("application_type") or "").lower() == "pihole"), None)
        item["minecraft"] = next((app for app in item["applications"] if str(app.get("application_type") or "").lower() == "minecraft"), None)
        item["disk_usage"] = item["disk_check"].get("disk_usage_percent") if item["disk_check"] else None

        settings = get_settings()
        disk_check = item["disk_check"] or {}
        item["disk_warning_percent"] = (
            disk_check.get("disk_warning_percent")
            if disk_check.get("disk_warning_percent") is not None
            else int(settings.get("disk_usage_warning_percent", "85"))
        )
        item["disk_critical_percent"] = (
            disk_check.get("disk_critical_percent")
            if disk_check.get("disk_critical_percent") is not None
            else int(settings.get("disk_usage_critical_percent", "95"))
        )
        item["overall_status"] = _system_check_status(item)
        item["configuration_issue"] = None if item["overall_status"] == "maintenance" else _system_check_configuration_issue(item)
        raw_update_error = str((item["updates"] or {}).get("last_error") or "")
        ping_status = str((item["ping_check"] or {}).get("status") or "").lower()
        suppress_transport_error = (
            item["overall_status"] == "maintenance"
            or (ping_status in {"offline", "critical", "failed"} and _is_system_check_transport_error(raw_update_error))
        )
        item["display_update_error"] = "" if suppress_transport_error else raw_update_error
        item["update_problem_visible"] = bool(item["display_update_error"])
        item["uptime_display"] = _format_uptime(item.get("system_uptime_seconds")) if item.get("system_uptime_seconds") is not None else ""

        checked = []
        for row in (item["ping_check"], item["disk_check"], item["http_check"], item["updates"], *item["applications"]):
            if row:
                checked.append(str(row.get("last_checked") or row.get("updated_at") or ""))
        item["last_checked_combined"] = max(checked) if checked else ""
        result.append(item)
    return result


def _first_run_counts(request: Request) -> dict:
    owner_id = int(request.state.user["id"])
    with db() as con:
        return {
            "categories": int(con.execute("SELECT COUNT(*) FROM categories WHERE owner_user_id=?", (owner_id,)).fetchone()[0]),
            "devices": int(con.execute("SELECT COUNT(*) FROM devices WHERE owner_user_id=?", (owner_id,)).fetchone()[0]),
        }


def _first_run_step() -> str:
    value = str(get_settings().get("first_run_step", "categories") or "categories")
    return value if value in {"categories", "items", "notifications", "finish"} else "categories"


def _set_first_run_step(step: str) -> None:
    with db() as con:
        con.execute(
            "INSERT INTO settings(key,value) VALUES ('first_run_step',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (step,),
        )


@app.get("/first-run", response_class=HTMLResponse)
def first_run_wizard(request: Request, step: str = ""):
    current = step if step in {"categories", "items", "notifications", "finish"} else _first_run_step()
    settings = get_settings()
    return templates.TemplateResponse(
        "first_run.html",
        page_context(
            request,
            "first_run",
            step=current,
            categories=fetch_categories(),
            counts=_first_run_counts(request),
            settings=settings,
            notification=notification_settings(),
        ),
    )


@app.post("/first-run/categories/accept")
def first_run_categories_accept(request: Request, categories: list[str] = Form([])):
    _replace_owner_categories(request, categories)
    _set_first_run_step("items")
    return RedirectResponse("/first-run?step=items", status_code=303)


@app.post("/first-run/categories/edit")
def first_run_categories_edit(request: Request):
    _set_first_run_step("categories")
    return RedirectResponse("/first-run?step=categories", status_code=303)


@app.get("/first-run/item-saved", response_class=HTMLResponse)
def first_run_item_saved(request: Request, device_id: int, item_type: str = "device"):
    device = fetch_device(device_id)
    if not device:
        return RedirectResponse("/first-run?step=items", status_code=303)
    return templates.TemplateResponse(
        "first_run_item_saved.html",
        page_context(request, "first_run", device=device, item_type=item_type),
    )


@app.post("/first-run/items/done")
def first_run_items_done(request: Request):
    _set_first_run_step("notifications")
    return RedirectResponse("/first-run?step=notifications", status_code=303)


@app.post("/first-run/notifications/done")
def first_run_notifications_done(request: Request):
    _set_first_run_step("finish")
    return RedirectResponse("/first-run?step=finish", status_code=303)


@app.post("/first-run/complete")
def first_run_complete(request: Request):
    with db() as con:
        con.execute(
            "INSERT INTO settings(key,value) VALUES ('first_run_complete','true') ON CONFLICT(key) DO UPDATE SET value='true'"
        )
        con.execute(
            "INSERT INTO settings(key,value) VALUES ('first_run_step','complete') ON CONFLICT(key) DO UPDATE SET value='complete'"
        )
    return RedirectResponse("/", status_code=303)


@app.post("/first-run/reset")
def first_run_reset(request: Request):
    with db() as con:
        con.execute(
            "INSERT INTO settings(key,value) VALUES ('first_run_complete','false') ON CONFLICT(key) DO UPDATE SET value='false'"
        )
        con.execute(
            "INSERT INTO settings(key,value) VALUES ('first_run_step','categories') ON CONFLICT(key) DO UPDATE SET value='categories'"
        )
    return RedirectResponse("/first-run", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    if str(get_settings().get("first_run_complete", "true")).lower() != "true":
        return RedirectResponse("/first-run", status_code=303)
    devices = fetch_devices()
    firmware_devices = [d for d in devices if category_config(d["category"]).get("show_firmware", True) and _firmware_monitoring_supported(d)]
    counts = {"ok": 0, "attention": 0, "deferred": 0, "unknown": 0}
    for d in firmware_devices:
        status = d["status"] or "unknown"
        counts[status] = counts.get(status, 0) + 1
    action_devices = [d for d in firmware_devices if d["status"] in ("attention", "deferred")]
    hcounts = health_summary()
    all_update_checks = [dict(row) for row in fetch_update_checks()]
    maintenance_device_ids = {
        int(row["device_id"])
        for row in fetch_health_checks()
        if row["device_id"] and bool(row["maintenance"])
    }
    system_checks = [row for row in all_update_checks if int(row["device_id"] or 0) not in maintenance_device_ids]
    application_checks = [dict(row) for row in fetch_application_checks() if int(row["device_id"] or 0) not in maintenance_device_ids]

    def _summary(rows):
        result = {"ok": 0, "available": 0, "failed": 0, "unknown": 0, "disabled": 0}
        for row in rows:
            if not row["enabled"]:
                result["disabled"] += 1
            elif row["status"] in result:
                result[row["status"]] += 1
            else:
                result["unknown"] += 1
        return result

    update_counts = _summary(system_checks)
    application_update = application_update_info()
    application_update_counts = _summary(application_checks)

    system_update_actions = [row for row in system_checks if row["enabled"] and (row["status"] in ("available", "failed") or row["reboot_required"])]
    application_update_actions = [row for row in application_checks if row["enabled"] and row["status"] in ("available", "failed")]
    software_update_count = sum(int(row.get("package_count") or 0) for row in system_checks if row["enabled"] and row["status"] == "available") + sum(1 for row in application_checks if row["enabled"] and row["status"] == "available")
    software_ok_count = sum(1 for row in system_checks if row["enabled"] and row["status"] == "ok") + sum(1 for row in application_checks if row["enabled"] and row["status"] == "ok")
    software_failed_count = sum(1 for row in system_checks if row["enabled"] and row["status"] == "failed") + sum(1 for row in application_checks if row["enabled"] and row["status"] == "failed")

    firmware_attention = bool(action_devices)
    update_problem = any(row["status"] == "failed" for row in system_update_actions)
    application_update_problem = any(row["status"] == "failed" for row in application_update_actions)
    update_attention = bool(system_update_actions)
    application_update_attention = application_update_counts["available"] > 0
    health_problem = (hcounts.get("critical", 0) + hcounts.get("offline", 0)) > 0
    health_attention = hcounts.get("warning", 0) > 0
    health_unknown = hcounts.get("unknown", 0) > 0
    health_maintenance = hcounts.get("maintenance", 0) > 0

    # One shared priority model for actionable Dashboard state.
    # Maintenance is an intentional exclusion, not an attention state:
    # Critical > Attention > Unknown > OK. The System Checks tile itself remains blue.
    if health_problem or update_problem or application_update_problem:
        overall = "problem"
    elif firmware_attention or update_attention or application_update_attention or health_attention:
        overall = "attention"
    elif health_unknown:
        overall = "unknown"
    else:
        overall = "ok"
    return templates.TemplateResponse(
        "dashboard.html",
        page_context(
            request, "dashboard", devices=devices, counts=counts, actions=action_devices, overall=overall,
            health_counts=hcounts, update_counts=update_counts, system_update_actions=system_update_actions,
            application_update_counts=application_update_counts, application_update=application_update,
            application_update_actions=application_update_actions, software_update_count=software_update_count,
            software_ok_count=software_ok_count, software_failed_count=software_failed_count,
        ),
    )


@app.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, category: str = ""):
    devices = fetch_devices()
    categories = fetch_categories()
    requested_category = (category or "").strip()
    # Only accept an existing category as active filter. Matching is
    # case-insensitive while preserving the configured display name.
    active_category = ""
    for configured in categories:
        if configured.strip().casefold() == requested_category.casefold():
            active_category = configured
            break
    all_tags = sorted({tag for d in devices for tag in tag_list(d["tags"] or "")}, key=str.lower)
    return templates.TemplateResponse(
        "devices.html",
        page_context(
            request,
            "devices",
            devices=devices,
            categories=categories,
            all_tags=all_tags,
            active_category=active_category,
        ),
    )



def _find_network_duplicate(hostname: str = "", ipv4_address: str = "", mac_address: str = "", exclude_device_id: int = 0) -> Optional[sqlite3.Row]:
    hostname = (hostname or "").strip().casefold()
    ipv4_address = (ipv4_address or "").strip()
    mac_address = re.sub(r"[^0-9a-f]", "", (mac_address or "").lower())
    for device in fetch_devices():
        if exclude_device_id and int(device["id"]) == int(exclude_device_id):
            continue
        current_hostname = str(device["hostname"] or "").strip().casefold()
        current_ipv4 = str(device["ipv4_address"] or "").strip()
        current_mac = re.sub(r"[^0-9a-f]", "", str(device["mac_address"] or "").lower())
        if ipv4_address and current_ipv4 and ipv4_address == current_ipv4:
            return device
        if hostname and current_hostname and hostname == current_hostname:
            return device
        if mac_address and current_mac and mac_address == current_mac:
            return device
    return None


@app.get("/devices/check-duplicate")
def check_device_duplicate(hostname: str = "", ipv4_address: str = "", mac_address: str = "", exclude_device_id: int = 0):
    duplicate = _find_network_duplicate(hostname, ipv4_address, mac_address, exclude_device_id)
    if not duplicate:
        return JSONResponse({"duplicate": False})
    return JSONResponse({
        "duplicate": True,
        "device_id": int(duplicate["id"]),
        "name": duplicate["display_name"] or duplicate["name"],
        "hostname": duplicate["hostname"] or "",
        "ipv4_address": duplicate["ipv4_address"] or "",
        "mac_address": duplicate["mac_address"] or "",
    })


@app.get("/devices/new", response_class=HTMLResponse)
def new_device(request: Request):
    return templates.TemplateResponse("device_form.html", page_context(request, "devices", device=None, device_profile=None, attachments=[], categories=fetch_categories(), category_configs=fetch_category_configs(), section_config=category_config("Other"), lifecycles=LIFECYCLES, firmware_sources=FIRMWARE_SOURCES, firmware_providers=FIRMWARE_PROVIDERS, check_methods=CHECK_METHODS, confidences=CONFIDENCES, health_check=None, update_check=None, unlinked_health_checks=[]))


@app.post("/devices")
async def create_device(
    request: Request, display_name: str = Form(...), category: str = Form("Other"), vendor: str = Form(""), model: str = Form(""),
    serial_number: str = Form(""), hostname: str = Form(""), ipv4_address: str = Form(""), ipv6_address: str = Form(""), mac_address: str = Form(""), lifecycle: str = Form("Supported"),
    purchase_date: str = Form(""), purchased_from: str = Form(""), purchase_price: str = Form(""),
    condition: str = Form(""), warranty_status: str = Form(""), warranty_until: str = Form(""), extended_warranty: Optional[str] = Form(None),
    current_firmware: str = Form(""), latest_firmware: str = Form(""), latest_firmware_override: str = Form(""), firmware_url: str = Form(""), firmware_lookup: str = Form(""), firmware_provider: str = Form("Auto"), firmware_identifier: str = Form(""), firmware_source: str = Form("Unknown"), check_method: str = Form("Not configured"), release_date: str = Form(""), release_summary: str = Form(""), release_notes_url: str = Form(""), confidence: str = Form("Unknown"),
    auto_check: Optional[str] = Form(None), virtual_device: Optional[str] = Form(None), notes: str = Form(""),
    item_type: str = Form("device"), first_run: Optional[str] = Form(None),
    attachment_description: str = Form(""), attachment_file: Optional[UploadFile] = File(None),
):
    t = now()
    name = display_name
    tags = ""
    purchase_price = format_euro(purchase_price)
    status = "unknown"
    matched_profile = await run_in_threadpool(_available_device_profile, vendor, model, sync_if_empty=True)
    if matched_profile:
        profile_firmware = matched_profile.get("firmware") or {}
        profile_source = profile_firmware.get("source") or {}
        firmware_url = str(profile_source.get("url") or firmware_url).strip()
        firmware_provider = "DJI" if profile_firmware.get("strategy") == "dji_release_notes_pdf" else firmware_provider
        firmware_source = "Official website"
        check_method = "Device Profile"
        confidence = "Official"
    with db() as con:
        cur = con.execute(
            """INSERT INTO devices(owner_user_id, name, display_name, category, vendor, model, serial_number, hostname, ipv4_address, ipv6_address, mac_address, tags, lifecycle, purchase_date, purchased_from, purchase_price, condition, warranty_status, warranty_until, extended_warranty, current_firmware, latest_firmware, latest_firmware_override, firmware_url, firmware_lookup, firmware_provider, firmware_identifier, firmware_source, check_method, release_date, release_summary, release_notes_url, confidence, auto_check, virtual_device, status, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (request.state.user["id"], name, display_name, category, vendor, model, serial_number, hostname, ipv4_address, ipv6_address, mac_address, tags, lifecycle, purchase_date, purchased_from, purchase_price, condition, warranty_status, warranty_until, 1 if extended_warranty else 0, current_firmware, latest_firmware, latest_firmware_override, firmware_url, firmware_lookup, firmware_provider, firmware_identifier, firmware_source, check_method, release_date, release_summary, release_notes_url, confidence, 1 if auto_check else 0, 1 if virtual_device and category.strip().lower() == "server" else 0, status, notes, t, t)
        )
        device_id = cur.lastrowid
    if attachment_file and attachment_file.filename:
        safe = "".join(c for c in attachment_file.filename if c.isalnum() or c in (".", "-", "_", " ")).strip() or "attachment"
        stored = f"{device_id}-{uuid.uuid4().hex}-{safe}"
        content = await attachment_file.read(DEVICE_EXPORT_MAX_BYTES + 1)
        if len(content) > DEVICE_EXPORT_MAX_BYTES:
            return RedirectResponse(f"/devices/{device_id}?attachment_message=Attachment+must+be+50+MB+or+smaller.&attachment_ok=0#attachments", status_code=303)
        with _database_gate.access():
            (UPLOAD_DIR / stored).write_bytes(content)
            with db() as con:
                con.execute(
                    "INSERT INTO attachments(device_id, original_name, stored_name, description, created_at) VALUES (?, ?, ?, ?, ?)",
                    (device_id, attachment_file.filename, stored, attachment_description.strip(), now()),
                )
    initial_check_error = await run_in_threadpool(_initial_device_firmware_check, device_id)
    is_server = item_type == "server" or category.strip().lower() == "server"
    if first_run and is_server:
        return RedirectResponse(f"/devices/{device_id}/host-integration?return_to=first-run", status_code=303)
    if first_run:
        return RedirectResponse(f"/first-run/item-saved?device_id={device_id}&item_type=device", status_code=303)
    if is_server:
        return RedirectResponse(f"/devices/{device_id}/host-integration", status_code=303)
    error_query = f"&firmware_check_error={quote(initial_check_error)}" if initial_check_error else ""
    return RedirectResponse(f"/devices/{device_id}?created=device{error_query}", status_code=303)


DEVICE_EXPORT_FORMAT = "outlaws-inventory-device"
DEVICE_EXPORT_SCHEMA = 1
DEVICE_EXPORT_MAX_BYTES = 50 * 1024 * 1024
DEVICE_EXPORT_MAX_UNCOMPRESSED = 100 * 1024 * 1024


def _device_export_payload(device_id: int) -> tuple[dict, list[sqlite3.Row]]:
    device = fetch_device(device_id)
    if not device:
        raise ValueError("Device not found.")
    device_data = {key: device[key] for key in device.keys() if key != "id"}
    attachments = [item for item in fetch_attachments(device_id) if (UPLOAD_DIR / item["stored_name"]).is_file()]
    attachment_manifest = []
    for item in attachments:
        source = UPLOAD_DIR / item["stored_name"]
        attachment_manifest.append({
            "original_name": item["original_name"],
            "description": item["description"] or "",
            "created_at": item["created_at"],
            "archive_name": f"attachments/{len(attachment_manifest):04d}-{safe_report_filename(item['original_name'])}",
            "size": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        })
    payload = {
        "format": DEVICE_EXPORT_FORMAT,
        "schema_version": DEVICE_EXPORT_SCHEMA,
        "application_version": APP_VERSION,
        "exported_at": now(),
        "device": device_data,
        "attachments": attachment_manifest,
    }
    return payload, attachments


def _safe_device_archive_member(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _find_import_match(con: sqlite3.Connection, device_data: dict) -> sqlite3.Row | None:
    serial = str(device_data.get("serial_number") or "").strip()
    if serial:
        row = con.execute("SELECT * FROM devices WHERE owner_user_id=? AND LOWER(TRIM(serial_number))=LOWER(?) LIMIT 1", (require_current_user_id(), serial)).fetchone()
        if row:
            return row
    display = str(device_data.get("display_name") or device_data.get("name") or "").strip()
    vendor = str(device_data.get("vendor") or "").strip()
    model = str(device_data.get("model") or "").strip()
    if display:
        return con.execute(
            "SELECT * FROM devices WHERE owner_user_id=? AND LOWER(TRIM(display_name))=LOWER(?) AND LOWER(TRIM(vendor))=LOWER(?) AND LOWER(TRIM(model))=LOWER(?) LIMIT 1",
            (require_current_user_id(), display, vendor, model),
        ).fetchone()
    return None


@app.get("/devices/{device_id}/export")
def export_device(device_id: int):
    with _database_gate.access():
        try:
            payload, attachments = _device_export_payload(device_id)
        except ValueError:
            return RedirectResponse("/devices", status_code=303)
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("device.json", json.dumps(payload, indent=2, ensure_ascii=False))
            for entry, original in zip(payload["attachments"], attachments):
                archive.write(UPLOAD_DIR / original["stored_name"], entry["archive_name"])
        output.seek(0)
        filename = f"device-{safe_report_filename(payload['device'].get('display_name') or payload['device'].get('name') or 'export')}.oi-device"
        return StreamingResponse(output, media_type="application/vnd.outlaws-inventory.device+zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/devices/{device_id}/report.pdf")
def device_report(device_id: int):
    device = fetch_device(device_id)
    if not device:
        return RedirectResponse("/devices", status_code=303)
    if device["virtual_device"]:
        return JSONResponse({"detail": "Device reports are only available for physical devices."}, status_code=404)
    pdf = build_device_report_pdf(device, fetch_attachments(device_id))
    filename = f"device-report-{safe_report_filename(display_name(device))}.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/devices/{device_id}", response_class=HTMLResponse)
def device_detail(request: Request, device_id: int):
    device = fetch_device(device_id)
    if not device:
        return RedirectResponse("/devices", status_code=303)
    _normalize_system_checks_for_device(device)
    system_check = next((item for item in _system_check_rows() if int(item["id"]) == int(device_id)), None)
    return templates.TemplateResponse("device_form.html", page_context(request, "devices", device=device, device_profile=_available_device_profile(device["vendor"] or "", device["model"] or ""), attachments=fetch_attachments(device_id), categories=fetch_categories(), category_configs=fetch_category_configs(), section_config=category_config(device["category"]), lifecycles=LIFECYCLES, firmware_sources=FIRMWARE_SOURCES, firmware_providers=FIRMWARE_PROVIDERS, check_methods=CHECK_METHODS, confidences=CONFIDENCES, health_check=fetch_device_health_check(device_id), update_check=fetch_device_update_check(device_id), unlinked_health_checks=fetch_unlinked_health_checks(), ssh_profiles=fetch_ssh_profiles(), update_activity=fetch_device_update_check(device_id), device_uptime=_format_uptime(device["system_uptime_seconds"]) if device["system_uptime_seconds"] is not None else "Pending Check", system_check=system_check, activity_history=fetch_activity_history(device_id, 50)))


@app.post("/devices/{device_id}")
def update_device(
    device_id: int, display_name: str = Form(...), category: str = Form("Other"), vendor: str = Form(""), model: str = Form(""),
    serial_number: str = Form(""), hostname: str = Form(""), ipv4_address: str = Form(""), ipv6_address: str = Form(""), mac_address: str = Form(""), lifecycle: str = Form("Supported"),
    purchase_date: str = Form(""), purchased_from: str = Form(""), purchase_price: str = Form(""),
    condition: str = Form(""), warranty_status: str = Form(""), warranty_until: str = Form(""), extended_warranty: Optional[str] = Form(None),
    current_firmware: str = Form(""), latest_firmware: str = Form(""), latest_firmware_override: str = Form(""), firmware_url: str = Form(""), firmware_lookup: str = Form(""), firmware_provider: str = Form("Auto"), firmware_identifier: str = Form(""), firmware_source: str = Form("Unknown"), check_method: str = Form("Not configured"), release_date: str = Form(""), release_summary: str = Form(""), release_notes_url: str = Form(""), confidence: str = Form("Unknown"),
    auto_check: Optional[str] = Form(None), virtual_device: Optional[str] = Form(None), status: str = Form("unknown"), notes: str = Form(""),
):
    name = display_name
    purchase_price = format_euro(purchase_price)
    matched_profile = _available_device_profile(vendor, model, sync_if_empty=True)
    if matched_profile:
        profile_firmware = matched_profile.get("firmware") or {}
        profile_source = profile_firmware.get("source") or {}
        firmware_url = str(profile_source.get("url") or firmware_url).strip()
        firmware_provider = "DJI" if profile_firmware.get("strategy") == "dji_release_notes_pdf" else firmware_provider
        firmware_source = "Official website"
        check_method = "Device Profile"
        confidence = "Official"
    with db() as con:
        existing = con.execute("SELECT tags FROM devices WHERE id=? AND owner_user_id=?", (device_id, require_current_user_id())).fetchone()
        tags = existing["tags"] if existing else ""
        con.execute(
            """UPDATE devices SET name=?, display_name=?, category=?, vendor=?, model=?, serial_number=?, hostname=?, ipv4_address=?, ipv6_address=?, mac_address=?, tags=?, lifecycle=?, purchase_date=?, purchased_from=?, purchase_price=?, condition=?, warranty_status=?, warranty_until=?, extended_warranty=?, current_firmware=?, latest_firmware=?, latest_firmware_override=?, firmware_url=?, firmware_lookup=?, firmware_provider=?, firmware_identifier=?, firmware_source=?, check_method=?, release_date=?, release_summary=?, release_notes_url=?, confidence=?, auto_check=?, virtual_device=?, status=?, notes=?, updated_at=? WHERE id=? AND owner_user_id=?""",
            (name, display_name, category, vendor, model, serial_number, hostname, ipv4_address, ipv6_address, mac_address, tags, lifecycle, purchase_date, purchased_from, purchase_price, condition, warranty_status, warranty_until, 1 if extended_warranty else 0, current_firmware, latest_firmware, latest_firmware_override, firmware_url, firmware_lookup, firmware_provider, firmware_identifier, firmware_source, check_method, release_date, release_summary, release_notes_url, confidence, 1 if auto_check else 0, 1 if virtual_device and category.strip().lower() == "server" else 0, status, notes, now(), device_id, require_current_user_id())
        )
    return RedirectResponse(f"/devices/{device_id}", status_code=303)


@app.post("/devices/{device_id}/delete")
def delete_device(device_id: int):
    with _database_gate.access():
        with db() as con:
            con.execute("BEGIN IMMEDIATE")
            owned = con.execute("SELECT id FROM devices WHERE id=? AND owner_user_id=?", (device_id, require_current_user_id())).fetchone()
            if not owned:
                return RedirectResponse("/devices", status_code=303)
            attachments = con.execute("SELECT stored_name FROM attachments WHERE device_id=?", (device_id,)).fetchall()
            con.execute("DELETE FROM attachments WHERE device_id=?", (device_id,))
            con.execute("DELETE FROM devices WHERE id=? AND owner_user_id=?", (device_id, require_current_user_id()))
        for attachment in attachments:
            (UPLOAD_DIR / attachment["stored_name"]).unlink(missing_ok=True)
        return RedirectResponse("/devices", status_code=303)


@app.get("/devices/{device_id}/check", include_in_schema=False)
def check_one_refresh(device_id: int):
    return RedirectResponse(f"/devices/{device_id}", status_code=303)

def _check_and_store_device_firmware(device_id: int) -> str:
    device = fetch_device(device_id)
    if not device:
        return ""
    info = check_device(device)
    with db() as con:
        con.execute("""UPDATE devices SET status=?, latest_firmware=?, release_date=?, release_summary=?, release_notes_url=?, confidence=?, firmware_source=?, check_method=?, last_checked=?, updated_at=? WHERE id=? AND owner_user_id=?""", (info["status"], info.get("automatic_latest", info["latest"]), info["release_date"], info["summary"], info["notes_url"], info["confidence"], info.get("source", device["firmware_source"] or "Unknown"), info.get("method", device["check_method"] or "Not configured"), now(), now(), device_id, require_current_user_id()))
    return str(info.get("error") or "").strip()


def _initial_device_firmware_check(device_id: int) -> str:
    """One initial check for a saved device with a configured firmware source.

    This is independent of the recurring auto_check preference. Failures must
    never undo successful device creation or invite a duplicate Save.
    """
    try:
        device = fetch_device(device_id)
        if not device or not str(device["firmware_url"] or "").strip():
            return ""
        if not category_config(device["category"]).get("show_firmware", True) or not _firmware_monitoring_supported(device):
            return ""
        return _check_and_store_device_firmware(device_id)
    except Exception:
        return "Device saved, but its initial firmware check could not complete. Try Check Now."


@app.post("/devices/{device_id}/check")
def check_one(device_id: int):
    if not fetch_device(device_id):
        return RedirectResponse(f"/devices/{device_id}#firmware", status_code=303)
    error = _check_and_store_device_firmware(device_id)
    dispatch_notifications()
    if error:
        return RedirectResponse(f"/devices/{device_id}?firmware_check_error={quote(error)}#firmware", status_code=303)
    return RedirectResponse(f"/devices/{device_id}#firmware", status_code=303)


@app.post("/devices/{device_id}/mark-updated")
def mark_firmware_updated(device_id: int, return_to: str = Form("device")):
    device = fetch_device(device_id)
    if device:
        effective_latest = _effective_latest_version(device["latest_firmware"] or "", device["latest_firmware_override"] or "")
        if not effective_latest:
            return RedirectResponse("/firmware", status_code=303)
        previous_version = str(device["current_firmware"] or "").strip()
        with db() as con:
            con.execute("UPDATE devices SET current_firmware=?, status='ok', last_firmware_update=?, updated_at=? WHERE id=?", (effective_latest, now(), now(), device_id))
        version_summary = f"{previous_version or 'Unknown'} → {effective_latest}"
        add_activity_event(device_id, require_current_user_id(), "firmware_update", "Firmware Update", "success", version_summary)
    return RedirectResponse("/firmware" if return_to == "firmware" else f"/devices/{device_id}", status_code=303)


@app.post("/devices/{device_id}/defer")
def defer_firmware_update(device_id: int, deferred_reason: str = Form(""), deferred_until: str = Form("Next firmware release")):
    device = fetch_device(device_id)
    if device and device["latest_firmware"]:
        with db() as con:
            con.execute("UPDATE devices SET status='deferred', deferred_version=?, deferred_reason=?, deferred_until=?, updated_at=? WHERE id=?", (device["latest_firmware"], deferred_reason, deferred_until, now(), device_id))
    return RedirectResponse(f"/devices/{device_id}", status_code=303)


@app.post("/devices/{device_id}/attachments")
async def upload_attachment(device_id: int, description: str = Form(""), file: UploadFile = File(...)):
    if not fetch_device(device_id):
        return RedirectResponse("/devices", status_code=303)
    original_name = Path(file.filename or "attachment").name[:255] or "attachment"
    suffix = Path(original_name).suffix[:16]
    stored = f"{device_id}-{uuid.uuid4().hex}{suffix}"
    content = await file.read(DEVICE_EXPORT_MAX_BYTES + 1)
    if not content or len(content) > DEVICE_EXPORT_MAX_BYTES:
        return RedirectResponse(f"/devices/{device_id}?attachment_message=Attachment+must+be+50+MB+or+smaller.&attachment_ok=0#attachments", status_code=303)
    with _database_gate.access():
        attachment_path = UPLOAD_DIR / stored
        attachment_path.write_bytes(content)
        attachment_path.chmod(0o600)
        with db() as con:
            con.execute("INSERT INTO attachments(device_id, original_name, stored_name, description, created_at) VALUES (?, ?, ?, ?, ?)", (device_id, original_name, stored, description, now()))
        return RedirectResponse(f"/devices/{device_id}", status_code=303)


@app.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int):
    with db() as con:
        a = con.execute("SELECT a.* FROM attachments a JOIN devices d ON d.id=a.device_id WHERE a.id=? AND d.owner_user_id=?", (attachment_id, require_current_user_id())).fetchone()
    if not a:
        return RedirectResponse("/devices", status_code=303)
    return FileResponse(UPLOAD_DIR / a["stored_name"], filename=a["original_name"])


@app.post("/attachments/{attachment_id}/delete")
def delete_attachment(attachment_id: int):
    with _database_gate.access():
        with db() as con:
            a = con.execute("SELECT a.* FROM attachments a JOIN devices d ON d.id=a.device_id WHERE a.id=? AND d.owner_user_id=?", (attachment_id, require_current_user_id())).fetchone()
            device_id = a["device_id"] if a else 0
            if a:
                (UPLOAD_DIR / a["stored_name"]).unlink(missing_ok=True)
                con.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        return RedirectResponse(f"/devices/{device_id}", status_code=303)


@app.post("/devices/{device_id}/link-health")
def link_device_health(device_id: int, health_check_id: int = Form(...)):
    if fetch_device(device_id) and fetch_health_check(health_check_id):
        with db() as con:
            con.execute("UPDATE health_checks SET device_id=NULL, updated_at=? WHERE device_id=?", (now(), device_id))
            con.execute("UPDATE health_checks SET device_id=?, updated_at=? WHERE id=?", (device_id, now(), health_check_id))
    return RedirectResponse(f"/devices/{device_id}", status_code=303)


@app.post("/devices/{device_id}/unlink-health")
def unlink_device_health(device_id: int):
    with db() as con:
        con.execute("UPDATE health_checks SET device_id=NULL, updated_at=? WHERE device_id=?", (now(), device_id))
    return RedirectResponse(f"/devices/{device_id}", status_code=303)


@app.get("/firmware", response_class=HTMLResponse)
def firmware_page(request: Request):
    # Respect the same category-level Firmware setting used on device pages.
    devices = [d for d in fetch_devices() if category_config(d["category"]).get("show_firmware", True) and _firmware_monitoring_supported(d)]
    return templates.TemplateResponse("firmware.html", page_context(request, "firmware", devices=devices, check_all_running=_operation_state("firmware-check-all")["running"]))


@app.post("/firmware/check-all")
def check_all():
    user_id = require_current_user_id()
    def action() -> None:
        execute_all_firmware_checks()
        dispatch_notifications()
    _start_user_operation("firmware-check-all", user_id, action)
    return RedirectResponse("/firmware", status_code=303)

@app.get("/firmware/check-all/status", include_in_schema=False)
def firmware_check_all_status():
    return JSONResponse(_operation_state("firmware-check-all"))

@app.get("/firmware/check-all", include_in_schema=False)
def firmware_check_all_refresh():
    return RedirectResponse("/firmware", status_code=303)



@app.get("/system-checks", response_class=HTMLResponse)
def system_checks_page(request: Request):
    _normalize_all_system_checks()
    servers = _system_check_rows()
    counts = {
        "total": len(servers),
        "ok": sum(1 for item in servers if item["overall_status"] == "ok"),
        "attention": sum(1 for item in servers if item["overall_status"] == "attention"),
        "critical": sum(1 for item in servers if item["overall_status"] == "critical"),
        "reboot": sum(1 for item in servers if item["overall_status"] == "reboot"),
        "maintenance": sum(1 for item in servers if item["overall_status"] == "maintenance"),
        "unknown": sum(1 for item in servers if item["overall_status"] == "unknown"),
    }
    return templates.TemplateResponse(
        "system_checks.html",
        page_context(request, "system_checks", servers=servers, counts=counts, check_all_running=_operation_state("system-check-all")["running"]),
    )


def run_all_system_checks(*, notify: bool = True, session_scoped: bool = True) -> dict[str, int]:
    """Run the same health/update refresh used by Check All.

    Setup restore has no authenticated browser user yet, so it uses the persisted
    owner IDs on the checks instead of session-scoped fetch helpers.
    """
    if session_scoped:
        _normalize_all_system_checks()
        health_checks = fetch_health_checks()
        update_checks = fetch_update_checks()
        application_checks = fetch_application_checks()
    else:
        with db() as con:
            health_checks = con.execute(
                """SELECT * FROM health_checks
                   ORDER BY owner_user_id,device_id,
                            CASE LOWER(COALESCE(check_type,'ping'))
                              WHEN 'ping' THEN 0
                              WHEN 'http' THEN 1
                              WHEN 'disk' THEN 2
                              ELSE 3
                            END,id"""
            ).fetchall()
            update_checks = con.execute(
                "SELECT * FROM update_checks ORDER BY owner_user_id,id"
            ).fetchall()
            application_checks = con.execute(
                "SELECT * FROM application_checks ORDER BY owner_user_id,id"
            ).fetchall()

    stats = {"health_checked": 0, "health_failed": 0, "updates_checked": 0, "updates_failed": 0, "applications_checked": 0, "applications_failed": 0}

    for check in health_checks:
        if check["enabled"] and not check["maintenance"]:
            try:
                execute_health_check(check)
                stats["health_checked"] += 1
            except Exception as exc:
                stats["health_failed"] += 1
                with db() as con:
                    con.execute(
                        """UPDATE health_checks
                           SET status='unknown', last_checked=?, last_error=?, updated_at=?
                           WHERE id=?""",
                        (now(), f"Status refresh failed: {exc}", now(), check["id"]),
                    )

    for check in update_checks:
        if check["enabled"] and not _device_system_checks_maintenance(check["device_id"], check["owner_user_id"]):
            try:
                execute_update_check(check)
                stats["updates_checked"] += 1
            except Exception as exc:
                stats["updates_failed"] += 1
                with db() as con:
                    con.execute(
                        """UPDATE update_checks
                           SET status='failed', last_checked=?, last_error=?, updated_at=?
                           WHERE id=?""",
                        (now(), f"Check All failed: {exc}", now(), check["id"]),
                    )

    for check in application_checks:
        if check["enabled"] and not _device_system_checks_maintenance(check["device_id"], check["owner_user_id"]):
            try:
                execute_application_check(check)
                stats["applications_checked"] += 1
            except Exception as exc:
                stats["applications_failed"] += 1
                with db() as con:
                    con.execute("UPDATE application_checks SET status='failed', last_checked=?, last_error=?, updated_at=? WHERE id=?",
                                (now(), f"Check All failed: {exc}", now(), check["id"]))

    if notify:
        dispatch_notifications()
    return stats


@app.post("/system-checks/check-all")
def system_checks_check_all(request: Request):
    user_id = require_current_user_id()
    _start_user_operation(
        "system-check-all",
        user_id,
        lambda: run_all_system_checks(notify=True, session_scoped=True),
    )
    return RedirectResponse("/system-checks", status_code=303)

@app.get("/system-checks/check-all/status", include_in_schema=False)
def system_checks_check_all_status():
    return JSONResponse(_operation_state("system-check-all"))

@app.get("/system-checks/check-all", include_in_schema=False)
def system_checks_check_all_refresh():
    return RedirectResponse("/system-checks", status_code=303)


@app.get("/system-checks/{device_id}", response_class=HTMLResponse)
def system_check_detail(request: Request, device_id: int):
    device = fetch_device(device_id)
    if device:
        _normalize_system_checks_for_device(device)
    server = next((item for item in _system_check_rows() if int(item["id"]) == int(device_id)), None)
    if not server:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "system_check_detail.html",
        page_context(request, "system_checks", server=server, activity_history=fetch_activity_history(device_id, 50), activity_history_groups=group_activity_history(fetch_activity_history(device_id, 50)), upgrade_result=request.query_params.get("upgrade", ""), reboot_result=request.query_params.get("reboot", ""), minecraft_update_result=request.query_params.get("minecraft_update", "")),
    )



@app.post("/system-checks/{device_id}")
def save_system_check_detail(
    request: Request,
    device_id: int,
    check_ping: Optional[str] = Form(None),
    check_disk: Optional[str] = Form(None),
    check_http: Optional[str] = Form(None),
    check_apt_updates: Optional[str] = Form(None),
    check_pihole: Optional[str] = Form(None),
    check_minecraft: Optional[str] = Form(None),
    minecraft_jar_path: str = Form(""),
    http_url: str = Form(""),
    disk_warning_percent: int = Form(85),
    disk_critical_percent: int = Form(95),
    maintenance: Optional[str] = Form(None),
    autosave: Optional[str] = Form(None),
):
    device = fetch_device(device_id)
    if not device:
        raise HTTPException(status_code=404)
    checks = [name for name, enabled in (("ping", check_ping), ("disk", check_disk), ("http", check_http)) if enabled]
    existing = fetch_device_health_check(device_id)
    existing_health_group = fetch_health_group(int(existing["id"])) if existing else []
    previously_enabled_health_types = {str(row["check_type"]) for row in existing_health_group if row["enabled"]}
    previous_http_url = next((str(row["url"] or "").strip() for row in existing_health_group if str(row["check_type"]) == "http"), "")
    requested_http_url = http_url.strip()
    http_url_changed = "http" in set(checks) and requested_http_url != previous_http_url
    requested_health_types = set(checks)
    newly_enabled_health_types = requested_health_types - previously_enabled_health_types
    previous_maintenance = bool(existing["maintenance"]) if existing else False
    requested_maintenance = bool(maintenance)
    check_id = _save_health_group(
        int(existing["id"]) if existing else None,
        device["display_name"] or device["name"],
        device_id,
        resolved_target(device_id, ""),
        int(get_settings().get("default_health_check_interval_minutes", "10")),
        True,
        bool(maintenance),
        checks,
        http_url,
        disk_warning_percent,
        disk_critical_percent,
    )
    if previous_maintenance != requested_maintenance:
        add_activity_event(
            device_id, require_current_user_id(), "maintenance",
            "Maintenance Mode Enabled" if requested_maintenance else "Maintenance Mode Disabled",
            "info", "System Checks excluded during maintenance." if requested_maintenance else "System Checks returned to normal monitoring."
        )
    if not autosave:
        _run_saved_health_group(check_id)
    elif (newly_enabled_health_types or http_url_changed) and not requested_maintenance:
        # Autosave validates only checks that were just enabled, plus HTTP when its
        # configured URL changes. Other health results remain authoritative.
        for health_check in fetch_health_group(check_id):
            check_type = str(health_check["check_type"])
            if health_check["enabled"] and (check_type in newly_enabled_health_types or (check_type == "http" and http_url_changed)):
                execute_health_check(health_check)

    existing_update = fetch_device_update_check(device_id)
    apt_was_enabled = bool(existing_update and existing_update["enabled"])
    apt_available = bool(device["managed_host"] and device["managed_ssh_profile_id"])
    if check_apt_updates and apt_available:
        profile_id = int(device["managed_ssh_profile_id"] or 0)
        ensure_managed_host_checks(
            device,
            profile_id,
            str(device["managed_system_type"] or "debian"),
            False,
            True,
        )
        update_check = fetch_device_update_check(device_id)
        if update_check and update_check["enabled"] and (not autosave or not apt_was_enabled):
            execute_update_check(update_check)
    elif check_apt_updates and not apt_available:
        if not (existing_update and existing_update["enabled"]):
            if autosave:
                return JSONResponse({"ok": False, "detail": "Managed SSH setup required."}, status_code=409)
            return RedirectResponse(f"/system-checks/{device_id}?apt=setup-required", status_code=303)
    elif apt_available and existing_update and existing_update["enabled"]:
        with db() as con:
            con.execute(
                "UPDATE update_checks SET enabled=0, status='unknown', package_count=0, packages_json='[]', updated_at=? WHERE id=? AND owner_user_id=?",
                (now(), existing_update["id"], require_current_user_id()),
            )

    existing_pihole = fetch_device_application_check(device_id, "pihole")
    pihole_was_enabled = bool(existing_pihole and existing_pihole["enabled"])
    if check_pihole and apt_available:
        profile_id = int(device["managed_ssh_profile_id"] or 0)
        with db() as con:
            t = now()
            if existing_pihole:
                con.execute("UPDATE application_checks SET ssh_profile_id=?, enabled=1, status=CASE WHEN enabled=0 THEN 'unknown' ELSE status END, updated_at=? WHERE id=? AND owner_user_id=?",
                            (profile_id, t, existing_pihole["id"], require_current_user_id()))
            else:
                con.execute("INSERT INTO application_checks(device_id,owner_user_id,ssh_profile_id,application_type,enabled,status,created_at,updated_at) VALUES (?,?,?,'pihole',1,'unknown',?,?)",
                            (device_id, require_current_user_id(), profile_id, t, t))
        pihole_check = fetch_device_application_check(device_id, "pihole")
        if pihole_check and (not autosave or not pihole_was_enabled):
            execute_application_check(pihole_check)
    elif check_pihole and not apt_available:
        if autosave:
            return JSONResponse({"ok": False, "detail": "Managed SSH setup required."}, status_code=409)
        return RedirectResponse(f"/system-checks/{device_id}?pihole=setup-required", status_code=303)
    elif existing_pihole and existing_pihole["enabled"]:
        with db() as con:
            con.execute("UPDATE application_checks SET enabled=0, status='unknown', details_json='{}', updated_at=? WHERE id=? AND owner_user_id=?",
                        (now(), existing_pihole["id"], require_current_user_id()))

    existing_minecraft = fetch_device_application_check(device_id, "minecraft")
    minecraft_was_enabled = bool(existing_minecraft and existing_minecraft["enabled"])
    if check_minecraft and apt_available:
        profile_id = int(device["managed_ssh_profile_id"] or 0)
        with db() as con:
            t = now()
            if existing_minecraft:
                con.execute("UPDATE application_checks SET ssh_profile_id=?, minecraft_jar_path=?, enabled=1, status=CASE WHEN enabled=0 THEN 'unknown' ELSE status END, updated_at=? WHERE id=? AND owner_user_id=?", (profile_id, minecraft_jar_path.strip(), t, existing_minecraft["id"], require_current_user_id()))
            else:
                con.execute("INSERT INTO application_checks(device_id,owner_user_id,ssh_profile_id,application_type,minecraft_jar_path,enabled,status,created_at,updated_at) VALUES (?,?,?,'minecraft',?,1,'unknown',?,?)", (device_id, require_current_user_id(), profile_id, minecraft_jar_path.strip(), t, t))
        minecraft_check = fetch_device_application_check(device_id, "minecraft")
        if minecraft_check and (not autosave or not minecraft_was_enabled):
            execute_application_check(minecraft_check)
    elif check_minecraft and not apt_available:
        if autosave: return JSONResponse({"ok": False, "detail": "Managed SSH setup required."}, status_code=409)
        return RedirectResponse(f"/system-checks/{device_id}?minecraft=setup-required", status_code=303)
    elif existing_minecraft and existing_minecraft["enabled"]:
        with db() as con:
            con.execute("UPDATE application_checks SET enabled=0, status='unknown', details_json='{}', updated_at=? WHERE id=? AND owner_user_id=?", (now(), existing_minecraft["id"], require_current_user_id()))

    refreshed = fetch_device(device_id)
    if not autosave and refreshed and refreshed["managed_host"] and refreshed["managed_ssh_profile_id"]:
        validation = managed_host_validation(refreshed)
        store_managed_host_validation(device_id, validation)

    if autosave:
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)



@app.get("/system-checks/{device_id}/check", include_in_schema=False)
def system_check_device_refresh(device_id: int):
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)

@app.get("/system-checks/{device_id}/upgrade", include_in_schema=False)
def system_upgrade_refresh(device_id: int):
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)

@app.get("/system-checks/{device_id}/applications/pihole/update", include_in_schema=False)
def pihole_upgrade_refresh(device_id: int):
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)

@app.get("/system-checks/{device_id}/applications/minecraft/update", include_in_schema=False)
def minecraft_upgrade_refresh(device_id: int):
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)

@app.get("/system-checks/{device_id}/reboot", include_in_schema=False)
def system_reboot_refresh(device_id: int):
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)

@app.post("/system-checks/{device_id}/check")
def check_system_check_device(device_id: int):
    device = fetch_device(device_id)
    if not device:
        raise HTTPException(status_code=404)
    _normalize_system_checks_for_device(device)
    for check in fetch_health_checks():
        if int(check["device_id"] or 0) == int(device_id) and check["enabled"] and not check["maintenance"]:
            execute_health_check(check)
    update_check = fetch_device_update_check(device_id)
    if update_check and update_check["enabled"]:
        execute_update_check(update_check)
    for application_check in fetch_application_checks():
        if int(application_check["device_id"] or 0) == int(device_id) and application_check["enabled"]:
            execute_application_check(application_check)
    dispatch_notifications()
    return RedirectResponse(f"/system-checks/{device_id}", status_code=303)


@app.post("/system-checks/{device_id}/upgrade")
def upgrade_system_check_device(device_id: int):
    check = fetch_device_update_check(device_id)
    if not check or not check["enabled"] or check["status"] != "available":
        return RedirectResponse(f"/system-checks/{device_id}?upgrade=skipped", status_code=303)
    execute_apt_upgrade(check)
    refreshed = fetch_device_update_check(device_id)
    result = "success" if refreshed and refreshed["upgrade_status"] == "success" else "failed"
    return RedirectResponse(f"/system-checks/{device_id}?upgrade={result}", status_code=303)


@app.post("/system-checks/{device_id}/applications/pihole/update")
def update_pihole_system_check_device(device_id: int):
    check = fetch_device_application_check(device_id, "pihole")
    if not check or not check["enabled"] or check["status"] != "available":
        return RedirectResponse(f"/system-checks/{device_id}?pihole_update=skipped", status_code=303)
    execute_pihole_update(check)
    refreshed = fetch_device_application_check(device_id, "pihole")
    result = "success" if refreshed and refreshed["update_status"] == "success" else "failed"
    dispatch_notifications()
    return RedirectResponse(f"/system-checks/{device_id}?pihole_update={result}", status_code=303)


@app.post("/system-checks/{device_id}/applications/minecraft/update")
def update_minecraft_system_check_device(device_id: int):
    check = fetch_device_application_check(device_id, "minecraft")
    if not check or not check["enabled"] or check["status"] != "available":
        return RedirectResponse(f"/system-checks/{device_id}?minecraft_update=skipped", status_code=303)
    execute_minecraft_update(check)
    refreshed = fetch_device_application_check(device_id, "minecraft")
    result = "success" if refreshed and refreshed["update_status"] == "success" else "failed"
    dispatch_notifications()
    return RedirectResponse(f"/system-checks/{device_id}?minecraft_update={result}", status_code=303)


@app.post("/system-checks/{device_id}/reboot")
def reboot_system_check_device(device_id: int):
    check = fetch_device_update_check(device_id)
    if not check or not check["enabled"] or not check["reboot_required"]:
        return RedirectResponse(f"/system-checks/{device_id}?reboot=skipped", status_code=303)
    result = execute_remote_reboot(check)
    add_activity_event(device_id, int(check["owner_user_id"]), "reboot", "Reboot", str(result["status"]), "Host reboot completed." if result["status"] == "success" else "Host reboot failed.", str(result.get("output", "")))
    return RedirectResponse(f"/system-checks/{device_id}?reboot={result['status']}", status_code=303)


@app.get("/health", response_class=HTMLResponse)
def health_page(request: Request):
    return RedirectResponse("/system-checks", status_code=303)


@app.get("/health/new", response_class=HTMLResponse)
def new_health_check(request: Request):
    return RedirectResponse("/system-checks", status_code=303)


@app.get("/health/check-all", include_in_schema=False)
def health_check_all_refresh():
    return RedirectResponse("/system-checks", status_code=303)

@app.post("/health/check-all")
def check_health_all():
    run_due_health_checks(force=True); dispatch_notifications(); return RedirectResponse("/system-checks", status_code=303)


def _save_health_group(group_id: int | None, name: str, device_id: int, host: str, interval_minutes: int, enabled: bool, maintenance: bool, checks: list[str], http_url: str, disk_warning_percent: int, disk_critical_percent: int) -> int:
    disk_warning_percent=max(1,min(99,int(disk_warning_percent)))
    disk_critical_percent=max(disk_warning_percent+1,min(100,int(disk_critical_percent)))
    owner=require_current_user_id(); t=now(); target=resolved_target(device_id or None, host); key=f"device:{device_id}" if device_id else f"manual:{uuid.uuid4().hex}"
    existing=[]
    if group_id:
        existing=fetch_health_group(group_id)
        if existing: key=health_group_key(existing[0])
    by_type={str(r["check_type"]):r for r in existing}
    if not checks:
        # It is valid for a server to have no Ping/Disk/HTTP health checks. Keep
        # existing rows disabled so the user's choice persists and can be
        # re-enabled later, while the scheduler and overview ignore them.
        if not existing:
            return 0
        with db() as con:
            con.execute(
                "UPDATE health_checks SET enabled=0, maintenance=?, status='unknown', updated_at=? WHERE owner_user_id=? AND group_key=?",
                (1 if maintenance else 0, t, owner, key),
            )
        return int(existing[0]["id"])
    with db() as con:
        for check_type in checks:
            url=http_url.strip() if check_type=="http" else ""
            if check_type in by_type:
                previous_status = str(by_type[check_type]["status"] or "unknown")
                if maintenance:
                    next_status = "maintenance"
                elif int(by_type[check_type]["maintenance"] or 0) and previous_status == "maintenance":
                    next_status = "unknown"
                else:
                    # Configuration autosave must not invalidate an otherwise fresh
                    # result. Newly added checks start Unknown and are validated by
                    # the caller immediately.
                    next_status = previous_status
                con.execute("UPDATE health_checks SET device_id=?,owner_user_id=?,name=?,host=?,url=?,interval_minutes=?,enabled=?,maintenance=?,status=?,group_key=?,disk_warning_percent=?,disk_critical_percent=?,updated_at=? WHERE id=? AND owner_user_id=?",
                    (device_id or None,owner,name,target,url,interval_minutes or 10,1 if enabled else 0,1 if maintenance else 0,next_status,key,disk_warning_percent if check_type=="disk" else None,disk_critical_percent if check_type=="disk" else None,t,by_type[check_type]["id"],owner))
            else:
                con.execute("INSERT INTO health_checks(device_id,owner_user_id,name,host,check_type,url,interval_minutes,enabled,maintenance,status,group_key,disk_warning_percent,disk_critical_percent,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (device_id or None,owner,name,target,check_type,url,interval_minutes or 10,1 if enabled else 0,1 if maintenance else 0,'maintenance' if maintenance else 'unknown',key,disk_warning_percent if check_type=="disk" else None,disk_critical_percent if check_type=="disk" else None,t,t))
        for check_type,row in by_type.items():
            if check_type not in checks: con.execute("DELETE FROM health_checks WHERE id=? AND owner_user_id=?",(row["id"],owner))
        first=con.execute("SELECT id FROM health_checks WHERE owner_user_id=? AND group_key=? ORDER BY id LIMIT 1",(owner,key)).fetchone()
    return int(first["id"])


def _run_saved_health_group(check_id: int) -> None:
    """Immediately validate a saved, enabled Health configuration."""
    for check in fetch_health_group(check_id):
        if check["enabled"]:
            execute_health_check(check)
    dispatch_notifications()


@app.post("/health")
def create_health_check(name: str=Form(...), device_id:int=Form(0), host:str=Form(""), interval_minutes:int=Form(10), enabled:Optional[str]=Form(None), maintenance:Optional[str]=Form(None), check_ping:Optional[str]=Form(None), check_disk:Optional[str]=Form(None), check_http:Optional[str]=Form(None), http_url:str=Form(""),disk_warning_percent:int=Form(85),disk_critical_percent:int=Form(95)):
    checks=[t for t,v in (("ping",check_ping),("disk",check_disk),("http",check_http)) if v]
    check_id=_save_health_group(None,name,device_id,host,interval_minutes,bool(enabled),bool(maintenance),checks,http_url,max(1,min(99,disk_warning_percent)),max(2,min(100,disk_critical_percent)))
    _run_saved_health_group(check_id)
    return RedirectResponse(f"/system-checks/{device_id}" if device_id else "/system-checks",status_code=303)


@app.get("/health/{check_id}", response_class=HTMLResponse)
def edit_health_check(request:Request, check_id:int):
    return RedirectResponse("/system-checks", status_code=303)


@app.post("/health/{check_id}")
def update_health_check(check_id:int,name:str=Form(...),device_id:int=Form(0),host:str=Form(""),interval_minutes:int=Form(10),enabled:Optional[str]=Form(None),maintenance:Optional[str]=Form(None),check_ping:Optional[str]=Form(None),check_disk:Optional[str]=Form(None),check_http:Optional[str]=Form(None),http_url:str=Form(""),disk_warning_percent:int=Form(85),disk_critical_percent:int=Form(95)):
    checks=[t for t,v in (("ping",check_ping),("disk",check_disk),("http",check_http)) if v]
    new_id=_save_health_group(check_id,name,device_id,host,interval_minutes,bool(enabled),bool(maintenance),checks,http_url,max(1,min(99,disk_warning_percent)),max(2,min(100,disk_critical_percent)))
    _run_saved_health_group(new_id)
    return RedirectResponse(f"/system-checks/{device_id}" if device_id else "/system-checks",status_code=303)


@app.post("/health/{check_id}/delete")
def delete_health_check(check_id:int):
    rows=fetch_health_group(check_id)
    with db() as con:
        for row in rows: con.execute("DELETE FROM health_checks WHERE id=? AND owner_user_id=?",(row["id"],require_current_user_id()))
    return RedirectResponse("/health",status_code=303)


@app.post("/health/{check_id}/check")
def check_health_one(check_id:int):
    for check in fetch_health_group(check_id): execute_health_check(check)
    dispatch_notifications(); return RedirectResponse("/health",status_code=303)


def _run_delayed(command: list[str], delay: float = 1.0) -> None:
    def worker() -> None:
        time.sleep(delay)
        subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=worker, daemon=True).start()


def _create_reconnect_action(kind: str, expected_version: str = "") -> str:
    action_id = uuid.uuid4().hex
    payload = {
        "kind": kind,
        "created_at": time.time(),
        "previous_startup_id": PROCESS_START_ID,
        "expected_version": normalize_release_version(expected_version),
    }
    (RECONNECT_DIR / f"{action_id}.json").write_text(json.dumps(payload), encoding="utf-8")
    return action_id


def _reconnect_wait_page(
    heading: str,
    detail_lines: list[str],
    success_url: str,
    action_id: str,
    *,
    fallback_url: str = "/settings",
) -> HTMLResponse:
    details = "<br>".join(detail_lines)
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{heading}</title><style>
:root{{--bg:#0b1220;--panel:#121c2d;--line:#25354d;--text:#e8eef7;--muted:#8ea0b8}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at top left,#172744,#0b1220 42%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
.wait-card{{width:min(460px,100%);padding:34px;border:1px solid var(--line);border-radius:20px;background:rgba(18,28,45,.96);box-shadow:0 22px 70px rgba(0,0,0,.42);text-align:center}}
.spinner{{width:42px;height:42px;margin:0 auto 18px;border:4px solid rgba(157,204,255,.18);border-top-color:#9dccff;border-radius:50%;animation:spin .8s linear infinite}}
h2{{margin:0 0 8px;font-size:22px}}p{{margin:0;color:var(--muted);line-height:1.5}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
</style></head><body><main class="wait-card"><div class="spinner" aria-hidden="true"></div><h2>{heading}</h2><p>{details}</p></main>
<script>
const actionId={json.dumps(action_id)};
const successUrl={json.dumps(success_url)};
let done=false;
let attempts=0;
let timer=null;
function schedule(delay=900){{
  if(done) return;
  window.clearTimeout(timer);
  timer=window.setTimeout(probe,delay);
}}
async function probe(){{
  if(done) return;
  attempts+=1;
  const controller=new AbortController();
  const timeout=window.setTimeout(()=>controller.abort(),2200);
  const nonce=Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);
  try{{
    const response=await fetch('/system/reconnect/'+encodeURIComponent(actionId)+'/'+nonce,{{
      method:'GET',
      cache:'no-store',
      credentials:'same-origin',
      redirect:'error',
      signal:controller.signal,
      headers:{{'Accept':'application/json','Cache-Control':'no-cache','Pragma':'no-cache'}}
    }});
    if(response.ok){{
      const state=await response.json();
      if(state.ready){{
        done=true;
        window.clearTimeout(timer);
        window.location.assign(successUrl);
        return;
      }}
      if(state.failed){{
        done=true;
        window.location.assign('/settings?update_message='+encodeURIComponent(state.message||'The operation failed.')+'&update_ok=0&update_open=1');
        return;
      }}
    }}
  }}catch(error){{
    // Expected while the service is stopping or booting.
  }}finally{{
    window.clearTimeout(timeout);
  }}
  schedule();
}}
window.addEventListener('pageshow',()=>schedule(350),{{once:true}});
window.addEventListener('online',()=>schedule(100));
document.addEventListener('visibilitychange',()=>{{if(!document.hidden) schedule(100);}});
schedule(500);
</script></body></html>""", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.get("/system/reconnect/{action_id}")
@app.get("/system/reconnect/{action_id}/{nonce}")
def reconnect_status(action_id: str, nonce: str = ""):
    if not re.fullmatch(r"[a-f0-9]{32}", action_id):
        return JSONResponse({"ready": False, "failed": True, "message": "Invalid reconnect action."}, status_code=400)
    action_file = RECONNECT_DIR / f"{action_id}.json"
    if not action_file.exists():
        return JSONResponse({"ready": False, "failed": True, "message": "Reconnect action was not found."}, status_code=404)
    try:
        action = json.loads(action_file.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse({"ready": False, "failed": True, "message": "Reconnect action is unreadable."}, status_code=500)

    previous_startup_id = str(action.get("previous_startup_id") or "")
    expected_version = normalize_release_version(str(action.get("expected_version") or ""))
    new_process = bool(previous_startup_id and PROCESS_START_ID != previous_startup_id)
    version_ok = not expected_version or version_tuple(APP_VERSION) == version_tuple(expected_version)

    if action.get("kind") == "update":
        result_file = UPDATE_STAGING_DIR / "result.json"
        if result_file.exists():
            try:
                result = json.loads(result_file.read_text(encoding="utf-8"))
                if result.get("state") == "failed":
                    return JSONResponse({"ready": False, "failed": True, "message": result.get("message") or "Update failed."})
            except Exception:
                pass

    ready = version_ok and (new_process or (expected_version and version_tuple(APP_VERSION) == version_tuple(expected_version)))
    return JSONResponse(
        {"ready": ready, "failed": False, "app_version": APP_VERSION, "startup_id": PROCESS_START_ID},
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        },
    )


@app.get("/system/ready")
def system_ready():
    return JSONResponse(
        {"ready": True, "app_version": APP_VERSION, "startup_id": PROCESS_START_ID},
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/settings/system/restart-app", include_in_schema=False)
@app.get("/settings/system/reboot", include_in_schema=False)
@app.get("/settings/system/shutdown", include_in_schema=False)
def settings_system_action_refresh():
    return RedirectResponse("/settings?system_actions_open=1#system-actions", status_code=303)

@app.post("/settings/system/restart-app")
def restart_application():
    action_id = _create_reconnect_action("restart")
    _run_delayed(["sudo", "-n", "/usr/bin/systemctl", "restart", "outlaws-inventory.service"], delay=1.5)
    return _reconnect_wait_page(
        "Restarting Outlaw's Inventory",
        ["Waiting for the application to return."],
        "/settings?system_action_message=Outlaw%27s+Inventory+restarted+successfully.&system_action_ok=1&system_actions_open=1#system-actions",
        action_id,
    )


@app.post("/settings/system/reboot")
def reboot_system():
    action_id = _create_reconnect_action("reboot")
    _run_delayed(["sudo", "-n", "/usr/bin/systemctl", "reboot"], delay=1.5)
    return _reconnect_wait_page(
        "Rebooting system",
        ["Waiting for the system and application to return."],
        "/settings?system_action_message=System+reboot+completed.&system_action_ok=1&system_actions_open=1#system-actions",
        action_id,
    )


@app.post("/settings/system/shutdown")
def shutdown_system():
    _run_delayed(["sudo", "-n", "/usr/bin/systemctl", "poweroff"])
    return HTMLResponse("<html><body style='background:#0b1020;color:#fff;font-family:sans-serif;padding:3rem'><h2>Shutting down system…</h2><p>The system will remain unavailable until it is powered on again.</p></body></html>")


def normalize_release_version(value: str | None) -> str:
    value = (value or "").strip()
    return value[1:] if value.lower().startswith("v") else value


def version_tuple(value: str | None) -> tuple[int, int, int]:
    # Supported releases use a strict major.minor.patch version. Historical
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", normalize_release_version(value))
    if not match:
        return (0, 0, 0)
    return tuple(int(part) for part in match.groups())


def github_update_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"OutlawsInventory/{APP_VERSION}",
    }
    if GITHUB_TOKEN_FILE.exists():
        token = GITHUB_TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def application_update_info() -> dict[str, object]:
    settings = get_settings()
    latest = settings.get("application_update_latest_version", "")
    pending_file = UPDATE_STAGING_DIR / "pending.json"
    result_file = UPDATE_STAGING_DIR / "result.json"
    result: dict[str, object] = {}
    if result_file.exists():
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
        except Exception:
            result = {"state": "unknown", "message": "The last update result could not be read."}
    # A manual installation or a completed restart can leave the old helper's
    # transient 'installing' state behind. Do not show it once no pending
    # package exists or the referenced version is already installed.
    result_version = normalize_release_version(str(result.get("version") or ""))
    if result.get("state") == "installing" and (
        not pending_file.exists() or (result_version and version_tuple(result_version) <= version_tuple(APP_VERSION))
    ):
        result = {}
        result_file.unlink(missing_ok=True)
    # Privileged helpers publish a small, app-owned state file. The web app
    # never probes or reads the root-only backup directory directly.
    rollback_state = UPDATE_STAGING_DIR / "rollback.json"
    rollback_version = ""
    try:
        if rollback_state.is_file():
            rollback_version = normalize_release_version(
                str(json.loads(rollback_state.read_text(encoding="utf-8")).get("version") or "")
            )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        rollback_version = ""
    pending_version = ""
    if pending_file.exists():
        try:
            pending_version = normalize_release_version(str(json.loads(pending_file.read_text(encoding="utf-8")).get("version") or ""))
        except Exception:
            pending_version = ""
    return {
        "repository": APPLICATION_UPDATE_REPOSITORY,
        "token_configured": GITHUB_TOKEN_FILE.exists() and bool(GITHUB_TOKEN_FILE.read_text(encoding="utf-8").strip()),
        "channel": "acceptance" if settings.get("application_update_channel", "production") == "acceptance" else "production",
        "last_checked": settings.get("application_update_last_checked", ""),
        "latest_version": latest,
        "latest_tag": settings.get("application_update_latest_tag", ""),
        "release_name": settings.get("application_update_release_name", ""),
        "release_notes": settings.get("application_update_release_notes", ""),
        "release_prerelease": settings.get("application_update_release_prerelease", "0") == "1",
        "update_available": bool(latest and version_tuple(latest) > version_tuple(APP_VERSION)),
        "newer_than_release": bool(latest and version_tuple(APP_VERSION) > version_tuple(latest)),
        "version_relation": (
            "update_available" if latest and version_tuple(latest) > version_tuple(APP_VERSION)
            else "newer_installed" if latest and version_tuple(APP_VERSION) > version_tuple(latest)
            else "up_to_date" if latest
            else "not_checked"
        ),
        "pending_version": pending_version,
        "rollback_version": rollback_version,
        "result": result,
    }


def check_application_release() -> tuple[bool, str]:
    settings = get_settings()
    repository = APPLICATION_UPDATE_REPOSITORY
    channel = "acceptance" if settings.get("application_update_channel", "production") == "acceptance" else "production"
    if channel == "acceptance":
        # Acceptance sees both normal releases and pre-releases. Drafts are
        # never installable. Select by semantic version rather than relying on
        # GitHub's publication order so the effective latest version is clear.
        url = f"https://api.github.com/repos/{repository}/releases?per_page=100"
        response = requests.get(url, headers=github_update_headers(), timeout=20)
        if response.status_code == 404:
            return False, "Repository or releases not found. For a private repository, check the token permissions."
        response.raise_for_status()
        releases = [item for item in (response.json() or []) if not item.get("draft")]
        releases = [item for item in releases if normalize_release_version(str(item.get("tag_name") or ""))]
        if not releases:
            return False, "No published Production or Acceptance release was found."
        release = max(releases, key=lambda item: version_tuple(normalize_release_version(str(item.get("tag_name") or ""))))
    else:
        # Production intentionally uses GitHub's latest stable release endpoint;
        # GitHub excludes drafts and pre-releases from this endpoint.
        url = f"https://api.github.com/repos/{repository}/releases/latest"
        response = requests.get(url, headers=github_update_headers(), timeout=20)
        if response.status_code == 404:
            return False, "Repository or latest Production release not found. For a private repository, check the token permissions."
        response.raise_for_status()
        release = response.json()
    assets = release.get("assets") or []
    zip_asset = None
    checksum_asset = None
    for asset in assets:
        name = str(asset.get("name") or "")
        if re.fullmatch(r"outlaws-inventory-v\d+(?:\.\d+){2,3}\.zip", name):
            zip_asset = asset
        elif name == "SHA256SUMS":
            checksum_asset = asset
    tag = str(release.get("tag_name") or "")
    version = normalize_release_version(tag)
    if not version or not zip_asset or not checksum_asset:
        return False, "The latest release must contain the versioned ZIP and SHA256SUMS assets."
    values = {
        "application_update_last_checked": now(),
        "application_update_latest_version": version,
        "application_update_latest_tag": tag,
        "application_update_release_name": str(release.get("name") or tag),
        "application_update_release_notes": str(release.get("body") or "")[:12000],
        "application_update_release_prerelease": "1" if release.get("prerelease") else "0",
        "application_update_zip_asset_id": str(zip_asset.get("id") or ""),
        "application_update_checksum_asset_id": str(checksum_asset.get("id") or ""),
    }
    with db() as con:
        for key, value in values.items():
            con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    if version_tuple(version) > version_tuple(APP_VERSION):
        return True, f"New version available: v{version}"
    if version_tuple(APP_VERSION) > version_tuple(version):
        return True, f"Installed version v{APP_VERSION} is newer than the latest published release v{version}."
    return True, f"Already on latest version: v{version}"


def download_release_asset(repository: str, asset_id: str, destination: Path) -> None:
    response = requests.get(
        f"https://api.github.com/repos/{repository}/releases/assets/{asset_id}",
        headers={**github_update_headers(), "Accept": "application/octet-stream"},
        timeout=90,
        allow_redirects=True,
    )
    response.raise_for_status()
    destination.write_bytes(response.content)


def prepare_application_update() -> tuple[bool, str]:
    settings = get_settings()
    repository = APPLICATION_UPDATE_REPOSITORY
    version = settings.get("application_update_latest_version", "").strip()
    zip_asset_id = settings.get("application_update_zip_asset_id", "").strip()
    checksum_asset_id = settings.get("application_update_checksum_asset_id", "").strip()
    if not repository or not version or not zip_asset_id or not checksum_asset_id:
        return False, "Run Check for updates first."
    if version_tuple(version) <= version_tuple(APP_VERSION):
        return False, "No newer release is available."
    UPDATE_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    # Every installation attempt starts from a clean preparation state.
    # Historical release ZIPs are retained until the update succeeds, so the
    # current and previous package can still be kept for rollback/history.
    for stale_name in ("pending.json", "result.json", "SHA256SUMS"):
        (UPDATE_STAGING_DIR / stale_name).unlink(missing_ok=True)
    for stale in UPDATE_STAGING_DIR.glob("*.tmp*"):
        if stale.is_file():
            stale.unlink(missing_ok=True)
    zip_name = f"outlaws-inventory-v{version}.zip"
    zip_path = UPDATE_STAGING_DIR / zip_name
    sums_path = UPDATE_STAGING_DIR / "SHA256SUMS"
    zip_path.unlink(missing_ok=True)
    download_release_asset(repository, zip_asset_id, zip_path)
    download_release_asset(repository, checksum_asset_id, sums_path)
    expected = ""
    for line in sums_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == zip_name:
            expected = parts[0].lower()
            break
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if not expected or expected != actual:
        zip_path.unlink(missing_ok=True)
        return False, "Checksum verification failed. The update was not installed."
    pending = {
        "version": version,
        "zip": str(zip_path),
        "sha256": actual,
        "prepared_at": now(),
    }
    (UPDATE_STAGING_DIR / "pending.json").write_text(json.dumps(pending, indent=2), encoding="utf-8")
    (UPDATE_STAGING_DIR / "result.json").write_text(json.dumps({"state": "prepared", "message": f"v{version} is ready to install."}), encoding="utf-8")
    return True, f"v{version} downloaded and verified."


@app.get("/settings/application-update/test", include_in_schema=False)
@app.get("/settings/application-update/check", include_in_schema=False)
@app.get("/settings/application-update/prepare", include_in_schema=False)
@app.get("/settings/application-update/install", include_in_schema=False)
@app.get("/settings/application-update/rollback", include_in_schema=False)
def application_update_action_refresh():
    return RedirectResponse("/settings?update_open=1#application-version", status_code=303)

@app.post("/settings/application-update/channel")
def set_application_update_channel(channel: str = Form("production")):
    channel = "acceptance" if channel == "acceptance" else "production"
    with db() as con:
        con.execute(
            "INSERT INTO settings(key,value) VALUES('application_update_channel',?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (channel,),
        )
    label = "Acceptance" if channel == "acceptance" else "Production"
    try:
        ok, message = check_application_release()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        ok, message = False, f"GitHub update check failed after switching to {label} (HTTP {status or 'error'})."
    except requests.RequestException:
        ok, message = False, f"GitHub could not be reached after switching to {label}. The release channel was saved."
    if ok:
        message = f"Release channel changed to {label}. {message}"
    return RedirectResponse(
        f"/settings?update_message={quote(message)}&update_ok={1 if ok else 0}&update_open=1#application-version",
        status_code=303,
    )


@app.post("/settings/application-update/test")
def test_application_update_connection_route():
    try:
        ok, message = check_application_release()
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status == 401:
            ok, message = False, "GitHub authentication failed. Replace the token and try again."
        elif status == 403:
            ok, message = False, "GitHub denied access. Check that the token has read-only Contents access to this repository."
        else:
            ok, message = False, f"GitHub connection failed (HTTP {status or 'error'})."
    except requests.RequestException:
        ok, message = False, "GitHub could not be reached. Check the internet connection and try again."
    if ok:
        info = application_update_info()
        latest = str(info.get("latest_version") or "")
        if latest and version_tuple(latest) <= version_tuple(APP_VERSION):
            message = f"Connected to GitHub. v{APP_VERSION} is up to date."
        else:
            message = f"Connected to GitHub. {message}"
    return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok={1 if ok else 0}&update_open=1", status_code=303)


@app.post("/settings/application-update/token")
def save_application_update_token(token: str = Form("")):
    with _database_gate.access():
        token = token.strip()
        if not token:
            return RedirectResponse("/settings?update_message=Enter+a+GitHub+token+first.&update_ok=0&update_open=1", status_code=303)
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        GITHUB_TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
        GITHUB_TOKEN_FILE.chmod(0o600)
        return RedirectResponse("/settings?update_message=GitHub+token+saved.&update_ok=1&update_open=1", status_code=303)


@app.post("/settings/application-update/token/remove")
def remove_application_update_token():
    with _database_gate.access():
        GITHUB_TOKEN_FILE.unlink(missing_ok=True)
        return RedirectResponse("/settings?update_message=GitHub+token+removed.&update_ok=1&update_open=1", status_code=303)


@app.post("/settings/application-update/check")
def check_application_update_route():
    ok, message = check_application_release()
    return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok={1 if ok else 0}&update_open=1", status_code=303)


@app.post("/settings/application-update/prepare")
def prepare_application_update_route():
    ok, message = prepare_application_update()
    return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok={1 if ok else 0}&update_open=1", status_code=303)


def _start_application_update() -> HTMLResponse | RedirectResponse:
    info = application_update_info()
    latest = str(info.get("latest_version") or "")
    if not latest or version_tuple(latest) <= version_tuple(APP_VERSION):
        return RedirectResponse("/settings?update_message=No+newer+release+is+available.&update_ok=0&update_open=1", status_code=303)
    # Install always downloads and validates a fresh package. Check for updates
    # only checks GitHub and never prepares staging content.
    ok, message = prepare_application_update()
    if not ok:
        return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok=0", status_code=303)
    queued_at = int(time.time())
    (UPDATE_STAGING_DIR / "result.json").write_text(
        json.dumps({
            "state": "queued", "stage": "Starting update", "progress": 0,
            "version": latest, "message": f"Update to v{latest} is queued.",
            "started_at_epoch": queued_at, "updated_at_epoch": queued_at,
            "heartbeat_at_epoch": queued_at,
        }, indent=2),
        encoding="utf-8",
    )
    try:
        launch = subprocess.run(
            ["sudo", "-n", "/usr/local/sbin/outlaws-inventory-self-update-launcher"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except Exception as exc:
        message = f"Could not start the independent update job: {exc}"
        (UPDATE_STAGING_DIR / "result.json").write_text(json.dumps({"state": "failed", "version": latest, "message": message}), encoding="utf-8")
        return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok=0", status_code=303)
    if launch.returncode != 0:
        detail = (launch.stderr or launch.stdout or "The update launcher failed.").strip()
        message = f"Could not start the independent update job: {detail}"
        (UPDATE_STAGING_DIR / "result.json").write_text(json.dumps({"state": "failed", "version": latest, "message": message}), encoding="utf-8")
        return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok=0", status_code=303)
    success_url = (
        "/settings?update_message="
        + quote(f"Outlaw's Inventory was successfully updated to v{latest}.")
        + "&update_ok=1&update_open=1&release_notes_open=1"
    )
    return RedirectResponse(f"/settings/application-update/progress?version={quote(latest)}", status_code=303)


@app.post("/settings/application-update/install")
def install_application_update_route():
    return _start_application_update()


def _application_update_progress_page(version: str, success_url: str) -> HTMLResponse:
    safe_version = re.sub(r"[^0-9A-Za-z._-]", "", version)
    safe_success = json.dumps(success_url)
    return HTMLResponse(f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Updating Outlaw's Inventory</title>
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#0b1020;color:#eef2ff;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;min-height:100vh;display:grid;place-items:center;padding:24px}}
main{{width:min(620px,100%);background:#11182a;border:1px solid #26314b;border-radius:18px;padding:34px;text-align:center;box-shadow:0 18px 60px rgba(0,0,0,.28)}}
.spinner{{width:54px;height:54px;margin:0 auto 24px;border:7px solid #263653;border-top-color:#79b8ff;border-radius:50%;animation:spin .85s linear infinite}}@keyframes spin{{to{{transform:rotate(360deg)}}}}
h1{{font-size:1.65rem;margin:0 0 12px}}p{{color:#aeb8cf;margin:0;line-height:1.65}}#error{{display:none;margin-top:20px;padding:13px 15px;border:1px solid #8a3038;background:#2b1217;color:#ffb8bf;border-radius:12px;text-align:left}}#error-message{{white-space:pre-wrap}}#update-log{{display:none;margin-top:14px}}#update-log summary{{cursor:pointer;color:#dbe4ff;font-weight:650}}#update-log pre{{margin:10px 0 0;max-height:320px;overflow:auto;white-space:pre-wrap;word-break:break-word;background:#0b1020;border:1px solid #3a2630;border-radius:9px;padding:12px;color:#e8c7ca;font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}}a{{color:#9fb3ff}}
@media(max-width:560px){{main{{padding:26px}}}}
</style></head><body><main>
<div class='spinner' id='spinner' aria-hidden='true'></div>
<h1>Updating Outlaw's Inventory</h1>
<p>Installing version v{safe_version}.</p>
<p>This will take about a minute...</p>
<div id='error'><div id='error-message'></div><details id='update-log'><summary>Show update log</summary><pre id='update-log-text'></pre></details><div style='margin-top:12px'><a href='/settings?update_open=1'>Return to Settings</a></div></div>
<script>
const successUrl={safe_success};
const targetVersion={json.dumps(safe_version)};
const pollIntervalMs=2000;
const timeoutMs=300000;
const started=Date.now();
let finished=false;
let consecutiveErrors=0;
function complete(message){{
  if(finished)return;finished=true;
  window.setTimeout(()=>window.location.replace(successUrl),650);
}}
function fail(message,updateLog){{
  if(finished)return;finished=true;
  document.getElementById('spinner').style.display='none';
  const e=document.getElementById('error');e.style.display='block';
  document.getElementById('error-message').textContent=message||'Update verification failed.';
  const log=String(updateLog||'').trim();
  if(log){{
    document.getElementById('update-log-text').textContent=log;
    document.getElementById('update-log').style.display='block';
  }}
}}
async function fetchStatus(){{
  const controller=new AbortController();
  const timer=window.setTimeout(()=>controller.abort(),5000);
  try{{
    const url='/settings/application-update/status?expected='+encodeURIComponent(targetVersion)+'&_='+Date.now();
    const response=await fetch(url,{{cache:'no-store',signal:controller.signal,headers:{{'Accept':'application/json'}}}});
    if(!response.ok)throw new Error('HTTP '+response.status);
    return await response.json();
  }}finally{{window.clearTimeout(timer)}}
}}
async function poll(){{
  if(finished)return;
  try{{
    const status=await fetchStatus();
    consecutiveErrors=0;
    if(status.state==='completed' && status.runtime_verified===true && String(status.app_version||'')===targetVersion){{
      complete(status.message||"Outlaw's Inventory has been updated successfully.");return;
    }}
    if(status.state==='failed'){{fail(status.message||'Update failed.',status.update_log||'');return;}}
  }}catch(_error){{
    consecutiveErrors+=1;
  }}
  if(Date.now()-started>=timeoutMs){{
    fail('The application did not confirm a successful update within 5 minutes. Open Settings in a new tab to inspect the installed version.');return;
  }}
  window.setTimeout(poll,pollIntervalMs);
}}
window.setTimeout(poll,500);
</script></main></body></html>""")


@app.get("/settings/application-update/progress", response_class=HTMLResponse, include_in_schema=False)
def application_update_progress_route(version: str = ""):
    target = normalize_release_version(version)
    if not target:
        return RedirectResponse("/settings?update_open=1#application-version", status_code=303)
    success_url = (
        "/settings?update_message="
        + quote(f"Outlaw's Inventory is now running v{target}.")
        + "&update_ok=1&update_open=1&release_notes_open=1"
    )
    return _application_update_progress_page(target, success_url)


@app.post("/settings/application-update/rollback")
def rollback_application_update_route():
    info = application_update_info()
    rollback_version = str(info.get("rollback_version") or "")
    if not rollback_version:
        return RedirectResponse("/settings?update_message=No+previous+version+is+available.&update_ok=0&update_open=1", status_code=303)
    (UPDATE_STAGING_DIR / "result.json").write_text(
        json.dumps({"state": "queued", "version": rollback_version, "message": f"Rollback to v{rollback_version} is queued."}),
        encoding="utf-8",
    )
    try:
        launch = subprocess.run(
            ["sudo", "-n", "/usr/local/sbin/outlaws-inventory-self-rollback-launcher"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except Exception as exc:
        message = f"Could not start the independent rollback job: {exc}"
        (UPDATE_STAGING_DIR / "result.json").write_text(json.dumps({"state": "failed", "version": rollback_version, "message": message}), encoding="utf-8")
        return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok=0", status_code=303)
    if launch.returncode != 0:
        detail = (launch.stderr or launch.stdout or "The rollback launcher failed.").strip()
        message = f"Could not start the independent rollback job: {detail}"
        (UPDATE_STAGING_DIR / "result.json").write_text(json.dumps({"state": "failed", "version": rollback_version, "message": message}), encoding="utf-8")
        return RedirectResponse(f"/settings?update_message={quote(message)}&update_ok=0", status_code=303)
    return RedirectResponse(f"/settings/application-update/progress?version={quote(rollback_version)}", status_code=303)


def _tail_application_update_log(max_lines: int = 100) -> str:
    log_file = UPDATE_STAGING_DIR / "update.log"
    try:
        if not log_file.is_file():
            return ""
        # The updater log is local application data. Read only the fixed log path
        # and expose at most the last 100 lines on an explicitly failed update.
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max(1, min(int(max_lines), 100)):])
    except Exception:
        return ""


@app.get("/settings/application-update/status")
def application_update_status_route(expected: str = ""):
    expected_version = normalize_release_version(expected)
    result_file = UPDATE_STAGING_DIR / "result.json"
    result: dict[str, object] = {}
    if result_file.exists():
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
        except Exception:
            result = {"state": "unknown", "message": "Update status is unreadable."}

    result_state = str(result.get("state") or "idle")
    result_version = normalize_release_version(str(result.get("version") or ""))
    target_version = expected_version or result_version

    database_ready = False
    try:
        with db() as con:
            con.execute("SELECT 1").fetchone()
        database_ready = True
    except Exception:
        database_ready = False

    version_matches = bool(target_version and version_tuple(target_version) == version_tuple(APP_VERSION))
    helper_succeeded = result_state == "success" and (not result_version or version_tuple(result_version) == version_tuple(APP_VERSION))
    runtime_verified = bool(version_matches and database_ready and helper_succeeded)

    if runtime_verified:
        return JSONResponse({
            "state": "completed",
            "stage": "Update verified",
            "progress": 100,
            "version": target_version,
            "app_version": APP_VERSION,
            "runtime_verified": True,
            "database_ready": True,
            "startup_id": PROCESS_START_ID,
            "message": f"Outlaw's Inventory was successfully updated to v{APP_VERSION}.",
            "heartbeat_age_seconds": 0,
            "stalled": False,
            "started_at_epoch": result.get("started_at_epoch", 0),
        }, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

    if result_state == "failed":
        result["app_version"] = APP_VERSION
        result["runtime_verified"] = False
        result["database_ready"] = database_ready
        update_log = _tail_application_update_log(100)
        if update_log:
            result["update_log"] = update_log
        return JSONResponse(result, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})

    heartbeat = float(result.get("heartbeat_at_epoch") or result.get("updated_at_epoch") or 0)
    age = max(0, int(time.time() - heartbeat)) if heartbeat else None
    result["state"] = result_state
    result["heartbeat_age_seconds"] = age
    result["stalled"] = bool(result_state in {"queued", "installing", "restarting", "validating"} and age is not None and age > 45)
    result["progress"] = max(0, min(100, int(result.get("progress") or 0)))
    result["app_version"] = APP_VERSION
    result["runtime_verified"] = False
    result["database_ready"] = database_ready
    result["expected_version"] = target_version
    return JSONResponse(result, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})



BACKUP_FORMAT = "outlaws-inventory-backup"
BACKUP_SCHEMA = 1
BACKUP_MAX_BYTES = 1024 * 1024 * 1024
BACKUP_MAX_UNCOMPRESSED = 2 * 1024 * 1024 * 1024
BACKUP_COMPONENTS = (("uploads", UPLOAD_DIR), ("keys", KEY_DIR), ("secrets", SECRETS_DIR), ("avatars", AVATAR_DIR))


def _backup_filename(kind: str = "manual") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"outlaws-inventory-{kind}-backup-v{APP_VERSION}-{stamp}.oi-backup"


def _backup_safe_member(name: str) -> bool:
    path = Path(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_full_backup(kind: str = "manual") -> Path:
    if not _backup_lock.acquire(blocking=False):
        raise RuntimeError("Another backup or restore operation is already running.")
    exclusive = False
    try:
        _database_gate.acquire_exclusive()
        exclusive = True
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        destination = BACKUP_DIR / _backup_filename(kind)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        files: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="outlaws-backup-") as temp_name:
            snapshot = Path(temp_name) / "database.sqlite3"
            with db() as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            candidates: list[tuple[str, Path]] = [("database.sqlite3", snapshot)]
            for prefix, directory in BACKUP_COMPONENTS:
                if directory.exists():
                    copied = Path(temp_name) / prefix
                    shutil.copytree(directory, copied)
                    for file_path in sorted(copied.rglob("*")):
                        if file_path.is_file():
                            candidates.append((f"{prefix}/{file_path.relative_to(copied).as_posix()}", file_path))
            for archive_name, file_path in candidates:
                files.append({"path": archive_name, "size": file_path.stat().st_size, "sha256": _sha256_file(file_path)})
            manifest = {
                "format": BACKUP_FORMAT, "schema_version": BACKUP_SCHEMA,
                "application_version": APP_VERSION, "created_at": now(), "kind": kind,
                "includes_secrets": True, "files": files,
            }
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
                for archive_name, file_path in candidates:
                    archive.write(file_path, archive_name)
        temporary.replace(destination)
        destination.chmod(0o600)
        return destination
    finally:
        if exclusive:
            _database_gate.release_exclusive()
        _backup_lock.release()


def _backup_cache_signature(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns), "ctime_ns": int(stat.st_ctime_ns)}


def _load_backup_inspection_cache() -> dict[str, dict[str, object]]:
    try:
        raw = json.loads(BACKUP_INSPECTION_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and int(raw.get("schema", 0)) == 1 and isinstance(raw.get("entries"), dict):
            return {str(k): v for k, v in raw["entries"].items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def _save_backup_inspection_cache(entries: dict[str, dict[str, object]]) -> None:
    try:
        payload = {"schema": 1, "entries": entries}
        temporary = BACKUP_INSPECTION_CACHE_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(BACKUP_INSPECTION_CACHE_FILE)
        BACKUP_INSPECTION_CACHE_FILE.chmod(0o600)
    except OSError:
        pass


def _inspect_full_backup_integrity(path: Path) -> dict[str, object]:
    """Perform the expensive archive/checksum validation independent of restore policy."""
    result: dict[str, object] = {
        "valid": False,
        "reason": "Backup could not be validated.",
        "manifest": {},
    }
    try:
        if not path.is_file() or path.stat().st_size > BACKUP_MAX_BYTES:
            raise ValueError("Backup file is missing or exceeds the 1 GB safety limit.")
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > 10000 or sum(info.file_size for info in infos) > BACKUP_MAX_UNCOMPRESSED:
                raise ValueError("Backup archive exceeds safety limits.")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or any(not _backup_safe_member(name) for name in names):
                raise ValueError("Backup contains unsafe or duplicate archive paths.")
            if "manifest.json" not in names or "database.sqlite3" not in names:
                raise ValueError("Backup manifest or database is missing.")
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("format") != BACKUP_FORMAT or int(manifest.get("schema_version", 0)) != BACKUP_SCHEMA:
                raise ValueError("Unsupported backup format or schema version.")
            entries = manifest.get("files")
            if not isinstance(entries, list):
                raise ValueError("Backup manifest is invalid.")
            expected = {str(item.get("path")): item for item in entries if isinstance(item, dict)}
            if len(expected) != len(entries) or "manifest.json" in expected:
                raise ValueError("Backup manifest contains invalid or duplicate entries.")
            archive_files = {info.filename for info in infos if not info.is_dir()}
            if archive_files != set(expected) | {"manifest.json"}:
                raise ValueError("Backup contains files not covered by its manifest.")
            if "database.sqlite3" not in expected:
                raise ValueError("Database checksum entry is missing.")
            for name, item in expected.items():
                if name not in names or not _backup_safe_member(name):
                    raise ValueError(f"Backup component is missing: {name}")
                data = archive.read(name)
                if len(data) != int(item.get("size", -1)) or hashlib.sha256(data).hexdigest() != str(item.get("sha256", "")):
                    raise ValueError(f"Checksum validation failed: {name}")
        return {"valid": True, "reason": "Backup integrity verified.", "manifest": manifest}
    except Exception as exc:
        result["reason"] = str(exc) or "Backup could not be validated."
        return result


def _cached_backup_integrity(path: Path) -> dict[str, object]:
    """Cache expensive checksum validation until the physical backup file changes."""
    if not path.is_file():
        return {"valid": False, "reason": "Backup file is missing.", "manifest": {}}
    signature = _backup_cache_signature(path)
    with _backup_inspection_cache_lock:
        cache = _load_backup_inspection_cache()
        entry = cache.get(path.name)
        if (
            isinstance(entry, dict)
            and entry.get("size") == signature["size"]
            and entry.get("mtime_ns") == signature["mtime_ns"]
            and entry.get("ctime_ns") == signature["ctime_ns"]
            and isinstance(entry.get("inspection"), dict)
        ):
            return dict(entry["inspection"])

        inspection = _inspect_full_backup_integrity(path)
        cache[path.name] = {**signature, "inspection": inspection}
        existing_names = {candidate.name for candidate in BACKUP_DIR.glob("*.oi-backup")}
        cache = {name: value for name, value in cache.items() if name in existing_names}
        _save_backup_inspection_cache(cache)
        return inspection


def inspect_full_backup(path: Path, *, use_cache: bool = True) -> dict[str, object]:
    """Inspect integrity separately from restore support; restore can force a fresh validation."""
    integrity = _cached_backup_integrity(path) if use_cache else _inspect_full_backup_integrity(path)
    result: dict[str, object] = {
        "valid": bool(integrity.get("valid")),
        "restorable": False,
        "status": "Invalid",
        "reason": str(integrity.get("reason") or "Backup could not be validated."),
        "manifest": integrity.get("manifest") if isinstance(integrity.get("manifest"), dict) else {},
    }
    if not result["valid"]:
        return result

    manifest = result["manifest"]
    backup_version = str(manifest.get("application_version") or "").strip().lstrip("v")
    if not backup_version:
        result.update(status="Unsupported", reason="Backup application version is missing.")
    elif version_tuple(backup_version) < version_tuple("0.15.0"):
        result.update(status="Unsupported", reason="Backup predates the supported v0.15.0 baseline.")
    elif version_tuple(backup_version) > version_tuple(APP_VERSION):
        result.update(status="Unsupported", reason=f"Backup was created by newer version v{backup_version}.")
    else:
        result.update(restorable=True, status="Restorable", reason="Backup is valid and supported by this version.")
    return result


def validate_full_backup(path: Path) -> dict[str, object]:
    inspection = inspect_full_backup(path, use_cache=False)
    if not inspection["valid"]:
        raise ValueError(str(inspection["reason"]))
    if not inspection["restorable"]:
        manifest = inspection.get("manifest") or {}
        backup_version = str(manifest.get("application_version") or "").strip().lstrip("v")
        if backup_version and version_tuple(backup_version) < version_tuple("0.15.0"):
            raise ValueError("This backup predates the supported v0.15.0 backup baseline. Create a new backup from v0.15.0 or newer.")
        if backup_version and version_tuple(backup_version) > version_tuple(APP_VERSION):
            raise ValueError(f"This backup was created by newer Outlaw's Inventory v{backup_version}. Update this installation before restoring it.")
        raise ValueError(str(inspection["reason"]))
    return dict(inspection["manifest"])


def list_backups() -> list[dict[str, object]]:
    result = []
    for path in sorted(BACKUP_DIR.glob("*.oi-backup"), key=lambda p: p.stat().st_mtime, reverse=True):
        inspection = inspect_full_backup(path)
        manifest = inspection.get("manifest") if inspection.get("valid") else {}
        manifest = manifest if isinstance(manifest, dict) else {}
        result.append({
            "name": path.name,
            "size": path.stat().st_size,
            "size_label": f"{path.stat().st_size / 1024 / 1024:.1f} MB",
            "created_at": manifest.get("created_at", ""),
            "version": manifest.get("application_version", ""),
            "kind": manifest.get("kind", ""),
            "valid": bool(inspection["valid"]),
            "restorable": bool(inspection["restorable"]),
            "status": str(inspection["status"]),
            "reason": str(inspection["reason"]),
        })
    return result

def _warm_backup_inspection_cache() -> None:
    """Populate missing backup inspection entries away from the Settings request path."""
    try:
        list_backups()
    except Exception:
        # Cache warming is an optimization only; Settings/restore remain authoritative.
        pass


def _copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir() if source.exists() else []:
        target = destination / child.name
        if child.is_dir(): shutil.copytree(child, target)
        else: shutil.copy2(child, target)


def restore_full_backup(path: Path) -> None:
    validate_full_backup(path)
    if not _backup_lock.acquire(blocking=False):
        raise RuntimeError("Another backup or restore operation is already running.")
    rollback_root = None
    extract_root = None
    live_changed = False
    keep_recovery = False
    exclusive = False
    try:
        _database_gate.acquire_exclusive()
        exclusive = True
        rollback_root = Path(tempfile.mkdtemp(prefix="outlaws-restore-rollback-"))
        extract_root = Path(tempfile.mkdtemp(prefix="outlaws-restore-extract-"))
        current_db = rollback_root / "database.sqlite3"
        with db() as source, closing(sqlite3.connect(current_db)) as target:
            source.backup(target)
        for prefix, directory in BACKUP_COMPONENTS:
            if directory.exists():
                shutil.copytree(directory, rollback_root / prefix)
        with zipfile.ZipFile(path, "r") as archive:
            archive.extractall(extract_root)
        candidate_db = extract_root / "database.sqlite3"
        candidate = sqlite3.connect(candidate_db)
        try:
            integrity = candidate.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"Database integrity check failed: {integrity}")
            live = db()
            try:
                live_changed = True
                candidate.backup(live)
                live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                live.close()
        finally:
            candidate.close()
        # SQLite owns WAL/SHM lifecycle; never unlink them under other readers.
        for prefix, directory in BACKUP_COMPONENTS:
            shutil.rmtree(directory, ignore_errors=False) if directory.exists() else None
            directory.mkdir(parents=True, exist_ok=True)
            _copy_tree_contents(extract_root / prefix, directory)
        init_db()
        normalize_runtime_data_permissions()
    except BaseException as failure:
        if live_changed:
            try:
                rollback_source = sqlite3.connect(rollback_root / "database.sqlite3")
                rollback_live = db()
                try:
                    rollback_source.backup(rollback_live)
                    rollback_live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    rollback_live.close(); rollback_source.close()
                for prefix, directory in BACKUP_COMPONENTS:
                    if directory.exists():
                        shutil.rmtree(directory)
                    directory.mkdir(parents=True, exist_ok=True)
                    _copy_tree_contents(rollback_root / prefix, directory)
                normalize_runtime_data_permissions()
            except BaseException as recovery_error:
                keep_recovery = True
                raise RuntimeError(f"Restore failed and automatic recovery could not finish. Recovery files retained at {rollback_root}: {recovery_error}") from failure
        raise
    finally:
        if rollback_root and not keep_recovery:
            shutil.rmtree(rollback_root, ignore_errors=True)
        if extract_root:
            shutil.rmtree(extract_root, ignore_errors=True)
        if exclusive:
            _database_gate.release_exclusive()
        _backup_lock.release()


def prune_backups(retention: int) -> None:
    automatic: list[Path] = []
    for path in BACKUP_DIR.glob("*.oi-backup"):
        inspection = inspect_full_backup(path)
        manifest = inspection.get("manifest") if inspection.get("valid") else {}
        if isinstance(manifest, dict) and manifest.get("kind") == "automatic":
            automatic.append(path)
    automatic.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for path in automatic[max(1, retention):]:
        path.unlink(missing_ok=True)


def _validated_clock_time(value: str | None, default: str = "02:00") -> str:
    raw = (value or default).strip()
    try:
        hour, minute = [int(part) for part in raw.split(":", 1)]
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    except (TypeError, ValueError):
        pass
    return default


def backup_settings() -> dict[str, object]:
    settings = get_settings()
    schedule = settings.get("automatic_backup_schedule", "disabled")
    retention = settings.get("automatic_backup_retention", "10")
    return {
        "schedule": schedule if schedule in {"disabled", "daily", "weekly"} else "disabled",
        "time": _validated_clock_time(settings.get("automatic_backup_time"), "02:00"),
        "retention": retention if retention in {"5", "10", "20", "50"} else "10",
        "last_run": settings.get("automatic_backup_last_run", "Never") or "Never",
    }


def run_due_automatic_backup(force: bool = False) -> str:
    cfg = backup_settings(); schedule = str(cfg["schedule"])
    if schedule == "disabled" and not force:
        return "disabled"
    current = datetime.now().replace(second=0, microsecond=0)
    hour, minute = [int(part) for part in str(cfg["time"]).split(":", 1)]
    last = _parse_setting_datetime(str(cfg["last_run"]))
    interval_days = 1 if schedule == "daily" else 7
    if not force:
        if (current.hour, current.minute) < (hour, minute):
            return "not due"
        if last and (current.date() - last.date()).days < interval_days:
            return "already completed"
    create_full_backup("automatic")
    prune_backups(int(cfg["retention"]))
    with db() as con:
        con.execute("INSERT INTO settings(key,value) VALUES ('automatic_backup_last_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now(),))
    return "backup completed"

@app.post("/settings/account/sessions/{session_id}/revoke")
def revoke_account_session(request: Request, session_id: int):
    user = request.state.user
    with db() as con:
        con.execute("DELETE FROM auth_sessions WHERE id=? AND user_id=? AND id<>?", (session_id,user["id"],user["session_id"]))
    return RedirectResponse("/settings?account_open=1&account_message=Session+signed+out.&account_ok=1", status_code=303)


@app.post("/settings/account/sessions/revoke-others")
def revoke_other_account_sessions(request: Request):
    user = request.state.user
    with db() as con:
        con.execute("DELETE FROM auth_sessions WHERE user_id=? AND id<>?", (user["id"],user["session_id"]))
    return RedirectResponse("/settings?account_open=1&account_message=Other+sessions+signed+out.&account_ok=1", status_code=303)


@app.post("/settings/account/sessions/revoke-all")
def revoke_all_account_sessions(request: Request):
    user = request.state.user
    with db() as con:
        con.execute("DELETE FROM auth_sessions WHERE user_id=?", (user["id"],))
    response = RedirectResponse("/login", status_code=303)
    _delete_session_cookie(response, request)
    return response


@app.post("/settings/account/trusted-devices/{device_id}/revoke")
def revoke_trusted_device(request: Request, device_id: int):
    user = request.state.user
    raw = request.cookies.get(TRUSTED_DEVICE_COOKIE, "")
    with db() as con:
        row = con.execute("SELECT token_hash FROM trusted_devices WHERE id=? AND user_id=?", (device_id,user["id"])).fetchone()
        con.execute("DELETE FROM trusted_devices WHERE id=? AND user_id=?", (device_id,user["id"]))
    response = RedirectResponse("/settings?account_open=1&account_message=Trusted+device+removed.&account_ok=1", status_code=303)
    if row and raw and hmac.compare_digest(row["token_hash"], _hash_session_token(raw)):
        _delete_trusted_device_cookie(response, request)
    return response


@app.post("/settings/account/trusted-devices/revoke-all")
def revoke_all_trusted_devices(request: Request):
    with db() as con:
        con.execute("DELETE FROM trusted_devices WHERE user_id=?", (request.state.user["id"],))
    response = RedirectResponse("/settings?account_open=1&account_message=All+trusted+devices+removed.&account_ok=1", status_code=303)
    _delete_trusted_device_cookie(response, request)
    return response




def documentation_catalog() -> list[tuple[str, str]]:
    docs_dir = BASE_DIR / "docs"
    ordered_docs = [
        ("PROJECT.md", "Purpose and product scope"),
        ("INSTALL.md", "Installation and first-run setup"),
        ("SYSTEM_CHECKS.md", "System Checks"),
        ("DEVICE_PROFILES.md", "Device Profiles"),
        ("BACKUPS.md", "Backups and restore"),
        ("SECURITY.md", "Security"),
        ("DECISIONS.md", "Product decisions"),
        ("ROADMAP.md", "Roadmap"),
        ("IDEAS.md", "Ideas"),
        ("ARCHITECTURE.md", "Architecture"),
        ("DATABASE_DESIGN.md", "Database design"),
        ("RELEASE_PROCESS.md", "Release process"),
        ("TODO.md", "Technical notes"),
    ]
    return [(name, title) for name, title in ordered_docs if (docs_dir / name).is_file()]


def documentation_content(filename: str) -> tuple[str, str]:
    available = documentation_catalog()
    allowed = {name: title for name, title in available}
    selected = filename if filename in allowed else (available[0][0] if available else "")
    path = BASE_DIR / "docs" / selected
    content = path.read_text(encoding="utf-8") if selected and path.is_file() else "Documentation is not available."
    return allowed.get(selected, "Documentation"), content


@app.get("/help", response_class=HTMLResponse)
def help_page(request: Request):
    return RedirectResponse("/settings?documentation_open=1#documentation", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    active_sessions, trusted_devices = _account_security_data(int(request.state.user["id"]), int(request.state.user["session_id"]))
    user = request.state.user
    mfa_setup = request.query_params.get("mfa_setup", "")
    return templates.TemplateResponse("settings.html", page_context(request, "settings", active_sessions=active_sessions, trusted_devices=trusted_devices, account_message=request.query_params.get("account_message", ""), account_ok=request.query_params.get("account_ok", ""), account_open=request.query_params.get("account_open", ""), mfa_setup=mfa_setup, mfa_secret=str(user["totp_secret"] or ""), mfa_qr_data_uri=_totp_qr_data_uri(user["username"], str(user["totp_secret"] or "")) if mfa_setup == "1" and str(user["totp_secret"] or "") else "", profile_initials=_profile_initials(user), categories=fetch_category_configs(), category_usage=category_usage(), ssh_profiles=fetch_ssh_profiles(), key_files=available_key_files(), key_dir=str(KEY_DIR), maintenance_schedule=automatic_maintenance_schedule(), health_interval=get_settings().get("default_health_check_interval_minutes", "10"), device_profiles=device_profiles_status(), device_profiles_message=request.query_params.get("device_profiles_message", ""), device_profiles_ok=request.query_params.get("device_profiles_ok", ""), device_profiles_open=request.query_params.get("device_profiles_open", ""), application_update=application_update_info(), update_message=request.query_params.get("update_message", ""), update_ok=request.query_params.get("update_ok", ""), update_open=request.query_params.get("update_open", ""), release_notes_open=request.query_params.get("release_notes_open", ""), notification=notification_settings(), notification_message=request.query_params.get("notification_message", ""), notification_ok=request.query_params.get("notification_ok", ""), notification_open=request.query_params.get("notification_open", ""), import_message=request.query_params.get("import_message", ""), import_ok=request.query_params.get("import_ok", ""), import_open=request.query_params.get("import_open", ""), backups=list_backups(), backup_config=backup_settings(), backup_message=request.query_params.get("backup_message", ""), backup_ok=request.query_params.get("backup_ok", ""), backup_open=request.query_params.get("backup_open", ""), authentication=_auth_settings(), users=fetch_users() if _is_admin(request) else [], auth_message=request.query_params.get("auth_message", ""), auth_ok=request.query_params.get("auth_ok", ""), auth_open=request.query_params.get("auth_open", ""), integrity_report=json.loads(get_settings().get("data_integrity_report", "{}") or "{}"), integrity_message=request.query_params.get("integrity_message", ""), integrity_ok=request.query_params.get("integrity_ok", ""), integrity_open=request.query_params.get("integrity_open", ""), documentation=documentation_catalog(), documentation_open=request.query_params.get("documentation_open", ""), system_action_message=request.query_params.get("system_action_message", ""), system_action_ok=request.query_params.get("system_action_ok", ""), system_actions_open=request.query_params.get("system_actions_open", ""), authorization_message=request.query_params.get("authorization_message", ""), authorization_ok=request.query_params.get("authorization_ok", "")))




@app.get("/device-profiles/match")
def device_profile_match_api(vendor: str = "", model: str = ""):
    profile = _available_device_profile(vendor, model, sync_if_empty=True)
    if not profile:
        return JSONResponse({"match": False})
    device = profile.get("device") or {}
    firmware = profile.get("firmware") or {}
    source = firmware.get("source") or {}
    return JSONResponse({
        "match": True,
        "id": profile.get("id", ""),
        "profile_version": profile.get("profile_version", 0),
        "origin": profile.get("origin", ""),
        "status": profile.get("status", ""),
        "vendor": device.get("vendor", ""),
        "model": device.get("model", ""),
        "category": device.get("category", ""),
        "strategy": firmware.get("strategy", ""),
        "source_url": source.get("url", ""),
    })


@app.get("/settings/device-profiles/check", include_in_schema=False)
def device_profiles_check_refresh():
    return RedirectResponse("/settings?device_profiles_open=1#device-profiles", status_code=303)


@app.post("/settings/device-profiles/check")
def device_profiles_check_now():
    result = sync_device_profiles()
    if result.get("ok"):
        count = int(result.get("updated", 0) or 0)
        message = f"Device Profiles checked successfully. {count} profile{'s' if count != 1 else ''} updated." if count else "Device Profiles checked successfully. Catalog is up to date."
        ok = 1
    else:
        message = f"Device Profiles check failed: {result.get('error', 'unknown error')}"
        ok = 0
    return RedirectResponse(f"/settings?device_profiles_message={quote(message)}&device_profiles_ok={ok}&device_profiles_open=1#device-profiles", status_code=303)


@app.get("/settings/documentation/{filename}", response_class=HTMLResponse)
def settings_documentation(request: Request, filename: str):
    title, content = documentation_content(filename)
    return templates.TemplateResponse(
        "documentation.html",
        page_context(request, "settings", selected_title=title, document_content=content),
    )


@app.get("/settings/data-integrity/check", include_in_schema=False)
@app.get("/settings/backups/create", include_in_schema=False)
@app.get("/settings/backups/restore-upload", include_in_schema=False)
def settings_long_action_refresh():
    return RedirectResponse("/settings", status_code=303)

@app.get("/settings/backups/{filename}/restore", include_in_schema=False)
def settings_backup_restore_refresh(filename: str):
    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/data-integrity/check")
def run_data_integrity_check(request: Request):
    if not _is_admin(request):
        return RedirectResponse("/settings", status_code=303)
    try:
        with db() as con:
            report = _repair_and_audit_integrity(con)
        message, ok = f"Integrity check passed: {len(report['checks'])} checks completed.", 1
    except Exception as exc:
        message, ok = f"Integrity check failed: {exc}", 0
    return RedirectResponse(f"/settings?integrity_message={quote(message)}&integrity_ok={ok}&integrity_open=1", status_code=303)

@app.post("/settings/backups/create")
def create_backup_route():
    try:
        backup = create_full_backup("manual")
        message, ok = f"Backup created: {backup.name}", 1
    except Exception as exc:
        message, ok = f"Backup failed: {exc}", 0
    return RedirectResponse(f"/settings?backup_message={quote(message)}&backup_ok={ok}&backup_open=1", status_code=303)


@app.post("/settings/backups/configure")
def configure_backups(automatic_backup_schedule: str = Form("disabled"), automatic_backup_time: str = Form("02:00"), automatic_backup_retention: str = Form("10")):
    schedule = automatic_backup_schedule if automatic_backup_schedule in {"disabled", "daily", "weekly"} else "disabled"
    backup_time = _validated_clock_time(automatic_backup_time, "02:00")
    retention = automatic_backup_retention if automatic_backup_retention in {"5", "10", "20", "50"} else "10"
    with db() as con:
        for key, value in (("automatic_backup_schedule", schedule), ("automatic_backup_time", backup_time), ("automatic_backup_retention", retention)):
            con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    return RedirectResponse("/settings?backup_message=Backup+schedule+saved.&backup_ok=1&backup_open=1", status_code=303)


@app.get("/settings/backups/{filename}/download")
def download_backup(filename: str):
    safe = Path(filename).name
    path = BACKUP_DIR / safe
    if safe != filename or not path.is_file() or path.suffix != ".oi-backup":
        return RedirectResponse("/settings?backup_message=Backup+not+found.&backup_ok=0&backup_open=1", status_code=303)
    return FileResponse(path, filename=path.name, media_type="application/zip")


@app.post("/settings/backups/{filename}/delete")
def delete_backup(filename: str):
    safe = Path(filename).name; path = BACKUP_DIR / safe
    if safe == filename and path.is_file() and path.suffix == ".oi-backup": path.unlink()
    return RedirectResponse("/settings?backup_message=Backup+deleted.&backup_ok=1&backup_open=1", status_code=303)


@app.post("/settings/backups/{filename}/restore")
def restore_saved_backup(filename: str):
    safe = Path(filename).name; path = BACKUP_DIR / safe
    try:
        if safe != filename or not path.is_file(): raise ValueError("Backup not found.")
        # Keep an independent pre-restore recovery file on the server.
        create_full_backup("pre-restore")
        restore_full_backup(path)
        message, ok = "Backup restored successfully.", 1
    except Exception as exc:
        message, ok = f"Restore failed: {exc}", 0
    return RedirectResponse(f"/settings?backup_message={quote(message)}&backup_ok={ok}&backup_open=1", status_code=303)


@app.post("/settings/backups/restore-upload")
async def restore_uploaded_backup(file: UploadFile = File(...)):
    raw = await file.read(BACKUP_MAX_BYTES + 1)
    if len(raw) > BACKUP_MAX_BYTES:
        return RedirectResponse("/settings?backup_message=Restore+failed:+backup+exceeds+1+GB.&backup_ok=0&backup_open=1", status_code=303)
    temporary = BACKUP_DIR / f"upload-{uuid.uuid4().hex}.oi-backup.tmp"
    try:
        temporary.write_bytes(raw); validate_full_backup(temporary)
        create_full_backup("pre-restore")
        restore_full_backup(temporary)
        message, ok = "Uploaded backup restored successfully.", 1
    except Exception as exc:
        message, ok = f"Restore failed: {exc}", 0
    finally:
        temporary.unlink(missing_ok=True)
    return RedirectResponse(f"/settings?backup_message={quote(message)}&backup_ok={ok}&backup_open=1", status_code=303)


@app.post("/settings/device-import")
async def import_device(file: UploadFile = File(...), conflict_mode: str = Form("copy")):
    raw = await file.read(DEVICE_EXPORT_MAX_BYTES + 1)
    if len(raw) > DEVICE_EXPORT_MAX_BYTES:
        message = "Import failed: device export is larger than 50 MB."
        return RedirectResponse(f"/settings?import_message={quote(message)}&import_ok=0&backup_open=1", status_code=303)
    with _database_gate.access():
        try:
            with zipfile.ZipFile(BytesIO(raw), "r") as archive:
                infos = archive.infolist()
                if len(infos) > 100 or sum(info.file_size for info in infos) > DEVICE_EXPORT_MAX_UNCOMPRESSED:
                    raise ValueError("Archive limits exceeded.")
                if len({info.filename for info in infos}) != len(infos):
                    raise ValueError("Duplicate archive entries are not allowed.")
                if any(not _safe_device_archive_member(info.filename) for info in infos):
                    raise ValueError("Unsafe archive path.")
                if "device.json" not in archive.namelist():
                    raise ValueError("device.json is missing.")
                payload = json.loads(archive.read("device.json").decode("utf-8"))
                if payload.get("format") != DEVICE_EXPORT_FORMAT or int(payload.get("schema_version", 0)) != DEVICE_EXPORT_SCHEMA:
                    raise ValueError("Unsupported device export format.")
                device_data = payload.get("device")
                attachment_entries = payload.get("attachments", [])
                if not isinstance(device_data, dict) or not isinstance(attachment_entries, list):
                    raise ValueError("Invalid device export data.")
                if not str(device_data.get("display_name") or device_data.get("name") or "").strip():
                    raise ValueError("Device name is missing.")
                attachment_files = []
                for entry in attachment_entries:
                    archive_name = str(entry.get("archive_name") or "")
                    if archive_name not in archive.namelist() or not archive_name.startswith("attachments/"):
                        raise ValueError("An attachment is missing from the archive.")
                    data = archive.read(archive_name)
                    if hashlib.sha256(data).hexdigest() != str(entry.get("sha256") or ""):
                        raise ValueError("Attachment checksum validation failed.")
                    attachment_files.append((entry, data))
        except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            message = f"Import failed: {exc}"
            return RedirectResponse(f"/settings?import_message={quote(message)}&import_ok=0&backup_open=1", status_code=303)

        imported_files: list[Path] = []
        replaced_files: list[Path] = []
        try:
            with db() as con:
                columns = [row[1] for row in con.execute("PRAGMA table_info(devices)").fetchall() if row[1] != "id"]
                clean = {column: device_data.get(column) for column in columns if column in device_data and column != "owner_user_id"}
                clean["owner_user_id"] = require_current_user_id()
                clean["name"] = str(clean.get("display_name") or clean.get("name") or "Imported device").strip()
                clean["display_name"] = clean["name"]
                clean["updated_at"] = now()
                clean.setdefault("created_at", now())
                category = str(clean.get("category") or "Other").strip() or "Other"
                clean["category"] = category
                con.execute("INSERT OR IGNORE INTO categories(owner_user_id,name,show_ownership,show_firmware,show_network,show_health,show_updates,show_system_checks) VALUES (?,?,1,1,0,0,0,0)", (require_current_user_id(), category))
                match = _find_import_match(con, clean)
                replace = conflict_mode == "replace" and match is not None
                if replace:
                    device_id = int(match["id"])
                    replaced_files = [UPLOAD_DIR / old["stored_name"] for old in con.execute("SELECT stored_name FROM attachments WHERE device_id=?", (device_id,)).fetchall()]
                    con.execute("DELETE FROM attachments WHERE device_id=?", (device_id,))
                    assignments = ", ".join(f'"{key}"=?' for key in clean)
                    con.execute(f"UPDATE devices SET {assignments} WHERE id=?", (*clean.values(), device_id))
                else:
                    if match:
                        base = clean["display_name"]
                        suffix = " (Imported)"
                        candidate = base + suffix
                        index = 2
                        while con.execute("SELECT 1 FROM devices WHERE owner_user_id=? AND LOWER(display_name)=LOWER(?)", (require_current_user_id(), candidate)).fetchone():
                            candidate = f"{base}{suffix[:-1]} {index})"
                            index += 1
                        clean["display_name"] = clean["name"] = candidate
                    names = ", ".join(f'"{key}"' for key in clean)
                    placeholders = ", ".join("?" for _ in clean)
                    cur = con.execute(f"INSERT INTO devices ({names}) VALUES ({placeholders})", tuple(clean.values()))
                    device_id = int(cur.lastrowid)
                for entry, data in attachment_files:
                    original_name = Path(str(entry.get("original_name") or "attachment")).name or "attachment"
                    stored_name = f"{device_id}-{uuid.uuid4().hex}-{safe_report_filename(original_name)}"
                    target = UPLOAD_DIR / stored_name
                    target.write_bytes(data)
                    imported_files.append(target)
                    con.execute("INSERT INTO attachments(device_id, original_name, stored_name, description, created_at) VALUES (?,?,?,?,?)", (device_id, original_name, stored_name, str(entry.get("description") or ""), str(entry.get("created_at") or now())))
            for path in replaced_files:
                path.unlink(missing_ok=True)
            message = f"Device imported successfully: {clean['display_name']}"
            return RedirectResponse(f"/devices/{device_id}?imported=1", status_code=303)
        except Exception:
            for path in imported_files:
                path.unlink(missing_ok=True)
            message = "Import failed: no changes were saved."
            return RedirectResponse(f"/settings?import_message={quote(message)}&import_ok=0&backup_open=1", status_code=303)


@app.post("/settings/categories")
def add_category(name: str = Form(""), show_ownership: Optional[str] = Form(None), show_firmware: Optional[str] = Form(None), show_network: Optional[str] = Form(None), show_system_checks: Optional[str] = Form(None)):
    name = (name or "").strip()
    if name:
        system_checks = 1 if show_system_checks else 0
        with db() as con:
            con.execute("INSERT OR IGNORE INTO categories(owner_user_id,name,show_ownership,show_firmware,show_network,show_health,show_updates,show_system_checks) VALUES (?,?,?,?,?,?,?,?)", (require_current_user_id(), name, 1 if show_ownership else 0, 1 if show_firmware else 0, 1 if show_network else 0, system_checks, system_checks, system_checks))
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/categories/edit")
def edit_category(old_name: str = Form(""), new_name: str = Form(""), show_ownership: Optional[str] = Form(None), show_firmware: Optional[str] = Form(None), show_network: Optional[str] = Form(None), show_system_checks: Optional[str] = Form(None)):
    old_name = (old_name or "").strip()
    new_name = (new_name or "").strip()
    if old_name and new_name:
        system_checks = 1 if show_system_checks else 0
        flags = (1 if show_ownership else 0, 1 if show_firmware else 0, 1 if show_network else 0, system_checks, system_checks, system_checks)
        with db() as con:
            if old_name != new_name:
                exists = con.execute("SELECT 1 FROM categories WHERE owner_user_id=? AND name=? COLLATE NOCASE", (require_current_user_id(), new_name)).fetchone()
                if exists:
                    return RedirectResponse("/settings", status_code=303)

@app.post("/settings/categories/delete")
def delete_category(name: str = Form("")):
    name = (name or "").strip()
    if name:
        with db() as con:
            used = con.execute(
                "SELECT COUNT(*) FROM devices WHERE owner_user_id=? AND LOWER(TRIM(COALESCE(category,''))) = LOWER(TRIM(?))",
                (require_current_user_id(), name),
            ).fetchone()[0]
            if used == 0:
                con.execute("DELETE FROM categories WHERE owner_user_id=? AND name=?", (require_current_user_id(), name))
    return RedirectResponse("/settings", status_code=303)




@app.post("/settings/notifications")
def save_notification_settings(
    notifications_enabled: Optional[str] = Form(None), notification_health_enabled: Optional[str] = Form(None),
    notification_firmware_enabled: Optional[str] = Form(None), notification_updates_enabled: Optional[str] = Form(None),
    notification_application_enabled: Optional[str] = Form(None), smtp_host: str = Form(""), smtp_port: str = Form("587"),
    smtp_encryption: str = Form("starttls"), smtp_username: str = Form(""), smtp_password: str = Form(""),
    smtp_sender_name: str = Form("Outlaw's Inventory"), smtp_sender_address: str = Form(""), smtp_recipient_address: str = Form(""),
    application_base_url: str = Form(""), return_to: str = Form(""),
):
    with _database_gate.access():
        values={"smtp_host":smtp_host.strip(), "smtp_port":smtp_port.strip() or "587", "smtp_encryption":smtp_encryption if smtp_encryption in {"starttls","ssl","none"} else "starttls", "smtp_username":smtp_username.strip(), "smtp_sender_name":smtp_sender_name.strip() or "Outlaw's Inventory", "smtp_sender_address":smtp_sender_address.strip(), "smtp_recipient_address":smtp_recipient_address.strip(), "application_base_url":application_base_url.strip().rstrip("/")}
        if return_to == "first-run":
            values.update({"notifications_enabled":"true" if notifications_enabled else "false", "notification_health_enabled":"true" if notification_health_enabled else "false", "notification_firmware_enabled":"true" if notification_firmware_enabled else "false", "notification_updates_enabled":"true" if notification_updates_enabled else "false", "notification_application_enabled":"true" if notification_application_enabled else "false"})
        with db() as con:
            for key,value in values.items(): con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value))
        if smtp_password.strip():
            SMTP_PASSWORD_FILE.write_text(smtp_password.strip(), encoding="utf-8"); SMTP_PASSWORD_FILE.chmod(0o600)
        if return_to == "first-run":
            _set_first_run_step("finish")
            return RedirectResponse("/first-run?step=finish", status_code=303)
        return RedirectResponse("/settings?notification_message=Notification+settings+saved.&notification_ok=1&notification_open=1", status_code=303)


@app.post("/settings/notifications/autosave")
async def autosave_notification_settings(request: Request):
    data = await request.json()
    allowed = {
        "notifications_enabled",
        "notification_health_enabled",
        "notification_firmware_enabled",
        "notification_updates_enabled",
        "notification_application_enabled",
    }
    values = {}
    for key, value in data.items():
        if key not in allowed:
            continue
        if isinstance(value, bool):
            values[key] = "true" if value else "false"
        elif str(value).strip().lower() in {"1", "true", "yes", "on"}:
            values[key] = "true"
        else:
            values[key] = "false"
    if not values:
        return JSONResponse({"ok": False, "error": "No supported notification setting supplied."}, status_code=400)
    with db() as con:
        for key, value in values.items():
            con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    return JSONResponse({"ok": True, "saved": list(values)})


@app.post("/settings/notifications/test")
def test_notification_settings():
    stamp = now()
    ok, message = send_notification_email(
        "Outlaw's Inventory test notification",
        f"This is a test notification from Outlaw's Inventory v{APP_VERSION}.\n\nSent: {stamp}",
        _notification_email_html(
            "Test notification",
            "Email notifications are configured correctly.",
            [("Application version", f"v{APP_VERSION}"), ("Sent", stamp)],
            accent="#22c55e",
            footer_text="Outlaw's Inventory notification test",
        ),
    )
    return RedirectResponse(f"/settings?notification_message={quote(message)}&notification_ok={1 if ok else 0}&notification_open=1", status_code=303)


@app.post("/settings/autosave")
async def autosave_settings(request: Request):
    data = await request.json()
    admin_only = {"daily_check_time", "maintenance_check_interval_hours", "default_health_check_interval_minutes", "disk_usage_warning_percent", "disk_usage_critical_percent"}
    if any(key in admin_only for key in data) and not _is_admin(request):
        return JSONResponse({"ok": False, "error": "Administrator access required."}, status_code=403)
    allowed = {
        "dashboard_refresh_minutes", "language", "daily_check_time",
        "maintenance_check_interval_hours", "default_health_check_interval_minutes",
        "disk_usage_warning_percent", "disk_usage_critical_percent",
    }
    values = {}
    for key, value in data.items():
        if key not in allowed:
            continue
        text = str(value).strip()
        if key == "daily_check_time":
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text): text = "03:00"
        elif key == "maintenance_check_interval_hours":
            try: text = str(max(0, min(168, int(text))))
            except ValueError: text = "24"
        elif key == "language":
            text = text if text in {"en", "nl"} else "en"
        elif key == "default_health_check_interval_minutes":
            try: text = str(max(1, min(1440, int(text))))
            except ValueError: text = "10"
        elif key in {"disk_usage_warning_percent", "disk_usage_critical_percent"}:
            try: text = str(max(1, min(100, int(text))))
            except ValueError: text = "85" if key.endswith("warning_percent") else "95"
        values[key] = text
    with db() as con:
        for key, value in values.items():
            con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        if "default_health_check_interval_minutes" in values:
            con.execute("UPDATE health_checks SET interval_minutes=?, updated_at=? WHERE enabled=1", (int(values["default_health_check_interval_minutes"]), now()))
    return JSONResponse({"ok": True, "saved": list(values)})

@app.post("/settings")
def save_settings_compat(daily_check_time: str = Form("08:00"), dashboard_refresh_minutes: str = Form("5"), system_update_checks_enabled: Optional[str] = Form(None), system_update_check_interval_hours: str = Form("24"), default_health_check_interval_minutes: str = Form("10")):
    values = {
        "daily_check_time": daily_check_time, "dashboard_refresh_minutes": dashboard_refresh_minutes,
        "system_update_checks_enabled": "true" if system_update_checks_enabled else "false",
        "system_update_check_interval_hours": system_update_check_interval_hours,
        "default_health_check_interval_minutes": default_health_check_interval_minutes,
    }
    with db() as con:
        for key, value in values.items():
            con.execute("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    return RedirectResponse("/settings", status_code=303)



def _public_key_line(private_key_path: str) -> str:
    key = _load_private_key(private_key_path)
    return f"{key.get_name()} {key.get_base64()} outlaws-inventory"


def inspect_host_integration(device: sqlite3.Row, profile: sqlite3.Row | None) -> dict[str, object]:
    target = resolved_target(device["id"], "")
    result: dict[str, object] = {
        "target": target, "reachable": False, "key_login": False, "os_name": "Unknown",
        "apt_available": False, "sudo_update": False, "sudo_upgrade": False, "sudo_kernel_upgrade": False, "sudo_pihole_check": False, "sudo_pihole_update": False, "sudo_minecraft_update": False, "sudo_reboot": False,
        "virtualization": "unknown", "is_container": False, "messages": [],
    }
    if not target:
        result["messages"].append("Add an IPv4 address or hostname to this Inventory item first.")
        return result
    if not profile:
        result["messages"].append("Select an SSH profile.")
        return result
    client = _ssh_client(profile)
    try:
        pkey = _load_private_key(profile["private_key_path"])
        client.connect(
            hostname=target, port=int(profile["port"] or 22), username=profile["username"], pkey=pkey,
            timeout=8, auth_timeout=8, banner_timeout=8, look_for_keys=False, allow_agent=False,
        )
        result["reachable"] = True
        result["key_login"] = True
        command = (
            "printf '__OS__\\n'; . /etc/os-release 2>/dev/null; printf '%s\\n' \"${PRETTY_NAME:-Unknown}\"; "
            "printf '__VIRT__\\n'; /usr/bin/systemd-detect-virt 2>/dev/null || echo none; "
            "printf '__CONTAINER__\\n'; /usr/bin/systemd-detect-virt --container >/dev/null 2>&1 && echo yes || echo no; "
            "printf '__APT__\\n'; command -v /usr/bin/apt-get >/dev/null && echo yes || echo no; "
            "printf '__UPDATE__\\n'; sudo -n -l /usr/bin/apt-get update >/dev/null 2>&1 && echo yes || echo no; "
            "printf '__UPGRADE__\\n'; sudo -n -l /usr/bin/apt-get upgrade -y >/dev/null 2>&1 && echo yes || echo no; "
            "printf '__PIHOLECHECK__\\n'; if test -x /usr/local/bin/pihole; then sudo -n -l /usr/local/bin/pihole -up --check-only >/dev/null 2>&1 && echo yes || echo no; else echo na; fi; "
            "printf '__PIHOLEUPDATE__\\n'; if test -x /usr/local/bin/pihole; then sudo -n -l /usr/local/bin/pihole -up >/dev/null 2>&1 && echo yes || echo no; else echo na; fi; "
            "printf '__KERNEL__\\n'; test -x /usr/local/sbin/outlaws-kernel-upgrade && sudo -n -l /usr/local/sbin/outlaws-kernel-upgrade >/dev/null 2>&1 && echo yes || echo no; "
            "printf '__MINECRAFTUPDATE__\\n'; if test -x /usr/local/sbin/outlaws-minecraft-update; then sudo -n -l /usr/local/sbin/outlaws-minecraft-update /tmp/outlaws-validation.jar >/dev/null 2>&1 && echo yes || echo no; else echo no; fi; "
            "printf '__REBOOT__\\n'; sudo -n -l /usr/sbin/reboot >/dev/null 2>&1 && echo yes || echo no"
        )
        _, stdout, _ = client.exec_command(command, timeout=20)
        out = stdout.read().decode("utf-8", "replace")
        def section(name: str) -> str:
            token = f"__{name}__\n"
            if token not in out:
                return ""
            return out.split(token, 1)[1].split("__", 1)[0].strip()
        result["os_name"] = section("OS") or "Unknown"
        result["virtualization"] = section("VIRT") or "none"
        result["is_container"] = section("CONTAINER") == "yes"
        result["apt_available"] = section("APT") == "yes"
        result["sudo_pihole_check"] = section("PIHOLECHECK") == "yes"
        result["sudo_pihole_update"] = section("PIHOLEUPDATE") == "yes"
        result["sudo_minecraft_update"] = section("MINECRAFTUPDATE") == "yes"
        result["sudo_update"] = section("UPDATE") == "yes"
        result["sudo_upgrade"] = section("UPGRADE") == "yes"
        result["sudo_kernel_upgrade"] = section("KERNEL") == "yes"
        result["sudo_reboot"] = section("REBOOT") == "yes"
    except Exception as exc:
        result["messages"].append(str(exc))
    finally:
        client.close()
    return result


def managed_host_validation(device: sqlite3.Row, profile: sqlite3.Row | None = None) -> dict[str, object]:
    """Validate integration health without changing the remote host."""
    if profile is None and device["managed_ssh_profile_id"]:
        profile = fetch_ssh_profile(int(device["managed_ssh_profile_id"]))
    inspection = inspect_host_integration(device, profile)
    with db() as con:
        health = con.execute("SELECT id, enabled, status, last_error FROM health_checks WHERE device_id=? LIMIT 1", (device["id"],)).fetchone()
        update = con.execute("SELECT id, enabled, status, last_error FROM update_checks WHERE device_id=? LIMIT 1", (device["id"],)).fetchone()
        pihole = con.execute("SELECT id, enabled, status, last_error FROM application_checks WHERE device_id=? AND application_type='pihole' LIMIT 1", (device["id"],)).fetchone()
        minecraft = con.execute("SELECT id, enabled, status, last_error FROM application_checks WHERE device_id=? AND application_type='minecraft' LIMIT 1", (device["id"],)).fetchone()
    details = {
        "reachable": bool(inspection.get("reachable")),
        "key_login": bool(inspection.get("key_login")),
        "os_name": str(inspection.get("os_name") or "Unknown"),
        "virtualization": str(inspection.get("virtualization") or "unknown"),
        "is_container": bool(inspection.get("is_container")),
        "apt_available": bool(inspection.get("apt_available")),
        "sudo_update": bool(inspection.get("sudo_update")),
        "sudo_upgrade": bool(inspection.get("sudo_upgrade")),
        "sudo_kernel_upgrade": bool(inspection.get("sudo_kernel_upgrade")),
        "sudo_pihole_check": bool(inspection.get("sudo_pihole_check")),
        "sudo_pihole_update": bool(inspection.get("sudo_pihole_update")),
        "sudo_minecraft_update": bool(inspection.get("sudo_minecraft_update")),
        "sudo_reboot": bool(inspection.get("sudo_reboot")),
        "health_check": bool(health and health["enabled"]),
        "health_status": str(health["status"] if health else "missing"),
        "update_check": bool(update and update["enabled"]),
        "update_status": str(update["status"] if update else "missing"),
        "pihole_check": bool(pihole and pihole["enabled"]),
        "pihole_status": str(pihole["status"] if pihole else "missing"),
        "minecraft_check": bool(minecraft and minecraft["enabled"]),
        "minecraft_status": str(minecraft["status"] if minecraft else "missing"),
        "messages": list(inspection.get("messages") or []),
    }
    critical_ok = details["reachable"] and details["key_login"]
    configuration_ok = all(details[key] for key in ("apt_available", "sudo_update", "sudo_upgrade", "sudo_kernel_upgrade", "sudo_reboot", "health_check", "update_check"))
    if details["pihole_check"]:
        configuration_ok = configuration_ok and details["sudo_pihole_check"] and details["sudo_pihole_update"]
    if details["minecraft_check"]:
        configuration_ok = configuration_ok and details["sudo_minecraft_update"]
    # A persisted check result describes the last check run, not whether the
    # managed-host configuration itself is valid. Reconfiguration is determined
    # from fresh SSH/permission inspection; checks are executed immediately after.
    if critical_ok and configuration_ok:
        status = "ready"
        message = "Host integration is ready."
    elif critical_ok:
        status = "warning"
        message = "Host is reachable, but part of the managed integration needs attention."
    else:
        status = "failed"
        message = "Managed SSH validation failed."
    details["status"] = status
    details["message"] = message
    return details


def store_managed_host_validation(device_id: int, validation: dict[str, object]) -> None:
    with db() as con:
        platform = str(validation.get("virtualization") or "unknown")
        virtual = 0 if platform in ("none", "unknown", "") else 1
        con.execute(
            "UPDATE devices SET integration_status=?, integration_checked_at=?, integration_message=?, integration_details=?, detected_platform=?, virtual_device=CASE WHEN ?=1 THEN 1 ELSE virtual_device END, updated_at=? WHERE id=?",
            (validation["status"], now(), validation["message"], json.dumps(validation), platform, virtual, now(), device_id),
        )



SYSTEM_CHECK_ACCOUNT = "outlaw"
SYSTEM_CHECK_PACKAGES = ("sudo", "curl", "nano", "ca-certificates", "locales", "tzdata")


def ensure_system_check_profile() -> sqlite3.Row:
    with _database_gate.access():
        owner_user_id = require_current_user_id()
        # Reuse an existing outlaw profile first so an already-deployed, working
        # SSH identity is not replaced during reconfiguration.
        with db() as con:
            existing = con.execute(
                "SELECT * FROM ssh_profiles WHERE owner_user_id=? AND username=? "
                "ORDER BY CASE WHEN name='System Checks' THEN 0 ELSE 1 END, id LIMIT 1",
                (owner_user_id, SYSTEM_CHECK_ACCOUNT),
            ).fetchone()
            if existing:
                if str(existing["name"] or "") != "System Checks":
                    conflict = con.execute("SELECT id FROM ssh_profiles WHERE owner_user_id=? AND name='System Checks' AND id<>? LIMIT 1", (owner_user_id, int(existing["id"]))).fetchone()
                    if not conflict:
                        con.execute("UPDATE ssh_profiles SET name='System Checks', updated_at=? WHERE id=? AND owner_user_id=?", (now(), int(existing["id"]), owner_user_id))
                        existing = con.execute("SELECT * FROM ssh_profiles WHERE id=?", (int(existing["id"]),)).fetchone()
                return existing

        key_path = KEY_DIR / "system-checks-rsa"
        if not key_path.exists():
            key = paramiko.RSAKey.generate(3072)
            key.write_private_key_file(str(key_path))
            key_path.chmod(0o600)
            public_line = f"{key.get_name()} {key.get_base64()} outlaws-inventory-system-checks\n"
            key_path.with_suffix(".pub").write_text(public_line, encoding="utf-8")
            key_path.with_suffix(".pub").chmod(0o644)

        with db() as con:
            name_conflict = con.execute(
                "SELECT id, username FROM ssh_profiles WHERE owner_user_id=? AND name='System Checks' LIMIT 1",
                (owner_user_id,),
            ).fetchone()
            if name_conflict:
                raise RuntimeError("System Checks profile name is already in use by a different runtime account.")
            cur = con.execute(
                """INSERT INTO ssh_profiles(owner_user_id,name,username,port,private_key_path,known_host_fingerprint,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (owner_user_id, "System Checks", SYSTEM_CHECK_ACCOUNT, 22, str(key_path), "", now(), now()),
            )
            return con.execute("SELECT * FROM ssh_profiles WHERE id=?", (cur.lastrowid,)).fetchone()


def configure_remote_host(device: sqlite3.Row, profile: sqlite3.Row, bootstrap_username: str, bootstrap_password: str, sudo_password: str, locale_name: str, timezone_name: str, auth_method: str = "admin", cleanup_temporary_root: bool = False, enable_pihole: bool = False, enable_minecraft: bool = False) -> dict[str, object]:
    """Configure the runtime System Checks identity on the existing ``outlaw`` account.

    The supplied administrator/root credentials are bootstrap-only. If ``outlaw``
    does not exist it is created; otherwise the existing account is preserved.
    Reconfigure is idempotent and keeps unrelated administrator sudoers additions.
    """
    target = resolved_target(device["id"], "")
    if not target:
        return {"ok": False, "message": "The device has no IPv4 address or hostname."}
    if not bootstrap_username.strip():
        return {"ok": False, "message": "A bootstrap username is required."}
    try:
        public_key = _public_key_line(profile["private_key_path"])
    except Exception as exc:
        return {"ok": False, "message": f"Could not read the SSH key: {exc}"}

    managed_user = SYSTEM_CHECK_ACCOUNT
    locale_name = locale_name.strip()
    timezone_name = timezone_name.strip()
    if locale_name and not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9-]+)?(?:@[A-Za-z0-9_-]+)?", locale_name):
        return {"ok": False, "message": "Invalid locale."}
    if timezone_name and (not re.fullmatch(r"[A-Za-z0-9_+/-]+", timezone_name) or ".." in timezone_name or timezone_name.startswith("/")):
        return {"ok": False, "message": "Invalid timezone."}
    kernel_wrapper = "#!/bin/sh\nset -eu\nexec /usr/bin/apt-get install --only-upgrade -y linux-image-amd64\n"
    minecraft_wrapper = r'''#!/usr/bin/python3
import hashlib,json,os,re,shutil,socket,stat,subprocess,sys,tempfile,time,urllib.request,zipfile

if True:
 def fail(message, code=1):
    print(message, file=sys.stderr); raise SystemExit(code)

 def fetch_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'OutlawsInventory-MinecraftUpdater/1'})
    with urllib.request.urlopen(req,timeout=20) as response:
        return json.load(response)

 def jar_version(path):
    try:
        with zipfile.ZipFile(path) as z:
            data=json.loads(z.read('version.json'))
        return str(data.get('id') or data.get('name') or '').strip()
    except Exception:
        return ''

 def configured_port(jar):
    props=os.path.join(os.path.dirname(jar),'server.properties')
    port=25565; bind=''
    try:
        for raw in open(props,encoding='utf-8',errors='replace'):
            line=raw.strip()
            if not line or line.startswith('#') or '=' not in line: continue
            key,value=line.split('=',1)
            if key.strip()=='server-port': port=int(value.strip())
            elif key.strip()=='server-ip': bind=value.strip()
    except Exception:
        pass
    return bind or '127.0.0.1',port

 def wait_ready(unit,jar,seconds=90):
    host,port=configured_port(jar)
    deadline=time.time()+seconds
    while time.time()<deadline:
        active=subprocess.run(['/usr/bin/systemctl','is-active','--quiet',unit]).returncode==0
        if active:
            try:
                with socket.create_connection((host,port),timeout=1): return True
            except Exception: pass
        time.sleep(2)
    return False

if len(sys.argv)!=3: fail('Usage: outlaws-minecraft-update <minecraft.service> <server.jar>',2)
unit=sys.argv[1].strip(); jar=os.path.realpath(sys.argv[2])
if not re.fullmatch(r'[A-Za-z0-9_.@-]*minecraft[A-Za-z0-9_.@-]*\.service',unit,re.I): fail('Refusing non-Minecraft systemd unit.',3)
if not jar.endswith('.jar') or not os.path.isfile(jar): fail('Minecraft server JAR does not exist or is not a .jar file.',4)
load=subprocess.run(['/usr/bin/systemctl','show',unit,'--property=LoadState','--value'],capture_output=True,text=True)
if load.returncode!=0 or load.stdout.strip() in ('','not-found'): fail('Minecraft systemd service was not found.',5)
manifest=fetch_json('https://piston-meta.mojang.com/mc/game/version_manifest_v2.json')
latest=str((manifest.get('latest') or {}).get('release') or '').strip()
entry=next((x for x in manifest.get('versions',[]) if str(x.get('id') or '')==latest),None)
if not latest or not entry or not entry.get('url'): fail('Could not resolve the latest official Minecraft release.',6)
meta=fetch_json(entry['url']); server=((meta.get('downloads') or {}).get('server') or {})
url=str(server.get('url') or ''); expected=str(server.get('sha1') or '').lower()
if not url or not expected: fail('Latest Minecraft release does not expose an official server download.',7)
current=jar_version(jar)
if current==latest:
    print(f'Minecraft server is already current: {current}.'); raise SystemExit(0)
st=os.stat(jar); directory=os.path.dirname(jar); backup=jar+'.outlaws-previous'
fd,tmp=tempfile.mkstemp(prefix='.outlaws-minecraft-',suffix='.jar',dir=directory); os.close(fd)
stopped=False; replaced=False
try:
    subprocess.run(['/usr/bin/systemctl','stop',unit],check=True); stopped=True
    print(f'Stopped {unit}.')
    digest=hashlib.sha1()
    req=urllib.request.Request(url,headers={'User-Agent':'OutlawsInventory-MinecraftUpdater/1'})
    with urllib.request.urlopen(req,timeout=120) as src, open(tmp,'wb') as dst:
        while True:
            chunk=src.read(1024*1024)
            if not chunk: break
            dst.write(chunk); digest.update(chunk)
    if digest.hexdigest().lower()!=expected: fail('Downloaded server.jar failed Mojang SHA-1 verification.',8)
    downloaded=jar_version(tmp)
    if downloaded!=latest: fail(f'Downloaded server.jar reports {downloaded or "unknown"}; expected {latest}.',9)
    os.chown(tmp,st.st_uid,st.st_gid); os.chmod(tmp,stat.S_IMODE(st.st_mode))
    if os.path.exists(backup): os.unlink(backup)
    os.replace(jar,backup); os.replace(tmp,jar); replaced=True
    subprocess.run(['/usr/bin/systemctl','start',unit],check=True)
    if not wait_ready(unit,jar): raise RuntimeError('Updated Minecraft service did not become reachable on its configured port.')
    print(f'Updated Minecraft server: {current or "unknown"} -> {latest}.')
    print(f'Service {unit} is running and listening on port {configured_port(jar)[1]}.')
except BaseException as exc:
    try:
        if replaced and os.path.exists(backup):
            subprocess.run(['/usr/bin/systemctl','stop',unit],check=False)
            if os.path.exists(jar): os.unlink(jar)
            os.replace(backup,jar)
            subprocess.run(['/usr/bin/systemctl','start',unit],check=False)
            print('Update failed; previous server.jar restored.',file=sys.stderr)
        elif stopped:
            subprocess.run(['/usr/bin/systemctl','start',unit],check=False)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    if isinstance(exc,SystemExit): raise
    fail(str(exc),10)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
'''
    required_sudo_rules = [
        f"{managed_user} ALL=(root) NOPASSWD: /usr/bin/apt-get update",
        f"{managed_user} ALL=(root) NOPASSWD: /usr/bin/apt-get upgrade -y",
        f"{managed_user} ALL=(root) NOPASSWD: /usr/local/sbin/outlaws-kernel-upgrade",
        f"{managed_user} ALL=(root) NOPASSWD: /usr/sbin/reboot",
    ]
    if enable_pihole:
        required_sudo_rules.extend([
            f"{managed_user} ALL=(root) NOPASSWD: /usr/local/bin/pihole -up --check-only",
            f"{managed_user} ALL=(root) NOPASSWD: /usr/local/bin/pihole -up",
        ])
    if enable_minecraft:
        required_sudo_rules.append(f"{managed_user} ALL=(root) NOPASSWD: /usr/local/sbin/outlaws-minecraft-update *")

    script_lines = [
        "set -eu",
        "export DEBIAN_FRONTEND=noninteractive",
        "missing_packages=''",
        *[
            f"/usr/bin/dpkg-query -W -f='${{Status}}' {shlex.quote(pkg)} 2>/dev/null | /usr/bin/grep -q 'install ok installed' || missing_packages=\"$missing_packages {shlex.quote(pkg)}\""
            for pkg in SYSTEM_CHECK_PACKAGES
        ],
        'if [ -n "$missing_packages" ]; then /usr/bin/apt-get update && /usr/bin/apt-get install -y $missing_packages; fi',
    ]

    if timezone_name:
        tz = shlex.quote(timezone_name)
        zonefile = shlex.quote(f"/usr/share/zoneinfo/{timezone_name}")
        script_lines += [
            "current_timezone=$(/usr/bin/cat /etc/timezone 2>/dev/null || true)",
            f'if [ "$current_timezone" != {tz} ]; then',
            f"  if [ -e {zonefile} ]; then",
            f"    ( /usr/bin/ln -snf {zonefile} /etc/localtime && /usr/bin/printf '%s\\n' {tz} > /etc/timezone ) || /usr/bin/printf '%s\\n' 'Warning: optional timezone configuration could not be applied.' >&2",
            "  else",
            "    /usr/bin/printf '%s\\n' 'Warning: optional timezone configuration was skipped because the requested zone does not exist.' >&2",
            "  fi",
            "fi",
        ]
    if locale_name:
        loc = shlex.quote(locale_name)
        script_lines += [
            "current_locale=$(/usr/bin/sed -n 's/^LANG=//p' /etc/default/locale 2>/dev/null | /usr/bin/head -n1 | /usr/bin/tr -d '\"' || true)",
            f'if [ "$current_locale" != {loc} ]; then',
            "  (",
            f"    /usr/bin/sed -i -E 's/^# *({re.escape(locale_name)}[[:space:]]+UTF-8)/\\1/' /etc/locale.gen || true",
            "    /usr/sbin/locale-gen",
            f"    /usr/sbin/update-locale LANG={loc}",
            "  ) || /usr/bin/printf '%s\\n' 'Warning: optional locale configuration could not be applied.' >&2",
            "fi",
        ]

    script_lines += [
        f"if ! /usr/bin/id {shlex.quote(managed_user)} >/dev/null 2>&1; then /usr/sbin/useradd --create-home --shell /bin/bash {shlex.quote(managed_user)}; /usr/sbin/usermod --password \"x-outlaws-key-only-$(/usr/bin/date +%s%N)\" {shlex.quote(managed_user)}; fi",
        f"home_dir=$(/usr/bin/getent passwd {shlex.quote(managed_user)} | /usr/bin/cut -d: -f6)",
        'if [ -z "$home_dir" ]; then echo "Managed service account has no home directory." >&2; exit 41; fi',
        f"managed_group=$(/usr/bin/id -gn {shlex.quote(managed_user)})",
        f'/usr/bin/install -d -m 700 -o {shlex.quote(managed_user)} -g "$managed_group" "$home_dir/.ssh"',
        'key_file="$home_dir/.ssh/authorized_keys"',
        f'if [ ! -e "$key_file" ]; then /usr/bin/install -m 600 -o {shlex.quote(managed_user)} -g "$managed_group" /dev/null "$key_file"; fi',
        f'/usr/bin/chown {shlex.quote(managed_user)}:"$managed_group" "$key_file"',
        '/usr/bin/chmod 600 "$key_file"',
        f'/usr/bin/grep -qxF {shlex.quote(public_key)} "$key_file" || /usr/bin/printf \'%s\\n\' {shlex.quote(public_key)} >> "$key_file"',
        'wrapper_tmp=$(/usr/bin/mktemp)',
        f'/usr/bin/printf \'%s\' {shlex.quote(kernel_wrapper)} > "$wrapper_tmp"',
        'if [ ! -f /usr/local/sbin/outlaws-kernel-upgrade ] || ! /usr/bin/cmp -s "$wrapper_tmp" /usr/local/sbin/outlaws-kernel-upgrade; then /usr/bin/install -o root -g root -m 755 "$wrapper_tmp" /usr/local/sbin/outlaws-kernel-upgrade; fi',
        '/usr/bin/rm -f "$wrapper_tmp"',
        'minecraft_wrapper_tmp=$(/usr/bin/mktemp)',
        f'/usr/bin/printf \'%s\' {shlex.quote(minecraft_wrapper)} > "$minecraft_wrapper_tmp"',
        'if [ ! -f /usr/local/sbin/outlaws-minecraft-update ] || ! /usr/bin/cmp -s "$minecraft_wrapper_tmp" /usr/local/sbin/outlaws-minecraft-update; then /usr/bin/install -o root -g root -m 755 "$minecraft_wrapper_tmp" /usr/local/sbin/outlaws-minecraft-update; fi',
        '/usr/bin/rm -f "$minecraft_wrapper_tmp"',
        'sudo_file=/etc/sudoers.d/outlaws-inventory',
        'sudo_tmp=$(/usr/bin/mktemp)',
        'if [ -f "$sudo_file" ]; then /usr/bin/cat "$sudo_file" > "$sudo_tmp"; else /usr/bin/printf \'%s\\n\' "# Outlaw\'s Inventory managed permissions" > "$sudo_tmp"; fi',
    ]
    for rule in required_sudo_rules:
        quoted = shlex.quote(rule)
        script_lines.append(f'/usr/bin/grep -qxF {quoted} "$sudo_tmp" || /usr/bin/printf \'%s\\n\' {quoted} >> "$sudo_tmp"')
    script_lines += [
        '/usr/sbin/visudo -cf "$sudo_tmp"',
        'if [ ! -f "$sudo_file" ] || ! /usr/bin/cmp -s "$sudo_tmp" "$sudo_file"; then /usr/bin/install -o root -g root -m 440 "$sudo_tmp" "$sudo_file"; fi',
        '/usr/bin/rm -f "$sudo_tmp"',
        '/usr/sbin/visudo -cf "$sudo_file"',
    ]
    if auth_method == "root" and cleanup_temporary_root:
        script_lines += [
            'if [ -e /etc/ssh/sshd_config.d/99-outlaws-bootstrap.conf ]; then /usr/bin/rm -f /etc/ssh/sshd_config.d/99-outlaws-bootstrap.conf; /usr/bin/systemctl reload ssh || /usr/bin/systemctl restart ssh; fi',
        ]
    script = "\n".join(script_lines)

    client = _ssh_client(profile)
    try:
        connect_kwargs = dict(
            hostname=target, port=int(profile["port"] or 22), username=bootstrap_username.strip(),
            timeout=10, auth_timeout=10, banner_timeout=10, look_for_keys=False, allow_agent=False,
        )
        if bootstrap_password:
            connect_kwargs["password"] = bootstrap_password
        else:
            connect_kwargs["pkey"] = _load_private_key(profile["private_key_path"])
        client.connect(**connect_kwargs)
        if bootstrap_username.strip() == "root":
            command = f"/bin/sh -c {shlex.quote(script)}"
            stdin, stdout, stderr = client.exec_command(command, timeout=120)
        else:
            command = f"sudo -S -p '' /bin/sh -c {shlex.quote(script)}"
            stdin, stdout, stderr = client.exec_command(command, timeout=120)
            stdin.write((sudo_password or bootstrap_password) + "\n")
            stdin.flush()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if code != 0:
            combined = (out + "\n" + err).strip()
            return {"ok": False, "message": combined[-4000:] or f"Remote setup failed with exit code {code}."}
    except paramiko.AuthenticationException:
        return {
            "ok": False,
            "message": "SSH authentication failed. Verify the administrator username and password. For root, password login may be disabled; use the temporary root-access instructions or an existing sudo-enabled account.",
        }
    except paramiko.SSHException as exc:
        return {"ok": False, "message": f"SSH connection failed: {exc}"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        client.close()

    validation = inspect_host_integration(device, profile)
    required = [
        ("SSH key login", "key_login"),
        ("APT available", "apt_available"),
        ("APT update permission", "sudo_update"),
        ("APT upgrade permission", "sudo_upgrade"),
        ("Kernel upgrade permission", "sudo_kernel_upgrade"),
        ("Reboot permission", "sudo_reboot"),
    ]
    if enable_pihole:
        required.extend([
            ("Pi-hole check permission", "sudo_pihole_check"),
            ("Pi-hole update permission", "sudo_pihole_update"),
        ])
    if enable_minecraft:
        required.append(("Minecraft update permission", "sudo_minecraft_update"))
    failed = [label for label, key in required if not bool(validation.get(key))]
    validation["validation_steps"] = [{"label": label, "ok": bool(validation.get(key))} for label, key in required]
    if failed:
        diagnostic = "; ".join(str(item) for item in (validation.get("messages") or []) if item)
        suffix = f" Details: {diagnostic}" if diagnostic else ""
        return {
            "ok": False,
            "message": "Configuration was written, but validation failed: " + ", ".join(failed) + "." + suffix,
            "inspection": validation,
        }
    return {"ok": True, "message": "Host integration configured and validated.", "inspection": validation}

def ensure_managed_host_checks(device: sqlite3.Row, profile_id: int, system_type: str, create_health: bool, create_updates: bool) -> None:
    """Ensure managed rows exist without rewriting already-correct state."""
    target = resolved_target(device["id"], "")
    label = device["display_name"] or device["name"]
    owner_id = require_current_user_id()
    t = now()
    with db() as con:
        if create_health:
            for check_type, suffix in (("ping", "Ping"), ("disk", "Disk usage")):
                existing = con.execute(
                    "SELECT * FROM health_checks WHERE device_id=? AND check_type=? LIMIT 1",
                    (device["id"], check_type),
                ).fetchone()
                check_name = f"{label} — {suffix}"
                if existing:
                    desired = (check_name, target, 1, 0)
                    current = (str(existing["name"] or ""), str(existing["host"] or ""), int(existing["enabled"] or 0), int(existing["maintenance"] or 0))
                    if current != desired:
                        con.execute(
                            """UPDATE health_checks SET name=?, host=?, enabled=1, maintenance=0, updated_at=? WHERE id=?""",
                            (check_name, target, t, existing["id"]),
                        )
                else:
                    con.execute(
                        """INSERT INTO health_checks(
                               device_id,owner_user_id,name,host,check_type,url,
                               interval_minutes,enabled,maintenance,status,created_at,updated_at
                           ) VALUES (?,?,?,?,?,'',10,1,0,'unknown',?,?)""",
                        (device["id"], owner_id, check_name, target, check_type, t, t),
                    )
        if create_updates:
            existing = con.execute("SELECT * FROM update_checks WHERE device_id=? LIMIT 1", (device["id"],)).fetchone()
            if existing:
                desired = (int(profile_id), str(target), str(system_type), 1)
                current = (int(existing["ssh_profile_id"] or 0), str(existing["host"] or ""), str(existing["system_type"] or ""), int(existing["enabled"] or 0))
                if current != desired:
                    con.execute(
                        "UPDATE update_checks SET ssh_profile_id=?, host=?, system_type=?, enabled=1, updated_at=? WHERE id=?",
                        (profile_id, target, system_type, t, existing["id"]),
                    )
            else:
                con.execute(
                    """INSERT INTO update_checks(
                           device_id,owner_user_id,ssh_profile_id,name,host,system_type,
                           minecraft_jar_path,enabled,status,created_at,updated_at
                       ) VALUES (?,?,?,?,?,?,'server.jar',1,'unknown',?,?)""",
                    (device["id"], owner_id, profile_id, label, target, system_type, t, t),
                )


def ensure_managed_pihole_check(device: sqlite3.Row, profile_id: int, enabled: bool) -> None:
    """Apply the desired Pi-hole check state without duplicating or resetting it."""
    existing = fetch_device_application_check(int(device["id"]), "pihole")
    t = now()
    with db() as con:
        if enabled:
            if existing:
                desired = (int(profile_id), 1)
                current = (int(existing["ssh_profile_id"] or 0), int(existing["enabled"] or 0))
                if current != desired:
                    con.execute(
                        "UPDATE application_checks SET ssh_profile_id=?, enabled=1, updated_at=? WHERE id=? AND owner_user_id=?",
                        (profile_id, t, existing["id"], require_current_user_id()),
                    )
            else:
                con.execute(
                    "INSERT INTO application_checks(device_id,owner_user_id,ssh_profile_id,application_type,enabled,status,created_at,updated_at) VALUES (?,?,?,'pihole',1,'unknown',?,?)",
                    (device["id"], require_current_user_id(), profile_id, t, t),
                )
        elif existing and existing["enabled"]:
            con.execute(
                "UPDATE application_checks SET enabled=0, status='unknown', details_json='{}', updated_at=? WHERE id=? AND owner_user_id=?",
                (t, existing["id"], require_current_user_id()),
            )


def ensure_managed_minecraft_check(device: sqlite3.Row, profile_id: int, enabled: bool) -> None:
    existing = fetch_device_application_check(int(device["id"]), "minecraft")
    t = now()
    with db() as con:
        if enabled:
            if existing:
                desired = (int(profile_id), 1)
                current = (int(existing["ssh_profile_id"] or 0), int(existing["enabled"] or 0))
                if current != desired:
                    con.execute("UPDATE application_checks SET ssh_profile_id=?, enabled=1, updated_at=? WHERE id=? AND owner_user_id=?", (profile_id, t, existing["id"], require_current_user_id()))
            else:
                con.execute("INSERT INTO application_checks(device_id,owner_user_id,ssh_profile_id,application_type,minecraft_jar_path,enabled,status,created_at,updated_at) VALUES (?,?,?,'minecraft','',1,'unknown',?,?)", (device["id"], require_current_user_id(), profile_id, t, t))
        elif existing and existing["enabled"]:
            con.execute("UPDATE application_checks SET enabled=0, status='unknown', details_json='{}', updated_at=? WHERE id=? AND owner_user_id=?", (t, existing["id"], require_current_user_id()))


@app.get("/devices/{device_id}/host-integration", response_class=HTMLResponse)
def host_integration_page(request: Request, device_id: int, return_to: str = ""):
    device = fetch_device(device_id)
    if not device:
        return RedirectResponse("/devices", status_code=303)
    dedicated_profile = ensure_system_check_profile()
    profiles = [dedicated_profile]
    # Bootstrap credentials are only used to provision the host. Runtime checks
    # use the System Checks key with the existing (or newly-created) outlaw account.
    selected_id = int(dedicated_profile["id"])
    profile = dedicated_profile
    inspection = inspect_host_integration(device, profile) if profile and device["managed_host"] else None
    if device["managed_host"] and profile:
        validation = managed_host_validation(device, profile)
        store_managed_host_validation(device_id, validation)
        device = fetch_device(device_id)
    details = {}
    try:
        details = json.loads(device["integration_details"] or "{}")
    except (TypeError, json.JSONDecodeError):
        details = {}
    reconfigure = request.query_params.get("reconfigure") == "1" or return_to in ("device", "system-checks")
    health = fetch_device_health_check(device_id)
    update = fetch_device_update_check(device_id)
    pihole = fetch_device_application_check(device_id, "pihole")
    minecraft = fetch_device_application_check(device_id, "minecraft")
    setup_checks = {
        "health": bool(health and health["enabled"]) if reconfigure else True,
        "updates": bool(update and update["enabled"]) if reconfigure else True,
        "pihole": bool(pihole and pihole["enabled"]),
        "minecraft": bool(minecraft and minecraft["enabled"]),
    }
    return templates.TemplateResponse("host_integration.html", page_context(
        request, "devices", device=device, profiles=profiles, selected_profile_id=selected_id,
        inspection=inspection, integration_details=details, result="", return_to=return_to, setup_checks=setup_checks,
    ))


@app.post("/devices/{device_id}/host-integration")
def configure_host_integration(
    request: Request, device_id: int, ssh_profile_id: int = Form(0), system_type: str = Form("debian"),
    bootstrap_username: str = Form(...), bootstrap_password: str = Form(""), sudo_password: str = Form(""),
    locale_name: str = Form("en_US.UTF-8"), timezone_name: str = Form("Europe/Amsterdam"),
    auth_method: str = Form("admin"), cleanup_temporary_root: Optional[str] = Form(None), return_to: str = Form(""), configure_locale_timezone: Optional[str] = Form(None),
    create_health: Optional[str] = Form(None), create_updates: Optional[str] = Form(None), create_pihole: Optional[str] = Form(None), create_minecraft: Optional[str] = Form(None),
):
    device = fetch_device(device_id)
    # Runtime checks use the managed System Checks key as the outlaw account.
    # The administrator/root credentials submitted below are bootstrap-only.
    profile = ensure_system_check_profile()
    ssh_profile_id = int(profile["id"]) if profile else 0
    if not device or not profile:
        return RedirectResponse(f"/devices/{device_id}", status_code=303)
    result = configure_remote_host(device, profile, bootstrap_username, bootstrap_password, sudo_password, locale_name if configure_locale_timezone else "", timezone_name if configure_locale_timezone else "", auth_method, bool(cleanup_temporary_root), bool(create_pihole), bool(create_minecraft))
    status = "ready" if result.get("ok") else "failed"
    message = str(result.get("message", ""))
    with db() as con:
        if result.get("ok"):
            con.execute("UPDATE devices SET managed_host=1, managed_ssh_profile_id=?, managed_system_type=?, integration_status=?, integration_checked_at=?, integration_message=?, updated_at=? WHERE id=?", (ssh_profile_id, system_type, status, now(), message, now(), device_id))
        else:
            # A failed reconfigure must never replace a previously working runtime profile.
            con.execute("UPDATE devices SET integration_status=?, integration_checked_at=?, integration_message=?, updated_at=? WHERE id=?", (status, now(), message, now(), device_id))
    if result.get("ok"):
        device = fetch_device(device_id)
        ensure_managed_host_checks(device, ssh_profile_id, system_type, bool(create_health), bool(create_updates))
        ensure_managed_pihole_check(device, ssh_profile_id, bool(create_pihole))
        ensure_managed_minecraft_check(device, ssh_profile_id, bool(create_minecraft))
        for health in fetch_health_checks():
            if int(health["device_id"] or 0) == int(device_id):
                execute_health_check(health)
        update = fetch_device_update_check(device_id)
        if update and update["enabled"]:
            execute_update_check(update)
        pihole = fetch_device_application_check(device_id, "pihole")
        if pihole and pihole["enabled"]:
            execute_application_check(pihole)
        minecraft = fetch_device_application_check(device_id, "minecraft")
        if minecraft and minecraft["enabled"]:
            execute_application_check(minecraft)
        refreshed = fetch_device(device_id)
        validation = managed_host_validation(refreshed, profile)
        store_managed_host_validation(device_id, validation)
    refreshed = fetch_device(device_id)
    if result.get("ok") and return_to == "first-run":
        return RedirectResponse(f"/first-run/item-saved?device_id={device_id}&item_type=server&configured=1", status_code=303)
    if result.get("ok") and return_to == "system-checks":
        return RedirectResponse(f"/system-checks/{device_id}", status_code=303)
    if result.get("ok") and return_to == "device":
        return RedirectResponse(f"/devices/{device_id}", status_code=303)
    inspection = result.get("inspection") or inspect_host_integration(refreshed, profile)
    try:
        details = json.loads(refreshed["integration_details"] or "{}")
    except (TypeError, json.JSONDecodeError):
        details = {}
    return templates.TemplateResponse("host_integration.html", page_context(
        request, "devices", device=refreshed, profiles=fetch_ssh_profiles(), selected_profile_id=ssh_profile_id,
        inspection=inspection, integration_details=details, result=status, return_to=return_to,
        setup_checks={"health": bool(create_health), "updates": bool(create_updates), "pihole": bool(create_pihole)},
    ))


@app.get("/devices/{device_id}/host-integration/validate", include_in_schema=False)
def validate_host_integration_refresh(device_id: int):
    return RedirectResponse(f"/devices/{device_id}/host-integration", status_code=303)

@app.post("/devices/{device_id}/host-integration/validate")
def validate_host_integration(device_id: int):
    device = fetch_device(device_id)
    if not device or not device["managed_host"]:
        return RedirectResponse(f"/devices/{device_id}", status_code=303)
    validation = managed_host_validation(device)
    store_managed_host_validation(device_id, validation)
    health = fetch_device_health_check(device_id)
    if health:
        execute_health_check(health)
    return RedirectResponse(f"/devices/{device_id}/host-integration?validated=1", status_code=303)


@app.post("/settings/ssh-profiles")
def add_ssh_profile(
    name: str = Form(...), username: str = Form("outlaw"), port: int = Form(22),
    private_key_path: str = Form(""), known_host_fingerprint: str = Form(""),
):
    requested = Path((private_key_path or "").strip()).name
    key_path = (KEY_DIR / requested).resolve() if requested else None
    if not key_path or key_path.parent != KEY_DIR.resolve() or not key_path.is_file():
        return RedirectResponse("/settings?ssh_error=key", status_code=303)
    try:
        key_path.chmod(0o600)
    except Exception:
        pass
    with db() as con:
        con.execute(
            """INSERT INTO ssh_profiles(owner_user_id, name, username, port, private_key_path, known_host_fingerprint, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(owner_user_id,name) DO UPDATE SET username=excluded.username, port=excluded.port,
               private_key_path=excluded.private_key_path, known_host_fingerprint=excluded.known_host_fingerprint, updated_at=excluded.updated_at""",
            (require_current_user_id(), name.strip(), username.strip(), int(port or 22), str(key_path), known_host_fingerprint.strip(), now(), now()),
        )
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/ssh-profiles/{profile_id}/delete")
def delete_ssh_profile(profile_id: int):
    with db() as con:
        used = con.execute("SELECT COUNT(*) FROM update_checks WHERE ssh_profile_id=?", (profile_id,)).fetchone()[0]
        if not used:
            con.execute("DELETE FROM ssh_profiles WHERE id=? AND owner_user_id=?", (profile_id, require_current_user_id()))
    return RedirectResponse("/settings", status_code=303)


@app.get("/updates", response_class=HTMLResponse)
def updates_page(request: Request):
    return RedirectResponse("/system-checks", status_code=303)


@app.get("/updates/new", response_class=HTMLResponse)
def new_update_check(request: Request):
    return RedirectResponse("/system-checks", status_code=303)


@app.post("/updates")
def create_update_check(
    name: str = Form(...), device_id: int = Form(0), host: str = Form(""), system_type: str = Form("debian"),
    ssh_profile_id: int = Form(...), minecraft_jar_path: str = Form("server.jar"), enabled: Optional[str] = Form(None),
):
    t = now()
    with db() as con:
        cur = con.execute(
            """INSERT INTO update_checks(device_id, owner_user_id, ssh_profile_id, name, host, system_type, minecraft_jar_path, enabled, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unknown', ?, ?)""",
            (device_id or None, require_current_user_id(), ssh_profile_id, name.strip(), resolved_target(device_id or None, host), system_type, minecraft_jar_path.strip() or "server.jar", 1 if enabled else 0, t, t),
        )
        check_id = cur.lastrowid
    return RedirectResponse(f"/system-checks/{device_id}" if device_id else "/system-checks", status_code=303)


def execute_all_update_checks() -> dict[str, int]:
    """Run enabled checks concurrently and isolate unexpected per-target failures."""
    checks = [
        check for check in fetch_update_checks()
        if check["enabled"] and not _device_system_checks_maintenance(check["device_id"], check["owner_user_id"])
    ]
    counts = {"checked": 0, "failed": 0}
    if not checks:
        return counts
    workers = min(4, len(checks))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="update-check") as pool:
        futures = {pool.submit(execute_update_check, check): check for check in checks}
        for future in as_completed(futures):
            check = futures[future]
            counts["checked"] += 1
            try:
                future.result()
            except Exception as exc:
                counts["failed"] += 1
                with db() as con:
                    con.execute(
                        "UPDATE update_checks SET status='failed', package_count=0, packages_json='[]', last_checked=?, last_error=?, updated_at=? WHERE id=?",
                        (now(), f"Unexpected update-check error: {exc}", now(), check["id"]),
                    )
    return counts


@app.get("/updates/check-all", include_in_schema=False)
@app.get("/updates/check-all/", include_in_schema=False)
def updates_check_all_refresh():
    return RedirectResponse("/system-checks", status_code=303)

@app.post("/updates/check-all")
@app.post("/updates/check-all/", include_in_schema=False)
def check_updates_all():
    """Run all enabled update checks; keep this static route before dynamic routes."""
    result = execute_all_update_checks()
    dispatch_notifications()
    return RedirectResponse(
        f"/updates?checked={result['checked']}&failed={result['failed']}", status_code=303
    )


@app.get("/updates/{check_id}", response_class=HTMLResponse)
def edit_update_check(request: Request, check_id: int):
    return RedirectResponse("/system-checks", status_code=303)


@app.post("/updates/{check_id}")
def update_update_check(
    check_id: int, name: str = Form(...), device_id: int = Form(0), host: str = Form(""), system_type: str = Form("debian"),
    ssh_profile_id: int = Form(...), minecraft_jar_path: str = Form("server.jar"), enabled: Optional[str] = Form(None),
):
    with db() as con:
        con.execute(
            """UPDATE update_checks SET device_id=?, owner_user_id=?, ssh_profile_id=?, name=?, host=?, system_type=?, minecraft_jar_path=?, enabled=?, status='unknown', updated_at=? WHERE id=? AND owner_user_id=?""",
            (device_id or None, require_current_user_id(), ssh_profile_id, name.strip(), resolved_target(device_id or None, host), system_type, minecraft_jar_path.strip() or "server.jar", 1 if enabled else 0, now(), check_id, require_current_user_id()),
        )
    return RedirectResponse(f"/system-checks/{device_id}" if device_id else "/system-checks", status_code=303)


@app.get("/updates/{check_id}/check", include_in_schema=False)
@app.get("/updates/{check_id}/upgrade", include_in_schema=False)
@app.get("/updates/{check_id}/reboot", include_in_schema=False)
def legacy_update_action_refresh(check_id: int):
    check = fetch_update_check(check_id)
    device_id = int(check["device_id"] or 0) if check else 0
    return RedirectResponse(f"/system-checks/{device_id}" if device_id else "/system-checks", status_code=303)

@app.post("/updates/{check_id}/check")
def check_updates_one(check_id: int):
    check = fetch_update_check(check_id)
    device_id = int(check["device_id"] or 0) if check else 0
    if check and check["enabled"]:
        execute_update_check(check)
        dispatch_notifications()
    return RedirectResponse(f"/system-checks/{device_id}" if device_id else "/system-checks", status_code=303)


@app.post("/updates/{check_id}/upgrade")
def upgrade_updates_one(check_id: int):
    check = fetch_update_check(check_id)
    if not check or not check["enabled"] or check["status"] != "available":
        return RedirectResponse("/system-checks", status_code=303)
    execute_apt_upgrade(check)
    refreshed = fetch_update_check(check_id)
    result = "success" if refreshed and refreshed["upgrade_status"] == "success" else "failed"
    return RedirectResponse("/system-checks", status_code=303)


@app.post("/updates/{check_id}/reboot")
def reboot_update_host(check_id: int):
    check = fetch_update_check(check_id)
    if not check or not check["enabled"] or not check["reboot_required"]:
        return RedirectResponse("/system-checks", status_code=303)
    result = execute_remote_reboot(check)
    return RedirectResponse("/system-checks", status_code=303)


@app.post("/updates/{check_id}/delete")
def delete_update_check(check_id: int):
    with db() as con:
        con.execute("DELETE FROM update_checks WHERE id=? AND owner_user_id=?", (check_id, require_current_user_id()))
    return RedirectResponse("/system-checks", status_code=303)


def changelog_entries() -> list[dict[str, object]]:
    """Return all changelog releases as structured, display-safe data."""
    changelog = BASE_DIR / "CHANGELOG.md"
    if not changelog.is_file():
        return []
    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    section = ""
    for raw_line in changelog.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            if current:
                entries.append(current)
            heading = line[3:].strip()
            parts = [part.strip() for part in re.split(r"\s+[—-]\s+", heading, maxsplit=2)]
            version = parts[0] if parts else heading
            date = ""
            summary = ""
            for part in parts[1:]:
                if re.fullmatch(r"\d{2}-\d{2}-\d{4}", part):
                    date = part
                elif not summary:
                    summary = part
            current = {"title": heading, "version": version, "date": date, "summary": summary, "sections": []}
            section = ""
        elif current and line.startswith("### "):
            section = line[4:].strip()
            current["sections"].append({"title": section, "items": []})
        elif current and line.startswith("- "):
            sections = current["sections"]
            if not sections:
                sections.append({"title": "", "items": []})
            sections[-1]["items"].append(line[2:].strip())
        elif current and line and not line.startswith("#"):
            sections = current["sections"]
            if not sections:
                sections.append({"title": "", "items": []})
            sections[-1]["items"].append(line)
    if current:
        entries.append(current)
    return entries


@app.get("/release-notes", response_class=HTMLResponse)
def release_notes(request: Request):
    return templates.TemplateResponse(
        "release_notes.html",
        page_context(request, "release_notes", release_entries=changelog_entries()),
    )
