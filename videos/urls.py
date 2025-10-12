from django.urls import path
from . import views

app_name = "videos"
urlpatterns = [
    path("", views.movie_list, name="list"),
    path("create/", views.movie_create, name="create"),
    path("<int:pk>/update/", views.movie_update, name="update"),
    path("<int:pk>/delete/", views.movie_delete, name="delete"),
]
