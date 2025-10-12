from django.shortcuts import render, redirect, get_object_or_404
from .models import Movies
from .forms import MovieForm

def movie_list(request):
    movies = Movies.objects.all().order_by("-ReleaseYear", "MovieTitle")
    return render(request, "videos/movie_list.html", {"movies": movies})

def movie_create(request):
    form = MovieForm(request.POST or None)
    if form.is_valid():
        form.save()
        return redirect("videos:list")
    return render(request, "videos/movie_form.html", {"form": form})

def movie_update(request, pk):
    movie = get_object_or_404(Movies, pk=pk)
    form = MovieForm(request.POST or None, instance=movie)
    if form.is_valid():
        form.save()
        return redirect("videos:list")
    return render(request, "videos/movie_form.html", {"form": form})

def movie_delete(request, pk):
    movie = get_object_or_404(Movies, pk=pk)
    if request.method == "POST":
        movie.delete()
        return redirect("videos:list")
    return render(request, "videos/movie_confirm_delete.html", {"movie": movie})
