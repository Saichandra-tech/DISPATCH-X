from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    DeliveryPartner, InsurancePlan, Subscription,
    ParametricEvent, Payout, GPSLog, FraudAlert, AdminActionLog
)


@admin.register(DeliveryPartner)
class DeliveryPartnerAdmin(UserAdmin):
    list_display  = ('name', 'phone', 'zone', 'risk_level', 'fraud_score', 'is_active')
    list_filter   = ('risk_level', 'zone', 'is_active', 'is_admin')
    search_fields = ('name', 'phone')
    ordering      = ('-joined_date',)
    fieldsets = (
        (None,         {'fields': ('phone', 'password')}),
        ('Personal',   {'fields': ('name', 'email', 'zone')}),
        ('Risk & Fraud',{'fields': ('risk_level','fraud_score','risk_score','behavior_score','gps_anomalies','max_speed_kmh','ip_address','device_id')}),
        ('Earnings',   {'fields': ('avg_daily_earnings', 'deliveries_per_day')}),
        ('Permissions',{'fields': ('is_active','is_staff','is_admin','is_superuser','groups','user_permissions')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('phone','name','password1','password2','zone')}),
    )


@admin.register(InsurancePlan)
class InsurancePlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'tier', 'weekly_premium', 'daily_coverage', 'covers_rain', 'covers_aqi', 'covers_curfew')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'plan', 'status', 'start_date', 'end_date')
    list_filter   = ('status',)


@admin.register(ParametricEvent)
class ParametricEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'zone', 'value', 'triggered', 'timestamp', 'affected_users', 'total_payout')
    list_filter  = ('event_type', 'triggered')


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display  = ('partner', 'amount', 'status', 'created_at', 'reason')
    list_filter   = ('status',)
    search_fields = ('partner__name',)


@admin.register(FraudAlert)
class FraudAlertAdmin(admin.ModelAdmin):
    list_display  = ('alert_type', 'severity', 'resolved', 'created_at')
    list_filter   = ('severity', 'resolved', 'alert_type')


@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'admin', 'partner', 'created_at')
    list_filter  = ('action',)


@admin.register(GPSLog)
class GPSLogAdmin(admin.ModelAdmin):
    list_display = ('partner', 'speed_kmh', 'is_anomaly', 'anomaly_type', 'timestamp')
    list_filter  = ('is_anomaly',)
