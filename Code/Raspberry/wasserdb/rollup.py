"""Rollup-Job: messwerte -> Stunde/Tag/Woche/Monat, plus Pruning."""

import threading
import time
from datetime import datetime, timedelta

from . import get_connection, ROHDATEN_AUFBEWAHRUNG_TAGE

ROLLUP_INTERVALL_SEK = 300


def _berechne_verbrauch_stunde(conn):
    rows = conn.execute(
        """
        SELECT ip, substr(zeitstempel, 1, 13) AS stunde_roh,
               MIN(liter_gesamt) AS erster, MAX(liter_gesamt) AS letzter
        FROM messwerte GROUP BY ip, stunde_roh ORDER BY ip, stunde_roh
        """
    ).fetchall()

    letzter_wert_je_ip = {}
    for row in rows:
        ip = row["ip"]
        stunde_key = row["stunde_roh"].replace("T", " ")
        vorheriger_wert = letzter_wert_je_ip.get(ip)
        if vorheriger_wert is None:
            verbrauch = row["letzter"] - row["erster"]
        else:
            verbrauch = row["letzter"] - vorheriger_wert
            if verbrauch < 0:
                verbrauch = row["letzter"] - row["erster"]
        if verbrauch < 0:
            verbrauch = 0.0
        conn.execute(
            "INSERT OR REPLACE INTO verbrauch_stunde (ip, stunde, liter_verbrauch) VALUES (?, ?, ?)",
            (ip, stunde_key, round(verbrauch, 3)),
        )
        letzter_wert_je_ip[ip] = row["letzter"]


def _berechne_verbrauch_tag(conn):
    rows = conn.execute(
        "SELECT ip, substr(stunde, 1, 10) AS tag, SUM(liter_verbrauch) AS summe "
        "FROM verbrauch_stunde GROUP BY ip, tag"
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT OR REPLACE INTO verbrauch_tag (ip, tag, liter_verbrauch) VALUES (?, ?, ?)",
            (row["ip"], row["tag"], round(row["summe"], 3)),
        )


def _iso_kalenderwoche(tag_str):
    datum = datetime.strptime(tag_str, "%Y-%m-%d").date()
    iso_jahr, iso_kw, _ = datum.isocalendar()
    return iso_jahr, iso_kw


def _berechne_verbrauch_woche(conn):
    rows = conn.execute("SELECT ip, tag, liter_verbrauch FROM verbrauch_tag").fetchall()
    wochen_summen = {}
    for row in rows:
        jahr, kw = _iso_kalenderwoche(row["tag"])
        key = (row["ip"], jahr, kw)
        wochen_summen[key] = wochen_summen.get(key, 0.0) + row["liter_verbrauch"]
    for (ip, jahr, kw), summe in wochen_summen.items():
        conn.execute(
            "INSERT OR REPLACE INTO verbrauch_woche (ip, jahr, kw, liter_verbrauch) VALUES (?, ?, ?, ?)",
            (ip, jahr, kw, round(summe, 3)),
        )


def _berechne_verbrauch_monat(conn):
    rows = conn.execute(
        "SELECT ip, substr(tag, 1, 7) AS monat, SUM(liter_verbrauch) AS summe "
        "FROM verbrauch_tag GROUP BY ip, monat"
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT OR REPLACE INTO verbrauch_monat (ip, monat, liter_verbrauch) VALUES (?, ?, ?)",
            (row["ip"], row["monat"], round(row["summe"], 3)),
        )


def _raeume_rohdaten_auf(conn):
    grenze = (datetime.now() - timedelta(days=ROHDATEN_AUFBEWAHRUNG_TAGE)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM messwerte WHERE zeitstempel < ?", (grenze,))


def fuehre_rollup_aus():
    conn = get_connection()
    try:
        _berechne_verbrauch_stunde(conn)
        _berechne_verbrauch_tag(conn)
        _berechne_verbrauch_woche(conn)
        _berechne_verbrauch_monat(conn)
        _raeume_rohdaten_auf(conn)
        conn.commit()
    finally:
        conn.close()


def _rollup_schleife():
    while True:
        try:
            fuehre_rollup_aus()
        except Exception as e:
            print(f"[wasserdb.rollup] Fehler beim Rollup: {e}")
        time.sleep(ROLLUP_INTERVALL_SEK)


def starte_rollup_thread():
    thread = threading.Thread(target=_rollup_schleife, daemon=True)
    thread.start()
    print(f"[wasserdb.rollup] Rollup-Thread gestartet (Intervall: {ROLLUP_INTERVALL_SEK}s)")
    return thread
