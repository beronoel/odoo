# -*- coding: utf-8 -*-
import base64
import collections
import logging
import threading
import types
import xmlrpclib
from datetime import datetime

import werkzeug.exceptions
import werkzeug.wrappers
from lxml import etree
from lxml.builder import E

import openerp.modules.registry
from openerp import http, models, service
from openerp.exceptions import AccessDenied
from openerp.service import security

from . import global_, database, model

logger = logging.getLogger(__name__)


class Rpc2(http.Controller):
    @http.route('/RPC2/', auth='none', methods=['POST'])
    def rpc2(self, db=None):
        req = http.request.httprequest
        if req.mimetype != 'text/xml':
            return werkzeug.exceptions.UnsupportedMediaType(
                "XML-RPC only allows text/xml request types, got %s" % req.mimetype)

        params, method = xmlrpclib.loads(req.stream.read())

        try:
            result = self.dispatch(db, method, params)
        except Exception, e:
            response = service.wsgi_server.xmlrpc_convert_exception_int(e)
        else:
            if result is None:
                logger.warn(
                    "Method %s returned `None`, converting to `False`", method)
                result = False

            response = (
                "<?xml version='1.0'?>\n"
                "<methodResponse>\n%s</methodResponse>\n" %
                    RecordMarshaller('utf-8', allow_none=False).dumps((result,))
            )

        return werkzeug.wrappers.Response(response, mimetype='text/xml' )

    def dispatch(self, db, method, params):
        if method.startswith('system'):
            raise NameError("System methods not supported")
        # FIXME: introspection ("system") methods
        #   - system.listMethods()
        #   - system.methodHelp(method)
        #   - system.methodSignature(method)
        #   - system.multicall(callspecs)

        path = method.split('.')
        if not db:
            if len(path) != 1:
                raise NameError("{} is not a valid global method".format(method))
            [func] = path
            return global_.dispatch(func, *params)

        authorization = http.request.httprequest.authorization
        uid = security.login(db, authorization.username, authorization.password)
        if not uid:
            raise AccessDenied()

        threading.current_thread().uid = uid
        threading.current_thread().dbname = db

        openerp.modules.registry.RegistryManager.check_registry_signaling(db)
        registry = openerp.registry(db)
        try:
            if len(path) == 1:
                [func] = path
                return database.dispatch(registry, uid, func, *params)
            else:
                model_name, func = method.rsplit('.', 1)
                return model.dispatch(registry, uid, model_name, func, *params)
        finally:
            openerp.modules.registry.RegistryManager.signal_caches_change(db)

class Dispatcher(object):
    """ Dispatches values to instance methods based on value types

    >>> class A(object):
    ...     dispatcher = Dispatcher()
    ...     @dispatcher.register(int)
    ...     def _int(self, value):
    ...         return "int {}".format(value)
    ...     @dispatcher.register(float)
    ...     def _float(self, value):
    ...         return "float {}".format(value)
    >>> a = A()
    >>> a.dispatcher(1)
    'int 1'
    >>> a.dispatcher(1.)
    'float 1.0'
    """
    def __init__(self):
        self.types = []
        self.default = None

    def register(self, types):
        def decorator(fn):
            self.types.append((types, fn))
            return fn
        return decorator
    def register_default(self, default):
        self.default = default

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return Proxy(self, instance)

class RecordMarshaller(object):
    serialize = Dispatcher()
    def __init__(self, encoding='utf-8', allow_none=False):
        self.encoding = encoding
        self.allow_none = allow_none
        self.memo = set()
    def dumps(self, values):
        if isinstance(values, xmlrpclib.Fault):
            tree = E.fault(self.serialize({
                'faultCode': values.faultCode,
                'faultString': values.faultString,
            }))
        else:
            tree = E.params()
            tree.extend(E.param(self.serialize(value)) for value in values)
        return etree.tostring(tree, encoding=self.encoding, xml_declaration=False)

    @serialize.register(models.BaseModel)
    def dump_model(self, value):
        return self.serialize(value.ids)

    @serialize.register(types.NoneType)
    def dump_none(self, value):
        if self.allow_none:
            return E.nil()
        raise TypeError("cannot marshal None unless allow_none is enabled")

    @serialize.register(bool)
    def dump_bool(self, value):
        return E.value(E.boolean("1" if value else "0"))

    @serialize.register((int, long))
    def dump_int(self, value):
        if value > xmlrpclib.MAXINT or value < xmlrpclib.MININT:
            raise OverflowError("int exceeds XML-RPC limits")
        return E.value(E.int(str(value)))

    @serialize.register(float)
    def dump_float(self, value):
        return E.value(E.double(repr(value)))

    @serialize.register(basestring)
    def dump_str(self, value):
        return E.value(E.string(value))

    @serialize.register(collections.Mapping)
    def dump_mapping(self, value):
        m = id(value)
        if m in self.memo:
            raise TypeError("cannot marshal recursive dictionaries")
        self.memo.add(m)
        struct = E.struct()
        struct.extend(
            # coerce all keys to string (same as JSON)
            E.member(E.name(unicode(k)), self.serialize(v))
            for k, v in value.iteritems()
        )
        self.memo.remove(m)
        return E.value(struct)

    @serialize.register(collections.Iterable)
    def dump_iterable(self, value):
        m = id(value)
        if m in self.memo:
            raise TypeError("cannot marshal recursive sequences")
        self.memo.add(m)
        data = E.data()
        data.extend(self.serialize(v) for v in value)
        self.memo.remove(m)
        return E.value(E.array(data))

    @serialize.register(datetime)
    def dump_datetime(self, value):
        d = etree.Element('datetime.iso8601')
        d.text = value.replace(microsecond=0).isoformat()
        return E.value(d)

    @serialize.register(xmlrpclib.Binary)
    def dump_binary(self, value):
        return E.value(E.base64(base64.encodestring(value.data)))

    @serialize.register_default
    def fallback(self, value):
        return self.serialize(vars(value))


class Proxy(object):
    def __init__(self, dispatcher, instance):
        self.dispatcher = dispatcher
        self.instance = instance
    def __call__(self, item):
        for types, fn in self.dispatcher.types:
            if isinstance(item, types):
                return fn(self.instance, item)
        return self.dispatcher.default(self.instance, item)
