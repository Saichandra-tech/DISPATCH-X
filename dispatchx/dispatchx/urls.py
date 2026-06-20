from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('insurance.urls')),
    path('login/',  auth_views.LoginView.as_view(template_name='insurance/login.html'),  name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
