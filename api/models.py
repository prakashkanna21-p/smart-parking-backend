from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from phonenumber_field.modelfields import PhoneNumberField
from datetime import datetime, timedelta
import uuid

class User(AbstractUser):
    USER_TYPES = (
        ('VEHICLE_OWNER', 'Vehicle Owner'),
        ('LAND_OWNER', 'Land Owner'),
        ('ADMIN', 'Admin'),
    )
    
    user_type = models.CharField(max_length=20, choices=USER_TYPES, default='VEHICLE_OWNER')
    phone_number = PhoneNumberField(unique=True)
    profile_picture = models.ImageField(upload_to='profiles/', null=True, blank=True)
    address = models.TextField(blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.username} - {self.get_user_type_display()}"

class ParkingSpace(models.Model):
    VERIFICATION_STATUS = (
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    )
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='parking_spaces')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    # Location fields
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    
    # Parking details
    total_slots = models.IntegerField()
    available_slots = models.IntegerField()
    price_per_hour = models.DecimalField(max_digits=10, decimal_places=2)
    opening_time = models.TimeField()
    closing_time = models.TimeField()
    
    # Additional features
    images = models.JSONField(default=list)
    has_cctv = models.BooleanField(default=False)
    has_ev_charging = models.BooleanField(default=False)
    is_covered = models.BooleanField(default=False)
    has_guard = models.BooleanField(default=False)
    
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS, default='PENDING')
    is_active = models.BooleanField(default=True)
    total_ratings = models.FloatField(default=0)
    total_reviews_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def update_availability(self):
        active_bookings = self.bookings.filter(
            status='ACTIVE',
            booking_time__lte=datetime.now(),
            end_time__gte=datetime.now()
        )
        self.available_slots = self.total_slots - active_bookings.count()
        self.save()
    
    def __str__(self):
        return f"{self.name} - {self.city}"

class Booking(models.Model):
    BOOKING_STATUS = (
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('ACTIVE', 'Active'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )
    
    VEHICLE_TYPES = (
        ('car', '🚗 Car'),
        ('suv', '🚙 SUV / MUV'),
        ('bike', '🏍️ Bike / Motorcycle'),
        ('truck', '🚚 Truck / Lorry'),
        ('auto', '🛺 Auto / Rickshaw'),
    )
    
    booking_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    parking_space = models.ForeignKey(ParkingSpace, on_delete=models.CASCADE, related_name='bookings')
    
    # Vehicle details
    vehicle_number = models.CharField(
        max_length=20,
        validators=[
            RegexValidator(
                regex=r'^[A-Z0-9]{6,10}$',
                message='Enter a valid vehicle number (e.g., KA01AB1234)'
            )
        ]
    )
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES, default='car')
    owner_name = models.CharField(max_length=100)
    owner_mobile = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^[0-9]{10}$',
                message='Enter a valid 10-digit mobile number'
            )
        ]
    )
    vehicle_photo = models.ImageField(upload_to='vehicles/', null=True, blank=True)
    
    # Booking details
    booking_time = models.DateTimeField()
    end_time = models.DateTimeField()
    total_hours = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    status = models.CharField(max_length=20, choices=BOOKING_STATUS, default='PENDING')
    qr_code = models.TextField(blank=True)
    entry_time = models.DateTimeField(null=True, blank=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.booking_id:
            self.booking_id = str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Booking {self.booking_id} - {self.user.username} - {self.vehicle_number}"

class Payment(models.Model):
    PAYMENT_STATUS = (
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    )
    
    PAYMENT_METHODS = (
        ('CARD', 'Card'),
        ('UPI', 'UPI'),
        ('NETBANKING', 'Net Banking'),
        ('WALLET', 'Wallet'),
    )
    
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='payment')
    stripe_payment_intent_id = models.CharField(max_length=200, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CARD')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PENDING')
    transaction_id = models.CharField(max_length=200, unique=True)
    payment_date = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Payment {self.transaction_id} - {self.amount}"

class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review')
    parking_space = models.ForeignKey(ParkingSpace, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update parking space average rating
        reviews = self.parking_space.reviews.all()
        avg_rating = reviews.aggregate(models.Avg('rating'))['rating__avg']
        self.parking_space.total_ratings = avg_rating
        self.parking_space.total_reviews_count = reviews.count()
        self.parking_space.save()
    
    def __str__(self):
        return f"Review for {self.parking_space.name} - {self.rating}★"

class Complaint(models.Model):
    COMPLAINT_TYPES = (
        ('PAYMENT', 'Payment Issue'),
        ('PARKING', 'Parking Issue'),
        ('SAFETY', 'Safety Concern'),
        ('VEHICLE', 'Vehicle Issue'),
        ('OTHER', 'Other'),
    )
    
    COMPLAINT_STATUS = (
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
        ('REJECTED', 'Rejected'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='complaints')
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True)
    complaint_type = models.CharField(max_length=20, choices=COMPLAINT_TYPES)
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=COMPLAINT_STATUS, default='PENDING')
    admin_remark = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Complaint {self.id} - {self.subject}"

class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('BOOKING', 'Booking'),
        ('PAYMENT', 'Payment'),
        ('SYSTEM', 'System'),
        ('PROMOTION', 'Promotion'),
    )
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Notification for {self.user.username} - {self.title}"