"""Lese-/Schreibfunktionen fuer Wasserverbrauchsdaten."""

from datetime import datetime, timedelta
from . import get_connection


def insert_messwert(ip, liter_gesamt, zeitstempel=None):
    if zeitstempel is None:
        zeitstempel = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO messwerte (ip, zeitstempel, liter_gesamt) VALUES (?, ?, ?)",
            (ip, zeitstempel, liter_gesamt),
        )
        conn.commit()
    finally:
        conn.close()


def liste_geraete_ips():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT DISTINCT ip FROM messwerte ORDER BY ip").fetchall()
        return [row["ip"] for row in rows]
    finally:
        conn.close()


_TABELLEN = {
    "stunde": ("verbrauch_stunde", "stunde"),
    "tag":    ("verbrauch_tag", "tag"),
    "woche":  ("verbrauch_woche", None),
    "monat":  ("verbrauch_monat", "monat"),
}


def _periode_start(zeitraum, jetzt=None):
    if jetzt is None:
        jetzt = datetime.now()
    if zeitraum == "stunde":
        start = jetzt.replace(minute=0, second=0, microsecond=0)
        label = start.strftime("%Y-%m-%d %H")
    elif zeitraum == "tag":
        start = jetzt.replace(hour=0, minute=0, second=0, microsecond=0)
        label = start.strftime("%Y-%m-%d")
    elif zeitraum == "woche":
        start = (jetzt - timedelta(days=jetzt.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        jahr, kw, _ = jetzt.isocalendar()
        label = f"{jahr}-KW{kw:02d}"
    elif zeitraum == "monat":
        start = jetzt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = jetzt.strftime("%Y-%m")
    else:
        raise ValueError(f"Unbekannter Zeitraum: {zeitraum}")
    return start, label


def _live_wert_aktuelle_periode(ip, zeitraum):
    start, label = _periode_start(zeitraum)
    start_iso = start.isoformat(timespec="seconds")

    conn = get_connection()
    try:
        baseline_row = conn.execute(
            "SELECT MAX(liter_gesamt) AS wert FROM messwerte WHERE ip = ? AND zeitstempel < ?",
            (ip, start_iso),
        ).fetchone()
        baseline = baseline_row["wert"]

        aktuell_row = conn.execute(
            "SELECT MAX(liter_gesamt) AS wert FROM messwerte WHERE ip = ? AND zeitstempel >= ?",
            (ip, start_iso),
        ).fetchone()
        aktuell = aktuell_row["wert"]

        if aktuell is None:
            return None

        if baseline is None:
            erster_row = conn.execute(
                "SELECT MIN(liter_gesamt) AS wert FROM messwerte WHERE ip = ? AND zeitstempel >= ?",
                (ip, start_iso),
            ).fetchone()
            baseline = erster_row["wert"]

        verbrauch = aktuell - baseline
        if verbrauch < 0:
            verbrauch = 0.0
        return {"label": label, "liter": round(verbrauch, 3)}
    finally:
        conn.close()


def hole_verlauf(ip, zeitraum, anzahl=24, live_ergaenzen=True):
    if zeitraum not in _TABELLEN:
        raise ValueError(f"Unbekannter Zeitraum: {zeitraum}")

    conn = get_connection()
    try:
        if zeitraum == "woche":
            rows = conn.execute(
                """
                SELECT jahr, kw, liter_verbrauch FROM verbrauch_woche
                WHERE ip = ? ORDER BY jahr DESC, kw DESC LIMIT ?
                """,
                (ip, anzahl),
            ).fetchall()
            ergebnis = [
                {"label": f"{r['jahr']}-KW{r['kw']:02d}", "liter": r["liter_verbrauch"]}
                for r in rows
            ]
        else:
            tabelle, spalte = _TABELLEN[zeitraum]
            rows = conn.execute(
                f"""
                SELECT {spalte} AS label, liter_verbrauch FROM {tabelle}
                WHERE ip = ? ORDER BY {spalte} DESC LIMIT ?
                """,
                (ip, anzahl),
            ).fetchall()
            ergebnis = [{"label": r["label"], "liter": r["liter_verbrauch"]} for r in rows]

        ergebnis.reverse()
    finally:
        conn.close()

    if live_ergaenzen:
        live = _live_wert_aktuelle_periode(ip, zeitraum)
        if live is not None:
            if ergebnis and ergebnis[-1]["label"] == live["label"]:
                ergebnis[-1] = live
            else:
                ergebnis.append(live)
                if len(ergebnis) > anzahl:
                    ergebnis = ergebnis[1:]

    return ergebnis
