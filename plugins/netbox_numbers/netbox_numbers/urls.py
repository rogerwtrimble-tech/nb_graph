from django.urls import include, path

from utilities.urls import get_model_urls

from . import views  # noqa: F401  (registers model views)

urlpatterns = [
    path('telephone-numbers/', include(get_model_urls('netbox_numbers', 'telephonenumber', detail=False))),
    path('telephone-numbers/<int:pk>/', include(get_model_urls('netbox_numbers', 'telephonenumber'))),
]
