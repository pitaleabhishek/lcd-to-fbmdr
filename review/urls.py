from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("labour/<int:pk>/", views.labour, name="labour"),
    path("review/<int:pk>/", views.workspace, name="workspace"),
    path("review/<int:pk>/output/", views.output, name="output"),
    path("login/", auth_views.LoginView.as_view(template_name="review/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
