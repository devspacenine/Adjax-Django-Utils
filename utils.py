from django.template import loader, Context, RequestContext, TemplateSyntaxError
from django.template.loader_tags import ExtendsNode, BlockNode
from django.utils.hashcompat import sha_constructor
from django.conf import settings
from django.utils import simplejson
from django.http import HttpResponse
from django.shortcuts import render_to_response

import datetime, time, os, random, Image, ImageDraw, ImageFont, hashlib #@UnresolvedImport

SALT = settings.SECRET_KEY[:20]
encoder = simplejson.JSONEncoder()

def get_template(template):
    if isinstance(template, (tuple, list)):
        return loader.select_template(template)
    return loader.get_template(template)

class BlockNotFound(Exception):
    pass

def render_template_block(template, block, context):
    """
    Renders a single block from a template. This template should have previously been rendered.
    """
    return render_template_block_nodelist(template.nodelist, block, context)

def render_template_block_nodelist(nodelist, block, context):
    """
    Searches a template and any extended parent templates for a block with the given name and renders it.
    """
    for node in nodelist:
        if isinstance(node, BlockNode) and node.name == block:
            return node.render(context)
        for key in ('nodelist', 'nodelist_true', 'nodelist_false'):
            if hasattr(node, key):
                try:
                    return render_template_block_nodelist(getattr(node, key), block, context)
                except:
                    pass
    for node in nodelist:
        if isinstance(node, ExtendsNode):
            try:
                return render_template_block(node.get_parent(context), block, context)
            except BlockNotFound:
                pass
    raise BlockNotFound

def render_block_to_string(template_name, block, dictionary=None, context_instance=None):
    """
    Loads the given template_name and renders the given block with the given dictionary as
    context. Returns a string.
    """
    dictionary = dictionary or {}
    t = get_template(template_name)
    if context_instance:
        context_instance.update(dictionary)
    else:
        context_instance = Context(dictionary)
    t.render(context_instance)
    return render_template_block(t, block, context_instance)

def direct_block_to_template(request, template, block, extra_context=None, mimetype=None, **kwargs):
    """
    Render a given block in a given template with any extra URL parameters in the context as
    ``{{ params }}``.
    """
    if extra_context is None:
        extra_context = {}
    dictionary = {'params': kwargs}
    for key, value in extra_context.items():
        if callable(value):
            dictionary[key] = value()
        else:
            dictionary[key] = value
    c = RequestContext(request, dictionary)
    t = get_template(template)
    t.render(c)
    return HttpResponse(render_template_block(t, block, c), mimetype=mimetype)

def render_ajax_response(request, template_name, context=None):
    """
    If request is AJAX, loads the given template name and renders an ajax_block and/or ajax_script tag
    with a matching name in node_names to a response, using the given dictionary
    as context. The template_name may be a string to load a single template using
    get_template, or it may be a tuple to use select_template to find one of the
    templates in the list. Returns an HttpResponse with a MIME type "application/json" and JSON object.
    {"$-html":*, "$-styles":*, "$-canonical":*, "$-meta":*, "$-prescript":*, "$-postscript":*}.

    If request is not AJAX, renders the template with render_to_response.
    """

    if not request.is_ajax():
        return render_to_response(
            template_name,
            context,
            context_instance=RequestContext(request),
            mimetype = 'text/html'
        )

    nodeName = request.GET['node_name']
    context_instance = RequestContext(request)

    try:
        html = render_block_to_string(template_name, nodeName, context, context_instance)
    except BlockNotFound:
        html = ''

    try:
        css = render_block_to_string(template_name, "%s-styles" % nodeName, context, context_instance)
    except BlockNotFound:
        css = ''

    try:
        canonical = render_block_to_string(template_name, "%s-canonical" % nodeName, context, context_instance)
    except BlockNotFound:
        canonical = ''

    try:
        meta = render_block_to_string(template_name, "%s-meta" % nodeName, context, context_instance)
    except BlockNotFound:
        meta = ''

    try:
        preScript = render_block_to_string(template_name, "pre-%s" % nodeName, context, context_instance)
    except BlockNotFound:
        preScript = ''

    try:
        postScript = render_block_to_string(template_name, "post-%s" % nodeName, context, context_instance)
    except BlockNotFound:
        postScript = ''

    if html or css or canonical or meta or preScript or postScript:
        return HttpResponse(encoder.encode({"html":html,"css":css,"canonical":canonical,"meta":meta,"prescript":preScript,"postscript":postScript}), mimetype="application/json")
    raise TemplateSyntaxError('Could not find matching nodes')

def empty_response():
    return HttpResponse(encoder.encode({"html":'',"css":'',"canonical":'',"meta":'',"prescript":'',"postscript":''}), mimetype="application/json")

def generate_captcha(request, backgroungPath='img/bg.jpg', fontPath='img/captcha-font.ttf', tempPath='img/tmp/'):
    """
    Generates a captcha image for protection against bots
    """
    # create a 5 char random string and sha hash it, note no bit "i"
    imgtext = ''.join([random.choice('QWERTYUOPASDFGHJKLZXCVBNM') for i in range(5)])
    # create hash
    imghash = hashlib.sha1(SALT+imgtext).hexdigest()
    # create an image with the string
    im = Image.open(os.path.join(settings.STATIC_ROOT, backgroundPath)) #@UndefinedVariable
    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype(os.path.join(settings.STATIC_ROOT, fontPath), 30)
    draw.text((10,10), imgtext, font=font, fill=(80,80,80))
    # delete any old captcha images
    for tempFile in os.listdir(os.path.join(settings.MEDIA_ROOT, tempPath)):
        delta = time.time() - os.path.getmtime(os.path.join(settings.MEDIA_ROOT, tempPath, tempFile))
        if delta > 180 or delta < 0:
            os.remove(os.path.join(settings.MEDIA_ROOT, tempPath, tempFile))
    # save as a temporary image using the users IP address
    tempname = request.META['REMOTE_ADDR'] + str(datetime.datetime.now()) + '.jpg'
    temp = os.path.join(settings.MEDIA_ROOT, tempPath + tempname)
    im.save(temp, "JPEG")
    return (imghash, tempname)

def generate_sha1(string, salt=None):
    """
    Generates a 40 char sha1 hash for supplied string. Doesn't need to be very secure
    because it's not used for password checking. We got Django for that.

    :param string:
        The string that needs to be encrypted.

    :param salt:
        Optionally define your own salt. If none is supplied, will use a random
        string of 5 characters.

    :return: Tuple containing the salt and hash.

    """
    if not salt:
        salt = sha_constructor(str(random.random())).hexdigest()[:25]

    return sha_constructor(salt+str(string)).hexdigest()[:40]
