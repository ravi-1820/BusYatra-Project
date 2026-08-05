from django.test import TestCase, Client
from django.urls import reverse
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


