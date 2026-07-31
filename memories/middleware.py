from .models import set_current_user, Profile


class CurrentUserMiddleware:
    """将当前请求用户存入线程局部变量，供 signal 使用"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                set_current_user(request.user.profile)
            except Profile.DoesNotExist:
                set_current_user(None)
        else:
            set_current_user(None)
        response = self.get_response(request)
        return response
