import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BusYatra.settings')
django.setup()

from Bus.models import User, Bus

def seed_data():
    print("Seeding database...")
    
    # 1. Create a manager
    manager, created = User.objects.get_or_create(
        email="manager@busyatra.com",
        defaults={
            "name": "Yatra Operator",
            "phone": "9876543210",
            "password": "password123",
            "usertype": "manager"
        }
    )
    if created:
        print(f"Created Manager: {manager.email}")
    else:
        print(f"Manager already exists: {manager.email}")

    # 2. Sample Buses List
    buses_list = [
        {
            "bus_name": "Yatra Sleeper Express",
            "bus_number": "MH-09-AX-9999",
            "bus_type": "A/C Sleeper",
            "source": "Mumbai",
            "destination": "Goa",
            "departure_time": "19:30:00",
            "arrival_time": "07:30:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 1500.00,
            "image": "bus/Ac_sleeper_exterior.png"
        },
        {
            "bus_name": "Yatra sleeper Express Return",
            "bus_number": "GA-01-BY-8888",
            "bus_type": "A/C Sleeper",
            "source": "Goa",
            "destination": "Mumbai",
            "departure_time": "18:30:00",
            "arrival_time": "06:30:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 1500.00,
            "image": "bus/Ac_sleeper_exterior.png"
        },
        {
            "bus_name": "Pune Intercity Seater",
            "bus_number": "MH-12-PZ-1234",
            "bus_type": "A/C Seater",
            "source": "Mumbai",
            "destination": "Pune",
            "departure_time": "15:30:00",
            "arrival_time": "19:30:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 800.00,
            "image": "bus/AC_Seater_exterior.png"
        },
        {
            "bus_name": "Pune Intercity Return",
            "bus_number": "MH-12-PZ-4321",
            "bus_type": "A/C Seater",
            "source": "Pune",
            "destination": "Mumbai",
            "departure_time": "08:30:00",
            "arrival_time": "12:30:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 800.00,
            "image": "bus/AC_Seater_exterior.png"
        },
        {
            "bus_name": "Pink City Cruiser",
            "bus_number": "DL-01-JP-5555",
            "bus_type": "A/C Seater",
            "source": "Delhi",
            "destination": "Jaipur",
            "departure_time": "06:00:00",
            "arrival_time": "11:00:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 600.00,
            "image": "bus/AC_Seater_exterior.png"
        },
        {
            "bus_name": "Pink City Return",
            "bus_number": "RJ-14-DL-6666",
            "bus_type": "A/C Seater",
            "source": "Jaipur",
            "destination": "Delhi",
            "departure_time": "16:00:00",
            "arrival_time": "21:00:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 600.00,
            "image": "bus/AC_Seater_exterior.png"
        },
        {
            "bus_name": "Southern Glide Sleeper",
            "bus_number": "KA-03-CH-4444",
            "bus_type": "A/C Sleeper",
            "source": "Bangalore",
            "destination": "Chennai",
            "departure_time": "22:00:00",
            "arrival_time": "06:00:00",
            "total_seats": 40,
            "available_seats": 40,
            "fare": 1200.00,
            "image": "bus/Ac_sleeper_exterior.png"
        }
    ]

    for bus_data in buses_list:
        bus, created = Bus.objects.get_or_create(
            bus_number=bus_data["bus_number"],
            defaults={
                "manager": manager,
                "bus_name": bus_data["bus_name"],
                "bus_type": bus_data["bus_type"],
                "source": bus_data["source"],
                "destination": bus_data["destination"],
                "departure_time": bus_data["departure_time"],
                "arrival_time": bus_data["arrival_time"],
                "total_seats": bus_data["total_seats"],
                "available_seats": bus_data["available_seats"],
                "fare": bus_data["fare"],
                "image": bus_data["image"]
            }
        )
        if created:
            print(f"Created Bus: {bus.bus_name} ({bus.source} -> {bus.destination})")
        else:
            print(f"Bus already exists: {bus.bus_name} ({bus.source} -> {bus.destination})")

    print("Data seeding completed successfully!")

if __name__ == "__main__":
    seed_data()
