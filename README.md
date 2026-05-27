# FermentGuard 🍯

**A practical, ready-to-run Streamlit dashboard for monitoring and logging honey-based vinegar fermentation with a submerged generator.**

Built for small-batch producers who want clean data, beautiful trend charts, and zero-friction daily logging — all stored locally in SQLite.

---

## Features

- **Multi-batch tracking** — Run several ferments at once (different honeys, volumes, or experiments)
- **Clean log entry form** — Quick numeric inputs for pH, DO, temperature, aeration + free-text notes
- **Automatic calculations**
  - Estimated acidity progress (% toward target)
  - Optimal range alerts (pH 3.2–4.2, 24–30°C, DO 25–65%, etc.)
- **Interactive Plotly charts** — pH, dissolved oxygen, and temperature over time with optimal bands highlighted
- **CSV export** — One-click full history export per batch for spreadsheets or records
- **Simulation mode** — Instantly inject 8 days of realistic data for testing or demos (no hardware needed)
- **Batch lifecycle** — Mark complete or archive; sidebar overview of all activity
- **Local-first** — Everything lives in `fermentguard.db` (no cloud, no accounts)

---

## Tech Stack

- Python 3.10+
- Streamlit (UI)
- SQLite (embedded database)
- Plotly (interactive charts)
- pandas (data handling)

---

## Quick Start

### 1. Clone / Create the folder

```bash
cd /path/to/your/projects
# (or just create fermentguard/ wherever you like)
```

### 2. Install dependencies

```bash
cd fermentguard
python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

### 3. Run the dashboard

```bash
streamlit run app.py
```

The app will automatically:
- Create `fermentguard.db`
- Seed a realistic demo batch (`HV-2025-03-HoneyClover`) with 8 days of data so you can explore immediately

Then open the browser at the URL Streamlit prints (usually http://localhost:8501).

---

## Typical Daily Workflow

1. Open the dashboard
2. In the sidebar, select the batch you're working on (or create a new one)
3. Fill the **Add Log Entry** form with your refractometer/pH meter readings + notes
4. Watch the trend charts update live
5. If something looks off, the alert banners tell you immediately
6. At the end of a batch, export the CSV for your records and mark it complete

**Pro tip**: Keep the tab open on a small monitor or tablet near your ferment station.

---

## Simulation Mode

Toggle **Simulation Mode** in the sidebar.

Click **🧪 Simulate 8 Days of Data** under the log form to instantly populate a batch with realistic drifting pH, temperature, DO, and aeration values. Perfect for:
- Testing the UI before you have hardware
- Training staff
- Exploring "what if" scenarios

---

## Optimal Ranges (Submerged Generator)

These are the defaults used for alerts and visual bands:

| Parameter         | Optimal Range     | Notes |
|-------------------|-------------------|-------|
| pH                | 3.2 – 4.2         | Target finished ~3.4–3.6 |
| Temperature       | 24 – 30 °C        | 26–28 °C is sweet spot for most acetobacter |
| Dissolved Oxygen  | 25 – 65 %         | High early, can taper later |
| Aeration Rate     | 0.3 – 1.8 L/min   | Depends on vessel size & stone diffuser |

You can adjust these in `utils.py` (`OPTIMAL_RANGES` dict) if your setup or honey type has different needs.

---

## Database Schema (for the curious)

Two tables:

- **batches** — `batch_id`, `start_date`, `description`, `status`, `created_at`
- **measurements** — `id`, `batch_id`, `measured_at`, `pH`, `dissolved_oxygen`, `temperature_C`, `aeration_rate`, `notes`

Foreign key cascade delete is enabled — archiving/deleting a batch cleans its logs.

---

## File Layout

```
fermentguard/
├── app.py              # Main Streamlit application
├── database.py         # All SQLite access (clean separation)
├── utils.py            # Calculations, alerts, simulation generator
├── requirements.txt
├── .gitignore
├── fermentguard.db     # Created on first run (gitignored)
└── README.md
```

The code is intentionally modular so you can later add:
- Hardware integration (Arduino/ESP32 serial or MQTT)
- Titratable acidity calculator
- Photo attachments per log entry
- Email/SMS alerts

---

## Safety & Best Practices

This tool is a **monitoring aid**, not a substitute for:
- Proper titration / acidity testing before bottling
- Sensory evaluation (smell, taste)
- pH meter calibration
- Good sanitation practices

Never rely solely on software for food safety decisions.

---

## Troubleshooting

**Port already in use?**
```bash
streamlit run app.py --server.port 8502
```

**Database locked or weird state?**
Delete `fermentguard.db` (and the `-shm`/`-wal` files) and restart — it will re-seed the demo batch.

**Charts not updating?**
Use the **Refresh Data** button in the sidebar or just hit `R` in the browser.

---

## License & Credits

MIT-style — use freely for your production or hobby ferments.

Built with ❤️ for people who make excellent vinegar.

---

## Future Ideas (pull requests welcome)

- Titratable acidity % estimation from pH + known starting gravity
- Mother health / pellicle scoring
- Multi-stage tracking (alcohol → acetic)
- Dark mode toggle
- Simple mobile PWA manifest

---

**Happy fermenting!** If FermentGuard helps you make better batches, let the community know.
