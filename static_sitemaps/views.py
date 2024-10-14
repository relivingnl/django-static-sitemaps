import os

from django.http import HttpResponse, Http404
from django.views.generic import View

from static_sitemaps import conf
from static_sitemaps.util import _lazy_load


class SitemapView(View):
    def get(self, request, *args, **kwargs):
        section = kwargs.get('section')

        try:
            storage = _lazy_load(conf.STORAGE_CLASS)(location=conf.ROOT_DIR)
        except TypeError:
            storage = _lazy_load(conf.STORAGE_CLASS)()

        path = os.path.join(conf.ROOT_DIR, '{}.xml'.format(section))

        f = storage.open(path)
        content = f.readlines()
        f.close()
        return HttpResponse(content, content_type='application/xml')
