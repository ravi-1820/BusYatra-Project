from .models import User

def login_user(request):
    email = request.session.get('email')
    if email:
        try:
            user = User.objects.get(email=email)
            return {'login_user': user}
        except User.DoesNotExist:
            pass
    return {'login_user': None}
