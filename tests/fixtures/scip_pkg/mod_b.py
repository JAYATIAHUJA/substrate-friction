from mod_a import Child, lower


def run(n):
    return Child().greet() + str(lower(n))
