#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

import sys
import traceback
import re

from django.shortcuts import render_to_response
from django.template import RequestContext, loader
from django.http import (HttpResponse, HttpResponseNotFound,
                         HttpResponseServerError, Http404)
import json
from django.conf import settings
from django.contrib import auth
from django.contrib.auth.models import User

from django.core.mail import send_mail

from mathics.core.definitions import Definitions
from mathics.core.evaluation import Evaluation, Message, Result, Output

from mathics.web.models import Query, Worksheet
from mathics.web.forms import LoginForm, SaveForm, SaveNewForm, DeleteForm
from mathics.doc import documentation
from mathics.doc.doc import DocPart, DocChapter, DocSection
import six
from six.moves import range
from string import Template

if settings.DEBUG:
    JSON_CONTENT_TYPE = 'text/html'
else:
    JSON_CONTENT_TYPE = 'application/json'


def get_content_type(request):
    return ('text/html' if 'MSIE' in request.META.get('HTTP_USER_AGENT', '')
            else 'application/xhtml+xml')


class JsonResponse(HttpResponse):
    def __init__(self, result={}):
        response = json.dumps(result)
        super(JsonResponse, self).__init__(response, content_type=JSON_CONTENT_TYPE)


class WebOutput(Output):
    pass


def require_ajax_login(func):
    def new_func(request, *args, **kwargs):
        if not request.user.is_authenticated():
            return JsonResponse({'requireLogin': True})
        return func(request, *args, **kwargs)
    return new_func

definitions = Definitions(add_builtin=True)


def require_ajax_login(f):
    return f


def main_view(request, name):
    if settings.REQUIRE_LOGIN and not request.user.is_authenticated():
        raise Http404
    user = request.user

    try:
        if user.is_authenticated():
            worksheet = user.worksheets.get(name=name)
        else:
            worksheet = Worksheet.objects.get(user__isnull=True, name=name)
    except Worksheet.DoesNotExist:
        raise Http404

    content_type = get_content_type(request)
    return render_to_response('main.html', {
        'login_form': LoginForm(),
        'save_new_form': SaveNewForm(),
        'require_login': settings.REQUIRE_LOGIN,
        'worksheet': name,
    }, context_instance=RequestContext(request), content_type=content_type)


def blank_worksheet(request):
    content_type = get_content_type(request)
    return render_to_response('main.html', {
        'login_form': LoginForm(),
        'save_new_form': SaveNewForm(),
        'require_login': settings.REQUIRE_LOGIN,
        'worksheet': '',
    }, context_instance=RequestContext(request), content_type=content_type)


def worksheets(request):
    content_type = get_content_type(request)
    return render_to_response('worksheets.html', {
        'login_form': LoginForm(),
        'save_form': SaveForm(),
        'delete_form': DeleteForm(),
        'require_login': settings.REQUIRE_LOGIN,
    }, context_instance=RequestContext(request), content_type=content_type)


def error_404_view(request):
    t = loader.get_template('404.html')
    return HttpResponseNotFound(t.render(RequestContext(request, {
        'title': 'Page not found',
        'request_path': request.path,
    })))


def error_500_view(request):
    t = loader.get_template('500.html')
    return HttpResponseServerError(t.render(RequestContext(request, {
        'title': 'Server error',
    })))


def query(request):
    from mathics.core.parser import MultiLineFeeder

    input = request.POST.get('query', '')
    if settings.DEBUG and not input:
        input = request.GET.get('query', '')

    if settings.LOG_QUERIES:
        query_log = Query(query=input, error=True,
                          browser=request.META.get('HTTP_USER_AGENT', ''),
                          remote_user=request.META.get('REMOTE_USER', ''),
                          remote_addr=request.META.get('REMOTE_ADDR', ''),
                          remote_host=request.META.get('REMOTE_HOST', ''),
                          meta=six.text_type(request.META),
                          log='',
                          )
        query_log.save()

    user_definitions = request.session.get('definitions')
    definitions.set_user_definitions(user_definitions)
    evaluation = Evaluation(definitions, format='xml', output=WebOutput())
    feeder = MultiLineFeeder(input, '<notebook>')
    results = []
    try:
        while not feeder.empty():
            expr = evaluation.parse_feeder(feeder)
            if expr is None:
                results.append(Result(evaluation.out, None, None))  # syntax errors
                evaluation.out = []
                continue
            result = evaluation.evaluate(expr, timeout=settings.TIMEOUT)
            if result is not None:
                results.append(result)
    except Exception as exc:
        if settings.DEBUG and settings.DISPLAY_EXCEPTIONS:
            info = traceback.format_exception(*sys.exc_info())
            info = '\n'.join(info)
            msg = 'Exception raised: %s\n\n%s' % (exc, info)
            results.append(Result([Message('System', 'exception', msg)], None, None))
        else:
            raise
    result = {
        'results': [result.get_data() for result in results],
    }
    request.session['definitions'] = definitions.get_user_definitions()

    if settings.LOG_QUERIES:
        query_log.timeout = evaluation.timeout
        query_log.result = six.text_type(result)  # evaluation.results
        query_log.error = False
        query_log.save()

    return JsonResponse(result)

# taken from http://code.activestate.com/recipes/410076/


def nicepass(alpha=6, numeric=2):
    """
    returns a human-readble password (say rol86din instead of
    a difficult to remember K8Yn9muL )
    """
    import string
    import random
    vowels = ['a', 'e', 'i', 'o', 'u']
    consonants = [a for a in string.ascii_lowercase if a not in vowels]
    digits = string.digits

    # utility functions
    def a_part(slen):
        ret = ''
        for i in range(slen):
            if i % 2 == 0:
                randid = random.randint(0, 20)  # number of consonants
                ret += consonants[randid]
            else:
                randid = random.randint(0, 4)  # number of vowels
                ret += vowels[randid]
        return ret

    def n_part(slen):
        ret = ''
        for i in range(slen):
            randid = random.randint(0, 9)  # number of digits
            ret += digits[randid]
        return ret

    fpl = alpha / 2
    if alpha % 2:
        fpl = int(alpha / 2) + 1
    lpl = alpha - fpl

    start = a_part(fpl)
    mid = n_part(numeric)
    end = a_part(lpl)

    return "%s%s%s" % (start, mid, end)


def email_user(user, subject, text):
    send_mail(subject, text, 'noreply@mathics.net', [user.username], fail_silently=False)


def login(request):
    if settings.DEBUG and not request.POST:
        request.POST = request.GET
    form = LoginForm(request.POST)
    result = ''
    general_errors = []
    if form.is_valid():
        email = form.cleaned_data['email']
        password = form.cleaned_data['password']
        if password:
            user = auth.authenticate(username=email, password=password)
            if user is None:
                general_errors = ["Invalid username and/or password."]
            else:
                result = 'ok'
                auth.login(request, user)
        else:
            password = nicepass()
            try:
                user = User.objects.get(username=email)
                result = 'reset'
                email_user(
                    user, "Your password at mathics.net",
                    ("""You have reset your password at mathics.net.\n
Your password is: %s\n\nYours,\nThe Mathics team""") % password)
            except User.DoesNotExist:
                user = User(username=email, email=email)
                result = 'created'
                email_user(
                    user, "New account at mathics.net",
                    """Welcome to mathics.net!\n
Your password is: %s\n\nYours,\nThe Mathics team""" % password)
            user.set_password(password)
            user.save()

    return JsonResponse({
        'result': result,
        'form': form.as_json(general_errors=general_errors),
    })


def logout(request):
    # Remember user definitions
    user_definitions = request.session.get('definitions', {})
    auth.logout(request)
    request.session['definitions'] = user_definitions
    return JsonResponse()


@require_ajax_login
def save(request):
    if settings.DEBUG and not request.POST:
        request.POST = request.GET
    if settings.REQUIRE_LOGIN and not request.user.is_authenticated():
        raise Http404
    form = SaveForm(request.POST)
    overwrite = request.POST.get('overwrite', False)
    result = ''
    general_errors = []
    if form.is_valid():
        content = request.POST.get('content', '')
        name = form.cleaned_data['name']

        if re.match(r'^[0-9A-Za-z]+[0-9A-Za-z._()\-\[\] ]*$', name) is None:
            general_errors = ["Worksheet name is invalid."]
        else:
            user = request.user
            if not user.is_authenticated():
                user = None
            try:
                worksheet = Worksheet.objects.get(user=user, name=name)
                if overwrite:
                    worksheet.content = content
                else:
                    result = 'overwrite'
            except Worksheet.DoesNotExist:
                worksheet = Worksheet(user=user, name=name, content=content)
            worksheet.save()

    return JsonResponse({
        'form': form.as_json(general_errors=general_errors),
        'result': result,
    })


def open(request):
    if settings.REQUIRE_LOGIN and not request.user.is_authenticated():
        raise Http404
    user = request.user
    name = request.POST.get('name', '')
    try:
        if user.is_authenticated():
            worksheet = user.worksheets.get(name=name)
        else:
            worksheet = Worksheet.objects.get(user__isnull=True, name=name)
        content = worksheet.content
    except Worksheet.DoesNotExist:
        content = ''

    return JsonResponse({
        'content': content,
    })


@require_ajax_login
def delete(request):
    if settings.REQUIRE_LOGIN and not request.user.is_authenticated():
        raise Http404
    user = request.user
    name = request.POST.get('name', '')
    confirm = request.POST.get('confirm', '').lower().strip()

    if not confirm or name.lower().strip() != confirm:
        return JsonResponse({
            'result': 'confirm',
            'form': '{}'
        })

    try:
        if user.is_authenticated():
            worksheet = user.worksheets.get(name=name)
        else:
            worksheet = Worksheet.objects.get(user__isnull=True, name=name)

        worksheet.delete()
    except Worksheet.DoesNotExist:
        raise Http404

    return JsonResponse({
        'result': '',
        'form': '{}'
    })


def get_worksheets(request):
    if settings.REQUIRE_LOGIN and not request.user.is_authenticated():
        result = []
    else:
        if request.user.is_authenticated():
            result = list(request.user.worksheets.order_by(
                'name').values('name'))
        else:
            result = list(Worksheet.objects.filter(
                user__isnull=True).order_by('name').values('name'))
    return JsonResponse({
        'worksheets': result,
    })

# auxiliary function


def render_doc(request, template_name, context, data=None, ajax=False):
    object = context.get('object')
    context.update({
        'ajax': ajax,
        'help_base': ('doc/base_ajax.html' if ajax else
                      'doc/base_standalone.html'),
        'prev': object.get_prev() if object else None,
        'next': object.get_next() if object else None,
    })
    if ajax:
        template = loader.get_template('doc/%s' % template_name)
        result = template.render(RequestContext(request, context))
        result = {
            'content': result,
        }
        if data is not None:
            result['data'] = data
        return JsonResponse(result)
    else:
        context.update({
            'data': data,
        })
        return render_to_response(
            'doc/%s' % template_name, context,
            context_instance=RequestContext(request),
            content_type=get_content_type(request))


def doc(request, ajax=''):
    return render_doc(request, 'overview.html', {
        'title': 'Documentation',
        'doc': documentation,
    }, ajax=ajax)


def doc_part(request, part, ajax=''):
    part = documentation.get_part(part)
    if not part:
        raise Http404
    return render_doc(request, 'part.html', {
        'title': part.get_title_html(),
        'part': part,
        'object': part,
    }, ajax=ajax)


def doc_chapter(request, part, chapter, ajax=''):
    chapter = documentation.get_chapter(part, chapter)
    if not chapter:
        raise Http404
    return render_doc(request, 'chapter.html', {
        'title': chapter.get_title_html(),
        'chapter': chapter,
        'object': chapter,
    }, ajax=ajax)


def doc_section(request, part, chapter, section, ajax=''):
    section = documentation.get_section(part, chapter, section)
    if not section:
        raise Http404
    data = section.html_data()
    return render_doc(request, 'section.html', {
        'title': section.get_title_html(),
        'title_operator': section.operator,
        'section': section,
        'object': section,
    }, data=data, ajax=ajax)


def doc_search(request):
    query = request.GET.get('query', '')
    result = documentation.search(query)
    if len([item for exact, item in result if exact]) <= 1:
        for exact, item in result:
            if exact or len(result) == 1:
                if isinstance(item, DocPart):
                    return doc_part(request, item.slug, ajax=True)
                elif isinstance(item, DocChapter):
                    return doc_chapter(
                        request, item.part.slug, item.slug, ajax=True)
                else:
                    return doc_section(
                        request, item.chapter.part.slug, item.chapter.slug,
                        item.slug, ajax=True)
    result = [item for exact, item in result]

    return render_doc(request, 'search.html', {
        'title': "Search documentation",
        'result': result,
    }, ajax=True)
