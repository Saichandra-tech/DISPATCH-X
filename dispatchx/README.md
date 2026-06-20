# DispatchX — Parametric Insurance Platform

> Full-stack parametric insurance for gig delivery workers.  
> Auto-payouts triggered by weather/AQI/zone events. AI-powered fraud detection.

---

## Tech Stack

| Layer       | Technology               |
|-------------|--------------------------|
| Backend     | Python 3.10+ · Django 4.2 |
| Database    | SQLite (via Django ORM)  |
| Frontend    | HTML5 · CSS3 · Vanilla JS |
| AI Engine   | Pure Python (no ML deps) |
| Auth        | Django's custom user model |

---

## Project Structure

```
dispatchx/
├── manage.py
├── requirements.txt
│
├── dispatchx/               # Django project config
│   ├── settings.py          # All settings (SQLite, static, auth)
│   ├── urls.py              # Root URL routing
│   └── wsgi.py
│
├── insurance/               # Main Django app
│   ├── models.py            # 8 database models (schema below)
│   ├── views.py             # All page + API views
│   ├── urls.py              # App-level URL patterns
│   ├── admin.py             # Django admin registrations
│   ├── ai_engine.py         # AI fraud detection & risk scoring
│   └── management/
│       └── commands/
│           └── seed_data.py # Database seeder
│
├── static/
│   ├── css/main.css         # Full dark-theme UI stylesheet
│   └── js/main.js           # Client-side logic (graph, simulator, actions)
│
└── templates/
    └── insurance/
        ├── base.html        # Layout with sidebar + ticker
        ├── login.html
        ├── signup.html
        ├── dashboard.html   # Main partner dashboard
        ├── subscription.html
        ├── payouts.html
        ├── admin_panel.html # Full admin with 6 tabs
        └── user_detail.html
```

---

## Database Schema (SQLite via Django ORM)

```
DeliveryPartner     — Custom user: phone auth, risk/fraud scores, GPS data
InsurancePlan       — 3 tiers: Basic/Storm/Total (₹20/₹35/₹50)
Subscription        — Active weekly subscription per partner
ParametricEvent     — Rain/AQI/Curfew/Cyclone triggers with zone + value
Payout              — Released/Delayed/Blocked payout per partner per event
GPSLog              — GPS point log with anomaly flags
FraudAlert          — Multi-user fraud alerts with severity levels
AdminActionLog      — Audit trail of all admin actions
```

---

## Quick Start

```bash
# 1. Install Django
pip install -r requirements.txt

# 2. Run migrations (creates db.sqlite3)
python manage.py migrate

# 3. Seed demo data (partners, plans, events, payouts, fraud alerts)
python manage.py seed_data

# 4. Start the server
python manage.py runserver
```

Open http://127.0.0.1:8000

---

## Login Credentials

| Role    | Phone      | Password  |
|---------|------------|-----------|
| Partner | 9876543210 | demo123   |
| Admin   | 9000000000 | admin123  |

---

## Pages & Routes

| URL                     | Page                        | Access  |
|-------------------------|-----------------------------|---------|
| `/`                     | → Dashboard redirect        | Auth    |
| `/login/`               | Login page                  | Public  |
| `/signup/`              | Signup page                 | Public  |
| `/dashboard/`           | Partner dashboard           | Auth    |
| `/subscription/`        | Plan selection              | Auth    |
| `/payouts/`             | Payout history              | Auth    |
| `/admin-panel/`         | Admin panel (6 tabs)        | Admin   |
| `/admin-panel/user/<id>/` | User detail + actions     | Admin   |
| `/api/risk-score/`      | JSON: partner's risk score  | Auth    |
| `/api/admin/action/<id>/` | POST: take admin action   | Admin   |
| `/api/admin/trigger-event/` | POST: fire parametric event | Admin |
| `/api/admin/fraud-graph/`   | JSON: graph data          | Admin   |

---

## AI Engine — `insurance/ai_engine.py`

### Risk Score Formula
```
RiskScore = 0.30 × SpeedScore
          + 0.30 × (1 - BehaviorScore)
          + 0.20 × NetworkRisk
          + 0.20 × GraphScore
```

### Decision Thresholds
| Score Range | Decision   | Action                     |
|-------------|------------|----------------------------|
| 0.00–0.35   | ALLOW      | Payout released immediately |
| 0.35–0.55   | MONITOR    | Payout released, flagged    |
| 0.55–0.75   | OTP_VERIFY | Payout held for OTP         |
| 0.75+       | BLOCK      | Payout blocked, admin alert |

### Fraud Signals Detected
- **GPS Teleportation** — >20km jump in <5 minutes
- **Overspeed** — speed >100 km/h between GPS points
- **Static Spoofing** — GPS points suspiciously static (std dev < 0.05km)
- **Shared IP Cluster** — same IP across ≥2 accounts
- **Shared Device Ring** — same device ID across ≥2 accounts
- **Graph Ring Detection** — BFS connected components across fraud graph

### Parametric Triggers
| Event   | Threshold     | Plan Required |
|---------|---------------|---------------|
| Rain    | >50 mm/hr     | All plans     |
| AQI     | >300 index    | Storm Guard+  |
| Curfew  | Active zone   | Total Defense |
| Cyclone | Alert issued  | Total Defense |

---

## API Examples

### Trigger a parametric event (Admin)
```bash
curl -X POST http://127.0.0.1:8000/api/admin/trigger-event/ \
  -H "Content-Type: application/json" \
  -H "X-CSRFToken: <token>" \
  -d '{"event_type": "rain", "zone": "hyderabad_central", "value": 75}'
```

Response:
```json
{
  "ok": true,
  "event_id": 6,
  "payouts_created": 14,
  "total_amount": 4200.0
}
```

### Take admin action on a user
```bash
curl -X POST http://127.0.0.1:8000/api/admin/action/5/ \
  -H "Content-Type: application/json" \
  -d '{"action": "block", "notes": "GPS teleportation confirmed"}'
```

### Get fraud graph data
```bash
curl http://127.0.0.1:8000/api/admin/fraud-graph/
```

Response includes `nodes`, `edges`, and `clusters` arrays for visualization.

---

## Admin Panel Tabs

1. **🚨 Fraud Alerts** — Live unresolved alerts with Investigate/Block/Resolve actions
2. **👥 User Monitor** — Searchable table with risk scores, GPS speed, anomaly counts
3. **🕸 Fraud Network** — SVG graph: shared IP (red) + shared device (yellow dashed) edges
4. **📊 Risk Heatmap** — Zone-level risk visualization across Hyderabad
5. **⚡ Trigger Event** — Simulate parametric events + live AI simulator with sliders
6. **📋 Action Log** — Full audit trail of admin actions

---

## Fairness & Progressive Actions

DispatchX never blocks on a single anomaly. The system follows:

1. **Monitor** — Log and track, payout proceeds
2. **OTP Verify** — Delay payout, require SMS confirmation
3. **Delay** — Hold payout pending investigation
4. **Block** — Freeze payout and account, alert admin

GPS drift is allowed. Pattern-based detection requires multiple signals
across multiple sessions before escalating.

---

## Market Crash / Fraud Ring Survival

When mass fake accounts attempt to collect payouts simultaneously:

- Graph-based ring detection identifies clusters via shared IP/device
- Synchronized payout timing flags burst claims
- Critical-risk accounts are auto-blocked before payout release
- Admin gets real-time fraud alerts for manual review
- Progressive action system prevents legitimate users from being caught in sweeps
