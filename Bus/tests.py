from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
import os
from .models import User, Contact, Bus

class BusYatraViewsTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Create a manager user
        self.manager = User.objects.create(
            name="Test Manager",
            email="manager_test@busyatra.com",
            phone="1234567890",
            password="password123",
            usertype="manager"
        )
        # Create an admin user
        self.admin = User.objects.create(
            name="Test Admin",
            email="admin_test@busyatra.com",
            phone="1112223333",
            password="password123",
            usertype="admin"
        )
        # Create a customer user
        self.customer = User.objects.create(
            name="Test Customer",
            email="customer_test@busyatra.com",
            phone="0987654321",
            password="password123",
            usertype="customer"
        )
        # Create a sample contact message
        self.contact = Contact.objects.create(
            name="Sender Name",
            email="sender@example.com",
            phone="1122334455",
            subject="Help with booking",
            message="I am facing an issue with booking seats."
        )

    def test_manager_seats_view_authenticated(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call manager-seats url
        response = self.client.get(reverse('manager_seats'))
        self.assertEqual(response.status_code, 200)
        # Check that the template loaded successfully
        self.assertTemplateUsed(response, 'manager-seats.html')

    def test_contact_messages_view_authenticated_manager(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call contact_message url
        response = self.client.get(reverse('contact_message'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'contact_messages.html')
        self.assertContains(response, "Help with booking")

    def test_contact_messages_view_unauthenticated_redirects(self):
        # Not logged in
        response = self.client.get(reverse('contact_message'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

    def test_contact_messages_view_customer_denied(self):
        # Logged in as customer
        session = self.client.session
        session['email'] = self.customer.email
        session.save()

        response = self.client.get(reverse('contact_message'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('index'))

    def test_manager_reports_view_authenticated(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call manager-reports url (redirects to manager_dashboard)
        response = self.client.get(reverse('manager_reports'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('manager_dashboard'))

    def test_export_pdf_view_authenticated_and_valid(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call export_pdf url with valid dates
        response = self.client.get(reverse('export_pdf'), {'start_date': '2026-07-01', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_export_pdf_admin_authenticated(self):
        # Set session for admin
        session = self.client.session
        session['email'] = self.admin.email
        session.save()

        # Call export_pdf url with valid dates for admin
        response = self.client.get(reverse('export_pdf'), {'start_date': '2026-07-01', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_export_csv_view_authenticated_and_valid(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call export_csv url with valid dates
        response = self.client.get(reverse('export_csv'), {'start_date': '2026-07-01', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertTrue(response['Content-Disposition'].startswith('attachment; filename="manager_report_'))

    def test_export_views_invalid_dates(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Test empty start date
        response = self.client.get(reverse('export_pdf'), {'start_date': '', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Validation Error", status_code=400)

        # Test start date after end date
        response = self.client.get(reverse('export_csv'), {'start_date': '2026-07-28', 'end_date': '2026-07-01'})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Validation Error", status_code=400)

    def test_manager_dashboard_view_authenticated_with_analytics_context(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call manager_dashboard url
        response = self.client.get(reverse('manager_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'manager-dashboard.html')

        # Verify both dashboard and analytics report context variables exist
        self.assertIn('fleet_count', response.context)
        self.assertIn('net_revenue', response.context)
        self.assertIn('total_revenue', response.context)
        self.assertIn('total_tickets', response.context)
        self.assertIn('total_buses', response.context)
        self.assertIn('avg_occupancy', response.context)
        self.assertIn('weekly_revenue', response.context)
        self.assertIn('route_data', response.context)

    def test_manager_dashboard_view_date_filtering(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call manager_dashboard url with GET date filter parameters
        response = self.client.get(reverse('manager_dashboard'), {'start_date': '2026-07-01', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['start_date'], '2026-07-01')
        self.assertEqual(response.context['end_date'], '2026-07-28')

    def test_export_views_unauthenticated_redirects(self):
        # Unauthenticated request to pdf export
        response = self.client.get(reverse('export_pdf'), {'start_date': '2026-07-01', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

        # Unauthenticated request to csv export
        response = self.client.get(reverse('export_csv'), {'start_date': '2026-07-01', 'end_date': '2026-07-28'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('login'))

    def test_manager_buses_pagination(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call manager_buses url
        response = self.client.get(reverse('manager_buses'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)
        self.assertIn('buses', response.context)

    def test_contact_messages_pagination(self):
        # Set session for manager
        session = self.client.session
        session['email'] = self.manager.email
        session.save()

        # Call contact_message url
        response = self.client.get(reverse('contact_message'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('page_obj', response.context)
        self.assertIn('contacts', response.context)

    def test_my_orders_pagination(self):
        # Set session for customer
        session = self.client.session
        session['email'] = self.customer.email
        session.save()

        # Call my_orders url
        response = self.client.get(reverse('my_orders'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'my-orders.html')
        self.assertIn('upcoming_page_obj', response.context)
        self.assertIn('past_page_obj', response.context)
        self.assertIn('cancelled_page_obj', response.context)
        self.assertEqual(response.context['upcoming_page_obj'].paginator.per_page, 3)

    def test_bus_search_scenarios(self):
        # Create test buses
        bus1 = Bus.objects.create(
            manager=self.manager,
            bus_name="Express Bus 1",
            bus_number="GJ01AB1234",
            bus_type="AC Sleeper",
            source="Ahmedabad",
            destination="Jaipur",
            departure_time="08:00:00",
            arrival_time="16:00:00",
            total_seats=30,
            available_seats=30,
            fare=500
        )
        bus2 = Bus.objects.create(
            manager=self.manager,
            bus_name="Express Bus 2",
            bus_number="DL01XY9876",
            bus_type="Non-AC Seater",
            source="Delhi",
            destination="Mumbai",
            departure_time="10:00:00",
            arrival_time="22:00:00",
            total_seats=40,
            available_seats=40,
            fare=600
        )

        # Scenario 1 - Normal Search with Source & Destination
        resp1 = self.client.get(reverse('bus_list'), {'from': 'Ahmedabad', 'to': 'Jaipur'})
        self.assertEqual(resp1.status_code, 200)
        buses1 = resp1.context['buses'].object_list
        self.assertEqual(len(buses1), 1)
        self.assertEqual(buses1[0].id, bus1.id)

        # Scenario 2 - Search Without Filters & Placeholders
        resp2 = self.client.get(reverse('bus_list'), {'from': 'Select Source', 'to': 'Select Destination'})
        self.assertEqual(resp2.status_code, 200)
        buses2 = resp2.context['buses'].object_list
        self.assertEqual(len(buses2), 2)

        # Scenario 3 - Direct navigation ("Book Now") without parameters
        resp3 = self.client.get(reverse('bus_list'))
        self.assertEqual(resp3.status_code, 200)
        buses3 = resp3.context['buses'].object_list
        self.assertEqual(len(buses3), 2)

        # Scenario 4 - After returning from search, search without filters
        # 1. Search with filters first
        self.client.get(reverse('bus_list'), {'from': 'Ahmedabad', 'to': 'Jaipur'})
        # 2. Search again without filters
        resp4 = self.client.get(reverse('bus_list'), {'from': '', 'to': ''})
        self.assertEqual(resp4.status_code, 200)
        buses4 = resp4.context['buses'].object_list
        self.assertEqual(len(buses4), 2)
        # Ensure session does not store journey_from or journey_to
        self.assertNotIn('journey_from', self.client.session)
        self.assertNotIn('journey_to', self.client.session)

    def test_forgot_password_get(self):
        response = self.client.get(reverse('forgot_password'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'forgot_password.html')

    @patch('Bus.views.send_mail')
    def test_forgot_password_nonexistent_email(self, mock_send_mail):
        response = self.client.post(reverse('forgot_password'), {'email': 'nonexistent_test_email@example.com'})
        self.assertFalse(mock_send_mail.called)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'forgot_password.html')
        self.assertContains(response, "Email doesn&#x27;t exist..!")

    @patch('Bus.views.send_mail')
    def test_forgot_password_otp_success(self, mock_send_mail):
        mock_send_mail.return_value = 1
        response = self.client.post(reverse('forgot_password'), {'email': self.customer.email})
        self.assertTrue(mock_send_mail.called)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verify_forgot_otp'))
        self.assertEqual(self.client.session.get('forgot_email'), self.customer.email)
        self.assertIsNotNone(self.client.session.get('forgot_otp'))

    @patch('Bus.views.send_mail')
    def test_forgot_password_otp_email_failure(self, mock_send_mail):
        mock_send_mail.side_effect = Exception("SMTP Auth Error details")
        response = self.client.post(reverse('forgot_password'), {'email': self.customer.email})
        self.assertTrue(mock_send_mail.called)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'forgot_password.html')
        self.assertContains(response, "Failed to send OTP email. Please try again or contact support.")
        self.assertNotContains(response, "SMTP Auth Error details")
        self.assertNotIn('forgot_otp', self.client.session)
        self.assertNotIn('forgot_email', self.client.session)

    def test_email_settings_from_environment(self):
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'EMAIL_HOST'))
        self.assertTrue(hasattr(settings, 'EMAIL_PORT'))
        self.assertTrue(hasattr(settings, 'EMAIL_USE_TLS'))
        self.assertTrue(hasattr(settings, 'EMAIL_HOST_USER'))
        self.assertTrue(hasattr(settings, 'EMAIL_HOST_PASSWORD'))
        self.assertTrue(hasattr(settings, 'EMAIL_TIMEOUT'))
        self.assertIsInstance(settings.EMAIL_TIMEOUT, int)
        self.assertGreater(settings.EMAIL_TIMEOUT, 0)

    def test_app_password_whitespace_normalization(self):
        raw_password_with_spaces = "potl abet ampb gjag"
        normalized = raw_password_with_spaces.replace(" ", "")
        self.assertEqual(normalized, "potlabetampbgjag")


from datetime import date, timedelta
from .models import Booking, SeatBooking

class PaymentToTicketFlowTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create(
            name="User A",
            email="user_a@busyatra.com",
            phone="9998887771",
            password="password123",
            usertype="customer"
        )
        self.user_b = User.objects.create(
            name="User B",
            email="user_b@busyatra.com",
            phone="9998887772",
            password="password123",
            usertype="customer"
        )
        self.bus = Bus.objects.create(
            manager=self.user_a,
            bus_name="Express Bus",
            bus_number="EX123",
            bus_type="AC",
            source="Mumbai",
            destination="Pune",
            departure_time="10:00:00",
            arrival_time="14:00:00",
            fare=500,
            total_seats=40,
            available_seats=40
        )
        self.travel_date = (date.today() + timedelta(days=2)).strftime("%Y-%m-%d")
        
        # Create valid booking for user A
        self.booking_a1 = Booking.objects.create(
            user=self.user_a,
            bus=self.bus,
            seat_number="A1",
            passenger_name="Passenger A1",
            passenger_age=25,
            passenger_gender="Male",
            amount=500,
            travel_date=self.travel_date,
            status="booked",
            payment=False
        )
        self.booking_a2 = Booking.objects.create(
            user=self.user_a,
            bus=self.bus,
            seat_number="A2",
            passenger_name="Passenger A2",
            passenger_age=24,
            passenger_gender="Female",
            amount=500,
            travel_date=self.travel_date,
            status="booked",
            payment=False
        )
        # Create booking for user B
        self.booking_b1 = Booking.objects.create(
            user=self.user_b,
            bus=self.bus,
            seat_number="B1",
            passenger_name="Passenger B1",
            passenger_age=30,
            passenger_gender="Male",
            amount=500,
            travel_date=self.travel_date,
            status="booked",
            payment=False
        )

    def login_user(self, user):
        session = self.client.session
        session['email'] = user.email
        session['name'] = user.name
        session['user_id'] = user.id
        session.save()

    def test_1_valid_booking_ticket_loads(self):
        self.login_user(self.user_a)
        # Mark booking paid and load ticket
        self.booking_a1.payment = True
        self.booking_a1.payment_status = "success"
        self.booking_a1.save()

        response = self.client.get(reverse('ticket'), {'booking_ids': str(self.booking_a1.id)})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ticket.html')
        self.assertContains(response, "Passenger A1")
        self.assertContains(response, "A1")

    def test_2_multiple_bookings_preserved(self):
        self.login_user(self.user_a)
        booking_ids_str = f"{self.booking_a1.id},{self.booking_a2.id}"
        response = self.client.get(reverse('ticket'), {'booking_ids': booking_ids_str})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passenger A1")
        self.assertContains(response, "Passenger A2")

    def test_3_empty_booking_ids_no_500(self):
        self.login_user(self.user_a)
        response = self.client.get(reverse('ticket'), {'booking_ids': ''})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('my_orders'))

    def test_4_missing_booking_ids_no_500(self):
        self.login_user(self.user_a)
        response = self.client.get(reverse('ticket'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('my_orders'))

    def test_5_invalid_booking_id_no_500(self):
        self.login_user(self.user_a)
        response = self.client.get(reverse('ticket'), {'booking_ids': '999999'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('my_orders'))

    def test_6_unauthorized_booking_access_denied(self):
        # User A tries to access User B's booking
        self.login_user(self.user_a)
        response = self.client.get(reverse('ticket'), {'booking_ids': str(self.booking_b1.id)})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('my_orders'))

    @patch('Bus.views.generate_ticket_pdf_bytes')
    def test_7_payment_success_callback_redirects_properly(self, mock_pdf):
        mock_pdf.return_value = b"%PDF-1.4 Mock PDF Content"
        self.login_user(self.user_a)
        booking_ids_str = f"{self.booking_a1.id},{self.booking_a2.id}"
        
        response = self.client.get(reverse('ticket'), {
            'booking_ids': booking_ids_str,
            'razorpay_payment_id': 'mock_pay_12345',
            'razorpay_order_id': 'mock_order_67890',
            'razorpay_signature': 'mock_sig'
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, f"/ticket/?booking_ids={booking_ids_str}")

        # Check DB update
        b1 = Booking.objects.get(id=self.booking_a1.id)
        b2 = Booking.objects.get(id=self.booking_a2.id)
        self.assertTrue(b1.payment)
        self.assertEqual(b1.payment_status, "success")
        self.assertEqual(b1.payment_id, "mock_pay_12345")
        self.assertTrue(b2.payment)
        self.assertEqual(b2.payment_status, "success")





