from Symtab import ModuleScope
from PyrexTypes import *
from UtilityCode import CythonUtilityCode
from Errors import error
from Scanning import StringSourceDescriptor
import Options

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
view_utility_code = CythonUtilityCode(u"""
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

    cdef Py_buffer view
    cdef int gotbuf_flag

    def __cinit__(memoryview self, object obj, int flags):
        __Pyx_GetBuffer(obj, &self.view, flags)

    def __dealloc__(memoryview self):
        __Pyx_ReleaseBuffer(&self.view)

cdef memoryview memoryview_cwrapper(object o, int flags):
    return memoryview(o, flags)

# XXX: put in #defines...
DEF BUF_MAX_NDIMS = %d
DEF __Pyx_MEMVIEW_DIRECT  = 1
DEF __Pyx_MEMVIEW_PTR     = 2
DEF __Pyx_MEMVIEW_FULL    = 4
DEF __Pyx_MEMVIEW_CONTIG  = 8
DEF __Pyx_MEMVIEW_STRIDED = 16
DEF __Pyx_MEMVIEW_FOLLOW  = 32

cdef extern from *:
    struct __pyx_obj_memoryview:
        Py_buffer view

    ctypedef struct __Pyx_mv_DimInfo:
        Py_ssize_t shape, strides, suboffsets

    ctypedef struct __Pyx_memviewslice:
        __pyx_obj_memoryview *memview
        char *data
        __Pyx_mv_DimInfo diminfo[BUF_MAX_NDIMS]

cdef is_cf_contig(int *specs, int ndim):

    is_c_contig = is_f_contig = False

    # c_contiguous: 'follow', 'follow', ..., 'follow', 'contig'
    if specs[ndim-1] & __Pyx_MEMVIEW_CONTIG:
        for i in range(0, ndim-1):
            if not (specs[i] & __Pyx_MEMVIEW_FOLLOW):
                break
        else:
            is_c_contig = True

    # f_contiguous: 'contig', 'follow', 'follow', ..., 'follow'
    elif ndim > 1 and (specs[0] & __Pyx_MEMVIEW_CONTIG):
        for i in range(1, ndim):
            if not (specs[i] & __Pyx_MEMVIEW_FOLLOW):
                break
        else:
            is_f_contig = True

    return is_c_contig, is_f_contig
    
cdef object init_memviewslice_from_memview(
        memoryview memview,
        int *axes_specs, 
        int ndim, 
        Py_ssize_t itemsize,
        char *format,
        __Pyx_memviewslice *memviewslice):

    cdef int i

    if ndim > BUF_MAX_NDIMS:
        raise ValueError("number of dimensions exceed maximum of" + str(BUF_MAX_NDIMS))
    
    cdef Py_buffer pybuf = memview.view
    if pybuf.ndim != ndim:
        raise ValueError("incompatible number of dimensions.")

    cdef str pyx_format = pybuf.format
    cdef str view_format = format
    if pyx_format != view_format:
        raise ValueError("Buffer and memoryview datatype formats do not match.")

    if itemsize != pybuf.itemsize:
        raise ValueError("Buffer and memoryview itemsize do not match.")

    if not pybuf.strides:
        raise ValueError("no stride information provided.")

    has_suboffsets = True
    if not pybuf.suboffsets:
        has_suboffsets = False

    is_c_contig, is_f_contig = is_cf_contig(axes_specs, ndim)

    cdef int spec = 0
    for i in range(ndim):
        istr = str(i)
        spec = axes_specs[i]
        if spec & __Pyx_MEMVIEW_CONTIG:
            if pybuf.strides[i] != 1:
                raise ValueError("Dimension "+istr+" in axes specification is incompatible with buffer.")
        if spec & (__Pyx_MEMVIEW_STRIDED | __Pyx_MEMVIEW_FOLLOW):
            if pybuf.strides[i] <= 1:
                raise ValueError("Dimension "+istr+" in axes specification is incompatible with buffer.")
        if spec & __Pyx_MEMVIEW_DIRECT:
            if has_suboffsets and pybuf.suboffsets[i] >= 0:
                raise ValueError("Dimension "+istr+" in axes specification is incompatible with buffer.")
        if spec & (__Pyx_MEMVIEW_PTR | __Pyx_MEMVIEW_FULL):
            if not has_suboffsets:
                raise ValueError("Buffer object does not provide suboffsets.")
        if spec & __Pyx_MEMVIEW_PTR:
            if pybuf.suboffsets[i] < 0:
                raise ValueError("Buffer object suboffset in dimension "+istr+"must be >= 0.")

    if is_f_contig:
        idx = 0; stride = 1
        for i in range(ndim):
            if stride != pybuf.strides[i]:
                raise ValueError("Buffer object not fortran contiguous.")
            stride = stride * pybuf.shape[i]
    elif is_c_contig:
        idx = ndim-1; stride = 1
        for i in range(ndim-1,-1,-1):
            if stride != pybuf.strides[i]:
                raise ValueError("Buffer object not C contiguous.")
            stride = stride * pybuf.shape[i]

    for i in range(ndim):
        memviewslice.diminfo[i].strides = pybuf.strides[i]
        memviewslice.diminfo[i].shape = pybuf.shape[i]
        if has_suboffsets:
            memviewslice.diminfo[i].suboffsets = pybuf.suboffsets[i]

    memviewslice.memview = <__pyx_obj_memoryview*>memview
    memviewslice.data = <char *>pybuf.buf

""" % Options.buffer_max_dims, name="foobar", prefix="__pyx_viewaxis_")

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
                self.strides[idx] = stride
                int_dim = <Py_ssize_t>dim
                stride = stride * int_dim
                idx += 1
            assert idx == self.ndim
            self.len = stride * self.itemsize
        elif mode == "c":
            idx = self.ndim-1; stride = 1
            for dim in reversed(shape):
                self.strides[idx] = stride
                int_dim = <Py_ssize_t>dim
                stride = stride * int_dim
                idx -= 1
            assert idx == -1
            self.len = stride * self.itemsize
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
''', prefix=cyarray_prefix)
