from __future__ import print_function

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

import gzip
import hashlib
import os
import subprocess
from six import BytesIO

from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.paginator import EmptyPage, PageNotAnInteger

try:
    from django.urls import reverse, NoReverseMatch
except ImportError:  # Django < 2.0
    from django.core.urlresolvers import reverse, NoReverseMatch

from django.template import loader
from django.utils import translation
from django.utils.encoding import smart_str

from static_sitemaps import conf
from static_sitemaps.util import _lazy_load

__author__ = 'xaralis'


class SitemapGenerator(object):
    def __init__(self, verbosity):
        self.verbosity = verbosity
        try:
            self.storage = _lazy_load(conf.STORAGE_CLASS)(location=conf.ROOT_DIR)
        except TypeError:
            self.storage = _lazy_load(conf.STORAGE_CLASS)()

        self.sitemaps = conf.ROOT_SITEMAP

        if not isinstance(self.sitemaps, dict):
            self.sitemaps = dict(enumerate(self.sitemaps))

    @staticmethod
    def get_hash(bytestream):
        return hashlib.md5(bytestream).digest()

    @staticmethod
    def normalize_url(url):
        if url[-1] != '/':
            url += '/'
        if not url.startswith(('http://', 'https://')):
            protocol = conf.FORCE_PROTOCOL or 'http'
            prefix = '%s://' % protocol
            if url.startswith('/'):
                from django.contrib.sites.models import Site
                url = prefix + Site.objects.get_current().domain + url
            else:
                url = prefix + url
        return url

    def _write(self, path, output):
        output = bytes(output, "utf8")  # botoS3 has some issues with encoding in Python 3
        self.storage.save(path, ContentFile(output))

    def read_hash(self, path):
        with self.storage.open(path) as f:
            result = self.get_hash(f.read())
        return result

    def out(self, string, min_level=1):
        if self.verbosity >= min_level:
            print(string)

    def write(self):
        for filename, sitemap in self.sitemaps.items():
            self.out(f'Generating sitemaps for filename ({filename}).', 1)
            translation.activate(conf.LANGUAGE)
            self.write_index(filename, sitemap)
            translation.deactivate()
        self.out('Finished generating sitemaps.', 1)

    def write_index(self, index_filename, sitemap):
        baseurl = self.normalize_url(conf.get_url(index_filename))
        parts = []

        # Collect all pages and write them.
        for section, site in _lazy_load(sitemap).items():
            if callable(site):
                pages = site().paginator.num_pages
            else:
                pages = site.paginator.num_pages

            for page in range(1, pages + 1):
                filename = conf.FILENAME_TEMPLATE % {'section': section,
                                                     'page': page}
                lastmod = self.write_page(site, page, filename)

                if conf.USE_GZIP:
                    filename += '.gz'

                parts.append({
                    'location': '%s%s' % (baseurl, filename),
                    'lastmod': lastmod
                })

        path = os.path.join(conf.ROOT_DIR, index_filename)
        self.out('Writing index file.', 2)

        if self.storage.exists(path):
            self.storage.delete(path)

        output = loader.render_to_string(conf.INDEX_TEMPLATE, {'sitemaps': parts})
        self._write(path, output)

    def write_page(self, site, page, filename):
        self.out('Writing sitemap %s.' % filename, 2)
        old_page_md5 = None
        urls = []

        if conf.MOCK_SITE:
            if conf.MOCK_SITE_NAME is None:
                raise ImproperlyConfigured("STATICSITEMAPS_MOCK_SITE_NAME must not be None. Try setting to www.yoursite.com")
            from django.contrib.sites.requests import RequestSite
            from django.test.client import RequestFactory
            rs = RequestSite(RequestFactory().get('/', SERVER_NAME=conf.MOCK_SITE_NAME))
        try:
            if callable(site):
                if conf.MOCK_SITE:
                    urls.extend(site().get_urls(page, rs, protocol=conf.MOCK_SITE_PROTOCOL))
                else:
                    urls.extend(site().get_urls(page, protocol=conf.FORCE_PROTOCOL))
            else:
                if conf.MOCK_SITE:
                    urls.extend(site.get_urls(page, rs, protocol=conf.MOCK_SITE_PROTOCOL))
                else:
                    urls.extend(site.get_urls(page, protocol=conf.FORCE_PROTOCOL))
        except EmptyPage:
            self.out("Page %s empty" % page)
        except PageNotAnInteger:
            self.out("No page '%s'" % page)

        lastmods = [lastmod for lastmod in [u.get('lastmod') for u in urls] if lastmod is not None]
        file_lastmod = max(lastmods) if len(lastmods) > 0 else None
        path = os.path.join(conf.ROOT_DIR, filename)
        template = getattr(site, 'sitemap_template', 'sitemap.xml')

        if self.storage.exists(path):
            old_page_md5 = self.read_hash(path)
            self.storage.delete(path)

        output = smart_str(loader.render_to_string(template, {'urlset': urls}))
        self._write(path, output)

        if conf.USE_GZIP:
            if conf.GZIP_METHOD not in ['python', 'system', ]:
                raise ImproperlyConfigured("STATICSITEMAPS_GZIP_METHOD must be in ['python', 'system']")

            if conf.GZIP_METHOD == 'system' and not os.path.exists(conf.SYSTEM_GZIP_PATH):
                raise ImproperlyConfigured('STATICSITEMAPS_SYSTEM_GZIP_PATH does not exist')

            if conf.GZIP_METHOD == 'system' and not isinstance(self.storage, FileSystemStorage):
                raise ImproperlyConfigured('system gzip method can only be used with FileSystemStorage')

            if conf.GZIP_METHOD == 'system':
                # GZIP with system gzip binary
                subprocess.call([conf.SYSTEM_GZIP_PATH, '-f', path, ])
            else:
                # GZIP with python gzip lib
                try:
                    gzipped_path = '%s.gz' % path
                    if self.storage.exists(gzipped_path):
                        self.storage.delete(gzipped_path)

                    self.out('Compressing...', 2)
                    buf = BytesIO()
                    with gzip.GzipFile(fileobj=buf, mode="w") as f:
                        f.write(output.encode('utf-8'))
                    self.storage.save(gzipped_path, ContentFile(buf.getvalue()))
                except OSError:
                    self.out("Compress %s file error" % path)

        return file_lastmod
