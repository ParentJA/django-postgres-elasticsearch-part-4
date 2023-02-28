from urllib.parse import SplitResult, urlencode, urlsplit

from elasticsearch_dsl import Search
from elasticsearch_dsl.query import Match, Term
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from . import constants
from .models import Wine, WineSearchWord
from .serializers import WineSerializer, WineSearchWordSerializer
from .filters import WineFilterSet, WineSearchWordFilterSet


class WinesView(ListAPIView):
    queryset = Wine.objects.all()
    serializer_class = WineSerializer
    filterset_class = WineFilterSet


class WineSearchWordsView(ListAPIView):
    queryset = WineSearchWord.objects.all()
    serializer_class = WineSearchWordSerializer
    filterset_class = WineSearchWordFilterSet


class ESWinesView(APIView):
    def _build_url(self, params, new_offset):
        url = self.request.build_absolute_uri()
        old_result = urlsplit(url)
        new_result = SplitResult(
            old_result.scheme,
            old_result.netloc,
            old_result.path,
            query=urlencode({
                **params,
                'offset': new_offset,
            }, doseq=True),
            fragment='',
        )
        return new_result.geturl()

    def _get_previous_page(self, params):
        limit, offset = params.get('limit'), params.get('offset')
        if offset > 0:
            return self._build_url(params, offset - limit)
        else:
            return None

    def _get_next_page(self, params, count):
        limit, offset = params.get('limit'), params.get('offset')
        if (offset + limit) < count:
            return self._build_url(params, offset + limit)
        else:
            return None

    def get(self, request, *args, **kwargs):
        query = self.request.query_params.get('query')
        country = self.request.query_params.get('country')
        points = self.request.query_params.get('points')
        limit = int(self.request.query_params.get('limit', 10))
        offset = int(self.request.query_params.get('offset', 0))

        # Build Elasticsearch query.
        search = Search(index=constants.ES_INDEX)
        q = {'should': [], 'filter': []}

        # Build should clause.
        if query:
            q['should'] = [
                Match(variety=query),
                Match(winery=query),
                Match(description=query)
            ]
            q['minimum_should_match'] = 1

        # Build filter clause.
        if country:
            q['filter'].append(Term(country=country))
        if points:
            q['filter'].append(Term(points=points))

        search = search.query('bool', **q)[offset : offset + limit]

        response = search.execute()

        return Response(data={
            'count': response.hits.total.value,
            'next': self._get_next_page({
                'limit': limit,
                'offset': offset,
                'query': query,
            }, count=response.hits.total.value),
            'previous': self._get_previous_page({
                'limit': limit,
                'offset': offset,
                'query': query,
            }),
            'results': [{
                'id': hit.meta.id,
                'country': hit.country,
                'description': hit.description,
                'points': hit.points,
                'price': hit.price,
                'variety': hit.variety,
                'winery': hit.winery,
            } for hit in response],
        })
