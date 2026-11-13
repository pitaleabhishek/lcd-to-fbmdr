from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("labour/<int:pk>/", views.labour, name="labour"),
    path("labour/<int:pk>/review/", views.start_review, name="start_review"),
    path("labour/<int:pk>/history/", views.labour_history, name="labour_history"),
    path(
        "labour/<int:pk>/observations/<int:obs_pk>/correct/",
        views.correct_observation,
        name="correct_observation",
    ),
    path("source/<str:kind>/<int:pk>/", views.source, name="source"),
    path("review/new/", views.new_review, name="new_review"),
    path("review/<int:pk>/quick/", views.quick_review, name="quick_review"),
    path("review/<int:pk>/", views.workspace, name="workspace"),
    path(
        "review/<int:pk>/amend/<int:amendment_pk>/",
        views.amendment_workspace,
        name="amendment_workspace",
    ),
    path(
        "review/<int:pk>/amend/<int:amendment_pk>/quick/",
        views.amendment_quick,
        name="amendment_quick",
    ),
    path(
        "review/<int:pk>/amend/<int:amendment_pk>/output/",
        views.amendment_output,
        name="amendment_output",
    ),
    path(
        "review/<int:pk>/provenance/<str:key>/",
        views.field_provenance,
        name="field_provenance",
    ),
    path("review/<int:pk>/field/", views.save_field, name="save_field"),
    path("review/<int:pk>/na/", views.na_field, name="na_field"),
    path("review/<int:pk>/history/", views.history, name="history"),
    path("review/<int:pk>/output/", views.output, name="output"),
    path("review/<int:pk>/form1/", views.form1_output, name="form1_output"),
    path(
        "review/<int:pk>/form1/save/",
        views.save_form1,
        name="save_form1",
    ),
    path("login/", auth_views.LoginView.as_view(template_name="review/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
