"""Small Ren'Py runtime adapter. Never inspect game objects in screens."""


from .compat import string_types, integer_types


def collect_context(renpy, config):
    """Best-effort current statement and return-stack metadata.

    This is not a debugger: get_return_stack contains return destinations,
    not the current label or a Python stack trace.
    """
    result = {}
    name = getattr(config, 'name', None)
    if isinstance(name, string_types):
        result['game'] = name
    version = getattr(renpy, 'version_string', None)
    if isinstance(version, string_types):
        result['version'] = version
    try:
        filename, line = renpy.get_filename_line()
        if isinstance(filename, string_types):
            result['filename'] = filename
        if type(line) in integer_types:
            result['line'] = line
    except Exception:
        pass
    try:
        stack = renpy.get_return_stack()
        if isinstance(stack, (tuple, list)):
            result['return_depth'] = len(stack)
            labels = [frame for frame in stack if isinstance(frame, string_types)]
            result['return_labels'] = ', '.join(labels[-4:]) if labels else '(none available)'
    except Exception:
        pass
    try:
        # Public engine indicator, sampled only. False does not establish
        # that no rollback took place between inspector snapshots.
        rolling = renpy.in_rollback()
        if type(rolling) is bool:
            result['rollback_active'] = rolling
    except Exception:
        pass
    return result
