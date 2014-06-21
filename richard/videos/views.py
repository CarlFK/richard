# richard -- video index system
# Copyright (C) 2012, 2013 richard contributors.  See AUTHORS.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import bleach
import json

from django.db.models import Count
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.paginator import EmptyPage, Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template import RequestContext
from haystack.query import SearchQuerySet


from richard.videos import models
from richard.videos import forms

def split_year(title):
    """Returns (title base, year)

    Some categories have a year at the end. This detects that
    and returns a split.

    Example:
    >>> split_year('Foo')
    ('Foo', None)
    >>> split_year('PyCon 2013')
    ('PyCon', 2013)

    """
    try:
        title = title.strip()
        return title[:-4].strip(), int(title[-4:])
    except (IndexError, ValueError):
        return title, None


def category_list(request):
    categories = models.Category.objects.order_by('title')

    # category title -> list of categories
    cats = {}
    for cat in categories:
        title, year = split_year(cat.title)
        cat._year = year
        cats.setdefault(title, []).append(cat)

    ret = render(
        request, 'videos/category_list.html',
        {'cats_by_group': cats})
    return ret


def category(request, category_id, slug):
    obj = get_object_or_404(models.Category, pk=category_id)

    videos = (obj.video_set.live().select_related('category')
                                  .prefetch_related('speakers'))

    ret = render(
        request, 'videos/category.html',
        {'view': 'videos',
         'category': obj,
         'videos': videos})
    return ret


def category_files(request, category_id, slug):
    obj = get_object_or_404(models.Category, pk=category_id)

    videos = obj.video_set.live().prefetch_related('speakers')

    ret = render(
        request, 'videos/category.html',
        {'view': 'files',
         'category': obj,
         'videos': videos})
    return ret


def speaker_list(request):
    # TODO: Should cache this--no need to look it up every time.
    qs = models.Speaker.objects.values_list('name', flat=True)
    chars = list(set(sname[0].lower() for sname in qs))
    chars.sort()

    c = request.GET.get('character', 'a')

    # make sure that there are speakers in the DB
    if chars:
        if len(c) != 1 or c not in chars:
            c = chars[0]

    speakers = (models.Speaker.objects.filter(name__istartswith=c)
                                      .annotate(video_count=Count('video')))

    ret = render(
        request, 'videos/speaker_list.html',
        {'chars': chars,
         'active_char': c,
         'speakers': speakers})
    return ret


def speaker(request, speaker_id, slug=None):
    obj = get_object_or_404(models.Speaker, pk=speaker_id)

    videos = (obj.video_set.live().select_related('category')
                                  .prefetch_related('speakers'))

    ret = render(
        request, 'videos/speaker.html',
        {'speaker': obj,
         'videos': videos})
    return ret

def video(request, video_id, slug):
    obj = get_object_or_404(models.Video, pk=video_id)

    meta = [
        ('keywords', ",".join([t.tag for t in obj.tags.all()]))
        ]
    if obj.summary:
        meta.append(('description',
                     bleach.clean(obj.summary, tags=[], strip=True)))

    # Figure out how we're going to embed the video.
    # This is used by JavaScript code to seek to a specific video position.

    if obj.source_url and 'youtube' in obj.source_url:
        # Universal Subtitles is hardcoded for YouTube videos
        embed_type = 'unisubs'
    elif obj.embed:
        embed_type = 'custom'
    else:
        embed_type = 'html5'

    embed = obj.embed
    available_formats = obj.get_available_formats(html5tag=True)

    # For Firefox, we nix any non-free formats.
    if request.BROWSER.name == 'Firefox':
        available_formats = [
            af for af in available_formats
            if af['mime_type'].endswith(('ogg', 'ogv', 'webm'))]

    # crazy unauthorized edit
    if "editkey" in request.GET:
        edit_key = request.GET['editkey']
        template='videos/video_edit.html'
        if request.method == 'POST':
            video_form = forms.Video_Form(request.POST, instance=obj)
            if video_form.is_valid():
                video_form.save()
            else:
                print video_form.errors
        else:
            video_form = forms.Video_Form(instance=obj)
    else:
        template='videos/video.html'
        video_form = None

    ret = render(
        request,
        template,
        {'meta': meta,
         'v': obj,
         'v_form':video_form,
         'embed': embed,
         'embed_type': embed_type,
         'available_formats': available_formats},
        context_instance=RequestContext(request))

    return ret


def search(request):
    q = request.GET.get('q', '')
    if q:
        qs = (SearchQuerySet().filter_or(content=q)
                              .filter_or(speakers__startswith=q.lower()))

        page = Paginator(qs, 25)
        p = request.GET.get('p', '1')
        try:
            p = max(1, int(p))
        except ValueError:
            p = 1

        try:
            page = page.page(p)
        except EmptyPage:
            page = page.page(1)

    else:
        page = None

    return render(request,
                  'videos/search.html',
                  {'query': q,
                   'page': page})


def opensearch(request):
    """Return opensearch description document."""
    ret = render(
        request, 'videos/opensearch.xml',
        {'site': Site.objects.get_current()},
        content_type='application/opensearchdescription+xml')
    return ret


def opensearch_suggestions(request):
    """Return suggestions for a search query.

    Implements the OpenSearch suggestions extension.
    """
    if not settings.OPENSEARCH_ENABLE_SUGGESTIONS:
        raise Http404

    query = request.GET.get('q', '')
    sqs = (SearchQuerySet().filter(title_auto=query)
                           .values_list('title_auto', flat=True))
    result = [query, list(sqs)]

    return JSONResponse(json.dumps(result))


# TODO: Move this elsewhere

class JSONResponse(HttpResponse):
    def __init__(self, content):
        super(JSONResponse, self).__init__(
            content, mimetype='application/json')


def apiurlforsource(request):
    host_url = request.GET.get('host_url')
    if not host_url:
        raise Http404

    obj = get_object_or_404(models.Video, source_url=host_url)
    return JSONResponse('{"source_url": "http://pyvideo.org%s"}' %
                        obj.get_absolute_url())
