from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden
from .models import User, Bus, Booking, Route, SeatBooking, Schedule, Contact, Review, SystemSettings
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.db import transaction
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator, Page, EmptyPage, PageNotAnInteger
import random
import razorpay
import json
import logging
import uuid
from datetime import date, timedelta, datetime
from decimal import Decimal


# Reportlab imports for PDF ticket generation
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from django.contrib.staticfiles import finders
from io import BytesIO

# Initialize standard Python logging
logger = logging.getLogger(__name__)

#==========================================================================
#    Helper Authentication Functions (Security & Code Reusability)
#==========================================================================

def get_customer_user(request):
    try:
        return get_logged_in_user(request, 'customer')
    except Exception as e:
        logger.error(f"Error in get_customer_user: {e}")
        return None

def get_manager_user(request):
    try:
        return get_logged_in_user(request, 'manager')
    except Exception as e:
        logger.error(f"Error in get_manager_user: {e}")
        return None

def get_admin_user(request):
    try:
        return get_logged_in_user(request, 'admin')
    except Exception as e:
        logger.error(f"Error in get_admin_user: {e}")
        return None

def get_logged_in_user(request, usertype):
    email = request.session.get('email')
    if not email:
        return None
    try:
        return User.objects.get(email=email, usertype=usertype)
    except User.DoesNotExist:
        return None

def parse_booking_ids(booking_ids):
    try:
        if not booking_ids:
            return []
        return [int(item) for item in booking_ids.split(",") if item.strip().isdigit()]
    except Exception as e:
        logger.error(f"Error parsing booking ids: {e}")
        return []

def get_customer_bookings(customer, booking_ids):
    try:
        ids = parse_booking_ids(booking_ids)
        if not ids:
            return Booking.objects.none()
        return Booking.objects.filter(id__in=ids, user=customer).select_related('bus', 'user')
    except Exception as e:
        logger.error(f"Error fetching customer bookings: {e}")
        return Booking.objects.none()

def is_valid_date(date_str):
    if not date_str or not isinstance(date_str, str):
        return False
    if date_str.strip().lower() in ("none", "null", ""):
        return False
    from datetime import datetime
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False

def is_valid_city(city_str):
    try:
        if not city_str or not isinstance(city_str, str):
            return False
        if city_str.strip().lower() in ("none", "null", ""):
            return False
        return True
    except Exception as e:
        logger.error(f"Error validating city: {e}")
        return False

def normalize_search_city(city_str):
    try:
        if not city_str or not isinstance(city_str, str):
            return ""
        val = city_str.strip()
        if val.lower() in ("", "none", "null", "select source", "select destination", "source", "destination"):
            return ""
        return val
    except Exception as e:
        logger.error(f"Error normalizing search city: {e}")
        return ""

def is_valid_passengers(passengers_str):
    if not passengers_str:
        return False
    try:
        val = int(passengers_str)
        return val > 0
    except ValueError:
        return False

def get_search_details(request):
    try:
        raw_from = request.GET.get('from') or request.GET.get('source')
        raw_to = request.GET.get('to') or request.GET.get('destination')
        raw_date = request.GET.get('date')
        raw_return_date = request.GET.get('return_date')
        raw_passengers = request.GET.get('passengers')

        from_city = normalize_search_city(raw_from)
        to_city = normalize_search_city(raw_to)

        if is_valid_date(raw_date):
            travel_date = raw_date.strip()
        else:
            travel_date = date.today().strftime("%Y-%m-%d")

        if is_valid_passengers(raw_passengers):
            passengers = raw_passengers.strip()
        else:
            passengers = "1"

        raw_round_trip = request.GET.get('round_trip')
        is_round_trip = True if raw_round_trip in ['1', 'true', 'True', 'on'] else False

        if is_round_trip and is_valid_date(raw_return_date):
            clean_return = raw_return_date.strip()
            if clean_return >= travel_date:
                return_date = clean_return
            else:
                return_date = travel_date
        else:
            return_date = travel_date

        return {
            'from_city': from_city,
            'to_city': to_city,
            'travel_date': travel_date,
            'return_date': return_date,
            'passengers': passengers,
            'round_trip': is_round_trip,
        }
    except Exception as e:
        logger.error(f"Error getting search details: {e}")
        today_str = date.today().strftime("%Y-%m-%d")
        return {
            'from_city': '',
            'to_city': '',
            'travel_date': today_str,
            'return_date': today_str,
            'passengers': '1',
            'round_trip': False,
        }

def travel_date_or_today(travel_date):
    try:
        if is_valid_date(travel_date):
            return travel_date
        return date.today().strftime("%Y-%m-%d")
    except Exception as e:
        logger.error(f"Error in travel_date_or_today: {e}")
        return date.today().strftime("%Y-%m-%d")

def booked_seat_count(bus, travel_date):
    try:
        date_to_use = travel_date_or_today(travel_date)
        return Booking.objects.filter(
            bus=bus,
            travel_date=date_to_use,
            payment=True,
            payment_status="success",
            booking_status="booked"
        ).count()
    except Exception as e:
        logger.error(f"Error counting booked seats: {e}")
        return 0

def set_live_available_seats(buses, travel_date):
    try:
        date_to_use = travel_date_or_today(travel_date)
        for bus in buses:
            bus.available_seats = max(0, bus.total_seats - booked_seat_count(bus, date_to_use))
    except Exception as e:
        logger.error(f"Error setting live available seats: {e}")

def get_booked_seats(bus, travel_date):
    try:
        date_to_use = travel_date_or_today(travel_date)
        return list(
            SeatBooking.objects.filter(
                bus=bus,
                journey_date=date_to_use
            ).values_list("seat_number", flat=True)
        )
    except Exception as e:
        logger.error(f"Error getting booked seats: {e}")
        return []

def calculate_payment_summary(bookings):
    try:
        sys_settings = SystemSettings.get_settings()
        subtotal = sum(booking.amount for booking in bookings)
        gst_fees = int((subtotal * sys_settings.gst_percentage) / 100)
        convenience_fee = int(sys_settings.convenience_fee) * len(bookings)
        total_price = subtotal + gst_fees + convenience_fee
        return subtotal, gst_fees, convenience_fee, total_price
    except Exception as e:
        logger.error(f"Error calculating payment summary: {e}")
        return 0, 0, 0, 0



def make_passenger_dict(booking):
    try:
        return {
            'name': booking.passenger_name,
            'age': booking.passenger_age,
            'gender': booking.passenger_gender,
            'seat': booking.seat_number,
        }
    except Exception as e:
        logger.error(f"Error making passenger dict: {e}")
        return {'name': '', 'age': 0, 'gender': '', 'seat': ''}

def build_order_groups(bookings):
    try:
        groups = []
        group_by_key = {}

        for booking in bookings:
            j_type = getattr(booking, 'journey_type', 'ONE_WAY')
            rt_id = getattr(booking, 'round_trip_id', None)

            if j_type == 'ROUND_TRIP' and rt_id:
                key = ('ROUND_TRIP', str(rt_id))
            else:
                key = (booking.bus.id, booking.travel_date, booking.booking_date, booking.status, booking.payment)

            if key not in group_by_key:
                group_by_key[key] = {
                    'id': booking.id,
                    'booking_ids': [],
                    'bus': booking.bus,
                    'travel_date': booking.travel_date,
                    'booking_date': booking.booking_date,
                    'status': booking.status,
                    'payment': booking.payment,
                    'seat_numbers': [],
                    'passengers': [],
                    'total_fare': 0,
                    'journey_type': j_type,
                    'round_trip_id': str(rt_id) if rt_id else None,
                    'dep_bus': None,
                    'ret_bus': None,
                    'dep_date': None,
                    'ret_date': None,
                    'dep_seats': [],
                    'ret_seats': [],
                }
                groups.append(group_by_key[key])

            group = group_by_key[key]
            group['booking_ids'].append(str(booking.id))
            group['seat_numbers'].append(booking.seat_number)

            p_dict = make_passenger_dict(booking)
            p_key = (p_dict['name'], p_dict['age'], p_dict['gender'])
            existing_p_keys = [(p['name'], p['age'], p['gender']) for p in group['passengers']]
            if p_key not in existing_p_keys:
                group['passengers'].append(p_dict)

            group['total_fare'] += booking.amount

            if j_type == 'ROUND_TRIP':
                if not group['dep_bus']:
                    group['dep_bus'] = booking.bus
                    group['dep_date'] = booking.travel_date
                    group['dep_seats'].append(booking.seat_number)
                    group['dep_booking_id'] = booking.id
                elif group['dep_bus'].id == booking.bus.id:
                    group['dep_seats'].append(booking.seat_number)
                else:
                    group['ret_bus'] = booking.bus
                    group['ret_date'] = booking.travel_date
                    group['ret_seats'].append(booking.seat_number)
                    if not group.get('ret_booking_id'):
                        group['ret_booking_id'] = booking.id

        for group in groups:
            group['seat_numbers_str'] = ", ".join(list(dict.fromkeys(group['seat_numbers'])))
            group['booking_ids_str'] = ",".join(group['booking_ids'])
            group['num_seats'] = len(group['seat_numbers'])
            group['dep_seats_str'] = ", ".join(list(dict.fromkeys(group['dep_seats'])))
            group['ret_seats_str'] = ", ".join(list(dict.fromkeys(group['ret_seats'])))

        return groups
    except Exception as e:
        logger.error(f"Error building order groups: {e}")
        return []

def split_orders_by_date(groups):
    try:
        today = date.today()
        upcoming = []
        past = []
        cancelled = []

        for group in groups:
            if group['status'] == 'cancelled':
                cancelled.append(group)
            elif group['status'] == 'completed' or group['travel_date'] < today:
                past.append(group)
            else:
                upcoming.append(group)

        return upcoming, past, cancelled
    except Exception as e:
        logger.error(f"Error splitting orders: {e}")
        return [], [], []


def create_pending_bookings(customer, bus, seats, travel_date, post_data):
    try:
        booking_ids = []

        for seat in seats:
            booking = Booking.objects.create(
                user=customer,
                bus=bus,
                seat_number=seat,
                passenger_name=post_data.get(f"passenger_name_{seat}", ""),
                passenger_age=int(post_data.get(f"passenger_age_{seat}", 0)),
                passenger_gender=post_data.get(f"passenger_gender_{seat}", ""),
                amount=bus.fare,
                travel_date=travel_date,
                status="booked",
                payment=False
            )
            booking_ids.append(str(booking.id))

        return booking_ids
    except Exception as e:
        logger.error(f"Error creating pending bookings: {e}")
        return []

def mark_bookings_paid(bookings, payment_id, order_id, signature):
    try:
        for booking in bookings:
            booking.payment = True
            booking.payment_status = "success"
            booking.booking_status = "booked"
            booking.status = "booked"
            booking.payment_id = payment_id
            booking.razorpay_order_id = order_id
            booking.razorpay_signature = signature
            booking.save()

            SeatBooking.objects.get_or_create(
                booking=booking,
                bus=booking.bus,
                seat_number=booking.seat_number,
                journey_date=booking.travel_date
            )
    except Exception as e:
        logger.error(f"Error marking bookings paid: {e}")

def mark_bookings_failed(bookings):
    try:
        for booking in bookings:
            booking.payment = False
            booking.payment_status = "failed"
            booking.booking_status = "cancelled"
            booking.status = "cancelled"
            booking.save()
    except Exception as e:
        logger.error(f"Error marking bookings failed: {e}")

#==========================================================================
#    Customer Views
#==========================================================================

def index(request):
    try:
        routes = Route.objects.all()
        sources = Bus.objects.values_list('source', flat=True).distinct().order_by('source')
        destinations = Bus.objects.values_list('destination', flat=True).distinct().order_by('destination')
        featured_reviews = Review.objects.filter(
            is_featured=True, is_active=True
        ).select_related('user', 'bus').order_by('-created_at')[:6]
        
        context = {
            'routes': routes,
            'sources': sources,
            'destinations': destinations,
            'featured_reviews': featured_reviews
        }
        return render(request, 'index.html', context)
    except Exception as e:
        logger.error(f"Error loading homepage: {e}")
        return HttpResponse("An error occurred loading the home page.")


def about(request):
    try:
        return render(request, 'about.html')
    except Exception as e:
        logger.error(f"Error in about view: {e}")
        return HttpResponse("An error occurred loading the page.")

def travel_guidelines(request):
    try:
        return render(request, 'travel_guidelines.html')
    except Exception as e:
        logger.error(f"Error rendering travel guidelines page: {e}")
        return HttpResponse("An error occurred loading the travel guidelines page.")

def contact(request):
    if request.method == 'POST':
        # print(request.POST)  # Debug
        # print("Name:", request.POST.get('name'))
        # print("Email:", request.POST.get('email'))
        # print("Phone:", request.POST.get('phone'))
        # print("Subject:", request.POST.get('subject'))
        # print("Message:", request.POST.get('message'))
        try:
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            subject = request.POST.get('subject', '').strip()
            message = request.POST.get('message', '').strip()

            if not name or not email or not phone or not subject or not message:
                return render(request, 'contact.html', {'msg': 'All fields are required.'})

            Contact.objects.create(
                name=name,
                email=email,
                phone=phone,
                subject=subject,
                message=message
            )
            send_mail(
    subject=f"New Contact Message: {subject}",
    message=f"""
New Contact Form Submission

Name: {name}
Email: {email}
Phone: {phone}

Subject:
{subject}

Message:
{message}
""",
    from_email=settings.EMAIL_HOST_USER,
    recipient_list=[settings.EMAIL_HOST_USER],   # Admin Email
    fail_silently=False,
)
            success_msg = "Message Sent! Our support team will get back to you within 24 hours."
            return render(request, 'contact.html', {'msg': success_msg})
        except Exception as e:
            logger.error(f"Error saving contact message: {e}")
            error_msg = "Something went wrong. Please try again."
            return render(request, 'contact.html', {'msg': error_msg})

    return render(request, 'contact.html')

def contact_message(request):
    # Login Check
    if 'email' not in request.session:
        return redirect('login')
    try:
        user = User.objects.get(email=request.session['email'])
        if user.usertype not in ['admin', 'manager']:
            return redirect('index')
        contacts_list = Contact.objects.all().order_by('-id')
        paginator = Paginator(contacts_list, 2)
        page = request.GET.get('page', 1)
        try:
            contacts = paginator.page(page)
        except PageNotAnInteger:
            contacts = paginator.page(1)
        except EmptyPage:
            contacts = paginator.page(paginator.num_pages)

        context = {
            'user': user,
            'contacts': contacts,
            'page_obj': contacts,
        }
        return render(request, 'contact_messages.html', context)
    except User.DoesNotExist:
        return redirect('login')
    except Exception as e:
        logger.error(f"Error loading contact messages: {e}")
        context = {
            'user': None,
            'contacts': [],
            'msg': "Something went wrong. Please try again."
        }
        return render(request, 'contact_messages.html', context)
      
def register(request):
    if request.method == "POST":
        try:
            name = request.POST.get("name", "").strip()
            email = request.POST.get("email", "").strip()
            phone = request.POST.get("mobile", "").strip()
            password = request.POST.get("password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()
            usertype = request.POST.get("usertype", "customer").strip()
            profile = request.FILES.get("profile")

            if not name or not email or not phone or not password or not confirm_password:
                return render(request, "register.html", {"msg": "All fields are required."})

            if User.objects.filter(email=email).exists():
                return render(request, "register.html", {"msg": "An account with this email already exists."})

            if User.objects.filter(phone=phone).exists():
                return render(request, "register.html", {"msg": "An account with this mobile number already exists."})

            if password != confirm_password:
                return render(request, "register.html", {"msg": "Password and Confirm Password do not match."})

            User.objects.create(
                name=name,
                email=email,
                phone=phone,
                password=password,
                profile=profile,
                usertype=usertype
            )

            # Send welcome email notification
            sys_settings = SystemSettings.get_settings()
            welcome_subject = f"Welcome to {sys_settings.app_name}"
            welcome_message = f"Hello {name},\nWelcome to {sys_settings.app_name}!\nYour account has been created successfully.\nA welcome bonus of Rs. {sys_settings.welcome_bonus:g} has been added to your wallet!\nLogin Email: {email}\nRegards,\n{sys_settings.app_name} Team"
            try:
                send_mail(
                    welcome_subject,
                    welcome_message,
                    settings.EMAIL_HOST_USER,
                    [email],
                    fail_silently=False
                )
            except Exception as mail_err:
                logger.error(f"Welcome email could not be sent to {email}: {mail_err}")


            success_msg = "Registration completed successfully. You can now log in."
            return render(request, "register.html", {"msg1": success_msg})
        except Exception as e:
            logger.error(f"Registration Error: {e}")
            return render(request, "register.html", {"msg": "Something went wrong. Please try again."})

    return render(request, "register.html")

@csrf_exempt
def login(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        try:
            # Step 1: Check if the user with this email exists
            user = User.objects.get(email=email)

            # Step 2: Validate password
            if user.password == password:
                # Step 3: Set up the session — no OTP needed
                request.session['email'] = user.email
                request.session['name'] = user.name
                request.session['profile'] = user.profile.url if user.profile else ''
                request.session['usertype'] = user.usertype

                # Step 4: Redirect based on user role
                if user.usertype == 'customer':
                    return redirect('index')
                elif user.usertype == 'manager':
                    return redirect('manager_dashboard')
                else:
                    return redirect('admin_dashboard')
            else:
                return render(request, 'login.html', {'msg': "Password doesn't match..!"})

        except User.DoesNotExist:
            return render(request, 'login.html', {'msg': "Email doesn't exist..!"})
        except Exception as e:
            logger.error(f"Login Error: {e}")
            return render(request, 'login.html', {'msg': "Something went wrong. Please try again."})

    return render(request, 'login.html')

def forgot_password(request):
    if request.method == "POST":
        try:
            email = request.POST.get("email", "").strip()
            user = User.objects.get(email=email)
            otp = random.randint(100000, 999999)
            request.session['forgot_email'] = email
            request.session['forgot_otp'] = str(otp)

            logger.info(f"Forgot password OTP generated for {email}: {otp}")

            try:
                send_mail(
                    "BusYatra Reset Password OTP",
                    f"Hello {user.name},\n\nYour OTP to reset password is: {otp}\n\nDo not share this OTP with anyone.\n\nBusYatra Team",
                    settings.EMAIL_HOST_USER,
                    [email],
                    fail_silently=False,
                )
            except Exception as email_err:
                logger.error(f"Forgot password OTP email could not be sent: {email_err}")

            return redirect('verify_forgot_otp')
        except User.DoesNotExist:
            return render(request, "forgot_password.html", {"msg": "Email doesn't exist..!"})
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            return render(request, "forgot_password.html", {"msg": "Something went wrong. Please try again."})

    return render(request, "forgot_password.html")

def verify_forgot_otp(request):
    if request.method == "POST":
        try:
            user_otp = request.POST.get("otp", "").strip()
            session_otp = request.session.get("forgot_otp")
            email = request.session.get("forgot_email")

            if not email or not session_otp:
                return redirect("login")

            if user_otp == session_otp:
                request.session['otp_verified'] = True
                return redirect("reset_password")
            else:
                return render(request, "verify_forgot_otp.html", {"msg": "Invalid OTP. Please enter the correct OTP."})
        except Exception as e:
            logger.error(f"Verify Forgot OTP error: {e}")
            return render(request, "verify_forgot_otp.html", {"msg": "Something went wrong. Please try again."})

    return render(request, "verify_forgot_otp.html")

def reset_password(request):
    if 'forgot_email' not in request.session or not request.session.get('otp_verified'):
        return redirect("login")

    if request.method == "POST":
        try:
            password = request.POST.get("password", "").strip()
            confirm_password = request.POST.get("confirm_password", "").strip()
            email = request.session.get("forgot_email")

            if not password or not confirm_password:
                return render(request, "reset_password.html", {"msg": "All fields are required."})

            if password != confirm_password:
                return render(request, "reset_password.html", {"msg": "Password and Confirm Password do not match."})

            user = User.objects.get(email=email)
            user.password = password
            user.save()

            if 'forgot_email' in request.session:
                del request.session['forgot_email']
            if 'forgot_otp' in request.session:
                del request.session['forgot_otp']
            if 'otp_verified' in request.session:
                del request.session['otp_verified']

            return render(request, "login.html", {"success": "Password reset successful! Please login with your new password."})
        except Exception as e:
            logger.error(f"Reset Password error: {e}")
            return render(request, "reset_password.html", {"msg": "Something went wrong. Please try again."})

    return render(request, "reset_password.html")

def logout(request):
    try:
        request.session.flush()
    except Exception as e:
        logger.error(f"Error during logout: {e}")
    return redirect('login')

def account(request):
    email = request.session.get('email')
    if not email:
        return redirect('login')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        try:
            user.name = request.POST.get('name', user.name)
            user.phone = request.POST.get('mobile', user.phone)
            if 'profile' in request.FILES:
                user.profile = request.FILES['profile']
            user.save()
            request.session['profile'] = user.profile.url if user.profile else ''

            if user.usertype == 'customer':
                return redirect('index')
            elif user.usertype == 'manager':
                return redirect('manager_dashboard')
            else:
                return redirect('admin_dashboard')
        except Exception as e:
            logger.error(f"Account Update Error: {e}")
            return render(request, 'account.html', {'user': user, 'msg': 'Error updating details.'})

    return render(request, 'account.html', {'user': user})

def delete_account(request):
    email = request.session.get('email')
    if email:
        try:
            user = User.objects.get(email=email)
            user.delete()
        except User.DoesNotExist:
            pass
    request.session.flush()
    return redirect('login')

def bus_list(request):
    search = get_search_details(request)

    if search.get('round_trip') and search['from_city'] and search['to_city']:
        dep_buses = list(Bus.objects.filter(
            source__iexact=search['from_city'],
            destination__iexact=search['to_city']
        ).order_by('id'))

        ret_buses = list(Bus.objects.filter(
            source__iexact=search['to_city'],
            destination__iexact=search['from_city']
        ).order_by('id'))

        set_live_available_seats(dep_buses, search['travel_date'])
        set_live_available_seats(ret_buses, search['return_date'])

        return render(request, 'bus_list.html', {
            'dep_buses': dep_buses,
            'ret_buses': ret_buses,
            'from_city': search['from_city'],
            'to_city': search['to_city'],
            'travel_date': search['travel_date'],
            'return_date': search['return_date'],
            'passengers': search['passengers'],
            'round_trip': True,
        })

    buses = Bus.objects.all().order_by('id')

    if search['from_city'] and search['to_city']:
        buses = buses.filter(
            source__iexact=search['from_city'],
            destination__iexact=search['to_city']
        )
    elif search['from_city']:
        buses = buses.filter(source__iexact=search['from_city'])
    elif search['to_city']:
        buses = buses.filter(destination__iexact=search['to_city'])

    class CustomPage(Page):
        def count(self):
            return len(self.object_list)

    class CustomPaginator(Paginator):
        def _get_page(self, *args, **kwargs):
            return CustomPage(*args, **kwargs)

    paginator = CustomPaginator(buses, 5)
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        try:
            page_number = int(page_number)
            page_obj = paginator.page(1 if page_number < 1 else paginator.num_pages)
        except (ValueError, TypeError):
            page_obj = paginator.page(1)

    set_live_available_seats(page_obj.object_list, search['travel_date'])

    return render(request, 'bus_list.html', {
        'buses': page_obj,
        'from_city': search['from_city'],
        'to_city': search['to_city'],
        'travel_date': search['travel_date'],
        'return_date': search['return_date'],
        'passengers': search['passengers'],
        'round_trip': False,
    })

def bus_detail(request, pk):
    try:
        bus = Bus.objects.get(id=pk)
    except Bus.DoesNotExist:
        return redirect('bus_list')

    search = get_search_details(request)
    set_live_available_seats([bus], search['travel_date'])

    reviews = Review.objects.filter(bus=bus, is_active=True).select_related('user', 'booking').order_by('-created_at')
    
    stats = reviews.aggregate(
        avg_rating=Avg('rating'),
        total_reviews=Count('id'),
        star_5=Count('id', filter=Q(rating=5)),
        star_4=Count('id', filter=Q(rating=4)),
        star_3=Count('id', filter=Q(rating=3)),
        star_2=Count('id', filter=Q(rating=2)),
        star_1=Count('id', filter=Q(rating=1)),
    )

    avg_rating = round(stats['avg_rating'], 1) if stats['avg_rating'] else 0.0
    total_reviews = stats['total_reviews'] or 0

    def get_pct(count):
        return round((count / total_reviews) * 100) if total_reviews > 0 else 0

    star_breakdown = [
        {'stars': 5, 'count': stats['star_5'] or 0, 'pct': get_pct(stats['star_5'] or 0)},
        {'stars': 4, 'count': stats['star_4'] or 0, 'pct': get_pct(stats['star_4'] or 0)},
        {'stars': 3, 'count': stats['star_3'] or 0, 'pct': get_pct(stats['star_3'] or 0)},
        {'stars': 2, 'count': stats['star_2'] or 0, 'pct': get_pct(stats['star_2'] or 0)},
        {'stars': 1, 'count': stats['star_1'] or 0, 'pct': get_pct(stats['star_1'] or 0)},
    ]

    return render(request, 'bus_detail.html', {
        'bus': bus,
        'from_city': search['from_city'],
        'to_city': search['to_city'],
        'travel_date': search['travel_date'],
        'passengers': search['passengers'],
        'reviews': reviews,
        'avg_rating': avg_rating,
        'total_reviews': total_reviews,
        'star_breakdown': star_breakdown,
    })


def seat_booking(request, pk=None):
    customer = get_customer_user(request)
    if not customer:
        return redirect("login")

    try:
        is_round_trip = (request.GET.get("round_trip") == "1" or request.POST.get("round_trip") == "1" or bool(request.GET.get("ret_bus_id")) or bool(request.POST.get("ret_bus_id")))

        if is_round_trip:
            dep_bus_id = request.GET.get("dep_bus_id") or request.POST.get("dep_bus_id") or pk
            ret_bus_id = request.GET.get("ret_bus_id") or request.POST.get("ret_bus_id")

            dep_bus = Bus.objects.filter(id=dep_bus_id).first() if dep_bus_id else None
            ret_bus = Bus.objects.filter(id=ret_bus_id).first() if ret_bus_id else None

            if not dep_bus or not ret_bus:
                return redirect("bus_list")

            raw_dep_date = request.GET.get("date") or request.POST.get("date") or request.session.get("journey_date")
            raw_ret_date = request.GET.get("return_date") or request.POST.get("return_date") or request.session.get("return_date")

            travel_date = raw_dep_date if is_valid_date(raw_dep_date) else date.today().strftime("%Y-%m-%d")
            return_date = raw_ret_date if (is_valid_date(raw_ret_date) and raw_ret_date >= travel_date) else travel_date

            request.session["journey_date"] = travel_date
            request.session["return_date"] = return_date

            passengers_count = int(request.GET.get("passengers") or request.POST.get("passengers") or "1")

            if request.method == "POST":
                dep_selected_seats = request.POST.get("dep_selected_seats", "")
                ret_selected_seats = request.POST.get("ret_selected_seats", "")

                dep_seats = [seat.strip() for seat in dep_selected_seats.split(",") if seat.strip()]
                ret_seats = [seat.strip() for seat in ret_selected_seats.split(",") if seat.strip()]

                if len(dep_seats) != passengers_count or len(ret_seats) != passengers_count:
                    return render(request, "seat_booking.html", {
                        "is_round_trip": True,
                        "dep_bus": dep_bus,
                        "ret_bus": ret_bus,
                        "bus": dep_bus,
                        "travel_date": travel_date,
                        "return_date": return_date,
                        "passengers_count": passengers_count,
                        "booked_seats": json.dumps(get_booked_seats(dep_bus, travel_date)),
                        "dep_booked_seats": json.dumps(get_booked_seats(dep_bus, travel_date)),
                        "ret_booked_seats": json.dumps(get_booked_seats(ret_bus, return_date)),
                        "msg": f"Please select exactly {passengers_count} departure seat(s) and {passengers_count} return seat(s)."
                    })

                dep_already_booked = SeatBooking.objects.filter(bus=dep_bus, journey_date=travel_date, seat_number__in=dep_seats).exists()
                ret_already_booked = SeatBooking.objects.filter(bus=ret_bus, journey_date=return_date, seat_number__in=ret_seats).exists()

                if dep_already_booked or ret_already_booked:
                    return render(request, "seat_booking.html", {
                        "is_round_trip": True,
                        "dep_bus": dep_bus,
                        "ret_bus": ret_bus,
                        "bus": dep_bus,
                        "travel_date": travel_date,
                        "return_date": return_date,
                        "passengers_count": passengers_count,
                        "booked_seats": json.dumps(get_booked_seats(dep_bus, travel_date)),
                        "dep_booked_seats": json.dumps(get_booked_seats(dep_bus, travel_date)),
                        "ret_booked_seats": json.dumps(get_booked_seats(ret_bus, return_date)),
                        "msg": "One or more selected seats are no longer available. Please select different seats."
                    })

                with transaction.atomic():
                    rt_id = uuid.uuid4()
                    created_booking_ids = []

                    for i in range(1, passengers_count + 1):
                        p_name = request.POST.get(f"passenger_name_{i}", f"Passenger {i}").strip() or f"Passenger {i}"
                        p_age_str = request.POST.get(f"passenger_age_{i}", "25").strip()
                        p_age = int(p_age_str) if p_age_str.isdigit() and int(p_age_str) > 0 else 25
                        p_gender = request.POST.get(f"passenger_gender_{i}", "Male").strip() or "Male"

                        b_dep = Booking.objects.create(
                            user=customer,
                            bus=dep_bus,
                            seat_number=dep_seats[i - 1],
                            passenger_name=p_name,
                            passenger_age=p_age,
                            passenger_gender=p_gender,
                            amount=dep_bus.fare,
                            travel_date=travel_date,
                            journey_type="ROUND_TRIP",
                            round_trip_id=rt_id,
                            status="booked",
                            payment=False
                        )
                        created_booking_ids.append(str(b_dep.id))

                        b_ret = Booking.objects.create(
                            user=customer,
                            bus=ret_bus,
                            seat_number=ret_seats[i - 1],
                            passenger_name=p_name,
                            passenger_age=p_age,
                            passenger_gender=p_gender,
                            amount=ret_bus.fare,
                            travel_date=return_date,
                            journey_type="ROUND_TRIP",
                            round_trip_id=rt_id,
                            status="booked",
                            payment=False
                        )
                        created_booking_ids.append(str(b_ret.id))

                return redirect(f"/payment/?booking_ids={','.join(created_booking_ids)}&round_trip=1")

            return render(request, "seat_booking.html", {
                "is_round_trip": True,
                "dep_bus": dep_bus,
                "ret_bus": ret_bus,
                "bus": dep_bus,
                "travel_date": travel_date,
                "return_date": return_date,
                "passengers_count": passengers_count,
                "booked_seats": json.dumps(get_booked_seats(dep_bus, travel_date)),
                "dep_booked_seats": json.dumps(get_booked_seats(dep_bus, travel_date)),
                "ret_booked_seats": json.dumps(get_booked_seats(ret_bus, return_date)),
            })

        bus = Bus.objects.get(id=pk) if pk else Bus.objects.first()
        if not bus:
            return redirect("bus_list")

        raw_date = request.GET.get("date") or request.POST.get("date") or request.session.get("journey_date")
        if is_valid_date(raw_date):
            travel_date = raw_date
        else:
            travel_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        request.session["journey_date"] = travel_date

        if request.method == "POST":
            selected_seats = request.POST.get("selected_seats", "")
            seats = [seat.strip() for seat in selected_seats.split(",") if seat.strip()]

            if not seats:
                return redirect(f"/seat_booking/{bus.id}/")

            already_booked = SeatBooking.objects.filter(
                bus=bus,
                journey_date=travel_date,
                seat_number__in=seats
            ).exists()

            if already_booked:
                return render(request, "seat_booking.html", {
                    "bus": bus,
                    "travel_date": travel_date,
                    "booked_seats": json.dumps(get_booked_seats(bus, travel_date)),
                    "msg": "Selected seat already booked."
                })

            booking_ids = create_pending_bookings(customer, bus, seats, travel_date, request.POST)
            return redirect(f"/payment/?booking_ids={','.join(booking_ids)}")

        return render(request, "seat_booking.html", {
            "bus": bus,
            "travel_date": travel_date,
            "booked_seats": json.dumps(get_booked_seats(bus, travel_date))
        })
    except Exception as e:
        logger.error(f"Seat Booking Error: {e}")
        return HttpResponse(f"Error occurred: {e}")

def dashboard(request):
    try:
        customer = get_customer_user(request)
        if not customer:
            return redirect('login')
        return render(request, 'dashboard.html')
    except Exception as e:
        logger.error(f"Error in dashboard view: {e}")
        return redirect('login')

def my_orders(request):
    customer = get_customer_user(request)
    if not customer:
        return redirect('login')

    try:
        bookings = Booking.objects.filter(user=customer).order_by('-id')
        grouped_bookings = build_order_groups(bookings)
        upcoming, past, cancelled = split_orders_by_date(grouped_bookings)

        # Attach review status to past bookings
        user_reviews = {r.booking_id: r for r in Review.objects.filter(user=customer)}
        today_date = date.today()

        for group in past:
            j_type = group.get('journey_type', 'ONE_WAY')
            if j_type == 'ROUND_TRIP':
                dep_id = group.get('dep_booking_id') or group['id']
                group['dep_booking_id'] = dep_id
                group['dep_review'] = user_reviews.get(dep_id)
                group['dep_can_review'] = bool(group['payment'] and group['status'] != 'cancelled' and group.get('dep_date', group['travel_date']) <= today_date and not group['dep_review'])

                ret_id = group.get('ret_booking_id')
                group['ret_booking_id'] = ret_id
                group['ret_review'] = user_reviews.get(ret_id) if ret_id else None
                group['ret_can_review'] = bool(group['payment'] and group['status'] != 'cancelled' and group.get('ret_date') and group['ret_date'] <= today_date and not group['ret_review']) if ret_id else False
            else:
                primary_id = group['id']
                group['primary_booking_id'] = primary_id
                group['review'] = user_reviews.get(primary_id)
                group['can_review'] = bool(group['payment'] and group['status'] != 'cancelled' and group['travel_date'] <= today_date and not group['review'])

        active_tab = request.GET.get('tab', 'upcoming')
        if active_tab not in ['upcoming', 'past', 'cancelled']:
            active_tab = 'upcoming'

        def paginate_list(item_list, param_name):
            paginator = Paginator(item_list, 3)
            page_val = request.GET.get(param_name) or (request.GET.get('page') if active_tab == param_name.replace('_page', '') else 1)
            try:
                page_obj = paginator.page(page_val)
            except PageNotAnInteger:
                page_obj = paginator.page(1)
            except EmptyPage:
                try:
                    page_num = int(page_val)
                    page_obj = paginator.page(1 if page_num < 1 else paginator.num_pages)
                except (ValueError, TypeError):
                    page_obj = paginator.page(1)
            return page_obj

        upcoming_page_obj = paginate_list(upcoming, 'upcoming_page')
        past_page_obj = paginate_list(past, 'past_page')
        cancelled_page_obj = paginate_list(cancelled, 'cancelled_page')

        return render(request, 'my-orders.html', {
            'user': customer,
            'bookings': grouped_bookings,
            'upcoming_bookings': upcoming_page_obj,
            'past_bookings': past_page_obj,
            'cancelled_bookings': cancelled_page_obj,
            'upcoming_page_obj': upcoming_page_obj,
            'past_page_obj': past_page_obj,
            'cancelled_page_obj': cancelled_page_obj,
            'active_tab': active_tab,
        })
    except Exception as e:
        logger.error(f"My Orders View Error: {e}")
        return HttpResponse("An error occurred loading bookings.")


#==========================================================================
#    Reviews & Ratings Views
#==========================================================================

def add_review(request, booking_id):
    customer = get_customer_user(request)
    if not customer:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Please login to submit a review.'}, status=401)
        messages.error(request, 'Please login to submit a review.', extra_tags='customer_review')
        return redirect('login')

    try:
        booking = Booking.objects.select_related('bus', 'user').get(id=booking_id, user=customer)
    except Booking.DoesNotExist:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Booking not found or unauthorized.'}, status=404)
        messages.error(request, 'Booking not found or unauthorized.', extra_tags='customer_review')
        return redirect('my_orders')

    today_date = date.today()

    if not booking.payment:
        msg = "Only paid bookings are eligible for review."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg, extra_tags='customer_review')
        return redirect('my_orders')

    if booking.status == 'cancelled':
        msg = "Cancelled bookings cannot be reviewed."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg, extra_tags='customer_review')
        return redirect('my_orders')

    if booking.travel_date > today_date:
        msg = "You can only review a booking after completing your journey."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg, extra_tags='customer_review')
        return redirect('my_orders')

    if hasattr(booking, 'review') or Review.objects.filter(booking=booking).exists():
        msg = "You have already submitted a review for this booking."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg, extra_tags='customer_review')
        return redirect('my_orders')

    if request.method == 'POST':
        try:
            rating_str = request.POST.get('rating', '').strip()
            comment = request.POST.get('comment', '').strip()

            if not rating_str or not rating_str.isdigit():
                msg = "Please select a valid star rating (1 to 5)."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': msg}, status=400)
                messages.error(request, msg, extra_tags='customer_review')
                return redirect('my_orders')

            rating = int(rating_str)
            if rating < 1 or rating > 5:
                msg = "Rating must be between 1 and 5 stars."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': msg}, status=400)
                messages.error(request, msg, extra_tags='customer_review')
                return redirect('my_orders')

            if not comment:
                msg = "Please enter a comment for your review."
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': msg}, status=400)
                messages.error(request, msg, extra_tags='customer_review')
                return redirect('my_orders')

            review = Review.objects.create(
                user=customer,
                bus=booking.bus,
                booking=booking,
                rating=rating,
                comment=comment
            )

            success_msg = "Thank you! Your review has been submitted successfully."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_msg, 'review_id': review.id, 'rating': review.rating})
            messages.success(request, success_msg, extra_tags='customer_review')
            return redirect('/my-orders/?tab=past')
        except Exception as e:
            logger.error(f"Error submitting review: {e}")
            msg = "An error occurred while submitting your review. Please try again."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': msg}, status=500)
            messages.error(request, msg, extra_tags='customer_review')
            return redirect('my_orders')

    return redirect('/my-orders/?tab=past')



def edit_review(request, review_id):
    customer = get_customer_user(request)
    if not customer:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Please login.'}, status=401)
        messages.error(request, 'Please login.')
        return redirect('login')

    try:
        review = Review.objects.get(id=review_id, user=customer)
    except Review.DoesNotExist:
        msg = "Review not found or unauthorized."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=404)
        messages.error(request, msg)
        return redirect('my_orders')

    if request.method == 'POST':
        try:
            rating_str = request.POST.get('rating', '').strip()
            comment = request.POST.get('comment', '').strip()

            if rating_str and rating_str.isdigit():
                rating = int(rating_str)
                if 1 <= rating <= 5:
                    review.rating = rating

            if comment:
                review.comment = comment

            review.save()
            success_msg = "Your review has been updated successfully."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_msg})
            messages.success(request, success_msg)
            return redirect('/my-orders/?tab=past')
        except Exception as e:
            logger.error(f"Error editing review: {e}")
            msg = "An error occurred while updating your review."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': msg}, status=500)
            messages.error(request, msg)
            return redirect('my_orders')

    return redirect('/my-orders/?tab=past')


def delete_review(request, review_id):
    customer = get_customer_user(request)
    if not customer:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Please login.'}, status=401)
        messages.error(request, 'Please login.')
        return redirect('login')

    try:
        review = Review.objects.get(id=review_id, user=customer)
    except Review.DoesNotExist:
        msg = "Review not found or unauthorized."
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg}, status=404)
        messages.error(request, msg)
        return redirect('my_orders')

    if request.method == 'POST':
        try:
            review.delete()
            success_msg = "Your review has been deleted."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': success_msg})
            messages.success(request, success_msg)
            return redirect('/my-orders/?tab=past')
        except Exception as e:
            logger.error(f"Error deleting review: {e}")
            msg = "An error occurred while deleting your review."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': msg}, status=500)
            messages.error(request, msg)
            return redirect('my_orders')

    return redirect('/my-orders/?tab=past')


def payment(request):
    customer = get_customer_user(request)
    if not customer:
        return redirect("login")

    try:
        booking_ids = request.GET.get("booking_ids")
        bookings = get_customer_bookings(customer, booking_ids)
        if not bookings.exists():
            return redirect("index")

        is_round_trip = any(getattr(b, 'journey_type', 'ONE_WAY') == 'ROUND_TRIP' for b in bookings) or request.GET.get("round_trip") == "1"

        if is_round_trip:
            first_b = bookings.first()
            dep_bookings = [b for b in bookings if b.bus.source.lower() == first_b.bus.source.lower()]
            ret_bookings = [b for b in bookings if b.bus.source.lower() != first_b.bus.source.lower()]
            if not ret_bookings and len(bookings) > 1:
                half = len(bookings) // 2
                dep_bookings = list(bookings)[:half]
                ret_bookings = list(bookings)[half:]

            dep_bus = dep_bookings[0].bus if dep_bookings else first_b.bus
            ret_bus = ret_bookings[0].bus if ret_bookings else None
            dep_seats = ", ".join(list(dict.fromkeys([b.seat_number for b in dep_bookings]))) if dep_bookings else ""
            ret_seats = ", ".join(list(dict.fromkeys([b.seat_number for b in ret_bookings]))) if ret_bookings else ""
            dep_date = dep_bookings[0].travel_date if dep_bookings else first_b.travel_date
            ret_date = ret_bookings[0].travel_date if ret_bookings else None
        else:
            dep_bookings = None
            ret_bookings = None
            dep_bus = bookings.first().bus
            ret_bus = None
            dep_seats = ", ".join([b.seat_number for b in bookings])
            ret_seats = ""
            dep_date = bookings.first().travel_date
            ret_date = None

        subtotal, gst_fees, convenience_fee, total_price = calculate_payment_summary(bookings)
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        is_mock = False
        try:
            payment_order = client.order.create({
                "amount": int(total_price * 100),
                "currency": "INR",
                "payment_capture": 1
            })
        except Exception as razorpay_err:
            is_mock = True
            payment_order = {
                "id": f"mock_order_{random.randint(100000, 999999)}",
                "amount": int(total_price * 100),
                "currency": "INR",
            }
            logger.warning(f"Razorpay fallback to mock: {razorpay_err}")

        return render(request, "payment.html", {
            "bookings": bookings,
            "booking_ids": booking_ids,
            "bus": dep_bus,
            "dep_bus": dep_bus,
            "ret_bus": ret_bus,
            "travel_date": dep_date,
            "dep_date": dep_date,
            "ret_date": ret_date,
            "seats": dep_seats,
            "dep_seats": dep_seats,
            "ret_seats": ret_seats,
            "is_round_trip": is_round_trip,
            "subtotal": subtotal,
            "gst_fees": gst_fees,
            "convenience_fee": convenience_fee,
            "total_price": total_price,
            "payment": payment_order,
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "is_mock": is_mock,
        })
    except Exception as e:
        logger.error(f"Payment Initialization Error: {e}")
        return HttpResponse(f"Error occurred: {e}")
    
def generate_ticket_pdf_bytes(bookings):
    import qrcode

    def format_time(t):
        if not t: return ""
        if isinstance(t, str): return t
        try: return t.strftime('%I:%M %p')
        except Exception: return str(t)

    def format_date(d):
        if not d: return ""
        if isinstance(d, str): return d
        try: return d.strftime('%d-%b-%Y')
        except Exception: return str(d)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    brand_style = ParagraphStyle(
        'BrandTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=22, leading=26, textColor=HexColor('#0F172A')
    )
    tagline_style = ParagraphStyle(
        'BrandTagline', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=11, textColor=HexColor('#475569')
    )
    receipt_title_style = ParagraphStyle(
        'ReceiptTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, leading=22, alignment=2, textColor=HexColor('#3B82F6')
    )
    receipt_meta_style = ParagraphStyle(
        'ReceiptMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, alignment=2, textColor=HexColor('#64748B')
    )
    section_heading_style = ParagraphStyle(
        'SectionHeading', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=HexColor('#0F172A'), spaceBefore=8, spaceAfter=4
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=HexColor('#475569')
    )
    value_style = ParagraphStyle(
        'Value', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, textColor=HexColor('#0F172A')
    )
    route_style = ParagraphStyle(
        'RouteStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13, alignment=0, textColor=HexColor('#0F172A')
    )
    qr_text_style = ParagraphStyle(
        'QRText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=1, textColor=HexColor('#64748B')
    )
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=0, textColor=colors.white
    )
    table_cell_style = ParagraphStyle(
        'TableCell', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, alignment=0, textColor=HexColor('#0F172A')
    )
    footer_text_style = ParagraphStyle(
        'FooterText', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, alignment=1, textColor=HexColor('#475569')
    )
    thankyou_style = ParagraphStyle(
        'ThankYouText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, alignment=1, textColor=HexColor('#0F172A'), spaceBefore=10, spaceAfter=5
    )
    terms_style = ParagraphStyle(
        'TermsText', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=11, textColor=HexColor('#475569')
    )

    elements = []
    first_b = bookings.first()

    logo_path = finders.find('assets/images/logo.png')
    if logo_path:
        try:
            logo_element = Image(logo_path, width=110, height=35)
        except Exception:
            logo_element = Paragraph("<b>BusYatra</b>", brand_style)
    else:
        logo_element = Paragraph("<b>BusYatra</b>", brand_style)

    header_left_data = [
        [logo_element],
        [Paragraph("Premium Bus Ticket Reservation", tagline_style)]
    ]
    header_left_table = Table(header_left_data, colWidths=[270])
    header_left_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))

    booking_date_str = format_date(first_b.booking_date)
    is_round_trip = any(getattr(b, 'journey_type', 'ONE_WAY') == 'ROUND_TRIP' for b in bookings) or len(set(b.bus.id for b in bookings)) > 1

    header_right_data = [
        [Paragraph("Round Trip E-Ticket" if is_round_trip else "E-Ticket Receipt", receipt_title_style)],
        [Paragraph(f"Booking Date: {booking_date_str}", receipt_meta_style)]
    ]
    header_right_table = Table(header_right_data, colWidths=[270])
    header_right_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))

    header_table = Table([[header_left_table, header_right_table]], colWidths=[270, 270])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(header_table)

    divider = Table([['']], colWidths=[540])
    divider.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, HexColor('#E2E8F0')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 8))

    def build_journey_section(journey_title, b_list):
        if not b_list: return
        b_first = b_list[0]
        b_bus = b_first.bus
        dep_time_str = format_time(b_bus.departure_time)
        arr_time_str = format_time(b_bus.arrival_time)
        trv_date_str = format_date(b_first.travel_date)

        r_html = f"<font size=10><b>{b_bus.source}</b></font> <font size=10 color='#3B82F6'><b>→</b></font> <font size=10><b>{b_bus.destination}</b></font>"
        r_p = Paragraph(r_html, route_style)

        j_left = [
            [Paragraph("<b>Route:</b>", label_style), r_p],
            [Paragraph("<b>Bus Name:</b>", label_style), Paragraph(b_bus.bus_name, value_style)],
            [Paragraph("<b>Bus Number:</b>", label_style), Paragraph(b_bus.bus_number, value_style)],
            [Paragraph("<b>Travel Date:</b>", label_style), Paragraph(trv_date_str, value_style)],
            [Paragraph("<b>Departure:</b>", label_style), Paragraph(dep_time_str, value_style)],
            [Paragraph("<b>Arrival:</b>", label_style), Paragraph(arr_time_str, value_style)],
        ]
        j_left_tbl = Table(j_left, colWidths=[100, 260])
        j_left_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        b_ids = [f"BY-{b.id}" for b in b_list]
        s_nums = [b.seat_number for b in b_list]
        p_names = [b.passenger_name for b in b_list]
        p_stat = getattr(b_first, 'payment_status', 'SUCCESS' if b_first.payment else 'FAILED').upper()
        b_stat = getattr(b_first, 'booking_status', b_first.status).upper()

        q_data = (
            f"Booking ID: {', '.join(b_ids)}\n"
            f"Passenger: {', '.join(p_names)}\n"
            f"Bus: {b_bus.bus_number}\n"
            f"Date: {trv_date_str}\n"
            f"Seat: {', '.join(s_nums)}\n"
            f"Payment: {p_stat}\n"
            f"Booking: {b_stat}"
        )
        qr = qrcode.QRCode(version=1, box_size=3, border=1)
        qr.add_data(q_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#0F172A", back_color="white")
        qr_buf = BytesIO()
        qr_img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        qr_flow = Image(qr_buf, width=95, height=95)

        j_right = [
            [qr_flow],
            [Paragraph("Show QR while Boarding", qr_text_style)]
        ]
        j_right_tbl = Table(j_right, colWidths=[150])
        j_right_tbl.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
        ]))

        j_sec_tbl = Table([[j_left_tbl, j_right_tbl]], colWidths=[380, 160])
        j_sec_tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))

        elements.append(Paragraph(journey_title, section_heading_style))
        elements.append(j_sec_tbl)
        elements.append(Spacer(1, 6))

    if is_round_trip:
        dep_b_list = [b for b in bookings if b.bus.source.lower() == first_b.bus.source.lower()]
        ret_b_list = [b for b in bookings if b.bus.source.lower() != first_b.bus.source.lower()]
        if not ret_b_list and len(bookings) > 1:
            half = len(bookings) // 2
            dep_b_list = list(bookings)[:half]
            ret_b_list = list(bookings)[half:]

        build_journey_section("Departure Journey", dep_b_list)
        build_journey_section("Return Journey", ret_b_list)
    else:
        build_journey_section("Journey Details", list(bookings))

    def make_badge(text, badge_type):
        bg = HexColor('#ECFDF5') if badge_type == 'success' else (HexColor('#FEF3C7') if badge_type == 'warning' else HexColor('#FEE2E2'))
        fg = HexColor('#047857') if badge_type == 'success' else (HexColor('#B45309') if badge_type == 'warning' else HexColor('#B91C1C'))
        b_p = ParagraphStyle('BadgeP', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=fg)
        bt = Table([[Paragraph(text, b_p)]], colWidths=[70], rowHeights=[16])
        bt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        return bt

    payment_status_str = getattr(first_b, 'payment_status', 'SUCCESS' if first_b.payment else 'FAILED').upper()
    booking_status_str = getattr(first_b, 'booking_status', first_b.status).upper()
    pay_badge = make_badge(payment_status_str, 'success' if payment_status_str in ['PAID', 'SUCCESS'] else ('warning' if payment_status_str == 'PENDING' else 'danger'))
    book_badge = make_badge(booking_status_str, 'success' if booking_status_str in ['BOOKED', 'SUCCESS', 'COMPLETED'] else 'danger')

    payment_id_val = first_b.payment_id or "N/A"
    sys_settings = SystemSettings.get_settings()
    subtotal = sum(b.amount for b in bookings)
    gst_fees = int((subtotal * sys_settings.gst_percentage) / 100)
    convenience_fee = int(sys_settings.convenience_fee) * len(bookings)
    total_amount = subtotal + gst_fees + convenience_fee


    payment_data = [
        [Paragraph("<b>Payment ID:</b>", label_style), Paragraph(payment_id_val, value_style), Paragraph("<b>Payment Status:</b>", label_style), pay_badge],
        [Paragraph("<b>Booking Status:</b>", label_style), book_badge, Paragraph("<b>Total Paid:</b>", label_style), Paragraph(f"Rs. {total_amount:.2f} (incl. GST & fees)", value_style)],
        [Paragraph("<b>Payment Method:</b>", label_style), Paragraph("Online (Razorpay)", value_style), Paragraph("", label_style), Paragraph("", value_style)]
    ]
    payment_table = Table(payment_data, colWidths=[100, 170, 100, 170])
    payment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    elements.append(Paragraph("Transaction Details", section_heading_style))
    elements.append(payment_table)
    elements.append(Spacer(1, 8))

    table_data = [[
        Paragraph("Booking ID", table_header_style),
        Paragraph("Journey", table_header_style),
        Paragraph("Passenger Name", table_header_style),
        Paragraph("Age", table_header_style),
        Paragraph("Gender", table_header_style),
        Paragraph("Seat No", table_header_style),
        Paragraph("Fare", table_header_style)
    ]]

    for b in bookings:
        j_label = f"{b.bus.source} → {b.bus.destination}"
        table_data.append([
            Paragraph(f"BY-{b.id}", table_cell_style),
            Paragraph(j_label, table_cell_style),
            Paragraph(b.passenger_name, table_cell_style),
            Paragraph(str(b.passenger_age), table_cell_style),
            Paragraph(b.passenger_gender, table_cell_style),
            Paragraph(b.seat_number, table_cell_style),
            Paragraph(f"Rs. {b.amount:.2f}", table_cell_style)
        ])

    passenger_table = Table(table_data, colWidths=[60, 120, 110, 30, 45, 55, 65])
    passenger_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#0F172A')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    elements.append(Paragraph("Passenger & Seat Details", section_heading_style))
    elements.append(passenger_table)
    elements.append(Spacer(1, 8))

    elements.append(Paragraph("Thank you for choosing BusYatra. Have a Safe Journey!", thankyou_style))
    elements.append(Spacer(1, 4))

    terms_html = (
        "<b>Terms & Conditions:</b><br/>"
        "• Carry a valid Government ID.<br/>"
        "• Reach boarding point at least 30 minutes before departure.<br/>"
        "• Keep this ticket until journey completion.<br/>"
        "• Ticket is non-transferable.<br/>"
        "• Cancellation and refund are subject to BusYatra policy.<br/>"
        "• Contact Support: <b>support@busyatra.com</b>"
    )
    terms_table = Table([[Paragraph(terms_html, terms_style)]], colWidths=[540])
    terms_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(terms_table)
    elements.append(Spacer(1, 8))

    footer_html = "BusYatra  •  Premium Bus Ticket Reservation  •  www.busyatra.com  •  support@busyatra.com"
    elements.append(Paragraph(footer_html, footer_text_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def ticket(request):
    customer = get_customer_user(request)
    if not customer:
        return redirect("login")

    try:
        booking_ids = request.GET.get("booking_ids")
        bookings = get_customer_bookings(customer, booking_ids)
        if not bookings.exists():
            return redirect("index")

        payment_id = request.GET.get("razorpay_payment_id")
        order_id = request.GET.get("razorpay_order_id")
        signature = request.GET.get("razorpay_signature")

        if payment_id or signature:
            verified = signature == "mock_sig"

            if not verified:
                client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
                try:
                    client.utility.verify_payment_signature({
                        'razorpay_order_id': order_id,
                        'razorpay_payment_id': payment_id,
                        'razorpay_signature': signature
                    })
                    verified = True
                except Exception as signature_err:
                    logger.error(f"Razorpay verification failed: {signature_err}")

            if not verified:
                mark_bookings_failed(bookings)
                return redirect("my_orders")

            mark_bookings_paid(bookings, payment_id, order_id, signature)

            try:
                from django.core.mail import EmailMessage
                pdf_bytes = generate_ticket_pdf_bytes(bookings)
                passenger_names = ", ".join([booking.passenger_name for booking in bookings])
                seat_numbers = ", ".join([booking.seat_number for booking in bookings])

                email_msg = EmailMessage(
                    subject="BusYatra Ticket Confirmation",
                    body=f"Dear {customer.name},\nThank you for choosing BusYatra. Your booking has been successfully confirmed!\nPassenger(s): {passenger_names}\nSeat(s): {seat_numbers}\nPlease find your attached e-ticket PDF containing details and guidelines.\nWarm regards,\nBusYatra Team",
                    from_email=settings.EMAIL_HOST_USER,
                    to=[bookings.first().user.email]
                )
                email_msg.attach('BusYatra_Ticket.pdf', pdf_bytes, 'application/pdf')
                email_msg.send()
            except Exception as email_err:
                logger.error(f"Failed to send confirmation email: {email_err}")

            return redirect(f"/ticket/?booking_ids={booking_ids}")

        subtotal = sum(booking.amount for booking in bookings)
        gst = int((subtotal * 5) / 100)

        return render(request, "ticket.html", {
            "bookings": bookings,
            "booking_ids_str": booking_ids,
            "subtotal": subtotal,
            "gst": gst,
            "total_amount": subtotal + gst,
        })
    except Exception as e:
        logger.error(f"Ticket Detail Page Error: {e}")
        return HttpResponse(f"Error occurred: {e}")

def download_ticket_pdf(request):
    customer = get_customer_user(request)
    if not customer:
        return redirect('login')

    try:
        booking_ids = request.GET.get("booking_ids")
        bookings = get_customer_bookings(customer, booking_ids)
        if not bookings.exists():
            return HttpResponse("No Booking Selected")

        pdf_bytes = generate_ticket_pdf_bytes(bookings)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        
        # Check if the ticket should be displayed inline for printing
        inline = request.GET.get("inline")
        if inline == "1" or inline == "true":
            response['Content-Disposition'] = 'inline; filename="BusYatra_Ticket.pdf"'
        else:
            response['Content-Disposition'] = 'attachment; filename="BusYatra_Ticket.pdf"'
        return response
    except Exception as e:
        logger.error(f"PDF Download Error: {e}")
        return HttpResponse("Error generating PDF")

#==========================================================================
#    Manager Views
#==========================================================================

def manager_bookings(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    buses = Bus.objects.filter(manager=manager)
    bookings_list = Booking.objects.filter(bus__in=buses).order_by('-booking_date')
    paginator = Paginator(bookings_list, 6)
    page = request.GET.get('page', 1)
    try:
        bookings = paginator.page(page)
    except PageNotAnInteger:
        bookings = paginator.page(1)
    except EmptyPage:
        bookings = paginator.page(paginator.num_pages)

    return render(request, 'manager-bookings.html', {'bookings': bookings, 'page_obj': bookings})

def manager_buses(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    buses_list = Bus.objects.filter(manager=manager).order_by('-id')
    paginator = Paginator(buses_list, 6)
    page = request.GET.get('page', 1)
    try:
        buses = paginator.page(page)
    except PageNotAnInteger:
        buses = paginator.page(1)
    except EmptyPage:
        buses = paginator.page(paginator.num_pages)

    return render(request, 'manager-buses.html', {'buses': buses, 'page_obj': buses})

def add_bus(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    if request.method == 'POST':
        try:
            bus_number = request.POST.get('bus_number', '').strip()
            
            # Prevent duplicate bus license registrations
            if Bus.objects.filter(bus_number=bus_number).exists():
                return render(request, 'add_bus.html', {'msg': 'Duplicate Bus Number should not be allowed.'})

            Bus.objects.create(
                manager=manager,
                bus_name=request.POST.get('bus_name', ''),
                bus_number=bus_number,
                bus_type=request.POST.get('bus_type', ''),
                source=request.POST.get('source', ''),
                destination=request.POST.get('destination', ''),
                departure_time=request.POST.get('departure_time'),
                arrival_time=request.POST.get('arrival_time'),
                total_seats=int(request.POST.get('total_seats', 0)),
                available_seats=int(request.POST.get('available_seats', 0)),
                fare=float(request.POST.get('fare', 0.0)),
                image=request.FILES.get('image', '')
            )
            return redirect('manager_buses')
        except Exception as e:
            logger.error(f"Error adding bus: {e}")
            return render(request, 'add_bus.html', {'msg': 'Error saving details. Please try again.'})

    return render(request, 'add_bus.html')

def edit_bus(request, bus_id):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        bus = Bus.objects.get(id=bus_id, manager=manager)
    except Bus.DoesNotExist:
        return redirect('manager_buses')

    if request.method == 'POST':
        try:
            bus_number = request.POST.get('bus_number', '').strip()
            
            # Verify license uniqueness
            if Bus.objects.filter(bus_number=bus_number).exclude(id=bus_id).exists():
                return render(request, 'edit_bus.html', {'bus': bus, 'msg': 'Duplicate Bus Number should not be allowed.'})

            bus.bus_name = request.POST.get('bus_name', bus.bus_name)
            bus.bus_number = bus_number
            bus.bus_type = request.POST.get('bus_type', bus.bus_type)
            bus.source = request.POST.get('source', bus.source)
            bus.destination = request.POST.get('destination', bus.destination)
            bus.departure_time = request.POST.get('departure_time', bus.departure_time)
            bus.arrival_time = request.POST.get('arrival_time', bus.arrival_time)
            bus.total_seats = int(request.POST.get('total_seats', bus.total_seats))
            bus.available_seats = int(request.POST.get('available_seats', bus.available_seats))
            bus.fare = float(request.POST.get('fare', bus.fare))

            if 'image' in request.FILES:
                bus.image = request.FILES['image']
            bus.save()
            return redirect('manager_buses')
        except Exception as e:
            logger.error(f"Error updating bus: {e}")
            return render(request, 'edit_bus.html', {'bus': bus, 'msg': 'Error saving edits.'})

    return render(request, 'edit_bus.html', {'bus': bus})

def delete_bus(request, bus_id):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        bus = Bus.objects.get(id=bus_id, manager=manager)
        bus.delete()
    except Bus.DoesNotExist:
        pass
    return redirect('manager_buses')

def manager_routes(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    routes_list = Route.objects.filter(manager=manager).order_by('-id')
    paginator = Paginator(routes_list, 6)
    page = request.GET.get('page', 1)
    try:
        routes = paginator.page(page)
    except PageNotAnInteger:
        routes = paginator.page(1)
    except EmptyPage:
        routes = paginator.page(paginator.num_pages)

    return render(request, 'manager-routes.html', {'routes': routes, 'page_obj': routes})

def add_route(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    if request.method == 'POST':
        try:
            source = request.POST.get('source', '').strip()
            destination = request.POST.get('destination', '').strip()
            
            # Check for duplicates
            if Route.objects.filter(source=source, destination=destination).exists():
                return render(request, 'add_route.html', {'msg1': 'Duplicate Route should not be created.'})

            Route.objects.create(
                manager=manager,
                source=source,
                destination=destination,
                distance=int(request.POST.get('distance', 0)),
                duration=request.POST.get('duration', '')
            )
            return render(request, 'add_route.html', {'msg': 'Route saved successfully!'})
        except Exception as e:
            logger.error(f"Error adding route: {e}")
            return render(request, 'add_route.html', {'msg1': f'Error saving route: {e}'})

    return render(request, 'add_route.html')

def edit_route(request, route_id):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        route = Route.objects.get(id=route_id, manager=manager)
    except Route.DoesNotExist:
        return redirect('manager_routes')

    if request.method == "POST":
        try:
            source = request.POST.get('source', '').strip()
            destination = request.POST.get('destination', '').strip()
            
            # Verify uniqueness on update
            if Route.objects.filter(source=source, destination=destination).exclude(id=route_id).exists():
                return render(request, 'edit_route.html', {'route': route, 'msg1': 'Duplicate Route should not be created.'})

            route.source = source
            route.destination = destination
            route.distance = int(request.POST.get('distance', route.distance))
            route.duration = request.POST.get('duration', route.duration)
            route.save()
            return redirect('manager_routes')
        except Exception as e:
            logger.error(f"Error editing route: {e}")
            return render(request, 'edit_route.html', {'route': route, 'msg1': 'Error saving edits.'})

    return render(request, 'edit_route.html', {'route': route})

def delete_route(request, route_id):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        route = Route.objects.get(id=route_id, manager=manager)
        route.delete()
    except Route.DoesNotExist:
        pass
    return redirect('manager_routes')

def get_report_context(user, start_date_str, end_date_str):
    if user and getattr(user, 'usertype', '') == 'admin':
        buses_query = Bus.objects.all()
    elif user and getattr(user, 'usertype', '') == 'manager':
        buses_query = Bus.objects.filter(manager=user)
    elif user:
        buses_query = Bus.objects.filter(manager=user)
    else:
        buses_query = Bus.objects.all()
    total_buses = buses_query.count()

    # Step 1: Filter paid/completed bookings by date range with select_related for query optimization
    bookings_query = Booking.objects.filter(
        bus__in=buses_query,
        payment=True,
        status__in=['booked', 'completed']
    ).select_related('bus')

    if start_date_str and start_date_str.strip():
        bookings_query = bookings_query.filter(booking_date__gte=start_date_str)
    if end_date_str and end_date_str.strip():
        bookings_query = bookings_query.filter(booking_date__lte=end_date_str)

    total_revenue = bookings_query.aggregate(total=Sum('amount'))['total'] or 0.0
    total_tickets = bookings_query.count()

    # Step 2: Average occupancy across schedules in the date range (optimized with select_related)
    schedules = Schedule.objects.filter(bus__in=buses_query).select_related('bus')
    if start_date_str and start_date_str.strip():
        schedules = schedules.filter(journey_date__gte=start_date_str)
    if end_date_str and end_date_str.strip():
        schedules = schedules.filter(journey_date__lte=end_date_str)

    total_capacity = 0
    total_booked_seats = 0
    for s in schedules:
        total_capacity += s.bus.total_seats
        total_booked_seats += SeatBooking.objects.filter(
            bus=s.bus, journey_date=s.journey_date
        ).count()

    if total_capacity > 0:
        avg_occupancy = (total_booked_seats / total_capacity) * 100
    else:
        sum_total_seats = buses_query.aggregate(total=Sum('total_seats'))['total'] or 0
        if sum_total_seats > 0:
            all_seat_bookings = SeatBooking.objects.filter(bus__in=buses_query).count()
            avg_occupancy = (all_seat_bookings / sum_total_seats) * 100
        else:
            avg_occupancy = 0.0

    # Step 3: Weekly Revenue chart — pick up to 7 days from the date range
    if start_date_str and end_date_str:
        try:
            start_date_obj = date.fromisoformat(start_date_str)
            end_date_obj = date.fromisoformat(end_date_str)
            delta = end_date_obj - start_date_obj
            chart_days = [start_date_obj + timedelta(days=i) for i in range(min(delta.days + 1, 7))]
        except Exception:
            today = date.today()
            chart_days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    else:
        today = date.today()
        chart_days = [today - timedelta(days=i) for i in range(6, -1, -1)]

    weekly_revenue = []
    day_names = []
    for d in chart_days:
        day_rev = Booking.objects.filter(
            bus__in=buses_query,
            payment=True,
            status__in=['booked', 'completed'],
            booking_date=d
        ).aggregate(total=Sum('amount'))['total'] or 0.0
        weekly_revenue.append(float(day_rev))
        day_names.append(d.strftime('%a'))

    max_rev = max(weekly_revenue) if weekly_revenue else 0
    if max_rev == 0:
        max_rev = 1000

    # Build SVG path and node coordinates for the line chart
    svg_nodes = []
    points = []
    for i, rev in enumerate(weekly_revenue):
        x = 70 + i * 70
        y = 170 - (rev / max_rev) * 140
        points.append((x, y))
        svg_nodes.append({
            'x': x,
            'y': y,
            'rev': rev,
            'day': day_names[i],
            'x_text': x - 12
        })

    svg_path = "M " + " L ".join([f"{x} {y}" for x, y in points]) if points else ""

    # Step 4: Route Productivity — revenue % per route
    route_revenue = {}
    total_rev_sum = 0
    for booking in bookings_query:
        route_key = f"{booking.bus.source} \u2194 {booking.bus.destination}"
        amount = float(booking.amount)
        route_revenue[route_key] = route_revenue.get(route_key, 0.0) + amount
        total_rev_sum += amount

    colors_list = ['bg-warning', 'bg-primary', 'bg-success', 'bg-info', 'bg-danger']
    route_data = []
    for idx, (route, rev) in enumerate(sorted(route_revenue.items(), key=lambda x: x[1], reverse=True)):
        pct = (rev / total_rev_sum * 100) if total_rev_sum > 0 else 0
        route_data.append({
            'route': route,
            'revenue': rev,
            'percentage': round(pct, 1),
            'color': colors_list[idx % len(colors_list)]
        })

    return {
        'total_buses': total_buses,
        'total_revenue': total_revenue,
        'total_tickets': total_tickets,
        'avg_occupancy': round(avg_occupancy, 1),
        'start_date': start_date_str or (date.today() - timedelta(days=30)).isoformat(),
        'end_date': end_date_str or date.today().isoformat(),
        'weekly_revenue': weekly_revenue,
        'day_names': day_names,
        'svg_path': svg_path,
        'svg_nodes': svg_nodes,
        'route_data': route_data,
        'max_rev': round(max_rev, 1),
        'half_max_rev': round(max_rev / 2, 1),
        'quarter_max_rev': round(max_rev / 4, 1),
    }


def manager_dashboard(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        my_buses = Bus.objects.filter(manager=manager)
        fleet_count = my_buses.count()
        route_count = Route.objects.filter(manager=manager).count()

        schedules = Schedule.objects.filter(bus__in=my_buses).select_related('bus')
        schedule_count = schedules.count()

        bookings = Booking.objects.filter(bus__in=my_buses).select_related('bus')
        bookings_count = bookings.count()
        passenger_count = bookings_count

        net_revenue = bookings.filter(
            payment=True, status__in=['booked', 'completed']
        ).aggregate(total=Sum('amount'))['total'] or 0

        if schedules.exists():
            total_capacity = sum(s.bus.total_seats for s in schedules)
            booked_seats = SeatBooking.objects.filter(
                bus__in=my_buses,
                journey_date__in=[s.journey_date for s in schedules]
            ).count()
            available_seats = max(0, total_capacity - booked_seats)
        else:
            total_capacity = sum(b.total_seats for b in my_buses)
            booked_seats = SeatBooking.objects.filter(bus__in=my_buses).count()
            available_seats = max(0, total_capacity - booked_seats)

        recent_bookings = bookings.order_by('-id')[:5]
        recent_buses = my_buses.order_by('-id')[:5]

        active_trips_list = []
        for s in schedules.order_by('-journey_date')[:5]:
            reserved_count = SeatBooking.objects.filter(
                bus=s.bus, journey_date=s.journey_date
            ).count()
            occupancy_pct = int((reserved_count / s.bus.total_seats * 100)) if s.bus.total_seats > 0 else 0
            active_trips_list.append({
                'schedule': s,
                'reserved_count': reserved_count,
                'occupancy_pct': occupancy_pct
            })

        # Read date filter params from GET (same as Reports page)
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        # Get analytics data using the shared helper (no duplicate code)
        report_ctx = get_report_context(manager, start_date_str, end_date_str)

        context = {
            'fleet_count': fleet_count,
            'route_count': route_count,
            'schedule_count': schedule_count,
            'bookings_count': bookings_count,
            'passenger_count': passenger_count,
            'net_revenue': float(net_revenue),
            'booked_seats': booked_seats,
            'available_seats': available_seats,
            'recent_bookings': recent_bookings,
            'recent_buses': recent_buses,
            'active_trips_list': active_trips_list,
        }
        # Merge the analytics context from the shared helper
        context.update(report_ctx)

        return render(request, 'manager-dashboard.html', context)
    except Exception as e:
        logger.error(f"Manager Dashboard Error: {e}")
        return HttpResponse("An error occurred loading dashboard data.")


def manager_reports(request):
    try:
        return redirect('manager_dashboard')
    except Exception as e:
        logger.error(f"Error redirecting manager reports: {e}")
        return redirect('login')


def export_pdf(request):
    # 1. Authenticate Manager or Admin
    manager = get_manager_user(request)
    admin = get_admin_user(request) if not manager else None
    if not manager and not admin:
        return redirect('login')

    # 2. Get and validate date filters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if not start_date_str or not end_date_str or not start_date_str.strip() or not end_date_str.strip():
        return HttpResponse("Validation Error: Please select both Start Date and End Date.", status=400)

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        if start_date > end_date:
            return HttpResponse("Validation Error: Start Date cannot be later than End Date.", status=400)
    except ValueError:
        return HttpResponse("Validation Error: Invalid date format. Use YYYY-MM-DD.", status=400)

    # 3. Query the filtered bookings
    if manager:
        buses_query = Bus.objects.filter(manager=manager)
    else:
        buses_query = Bus.objects.all()
    total_buses = buses_query.count()

    bookings_query = Booking.objects.filter(
        bus__in=buses_query,
        payment=True,
        status__in=['booked', 'completed'],
        booking_date__gte=start_date_str,
        booking_date__lte=end_date_str
    ).order_by('booking_date')

    # 4. Calculate analytics statistics
    total_revenue = bookings_query.aggregate(total=Sum('amount'))['total'] or 0.0
    total_tickets = bookings_query.count()

    # Calculate average occupancy
    schedules = Schedule.objects.filter(
        bus__in=buses_query,
        journey_date__gte=start_date_str,
        journey_date__lte=end_date_str
    )
    total_capacity = 0
    total_booked_seats = 0
    for s in schedules:
        total_capacity += s.bus.total_seats
        booked_count = SeatBooking.objects.filter(bus=s.bus, journey_date=s.journey_date).count()
        total_booked_seats += booked_count

    if total_capacity > 0:
        avg_occupancy = (total_booked_seats / total_capacity) * 100
    else:
        sum_total_seats = buses_query.aggregate(total=Sum('total_seats'))['total'] or 0
        if sum_total_seats > 0:
            total_seat_bookings = SeatBooking.objects.filter(bus__in=buses_query).count()
            avg_occupancy = (total_seat_bookings / sum_total_seats) * 100
        else:
            avg_occupancy = 0.0

    # 5. Generate PDF report using ReportLab
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Define custom styles
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=20, leading=24, textColor=HexColor('#0F172A')
    )
    meta_style = ParagraphStyle(
        'DocMeta', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=13, textColor=HexColor('#64748B')
    )
    section_style = ParagraphStyle(
        'SectionTitle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=HexColor('#0F172A'), spaceBefore=12, spaceAfter=6
    )
    th_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white
    )
    td_style = ParagraphStyle(
        'TableCell', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, textColor=HexColor('#0F172A')
    )
    stat_label_style = ParagraphStyle(
        'StatLabel', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, textColor=HexColor('#475569')
    )
    stat_val_style = ParagraphStyle(
        'StatVal', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, leading=18, textColor=HexColor('#0F172A')
    )

    user = manager or admin
    user_name = user.name if user else "System User"
    user_email = user.email if user else ""
    user_role = "Manager" if manager else "Admin"

    elements = []

    # Left content of header: Report Title & Period
    left_content = [
        [Paragraph(f"<b>BusYatra {user_role} Performance Report</b>", title_style)],
        [Paragraph(f"Reporting Period: {start_date_str} to {end_date_str}", meta_style)]
    ]
    left_table = Table(left_content, colWidths=[360])
    left_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))

    # Right content of header: User profile info
    right_content = [
        [Paragraph(f"<b>{user_role}:</b> {user_name}", meta_style)],
        [Paragraph(f"<b>Email:</b> {user_email}", meta_style)],
        [Paragraph(f"<b>Generated On:</b> {date.today().isoformat()}", meta_style)]
    ]
    right_table = Table(right_content, colWidths=[180])
    right_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
    ]))

    header_table = Table([[left_table, right_table]], colWidths=[360, 180])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    elements.append(header_table)

    # Add a thin gray separator line
    divider = Table([['']], colWidths=[540])
    divider.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, HexColor('#CBD5E1')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 10))

    # KPI Statistics Row
    kpi_data = [
        [
            Paragraph("Brand Earnings", stat_label_style),
            Paragraph("Tickets Booked", stat_label_style),
            Paragraph("Buses Managed", stat_label_style),
            Paragraph("Avg Occupancy", stat_label_style)
        ],
        [
            Paragraph(f"INR {total_revenue:.2f}", stat_val_style),
            Paragraph(str(total_tickets), stat_val_style),
            Paragraph(f"{total_buses} Buses", stat_val_style),
            Paragraph(f"{avg_occupancy:.1f}%", stat_val_style)
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, HexColor('#E2E8F0')),
        ('INNERGRID', (0,0), (-1,-1), 1, HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 10))

    # Transactions List Section
    elements.append(Paragraph("Booking Transaction Details", section_style))

    # Build transaction table
    col_widths = [40, 110, 150, 80, 50, 60, 50]
    table_data = [[
        Paragraph("ID", th_style),
        Paragraph("Passenger", th_style),
        Paragraph("Bus & Route", th_style),
        Paragraph("Travel Date", th_style),
        Paragraph("Seat", th_style),
        Paragraph("Amount", th_style),
        Paragraph("Status", th_style)
    ]]

    for b in bookings_query:
        passenger_info = f"<b>{b.passenger_name}</b><br/>{b.passenger_gender}, {b.passenger_age} yrs"
        bus_route = f"<b>{b.bus.bus_name}</b> ({b.bus.bus_number})<br/>{b.bus.source} to {b.bus.destination}"
        table_data.append([
            Paragraph(str(b.id), td_style),
            Paragraph(passenger_info, td_style),
            Paragraph(bus_route, td_style),
            Paragraph(b.travel_date.strftime('%d-%b-%Y'), td_style),
            Paragraph(b.seat_number, td_style),
            Paragraph(f"INR {b.amount:.2f}", td_style),
            Paragraph(b.status.capitalize(), td_style)
        ])

    bookings_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    bookings_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), HexColor('#0F172A')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, HexColor('#F8FAFC')]),
        ('GRID', (0,0), (-1,-1), 0.5, HexColor('#E2E8F0')),
    ]))
    elements.append(bookings_table)

    # Render PDF document to the memory buffer
    doc.build(elements)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    # Return response as attachment download
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="manager_report_{start_date_str}_to_{end_date_str}.pdf"'
    return response


def export_csv(request):
    import csv

    # 1. Authenticate Manager or Admin
    manager = get_manager_user(request)
    admin = get_admin_user(request) if not manager else None
    if not manager and not admin:
        return redirect('login')

    # 2. Get and validate date filters
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    if not start_date_str or not end_date_str or not start_date_str.strip() or not end_date_str.strip():
        return HttpResponse("Validation Error: Please select both Start Date and End Date.", status=400)

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
        if start_date > end_date:
            return HttpResponse("Validation Error: Start Date cannot be later than End Date.", status=400)
    except ValueError:
        return HttpResponse("Validation Error: Invalid date format. Use YYYY-MM-DD.", status=400)

    # 3. Query the filtered bookings
    if manager:
        buses_query = Bus.objects.filter(manager=manager)
    else:
        buses_query = Bus.objects.all()

    bookings_query = Booking.objects.filter(
        bus__in=buses_query,
        payment=True,
        status__in=['booked', 'completed'],
        booking_date__gte=start_date_str,
        booking_date__lte=end_date_str
    ).order_by('booking_date')

    # 4. Prepare the HTTP response with CSV content type
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="manager_report_{start_date_str}_to_{end_date_str}.csv"'

    writer = csv.writer(response)

    # Write column headers
    writer.writerow([
        'Booking ID', 'Passenger Name', 'Age', 'Gender',
        'Bus Name', 'Bus Number', 'Source', 'Destination',
        'Travel Date', 'Booking Date', 'Seat Number', 'Amount (INR)', 'Status'
    ])

    # Write data rows
    for booking in bookings_query:
        writer.writerow([
            booking.id,
            booking.passenger_name,
            booking.passenger_age,
            booking.passenger_gender,
            booking.bus.bus_name,
            booking.bus.bus_number,
            booking.bus.source,
            booking.bus.destination,
            booking.travel_date,
            booking.booking_date,
            booking.seat_number,
            booking.amount,
            booking.status
        ])

    return response


def manager_schedules(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    buses = Bus.objects.filter(manager=manager)

    if request.method == 'POST':
        try:
            bus_id = request.POST.get('bus')
            bus = Bus.objects.get(id=bus_id, manager=manager)
            
            Schedule.objects.create(
                bus=bus,
                journey_date=request.POST.get('journey_date'),
                departure_time=request.POST.get('departure_time'),
                arrival_time=request.POST.get('arrival_time'),
                status=request.POST.get('status', 'Available')
            )
            return redirect('manager_schedules')
        except Exception as e:
            logger.error(f"Error creating schedule: {e}")

    schedules_list = Schedule.objects.filter(bus__in=buses).order_by('-journey_date')
    paginator = Paginator(schedules_list, 6)
    page = request.GET.get('page', 1)
    try:
        schedules = paginator.page(page)
    except PageNotAnInteger:
        schedules = paginator.page(1)
    except EmptyPage:
        schedules = paginator.page(paginator.num_pages)

    context = {
        'schedules': schedules,
        'page_obj': schedules,
        'buses': buses
    }
    return render(request, 'manager-schedules.html', context)

def edit_schedule(request, pk):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        schedule = Schedule.objects.get(id=pk, bus__manager=manager)
    except Schedule.DoesNotExist:
        return redirect('manager_schedules')

    buses = Bus.objects.filter(manager=manager)

    if request.method == 'POST':
        try:
            bus_id = request.POST.get('bus')
            schedule.bus = Bus.objects.get(id=bus_id, manager=manager)
            schedule.journey_date = request.POST.get('journey_date', schedule.journey_date)
            schedule.departure_time = request.POST.get('departure_time', schedule.departure_time)
            schedule.arrival_time = request.POST.get('arrival_time', schedule.arrival_time)
            schedule.status = request.POST.get('status', schedule.status)
            schedule.save()
            return redirect('manager_schedules')
        except Exception as e:
            logger.error(f"Error updating schedule: {e}")

    context = {
        'schedule': schedule,
        'buses': buses
    }
    return render(request, 'edit_schedule.html', context)

def delete_schedule(request, pk):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        schedule = Schedule.objects.get(id=pk, bus__manager=manager)
        schedule.delete()
    except Schedule.DoesNotExist:
        pass
    return redirect('manager_schedules')

def manager_seats(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    buses = Bus.objects.filter(manager=manager)
    bus_id = request.GET.get('bus_id')
    selected_date_str = request.GET.get('date') or str(date.today())

    selected_bus = None
    booked_seats = []
    booked_seats_details = {}

    if bus_id:
        try:
            selected_bus = Bus.objects.get(id=bus_id, manager=manager)
            seat_bookings = SeatBooking.objects.filter(bus=selected_bus, journey_date=selected_date_str)
            for sb in seat_bookings:
                booking = sb.booking
                booked_seats.append(sb.seat_number)
                booked_seats_details[sb.seat_number] = {
                    'passenger_name': booking.passenger_name,
                    'passenger_age': booking.passenger_age,
                    'passenger_gender': booking.passenger_gender,
                    'pnr': f"BY-{booking.id}",
                    'status': booking.status.upper() if booking.payment else 'UNPAID'
                }
        except Bus.DoesNotExist:
            pass

    context = {
        'buses': buses,
        'selected_bus': selected_bus,
        'selected_date': selected_date_str,
        'booked_seats_json': json.dumps(booked_seats),
        'booked_details_json': json.dumps(booked_seats_details)
    }
    return render(request, 'manager-seats.html', context)

def manager_profile(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    msg = None
    msg1 = None

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_profile':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()

            if not name or not email or not phone:
                msg = "Name, Email and Phone Number are required fields."
            else:
                if User.objects.filter(email=email).exclude(id=manager.id).exists():
                    msg = "Email already exists."
                elif User.objects.filter(phone=phone).exclude(id=manager.id).exists():
                    msg = "Phone Number already exists."
                else:
                    try:
                        manager.name = name
                        manager.email = email
                        manager.phone = phone
                        if 'profile' in request.FILES:
                            manager.profile = request.FILES['profile']
                        manager.save()
                        request.session['email'] = email
                        msg1 = "Profile updated successfully!"
                    except Exception as e:
                        msg = f"Profile save error: {e}"

        elif action == 'change_password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not old_password or not new_password or not confirm_password:
                msg = "All password fields are required."
            elif old_password != manager.password:
                msg = "Incorrect current password."
            elif new_password != confirm_password:
                msg = "New passwords do not match."
            else:
                try:
                    manager.password = new_password
                    manager.save()
                    msg1 = "Password changed successfully!"
                except Exception as e:
                    msg = f"Password update error: {e}"

    return render(request, 'manager-profile.html', {'msg': msg, 'msg1': msg1})

def manager_booking_detail(request, booking_id):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        booking = Booking.objects.get(id=booking_id, bus__manager=manager)
        return render(request, 'manager-booking-detail.html', {'booking': booking})
    except Booking.DoesNotExist:
        return redirect('manager_bookings')

def manager_cancel_booking(request, booking_id):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        booking = Booking.objects.get(id=booking_id, bus__manager=manager)
        booking.status = 'cancelled'
        booking.booking_status = 'cancelled'
        booking.save()
        
        # Free blocked seats
        SeatBooking.objects.filter(booking=booking).delete()
    except Booking.DoesNotExist:
        pass

    return redirect('manager_bookings')

#==========================================================================
#    Admin Views
#==========================================================================
def admin_dashboard(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')
    
    try:
        total_customers = User.objects.filter(usertype='customer').count()
        total_managers = User.objects.filter(usertype='manager').count()
        total_buses = Bus.objects.count()
        total_routes = Route.objects.count()
        total_schedules = Schedule.objects.count()
        total_bookings = Booking.objects.count()
        total_successful_payments = Booking.objects.filter(payment=True).count()

        total_revenue = Booking.objects.filter(payment=True).aggregate(total=Sum('amount'))['total'] or 0
        total_booked_seats = SeatBooking.objects.count()

        total_schedule_seats = Schedule.objects.aggregate(total=Sum('bus__total_seats'))['total'] or 0
        total_available_seats = max(0, total_schedule_seats - total_booked_seats)

        recent_bookings = Booking.objects.all().order_by('-id')[:5]
        recent_buses = Bus.objects.all().order_by('-id')[:5]
        recent_customers = User.objects.filter(usertype='customer').order_by('-id')[:5]
        recent_managers = User.objects.filter(usertype='manager').order_by('-id')[:5]

        # Read date filter params from GET
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        # Get analytics data using the shared helper get_report_context
        report_ctx = get_report_context(admin, start_date_str, end_date_str)

        context = {
            'fleet_count': total_buses,
            'route_count': total_routes,
            'schedule_count': total_schedules,
            'bookings_count': total_bookings,
            'passenger_count': total_booked_seats,
            'net_revenue': total_revenue,
            'booked_seats': total_booked_seats,
            'available_seats': total_available_seats,
            
            'total_customers': total_customers,
            'total_managers': total_managers,
            'total_successful_payments': total_successful_payments,
            
            'recent_bookings': recent_bookings,
            'recent_buses': recent_buses,
            'recent_customers': recent_customers,
            'recent_managers': recent_managers,
            'login_user': admin,
        }
        context.update(report_ctx)
        return render(request, 'admin-dashboard.html', context)
    except Exception as e:
        logger.error(f"Admin Dashboard Error: {e}")
        return HttpResponse("An error occurred loading admin dashboard data.")

def admin_users(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    query = request.GET.get('search', '').strip()
    customers_list = User.objects.filter(usertype='customer').order_by('-id')
    if query:
        customers_list = customers_list.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )

    paginator = Paginator(customers_list, 6)
    page = request.GET.get('page', 1)
    try:
        customers = paginator.page(page)
    except PageNotAnInteger:
        customers = paginator.page(1)
    except EmptyPage:
        customers = paginator.page(paginator.num_pages)

    return render(request, 'admin-users.html', {'customers': customers, 'page_obj': customers, 'search_query': query, 'login_user': admin})

def admin_add_customer(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    msg = None
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()

        if not name or not email or not phone or not password:

            msg = "All fields are required."
        elif User.objects.filter(email=email).exists():
            msg = "Email already exists."
        elif User.objects.filter(phone=phone).exists():
            msg = "Phone number already exists."
        else:
            try:
                profile_pic = request.FILES.get('profile', '')
                User.objects.create(
                    name=name,
                    email=email,
                    phone=phone,
                    password=password,
                    profile=profile_pic,
                    usertype='customer'
                )
                return redirect('admin_users')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-add-customer.html', {'msg': msg, 'login_user': admin})

def admin_edit_customer(request, user_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        customer = User.objects.get(id=user_id, usertype='customer')
    except User.DoesNotExist:
        return redirect('admin_users')

    msg = None
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()

        if not name or not email or not phone:
            msg = "Name, Email and Phone are required."
        elif User.objects.filter(email=email).exclude(id=customer.id).exists():
            msg = "Email already exists."
        elif User.objects.filter(phone=phone).exclude(id=customer.id).exists():
            msg = "Phone number already exists."
        else:
            try:
                customer.name = name
                customer.email = email
                customer.phone = phone
                if password:
                    customer.password = password
                if 'profile' in request.FILES:
                    customer.profile = request.FILES['profile']
                customer.save()
                return redirect('admin_users')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-edit-customer.html', {'customer': customer, 'msg': msg, 'login_user': admin})

def admin_delete_customer(request, user_id):
    try:
        admin = get_admin_user(request)
        if not admin:
            return redirect('login')

        User.objects.filter(id=user_id, usertype='customer').delete()
        return redirect('admin_users')
    except Exception as e:
        logger.error(f"Error deleting customer: {e}")
        return redirect('admin_users')

def admin_customer_detail(request, user_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        customer = User.objects.get(id=user_id, usertype='customer')
        bookings = Booking.objects.filter(user=customer)
        return render(request, 'admin-customer-detail.html', {'customer': customer, 'bookings': bookings, 'login_user': admin})
    except User.DoesNotExist:
        return redirect('admin_users')

def admin_managers(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    query = request.GET.get('search', '').strip()
    managers_list = User.objects.filter(usertype='manager').order_by('-id')
    if query:
        managers_list = managers_list.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )

    for mgr in managers_list:
        mgr.buses_count = Bus.objects.filter(manager=mgr).count()
        mgr.bookings_count = Booking.objects.filter(bus__manager=mgr).count()

    paginator = Paginator(managers_list, 6)
    page = request.GET.get('page', 1)
    try:
        managers = paginator.page(page)
    except PageNotAnInteger:
        managers = paginator.page(1)
    except EmptyPage:
        managers = paginator.page(paginator.num_pages)

    return render(request, 'admin-managers.html', {'managers': managers, 'page_obj': managers, 'search_query': query, 'login_user': admin})

def admin_add_manager(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    msg = None
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()

        if not name or not email or not phone or not password:
            msg = "All fields are required."
        elif User.objects.filter(email=email).exists():
            msg = "Email already exists."
        elif User.objects.filter(phone=phone).exists():
            msg = "Phone number already exists."
        else:
            try:
                profile_pic = request.FILES.get('profile', '')
                User.objects.create(
                    name=name,
                    email=email,
                    phone=phone,
                    password=password,
                    profile=profile_pic,
                    usertype='manager'
                )
                return redirect('admin_managers')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-add-manager.html', {'msg': msg, 'login_user': admin})

def admin_edit_manager(request, user_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        manager = User.objects.get(id=user_id, usertype='manager')
    except User.DoesNotExist:
        return redirect('admin_managers')

    msg = None
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        password = request.POST.get('password', '').strip()

        if not name or not email or not phone:
            msg = "Name, Email and Phone are required."
        elif User.objects.filter(email=email).exclude(id=manager.id).exists():
            msg = "Email already exists."
        elif User.objects.filter(phone=phone).exclude(id=manager.id).exists():
            msg = "Phone number already exists."
        else:
            try:
                manager.name = name
                manager.email = email
                manager.phone = phone
                if password:
                    manager.password = password
                if 'profile' in request.FILES:
                    manager.profile = request.FILES['profile']
                manager.save()
                return redirect('admin_managers')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-edit-manager.html', {'manager': manager, 'msg': msg, 'login_user': admin})

def admin_delete_manager(request, user_id):
    try:
        admin = get_admin_user(request)
        if not admin:
            return redirect('login')

        User.objects.filter(id=user_id, usertype='manager').delete()
        return redirect('admin_managers')
    except Exception as e:
        logger.error(f"Error deleting manager: {e}")
        return redirect('admin_managers')

def admin_manager_detail(request, user_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        manager = User.objects.get(id=user_id, usertype='manager')
        buses = Bus.objects.filter(manager=manager)
        for bus in buses:
            bus.booking_count = Booking.objects.filter(bus=bus).count()
            bus.total_revenue = Booking.objects.filter(bus=bus, payment=True).aggregate(total=Sum('amount'))['total'] or 0
        return render(request, 'admin-manager-detail.html', {'manager': manager, 'buses': buses, 'login_user': admin})
    except User.DoesNotExist:
        return redirect('admin_managers')

def admin_buses(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    buses_list = Bus.objects.all().order_by('-id')
    paginator = Paginator(buses_list, 6)
    page = request.GET.get('page', 1)
    try:
        buses = paginator.page(page)
    except PageNotAnInteger:
        buses = paginator.page(1)
    except EmptyPage:
        buses = paginator.page(paginator.num_pages)

    return render(request, 'admin-buses.html', {'buses': buses, 'page_obj': buses, 'login_user': admin})

def admin_add_bus(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    managers = User.objects.filter(usertype='manager')
    msg = None
    if request.method == "POST":
        manager_id = request.POST.get('manager')
        bus_name = request.POST.get('bus_name', '').strip()
        bus_number = request.POST.get('bus_number', '').strip()
        bus_type = request.POST.get('bus_type', '').strip()
        source = request.POST.get('source', '').strip()
        destination = request.POST.get('destination', '').strip()
        departure_time = request.POST.get('departure_time')
        arrival_time = request.POST.get('arrival_time')
        total_seats = request.POST.get('total_seats')
        fare = request.POST.get('fare')

        if not manager_id or not bus_name or not bus_number or not source or not destination or not departure_time or not arrival_time or not total_seats or not fare:
            msg = "All fields are required."
        elif Bus.objects.filter(bus_number=bus_number).exists():
            msg = "Duplicate Bus Number should not be allowed."
        else:
            try:
                mgr = User.objects.get(id=manager_id, usertype='manager')
                bus_image = request.FILES.get('image', '')
                Bus.objects.create(
                    manager=mgr,
                    bus_name=bus_name,
                    bus_number=bus_number,
                    bus_type=bus_type,
                    source=source,
                    destination=destination,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    total_seats=int(total_seats),
                    available_seats=int(total_seats),
                    fare=float(fare),
                    image=bus_image
                )
                return redirect('admin_buses')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-add-bus.html', {'managers': managers, 'msg': msg, 'login_user': admin})

def admin_edit_bus(request, bus_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        bus = Bus.objects.get(id=bus_id)
    except Bus.DoesNotExist:
        return redirect('admin_buses')

    managers = User.objects.filter(usertype='manager')
    msg = None
    if request.method == "POST":
        manager_id = request.POST.get('manager')
        bus_name = request.POST.get('bus_name', '').strip()
        bus_number = request.POST.get('bus_number', '').strip()
        bus_type = request.POST.get('bus_type', '').strip()
        source = request.POST.get('source', '').strip()
        destination = request.POST.get('destination', '').strip()
        departure_time = request.POST.get('departure_time')
        arrival_time = request.POST.get('arrival_time')
        total_seats = request.POST.get('total_seats')
        fare = request.POST.get('fare')

        if not manager_id or not bus_name or not bus_number or not source or not destination or not departure_time or not arrival_time or not total_seats or not fare:
            msg = "All fields are required."
        elif Bus.objects.filter(bus_number=bus_number).exclude(id=bus.id).exists():
            msg = "Duplicate Bus Number should not be allowed."
        else:
            try:
                mgr = User.objects.get(id=manager_id, usertype='manager')
                bus.manager = mgr
                bus.bus_name = bus_name
                bus.bus_number = bus_number
                bus.bus_type = bus_type
                bus.source = source
                bus.destination = destination
                bus.departure_time = departure_time
                bus.arrival_time = arrival_time
                bus.total_seats = int(total_seats)
                bus.fare = float(fare)
                if 'image' in request.FILES:
                    bus.image = request.FILES['image']
                bus.save()
                return redirect('admin_buses')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-edit-bus.html', {'bus': bus, 'managers': managers, 'msg': msg, 'login_user': admin})

def admin_delete_bus(request, bus_id):
    try:
        admin = get_admin_user(request)
        if not admin:
            return redirect('login')

        Bus.objects.filter(id=bus_id).delete()
        return redirect('admin_buses')
    except Exception as e:
        logger.error(f"Error deleting bus: {e}")
        return redirect('admin_buses')

def admin_routes(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    routes_list = Route.objects.all().order_by('-id')
    for route in routes_list:
        route.fleet_count = Bus.objects.filter(source=route.source, destination=route.destination).count()

    paginator = Paginator(routes_list, 6)
    page = request.GET.get('page', 1)
    try:
        routes = paginator.page(page)
    except PageNotAnInteger:
        routes = paginator.page(1)
    except EmptyPage:
        routes = paginator.page(paginator.num_pages)

    return render(request, 'admin-routes.html', {'routes': routes, 'page_obj': routes, 'login_user': admin})

def admin_add_route(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    managers = User.objects.filter(usertype='manager')
    msg = None
    if request.method == "POST":
        manager_id = request.POST.get('manager')
        source = request.POST.get('source', '').strip()
        destination = request.POST.get('destination', '').strip()
        distance = request.POST.get('distance')
        duration = request.POST.get('duration', '').strip()

        if not manager_id or not source or not destination or not distance or not duration:
            msg = "All fields are required."
        elif Route.objects.filter(source=source, destination=destination).exists():
            msg = "Duplicate Route should not be created."
        else:
            try:
                mgr = User.objects.get(id=manager_id, usertype='manager')
                Route.objects.create(
                    manager=mgr,
                    source=source,
                    destination=destination,
                    distance=int(distance),
                    duration=duration
                )
                return redirect('admin_routes')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-add-route.html', {'managers': managers, 'msg': msg, 'login_user': admin})

def admin_edit_route(request, route_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        return redirect('admin_routes')

    managers = User.objects.filter(usertype='manager')
    msg = None
    if request.method == "POST":
        manager_id = request.POST.get('manager')
        source = request.POST.get('source', '').strip()
        destination = request.POST.get('destination', '').strip()
        distance = request.POST.get('distance')
        duration = request.POST.get('duration', '').strip()

        if not manager_id or not source or not destination or not distance or not duration:
            msg = "All fields are required."
        elif Route.objects.filter(source=source, destination=destination).exclude(id=route.id).exists():
            msg = "Duplicate Route should not be created."
        else:
            try:
                mgr = User.objects.get(id=manager_id, usertype='manager')
                route.manager = mgr
                route.source = source
                route.destination = destination
                route.distance = int(distance)
                route.duration = duration
                route.save()
                return redirect('admin_routes')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-edit-route.html', {'route': route, 'managers': managers, 'msg': msg, 'login_user': admin})

def admin_delete_route(request, route_id):
    try:
        admin = get_admin_user(request)
        if not admin:
            return redirect('login')

        Route.objects.filter(id=route_id).delete()
        return redirect('admin_routes')
    except Exception as e:
        logger.error(f"Error deleting route: {e}")
        return redirect('admin_routes')

def admin_schedules(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    schedules_list = Schedule.objects.all().order_by('-journey_date')
    paginator = Paginator(schedules_list, 6)
    page = request.GET.get('page', 1)
    try:
        schedules = paginator.page(page)
    except PageNotAnInteger:
        schedules = paginator.page(1)
    except EmptyPage:
        schedules = paginator.page(paginator.num_pages)

    return render(request, 'admin-schedules.html', {'schedules': schedules, 'page_obj': schedules, 'login_user': admin})

def admin_add_schedule(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    buses = Bus.objects.all()
    msg = None
    if request.method == "POST":
        bus_id = request.POST.get('bus')
        journey_date = request.POST.get('journey_date')
        departure_time = request.POST.get('departure_time')
        arrival_time = request.POST.get('arrival_time')
        status = request.POST.get('status', 'Available')

        if not bus_id or not journey_date or not departure_time or not arrival_time:
            msg = "All fields are required."
        else:
            try:
                bus = Bus.objects.get(id=bus_id)
                Schedule.objects.create(
                    bus=bus,
                    journey_date=journey_date,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    status=status
                )
                return redirect('admin_schedules')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-add-schedule.html', {'buses': buses, 'msg': msg, 'login_user': admin})

def admin_edit_schedule(request, schedule_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        schedule = Schedule.objects.get(id=schedule_id)
    except Schedule.DoesNotExist:
        return redirect('admin_schedules')

    buses = Bus.objects.all()
    msg = None
    if request.method == "POST":
        bus_id = request.POST.get('bus')
        journey_date = request.POST.get('journey_date')
        departure_time = request.POST.get('departure_time')
        arrival_time = request.POST.get('arrival_time')
        status = request.POST.get('status', 'Available')

        if not bus_id or not journey_date or not departure_time or not arrival_time:
            msg = "All fields are required."
        else:
            try:
                bus = Bus.objects.get(id=bus_id)
                schedule.bus = bus
                schedule.journey_date = journey_date
                schedule.departure_time = departure_time
                schedule.arrival_time = arrival_time
                schedule.status = status
                schedule.save()
                return redirect('admin_schedules')
            except Exception as e:
                msg = f"Save error: {e}"

    return render(request, 'admin-edit-schedule.html', {'schedule': schedule, 'buses': buses, 'msg': msg, 'login_user': admin})

def admin_delete_schedule(request, schedule_id):
    try:
        admin = get_admin_user(request)
        if not admin:
            return redirect('login')

        Schedule.objects.filter(id=schedule_id).delete()
        return redirect('admin_schedules')
    except Exception as e:
        logger.error(f"Error deleting schedule: {e}")
        return redirect('admin_schedules')

def admin_bookings(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    bookings_list = Booking.objects.all().order_by('-booking_date')
    paginator = Paginator(bookings_list, 6)
    page = request.GET.get('page', 1)
    try:
        bookings = paginator.page(page)
    except PageNotAnInteger:
        bookings = paginator.page(1)
    except EmptyPage:
        bookings = paginator.page(paginator.num_pages)

    return render(request, 'admin-bookings.html', {'bookings': bookings, 'page_obj': bookings, 'login_user': admin})

def admin_booking_detail(request, booking_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        booking = Booking.objects.get(id=booking_id)
        return render(request, 'admin-booking-detail.html', {'booking': booking, 'login_user': admin})
    except Booking.DoesNotExist:
        return redirect('admin_bookings')

def admin_cancel_booking(request, booking_id):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        booking = Booking.objects.get(id=booking_id)
        booking.status = 'cancelled'
        booking.booking_status = 'cancelled'
        booking.save()
        SeatBooking.objects.filter(booking=booking).delete()
    except Booking.DoesNotExist:
        pass

    return redirect('admin_bookings')

def admin_payments(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    bookings_list = Booking.objects.filter(payment=True).order_by('-booking_date')
    paginator = Paginator(bookings_list, 6)
    page = request.GET.get('page', 1)
    try:
        bookings = paginator.page(page)
    except PageNotAnInteger:
        bookings = paginator.page(1)
    except EmptyPage:
        bookings = paginator.page(paginator.num_pages)

    return render(request, 'admin-payments.html', {'bookings': bookings, 'page_obj': bookings, 'login_user': admin})

def admin_profile(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    msg = None
    msg1 = None
    if request.method == "POST":
        action = request.POST.get('action')
        if action == 'update_profile':
            name = request.POST.get('name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()

            if not name or not email or not phone:
                msg = "Name, Email, and Phone are required."
            elif User.objects.filter(email=email).exclude(id=admin.id).exists():
                msg = "Email already exists."
            elif User.objects.filter(phone=phone).exclude(id=admin.id).exists():
                msg = "Phone number already exists."
            else:
                try:
                    admin.name = name
                    admin.email = email
                    admin.phone = phone
                    if 'profile' in request.FILES:
                        admin.profile = request.FILES['profile']
                    admin.save()
                    request.session['email'] = email
                    msg1 = "Profile updated successfully!"
                except Exception as e:
                    msg = f"Save error: {e}"

        elif action == 'change_password':
            old_pass = request.POST.get('old_password', '')
            new_pass = request.POST.get('new_password', '')
            confirm_pass = request.POST.get('confirm_password', '')

            if not old_pass or not new_pass or not confirm_pass:
                msg = "All password fields are required."
            elif old_pass != admin.password:
                msg = "Incorrect current password."
            elif new_pass != confirm_pass:
                msg = "New passwords do not match."
            else:
                try:
                    admin.password = new_pass
                    admin.save()
                    msg1 = "Password changed successfully!"
                except Exception as e:
                    msg = f"Password save error: {e}"

    return render(request, 'admin-profile.html', {'msg': msg, 'msg1': msg1, 'login_user': admin})

def admin_reports(request):
    try:
        return redirect('admin_dashboard')
    except Exception as e:
        logger.error(f"Error redirecting admin reports: {e}")
        return redirect('login')

def admin_settings(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    sys_settings = SystemSettings.get_settings()

    if request.method == 'POST':
        try:
            app_name = request.POST.get('app_name', 'BusYatra').strip()
            currency = request.POST.get('currency', 'INR (₹)').strip()
            welcome_bonus = Decimal(request.POST.get('welcome_bonus', '100'))
            cashback_percentage = Decimal(request.POST.get('cashback_percentage', '10'))
            gst_percentage = Decimal(request.POST.get('gst_percentage', '5'))
            convenience_fee = Decimal(request.POST.get('convenience_fee', '20'))
            full_refund_hours = int(request.POST.get('full_refund_hours', '24'))
            half_refund_hours = int(request.POST.get('half_refund_hours', '12'))
            maintenance_mode = request.POST.get('maintenance_mode') == 'on'

            if cashback_percentage < 0 or cashback_percentage > 100:
                messages.error(request, 'Wallet Cashback Percentage must be between 0% and 100%.')
                return redirect('admin_settings')

            if gst_percentage < 0 or gst_percentage > 100:
                messages.error(request, 'Booking GST Rate must be between 0% and 100%.')
                return redirect('admin_settings')

            if convenience_fee < 0:
                messages.error(request, 'Convenience Fee cannot be negative.')
                return redirect('admin_settings')

            if full_refund_hours <= 0:
                messages.error(request, '100% Refund Threshold hours must be greater than 0.')
                return redirect('admin_settings')

            if half_refund_hours < 0:
                messages.error(request, '50% Refund Threshold hours cannot be negative.')
                return redirect('admin_settings')

            if half_refund_hours > full_refund_hours:
                messages.error(request, '50% Refund Threshold hours cannot be greater than 100% Refund Threshold hours.')
                return redirect('admin_settings')

            sys_settings.app_name = app_name
            sys_settings.currency = currency
            sys_settings.welcome_bonus = welcome_bonus
            sys_settings.cashback_percentage = cashback_percentage
            sys_settings.gst_percentage = gst_percentage
            sys_settings.convenience_fee = convenience_fee
            sys_settings.full_refund_hours = full_refund_hours
            sys_settings.half_refund_hours = half_refund_hours
            sys_settings.maintenance_mode = maintenance_mode
            sys_settings.save()


            messages.success(request, 'Global configuration saved successfully.')
            return redirect('admin_settings')
        except Exception as e:
            logger.error(f"Error saving admin settings: {e}")
            messages.error(request, 'Invalid values submitted. Please check inputs and try again.')
            return redirect('admin_settings')

    return render(request, 'admin-settings.html', {
        'login_user': admin,
        'sys_settings': sys_settings
    })


def cancel_booking(request, booking_id):
    customer = get_customer_user(request)
    if not customer:
        messages.error(request, "Please log in to cancel a booking.")
        return redirect('login')

    try:
        booking = Booking.objects.select_related('bus', 'user').get(id=booking_id, user=customer)
        if booking.status == 'cancelled':
            messages.warning(request, "This booking is already cancelled.", extra_tags='customer_review')
            return redirect('/my-orders/?tab=cancelled')

        sys_settings = SystemSettings.get_settings()

        departure_dt = datetime.combine(booking.travel_date, booking.bus.departure_time)
        now_dt = datetime.now()
        hours_diff = (departure_dt - now_dt).total_seconds() / 3600.0

        if hours_diff >= sys_settings.full_refund_hours:
            refund_pct = 100
        elif hours_diff >= sys_settings.half_refund_hours:
            refund_pct = 50
        else:
            refund_pct = 0

        refund_amount = (booking.amount * Decimal(refund_pct)) / Decimal('100')

        booking.status = 'cancelled'
        booking.booking_status = 'cancelled'
        booking.save()

        SeatBooking.objects.filter(booking=booking).delete()

        msg = f"Ticket #{booking.id} cancelled successfully. Refund: {refund_pct}% (₹{refund_amount:.2f})."
        messages.success(request, msg, extra_tags='customer_review')
        return redirect('/my-orders/?tab=cancelled')
    except Booking.DoesNotExist:
        messages.error(request, "Booking not found or unauthorized.", extra_tags='customer_review')
        return redirect('my_orders')




#==========================================================================
#    Manager & Admin Review Management Views
#==========================================================================

def manager_reviews(request):
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        my_buses = Bus.objects.filter(manager=manager)
        review_list = Review.objects.filter(bus__in=my_buses).select_related('user', 'bus')

        # Calculate Stats before filtering
        total_reviews = review_list.count()
        featured_count = review_list.filter(is_featured=True).count()
        avg_rating_val = review_list.aggregate(avg=Avg('rating'))['avg'] or 0.0
        avg_rating = round(float(avg_rating_val), 1)

        # Filters
        q = request.GET.get('q', '').strip()
        if q:
            review_list = review_list.filter(
                Q(user__name__icontains=q) |
                Q(user__email__icontains=q) |
                Q(bus__bus_name__icontains=q) |
                Q(comment__icontains=q)
            )

        rating_filter = request.GET.get('rating', '').strip()
        if rating_filter.isdigit():
            review_list = review_list.filter(rating=int(rating_filter))

        featured_filter = request.GET.get('featured', '').strip()
        if featured_filter == '1':
            review_list = review_list.filter(is_featured=True)
        elif featured_filter == '0':
            review_list = review_list.filter(is_featured=False)

        bus_id = request.GET.get('bus_id', '').strip()
        if bus_id.isdigit():
            review_list = review_list.filter(bus_id=int(bus_id))

        paginator = Paginator(review_list, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'manager': manager,
            'my_buses': my_buses,
            'page_obj': page_obj,
            'total_reviews': total_reviews,
            'featured_count': featured_count,
            'avg_rating': avg_rating,
            'q': q,
            'rating_filter': rating_filter,
            'featured_filter': featured_filter,
            'bus_id': bus_id,
        }
        return render(request, 'manager-reviews.html', context)
    except Exception as e:
        logger.error(f"Error loading manager reviews: {e}")
        messages.error(request, "Error loading review management page.")
        return redirect('manager_dashboard')


def admin_reviews(request):
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        all_buses = Bus.objects.all()
        all_managers = User.objects.filter(usertype='manager')
        review_list = Review.objects.all().select_related('user', 'bus', 'bus__manager')

        # Calculate Stats before filtering
        total_reviews = review_list.count()
        featured_count = review_list.filter(is_featured=True).count()
        avg_rating_val = review_list.aggregate(avg=Avg('rating'))['avg'] or 0.0
        avg_rating = round(float(avg_rating_val), 1)

        # Filters
        q = request.GET.get('q', '').strip()
        if q:
            review_list = review_list.filter(
                Q(user__name__icontains=q) |
                Q(user__email__icontains=q) |
                Q(bus__bus_name__icontains=q) |
                Q(bus__bus_number__icontains=q) |
                Q(comment__icontains=q)
            )

        manager_id = request.GET.get('manager_id', '').strip()
        if manager_id.isdigit():
            review_list = review_list.filter(bus__manager_id=int(manager_id))

        bus_id = request.GET.get('bus_id', '').strip()
        if bus_id.isdigit():
            review_list = review_list.filter(bus_id=int(bus_id))

        rating_filter = request.GET.get('rating', '').strip()
        if rating_filter.isdigit():
            review_list = review_list.filter(rating=int(rating_filter))

        featured_filter = request.GET.get('featured', '').strip()
        if featured_filter == '1':
            review_list = review_list.filter(is_featured=True)
        elif featured_filter == '0':
            review_list = review_list.filter(is_featured=False)

        paginator = Paginator(review_list, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'admin': admin,
            'all_buses': all_buses,
            'all_managers': all_managers,
            'page_obj': page_obj,
            'total_reviews': total_reviews,
            'featured_count': featured_count,
            'avg_rating': avg_rating,
            'q': q,
            'manager_id': manager_id,
            'bus_id': bus_id,
            'rating_filter': rating_filter,
            'featured_filter': featured_filter,
        }
        return render(request, 'admin-reviews.html', context)
    except Exception as e:
        logger.error(f"Error loading admin reviews: {e}")
        messages.error(request, "Error loading review management page.")
        return redirect('admin_dashboard')


def toggle_feature_review(request, review_id):
    manager = get_manager_user(request)
    admin = get_admin_user(request)

    if not manager and not admin:
        return HttpResponseForbidden("Unauthorized access.")

    try:
        review = Review.objects.select_related('bus', 'bus__manager').get(id=review_id)
    except Review.DoesNotExist:
        messages.error(request, "Review not found.")
        return redirect(request.META.get('HTTP_REFERER', 'index'))

    if manager and not admin:
        if review.bus.manager != manager:
            return HttpResponseForbidden("You are not authorized to feature reviews for buses belonging to another manager.")

    review.is_featured = not review.is_featured
    review.save()

    status_str = "featured on the homepage" if review.is_featured else "removed from homepage featuring"
    messages.success(request, f"Review for '{review.bus.bus_name}' has been {status_str}.")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('admin_reviews' if admin else 'manager_reviews')


def delete_review_management(request, review_id):
    if request.method != 'POST':
        return HttpResponseForbidden("POST request required.")

    manager = get_manager_user(request)
    admin = get_admin_user(request)

    if not manager and not admin:
        return HttpResponseForbidden("Unauthorized access.")

    try:
        review = Review.objects.select_related('bus', 'bus__manager').get(id=review_id)
    except Review.DoesNotExist:
        messages.error(request, "Review not found.")
        return redirect(request.META.get('HTTP_REFERER', 'index'))

    if manager and not admin:
        if review.bus.manager != manager:
            return HttpResponseForbidden("You are not authorized to delete reviews for another manager's buses.")

    bus_name = review.bus.bus_name
    review.delete()
    messages.success(request, f"Review for '{bus_name}' deleted successfully.")

    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('admin_reviews' if admin else 'manager_reviews')

