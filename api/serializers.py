from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import User, ParkingSpace, Booking, Payment, Review, Complaint, Notification
from datetime import datetime

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 
                 'user_type', 'phone_number', 'profile_picture', 'address', 'is_verified')
        read_only_fields = ('is_verified',)

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'first_name', 'last_name', 
                 'user_type', 'phone_number')
    
    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            user_type=validated_data.get('user_type', 'VEHICLE_OWNER'),
            phone_number=validated_data.get('phone_number')
        )
        return user

class ParkingSpaceSerializer(serializers.ModelSerializer):
    owner_details = UserSerializer(source='owner', read_only=True)
    distance = serializers.FloatField(read_only=True)
    
    class Meta:
        model = ParkingSpace
        fields = '__all__'
        read_only_fields = ('owner', 'total_ratings', 'total_reviews_count', 'verification_status')
    
    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Add location as GeoJSON-like object for frontend compatibility
        if instance.latitude and instance.longitude:
            representation['location'] = {
                'type': 'Point',
                'coordinates': [float(instance.longitude), float(instance.latitude)]
            }
        return representation

class BookingSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    parking_details = ParkingSpaceSerializer(source='parking_space', read_only=True)
    
    class Meta:
        model = Booking
        fields = '__all__'
        read_only_fields = ('booking_id', 'user', 'status', 'qr_code', 'total_hours', 'total_amount')
    
    def validate(self, data):
        parking_space = data.get('parking_space')
        booking_time = data.get('booking_time')
        end_time = data.get('end_time')
        
        # Validate time
        if booking_time >= end_time:
            raise serializers.ValidationError({"end_time": "End time must be after booking time"})
        
        # Validate parking availability
        if booking_time < datetime.now():
            raise serializers.ValidationError({"booking_time": "Cannot book past time"})
        
        # Validate vehicle number format
        vehicle_number = data.get('vehicle_number', '')
        if vehicle_number and len(vehicle_number) < 6:
            raise serializers.ValidationError({"vehicle_number": "Please enter a valid vehicle number"})
        
        # Validate mobile number
        owner_mobile = data.get('owner_mobile', '')
        if owner_mobile and len(owner_mobile) != 10:
            raise serializers.ValidationError({"owner_mobile": "Mobile number must be 10 digits"})
        
        # Check slot availability
        if parking_space:
            active_bookings = Booking.objects.filter(
                parking_space=parking_space,
                status__in=['PENDING', 'ACCEPTED', 'ACTIVE'],
                booking_time__lt=end_time,
                end_time__gt=booking_time
            ).count()
            
            if active_bookings >= parking_space.total_slots:
                raise serializers.ValidationError({"parking_space": "No slots available for selected time"})
        
        # Calculate total amount
        if booking_time and end_time:
            total_seconds = (end_time - booking_time).total_seconds()
            total_hours = int(total_seconds / 3600)
            if total_seconds % 3600 > 0:
                total_hours += 1  # Round up to nearest hour
            
            data['total_hours'] = total_hours
            if parking_space:
                data['total_amount'] = total_hours * float(parking_space.price_per_hour)
        
        return data

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = ('transaction_id', 'payment_date')

class ReviewSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = Review
        fields = '__all__'
        read_only_fields = ('user',)

class ComplaintSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    
    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ('user', 'status', 'admin_remark')

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ('created_at',)