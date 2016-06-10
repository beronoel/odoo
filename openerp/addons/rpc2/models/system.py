# -*- coding: utf-8 -*-

import itertools
import xmlrpclib

from odoo import models, exceptions, service

from ..model import dispatch, extract_call_info


class RpcSystem(models.AbstractModel):
    _name = 'system'

    def listMethods(self):
        """
        This method returns a list of the methods the server has, by name.

        Only returns model methods, neither db-bound nor global methods are
        listed.
        """
        # TODO: remove BaseModel methods as they're going to be present in every model returned?
        return [
            "%s.%s" % (modelName, attrName)
            for modelName, Model in self.env.iteritems()
            for attrName, attr in vars(Model).iteritems()
            if not attrName.startswith('_')
            if callable(attr)
        ]

    def methodHelp(self, method_name):
        """
        Returns the method's docstring.

        Ignores db-bound and global methods.
        """
        model, method = method_name.rsplit('.', 1)
        if method.startswith('_'):
            raise exceptions.AccessError(
                "%s is a private method and can not be called over RPC" % method)

        m = getattr(self.env[model], method)
        # The server may give as much or as little detail as it wants,
        # including an empty string.
        return m.__doc__ or ""

    # methodSignature is useless here

    def multicall(self, callspecs):
        """
        Performs multiple *independent* method calls within a single RPC call.

        The "parent" context (context of the multicall) is merged into the
        context of each call's subject, if any.

        Callspecs are of the form ``{'methodName': string, 'params': [subject[, args][, kwargs]]}``.

        The result is an array of either call results wrapped in a
        single-element array or RPC error specs.
        """
        results = []
        for callspec in callspecs:
            model, method = callspec['methodName'].rsplit('.', 1)
            # dispatch creates a new cursor and automatically
            # commits/rollbacks internally, so calls are properly sequential
            # and independent
            try:
                result = dispatch(self.env.registry, self.env.uid, model, method, *callspec['params'])
            except NameError, e:
                results.append({
                    'faultCode': xmlrpclib.METHOD_NOT_FOUND,
                    'faultString': str(e),
                })
            except xmlrpclib.Fault, f:
                results.append({
                    'faultCode': f.faultCode,
                    'faultString': f.faultString,
                })
            except Exception, e:
                xmlrpcified = service.wsgi_server.xmlrpc_convert_exception_int(e)
                results.append({
                    'faultCode': xmlrpcified.faultCode,
                    'faultString': xmlrpcified.faultString,
                })
            else:
                results.append([result])
        return results

    def pipeline(self, firstCall, pipeline):
        """ Applies a sequence of method calls to a base subject.

        If one step of the pipeline returns a recordset, the next step will
        apply to that, otherwise the previous step's recordset will be reused.

        pipeline callspecs are of the form::

            {'methodName': string, 'params': [[args][, kwargs]]}

        where ``method`` is a dotless actual method name rather than fully
        decorated with the model name.

        The first call is of the same form as ``multicall``'s callspec, and
        its methodName must similarly be fully decorated.

        The result is the final return value of the entire pipeline.
        """

        model, method = firstCall['methodName'].rsplit('.', 1)
        ids, context, args, kwargs = extract_call_info(method, firstCall['params'])

        records = result = getattr(
            self.env(context=context)[model].browse(ids),
            method
        )(*args, **kwargs)

        for spec in pipeline:
            method = spec['methodName']
            if method.startswith('_'):
                raise exceptions.AccessError(
                    "%s is a private method and can not be called over RPC" % method)

            args, kwargs = itertools.islice(
                itertools.chain(spec['params'], [None, None]),
                0, 2
            )
            if type(args) is dict:
                kwargs = args
                args = None
            if args is None: args = []
            if kwargs is None: kwargs = {}

            result = getattr(records, method)(*args, **kwargs)
            # TODO: check for uid change?
            if isinstance(result, models.BaseModel):
                records = result

        return result

# TODO: rpc. namespace for JSON-RPC introspection
