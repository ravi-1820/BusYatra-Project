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

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'bus', 'rating', 'is_featured', 'is_active', 'created_at')
    list_filter = ('rating', 'is_featured', 'is_active', 'created_at', 'bus')
    list_editable = ('is_featured', 'is_active')
    search_fields = ('user__name', 'user__email', 'bus__bus_name', 'bus__bus_number', 'comment')
    readonly_fields = ('created_at', 'updated_at')



