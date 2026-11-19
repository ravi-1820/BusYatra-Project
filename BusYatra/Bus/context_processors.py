from .models import User, SystemSettings

def login_user(request):
    email = request.session.get('email')
    if email:
        try:
            user = User.objects.get(email=email)
            return {'login_user': user}
        except User.DoesNotExist:
            pass
    return {'login_user': None}

def bus_settings(request):
    try:
        settings = SystemSettings.get_settings()
    except Exception:
        settings = None
    return {
        'sys_settings': settings
    }
