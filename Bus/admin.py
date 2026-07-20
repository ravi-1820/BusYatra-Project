from django.contrib import admin
from .models import *

# Register your models here.
admin.site.register(User)
admin.site.register(Bus)
admin.site.register(Booking)
admin.site.register(Route)
admin.site.register(SeatBooking)
admin.site.register(Schedule)
admin.site.register(Contact)

