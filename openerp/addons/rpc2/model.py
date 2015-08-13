# -*- coding: utf-8 -*-
import itertools

import openerp.api
import openerp.exceptions

def dispatch(registry, uid, model, method, *args):
    if method.startswith('_'):
        raise openerp.exceptions.AccessError(
            "%s is a private method and can not be called over RPC" % method)

    subject, args, kwargs = itertools.islice(
        itertools.chain(args, [None], [None]),
        0, 3)
    ids = []
    context = {}
    # comes straight from xmlrpclib.loads, so should only be list or dict
    if type(subject) is list:
        ids = subject
    elif type(subject) is dict:
        ids = subject.get('records') or []
        context = subject.get('context') or {}
    elif subject:
        # other truthy subjects are errors
        raise ValueError("Unknown RPC subject %s, expected falsy value, list or dict" % subject)

    # optional args, kwargs
    if type(args) is dict:
        kwargs = args
        args = None

    if args is None: args = []
    if kwargs is None: kwargs = {}

    with registry.cursor() as cr:
        env = openerp.api.Environment(cr, uid, context or {})
        records = env[model].browse(ids or [])
        return getattr(records, method)(*args, **kwargs)
