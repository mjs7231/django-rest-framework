import re

from django.conf.urls.defaults import patterns, url, include
from django.test import TestCase
from django.test.client import RequestFactory

from rest_framework import status, permissions
from rest_framework.compat import yaml
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.renderers import BaseRenderer, JSONRenderer, YAMLRenderer, \
    XMLRenderer, JSONPRenderer, BrowsableAPIRenderer
from rest_framework.parsers import YAMLParser, XMLParser
from rest_framework.settings import api_settings

from StringIO import StringIO
import datetime
from decimal import Decimal


DUMMYSTATUS = status.HTTP_200_OK
DUMMYCONTENT = 'dummycontent'

RENDERER_A_SERIALIZER = lambda x: 'Renderer A: %s' % x
RENDERER_B_SERIALIZER = lambda x: 'Renderer B: %s' % x


expected_results = [
    ((elem for elem in [1, 2, 3]), JSONRenderer, '[1, 2, 3]')  # Generator
]


class BasicRendererTests(TestCase):
    def test_expected_results(self):
        for value, renderer_cls, expected in expected_results:
            output = renderer_cls().render(value)
            self.assertEquals(output, expected)


class RendererA(BaseRenderer):
    media_type = 'mock/renderera'
    format = "formata"

    def render(self, data, media_type=None, renderer_context=None):
        return RENDERER_A_SERIALIZER(data)


class RendererB(BaseRenderer):
    media_type = 'mock/rendererb'
    format = "formatb"

    def render(self, data, media_type=None, renderer_context=None):
        return RENDERER_B_SERIALIZER(data)


class MockView(APIView):
    renderer_classes = (RendererA, RendererB)

    def get(self, request, **kwargs):
        response = Response(DUMMYCONTENT, status=DUMMYSTATUS)
        return response


class MockGETView(APIView):

    def get(self, request, **kwargs):
        return Response({'foo': ['bar', 'baz']})


class HTMLView(APIView):
    renderer_classes = (BrowsableAPIRenderer, )

    def get(self, request, **kwargs):
        return Response('text')


class HTMLView1(APIView):
    renderer_classes = (BrowsableAPIRenderer, JSONRenderer)

    def get(self, request, **kwargs):
        return Response('text')

urlpatterns = patterns('',
    url(r'^.*\.(?P<format>.+)$', MockView.as_view(renderer_classes=[RendererA, RendererB])),
    url(r'^$', MockView.as_view(renderer_classes=[RendererA, RendererB])),
    url(r'^jsonp/jsonrenderer$', MockGETView.as_view(renderer_classes=[JSONRenderer, JSONPRenderer])),
    url(r'^jsonp/nojsonrenderer$', MockGETView.as_view(renderer_classes=[JSONPRenderer])),
    url(r'^html$', HTMLView.as_view()),
    url(r'^html1$', HTMLView1.as_view()),
    url(r'^api', include('rest_framework.urls', namespace='rest_framework'))
)


class POSTDeniedPermission(permissions.BasePermission):
    def has_permission(self, request, view, obj=None):
        return request.method != 'POST'


class POSTDeniedView(APIView):
    renderer_classes = (BrowsableAPIRenderer,)
    permission_classes = (POSTDeniedPermission,)

    def get(self, request):
        return Response()

    def post(self, request):
        return Response()

    def put(self, request):
        return Response()


class DocumentingRendererTests(TestCase):
    def test_only_permitted_forms_are_displayed(self):
        view = POSTDeniedView.as_view()
        request = RequestFactory().get('/')
        response = view(request).render()
        self.assertNotContains(response, '>POST<')
        self.assertContains(response, '>PUT<')


class RendererEndToEndTests(TestCase):
    """
    End-to-end testing of renderers using an RendererMixin on a generic view.
    """

    urls = 'rest_framework.tests.renderers'

    def test_default_renderer_serializes_content(self):
        """If the Accept header is not set the default renderer should serialize the response."""
        resp = self.client.get('/')
        self.assertEquals(resp['Content-Type'], RendererA.media_type)
        self.assertEquals(resp.content, RENDERER_A_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_head_method_serializes_no_content(self):
        """No response must be included in HEAD requests."""
        resp = self.client.head('/')
        self.assertEquals(resp.status_code, DUMMYSTATUS)
        self.assertEquals(resp['Content-Type'], RendererA.media_type)
        self.assertEquals(resp.content, '')

    def test_default_renderer_serializes_content_on_accept_any(self):
        """If the Accept header is set to */* the default renderer should serialize the response."""
        resp = self.client.get('/', HTTP_ACCEPT='*/*')
        self.assertEquals(resp['Content-Type'], RendererA.media_type)
        self.assertEquals(resp.content, RENDERER_A_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_specified_renderer_serializes_content_default_case(self):
        """If the Accept header is set the specified renderer should serialize the response.
        (In this case we check that works for the default renderer)"""
        resp = self.client.get('/', HTTP_ACCEPT=RendererA.media_type)
        self.assertEquals(resp['Content-Type'], RendererA.media_type)
        self.assertEquals(resp.content, RENDERER_A_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_specified_renderer_serializes_content_non_default_case(self):
        """If the Accept header is set the specified renderer should serialize the response.
        (In this case we check that works for a non-default renderer)"""
        resp = self.client.get('/', HTTP_ACCEPT=RendererB.media_type)
        self.assertEquals(resp['Content-Type'], RendererB.media_type)
        self.assertEquals(resp.content, RENDERER_B_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_specified_renderer_serializes_content_on_accept_query(self):
        """The '_accept' query string should behave in the same way as the Accept header."""
        param = '?%s=%s' % (
            api_settings.URL_ACCEPT_OVERRIDE,
            RendererB.media_type
        )
        resp = self.client.get('/' + param)
        self.assertEquals(resp['Content-Type'], RendererB.media_type)
        self.assertEquals(resp.content, RENDERER_B_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_unsatisfiable_accept_header_on_request_returns_406_status(self):
        """If the Accept header is unsatisfiable we should return a 406 Not Acceptable response."""
        resp = self.client.get('/', HTTP_ACCEPT='foo/bar')
        self.assertEquals(resp.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_specified_renderer_serializes_content_on_format_query(self):
        """If a 'format' query is specified, the renderer with the matching
        format attribute should serialize the response."""
        param = '?%s=%s' % (
            api_settings.URL_FORMAT_OVERRIDE,
            RendererB.format
        )
        resp = self.client.get('/' + param)
        self.assertEquals(resp['Content-Type'], RendererB.media_type)
        self.assertEquals(resp.content, RENDERER_B_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_specified_renderer_serializes_content_on_format_kwargs(self):
        """If a 'format' keyword arg is specified, the renderer with the matching
        format attribute should serialize the response."""
        resp = self.client.get('/something.formatb')
        self.assertEquals(resp['Content-Type'], RendererB.media_type)
        self.assertEquals(resp.content, RENDERER_B_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)

    def test_specified_renderer_is_used_on_format_query_with_matching_accept(self):
        """If both a 'format' query and a matching Accept header specified,
        the renderer with the matching format attribute should serialize the response."""
        param = '?%s=%s' % (
            api_settings.URL_FORMAT_OVERRIDE,
            RendererB.format
        )
        resp = self.client.get('/' + param,
                               HTTP_ACCEPT=RendererB.media_type)
        self.assertEquals(resp['Content-Type'], RendererB.media_type)
        self.assertEquals(resp.content, RENDERER_B_SERIALIZER(DUMMYCONTENT))
        self.assertEquals(resp.status_code, DUMMYSTATUS)


_flat_repr = '{"foo": ["bar", "baz"]}'
_indented_repr = '{\n  "foo": [\n    "bar",\n    "baz"\n  ]\n}'


def strip_trailing_whitespace(content):
    """
    Seems to be some inconsistencies re. trailing whitespace with
    different versions of the json lib.
    """
    return re.sub(' +\n', '\n', content)


class JSONRendererTests(TestCase):
    """
    Tests specific to the JSON Renderer
    """

    def test_without_content_type_args(self):
        """
        Test basic JSON rendering.
        """
        obj = {'foo': ['bar', 'baz']}
        renderer = JSONRenderer()
        content = renderer.render(obj, 'application/json')
        # Fix failing test case which depends on version of JSON library.
        self.assertEquals(content, _flat_repr)

    def test_with_content_type_args(self):
        """
        Test JSON rendering with additional content type arguments supplied.
        """
        obj = {'foo': ['bar', 'baz']}
        renderer = JSONRenderer()
        content = renderer.render(obj, 'application/json; indent=2')
        self.assertEquals(strip_trailing_whitespace(content), _indented_repr)


class JSONPRendererTests(TestCase):
    """
    Tests specific to the JSONP Renderer
    """

    urls = 'rest_framework.tests.renderers'

    def test_without_callback_with_json_renderer(self):
        """
        Test JSONP rendering with View JSON Renderer.
        """
        resp = self.client.get('/jsonp/jsonrenderer',
                               HTTP_ACCEPT='application/javascript')
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp['Content-Type'], 'application/javascript')
        self.assertEquals(resp.content, 'callback(%s);' % _flat_repr)

    def test_without_callback_without_json_renderer(self):
        """
        Test JSONP rendering without View JSON Renderer.
        """
        resp = self.client.get('/jsonp/nojsonrenderer',
                               HTTP_ACCEPT='application/javascript')
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp['Content-Type'], 'application/javascript')
        self.assertEquals(resp.content, 'callback(%s);' % _flat_repr)

    def test_with_callback(self):
        """
        Test JSONP rendering with callback function name.
        """
        callback_func = 'myjsonpcallback'
        resp = self.client.get('/jsonp/nojsonrenderer?callback=' + callback_func,
                               HTTP_ACCEPT='application/javascript')
        self.assertEquals(resp.status_code, 200)
        self.assertEquals(resp['Content-Type'], 'application/javascript')
        self.assertEquals(resp.content, '%s(%s);' % (callback_func, _flat_repr))


if yaml:
    _yaml_repr = 'foo: [bar, baz]\n'

    class YAMLRendererTests(TestCase):
        """
        Tests specific to the JSON Renderer
        """

        def test_render(self):
            """
            Test basic YAML rendering.
            """
            obj = {'foo': ['bar', 'baz']}
            renderer = YAMLRenderer()
            content = renderer.render(obj, 'application/yaml')
            self.assertEquals(content, _yaml_repr)

        def test_render_and_parse(self):
            """
            Test rendering and then parsing returns the original object.
            IE obj -> render -> parse -> obj.
            """
            obj = {'foo': ['bar', 'baz']}

            renderer = YAMLRenderer()
            parser = YAMLParser()

            content = renderer.render(obj, 'application/yaml')
            data = parser.parse(StringIO(content))
            self.assertEquals(obj, data)


class XMLRendererTestCase(TestCase):
    """
    Tests specific to the XML Renderer
    """

    _complex_data = {
        "creation_date": datetime.datetime(2011, 12, 25, 12, 45, 00),
        "name": "name",
        "sub_data_list": [
            {
                "sub_id": 1,
                "sub_name": "first"
            },
            {
                "sub_id": 2,
                "sub_name": "second"
            }
        ]
    }

    def test_render_string(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render({'field': 'astring'}, 'application/xml')
        self.assertXMLContains(content, '<field>astring</field>')

    def test_render_integer(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render({'field': 111}, 'application/xml')
        self.assertXMLContains(content, '<field>111</field>')

    def test_render_datetime(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render({
            'field': datetime.datetime(2011, 12, 25, 12, 45, 00)
        }, 'application/xml')
        self.assertXMLContains(content, '<field>2011-12-25 12:45:00</field>')

    def test_render_float(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render({'field': 123.4}, 'application/xml')
        self.assertXMLContains(content, '<field>123.4</field>')

    def test_render_decimal(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render({'field': Decimal('111.2')}, 'application/xml')
        self.assertXMLContains(content, '<field>111.2</field>')

    def test_render_none(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render({'field': None}, 'application/xml')
        self.assertXMLContains(content, '<field></field>')

    def test_render_complex_data(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = renderer.render(self._complex_data, 'application/xml')
        self.assertXMLContains(content, '<sub_name>first</sub_name>')
        self.assertXMLContains(content, '<sub_name>second</sub_name>')

    def test_render_and_parse_complex_data(self):
        """
        Test XML rendering.
        """
        renderer = XMLRenderer()
        content = StringIO(renderer.render(self._complex_data, 'application/xml'))

        parser = XMLParser()
        complex_data_out = parser.parse(content)
        error_msg = "complex data differs!IN:\n %s \n\n OUT:\n %s" % (repr(self._complex_data), repr(complex_data_out))
        self.assertEqual(self._complex_data, complex_data_out, error_msg)

    def assertXMLContains(self, xml, string):
        self.assertTrue(xml.startswith('<?xml version="1.0" encoding="utf-8"?>\n<root>'))
        self.assertTrue(xml.endswith('</root>'))
        self.assertTrue(string in xml, '%r not in %r' % (string, xml))
