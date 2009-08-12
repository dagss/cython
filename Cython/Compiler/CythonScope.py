from Symtab import ModuleScope
from PyrexTypes import *
from UtilityCode import CythonUtilityCode
from Errors import error
from Scanning import StringSourceDescriptor
import Options
import Buffer

class CythonScope(ModuleScope):
    def __init__(self):
        ModuleScope.__init__(self, u'cython', None, None, no_outer_scope=True)
        self.pxd_file_loaded = True
        self.populate_cython_scope()
        
    def lookup_type(self, name):
        # This function should go away when types are all first-level objects. 
        type = parse_basic_type(name)
        if type:
            return type

    def find_module(self, module_name, pos):
        error("cython.%s is not available" % module_name, pos)

    def find_submodule(self, module_name):
        entry = self.entries.get(module_name, None)
        if entry and entry.as_module:
            return entry.as_module
        else:
            # TODO: fix find_submodule control flow so that we're not
            # expected to create a submodule here (to protect CythonScope's
            # possible immutability). Hack ourselves out of the situation
            # for now.
            raise error((StringSourceDescriptor(u"cython", u""), 0, 0),
                  "cython.%s is not available" % module_name)

    def populate_cython_scope(self):
        # These are used to optimize isinstance in FinalOptimizePhase
        type_object = self.declare_typedef(
            'PyTypeObject', 
            base_type = c_void_type, 
            pos = None,
            cname = 'PyTypeObject')
        type_object.is_void = True
        
        self.declare_cfunction(
            'PyObject_TypeCheck',
            CFuncType(c_bint_type, [CFuncTypeArg("o", py_object_type, None),
                                    CFuncTypeArg("t", c_ptr_type(type_object), None)]),
            pos = None,
            defining = 1,
            cname = 'PyObject_TypeCheck')

        # A special function just to make it easy to test the scope and
        # utility code functionality in isolation. It is available to
        # "end-users" but nobody will know it is there anyway...
        entry = self.declare_cfunction(
            '_testscope',
            CFuncType(py_object_type, [CFuncTypeArg("value", c_int_type, None)]),
            pos=None,
            defining=1,
            cname='__pyx_cython__testscope'
        )
        entry.utility_code_definition = cython_testscope_utility_code

        #
        # The view sub-scope
        #
        self.viewscope = viewscope = ModuleScope(u'view', self, None, no_outer_scope=True)
        self.declare_module('view', viewscope, None)
        viewscope.pxd_file_loaded = True
        entry = viewscope.declare_cfunction(
            '_testscope',
            CFuncType(py_object_type, [CFuncTypeArg("value", c_int_type, None)]),
            pos=None,
            defining=1,
            cname='__pyx_cython_view__testscope'
        )
        entry.utility_code_definition = cythonview_testscope_utility_code
        

        for x in ('strided', 'contig', 'follow', 'direct', 'ptr', 'full'):
            entry = viewscope.declare_var(x, py_object_type, None,
                                          cname='__pyx_viewaxis_%s' % x,
                                          is_cdef=True)
            entry.utility_code_definition = view_utility_code

        #
        # cython.view.memoryview declaration
        #
        self.memviewentry = entry = viewscope.declare_c_class(memview_name, None,
                implementing=1,
                objstruct_cname = memview_objstruct_cname,
                typeobj_cname = memview_typeobj_cname,
                typeptr_cname= memview_typeptr_cname)

        entry.utility_code_definition = view_utility_code

        #
        # cython.array declaration
        #
        name = u'array'
        entry = self.declare_c_class(name, None,
                implementing=1,
                objstruct_cname='__pyx_obj_array',
                typeobj_cname='__pyx_tobj_array',
                typeptr_cname=Naming.typeptr_prefix+name)

        # NOTE: the typeptr_cname is constrained to be '__pyx_ptype_<name>'
        # (name is 'array' in this case).  otherwise the code generation for
        # the struct pointers will not work!

        entry.utility_code_definition = cython_array_utility_code

        arr_scope = entry.type.scope

        arr_scope.declare_var(u'data', c_char_ptr_type, None, is_cdef = 1)
        arr_scope.declare_var(u'len', c_size_t_type, None, is_cdef = 1)
        arr_scope.declare_var(u'format', c_char_ptr_type, None, is_cdef = 1)
        arr_scope.declare_var(u'ndim', c_int_type, None, is_cdef = 1)
        arr_scope.declare_var(u'shape', c_py_ssize_t_ptr_type, None, is_cdef = 1)
        arr_scope.declare_var(u'strides', c_py_ssize_t_ptr_type, None, is_cdef = 1)
        arr_scope.declare_var(u'itemsize', c_py_ssize_t_type, None, is_cdef = 1)

        # declare the __getbuffer__ & __releasebuffer__ functions

        for name in ('__getbuffer__', '__releasebuffer__'):
            entry = arr_scope.declare_pyfunction(name, None)
            # FIXME XXX: hack right here!!!
            entry.func_cname = '__pyx_pf_9__pyxutil_5array_' + name
            entry.utility_code_definition = cython_array_utility_code

        #
        # Declare the array modes
        #
        entry = self.declare_var(u'PyBUF_C_CONTIGUOUS', c_int_type, None,
                cname='PyBUF_C_CONTIGUOUS',is_cdef = 1)
        entry = self.declare_var(u'PyBUF_F_CONTIGUOUS', c_int_type, None,
                is_cdef = 1)
        entry = self.declare_var(u'PyBUF_ANY_CONTIGUOUS', c_int_type, None,
                is_cdef = 1)

def create_cython_scope(context):
    # One could in fact probably make it a singleton,
    # but not sure yet whether any code mutates it (which would kill reusing
    # it across different contexts)
    return CythonScope()

cython_testscope_utility_code = CythonUtilityCode(u"""
cdef object _testscope(int value):
    return "hello from cython scope, value=%d" % value
""", name="cython utility code", prefix="__pyx_cython_")

cythonview_testscope_utility_code = CythonUtilityCode(u"""
cdef object _testscope(int value):
    return "hello from cython.view scope, value=%d" % value
""", name="cython utility code", prefix="__pyx_cython_view_")

memview_name = u'memoryview'
memview_typeptr_cname = Naming.typeptr_prefix+memview_name
memview_typeobj_cname = '__pyx_tobj_'+memview_name
memview_objstruct_cname = '__pyx_obj_'+memview_name
view_utility_code = CythonUtilityCode(
u"""
cdef class Enum(object):
    cdef object name
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return self.name

cdef strided = Enum("<strided axis packing mode>")
cdef contig = Enum("<contig axis packing mode>")
cdef follow = Enum("<follow axis packing mode>")
cdef direct = Enum("<direct axis access mode>")
cdef ptr = Enum("<ptr axis access mode>")
cdef full = Enum("<full axis access mode>")

cdef extern from *:
    int __Pyx_GetBuffer(object, Py_buffer *, int)
    void __Pyx_ReleaseBuffer(Py_buffer *)

cdef class memoryview(object):

    cdef object obj
    cdef Py_buffer view
    cdef int gotbuf_flag

    def __cinit__(memoryview self, object obj, int flags):
        self.obj = obj
        __Pyx_GetBuffer(self.obj, &self.view, flags)

    def __dealloc__(memoryview self):
        self.obj = None
        __Pyx_ReleaseBuffer(&self.view)

cdef memoryview memoryview_cwrapper(object o, int flags):
    return memoryview(o, flags)
""", name="view_code",
    prefix="__pyx_viewaxis_",
    requires=(Buffer.GetAndReleaseBufferUtilityCode(),))

cyarray_prefix = u'__pyx_cythonarray_'
cython_array_utility_code = CythonUtilityCode(u'''
cdef extern from "stdlib.h":
    void *malloc(size_t)
    void free(void *)

cdef extern from "Python.h":

    cdef enum:
        PyBUF_C_CONTIGUOUS,
        PyBUF_F_CONTIGUOUS,
        PyBUF_ANY_CONTIGUOUS

cdef class array:

    cdef:
        char *data
        Py_ssize_t len
        char *format
        int ndim
        Py_ssize_t *shape
        Py_ssize_t *strides
        Py_ssize_t itemsize
        str mode

    def __cinit__(array self, tuple shape, Py_ssize_t itemsize, char *format, mode="c"):

        self.ndim = len(shape)
        self.itemsize = itemsize

        if not self.ndim:
            raise ValueError("Empty shape tuple for cython.array")
        
        if self.itemsize <= 0:
            raise ValueError("itemsize <= 0 for cython.array")

        self.format = format
        
        self.shape = <Py_ssize_t *>malloc(sizeof(Py_ssize_t)*self.ndim)
        self.strides = <Py_ssize_t *>malloc(sizeof(Py_ssize_t)*self.ndim)

        if not self.shape or not self.strides:
            raise MemoryError("unable to allocate shape or strides.")

        cdef int idx
        cdef Py_ssize_t int_dim, stride
        idx = 0
        for dim in shape:
            int_dim = <Py_ssize_t>dim
            if int_dim <= 0:
                raise ValueError("Invalid shape.")
            self.shape[idx] = int_dim
            idx += 1
        assert idx == self.ndim

        if mode == "fortran":
            idx = 0; stride = 1
            for dim in shape:
                self.strides[idx] = stride*itemsize
                int_dim = <Py_ssize_t>dim
                stride = stride * int_dim
                idx += 1
            assert idx == self.ndim
            self.len = stride * itemsize
        elif mode == "c":
            idx = self.ndim-1; stride = 1
            for dim in reversed(shape):
                self.strides[idx] = stride*itemsize
                int_dim = <Py_ssize_t>dim
                stride = stride * int_dim
                idx -= 1
            assert idx == -1
            self.len = stride * itemsize
        else:
            raise ValueError("Invalid mode, expected 'c' or 'fortran', got %s" % mode)

        self.mode = mode

        self.data = <char *>malloc(self.len)
        if not self.data:
            raise MemoryError("unable to allocate array data.")

    def __getbuffer__(self, Py_buffer *info, int flags):

        cdef int bufmode = -1
        if self.mode == "c":
            bufmode = PyBUF_C_CONTIGUOUS | PyBUF_ANY_CONTIGUOUS
        elif self.mode == "fortran":
            bufmode = PyBUF_F_CONTIGUOUS | PyBUF_ANY_CONTIGUOUS
        if not (flags & bufmode):
            raise ValueError("Can only create a buffer that is contiguous in memory.")
        info.buf = self.data
        info.len = self.len
        info.ndim = self.ndim
        info.shape = self.shape
        info.strides = self.strides
        info.suboffsets = NULL
        info.itemsize = self.itemsize
        info.format = self.format
        # we do not need to call releasebuffer
        info.obj = None

    def __releasebuffer__(array self, Py_buffer* info):
        # array.__releasebuffer__ should not be called, 
        # because the Py_buffer's 'obj' field is set to None.
        raise NotImplementedError()

    def __dealloc__(array self):
        if self.data:
            free(self.data)
            self.data = NULL
        if self.strides:
            free(self.strides)
            self.strides = NULL
        if self.shape:
            free(self.shape)
            self.shape = NULL
        self.format = NULL
        self.itemsize = 0

cdef array array_cwrapper(tuple shape, Py_ssize_t itemsize, char *format, char *mode):
    return array(shape, itemsize, format, mode)

''', prefix=cyarray_prefix)
