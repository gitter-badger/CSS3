from CSS3.completions import descriptors as d
from CSS3.completions import functions as f
from CSS3.completions import properties as p
from CSS3.completions import selectors as s
from CSS3.completions import types as t
import sublime
import sublime_plugin


class CSS3Completions(sublime_plugin.EventListener):

    def on_query_completions(self, view, prefix, locations):
        """Populate the completions menu based on the current cursor location.

        Args:
            view (sublime.View): A Sublime API object that contains the
                match_selector() method for detecting if the current scope has
                completions, and the substr() method for getting text from the
                document.
            prefix (str): The first part of the text that triggered the
                completions menu, e.g. "tex" for "text-decoration".
            locations (list: int): The integer positions of cursors.

        Returns:
            A list of (<label>, <completion>) tuples or None, and a flag that
            determines whether word completions are offered. <label> is what
            will appear in the completions menu. <completion> is the snippet
            that will be inserted.
        """
        if len(locations) > 1:
            # If there's multiple cursors, we can't offer completions.
            #     body {
            #         foo: |<- cursor
            #         bar: |<- second cursor
            #     }
            #
            # Which values do we offer? foo's or bar's?
            return [], sublime.INHIBIT_WORD_COMPLETIONS

        if view.match_selector(locations[0], "comment.block.css"):
            return []

        # The start position of the prefix determines which completions are
        # offered.
        #         |--prefix--|
        # start ->text-decorat|<- current cursor location
        start = locations[0] - len(prefix)
        current_scopes = get_current_scopes(view, start)

        # INSIDE FUNCTIONS
        if view.match_selector(start, "source.css meta.function"):
            return get_functions(current_scopes)

        # OUTSIDE AT-RULES
        if (
            view.match_selector(start, "source.css -meta.at-rule -meta.property-list.css") and
            view.match_selector(start - 1, "punctuation.definition.keyword.css")
        ):
            return s.at_rules, sublime.INHIBIT_WORD_COMPLETIONS

        # INSIDE AT-RULES
        if view.match_selector(start, "source.css meta.at-rule"):
            return handle_completions_inside_at_rules(view, start)

        # PROPERTY NAMES
        if property_name_scope(view, start):
            return p.names, sublime.INHIBIT_WORD_COMPLETIONS

        # PROPERTY VALUES
        if view.match_selector(start, "source.css meta.property-value-pair"):
            return get_property_values(current_scopes)

        # SELECTORS
        if view.match_selector(start, "meta.selector.css"):
            return handle_selector_completions(view, start)


def get_current_scopes(view, location):
    return view.scope_name(location).split()


def handle_selector_completions(view, location):
    if view.match_selector(location - 1, "punctuation.definition.entity.pseudo-element.css"):
        return s.pseudo_elements, sublime.INHIBIT_WORD_COMPLETIONS

    if view.match_selector(location - 1, "punctuation.definition.entity.pseudo-class.css"):
        return s.pseudo_classes, sublime.INHIBIT_WORD_COMPLETIONS

    # If we're not in a class, id, pseudo-class, or pseudo-element, offer HTML
    # tags as completions.
    if view.match_selector(location, "source.css -entity.other.attribute-name."):
        return s.html_tags


def handle_completions_inside_at_rules(view, location):
    current_scopes = get_current_scopes(view, location)

    if should_offer_at_rule_completions(view, location):
        return s.nestable_at_rules, sublime.INHIBIT_WORD_COMPLETIONS

    if view.match_selector(location, "meta.at-rule.keyframes.block.css -meta.keyframes-declaration-list.css"):
        # @keyframes selector
        return s.keyframes_selector, sublime.INHIBIT_WORD_COMPLETIONS

    if view.match_selector(location, "meta.at-rule.font-face.block.css"):
        # @font-face
        if view.match_selector(location, "source.css -meta.descriptor.font-face"):
            return d.font_face_descriptors, sublime.INHIBIT_WORD_COMPLETIONS
        return get_descriptors(current_scopes, descriptors_for="font-face")

    if view.match_selector(location, "meta.at-rule.font-feature-values.block.css"):
        # @font-feature-values
        if view.match_selector(location, "-meta.font-feature-type-block.css"):
            return s.font_feature_types, sublime.INHIBIT_WORD_COMPLETIONS
        return []

    if view.match_selector(location, "meta.at-rule.viewport.block.css"):
        # @viewport
        if view.match_selector(location, "source.css -meta.descriptor.viewport"):
            return d.viewport_descriptors, sublime.INHIBIT_WORD_COMPLETIONS
        return get_descriptors(current_scopes, descriptors_for="viewport")

    if view.match_selector(location, "meta.at-rule.page.block.css -meta.page-margin-box.css"):
        # @top-right, etc.
        return s.page_margin_boxes, sublime.INHIBIT_WORD_COMPLETIONS

    if view.match_selector(location, "meta.at-rule.page.css -meta.at-rule.page.block.css"):
        # @page :left, etc.
        return s.at_page_selectors

    if view.match_selector(location, "meta.at-rule.charset.css"):
        # @charset
        return [('"UTF-8";',)], sublime.INHIBIT_WORD_COMPLETIONS

    if view.match_selector(location, "meta.at-rule.counter-style.block.css"):
        # @counter-style
        if view.match_selector(location, "-meta.descriptor.counter-style"):
            return d.counter_style_descriptors, sublime.INHIBIT_WORD_COMPLETIONS
        return get_descriptors(current_scopes, descriptors_for="counter-style")

    if view.match_selector(location, "meta.at-rule.color-profile.block.css"):
        if view.match_selector(location, "-meta.descriptor.color-profile"):
            return d.color_profile_descriptors, sublime.INHIBIT_WORD_COMPLETIONS

        return get_descriptors(current_scopes, descriptors_for="color-profile")


scopes_that_forbid_nested_at_rules = (
    "meta.property-list.css, "
    "meta.at-rule.font-face.block.css, "
    "meta.at-rule.keyframes.block.css, "
    "meta.at-rule.font-feature-values.block.css, "
    "meta.at-rule.viewport.block.css, "
    "meta.at-rule.color-profile.block.css, "
    "meta.at-rule.counter-style.block.css, "
    "meta.at-rule.page.block.css"
)


def property_name_scope(view, location):
    """Return True if the given location has a scope that should offer property
    names as completions.

    When we're inside a property list or a page margin box, the
    meta.property-value-pair.css scope is triggered when the ':' is typed. If
    that scope is not present, the user is typing a property name, not a value.

    Args:
        view (sublime.View): required for the view.match_selector() method.
        location (int): cursor position in the text (determines current scope).
    """
    return (
        view.match_selector(location, "source.css meta.property-list.css -meta.property-value-pair") or
        view.match_selector(location, "source.css meta.page-margin-box.css -meta.property-value-pair")
    )


def should_offer_at_rule_completions(view, location):
    """Return True if the given location should offer @-rules as completions.

    @media and @supports can have @-rules nested inside them.

    Example:
        @media screen {
            @media (min-width: 480px) {
                ...
            }
        }

    For the other @-rules, however, nested @-rules don't make sense.

    Example:
        @media screen {
            @keyframes {
                @media???
            }
        }

    Args:
        view (sublime.View):
        location (int): the integer position of the

    This function returns True if we're in an @media or @supports scope, but NOT
    in any other scope.
    """
    if not view.match_selector(location, "meta.at-rule.media.block.css, meta.at-rule.supports.block.css"):
        return False

    return not view.match_selector(location, scopes_that_forbid_nested_at_rules)


def get_property_values(current_scopes):
    property_name = get_name(current_scopes, prefix="meta.property-value-pair.")
    completions = p.name_to_completions.get(property_name, []) + [t.var]
    if property_name and property_name in p.allow_word_completions:
        return completions

    return completions, sublime.INHIBIT_WORD_COMPLETIONS


def get_descriptors(current_scopes, descriptors_for):
    completions = []

    descriptor_name = get_name(current_scopes, prefix="meta.descriptor.{}".format(descriptors_for))

    # There is a separate completions dictionary for every @-rule.
    completions_dict = d.at_rule_to_completions_dict.get(descriptors_for, {})
    completions = completions_dict.get(descriptor_name, []) + [t.var]

    if descriptor_name and descriptor_name in f.allow_word_completions:
        return completions

    return completions, sublime.INHIBIT_WORD_COMPLETIONS


def get_functions(current_scopes):
    completions = []

    func_name = get_name(current_scopes, prefix="meta.function.")

    # Append the var() completion to every set of completions.
    completions = f.func_name_to_completions.get(func_name, []) + [t.var]

    if func_name and func_name in f.allow_word_completions:
        # If the function takes an identifier as an argument, the
        # identifier will be in the local symbol index. Therefore,
        # we don't want to inhibit word completions.
        return completions

    return completions, sublime.INHIBIT_WORD_COMPLETIONS


def get_name(scopes, prefix):
    """
    Scans a list of scopes and returns the name of the function or descriptor
    with the given prefix. If there are multiple matches, only the name from the
    highest-precedence (rightmost) scope will be returned. If there are no
    scopes with the given prefix, an empty string is returned.

    Args:
        scopes (list: str): e.g. ['source.css', 'foo.bar.baz.css']
        prefix (str): e.g. 'foo.bar'

    Returns:
        The

    >>> scopes = ['source.css', 'meta.function.foo.css']
    >>> get_name(scopes, prefix='meta.function')
    'foo'
    >>> scopes = ['source.css', 'meta.descriptor.color-profile.bar.css']
    >>> get_name(scopes, prefix='meta.descriptor.color-profile')
    'bar'
    >>> scopes = ['source.css', 'meta.function.baz.css']
    >>> get_name(scopes, prefix='meta.descriptor.color-profile')
    ''
    """
    name_index = -2
    for scope in reversed(scopes):
        if scope.startswith(prefix):
            # ['meta', 'function', 'foo', 'css'] -> 'foo'
            return scope.split(".")[name_index]

    return ""






    # PROPERTY NAME COMPLETIONS

    # PROPERTY VALUE COMPLETIONS

    # SELECTOR COMPLETIONS

    # PSEUDO-CLASS FUNCTION COMPLETIONS

    # PSEUDO-ELEMENT FUNCTION COMPLETIONS

    # FUNCTION COMPLETIONS

    # if view.match_selector(start, "meta.property-value"):
    #     # value completions
    #     # TODO: look up completions for the given property. get the
    #     # property name from the scope!
    #     region = view.line(point)
    #     line = view.substr(region).strip()
    #     matches = property_name_rx.search(line)
    #     if matches is not None:
    #         prop_name = matches.group("prop_name")
    #         if prop_name in properties.value_for_name:
    #             return properties.value_for_name[prop_name] + values.all_values, INHIBIT_BOTH

    #     return []

    # if view.match_selector(start, "meta.property-list.css"):
    #     # property names
    #     return properties.names, INHIBIT_BOTH
