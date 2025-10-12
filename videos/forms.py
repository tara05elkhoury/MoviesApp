from django import forms
from django.forms import ModelForm
from .models import Movies

class MovieForm(ModelForm):
    class Meta:
        model = Movies
        fields = [
            "MovieTitle",
            "Actor1Name",
            "Actor2Name",
            "DirectorName",
            "MovieGenre",
            "ReleaseYear",
        ]
