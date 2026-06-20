from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
import json


# ─────────────────────────────────────────────
# CUSTOM USER MANAGER
# ─────────────────────────────────────────────
class DeliveryPartnerManager(BaseUserManager):
    def create_user(self, phone, name, password=None, **extra_fields):
        if not phone:
            raise ValueError('Phone number is required')
        user = self.model(phone=phone, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, name, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_admin', True)
        return self.create_user(phone, name, password, **extra_fields)


# ─────────────────────────────────────────────
# DELIVERY PARTNER (Custom User)
# ─────────────────────────────────────────────
class DeliveryPartner(AbstractBaseUser, PermissionsMixin):
    RISK_CHOICES = [
        ('low',      'Low'),
        ('medium',   'Medium'),
        ('high',     'High'),
        ('critical', 'Critical'),
    ]
    ZONE_CHOICES = [
        ('hyderabad_central', 'Hyderabad Central'),
        ('banjara_hills',     'Banjara Hills'),
        ('jubilee_hills',     'Jubilee Hills'),
        ('secunderabad',      'Secunderabad'),
        ('hitec_city',        'HITEC City'),
        ('gachibowli',        'Gachibowli'),
        ('lb_nagar',          'LB Nagar'),
        ('kukatpally',        'Kukatpally'),
    ]

    # Identity
    name        = models.CharField(max_length=100)
    phone       = models.CharField(max_length=15, unique=True)
    email       = models.EmailField(blank=True, null=True)
    zone        = models.CharField(max_length=30, choices=ZONE_CHOICES, default='hyderabad_central')
    joined_date = models.DateTimeField(default=timezone.now)

    # Auth
    is_active    = models.BooleanField(default=True)
    is_staff     = models.BooleanField(default=False)
    is_admin     = models.BooleanField(default=False)

    # Risk & Fraud
    risk_level      = models.CharField(max_length=10, choices=RISK_CHOICES, default='low')
    fraud_score     = models.FloatField(default=0.0)          # 0.0 – 1.0
    risk_score      = models.FloatField(default=0.0)          # composite
    behavior_score  = models.FloatField(default=1.0)          # 0.0 – 1.0
    gps_anomalies   = models.IntegerField(default=0)
    max_speed_kmh   = models.FloatField(default=30.0)         # recorded max speed
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    device_id       = models.CharField(max_length=50, blank=True)

    # Earnings
    avg_daily_earnings = models.FloatField(default=600.0)
    deliveries_per_day = models.IntegerField(default=8)

    USERNAME_FIELD  = 'phone'
    REQUIRED_FIELDS = ['name']

    objects = DeliveryPartnerManager()

    class Meta:
        db_table = 'delivery_partners'
        verbose_name = 'Delivery Partner'

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def risk_color(self):
        return {'low':'#10b981','medium':'#f59e0b','high':'#ef4444','critical':'#f87171'}.get(self.risk_level,'#6b7280')

    @property
    def active_subscription(self):
        return (self.subscriptions
                .filter(status='active', end_date__gte=timezone.now())
                .select_related('plan')
                .order_by('-end_date')
                .first())

    def compute_risk_score(self):
        """RiskScore = 0.30*SpeedScore + 0.30*(1-BehaviorScore) + 0.20*NetworkRisk + 0.20*GraphScore"""
        speed_score    = min(self.max_speed_kmh / 120.0, 1.0)
        behavior_risk  = 1.0 - self.behavior_score
        network_risk   = min(self.fraud_score, 1.0)
        graph_score    = min(self.gps_anomalies / 10.0, 1.0)
        score = (0.30 * speed_score + 0.30 * behavior_risk +
                 0.20 * network_risk + 0.20 * graph_score)
        self.risk_score = round(score, 3)
        if score < 0.35:
            self.risk_level = 'low'
        elif score < 0.55:
            self.risk_level = 'medium'
        elif score < 0.75:
            self.risk_level = 'high'
        else:
            self.risk_level = 'critical'
        self.save(update_fields=['risk_score', 'risk_level'])
        return self.risk_score


# ─────────────────────────────────────────────
# INSURANCE PLAN
# ─────────────────────────────────────────────
class InsurancePlan(models.Model):
    TIER_CHOICES = [('low','Low'),('medium','Medium'),('high','High')]
    tier             = models.CharField(max_length=10, choices=TIER_CHOICES, unique=True)
    name             = models.CharField(max_length=50)
    weekly_premium   = models.DecimalField(max_digits=6, decimal_places=2)
    daily_coverage   = models.DecimalField(max_digits=8, decimal_places=2)
    description      = models.TextField()
    covers_rain      = models.BooleanField(default=True)
    covers_aqi       = models.BooleanField(default=False)
    covers_curfew    = models.BooleanField(default=False)
    covers_cyclone   = models.BooleanField(default=False)

    class Meta:
        db_table = 'insurance_plans'

    def __str__(self):
        return f"{self.name} (₹{self.weekly_premium}/week)"


# ─────────────────────────────────────────────
# SUBSCRIPTION
# ─────────────────────────────────────────────
class Subscription(models.Model):
    STATUS_CHOICES = [('active','Active'),('expired','Expired'),('cancelled','Cancelled')]
    partner    = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE, related_name='subscriptions')
    plan       = models.ForeignKey(InsurancePlan, on_delete=models.PROTECT)
    status     = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    start_date = models.DateTimeField(default=timezone.now)
    end_date   = models.DateTimeField()
    premium_paid = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        db_table = 'subscriptions'

    def __str__(self):
        return f"{self.partner.name} – {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        return self.status == 'active' and self.end_date >= timezone.now()


# ─────────────────────────────────────────────
# PARAMETRIC TRIGGER EVENT
# ─────────────────────────────────────────────
class ParametricEvent(models.Model):
    TYPE_CHOICES = [
        ('rain',    'Heavy Rain'),
        ('aqi',     'AQI Spike'),
        ('curfew',  'Zone Curfew'),
        ('cyclone', 'Cyclone Alert'),
        ('flood',   'Flood Warning'),
    ]
    event_type   = models.CharField(max_length=15, choices=TYPE_CHOICES)
    zone         = models.CharField(max_length=30)
    threshold    = models.CharField(max_length=50)   # e.g. ">50mm/hr"
    value        = models.FloatField()                # actual measured value
    triggered    = models.BooleanField(default=True)
    timestamp    = models.DateTimeField(default=timezone.now)
    affected_users = models.IntegerField(default=0)
    total_payout   = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = 'parametric_events'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_event_type_display()} @ {self.zone} ({self.timestamp:%Y-%m-%d %H:%M})"


# ─────────────────────────────────────────────
# PAYOUT
# ─────────────────────────────────────────────
class Payout(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('released',  'Released'),
        ('delayed',   'Delayed'),
        ('blocked',   'Blocked'),
    ]
    partner    = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE, related_name='payouts')
    event      = models.ForeignKey(ParametricEvent, on_delete=models.SET_NULL, null=True)
    amount     = models.DecimalField(max_digits=8, decimal_places=2)
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    reason     = models.TextField(blank=True)          # why delayed/blocked
    created_at = models.DateTimeField(default=timezone.now)
    released_at= models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payouts'
        ordering = ['-created_at']

    def __str__(self):
        return f"₹{self.amount} → {self.partner.name} [{self.status}]"


# ─────────────────────────────────────────────
# GPS LOG (for fraud detection)
# ─────────────────────────────────────────────
class GPSLog(models.Model):
    partner   = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE, related_name='gps_logs')
    latitude  = models.FloatField()
    longitude = models.FloatField()
    speed_kmh = models.FloatField(default=0)
    timestamp = models.DateTimeField(default=timezone.now)
    is_anomaly = models.BooleanField(default=False)
    anomaly_type = models.CharField(max_length=50, blank=True)   # teleportation / overspeed / static

    class Meta:
        db_table = 'gps_logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.partner.name} @ ({self.latitude:.4f},{self.longitude:.4f}) {self.speed_kmh}km/h"


# ─────────────────────────────────────────────
# FRAUD ALERT
# ─────────────────────────────────────────────
class FraudAlert(models.Model):
    SEVERITY_CHOICES = [('low','Low'),('medium','Medium'),('high','High'),('critical','Critical')]
    TYPE_CHOICES = [
        ('gps_teleport',  'GPS Teleportation'),
        ('overspeed',     'Speed Anomaly'),
        ('shared_device', 'Shared Device Ring'),
        ('ip_cluster',    'IP Cluster'),
        ('sync_payout',   'Synchronized Payout'),
        ('static_spoof',  'Static GPS Spoofing'),
    ]
    alert_type   = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity     = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    description  = models.TextField()
    partners     = models.ManyToManyField(DeliveryPartner, related_name='fraud_alerts')
    resolved     = models.BooleanField(default=False)
    created_at   = models.DateTimeField(default=timezone.now)
    resolved_at  = models.DateTimeField(null=True, blank=True)
    admin_notes  = models.TextField(blank=True)

    class Meta:
        db_table = 'fraud_alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity.upper()}] {self.get_alert_type_display()}"


# ─────────────────────────────────────────────
# ADMIN ACTION LOG
# ─────────────────────────────────────────────
class AdminActionLog(models.Model):
    ACTION_CHOICES = [
        ('monitor',       'Set Monitor'),
        ('delay_payout',  'Delay Payout'),
        ('block',         'Block Account'),
        ('unblock',       'Unblock Account'),
        ('resolve_alert', 'Resolve Alert'),
        ('manual_payout', 'Manual Payout'),
    ]
    admin      = models.ForeignKey(DeliveryPartner, on_delete=models.SET_NULL, null=True, related_name='admin_actions')
    partner    = models.ForeignKey(DeliveryPartner, on_delete=models.CASCADE, related_name='received_actions', null=True)
    alert      = models.ForeignKey(FraudAlert, on_delete=models.SET_NULL, null=True, blank=True)
    action     = models.CharField(max_length=20, choices=ACTION_CHOICES)
    notes      = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'admin_action_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.partner} by {self.admin} @ {self.created_at:%H:%M}"
