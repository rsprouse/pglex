import os, re
import json
import logging
from elasticsearch import Elasticsearch, RequestsHttpConnection
import elasticsearch.exceptions as EE
from requests_aws4auth import AWS4Auth
from elasticsearch_dsl import Search, Q
from chalice import Chalice, Response, NotFoundError

app = Chalice(app_name='pglex')
app.debug = False
#app.log.setLevel(logging.DEBUG)

projects = {
    # Change 'mylang' to the name of your project. This name will become
    # part of your API URL. You can have multiple index definitions for
    # development. Each language project should include at least the
    # default index version '1'.
    'mylang': {
        '1': {
            'target_lang_search_fields': [],
            'contact_lang_search_fields': [],
            'boosts': {},
            'filter_fields': [],
            'source_fields': []
        }
    },
    # If you have multiple language projects, repeat this section for
    # each one.
    'anotherlang': {
        '1': {
            'target_lang_search_fields': [],
            'contact_lang_search_fields': [],
            'boosts': {},
            'filter_fields': [],
            'source_fields': []
        }
    }
}
all_projects = list(projects.keys())

target_lang_search_fields = [
    'lex.lo',   # lower case only
    'lex.lfwp',  # lower case icu folded with punctuation
    'lex.lfnp', # lower case icu folded with no punctuation
    'variants.lo',
    'variants.lfwp',
    'variants.lfnp',
    'ex_ol',
    'media_lex.lo',
    'media_lex.lfwp',
    'media_lex.lfnp',
    'morph_lex.lo',
    'morph_lex.lfwp',
    'morph_lex.lfnp',
    'deriv_lex.lo',
    'deriv_lex.lfwp',
    'deriv_lex.lfnp',
    'ur',
]

contact_lang_search_fields = [
    'defn',
    'gloss',
    'pos.lfnp',
    'note',
    'ref',
    'ex_cl',
    'litgloss',
    'sdomain.lfnp',
    'sciname',
    'usage_note',
]

# Default boost values per field.
boosts = {
    'lex.lo': '10',      # Boost matches on target language fields above
                         # contact language fields.
    'lex.lfwp': '6',
    'lex.lfnp': '3',
    'variants.lo': '10',
    'variants.lfwp': '6',
    'variants.lfnp': '3',
    'defn': '2',
    'gloss': '5',  # Gloss fields often have one or two words only, and it's
                   # likely that if you matched on of those words in the field
                   # that it's what you want at or near the top of your
                   # results, so a robust boost is called for.
    'pos.lfnp': '5',
    'sdomain.lfnp': '5'
}

filter_fields = [
    'id',
    'pos',
    'sdomain',
    'has_media',
    'is_morph',
]

# Fields to return in a query result.
source_fields = {
    'include': [
        'id', 'has_media', 'popcnt', 'is_morph', 'Date',
        'lex', 'defn', 'pos', 'gloss', 'ref', 'litgloss',
        'note', 'variants', 'sdomain', 'usage', 'ur', 'sciname',
        'ex_ol', 'ex_cl', 'ex', 'media', 'derivs', 'morphemes',
        'ImmediateConstituents',
        'Example_rf', 'PrintDictGramNote',
    ],
    'exclude': ['']
}

# Valid values for filter_fields query parameters.
filt_pat = re.compile('^\w+$')

# TODO: see if we can/should restrict access-control-allow-origin
headers={'Content-Type': 'application/json; charset=utf-8'}

# HTTP response codes.
HTTPSUCCESS = 200
HTTPNOTFOUND = 404
HTTPSERVERERROR = 500

def get_es_client():
    access_key_id = os.environ.get('aws_access_key_id')
    secret_access_key = os.environ.get('aws_secret_access_key')
    region = os.environ.get('aws_region')
    es_endpoint = os.environ.get('es_endpoint')
    service = 'es'  # elasticsearch
    
    awsauth = AWS4Auth(access_key_id, secret_access_key, region, service)
    es = Elasticsearch(
        hosts = [{'host': es_endpoint, 'port': 443}],
        http_auth = awsauth,
        use_ssl = True,
        verify_certs = True,
        connection_class = RequestsHttpConnection
    )
    return es

def get_CORS_domain():
    '''Return the CORS domain, depending on app stage. The values are
configured in chalice's config.json file.'''
    try:
        if app.current_request.headers['origin'].startswith('http://localhost') or \
           app.current_request.headers['origin'].startswith('https://localhost'):
            return 'http://localhost'
    except:
        pass
    return os.environ.get('cors_domain')

def get_header():
    '''Return the header dict to be used in Response.'''
    h = headers
    h['Access-Control-Allow-Origin'] = get_CORS_domain()
    h['Vary'] = 'Origin'   # to be used with Access-Control-Allow-Origin
    return h

class LexEsSearch(object):
    '''Search class for pglex app.'''
    def __init__(self, query={}, project=None, index_ver=None, using=None):
        index = 'lex_{:}_{:}-lex'.format(project, index_ver)
        self.s = Search(using=using, index=index)
        self.project = project
        self.index_ver = index_ver
        self.query = query
        self.results = {}
        self.explain = (
            'explain' in list(query.keys()) and query['explain'] == 'true'
        )
        self.includes_q = 'q' in list(query.keys())

    def build_search(self):
        if self.includes_q:
            self.add_q()
        self.add_filters()
        self.add_popularity()
        self.add_paging()
        self.add_sort()
        self.add_includes()
        self.add_explain()

    def add_q(self):
        '''String-based query with results returned by relevance.'''
        q = self.query['q']
        wildcarding = '*' in q or '?' in q
        if wildcarding is True:
            add_contact_lg = False
        else:
            add_contact_lg = True
        my_search_fields = get_search_fields(
            self.project, self.index_ver, self.query,
            add_target_lang=True, add_contact_lang=add_contact_lg
        )
        myboosts = boosts
        sfields = []
        for searchfield in my_search_fields:
            try:
                sfield, boost = searchfield.split('^')
            except ValueError:  # No '^' in string
                sfield = searchfield
                try:
                    boost = myboosts[sfield]
                except KeyError:
                    boost = '1'
            if not wildcarding:
                sfield += '^' + boost
            else:
                sfield = sfield.replace('.', '__')
                sfield = {sfield: {'value': q.lower(), 'boost': boost}}
            sfields.append(sfield)
        if wildcarding is True:
            queries = []
            for sfield in sfields:
                queries.append(Q("wildcard", **sfield))
            boolquery = Q(
                'bool',
                should=queries,
                minimum_should_match=1
            )
            self.s = self.s.query(boolquery)
        else:
            self.s = self.s.query('multi_match', query=q, fields=sfields)

    def add_filters(self):
        '''Filter queries that entries must match, e.g. part of speech.'''
        for filt in filter_fields:
            try:
                p = self.query[filt]
                # If filter came in as a query (url) param.
                #if type(p) == str and filt_pat.match(p):
                #    p = {filt: p}
                #    app.log.debug('jsonp: ' + p)
                if isinstance(p, list):
                    termtype = 'terms'
                #    pstr = ','.join(p)
                else:
                    termtype = 'term'
                #    pstr = p
                #app.log.debug('termtype: ' + termtype + '; filtp: ' + filt + ' -> ' + pstr)
                self.s = self.s.filter(termtype, **{filt: p})
            except KeyError:
                pass   # filter not included in query

    def add_popularity(self):
        '''Scale scores by a 'popularity' factor calculated from popcnt field
        or a random function. A random seed can be provided if a reproducible
        random sort is required. If paging through a randomized set of results,
        for example, then use the same seed when retrieving each page set.

        If no string search is in the query (i.e. only filters are used), then
        the _score values will be 0.0, in which case multiplying by the factor
        will have no effect, so the factor value replaces _score instead.
        This means documents will be scored based only on the popularity
        factor.'''
        if self.includes_q:
            mode = 'multiply'
        else:
            mode = 'replace'
        try:
            if self.query['pf'] == 'rand':
                try:
                    randarg = {'seed': self.query['seed'], 'field': '_seq_no'}
                except KeyError:
                    randarg = {}
                freqq = Q(
                    'function_score',
                    query=self.s.query,
                    random_score=randarg,
                    boost_mode=mode
                )
                self.s = self.s.query(freqq)
            elif self.query['pf'] != '0':
                freqq = Q(
                    'function_score',
                    query=self.s.query,
                    field_value_factor={
                        'field': 'popcnt',
                        'modifier': 'ln1p',
                        'factor': int(self.query['pf']),
                        'missing': 1
                    },
                    boost_mode=mode
                )
                self.s = self.s.query(freqq)
        except KeyError:
            pass

    def add_paging(self):
        '''Return a page of results. The default is the first 10 entries.'''
        try:
            size = int(self.query['size'])
        except KeyError:
            size = 10
        try:
            getfrom = int(self.query['from'])
        except KeyError:
            getfrom = 0
        self.s = self.s[getfrom:getfrom+size]

    def add_sort(self):
        sortfld = '_score'
        sortparams = {'order': 'desc'}
        try:
            keys = list(self.query.keys())
            assert('sort' in keys or 'order' in keys or 'sortmode' in keys)
            if 'sort' in keys:
                sortfld = self.query['sort']
            if 'order' in keys:
                sortparams['order'] = self.query['order']
            else:
                if sortfld == '_score':
                    sortparams['order'] = 'desc'
                else:
                    sortparams['order'] = 'asc'
            if 'sortmode' in keys:
                sortparams['mode'] = self.query['sortmode']
        except AssertionError:
            pass
        self.s = self.s.sort({sortfld: sortparams})

    def add_includes(self):
        try:
            inc_fields = self.query['inc'].split(',')
            self.s = self.s.source({'include': inc_fields})
        except KeyError:
            self.s = self.s.source(source_fields)

    def add_explain(self):
        if self.explain is True:
            self.s = self.s.extra(explain=True)

def get_query(app):
    '''Get query parameters from POST or GET.'''
    try:
        print(app.current_request.raw_body)
        query = json.loads(app.current_request.raw_body)
    except json.decoder.JSONDecodeError:
        query = app.current_request.query_params
    if 'explain' not in list(query.keys()):
        query['explain'] = 'false'
    return query

def get_search_fields(project, index_ver, query,
        add_target_lang, add_contact_lang):
    '''Return list of multi_match fields based on defaults, project additions,
and query params.
'''
    my_search_fields = []
    if add_target_lang is True:
        my_search_fields += target_lang_search_fields.copy()
        my_search_fields += \
            projects[project][index_ver]['target_lang_search_fields']
    if add_contact_lang is True:
        my_search_fields += contact_lang_search_fields.copy()
        my_search_fields += \
            projects[project][index_ver]['contact_lang_search_fields']
    if index_ver == 'dev' and index_ver not in list(projects[project].keys()):
        index_ver = '1'
    try:
        my_search_fields = query['flds'].split(',')
    except KeyError:
        pass
    return my_search_fields

def get_source_fields(project, index_ver):
    my_source_fields = source_fields.copy()
    if index_ver == 'dev' and index_ver not in list(projects[project].keys()):
        index_ver = '1'
    return my_search_fields + projects[project][index_ver]['source_fields']

def explain_query(project, index_ver, lexid, app):
    assert(project in all_projects)
    assert(index_ver == 'dev' or index_ver == str(int(index_ver)))
    query = get_query(app)
    es = get_es_client()
    index = 'lex_{:}_{:}-lex'.format(project, index_ver)
    try:
        s = es.explain(
            index=index, doc_type='lex', id=lexid,
            body={"query": {"match": { query['fld']: query['q'] }}}
        )
        body = json.dumps(s)
        status_code = HTTPSUCCESS
    except Exception:
        body = '{}'
        status_code = HTTPNOTFOUND
    return Response(
        body=body,
        status_code=status_code,
        headers=get_header()
    )

def do_query(project, index_ver, app):
    assert(project in all_projects)
    assert(index_ver == 'dev' or index_ver == str(int(index_ver)))
    results = {}
    query = get_query(app)
    es = get_es_client()

    les = LexEsSearch(
        using=es,
        project=project,
        index_ver=index_ver,
        query=query,
    )
    les.build_search()
    if les.explain is True:
        results['query'] = les.query
        results['search'] = les.s.to_dict()

    try:
        r = les.s.execute()
        if r.hits.total >= 1:
            results.update(r.to_dict()['hits'])
        elif r.hits.total == 0:
            results.update({'hits': []})
        status_code = HTTPSUCCESS
    except Exception as e:
        results.update({'hits': [], 'error': repr(e)})
        status_code = HTTPSERVERERROR
    return Response(
        body=results,
        status_code=status_code,
        headers=get_header()
    )

def do_lex(project, index_ver, lexid):
    assert(project in all_projects)
    assert(index_ver == 'dev' or index_ver == str(int(index_ver)))
    results = {}
    es = get_es_client()
    les = LexEsSearch(
        using=es,
        project=project,
        index_ver=index_ver
    )
    try:
        termtype = 'term'
        if lexid is None:
            query = get_query(app)
            # Ensure lexid is a string, not int.
            lexid = [str(lxid) for lxid in query['lexid']]
            if not isinstance(lexid, str):  # Should be a list.
                termtype = 'terms'
        les.s = les.s.filter(termtype, id=lexid)
        r = les.s.execute()
        app.log.debug(r.hits.total)
        if r.hits.total > 0:
            hits = r.to_dict()['hits']
            hits['hits'] = {lex['_id']: lex['_source'] for lex in hits['hits']}
            results.update(hits)
        elif r.hits.total == 0:
            results.update({'hits': []})
        status_code = HTTPSUCCESS
    except Exception as e:
        app.log.debug(str(e))
        body = '{}'
        status_code = HTTPNOTFOUND
    return Response(
        body=results,
        status_code=status_code,
        headers=get_header()
    )

@app.route('/{project}/{index_ver}/q',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
@app.route('/{project}/q',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def q(project, index_ver='1'):
    return do_query(project, index_ver, app)

@app.route('/{project}/{index_ver}/lex/{lexid}', methods=['GET', 'POST'], content_types=['application/json', 'application/x-www-form-urlencoded'])
@app.route('/{project}/lex/{lexid}', methods=['GET', 'POST'], content_types=['application/json', 'application/x-www-form-urlencoded'])
@app.route('/{project}/{index_ver}/lex', methods=['GET', 'POST'], content_types=['application/json', 'application/x-www-form-urlencoded'])
@app.route('/{project}/lex', methods=['GET', 'POST'], content_types=['application/json', 'application/x-www-form-urlencoded'])
def lex(project, lexid=None, index_ver='1'):
    return do_lex(project, index_ver, lexid)

# Explain query match with particular lex.
@app.route('/{project}/{index_ver}/eq/{lexid}',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
@app.route('/{project}/explain/{lexid}',
    methods=['GET', 'POST'],
    content_types=['application/json', 'application/x-www-form-urlencoded']
)
def explain(project, lexid, index_ver='1'):
    return explain_query(project, index_ver, lexid, app)

@app.route('/testperms')
def testperms(myparam='default'):
    es = get_es_client()
    try:
        r = es.search('karuk1-bndl')
        status_code = HTTPSUCCESS
        body = r
    except EE.NotFoundError as e:
        body = e.error
        status_code = e.status_code
    except EE.TransportError as e:
        body = e.error
        status_code = e.status_code
    return Response(
        body=body,
        status_code=status_code,
        headers=get_header()
    )

