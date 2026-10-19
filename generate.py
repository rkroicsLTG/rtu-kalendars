#!/usr/bin/env python3
"""Nolasa RTU nodarbību grafiku (nodarbibas.rtu.lv) un saglabā to iCalendar (.ics) failā.

Konfigurācija – vides mainīgie (noklusējums: RTU RA, Lāzertehnoloģijas ENML0, 1. kurss, 1. grupa):
  RTU_PROGRAM_ID  – programmas ID nodarbibas.rtu.lv sistēmā (ENML0 = 1939)
  RTU_COURSE      – kurss (1, 2, ...)
  RTU_GROUP       – grupa ("1")
  RTU_OUTPUT      – izvades fails (docs/rtu.ics)
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE = "https://nodarbibas.rtu.lv"
TZ = ZoneInfo("Europe/Riga")

PROGRAM_ID = int(os.environ.get("RTU_PROGRAM_ID", "1939"))
COURSE = int(os.environ.get("RTU_COURSE", "1"))
GROUP = os.environ.get("RTU_GROUP", "1")
OUTPUT = os.environ.get("RTU_OUTPUT", "docs/rtu.ics")
CAL_NAME = os.environ.get("RTU_CAL_NAME", "RTU nodarbības")


def http(path, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{BASE}/{path.lstrip('/')}",
        data=body,
        headers={
            "User-Agent": "rtu-kalendars (personal iCal feed)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    # RTU serveris dažkārt (īpaši naktīs) atbild lēni vai nepieejams – mēģina vairākas reizes
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code < 500:
                raise
            if attempt == 3:
                raise
            wait = 15 * (attempt + 1)
            print(f"{path}: {e} – mēģinu vēlreiz pēc {wait} s", file=sys.stderr)
            time.sleep(wait)


def post_json(path, data):
    return json.loads(http(path, data))


def semester_ids():
    """Semestru ID no sākumlapas izvēlnes (#semester-id)."""
    html = http("/")
    block = re.search(r'id="semester-id".*?</select>', html, re.S)
    return [int(v) for v in re.findall(r'<option[^>]*value="(\d+)"', block.group(0) if block else "")]


def relevant_semesters(now):
    """Semestri, kas vēl nav beigušies (ar 14 dienu rezervi) un sākas tuvāko 6 mēnešu laikā."""
    out = []
    for sid in semester_ids():
        info = post_json("getChousenSemesterStartEndDate", {"semesterId": sid})
        start = dt.datetime.fromtimestamp(info["startDate"] / 1000, TZ)
        ends = [info.get(k) for k in ("endDate", "lessonEndDate", "examEndDate") if info.get(k)]
        end = dt.datetime.fromtimestamp(max(ends) / 1000, TZ)
        if end >= now - dt.timedelta(days=14) and start <= now + dt.timedelta(days=180):
            out.append((sid, info.get("titleLV", str(sid)), start, end))
    return out


def find_semester_program(semester_id):
    groups = post_json(
        "findGroupByCourseId",
        {"courseId": COURSE, "semesterId": semester_id, "programId": PROGRAM_ID},
    )
    for g in groups:
        if str(g.get("group")) == str(GROUP):
            return g["semesterProgramId"]
    return None


def months_between(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_events(sp_id, start, end):
    events = {}
    for y, m in months_between(start, end):
        for e in post_json("getSemesterProgEventList", {"semesterProgramId": sp_id, "year": y, "month": m}):
            events[e["eventDateId"]] = e
    return list(events.values())


# ---------- iCalendar ----------

def esc(s):
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    """RFC 5545: rindas ne garākas par 75 baitiem."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not parts else 74
        if len(cur) + len(b) > limit:
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    "TZID:Europe/Riga",
    "BEGIN:STANDARD",
    "DTSTART:19701025T040000",
    "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
    "TZOFFSETFROM:+0300",
    "TZOFFSETTO:+0200",
    "TZNAME:EET",
    "END:STANDARD",
    "BEGIN:DAYLIGHT",
    "DTSTART:19700329T030000",
    "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
    "TZOFFSETFROM:+0200",
    "TZOFFSETTO:+0300",
    "TZNAME:EEST",
    "END:DAYLIGHT",
    "END:VTIMEZONE",
]


def summary_of(e):
    name = (e.get("eventTempName") or "").strip()
    lect = (e.get("lecturerInfoText") or "").strip()
    if lect and name.endswith(", " + lect):
        name = name[: -len(", " + lect)]
    return name


def vevent(e, stamp):
    day = dt.datetime.fromtimestamp(e["eventDate"] / 1000, TZ).date()
    s, f = e["customStart"], e["customEnd"]
    start = dt.datetime(day.year, day.month, day.day, s["hour"], s["minute"])
    end = dt.datetime(day.year, day.month, day.day, f["hour"], f["minute"])
    room = e.get("room") or {}
    location = room.get("roomName") or e.get("roomInfoText") or ""
    desc = []
    if e.get("lecturerInfoText"):
        desc.append(f"Pasniedzējs: {e['lecturerInfoText']}")
    if e.get("roomInfoText"):
        desc.append(f"Telpa: {e['roomInfoText']}")
    if e.get("programInfoText"):
        desc.append(e["programInfoText"])
    return [
        "BEGIN:VEVENT",
        f"UID:{e['eventDateId']}@nodarbibas.rtu.lv",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID=Europe/Riga:{start:%Y%m%dT%H%M%S}",
        f"DTEND;TZID=Europe/Riga:{end:%Y%m%dT%H%M%S}",
        f"SUMMARY:{esc(summary_of(e))}",
        f"LOCATION:{esc(location)}",
        f"DESCRIPTION:{esc(chr(10).join(desc))}",
        "END:VEVENT",
    ]


def build_ics(events):
    # Fiksēts DTSTAMP, lai fails (un git vēsture) mainītos tikai tad, ja mainās grafiks
    stamp = "20260101T000000Z"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//rtu-kalendars//LV",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(CAL_NAME)}",
        "X-WR-TIMEZONE:Europe/Riga",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
        *VTIMEZONE,
    ]
    for e in sorted(events, key=lambda e: (e["eventDate"], e["customStart"]["hour"], e["customStart"]["minute"], e["eventDateId"])):
        lines += vevent(e, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def main():
    now = dt.datetime.now(TZ)
    all_events = []
    for sid, title, start, end in relevant_semesters(now):
        sp_id = find_semester_program(sid)
        if not sp_id:
            print(f"{title}: grupa {COURSE}. kurss / {GROUP}. grupa nav atrasta", file=sys.stderr)
            continue
        if http("isSemesterProgramPublished", {"semesterProgramId": sp_id}).strip() != "true":
            print(f"{title}: grafiks vēl nav publicēts", file=sys.stderr)
            continue
        ev = fetch_events(sp_id, start, end)
        print(f"{title}: {len(ev)} nodarbības (semesterProgramId={sp_id})")
        all_events += ev
    if not all_events:
        # Neatstāj tukšu kalendāru, ja RTU serveris uz brīdi nestrādā vai nekas nav atrasts
        print("Neviena nodarbība netika saņemta – esošais fails netiek mainīts.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(all_events))
    print(f"Saglabāts: {OUTPUT} ({len(all_events)} notikumi)")


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        if isinstance(e, urllib.error.HTTPError) and e.code < 500:
            raise
        # Īslaicīga RTU servera nepieejamība nav kļūda – esošais kalendārs paliek, nākamā palaišana mēģinās vēlreiz
        print(f"::warning::RTU serveris nav pieejams ({e}); kalendārs šoreiz netika atjaunots.")
        sys.exit(0)
