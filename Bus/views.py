from django.shortcuts import render, redirect
from django.http import HttpResponse
from .models import User, Bus, Booking, Route, SeatBooking, Schedule, Contact
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator, Page, EmptyPage, PageNotAnInteger
import random
import razorpay
import json
import logging
from datetime import date, timedelta

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
        raw_passengers = request.GET.get('passengers')

        # Determine source city
        if 'from' in request.GET or 'source' in request.GET:
            if is_valid_city(raw_from):
                from_city = raw_from.strip()
                request.session['journey_from'] = from_city
            else:
                if raw_from == "":
                    from_city = ""
                    request.session['journey_from'] = ""
                else:
                    session_from = request.session.get('journey_from')
                    from_city = session_from.strip() if is_valid_city(session_from) else ""
        else:
            session_from = request.session.get('journey_from')
            from_city = session_from.strip() if is_valid_city(session_from) else ""

        # Determine destination city
        if 'to' in request.GET or 'destination' in request.GET:
            if is_valid_city(raw_to):
                to_city = raw_to.strip()
                request.session['journey_to'] = to_city
            else:
                if raw_to == "":
                    to_city = ""
                    request.session['journey_to'] = ""
                else:
                    session_to = request.session.get('journey_to')
                    to_city = session_to.strip() if is_valid_city(session_to) else ""
        else:
            session_to = request.session.get('journey_to')
            to_city = session_to.strip() if is_valid_city(session_to) else ""

        # Determine travel date
        if 'date' in request.GET:
            if is_valid_date(raw_date):
                travel_date = raw_date.strip()
                request.session['journey_date'] = travel_date
            else:
                if raw_date == "":
                    travel_date = date.today().strftime("%Y-%m-%d")
                    request.session['journey_date'] = travel_date
                else:
                    session_date = request.session.get('journey_date')
                    travel_date = session_date.strip() if is_valid_date(session_date) else date.today().strftime("%Y-%m-%d")
        else:
            session_date = request.session.get('journey_date')
            travel_date = session_date.strip() if is_valid_date(session_date) else date.today().strftime("%Y-%m-%d")

        # Determine passengers count
        if 'passengers' in request.GET:
            if is_valid_passengers(raw_passengers):
                passengers = raw_passengers.strip()
                request.session['num_passengers'] = passengers
            else:
                if raw_passengers == "":
                    passengers = "1"
                    request.session['num_passengers'] = "1"
                else:
                    session_passengers = request.session.get('num_passengers')
                    passengers = session_passengers.strip() if is_valid_passengers(session_passengers) else "1"
        else:
            session_passengers = request.session.get('num_passengers')
            passengers = session_passengers.strip() if is_valid_passengers(session_passengers) else "1"

        # Determine round_trip option
        if 'round_trip' in request.GET:
            raw_round_trip = request.GET.get('round_trip')
            is_round_trip = True if raw_round_trip in ['1', 'true', 'True', 'on'] else False
            request.session['round_trip'] = is_round_trip
        else:
            is_round_trip = request.session.get('round_trip', False)

        return {
            'from_city': from_city,
            'to_city': to_city,
            'travel_date': travel_date,
            'passengers': passengers,
            'round_trip': is_round_trip,
        }
    except Exception as e:
        logger.error(f"Error getting search details: {e}")
        return {
            'from_city': '',
            'to_city': '',
            'travel_date': date.today().strftime("%Y-%m-%d"),
            'passengers': '1',
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
        subtotal = sum(booking.amount for booking in bookings)
        gst_fees = int((subtotal * 5) / 100)
        convenience_fee = 40 * len(bookings)
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
                }
                groups.append(group_by_key[key])

            group = group_by_key[key]
            group['booking_ids'].append(str(booking.id))
            group['seat_numbers'].append(booking.seat_number)
            group['passengers'].append(make_passenger_dict(booking))
            group['total_fare'] += booking.amount

        for group in groups:
            group['seat_numbers_str'] = ", ".join(group['seat_numbers'])
            group['booking_ids_str'] = ",".join(group['booking_ids'])
            group['num_seats'] = len(group['seat_numbers'])

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
            elif group['travel_date'] >= today:
                upcoming.append(group)
            else:
                past.append(group)

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
        context = {
            'routes': routes,
            'sources': sources,
            'destinations': destinations
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
            welcome_subject = "Welcome to BusYatra"
            welcome_message = f"Hello {name},\nWelcome to BusYatra!\nYour account has been created successfully For BusYatra.\nLogin Email: {email}\nRegards,\nBusYatra Team"
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
    buses = Bus.objects.all().order_by('id')

    if search['from_city'] and search['to_city']:
        if search.get('round_trip'):
            buses = buses.filter(
                (Q(source__iexact=search['from_city']) & Q(destination__iexact=search['to_city'])) |
                (Q(source__iexact=search['to_city']) & Q(destination__iexact=search['from_city']))
            )
        else:
            buses = buses.filter(
                source__iexact=search['from_city'],
                destination__iexact=search['to_city']
            )

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
        'passengers': search['passengers'],
        'round_trip': search.get('round_trip', False),
    })

def bus_detail(request, pk):
    try:
        bus = Bus.objects.get(id=pk)
    except Bus.DoesNotExist:
        return redirect('bus_list')

    search = get_search_details(request)
    set_live_available_seats([bus], search['travel_date'])

    return render(request, 'bus_detail.html', {
        'bus': bus,
        'from_city': search['from_city'],
        'to_city': search['to_city'],
        'travel_date': search['travel_date'],
        'passengers': search['passengers'],
    })

def seat_booking(request, pk=None):
    customer = get_customer_user(request)
    if not customer:
        return redirect("login")

    try:
        bus = Bus.objects.get(id=pk) if pk else Bus.objects.first()
        if not bus:
            return redirect("bus_list")

        raw_date = request.GET.get("date") or request.session.get("journey_date")
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

def payment(request):
    customer = get_customer_user(request)
    if not customer:
        return redirect("login")

    try:
        booking_ids = request.GET.get("booking_ids")
        bookings = get_customer_bookings(customer, booking_ids)
        if not bookings.exists():
            return redirect("index")

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

        first_booking = bookings.first()
        return render(request, "payment.html", {
            "bookings": bookings,
            "booking_ids": booking_ids,
            "bus": first_booking.bus,
            "travel_date": first_booking.travel_date,
            "seats": ", ".join([booking.seat_number for booking in bookings]),
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
    
    # 0.5 inch margins (36 points) for maximum space utilization and clean framing
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles to establish beautiful visual hierarchy
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
    bus = first_b.bus
    
    # 1. Company Branding Header Section
    logo_path = finders.find('assets/images/logo.png')
    if logo_path:
        try:
            logo_element = Image(logo_path, width=110, height=35)
        except Exception:
            logo_element = Paragraph("<b>BusYatra</b>", brand_style)
    else:
        logo_element = Paragraph("<b>BusYatra</b>", brand_style)

    # Wrap logo with tagline below it
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
    header_right_text = f"<b>E-Ticket Receipt</b><br/><font color='#64748B'>Booking Date: {booking_date_str}</font>"
    header_right_p = Paragraph(header_right_text, receipt_meta_style)
    
    header_right_data = [
        [Paragraph("E-Ticket Receipt", receipt_title_style)],
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

    # Professional divider line
    divider = Table([['']], colWidths=[540])
    divider.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1, HexColor('#E2E8F0')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 8))

    # 2. Journey Details & QR Code (Side-by-Side)
    departure_time_str = format_time(bus.departure_time)
    arrival_time_str = format_time(bus.arrival_time)
    travel_date_str = format_date(first_b.travel_date)

    # Route display: Source → Destination (Single row)
    route_html = f"<font size=10><b>{bus.source}</b></font> <font size=10 color='#3B82F6'><b>→</b></font> <font size=10><b>{bus.destination}</b></font>"
    route_p = Paragraph(route_html, route_style)

    journey_left_data = [
        [Paragraph("<b>Route:</b>", label_style), route_p],
        [Paragraph("<b>Bus Name:</b>", label_style), Paragraph(bus.bus_name, value_style)],
        [Paragraph("<b>Bus Number:</b>", label_style), Paragraph(bus.bus_number, value_style)],
        [Paragraph("<b>Travel Date:</b>", label_style), Paragraph(travel_date_str, value_style)],
        [Paragraph("<b>Departure:</b>", label_style), Paragraph(departure_time_str, value_style)],
        [Paragraph("<b>Arrival:</b>", label_style), Paragraph(arrival_time_str, value_style)],
    ]
    journey_left_table = Table(journey_left_data, colWidths=[100, 260])
    journey_left_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    # Generate QR Code details
    booking_ids_list = [f"BY-{b.id}" for b in bookings]
    seat_numbers_list = [b.seat_number for b in bookings]
    passenger_names_list = [b.passenger_name for b in bookings]
    
    payment_status_str = getattr(first_b, 'payment_status', 'SUCCESS' if first_b.payment else 'FAILED').upper()
    booking_status_str = getattr(first_b, 'booking_status', first_b.status).upper()

    qr_data = (
        f"Booking ID: {', '.join(booking_ids_list)}\n"
        f"Passenger: {', '.join(passenger_names_list)}\n"
        f"Bus: {bus.bus_number}\n"
        f"Date: {travel_date_str}\n"
        f"Seat: {', '.join(seat_numbers_list)}\n"
        f"Payment: {payment_status_str}\n"
        f"Booking: {booking_status_str}"
    )
    
    qr = qrcode.QRCode(version=1, box_size=3, border=1)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#0F172A", back_color="white")
    
    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    
    qr_flowable = Image(qr_buffer, width=105, height=105)
    
    # Package QR Code and subtitle
    journey_right_data = [
        [qr_flowable],
        [Paragraph("Show QR while Boarding", qr_text_style)]
    ]
    journey_right_table = Table(journey_right_data, colWidths=[150])
    journey_right_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    # Outer Section Table for Journey & QR
    journey_section_table = Table([[journey_left_table, journey_right_table]], colWidths=[380, 160])
    journey_section_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    elements.append(Paragraph("Journey Details", section_heading_style))
    elements.append(journey_section_table)
    elements.append(Spacer(1, 10))

    # 3. Status Badges and Transaction Details
    def make_badge(text, badge_type):
        if badge_type == 'success':
            bg = HexColor('#ECFDF5')
            fg = HexColor('#047857')
        elif badge_type == 'warning':
            bg = HexColor('#FEF3C7')
            fg = HexColor('#B45309')
        else: # danger
            bg = HexColor('#FEE2E2')
            fg = HexColor('#B91C1C')
            
        badge_p_style = ParagraphStyle(
            'BadgeP',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            alignment=1, # Center
            textColor=fg
        )
        b_table = Table([[Paragraph(text, badge_p_style)]], colWidths=[70], rowHeights=[16])
        b_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
        ]))
        return b_table

    # Build Badges
    p_badge_type = 'success' if payment_status_str in ['PAID', 'SUCCESS'] else ('warning' if payment_status_str == 'PENDING' else 'danger')
    b_badge_type = 'success' if booking_status_str in ['BOOKED', 'SUCCESS', 'COMPLETED'] else 'danger'
    
    pay_badge = make_badge(payment_status_str, p_badge_type)
    book_badge = make_badge(booking_status_str, b_badge_type)

    payment_id_val = first_b.payment_id or "N/A"
    subtotal = sum(b.amount for b in bookings)
    gst_fees = int((subtotal * 5) / 100)
    convenience_fee = 40 * len(bookings)
    total_amount = subtotal + gst_fees + convenience_fee

    payment_data = [
        [Paragraph("<b>Payment ID:</b>", label_style), Paragraph(payment_id_val, value_style), Paragraph("<b>Payment Status:</b>", label_style), pay_badge],
        # Display the total paid amount using "Rs." instead of "₹" to prevent rendering issues in PDF readers
        [Paragraph("<b>Booking Status:</b>", label_style), book_badge, Paragraph("<b>Total Paid:</b>", label_style), Paragraph(f"Rs. {total_amount:.2f} (incl. GST & fees)", value_style)],
        [Paragraph("<b>Payment Method:</b>", label_style), Paragraph("Online (Razorpay)", value_style), Paragraph("", label_style), Paragraph("", value_style)]
    ]
    payment_table = Table(payment_data, colWidths=[100, 170, 100, 170])
    payment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    elements.append(Paragraph("Transaction Details", section_heading_style))
    elements.append(payment_table)
    elements.append(Spacer(1, 10))

    # 4. Passenger Details Table
    table_data = [[
        Paragraph("Booking ID", table_header_style),
        Paragraph("Passenger Name", table_header_style),
        Paragraph("Email", table_header_style),
        Paragraph("Age", table_header_style),
        Paragraph("Gender", table_header_style),
        Paragraph("Seat No", table_header_style),
        Paragraph("Fare", table_header_style)
    ]]

    for b in bookings:
        table_data.append([
            Paragraph(f"BY-{b.id}", table_cell_style),
            Paragraph(b.passenger_name, table_cell_style),
            Paragraph(b.user.email, table_cell_style), # booking.user.email
            Paragraph(str(b.passenger_age), table_cell_style),
            Paragraph(b.passenger_gender, table_cell_style),
            Paragraph(b.seat_number, table_cell_style),
            # Display passenger fare using "Rs." instead of "₹" to prevent rendering issues in PDF readers
            Paragraph(f"Rs. {b.amount:.2f}", table_cell_style)
        ])

    passenger_table = Table(table_data, colWidths=[75, 100, 140, 30, 50, 65, 80])
    passenger_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#0F172A')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(Paragraph("Passenger & Seat Details", section_heading_style))
    elements.append(passenger_table)
    elements.append(Spacer(1, 10))

    # 5. Thank You & Have a Safe Journey Section
    elements.append(Paragraph("Thank you for choosing BusYatra. Have a Safe Journey!", thankyou_style))
    elements.append(Spacer(1, 5))

    # 6. Terms & Conditions Section Box
    terms_html = (
        "<b>Terms & Conditions:</b><br/>"
        "• Carry a valid Government ID.<br/>"
        "• Reach boarding point at least 30 minutes before departure.<br/>"
        "• Keep this ticket until journey completion.<br/>"
        "• Ticket is non-transferable.<br/>"
        "• Cancellation and refund are subject to BusYatra policy.<br/>"
        "• BusYatra is not responsible for delays caused by weather or traffic.<br/>"
        "• Show this QR Code while boarding.<br/>"
        "• Contact Support: <b>support@busyatra.com</b>"
    )
    terms_p = Paragraph(terms_html, terms_style)
    terms_table = Table([[terms_p]], colWidths=[540])
    terms_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 0.5, HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(terms_table)
    elements.append(Spacer(1, 12))

    # 7. Footer
    footer_html = "BusYatra  •  Premium Bus Ticket Reservation  •  www.busyatra.com  •  support@busyatra.com"
    elements.append(Paragraph(footer_html, footer_text_style))

    # Build the document
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
    try:
        admin = get_admin_user(request)
        if not admin:
            return redirect('login')
        return render(request, 'admin-settings.html', {'login_user': admin})
    except Exception as e:
        logger.error(f"Error in admin settings view: {e}")
        return redirect('login')
