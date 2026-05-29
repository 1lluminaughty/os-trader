# OS-Trader Dashboard

Live-Dashboard für 10 Optionsscheine mit 6-Monats-Charts und Einstiegssignalen (RSI, Bollinger, EMA-Crossover, Nähe 6M-Tief). Datenquelle: ariva.de.

## Setup

```bash
cd /Users/mathias/Downloads/OS_trader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Start

```bash
streamlit run app.py
```

Öffnet `http://localhost:8501`. Auto-Refresh alle 30s.

## Signal-Logik

| Signal | Bedingung |
|---|---|
| **RSI** | 14-Tage-RSI < 30 |
| **BB** | Schlusskurs ≤ unteres Bollinger-Band (20, 2σ) |
| **6M-Tief** | Aktueller Kurs ≤ 5 % über dem 6-Monats-Tief |
| **EMA-X** | 20-Tage-EMA hat 50-Tage-EMA in den letzten 5 Handelstagen von unten gekreuzt |

Grüner Badge = Signal aktiv. **Hinweise, keine Anlageberatung.**

## 24/7 Deployment auf Home-Server (Docker + Tailscale)

### 1. Projekt auf den Server kopieren

Vom Mac aus per `rsync` (ohne venv & Caches):

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' --exclude='.claude' \
  ~/Downloads/OS_trader/ \
  benutzer@192.168.178.42:~/os-trader/
```

Oder per `git push`/`git clone`, falls du das Projekt versionierst.

### 2. Docker auf dem Server (falls nicht vorhanden)

```bash
ssh benutzer@192.168.178.42
# Debian/Ubuntu:
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# Neu einloggen, damit die Gruppe aktiv wird.
```

### 3. Container starten

```bash
cd ~/os-trader
docker compose up -d --build
```

Erster Build dauert ~2 min (Image-Download + pip install). Danach läuft der Container im Hintergrund:

```bash
docker compose ps          # Status (sollte "healthy" zeigen nach ~30s)
docker compose logs -f     # Live-Logs
docker compose restart     # Neustart
docker compose down        # Stoppen
```

Bei `restart: unless-stopped` startet der Container automatisch nach Server-Reboot wieder mit.

### 4. Tailscale für sicheren Zugriff

**Auf dem Server:**
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# → öffnet einen Login-Link, einmalig im Browser bestätigen
tailscale ip -4   # Tailscale-IP merken, z.B. 100.x.y.z
```

**Auf deinem Mac / iPhone / Laptop:**
1. App von [tailscale.com/download](https://tailscale.com/download) installieren
2. Mit demselben Account einloggen
3. Dashboard öffnen unter `http://<tailscale-ip-vom-server>:8501` oder per MagicDNS `http://<server-hostname>:8501`

Damit ist das Dashboard **nur in deinem Tailnet erreichbar** — niemand außer deinen eigenen Geräten kommt dran. Kein Port-Forwarding am Router nötig.

### Updates ausrollen

Nach lokalen Änderungen:
```bash
rsync -av --exclude='.venv' ~/Downloads/OS_trader/ benutzer@192.168.178.42:~/os-trader/
ssh benutzer@192.168.178.42 'cd ~/os-trader && docker compose up -d --build'
```

Der Build cached die requirements-Layer, daher dauert ein Re-Build bei reinen Code-Änderungen <30 s.

## Troubleshooting

- **Leere Charts:** ariva.de blockt evtl. den User-Agent. In `data.py` USER_AGENT anpassen.
- **429 Rate Limit:** Refresh-Intervall in `app.py` von `30_000` auf `60_000` ms erhöhen.
- **Einzelner Schein lädt nicht:** Möglicherweise nicht an EUWAX Stuttgart gelistet. Fallback `boerse_id=12` (Frankfurt) wird automatisch versucht.
