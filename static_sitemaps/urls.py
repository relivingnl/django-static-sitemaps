from django.conf import settings
from static_sitemaps.views import SitemapView

try:
    from django.urls import path, re_path

    try:
        sitemaps = settings.STATICSITEMAPS_ROOT_SITEMAP.keys()
    except AttributeError:
        sitemaps = ['sitemap.xml']

    urlpatterns = [
        re_path(r'^(?P<section>sitemap-.+)\.xml$', SitemapView.as_view()),
    ]

    for sitemap in sitemaps:
        urlpatterns += path(sitemap, SitemapView.as_view(), kwargs={'section': 'sitemap'},
                            name=f'static_sitemaps_index_{sitemap}'),

except ImportError: # Django < 2.0
    from django.conf.urls import url

    urlpatterns = [
        url(r'^sitemap\.xml$', SitemapView.as_view(), kwargs={'section': 'sitemap'}, name='static_sitemaps_index'),
        url(r'^(?P<section>sitemap-.+)\.xml$', SitemapView.as_view()),
    ]
