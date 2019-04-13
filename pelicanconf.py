#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

AUTHOR = u'Andy Gocke'
SITENAME = u'comment out'
SITEURL = u'localhost:8000'

TIMEZONE = 'America/Los_Angeles'

DEFAULT_LANG = u'en'
DEFAULT_DATE_FORMAT = ('%Y. %b. %d')

THEME = 'themes/commentout'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

STATIC_PATHS = [ 'extras/CNAME', 'extras/favicon.ico', 'images' ]
EXTRA_PATH_METADATA = { 
    'extras/CNAME': { 'path': 'CNAME' },
    'extras/favicon.ico': {'path': 'favicon.ico'}
}

# Blogroll
LINKS = (('Pelican', 'http://getpelican.com/'),
         ('Python.org', 'http://python.org/'),
         ('Jinja2', 'http://jinja.pocoo.org/'),
         ('You can modify those links in your config file', '#'),)

# Social widget
SOCIAL = (('You can add links in your config file', '#'),
          ('Another social link', '#'),)

DEFAULT_PAGINATION = False

MD_EXTENSIONS = ['codehilite(css_class=highlight)', 'extra']

# Uncomment following line if you want document-relative URLs when developing
#RELATIVE_URLS = True
