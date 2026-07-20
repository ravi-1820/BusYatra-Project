from django.shortcuts import render, redirect
from django.http import HttpResponse
from .models import User, Bus, Booking, Route, SeatBooking, Schedule, Contact
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDate, TruncMonth
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
    """
    Returns the logged-in customer User object if valid, otherwise None.
    """
    return get_logged_in_user(request, 'customer')

def get_manager_user(request):
    """
    Returns the logged-in manager User object if valid, otherwise None.
    """
    return get_logged_in_user(request, 'manager')

def get_admin_user(request):
    """
    Returns the logged-in admin User object if valid, otherwise None.
    """
    return get_logged_in_user(request, 'admin')

def get_logged_in_user(request, usertype):
    """
    Session email se user nikalta hai. User na mile to None return karta hai.
    """
    email = request.session.get('email')
    if not email:
        return None
    try:
        return User.objects.get(email=email, usertype=usertype)
    except User.DoesNotExist:
        return None

def parse_booking_ids(booking_ids):
    """
    "1,2,3" ko [1, 2, 3] me badalta hai. Galat values ignore hoti hain.
    """
    if not booking_ids:
        return []
    return [int(item) for item in booking_ids.split(",") if item.strip().isdigit()]

def get_customer_bookings(customer, booking_ids):
    """
    Sirf logged-in customer ki bookings return karta hai.
    """
    ids = parse_booking_ids(booking_ids)
    if not ids:
        return Booking.objects.none()
    return Booking.objects.filter(id__in=ids, user=customer)

def get_search_details(request):
    """
    Search values GET se lo. Agar GET me value nahi hai to session se lo.
    """
    fields = {
        'from': 'journey_from',
        'to': 'journey_to',
        'date': 'journey_date',
        'passengers': 'num_passengers',
    }

    data = {}
    for query_name, session_name in fields.items():
        default = '1' if query_name == 'passengers' else None
        value = request.GET.get(query_name)

        if query_name in request.GET:
            request.session[session_name] = value
        else:
            value = request.session.get(session_name, default)

        data[query_name] = value

    return {
        'from_city': data['from'],
        'to_city': data['to'],
        'travel_date': data['date'],
        'passengers': data['passengers'],
    }

def travel_date_or_today(travel_date):
    """
    Seat count ke liye date chahiye. Date na mile to aaj ki date use hoti hai.
    """
    return travel_date or date.today().strftime("%Y-%m-%d")

def booked_seat_count(bus, travel_date):
    """
    Sirf successful paid bookings ko booked seat maana gaya hai.
    """
    return Booking.objects.filter(
        bus=bus,
        travel_date=travel_date,
        payment=True,
        payment_status="success",
        booking_status="booked"
    ).count()

def set_live_available_seats(buses, travel_date):
    """
    Har bus par current available_seats value attach karta hai.
    """
    date_to_use = travel_date_or_today(travel_date)
    for bus in buses:
        bus.available_seats = max(0, bus.total_seats - booked_seat_count(bus, date_to_use))

def get_booked_seats(bus, travel_date):
    """
    Seat map ke liye blocked seat numbers ki list.
    """
    return list(
        SeatBooking.objects.filter(
            bus=bus,
            journey_date=travel_date
        ).values_list("seat_number", flat=True)
    )

def calculate_payment_summary(bookings):
    """
    Fare summary ek jagah calculate hoti hai.
    """
    subtotal = sum(booking.amount for booking in bookings)
    gst_fees = int((subtotal * 5) / 100)
    convenience_fee = 40 * len(bookings)
    total_price = subtotal + gst_fees + convenience_fee
    return subtotal, gst_fees, convenience_fee, total_price

def make_passenger_dict(booking):
    """
    Template me passenger details dikhane ke liye simple dict.
    """
    return {
        'name': booking.passenger_name,
        'age': booking.passenger_age,
        'gender': booking.passenger_gender,
        'seat': booking.seat_number,
    }

def build_order_groups(bookings):
    """
    Ek payment me kai seats ho sakti hain. Unhe ek card/group me combine karta hai.
    """
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

def split_orders_by_date(groups):
    """
    Orders ko upcoming, past, cancelled lists me baantta hai.
    """
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

def create_pending_bookings(customer, bus, seats, travel_date, post_data):
    """
    Selected seats ke liye unpaid bookings banata hai.
    """
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

def mark_bookings_paid(bookings, payment_id, order_id, signature):
    """
    Payment success ke baad booking confirm aur seat block karta hai.
    """
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

def mark_bookings_failed(bookings):
    """
    Payment fail ho to booking cancel karta hai.
    """
    for booking in bookings:
        booking.payment = False
        booking.payment_status = "failed"
        booking.booking_status = "cancelled"
        booking.status = "cancelled"
        booking.save()

#==========================================================================
#    Customer Views
#==========================================================================

def index(request):
    """
    Renders the homepage with routes, distinct sources, and destinations.
    """
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
    """
    Renders the about page.
    """
    return render(request, 'about.html')

def contact(request):
    """
    Handles user contact form submission.
    """
    if request.method == 'POST':
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
            success_msg = "Message Sent! Our support team will get back to you within 24 hours."
            return render(request, 'contact.html', {'msg': success_msg})
        except Exception as e:
            logger.error(f"Error saving contact message: {e}")
            error_msg = "Something went wrong. Please try again."
            return render(request, 'contact.html', {'msg': error_msg})

    return render(request, 'contact.html')

def register(request):
    """
    Handles new user registration with email and mobile uniqueness validations.
    """
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
            welcome_message = f"Hello {name},\n\nWelcome to BusYatra!\nYour account has been created successfully.\nLogin Email: {email}\n\nRegards,\nTeam BusYatra"
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
    """
    Handles user login by verifying credentials and sending a one-time OTP.
    """
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        try:
            user = User.objects.get(email=email)
            if user.password == password:
                otp = random.randint(100000, 999999)
                request.session['otp'] = str(otp)
                request.session['email'] = user.email

                # Log OTP for local/offline debugging
                logger.info(f"OTP generated for {user.email}: {otp}")

                # Send OTP via email
                try:
                    send_mail(
                        "BusYatra Login OTP",
                        f"Hello {user.name},\n\nYour Login OTP is: {otp}\n\nDo not share this OTP with anyone.\n\nBusYatra Team",
                        settings.EMAIL_HOST_USER,
                        [user.email],
                        fail_silently=False,
                    )
                except Exception as email_err:
                    logger.error(f"OTP email could not be sent to {user.email}: {email_err}")

                return redirect('verify_otp')
            else:
                return render(request, 'login.html', {'msg': "Password doesn't match..!"})
        except User.DoesNotExist:
            return render(request, 'login.html', {'msg': "Email doesn't exist..!"})
        except Exception as e:
            logger.error(f"Login Error: {e}")
            return render(request, 'login.html', {'msg': "Something went wrong. Please try again."})

    return render(request, 'login.html')

def verify_otp(request):
    """
    Verifies the login OTP stored in the session.
    """
    if request.method == "POST":
        try:
            user_otp = request.POST.get("otp", "").strip()
            session_otp = request.session.get("otp")
            email = request.session.get("email")

            if not email:
                return redirect("login")

            if user_otp == session_otp:
                user = User.objects.get(email=email)
                request.session["email"] = user.email
                request.session["name"] = user.name
                request.session["profile"] = user.profile.url if user.profile else ""
                request.session["usertype"] = user.usertype

                if "otp" in request.session:
                    del request.session["otp"]

                if user.usertype == "customer":
                    return redirect("index")
                elif user.usertype == "manager":
                    return redirect("manager_dashboard")
                else:
                    return redirect("admin_dashboard")
            else:
                return render(request, "verify_otp.html", {"msg": "Invalid OTP. Please enter the correct OTP."})
        except User.DoesNotExist:
            return render(request, "verify_otp.html", {"msg": "User account not found."})
        except Exception as e:
            logger.error(f"OTP Verification Error: {e}")
            return render(request, "verify_otp.html", {"msg": "Something went wrong. Please try again."})

    return render(request, "verify_otp.html")

def forgot_password(request):
    """
    Handles forgot password request by verifying email and sending OTP.
    """
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
    """
    Verifies the forgot password OTP.
    """
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
    """
    Resets the user's password to the newly provided one.
    """
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
    """
    Flushes the current session and logs the user out.
    """
    request.session.flush()
    return redirect('login')

def account(request):
    """
    Handles user profile detail updates.
    """
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
    """
    Deletes the current user account and clears the session.
    """
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
    """
    Bus search page: route filter, pagination, aur live available seats.
    """
    search = get_search_details(request)
    buses = Bus.objects.all().order_by('id')

    if search['from_city'] and search['to_city']:
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
    })

def bus_detail(request, pk):
    """
    Single bus detail page with live available seat count.
    """
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
    """
    Seat map dikhata hai aur selected seats ki pending booking banata hai.
    """
    customer = get_customer_user(request)
    if not customer:
        return redirect("login")

    try:
        bus = Bus.objects.get(id=pk) if pk else Bus.objects.first()
        if not bus:
            return redirect("bus_list")

        travel_date = request.GET.get("date") or request.session.get("journey_date")
        if not travel_date:
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
    """
    Renders customer dashboard page.
    """
    customer = get_customer_user(request)
    if not customer:
        return redirect('login')
    return render(request, 'dashboard.html')

def my_orders(request):
    """
    Customer ki bookings ko readable groups me dikhata hai.
    """
    customer = get_customer_user(request)
    if not customer:
        return redirect('login')

    try:
        bookings = Booking.objects.filter(user=customer).order_by('-id')
        grouped_bookings = build_order_groups(bookings)
        upcoming, past, cancelled = split_orders_by_date(grouped_bookings)

        return render(request, 'my-orders.html', {
            'user': customer,
            'bookings': grouped_bookings,
            'upcoming_bookings': upcoming,
            'past_bookings': past,
            'cancelled_bookings': cancelled,
        })
    except Exception as e:
        logger.error(f"My Orders View Error: {e}")
        return HttpResponse("An error occurred loading bookings.")

def payment(request):
    """
    Payment page: booking verify, amount calculate, Razorpay order create.
    """
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
    """
    Generates PDF binary stream for list of bookings using ReportLab.
    """
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
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=HexColor('#0F172A')
    )
    header_right_style = ParagraphStyle(
        'HeaderRight', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, alignment=2, textColor=HexColor('#475569')
    )
    section_heading_style = ParagraphStyle(
        'SectionHeading', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=14, leading=18, textColor=HexColor('#0D6EFD'), spaceAfter=6
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=HexColor('#475569')
    )
    value_style = ParagraphStyle(
        'Value', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, textColor=HexColor('#0F172A')
    )
    table_header_style = ParagraphStyle(
        'TableHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, alignment=1, textColor=colors.white
    )
    table_cell_style = ParagraphStyle(
        'TableCell', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leading=12, alignment=1
    )
    footer_style = ParagraphStyle(
        'FooterText', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1, textColor=HexColor('#0F172A')
    )

    elements = []

    logo_path = finders.find('assets/images/logo.png')
    if logo_path:
        try:
            logo_element = Image(logo_path, width=120, height=40)
        except Exception:
            logo_element = Paragraph("<b>BusYatra</b>", title_style)
    else:
        logo_element = Paragraph("<b>BusYatra</b>", title_style)

    booking_date_str = format_date(bookings.first().booking_date)
    header_right_text = f"<b>E-Ticket Receipt</b><br/>Booking Date: {booking_date_str}"
    header_right_p = Paragraph(header_right_text, header_right_style)

    header_table = Table([[logo_element, header_right_p]], colWidths=[270, 270])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(header_table)

    line_table = Table([['']], colWidths=[540])
    line_table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 1.5, HexColor('#E2E8F0')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 10))

    elements.append(Paragraph("Journey Details", section_heading_style))
    first_b = bookings.first()
    bus = first_b.bus

    departure_time_str = format_time(bus.departure_time)
    arrival_time_str = format_time(bus.arrival_time)
    travel_date_str = format_date(first_b.travel_date)

    journey_data = [
        [Paragraph("Bus Name:", label_style), Paragraph(bus.bus_name, value_style), Paragraph("Bus Number:", label_style), Paragraph(bus.bus_number, value_style)],
        [Paragraph("Source:", label_style), Paragraph(bus.source, value_style), Paragraph("Destination:", label_style), Paragraph(bus.destination, value_style)],
        [Paragraph("Departure Time:", label_style), Paragraph(departure_time_str, value_style), Paragraph("Arrival Time:", label_style), Paragraph(arrival_time_str, value_style)],
        [Paragraph("Travel Date:", label_style), Paragraph(travel_date_str, value_style), Paragraph("", label_style), Paragraph("", value_style)]
    ]

    journey_table = Table(journey_data, colWidths=[100, 170, 100, 170])
    journey_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(journey_table)
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("Transaction Details", section_heading_style))
    payment_status_str = getattr(first_b, 'payment_status', 'SUCCESS' if first_b.payment else 'FAILED').upper()
    booking_status_str = getattr(first_b, 'booking_status', first_b.status).upper()
    payment_id_val = first_b.payment_id or "N/A"

    subtotal = sum(b.amount for b in bookings)
    gst_fees = int((subtotal * 5) / 100)
    convenience_fee = 40 * len(bookings)
    total_amount = subtotal + gst_fees + convenience_fee

    payment_data = [
        [Paragraph("Payment ID:", label_style), Paragraph(payment_id_val, value_style), Paragraph("Payment Status:", label_style), Paragraph(f"<b>{payment_status_str}</b>", value_style)],
        [Paragraph("Booking Status:", label_style), Paragraph(f"<b>{booking_status_str}</b>", value_style), Paragraph("Total Paid Amount:", label_style), Paragraph(f"₹{total_amount} (incl. GST & fees)", value_style)]
    ]
    payment_table = Table(payment_data, colWidths=[100, 170, 100, 170])
    payment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(payment_table)
    elements.append(Spacer(1, 15))

    elements.append(Paragraph("Passenger & Seat Details", section_heading_style))
    table_data = [[
        Paragraph("Booking ID", table_header_style),
        Paragraph("Passenger Name", table_header_style),
        Paragraph("Age", table_header_style),
        Paragraph("Gender", table_header_style),
        Paragraph("Seat No", table_header_style),
        Paragraph("Fare", table_header_style)
    ]]

    for b in bookings:
        table_data.append([
            Paragraph(f"BY-{b.id}", table_cell_style),
            Paragraph(b.passenger_name, table_cell_style),
            Paragraph(str(b.passenger_age), table_cell_style),
            Paragraph(b.passenger_gender, table_cell_style),
            Paragraph(b.seat_number, table_cell_style),
            Paragraph(f"₹{b.amount}", table_cell_style)
        ])

    passenger_table = Table(table_data, colWidths=[80, 160, 45, 65, 80, 110])
    passenger_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#0F172A')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CBD5E1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(passenger_table)
    elements.append(Spacer(1, 30))

    elements.append(Paragraph("Thank you for choosing BusYatra.", footer_style))
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

def ticket(request):
    """
    Payment callback verify karta hai. Success par ticket dikhata hai.
    """
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
                    body=f"Dear {customer.name},\n\nThank you for choosing BusYatra. Your booking has been successfully confirmed!\n\nPassenger(s): {passenger_names}\nSeat(s): {seat_numbers}\n\nPlease find your attached e-ticket PDF containing details and guidelines.\n\nWarm regards,\nTeam BusYatra",
                    from_email=settings.EMAIL_HOST_USER,
                    to=[customer.email]
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
    """
    Logged-in customer ke ticket ka PDF download karata hai.
    """
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
        response['Content-Disposition'] = 'attachment; filename="BusYatra_Ticket.pdf"'
        return response
    except Exception as e:
        logger.error(f"PDF Download Error: {e}")
        return HttpResponse("Error generating PDF")

def manager_bookings(request):
    """
    Lists all bookings placed on buses owned by the logged-in manager.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    buses = Bus.objects.filter(manager=manager)
    bookings = Booking.objects.filter(bus__in=buses).order_by('-booking_date')
    return render(request, 'manager-bookings.html', {'bookings': bookings})

def manager_buses(request):
    """
    Lists the manager's active bus fleet.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    buses = Bus.objects.filter(manager=manager)
    return render(request, 'manager-buses.html', {'buses': buses})

def add_bus(request):
    """
    Allows a manager to register a new bus with unique license number check.
    """
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
    """
    Modifies configuration of a specific bus owned by the manager.
    """
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
    """
    Deletes a specific bus owned by the logged-in manager.
    """
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
    """
    Lists routes managed by the active manager.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    routes = Route.objects.filter(manager=manager)
    return render(request, 'manager-routes.html', {'routes': routes})

def add_route(request):
    """
    Registers a new unique route.
    """
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
    """
    Updates route configurations.
    """
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
    """
    Deletes route records.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        route = Route.objects.get(id=route_id, manager=manager)
        route.delete()
    except Route.DoesNotExist:
        pass
    return redirect('manager_routes')

def manager_dashboard(request):
    """
    Compiles operational fleet and business metrics for the manager.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        my_buses = Bus.objects.filter(manager=manager)
        fleet_count = my_buses.count()
        route_count = Route.objects.filter(manager=manager).count()

        schedules = Schedule.objects.filter(bus__in=my_buses)
        schedule_count = schedules.count()

        bookings = Booking.objects.filter(bus__in=my_buses)
        bookings_count = bookings.count()
        passenger_count = bookings_count

        net_revenue = bookings.filter(payment=True, status__in=['booked', 'completed']).aggregate(total=Sum('amount'))['total'] or 0

        if schedules.exists():
            total_capacity = sum(s.bus.total_seats for s in schedules)
            booked_seats = SeatBooking.objects.filter(bus__in=my_buses, journey_date__in=[s.journey_date for s in schedules]).count()
            available_seats = max(0, total_capacity - booked_seats)
        else:
            total_capacity = sum(b.total_seats for b in my_buses)
            booked_seats = SeatBooking.objects.filter(bus__in=my_buses).count()
            available_seats = max(0, total_capacity - booked_seats)

        recent_bookings = bookings.order_by('-id')[:5]
        recent_buses = my_buses.order_by('-id')[:5]

        active_trips_list = []
        for s in schedules.order_by('-journey_date')[:5]:
            reserved_count = SeatBooking.objects.filter(bus=s.bus, journey_date=s.journey_date).count()
            occupancy_pct = int((reserved_count / s.bus.total_seats * 100)) if s.bus.total_seats > 0 else 0
            active_trips_list.append({
                'schedule': s,
                'reserved_count': reserved_count,
                'occupancy_pct': occupancy_pct
            })

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
        return render(request, 'manager-dashboard.html', context)
    except Exception as e:
        logger.error(f"Manager Dashboard Error: {e}")
        return HttpResponse("An error occurred loading dashboard data.")

def manager_reports(request):
    """
    Renders reports interface.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')
    return render(request, 'manager-reports.html')

def manager_schedules(request):
    """
    Creates and schedules travel trip calendars.
    """
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

    schedules = Schedule.objects.filter(bus__in=buses).order_by('-journey_date')
    context = {
        'schedules': schedules,
        'buses': buses
    }
    return render(request, 'manager-schedules.html', context)

def edit_schedule(request, pk):
    """
    Alters scheduled calendars.
    """
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
    """
    Deletes schedule sheets.
    """
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
    """
    Displays real-time booking lists and seat maps for the manager.
    """
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
    """
    Alters settings profile for a manager.
    """
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
    """
    Renders details for a customer booking on one of the manager's buses.
    """
    manager = get_manager_user(request)
    if not manager:
        return redirect('login')

    try:
        booking = Booking.objects.get(id=booking_id, bus__manager=manager)
        return render(request, 'manager-booking-detail.html', {'booking': booking})
    except Booking.DoesNotExist:
        return redirect('manager_bookings')

def manager_cancel_booking(request, booking_id):
    """
    Cancels a customer's booking. Frees up their seat allocation.
    """
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
    """
    Assembles metrics dashboard across the system.
    """
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
        return render(request, 'admin-dashboard.html', context)
    except Exception as e:
        logger.error(f"Admin Dashboard Error: {e}")
        return HttpResponse("An error occurred loading admin dashboard data.")

def admin_users(request):
    """
    Lists customer accounts. Supports search filters.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    query = request.GET.get('search', '').strip()
    customers = User.objects.filter(usertype='customer')
    if query:
        customers = customers.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )

    return render(request, 'admin-users.html', {'customers': customers, 'search_query': query, 'login_user': admin})

def admin_add_customer(request):
    """
    Creates customer profiles from admin console.
    """
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
    """
    Updates configuration profiles of customer accounts.
    """
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
    """
    Deletes customer profiles.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    User.objects.filter(id=user_id, usertype='customer').delete()
    return redirect('admin_users')

def admin_customer_detail(request, user_id):
    """
    Renders billing ledger and profile history metrics for a customer.
    """
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
    """
    Lists registered managers. Supports search queries.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    query = request.GET.get('search', '').strip()
    managers = User.objects.filter(usertype='manager')
    if query:
        managers = managers.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query)
        )

    for mgr in managers:
        mgr.buses_count = Bus.objects.filter(manager=mgr).count()
        mgr.bookings_count = Booking.objects.filter(bus__manager=mgr).count()

    return render(request, 'admin-managers.html', {'managers': managers, 'search_query': query, 'login_user': admin})

def admin_add_manager(request):
    """
    Registers a new manager profile.
    """
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
    """
    Updates profiles of manager accounts.
    """
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
    """
    Removes manager configurations.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    User.objects.filter(id=user_id, usertype='manager').delete()
    return redirect('admin_managers')

def admin_manager_detail(request, user_id):
    """
    Renders details of a manager, showing their fleet and generated revenue.
    """
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
    """
    Lists registered buses.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    buses = Bus.objects.all()
    return render(request, 'admin-buses.html', {'buses': buses, 'login_user': admin})

def admin_add_bus(request):
    """
    Registers a new bus from the admin panel.
    """
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
            msg = "Duplicate Bus Number should not be allowed."
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
    """
    Alters bus config specs from the admin panel.
    """
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
            msg = "Duplicate Bus Number should not be allowed."
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
    """
    Deletes bus records.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    Bus.objects.filter(id=bus_id).delete()
    return redirect('admin_buses')

def admin_routes(request):
    """
    Lists routes. Matches fleet counts.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    routes = Route.objects.all()
    for route in routes:
        route.fleet_count = Bus.objects.filter(source=route.source, destination=route.destination).count()
    return render(request, 'admin-routes.html', {'routes': routes, 'login_user': admin})

def admin_add_route(request):
    """
    Registers a new route from the admin panel.
    """
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
            msg = "Duplicate Route should not be created."
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
    """
    Alters route configurations.
    """
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
            msg = "Duplicate Route should not be created."
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
    """
    Deletes route records.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    Route.objects.filter(id=route_id).delete()
    return redirect('admin_routes')

def admin_schedules(request):
    """
    Lists schedules.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    schedules = Schedule.objects.all()
    return render(request, 'admin-schedules.html', {'schedules': schedules, 'login_user': admin})

def admin_add_schedule(request):
    """
    Registers a new schedule calendar.
    """
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
    """
    Alters travel schedules.
    """
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
    """
    Deletes schedule calendars.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    Schedule.objects.filter(id=schedule_id).delete()
    return redirect('admin_schedules')

def admin_bookings(request):
    """
    Lists system-wide customer bookings.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    bookings = Booking.objects.all()
    return render(request, 'admin-bookings.html', {'bookings': bookings, 'login_user': admin})

def admin_booking_detail(request, booking_id):
    """
    Renders details of any system-wide customer booking.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        booking = Booking.objects.get(id=booking_id)
        return render(request, 'admin-booking-detail.html', {'booking': booking, 'login_user': admin})
    except Booking.DoesNotExist:
        return redirect('admin_bookings')

def admin_cancel_booking(request, booking_id):
    """
    Cancels a ticket. Frees booked seats.
    """
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
    """
    Lists bookings that have successfully processed payments.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    bookings = Booking.objects.filter(payment=True)
    return render(request, 'admin-payments.html', {'bookings': bookings, 'login_user': admin})

def admin_profile(request):
    """
    Alters configurations and settings for the active admin.
    """
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
    """
    Generates analytical graphs and operational spreadsheets for system admins.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')

    try:
        total_bookings = Booking.objects.count()
        cancelled_bookings = Booking.objects.filter(status='cancelled').count()
        successful_bookings = Booking.objects.filter(payment=True)
        total_revenue = successful_bookings.aggregate(total=Sum('amount'))['total'] or 0

        daily_bookings = Booking.objects.annotate(date=TruncDate('booking_date')).values('date').annotate(count=Count('id')).order_by('-date')[:7]
        monthly_bookings = Booking.objects.annotate(month=TruncMonth('booking_date')).values('month').annotate(count=Count('id')).order_by('-month')[:6]

        most_booked_routes = Booking.objects.values('bus__source', 'bus__destination').annotate(count=Count('id')).order_by('-count')[:5]

        most_used_buses = Booking.objects.values('bus__bus_name', 'bus__bus_number').annotate(count=Count('id')).order_by('-count')[:5]
        for bus in most_used_buses:
            bus['buses_count'] = Bus.objects.filter(bus_name=bus['bus__bus_name']).count()
            bus['tickets_sold'] = Booking.objects.filter(bus__bus_name=bus['bus__bus_name']).count()
            bus['gross_earnings'] = Booking.objects.filter(bus__bus_name=bus['bus__bus_name'], payment=True).aggregate(total=Sum('amount'))['total'] or 0

        context = {
            'total_bookings': total_bookings,
            'cancelled_bookings': cancelled_bookings,
            'net_earnings': total_revenue,
            'daily_bookings': daily_bookings,
            'monthly_bookings': monthly_bookings,
            'most_booked_routes': most_booked_routes,
            'most_used_buses': most_used_buses,
            'login_user': admin,
        }
        return render(request, 'admin-reports.html', context)
    except Exception as e:
        logger.error(f"Admin Reports Generation Error: {e}")
        return HttpResponse("An error occurred generating reports.")

def admin_settings(request):
    """
    Renders admin settings interface.
    """
    admin = get_admin_user(request)
    if not admin:
        return redirect('login')
    return render(request, 'admin-settings.html', {'login_user': admin})
