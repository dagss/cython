ctypedef int (*spamfunc)(int, char *) except 42
ctypedef int (*grailfunc)(int, char *)

cdef grailfunc grail
cdef spamfunc spam

grail = spam # type mismatch
spam = grail # type mismatch
_ERRORS = u"""
7:28: Cannot assign type 'spamfunc' to 'grailfunc'
8:28: Cannot assign type 'grailfunc' to 'spamfunc'
"""
