"""
Management command to seed the database with realistic demo data.
Run: python manage.py seed_data
"""
import random
import os
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from insurance.models import (
    DeliveryPartner, InsurancePlan, Subscription,
    ParametricEvent, Payout, FraudAlert, AdminActionLog
)


NAMES = [
    "Ravi Kumar","Sita Devi","Arjun Singh","Priya Nair","Mohammed Irfan",
    "Lakshmi Rao","Suresh Babu","Anita Sharma","Vijay Reddy","Deepa Pillai",
    "Arun Mehta","Kavitha Krishnan","Santosh Yadav","Nandini Verma","Rajesh Patil",
    "Fatima Sheikh","Kiran Gupta","Uma Shankar","Ganesh Prasad","Meera Iyer",
    "Bhaskar Rao","Sunita Jain","Prakash Nair","Rekha Bose","Dinesh Tiwari",
    "Latha Menon","Sunil Patel","Radha Krishnan","Mohan Lal","Pooja Desai",
]

ZONES = [z[0] for z in DeliveryPartner.ZONE_CHOICES]

# Fraud ring IPs and devices for simulation
FRAUD_IPS    = ['192.168.1.10','192.168.1.11','10.0.0.99']
FRAUD_DEVICES= ['DEV-FRAUD-01','DEV-FRAUD-02']


class Command(BaseCommand):
    help = 'Seed database with demo data for DispatchX'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding DispatchX database...')

        # ── Plans ──────────────────────────────
        plans_data = [
            dict(tier='low',    name='Basic Shield',  weekly_premium=20, daily_coverage=150,
                 description='Essential rain protection for delivery partners.',
                 covers_rain=True,  covers_aqi=False, covers_curfew=False, covers_cyclone=False),
            dict(tier='medium', name='Storm Guard',   weekly_premium=35, daily_coverage=300,
                 description='Weather + AQI protection for medium-risk zones.',
                 covers_rain=True,  covers_aqi=True,  covers_curfew=False, covers_cyclone=False),
            dict(tier='high',   name='Total Defense', weekly_premium=50, daily_coverage=500,
                 description='Full parametric cover including curfews and cyclones.',
                 covers_rain=True,  covers_aqi=True,  covers_curfew=True,  covers_cyclone=True),
        ]
        plans = {}
        for pd in plans_data:
            plan, _ = InsurancePlan.objects.get_or_create(tier=pd['tier'], defaults=pd)
            plans[pd['tier']] = plan
        self.stdout.write(f'  ✓ {len(plans)} plans created')

        # ── Admin user ──────────────────────────
        if not DeliveryPartner.objects.filter(phone='9000000000').exists():
            admin = DeliveryPartner.objects.create_superuser(
                phone='9000000000', name='Admin User', password='admin123'
            )
        else:
            admin = DeliveryPartner.objects.get(phone='9000000000')

        # ── Demo login user ─────────────────────
        if not DeliveryPartner.objects.filter(phone='9876543210').exists():
            demo = DeliveryPartner.objects.create_user(
                phone='9876543210', name='Ravi Kumar', password='demo123',
                zone='hyderabad_central'
            )
            demo.avg_daily_earnings = 650
            demo.deliveries_per_day = 9
            demo.save()
        else:
            demo = DeliveryPartner.objects.get(phone='9876543210')

        # ── Delivery partners ───────────────────
        partners = [demo]
        for i, name in enumerate(NAMES):
            phone = f'70{str(i+1).zfill(8)}'
            if DeliveryPartner.objects.filter(phone=phone).exists():
                partners.append(DeliveryPartner.objects.get(phone=phone))
                continue
            fraud = random.random()
            is_fraud_ring = fraud > 0.80

            p = DeliveryPartner.objects.create_user(
                phone=phone, name=name, password='pass123',
                zone=random.choice(ZONES)
            )
            p.avg_daily_earnings = random.randint(500, 800)
            p.deliveries_per_day = random.randint(5, 15)
            p.fraud_score    = round(fraud, 2)
            p.behavior_score = round(max(0.1, 1.0 - fraud * 0.8), 2)
            p.gps_anomalies  = random.randint(0,10) if fraud > 0.5 else random.randint(0,2)
            p.max_speed_kmh  = random.randint(120,200) if fraud > 0.85 else random.randint(15,80)
            p.ip_address     = random.choice(FRAUD_IPS) if is_fraud_ring else f'10.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}'
            p.device_id      = random.choice(FRAUD_DEVICES) if fraud > 0.88 else f'DEV-{random.randint(10000,99999)}'
            p.compute_risk_score()
            partners.append(p)

        self.stdout.write(f'  ✓ {len(partners)} partners created')

        # ── Subscriptions ───────────────────────
        for p in partners:
            if Subscription.objects.filter(partner=p, status='active').exists():
                continue
            tier = 'low' if p.risk_level in ('low','medium') else 'high'
            Subscription.objects.create(
                partner=p, plan=plans[tier], status='active',
                start_date=timezone.now() - timedelta(days=random.randint(0,6)),
                end_date=timezone.now() + timedelta(days=random.randint(1,7)),
                premium_paid=plans[tier].weekly_premium,
            )

        self.stdout.write(f'  ✓ Subscriptions assigned')

        # ── Parametric Events ───────────────────
        event_configs = [
            ('rain',    'hyderabad_central', '>50mm/hr',  65.0, True),
            ('aqi',     'banjara_hills',     '>300 AQI', 320.0, True),
            ('curfew',  'lb_nagar',          'Active',     1.0, True),
            ('cyclone', 'secunderabad',      'Cat 2',      1.0, True),
            ('rain',    'gachibowli',        '>50mm/hr',  30.0, False),
        ]
        events = []
        for et, zone, thresh, val, trig in event_configs:
            e = ParametricEvent.objects.create(
                event_type=et, zone=zone, threshold=thresh, value=val,
                triggered=trig,
                timestamp=timezone.now() - timedelta(hours=random.randint(1,48)),
                affected_users=random.randint(8,30) if trig else 0,
                total_payout=random.randint(2000,15000) if trig else 0,
            )
            events.append(e)
        self.stdout.write(f'  ✓ {len(events)} parametric events created')

        # ── Payouts ─────────────────────────────
        triggers = ['Heavy Rain','AQI Spike','Zone Curfew','Cyclone Alert','Flood Warning']
        for p in partners[:20]:
            for _ in range(random.randint(0,5)):
                status_choices = ['released','released','released','delayed','blocked'] if p.risk_level in ('high','critical') else ['released','released','released','delayed']
                st = random.choice(status_choices)
                Payout.objects.create(
                    partner=p,
                    event=random.choice(events),
                    amount=round(random.uniform(100, 500), 2),
                    status=st,
                    reason=f'Auto-trigger: {random.choice(triggers)}',
                    created_at=timezone.now() - timedelta(days=random.randint(0,30)),
                    released_at=timezone.now() if st == 'released' else None,
                )

        self.stdout.write(f'  ✓ Payouts generated')

        # ── Fraud Alerts ────────────────────────
        fraud_partners = [p for p in partners if p.risk_level in ('high','critical')][:6]
        if len(fraud_partners) >= 3:
            alert_data = [
                ('gps_teleport',  'critical', '3 accounts teleported 45km in 4 minutes'),
                ('shared_device', 'critical', 'Same device ID across 3 accounts'),
                ('overspeed',     'high',     'Delivery logged at 187 km/h'),
                ('ip_cluster',    'high',     '4 accounts share same IP subnet'),
                ('sync_payout',   'critical', 'Claims submitted within 3 seconds of each other'),
            ]
            for at, sev, desc in alert_data:
                alert = FraudAlert.objects.create(
                    alert_type=at, severity=sev, description=desc,
                    created_at=timezone.now() - timedelta(hours=random.randint(0,12))
                )
                alert.partners.set(random.sample(fraud_partners, min(3, len(fraud_partners))))

        self.stdout.write(f'  ✓ Fraud alerts created')

        self.stdout.write(self.style.SUCCESS("""
✅ DispatchX database seeded successfully!

LOGIN CREDENTIALS:
─────────────────────────────────────
  Demo User:  phone=9876543210  pass=demo123
  Admin:      phone=9000000000  pass=admin123
─────────────────────────────────────
Run: python manage.py runserver
"""))
