from Errors import PyrexError, CompileError, InternalError, error
import Errors
import DebugFlags

#
# Really small pipeline stages.
#
def dumptree(t):
    # For quick debugging in pipelines
    print t.dump()
    return t

def parse_stage_factory(context):
    def parse(compsrc):
        source_desc = compsrc.source_desc
        full_module_name = compsrc.full_module_name
        initial_pos = (source_desc, 1, 0)
        scope = context.find_module(full_module_name, pos = initial_pos, need_pxd = 0)
        tree = context.parse(source_desc, scope, pxd = 0, full_module_name = full_module_name)
        tree.compilation_source = compsrc
        tree.scope = scope
        tree.is_pxd = False
        return tree
    return parse

def parse_pxd_stage_factory(context, scope, module_name):
    def parse(source_desc):
        tree = context.parse(source_desc, scope, pxd=True,
                             full_module_name=module_name)
        tree.scope = scope
        tree.is_pxd = True
        return tree
    return parse

def generate_pyx_code_stage_factory(options, result):
    def generate_pyx_code_stage(module_node):
        module_node.process_implementation(options, result)
        result.compilation_source = module_node.compilation_source
        return result
    return generate_pyx_code_stage

def inject_pxd_code_stage_factory(context):
    def inject_pxd_code_stage(module_node):
        from textwrap import dedent
        stats = module_node.body.stats
        for name, (statlistnode, scope) in context.pxds.iteritems():
            module_node.merge_in(statlistnode, scope)
        return module_node
    return inject_pxd_code_stage

def inject_utility_code_stage(module_node):
    added = []
    # need to copy list as the list will be altered!
    for utilcode in module_node.scope.utility_code_list[:]:
        if utilcode in added: continue
        added.append(utilcode)
        tree = utilcode.get_tree()
        if tree:
            module_node.merge_in(tree.body, tree.scope, merge_scope=True)
    return module_node

#
# Pipeline factories
#

def create_pipeline(context, mode):
    assert mode in ('pyx', 'py', 'pxd')
    from Visitor import PrintTree
    from ParseTreeTransforms import WithTransform, NormalizeTree, PostParse, PxdPostParse
    from ParseTreeTransforms import AnalyseDeclarationsTransform, AnalyseExpressionsTransform
    from ParseTreeTransforms import CreateClosureClasses, MarkClosureVisitor, DecoratorTransform
    from ParseTreeTransforms import InterpretCompilerDirectives, TransformBuiltinMethods
    from ParseTreeTransforms import AlignFunctionDefinitions, GilCheck
    from AutoDocTransforms import EmbedSignature
    from Optimize import FlattenInListTransform, SwitchTransform, IterationTransform
    from Optimize import OptimizeBuiltinCalls, ConstantFolding, FinalOptimizePhase
    from Buffer import IntroduceBufferAuxiliaryVars
    from ModuleNode import check_c_declarations


    # Temporary hack that can be used to ensure that all result_code's
    # are generated at code generation time.
    import Visitor
    class ClearResultCodes(Visitor.CythonTransform):
        def visit_ExprNode(self, node):
            self.visitchildren(node)
            node.result_code = "<cleared>"
            return node

    if mode == 'pxd':
        _check_c_declarations = None
        _specific_post_parse = PxdPostParse(context)
    else:
        _check_c_declarations = check_c_declarations
        _specific_post_parse = None

    if mode == 'py':
        _align_function_definitions = AlignFunctionDefinitions(context)
    else:
        _align_function_definitions = None

    return [
        NormalizeTree(context),
        PostParse(context),
        _specific_post_parse,
        InterpretCompilerDirectives(context, context.pragma_overrides),
        _align_function_definitions,
        ConstantFolding(),
        FlattenInListTransform(),
        WithTransform(context),
        DecoratorTransform(context),
        AnalyseDeclarationsTransform(context),
        EmbedSignature(context),
        TransformBuiltinMethods(context),
        IntroduceBufferAuxiliaryVars(context),
        _check_c_declarations,
        AnalyseExpressionsTransform(context),
        OptimizeBuiltinCalls(),
        ConstantFolding(),
        IterationTransform(),
        SwitchTransform(),
        FinalOptimizePhase(context),
        GilCheck(),
    #            ClearResultCodes(context),
    #            SpecialFunctions(context),
        #        CreateClosureClasses(context),
        ]

def create_pyx_pipeline(context, options, result, py=False):
    if py:
        mode = 'py'
    else:
        mode = 'pyx'
    return ([
            parse_stage_factory(context),
        ] + create_pipeline(context, mode) + [
            inject_pxd_code_stage_factory(context),
            inject_utility_code_stage,
            generate_pyx_code_stage_factory(options, result),
        ])

def create_pxd_pipeline(context, scope, module_name):
    from CodeGeneration import ExtractPxdCode

    # The pxd pipeline ends up with a CCodeWriter containing the
    # code of the pxd, as well as a pxd scope.
    return [
        parse_pxd_stage_factory(context, scope, module_name)
        ] + create_pipeline(context, 'pxd') + [
        ExtractPxdCode(context)
        ]

def create_py_pipeline(context, options, result):
    return create_pyx_pipeline(context, options, result, py=True)

#
# Running a pipeline
#
def run_pipeline(pipeline, source):
    err = None
    data = source
    try:
        for phase in pipeline:
            if phase is not None:
                if DebugFlags.debug_verbose_pipeline:
                    print "Entering pipeline phase %r" % phase
                data = phase(data)
    except CompileError, err:
        # err is set
        Errors.report_error(err)
    except InternalError, err:
        # Only raise if there was not an earlier error
        if Errors.num_errors == 0:
            raise
    return (err, data)

