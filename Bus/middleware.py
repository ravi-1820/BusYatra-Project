from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import SystemSettings

class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            settings = SystemSettings.get_settings()
            maintenance_active = settings.maintenance_mode
        except Exception:
            maintenance_active = False

        request.maintenance_mode = maintenance_active

        path = request.path_info.lower()

        # Exempt admin, manager, auth, static, and media paths
        is_exempt = (
            path.startswith('/admin') or
            path.startswith('/manager') or
            path.startswith('/login') or
            path.startswith('/logout') or
            path.startswith('/static') or
            path.startswith('/media')
        )

        # Check if user is logged-in manager or admin in session
        user_type = request.session.get('usertype')
        if user_type in ['admin', 'manager']:
            is_exempt = True

        if maintenance_active and not is_exempt:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'BusYatra is currently undergoing scheduled maintenance. Please try again later.'
                }, status=503)

            if request.method == 'POST' and ('payment' in path or 'seat-booking' in path or 'review' in path):
                return render(request, 'maintenance.html', status=503)

        response = self.get_response(request)
        return response
