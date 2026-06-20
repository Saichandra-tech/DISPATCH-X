from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta
import json

from .models import (
    DeliveryPartner, InsurancePlan, Subscription,
    ParametricEvent, Payout, GPSLog, FraudAlert, AdminActionLog
)
from .ai_engine import (
    assess_risk, evaluate_parametric_trigger, decide_payout,
    FraudGraph, GPSPoint
)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def is_admin(user):
    return user.is_authenticated and user.is_admin


def get_active_subscription(partner):
    return partner.active_subscription


def ensure_default_plans():
    if InsurancePlan.objects.exists():
        return
    defaults = [
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
    for pd in defaults:
        InsurancePlan.objects.get_or_create(tier=pd['tier'], defaults=pd)


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        data  = request.POST
        phone = data.get('phone', '').strip()
        name  = data.get('name', '').strip()
        pwd   = data.get('password', '')
        zone  = data.get('zone', 'hyderabad_central')
        if DeliveryPartner.objects.filter(phone=phone).exists():
            return render(request, 'insurance/signup.html', {
                'error': 'Phone number already registered.', 'zones': DeliveryPartner.ZONE_CHOICES
            })
        user = DeliveryPartner.objects.create_user(phone=phone, name=name, password=pwd, zone=zone)
        login(request, user)
        return redirect('dashboard')
    return render(request, 'insurance/signup.html', {'zones': DeliveryPartner.ZONE_CHOICES})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        phone = request.POST.get('phone', '').strip()
        pwd   = request.POST.get('password', '')
        user  = authenticate(request, phone=phone, password=pwd)
        if user:
            login(request, user)
            return redirect(request.GET.get('next', 'dashboard'))
        error = 'Invalid phone number or password.'
    return render(request, 'insurance/login.html', {'error': error})


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@login_required
@ensure_csrf_cookie
def dashboard_view(request):
    partner = request.user
    sub     = get_active_subscription(partner)
    last_gps = partner.gps_logs.first()
    recent_payouts  = partner.payouts.select_related('event').order_by('-created_at')[:5]
    active_events   = ParametricEvent.objects.filter(triggered=True).order_by('-timestamp')[:5]
    total_received  = partner.payouts.filter(status='released').aggregate(t=Sum('amount'))['t'] or 0
    total_blocked   = partner.payouts.filter(status='blocked').count()

    context = {
        'partner':       partner,
        'subscription':  sub,
        'recent_payouts':recent_payouts,
        'active_events': active_events,
        'total_received':total_received,
        'total_blocked': total_blocked,
        'risk_color':    partner.risk_color,
        'last_gps':      last_gps,
    }
    return render(request, 'insurance/dashboard.html', context)


# ─────────────────────────────────────────────
# SUBSCRIPTION
# ─────────────────────────────────────────────
@login_required
def subscription_view(request):
    partner = request.user
    ensure_default_plans()
    plans   = InsurancePlan.objects.all().order_by('weekly_premium')
    sub     = get_active_subscription(partner)
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        plan    = get_object_or_404(InsurancePlan, id=plan_id)
        # Cancel existing
        Subscription.objects.filter(partner=partner, status='active').update(status='cancelled')
        # Create new
        Subscription.objects.create(
            partner      = partner,
            plan         = plan,
            status       = 'active',
            start_date   = timezone.now(),
            end_date     = timezone.now() + timedelta(weeks=1),
            premium_paid = plan.weekly_premium,
        )
        return redirect('dashboard')
    return render(request, 'insurance/subscription.html', {
        'partner': partner, 'plans': plans, 'current_sub': sub
    })


# ─────────────────────────────────────────────
# PAYOUTS
# ─────────────────────────────────────────────
@login_required
def payouts_view(request):
    partner = request.user
    status  = request.GET.get('status', '')
    qs      = partner.payouts.select_related('event').order_by('-created_at')
    if status:
        qs = qs.filter(status=status)
    totals = {
        'released': partner.payouts.filter(status='released').aggregate(t=Sum('amount'))['t'] or 0,
        'delayed':  partner.payouts.filter(status='delayed').aggregate(t=Sum('amount'))['t'] or 0,
        'blocked':  partner.payouts.filter(status='blocked').aggregate(t=Sum('amount'))['t'] or 0,
    }
    return render(request, 'insurance/payouts.html', {
        'partner': partner, 'payouts': qs, 'totals': totals, 'filter_status': status
    })


# ─────────────────────────────────────────────
# ADMIN VIEWS
# ─────────────────────────────────────────────
@login_required
@user_passes_test(is_admin)
def admin_dashboard_view(request):
    users         = DeliveryPartner.objects.all()
    alerts        = FraudAlert.objects.filter(resolved=False).prefetch_related('partners')[:20]
    critical_users= users.filter(risk_level='critical')
    events        = ParametricEvent.objects.order_by('-timestamp')[:10]
    action_log    = AdminActionLog.objects.select_related('admin','partner').order_by('-created_at')[:20]
    payout_stats  = {
        'released': Payout.objects.filter(status='released').aggregate(t=Sum('amount'))['t'] or 0,
        'blocked':  Payout.objects.filter(status='blocked').count(),
        'total':    Payout.objects.count(),
    }
    zone_risks = []
    for zone, label in DeliveryPartner.ZONE_CHOICES:
        zu = users.filter(zone=zone)
        avg = sum(u.risk_score for u in zu) / max(zu.count(), 1)
        zone_risks.append({'zone': label, 'avg_risk': round(avg*100), 'count': zu.count()})

    return render(request, 'insurance/admin_panel.html', {
        'users': users, 'alerts': alerts, 'critical_users': critical_users,
        'events': events, 'action_log': action_log, 'payout_stats': payout_stats,
        'zone_risks': zone_risks,
    })


@login_required
@user_passes_test(is_admin)
def admin_user_detail(request, user_id):
    target  = get_object_or_404(DeliveryPartner, id=user_id)
    payouts = target.payouts.select_related('event').order_by('-created_at')[:10]
    alerts  = target.fraud_alerts.order_by('-created_at')[:5]
    return render(request, 'insurance/user_detail.html', {
        'target': target, 'payouts': payouts, 'alerts': alerts
    })


# ─────────────────────────────────────────────
# API ENDPOINTS (JSON)
# ─────────────────────────────────────────────
@login_required
@user_passes_test(is_admin)
def api_take_action(request, user_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    data   = json.loads(request.body)
    action = data.get('action')
    notes  = data.get('notes', '')
    target = get_object_or_404(DeliveryPartner, id=user_id)
    valid  = ['monitor','delay_payout','block','unblock','resolve_alert','manual_payout']
    if action not in valid:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    if action == 'block':
        target.risk_level = 'critical'
        target.is_active  = False
        target.save(update_fields=['risk_level','is_active'])
        Payout.objects.filter(partner=target, status='pending').update(status='blocked')
    elif action == 'unblock':
        target.is_active = True
        target.save(update_fields=['is_active'])
    elif action == 'delay_payout':
        Payout.objects.filter(partner=target, status='pending').update(status='delayed')
    elif action == 'monitor':
        if target.risk_level not in ('high','critical'):
            target.risk_level = 'medium'
            target.save(update_fields=['risk_level'])

    AdminActionLog.objects.create(
        admin=request.user, partner=target, action=action, notes=notes
    )
    return JsonResponse({'ok': True, 'action': action, 'target': str(target)})


@login_required
@require_POST
def api_update_location(request):
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    lat = data.get('lat')
    lon = data.get('lon')
    if lat is None or lon is None:
        return JsonResponse({'error': 'lat/lon required'}, status=400)

    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'lat/lon invalid'}, status=400)

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return JsonResponse({'error': 'lat/lon out of range'}, status=400)

    speed_kmh = data.get('speed_kmh') or 0
    try:
        speed_kmh = float(speed_kmh)
    except (TypeError, ValueError):
        speed_kmh = 0

    GPSLog.objects.create(
        partner=request.user,
        latitude=lat,
        longitude=lon,
        speed_kmh=max(speed_kmh, 0),
    )

    if speed_kmh > request.user.max_speed_kmh:
        request.user.max_speed_kmh = speed_kmh
        request.user.save(update_fields=['max_speed_kmh'])

    return JsonResponse({
        'ok': True,
        'lat': lat,
        'lon': lon,
        'speed_kmh': round(speed_kmh, 1),
        'timestamp': timezone.now().isoformat(),
    })


@login_required
@user_passes_test(is_admin)
def api_resolve_alert(request, alert_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    alert = get_object_or_404(FraudAlert, id=alert_id)
    alert.resolved    = True
    alert.resolved_at = timezone.now()
    alert.admin_notes = json.loads(request.body).get('notes', '')
    alert.save()
    AdminActionLog.objects.create(
        admin=request.user, alert=alert, action='resolve_alert',
        notes=alert.admin_notes
    )
    return JsonResponse({'ok': True})


@login_required
def api_risk_score(request):
    """Return current risk score for the logged-in partner."""
    p = request.user
    return JsonResponse({
        'risk_score':     p.risk_score,
        'risk_level':     p.risk_level,
        'fraud_score':    p.fraud_score,
        'behavior_score': p.behavior_score,
        'gps_anomalies':  p.gps_anomalies,
        'max_speed':      p.max_speed_kmh,
    })


@login_required
@user_passes_test(is_admin)
def api_trigger_event(request):
    """Simulate a parametric trigger and process payouts for eligible partners."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    data = json.loads(request.body)
    event_type = data.get('event_type', 'rain')
    zone       = data.get('zone', 'hyderabad_central')
    value      = float(data.get('value', 60))

    event = ParametricEvent.objects.create(
        event_type=event_type, zone=zone,
        threshold=f">{value}", value=value, triggered=True,
    )

    plan_key_map = {
        'rain': 'covers_rain', 'aqi': 'covers_aqi',
        'curfew': 'covers_curfew', 'cyclone': 'covers_cyclone', 'flood': 'covers_rain',
    }
    plan_key = plan_key_map.get(event_type, 'covers_rain')

    active_subs = Subscription.objects.filter(
        status='active', end_date__gte=timezone.now(),
        **{f'plan__{plan_key}': True}
    ).select_related('partner','plan')

    payouts_created = 0
    total_amount    = 0

    for sub in active_subs:
        partner  = sub.partner
        plan     = sub.plan
        trig_res = evaluate_parametric_trigger(
            event_type, value,
            {plan_key: getattr(plan, plan_key, False)}
        )
        # Minimal risk assessment for quick check
        from .ai_engine import RiskAssessment, FraudSignal
        ra = RiskAssessment(
            partner_id=partner.id,
            risk_score=partner.risk_score,
            risk_level=partner.risk_level,
            decision=('BLOCK' if partner.risk_level=='critical' else
                      'OTP_VERIFY' if partner.risk_level=='high' else
                      'MONITOR' if partner.risk_level=='medium' else 'ALLOW'),
            component_scores={},
            fraud_signals=[],
            payout_eligible=partner.risk_level != 'critical',
        )
        decision = decide_payout(ra, trig_res, float(plan.daily_coverage))
        payout   = Payout.objects.create(
            partner=partner, event=event,
            amount=decision['amount'],
            status=decision['status'],
            reason=decision['reason'],
            released_at=timezone.now() if decision['status']=='released' else None,
        )
        payouts_created += 1
        total_amount    += decision['amount']

    event.affected_users = payouts_created
    event.total_payout   = total_amount
    event.save()

    return JsonResponse({
        'ok': True, 'event_id': event.id,
        'payouts_created': payouts_created,
        'total_amount': float(total_amount),
    })


@login_required
@user_passes_test(is_admin)
def api_fraud_graph(request):
    """Return graph data for the fraud network visualization."""
    partners = list(DeliveryPartner.objects.values('id','name','ip_address','device_id','risk_level','zone'))
    graph    = FraudGraph()
    graph.build_from_partners([{'id':p['id'],'ip_address':p['ip_address'],'device_id':p['device_id']} for p in partners])

    nodes = []
    for p in partners:
        nodes.append({
            'id':    p['id'],
            'name':  p['name'],
            'risk':  p['risk_level'],
            'zone':  p['zone'],
            'score': graph.graph_risk_score(p['id']),
        })

    edges = []
    for (a,b), types in graph.edge_types.items():
        edges.append({'source': a, 'target': b, 'types': types})

    clusters = graph.get_clusters(min_size=2)

    return JsonResponse({'nodes': nodes, 'edges': edges, 'clusters': clusters})
