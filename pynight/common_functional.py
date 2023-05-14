from .common_regex import rget


##
def fn_name(fn, ):
    ##
    # return rget(str(fn), r'^<function (\S+)')
    ##
    #: [[https://stackoverflow.com/questions/58108488/what-is-qualname-in-python][What is __qualname__ in python? - Stack Overflow]]
    return f"{fn.__module__}.{fn.__qualname__}"

    # return fn.__name__
    ##
##
