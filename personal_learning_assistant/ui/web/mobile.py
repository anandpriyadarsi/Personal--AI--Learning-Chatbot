"""Private PWA presentation boundary; no academic storage or domain calculation."""
from ipaddress import ip_address
from urllib.parse import urlsplit
from flask import Blueprint, abort, current_app, jsonify, render_template, request

mobile = Blueprint('mobile', __name__)


def cloud_ai_allowed():
    """Private mode requires both explicit permission and a data acknowledgement."""
    return (not current_app.config.get('PRIVATE_MOBILE_MODE') or (
        current_app.config.get('MOBILE_ALLOW_CLOUD_AI') is True and
        current_app.config.get('MOBILE_AI_DATA_ACK') == 'questions-sources-history-leave-device'))


@mobile.get('/manifest.webmanifest')
def manifest():
    response = jsonify(id='/', name='ANVAYA · Personal Learning Intelligence',
        short_name='ANVAYA', description='Your private learning companion. Academic work requires your Python host.',
        start_url='/', scope='/', display='standalone', background_color='#0b0f14',
        theme_color='#0b0f14', lang='en', prefer_related_applications=False,
        icons=[{'src': f'/static/brand/anvaya-mobile-{size}.png', 'sizes': f'{size}x{size}',
                'type': 'image/png', 'purpose': 'any maskable'} for size in (192, 512)])
    response.mimetype = 'application/manifest+json'
    return response


@mobile.get('/mobile-sw.js')
def worker():
    response = current_app.send_static_file('js/mobile-sw.js')
    response.mimetype = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-store'
    return response


@mobile.get('/mobile/offline')
def offline():
    return render_template('mobile_offline.html')


@mobile.get('/mobile/settings')
def settings():
    return render_template('mobile_settings.html', active_page='mobile-settings',
                           cloud_enabled=cloud_ai_allowed())


def register_mobile(app):
    app.register_blueprint(mobile)
    if app.config.get('PRIVATE_MOBILE_MODE'):
        # DNS rebinding protection. No proxy-header trust or remote serving is implied.
        app.config['TRUSTED_HOSTS'] = ['localhost', '127.0.0.1', '[::1]']

    @app.before_request
    def private_request_boundary():
        if not app.config.get('PRIVATE_MOBILE_MODE'):
            return None
        try:
            local = ip_address(request.remote_addr or '').is_loopback
        except ValueError:
            local = False
        if not local:
            abort(403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            if request.headers.get('Sec-Fetch-Site') == 'cross-site':
                abort(403)
            if origin:
                source, target = urlsplit(origin), urlsplit(request.host_url)
                if (source.scheme, source.netloc) != (target.scheme, target.netloc):
                    abort(403)
        return None

    @app.after_request
    def private_response_boundary(response):
        if app.config.get('PRIVATE_MOBILE_MODE'):
            # The Android localhost app serves only APK-bundled static files here.
            # Other private-PWA contexts and all student data remain no-store.
            if (app.config.get('ANDROID_LOCAL_RUNTIME') is True
                    and request.endpoint == 'static'
                    and request.method in ('GET', 'HEAD')
                    and response.status_code in (200, 304)):
                response.headers['Cache-Control'] = 'private, max-age=300'
            else:
                response.headers['Cache-Control'] = 'no-store'
            # Retain same-origin form Origin headers; suppress external referrers.
            response.headers['Referrer-Policy'] = 'same-origin'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; worker-src 'self'; "
                "manifest-src 'self'; frame-src 'self'; frame-ancestors 'none'; object-src 'none'; "
                "base-uri 'none'; form-action 'self'")
        if request.endpoint in ('mobile.manifest', 'mobile.worker', 'mobile.offline'):
            response.headers['Cache-Control'] = 'no-store'
        return response
