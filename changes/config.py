import logging
import flask
import os
import os.path

from celery.signals import task_postrun
from datetime import timedelta
from flask.ext.restful import Api
from flask.ext.sqlalchemy import SQLAlchemy
from flask_mail import Mail
from kombu import Queue
from raven.contrib.flask import Sentry
from urlparse import urlparse
from werkzeug.contrib.fixers import ProxyFix

from changes.constants import PROJECT_ROOT
from changes.ext.celery import Celery
from changes.ext.pubsub import PubSub
from changes.ext.redis import Redis
from changes.utils.trace import TracerMiddleware


db = SQLAlchemy(session_options={
    'autoflush': True,
})
api = Api(prefix='/api/0')
mail = Mail()
pubsub = PubSub()
queue = Celery()
redis = Redis()
sentry = Sentry(logging=True, level=logging.WARN)


def create_app(_read_config=True, **config):
    app = flask.Flask(__name__,
                      static_folder=None,
                      template_folder=os.path.join(PROJECT_ROOT, 'templates'))

    app.wsgi_app = ProxyFix(app.wsgi_app)
    app.wsgi_app = TracerMiddleware(app.wsgi_app, app)

    # This key is insecure and you should override it on the server
    app.config['SECRET_KEY'] = 't\xad\xe7\xff%\xd2.\xfe\x03\x02=\xec\xaf\\2+\xb8=\xf7\x8a\x9aLD\xb1'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql:///changes'
    app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
    app.config['REDIS_URL'] = 'redis://localhost/0'
    app.config['DEBUG'] = True
    app.config['HTTP_PORT'] = 5000
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    app.config['API_TRACEBACKS'] = True

    app.config['CELERY_ACKS_LATE'] = True
    app.config['CELERY_BROKER_URL'] = 'redis://localhost/0'
    app.config['CELERY_ACCEPT_CONTENT'] = ['json', 'pickle']
    app.config['CELERY_RESULT_SERIALIZER'] = 'json'
    app.config['CELERY_TASK_SERIALIZER'] = 'json'
    app.config['CELERYD_PREFETCH_MULTIPLIER'] = 1
    app.config['CELERY_DEFAULT_QUEUE'] = "default"
    app.config['CELERY_DEFAULT_EXCHANGE'] = "default"
    app.config['CELERY_DEFAULT_EXCHANGE_TYPE'] = "direct"
    app.config['CELERY_DEFAULT_ROUTING_KEY'] = "default"
    app.config['CELERY_QUEUES'] = (
        Queue('job.sync', routing_key='job.sync'),
        Queue('job.create', routing_key='job.create'),
        Queue('celery', routing_key='celery'),
        Queue('default', routing_key='default'),
        Queue('repo.sync', routing_key='repo.sync'),
    )
    app.config['CELERY_ROUTES'] = {
        'create_job': {
            'queue': 'job.create',
            'routing_key': 'job.create',
        },
        'sync_job': {
            'queue': 'job.sync',
            'routing_key': 'job.sync',
        },
        'sync_repo': {
            'queue': 'repo.sync',
            'routing_key': 'repo.sync',
        },
    }

    app.config['EVENT_LISTENERS'] = (
        ('changes.listeners.mail.job_finished_handler', 'job.finished'),
    )

    # celerybeat must be running for our cleanup tasks to execute
    # e.g. celery worker -B
    app.config['CELERYBEAT_SCHEDULE'] = {
        'cleanup-jobs': {
            'task': 'cleanup_jobs',
            'schedule': timedelta(minutes=1),
        },
        # 'check-repos': {
        #     'task': 'check_repos',
        #     'schedule': timedelta(minutes=5),
        # },
    }
    app.config['CELERY_TIMEZONE'] = 'UTC'

    app.config['SENTRY_DSN'] = None

    app.config['JENKINS_URL'] = None
    app.config['JENKINS_TOKEN'] = None

    app.config['KOALITY_URL'] = None
    app.config['KOALITY_API_KEY'] = None

    app.config['GOOGLE_CLIENT_ID'] = None
    app.config['GOOGLE_CLIENT_SECRET'] = None
    app.config['GOOGLE_DOMAIN'] = None

    app.config['REPO_ROOT'] = None

    app.config['MAIL_DEFAULT_SENDER'] = 'changes@localhost'
    app.config['BASE_URI'] = None

    app.config.update(config)

    if _read_config:
        if os.environ.get('CHANGES_CONF'):
            # CHANGES_CONF=/etc/changes.conf.py
            app.config.from_envvar('CHANGES_CONF')
        else:
            # Look for ~/.changes/changes.conf.py
            path = os.path.normpath(os.path.expanduser('~/.changes/changes.conf.py'))
            app.config.from_pyfile(path, silent=True)

    if not app.config['BASE_URI']:
        raise ValueError('You must set ``BASE_URI`` in your configuration.')

    parsed_url = urlparse(app.config['BASE_URI'])
    app.config.setdefault('SERVER_NAME', parsed_url.netloc)
    app.config.setdefault('PREFERRED_URL_SCHEME', parsed_url.scheme)

    # init sentry first
    sentry.init_app(app)

    api.init_app(app)
    db.init_app(app)
    mail.init_app(app)
    pubsub.init_app(app)
    queue.init_app(app)
    redis.init_app(app)

    from raven.contrib.celery import register_signal, register_logger_signal
    register_signal(sentry.client)
    register_logger_signal(sentry.client)

    # configure debug routes first
    if app.debug:
        configure_debug_routes(app)

    configure_templates(app)

    # TODO: these can be moved to wsgi app entrypoints
    configure_api_routes(app)
    configure_web_routes(app)

    configure_event_listeners(app)
    configure_jobs(app)

    return app


def configure_templates(app):
    from changes.utils.times import duration

    app.jinja_env.filters['duration'] = duration


def configure_api_routes(app):
    from changes.api.auth_index import AuthIndexAPIView
    from changes.api.author_build_index import AuthorBuildIndexAPIView
    from changes.api.build_details import BuildDetailsAPIView
    from changes.api.build_index import BuildIndexAPIView
    from changes.api.build_retry import BuildRetryAPIView
    from changes.api.build_test_index import BuildTestIndexAPIView
    from changes.api.change_details import ChangeDetailsAPIView
    from changes.api.change_index import ChangeIndexAPIView
    from changes.api.job_details import JobDetailsAPIView
    from changes.api.job_log_details import JobLogDetailsAPIView
    from changes.api.jobphase_index import JobPhaseIndexAPIView
    from changes.api.node_details import NodeDetailsAPIView
    from changes.api.node_job_index import NodeJobIndexAPIView
    from changes.api.patch_details import PatchDetailsAPIView
    from changes.api.project_build_index import ProjectBuildIndexAPIView
    from changes.api.project_commit_details import ProjectCommitDetailsAPIView
    from changes.api.project_commit_index import ProjectCommitIndexAPIView
    from changes.api.project_index import ProjectIndexAPIView
    from changes.api.project_stats_index import ProjectStatsIndexAPIView
    from changes.api.project_test_details import ProjectTestDetailsAPIView
    from changes.api.project_test_index import ProjectTestIndexAPIView
    from changes.api.project_details import ProjectDetailsAPIView
    from changes.api.testgroup_details import TestGroupDetailsAPIView

    api.add_resource(AuthIndexAPIView, '/auth/')
    api.add_resource(BuildIndexAPIView, '/builds/')
    api.add_resource(AuthorBuildIndexAPIView, '/authors/<author_id>/builds/')
    api.add_resource(BuildDetailsAPIView, '/builds/<build_id>/')
    api.add_resource(BuildRetryAPIView, '/builds/<build_id>/retry/')
    api.add_resource(BuildTestIndexAPIView, '/builds/<build_id>/tests/')
    api.add_resource(JobDetailsAPIView, '/jobs/<job_id>/')
    api.add_resource(JobLogDetailsAPIView, '/jobs/<job_id>/logs/<source_id>/')
    api.add_resource(JobPhaseIndexAPIView, '/jobs/<job_id>/phases/')
    api.add_resource(ChangeIndexAPIView, '/changes/')
    api.add_resource(ChangeDetailsAPIView, '/changes/<change_id>/')
    api.add_resource(NodeDetailsAPIView, '/nodes/<node_id>/')
    api.add_resource(NodeJobIndexAPIView, '/nodes/<node_id>/jobs/')
    api.add_resource(PatchDetailsAPIView, '/patches/<patch_id>/')
    api.add_resource(ProjectIndexAPIView, '/projects/')
    api.add_resource(ProjectDetailsAPIView, '/projects/<project_id>/')
    api.add_resource(ProjectBuildIndexAPIView, '/projects/<project_id>/builds/')
    api.add_resource(ProjectCommitIndexAPIView, '/projects/<project_id>/commits/')
    api.add_resource(ProjectCommitDetailsAPIView, '/projects/<project_id>/commits/<commit_id>/')
    api.add_resource(ProjectStatsIndexAPIView, '/projects/<project_id>/stats/')
    api.add_resource(ProjectTestIndexAPIView, '/projects/<project_id>/tests/')
    api.add_resource(ProjectTestDetailsAPIView, '/projects/<project_id>/tests/<test_id>/')
    api.add_resource(TestGroupDetailsAPIView, '/testgroups/<testgroup_id>/')


def configure_web_routes(app):
    from changes.web.auth import AuthorizedView, LoginView, LogoutView
    from changes.web.index import IndexView
    from changes.web.static import StaticView

    app.add_url_rule(
        '/static/<path:filename>',
        view_func=StaticView.as_view('static', root=os.path.join(PROJECT_ROOT, 'static')))
    app.add_url_rule(
        '/partials/<path:filename>',
        view_func=StaticView.as_view('partials', root=os.path.join(PROJECT_ROOT, 'partials')))

    app.add_url_rule(
        '/auth/login/', view_func=LoginView.as_view('login', authorized_url='authorized'))
    app.add_url_rule(
        '/auth/logout/', view_func=LogoutView.as_view('logout', complete_url='index'))
    app.add_url_rule(
        '/auth/complete/', view_func=AuthorizedView.as_view('authorized', authorized_url='authorized', complete_url='index'))

    app.add_url_rule(
        '/<path:path>', view_func=IndexView.as_view('index-path'))
    app.add_url_rule(
        '/', view_func=IndexView.as_view('index'))


def configure_debug_routes(app):
    from changes.debug.reports.build import BuildReportMailView

    app.add_url_rule(
        '/debug/mail/report/build/', view_func=BuildReportMailView.as_view('debug-build-report'))


def configure_jobs(app):
    from changes.jobs.check_repos import check_repos
    from changes.jobs.cleanup_jobs import cleanup_jobs
    from changes.jobs.create_job import create_job
    from changes.jobs.notify_listeners import notify_listeners
    from changes.jobs.sync_artifact import sync_artifact
    from changes.jobs.sync_job import sync_job
    from changes.jobs.sync_repo import sync_repo
    from changes.jobs.update_build_result import update_build_result
    from changes.jobs.update_project_stats import (
        update_project_stats, update_project_plan_stats)

    queue.register('check_repos', check_repos)
    queue.register('cleanup_jobs', cleanup_jobs)
    queue.register('create_job', create_job)
    queue.register('notify_listeners', notify_listeners)
    queue.register('sync_artifact', sync_artifact)
    queue.register('sync_job', sync_job)
    queue.register('sync_repo', sync_repo)
    queue.register('update_build_result', update_build_result)
    queue.register('update_project_stats', update_project_stats)
    queue.register('update_project_plan_stats', update_project_plan_stats)

    @task_postrun.connect
    def cleanup_session(*args, **kwargs):
        """
        Emulate a request cycle for each task to ensure the session objects
        get cleaned up as expected.
        """
        db.session.commit()
        db.session.remove()


def configure_event_listeners(app):
    from changes.signals import register_listener
    from changes.utils.imports import import_string

    for func_path, signal_name in app.config['EVENT_LISTENERS']:
        func = import_string(func_path)
        register_listener(func, signal_name)
