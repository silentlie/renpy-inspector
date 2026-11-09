"""Small Ren'Py runtime adapter. Never inspect game objects in screens."""


def collect_context(renpy, config):
    """Best-effort current statement and return-stack metadata.

    This is not a debugger: get_return_stack contains return destinations,
    not the current label or a Python stack trace.
    """
    result = {}
    name = getattr(config, 'name', None)
    if type(name) is str:
        result['game'] = name
    version = getattr(renpy, 'version_string', None)
    if type(version) is str:
        result['version'] = version
    try:
        filename, line = renpy.get_filename_line()
        if type(filename) is str:
            result['filename'] = filename
        if type(line) is int:
            result['line'] = line
    except Exception:
        pass
    try:
        stack = renpy.get_return_stack()
        if isinstance(stack, (tuple, list)):
            result['return_depth'] = len(stack)
            labels = [frame for frame in stack if type(frame) is str]
            result['return_labels'] = ', '.join(labels[-4:]) if labels else '(none available)'
    except Exception:
        pass
    return result
