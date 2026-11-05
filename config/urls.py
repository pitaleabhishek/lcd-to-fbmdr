from django.urls import include, path

urlpatterns = [
    path("", include("review.urls")),
]
