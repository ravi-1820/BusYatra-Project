from django.urls import path, re_path
from . import views

urlpatterns = [
    #Customer URL patterns
    path('', views.index, name='home'),
    path('index/', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('user-dashboard/', views.dashboard, name='user_dashboard'),
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    # 'verify_otp/' URL removed — Login OTP flow has been removed
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-forgot-otp/', views.verify_forgot_otp, name='verify_forgot_otp'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path('logout/', views.logout, name='logout'),
    path('account/', views.account, name='account'),
    path('delete-account/', views.delete_account, name='delete_account'),
    path('bus_list/', views.bus_list, name='bus_list'),
    path('bus_detail/<int:pk>/', views.bus_detail, name='bus_detail'),
    path('seat_booking/<int:pk>/', views.seat_booking, name='seat_booking'),
    path('my-orders/', views.my_orders, name='my_orders'),
    path('payment/', views.payment, name='payment'),
    path('seat-booking/', views.seat_booking, name='seat_booking'),
    path('ticket/', views.ticket, name='ticket'),
    path('download-ticket/', views.download_ticket_pdf, name='download_ticket_pdf'),
    path('travel-guidelines/', views.travel_guidelines, name='travel_guidelines'),
    
    # Review URL patterns
    path('review/add/<int:booking_id>/', views.add_review, name='add_review'),
    path('review/edit/<int:review_id>/', views.edit_review, name='edit_review'),
    path('review/delete/<int:review_id>/', views.delete_review, name='delete_review'),
    path('review/feature/<int:review_id>/', views.toggle_feature_review, name='toggle_feature_review'),
    path('review/management-delete/<int:review_id>/', views.delete_review_management, name='delete_review_management'),
    path('manager-reviews/', views.manager_reviews, name='manager_reviews'),
    path('admin-reviews/', views.admin_reviews, name='admin_reviews'),

    
    #Manager URL patterns
    path('manager-bookings/', views.manager_bookings, name='manager_bookings')  ,
    path('manager-buses/', views.manager_buses, name='manager_buses'),
    path('add-bus/', views.add_bus, name='add_bus'),
    path('edit-bus/<int:bus_id>/', views.edit_bus, name='edit_bus'),
    path('delete-bus/<int:bus_id>/', views.delete_bus, name='delete_bus'),
    path('manager-dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('manager-reports/', views.manager_reports, name='manager_reports'),
    path('manager-reports/export/pdf/', views.export_pdf, name='export_pdf'),
    path('manager-reports/export/csv/', views.export_csv, name='export_csv'),
    path('manager-routes/', views.manager_routes, name='manager_routes'),
    path('add_route/', views.add_route, name='add_route'),
    path('edit_route/<int:route_id>/', views.edit_route, name='edit_route'),
    path('delete_route/<int:route_id>/', views.delete_route, name='delete_route'),
    path('manager-schedules/', views.manager_schedules, name='manager_schedules'),
    path('edit-schedule/<int:pk>/', views.edit_schedule, name='edit_schedule'),
    path('delete-schedule/<int:pk>/', views.delete_schedule, name='delete_schedule'),
    path('manager-seats/', views.manager_seats, name='manager_seats'),
    path('manager-profile/', views.manager_profile, name='manager_profile'),
    path('manager-booking/<int:booking_id>/', views.manager_booking_detail, name='manager_booking_detail'),
    path('manager-cancel-booking/<int:booking_id>/', views.manager_cancel_booking, name='manager_cancel_booking'),

    #Admin URL patterns
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # Customer CRUD
    path('admin-users/', views.admin_users, name='admin_users'),
    path('admin-add-customer/', views.admin_add_customer, name='admin_add_customer'),
    path('admin-edit-customer/<int:user_id>/', views.admin_edit_customer, name='admin_edit_customer'),
    path('admin-delete-customer/<int:user_id>/', views.admin_delete_customer, name='admin_delete_customer'),
    path('admin-customer-detail/<int:user_id>/', views.admin_customer_detail, name='admin_customer_detail'),
    
    # Manager CRUD
    path('admin-managers/', views.admin_managers, name='admin_managers'),
    path('admin-add-manager/', views.admin_add_manager, name='admin_add_manager'),
    path('admin-edit-manager/<int:user_id>/', views.admin_edit_manager, name='admin_edit_manager'),
    path('admin-delete-manager/<int:user_id>/', views.admin_delete_manager, name='admin_delete_manager'),
    path('admin-manager-detail/<int:user_id>/', views.admin_manager_detail, name='admin_manager_detail'),
    
    # Bus CRUD
    path('admin-buses/', views.admin_buses, name='admin_buses'),
    path('admin-add-bus/', views.admin_add_bus, name='admin_add_bus'),
    path('admin-edit-bus/<int:bus_id>/', views.admin_edit_bus, name='admin_edit_bus'),
    path('admin-delete-bus/<int:bus_id>/', views.admin_delete_bus, name='admin_delete_bus'),
    
    # Route CRUD
    path('admin-routes/', views.admin_routes, name='admin_routes'),
    path('admin-add-route/', views.admin_add_route, name='admin_add_route'),
    path('admin-edit-route/<int:route_id>/', views.admin_edit_route, name='admin_edit_route'),
    path('admin-delete-route/<int:route_id>/', views.admin_delete_route, name='admin_delete_route'),
    
    # Schedule CRUD
    path('admin-schedules/', views.admin_schedules, name='admin_schedules'),
    path('admin-add-schedule/', views.admin_add_schedule, name='admin_add_schedule'),
    path('admin-edit-schedule/<int:schedule_id>/', views.admin_edit_schedule, name='admin_edit_schedule'),
    path('admin-delete-schedule/<int:schedule_id>/', views.admin_delete_schedule, name='admin_delete_schedule'),
    
    # Booking Management
    path('admin-bookings/', views.admin_bookings, name='admin_bookings'),
    path('admin-booking-detail/<int:booking_id>/', views.admin_booking_detail, name='admin_booking_detail'),
    path('admin-cancel-booking/<int:booking_id>/', views.admin_cancel_booking, name='admin_cancel_booking'),
    
    # Payment Management
    path('admin-payments/', views.admin_payments, name='admin_payments'),
    
    # Profile & Settings
    path('admin-profile/', views.admin_profile, name='admin_profile'),
    path('admin-reports/', views.admin_reports, name='admin_reports'),
    path('admin-settings/', views.admin_settings, name='admin_settings'),

    #Contact Message for Admin or Manager.
    path('contact_message/', views.contact_message, name='contact_message'),
]
