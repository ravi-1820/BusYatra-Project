from django.test import TestCase, Client
from django.urls import reverse
from datetime import date, timedelta
from Bus.models import User, Bus, Booking, SeatBooking, Schedule, Route

class BusYatraTestCases(TestCase):
    def setUp(self):
        # 1. Create a Manager
        self.manager = User.objects.create(
            name="Manager Yatra",
            email="manager@test.com",
            phone="9876540001",
            password="password123",
            usertype="manager"
        )
        
        # 2. Create a Customer
        self.customer = User.objects.create(
            name="Customer One",
            email="customer@test.com",
            phone="9876540002",
            password="password123",
            usertype="customer"
        )

        # 3. Create Buses
        self.bus_mumbai_goa = Bus.objects.create(
            manager=self.manager,
            bus_name="Mumbai Goa Sleeper",
            bus_number="MH-01-AB-1234",
            bus_type="A/C Sleeper",
            source="Mumbai",
            destination="Goa",
            departure_time="20:00:00",
            arrival_time="08:00:00",
            total_seats=40,
            available_seats=40,
            fare=1200.00,
            image="bus/Ac_sleeper_exterior.png"
        )
        self.bus_delhi_jaipur = Bus.objects.create(
            manager=self.manager,
            bus_name="Delhi Jaipur Seater",
            bus_number="DL-01-CD-5678",
            bus_type="A/C Seater",
            source="Delhi",
            destination="Jaipur",
            departure_time="07:00:00",
            arrival_time="12:00:00",
            total_seats=40,
            available_seats=40,
            fare=500.00,
            image="bus/AC_Seater_exterior.png"
        )

        self.client = Client()

    def test_bus_search_filtering(self):
        """Test search filters out unrelated buses and matches route exactly."""
        # Query matching route
        response = self.client.get(reverse('bus_list') + '?from=Mumbai&to=Goa&date=2026-07-20&passengers=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.bus_mumbai_goa, response.context['buses'])
        self.assertNotIn(self.bus_delhi_jaipur, response.context['buses'])

        # Query no matching route (e.g. Pune -> Surat)
        response = self.client.get(reverse('bus_list') + '?from=Pune&to=Surat&date=2026-07-20&passengers=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['buses'].count(), 0)

        # Query blank search (no source/destination selected)
        response = self.client.get(reverse('bus_list') + '?from=&to=&date=2026-07-20&passengers=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['buses'].count(), 2) # returns both buses

    def test_seat_booking_and_date_wise_availability(self):
        """Test seat booking, and verify date-wise seat blockages work correctly."""
        travel_date_1 = date.today() + timedelta(days=1)
        travel_date_2 = date.today() + timedelta(days=2)

        # Log in the user session
        session = self.client.session
        session['email'] = self.customer.email
        session.save()

        # 1. Create a paid Booking on travel_date_1
        booking = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L1",
            passenger_name="Rahul",
            passenger_age=28,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=travel_date_1,
            status="booked",
            payment=True
        )
        
        # Block seat in database
        SeatBooking.objects.create(
            booking=booking,
            bus=self.bus_mumbai_goa,
            seat_number="L1",
            journey_date=travel_date_1
        )

        # 2. Check availability on travel_date_1: Seat 'L1' should be blocked
        response = self.client.get(reverse('seat_booking', args=[self.bus_mumbai_goa.id]) + f'?date={travel_date_1}')
        self.assertEqual(response.status_code, 200)
        self.assertIn("L1", response.context['booked_seats'])

        # 3. Check availability on travel_date_2: Seat 'L1' should be available
        response = self.client.get(reverse('seat_booking', args=[self.bus_mumbai_goa.id]) + f'?date={travel_date_2}')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("L1", response.context['booked_seats'])

    def test_manager_features_and_schedules_crud(self):
        """Test manager dashboard profile header, schedule CRUD, and scoped bookings."""
        # Log in the manager session
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # 1. Verify manager schedules list page loading
        response = self.client.get(reverse('manager_schedules'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('buses', response.context)
        self.assertIn('schedules', response.context)

        # 2. Add Trip Schedule
        today_date = date.today()
        response = self.client.post(reverse('manager_schedules'), {
            'bus': self.bus_mumbai_goa.id,
            'journey_date': str(today_date),
            'departure_time': '10:00',
            'arrival_time': '22:00',
            'status': 'Available'
        })
        self.assertEqual(response.status_code, 302) # Redirects on POST success
        self.assertTrue(Schedule.objects.filter(bus=self.bus_mumbai_goa, journey_date=today_date).exists())
        schedule = Schedule.objects.get(bus=self.bus_mumbai_goa, journey_date=today_date)

        # 3. Edit Trip Schedule
        response = self.client.post(reverse('edit_schedule', args=[schedule.id]), {
            'bus': self.bus_mumbai_goa.id,
            'journey_date': str(today_date),
            'departure_time': '11:00',
            'arrival_time': '23:00',
            'status': 'Cancelled'
        })
        self.assertEqual(response.status_code, 302)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'Cancelled')

        # 4. Scoped Manager Bookings:
        # Create a booking on self.bus_mumbai_goa (owned by self.manager)
        booking_mine = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L2",
            passenger_name="Me",
            passenger_age=30,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=today_date,
            status="booked",
            payment=True
        )
        
        # Log in as manager
        response = self.client.get(reverse('manager_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(booking_mine, response.context['bookings'])

        # 5. Delete Trip Schedule
        response = self.client.post(reverse('delete_schedule', args=[schedule.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Schedule.objects.filter(id=schedule.id).exists())

    def test_manager_validations_and_profile_crud(self):
        """Test bus/route duplicate validations, profile update, password change, and booking cancellations."""
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # 1. Bus Uniqueness Validation
        response = self.client.post(reverse('add_bus'), {
            'bus_name': 'Another Bus',
            'bus_number': self.bus_mumbai_goa.bus_number, # Duplicate
            'bus_type': 'AC Sleeper (2+1)',
            'source': 'Mumbai',
            'destination': 'Goa',
            'departure_time': '10:00',
            'arrival_time': '22:00',
            'total_seats': 36,
            'available_seats': 36,
            'fare': 1500
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Bus Number should not be allowed.")

        # 2. Route Uniqueness Validation
        route = Route.objects.create(
            manager=self.manager,
            source='Mumbai',
            destination='Goa',
            distance=600,
            duration='12 hours'
        )
        response = self.client.post(reverse('add_route'), {
            'source': 'Mumbai',
            'destination': 'Goa', # Duplicate
            'distance': 600,
            'duration': '12 hours'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Route should not be created.")

        # 3. Profile Info Update
        response = self.client.post(reverse('manager_profile'), {
            'action': 'update_profile',
            'name': 'Updated Manager Name',
            'email': 'newmanager@busyatra.com',
            'phone': '9999999999'
        })
        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.name, 'Updated Manager Name')
        self.assertEqual(self.manager.email, 'newmanager@busyatra.com')
        self.assertEqual(self.manager.phone, '9999999999')

        # 4. Profile Password Change
        # Update session since manager email changed in step 3
        session = self.client.session
        session['email'] = 'newmanager@busyatra.com'
        session.save()
        
        response = self.client.post(reverse('manager_profile'), {
            'action': 'change_password',
            'old_password': 'password123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        self.assertEqual(response.status_code, 200)
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.password, 'newpassword123')

        # 5. Booking Details Page & Cancellation Flow
        booking = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L10",
            passenger_name="Auditor Pax",
            passenger_age=35,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=date.today(),
            status="booked",
            payment=True
        )
        sb = SeatBooking.objects.create(
            booking=booking,
            bus=self.bus_mumbai_goa,
            seat_number="L10",
            journey_date=date.today()
        )

        response = self.client.get(reverse('manager_booking_detail', args=[booking.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auditor Pax")

        # Cancel Booking
        response = self.client.get(reverse('manager_cancel_booking', args=[booking.id]))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        # SeatBooking must be deleted/released
        self.assertFalse(SeatBooking.objects.filter(id=sb.id).exists())

    def test_admin_validations_and_crud(self):
        """Test admin panel actions: CRUD for customer, manager, buses, routes, schedules, cancellations, and profile."""
        # Create an Admin User
        admin_user = User.objects.create(
            name="Admin User",
            email="admin@test.com",
            phone="9876540003",
            password="adminpassword",
            usertype="admin"
        )
        
        session = self.client.session
        session['email'] = admin_user.email
        session.save()
        
        # 1. Access Dashboard
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Overview")
        
        # 2. Add Customer CRUD
        response = self.client.post(reverse('admin_add_customer'), {
            'name': 'New Customer',
            'email': 'newcustomer@test.com',
            'phone': '1234567890',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 302) # Redirect to users list
        self.assertTrue(User.objects.filter(email='newcustomer@test.com', usertype='customer').exists())
        
        # 3. Add Manager CRUD
        response = self.client.post(reverse('admin_add_manager'), {
            'name': 'New Manager',
            'email': 'newmanager@test.com',
            'phone': '1234567891',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 302)
        new_mgr = User.objects.get(email='newmanager@test.com', usertype='manager')
        
        # 4. Bus Uniqueness validation warning
        response = self.client.post(reverse('admin_add_bus'), {
            'manager': new_mgr.id,
            'bus_name': 'Admin Bus',
            'bus_number': self.bus_mumbai_goa.bus_number, # Duplicate
            'bus_type': 'AC Sleeper (2+1)',
            'source': 'Mumbai',
            'destination': 'Goa',
            'departure_time': '10:00',
            'arrival_time': '22:00',
            'total_seats': 36,
            'fare': 1500
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Bus Number should not be allowed.")
        
        # 5. Route Uniqueness Validation
        route = Route.objects.create(
            manager=new_mgr,
            source='Mumbai',
            destination='Pune',
            distance=150,
            duration='3 hours'
        )
        response = self.client.post(reverse('admin_add_route'), {
            'manager': new_mgr.id,
            'source': 'Mumbai',
            'destination': 'Pune', # Duplicate
            'distance': 150,
            'duration': '3 hours'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate Route should not be created.")
        
        # 6. Booking cancellation
        booking = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L12",
            passenger_name="Admin Audit Pax",
            passenger_age=40,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=date.today(),
            status="booked",
            payment=True
        )
        sb = SeatBooking.objects.create(
            booking=booking,
            bus=self.bus_mumbai_goa,
            seat_number="L12",
            journey_date=date.today()
        )
        response = self.client.get(reverse('admin_cancel_booking', args=[booking.id]))
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'cancelled')
        self.assertFalse(SeatBooking.objects.filter(id=sb.id).exists())

    def test_payment_success_flow_and_email(self):
        """Test successful mock Razorpay payment callback: updates booking, blocks seat, sends email, and redirects."""
        from django.core import mail
        
        # Log in customer session
        session = self.client.session
        session['email'] = self.customer.email
        session.save()

        # Create pending booking
        booking = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L15",
            passenger_name="Ravi",
            passenger_age=25,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=date.today() + timedelta(days=5),
            status="booked",
            payment=False
        )

        # Trigger ticket callback view with mock payment info
        url = reverse('ticket') + f'?booking_ids={booking.id}&razorpay_payment_id=mock_payment_100&razorpay_order_id=mock_order_100&razorpay_signature=mock_sig'
        response = self.client.get(url)
        
        # Verify Post/Redirect/Get redirect to clean ticket view
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/ticket/?booking_ids={booking.id}', response['Location'])

        # Verify database update
        booking.refresh_from_db()
        self.assertTrue(booking.payment)
        self.assertEqual(booking.payment_status, "success")
        self.assertEqual(booking.booking_status, "booked")
        self.assertEqual(booking.status, "booked")
        self.assertEqual(booking.payment_id, "mock_payment_100")
        self.assertEqual(booking.razorpay_order_id, "mock_order_100")
        self.assertEqual(booking.razorpay_signature, "mock_sig")

        # Verify SeatBooking reservation is created
        self.assertTrue(SeatBooking.objects.filter(booking=booking, seat_number="L15").exists())

        # Verify email is sent with attachment
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, "BusYatra Ticket Confirmation")
        self.assertIn("Ravi", sent_email.body)
        self.assertEqual(len(sent_email.attachments), 1)
        self.assertEqual(sent_email.attachments[0][0], "BusYatra_Ticket.pdf")
        self.assertEqual(sent_email.attachments[0][2], "application/pdf")

    def test_payment_failure_flow(self):
        """Test failed payment: updates booking status to cancelled, clear payment data, and redirects to my_orders."""
        # Log in customer session
        session = self.client.session
        session['email'] = self.customer.email
        session.save()

        # Create pending booking
        booking = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L16",
            passenger_name="Shyam",
            passenger_age=30,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=date.today() + timedelta(days=5),
            status="booked",
            payment=False
        )

        # Trigger ticket callback view with incorrect/failed signature (real signature library will fail, mock is bypassed if signature doesn't match mock_sig)
        url = reverse('ticket') + f'?booking_ids={booking.id}&razorpay_payment_id=mock_pay_id&razorpay_order_id=mock_order_id&razorpay_signature=invalid_sig_here'
        response = self.client.get(url)
        
        # Verify redirect to My Orders
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('my_orders'), response['Location'])

        # Verify database update to cancelled/failed and no payment IDs stored
        booking.refresh_from_db()
        self.assertFalse(booking.payment)
        self.assertEqual(booking.payment_status, "failed")
        self.assertEqual(booking.booking_status, "cancelled")
        self.assertEqual(booking.status, "cancelled")
        self.assertIsNone(booking.payment_id)
        self.assertIsNone(booking.razorpay_order_id)
        self.assertIsNone(booking.razorpay_signature)

    def test_download_ticket_pdf_endpoint(self):
        """Test that the download_ticket_pdf endpoint serves a PDF file correctly."""
        # Log in customer session
        session = self.client.session
        session['email'] = self.customer.email
        session.save()

        # Create paid booking
        booking = Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L17",
            passenger_name="Gopal",
            passenger_age=40,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=date.today() + timedelta(days=5),
            status="booked",
            payment=True,
            payment_status="success",
            booking_status="booked",
            payment_id="mock_pay_17"
        )

        url = reverse('download_ticket_pdf') + f'?booking_ids={booking.id}'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment; filename="BusYatra_Ticket.pdf"', response['Content-Disposition'])
        self.assertTrue(len(response.content) > 0)

    def test_available_seats_calculation_and_date_wise_isolation(self):
        """Test that Available Seats is calculated dynamically and isolated by date and booking status."""
        test_date_tomorrow = date.today() + timedelta(days=1)
        test_date_after_tomorrow = date.today() + timedelta(days=2)

        # 1. Initially, tomorrow's list should show full availability (40 seats)
        response = self.client.get(reverse('bus_list') + f'?date={test_date_tomorrow}')
        self.assertEqual(response.status_code, 200)
        for bus in response.context['buses']:
            if bus.id == self.bus_mumbai_goa.id:
                self.assertEqual(bus.available_seats, 40)

        # 2. Create one successfully paid booking for tomorrow
        Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L20",
            passenger_name="Pax A",
            passenger_age=25,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=test_date_tomorrow,
            status="booked",
            payment=True,
            payment_status="success",
            booking_status="booked",
            payment_id="mock_p_20"
        )

        # 3. Check tomorrow's list: available seats must be 39
        response = self.client.get(reverse('bus_list') + f'?date={test_date_tomorrow}')
        self.assertEqual(response.status_code, 200)
        buses = {b.id: b for b in response.context['buses']}
        self.assertEqual(buses[self.bus_mumbai_goa.id].available_seats, 39)

        # Also verify bus_detail view dynamically calculates 39 available seats
        response_detail = self.client.get(reverse('bus_detail', args=[self.bus_mumbai_goa.id]) + f'?date={test_date_tomorrow}')
        self.assertEqual(response_detail.status_code, 200)
        self.assertEqual(response_detail.context['bus'].available_seats, 39)

        # 4. Check day after tomorrow's list: available seats must still be 40
        response = self.client.get(reverse('bus_list') + f'?date={test_date_after_tomorrow}')
        self.assertEqual(response.status_code, 200)
        buses = {b.id: b for b in response.context['buses']}
        self.assertEqual(buses[self.bus_mumbai_goa.id].available_seats, 40)

        # 5. Create a cancelled booking for tomorrow
        Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L21",
            passenger_name="Pax Cancelled",
            passenger_age=25,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=test_date_tomorrow,
            status="cancelled",
            payment=True,
            payment_status="success",
            booking_status="cancelled",
            payment_id="mock_p_21"
        )

        # Create a pending payment booking for tomorrow
        Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L22",
            passenger_name="Pax Pending",
            passenger_age=25,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=test_date_tomorrow,
            status="booked",
            payment=False,
            payment_status="pending",
            booking_status="booked"
        )

        # Create a failed payment booking for tomorrow
        Booking.objects.create(
            user=self.customer,
            bus=self.bus_mumbai_goa,
            seat_number="L23",
            passenger_name="Pax Failed",
            passenger_age=25,
            passenger_gender="Male",
            amount=self.bus_mumbai_goa.fare,
            travel_date=test_date_tomorrow,
            status="cancelled",
            payment=False,
            payment_status="failed",
            booking_status="cancelled"
        )

        # 6. Verify tomorrow's available seats is STILL 39 (none of the failed, pending or cancelled bookings counted)
        response = self.client.get(reverse('bus_list') + f'?date={test_date_tomorrow}')
        self.assertEqual(response.status_code, 200)
        buses = {b.id: b for b in response.context['buses']}
        self.assertEqual(buses[self.bus_mumbai_goa.id].available_seats, 39)
        
    def test_forgot_password_flow(self):
        """Test the full forgot password, OTP verification, and reset password flow."""
        # 1. Forgot password request with non-existent email
        response = self.client.post(reverse('forgot_password'), {'email': 'nonexistent@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['msg'], "Email doesn't exist..!")

        # 2. Forgot password request with valid email
        response = self.client.post(reverse('forgot_password'), {'email': self.customer.email})
        # Should redirect to verify OTP
        self.assertRedirects(response, reverse('verify_forgot_otp'))

        # Verify session holds the email and OTP
        session = self.client.session
        self.assertEqual(session.get('forgot_email'), self.customer.email)
        otp = session.get('forgot_otp')
        self.assertTrue(otp.isdigit())

        # 3. OTP verification with invalid OTP
        response = self.client.post(reverse('verify_forgot_otp'), {'otp': '000000'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['msg'], "Invalid OTP. Please enter the correct OTP.")

        # 4. OTP verification with valid OTP
        response = self.client.post(reverse('verify_forgot_otp'), {'otp': otp})
        # Should redirect to reset password
        self.assertRedirects(response, reverse('reset_password'))
        self.assertTrue(self.client.session.get('otp_verified'))

        # 5. Reset password validations (mismatch)
        response = self.client.post(reverse('reset_password'), {
            'password': 'newpassword123',
            'confirm_password': 'mismatchpassword'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['msg'], "Password and Confirm Password do not match.")

        # 6. Reset password success
        response = self.client.post(reverse('reset_password'), {
            'password': 'newpassword123',
            'confirm_password': 'newpassword123'
        })
        # Renders login template directly with success message
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['success'], "Password reset successful! Please login with your new password.")

        # Verify database model has updated password
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.password, 'newpassword123')


class BusPaginationTests(TestCase):
    def setUp(self):
        # Create a Manager
        self.manager = User.objects.create(
            name="Manager Yatra",
            email="manager@test.com",
            phone="9876540001",
            password="password123",
            usertype="manager"
        )
        # Create 7 buses
        self.buses = []
        for i in range(1, 8):
            bus = Bus.objects.create(
                manager=self.manager,
                bus_name=f"Bus {i}",
                bus_number=f"MH-01-AB-100{i}",
                bus_type="A/C Sleeper",
                source="Mumbai",
                destination="Goa",
                departure_time="20:00:00",
                arrival_time="08:00:00",
                total_seats=40,
                available_seats=40,
                fare=1000.00 + i * 10,
            )
            self.buses.append(bus)
        self.client = Client()

    def test_pagination_page_one(self):
        """Verify page 1 contains exactly 5 buses and pagination info is correct."""
        response = self.client.get(reverse('bus_list') + '?page=1&from=Mumbai&to=Goa&date=2026-07-20&passengers=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['buses']), 5)
        # Previous button is disabled, next is active
        self.assertFalse(response.context['buses'].has_previous())
        self.assertTrue(response.context['buses'].has_next())
        self.assertEqual(response.context['buses'].number, 1)
        self.assertEqual(response.context['buses'].paginator.num_pages, 2)

    def test_pagination_page_two(self):
        """Verify page 2 contains remaining 2 buses."""
        response = self.client.get(reverse('bus_list') + '?page=2&from=Mumbai&to=Goa&date=2026-07-20&passengers=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['buses']), 2)
        # Previous button is active, next is disabled
        self.assertTrue(response.context['buses'].has_previous())
        self.assertFalse(response.context['buses'].has_next())
        self.assertEqual(response.context['buses'].number, 2)

    def test_pagination_invalid_page_falls_back(self):
        """Verify invalid page parameters correctly fallback to nearest valid pages."""
        # Non-integer page
        response = self.client.get(reverse('bus_list') + '?page=abc')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['buses'].number, 1)

        # Negative page
        response = self.client.get(reverse('bus_list') + '?page=-5')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['buses'].number, 1)

        # Page index too high (out of bounds)
        response = self.client.get(reverse('bus_list') + '?page=999')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['buses'].number, 2) # nearest valid page is the last page (2)

    def test_pagination_query_parameters_preserved(self):
        """Verify filtering/search parameters are preserved in pagination HTML links."""
        response = self.client.get(reverse('bus_list') + '?page=1&from=Mumbai&to=Goa&date=2026-07-20&passengers=2')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        
        # Check that page 2 link contains the query parameters
        self.assertIn('page=2', content)
        self.assertIn('from=Mumbai', content)
        self.assertIn('to=Goa', content)
        self.assertIn('date=2026-07-20', content)
        self.assertIn('passengers=2', content)







