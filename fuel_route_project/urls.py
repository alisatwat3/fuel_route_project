from django.urls import path, include
from route_planner.views_frontend import index

urlpatterns = [
    path('', index, name='index'),
    path('api/', include('route_planner.urls')),
]
