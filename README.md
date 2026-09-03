# Flight Deal Watcher – Zürich → Rio de Janeiro

Ein automatisierter, 24/7 laufender Preis-Watcher für Premium-Economy-Flüge von
**Zürich (ZRH)** nach **Rio de Janeiro (GIG)** für **2 Erwachsene**. Er sucht,
vergleicht, speichert Preise dauerhaft und benachrichtigt dich per **Telegram**
und **E-Mail**, sobald ein guter Deal auftaucht.

> **Die Software bucht nichts automatisch.** Sie liefert dir ausschliesslich
> einen Buchungs-/Suchlink – die Entscheidung und Buchung triffst immer du selbst.

---

## Inhalt

- [Was die Software macht](#was-die-software-macht)
- [Suchkriterien](#suchkriterien)
- [Architektur](#architektur)
- [Provider-Wahl: warum SerpApi/Google Flights](#provider-wahl-warum-serpapiGoogle-flights)
- [API-Budget & Suchfrequenz](#api-budget--suchfrequenz)
- [Installation (lokal)](#installation-lokal)
- [Secrets einrichten](#secrets-einrichten)
- [Lokale Nutzung](#lokale-nutzung)
- [GitHub Actions (24/7-Betrieb)](#github-actions-247-betrieb)
- [Dashboard](#dashboard)
- [Tests](#tests)
- [Kosten](#kosten)
- [Fehlerbehebung](#fehlerbehebung)
- [Konfiguration ändern](#konfiguration-ändern)
- [Bekannte Grenzen](#bekannte-grenzen)

---

## Was die Software macht

1. Sucht Premium-Economy-Round-Trip-Preise ZRH → GIG für 2 Erwachsene über die
   SerpApi Google-Flights-Engine.
2. Prüft jedes Angebot gegen harte Mindestanforderungen (Preis, Reisezeit,
   Umstiege, Datum, Klasse).
3. Bewertet gültige Angebote mit einer Deal-Klassifikation + Deal Score.
4. Speichert **jede** Preisbeobachtung dauerhaft in SQLite (`data/flights.db`).
5. Erkennt All-Time-Lows und verhindert doppelte Benachrichtigungen.
6. Verschickt Deal-Alarme via Telegram und E-Mail.
7. Aktualisiert ein statisches HTML-Dashboard (`docs/index.html`, geeignet für
   GitHub Pages).
8. Läuft automatisch 1×/Tag über GitHub Actions, manuell jederzeit auslösbar.

## Suchkriterien

| Kriterium | Wert |
|---|---|
| Route | ZRH → GIG, nur diese beiden Flughäfen |
| Passagiere | 2 Erwachsene |
| Klasse | Premium Economy |
| Preisobergrenze | CHF 1'600 pro Person / CHF 3'200 total (Alarmgrenze, nicht Zielpreis) |
| Hinflug-Fenster | 01.12.2026 – 10.12.2026 |
| Rückflug-Fenster | 07.01.2027 – 15.01.2027 |
| Max. Reisezeit | 17h pro Richtung |
| Umstiege | max. 1, kein Self-Transfer |
| Gepäck | 1 Aufgabegepäck pro Person berücksichtigt/verifiziert |

Alle Werte sind zentral in [`src/config.py`](src/config.py) änderbar.

### Deal-Klassifikation (pro Person)

| Preis | Stufe |
|---|---|
| ≤ CHF 1'000 | EXTREMER DEAL |
| 1'001–1'200 | SEHR STARKER DEAL |
| 1'201–1'400 | GUTER DEAL |
| 1'401–1'500 | INTERESSANT |
| 1'501–1'600 | INNERHALB DER OBERGRENZE |
| > 1'600 | kein Alarm |

Zusätzlich wird jedes neue **All-Time-Low** separat hervorgehoben.

### Deal Score (Sortier-Algorithmus)

Hauptsortierung ist immer der **tatsächliche Preis pro Person** (inkl. Gepäck,
falls nicht inkludiert). Als Tie-Breaker zwischen ähnlich teuren Angeboten dient
ein Deal Score (niedriger = besser), der Aufschläge in CHF-Äquivalent addiert:

```
score = preis_pro_person
        + 15 CHF je Umstieg (Hin + Rück)
        + 10 CHF je angefangene Stunde Reisezeit über 16h Referenz (2x8h direkt)
        + 50 CHF, falls Gepäck nicht verifiziert
        − 30 CHF, falls neues All-Time-Low
```

Siehe [`src/deal_engine.py`](src/deal_engine.py) für die vollständige, kommentierte
Implementierung.

## Architektur

```
main.py                    CLI-Einstiegspunkt / Orchestrierung
src/
  config.py                alle Schwellenwerte, zentral, dokumentiert
  models.py                Datenmodelle (FlightOffer, FlightLeg, BaggageInfo)
  providers/
    serpapi_provider.py    SerpApi-Client + Normalisierung -> FlightOffer
  filters.py                harte Mindestanforderungen (Preis, Dauer, Umstiege, ...)
  deal_engine.py            Klassifikation, All-Time-Low, Deal Score, Sortierung
  storage.py                SQLite: Historie, Duplikat-Schutz, Rotation, Run-Log
  notifiers/
    message_formatter.py    einheitlicher Nachrichtentext
    telegram.py              Telegram-Versand + Retry
    email_notifier.py        SMTP-E-Mail-Versand + Retry
  dashboard.py               statischer HTML-Dashboard-Generator
  logging_setup.py           zentrales Logging
tests/                       automatisierte Tests (unittest, keine echten API-Calls)
.github/workflows/watcher.yml  GitHub-Actions-Workflow für 24/7-Betrieb
data/flights.db               Preishistorie (wird versioniert!)
docs/index.html                generiertes Dashboard (für GitHub Pages)
```

Jedes Modul hat genau eine Verantwortung; nur `providers/serpapi_provider.py`
kennt SerpApi-spezifische JSON-Felder – ein Provider-Wechsel würde nur dieses
eine Modul betreffen.

## Provider-Wahl: warum SerpApi/Google Flights

Vor der Implementierung wurden recherchiert: Amadeus Self-Service, SerpApi
Google Flights, Skyscanner/Travelpayouts, Duffel sowie diverse Scraping-Anbieter.

- **Amadeus Self-Service** wurde am **17. Juli 2026** für unabhängige Entwickler
  komplett abgeschaltet (nur noch Enterprise, vertragsgebunden) – keine Option mehr.
- **Skyscanner/Travelpayouts "kostenlose" APIs** liefern i. d. R. nur
  Economy-Bestpreise ohne verlässlichen Kabinenklassen-Filter, Gepäckdaten oder
  Umstiegsdetails – zu ungenau für unsere Kriterien.
- **Web-Scraping-Anbieter** (Apify, ScrapingBee, RapidAPI-Wrapper) wurden bewusst
  ausgeschlossen, da fragil und teils ToS-riskant.
- **Duffel** ist primär eine Buchungs-API (NDC-Content) ohne nennenswerten
  Free-Tier für reines Preis-Monitoring.
- **SerpApi Google-Flights-Engine** liefert als einzige offizielle, ToS-konforme
  Option Premium-Economy-Filter, Gepäckinformationen, Umstiegsdetails,
  Buchungslinks und sogar eine eigene Tiefstpreis-/Historienauswertung
  (`price_insights`) – bei 250 Gratis-Suchen/Monat.

## API-Budget & Suchfrequenz

**Wichtig:** Ein bepreister Round-Trip kostet bei SerpApi **2 API-Calls**
(1. Outbound-Suche → `departure_token`, 2. Return-Suche mit diesem Token).

- Free-Tier: 250 Suchen/Monat
- Datumsmatrix: 10 Hinflug- × 9 Rückflugtage = **90 Kombinationen**
- Gewählte Frequenz: **4 Kombinationen/Tag** × 2 Calls = **8 Calls/Tag** =
  **240 Calls/Monat** (< 250, Sicherheitsmarge eingebaut über `SAFETY_MARGIN`
  in `config.py`)
- Damit wird die volle 90er-Matrix alle **~23 Tage** einmal komplett durchrotiert
  (`storage.get_next_combo_indices`/`advance_rotation`)
- Lauf-Frequenz: **1× täglich** (nicht alle 4–8h, wie ursprünglich als Zielbereich
  genannt – das ist mit dem kostenlosen Tier bei dieser Datumsmatrix schlicht
  nicht möglich, siehe Rechnung oben)

Falls du künftig eine höhere Frequenz oder vollständigere Abdeckung willst,
ist ein Upgrade auf den SerpApi-Starter-Plan (~$25/Monat ≈ CHF 22) mit 1'000
Suchen/Monat die naheliegendste Option – das überschreitet dein genanntes
Budget von CHF 5–10/Monat und wurde daher **nicht** automatisch aktiviert.
Ändere dafür einfach `SERPAPI_API_KEY` auf einen bezahlten Key und passe
`DAILY_COMBINATIONS_TO_CHECK` in `.env`/den GitHub Secrets an.

## Installation (lokal)

```bash
cd flight-deal-watcher
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .env mit echten Werten befüllen, siehe nächster Abschnitt
```

## Secrets einrichten

Alle Secrets kommen ausschliesslich aus `.env` (lokal) bzw. GitHub Secrets
(Produktion) – niemals aus dem Code.

### 1. SerpApi API-Key
- Kostenloser Account: https://serpapi.com/users/sign_up (250 Suchen/Monat gratis)
- Keine Kosten im Rahmen des Free-Tiers.
- Key eintragen in `.env` als `SERPAPI_API_KEY`.

### 2. Telegram
- Öffne Telegram, suche `@BotFather`, sende `/newbot`, folge den Anweisungen →
  du erhältst ein Bot-Token.
- Suche `@userinfobot`, sende ihm eine Nachricht → du erhältst deine `chat_id`.
- Beide Werte in `.env` eintragen (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Test: `python main.py --test-telegram`

### 3. E-Mail (SMTP)
- Empfehlung: bestehendes Gmail-Konto + **App-Passwort** (kein normales
  Passwort, jederzeit widerrufbar): https://myaccount.google.com/apppasswords
- `.env` ausfüllen: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`,
  `SMTP_USER=<deine-adresse>`, `SMTP_PASSWORD=<app-passwort>`,
  `EMAIL_FROM=<deine-adresse>`, `EMAIL_TO=<ziel-adresse>`
- Test: `python main.py --test-email`

## Lokale Nutzung

```bash
python main.py --dry-run         # sucht & zeigt Ergebnis, verschickt nichts
python main.py                   # normaler Lauf (sucht, speichert, benachrichtigt)
python main.py --test-telegram   # nur Telegram-Testnachricht
python main.py --test-email      # nur Test-E-Mail
```

## GitHub Actions (24/7-Betrieb)

1. Repository auf GitHub erstellen und dieses Projekt pushen.
2. Unter **Settings → Secrets and variables → Actions** folgende Secrets anlegen:
   `SERPAPI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SMTP_HOST`,
   `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
3. Unter **Settings → Actions → General → Workflow permissions** "Read and
   write permissions" aktivieren (nötig, damit der Workflow `data/flights.db`
   und `docs/index.html` zurückcommitten darf).
4. Der Workflow [`watcher.yml`](.github/workflows/watcher.yml) läuft danach
   automatisch täglich um 06:00 UTC und lässt sich zusätzlich jederzeit manuell
   über den Tab **Actions → Flight Deal Watcher → Run workflow** auslösen.

## Dashboard

Unter **Settings → Pages** als Quelle "Deploy from a branch", Branch `main`,
Ordner `/docs` auswählen. Danach ist das Dashboard unter
`https://<dein-username>.github.io/<repo-name>/` erreichbar. Es enthält
aktuell günstigsten Flug, Top Deals, Preisverlauf-Diagramm, All-Time-Low und
Status der letzten Suche. Keine Secrets landen im Dashboard-HTML.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

56 automatisierte Tests (Standard-`unittest`, keine externe Testbibliothek
nötig) decken u. a. ab: Preisfilter, CHF-1'600-Grenze pro Person, CHF-3'200
Gesamtgrenze, Premium-Economy-Filter, Datumsfenster, 17h-Grenze, 1-Umstieg-
Grenze, Self-Transfer-Erkennung, Gepäcklogik (inkl. "keine erfundenen Kosten"),
Deal-Klassifikation, All-Time-Low-Erkennung, Duplikat-Verhinderung, sowie die
SerpApi-Normalisierung und Fehlerbehandlung (401/429/5xx, defekte
API-Antworten) – vollständig mit gemockter API, ohne echte SerpApi-Requests zu
verbrauchen.

## Kosten

| Posten | CHF/Monat |
|---|---|
| SerpApi (Free-Tier, 240/250 Suchen genutzt) | 0 |
| GitHub Actions (Public Repo) | 0 |
| GitHub Pages (Dashboard) | 0 |
| Telegram | 0 |
| E-Mail (Gmail SMTP) | 0 |
| **Gesamt** | **CHF 0** |

Ziel CHF 0/Monat ist erreicht. Ein Upgrade auf höhere Suchfrequenz (~CHF 22/Monat)
ist möglich, aber **nicht aktiviert** – siehe Abschnitt "API-Budget & Suchfrequenz".

## Fehlerbehebung

| Problem | Lösung |
|---|---|
| `InvalidApiKeyError` | `SERPAPI_API_KEY` prüfen/neu generieren |
| `RateLimitError` / viele 429 | Free-Tier-Limit erreicht – `DAILY_COMBINATIONS_TO_CHECK` reduzieren oder bis Monatsanfang warten |
| Keine Telegram-Nachricht | `python main.py --test-telegram` ausführen, Bot-Token/Chat-ID prüfen |
| Keine E-Mail | `python main.py --test-email`, App-Passwort statt normalem Passwort verwenden |
| GitHub Action schlägt fehl | Tab "Actions" öffnen, Logs prüfen; bei 3 Fehlläufen in Folge kommt automatisch eine Warn-Benachrichtigung |
| `data/flights.db beschädigt` | Datei löschen, `storage.init_db()` erzeugt sie beim nächsten Lauf neu (Historie geht dabei verloren – ggf. vorher Backup) |

## Konfiguration ändern

Alles Zentrale steht in [`src/config.py`](src/config.py): Preisgrenzen,
Deal-Stufen, Datumsfenster, max. Reisezeit/Umstiege, Gepäckanforderung,
Suchfrequenz. Nach Änderungen: Tests laufen lassen
(`python3 -m unittest discover -s tests`), dann committen.

## Bekannte Grenzen

- Die Trennung von Hin-/Rückflug-Legs aus der SerpApi-Antwort nutzt eine
  robuste, aber heuristische Datums-Zuordnung. Bei API-Änderungen loggt das
  System eine Warnung statt zu crashen und überspringt das betroffene Angebot.
- Gepäckinformationen aus Google Flights sind nicht immer vollständig
  strukturiert; wo unklar, wird explizit "nicht verifiziert" ausgewiesen statt
  Kosten zu erfinden (Punkt 9 der Anforderungen).
- Bei 1×täglicher Suche mit rotierender Teilmatrix kann ein sehr kurzfristiger
  Preissturz bis zu ~23 Tage unentdeckt bleiben, falls er ausgerechnet eine
  gerade nicht geprüfte Datumskombination betrifft. Das ist der bewusste
  Trade-off für CHF 0/Monat – siehe "API-Budget & Suchfrequenz".
