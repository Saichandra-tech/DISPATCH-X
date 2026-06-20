from django.urls import path
from . import views

urlpatterns = [
    path('',               views.dashboard_view,       name='home'),
    path('signup/',        views.signup_view,           name='signup'),
    path('login/',         views.login_view,            name='login'),
    path('dashboard/',     views.dashboard_view,        name='dashboard'),
    path('subscription/',  views.subscription_view,     name='subscription'),
    path('payouts/',       views.payouts_view,          name='payouts'),

    # Admin
    path('admin-panel/',               views.admin_dashboard_view, name='admin_panel'),
    path('admin-panel/user/<int:user_id>/', views.admin_user_detail, name='admin_user_detail'),

    # API
    path('api/risk-score/',                    views.api_risk_score,    name='api_risk_score'),
    path('api/location/',                      views.api_update_location, name='api_update_location'),
    path('api/admin/action/<int:user_id>/',    views.api_take_action,   name='api_take_action'),
    path('api/admin/resolve/<int:alert_id>/',  views.api_resolve_alert, name='api_resolve_alert'),
    path('api/admin/trigger-event/',           views.api_trigger_event, name='api_trigger_event'),
    path('api/admin/fraud-graph/',             views.api_fraud_graph,   name='api_fraud_graph'),
]
