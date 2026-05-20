from django.urls import path, include 
from rest_framework.routers import DefaultRouter 
from .views import * 
router = DefaultRouter() 
router.register('auth', AuthViewSet, basename='auth') 
router.register('users', UserViewSet, basename='user') 
router.register('parking-spaces', ParkingSpaceViewSet, basename='parkingspace') 
router.register('bookings', BookingViewSet, basename='booking') 
router.register('payments', PaymentViewSet, basename='payment') 
router.register('reviews', ReviewViewSet, basename='review') 
router.register('dashboard', DashboardViewSet, basename='dashboard') 
urlpatterns = [path('', include(router.urls))] 
