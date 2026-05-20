from rest_framework import permissions

class IsVehicleOwner(permissions.BasePermission):
    """
    Permission class for Vehicle Owners only.
    Allows access only to users with user_type 'VEHICLE_OWNER'
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'VEHICLE_OWNER'
    
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and request.user.user_type == 'VEHICLE_OWNER'

class IsLandOwner(permissions.BasePermission):
    """
    Permission class for Land Owners only.
    Allows access only to users with user_type 'LAND_OWNER'
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'LAND_OWNER'
    
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and request.user.user_type == 'LAND_OWNER'

class IsAdmin(permissions.BasePermission):
    """
    Permission class for Admin only.
    Allows access only to users with user_type 'ADMIN'
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'ADMIN'
    
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and request.user.user_type == 'ADMIN'

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission class that allows:
    - Read access to anyone authenticated
    - Write/Delete access only to the owner or admin
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions are only allowed to the owner or admin
        if hasattr(obj, 'owner'):
            return obj.owner == request.user or request.user.user_type == 'ADMIN'
        elif hasattr(obj, 'user'):
            return obj.user == request.user or request.user.user_type == 'ADMIN'
        
        return False

class IsParkingOwner(permissions.BasePermission):
    """
    Permission class for parking space owners.
    Allows access only to the land owner who owns the parking space.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.user_type == 'LAND_OWNER'
    
    def has_object_permission(self, request, view, obj):
        # Check if the object has an owner attribute (ParkingSpace)
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        # Check if the object has a parking_space with owner (Booking, Review)
        elif hasattr(obj, 'parking_space'):
            return obj.parking_space.owner == request.user
        
        return False

class IsBookingOwner(permissions.BasePermission):
    """
    Permission class for booking owners.
    Allows access only to the user who made the booking.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Check if the user is the one who made the booking
        if hasattr(obj, 'user'):
            return obj.user == request.user
        # Check if the booking belongs to the user through payment
        elif hasattr(obj, 'booking') and hasattr(obj.booking, 'user'):
            return obj.booking.user == request.user
        
        return False

class IsVerifiedUser(permissions.BasePermission):
    """
    Permission class for verified users only.
    Allows access only to users who have been verified.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_verified
    
    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and request.user.is_verified

class CanModifyParkingSpace(permissions.BasePermission):
    """
    Permission class that allows:
    - Land owners to modify their own parking spaces
    - Admin to modify any parking space
    - Vehicle owners cannot modify any parking space
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Admin can do anything
        if request.user.user_type == 'ADMIN':
            return True
        
        # Land owners can create parking spaces
        if request.user.user_type == 'LAND_OWNER':
            return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        # Admin can modify any parking space
        if request.user.user_type == 'ADMIN':
            return True
        
        # Land owners can modify only their own parking spaces
        if request.user.user_type == 'LAND_OWNER' and hasattr(obj, 'owner'):
            return obj.owner == request.user
        
        return False

class CanManageBookings(permissions.BasePermission):
    """
    Permission class for managing bookings:
    - Vehicle owners can manage their own bookings
    - Land owners can manage bookings for their parking spaces
    - Admin can manage all bookings
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Admin can manage any booking
        if request.user.user_type == 'ADMIN':
            return True
        
        # Vehicle owners can manage their own bookings
        if request.user.user_type == 'VEHICLE_OWNER' and hasattr(obj, 'user'):
            return obj.user == request.user
        
        # Land owners can manage bookings for their parking spaces
        if request.user.user_type == 'LAND_OWNER' and hasattr(obj, 'parking_space'):
            return obj.parking_space.owner == request.user
        
        return False