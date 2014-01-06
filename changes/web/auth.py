from flask import current_app, redirect, request, session, url_for
from flask.views import MethodView
from oauth2client.client import OAuth2WebServerFlow


def get_auth_flow(redirect_uri=None):
    # XXX(dcramer): we have to generate this each request because oauth2client
    # doesn't want you to set redirect_uri as part of the request, which causes
    # a lot of runtime issues.
    return OAuth2WebServerFlow(
        client_id=current_app.config['GOOGLE_CLIENT_ID'],
        client_secret=current_app.config['GOOGLE_CLIENT_SECRET'],
        scope='https://www.googleapis.com/auth/userinfo.email',
        redirect_uri=redirect_uri,
    )


class LoginView(MethodView):
    def __init__(self, authorized_url):
        self.authorized_url = authorized_url
        super(LoginView, self).__init__()

    def get(self):
        redirect_uri = url_for(self.authorized_url, _external=True)
        flow = get_auth_flow(redirect_uri=redirect_uri)
        auth_uri = flow.step1_get_authorize_url()
        return redirect(auth_uri)


class AuthorizedView(MethodView):
    def __init__(self, complete_url, authorized_url):
        self.complete_url = complete_url
        self.authorized_url = authorized_url
        super(AuthorizedView, self).__init__()

    def get(self):
        redirect_uri = url_for(self.authorized_url, _external=True)
        flow = get_auth_flow(redirect_uri=redirect_uri)
        resp = flow.step2_exchange(request.args['code'])

        if current_app.config['GOOGLE_DOMAIN']:
            # TODO(dcramer): confirm this is actually what this value means
            if resp.id_token.get('hd') != current_app.config['GOOGLE_DOMAIN']:
                # TODO(dcramer): this should show some kind of error
                return redirect(self.complete_url)

        session['access_token'] = resp.access_token
        session['email'] = resp.id_token['email']

        return redirect(self.complete_url)


class LogoutView(MethodView):
    def __init__(self, complete_url):
        self.complete_url = complete_url
        super(LogoutView, self).__init__()

    def get(self):
        session.pop('access_token', None)
        session.pop('email', None)
        return redirect(self.complete_url)
