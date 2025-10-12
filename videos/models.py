from django.db import models

# Create your models here.
class Movies(models.Model):
    MovieID=models.AutoField(primary_key=True)
    MovieTitle = models.CharField(max_length=200)
    Actor1Name = models.CharField(max_length=200)
    Actor2Name = models.CharField(max_length=200)
    DirectorName = models.CharField(max_length=100)
    MovieGenre = models.CharField(max_length=100)
    ReleaseYear = models.IntegerField()

    def __str__(self):
        return f"{self.MovieTitle} ({self.ReleaseYear})"