"""Firmware provider metadata and inference helpers for Firmware Engine 2.0."""

PROVIDERS = ("Auto", "GitHub", "GL.iNet", "Garmin", "Brother", "Fujifilm", "DJI", "Onkyo", "Generic website", "Manual")

def infer_provider(vendor: str = "", model: str = "", url: str = "") -> str:
    text = f"{vendor} {model}".lower()
    url_l = (url or "").lower()
    if "github.com/" in url_l: return "GitHub"
    if "gl.i" in text or "mt3000" in text: return "GL.iNet"
    if "garmin" in text: return "Garmin"
    if "brother" in text: return "Brother"
    if "fuji" in text: return "Fujifilm"
    if "dji" in text: return "DJI"
    if "onkyo" in text or "tx-nr" in text or "ht-r" in text: return "Onkyo"
    if url_l: return "Generic website"
    return "Auto"
