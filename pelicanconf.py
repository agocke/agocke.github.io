#!/usr/bin/env python
# -*- coding: utf-8 -*- #
from __future__ import unicode_literals

AUTHOR = u'Andy Gocke'
SITENAME = u'comment out'
SITEURL = 'http://commentout.com'

TIMEZONE = 'America/Los_Angeles'

DEFAULT_LANG = u'en'

THEME = 'themes/commentout'

# Feed generation is usually not desired when developing
FEED_ALL_ATOM = None
CATEGORY_FEED_ATOM = None
TRANSLATION_FEED_ATOM = None
AUTHOR_FEED_ATOM = None
AUTHOR_FEED_RSS = None

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