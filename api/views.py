import math
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import User, ParkingSpace, Booking, Payment, Review, Complaint, Notification
from .serializers import *
from .permissions import *
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

class AuthViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]
    
    @action(detail=False, methods=['post'])
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def login(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'user': UserSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            })
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        if self.request.user.user_type == 'ADMIN':
            return User.objects.all()
        return User.objects.filter(id=self.request.user.id)
    
    @action(detail=False, methods=['get', 'put'])
    def profile(self, request):
        if request.method == 'GET':
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)
        else:
            serializer = self.get_serializer(request.user, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ParkingSpaceViewSet(viewsets.ModelViewSet):
    serializer_class = ParkingSpaceSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = ParkingSpace.objects.filter(is_active=True, verification_status='VERIFIED')
        
        # Filter by proximity
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius', 5)
        
        if lat and lng:
            try:
                lat = float(lat)
                lng = float(lng)
                radius = float(radius)
                
                # Simple bounding box filter
                lat_range = radius / 111.0
                lng_range = radius / (111.0 * abs(lat or 1))
                
                queryset = queryset.filter(
                    latitude__isnull=False,
                    longitude__isnull=False,
                    latitude__range=(lat - lat_range, lat + lat_range),
                    longitude__range=(lng - lng_range, lng + lng_range)
                )
                
                # Calculate distance for each parking space
                parking_list = []
                for parking in queryset:
                    if parking.latitude and parking.longitude:
                        R = 6371
                        lat1 = math.radians(lat)
                        lat2 = math.radians(float(parking.latitude))
                        delta_lat = math.radians(float(parking.latitude) - lat)
                        delta_lng = math.radians(float(parking.longitude) - lng)
                        
                        a = math.sin(delta_lat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng/2)**2
                        c = 2 * math.asin(math.sqrt(a))
                        distance = R * c
                        parking.distance = distance
                        parking_list.append(parking)
                
                queryset = sorted(parking_list, key=lambda x: getattr(x, 'distance', float('inf')))
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        
        # Filter by date/time - with SAFE date handling
        date = self.request.query_params.get('date')
        start_time = self.request.query_params.get('start_time')
        end_time = self.request.query_params.get('end_time')
        
        if date and start_time and end_time:
            try:
                booking_date = datetime.strptime(date, '%Y-%m-%d')
                
                # Check if date is too far in future (more than 10 years)
                current_year = datetime.now().year
                if booking_date.year > current_year + 10:
                    # Date too far, return empty queryset
                    return ParkingSpace.objects.none()
                
                start = datetime.combine(booking_date, datetime.strptime(start_time, '%H:%M').time())
                end = datetime.combine(booking_date, datetime.strptime(end_time, '%H:%M').time())
                
                # Exclude booked slots
                booked_spaces = Booking.objects.filter(
                    parking_space__in=queryset,
                    status__in=['PENDING', 'ACCEPTED', 'ACTIVE'],
                    booking_time__lt=end,
                    end_time__gt=start
                ).values_list('parking_space_id', flat=True)
                
                # Filter out booked spaces
                queryset = [p for p in queryset if p.id not in booked_spaces]
                
            except (ValueError, TypeError) as e:
                print(f"Date parsing error: {e}")
                pass
        
        return queryset
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsLandOwner]
        return super().get_permissions()
    
    @action(detail=True, methods=['post'])
    def update_availability(self, request, pk=None):
        parking_space = self.get_object()
        available_slots = request.data.get('available_slots')
        if available_slots is not None:
            try:
                available_slots = int(available_slots)
                if 0 <= available_slots <= parking_space.total_slots:
                    parking_space.available_slots = available_slots
                    parking_space.save()
                    return Response({'message': 'Availability updated successfully'})
                else:
                    return Response({'error': f'Available slots must be between 0 and {parking_space.total_slots}'}, 
                                  status=status.HTTP_400_BAD_REQUEST)
            except ValueError:
                return Response({'error': 'Invalid number format'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'error': 'available_slots required'}, status=status.HTTP_400_BAD_REQUEST)

class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'VEHICLE_OWNER':
            return Booking.objects.filter(user=user)
        elif user.user_type == 'LAND_OWNER':
            return Booking.objects.filter(parking_space__owner=user)
        else:
            return Booking.objects.all()
    
    def perform_create(self, serializer):
        # Get vehicle details from request
        vehicle_number = self.request.data.get('vehicle_number', '')
        vehicle_type = self.request.data.get('vehicle_type', 'car')
        owner_name = self.request.data.get('owner_name', '')
        owner_mobile = self.request.data.get('owner_mobile', '')
        
        # Save booking with vehicle details
        booking = serializer.save(
            user=self.request.user,
            status='PENDING',
            vehicle_number=vehicle_number,
            vehicle_type=vehicle_type,
            owner_name=owner_name,
            owner_mobile=owner_mobile
        )
        
        # Handle vehicle photo upload
        if 'vehicle_photo' in self.request.FILES:
            booking.vehicle_photo = self.request.FILES['vehicle_photo']
            booking.save()
        
        # Generate QR code
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(f"BOOKING:{booking.booking_id}")
            qr.make(fit=True)
            img = BytesIO()
            qr.make_image(fill='black', back_color='white').save(img, 'PNG')
            booking.qr_code = base64.b64encode(img.getvalue()).decode()
            booking.save()
        except Exception as e:
            print(f"QR Code generation failed: {e}")
        
        # Create notification for land owner
        Notification.objects.create(
            user=booking.parking_space.owner,
            type='BOOKING',
            title='New Booking Request',
            message=f'New booking request for {booking.parking_space.name} from {self.request.user.username} - Vehicle: {vehicle_number}'
        )
    
    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        booking = self.get_object()
        new_status = request.data.get('status')
        
        if new_status not in ['ACCEPTED', 'REJECTED', 'ACTIVE', 'COMPLETED']:
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        
        if new_status in ['ACCEPTED', 'REJECTED'] and request.user.user_type != 'LAND_OWNER':
            return Response({'error': 'Only land owner can accept/reject bookings'}, 
                          status=status.HTTP_403_FORBIDDEN)
        
        booking.status = new_status
        
        # If status is ACTIVE, set entry time
        if new_status == 'ACTIVE' and not booking.entry_time:
            booking.entry_time = datetime.now()
        
        # If status is COMPLETED, set exit time
        if new_status == 'COMPLETED' and not booking.exit_time:
            booking.exit_time = datetime.now()
        
        booking.save()
        
        # Create notification for vehicle owner
        Notification.objects.create(
            user=booking.user,
            type='BOOKING',
            title=f'Booking {new_status}',
            message=f'Your booking for {booking.parking_space.name} has been {new_status.lower()}'
        )
        
        return Response({'message': f'Booking {new_status} successfully', 'status': booking.status})
    
    @action(detail=True, methods=['post'])
    def cancel_booking(self, request, pk=None):
        booking = self.get_object()
        
        if booking.status in ['COMPLETED', 'CANCELLED']:
            return Response({'error': 'Cannot cancel this booking'}, status=status.HTTP_400_BAD_REQUEST)
        
        booking.status = 'CANCELLED'
        booking.save()
        
        # Refund if payment was made
        if hasattr(booking, 'payment') and booking.payment.status == 'COMPLETED':
            try:
                refund = stripe.Refund.create(
                    payment_intent=booking.payment.stripe_payment_intent_id
                )
                booking.payment.status = 'REFUNDED'
                booking.payment.save()
            except Exception as e:
                print(f"Refund failed: {e}")
        
        # Create notification
        Notification.objects.create(
            user=booking.user,
            type='BOOKING',
            title='Booking Cancelled',
            message=f'Your booking for {booking.parking_space.name} has been cancelled'
        )
        
        return Response({'message': 'Booking cancelled successfully'})

class PaymentViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    
    @action(detail=False, methods=['post'])
    def create_payment_intent(self, request):
        booking_id = request.data.get('booking_id')
        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(float(booking.total_amount) * 100),
                currency='usd',
                metadata={'booking_id': booking.booking_id}
            )
            
            payment, created = Payment.objects.get_or_create(
                booking=booking,
                defaults={
                    'stripe_payment_intent_id': intent.id,
                    'amount': booking.total_amount,
                    'transaction_id': intent.id,
                    'status': 'PENDING',
                    'payment_method': 'CARD'
                }
            )
            
            return Response({
                'client_secret': intent.client_secret,
                'payment_id': payment.id
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['post'])
    def confirm_payment(self, request):
        payment_id = request.data.get('payment_id')
        payment_intent_id = request.data.get('payment_intent_id')
        
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            if intent.status == 'succeeded':
                payment = Payment.objects.get(id=payment_id)
                payment.status = 'COMPLETED'
                payment.save()
                
                booking = payment.booking
                booking.status = 'ACCEPTED'
                booking.save()
                
                return Response({'message': 'Payment confirmed successfully'})
            else:
                return Response({'error': 'Payment not successful'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ReviewViewSet(viewsets.ModelViewSet):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)
    
    def perform_create(self, serializer):
        booking_id = self.request.data.get('booking_id')
        try:
            booking = Booking.objects.get(id=booking_id, user=self.request.user)
            if booking.status != 'COMPLETED':
                raise serializers.ValidationError("Can only review completed bookings")
            serializer.save(
                user=self.request.user,
                booking=booking,
                parking_space=booking.parking_space
            )
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking not found")

class DashboardViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def admin_stats(self, request):
        if request.user.user_type != 'ADMIN':
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        total_users = User.objects.count()
        total_parking_spaces = ParkingSpace.objects.count()
        total_bookings = Booking.objects.count()
        total_revenue = Payment.objects.filter(status='COMPLETED').aggregate(Sum('amount'))['amount__sum'] or 0
        
        recent_bookings = Booking.objects.order_by('-created_at')[:10]
        
        # Chart data
        bookings_by_status = Booking.objects.values('status').annotate(count=Count('id'))
        revenue_by_month = Payment.objects.filter(status='COMPLETED', payment_date__year=datetime.now().year)\
                            .extra({'month': "MONTH(payment_date)"}).values('month')\
                            .annotate(total=Sum('amount')).order_by('month')
        
        return Response({
            'total_users': total_users,
            'total_parking_spaces': total_parking_spaces,
            'total_bookings': total_bookings,
            'total_revenue': float(total_revenue),
            'recent_bookings': BookingSerializer(recent_bookings, many=True).data,
            'bookings_by_status': list(bookings_by_status),
            'revenue_by_month': list(revenue_by_month)
        })
    
    @action(detail=False, methods=['get'])
    def owner_stats(self, request):
        if request.user.user_type != 'LAND_OWNER':
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        parking_spaces = ParkingSpace.objects.filter(owner=request.user)
        total_bookings = Booking.objects.filter(parking_space__in=parking_spaces).count()
        total_earnings = Payment.objects.filter(
            booking__parking_space__in=parking_spaces,
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        recent_bookings = Booking.objects.filter(parking_space__in=parking_spaces).order_by('-created_at')[:10]
        
        return Response({
            'total_parking_spaces': parking_spaces.count(),
            'total_bookings': total_bookings,
            'total_earnings': float(total_earnings),
            'recent_bookings': BookingSerializer(recent_bookings, many=True).data
        })
    
    @action(detail=False, methods=['get'])
    def user_stats(self, request):
        if request.user.user_type != 'VEHICLE_OWNER':
            return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
        
        total_bookings = Booking.objects.filter(user=request.user).count()
        active_bookings = Booking.objects.filter(
            user=request.user,
            status='ACTIVE'
        ).count()
        total_spent = Payment.objects.filter(
            booking__user=request.user,
            status='COMPLETED'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        upcoming_bookings = Booking.objects.filter(
            user=request.user,
            status__in=['PENDING', 'ACCEPTED'],
            booking_time__gt=datetime.now()
        ).order_by('booking_time')[:5]
        
        return Response({
            'total_bookings': total_bookings,
            'active_bookings': active_bookings,
            'total_spent': float(total_spent),
            'upcoming_bookings': BookingSerializer(upcoming_bookings, many=True).data
        })