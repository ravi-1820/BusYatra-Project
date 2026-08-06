from django.db import models

# Create your models here.
class User(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=15, unique=True)
    password = models.CharField(max_length=100)
    profile =models.ImageField(default='', upload_to='profile/')
    usertype = models.CharField(max_length=20, default="customer")

    def __str__(self):
        return f'{self.name}'
    
class Bus(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    bus_name = models.CharField(max_length=100)
    bus_number = models.CharField(max_length=20)
    bus_type = models.CharField(max_length=20)
    source = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    departure_time = models.TimeField()
    arrival_time = models.TimeField()
    total_seats = models.IntegerField()
    available_seats = models.IntegerField()
    fare = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(default='', upload_to='bus/')

    def __str__(self):
        return f'{self.bus_name}'
    
class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    seat_number = models.CharField(max_length=10)
    passenger_name = models.CharField(max_length=100)
    passenger_age = models.IntegerField()
    passenger_gender = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    booking_date = models.DateField(auto_now_add=True)
    travel_date = models.DateField()
    STATUS_CHOICES = [
        ('booked', 'Booked'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='booked'
    )
    payment_id = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )
    razorpay_order_id = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )
    razorpay_signature = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )    
    payment = models.BooleanField(default=False)
    booking_status = models.CharField(
        max_length=20,
        default='booked'
    )
    payment_status = models.CharField(
        max_length=20,
        default='pending'
    )
    round_trip_id = models.UUIDField(
        null=True,
        blank=True,
        default=None
    )
    JOURNEY_TYPE_CHOICES = [
        ('ONE_WAY', 'One Way'),
        ('ROUND_TRIP', 'Round Trip'),
    ]
    journey_type = models.CharField(
        max_length=20,
        choices=JOURNEY_TYPE_CHOICES,
        default='ONE_WAY'
    )

    def __str__(self):
        return f"{self.user.name} - {self.bus.bus_name}"

class Route(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE)
    source = models.CharField(max_length=100)
    destination = models.CharField(max_length=100)
    distance = models.IntegerField()      # KM
    duration = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.source} → {self.destination}"

class SeatBooking(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='booked_seats')
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    seat_number = models.CharField(max_length=10)
    journey_date = models.DateField()

    class Meta:
        unique_together = ('bus', 'seat_number', 'journey_date')

    def __str__(self):
        return f"{self.bus.bus_name} - Seat {self.seat_number} on {self.journey_date}"

class Schedule(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    journey_date = models.DateField()
    departure_time = models.TimeField()
    arrival_time = models.TimeField()
    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Available')

    def __str__(self):
        return f"{self.bus.bus_name} on {self.journey_date}"
    
class Contact(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=10)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.name}'