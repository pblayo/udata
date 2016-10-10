# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import time

from datetime import datetime, timedelta, date

from werkzeug.urls import url_decode, url_parse

from factory.mongoengine import MongoEngineFactory

from udata import search
from udata.core.metrics import Metric
from udata.models import db
from udata.utils import multi_to_dict
from udata.i18n import gettext as _, format_date
from udata.tests import TestCase, DBTestMixin, SearchTestMixin
from udata.utils import faker


#############################################################################
#                           Fake object for testing                         #
#############################################################################

class Fake(db.Document):
    title = db.StringField()
    description = db.StringField()
    tags = db.ListField(db.StringField())
    other = db.ListField(db.StringField())

    def __unicode__(self):
        return 'fake'


class FakeMetricInt(Metric):
    model = Fake
    name = 'fake-metric-int'


class FakeMetricFloat(Metric):
    model = Fake
    name = 'fake-metric-float'
    value_type = float


class FakeFactory(MongoEngineFactory):
    class Meta:
        model = Fake


@search.register
class FakeSearch(search.ModelSearchAdapter):
    class Meta:
        doc_type = 'Fake'

    model = Fake
    fields = [
        'title^2',
        'description',
    ]
    facets = {
        'tag': search.TermsFacet(field='tags'),
        'other': search.TermsFacet(field='other'),
        'range': search.RangeFacet(
            field='a_num_field',
            ranges=[(_('Never reused'), (None, 1)),
                    (_('Little reused'), (1, 5)),
                    (_('Quite reused'), (5, 10)),
                    (_('Heavily reused'), (10, None))]),
    }
    sorts = {
        'title': search.Sort('title.raw'),
        'description': search.Sort('description.raw'),
    }


class FakeSearchWithDateRange(search.ModelSearchAdapter):
    class Meta:
        doc_type = 'Dataset'

    model = Fake
    fields = [
        'title^2',
        'description',
    ]
    facets = {
        'tag': search.TermsFacet(field='tags'),
        'other': search.TermsFacet(field='other'),
        'range': search.RangeFacet(
            field='a_num_field',
            ranges=[(_('Never reused'), (None, 1)),
                    (_('Little reused'), (1, 5)),
                    (_('Quite reused'), (5, 10)),
                    (_('Heavily reused'), (10, None))]),
    }


class FuzzySearch(FakeSearch):
    fuzzy = True


#############################################################################
#                     Elasticsearch DSL specific helpers                    #
#############################################################################

def get_body(facet_search):
    '''Extract the JSON body from a FacetedSearch'''
    return facet_search._s.to_dict()


def get_query(facet_search):
    '''Extract the query part from a FacetedSearch'''
    return get_body(facet_search).get('query')


def facet_agg_key(key):
    '''Build the facet aggregation key'''
    return '_filter_{0}'.format(key)


#############################################################################
#                                  Tests                                    #
#############################################################################


class SearchQueryTest(SearchTestMixin, TestCase):
    def test_execute_search_result(self):
        '''Should return a SearchResult with the right model'''
        self.init_search()
        result = search.query(FakeSearch)
        self.assertIsInstance(result, search.SearchResult)
        self.assertEqual(result.query.adapter, FakeSearch)

    def test_execute_search_result_with_model(self):
        '''Should return a SearchResult with the right model'''
        self.init_search()
        result = search.query(Fake)
        self.assertIsInstance(result, search.SearchResult)
        self.assertEqual(result.query.adapter, FakeSearch)

    def test_empty_search(self):
        '''An empty query should match all documents'''
        search_query = search.search_for(FakeSearch)
        body = get_body(search_query)
        self.assertEqual(body['query'], {'match_all': {}})
        self.assertNotIn('aggregations', body)
        self.assertNotIn('aggs', body)
        self.assertNotIn('sort', body)

    def test_paginated_search(self):
        '''Search should handle pagination'''
        search_query = search.search_for(FakeSearch, page=3, page_size=10)
        body = get_body(search_query)
        self.assertIn('from', body)
        self.assertEqual(body['from'], 20)
        self.assertIn('size', body)
        self.assertEqual(body['size'], 10)

    def test_sorted_search_asc(self):
        '''Search should sort by field in ascending order'''
        search_query = search.search_for(FakeSearch, sort='title')
        body = get_body(search_query)
        self.assertEqual(body['sort'], [{'title.raw': 'asc'}])

    def test_sorted_search_desc(self):
        '''Search should sort by field in descending order'''
        search_query = search.search_for(FakeSearch, sort='-title')
        body = get_body(search_query)
        self.assertEqual(body['sort'], [{'title.raw': 'desc'}])

    def test_multi_sorted_search(self):
        '''Search should sort'''
        search_query = search.search_for(FakeSearch,
                                         sort=['-title', 'description'])
        body = get_body(search_query)
        self.assertEqual(body['sort'], [
            {'title.raw': 'desc'},
            {'description.raw': 'asc'},
        ])

    def test_custom_scoring(self):
        '''Search should handle field boosting'''
        class FakeBoostedSearch(FakeSearch):
            boosters = [
                search.BoolBooster('some_bool_field', 1.1)
            ]

        query = search.search_for(FakeBoostedSearch)
        body = get_body(query)
        # Query should be wrapped in function_score
        self.assertIn('function_score', body['query'])
        self.assertIn('query', body['query']['function_score'])
        self.assertIn('functions', body['query']['function_score'])
        self.assertEqual(body['query']['function_score']['functions'][0], {
            'filter': {'term': {'some_bool_field': True}},
            'boost_factor': 1.1,
        })

    def test_decay_function_scoring(self):
        '''Search should handle field decay'''
        class FakeBoostedSearch(FakeSearch):
            boosters = [
                search.GaussDecay('a_num_field', 10),
                search.ExpDecay('another_field', 20),
                search.LinearDecay('last_field', 30),
            ]

        query = search.search_for(FakeBoostedSearch)
        body = get_body(query)
        functions = body['query']['function_score']['functions']
        # Query should be wrapped in a gaus decay function
        self.assertEqual(functions[0], {
            'gauss': {
                'a_num_field': {
                    'origin': 10,
                    'scale': 10,
                }
            },
        })
        self.assertEqual(functions[1], {
            'exp': {
                'another_field': {
                    'origin': 20,
                    'scale': 20,
                }
            },
        })
        self.assertEqual(functions[2], {
            'linear': {
                'last_field': {
                    'origin': 30,
                    'scale': 30,
                }
            },
        })

    def test_decay_function_scoring_with_options(self):
        '''Search should handle field decay with options'''
        class FakeBoostedSearch(FakeSearch):
            boosters = [
                search.GaussDecay('a_num_field', 10, 20, offset=5, decay=0.5),
                search.ExpDecay(
                    'another_field', 20, scale=30, offset=5, decay=0.5),
                search.LinearDecay('last_field', 30, 40, offset=5, decay=0.5),
            ]

        query = search.search_for(FakeBoostedSearch)
        body = get_body(query)
        functions = body['query']['function_score']['functions']
        # Query should be wrapped in a gaus decay function
        self.assertEqual(functions[0], {
            'gauss': {
                'a_num_field': {
                    'origin': 10,
                    'scale': 20,
                    'offset': 5,
                    'decay': 0.5,
                }
            },
        })
        self.assertEqual(functions[1], {
            'exp': {
                'another_field': {
                    'origin': 20,
                    'scale': 30,
                    'offset': 5,
                    'decay': 0.5,
                }
            },
        })
        self.assertEqual(functions[2], {
            'linear': {
                'last_field': {
                    'origin': 30,
                    'scale': 40,
                    'offset': 5,
                    'decay': 0.5
                }
            },
        })

    def test_decay_function_scoring_with_callables(self):
        '''Search should handle field decay with options'''
        get_dot5 = lambda: 0.5  # noqa
        get_5 = lambda: 5  # noqa
        get_10 = lambda: 10  # noqa
        get_20 = lambda: 20  # noqa
        get_30 = lambda: 30  # noqa
        get_40 = lambda: 40  # noqa

        class FakeBoostedSearch(FakeSearch):
            boosters = [
                search.GaussDecay('a_num_field', get_10,
                                  get_20, offset=get_5, decay=get_dot5),
                search.ExpDecay('another_field', get_20,
                                scale=get_30, offset=get_5, decay=get_dot5),
                search.LinearDecay('last_field', get_30,
                                   get_40, offset=get_5, decay=get_dot5),
            ]

        query = search.search_for(FakeBoostedSearch)
        body = get_body(query)
        functions = body['query']['function_score']['functions']
        # Query should be wrapped in a gaus decay function
        self.assertEqual(functions[0], {
            'gauss': {
                'a_num_field': {
                    'origin': 10,
                    'scale': 20,
                    'offset': 5,
                    'decay': 0.5,
                }
            },
        })
        self.assertEqual(functions[1], {
            'exp': {
                'another_field': {
                    'origin': 20,
                    'scale': 30,
                    'offset': 5,
                    'decay': 0.5,
                }
            },
        })
        self.assertEqual(functions[2], {
            'linear': {
                'last_field': {
                    'origin': 30,
                    'scale': 40,
                    'offset': 5,
                    'decay': 0.5
                }
            },
        })

    def test_custom_function_scoring(self):
        '''Search should handle field boosting by function'''
        class FakeBoostedSearch(FakeSearch):
            boosters = [
                search.FunctionBooster('doc["field"].value * 2')
            ]

        query = search.search_for(FakeBoostedSearch)
        body = get_body(query)
        # Query should be wrapped in function_score
        self.assertEqual(body['query']['function_score']['functions'][0], {
            'script_score': {'script': 'doc["field"].value * 2'},
        })

    def test_simple_query(self):
        '''A simple query should use query_string with specified fields'''
        search_query = search.search_for(FakeSearch, q='test')
        expected = {
            'bool': {
                'must': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': search.i18n_analyzer,
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description']
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_default_analyzer(self):
        '''Default analyzer is overridable'''
        class FakeAnalyzerSearch(FakeSearch):
            analyzer = 'simple'

        search_query = search.search_for(FakeAnalyzerSearch, q='test')
        expected = {
            'bool': {
                'must': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': 'simple',
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description']
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_default_type(self):
        '''Default analyzer is overridable'''
        class FakeAnalyzerSearch(FakeSearch):
            match_type = 'most_fields'

        search_query = search.search_for(FakeAnalyzerSearch, q='test')
        expected = {
            'bool': {
                'must': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': search.i18n_analyzer,
                        'type': 'most_fields',
                        'fields': ['title^2', 'description']
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_simple_excluding_query(self):
        '''A simple query should negate a simple term in query_string'''
        search_query = search.search_for(FakeSearch, q='-test')
        expected = {
            'bool': {
                'must_not': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': search.i18n_analyzer,
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description']
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_query_with_both_including_and_excluding_terms(self):
        '''A query should detect negation on each term in query_string'''
        search_query = search.search_for(FakeSearch, q='test -negated')
        expected = {
            'bool': {
                'must': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': search.i18n_analyzer,
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description']
                    }}
                ],
                'must_not': [
                    {'multi_match': {
                        'query': 'negated',
                        'analyzer': search.i18n_analyzer,
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description']
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_simple_query_fuzzy(self):
        '''A simple query should use query_string with specified fields'''
        search_query = search.search_for(FuzzySearch, q='test')
        expected = {
            'bool': {
                'must': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': search.i18n_analyzer,
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description'],
                        'fuzziness': 'AUTO',
                        'prefix_length': 2,
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_simple_query_flatten(self):
        '''A query uses query_string with specified fields and flattens'''
        search_query = search.search_for(FakeSearch, q='test')
        expected = {
            'bool': {
                'must': [
                    {'multi_match': {
                        'query': 'test',
                        'analyzer': search.i18n_analyzer,
                        'type': 'cross_fields',
                        'fields': ['title^2', 'description']
                    }}
                ]
            }
        }
        self.assertEqual(get_query(search_query), expected)

    def test_facets_true(self):
        search_query = search.search_for(FakeSearch, facets=True)
        aggregations = get_body(search_query).get('aggs', {})
        self.assertEqual(len(aggregations), len(FakeSearch.facets))
        for key in FakeSearch.facets.keys():
            self.assertIn(facet_agg_key(key), aggregations.keys())

    def test_facets_all(self):
        search_query = search.search_for(FakeSearch, facets='all')
        aggregations = get_body(search_query).get('aggs', {})
        self.assertEqual(len(aggregations), len(FakeSearch.facets))
        for key in FakeSearch.facets.keys():
            self.assertIn(facet_agg_key(key), aggregations.keys())

    def test_selected_facets(self):
        selected_facets = ['tag', 'other']
        search_query = search.search_for(
            FakeSearch, facets=selected_facets)
        aggregations = get_body(search_query).get('aggs', {})
        self.assertEqual(len(aggregations), len(selected_facets))
        for key in FakeSearch.facets.keys():
            if key in selected_facets:
                self.assertIn(facet_agg_key(key), aggregations.keys())
            else:
                self.assertNotIn(facet_agg_key(key), aggregations.keys())

    def test_aggregation_filter(self):
        search_query = search.search_for(FakeSearch, q='test', tag='value')
        expectations = [
            {'multi_match': {
                'query': 'test',
                'analyzer': search.i18n_analyzer,
                'type': 'cross_fields',
                'fields': ['title^2', 'description']
            }},
            {'term': {'tags': 'value'}},
        ]

        query = get_query(search_query)
        self.assertEqual(len(query['bool']['must']), len(expectations))
        for expected in expectations:
            self.assertIn(expected, query['bool']['must'])

    def test_aggregation_filter_multi(self):
        search_query = search.search_for(
            FakeSearchWithDateRange,
            q='test',
            tag=['value-1', 'value-2'],
            other='value',
            range='3-8',
            daterange='2013-01-07-2014-06-07'
        )
        expectations = [
            {'multi_match': {
                'query': 'test',
                'analyzer': search.i18n_analyzer,
                'type': 'cross_fields',
                'fields': ['title^2', 'description']
            }},
            {'term': {'tags': 'value-1'}},
            {'term': {'tags': 'value-2'}},
            {'term': {'other': 'value'}},
            {'range': {
                'a_num_field': {
                    'gte': 3,
                    'lte': 8,
                }
            }},
            {'range': {
                'a_daterange_field': {
                    'lte': '2014-06-07',
                    'gte': '2013-01-07',
                },
            }},
        ]
        query = get_query(search_query)
        for expected in expectations:
            self.assertIn(expected, query['bool']['must'])

    def test_to_url(self):
        kwargs = {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': 2,
            'facets': True,
        }
        search_query = search.search_for(FakeSearch, **kwargs)
        with self.app.test_request_context('/an_url'):
            url = search_query.to_url()
        parsed_url = url_parse(url)
        qs = url_decode(parsed_url.query)

        self.assertEqual(parsed_url.path, '/an_url')
        self.assertEqual(multi_to_dict(qs), {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': '2',
        })

    def test_to_url_with_override(self):
        kwargs = {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': 2,
        }
        search_query = search.search_for(FakeSearch, **kwargs)
        with self.app.test_request_context('/an_url'):
            url = search_query.to_url(tag='tag3', other='value')
        parsed_url = url_parse(url)
        qs = url_decode(parsed_url.query)

        self.assertEqual(parsed_url.path, '/an_url')
        self.assertEqual(multi_to_dict(qs), {
            'q': 'test',
            'tag': ['tag1', 'tag2', 'tag3'],
            'other': 'value',
        })

    def test_to_url_with_override_and_replace(self):
        kwargs = {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': 2,
        }
        search_query = search.search_for(FakeSearch, **kwargs)
        with self.app.test_request_context('/an_url'):
            url = search_query.to_url(tag='tag3', other='value', replace=True)
        parsed_url = url_parse(url)
        qs = url_decode(parsed_url.query)

        self.assertEqual(parsed_url.path, '/an_url')
        self.assertEqual(multi_to_dict(qs), {
            'q': 'test',
            'tag': 'tag3',
            'other': 'value',
        })

    def test_to_url_with_none(self):
        kwargs = {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': 2,
        }
        search_query = search.search_for(FakeSearch, **kwargs)
        with self.app.test_request_context('/an_url'):
            url = search_query.to_url(tag=None, other='value', replace=True)
        parsed_url = url_parse(url)
        qs = url_decode(parsed_url.query)

        self.assertEqual(parsed_url.path, '/an_url')
        self.assertEqual(multi_to_dict(qs), {
            'q': 'test',
            'other': 'value',
        })

    def test_to_url_with_specified_url(self):
        kwargs = {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': 2,
        }
        search_query = search.search_for(FakeSearch, **kwargs)
        with self.app.test_request_context('/an_url'):
            url = search_query.to_url('/another_url')
        parsed_url = url_parse(url)
        qs = url_decode(parsed_url.query)

        self.assertEqual(parsed_url.path, '/another_url')
        self.assertEqual(multi_to_dict(qs), {
            'q': 'test',
            'tag': ['tag1', 'tag2'],
            'page': '2',
        })


class TestMetricsMapping(TestCase):
    def test_map_metrics(self):
        mapping = search.metrics_mapping(Fake)
        self.assertEqual(mapping, {
            'type': 'object',
            'properties': {
                'fake-metric-int': {
                    'type': 'integer',
                },
                'fake-metric-float': {
                    'type': 'float',
                },
            }
        })


def hit_factory():
    return {
        "_score": float(faker.random_number(2)),
        "_type": "fake",
        "_id": faker.md5(),
        "_source": {
            "title": faker.sentence(),
            "tags": [faker.word() for _ in range(faker.random_digit())]
        },
        "_index": "udata-test"
    }


def es_factory(nb=20, page=1, page_size=20, total=42):
    '''Build a fake ElasticSearch response'''
    hits = sorted(
        (hit_factory() for _ in range(nb)),
        key=lambda h: h['_score']
    )
    max_score = hits[-1]['_score']
    return {
        "hits": {
            "hits": hits,
            "total": total,
            "max_score": max_score
        },
        "_shards": {
            "successful": 5,
            "failed": 0,
            "total": 5
        },
        "took": 52,
        "timed_out": False
    }


class FacetTestCase(TestCase):
    def assert_agg(self, name, expected):
        aggs = self.facet.to_aggregations(name)
        as_dict = dict((k, v.to_dict()) for k, v in aggs.items())
        self.assertEqual(as_dict, expected)


class TestTermsFacet(FacetTestCase):
    def setUp(self):
        self.facet = search.TermsFacet(field='tags')

    def test_to_query(self):
        self.assertEqual(self.facet.to_query(), {
            'terms': {
                'field': 'tags',
                'size': 20,
            }
        })

    def test_to_query_with_excludes(self):
        self.assertEqual(self.facet.to_query(args=['tag1', 'tag2']), {
            'terms': {
                'field': 'tags',
                'size': 20,
                'exclude': ['tag1', 'tag2']
            }
        })

    def test_from_response(self):
        response = es_factory()
        response['aggregations'] = {
            'test': {
                '_type': 'terms',
                'total': 229,
                'other': 33,
                'missing': 2,
                'buckets': [{
                    'key': faker.word(),
                    'doc_count': faker.random_number(2)
                } for _ in range(10)],
            }
        }

        extracted = self.facet.from_response('test', response)
        self.assertEqual(extracted['type'], 'terms')
        self.assertEqual(len(extracted['terms']), 10)

    def test_to_filter(self):
        self.assertEqual(
            self.facet.to_filter('value'),
            {'term': {'tags': 'value'}}
        )

    def test_to_filter_multi(self):
        self.assertEqual(
            self.facet.to_filter(['value1', 'value2']),
            [
                {'term': {'tags': 'value1'}},
                {'term': {'tags': 'value2'}},
            ]
        )

    def test_aggregations(self):
        expected = {'foo': {'terms': {'field': 'tags', 'size': 20}}}
        self.assert_agg('foo', expected)

    def test_labelize(self):
        self.assertEqual(self.facet.labelize('label', 'fake'), 'fake')


class TestModelTermsFacet(FacetTestCase, DBTestMixin):
    def setUp(self):
        self.facet = search.ModelTermsFacet(field='fakes', model=Fake)

    def test_to_query(self):
        self.assertEqual(self.facet.to_query(), {
            'terms': {
                'field': 'fakes',
                'size': 20,
            }
        })

    def test_to_query_with_excludes(self):
        self.assertEqual(self.facet.to_query(args=['id1', 'id2']), {
            'terms': {
                'field': 'fakes',
                'size': 20,
                'exclude': ['id1', 'id2']
            }
        })

    def test_labelize(self):
        fake = FakeFactory()
        self.assertEqual(
            self.facet.labelize('label', str(fake.id)), 'fake')

    def test_from_response(self):
        fakes = [FakeFactory() for _ in range(10)]
        response = es_factory()
        response['aggregations'] = {
            'test': {
                '_type': 'terms',
                'total': 229,
                'other': 33,
                'missing': 2,
                'buckets': [{
                    'key': str(f.id),
                    'doc_count': faker.random_number(2)
                } for f in fakes],
            }
        }

        extracted = self.facet.from_response('test', response)
        self.assertEqual(extracted['type'], 'models')
        self.assertEqual(len(extracted['models']), 10)
        for fake, row in zip(fakes, extracted['models']):
            self.assertIsInstance(row[0], Fake)
            self.assertIsInstance(row[1], int)
            self.assertEqual(fake.id, row[0].id)

    def test_from_response_no_fetch(self):
        fakes = [FakeFactory() for _ in range(10)]
        response = es_factory()
        response['aggregations'] = {
            'test': {
                '_type': 'terms',
                'total': 229,
                'other': 33,
                'missing': 2,
                'buckets': [{
                    'key': str(f.id),
                    'doc_count': faker.random_number(2)
                } for f in fakes],
            }
        }

        extracted = self.facet.from_response(
            'test', response, fetch=False)
        self.assertEqual(extracted['type'], 'models')
        self.assertEqual(len(extracted['models']), 10)
        for fake, row in zip(fakes, extracted['models']):
            self.assertIsInstance(row[0], dict)
            self.assertIsInstance(row[1], int)
            self.assertEqual(row[0]['id'], str(fake.id))
            self.assertEqual(row[0]['class'], 'Fake')

    def test_to_filter(self):
        self.assertEqual(self.facet.to_filter('value'),
                         {'term': {'fakes': 'value'}})

    def test_aggregations(self):
        expected = {'foo': {'terms': {'field': 'fakes', 'size': 20}}}
        self.assert_agg('foo', expected)


class TestRangeFacet(FacetTestCase):
    def setUp(self):
        self.facet = search.RangeFacet(
            field='some_field',
            ranges=[(_('Never reused'), (None, 1)),
                    (_('Little reused'), (1, 5)),
                    (_('Quite reused'), (5, 10)),
                    (_('Heavily reused'), (10, None))])

    def test_to_query(self):
        self.assertEqual(self.facet.to_query(), {
            'stats': {
                'field': 'some_field'
            }
        })

    def test_from_response(self):
        response = es_factory()
        response['aggregations'] = {
            'test': {
                '_type': 'stats',
                'count': 123,
                'total': 666,
                'min': 3,
                'max': 42,
                'mean': 21.5,
                'sum_of_squares': 29.0,
                'variance': 2.25,
                'std_deviation': 1.5
            }
        }

        extracted = self.facet.from_response('test', response)
        self.assertEqual(extracted['type'], 'range')
        self.assertEqual(extracted['min'], 3)
        self.assertEqual(extracted['max'], 42)

    def test_from_response_with_error(self):
        response = es_factory()
        response['aggregations'] = {
            'test': {
                '_type': 'stats',
                'count': 0,
                'total': 0,
                'min': 'Infinity',
                'max': '-Infinity',
                'mean': 0.0,
                'sum_of_squares': 0.0,
                'variance': 'NaN',
                'std_deviation': 'NaN'
            }
        }

        extracted = self.facet.from_response('test', response)
        self.assertEqual(extracted['type'], 'range')
        self.assertEqual(extracted['min'], None)
        self.assertEqual(extracted['max'], None)
        self.assertFalse(extracted['visible'])

    def test_to_filter(self):
        self.assertEqual(self.facet.to_filter('3-8'), {
            'range': {
                'some_field': {
                    'gte': 3,
                    'lte': 8,
                }
            }
        })

    def test_aggregations(self):
        expected = {'foo': {'stats': {'field': 'some_field'}}}
        self.assert_agg('foo', expected)

    def test_labelize(self):
        self.assertEqual(
            self.facet.labelize('label', '4-15'), 'label: 4-15')


class SearchResultTest(TestCase):
    def test_properties(self):
        '''Search result should map some properties for easy access'''
        response = es_factory(nb=10, total=42)
        max_score = response['hits']['max_score']
        query = search.search_for(FakeSearch)
        result = search.SearchResult(query, response)

        self.assertEqual(result.total, 42)
        self.assertEqual(result.max_score, max_score)

        ids = result.get_ids()
        self.assertEqual(len(ids), 10)

    def test_no_failures(self):
        '''Search result should not fail on missing properties'''
        query = search.search_for(FakeSearch)
        result = search.SearchResult(query, {})

        self.assertEqual(result.total, 0)
        self.assertEqual(result.max_score, 0)

        ids = result.get_ids()
        self.assertEqual(len(ids), 0)

    def test_pagination(self):
        '''Search results should be paginated'''
        kwargs = {'page': 2, 'page_size': 3}
        query = search.search_for(FakeSearch, **kwargs)
        result = search.SearchResult(query, es_factory(nb=3, total=11))

        self.assertEqual(result.page, 2),
        self.assertEqual(result.page_size, 3)
        self.assertEqual(result.pages, 4)

    def test_pagination_empty(self):
        '''Search results should be paginated even if empty'''
        query = search.search_for(FakeSearch, page=2, page_size=3)
        result = search.SearchResult(query, {})

        self.assertEqual(result.page, 1),
        self.assertEqual(result.page_size, 3)
        self.assertEqual(result.pages, 0)

    def test_no_pagination_in_query(self):
        '''Search results should be paginated even if not asked'''
        query = search.search_for(FakeSearch)
        result = search.SearchResult(query, {})

        self.assertEqual(result.page, 1),
        self.assertEqual(result.page_size, search.DEFAULT_PAGE_SIZE)
        self.assertEqual(result.pages, 0)


class SearchAdaptorTest(SearchTestMixin, TestCase):
    def assert_tokens(self, input, output):
        self.assertEqual(
            set(search.ModelSearchAdapter.completer_tokenize(input)),
            set(output))

    def test_completer_tokenizer(self):
        self.assert_tokens('test', ['test'])
        self.assert_tokens('test square',
                           ['test square', 'test', 'square'])
        self.assert_tokens('test\'s square',
                           ['test\'s square', 'test square', 'test', 'square'])
        self.assert_tokens(
            'test l\'apostrophe',
            ['test l\'apostrophe', 'test apostrophe', 'test', 'apostrophe'])
