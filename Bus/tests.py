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


from datetime import date, timedelta
from .models import Review, Booking

class ReviewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.manager = User.objects.create(
            name="Bus Manager",
            email="manager_rev@busyatra.com",
            phone="9998887771",
            password="password123",
            usertype="manager"
        )
        self.user1 = User.objects.create(
            name="Alice Customer",
            email="alice@example.com",
            phone="9998887772",
            password="password123",
            usertype="customer"
        )
        self.user2 = User.objects.create(
            name="Bob Customer",
            email="bob@example.com",
            phone="9998887773",
            password="password123",
            usertype="customer"
        )
        self.bus = Bus.objects.create(
            manager=self.manager,
            bus_name="Royal Volvo Express",
            bus_number="GJ01AB9999",
            bus_type="AC Sleeper",
            source="Ahmedabad",
            destination="Mumbai",
            departure_time="20:00:00",
            arrival_time="06:00:00",
            total_seats=30,
            available_seats=30,
            fare=800
        )
        yesterday = date.today() - timedelta(days=1)
        tomorrow = date.today() + timedelta(days=1)

        self.past_booking = Booking.objects.create(
            user=self.user1,
            bus=self.bus,
            seat_number="A1",
            passenger_name="Alice",
            passenger_age=25,
            passenger_gender="Female",
            amount=800,
            travel_date=yesterday,
            status="booked",
            payment=True,
            payment_status="success"
        )

        self.future_booking = Booking.objects.create(
            user=self.user1,
            bus=self.bus,
            seat_number="A2",
            passenger_name="Alice",
            passenger_age=25,
            passenger_gender="Female",
            amount=800,
            travel_date=tomorrow,
            status="booked",
            payment=True,
            payment_status="success"
        )

        self.unpaid_booking = Booking.objects.create(
            user=self.user1,
            bus=self.bus,
            seat_number="A3",
            passenger_name="Alice",
            passenger_age=25,
            passenger_gender="Female",
            amount=800,
            travel_date=yesterday,
            status="booked",
            payment=False,
            payment_status="pending"
        )

        self.cancelled_booking = Booking.objects.create(
            user=self.user1,
            bus=self.bus,
            seat_number="A4",
            passenger_name="Alice",
            passenger_age=25,
            passenger_gender="Female",
            amount=800,
            travel_date=yesterday,
            status="cancelled",
            payment=True,
            payment_status="success"
        )

    def login(self, user):
        session = self.client.session
        session['email'] = user.email
        session['name'] = user.name
        session['usertype'] = user.usertype
        session.save()

    def test_01_eligible_user_can_create_review(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '5',
            'comment': 'Awesome journey and super clean bus!'
        })
        self.assertEqual(Review.objects.count(), 1)
        rev = Review.objects.first()
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.user, self.user1)
        self.assertEqual(rev.bus, self.bus)

    def test_02_rating_1_accepted(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '1',
            'comment': 'Not satisfied with cleanliness.'
        })
        self.assertEqual(Review.objects.count(), 1)
        self.assertEqual(Review.objects.first().rating, 1)

    def test_03_rating_5_accepted(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '5',
            'comment': 'Excellent service!'
        })
        self.assertEqual(Review.objects.count(), 1)
        self.assertEqual(Review.objects.first().rating, 5)

    def test_04_rating_0_rejected(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '0',
            'comment': 'Bad service.'
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_05_rating_6_rejected(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '6',
            'comment': 'Over the top.'
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_06_empty_comment_rejected(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '5',
            'comment': '   '
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_07_future_booking_cannot_be_reviewed(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.future_booking.id]), {
            'rating': '5',
            'comment': 'Looking forward to it.'
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_08_cancelled_booking_cannot_be_reviewed(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.cancelled_booking.id]), {
            'rating': '3',
            'comment': 'Trip was cancelled.'
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_09_unpaid_booking_cannot_be_reviewed(self):
        self.login(self.user1)
        response = self.client.post(reverse('add_review', args=[self.unpaid_booking.id]), {
            'rating': '4',
            'comment': 'Never paid.'
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_10_user_cannot_review_another_users_booking(self):
        self.login(self.user2)
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '5',
            'comment': 'Fraudulent review attempt.'
        })
        self.assertEqual(Review.objects.count(), 0)

    def test_11_duplicate_review_prevented(self):
        self.login(self.user1)
        Review.objects.create(
            user=self.user1,
            bus=self.bus,
            booking=self.past_booking,
            rating=5,
            comment="First review"
        )
        response = self.client.post(reverse('add_review', args=[self.past_booking.id]), {
            'rating': '4',
            'comment': 'Second review attempt.'
        })
        self.assertEqual(Review.objects.count(), 1)

    def test_12_user_can_edit_own_review(self):
        self.login(self.user1)
        rev = Review.objects.create(
            user=self.user1,
            bus=self.bus,
            booking=self.past_booking,
            rating=3,
            comment="Initial ok review"
        )
        response = self.client.post(reverse('edit_review', args=[rev.id]), {
            'rating': '5',
            'comment': 'Updated to excellent service!'
        })
        rev.refresh_from_db()
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.comment, 'Updated to excellent service!')

    def test_13_user_cannot_edit_another_users_review(self):
        rev = Review.objects.create(
            user=self.user1,
            bus=self.bus,
            booking=self.past_booking,
            rating=5,
            comment="Alice original review"
        )
        self.login(self.user2)
        response = self.client.post(reverse('edit_review', args=[rev.id]), {
            'rating': '1',
            'comment': 'Tampered comment'
        })
        rev.refresh_from_db()
        self.assertEqual(rev.rating, 5)
        self.assertEqual(rev.comment, "Alice original review")

    def test_14_user_can_delete_own_review(self):
        self.login(self.user1)
        rev = Review.objects.create(
            user=self.user1,
            bus=self.bus,
            booking=self.past_booking,
            rating=4,
            comment="Review to delete"
        )
        response = self.client.post(reverse('delete_review', args=[rev.id]))
        self.assertEqual(Review.objects.count(), 0)

    def test_15_user_cannot_delete_another_users_review(self):
        rev = Review.objects.create(
            user=self.user1,
            bus=self.bus,
            booking=self.past_booking,
            rating=4,
            comment="Alice review"
        )
        self.login(self.user2)
        response = self.client.post(reverse('delete_review', args=[rev.id]))
        self.assertEqual(Review.objects.count(), 1)

    def test_16_average_rating_calculated_correctly(self):
        past2 = Booking.objects.create(
            user=self.user2,
            bus=self.bus,
            seat_number="B1",
            passenger_name="Bob",
            passenger_age=30,
            passenger_gender="Male",
            amount=800,
            travel_date=date.today() - timedelta(days=2),
            status="booked",
            payment=True,
            payment_status="success"
        )
        Review.objects.create(user=self.user1, bus=self.bus, booking=self.past_booking, rating=5, comment="5 stars")
        Review.objects.create(user=self.user2, bus=self.bus, booking=past2, rating=3, comment="3 stars")

        response = self.client.get(reverse('bus_detail', args=[self.bus.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['avg_rating'], 4.0)
        self.assertEqual(response.context['total_reviews'], 2)

    def test_17_review_appears_on_bus_detail_page(self):
        Review.objects.create(user=self.user1, bus=self.bus, booking=self.past_booking, rating=5, comment="Wonderful experience!")
        response = self.client.get(reverse('bus_detail', args=[self.bus.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wonderful experience!")
        self.assertContains(response, "Alice Customer")


class ReviewManagementTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create(
            name="System Admin",
            email="admin_rev@busyatra.com",
            phone="9990001111",
            password="adminpassword",
            usertype="admin"
        )
        self.manager1 = User.objects.create(
            name="Manager One",
            email="mgr1@busyatra.com",
            phone="9990001112",
            password="mgrpassword",
            usertype="manager"
        )
        self.manager2 = User.objects.create(
            name="Manager Two",
            email="mgr2@busyatra.com",
            phone="9990001113",
            password="mgrpassword",
            usertype="manager"
        )
        self.customer = User.objects.create(
            name="Customer One",
            email="cust1@busyatra.com",
            phone="9990001114",
            password="custpassword",
            usertype="customer"
        )

        self.bus1 = Bus.objects.create(
            manager=self.manager1,
            bus_name="Manager 1 Volvo",
            bus_number="GJ01AA1111",
            bus_type="AC Sleeper",
            source="Ahmedabad",
            destination="Mumbai",
            departure_time="20:00:00",
            arrival_time="06:00:00",
            total_seats=30,
            available_seats=30,
            fare=800
        )
        self.bus2 = Bus.objects.create(
            manager=self.manager2,
            bus_name="Manager 2 Express",
            bus_number="GJ01BB2222",
            bus_type="Non-AC Seater",
            source="Surat",
            destination="Pune",
            departure_time="21:00:00",
            arrival_time="07:00:00",
            total_seats=40,
            available_seats=40,
            fare=500
        )

        yesterday = date.today() - timedelta(days=1)
        self.booking1 = Booking.objects.create(
            user=self.customer,
            bus=self.bus1,
            seat_number="A1",
            passenger_name="Customer One",
            passenger_age=25,
            passenger_gender="Male",
            amount=800,
            travel_date=yesterday,
            status="booked",
            payment=True,
            payment_status="success"
        )
        self.booking2 = Booking.objects.create(
            user=self.customer,
            bus=self.bus2,
            seat_number="B1",
            passenger_name="Customer One",
            passenger_age=25,
            passenger_gender="Male",
            amount=500,
            travel_date=yesterday,
            status="booked",
            payment=True,
            payment_status="success"
        )

        self.review1 = Review.objects.create(
            user=self.customer,
            bus=self.bus1,
            booking=self.booking1,
            rating=5,
            comment="Great ride on Manager 1 bus!",
            is_featured=False
        )
        self.review2 = Review.objects.create(
            user=self.customer,
            bus=self.bus2,
            booking=self.booking2,
            rating=4,
            comment="Good ride on Manager 2 bus!",
            is_featured=False
        )

    def login(self, user):
        session = self.client.session
        session['email'] = user.email
        session['name'] = user.name
        session['usertype'] = user.usertype
        session.save()

    def test_01_manager_can_view_own_bus_reviews(self):
        self.login(self.manager1)
        response = self.client.get(reverse('manager_reviews'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Great ride on Manager 1 bus!")
        self.assertNotContains(response, "Good ride on Manager 2 bus!")

    def test_02_manager_cannot_view_another_managers_reviews(self):
        self.login(self.manager2)
        response = self.client.get(reverse('manager_reviews'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Good ride on Manager 2 bus!")
        self.assertNotContains(response, "Great ride on Manager 1 bus!")

    def test_03_manager_can_feature_own_bus_review(self):
        self.login(self.manager1)
        response = self.client.get(reverse('toggle_feature_review', args=[self.review1.id]))
        self.review1.refresh_from_db()
        self.assertTrue(self.review1.is_featured)

    def test_04_manager_cannot_feature_another_managers_review(self):
        self.login(self.manager1)
        response = self.client.get(reverse('toggle_feature_review', args=[self.review2.id]))
        self.assertEqual(response.status_code, 403)
        self.review2.refresh_from_db()
        self.assertFalse(self.review2.is_featured)

    def test_05_manager_can_unfeature_own_bus_review(self):
        self.review1.is_featured = True
        self.review1.save()
        self.login(self.manager1)
        response = self.client.get(reverse('toggle_feature_review', args=[self.review1.id]))
        self.review1.refresh_from_db()
        self.assertFalse(self.review1.is_featured)

    def test_06_admin_can_view_all_reviews(self):
        self.login(self.admin)
        response = self.client.get(reverse('admin_reviews'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Great ride on Manager 1 bus!")
        self.assertContains(response, "Good ride on Manager 2 bus!")

    def test_07_admin_can_feature_any_review(self):
        self.login(self.admin)
        response = self.client.get(reverse('toggle_feature_review', args=[self.review1.id]))
        self.review1.refresh_from_db()
        self.assertTrue(self.review1.is_featured)
        response2 = self.client.get(reverse('toggle_feature_review', args=[self.review2.id]))
        self.review2.refresh_from_db()
        self.assertTrue(self.review2.is_featured)

    def test_08_customer_cannot_feature_review(self):
        self.login(self.customer)
        response = self.client.get(reverse('toggle_feature_review', args=[self.review1.id]))
        self.assertEqual(response.status_code, 403)
        self.review1.refresh_from_db()
        self.assertFalse(self.review1.is_featured)

    def test_09_featured_review_appears_on_homepage(self):
        self.review1.is_featured = True
        self.review1.save()
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Great ride on Manager 1 bus!")

    def test_10_non_featured_review_does_not_appear_on_homepage(self):
        self.review1.is_featured = False
        self.review1.save()
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Great ride on Manager 1 bus!")

    def test_11_multiple_featured_reviews_appear_correctly(self):
        self.review1.is_featured = True
        self.review1.save()
        self.review2.is_featured = True
        self.review2.save()
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Great ride on Manager 1 bus!")
        self.assertContains(response, "Good ride on Manager 2 bus!")

    def test_12_no_featured_reviews_does_not_produce_errors(self):
        Review.objects.all().update(is_featured=False)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)




